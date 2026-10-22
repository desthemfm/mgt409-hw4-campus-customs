"""Campus Customs backend: the FastAPI app that Uvicorn runs.

Routes for the product catalogue and images, shopper accounts, and the chat concierge.
The agent itself lives in the files next to this one:
    agent.py          builds the PydanticAI agent and wires its tools
    tools.py          the tools (and shared database helpers)
    models.py         Pydantic / PydanticAI structured types
    prompts/prompt.md the system prompt
Passwords are hashed with Argon2id (see "Passwords and login protection" below).

Run from the backend folder (with the virtual environment activated):
    cd backend
    source .venv/bin/activate
    uvicorn main:app --reload --port 8000
--reload restarts the server whenever a .py file changes. The front end's dev server
forwards /api and /media requests here (see frontend/vite.config.ts).
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sqlite3
import threading
import time
from collections import deque
from collections.abc import Iterator
from contextlib import asynccontextmanager, closing
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic_ai.exceptions import AgentRunError, ModelHTTPError, UsageLimitExceeded
from starlette.middleware.sessions import SessionMiddleware

load_dotenv(Path(__file__).resolve().parent.parent / ".env")  # the project's .env (see .env.example)

# These read settings from .env, so they are imported after load_dotenv.
import agent  # noqa: E402
import tools  # noqa: E402
from models import (  # noqa: E402
    Category,
    ChatMessageOut,
    ChatRequest,
    ChatReply,
    ChatTurn,
    MAX_PASSWORD_LENGTH,
    LoginRequest,
    ProductDetail,
    ProductCard,
    SignupRequest,
    UserOut,
)

log = logging.getLogger("campus_customs")


# ---------- Passwords and login protection ----------
#
# Passwords are never stored. We store an Argon2id hash: a slow, memory-hungry one-way
# function with a random salt per user. Even with a full copy of the database, an attacker
# (human or AI) would have to guess each password separately, and every guess costs real
# time and memory.

# argon2-cffi defaults (RFC 9106 "low memory" profile): 3 passes, 64 MiB, 4 lanes, 16-byte salt.
# That is stronger than the OWASP minimum for Argon2id (2 passes, 19 MiB).
_hasher = PasswordHasher()

# Used when the email isn't found, so "no such user" takes as long as "wrong password".
# Otherwise an attacker could time responses to learn which emails have accounts.
_DUMMY_HASH = _hasher.hash("not-a-real-password")

# The sample users in the course data pack were hashed by the course's original app as
# pbkdf2_sha256$<salt>$<hex> with 120,000 iterations (from the course materials; the format
# itself doesn't record the count). After a successful login their hash is upgraded to Argon2id.
_LEGACY_ITERATIONS = int(os.getenv("PBKDF2_LEGACY_ITERATIONS") or 120_000)

MIN_PASSWORD_LENGTH = 8

# A short list of the most common passwords. NIST SP 800-63B says to reject known-breached
# passwords rather than force symbols and digits.
_COMMON_PASSWORDS = {
    "password", "password1", "password123", "12345678", "123456789", "1234567890", "qwerty123",
    "qwertyuiop", "iloveyou", "11111111", "00000000", "abc12345", "letmein1", "welcome1",
    "football", "baseball", "sunshine", "princess", "trustno1", "passw0rd", "admin123",
    "yale1701", "yaleuniversity", "bulldogs", "handsomedan", "boolaboola", "newhaven",
}


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored_hash: str | None, password: str) -> bool:
    """True if `password` matches `stored_hash`. Always does the same amount of work for missing users."""
    if stored_hash is None:
        _safe_verify(_DUMMY_HASH, password)
        return False
    if stored_hash.startswith("pbkdf2_sha256$"):
        return _verify_legacy_pbkdf2(stored_hash, password)
    return _safe_verify(stored_hash, password)


def needs_rehash(stored_hash: str) -> bool:
    """True for legacy PBKDF2 hashes or Argon2 hashes made with weaker settings than today's."""
    if not stored_hash.startswith("$argon2"):
        return True
    return _hasher.check_needs_rehash(stored_hash)


def _safe_verify(stored_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(stored_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def _verify_legacy_pbkdf2(stored_hash: str, password: str) -> bool:
    try:
        _, salt, expected_hex = stored_hash.split("$")
    except ValueError:
        return False
    if not _LEGACY_ITERATIONS:
        _safe_verify(_DUMMY_HASH, password)  # same timing as any other failure
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _LEGACY_ITERATIONS)
    return hmac.compare_digest(digest.hex(), expected_hex)  # constant-time comparison


def password_problem(password: str, *, email: str = "", first_name: str = "", last_name: str = "") -> str | None:
    """Return a human-readable reason the password is too weak, or None if it's acceptable."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    if len(password) > MAX_PASSWORD_LENGTH:
        return f"Password must be at most {MAX_PASSWORD_LENGTH} characters."
    lowered = password.lower()
    if lowered in _COMMON_PASSWORDS or len(set(password)) <= 2:
        return "That password is too common. Please choose something less guessable."
    personal = [email.split("@")[0].lower(), first_name.lower(), last_name.lower()]
    if any(p and len(p) >= 3 and p in lowered and len(lowered) - len(p) < 4 for p in personal):
        return "Please don't base your password on your name or email."
    return None


EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def normalize_email(email: str) -> str:
    return email.strip().lower()


class LoginRateLimiter:
    """Slows down password guessing: after too many failures, that email or IP must wait.

    In-memory, so it resets when the server restarts. That's fine for one server; a
    multi-server deployment would keep these counters in a shared store such as Redis.
    """

    def __init__(self, max_failures: int, window_seconds: int):
        self.max_failures = max_failures
        self.window = window_seconds
        self._failures: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> deque[float]:
        times = self._failures.setdefault(key, deque())
        while times and now - times[0] > self.window:
            times.popleft()
        return times

    def retry_after(self, *keys: str) -> int:
        """Seconds until the caller may try again, or 0 if allowed now."""
        now = time.monotonic()
        with self._lock:
            waits = []
            for key in keys:
                times = self._recent(key, now)
                if len(times) >= self.max_failures:
                    waits.append(int(self.window - (now - times[0])) + 1)
            return max(waits, default=0)

    def record_failure(self, *keys: str) -> None:
        now = time.monotonic()
        with self._lock:
            for key in keys:
                self._recent(key, now).append(now)

    def reset(self, *keys: str) -> None:
        with self._lock:
            for key in keys:
                self._failures.pop(key, None)

IMAGE_DIRS = tools.IMAGE_DIRS  # white-background web copies first, originals as a fallback

@asynccontextmanager
async def lifespan(_: FastAPI):
    """Runs once at startup.

    1. Prepares the course data pack's database if it hasn't been yet (the Problem 2 cleanup:
       category column, fixed names and placeholder descriptions). Safe to run every time.
    2. Saved chats are always read per shopper, newest first, so an index on (user_id, id)
       keeps reloading history fast as it grows.
    """
    if not tools.DB_PATH.exists():
        raise RuntimeError(f"Database not found at {tools.DB_PATH}. Unzip the course data pack into data/ (see README.md).")
    if tools.prepare_database():
        log.warning("Prepared the data pack database (Problem 2 cleanup applied).")
    with closing(tools.connect()) as con, con:
        con.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_user ON chat_messages (user_id, id)")
    yield


app = FastAPI(title="Campus Customs API", lifespan=lifespan)

SESSION_SECRET = os.getenv("SESSION_SECRET") or ""
if not SESSION_SECRET:
    # Still safe, but everyone is logged out whenever the server restarts.
    log.warning("SESSION_SECRET is not set in .env; using a temporary random secret.")
    SESSION_SECRET = secrets.token_urlsafe(48)

# The login cookie is signed (it can't be forged or edited) and only holds the user's id.
# HttpOnly keeps page scripts, and anything injected into the page, from reading it.
# SameSite=Lax stops other websites from sending it with forged requests.
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie="cc_session",
    max_age=7 * 24 * 60 * 60,  # one week
    same_site="lax",
    https_only=os.getenv("COOKIE_SECURE", "false").lower() == "true",
)

# 5 wrong passwords for one email (or 20 from one network address) means a 15-minute wait.
email_limiter = LoginRateLimiter(max_failures=5, window_seconds=15 * 60)
ip_limiter = LoginRateLimiter(max_failures=20, window_seconds=15 * 60)
# Each chat message costs a paid AI call, so cap it: 20 messages per 5 minutes per shopper.
chat_limiter = LoginRateLimiter(max_failures=20, window_seconds=5 * 60)


def get_db() -> Iterator[sqlite3.Connection]:
    con = tools.connect()
    try:
        yield con
    finally:
        con.close()


# ---------- Products ----------

@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/categories", response_model=list[Category])
def list_categories(db: sqlite3.Connection = Depends(get_db)) -> list[Category]:
    return [Category(name=c.name, count=c.count) for c in tools.list_categories(db)]


@app.get("/api/products", response_model=list[ProductCard])
def list_products(
    category: str | None = Query(None, description="Exact category, e.g. Hoodies"),
    q: str | None = Query(None, description="Keyword to match in name, description, colors, or tags"),
    db: sqlite3.Connection = Depends(get_db),
) -> list[ProductCard]:
    return tools.list_products(db, category, q)


@app.get("/api/products/{product_id}", response_model=ProductDetail)
def get_product(product_id: str, db: sqlite3.Connection = Depends(get_db)) -> ProductDetail:
    detail = tools.get_product_detail(db, product_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return detail


@app.get("/media/products/{filename}")
def product_image(filename: str) -> FileResponse:
    for folder in IMAGE_DIRS:
        path = (folder / filename).resolve()
        # Refuse anything that escapes the image folder (e.g. "..%2Fcampus_customs.db")
        if path.parent == folder.resolve() and path.is_file():
            # Product photo URLs carry ?v=<last-modified> (tools.image_url), so a re-cleaned photo
            # gets a new URL. That makes long browser caching safe.
            return FileResponse(path, headers={"Cache-Control": "public, max-age=604800"})
    raise HTTPException(status_code=404, detail="Image not found")


# ---------- Accounts ----------

USER_COLUMNS = "id, name, email, first_name, last_name, created_at"


def to_user(row: sqlite3.Row) -> UserOut:
    # Older rows may have NULL first/last names, so fall back to splitting `name`.
    first, _, last = row["name"].partition(" ")
    return UserOut(
        id=row["id"],
        first_name=row["first_name"] or first,
        last_name=row["last_name"] or last,
        name=row["name"],
        email=row["email"],
        created_at=row["created_at"],
    )


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@app.post("/api/auth/signup", response_model=UserOut, status_code=201)
def signup(body: SignupRequest, request: Request, db: sqlite3.Connection = Depends(get_db)) -> UserOut:
    first, last = body.first_name.strip(), body.last_name.strip()
    email = normalize_email(body.email)
    if not first or not last:
        raise HTTPException(422, "Please enter your first and last name.")
    if not EMAIL_RE.match(email):
        raise HTTPException(422, "Please enter a valid email address.")
    if body.password != body.confirm_password:
        raise HTTPException(422, "The passwords do not match.")
    problem = password_problem(body.password, email=email, first_name=first, last_name=last)
    if problem:
        raise HTTPException(422, problem)

    password_hash = hash_password(body.password)
    try:
        with db:  # one transaction: commits on success, rolls back on error
            cur = db.execute(
                "INSERT INTO users (name, email, password_hash, first_name, last_name) VALUES (?, ?, ?, ?, ?)",
                (f"{first} {last}", email, password_hash, first, last),
            )
    except sqlite3.IntegrityError:
        raise HTTPException(409, "An account with this email already exists. Try logging in instead.")

    row = db.execute(f"SELECT {USER_COLUMNS} FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
    request.session.clear()
    request.session["user_id"] = row["id"]
    log.info("New account created: user id %s", row["id"])  # never log emails or passwords
    return to_user(row)


@app.post("/api/auth/login", response_model=UserOut)
def login(body: LoginRequest, request: Request, db: sqlite3.Connection = Depends(get_db)) -> UserOut:
    email = normalize_email(body.email)
    email_key, ip_key = f"email:{email}", f"ip:{client_ip(request)}"

    wait = max(email_limiter.retry_after(email_key), ip_limiter.retry_after(ip_key))
    if wait:
        minutes = max(1, round(wait / 60))
        raise HTTPException(
            429,
            f"Too many failed attempts. Please wait about {minutes} minute{'s' if minutes > 1 else ''} and try again.",
            headers={"Retry-After": str(wait)},
        )

    row = db.execute(f"SELECT {USER_COLUMNS}, password_hash FROM users WHERE email = ?", (email,)).fetchone()
    if not verify_password(row["password_hash"] if row else None, body.password):
        email_limiter.record_failure(email_key)
        ip_limiter.record_failure(ip_key)
        # Same message whether the email exists or not, so attackers can't use this form
        # to find out who has an account.
        raise HTTPException(401, "Incorrect email or password.")

    email_limiter.reset(email_key)
    if needs_rehash(row["password_hash"]):
        with db:  # upgrade old or weaker hashes to today's Argon2id settings
            db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(body.password), row["id"]))

    request.session.clear()  # fresh session on login
    request.session["user_id"] = row["id"]
    return to_user(row)


@app.post("/api/auth/logout", status_code=204)
def logout(request: Request) -> None:
    request.session.clear()


def current_user(request: Request, db: sqlite3.Connection = Depends(get_db)) -> UserOut | None:
    user_id = request.session.get("user_id")
    if user_id is None:
        return None
    row = db.execute(f"SELECT {USER_COLUMNS} FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:  # account was deleted
        request.session.clear()
        return None
    return to_user(row)


@app.get("/api/auth/me", response_model=UserOut | None)
def me(user: UserOut | None = Depends(current_user)) -> UserOut | None:
    """The logged-in shopper, or null if nobody is logged in."""
    return user


# ---------- Chat ----------

def saved_history(db: sqlite3.Connection, user_id: int, limit: int) -> list[sqlite3.Row]:
    rows = db.execute(
        "SELECT id, role, content, products_json, created_at FROM chat_messages "
        "WHERE user_id = ? ORDER BY id DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    return rows[::-1]  # oldest first


def prepare_chat(body: ChatRequest, request: Request, user: UserOut | None, db: sqlite3.Connection):
    """Checks and context shared by the normal and the streaming chat routes."""
    message = body.message.strip()
    if not message:
        raise HTTPException(422, "Please type a message.")

    limit_key = f"user:{user.id}" if user else f"ip:{client_ip(request)}"
    wait = chat_limiter.retry_after(limit_key)
    if wait:
        raise HTTPException(429, "You're sending messages quickly. Please wait a moment and try again.",
                            headers={"Retry-After": str(wait)})
    chat_limiter.record_failure(limit_key)  # counts every message, not just failures

    # Signed-in shoppers: history comes from the database, never from the browser.
    # Guests: the browser sends its own recent messages, which only affect their own chat.
    if user:
        history = [ChatTurn(role=r["role"], content=r["content"]) for r in saved_history(db, user.id, agent.HISTORY_TURNS)]
    else:
        history = body.history

    # Who is chatting comes only from the signed-in session; what they're looking at is rebuilt
    # from the database using the ids the browser sent (unknown ids are dropped).
    shopper = (
        tools.Shopper(user.id, user.first_name, user.last_name, user.email, user.created_at) if user else None
    )
    deps = tools.AgentDeps(
        shopper=shopper,
        page=tools.build_page_view(db, body.page),
        cart=tools.clean_cart(db, body.cart),  # only real products and sizes
    )
    return message, history, deps


def agent_error_message(err: Exception) -> str:
    if isinstance(err, UsageLimitExceeded):
        log.warning("Chat hit the usage limit")
        return "Sorry, that question got a bit tangled. Could you ask it a simpler way?"
    if isinstance(err, (ModelHTTPError, AgentRunError)):
        log.error("Agent error: %s", type(err).__name__)
    else:  # network failures, timeouts, gateway outages
        log.exception("Unexpected agent failure: %s", type(err).__name__)
    return "Our concierge is momentarily unavailable. Please try again in a minute."


def finish_chat(output, deps: tools.AgentDeps, message: str, user: UserOut | None, db: sqlite3.Connection) -> ChatReply:
    """Turn the agent's checked answer into live product cards, and save signed-in exchanges."""
    # Product cards are rebuilt from the live database, so prices on cards are always current.
    products = tools.get_cards(db, output.product_ids)
    if user:
        with db:  # save both sides of the exchange together, or neither
            db.execute(
                "INSERT INTO chat_messages (user_id, role, content, products_json) VALUES (?, 'user', ?, NULL)",
                (user.id, message),
            )
            db.execute(
                "INSERT INTO chat_messages (user_id, role, content, products_json) VALUES (?, 'assistant', ?, ?)",
                (user.id, output.reply, json.dumps([p.model_dump() for p in products])),
            )
    heading = output.results_heading.strip() if output.results_heading and products else None
    # Cart changes the agent made through its cart tools; the website applies them to the browser cart.
    return ChatReply(reply=output.reply, products=products, results_heading=heading, cart_actions=deps.cart_actions)


@app.post("/api/chat", response_model=ChatReply)
async def chat(
    body: ChatRequest,
    request: Request,
    user: UserOut | None = Depends(current_user),
    db: sqlite3.Connection = Depends(get_db),
) -> ChatReply:
    """Send one shopper message to the agent and return its whole reply plus product cards."""
    message, history, deps = prepare_chat(body, request, user, db)
    try:
        output = await agent.run_chat(message, history, deps, route="/api/chat")
    except Exception as err:
        raise HTTPException(503, agent_error_message(err))
    return finish_chat(output, deps, message, user, db)


@app.post("/api/chat/stream")
async def chat_stream(
    body: ChatRequest,
    request: Request,
    user: UserOut | None = Depends(current_user),
    db: sqlite3.Connection = Depends(get_db),
) -> StreamingResponse:
    """Same as /api/chat, but streams progress and the reply as it is written (Problem 9).

    The response is NDJSON: one JSON event per line.
      {"type": "status", "text": "Checking sizes and stock…"}   the agent is using a tool
      {"type": "delta",  "reply": "<reply so far>"}             the reply as it is being written (a draft)
      {"type": "reset"}                                         the honesty check sent the draft back; start over
      {"type": "done",   ...ChatReply}                          the checked, final answer, plus product cards
      {"type": "error",  "detail": "..."}                       something went wrong
    The final answer always goes through the same honesty check and saving as /api/chat.
    """
    message, history, deps = prepare_chat(body, request, user, db)  # errors here are normal HTTP errors

    async def events():
        queue: asyncio.Queue[dict | None] = asyncio.Queue()

        async def run() -> None:
            try:
                output = await agent.run_chat(message, history, deps, on_event=queue.put_nowait, route="/api/chat/stream")
                # A fresh connection: the request's own one may be closed once streaming starts.
                with closing(tools.connect()) as con:
                    reply = finish_chat(output, deps, message, user, con)
                queue.put_nowait({"type": "done", **reply.model_dump()})
            except Exception as err:
                queue.put_nowait({"type": "error", "detail": agent_error_message(err)})
            finally:
                queue.put_nowait(None)

        task = asyncio.create_task(run())
        try:
            while (event := await queue.get()) is not None:
                yield json.dumps(event) + "\n"
        finally:
            if not task.done():  # the shopper closed the page mid-answer
                task.cancel()

    # X-Accel-Buffering stops proxies from holding back the stream; no-cache keeps it live.
    return StreamingResponse(events(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/chat/history", response_model=list[ChatMessageOut])
def chat_history(
    user: UserOut | None = Depends(current_user), db: sqlite3.Connection = Depends(get_db)
) -> list[ChatMessageOut]:
    """The signed-in shopper's recent conversation (empty for guests)."""
    if not user:
        return []
    rows = saved_history(db, user.id, 30)
    ids = [p["product_id"] for r in rows if r["products_json"] for p in json.loads(r["products_json"])]
    live = {p.product_id: p for p in tools.get_cards(db, ids)}  # refresh saved cards with live prices
    return [
        ChatMessageOut(
            id=r["id"],
            role=r["role"],
            content=r["content"],
            products=[live[p["product_id"]] for p in json.loads(r["products_json"] or "[]") if p["product_id"] in live],
            created_at=r["created_at"],
        )
        for r in rows
    ]
