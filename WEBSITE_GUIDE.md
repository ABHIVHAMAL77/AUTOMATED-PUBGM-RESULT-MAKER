# ESPORTS COUNTY PUBGM RESULT MAKER Website

Run the web version:

```powershell
.\run_web.bat
```

Open:

```text
http://127.0.0.1:8080
```

## Building the interface

The front-end is a React + Vite app in `web/`. `run_web.bat` builds it on the
first run, so nothing extra is needed to launch — but it does mean **Node.js
must be installed** (https://nodejs.org).

After editing anything under `web/src`, rebuild:

```powershell
cd web
npm run build
```

To work on the interface with hot reload, run the Python server in one terminal
and Vite in another; Vite proxies `/api` through to it:

```powershell
python -m uvicorn web_app:app --port 8080     # terminal 1
cd web; npm run dev                            # terminal 2 -> http://127.0.0.1:5173
```

## Add Purchased Emails

Only emails on the backend allowlist can register.

```powershell
python web_admin.py allow buyer@example.com
```

Show allowed emails:

```powershell
python web_admin.py list
```

Remove an email:

```powershell
python web_admin.py remove buyer@example.com
```

Your email is already allowed:

```text
abhiv@esportscounty.com
```

## Website Flow

1. Buyer opens the site and registers with the purchased email.
2. **Event Setup** — event name, point system, result-graphic template, teams
   and slots.
3. **Match Capture** — the main screen:
   - Drop the lobby screenshots so the site learns slots and player names.
   - Drop all post-match ranking screenshots and press **Read results**.
   - Review the table. Every row carries a confidence score that explains
     itself on hover; duplicate ranks and slots are flagged as you type, and
     the save button stays disabled until they are resolved.
   - Save the match. Unsaved work survives a refresh.
4. **Dashboard** — standings, saved matches, player stats and downloads
   (tournament sheet, standings PNG, latest match PNG).
5. **Observer API** — polls the PUBG Mobile observer endpoint when the server
   can reach it, with a mock mode for demos.

Each screen has its own URL, so the back button, refresh and bookmarks all work.

## Result graphic templates

**Event Setup → Result graphic template** offers ten built-in looks plus a
Custom slot, each shown as a live preview rendered with your own event's
colours and artwork. The choice applies to both exported PNGs — the match
graphic and the overall standings — every time a match is saved.

| Template | Look |
|---|---|
| Midnight Gold | Navy and gold, rounded team cards. The original design. |
| Neon Circuit | Near-black with cyan/magenta glow, for dark stream overlays. |
| Crimson Elite | Red on black, one wide column, outlined rows. |
| Arctic | Light template — white background, ice blue, striped rows. |
| Carbon Mono | Greyscale, hairline rules, no fills. |
| Sunset Arena | Orange into violet, soft cards. |
| Jungle Ops | Military olive, square edges, caps. |
| Royal Purple | Violet and gold with a strong podium highlight. |
| Broadcast Clean | Flat slate, one column, oversized rows — most legible. |
| Championship Gold | Black and heavy gold, big rank numerals. |

### Using your own graphics

Under **Your own graphics** you can upload:

- a **background image** (1920×1080 works best; anything else is scaled to fill
  and centre-cropped), and
- a **logo** (PNG with transparency, placed in a corner you choose).

Artwork works with *any* template, not only the Custom one — pick Custom when
you want the plainest table so your design does the talking. Two things happen
automatically so the standings stay readable on top of a photograph: the
background is dimmed (adjust with the **Background dimming** slider), and every
row gets a solid plate instead of the semi-transparent fill the templates use
over their own flat backgrounds.

You can also override the **accent** and **team name** colours, and force one
or two columns. A one-column layout switches itself to two when the lobby is
too big for the rows to stay legible.

Uploads are stored per event under `data/web/<user>/branding/`, so copying an
event folder takes its branding with it.

## Hosting Note

Manual mode is the best hosted selling product. API mode depends on where the
PUBG observer API is running:

- If the website runs on the same PC/network as the observer API, API mode can
  call it directly.
- If the website is hosted in the cloud, it cannot reach a buyer's local
  `127.0.0.1` observer API without a small local helper app or tunnel.

For cloud selling, launch Manual mode first and keep API mode as an advanced
setup.

## Discord bot integration

The Discord bot is optional. It reads the same saved event and match files as
the website, so anything saved from Manual OCR or Observer API is available in
Discord immediately.

First install the updated requirements:

```bat
%LocalAppData%\Programs\Python\Python312\python.exe -m pip install -r requirements.txt
```

Create a Discord application and bot in the Discord Developer Portal, copy the
bot token, invite it to your server with bot and application-command scopes.
Enable Message Content Intent if you want !results or @YourBot results; slash commands work through application commands.
Then run:

```bat
set DISCORD_BOT_TOKEN=your_discord_bot_token
set DISCORD_RESULTS_EMAIL=abhiv@esportscounty.com
set DISCORD_ANNOUNCE_CHANNEL_ID=your_results_channel_id
run_discord_bot.bat
```

Public result commands:

```text
/results
/results match:1
/standings
/matches
/players

!results
!standings
@YourBot results
```

Automation commands for server managers:

```text
/autostart api_url:http://127.0.0.1:10086/gettotalplayerlist poll_seconds:3 map_name:Erangel
/autostatus
/autostop
```

When auto-poll is running, the bot watches the observer API, saves the match
when only one team remains, regenerates the spreadsheet/graphics, posts the
match result in Discord, then waits for the next match data.



