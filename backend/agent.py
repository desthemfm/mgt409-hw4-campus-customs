"""Campus Customs shopping agent: builds the PydanticAI agent and wires up its tools.

main.py calls `run_chat()` from the /api/chat route. This file:
  1. builds the agent (model + system prompt from prompts/prompt.md + tools),
  2. "wires" each tool: registers a small function so the AI may call it. The real work
     lives in tools.py.
  3. checks the agent's final answer, so it can only quote prices and products that a
     tool actually returned in this conversation.

Try it from the terminal (from the backend folder, virtual environment activated):
    python agent.py "Do you have a gray hoodie under $70?"
"""

import asyncio
import fcntl
import json
import logging
import os
import re
import sys
import threading
import time
import uuid
from collections.abc import AsyncIterable, Callable
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from pydantic_ai import Agent, ModelRetry, RunContext, capture_run_messages
from pydantic_ai.exceptions import ModelHTTPError, UsageLimitExceeded
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    RetryPromptPart,
    ToolReturnPart,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    ToolCallPart,
    ToolCallPartDelta,
    UserPromptPart,
)
from pydantic_core import from_json
from pydantic_ai.usage import UsageLimits

import tools
from models import (
    AuditEntry,
    AuditToolCall,
    CartToolResult,
    CartView,
    CategoryInfo,
    ChatTurn,
    ProductInfo,
    ProductNotFound,
    RecallResult,
    SearchResult,
    ShopperProfile,
    ShopperReply,
    SizeNotCarried,
    StockCheck,
)

PROMPT_FILE = Path(__file__).resolve().parent / "prompts" / "prompt.md"
HISTORY_TURNS = 12  # how many earlier messages the agent sees (keeps cost and latency down)
# Hard ceiling per chat message: at most 8 model calls and 10 tool calls, so a confused
# or manipulated conversation can't loop forever or run up the bill.
LIMITS = UsageLimits(request_limit=8, tool_calls_limit=10)

def describe_context(deps: tools.AgentDeps) -> str:
    """The "who and where" briefing added to the system prompt for every message.

    Built only from server-side facts: the signed-in session (not anything the shopper typed)
    and products looked up in the database (the browser only sends ids).
    """
    lines = ["## Right now"]
    sh = deps.shopper
    if sh:
        lines += [
            f"- **Shopper:** signed in as {sh.full_name} (first name {sh.first_name}), email {sh.email}, "
            f"member since {sh.member_since[:10]}. Their saved conversation history is included above this turn.",
        ]
    else:
        lines.append("- **Shopper:** a guest (not signed in). Nothing is saved; you don't know their name or email.")

    page = deps.page
    if page is None or page.page_type == "other":
        lines.append("- **Page:** unknown.")
    elif page.product:
        p = page.product
        lines += [
            f"- **Page:** the product page for **{p.name}** (product_id `{p.product_id}`, {p.category}, {p.garment_type}).",
            f"  Colors on this piece: {', '.join(p.colors_on_item) or 'not listed'}. It comes in this one colorway only.",
            '  "This", "it", "this one" or "this hoodie" means this product unless they clearly mean something else.',
            "  For its price or stock, still call get_product_info / check_size_stock.",
        ]
    else:
        names = {"home": "the home page", "products": "the Products page", "about": "the About Us page", "cart": "their cart"}
        where = names.get(page.page_type, page.path)
        if page.category_filter:
            where += f", filtered to {page.category_filter}"
        lines.append(f"- **Page:** {where}.")
    if page and page.results:
        listed = "; ".join(f"{i}. {r.name} (`{r.product_id}`)" for i, r in enumerate(page.results, 1))
        # Only database product names go into the instructions. The heading text comes from the
        # browser, so it is left out: free text from the client must never become instructions.
        lines.append(
            f"- **Concierge results on the page**, in order: {listed}. "
            '"The second one", "the last one" and so on refer to this list.'
        )
    return "\n".join(lines)


def load_prompt() -> str:
    return PROMPT_FILE.read_text(encoding="utf-8")


PRICE_RE = re.compile(r"\$\s?(\d{1,4}(?:,\d{3})*(?:\.\d{1,2})?)")
# Numbers stated as stock: "only 2 left", "25 in stock", "15 available", "3 remaining".
QUANTITY_RE = re.compile(
    r"\bonly\s+(?P<a>\d{1,4})\b"
    r"|\b(?P<b>\d{1,4})\s+(?:left|in stock|available|remaining|on hand|units?|pieces? left)\b",
    re.IGNORECASE,
)


def stated_quantities(text: str) -> list[int]:
    return [int(m.group("a") or m.group("b")) for m in QUANTITY_RE.finditer(text)]


# "I've added…to your cart", "it's in your cart now", "placed it in your bag"
CART_CLAIM_RE = re.compile(
    r"\b(?:added|I've put|I have put|placed|popped)\b[^.!?]{0,80}\b(?:cart|bag)\b|\b(?:is|are) (?:now )?in your (?:cart|bag)\b",
    re.IGNORECASE,
)
SOLD_OUT_RE = re.compile(r"sold[ -]out|out of stock|none left|no longer (?:have|available)|unavailable", re.IGNORECASE)


def build_agent(model=None) -> Agent[tools.AgentDeps, ShopperReply]:
    agent = Agent(
        model or tools.make_model(),  # gpt-6-astra via Portkey, settings from backend/.env
        deps_type=tools.AgentDeps,
        output_type=ShopperReply,  # structured output: reply text + product ids for cards
        retries=2,
    )

    # The system prompt, read from prompts/prompt.md on every chat. Edits to the prompt
    # take effect on the next message, with no server restart (uvicorn --reload only
    # watches .py files).
    @agent.instructions
    def system_prompt() -> str:
        return load_prompt()

    # Extra instructions that change per chat: who is shopping and what they're looking at.
    @agent.instructions
    def shopper_and_page_context(ctx: RunContext[tools.AgentDeps]) -> str:
        return describe_context(ctx.deps)

    # Wiring: @agent.tool tells PydanticAI "the AI may call this function". The AI sees
    # the name, docstring, and parameters, decides when to call it, and gets the result back.
    @agent.tool
    def search_products(
        ctx: RunContext[tools.AgentDeps],
        query: str,
        category: str | None = None,
        max_price: float | None = None,
        size: str | None = None,
    ) -> SearchResult:
        """Search the Campus Customs catalogue. Returns up to 8 best matches with live price and sizes in stock.

        Args:
            query: The shopper's key words, e.g. "gray bulldog hoodie", "mom", "Berkeley college", "hockey".
            category: Optional exact category: T-Shirts, Crewnecks, Hoodies, Quarter-Zips, Jackets, or Long Sleeves.
            max_price: Optional budget in US dollars; only items at or below this price.
            size: Optional size (XS, S, M, L, XL, XXL); only items with that size in stock.
        """
        return tools.search_catalogue(ctx.deps, query, category, max_price, size)

    @agent.tool
    def get_product_info(ctx: RunContext[tools.AgentDeps], product: str) -> ProductInfo | ProductNotFound:
        """Look up one product's description, price, and live stock in every size (XS-XXL).

        Call this for any question about a product's price, description, colors, or which sizes are available.

        Args:
            product: The product_id from search_products (preferred), or the product's name.
        """
        return tools.product_info(ctx.deps, product)

    @agent.tool
    def check_size_stock(
        ctx: RunContext[tools.AgentDeps], product: str, size: str
    ) -> StockCheck | ProductNotFound | SizeNotCarried:
        """Check live stock for ONE size of one product. Tells you if it is sold out, low (1-5 left), or in stock.

        Call this whenever the shopper asks about a specific size ("do you have this in a large?").

        Args:
            product: The product_id from search_products (preferred), or the product's name.
            size: The size as the shopper said it, e.g. "L", "large", "XXL", "2XL".
        """
        return tools.stock_for_size(ctx.deps, product, size)

    @agent.tool
    def get_my_profile(ctx: RunContext[tools.AgentDeps]) -> ShopperProfile | str:
        """The signed-in shopper's own account: name, email, member-since date, and how many messages are saved.

        Only for the person chatting; there is no way to look up anyone else.
        """
        return tools.shopper_profile(ctx.deps)

    @agent.tool
    def recall_past_chats(ctx: RunContext[tools.AgentDeps], query: str) -> RecallResult:
        """Search this signed-in shopper's earlier saved conversations (including past visits).

        Use it when they refer to something from before: "the hoodie you showed me last time",
        "what did I ask about for my grandmother?".

        Args:
            query: Key words to look for, e.g. "grandmother", "fleece", "Berkeley".
        """
        return tools.recall_chats(ctx.deps, query)

    @agent.tool
    def add_to_cart(
        ctx: RunContext[tools.AgentDeps], product: str, size: str, quantity: int = 1
    ) -> CartToolResult | ProductNotFound | SizeNotCarried:
        """Put a piece in the shopper's cart. Only when they clearly ask ("add it", "I'll take a medium").

        Checks live stock and never adds more than we have. If they haven't said a size, ask first; don't guess.

        Args:
            product: The product_id (preferred) or the product's name.
            size: XS, S, M, L, XL, or XXL (everyday words like "large" work too).
            quantity: How many to add (1-10). Defaults to 1.
        """
        return tools.add_to_cart(ctx.deps, product, size, quantity)

    @agent.tool
    def remove_from_cart(
        ctx: RunContext[tools.AgentDeps], product: str, size: str, quantity: int | None = None
    ) -> CartToolResult | ProductNotFound | SizeNotCarried:
        """Take a piece out of the shopper's cart, when they ask.

        Args:
            product: The product_id (preferred) or the product's name.
            size: The size to remove.
            quantity: How many to remove; leave empty to remove that size entirely.
        """
        return tools.remove_from_cart(ctx.deps, product, size, quantity)

    @agent.tool
    def view_cart(ctx: RunContext[tools.AgentDeps]) -> CartView:
        """What is in the shopper's cart right now, with live prices, a subtotal, and any stock problems."""
        return tools.view_cart(ctx.deps)

    @agent.tool
    def list_categories(ctx: RunContext[tools.AgentDeps]) -> list[CategoryInfo]:
        """The shop's categories with how many products each has and their price range."""
        return tools.categories(ctx.deps)

    # Honesty check on the final answer, before the shopper ever sees it.
    @agent.output_validator
    def only_real_prices_and_products(ctx: RunContext[tools.AgentDeps], output: ShopperReply) -> ShopperReply:
        if CART_CLAIM_RE.search(output.reply) and not any(a.action == "add" for a in ctx.deps.cart_actions):
            raise ModelRetry(
                "The reply says something was added to the cart, but add_to_cart did not add anything this turn. "
                "Call add_to_cart (and check it succeeded), or don't claim it was added."
            )
        unknown_ids = [p for p in output.product_ids if p not in ctx.deps.seen_product_ids]
        if unknown_ids:
            raise ModelRetry(
                f"product_ids {unknown_ids} were not returned by any tool. Look them up first, or remove them."
            )
        not_said = [f"{name} in {size}" for name, size in ctx.deps.sold_out_checks if not SOLD_OUT_RE.search(output.reply)]
        if not_said:
            raise ModelRetry(
                f"A stock check showed {', '.join(not_said)} is sold out. Tell the shopper clearly that it's sold out "
                "in that size, then offer the sizes that are in stock."
            )
        made_up_qty = sorted(
            n for n in stated_quantities(output.reply) if n not in ctx.deps.seen_quantities
        )
        if made_up_qty:
            raise ModelRetry(
                f"The reply states stock quantities {made_up_qty} that no tool returned in this turn. "
                "Call get_product_info or check_size_stock, and quote only the quantities they return."
            )
        quoted = {float(m.replace(",", "")) for m in PRICE_RE.findall(output.reply)}
        allowed = {round(p * n, 2) for p in ctx.deps.seen_prices for n in range(1, 11)}  # a price, or a few of one item
        allowed |= ctx.deps.shopper_amounts  # e.g. repeating the shopper's own "under $60" budget
        made_up = sorted(q for q in quoted if round(q, 2) not in allowed)
        if made_up:
            raise ModelRetry(
                f"The reply quotes {', '.join(f'${q:g}' for q in made_up)}, which no tool returned. "
                "Only quote prices from tool results; call a tool to look them up if needed."
            )
        return output

    return agent


@lru_cache(maxsize=1)
def get_agent() -> Agent[tools.AgentDeps, ShopperReply]:
    """Build the agent once and reuse it for every chat."""
    return build_agent()


def to_message_history(turns: list[ChatTurn]) -> list[ModelMessage]:
    """Turn saved (role, text) pairs into PydanticAI's message format."""
    history: list[ModelMessage] = []
    for t in turns[-HISTORY_TURNS:]:
        if t.role == "user":
            history.append(ModelRequest(parts=[UserPromptPart(content=t.content)]))
        else:
            history.append(ModelResponse(parts=[TextPart(content=t.content)]))
    # A history that starts with an assistant message confuses some models; drop leading ones.
    while history and isinstance(history[0], ModelResponse):
        history.pop(0)
    return history


# ---------- Streaming (Problem 9) ----------

# What the shopper sees while each tool runs, instead of a silent typing indicator.
TOOL_STATUS = {
    "search_products": "Searching the collection…",
    "get_product_info": "Looking up the details…",
    "check_size_stock": "Checking sizes and stock…",
    "list_categories": "Looking over the collection…",
    "get_my_profile": "Checking your account…",
    "recall_past_chats": "Looking back through our earlier chats…",
    "add_to_cart": "Adding it to your cart…",
    "remove_from_cart": "Updating your cart…",
    "view_cart": "Looking at your cart…",
}
OUTPUT_TOOL = "final_result"  # the tool PydanticAI uses to return the structured ShopperReply


class ReplyStreamer:
    """Turns PydanticAI's raw stream events into simple events for the website.

    The final answer arrives as a JSON tool call ({"reply": "...", "product_ids": [...]}) that
    is streamed in small pieces. We parse the partial JSON as it grows and pass on the
    "reply" text written so far.
    """

    def __init__(self, emit: Callable[[dict], None]):
        self.emit = emit
        self.output_part: int | None = None  # index of the final_result tool call being streamed
        self.buffer = ""
        self.sent = ""
        self.drafts = 0
        self.last_status = ""

    def _status(self, tool_name: str) -> None:
        status = TOOL_STATUS.get(tool_name)
        if status and status != self.last_status:  # a tool is announced as it is written and as it runs
            self.last_status = status
            self.emit({"type": "status", "text": status})

    async def handle(self, _ctx: RunContext, events: AsyncIterable) -> None:
        async for ev in events:
            if isinstance(ev, PartStartEvent) and isinstance(ev.part, ToolCallPart):
                if ev.part.tool_name == OUTPUT_TOOL:
                    if self.drafts:  # the honesty check rejected the last draft; it is being rewritten
                        self.emit({"type": "reset"})
                    self.drafts += 1
                    self.output_part, self.buffer, self.sent = ev.index, "", ""
                    self._add(ev.part.args)
                else:
                    self._status(ev.part.tool_name)
            elif isinstance(ev, PartDeltaEvent) and ev.index == self.output_part and isinstance(ev.delta, ToolCallPartDelta):
                self._add(ev.delta.args_delta)
            elif isinstance(ev, FunctionToolCallEvent):
                self._status(ev.part.tool_name)

    def _add(self, piece: str | dict | None) -> None:
        if isinstance(piece, dict):  # some models send whole arguments at once
            self.buffer = json.dumps(piece)
        elif piece:
            self.buffer += piece
        try:
            # "trailing-strings" keeps the unfinished reply text; plain allow_partial would drop it.
            partial = from_json(self.buffer, allow_partial="trailing-strings")
        except ValueError:
            return
        reply = partial.get("reply") if isinstance(partial, dict) else None
        if isinstance(reply, str) and len(reply) > len(self.sent):
            self.sent = reply
            self.emit({"type": "delta", "reply": reply})


async def run_chat(
    message: str,
    history: list[ChatTurn],
    deps: tools.AgentDeps,
    on_event: Callable[[dict], None] | None = None,
    route: str = "agent.py",
) -> ShopperReply:
    """Run the agent on one message, and append what happened to output/audit_trail.json.

    With on_event, progress and the draft reply are streamed to it as well.
    """
    for text in [message, *(t.content for t in history if t.role == "user")]:
        deps.shopper_amounts.update(round(float(m.replace(",", "")), 2) for m in PRICE_RE.findall(text))
    started, t0 = datetime.now(timezone.utc), time.monotonic()
    result, stop, error = None, "final_answer", None
    # capture_run_messages keeps the agent's steps even if the run fails, so failures are audited too.
    with capture_run_messages() as messages:
        try:
            result = await get_agent().run(
                message,
                deps=deps,
                message_history=to_message_history(history),
                usage_limits=LIMITS,
                event_stream_handler=ReplyStreamer(on_event).handle if on_event else None,
            )
            return result.output  # always the version that passed the honesty check
        except UsageLimitExceeded as err:
            stop, error = "usage_limit", str(err)
            raise
        except ModelHTTPError as err:
            if is_content_filter(err):
                # Azure's own safety filter blocked the message (usually a jailbreak attempt) before
                # our agent saw it. Answer with a polite, on-voice refusal instead of an error.
                stop, error = "content_filter", "blocked by the model gateway's content filter"
                return ShopperReply(reply=filtered_reply(message))
            stop, error = "model_error", f"{type(err).__name__} {err.status_code}"
            raise
        except asyncio.CancelledError:
            stop, error = "cancelled", "the shopper left before the answer finished"
            raise
        except Exception as err:
            stop, error = "error", type(err).__name__
            raise
        finally:
            # Auditing must never break a chat: any problem building the entry is logged, not raised.
            try:
                entry = audit_entry(message, deps, route, started, time.monotonic() - t0, messages, result, stop, error)
            except Exception:  # noqa: BLE001
                audit_log.exception("Could not build the audit trail entry")
            else:
                append_entry(entry)


FILTERED_REPLY = (
    "I'm afraid I can't help with that, but I'd be delighted to help you find something from the shop. "
    "Looking for a gift, a particular size, or gear for The Game?"
)


# Safety rule 11 must hold even when the gateway's filter blocks a message before the agent sees
# it (it can block self-harm content). A message that sounds like distress gets care, not shopping.
CARE_REPLY = (
    "I'm really sorry you're going through this, and I'm glad you said something. You don't have to handle it alone. "
    "In the US you can call or text 988 to reach the Suicide & Crisis Lifeline any time, and if you're in immediate danger "
    "please call 911. If you can, reach out to someone you trust and let them know how you're feeling right now."
)
DISTRESS_RE = re.compile(
    r"hurt(ing)? myself|harm(ing)? myself|self.?harm|kill(ing)? myself|suicid|end (it all|my life)|"
    r"don.?t want to (live|be alive|be here)|better off (dead|without me)|hopeless",
    re.IGNORECASE,
)


def filtered_reply(message: str) -> str:
    return CARE_REPLY if DISTRESS_RE.search(message) else FILTERED_REPLY


def is_content_filter(err: ModelHTTPError) -> bool:
    body = err.body if isinstance(err.body, dict) else {}
    return err.status_code == 400 and (body.get("code") == "content_filter" or "content management policy" in str(body))


# ---------- Audit trail (Problem 12) ----------
#
# Append-only audit trail of agent-loop activity (Problem 12): output/audit_trail.json.
#
# The file is one JSON array, one entry per agent run (one chat message). Entries are only ever
# added to the end; old entries are never rewritten or deleted, and nothing clears the file
# when the server restarts.
#
# How "append-only" works for a JSON array: the file always ends with "]". To add an entry we
# remove just that closing bracket and write ',\n{entry}\n]' in its place. Bytes before the
# bracket are never touched. An exclusive file lock (fcntl) stops two requests, or two server
# processes, from writing at the same moment.
#
# If the file is ever damaged (doesn't end in "]"), we don't "fix" it by rewriting it. The new
# entry goes to output/audit_trail.unreadable-append.jsonl instead, so no history is lost.

audit_log = logging.getLogger("campus_customs.audit")

AUDIT_PATH = Path(os.getenv("AUDIT_TRAIL_PATH", Path(__file__).resolve().parent.parent / "output" / "audit_trail.json"))
_lock = threading.Lock()  # one writer at a time inside this process; fcntl covers other processes


def append_entry(entry: dict, path: Path | None = None) -> None:
    """Add one entry to the end of the audit trail. Never raises: auditing must not break a chat."""
    path = path or AUDIT_PATH
    try:
        _append(entry, path)
    except Exception:  # noqa: BLE001
        audit_log.exception("Could not write the audit trail entry")


def _append(entry: dict, path: Path) -> None:
    body = json.dumps(entry, ensure_ascii=False, indent=2).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock, open(path, "a+b") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            if size == 0:  # brand-new file
                f.write(b"[\n" + body + b"\n]\n")
                return
            tail_len = min(size, 4096)
            f.seek(size - tail_len)
            tail = f.read(tail_len)
            close = tail.rfind(b"]")
            if close == -1 or tail[close + 1:].strip():
                _set_aside(entry, path)
                return
            before = tail[:close].rstrip()
            empty_array = before.endswith(b"[")
            f.truncate(size - tail_len + close)  # removes only the final "]" (and whitespace after it)
            f.write((b"\n" if empty_array else b",\n") + body + b"\n]\n")
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def _set_aside(entry: dict, path: Path) -> None:
    side = path.with_name(path.stem + ".unreadable-append.jsonl")
    audit_log.error("%s does not end with ']'; not touching it. Writing this entry to %s instead.", path.name, side.name)
    with open(side, "a", encoding="utf-8") as s:
        s.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_entries(path: Path | None = None) -> list[dict]:
    """The whole trail, oldest first (for tests and the harness)."""
    path = path or AUDIT_PATH
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))



def _short(value, limit: int) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def summarize_result(content) -> str:
    """One readable line for what a tool returned (the full objects are too long for an audit log)."""
    name = type(content).__name__
    if isinstance(content, SearchResult):
        found = ", ".join(f"{p.name} ({p.price_text})" for p in content.products[:3])
        more = f" +{len(content.products) - 3} more" if len(content.products) > 3 else ""
        return f"{content.total_matches} matches; showing {len(content.products)}: {found}{more}" if content.products else "no matches"
    if isinstance(content, ProductInfo):
        sizes = " ".join(f"{s.size}={s.quantity}" for s in content.stock_by_size)
        return f"{content.name} {content.price_text}; stock {sizes}"
    if isinstance(content, (StockCheck, CartToolResult)):
        return content.say_this
    if isinstance(content, CartView):
        return f"{content.item_count} item(s), subtotal {content.subtotal_text}"
    if isinstance(content, (ProductNotFound, SizeNotCarried)):
        return f"{name}: {content.message}"
    if isinstance(content, ShopperProfile):
        return "the signed-in shopper's own profile (name, email, member since)"  # keep personal details out of the log
    if isinstance(content, RecallResult):
        return f"{len(content.matches)} earlier message(s) found for '{content.query}'"
    if isinstance(content, list) and content and isinstance(content[0], CategoryInfo):
        return f"{len(content)} categories"
    return _short(content, 200)


def audit_entry(message, deps, route, started, seconds, messages, result, stop, error) -> dict:
    steps: list[AuditToolCall] = []
    calls: dict[str, tuple[str, str]] = {}  # tool_call_id -> (tool, args)
    model_name, finish = "", None
    for msg in messages:
        if isinstance(msg, ModelResponse):
            model_name = msg.model_name or model_name
            finish = msg.finish_reason or finish
            for part in msg.parts:
                if isinstance(part, ToolCallPart) and part.tool_name != OUTPUT_TOOL:
                    calls[part.tool_call_id] = (part.tool_name, _short(part.args_as_dict(), 160))
        elif isinstance(msg, ModelRequest):
            for part in msg.parts:
                if isinstance(part, ToolReturnPart) and part.tool_name != OUTPUT_TOOL:
                    tool, args = calls.pop(part.tool_call_id, (part.tool_name, ""))
                    steps.append(AuditToolCall(step=len(steps) + 1, tool=tool, args=args,
                                               result=_short(summarize_result(part.content), 200), outcome="ok"))
                elif isinstance(part, RetryPromptPart):
                    tool = "honesty_check" if part.tool_name in (None, OUTPUT_TOOL) else part.tool_name
                    args = "" if tool == "honesty_check" else calls.pop(part.tool_call_id, (tool, ""))[1]
                    steps.append(AuditToolCall(step=len(steps) + 1, tool=tool, args=args,
                                               result=_short(part.model_response(), 200), outcome="retry"))
    for tool, args in calls.values():  # tool calls that never returned (the run stopped first)
        steps.append(AuditToolCall(step=len(steps) + 1, tool=tool, args=args, result="no result: the run stopped", outcome="error"))

    output = result.output if result else None
    usage = {}
    if result:
        u = result.usage() if callable(result.usage) else result.usage  # a property in newer PydanticAI
        usage = {k: getattr(u, k) for k in ("requests", "tool_calls", "input_tokens", "output_tokens") if isinstance(getattr(u, k, None), int)}
    entry = AuditEntry(
        run_id=started.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6],
        started_at=started.isoformat(timespec="seconds"),
        finished_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        seconds=round(seconds, 2),
        route=route,
        shopper=f"user:{deps.shopper.user_id}" if deps.shopper else "guest",
        page=deps.page.path if deps.page else "",
        message=_short(message, 120),
        model=model_name or "unknown",
        tool_calls=steps,
        stop_reason=stop,
        model_finish_reason=finish,
        reply=_short(output.reply, 160) if output else (_short(filtered_reply(message), 160) if stop == "content_filter" else None),
        product_ids=output.product_ids if output else [],
        cart_actions=[f"{a.action} {a.quantity} × {a.product_id} ({a.size})" for a in deps.cart_actions],
        usage=usage,
        error=error,
    )
    return entry.model_dump()


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    question = " ".join(sys.argv[1:]) or "What hoodies do you have?"
    reply = asyncio.run(run_chat(question, [], tools.AgentDeps()))
    print(reply.reply)
    print("cards:", reply.product_ids)
