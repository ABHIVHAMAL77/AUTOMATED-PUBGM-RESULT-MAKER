# ESPORTS COUNTY PUBGM Result Maker

A production-style tournament result system for PUBG Mobile esports. It combines a web dashboard, online screenshot OCR, live match ingestion, standings calculation, exportable graphics, Excel/CSV outputs, buyer email access control, and Discord bot commands for teams, players, managers, and coaches.

This project was built for ESPORTS COUNTY to make match result work faster, cleaner, and easier to sell as a hosted tool.

## Portfolio Highlights

- Event-first workflow: create or choose an event before using Manual Result or Live Result mode.
- Manual result maker: upload PUBG Mobile match screenshots, extract standings with OCR, review/fix rows, then save official results.
- Live result maker: connect to a reachable observer/live match feed and automate result creation.
- Scoring engine: placement points, elimination points, total standings, match history, and player stats.
- Discord bot: public commands for results, standings, team screenshots, overall screenshots, and player details.
- Seller access model: only manually approved buyer emails can register and use the web app.
- Cloud deployment: Docker setup for Hostinger VPS, including subdomain routing for `result.esportscounty.com`.

## Tech Stack

- Python, FastAPI, Uvicorn
- React, TypeScript, Vite, Tailwind CSS
- RapidOCR / ONNX Runtime for online screenshot OCR
- Pillow and OpenPyXL for generated graphics and spreadsheet exports
- discord.py for the Discord bot
- Docker Compose for VPS deployment

## Deployment

For Hostinger VPS deployment, see:

- `HOSTINGER_SUBDOMAIN_SETUP.md` for `result.esportscounty.com` on the same VPS as `portal.esportscounty.com`
- `HOSTINGER_DEPLOYMENT.md` for full VPS deployment notes
- `.env.hostinger.example` for required environment variables

Runtime data, buyer lists, Discord tokens, and secret keys are intentionally excluded from GitHub.

## Screenshot OCR — Team Roster (Step 1)

On the **Screenshot OCR tab**, click **Load Slot Screenshot(s)** and pick the
in-game team list screenshots (the screen with big colored slot numbers and
4 players per card — take one screenshot per page so all teams are covered).
The app reads every card: slot number + the 4 player names, and suggests a
team tag from the players' common prefix (e.g. `Wz`, `SC`, `TLx`).

- Fix any OCR mistakes directly in the table (it is fully editable).
- If a slot number could not be read, type it in the Slot column.
- Loading more screenshots adds to the table; same slot loaded again is replaced.
- Click **Apply Roster To Event Slots** — players and tags are saved into the
  event, visible on the Event Setup tab.

This roster is the foundation for the next step: post-match rankings
screenshots have no slot numbers or team names, so the app fuzzy-matches
the player names it reads against this roster to work out which team placed
where.

## Screenshot OCR — Match Results (Step 2)

After the match, screenshot **every page** of the rankings screen (the gold
cards with the big rank numbers; the #1/#2 panel on the left is read too).
On the **Screenshot OCR tab**, click **Load Result Screenshot(s)** and select
all pages at once. The app:

- reads each team card: rank, player names, per-player eliminations
  (team eliminations = sum of its players — kill points come from this)
- finds card boundaries by the gold card shapes, so cut-off cards at the
  top/bottom of a page are detected and merged with the complete version
  from the neighbouring page (the repeated #1/#2 panel is de-duplicated)
- fuzzy-matches every card's players against the Step 1 roster to work out
  the team slot and name (works even when OCR slightly misreads an IGN)

The status line warns about anything that needs attention: unread ranks,
unmatched slots, or missing ranks (a page you forgot to screenshot). Fix
values directly in the table — the **Confidence** column scores each row and
explains itself on hover: whether the rank was actually read or inferred, how
strong the roster match was, whether another row claims the same rank, and
whether the card came back with fewer players than a full squad. Anything
below 70% is worth a look. Then set Match # and Map and click
**Save As Match Result** — points, standings, player stats, the tournament
sheet, CSVs and PNG graphics all update exactly like API mode.

### How accurate is it, and how do we know?

`tests/fixtures/` holds real screenshots labelled by hand, and
`scripts/ocr_bench.py` scores the pipeline against them field by field:

```
python scripts/ocr_bench.py            # results + roster
python scripts/ocr_bench.py -v         # every individual mismatch
python scripts/ocr_bench.py --save-baseline
```

`tests/accuracy_baseline.json` records the current numbers, and
`tests/test_accuracy.py` fails the suite if a change drops below them. Add
your own labelled screenshots to the fixtures folder to measure the pipeline
against your events specifically.

### The OCR is online for buyers and self-hosted

On the hosted website, buyers upload screenshots and OCR runs on your VPS. There is no separate OCR account, API key, or subscription required for the default mode. Screenshots stay inside your own ESPORTS COUNTY server instead of being sent to a third-party OCR provider.

<details>
<summary>Optional paid mode (you almost certainly do not want this)</summary>

The local engine is a Latin-script model, so Devanagari or CJK team names are
beyond it. If you regularly run those lobbies, you can have Claude re-read the
cards the confidence model distrusts, at roughly $0.15–0.25 per match:

```
pip install anthropic
set ANTHROPIC_API_KEY=sk-ant-...
set OCR_ENGINE=hybrid          local | hybrid | vision   (default: local)
```

Everything degrades back to the self-hosted OCR engine if the key is missing or the external service is unreachable, so turning it on can never break an event.

</details>

Note: OCR matches store player eliminations only (no damage/survival data —
the rankings screen does not show them), and players are tracked by name
instead of UID. Use one mode (API or OCR) per event for clean player stats.

## Login & accounts

The app is protected by a login screen. On the **very first launch** it asks
you to create your **Admin account** (pick any username + password — remember
it, there is no recovery besides deleting `data/users.json`, which wipes all
accounts).

- **admin** — full access: Event Setup, exports, deleting matches, and the
  **Admin Panel tab** where you add/remove users and reset passwords.
- **operator** — can only run matches and save results (Live Match polling +
  Screenshot OCR save). No Event Setup tab, no exports, no deleting matches,
  no user management.

Passwords are stored as salted PBKDF2 hashes in `data/users.json` — never in
plain text. Note: this keeps operators and casual users out; it cannot stop
someone with full file access to the PC from resetting accounts.

## Selling / hosted licenses

For customer builds, set `licenseServerUrl` in `data/settings.json` or set the
`PUBGM_LICENSE_SERVER_URL` environment variable. When this URL is present, the
login screen uses hosted email/password license accounts instead of local
`data/users.json` accounts.

This repo includes a starter FastAPI license server in `licensing_server/`.
See `SELLING_GUIDE.md` for the recommended payment + hosting flow.

## Web version

The website version is included as `web_app.py`.

Run it with:

```powershell
.\run_web.bat
```

Then open `http://127.0.0.1:8080`.

Purchased-user registration is controlled with `web_admin.py`; see
`WEBSITE_GUIDE.md`.

## How to run

Double-click `run.bat`. On a new PC it automatically installs the required
packages first (Python 3.12 must be installed — get it from python.org and
tick "Add python.exe to PATH" during install).

## Moving to another PC

Copy this whole folder anywhere (USB stick, cloud, etc.). Everything —
code, settings, event data, saved matches, exports — lives inside this one
folder. On the new PC: install Python 3.12, then double-click `run.bat`.

## How to use (API mode)

1. **Event Setup tab** — set the event name, stage, **total matches**
   (supports long tournaments, e.g. 30 matches), placement points
   (default `10,6,5,4,3,2,1,1` + 1 per elim), and team names.
   Use **Import Teams From Live Data** to grab team IDs from the API.
2. **Live Match tab** — check the API URL (default
   `http://127.0.0.1:10086/gettotalplayerlist`). Tick **Mock mode** to test
   without the observer. Click **Start Polling**. The table shows live
   standings; the header shows match progress (e.g. "Match 3 of 30 • 2 played").
3. When only one team is left the app asks to save the match. You can also
   click **Finalize & Save Match Result** anytime.
4. **After every saved match, everything updates automatically** — no more
   manual JSON → CSV copying:
   - `data/exports/Tournament Sheet.xlsx` — tabs mirror the old Google Sheet:
     SETUP, OVERALL GD (raw per-player API rows of every match),
     Match Standings, Overall Standings, Player Stats (with MVP rating)
   - `data/exports/csv/` — the same data as CSV files
     (`overall_gd.csv`, `match_standings.csv`, `overall_standings.csv`,
     `player_stats.csv`) — importable into Google Sheets
5. **Player Stats tab** — live player leaderboard: elims, damage, headshots,
   assists, knockouts, damage received, survival, heal, rescues, longest
   elimination, MVP rating. Click any column header to sort.
6. **Results & Export tab** — view any match, overall standings, export
   broadcast-style **1920x1080 PNG graphics**, open the tournament sheet.

## Result graphic templates

The exported PNGs come in ten designs — Midnight Gold, Neon Circuit, Crimson
Elite, Arctic, Carbon Mono, Sunset Arena, Jungle Ops, Royal Purple, Broadcast
Clean and Championship Gold. They differ in layout as well as colour: one or
two columns, card rows or striped or outlined, light or dark.

Pick one on the **Event Setup tab** ("Result graphic template"); it applies to
both the match graphic and the overall standings.

To use **your own background and logo**, open the web app (`run_web.bat`) —
Event Setup there has the full picker with live previews, artwork uploads,
colour overrides and a dimming slider. Whatever you choose there is what the
desktop app exports too; both read the same event file.

## Where data is stored

```
data/settings.json                    API URL, poll interval, mock mode
data/event.json                       event name, stage, total matches, teams, points
data/results/match_01.json            each finalized match (full per-player stats + raw API rows)
data/exports/Tournament Sheet.xlsx    auto-updated tournament workbook
data/exports/csv/                     auto-updated CSV files
data/exports/*.png                    exported result graphics
```

## Point system default

1st=10, 2nd=6, 3rd=5, 4th=4, 5th=3, 6th=2, 7th=1, 8th=1, 9th+=0, 1 point per elim.
Overall standings tiebreakers: total points → WWCD count → placement points →
elims → best single-match placement.

MVP rating = a player's share of total lobby contribution, where
contribution = elims×2 + knockouts + assists×0.75 + damage÷100 + rescues×0.5.



