# Problem 10 - Design: "Game Day"

The site is restyled as **a night game at the Yale Bowl**: deep navy, stadium lights, a scoreboard countdown to The Game, scoreboard-yellow prices, an electric-blue rivalry ticker, and a pink accent reserved for real "only N left" scarcity.

It still feels like the Campus Customs storefront:
- Yale blue throughout;
- the "Officially Licensed Merchandise" bar;
- the store's own section titles from yalebulldogblue.com ("Shop Bulldog Blue," "Yale Pride on the Go!," "Cozy Up for Fall," "Come Visit Us!");
- the same pages, navigation, cart, and concierge.

**How we got here:** we first built a heritage-catalogue look, but it read as too old-fashioned for today's buyers. We then previewed three fresher directions (The Drop, Bento Campus, Game Day) as live mockups with real products, and you chose **Game Day**.

## How we're capitalizing on the rivalry

The Yale–Harvard rivalry is the strongest emotion the shop can tap, and The Game is a **fixed deadline**. Here's how the site uses it:

1. **A countdown creates a "buy before Saturday" moment.** The home page leads with **"BEAT HARVARD."** and a live scoreboard counting down to kickoff (days, hours, minutes, seconds), turning "someday" into "this week."
2. **"Gear up" is one click.** The **Game-Day Kit** groups three pieces for the stands, including the 2025 Yale vs. Harvard T-Shirt, under one **"Add the kit in [size]"** button. That moves a shopper from one item to three.
3. **The rivalry is everywhere, briefly.** The ticker runs "BEAT HARVARD ✦ BOOLA BOOLA ✦ BULLDOGS," and "More for the Stands" features the football and Yale Bowl pieces.
4. **Scarcity is real.** Pink "Only 2 left in XL" tags come straight from the inventory table. They appear only for the true last one or two of a size, so they keep their meaning.
5. **It doesn't go stale.** After The Game, the hero switches automatically to "Bulldog blue, all season." The same layout can be pointed at the next moment (holiday gifts, Commencement) by changing one settings file.

Respectful rivalry: we name Harvard, but use no Harvard logos or marks. All the merchandise shown is officially licensed Yale gear.

## What we changed

| Area | Change | Why it helps |
|---|---|---|
| **Fonts** | **Big Shoulders Display** (stadium and scoreboard lettering) for headings and prices; **Inter** for everything people read: body, forms, chat | Instant game-day energy in headings, with easy reading everywhere else |
| **Color** | Night navy `#061529`; raised panels `#0c2140`; electric blue `#4ea1ff`; scoreboard yellow `#ffd84d` for prices; **pink `#ff4f8b` only for real scarcity and the main call to action** | One accent color with one meaning (pink = act now) guides the eye to "buy" without clutter |
| **Hierarchy** | 1. "BEAT HARVARD." and the countdown → 2. the Game-Day Kit → 3. More for the Stands → 4. the store's own sections → 5. Visit us | The most persuasive message comes first, with the everyday shop right below |
| **Motion** | Scoreboard digits **flip** like a real stadium clock; the ticker scrolls; cards lift and glow blue on hover | Feels live and exciting, but every effect switches off for shoppers who prefer reduced motion |
| **Product presentation** | Products on white tiles set into dark panels, so they "pop"; prices in big scoreboard yellow; green "In stock" sizes; pink low-stock line (grid) or sticker (hand-picked rows) | The product photo and the price are the brightest things on the page |
| **Chat feel** | A pink launcher button; a dark panel with a Yale-blue header and a ✦ mark; concierge replies in navy cards, the shopper's in electric blue; streaming and cart notes from Problem 9 kept | Feels like a press-box assistant, not a help-desk widget |

**Course style note:** AGENTS.md sets near-black and bright pink as the default style. Game Day's near-black navy with a bright pink accent stays close to that, while keeping Yale blue for the brand.

## Why it should help customers stick around and buy

- **Urgency without tricks.** The countdown is a real event, and the scarcity tags are real stock. Shoppers have a genuine reason to buy now.
- **Bigger baskets.** The kit adds three pieces at once in the shopper's size, and it skips any piece that's sold out in that size instead of failing or overselling.
- **The energy matches the moment.** Students, alumni, and parents shopping in rivalry week are already excited; the site meets that mood instead of feeling like a generic store.
- **Clear focus.** One accent color, one headline, and one main action keep the page easy to scan, so shoppers reach products faster.
- **The concierge stands out.** The bright pink chat button and dark "press box" panel invite questions, and the concierge can now add to the cart (Problem 9).
- **Nothing important moved.** Navigation, cart, product pages, sign-in, and the concierge all work exactly as before, so the new look adds excitement without confusion.

## How it's built

- **`frontend/src/gameday.css`** holds the theme, layered over `index.css`. Removing the `import './gameday.css'` line in `main.tsx` returns the plain storefront look.
- **`frontend/src/gameDay.ts`** is one settings file: the **kickoff time**, how long the "It's Game Day" message stays up, the kit's three products, and the "More for the Stands" picks.
- **New components:**
  - `Countdown.tsx`: the scoreboard. It's announced to screen readers as "30 days, 1 hours, 40 minutes until kickoff."
  - `GameDayKit.tsx`: the kit, with live stock per size, the size picker, and the one-click add.
- **Backend:** `ProductCard` gained **`low_stock_note`** ("Only 2 left in XL"), computed in the same SQL query from live inventory (`tools.low_stock_note`). It names the scarcest in-stock size when 5 or fewer remain; the site shows it only for the last 1–2.
- **Removed:** the earlier catalogue stylesheet and the three design mockups.

> **Kickoff:** set to **Saturday, November 21, 2026, 12:00 PM ET** in `gameDay.ts`, confirmed by the site owner on October 22, 2026. It's a setting, not live data; if the game time ever moves, it's a one-line change.

## Checked

| Check | Result |
|---|---|
| Home page | "BEAT HARVARD.", countdown "30 days, 1 hour, 40 minutes" (from Oct 22), kickoff line, ticker, and kit total **$158.00** = $32 + $68 + $58 from the database |
| Kit in XL | Added all 3 (badge 3). Pressed again until the cart held every XL Basic Hoodie in stock (2): the next press added **2 of 3** and said the hoodie couldn't be added, so it never oversells |
| Low-stock notes | All 102 cards compared with the inventory table: **0 mismatches**. Stickers limited to the last 1–2 of a size, so 6 on the home page (instead of 9) and 42 grid lines (instead of 71) |
| Products page, product page, and chat | Correct in the new theme. The concierge answered on a product page: "$58.00, with only 2 left in XL. Shall I add one in XL to your cart?" |
| Contrast | Text 16.6:1, muted 8.4–9.5:1, blue 6.9:1, yellow prices 11.6:1, pink line 5.2:1, text on pink buttons 5.9:1. Sold-out size buttons were 3.7:1, raised to **5.9:1** |
| Phone (375px) | No sideways scrolling. The countdown was cut off at first; digits were resized and it now fits (31–344px of 375). The low-stock sticker is smaller, and the duplicate stock line was removed |
| Build and tests | `npm run build` OK, lint clean, `backend/tests/test_tools.py` 3,314 / 3,314 |
