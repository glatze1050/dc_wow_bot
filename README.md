# WoW Discord Bot

A feature-rich Discord bot for World of Warcraft players. Built with `discord.py` and powered by the Blizzard, RaiderIO, and Warcraft Logs APIs.

> 🇩🇪 Eine deutsche Version dieser Anleitung liegt unter [`docs/README.de.md`](docs/README.de.md) — sie wird nicht aktiv gepflegt.

---

## Features

### Character commands
- **`/wow check <name> <realm> [region]`** — Full character report across 4 embeds:
  - Profile, gear (all 16 slots), secondary stats, content readiness
  - Mythic+ score (overall + per role), top 5 M+ runs, raid progression with progress bars
  - PvP stats per bracket (2v2 / 3v3 / Solo Shuffle / Rated BG / Skirmish), 8 most recent achievements
  - Warcraft Logs raid parses per boss, best/median performance, profile link
- **`/wow compare <name1> <realm1> <name2> <realm2>`** — Side-by-side comparison of two characters with overall scoring.

### Automatic posts
- 📢 **News feed** — Hourly check across three sources, filtered for patch / hotfix / content:
  - Blizzard Official (`worldofwarcraft.blizzard.com`)
  - Wowhead (`wowhead.com/news`)
  - Bluetracker (`bluetracker.gg`, EU-filtered)
- 🔄 **Weekly reset reminder** — Posted every Tuesday, 3 hours before EU reset, with an endgame checklist (vault, raids, weeklies, PvP cap, delves).
- 🔧 **Maintenance warnings** — Polled every 4 hours from Blizzard's service status; posts on `maintenance`, `partial_outage`, or `major_outage`.

### Admin commands
- `/wowsetup news_channel <id>`
- `/wowsetup reset_channel <id>`
- `/wowsetup maint_channel <id>`
- `/wowsetup overview`

---

## Requirements

- Python 3.10+ (only if running from source)
- A Discord application with a bot user
- Blizzard API credentials (required for profile / gear / stats / achievements)
- Warcraft Logs API credentials (optional — only for raid parses)

`/wow check` still works without Blizzard or WCL credentials — RaiderIO data (M+ score, raid progression) requires no auth.

---

## Setup

### 1. Discord bot

1. Go to <https://discord.com/developers/applications> → **New Application**.
2. **Bot** → **Reset Token** → copy it.
3. Enable **Server Members Intent** and **Message Content Intent**.
4. **OAuth2 → URL Generator**: scopes `bot` + `applications.commands`; permissions `View Channels`, `Send Messages`, `Read Message History`, `Embed Links`.
5. Use the generated URL to invite the bot to your server.

### 2. Blizzard API

1. <https://develop.battle.net> → **Create Client**.
2. Redirect URL: `http://localhost`. Intended Use: **Game Data APIs**.
3. Copy **Client ID** and **Client Secret**.

### 3. Warcraft Logs API (optional)

1. <https://www.warcraftlogs.com/api/clients/> → **Create Client**.
2. Redirect URLs: leave empty. **Public Client: No**.
3. Copy **Client ID** and **Client Secret**.

### 4. Configure `.env`

Copy `.env.example` to `.env` and fill in your values:

```env
DISCORD_TOKEN=...
BLIZZARD_CLIENT_ID=...
BLIZZARD_CLIENT_SECRET=...
WCL_CLIENT_ID=...
WCL_CLIENT_SECRET=...
```

### 5. Run the bot

**From source:**

```bash
pip install -r requirements.txt
python bot.py
```

**As a standalone executable** (Windows): build with PyInstaller using the included `bot.spec`, place `bot.exe` next to `.env`, and double-click.

On a successful start you should see:

```
[INFO] Logged in as       : WoWBot#1234
[INFO] Blizzard API       : Configured ✓
[INFO] Warcraft Logs API  : Configured ✓
[INFO] Commands           : /wow check · /wow compare · /wowsetup
[INFO] News-Quellen       : Blizzard Official + Wowhead + Bluetracker (EU)
[INFO] Background tasks   : Gestartet
[INFO] Slash commands     : Synced
```

### 6. First-time admin setup

In Discord (right-click channel → **Copy Channel ID**):

```
/wowsetup news_channel  <channel_id>
/wowsetup reset_channel <channel_id>
/wowsetup maint_channel <channel_id>
/wowsetup overview
```

All `/wowsetup` responses are ephemeral (only you see them).

---

## Examples

```
/wow check Thrall Draenor eu
/wow check Sylvanas twisting-nether eu
/wow compare Thrall Draenor Jaina Stormscale eu
```

Realms with spaces are normalized automatically (`Twisting Nether` → `twisting-nether`).

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `Character not found` | Check name + realm spelling; character must be on a Retail server. |
| M+ score / raid progression missing | Character must have logged in recently so RaiderIO has fresh data. |
| Gear / stats / achievements missing | Verify Blizzard credentials in `.env` (no leading/trailing whitespace). |
| Raid Logs section empty | Verify WCL credentials; character must have public logs on warcraftlogs.com. |
| Slash commands not appearing | Wait 1–2 minutes after start, or run `!sync` as the bot owner. |
| News / reset / maintenance not posted | Configure channels with `/wowsetup`; verify with `/wowsetup overview`. |
| Duplicate news posts | Delete `wow_bot_data.json` and restart the bot. |

---

## News sources

| Source | Color | Content |
|---|---|---|
| 🔵 Blizzard Official | Blue (`0x0070DD`) | Official patch notes, hotfixes, events, blue posts |
| 📰 Wowhead | Red (`0xCC2200`) | Datamines, hotfix summaries, class-change breakdowns |
| 🔷 Bluetracker | Light blue (`0x3498DB`) | Forum blue posts (EU-filtered) |

Articles are filtered against keywords (`patch`, `hotfix`, `update`, `nerf`, `buff`, `season`, `class`, …) and deduplicated via `wow_bot_data.json`.

---

## Project layout

```
.
├── bot.py              # Main bot (commands, embeds, background tasks)
├── bot.spec            # PyInstaller spec for building bot.exe
├── requirements.txt    # Python dependencies
├── .env.example        # Template for required environment variables
├── SETUP_GUIDE.txt     # Verbose setup walkthrough (mixed EN/DE)
└── docs/
    └── README.de.md    # German README (archived, not actively maintained)
```

---

## License

No license specified. All rights reserved by the author.
