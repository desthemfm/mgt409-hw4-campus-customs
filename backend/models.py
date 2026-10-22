"""Pydantic / PydanticAI structured types for the Campus Customs backend.

API shapes (what the website sends and receives) and the agent's structured output all
live here. The website's TypeScript types in frontend/src/api.ts and chat.ts mirror them.
"""

from typing import Literal

from pydantic import BaseModel, Field

# ---------- Products ----------


class SizeStock(BaseModel):
    size: str
    quantity: int


class ProductCard(BaseModel):
    """One product card: the tile on the Products page, the home page, and under chat replies.

    Always built fresh from the database (tools.to_card), so the price is never stale.
    """

    product_id: str
    name: str
    category: str
    garment_type: str
    description: str
    short_info: str = Field(description="One short line for the card: the first sentence of the description, trimmed.")
    price: float
    image_url: str
    total_stock: int
    in_stock: bool
    sizes_in_stock: list[str] = Field(description="Sizes with at least one unit, XS to XXL order.")
    low_stock_note: str | None = Field(
        default=None, description='e.g. "Only 2 left in XL": the scarcest in-stock size, when 5 or fewer remain.'
    )


class ProductDetail(ProductCard):
    """Everything the single-product page shows."""

    colors: list[str]
    search_tags: list[str]
    inventory: list[SizeStock]


class Category(BaseModel):
    name: str
    count: int


# ---------- Accounts ----------

MAX_PASSWORD_LENGTH = 128


class SignupRequest(BaseModel):
    first_name: str = Field(max_length=50)
    last_name: str = Field(max_length=50)
    email: str = Field(max_length=254)
    password: str = Field(max_length=MAX_PASSWORD_LENGTH)
    confirm_password: str = Field(max_length=MAX_PASSWORD_LENGTH)


class LoginRequest(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=MAX_PASSWORD_LENGTH)


class UserOut(BaseModel):
    """Public view of a user. Deliberately has no password_hash field, so it can never leak."""

    id: int
    first_name: str
    last_name: str
    name: str
    email: str
    created_at: str


# ---------- Chat: what the website sends and gets back ----------

MAX_MESSAGE_LENGTH = 1000


class ChatTurn(BaseModel):
    """One earlier message. Only used for guests; signed-in history comes from the database."""

    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class PageContext(BaseModel):
    """What the shopper is looking at when they send a message (sent by the website).

    Only ids and labels: the backend looks every product up in the database itself,
    ignores ids that don't exist, and never trusts the browser for names or prices.
    """

    path: str = Field(default="/", max_length=200, description='The page URL path, e.g. "/products/basic-hoodie-big-yale".')
    product_id: str | None = Field(default=None, max_length=120, description="Set on a single-product page.")
    category_filter: str | None = Field(default=None, max_length=40, description="The Products page category chip, if any.")
    results_heading: str | None = Field(default=None, max_length=60, description="Heading of the concierge results shown on the page.")
    result_product_ids: list[str] = Field(default_factory=list, max_length=12, description="Concierge results on the page, in order.")


class CartLine(BaseModel):
    """One line of the shopper's cart, as the browser holds it (the cart lives in the browser)."""

    product_id: str = Field(max_length=120)
    size: str = Field(max_length=8)
    quantity: int = Field(ge=1, le=99)


class CartAction(BaseModel):
    """A change to the cart that the concierge made; the website applies it to the browser cart."""

    action: Literal["add", "remove"]
    product_id: str
    size: str
    quantity: int = Field(description="Units added, or units removed.")
    name: str
    price: float
    image_url: str
    available: int = Field(description="Units in stock in this size right now, so the website can cap the cart.")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)
    history: list[ChatTurn] = Field(default_factory=list, max_length=40)
    # Where the shopper is, so "do you have this in pink?" or "the second one" makes sense.
    page: PageContext = Field(default_factory=PageContext)
    # What is in the shopper's cart, so the concierge can add to it without overselling stock.
    cart: list[CartLine] = Field(default_factory=list, max_length=50)


class ChatReply(BaseModel):
    """What POST /api/chat sends back to the website.

    The agent's ShopperReply only names product ids; main.py turns those into live
    ProductCards, so the AI never supplies a price that reaches the screen. When
    `products` is non-empty the website shows them as a results grid on the page.
    """

    reply: str = Field(description="The concierge's message, plain text with optional **bold** and '- ' bullets.")
    products: list[ProductCard] = Field(description="Matching items to show on the page, most relevant first.")
    results_heading: str | None = Field(default=None, description='Title for the on-page results, e.g. "Gray hoodies".')
    cart_actions: list[CartAction] = Field(default_factory=list, description="Cart changes the website should apply.")


class ChatMessageOut(BaseModel):
    """A saved message, for reloading a signed-in shopper's conversation."""

    id: int
    role: Literal["user", "assistant"]
    content: str
    products: list[ProductCard]
    created_at: str


# ---------- Agent: structured output and tool results ----------


class ShopperReply(BaseModel):
    """The agent's own structured answer (PydanticAI output_type).

    The model must fill in exactly these fields. agent.py checks them before main.py
    turns product_ids into ProductCards for the ChatReply.
    """

    reply: str = Field(
        description="What to say to the shopper. Short and friendly; plain text with optional **bold** and '- ' bullets."
    )
    product_ids: list[str] = Field(
        default_factory=list,
        max_length=12,
        description=(
            "product_id values of the matching items to show as cards on the page, most relevant first (up to 12). "
            "Only ids returned by a tool in this conversation. Empty if no products should be shown."
        ),
    )
    results_heading: str | None = Field(
        default=None,
        max_length=60,
        description=(
            'A short title for the cards shown on the page, naming what was searched, e.g. "Gray hoodies", '
            '"Gifts for Grandma", "Berkeley College pieces". No prices. Null when product_ids is empty.'
        ),
    )


# Stock labels the agent can repeat without doing any judging of its own.
StockStatus = Literal["in_stock", "low_stock", "sold_out"]
LOW_STOCK_THRESHOLD = 5  # 1-5 units counts as low stock (same rule as the website's "Only N left")
SizeName = Literal["XS", "S", "M", "L", "XL", "XXL"]


class SizeAvailability(BaseModel):
    """Stock for one size, straight from the inventory table."""

    size: SizeName
    quantity: int = Field(ge=0, description="Units on hand right now. 0 means sold out in this size.")
    status: StockStatus = Field(description="sold_out = 0, low_stock = 1-5, in_stock = 6 or more.")


class ProductRef(BaseModel):
    """Just enough to name a product, e.g. in "did you mean" suggestions."""

    product_id: str
    name: str


class ProductMatch(BaseModel):
    """One search hit: enough to recommend a product, kept small to save tokens."""

    product_id: str
    name: str
    category: str
    garment_type: str
    price: float = Field(description="Price in US dollars from the catalogue table.")
    price_text: str = Field(description='Price formatted for the reply, e.g. "$68.00". Quote this, not a rounded guess.')
    colors_on_item: list[str] = Field(description="Every color printed on the piece. Not a list of color options.")
    description: str
    sizes_in_stock: list[SizeName]
    low_stock_sizes: list[SizeName] = Field(description="Sizes with only 1-5 left (also listed in sizes_in_stock).")
    sold_out_sizes: list[SizeName]


class SearchResult(BaseModel):
    query: str
    filters: dict[str, str | float]
    total_matches: int = Field(description="How many products matched before trimming to the top results.")
    products: list[ProductMatch]
    note: str | None = None


class ProductInfo(BaseModel):
    """Everything the agent may say about one product: description, price, and stock in every size."""

    product_id: str
    name: str
    category: str
    garment_type: str
    description: str
    price: float = Field(description="Price in US dollars from the catalogue table.")
    price_text: str = Field(description='Price formatted for the reply, e.g. "$68.00".')
    colors_on_item: list[str] = Field(description="Every color printed on the piece. Not a list of color options.")
    stock_by_size: list[SizeAvailability] = Field(description="All six sizes, XS to XXL, with live quantities.")
    total_in_stock: int = Field(description="Sum of quantities across all sizes.")
    sizes_in_stock: list[SizeName]
    low_stock_sizes: list[SizeName]
    sold_out_sizes: list[SizeName]
    sold_out_everywhere: bool = Field(description="True only if every size is at 0.")


class StockCheck(BaseModel):
    """The answer to "is size X of product Y in stock?" """

    product_id: str
    name: str
    price_text: str
    size: SizeName
    quantity: int = Field(ge=0, description="Units on hand in this size right now.")
    status: StockStatus
    say_this: str = Field(description='A plain, accurate sentence about this size, e.g. "Sold out in L." Use it as the basis of the reply.')
    other_sizes_in_stock: list[SizeAvailability] = Field(description="Alternatives to offer, with their own quantities.")


class ProductNotFound(BaseModel):
    """Returned instead of a product when the id or name doesn't match anything."""

    found: Literal[False] = False
    looked_for: str
    message: str
    did_you_mean: list[ProductRef] = Field(description="Closest product names, if any. Never present these as the same item.")


class SizeNotCarried(BaseModel):
    """Returned when the shopper asks for a size the shop doesn't make."""

    found: Literal[False] = False
    size_asked: str
    message: str
    sizes_we_carry: list[SizeName]


class ShopperProfile(BaseModel):
    """The signed-in shopper's own account details (never anyone else's)."""

    first_name: str
    last_name: str
    email: str
    member_since: str = Field(description="Account creation date, YYYY-MM-DD.")
    saved_messages: int = Field(description="How many chat messages we have saved for this shopper.")


class PastMessage(BaseModel):
    role: Literal["user", "assistant"]
    said_on: str = Field(description="Date and time the message was saved (UTC).")
    text: str = Field(description="The message, trimmed to about 300 characters.")
    products_shown: list[ProductRef] = Field(description="Products that were shown with this message, if any.")


class RecallResult(BaseModel):
    """Earlier messages from this shopper's own saved conversations."""

    query: str
    matches: list[PastMessage] = Field(description="Newest first.")
    note: str | None = None


class CartToolResult(BaseModel):
    """What add_to_cart / remove_from_cart did."""

    done: bool = Field(description="True if the cart was actually changed.")
    product_id: str
    name: str
    size: SizeName
    price_text: str
    quantity_changed: int = Field(description="Units added (or removed). 0 if nothing changed.")
    now_in_cart: int = Field(description="Units of this piece in this size in the cart afterwards.")
    in_stock: int = Field(description="Units in stock in this size right now.")
    say_this: str = Field(description="An accurate sentence about what happened. Base the reply on it.")


class CartViewLine(BaseModel):
    product_id: str
    name: str
    size: SizeName
    quantity: int
    price_text: str
    line_total_text: str
    in_stock: int
    problem: str | None = Field(default=None, description="e.g. 'Only 2 left in L' or 'Sold out in L'.")


class CartView(BaseModel):
    lines: list[CartViewLine]
    item_count: int
    subtotal_text: str = Field(description="Live prices x quantities. Shipping and tax are not included.")
    note: str


class CategoryInfo(BaseModel):
    name: str
    count: int
    min_price: float
    max_price: float


# ---------- Audit trail (Problem 12) ----------

AuditStopReason = Literal["final_answer", "content_filter", "usage_limit", "model_error", "error", "cancelled"]


class AuditToolCall(BaseModel):
    """One step of the agent loop: a tool call, or the honesty check sending an answer back."""

    step: int = Field(description="Order within the run, starting at 1.")
    tool: str = Field(description="Tool name, or 'honesty_check' when the answer validator asked for a rewrite.")
    args: str = Field(description="The inputs the agent passed to the tool, as short JSON (trimmed to ~160 characters).")
    result: str = Field(description="What came back, in one short line (trimmed to ~200 characters).")
    outcome: Literal["ok", "retry", "error"]


class AuditEntry(BaseModel):
    """The record of one agent run (one chat message): one entry in output/audit_trail.json."""

    run_id: str
    started_at: str = Field(description="UTC, ISO 8601.")
    finished_at: str
    seconds: float
    route: str = Field(description="Which API route ran the agent: /api/chat or /api/chat/stream.")
    shopper: str = Field(description="'guest' or 'user:<id>'. Never a name or email.")
    page: str = Field(description="The page path the shopper was on.")
    message: str = Field(description="The shopper's message, trimmed to ~120 characters.")
    model: str = Field(description="The model that actually answered, as reported by the gateway.")
    tool_calls: list[AuditToolCall]
    stop_reason: AuditStopReason = Field(
        description=(
            "Why the loop ended: final_answer, content_filter (the gateway's safety filter blocked the message; "
            "the shopper got a polite refusal), usage_limit (hit the request/tool cap), model_error, error, or cancelled."
        )
    )
    model_finish_reason: str | None = Field(default=None, description="The model's own reason on its last response, e.g. 'stop' or 'tool_call'.")
    reply: str | None = Field(default=None, description="The final reply, trimmed to ~160 characters.")
    product_ids: list[str] = Field(default_factory=list)
    cart_actions: list[str] = Field(default_factory=list, description="e.g. 'add 1 × fencing-left-chest-hoodie (M)'.")
    usage: dict[str, int] = Field(default_factory=dict, description="Model requests, tool calls, and tokens used.")
    error: str | None = None
