"""Tools the Campus Customs agent can call, plus the shared database helpers behind them.

Every price and stock number the agent quotes comes from these functions, which read
the catalogue and inventory tables live. The agent has no tool that can read the users
table or change anything in the database: the chat route in main.py saves messages itself.

The website's product routes (main.py) use the same helpers, so the chat and the
product pages can never disagree about a price.
"""

import difflib
import json
import os
from contextlib import closing
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

from models import (
    LOW_STOCK_THRESHOLD,
    CartAction,
    CartLine,
    CartToolResult,
    CartView,
    CartViewLine,
    CategoryInfo,
    PageContext,
    PastMessage,
    ProductCard,
    ProductDetail,
    ProductInfo,
    ProductMatch,
    ProductNotFound,
    ProductRef,
    RecallResult,
    SearchResult,
    ShopperProfile,
    SizeAvailability,
    SizeNotCarried,
    SizeStock,
    StockCheck,
    StockStatus,
)

ROOT = Path(__file__).resolve().parent.parent  # the project folder
DATA_DIR = ROOT / "data"


def env_setting(name: str, default: str) -> str:
    """A setting from .env. A blank value (e.g. `CAMPUS_DB_PATH=`) counts as not set and uses the default."""
    value = (os.getenv(name) or "").strip()
    return value or default


def env_path(name: str, default: Path) -> Path:
    """A file path from .env, or the default when missing or blank. Relative paths are from the project folder."""
    value = (os.getenv(name) or "").strip()
    if not value:
        return default
    path = Path(value).expanduser()
    return path if path.is_absolute() else ROOT / path


DB_PATH = env_path("CAMPUS_DB_PATH", DATA_DIR / "campus_customs.db")

SIZE_ORDER = ["XS", "S", "M", "L", "XL", "XXL"]
SIZE_RANK_SQL = "CASE size " + " ".join(f"WHEN '{s}' THEN {i}" for i, s in enumerate(SIZE_ORDER)) + " END"
MAX_RESULTS = 12  # enough to fill the on-page results grid (Problem 7)


# ---------- Model connection (same setup as Homework 3) ----------

def load_model_settings() -> tuple[str, str, str]:
    """API key, gateway URL, and model name from backend/.env. Never logged."""
    api_key = os.getenv("PORTKEY_API_KEY")
    if not api_key:
        raise RuntimeError("PORTKEY_API_KEY is not set. Add it to backend/.env (see .env.example).")
    base_url = env_setting("PORTKEY_BASE_URL", "https://api.portkey.ai/v1")
    model = env_setting("OPENAI_MODEL", "gpt-6-astra")
    return api_key, base_url, model


def make_model() -> OpenAIResponsesModel:
    """The PydanticAI model object that talks to the course's Portkey gateway."""
    api_key, base_url, model_name = load_model_settings()
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=60,
        max_retries=2,
        # The course gateway may answer repeated questions from its cache. Cached replies carry
        # placeholder ids ("portkey_cache_...") that Azure rejects on the agent's next step, and a
        # cached answer could repeat old stock levels. Always ask for a fresh answer.
        default_headers={"x-portkey-cache-force-refresh": "true"},
    )
    return OpenAIResponsesModel(model_name, provider=OpenAIProvider(openai_client=client))


# ---------- What every tool call can see ----------

@dataclass(frozen=True)
class Shopper:
    """Who is chatting. Set by main.py from the signed-in session cookie, never by the AI."""

    user_id: int
    first_name: str
    last_name: str
    email: str
    member_since: str  # users.created_at

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()


@dataclass(frozen=True)
class ViewedProduct:
    product_id: str
    name: str
    category: str
    garment_type: str
    colors_on_item: list[str]


@dataclass(frozen=True)
class PageView:
    """What the shopper is looking at, rebuilt from the database (the browser only sends ids)."""

    path: str
    page_type: str  # "product", "products", "home", "about", "cart", or "other"
    product: ViewedProduct | None = None
    category_filter: str | None = None
    results_heading: str | None = None
    results: list[ProductRef] = field(default_factory=list)


@dataclass
class AgentDeps:
    """Per-chat context handed to every tool (PydanticAI "dependencies")."""

    shopper: Shopper | None = None  # None = guest
    page: PageView | None = None
    db_path: Path = DB_PATH
    # The shopper's cart as the browser sent it: (product_id, size) -> quantity. Cart tools update
    # this copy as they work, and list their changes in cart_actions for the website to apply.
    cart: dict[tuple[str, str], int] = field(default_factory=dict)
    cart_actions: list[CartAction] = field(default_factory=list)
    # Filled in as tools run: every product, price, and stock number the agent has actually
    # seen in this chat turn. agent.py checks the final reply against these, so the reply can
    # only quote real prices and quantities from the database.
    seen_product_ids: set[str] = field(default_factory=set)
    seen_prices: set[float] = field(default_factory=set)  # unit prices seen this turn (any product)
    # product_id -> (name, unit price): lets the answer check tie each quoted price to its product.
    seen_products: dict[str, tuple[str, float]] = field(default_factory=dict)
    # Amounts a tool calculated itself (cart line totals and subtotals): fine to quote as-is.
    tool_totals: set[float] = field(default_factory=set)
    # Category price ranges from list_categories: fine in "from $X to $Y" sentences.
    range_prices: set[float] = field(default_factory=set)
    seen_quantities: set[int] = field(default_factory=set)
    # Dollar amounts the shopper typed ("under $60"); fine to repeat back, but they are not prices.
    shopper_amounts: set[float] = field(default_factory=set)
    # (product name, size) pairs a tool reported as sold out; the reply must say so.
    sold_out_checks: list[tuple[str, str]] = field(default_factory=list)

    def remember(self, product_id: str, price: float, name: str) -> None:
        self.seen_product_ids.add(product_id)
        self.seen_prices.add(round(price, 2))
        self.seen_products[product_id] = (name, round(price, 2))

    def remember_stock(self, *quantities: int) -> None:
        self.seen_quantities.update(quantities)


# ---------- Database helpers (shared with the website routes) ----------

def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    # FastAPI may open a connection on one worker thread and use it on another. Each
    # connection belongs to one request or tool call and is never shared, so this is safe.
    con = sqlite3.connect(db_path, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")  # SQLite leaves foreign keys off unless asked
    return con


# Originals live in data/products; data/products_web holds the white-background copies
# made by scripts/clean_product_images.py. The image route serves the web copy when there is one.
IMAGE_DIRS = [DATA_DIR / "products_web", DATA_DIR / "products"]


def image_url(image_file_path: str) -> str:
    """URL for a product photo, with a version tag (?v=<last-modified time>).

    Database paths are relative to data/, e.g. "products/basic-hoodie-big-yale.jpg". The version
    tag lets browsers cache photos for a long time, yet re-cleaned photos show up right away,
    because a changed file gets a new URL.
    """
    name = Path(image_file_path).name
    for folder in IMAGE_DIRS:
        path = folder / name
        if path.is_file():
            return f"/media/{image_file_path}?v={int(path.stat().st_mtime)}"
    return f"/media/{image_file_path}"


PRODUCT_SELECT = """
    SELECT c.*, COALESCE(SUM(i.quantity), 0) AS total_stock,
           GROUP_CONCAT(CASE WHEN i.quantity > 0 THEN i.size || ':' || i.quantity END) AS stock_pairs
    FROM catalogue c LEFT JOIN inventory i ON i.product_id = c.product_id
"""

SHORT_INFO_LENGTH = 90


def short_info(description: str) -> str:
    """First sentence (or clause) of the description, short enough for one or two card lines."""
    first = re.split(r"(?<=[.!?])\s", description.strip(), maxsplit=1)[0].rstrip(".")
    if len(first) <= SHORT_INFO_LENGTH:
        return first
    cut = first[:SHORT_INFO_LENGTH].rsplit(" ", 1)[0].rstrip(",;:- ")
    return cut + "…"


def low_stock_note(stock: dict[str, int]) -> str | None:
    """'Only 2 left in XL' for the scarcest in-stock size, if it is 5 or fewer. Never invented."""
    low = [(q, SIZE_ORDER.index(s), s) for s, q in stock.items() if 0 < q <= LOW_STOCK_THRESHOLD]
    if not low:
        return None
    q, _, size = min(low)
    return f"Only {q} left in {size}"


def to_card(row: sqlite3.Row) -> ProductCard:
    stock = {s: int(q) for s, q in (pair.split(":") for pair in (row["stock_pairs"] or "").split(",") if pair)}
    in_stock_sizes = set(stock)
    return ProductCard(
        product_id=row["product_id"],
        name=row["name"],
        category=row["category"],
        garment_type=row["garment_type"],
        description=row["description"],
        short_info=short_info(row["description"]),
        price=row["price"],
        image_url=image_url(row["image_file_path"]),
        total_stock=row["total_stock"],
        in_stock=row["total_stock"] > 0,
        sizes_in_stock=[s for s in SIZE_ORDER if s in in_stock_sizes],
        low_stock_note=low_stock_note(stock),
    )


def list_categories(con: sqlite3.Connection) -> list[CategoryInfo]:
    rows = con.execute(
        "SELECT category, COUNT(*) AS n, MIN(price) AS lo, MAX(price) AS hi FROM catalogue GROUP BY category ORDER BY category"
    ).fetchall()
    return [CategoryInfo(name=r["category"], count=r["n"], min_price=r["lo"], max_price=r["hi"]) for r in rows]


def list_products(con: sqlite3.Connection, category: str | None = None, q: str | None = None) -> list[ProductCard]:
    """Simple filter for the Products page: exact category and/or every keyword must appear."""
    where, params = [], []
    if category:
        where.append("c.category = ?")
        params.append(category)
    if q:
        for word in q.split():
            where.append("(c.name LIKE ? OR c.description LIKE ? OR c.colors LIKE ? OR c.search_tags LIKE ?)")
            params += [f"%{word}%"] * 4
    sql = PRODUCT_SELECT + (" WHERE " + " AND ".join(where) if where else "")
    sql += " GROUP BY c.product_id ORDER BY c.category, c.name"
    return [to_card(r) for r in con.execute(sql, params).fetchall()]


def get_cards(con: sqlite3.Connection, product_ids: list[str]) -> list[ProductCard]:
    """Live product cards for these ids, in the same order; unknown ids are dropped."""
    if not product_ids:
        return []
    marks = ",".join("?" * len(product_ids))
    rows = con.execute(PRODUCT_SELECT + f" WHERE c.product_id IN ({marks}) GROUP BY c.product_id", product_ids).fetchall()
    by_id = {r["product_id"]: to_card(r) for r in rows}
    return [by_id[i] for i in dict.fromkeys(product_ids) if i in by_id]


def get_product_detail(con: sqlite3.Connection, product_id: str) -> ProductDetail | None:
    row = con.execute(PRODUCT_SELECT + " WHERE c.product_id = ? GROUP BY c.product_id", (product_id,)).fetchone()
    if row is None:
        return None
    sizes = con.execute(
        f"SELECT size, quantity FROM inventory WHERE product_id = ? ORDER BY {SIZE_RANK_SQL}", (product_id,)
    ).fetchall()
    return ProductDetail(
        **to_card(row).model_dump(),
        colors=json.loads(row["colors"]),
        search_tags=json.loads(row["search_tags"]),
        inventory=[SizeStock(size=s["size"], quantity=s["quantity"]) for s in sizes],
    )


def _stock_by_product(con: sqlite3.Connection) -> dict[str, dict[str, int]]:
    stock: dict[str, dict[str, int]] = {}
    for r in con.execute(f"SELECT product_id, size, quantity FROM inventory ORDER BY {SIZE_RANK_SQL}"):
        stock.setdefault(r["product_id"], {})[r["size"]] = r["quantity"]
    return stock


# ---------- Preparing the course data pack (Problem 2 cleanup, applied automatically) ----------
#
# The course data pack ships campus_customs.db with three placeholder descriptions, 22
# inconsistent garment labels, some misleading names, and no category column. In Problem 2
# we cleaned these up; prepare_database() applies the same cleanup to a fresh copy of the
# data pack the first time the server starts. It only touches the catalogue table (never
# users, inventory, or chats) and is safe to run more than once.

_PLACEHOLDER_FIXES = {  # written from each product's photo in Problem 2
    "benjamin-franklin-t-shirt": (
        "Light heather gray short-sleeve crew-neck T-shirt with a large center-chest Benjamin Franklin College shield in blue and red with white lightning bolts and fleurs-de-lis, above black BENJAMIN FRANKLIN COLLEGE lettering.",
        ["light heather gray", "blue", "red", "white", "black"],
        ["Yale", "Benjamin Franklin College", "Franklin", "residential college", "college shield", "crest", "gray T-shirt", "short sleeve", "Campus Customs"],
    ),
    "berkeley-sweater-fleece-jacket": (
        "Light heather gray sweater-knit fleece full-zip jacket with a stand-up collar, charcoal zipper and trim, zippered side pockets, and a small red Berkeley College shield with BERKELEY lettering on the left chest.",
        ["light heather gray", "charcoal gray", "red", "white"],
        ["Yale", "Berkeley College", "residential college", "fleece", "fleece jacket", "sweater fleece", "full zip", "gray jacket", "left chest crest", "Campus Customs"],
    ),
    "timothy-dwight-college-crewneck": (
        "Heather gray long-sleeve crewneck sweatshirt with ribbed collar, cuffs, and waistband, and a small red and white Timothy Dwight College shield with black TIMOTHY DWIGHT lettering on the left chest.",
        ["heather gray", "red", "white", "black"],
        ["Yale", "Timothy Dwight College", "TD", "residential college", "crewneck", "sweatshirt", "gray sweatshirt", "left chest crest", "long sleeve", "Campus Customs"],
    ),
}
_NAME_FIXES = {  # names that were wrong (checked against the photos)
    "school-of-architecture-crewneck": "School of Architecture 1/4 Zip",
    "squash-left-chest-tennis": "Squash Left Chest Crewneck",
    "yale-sports-creqneck-field-hockey": "Yale Sports Crewneck Field Hockey",
    "champion-reverse-weave-hoodie-1": "Champion Reverse Weave Hoodie",
    "ua-mens-tech-l-s-2-0": "UA Men's Tech Long Sleeve 2.0",
}
_NAME_CLEANUP = [  # names built from file names: "T Shirt" -> "T-Shirt", "1 4 Zip" -> "1/4 Zip", ...
    (r"\bT Shirt\b", "T-Shirt"), (r"\b1 4 Zip\b", "1/4 Zip"), (r"\bOf\b", "of"), (r"\bAnd\b", "and"),
    (r"\bVs\b", "vs."), (r"\bUa\b", "UA"), (r"\bVit\b", "VIT"), (r"\bTri Blend\b", "Tri-Blend"),
    (r"\bFull Zip\b", "Full-Zip"), (r"\bMens\b", "Men's"), (r"\bTrack Field\b", "Track & Field"),
]
_GARMENT_FIXES = {  # vague placeholder labels -> real ones
    "berkeley-sweater-fleece-jacket": "full-zip fleece jacket",
    "benjamin-franklin-t-shirt": "short-sleeve t-shirt",
    "timothy-dwight-college-crewneck": "crewneck sweatshirt",
}


def shop_category(garment_type: str) -> str:
    """One of the six shop categories, from a (lowercase) garment label."""
    g = garment_type.lower()
    if "t-shirt" in g:
        return "T-Shirts"
    if "performance shirt" in g:
        return "Long Sleeves"
    if "quarter-zip" in g:
        return "Quarter-Zips"
    if "jacket" in g:
        return "Jackets"
    if "hood" in g:
        return "Hoodies"
    if "crewneck" in g or "mockneck" in g:
        return "Crewnecks"
    raise ValueError(f"No shop category for garment type {garment_type!r}")


def prepare_database(db_path: Path = DB_PATH) -> bool:
    """Apply the Problem 2 cleanup if this database still needs it. Returns True if anything changed."""
    with closing(connect(db_path)) as con, con:
        columns = {r["name"] for r in con.execute("PRAGMA table_info(catalogue)")}
        placeholders = con.execute("SELECT COUNT(*) FROM catalogue WHERE description LIKE '%filename-based stub%'").fetchone()[0]
        if "category" in columns and not placeholders:
            return False
        if "category" not in columns:
            con.execute("ALTER TABLE catalogue ADD COLUMN category TEXT")
        for pid, (desc, colors, tags) in _PLACEHOLDER_FIXES.items():
            con.execute(
                "UPDATE catalogue SET description = ?, colors = ?, search_tags = ? WHERE product_id = ? AND description LIKE '%stub%'",
                (desc, json.dumps(colors), json.dumps(tags), pid),
            )
        for row in con.execute("SELECT product_id, name, garment_type, search_tags FROM catalogue").fetchall():
            pid = row["product_id"]
            name = _NAME_FIXES.get(pid)
            if name is None:
                name = row["name"]
                for pattern, replacement in _NAME_CLEANUP:
                    name = re.sub(pattern, replacement, name)
            garment = _GARMENT_FIXES.get(pid, row["garment_type"].lower())
            tags = json.loads(row["search_tags"])
            if pid == "squash-left-chest-tennis":  # it's a squash crewneck, not a tennis item
                tags = [t for t in tags if "tennis" not in t.lower()]
            con.execute(
                "UPDATE catalogue SET name = ?, garment_type = ?, category = ?, search_tags = ? WHERE product_id = ?",
                (name, garment, shop_category(garment), json.dumps(tags), pid),
            )
        return True


# ---------- Small helpers for the agent tools ----------

def stock_status(quantity: int) -> StockStatus:
    if quantity <= 0:
        return "sold_out"
    if quantity <= LOW_STOCK_THRESHOLD:
        return "low_stock"
    return "in_stock"


def price_text(price: float) -> str:
    return f"${price:,.2f}"


# Everyday ways shoppers say sizes -> the size codes in the inventory table.
SIZE_WORDS = {
    "xs": "XS", "x-small": "XS", "xsmall": "XS", "extra small": "XS", "extra-small": "XS",
    "s": "S", "small": "S", "sm": "S",
    "m": "M", "medium": "M", "med": "M",
    "l": "L", "large": "L", "lg": "L",
    "xl": "XL", "x-large": "XL", "xlarge": "XL", "extra large": "XL", "extra-large": "XL",
    "xxl": "XXL", "2xl": "XXL", "xx-large": "XXL", "xxlarge": "XXL", "2x": "XXL",
    "extra extra large": "XXL", "double xl": "XXL",
}


def normalize_size(size: str) -> str | None:
    key = re.sub(r"\s+", " ", size.strip().lower())
    return SIZE_WORDS.get(key) or (key.upper() if key.upper() in SIZE_ORDER else None)


def resolve_product(con: sqlite3.Connection, ref: str) -> tuple[str | None, list[ProductRef]]:
    """Find a product by id or by name. Returns (product_id, []) or (None, suggestions)."""
    ref = ref.strip()
    rows = con.execute("SELECT product_id, name FROM catalogue").fetchall()
    by_id = {r["product_id"]: r["name"] for r in rows}
    if ref in by_id:
        return ref, []
    lowered = ref.lower()
    exact = [r["product_id"] for r in rows if r["name"].lower() == lowered or r["product_id"] == lowered.replace(" ", "-")]
    if len(exact) == 1:
        return exact[0], []
    contains = [r["product_id"] for r in rows if lowered in r["name"].lower()]
    if len(contains) == 1:
        return contains[0], []
    names = {r["name"].lower(): r["product_id"] for r in rows}
    close = difflib.get_close_matches(lowered, names.keys(), n=3, cutoff=0.5)
    suggestions = [ProductRef(product_id=names[n], name=by_id[names[n]]) for n in close]
    if not suggestions and contains:
        suggestions = [ProductRef(product_id=i, name=by_id[i]) for i in contains[:3]]
    return None, suggestions


def _availability(inventory: list[SizeStock]) -> list[SizeAvailability]:
    return [SizeAvailability(size=s.size, quantity=s.quantity, status=stock_status(s.quantity)) for s in inventory]


# ---------- Keyword search for the agent ----------

# Shopper words -> words the catalogue actually uses.
SYNONYMS = {
    "grey": "gray", "tee": "t-shirt", "tees": "t-shirt", "tshirt": "t-shirt",
    "hoody": "hoodie", "hoodies": "hoodie", "sweatshirts": "sweatshirt", "crew": "crewneck",
    "quarterzip": "quarter-zip", "1/4": "quarter-zip", "halfzip": "quarter-zip", "zip-up": "zip",
    "jumper": "sweatshirt", "longsleeve": "long-sleeve", "coat": "jacket",
    "dog": "bulldog", "mascot": "bulldog", "dan": "bulldog", "maroon": "red", "crimson": "red",
    "mother": "mom", "father": "dad", "grandmother": "grandma", "grandfather": "grandpa",
}
STOPWORDS = {
    "a", "an", "the", "and", "or", "for", "with", "of", "in", "on", "to", "me", "my", "i", "you",
    "your", "do", "does", "have", "has", "any", "some", "something", "show", "find", "want", "looking",
    "like", "that", "this", "it", "is", "are", "what", "which", "yale", "campus", "customs", "merch",
    "gear", "item", "items", "stuff", "please", "got", "u", "one", "ones",
}
# Color words a shopper might use -> shades the catalogue actually lists.
COLOR_FAMILIES = {
    "pink": ("pink", "coral", "rose", "salmon", "blush", "magenta"),
    "blue": ("blue", "navy"),
    "gray": ("gray", "charcoal", "heather", "silver"),
    "white": ("white", "cream", "ivory", "off-white"),
    "red": ("red", "crimson", "maroon", "coral"),
    "black": ("black", "charcoal"),
    "green": ("green", "olive"),
    "yellow": ("yellow", "gold"),
    "orange": ("orange", "coral"),
}

# Scores for where a word was found: a match in the name counts most.
FIELD_WEIGHTS = {"name": 3, "category": 3, "tags": 2, "colors": 2, "garment": 2, "description": 1}


def _terms(query: str) -> list[tuple[str, ...]]:
    """Each search word, plus the other spellings or shades that should count as a match."""
    return [COLOR_FAMILIES.get(w, (w,)) for w in _words(query)]


def _words(query: str) -> list[str]:
    words = re.findall(r"[a-z0-9/&'-]+", query.lower())
    terms = []
    for w in words:
        w = SYNONYMS.get(w, w)
        if w in STOPWORDS or len(w) < 2:
            continue
        if len(w) > 4 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]  # "hoodies" -> "hoodie", "jackets" -> "jacket"
        terms.append(w)
    return list(dict.fromkeys(terms))


def search_catalogue(
    deps: AgentDeps,
    query: str,
    category: str | None = None,
    max_price: float | None = None,
    size: str | None = None,
    limit: int = MAX_RESULTS,
) -> SearchResult:
    terms = _terms(query)
    size = size.upper().strip() if size else None
    filters: dict[str, str | float] = {}
    if category:
        filters["category"] = category
    if max_price is not None:
        filters["max_price"] = max_price
    if size:
        filters["size_in_stock"] = size

    with closing(connect(deps.db_path)) as con:
        stock = _stock_by_product(con)
        rows = con.execute("SELECT * FROM catalogue").fetchall()

    scored = []
    for r in rows:
        if category and r["category"].lower() != category.lower():
            continue
        if max_price is not None and r["price"] > max_price:
            continue
        sizes = stock.get(r["product_id"], {})
        if size and sizes.get(size, 0) <= 0:
            continue
        fields = {
            "name": r["name"].lower(),
            "category": r["category"].lower(),
            "tags": r["search_tags"].lower(),
            "colors": r["colors"].lower(),
            "garment": r["garment_type"].lower(),
            "description": r["description"].lower(),
        }
        score = sum(
            max((w for f, w in FIELD_WEIGHTS.items() if any(alt in fields[f] for alt in t)), default=0) for t in terms
        )
        matched = sum(1 for t in terms if any(alt in v for alt in t for v in fields.values()))
        if terms and matched == 0:
            continue
        # Products that match every word rank above ones that match only some.
        scored.append((matched == len(terms), score, r, sizes))

    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    top = scored[: max(1, min(limit, MAX_RESULTS))]
    products = []
    for _, _, r, sizes in top:
        deps.remember(r["product_id"], r["price"], r["name"])
        products.append(
            ProductMatch(
                product_id=r["product_id"],
                name=r["name"],
                category=r["category"],
                garment_type=r["garment_type"],
                price=r["price"],
                price_text=price_text(r["price"]),
                colors_on_item=json.loads(r["colors"]),
                description=r["description"],
                sizes_in_stock=[s for s in SIZE_ORDER if sizes.get(s, 0) > 0],
                low_stock_sizes=[s for s in SIZE_ORDER if stock_status(sizes.get(s, 0)) == "low_stock"],
                sold_out_sizes=[s for s in SIZE_ORDER if sizes.get(s, 0) <= 0],
            )
        )

    note = None
    if not products:
        note = "No products matched. Say so honestly and suggest a broader search; do not invent items."
    elif not all(x[0] for x in top):
        note = "Some results match only part of the request. Mention that when it matters."
    return SearchResult(query=query, filters=filters, total_matches=len(scored), products=products, note=note)


# ---------- Product info and stock tools ----------

def _not_found(ref: str, suggestions: list[ProductRef]) -> ProductNotFound:
    return ProductNotFound(
        looked_for=ref,
        message=(
            f"No product matches '{ref}'. Do not guess its price or stock. "
            "Use search_products, or ask the shopper which item they mean."
        ),
        did_you_mean=suggestions,
    )


def product_info(deps: AgentDeps, product: str) -> ProductInfo | ProductNotFound:
    """Description, price, and stock in every size for one product (by id or name)."""
    with closing(connect(deps.db_path)) as con:
        product_id, suggestions = resolve_product(con, product)
        detail = get_product_detail(con, product_id) if product_id else None
    if detail is None:
        return _not_found(product, suggestions)

    sizes = _availability(detail.inventory)
    deps.remember(detail.product_id, detail.price, detail.name)
    deps.remember_stock(detail.total_stock, *(s.quantity for s in sizes))
    return ProductInfo(
        product_id=detail.product_id,
        name=detail.name,
        category=detail.category,
        garment_type=detail.garment_type,
        description=detail.description,
        price=detail.price,
        price_text=price_text(detail.price),
        colors_on_item=detail.colors,
        stock_by_size=sizes,
        total_in_stock=detail.total_stock,
        sizes_in_stock=[s.size for s in sizes if s.quantity > 0],
        low_stock_sizes=[s.size for s in sizes if s.status == "low_stock"],
        sold_out_sizes=[s.size for s in sizes if s.status == "sold_out"],
        sold_out_everywhere=detail.total_stock == 0,
    )


def stock_for_size(deps: AgentDeps, product: str, size: str) -> StockCheck | ProductNotFound | SizeNotCarried:
    """Live quantity for one size of one product, plus the other sizes that are available."""
    size_code = normalize_size(size)
    if size_code is None:
        return SizeNotCarried(
            size_asked=size,
            message=f"We don't carry a size called '{size}'. Say so, and offer the sizes we do carry.",
            sizes_we_carry=SIZE_ORDER,
        )
    with closing(connect(deps.db_path)) as con:
        product_id, suggestions = resolve_product(con, product)
        detail = get_product_detail(con, product_id) if product_id else None
    if detail is None:
        return _not_found(product, suggestions)

    sizes = _availability(detail.inventory)
    this = next(s for s in sizes if s.size == size_code)
    others = [s for s in sizes if s.size != size_code and s.quantity > 0]
    if this.status == "sold_out":
        say = f"{detail.name} is sold out in {size_code}."
        deps.sold_out_checks.append((detail.name, size_code))
    elif this.status == "low_stock":
        say = f"{detail.name} has only {this.quantity} left in {size_code}."
    else:
        say = f"{detail.name} is in stock in {size_code} ({this.quantity} available)."

    deps.remember(detail.product_id, detail.price, detail.name)
    deps.remember_stock(this.quantity, *(s.quantity for s in others))
    return StockCheck(
        product_id=detail.product_id,
        name=detail.name,
        price_text=price_text(detail.price),
        size=size_code,
        quantity=this.quantity,
        status=this.status,
        say_this=say,
        other_sizes_in_stock=others,
    )


def categories(deps: AgentDeps) -> list[CategoryInfo]:
    with closing(connect(deps.db_path)) as con:
        result = list_categories(con)
    for c in result:
        deps.range_prices.update({round(c.min_price, 2), round(c.max_price, 2)})
        deps.remember_stock(c.count)
    return result


# ---------- Page context ----------

PAGE_TYPES = {"/": "home", "/products": "products", "/about": "about", "/cart": "cart"}


def build_page_view(con: sqlite3.Connection, page: PageContext) -> PageView:
    """Turn the ids the browser sent into trusted facts from the database. Unknown ids are dropped."""
    path = page.path if page.path.startswith("/") else "/"
    product_id = page.product_id
    if product_id is None and (m := re.fullmatch(r"/products/([^/?#]+)", path)):
        product_id = m.group(1)

    product = None
    if product_id:
        row = con.execute(
            "SELECT product_id, name, category, garment_type, colors FROM catalogue WHERE product_id = ?", (product_id,)
        ).fetchone()
        if row:
            product = ViewedProduct(row["product_id"], row["name"], row["category"], row["garment_type"], json.loads(row["colors"]))

    categories_known = {r[0] for r in con.execute("SELECT DISTINCT category FROM catalogue")}
    category = page.category_filter if page.category_filter in categories_known else None

    results: list[ProductRef] = []
    if page.result_product_ids:
        names = {c.product_id: c.name for c in get_cards(con, page.result_product_ids)}
        results = [ProductRef(product_id=i, name=names[i]) for i in dict.fromkeys(page.result_product_ids) if i in names]

    page_type = "product" if product else PAGE_TYPES.get(path.split("?")[0], "other")
    return PageView(
        path=path,
        page_type=page_type,
        product=product,
        category_filter=category,
        results_heading=page.results_heading if results else None,
        results=results,
    )


# ---------- Shopper memory tools (only ever the signed-in shopper's own data) ----------

def shopper_profile(deps: AgentDeps) -> ShopperProfile | str:
    if deps.shopper is None:
        return "The shopper is a guest (not signed in). There is no account to describe."
    with closing(connect(deps.db_path)) as con:
        (count,) = con.execute("SELECT COUNT(*) FROM chat_messages WHERE user_id = ?", (deps.shopper.user_id,)).fetchone()
    sh = deps.shopper
    return ShopperProfile(
        first_name=sh.first_name,
        last_name=sh.last_name,
        email=sh.email,
        member_since=sh.member_since[:10],
        saved_messages=count,
    )


RECALL_LIMIT = 6


def recall_chats(deps: AgentDeps, query: str) -> RecallResult:
    """Search the signed-in shopper's saved chat history. The user id comes from deps, never from the AI."""
    if deps.shopper is None:
        return RecallResult(query=query, matches=[], note="Guest chats aren't saved, so there is nothing to recall.")
    words = [w for w in _words(query) if len(w) > 2][:6]
    where = " OR ".join(["content LIKE ? OR products_json LIKE ?"] * len(words)) or "1 = 1"
    params: list[object] = [deps.shopper.user_id]
    for w in words:
        params += [f"%{w}%", f"%{w}%"]
    with closing(connect(deps.db_path)) as con:
        rows = con.execute(
            f"SELECT role, content, products_json, created_at FROM chat_messages "
            f"WHERE user_id = ? AND ({where}) ORDER BY id DESC LIMIT ?",
            (*params, RECALL_LIMIT),
        ).fetchall()
    matches = []
    for r in rows:
        shown = [ProductRef(product_id=p["product_id"], name=p["name"]) for p in json.loads(r["products_json"] or "[]")]
        for ref in shown:
            deps.seen_product_ids.add(ref.product_id)  # ok to show as cards; prices still need a fresh lookup
        text = r["content"] if len(r["content"]) <= 300 else r["content"][:300].rsplit(" ", 1)[0] + "…"
        matches.append(PastMessage(role=r["role"], said_on=r["created_at"], text=text, products_shown=shown))
    note = None if matches else "Nothing in this shopper's saved chats matches. Say so; don't guess."
    if matches:
        note = "Prices and stock in old messages may be out of date. Look them up again before quoting."
    return RecallResult(query=query, matches=matches, note=note)


# ---------- Cart tools (Problem 9: add to cart from the chat) ----------

MAX_ADD_AT_ONCE = 10


def clean_cart(con: sqlite3.Connection, lines: list[CartLine]) -> dict[tuple[str, str], int]:
    """The browser's cart, keeping only real products and sizes (duplicates are merged)."""
    known = {r[0] for r in con.execute("SELECT product_id FROM catalogue")}
    cart: dict[tuple[str, str], int] = {}
    for line in lines:
        size = normalize_size(line.size)
        if line.product_id in known and size:
            cart[(line.product_id, size)] = cart.get((line.product_id, size), 0) + line.quantity
    return cart


def _cart_lookup(deps: AgentDeps, product: str, size: str):
    """Shared checks for add/remove: returns (detail, size_code, stock) or an error result."""
    size_code = normalize_size(size)
    if size_code is None:
        return SizeNotCarried(
            size_asked=size,
            message=f"We don't carry a size called '{size}'. Ask which of our sizes they'd like.",
            sizes_we_carry=SIZE_ORDER,
        )
    with closing(connect(deps.db_path)) as con:
        product_id, suggestions = resolve_product(con, product)
        detail = get_product_detail(con, product_id) if product_id else None
    if detail is None:
        return _not_found(product, suggestions)
    stock = next(s.quantity for s in detail.inventory if s.size == size_code)
    deps.remember(detail.product_id, detail.price, detail.name)
    deps.remember_stock(stock)
    return detail, size_code, stock


def add_to_cart(deps: AgentDeps, product: str, size: str, quantity: int = 1) -> CartToolResult | ProductNotFound | SizeNotCarried:
    checked = _cart_lookup(deps, product, size)
    if not isinstance(checked, tuple):
        return checked
    detail, size_code, stock = checked
    key = (detail.product_id, size_code)
    already = deps.cart.get(key, 0)
    wanted = max(1, min(quantity, MAX_ADD_AT_ONCE))
    added = max(0, min(wanted, stock - already))  # never put more in the cart than we have

    if stock == 0:
        say = f"{detail.name} is sold out in {size_code}, so nothing was added."
        deps.sold_out_checks.append((detail.name, size_code))
    elif added == 0:
        say = f"The cart already holds all {stock} {detail.name} we have in {size_code}; nothing more was added."
    elif added < wanted:
        say = f"Added {added} × {detail.name} in {size_code} ({price_text(detail.price)} each). That's all we have in that size."
    else:
        say = f"Added {added} × {detail.name} in {size_code} ({price_text(detail.price)} each) to the cart."

    if added:
        deps.cart[key] = already + added
        deps.cart_actions.append(CartAction(
            action="add", product_id=detail.product_id, size=size_code, quantity=added,
            name=detail.name, price=detail.price, image_url=detail.image_url, available=stock,
        ))
    deps.remember_stock(added, already + added)
    if added > 1:
        deps.tool_totals.add(round(detail.price * added, 2))
    return CartToolResult(
        done=added > 0, product_id=detail.product_id, name=detail.name, size=size_code,
        price_text=price_text(detail.price), quantity_changed=added, now_in_cart=already + added,
        in_stock=stock, say_this=say,
    )


def remove_from_cart(deps: AgentDeps, product: str, size: str, quantity: int | None = None) -> CartToolResult | ProductNotFound | SizeNotCarried:
    checked = _cart_lookup(deps, product, size)
    if not isinstance(checked, tuple):
        return checked
    detail, size_code, stock = checked
    key = (detail.product_id, size_code)
    already = deps.cart.get(key, 0)
    removed = already if quantity is None else max(0, min(quantity, already))
    if removed:
        deps.cart[key] = already - removed
        if deps.cart[key] == 0:
            del deps.cart[key]
        deps.cart_actions.append(CartAction(
            action="remove", product_id=detail.product_id, size=size_code, quantity=removed,
            name=detail.name, price=detail.price, image_url=detail.image_url, available=stock,
        ))
        say = f"Removed {removed} × {detail.name} in {size_code} from the cart."
    else:
        say = f"There was no {detail.name} in {size_code} in the cart, so nothing was removed."
    deps.remember_stock(removed, already - removed)
    return CartToolResult(
        done=removed > 0, product_id=detail.product_id, name=detail.name, size=size_code,
        price_text=price_text(detail.price), quantity_changed=removed, now_in_cart=already - removed,
        in_stock=stock, say_this=say,
    )


def view_cart(deps: AgentDeps) -> CartView:
    if not deps.cart:
        return CartView(lines=[], item_count=0, subtotal_text=price_text(0), note="The cart is empty.")
    with closing(connect(deps.db_path)) as con:
        details = {pid: get_product_detail(con, pid) for pid in {pid for pid, _ in deps.cart}}
    lines, subtotal = [], 0.0
    for (pid, size), qty in deps.cart.items():
        d = details[pid]
        stock = next(s.quantity for s in d.inventory if s.size == size)
        problem = None
        if stock == 0:
            problem = f"Sold out in {size}"
        elif qty > stock:
            problem = f"Only {stock} left in {size}"
        line_total = d.price * qty
        subtotal += line_total
        deps.remember(pid, d.price, d.name)
        deps.tool_totals.add(round(line_total, 2))
        deps.remember_stock(qty, stock)
        lines.append(CartViewLine(
            product_id=pid, name=d.name, size=size, quantity=qty, price_text=price_text(d.price),
            line_total_text=price_text(line_total), in_stock=stock, problem=problem,
        ))
    deps.tool_totals.add(round(subtotal, 2))
    count = sum(deps.cart.values())
    deps.remember_stock(count)
    return CartView(
        lines=lines, item_count=count, subtotal_text=price_text(subtotal),
        note="Prices are live. Shipping and tax are added at checkout, which isn't available online yet.",
    )

