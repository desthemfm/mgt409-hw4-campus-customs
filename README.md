# Campus Customs: Yale Bulldog Blue Shop with an AI Concierge

MGT 409 Homework 4. A shopping site for Campus Customs' officially licensed Yale apparel, with an AI **Bulldog Blue Concierge** that:
- answers questions with **honest prices and stock** from the shop's database;
- puts matching items on the page;
- remembers signed-in shoppers;
- can add items to the cart.

| Part | Built with |
|---|---|
| Front end | React, Vite, TypeScript |
| Back end | Python FastAPI |
| Agent | PydanticAI, using `gpt-6-astra` through the course Portkey gateway |
| Data | The course's SQLite data pack |

The full explanation of how it works (models, tools, safety rules, limits) is in **[output/harness.md](output/harness.md)**.

## Project layout

```
hw4/
├── AI_prompts.md          # every prompt typed to the vibe coder, by problem
├── requirements.txt       # backend Python packages
├── .env.example           # settings template (placeholders only)
├── .gitignore
├── README.md
├── frontend/              # Vite React TypeScript app (port 5174)
├── backend/
│   ├── main.py            # FastAPI app; run with: uvicorn main:app --reload --port 8000
│   ├── agent.py           # ┐
│   ├── tools.py           # │ the agent: four files
│   ├── models.py          # │
│   ├── prompts/prompt.md  # ┘ (system prompt)
│   └── tests/             # automated checks (tools, price check, audit trail, safety rules)
├── scripts/               # optional helpers: photo cleanup, live-site app check
└── output/
    ├── harness.md         # how the system works, and the build log
    ├── design.md          # Problem 10: the Game Day design
    ├── usability.md       # Problem 9: four usability improvements (2 backend, 2 front end)
    ├── app_check.html     # Problem 11: screenshot evidence (double-click to open)
    ├── app_check_images/  # screenshots linked from app_check.html
    └── audit_trail.json   # Problem 12: append-only log of agent runs
```

The **data pack is not in git**. You place it locally (step 1).

## What you need

- **Python 3.12** (3.10 or newer works)
- **Node.js 20+** and npm
- A **Portkey API key** for the course gateway

## 1. Place the data pack

Unzip the course data pack (`data.zip`) **into this project folder**, so you have:

```
hw4/
└── data/
    ├── campus_customs.db
    └── products/          # product photos referenced by the catalogue
```

```bash
unzip data.zip            # run inside the project folder; creates data/
```

The first time the backend starts, it prepares this database automatically:
- it adds the `category` column;
- it fixes three placeholder descriptions and some product names (the Problem 2 cleanup).

It only changes the product catalogue, and it's safe to run again.

## 2. Settings: `.env`

```bash
cp .env.example .env
```

Open `.env` and fill in:

| Setting | What to put |
|---|---|
| `PORTKEY_API_KEY` | Your course Portkey key |
| `SESSION_SECRET` | Any long random string. Generate one with `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `OPENAI_MODEL` | Already `gpt-6-astra`. Change it only if the gateway requires another model |

`.env` is in `.gitignore`. Never commit it.

## 3. Run the backend (terminal 1)

```bash
python3.12 -m venv backend/.venv
backend/.venv/bin/pip install -r requirements.txt

cd backend
source .venv/bin/activate
uvicorn main:app --reload --port 8000
```

Check it: http://127.0.0.1:8000/api/health should show `{"status":"ok"}`.

## 4. Run the front end (terminal 2)

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5174**. The dev server forwards `/api` and `/media` to the backend on port 8000, so both servers must be running.

## Try it

- **Browse:** the **Products** page, category chips, and single-item pages with live sizes and stock.
- **Shop your size:** tap a size under "Your size" on the Products page to see only pieces in stock in it. Your size is then preselected on product pages.
- **Game-Day Kit** (home page): pick a size and add all three pieces at once.
- **Ask the concierge** (the pink button, bottom right):
  - "Show me your T-shirts": matching cards appear on the page.
  - "Is this in stock in XL?" on a product page.
  - "Add one in medium to my cart."
- **Accounts:** create one, or use the course's sample user `test@campuscustoms.yale.edu` / `password`. Signed-in chats are saved and come back next visit.

## Tests (optional)

From `backend/`, with the virtual environment active:

| Command | What it checks | Cost |
|---|---|---|
| `python tests/test_tools.py` | All 102 products × 6 sizes: tool answers vs. the database | Free |
| `python tests/test_validator.py` | The price check: wrong, swapped, and valid prices and totals | Free |
| `python tests/test_audit.py` | The append-only audit trail (scripted stand-in model) | Free |
| `python tests/test_safety.py` | The 12 safety rules, against the live AI | Small AI cost |

**Live-site report** (`output/app_check.html`). Needs both servers running and Google Chrome installed:

```bash
python3.12 -m venv scripts/.venv
scripts/.venv/bin/pip install -r scripts/requirements-scripts.txt
scripts/.venv/bin/python scripts/app_check.py
```

**Optional, white-background product photos** (73 of the photos have black backgrounds):

```bash
scripts/.venv/bin/python scripts/clean_product_images.py   # writes data/products_web/; originals untouched
```

## Troubleshooting

- **"Database not found"** when the backend starts: the data pack isn't at `data/campus_customs.db` (step 1).
- **Chat says the concierge is unavailable:** check `PORTKEY_API_KEY` in `.env`, then restart the backend.
- **Port 8000 or 5174 is busy:** find what's using it with `lsof -nP -iTCP:8000 -sTCP:LISTEN` and stop that process (with `--reload`, also stop its child process).

## Security notes

- **Secrets:** they live only in `.env`, which is git-ignored. `.env.example` has placeholders only.
- **Passwords:** stored as Argon2id hashes. Login uses a signed, HttpOnly session cookie, and repeated wrong passwords trigger a lockout.
- **Limits on the concierge:** its tools can only read the catalogue and stock, the signed-in shopper's own profile and chats, and the browser cart. It can never read other users.
- **Answer checks (best effort):**
  - code checks the concierge's **final** answer: each `$` price must match the product it describes (or be a total with the quantity stated), stated stock numbers must come from a lookup, and "added to cart" must be true;
  - streamed drafts appear **before** this check and are replaced by the checked answer;
  - prices written without a `$` aren't checked.

  See `output/harness.md`, Part 1, section 7.
- **Audit trail:** `output/audit_trail.json` records every agent run with no names or emails.
