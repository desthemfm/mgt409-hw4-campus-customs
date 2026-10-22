"""Checks the agent's product and stock tools against the database. No AI calls, no cost.

Every price, quantity, and stock label the tools return is compared with a direct SQL
query of campus_customs.db, for all 102 products and all 6 sizes.

Run from the backend folder:
    python tests/test_tools.py
"""

import sys
from pathlib import Path as _Path

sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))  # the backend folder


import sqlite3

import tools
from models import ProductInfo, ProductNotFound, SizeNotCarried, StockCheck

tools.prepare_database()  # a fresh data pack works even if the server hasn't run yet
con = sqlite3.connect(tools.DB_PATH)
prices = dict(con.execute("SELECT product_id, price FROM catalogue"))
names = dict(con.execute("SELECT product_id, name FROM catalogue"))
stock = {(p, s): q for p, s, q in con.execute("SELECT product_id, size, quantity FROM inventory")}
con.close()

checks = 0


def check(condition: bool, message: str) -> None:
    global checks
    assert condition, message
    checks += 1


# 1. get_product_info: price, description, and every size match the database.
for pid in prices:
    deps = tools.AgentDeps()
    info = tools.product_info(deps, pid)
    check(isinstance(info, ProductInfo), f"{pid}: not found")
    check(info.price == prices[pid], f"{pid}: price {info.price} != {prices[pid]}")
    check(info.price_text == f"${prices[pid]:,.2f}", f"{pid}: price_text {info.price_text}")
    check([s.size for s in info.stock_by_size] == tools.SIZE_ORDER, f"{pid}: sizes out of order")
    for s in info.stock_by_size:
        q = stock[(pid, s.size)]
        check(s.quantity == q, f"{pid} {s.size}: {s.quantity} != {q}")
        expected = "sold_out" if q == 0 else "low_stock" if q <= 5 else "in_stock"
        check(s.status == expected, f"{pid} {s.size}: status {s.status}, expected {expected}")
    check(info.total_in_stock == sum(stock[(pid, s)] for s in tools.SIZE_ORDER), f"{pid}: total")
    check(set(info.sold_out_sizes) == {s for s in tools.SIZE_ORDER if stock[(pid, s)] == 0}, f"{pid}: sold_out_sizes")
    check(pid in deps.seen_product_ids and prices[pid] in deps.seen_prices, f"{pid}: not remembered")

# 2. check_size_stock: every product x size, including the "say this" sentence for sold-out sizes.
for pid in prices:
    for size in tools.SIZE_ORDER:
        deps = tools.AgentDeps()
        result = tools.stock_for_size(deps, pid, size)
        q = stock[(pid, size)]
        check(isinstance(result, StockCheck) and result.quantity == q, f"{pid} {size}")
        if q == 0:
            check("sold out" in result.say_this and (names[pid], size) in deps.sold_out_checks, f"{pid} {size} sold out")
        check(all(o.quantity > 0 and o.size != size for o in result.other_sizes_in_stock), f"{pid} {size}: others")

# 3. Everyday size words and names work; unknown products and sizes are refused, not guessed.
deps = tools.AgentDeps()
check(tools.stock_for_size(deps, "fencing-left-chest-hoodie", "large").size == "L", "'large' -> L")
check(tools.stock_for_size(deps, "fencing-left-chest-hoodie", "2XL").size == "XXL", "'2XL' -> XXL")
check(tools.product_info(deps, "Fencing Left Chest Hoodie").product_id == "fencing-left-chest-hoodie", "lookup by name")
check(isinstance(tools.product_info(deps, "Yale Swim Trunks"), ProductNotFound), "unknown product")
check(isinstance(tools.stock_for_size(deps, "fencing-left-chest-hoodie", "XXXL"), SizeNotCarried), "unknown size")
miss = tools.product_info(deps, "fencing hoody")
check(isinstance(miss, ProductNotFound) and any("Fencing" in r.name for r in miss.did_you_mean), "did_you_mean")

# 4. Search respects filters and reports real sizes.
deps = tools.AgentDeps()
result = tools.search_catalogue(deps, "hoodie", max_price=60, size="XL")
for p in result.products:
    check(p.price <= 60 and stock[(p.product_id, "XL")] > 0, f"search filter broken for {p.product_id}")

print(f"All {checks} checks passed against {len(prices)} products and {len(stock)} inventory rows.")
