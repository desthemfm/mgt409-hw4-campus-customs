# Problem 9 - Usability Improvements

Problem 9 asks for **two front-end and two agent/backend usability improvements**. We first read it as a choice of one pair or the other and built only the backend pair. A review caught this (Problem 14), and the front-end pair below was verified, extended where it fell short, and documented.

| # | Type | Improvement | In one line |
|---|---|---|---|
| 1 | Backend | **Streaming replies** | The answer appears as it's written, with live "what I'm doing" updates |
| 2 | Backend | **Cart actions from the chat** | The concierge can add, remove, or list cart items on request, never past stock |
| 3 | Front end | **Game-Day Kit** | Three pieces for the stands, one size, one click, with live stock per piece |
| 4 | Front end | **Shop your size** | Show only pieces in stock in my size; my size is remembered and preselected |

Each section says **what it adds**, **why it helps** the Campus Customs shopper and the business, **how it works**, and **how we tested it**. Screenshot evidence for all four is in `output/app_check.html` (checks 3a–3f).

---

## 1. Streaming replies (backend)

### What we added

Before, after a shopper sent a message, the chat showed three bouncing dots for **5–10 seconds** and then the whole answer appeared at once. Now:

1. **A live status line** appears as soon as the concierge starts working: "Searching the collection…", "Checking sizes and stock…", "Looking up the details…", "Looking back through our earlier chats…".
2. **The reply writes itself word by word**, in a lighter, dashed "draft" bubble marked *Writing…*.
3. When the answer is finished and has **passed the answer check** (Problem 6), the draft is replaced by the final reply, and any matching product cards appear on the page.

**Important limit:** the draft is shown **before** the answer check runs, and only the finished answer is checked. If the check rejects it, the draft is cleared ("Double-checking that answer…") and the rewritten, checked answer replaces it. So a wrong number could appear briefly in a draft, which is why the draft is styled as provisional (dashed, *Writing…*).

### Why it helps the shopper

- **It feels much faster.** Total time is about the same, but in our test something useful appeared after about 5 seconds instead of a silent wait. People judge speed by **how long until something happens**, not by when the last word arrives.
- **The status line builds trust.** "Checking sizes and stock…" shows the answer comes from the shop's real inventory, not a guess. That matters for a concierge whose main promise is honest prices and stock.
- **Shoppers can start reading right away.** For longer answers ("Tell me about the bomber jacket and which sizes you have"), they're halfway through by the time it finishes.

### Why it helps Campus Customs (the business)

- **Fewer abandoned chats.** A silent 10-second wait is when shoppers give up and leave. Visible progress keeps them engaged long enough to see products and add them to the cart.
- **It looks like a modern, premium service,** like the chat assistants shoppers already use, which suits the polished Bulldog Blue brand.
- **The same final checks.** The final text still goes through the same answer check (not the draft), the same product-card lookup from the database, and the same saving to `chat_messages` as before.

### How it works

- **Backend:** a new route, **`POST /api/chat/stream`** in `backend/main.py`, sends the answer as **NDJSON** (one small JSON message per line) instead of one big reply:

  | Event | Meaning |
  |---|---|
  | `{"type": "status", "text": "Checking sizes and stock…"}` | The agent started using a tool |
  | `{"type": "delta", "reply": "…reply so far…"}` | The reply as it's written (a draft) |
  | `{"type": "reset"}` | The honesty check sent the draft back; it's being rewritten |
  | `{"type": "done", "reply", "products", "results_heading"}` | The checked final answer and live product cards |
  | `{"type": "error", "detail": "…"}` | A friendly error message |

- **Agent:** `agent.run_chat()` takes an optional `on_event` callback and passes PydanticAI an **`event_stream_handler`**. A small `ReplyStreamer` class in `agent.py` listens to the agent's events:
  - a **tool starting** becomes a `status` event;
  - the **final answer**, which arrives as streamed JSON (`{"reply": "…", "product_ids": […]}`), is read **as it grows**, and the reply text so far is sent as `delta` events.

  The run itself is the normal `agent.run()`, so the **honesty check and its automatic retries are unchanged**.
- **Shared code:** `main.py` was split into `prepare_chat()` (rate limit, history, shopper and page context) and `finish_chat()` (live product cards and saving signed-in chats). The normal `/api/chat` and the streaming route behave identically; only the delivery differs.
- **Frontend:** `sendChatMessage()` in `src/chat.ts` reads the stream line by line as it arrives, calls `onUpdate` for each status or draft, and returns the final reply. `ChatWidget.tsx` shows the dots plus the status, then the dashed draft, then the final answer.

### Problems found and fixed while building it

- **The gateway cache broke multi-step answers.** Asking the same question twice made the course's Portkey gateway return a cached response containing placeholder ids (`portkey_cache_…`), and Azure rejected them on the agent's next step ("Expected an ID that begins with 'fc'"). A cached answer could also repeat **old stock levels**. Fix: the model client now sends `x-portkey-cache-force-refresh: true`, so every answer is fresh (`tools.make_model()`). We confirmed this header doesn't slow or buffer streaming (about 30 text chunks either way).
- **The reply arrived in one piece.** The agent was streaming its answer in 30–50 small pieces, but our partial-JSON reader (`pydantic_core.from_json(..., allow_partial=True)`) **drops a text field until its closing quote arrives**. Switching to `allow_partial="trailing-strings"` keeps the unfinished text. Before: 1 update per answer. After: 30.

### How we tested it

- **Stream test** (`/api/chat/stream`, "What would you suggest for my aunt?"):
  - 1.8s: `status` "Searching the collection…"
  - 5.5s: first `delta` ("I")
  - **30 deltas** building "I'd suggest the Yale Aunt Hoodie ($68.00)…"
  - 7.3s: `done`, with the Yale Aunt Hoodie card and heading "Gifts for your aunt"
- **In the browser** ("What do you have for my brother?"), sampled every 0.3s:
  - 0.3s: dots
  - 4.8s: "Searching the collection…"
  - 7.0s: draft starts writing
  - 10.0s: final answer, with "Gifts for your brother" cards on the page
- **Screenshot evidence:** the reply to "Tell me about the Brooks Brothers bomber jacket…" was caught mid-stream, as a dashed draft bubble reading "…is **$98.00**. Dark navy full-zip bomber jacket…" with *Writing…* underneath.
- **No change to accuracy or saving:** the final answers matched the database ($68.00 Aunt Hoodie; $98.00 bomber), and the original non-streaming `/api/chat` route still works for scripts and tests.

---

## 2. Cart actions from the chat (backend)

### What we added

The concierge can now **act**, not just talk. A shopper can say:

- "Add this in a medium"
- "I'll take two of the Grandpa Hoodie in large"
- "What's in my cart?"
- "Remove the XL ones"

The concierge checks live stock, changes the cart, and confirms in the chat with a green **"✓ Added to cart: 1 × Fencing Left Chest Hoodie (M) · View cart →"** note. The **Cart** badge at the top of the page updates immediately.

### Why it helps the shopper

- **Fewer steps.** Before, a shopper who found something in the chat had to click the card, open the product page, pick a size, and press Add to Cart. Now it's one sentence, in the conversation they're already having. That's especially handy on a phone.
- **It won't let them make a mistake.**
  - It **never guesses a size** ("What size would you like in the Yale Dad Hoodie?").
  - It **won't add a sold-out size** and offers sizes that are in stock instead.
  - It **won't add more than exists**: asking for 20 XL adds the 2 we have and says so.
- **"What's in my cart?" gets a clear answer,** with live prices, a subtotal, and a warning if something in the cart has since sold out.
- **Honest about what a cart is.** The concierge says plainly that nothing is charged or reserved and that online checkout isn't available yet.

### Why it helps Campus Customs (the business)

- **More conversations turn into baskets.** Every extra click between "I like that" and "it's in my cart" loses shoppers. Letting the concierge add the item at the moment of interest is how a good salesperson on the shop floor works: "Shall I set one aside in a medium for you?"
- **Gift shoppers in particular** (parents, grandparents, relatives) are guided from "something for my grandmother" to a sized item in the cart in one conversation.
- **No overselling.** The cart can never hold more than the inventory table says is in stock, so customers aren't promised items that don't exist.
- **It's ready for real checkout later.** Cart actions are typed (`CartAction`), so connecting them to a real order system later is straightforward.

### How it works

- **The website sends the cart** with every chat message (`ChatRequest.cart`: product id, size, and quantity for each line). The cart itself still lives in the shopper's browser, as in Problem 3. The server keeps only real products and sizes (`tools.clean_cart`), so a fake product id is ignored.
- **Three new agent tools** in `tools.py`, wired in `agent.py`:

  | Tool | What it does | Returns |
  |---|---|---|
  | `add_to_cart(product, size, quantity=1)` | Looks up live stock, subtracts what's already in the cart, and adds up to 10, never more than is left | `CartToolResult {done, quantity_changed, now_in_cart, in_stock, price_text, say_this}` |
  | `remove_from_cart(product, size, quantity?)` | Removes some or all of a size | `CartToolResult` |
  | `view_cart()` | Live prices × quantities, a subtotal, and any stock problem per line | `CartView {lines, item_count, subtotal_text, note}` |

  `say_this` is an accurate sentence written by code ("Added 2 × … That's all we have in that size."), which the agent builds its reply on, just like the stock tools in Problem 6.
- **Cart changes travel back as data:** every change is recorded as a `CartAction {action, product_id, size, quantity, name, price, image_url, available}` and returned in `ChatReply.cart_actions`. The chat widget applies them to the browser cart, still capped at `available`, and shows the green confirmation.
- **New honesty rule:** the answer check in `agent.py` now also rejects any reply that says something was **"added to your cart"** or is **"now in your cart"** unless `add_to_cart` actually added something this turn. The agent can't claim an action it didn't take. Cart subtotals and line totals are recorded as tool-returned prices, so the price check accepts them.
- **Prompt rules** (`prompts/prompt.md`, "The shopper's cart"):
  - only add on a clear request;
  - never guess a size;
  - report exactly what the tool did;
  - never say "added" unless `done: true`;
  - never pretend to check out or hold stock.

  The "Know your limits" rule was updated from "shoppers add pieces from the product page" to "you **can** add or remove pieces when asked; the cart is not an order."
- **Streaming status** (improvement 1): "Adding it to your cart…", "Updating your cart…", "Looking at your cart…".

### How we tested it

**Offline, no AI** (Fencing Left Chest Hoodie: XS 0, S 12, M 15, L 0, XL 2, XXL 0):

| Call | Result |
|---|---|
| add L | `done: false`, "sold out in L, so nothing was added" |
| add M | 1 added |
| add 20 XL | **2 added**, "That's all we have in that size" |
| add XL again | 0 added, "the cart already holds all 2" |
| add XXXL / unknown product | `SizeNotCarried` / `ProductNotFound` |
| view cart | M ×1 $68.00, XL ×2 $136.00, **subtotal $204.00** |
| remove XL | 2 removed |
| browser cart already holding 2 XL (plus a fake product id) | the fake id was dropped; adding XL was refused |

`backend/tests/test_tools.py` still passes all 3,314 checks.

**Live in the browser**, on the Fencing hoodie page, starting with an empty cart:

| Shopper said | Concierge | Cart after |
|---|---|---|
| "Add this in a large" | "…sold out in large, so nothing was added. Small and medium are in stock, and XL has only 2 left." | empty, badge 0 |
| "Okay, add a medium then" | "Added 1 Fencing Left Chest Hoodie in medium to your cart at $68.00…" plus a ✓ note | M×1, badge **1** |
| "Actually add 20 in XL too" | "Only 2 were left in XL, so I added those rather than the 20 requested…" | M×1, XL×2, badge **3** |
| "What's in my cart now?" | "1 in medium — $68.00 · 2 in XL — $136.00 (only 2 left in stock) · Subtotal: $204.00…" | unchanged |
| "Remove the XL ones please" | "Removed both XL Fencing Left Chest Hoodies from your cart." plus a ✓ note | M×1, badge **1** |
| "Add the Yale Dad Hoodie to my cart" (no size) | "Certainly—what size would you like in the Yale Dad Hoodie? It's $68.00." | unchanged; **no guessing** |

- **Cart page:** clicking **View cart →** in the chat showed exactly "Fencing Left Chest Hoodie, Size M · $68.00", subtotal $68.00.
- **Status lines seen** during the test: "Checking sizes and stock…", "Adding it to your cart…", "Looking at your cart…", "Updating your cart…", "Searching the collection…".

---

## 3. Game-Day Kit (front end)

### What it adds

On the home page, **"The Game-Day Kit"** groups three pieces for the stands:
- the 2025 Yale vs. Harvard T-Shirt, $32.00;
- the Basic Hoodie Big Yale, $68.00;
- the Super Heavyweight Crewneck Arched Yale Crest, $58.00.

The shopper picks **one size**, and each piece immediately shows its **live stock in that size**: "In stock in XL," "Only 2 left in XL," or a crossed-out "Sold out in XL." **One button** adds every piece that's in stock in that size. A note says exactly what happened, for example "Added 3 of 3 in XL," or which piece was skipped and why. The total shown, $158.00, is the three database prices added up, with no invented discount.

### Why it helps the shopper

- **Three decisions become one.** Without the kit, gearing up for The Game means opening three product pages, picking a size three times, and pressing Add to Cart three times.
- **No surprises at the cart.** Stock is shown per piece *before* adding, and a sold-out piece is skipped with an explanation instead of failing silently.

### Why it helps Campus Customs (the business)

- **Bigger baskets:** one click turns a single-item visit into a three-item basket, at the moment of peak rivalry interest.
- **No overselling:** the kit adds at most what's in stock, counting what's already in the cart.

### Is it a real usability improvement?

Yes. It was built during the Problem 10 redesign, but it's a distinct interactive feature: its own size picker, live per-size stock for several products at once, a combined add, and honest partial-add handling. That's different from the product page's single-item Add to Cart.

### How it works

`frontend/src/components/GameDayKit.tsx`:
- loads the three products' live details from `GET /api/products/{id}`;
- takes the size from a dropdown;
- calls the shared cart's `add()` once per piece, capped at that size's stock;
- writes the note from what was actually added.

The pieces are set in `frontend/src/gameDay.ts`.

### How we tested it

App check **3d** (Playwright, live site, `output/app_check_images/game_day_kit.png`):
- In **XL**, the kit's stock labels were "In stock in XL," "Only 2 left in XL," and "In stock in XL," exactly matching the database.
- One click added the 3 in-stock pieces (cart badge 3, cart contents checked), and the note read "Added 3 of 3 in XL."

An earlier manual test (Problem 10) showed that once the cart held both XL Basic Hoodies in stock, the kit added only the other 2 pieces and named the skipped one.

---

## 4. Shop your size (front end)

### What it adds

- **"Your size" buttons on the Products page** (Any, XS, S, M, L, XL, XXL). Choosing one shows **only the pieces in stock in that size**, for example "77 of 102 pieces in stock in XL." Each card confirms it: "✓ XL in stock · also S, M, L, XXL." It works together with the category buttons, and both are kept in the URL (`/products?category=Hoodies&size=XL`), so the view can be shared and the Back button works.
- **The size is remembered** in the browser. On any product page it's **preselected** when that size is in stock ("Size XL (your size): 25 in stock"), so Add to Cart is one click away. Picking a size on a product page updates the remembered size too.
- If a size is remembered but not active, the Products page offers **"Show only my size (XL)."**

### Why the existing stock display wasn't enough on its own

Before this, cards already listed sizes in stock and a "last few" note. That was **display only**: a shopper who wears XL still had to read the size line on up to 102 cards, and couldn't act on it. It also arrived with the card and design work rather than as a feature shoppers use. "Shop your size" turns that stock data into something the shopper can act on.

### Why it helps the shopper

- **No dead ends:** they never open a product only to find their size is sold out.
- **Less repetition:** they set their size once, not on every product page.
- **Mobile-friendly:** filtering beats scrolling 102 cards on a phone.

### Why it helps Campus Customs (the business)

- **Shoppers reach buyable items faster**, which means fewer abandoned visits.
- **It surfaces deep stock:** pieces with plenty left in a size get seen by the shoppers who can actually buy them.

### How it works

- `frontend/src/sizePreference.ts` stores the size in `localStorage` (`campus-customs-size`).
- `Products.tsx` filters the live product list by each card's `sizes_in_stock`, which comes from the inventory table through `GET /api/products`.
- `ProductCard.tsx` highlights the chosen size.
- `ProductDetail.tsx` preselects the remembered size when it's in stock.

No backend change was needed: the cards already carried live `sizes_in_stock`.

### How we tested it

App check **3e** and **3f** (Playwright, live site; `shop_your_size.png`, `shop_your_size_product.png`):
- Choosing **XL** showed **77 of 102**, exactly the 77 products whose XL quantity is above 0 in the database.
- Every card's size line started "✓ XL in stock."
- The URL became `/products?size=XL`, and the remembered size was XL.
- Opening a product with XL in stock showed **XL already selected**: "Size XL (your size): 25 in stock."

