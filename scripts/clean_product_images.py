"""Make web-ready copies of the product photos with a white background.

73 of the 102 photos in data/products were exported from transparent PNGs, so their
background came out solid black. That looks heavy on the white Bulldog Blue site.
This script flood-fills the near-black background from the image edges with white and
saves the result to data/products_web/. The originals in data/products are not changed.
The backend serves these web copies at /media/products/<file>, falling back to the originals.

Flood fill only spreads through near-black pixels touching the edge, so navy garments
(clearly not black) and logos inside the garment are left alone.

Second pass: enclosed gaps. Some photos also had black background trapped in closed-off
gaps, usually between a sleeve and the body, which the edge fill can't reach. Those gaps
are whitened too, but only when ALL of these hold, so real black stays black:
  - the area is almost pure black (average brightness <= 8 out of 255); real dark fabric and
    shadows on navy or charcoal pieces measure about 10-18;
  - it is big enough to be a gap (>= 400 pixels), not a speck or a thin print line;
  - the product's colors in the database do NOT include "black". The 11 products with black
    prints or black fabric (e.g. the Pierson shield, Morse and Saybrook logos) are skipped.
A thin dark frame hugging the photo border (one tee had one) is also removed.

Run from the project folder, after placing the data pack (needs Pillow, which the server itself does not):
    python3.12 -m venv scripts/.venv && scripts/.venv/bin/pip install -r scripts/requirements-scripts.txt
    scripts/.venv/bin/python scripts/clean_product_images.py
"""

import json
import sqlite3
from collections import deque
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "products"
DST = ROOT / "data" / "products_web"
DB = ROOT / "data" / "campus_customs.db"

WHITE = (255, 255, 255)
BLACK_LIMIT = 20  # an edge pixel counts as "black background" if every channel is below this
FILL_TOLERANCE = 45  # how far (sum of R+G+B differences) the fill may drift from the seed pixel
GAP_MIN_PIXELS = 400  # enclosed black areas smaller than this are left alone
GAP_MAX_MEAN = 8  # average brightness of a background gap; real dark fabric is brighter (about 10-18)
FRAME_MARGIN = 3  # a dark line entirely within this many pixels of the border is a frame, not product


def is_black(pixel: tuple[int, int, int]) -> bool:
    return max(pixel) < BLACK_LIMIT


def whiten_background(im: Image.Image) -> Image.Image:
    im = im.convert("RGB")
    w, h = im.size
    edge = [(x, 0) for x in range(w)] + [(x, h - 1) for x in range(w)]
    edge += [(0, y) for y in range(h)] + [(w - 1, y) for y in range(h)]
    for xy in edge:
        if is_black(im.getpixel(xy)):  # skips pixels already filled by an earlier pass
            ImageDraw.floodfill(im, xy, WHITE, thresh=FILL_TOLERANCE)
    return im


def dark_areas(im: Image.Image) -> list[list[tuple[int, int]]]:
    """Every connected patch of near-black pixels (4-neighbour), as lists of (x, y)."""
    w, h = im.size
    px = im.load()
    seen = bytearray(w * h)
    areas = []
    for y in range(h):
        for x in range(w):
            if seen[y * w + x] or not is_black(px[x, y]):
                continue
            seen[y * w + x] = 1
            queue, area = deque([(x, y)]), []
            while queue:
                cx, cy = queue.popleft()
                area.append((cx, cy))
                for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                    if 0 <= nx < w and 0 <= ny < h and not seen[ny * w + nx] and is_black(px[nx, ny]):
                        seen[ny * w + nx] = 1
                        queue.append((nx, ny))
            areas.append(area)
    return areas


def whiten_gaps_and_frame(im: Image.Image, protect_black: bool) -> tuple[Image.Image, int, int]:
    """Second pass: whiten trapped background gaps (unless the product has black in it) and border frames."""
    w, h = im.size
    px = im.load()
    gaps = frames = 0
    for area in dark_areas(im):
        on_border = all(min(x, y, w - 1 - x, h - 1 - y) < FRAME_MARGIN for x, y in area)
        if on_border and len(area) >= 50:
            for x, y in area:
                px[x, y] = WHITE
            frames += 1
            continue
        if protect_black or len(area) < GAP_MIN_PIXELS:
            continue
        brightness = [max(px[x, y]) for x, y in area]
        if sum(brightness) / len(brightness) > GAP_MAX_MEAN:
            continue  # too bright to be background: real dark fabric or shadow
        seed = min(area, key=lambda p: max(px[p]))  # darkest pixel; fill out to the soft edge like pass 1
        ImageDraw.floodfill(im, seed, WHITE, thresh=FILL_TOLERANCE)
        gaps += 1
    return im, gaps, frames


def products_with_black() -> set[str]:
    with sqlite3.connect(DB) as con:
        rows = con.execute("SELECT product_id, colors FROM catalogue").fetchall()
    return {pid for pid, colors in rows if any("black" in c.lower() for c in json.loads(colors))}


def main() -> None:
    DST.mkdir(parents=True, exist_ok=True)
    protected = products_with_black()
    cleaned = gap_images = gap_total = frame_total = 0
    for path in sorted(SRC.glob("*.jpg")):
        im = Image.open(path).convert("RGB")
        w, h = im.size
        corners = [im.getpixel(p) for p in [(2, 2), (w - 3, 2), (2, h - 3), (w - 3, h - 3)]]
        if all(is_black(c) for c in corners):
            im = whiten_background(im)
            cleaned += 1
        im, gaps, frames = whiten_gaps_and_frame(im, protect_black=path.stem in protected)
        gap_images += gaps > 0
        gap_total += gaps
        frame_total += frames
        im.save(DST / path.name, quality=90)
    print(
        f"Wrote {len(list(SRC.glob('*.jpg')))} images to {DST}: {cleaned} had black backgrounds, "
        f"{gap_total} trapped gaps whitened in {gap_images} images, {frame_total} border frames removed, "
        f"{len(protected)} products with black in their design protected"
    )


if __name__ == "__main__":
    main()
