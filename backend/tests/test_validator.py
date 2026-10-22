"""Regression checks for the price part of the honesty check (agent.price_problems). No AI, no cost.

Each case gives a reply and what the tools "saw" this turn (real prices from the database),
then checks the reply is rejected or accepted. Covers the gap found in review: a unit price
that is really a multiple ("One Fencing Left Chest Hoodie costs $136.00"), prices swapped
between products, and legitimate totals that must still pass.

Run from the backend folder:
    python tests/test_validator.py
"""

import os
import sqlite3
import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))  # the backend folder
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

import agent  # noqa: E402
import tools  # noqa: E402

tools.prepare_database()  # a fresh data pack works even if the server hasn't run yet

IDS = ["fencing-left-chest-hoodie", "boola-boola-t-shirt", "basic-hoodie-big-yale",
       "2025-yale-vs-harvard-t-shirt", "super-heavyweight-crewneck-arched-yale-crest"]
with sqlite3.connect(tools.DB_PATH) as con:
    DB = {pid: (name, price) for pid, name, price in con.execute(
        f"SELECT product_id, name, price FROM catalogue WHERE product_id IN ({','.join('?' * len(IDS))})", IDS)}
FENCING, BOOLA, BASIC, GAME_TEE, CREW = (DB[i] for i in IDS)
assert FENCING[1] == 68 and BOOLA[1] == 32 and BASIC[1] == 68 and GAME_TEE[1] == 32 and CREW[1] == 58, DB


def deps_with(*pids, shopper_amounts=(), tool_totals=(), range_prices=()):
    d = tools.AgentDeps()
    for pid in pids:
        d.remember(pid, DB[pid][1], DB[pid][0])
    d.shopper_amounts.update(shopper_amounts)
    d.tool_totals.update(tool_totals)
    d.range_prices.update(range_prices)
    return d


F, B, H, T, C = IDS
CASES = [
    # ---- must be REJECTED ----
    ("reject", "wrong unit price (the review case)", f"One {FENCING[0]} costs $136.00.", [F]),
    ("reject", "wrong unit price, no quantity", f"The {FENCING[0]} is $136.00.", [F]),
    ("reject", "made-up price", f"The {FENCING[0]} is on sale for $50.00.", [F]),
    ("reject", "swapped prices, same sentence", f"The {FENCING[0]} is $32.00 and the {BOOLA[0]} is $68.00.", [F, B]),
    ("reject", "swapped prices, bullet list", f"- {FENCING[0]}: $32.00\n- {BOOLA[0]}: $68.00", [F, B]),
    ("reject", "price of another seen product", f"The {CREW[0]} is $68.00.", [C, H]),
    ("reject", "wrong total for the quantity", f"Three {FENCING[0]}s would be $136.00.", [F]),
    ("reject", "total that matches no quantity", f"Two {FENCING[0]}s come to $140.00.", [F]),
    ("reject", "pronoun with wrong price", f"I'd suggest the {FENCING[0]}. It's $32.00.", [F, B]),
    ("reject", "unknown amount, no product named", "Everything is $1.00 today!", [F]),
    # ---- must be ACCEPTED ----
    ("accept", "correct unit price", f"The {FENCING[0]} is $68.00.", [F]),
    ("accept", "price written as $68", f"The {FENCING[0]} is $68, and only 2 left in XL.", [F]),
    ("accept", "two products, right prices", f"The {FENCING[0]} is $68.00 and the {BOOLA[0]} is $32.00.", [F, B]),
    ("accept", "price before the name", f"At $32.00, the {BOOLA[0]} is the lighter option.", [B, F]),
    ("accept", "bullet list, right prices", f"- {FENCING[0]}: $68.00\n- {BOOLA[0]}: $32.00", [F, B]),
    ("accept", "pronoun after a named product", f"I'd suggest the {FENCING[0]}. It's $68.00.", [F, B]),
    ("accept", "valid total with digits", f"Two {FENCING[0]}s would be $136.00.", [F]),
    ("accept", "valid total with ×", f"2 × {FENCING[0]} = $136.00", [F]),
    ("accept", "valid total in words", f"Three {BOOLA[0]}s come to $96.00 in total.", [B]),
    ("accept", "sum of named pieces (the kit)",
     f"Together, the {GAME_TEE[0]}, {BASIC[0]} and {CREW[0]} come to $158.00.", [T, H, C]),
    ("accept", "kit total stated before the names",
     f"Together they cost $158.00. That's the {GAME_TEE[0]} ($32.00), {BASIC[0]} ($68.00) and {CREW[0]} ($58.00).", [T, H, C]),
    ("reject", "wrong kit total stated before the names",
     f"Together they cost $150.00. That's the {GAME_TEE[0]} ($32.00), {BASIC[0]} ($68.00) and {CREW[0]} ($58.00).", [T, H, C]),
    ("accept", "mixed quantities total",
     f"Two {BASIC[0]}s ($68.00 each) and one {BOOLA[0]} ($32.00) come to $168.00 in total.", [H, B]),
    ("accept", "mixed total stated first",
     f"Your total would be $168.00: two {BASIC[0]}s at $68.00 and one {BOOLA[0]} at $32.00.", [H, B]),
    ("reject", "wrong mixed total",
     f"Two {BASIC[0]}s ($68.00 each) and one {BOOLA[0]} ($32.00) come to $170.00 in total.", [H, B]),
    ("reject", "unit price that only works as a sum of other pieces",
     f"The {FENCING[0]} costs $100.00, and the {BOOLA[0]} is $32.00.", [F, B]),
    ("accept", "price difference between two named pieces",
     f"The {BOOLA[0]} is $32.00 and the {FENCING[0]} is $68.00, so the tee is $36.00 less.", [B, F]),
    ("reject", "wrong price difference",
     f"The {BOOLA[0]} is $32.00 and the {FENCING[0]} is $68.00, so the tee is $40.00 less.", [B, F]),
    ("accept", "category price from list_categories", "Jackets are $98.00 across the collection.", [], {"range_prices": {98.0}}),
    ("accept", "shopper's own budget", f"The {BOOLA[0]} is $32.00, well under your $50 budget.", [B], {"shopper_amounts": {50.0}}),
    ("accept", "cart subtotal from view_cart", f"Your cart has 1 {FENCING[0]} at $68.00 and 1 {BOOLA[0]} at $32.00. Subtotal: $100.00.",
     [F, B], {"tool_totals": {100.0}}),
    ("accept", "category price range", "Hoodies range from $45.00 to $88.00.", [F], {"range_prices": {45.0, 88.0}}),
    ("accept", "no prices at all", f"The {FENCING[0]} is sold out in L.", [F]),
]

failures = 0
for expect, label, reply, pids, *extra in CASES:
    problems = agent.price_problems(reply, deps_with(*pids, **(extra[0] if extra else {})))
    got = "reject" if problems else "accept"
    ok = got == expect
    failures += not ok
    print(f"{'PASS' if ok else 'FAIL'} | expected {expect:6} | {label}" + (f"  -> {problems[0]}" if problems and ok else ""))
    if not ok:
        print(f"       reply: {reply!r}\n       problems: {problems}")

print(f"\n{len(CASES) - failures} of {len(CASES)} validator checks passed.")
sys.exit(1 if failures else 0)
