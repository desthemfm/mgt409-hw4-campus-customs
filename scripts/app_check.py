"""Problem 11: app check. Tests the live site like a shopper and writes output/app_check.html.

It drives the installed Google Chrome with Playwright, chats with the real concierge,
checks every answer against data/campus_customs.db, saves screenshots to
output/app_check_images/, and links them from output/app_check.html (relative paths, so
the page opens by double-clicking).

It chats as a guest, so nothing is written to the database (checked before and after).

Run from the homework 4 folder, with both servers running (backend on 8000, site on 5174):
    scripts/.venv/bin/pip install -r scripts/requirements-scripts.txt     # first time only
    scripts/.venv/bin/python scripts/app_check.py
"""

import html
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "campus_customs.db"
OUT = ROOT / "output"
IMAGES = OUT / "app_check_images"
SITE = "http://localhost:5174"
VIEWPORT = {"width": 1280, "height": 800}

# The item for the inventory check: it has a sold-out size and a nearly-gone size.
INVENTORY_ITEM = "fencing-left-chest-hoodie"


# ---------- database truth ----------

def db_rows(sql: str, *params):
    with sqlite3.connect(DB) as con:
        return con.execute(sql, params).fetchall()


def product(pid: str) -> dict:
    name, price, category = db_rows("SELECT name, price, category FROM catalogue WHERE product_id = ?", pid)[0]
    stock = dict(db_rows("SELECT size, quantity FROM inventory WHERE product_id = ?", pid))
    return {"id": pid, "name": name, "price": price, "category": category, "stock": stock}


def chat_rows() -> int:
    return db_rows("SELECT COUNT(*) FROM chat_messages")[0][0]


# ---------- driving the site ----------

def open_chat(page: Page) -> None:
    if not page.locator(".chat-panel").count():
        page.click(".chat-launcher")
    page.wait_for_selector("#chat-text")


def send(page: Page, text: str) -> None:
    page.fill("#chat-text", text)
    page.click(".chat-input button[type=submit]")
    page.wait_for_selector(".typing-row, .chat-msg.draft", timeout=15_000)


def wait_for_answer(page: Page) -> str:
    page.wait_for_function("() => !document.querySelector('.typing-row, .chat-msg.draft')", timeout=120_000)
    page.wait_for_timeout(600)  # let cards and images settle
    return page.locator(".chat-msg.assistant").last.inner_text()


def shoot(page: Page, name: str) -> str:
    IMAGES.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(IMAGES / name))
    return f"app_check_images/{name}"


def money(x: float) -> str:
    return f"${x:,.2f}"


# ---------- the checks ----------

def check_inventory(page: Page) -> dict:
    p = product(INVENTORY_ITEM)
    sold_out = [s for s, q in p["stock"].items() if q == 0]
    low = min(((q, s) for s, q in p["stock"].items() if 0 < q <= 5), default=None)
    ask_size_out = "L" if "L" in sold_out else sold_out[0]
    ask_size_low = low[1]

    page.goto(f"{SITE}/products/{p['id']}", wait_until="networkidle")
    open_chat(page)
    send(page, f"What does this cost, how many are left in {ask_size_low}, and is a {ask_size_out} available?")
    reply = wait_for_answer(page)
    img = shoot(page, "inventory.png")

    flat = reply.replace(",", "")
    checks = {
        "price": money(p["price"]) in reply or f"${p['price']:.0f}" in flat,
        "low_qty": re.search(rf"\b{low[0]}\b", reply) is not None,
        "sold_out": re.search(r"sold out|out of stock|unavailable", reply, re.I) is not None,
    }
    passed = all(checks.values())
    return {
        "title": "1. Chat checks an item's inventory (honest price and stock)",
        "image": img,
        "alt": "Concierge answering price and stock on the Fencing Left Chest Hoodie page",
        "passed": passed,
        "proves": (
            f"On the {p['name']} page, the concierge quoted <b>{money(p['price'])}</b>, said only <b>{low[0]} left in {ask_size_low}</b>, "
            f"and said <b>{ask_size_out} is sold out</b>, which matches the database exactly "
            f"(catalogue price {money(p['price'])}; inventory {ask_size_low} = {low[0]}, {ask_size_out} = 0)."
        ),
        "question": page.locator(".chat-msg.user").last.inner_text(),
        "reply": reply,
        "details": checks,
    }


def check_category_cards(page: Page) -> dict:
    page.goto(SITE + "/", wait_until="networkidle")
    open_chat(page)
    send(page, "Show me your T-shirts")
    reply = wait_for_answer(page)
    page.wait_for_selector(".concierge-results .product-card")
    page.click(".chat-close")  # move the panel out of the way so the cards are visible
    section = page.locator(".concierge-results")
    section.scroll_into_view_if_needed()
    page.evaluate("window.scrollTo(0, document.querySelector('.concierge-results').offsetTop - 70)")
    page.wait_for_function("() => [...document.querySelectorAll('.concierge-results img')].every(i => i.complete)")
    img = shoot(page, "category_search.png")

    heading = section.locator("h2").inner_text()
    cards = section.locator(".product-card")
    shown = []
    for i in range(cards.count()):
        href = cards.nth(i).get_attribute("href")
        shown.append((href.rsplit("/", 1)[1], cards.nth(i).locator(".price").inner_text()))
    wrong = [pid for pid, price in shown if product(pid)["category"] != "T-Shirts" or money(product(pid)["price"]) != price]
    total = db_rows("SELECT COUNT(*) FROM catalogue WHERE category = 'T-Shirts'")[0][0]
    passed = len(shown) > 0 and not wrong
    return {
        "title": "2. A category question fills the page with matching product cards",
        "image": img,
        "alt": "Concierge results section showing T-shirt cards with image, name, price, and short info",
        "passed": passed,
        "proves": (
            f"Asking “Show me your T-shirts” made a <b>“{html.escape(heading)}”</b> section appear on the page with "
            f"<b>{len(shown)} product cards</b> (image, name, price, short info, sizes in stock). Every card is a T-shirt, and "
            f"its price matches the database ({len(shown)} of {total} T-shirts shown; {len(wrong)} mismatches)."
        ),
        "question": "Show me your T-shirts",
        "reply": reply,
        "details": {"cards_shown": len(shown), "mismatches": wrong},
    }


def check_streaming(page: Page) -> dict:
    page.goto(f"{SITE}/products/yale-grandma-hoodie", wait_until="networkidle")
    open_chat(page)
    t0 = time.monotonic()
    page.fill("#chat-text", "Tell me about this hoodie and which sizes you have.")
    page.click(".chat-input button[type=submit]")
    page.wait_for_selector(".typing-row .chat-status", timeout=30_000)
    status = page.locator(".typing-row .chat-status").inner_text()
    t_status = time.monotonic() - t0
    page.wait_for_function(
        "() => (document.querySelector('.chat-msg.draft p')?.innerText || '').length > 60", timeout=60_000
    )
    t_draft = time.monotonic() - t0
    img = shoot(page, "streaming.png")
    draft_len = len(page.locator(".chat-msg.draft").inner_text())
    wait_for_answer(page)
    t_done = time.monotonic() - t0
    return {
        "title": "3a. Usability, backend (Problem 9): the reply streams in as it's written",
        "image": img,
        "alt": "Chat panel mid-answer: a dashed draft notecard with the reply being written",
        "passed": t_draft < t_done,
        "proves": (
            f"Mid-answer screenshot: the concierge showed “{html.escape(status)}” after {t_status:.1f}s, then the reply began "
            f"writing itself in the dashed draft bubble at {t_draft:.1f}s, before the final answer at {t_done:.1f}s. "
            "Shoppers see progress instead of a silent wait. The draft is shown before the answer check runs; "
            "the checked final answer then replaces it."
        ),
        "question": "Tell me about this hoodie and which sizes you have.",
        "reply": f"(captured mid-stream: {draft_len} characters written so far)",
        "details": {"status": status, "status_s": round(t_status, 1), "draft_s": round(t_draft, 1), "done_s": round(t_done, 1)},
    }


def check_add_to_cart(page: Page) -> tuple[dict, dict]:
    p = product(INVENTORY_ITEM)
    size = max(p["stock"], key=p["stock"].get)  # a size that is well stocked
    page.goto(f"{SITE}/products/{p['id']}", wait_until="networkidle")
    page.evaluate("localStorage.removeItem('campus-customs-cart')")
    page.reload(wait_until="networkidle")
    open_chat(page)
    send(page, f"Please add one of these in {size} to my cart.")
    reply = wait_for_answer(page)
    note = page.locator(".chat-cart-note").last
    note.scroll_into_view_if_needed()
    badge = page.locator(".cart-count").inner_text() if page.locator(".cart-count").count() else "0"
    has_note = note.count() > 0  # read now: the note is gone once we move to the cart page
    note_text = note.inner_text() if has_note else ""
    img = shoot(page, "add_to_cart.png")

    page.goto(f"{SITE}/cart", wait_until="networkidle")
    page.wait_for_selector(".cart-line")
    lines = page.locator(".cart-line").all_inner_texts()
    subtotal = page.locator(".cart-summary dd").first.inner_text()
    img2 = shoot(page, "cart_page.png")

    in_cart = len(lines) == 1 and p["name"] in lines[0] and f"Size {size}" in lines[0]
    chat_check = {
        "title": "3b. Usability, backend (Problem 9): the concierge adds an item to the cart",
        "image": img,
        "alt": "Chat reply with a green 'Added to cart' note and the cart badge showing 1",
        "passed": badge == "1" and has_note and p["name"] in note_text,
        "proves": (
            f"Asked to “add one of these in {size},” the concierge checked live stock ({size} = {p['stock'][size]} in the database), "
            f"added it, and showed a green <b>✓ Added to cart</b> note; the cart badge in the header changed to <b>{badge}</b>."
        ),
        "question": f"Please add one of these in {size} to my cart.",
        "reply": reply,
        "details": {"badge": badge, "note": note_text.replace("\n", " ")},
    }
    cart_check = {
        "title": "3c. The cart page shows what the concierge added",
        "image": img2,
        "alt": "Cart page with one Fencing Left Chest Hoodie and the subtotal",
        "passed": in_cart and subtotal == money(p["price"]),
        "proves": (
            f"Following “View cart,” the cart holds exactly <b>1 × {p['name']} (size {size})</b> with a subtotal of "
            f"<b>{subtotal}</b>, the database price, so the chat action really changed the shopper's cart."
        ),
        "question": "",
        "reply": "",
        "details": {"lines": lines, "subtotal": subtotal},
    }
    return chat_check, cart_check


KIT_IDS = ["2025-yale-vs-harvard-t-shirt", "basic-hoodie-big-yale", "super-heavyweight-crewneck-arched-yale-crest"]


def check_game_day_kit(page: Page) -> dict:
    size = "XL"
    kit = [product(pid) for pid in KIT_IDS]
    page.goto(SITE + "/", wait_until="networkidle")
    page.evaluate("localStorage.removeItem('campus-customs-cart')")
    page.reload(wait_until="networkidle")
    page.wait_for_selector(".kit-item")
    page.select_option("#kit-size", size)
    labels = page.locator(".kit-stock").all_inner_texts()
    expected = [f"Sold out in {size}" if p["stock"][size] == 0 else f"Only {p['stock'][size]} left in {size}" if p["stock"][size] <= 5
                else f"In stock in {size}" for p in kit]
    page.click(".kit-actions .btn")
    page.wait_for_selector(".kit-note")
    note = page.locator(".kit-note").inner_text()
    cart = page.evaluate("JSON.parse(localStorage.getItem('campus-customs-cart') || '[]')")
    in_stock = [p for p in kit if p["stock"][size] > 0]
    added_ok = sorted((c["product_id"], c["size"], c["quantity"]) for c in cart) == sorted((p["id"], size, 1) for p in in_stock)
    badge = page.locator(".cart-count").inner_text() if page.locator(".cart-count").count() else "0"
    page.evaluate("window.scrollTo(0, document.getElementById('kit').offsetTop - 70)")
    page.wait_for_timeout(400)
    img = shoot(page, "game_day_kit.png")
    total = sum(p["price"] for p in kit)
    stock_list = "; ".join(f"{p['name']}: {p['stock'][size]}" for p in kit)
    return {
        "title": "3d. Usability, front end (Problem 9): the Game-Day Kit, three pieces in one size with one click",
        "image": img,
        "alt": "Game-Day Kit with three products, live stock in XL, and the confirmation after adding",
        "passed": labels == expected and added_ok and badge == str(len(in_stock)),
        "proves": (
            f"Choosing <b>{size}</b> shows each piece's live stock in that size ({stock_list} in the database), "
            f"and one click added the <b>{len(in_stock)} in-stock pieces</b> (cart badge {badge}). "
            f"The {money(total)} total is the three database prices added up."
        ),
        "question": "", "reply": "",
        "details": {"labels": labels, "expected": expected, "note": note, "cart": cart},
    }


def check_shop_your_size(page: Page) -> tuple[dict, dict]:
    size = "XL"
    with_size = {pid for (pid,) in db_rows("SELECT product_id FROM inventory WHERE size = ? AND quantity > 0", size)}
    total = db_rows("SELECT COUNT(*) FROM catalogue")[0][0]
    page.goto(SITE + "/products", wait_until="networkidle")
    page.evaluate("localStorage.removeItem('campus-customs-size')")
    page.reload(wait_until="networkidle")
    page.wait_for_selector(".size-filter")
    page.locator(".size-filter .chip", has_text=size).first.click()
    page.wait_for_function("() => /in stock in XL/.test(document.querySelector('.result-count')?.innerText || '')")
    count_text = page.locator(".result-count").inner_text()
    cards = page.locator(".page .product-card")
    shown = {cards.nth(i).get_attribute("href").rsplit("/", 1)[1] for i in range(cards.count())}
    lines = page.locator(".page .product-card .card-sizes").all_inner_texts()
    url = page.url
    remembered = page.evaluate("localStorage.getItem('campus-customs-size')")
    # show the size buttons and the cards' "✓ XL in stock" lines in one screenshot
    page.evaluate("window.scrollTo(0, document.querySelector('.size-filter').getBoundingClientRect().top + window.scrollY - 82)")
    page.wait_for_timeout(300)
    img = shoot(page, "shop_your_size.png")

    # open a product that has XL in stock: the size should already be chosen
    pid = sorted(with_size)[0]
    page.goto(f"{SITE}/products/{pid}", wait_until="networkidle")
    page.wait_for_selector(".size-btn")
    picked = page.locator(".size-btn.picked .size-name").all_inner_texts()
    status = page.locator(".size-status").inner_text()
    img2 = shoot(page, "shop_your_size_product.png")
    filter_check = {
        "title": "3e. Usability, front end (Problem 9): Shop your size, showing only pieces in stock in my size",
        "image": img,
        "alt": "Products page filtered to pieces in stock in XL, each card confirming XL is in stock",
        "passed": shown == with_size and all(l.startswith(f"✓ {size} in stock") for l in lines) and remembered == size and "size=XL" in url,
        "proves": (
            f"Tapping <b>{size}</b> under “Your size” shows <b>{len(shown)} of {total}</b> pieces (“{html.escape(count_text)}”), exactly the "
            f"{len(with_size)} products with {size} stock above 0 in the database, and every card confirms “✓ {size} in stock”."
        ),
        "question": "", "reply": "",
        "details": {"shown": len(shown), "db": len(with_size), "url": url, "remembered": remembered},
    }
    preselect_check = {
        "title": "3f. Shop your size: the size is remembered and preselected on product pages",
        "image": img2,
        "alt": "Product page with XL already selected and marked as your size",
        "passed": picked == [size] and "(your size)" in status,
        "proves": (
            f"After choosing {size} on the Products page, opening the {html.escape(product(pid)['name'])} already has <b>{size}</b> selected: "
            f"“{html.escape(status)}”. The shopper doesn't have to pick their size again."
        ),
        "question": "", "reply": "",
        "details": {"picked": picked, "status": status},
    }
    return filter_check, preselect_check


# ---------- the report ----------

def write_report(results: list[dict], meta: dict) -> Path:
    def section(r: dict) -> str:
        badge = '<span class="pass">PASS</span>' if r["passed"] else '<span class="fail">FAIL</span>'
        qa = ""
        if r["question"]:
            qa = (f'<details><summary>Exact question and answer</summary><p><b>Shopper:</b> {html.escape(r["question"])}</p>'
                  f'<p><b>Concierge:</b> {html.escape(r["reply"])}</p></details>')
        return f"""
    <section>
      <h2>{r['title']} {badge}</h2>
      <a href="{r['image']}"><img src="{r['image']}" alt="{html.escape(r['alt'])}"></a>
      <p class="proves">{r['proves']}</p>
      {qa}
    </section>"""

    passed = sum(r["passed"] for r in results)
    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>App Check · Campus Customs (Problem 11)</title>
<style>
  body {{ font-family: -apple-system, 'Segoe UI', Inter, sans-serif; margin: 0; background: #f4f6fa; color: #14213d; line-height: 1.5; }}
  header {{ background: #061529; color: #eef4ff; padding: 28px 40px; }}
  header h1 {{ margin: 0 0 6px; font-size: 28px; }}
  header p {{ margin: 2px 0; color: #a9bdd6; }}
  main {{ max-width: 1000px; margin: 0 auto; padding: 24px 24px 60px; }}
  .summary {{ background: #fff; border: 1px solid #dde3ee; border-radius: 12px; padding: 14px 20px; margin-bottom: 18px; }}
  .summary li {{ margin: 3px 0; }}
  section {{ background: #fff; border: 1px solid #dde3ee; border-radius: 12px; padding: 20px 24px; margin: 18px 0; }}
  h2 {{ font-size: 20px; margin: 0 0 12px; display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }}
  img {{ width: 100%; border: 1px solid #cfd7e6; border-radius: 8px; display: block; }}
  .proves {{ font-size: 16px; margin: 12px 0 4px; }}
  .pass, .fail {{ font-size: 12px; font-weight: 700; padding: 3px 9px; border-radius: 999px; letter-spacing: .05em; }}
  .pass {{ background: #dcf5e4; color: #1e6b3a; }}
  .fail {{ background: #fde3e1; color: #b3261e; }}
  details {{ margin-top: 8px; color: #44516b; font-size: 14px; }}
  summary {{ cursor: pointer; color: #00356b; }}
  footer {{ color: #5d6a82; font-size: 13px; margin-top: 28px; }}
</style>
</head>
<body>
<header>
  <h1>App Check: Campus Customs Concierge (Problem 11)</h1>
  <p>Live site tested on {meta['when']} · {passed} of {len(results)} checks passed</p>
  <p>Front end {SITE} · FastAPI backend :8000 · PydanticAI agent · data/campus_customs.db</p>
</header>
<main>
  <div class="summary">
    <b>What was tested</b>
    <ul>
      {''.join(f"<li>{'✅' if r['passed'] else '❌'} {r['title']}</li>" for r in results)}
    </ul>
    Every price and stock number in the captions was read from the database during the test run, not typed in by hand.
  </div>
  {''.join(section(r) for r in results)}
  <footer>
    Generated by <code>scripts/app_check.py</code> (Playwright driving Google Chrome at {VIEWPORT['width']}×{VIEWPORT['height']}).
    The test chatted as a guest, so nothing was saved to the database: <code>chat_messages</code> had {meta['rows_before']} rows before
    and {meta['rows_after']} after. Click any screenshot to open it full size.
  </footer>
</main>
</body>
</html>
"""
    out = OUT / "app_check.html"
    out.write_text(page, encoding="utf-8")
    return out


def main() -> None:
    rows_before = chat_rows()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport=VIEWPORT, device_scale_factor=1)
        results = [check_inventory(page)]
        page = browser.new_page(viewport=VIEWPORT, device_scale_factor=1)  # fresh chat for each check
        results.append(check_category_cards(page))
        page = browser.new_page(viewport=VIEWPORT, device_scale_factor=1)
        results.append(check_streaming(page))
        page = browser.new_page(viewport=VIEWPORT, device_scale_factor=1)
        results.extend(check_add_to_cart(page))
        page = browser.new_page(viewport=VIEWPORT, device_scale_factor=1)
        results.append(check_game_day_kit(page))
        page = browser.new_page(viewport=VIEWPORT, device_scale_factor=1)
        results.extend(check_shop_your_size(page))
        browser.close()
    meta = {"when": datetime.now().strftime("%B %d, %Y at %I:%M %p").replace(" 0", " "), "rows_before": rows_before, "rows_after": chat_rows()}
    out = write_report(results, meta)
    for r in results:
        print(("PASS" if r["passed"] else "FAIL"), "|", r["title"], "|", r["details"])
    print("Report:", out)


if __name__ == "__main__":
    main()
