# WoW Discord Bot

> ⚠️ **Hinweis:** Diese deutsche Fassung wird nicht aktiv gepflegt. Die maßgebliche Dokumentation ist die englische [`README.md`](../README.md) im Repo-Root.

Ein funktionsreicher Discord-Bot für World-of-Warcraft-Spieler. Basiert auf `discord.py` und nutzt die Blizzard-, RaiderIO- und Warcraft-Logs-APIs.

---

## Features

### Character-Befehle
- **`/wow check <name> <realm> [region]`** — Vollständiger Character-Report über 4 Embeds:
  - Profil, Gear (alle 16 Slots), Sekundärstats, Content Readiness
  - Mythic+ Score (Gesamt + pro Rolle), Top-5-M+-Runs, Raid Progression mit Fortschrittsbalken
  - PvP-Stats pro Bracket (2v2 / 3v3 / Solo Shuffle / Rated BG / Skirmish), 8 neueste Achievements
  - Warcraft-Logs-Raid-Parses pro Boss, Best/Median Performance, Profil-Link
- **`/wow compare <name1> <realm1> <name2> <realm2>`** — Direkter Vergleich zweier Characters mit Gesamt-Score.

### Automatische Posts
- 📢 **News-Feed** — Stündliche Prüfung aus drei Quellen, gefiltert auf Patch / Hotfix / Content:
  - Blizzard Official (`worldofwarcraft.blizzard.com`)
  - Wowhead (`wowhead.com/news`)
  - Bluetracker (`bluetracker.gg`, EU-gefiltert)
- 🔄 **Weekly Reset Reminder** — Jeden Dienstag, 3 Stunden vor dem EU-Reset, mit Endgame-Checkliste (Vault, Raids, Weeklies, PvP-Cap, Delves).
- 🔧 **Maintenance-Warnungen** — Alle 4 Stunden vom Blizzard-Service-Status; postet bei `maintenance`, `partial_outage` oder `major_outage`.

### Admin-Befehle
- `/wowsetup news_channel <id>`
- `/wowsetup reset_channel <id>`
- `/wowsetup maint_channel <id>`
- `/wowsetup overview`

---

## Voraussetzungen

- Python 3.10+ (nur beim Start aus dem Source-Code)
- Eine Discord-Anwendung mit Bot-User
- Blizzard-API-Credentials (Pflicht für Profil / Gear / Stats / Achievements)
- Warcraft-Logs-API-Credentials (optional — nur für Raid-Parses)

`/wow check` funktioniert auch ohne Blizzard- oder WCL-Credentials — RaiderIO-Daten (M+-Score, Raid-Progression) brauchen keine Auth.

---

## Setup

### 1. Discord-Bot

1. <https://discord.com/developers/applications> → **New Application**.
2. **Bot** → **Reset Token** → kopieren.
3. **Server Members Intent** und **Message Content Intent** aktivieren.
4. **OAuth2 → URL Generator**: Scopes `bot` + `applications.commands`; Permissions `View Channels`, `Send Messages`, `Read Message History`, `Embed Links`.
5. URL nutzen, um den Bot auf den Server einzuladen.

### 2. Blizzard-API

1. <https://develop.battle.net> → **Create Client**.
2. Redirect URL: `http://localhost`. Intended Use: **Game Data APIs**.
3. **Client ID** und **Client Secret** kopieren.

### 3. Warcraft-Logs-API (optional)

1. <https://www.warcraftlogs.com/api/clients/> → **Create Client**.
2. Redirect URLs: leer lassen. **Public Client: Nein**.
3. **Client ID** und **Client Secret** kopieren.

### 4. `.env` konfigurieren

Kopiere `.env.example` zu `.env` und trage deine Werte ein:

```env
DISCORD_TOKEN=...
BLIZZARD_CLIENT_ID=...
BLIZZARD_CLIENT_SECRET=...
WCL_CLIENT_ID=...
WCL_CLIENT_SECRET=...
```

### 5. Bot starten

**Aus dem Source-Code:**

```bash
pip install -r requirements.txt
python bot.py
```

**Als Standalone-Executable** (Windows): Mit PyInstaller über die mitgelieferte `bot.spec` bauen, `bot.exe` neben die `.env` legen und doppelklicken.

Bei erfolgreichem Start siehst du:

```
[INFO] Logged in as       : WoWBot#1234
[INFO] Blizzard API       : Configured ✓
[INFO] Warcraft Logs API  : Configured ✓
[INFO] Commands           : /wow check · /wow compare · /wowsetup
[INFO] News-Quellen       : Blizzard Official + Wowhead + Bluetracker (EU)
[INFO] Background tasks   : Gestartet
[INFO] Slash commands     : Synced
```

### 6. Erstes Admin-Setup

In Discord (Rechtsklick auf Channel → **Channel-ID kopieren**):

```
/wowsetup news_channel  <channel_id>
/wowsetup reset_channel <channel_id>
/wowsetup maint_channel <channel_id>
/wowsetup overview
```

Alle `/wowsetup`-Antworten sind ephemeral (nur du siehst sie).

---

## Beispiele

```
/wow check Thrall Draenor eu
/wow check Sylvanas twisting-nether eu
/wow compare Thrall Draenor Jaina Stormscale eu
```

Realms mit Leerzeichen werden automatisch umgesetzt (`Twisting Nether` → `twisting-nether`).

---

## Troubleshooting

| Problem | Lösung |
|---|---|
| `Character nicht gefunden` | Name + Realm prüfen; Character muss auf einem Retail-Server sein. |
| M+-Score / Raid-Progression fehlt | Character muss sich kürzlich eingeloggt haben, damit RaiderIO frische Daten hat. |
| Gear / Stats / Achievements fehlen | Blizzard-Credentials in der `.env` prüfen (keine Leerzeichen vor/nach den Werten). |
| Raid-Logs-Sektion leer | WCL-Credentials prüfen; Character muss öffentliche Logs auf warcraftlogs.com haben. |
| Slash-Commands erscheinen nicht | 1–2 Minuten nach dem Start warten oder `!sync` als Bot-Owner ausführen. |
| News / Reset / Maintenance werden nicht gepostet | Channels mit `/wowsetup` setzen; mit `/wowsetup overview` verifizieren. |
| Doppelte News-Posts | `wow_bot_data.json` löschen und Bot neu starten. |

---

## News-Quellen

| Quelle | Farbe | Inhalt |
|---|---|---|
| 🔵 Blizzard Official | Blau (`0x0070DD`) | Offizielle Patch Notes, Hotfixes, Events, Blue Posts |
| 📰 Wowhead | Rot (`0xCC2200`) | Datamines, Hotfix-Zusammenfassungen, Class-Change-Breakdowns |
| 🔷 Bluetracker | Hellblau (`0x3498DB`) | Forum-Blue-Posts (EU-gefiltert) |

Artikel werden gegen Keywords gefiltert (`patch`, `hotfix`, `update`, `nerf`, `buff`, `season`, `class`, …) und über `wow_bot_data.json` dedupliziert.

---

## Projekt-Struktur

```
.
├── bot.py              # Hauptbot (Commands, Embeds, Background-Tasks)
├── bot.spec            # PyInstaller-Spec zum Bauen der bot.exe
├── requirements.txt    # Python-Dependencies
├── .env.example        # Template für die nötigen Environment-Variablen
├── SETUP_GUIDE.txt     # Ausführliche Setup-Anleitung (gemischt EN/DE)
└── docs/
    └── README.de.md    # Diese deutsche README (abgelegt, nicht gepflegt)
```

---

## Lizenz

Keine Lizenz angegeben. Alle Rechte beim Autor.
