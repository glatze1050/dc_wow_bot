import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiohttp
import asyncio
import os
import json
import base64
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────
BLIZZARD_CLIENT_ID     = os.getenv("BLIZZARD_CLIENT_ID",     "")
BLIZZARD_CLIENT_SECRET = os.getenv("BLIZZARD_CLIENT_SECRET", "")
WCL_CLIENT_ID          = os.getenv("WCL_CLIENT_ID",          "")
WCL_CLIENT_SECRET      = os.getenv("WCL_CLIENT_SECRET",      "")
DISCORD_TOKEN          = os.getenv("DISCORD_TOKEN",          "")
DATA_FILE              = "wow_bot_data.json"

# ─────────────────────────────────────────
#  CLASS COLOURS & EMOJIS
# ─────────────────────────────────────────
CLASS_COLORS = {
    "Death Knight": 0xC41E3A, "Demon Hunter": 0xA330C9,
    "Druid":        0xFF7C0A, "Evoker":       0x33937F,
    "Hunter":       0xAAD372, "Mage":         0x3FC7EB,
    "Monk":         0x00FF98, "Paladin":      0xF48CBA,
    "Priest":       0xDDDDDD, "Rogue":        0xFFF468,
    "Shaman":       0x0070DD, "Warlock":      0x8788EE,
    "Warrior":      0xC69B3A,
}
CLASS_EMOJIS = {
    "Death Knight": "💀", "Demon Hunter": "🔮", "Druid":   "🌿",
    "Evoker":       "🐉", "Hunter":       "🏹", "Mage":    "❄️",
    "Monk":         "👊", "Paladin":      "✨", "Priest":  "🕊️",
    "Rogue":        "🗡️", "Shaman":       "⚡", "Warlock": "🔥",
    "Warrior":      "⚔️",
}
FACTION_EMOJIS  = {"Alliance": "🔵", "Horde": "🔴"}
SLOT_EMOJIS = {
    "HEAD": "🪖", "NECK": "📿", "SHOULDER": "🔱", "BACK": "🧣",
    "CHEST": "🥋", "WRIST": "⌚", "HANDS": "🧤", "WAIST": "🪢",
    "LEGS": "👖", "FEET": "👢", "FINGER_1": "💍", "FINGER_2": "💍",
    "TRINKET_1": "🔮", "TRINKET_2": "🔮", "MAIN_HAND": "⚔️", "OFF_HAND": "🛡️",
}
QUALITY_ICONS = {
    "EPIC": "🟣", "RARE": "🔵", "UNCOMMON": "🟢",
    "COMMON": "⚪", "LEGENDARY": "🟠", "POOR": "⬜",
}
SLOT_ORDER = [
    "HEAD","NECK","SHOULDER","BACK","CHEST","WRIST",
    "HANDS","WAIST","LEGS","FEET",
    "FINGER_1","FINGER_2","TRINKET_1","TRINKET_2",
    "MAIN_HAND","OFF_HAND",
]

# Dungeon full names for M+ runs
DUNGEON_NAMES = {
    "ARA": "Ara-Kara",
    "COT": "City of Threads",
    "GB":  "Grim Batol",
    "MIS": "Mists of Tirna Scithe",
    "NW":  "The Necrotic Wake",
    "SV":  "Stonevault",
    "ToP": "Theater of Pain",
    "WM":  "The War Within",
    "BRH": "Black Rook Hold",
    "DHT": "Darkheart Thicket",
    "FALL": "Siege of Boralus",
    "HoI": "Hall of Infusion",
    "NO":  "Neltharus",
    "RLP": "Ruby Life Pools",
    "SBG": "The Underrot",
    "ULD": "Uldaman",
    "AD":  "Atal'Dazar",
    "FH":  "Freehold",
    "KR":  "The Rookery",
    "PSF": "Priory of the Sacred Flame",
    "DB":  "Darkflame Cleft",
    "DAWN": "The Dawnbreaker",
}

# Content readiness thresholds (equipped ilvl)
CONTENT_THRESHOLDS = [
    (636, "✅ Bereit für **Mythic Raid**"),
    (619, "✅ Bereit für **Heroic Raid** & hohe M+"),
    (606, "✅ Bereit für **Normal Raid** & M+ 10+"),
    (593, "✅ Bereit für **M+ 5+** & LFR"),
    (580, "⚠️ Bereit für **M+ 2-4** & LFR"),
    (0,   "🔰 Noch im Gearing-Prozess — M0 & World Quests empfohlen"),
]

# ─────────────────────────────────────────
#  DATA PERSISTENCE
# ─────────────────────────────────────────
def load_data() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {"news_channel": None, "reset_channel": None, "maint_channel": None, "seen_news": []}

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump({
            "news_channel":  news_channel_id,
            "reset_channel": reset_channel_id,
            "maint_channel": maint_channel_id,
            "seen_news":     seen_news,
        }, f, indent=2)

_data            = load_data()
news_channel_id  = _data.get("news_channel",  None)
reset_channel_id = _data.get("reset_channel", None)
maint_channel_id = _data.get("maint_channel", None)
seen_news: list  = _data.get("seen_news",     [])

# ─────────────────────────────────────────
#  BLIZZARD TOKEN CACHE
# ─────────────────────────────────────────
_blizzard_token        = None
_blizzard_token_expiry = 0

# ─────────────────────────────────────────
#  WARCRAFT LOGS TOKEN CACHE
# ─────────────────────────────────────────
_wcl_token        = None
_wcl_token_expiry = 0

# ─────────────────────────────────────────
#  BOT SETUP
# ─────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ─────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────
def error_embed(msg: str) -> discord.Embed:
    embed = discord.Embed(
        title="❌  Fehler",
        description=msg,
        color=0xC41E3A,
    )
    embed.set_footer(text="WoW Bot  ·  Fehler")
    return embed

def is_admin(interaction: discord.Interaction) -> bool:
    return interaction.user.guild_permissions.administrator

def mp_colour(score: float) -> int:
    if score >= 3000: return 0xFF8000
    if score >= 2500: return 0x9B59B6
    if score >= 2000: return 0x3498DB
    if score >= 1500: return 0x2ECC71
    return 0xAAAAAA

def progress_bar(killed: int, total: int, width: int = 8) -> str:
    if total == 0:
        return "░" * width
    filled = round(killed / total * width)
    return "█" * filled + "░" * (width - filled)

def content_readiness(ilvl: int) -> str:
    for threshold, label in CONTENT_THRESHOLDS:
        if ilvl >= threshold:
            return label
    return CONTENT_THRESHOLDS[-1][1]

def dungeon_full_name(short: str) -> str:
    return DUNGEON_NAMES.get(short, short)

def fmt_stat(d) -> str:
    if isinstance(d, dict):
        rating = d.get("rating", 0)
        pct    = d.get("value", d.get("rating_bonus_value", 0))
        return f"{pct:.1f}% ({rating:,})"
    return str(d)

# ─────────────────────────────────────────
#  BLIZZARD API
# ─────────────────────────────────────────
async def get_blizzard_token(region: str = "eu") -> str:
    global _blizzard_token, _blizzard_token_expiry
    now = datetime.now(timezone.utc).timestamp()
    if _blizzard_token and now < _blizzard_token_expiry - 60:
        return _blizzard_token
    url   = f"https://{region}.battle.net/oauth/token"
    creds = base64.b64encode(f"{BLIZZARD_CLIENT_ID}:{BLIZZARD_CLIENT_SECRET}".encode()).decode()
    async with aiohttp.ClientSession() as s:
        async with s.post(url,
            headers={"Authorization": f"Basic {creds}"},
            data={"grant_type": "client_credentials"},
        ) as r:
            if r.status != 200:
                raise ValueError(f"Blizzard Auth Fehler {r.status}")
            data = await r.json()
            _blizzard_token        = data["access_token"]
            _blizzard_token_expiry = now + data["expires_in"]
            return _blizzard_token

async def blizzard_get(path: str, region: str = "eu") -> dict:
    token = await get_blizzard_token(region)
    url   = f"https://{region}.api.blizzard.com{path}"
    params = {"namespace": f"profile-{region}", "locale": "en_GB" if region == "eu" else "en_US"}
    async with aiohttp.ClientSession() as s:
        async with s.get(url, params=params, headers={"Authorization": f"Bearer {token}"}) as r:
            if r.status == 404:
                raise ValueError("Character nicht gefunden. Name und Realm prüfen.")
            if r.status != 200:
                raise ValueError(f"Blizzard API Fehler {r.status}")
            return await r.json()

def realm_slug(realm: str) -> str:
    return realm.lower().replace(" ", "-").replace("'", "").replace("(", "").replace(")", "")

async def get_summary(realm: str, name: str, region: str) -> dict:
    return await blizzard_get(f"/profile/wow/character/{realm_slug(realm)}/{name.lower()}", region)

async def get_equipment(realm: str, name: str, region: str) -> dict:
    return await blizzard_get(f"/profile/wow/character/{realm_slug(realm)}/{name.lower()}/equipment", region)

async def get_statistics(realm: str, name: str, region: str) -> dict:
    return await blizzard_get(f"/profile/wow/character/{realm_slug(realm)}/{name.lower()}/statistics", region)

async def get_achievements(realm: str, name: str, region: str) -> dict:
    return await blizzard_get(f"/profile/wow/character/{realm_slug(realm)}/{name.lower()}/achievements", region)

async def get_pvp_summary(realm: str, name: str, region: str) -> dict:
    return await blizzard_get(f"/profile/wow/character/{realm_slug(realm)}/{name.lower()}/pvp-summary", region)

# ─────────────────────────────────────────
#  RAIDERIO API
# ─────────────────────────────────────────
async def get_raiderio(realm: str, name: str, region: str) -> dict:
    params = {
        "region": region, "realm": realm, "name": name,
        "fields": "mythic_plus_scores_by_season:current,raid_progression,mythic_plus_best_runs,gear",
    }
    async with aiohttp.ClientSession() as s:
        async with s.get("https://raider.io/api/v1/characters/profile", params=params) as r:
            if r.status == 400:
                raise ValueError("Character nicht auf RaiderIO gefunden.")
            if r.status != 200:
                raise ValueError(f"RaiderIO Fehler {r.status}")
            return await r.json()

# ─────────────────────────────────────────
#  WARCRAFT LOGS API  (v2 GraphQL)
# ─────────────────────────────────────────
async def get_wcl_token() -> str:
    global _wcl_token, _wcl_token_expiry
    now = datetime.now(timezone.utc).timestamp()
    if _wcl_token and now < _wcl_token_expiry - 60:
        return _wcl_token
    creds = base64.b64encode(f"{WCL_CLIENT_ID}:{WCL_CLIENT_SECRET}".encode()).decode()
    async with aiohttp.ClientSession() as s:
        async with s.post(
            "https://www.warcraftlogs.com/oauth/token",
            headers={"Authorization": f"Basic {creds}"},
            data={"grant_type": "client_credentials"},
        ) as r:
            if r.status != 200:
                raise ValueError(f"WCL Auth Fehler {r.status}")
            data = await r.json()
            _wcl_token        = data["access_token"]
            _wcl_token_expiry = now + data["expires_in"]
            return _wcl_token

async def get_wcl_character(realm: str, name: str, region: str) -> dict:
    """Holt zoneRankings (beste Parses im aktuellen Raid) + Profil-Link."""
    token = await get_wcl_token()
    query = """
    query($name: String!, $server: String!, $region: String!) {
      characterData {
        character(name: $name, serverSlug: $server, serverRegion: $region) {
          id
          name
          classID
          zoneRankings
        }
      }
    }
    """
    variables = {
        "name":   name.capitalize(),
        "server": realm_slug(realm),
        "region": region.upper(),
    }
    async with aiohttp.ClientSession() as s:
        async with s.post(
            "https://www.warcraftlogs.com/api/v2/client",
            headers={"Authorization": f"Bearer {token}"},
            json={"query": query, "variables": variables},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as r:
            if r.status != 200:
                raise ValueError(f"WCL API Fehler {r.status}")
            data = await r.json()
            char = (data.get("data") or {}).get("characterData", {}).get("character")
            if not char:
                raise ValueError("Character nicht auf Warcraft Logs.")
            return char

def wcl_parse_emoji(pct: float) -> str:
    if pct >= 99: return "🟠"   # Artifact / Legendary
    if pct >= 95: return "🟣"   # Epic
    if pct >= 75: return "🔵"   # Rare
    if pct >= 50: return "🟢"   # Uncommon
    if pct >= 25: return "⚪"   # Common
    return "⬜"                  # Poor

# ─────────────────────────────────────────
#  NEWS FETCHER
#  Quelle 1: worldofwarcraft.blizzard.com — Offizielle News & Patch Notes
#  Quelle 2: wowhead.com                  — Datamines, Hotfixes, Guides
#  Quelle 3: bluetracker.gg               — Blue Posts (nur EU-gefiltert)
# ─────────────────────────────────────────
NEWS_KEYWORDS = [
    "patch", "hotfix", "update", "maintenance", "notes",
    "season", "fix", "change", "nerf", "buff", "class",
]

# Fallback-Thumbnails pro Quelle (rechts im Embed)
DEFAULT_THUMB_BLIZZARD    = "https://wow.zamimg.com/images/wow/icons/large/inv_misc_questionmark.jpg"
DEFAULT_THUMB_WOWHEAD     = "https://wow.zamimg.com/images/logos/wh-icon-300.png"
DEFAULT_THUMB_BLUETRACKER = "https://bnetcmsus-a.akamaihd.net/cms/blog_header/x9/X9Y9Y9TXMHU61560451739683.png"

async def fetch_news_blizzard() -> list:
    url = "https://worldofwarcraft.blizzard.com/en-gb/api/search/news?page=1&pageSize=8"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status != 200:
                    return []
                data = await r.json()
                results = []
                for item in data.get("results", [])[:8]:
                    slug  = item.get("slug", "")
                    title = item.get("title", "")
                    type_ = item.get("type", {}).get("slug", "news")
                    # Filter: only patch/hotfix/game content, skip pure marketing
                    is_relevant = (
                        type_ in ("patch-notes", "hotfixes", "news", "blue-tracker")
                        or any(kw in title.lower() for kw in NEWS_KEYWORDS)
                    )
                    if not is_relevant:
                        continue
                    results.append({
                        "title":  title,
                        "url":    f"https://worldofwarcraft.blizzard.com/en-gb/news/{slug}",
                        "guid":   slug,
                        "source": "Blizzard Official",
                        "icon":   "🔵",
                        "color":  0x0070DD,
                        "thumb":  item.get("thumbnail", {}).get("url") or DEFAULT_THUMB_BLIZZARD,
                    })
                return results
    except Exception:
        return []

async def fetch_news_wowhead() -> list:
    import xml.etree.ElementTree as ET
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get("https://www.wowhead.com/news/rss", timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status != 200:
                    return []
                text = await r.text()
        root    = ET.fromstring(text)
        results = []
        for item in root.findall(".//item")[:8]:
            title = (item.findtext("title") or "").strip()
            link  = (item.findtext("link")  or "").strip()
            guid  = (item.findtext("guid")  or link).strip()
            desc  = (item.findtext("description") or "").lower()
            # Filter: only patch/hotfix content
            is_relevant = any(kw in title.lower() or kw in desc for kw in NEWS_KEYWORDS)
            if not is_relevant:
                continue
            if title and link:
                results.append({
                    "title":  title,
                    "url":    link,
                    "guid":   guid,
                    "source": "Wowhead",
                    "icon":   "📰",
                    "color":  0xCC2200,
                    "thumb":  DEFAULT_THUMB_WOWHEAD,
                })
        return results
    except Exception:
        return []

async def fetch_news_bluetracker() -> list:
    import xml.etree.ElementTree as ET
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://www.bluetracker.gg/rss/wow/",
                timeout=aiohttp.ClientTimeout(total=10),
                headers={"User-Agent": "Mozilla/5.0 (WoW Discord Bot)"},
            ) as r:
                if r.status != 200:
                    return []
                text = await r.text()
        root    = ET.fromstring(text)
        results = []
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            link  = (item.findtext("link")  or "").strip()
            guid  = (item.findtext("guid")  or link).strip()
            # EU-only filter: URL muss "/eu-en/" enthalten ODER Titel mit "[EU]" beginnen
            is_eu = ("/eu-en/" in link) or title.upper().startswith("[EU]")
            if not is_eu:
                continue
            if title and link:
                results.append({
                    "title":  title,
                    "url":    link,
                    "guid":   guid,
                    "source": "Bluetracker EU",
                    "icon":   "🔷",
                    "color":  0x3498DB,
                    "thumb":  DEFAULT_THUMB_BLUETRACKER,
                })
            if len(results) >= 8:
                break
        return results
    except Exception:
        return []

# ─────────────────────────────────────────
#  /wow check
# ─────────────────────────────────────────
class WowGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="wow", description="WoW Character Commands")

    # ══════════════════════════════════════
    #  /wow check
    # ══════════════════════════════════════
    @app_commands.command(name="check", description="Vollständiger Character-Check: Profil, Gear, Stats, M+, Raids, PvP, Achievements")
    @app_commands.describe(
        name="Character Name",
        realm="Realm (z.B. Silvermoon, Stormscale, twisting-nether)",
        region="Region (Standard: eu)",
    )
    @app_commands.choices(region=[
        app_commands.Choice(name="🇪🇺 EU", value="eu"),
        app_commands.Choice(name="🇺🇸 US", value="us"),
    ])
    async def check(self, interaction: discord.Interaction, name: str, realm: str, region: str = "eu"):
        await interaction.response.defer()

        blizzard_ok = bool(BLIZZARD_CLIENT_ID and BLIZZARD_CLIENT_SECRET)
        wcl_ok      = bool(WCL_CLIENT_ID and WCL_CLIENT_SECRET)

        async def safe(coro):
            try:
                return await coro
            except Exception:
                return None

        if blizzard_ok:
            summary, equipment, statistics, achievements, pvp, rio, wcl = await asyncio.gather(
                safe(get_summary(realm, name, region)),
                safe(get_equipment(realm, name, region)),
                safe(get_statistics(realm, name, region)),
                safe(get_achievements(realm, name, region)),
                safe(get_pvp_summary(realm, name, region)),
                safe(get_raiderio(realm, name, region)),
                safe(get_wcl_character(realm, name, region)) if wcl_ok else asyncio.sleep(0, result=None),
            )
        else:
            summary = equipment = statistics = achievements = pvp = None
            rio, wcl = await asyncio.gather(
                safe(get_raiderio(realm, name, region)),
                safe(get_wcl_character(realm, name, region)) if wcl_ok else asyncio.sleep(0, result=None),
            )

        if not summary and not rio:
            return await interaction.followup.send(embed=error_embed(
                f"**{name}** auf **{realm}-{region.upper()}** nicht gefunden.\n"
                "Name & Realm prüfen. Character muss auf einem Retail-Server sein."
            ))

        # ── Base info ─────────────────────────────────────────
        char_class  = ""
        if summary:
            char_class = summary.get("character_class", {}).get("name", "")
        elif rio:
            char_class = rio.get("class", "")

        mp_score = 0.0
        if rio:
            seasons = rio.get("mythic_plus_scores_by_season", [])
            if seasons:
                mp_score = seasons[0].get("scores", {}).get("all", 0.0)

        color       = CLASS_COLORS.get(char_class, mp_colour(mp_score))
        class_emoji = CLASS_EMOJIS.get(char_class, "⚔️")

        char_name  = summary.get("name", name.capitalize()) if summary else (rio or {}).get("name", name.capitalize())
        realm_name = summary.get("realm", {}).get("name", realm) if summary else (rio or {}).get("realm", realm)

        # Thumbnail: WoW Armory render
        thumb_url = None
        if rio and rio.get("thumbnail_url"):
            thumb_url = f"https://render.worldofwarcraft.com/{region}/" + rio["thumbnail_url"]

        embeds = []

        # ══════════════════════════════════
        #  EMBED 1 — PROFIL + GEAR + STATS
        # ══════════════════════════════════
        e1 = discord.Embed(color=color)
        e1.set_author(
            name=f"{class_emoji}  {char_name}  —  {realm_name} ({region.upper()})",
            icon_url=thumb_url or discord.Embed.Empty,
        )
        if thumb_url:
            e1.set_thumbnail(url=thumb_url)

        # ── Profil ────────────────────────────────────────────
        if summary:
            spec        = summary.get("active_spec", {}).get("name", "?")
            race        = summary.get("race",         {}).get("name", "?")
            faction     = summary.get("faction",      {}).get("name", "?")
            faction_ico = FACTION_EMOJIS.get(faction, "⚪")
            guild       = summary.get("guild",        {}).get("name", "")
            guild_str   = f"**<{guild}>**" if guild else "*Kein Guild*"
            level       = summary.get("level", "?")
            ilvl_eq     = summary.get("equipped_item_level", 0)
            ilvl_avg    = summary.get("average_item_level",  0)
            ach_pts     = summary.get("achievement_points",  0)
            readiness   = content_readiness(ilvl_eq)

            last_login_str = "Unbekannt"
            ts = summary.get("last_login_timestamp")
            if ts:
                dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
                last_login_str = f"<t:{int(dt.timestamp())}:R>"

            e1.add_field(name="📋 Profil", value=(
                f"{faction_ico} **{race}** {char_class} — {spec}\n"
                f"🏛️ {guild_str}\n"
                f"📊 Level **{level}** · iLvl **{ilvl_eq}** *(avg {ilvl_avg})*\n"
                f"🏆 **{ach_pts:,}** Achievement Points\n"
                f"🕒 Zuletzt online: {last_login_str}"
            ), inline=False)

            e1.add_field(name="🎯 Content Readiness", value=readiness, inline=False)

        elif rio:
            spec = rio.get("active_spec_name", "?")
            e1.add_field(name="📋 Profil", value=(
                f"{class_emoji} **{char_class}** — {spec}\n"
                f"*(Blizzard API nicht konfiguriert)*"
            ), inline=False)

        # ── Gear ──────────────────────────────────────────────
        if equipment:
            items_by_slot = {item["slot"]["type"]: item for item in equipment.get("equipped_items", [])}
            gear_lines = []
            total_ilvl = 0
            count      = 0
            for slot in SLOT_ORDER:
                if slot not in items_by_slot:
                    continue
                item      = items_by_slot[slot]
                slot_name = item.get("slot", {}).get("name", slot)
                item_name = item.get("name", "Unknown")
                item_ilvl = item.get("level", {}).get("value", 0)
                quality   = item.get("quality", {}).get("type", "COMMON")
                s_emoji   = SLOT_EMOJIS.get(slot, "🔹")
                q_icon    = QUALITY_ICONS.get(quality, "⚪")
                gear_lines.append(f"{s_emoji} **{slot_name}** {q_icon} {item_name} `{item_ilvl}`")
                if item_ilvl:
                    total_ilvl += item_ilvl
                    count      += 1

            if gear_lines:
                mid     = len(gear_lines) // 2
                avg_ilvl = round(total_ilvl / count) if count else 0
                e1.add_field(name=f"🛡️ Gear  *(Ø {avg_ilvl} iLvl)*", value="\n".join(gear_lines[:mid]), inline=True)
                e1.add_field(name="\u200b",                            value="\n".join(gear_lines[mid:]), inline=True)

        # ── Sekundärstats ─────────────────────────────────────
        if statistics:
            haste    = statistics.get("haste",    {})
            crit     = statistics.get("crit",     {})
            mastery  = statistics.get("mastery",  {})
            vers     = statistics.get("versatility", 0)
            vers_dmg = statistics.get("versatility_damage_done_bonus", 0)

            # Highest stat badge
            stats_values = {
                "Haste":        haste.get("rating", 0) if isinstance(haste, dict) else 0,
                "Crit":         crit.get("rating", 0)  if isinstance(crit,  dict) else 0,
                "Mastery":      mastery.get("rating", 0) if isinstance(mastery, dict) else 0,
                "Versatility":  vers if isinstance(vers, int) else 0,
            }
            top_stat = max(stats_values, key=stats_values.get)

            e1.add_field(name=f"📊 Sekundärstats  *(Hauptstat: {top_stat})*", value=(
                f"⚡ Haste:        **{fmt_stat(haste)}**\n"
                f"🎯 Crit:         **{fmt_stat(crit)}**\n"
                f"🔮 Mastery:      **{fmt_stat(mastery)}**\n"
                f"🛡️ Versatility: **{vers_dmg:.1f}% ({vers:,})**"
            ), inline=False)

        e1.set_footer(text="WoW Bot · Seite 1/4  —  Profil, Gear & Stats")
        embeds.append(e1)

        # ══════════════════════════════════
        #  EMBED 2 — M+ + RAIDS
        # ══════════════════════════════════
        e2 = discord.Embed(color=color)
        e2.set_author(
            name=f"{class_emoji}  {char_name}  —  Mythic+ & Raids",
            icon_url=thumb_url or discord.Embed.Empty,
        )
        if thumb_url:
            e2.set_thumbnail(url=thumb_url)

        if rio:
            # M+ Score
            seasons = rio.get("mythic_plus_scores_by_season", [])
            if seasons:
                sc     = seasons[0].get("scores", {})
                all_sc = sc.get("all",    0)
                tank   = sc.get("tank",   0)
                healer = sc.get("healer", 0)
                dps    = sc.get("dps",    0)

                # Score badge
                if all_sc >= 3000:   score_badge = "🟠 Elite"
                elif all_sc >= 2500: score_badge = "🟣 Fortgeschritten"
                elif all_sc >= 2000: score_badge = "🔵 Erfahren"
                elif all_sc >= 1500: score_badge = "🟢 Aktiv"
                elif all_sc > 0:     score_badge = "⬜ Beginner"
                else:                score_badge = "—"

                e2.add_field(name="🗝️ Mythic+ Score", value=(
                    f"**{all_sc:.0f}**  {score_badge}\n"
                    f"🛡️ Tank `{tank:.0f}`  💚 Healer `{healer:.0f}`  ⚔️ DPS `{dps:.0f}`"
                ), inline=False)

            # Top 5 Runs
            runs = rio.get("mythic_plus_best_runs", [])[:5]
            if runs:
                lines = []
                for r in runs:
                    short    = r.get("short_name", r.get("dungeon", "?"))
                    full     = dungeon_full_name(short)
                    level    = r.get("mythic_level", "?")
                    sc_r     = r.get("score", 0)
                    upgrades = r.get("num_keystone_upgrades", 0)
                    stars    = "⭐" * upgrades if upgrades else "  "
                    lines.append(f"🔑 `+{level:>2}` **{full}** {stars} — `{sc_r:.1f} pts`")
                e2.add_field(name="🏅 Top 5 M+ Runs", value="\n".join(lines), inline=False)

            # Raid Progression
            prog_dict = rio.get("raid_progression", {})
            if prog_dict:
                e2.add_field(name="⠀", value="**🏰 Raid Progression**", inline=False)
                for raid_name, p in prog_dict.items():
                    n  = p.get("normal_bosses_killed", 0)
                    h  = p.get("heroic_bosses_killed", 0)
                    m  = p.get("mythic_bosses_killed", 0)
                    nt = p.get("total_bosses", 0)
                    display = raid_name.replace("-", " ").title()
                    e2.add_field(name=f"📍 {display}", value=(
                        f"🟢 N `{progress_bar(n,nt)}` **{n}/{nt}**\n"
                        f"🔵 H `{progress_bar(h,nt)}` **{h}/{nt}**\n"
                        f"🟣 M `{progress_bar(m,nt)}` **{m}/{nt}**"
                    ), inline=True)

            profile_url = rio.get("profile_url")
            if profile_url:
                e2.add_field(name="🔗 RaiderIO", value=f"[Profil ansehen]({profile_url})", inline=False)
        else:
            e2.description = "*(RaiderIO-Daten nicht verfügbar — Character muss sich kürzlich eingeloggt haben.)*"

        e2.set_footer(text="WoW Bot · Seite 2/4  —  Mythic+ & Raids")
        embeds.append(e2)

        # ══════════════════════════════════
        #  EMBED 3 — PvP + ACHIEVEMENTS
        # ══════════════════════════════════
        e3 = discord.Embed(color=color)
        e3.set_author(
            name=f"{class_emoji}  {char_name}  —  PvP & Achievements",
            icon_url=thumb_url or discord.Embed.Empty,
        )
        if thumb_url:
            e3.set_thumbnail(url=thumb_url)

        # ── PvP ───────────────────────────────────────────────
        if pvp:
            brackets = pvp.get("brackets", [])
            pvp_lines = []
            for bracket in brackets:
                b_type  = bracket.get("bracket", {}).get("type", "")
                rating  = bracket.get("rating", 0)
                wins    = bracket.get("season_match_statistics", {}).get("won", 0)
                losses  = bracket.get("season_match_statistics", {}).get("lost", 0)
                total   = wins + losses
                winrate = round(wins / total * 100) if total > 0 else 0

                if b_type == "ARENA_2v2":   label = "⚔️ 2v2 Arena"
                elif b_type == "ARENA_3v3": label = "⚔️ 3v3 Arena"
                elif b_type == "BATTLEGROUND": label = "🏹 Rated BG"
                elif b_type == "ARENA_SKIRMISH": label = "🗡️ Skirmish"
                elif b_type == "SHUFFLE":   label = "🔀 Solo Shuffle"
                else:                       label = b_type.replace("_", " ").title()

                if rating > 0 or total > 0:
                    pvp_lines.append(
                        f"**{label}**\n"
                        f"Rating: **{rating}** · {wins}W/{losses}L · {winrate}% WR"
                    )

            if pvp_lines:
                e3.add_field(name="🏆 PvP Stats", value="\n\n".join(pvp_lines), inline=False)
            else:
                e3.add_field(name="🏆 PvP Stats", value="*Keine PvP-Aktivität diese Season.*", inline=False)

        # ── Achievements ──────────────────────────────────────
        if achievements:
            ach_pts    = (summary or {}).get("achievement_points", 0)
            ach_list   = achievements.get("achievements", [])
            total_done = len([a for a in ach_list if a.get("completed_timestamp")])

            recent = sorted(
                [a for a in ach_list if a.get("completed_timestamp")],
                key=lambda a: a["completed_timestamp"],
                reverse=True,
            )[:8]

            header = f"🏅 **{ach_pts:,} Punkte** · {total_done:,} abgeschlossen\n"
            lines  = []
            for a in recent:
                ts    = a["completed_timestamp"]
                dt    = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
                dts   = f"<t:{int(dt.timestamp())}:d>"
                aname = a.get("achievement", {}).get("name", "Unknown")
                lines.append(f"🏆 **{aname}** — {dts}")

            e3.add_field(
                name="🎖️ Achievements  *(8 neueste)*",
                value=header + "\n".join(lines),
                inline=False,
            )

        e3.set_footer(text="WoW Bot · Seite 3/4  —  PvP & Achievements")
        embeds.append(e3)

        # ══════════════════════════════════
        #  EMBED 4 — WARCRAFT LOGS
        # ══════════════════════════════════
        e4 = discord.Embed(color=color)
        e4.set_author(
            name=f"{class_emoji}  {char_name}  —  Raid Logs (Warcraft Logs)",
            icon_url=thumb_url or discord.Embed.Empty,
        )
        if thumb_url:
            e4.set_thumbnail(url=thumb_url)

        if wcl:
            zr_raw = wcl.get("zoneRankings")
            # zoneRankings kann String (JSON) oder dict zurückgeben
            if isinstance(zr_raw, str):
                try:    zr = json.loads(zr_raw)
                except: zr = {}
            else:
                zr = zr_raw or {}

            best_avg   = zr.get("bestPerformanceAverage")
            median_avg = zr.get("medianPerformanceAverage")
            zone_name  = (zr.get("zone") or {}).get("name") if isinstance(zr.get("zone"), dict) else zr.get("zoneName", "Aktueller Raid")
            difficulty = zr.get("difficulty")
            rankings   = zr.get("rankings", []) or []

            if best_avg is not None:
                badge = wcl_parse_emoji(best_avg)
                diff_label = {3: "Normal", 4: "Heroic", 5: "Mythic"}.get(difficulty, "")
                header_val = (
                    f"{badge} **Best Avg:** `{best_avg:.1f}%`\n"
                    f"📊 **Median Avg:** `{(median_avg or 0):.1f}%`"
                )
                if diff_label:
                    header_val = f"⚔️ **{zone_name}** — {diff_label}\n" + header_val
                elif zone_name:
                    header_val = f"⚔️ **{zone_name}**\n" + header_val
                e4.add_field(name="🗡️ Gesamt-Performance", value=header_val, inline=False)

            # Beste Parses pro Boss
            if rankings:
                lines = []
                for r in rankings[:12]:
                    enc   = r.get("encounter", {}) or {}
                    bname = enc.get("name", "?")
                    pct   = r.get("rankPercent")
                    if pct is None:
                        continue
                    spec  = r.get("spec", "")
                    dps   = r.get("amount", 0)
                    badge = wcl_parse_emoji(pct)
                    spec_str = f" *({spec})*" if spec else ""
                    dps_str  = f" · `{dps:,.0f}`" if dps else ""
                    lines.append(f"{badge} **{bname}**{spec_str} — `{pct:.1f}%`{dps_str}")
                if lines:
                    e4.add_field(name="🏆 Boss-Parses  *(Best)*", value="\n".join(lines), inline=False)

            # Link zum WCL-Profil
            wcl_id = wcl.get("id")
            if wcl_id:
                prof_url = f"https://www.warcraftlogs.com/character/id/{wcl_id}"
                e4.add_field(name="🔗 Warcraft Logs", value=f"[Profil ansehen]({prof_url})", inline=False)

            if best_avg is None and not rankings:
                e4.description = "*Keine Raid-Logs für diesen Character gefunden.*"
        elif not wcl_ok:
            e4.description = "*Warcraft Logs API nicht konfiguriert (WCL_CLIENT_ID / WCL_CLIENT_SECRET in .env setzen).*"
        else:
            e4.description = "*Character hat keine öffentlichen Raid-Logs.*"

        e4.set_footer(text="WoW Bot · Seite 4/4  —  Raid Logs  |  Daten: Blizzard API + RaiderIO + Warcraft Logs")
        embeds.append(e4)

        await interaction.followup.send(embeds=embeds)

    # ══════════════════════════════════════
    #  /wow compare
    # ══════════════════════════════════════
    @app_commands.command(name="compare", description="Zwei Characters vergleichen")
    @app_commands.describe(
        name1="Erster Character",
        realm1="Realm des ersten Characters",
        name2="Zweiter Character",
        realm2="Realm des zweiten Characters",
        region="Region (Standard: eu)",
    )
    @app_commands.choices(region=[
        app_commands.Choice(name="🇪🇺 EU", value="eu"),
        app_commands.Choice(name="🇺🇸 US", value="us"),
    ])
    async def compare(
        self,
        interaction: discord.Interaction,
        name1: str, realm1: str,
        name2: str, realm2: str,
        region: str = "eu",
    ):
        await interaction.response.defer()

        async def safe(coro):
            try:    return await coro
            except: return None

        blizzard_ok = bool(BLIZZARD_CLIENT_ID and BLIZZARD_CLIENT_SECRET)

        if blizzard_ok:
            s1, s2, rio1, rio2 = await asyncio.gather(
                safe(get_summary(realm1, name1, region)),
                safe(get_summary(realm2, name2, region)),
                safe(get_raiderio(realm1, name1, region)),
                safe(get_raiderio(realm2, name2, region)),
            )
        else:
            s1 = s2 = None
            rio1, rio2 = await asyncio.gather(
                safe(get_raiderio(realm1, name1, region)),
                safe(get_raiderio(realm2, name2, region)),
            )

        if not s1 and not rio1:
            return await interaction.followup.send(embed=error_embed(f"**{name1}** auf **{realm1}** nicht gefunden."))
        if not s2 and not rio2:
            return await interaction.followup.send(embed=error_embed(f"**{name2}** auf **{realm2}** nicht gefunden."))

        def char_info(s, rio, name, realm):
            cn     = s.get("name", name.capitalize())  if s   else (rio or {}).get("name", name.capitalize())
            rn     = s.get("realm", {}).get("name", realm) if s else realm
            cls    = s.get("character_class", {}).get("name", "") if s else (rio or {}).get("class", "")
            spec   = s.get("active_spec", {}).get("name", "?")    if s else (rio or {}).get("active_spec_name", "?")
            ilvl   = s.get("equipped_item_level", 0) if s else 0
            ach    = s.get("achievement_points", 0)  if s else 0
            ts     = s.get("last_login_timestamp")   if s else None
            last   = f"<t:{int(datetime.fromtimestamp(ts/1000,tz=timezone.utc).timestamp())}:R>" if ts else "?"
            mp     = 0.0
            if rio:
                seasons = rio.get("mythic_plus_scores_by_season", [])
                if seasons:
                    mp = seasons[0].get("scores", {}).get("all", 0.0)
            return cn, rn, cls, spec, ilvl, ach, last, mp

        cn1, rn1, cls1, spec1, ilvl1, ach1, last1, mp1 = char_info(s1, rio1, name1, realm1)
        cn2, rn2, cls2, spec2, ilvl2, ach2, last2, mp2 = char_info(s2, rio2, name2, realm2)

        e1_col = CLASS_COLORS.get(cls1, 0x888888)
        e2_col = CLASS_COLORS.get(cls2, 0x888888)

        def win(a, b):
            return "✅" if a > b else ("🔴" if a < b else "🟡")

        embed = discord.Embed(
            title=f"⚔️  {cn1} vs {cn2}",
            color=0xFFD700,
        )

        # Build side-by-side comparison
        embed.add_field(
            name=f"{CLASS_EMOJIS.get(cls1,'⚔️')} {cn1}\n{rn1} · {cls1}",
            value=(
                f"iLvl: **{ilvl1}** {win(ilvl1, ilvl2)}\n"
                f"M+ Score: **{mp1:.0f}** {win(mp1, mp2)}\n"
                f"Achievements: **{ach1:,}** {win(ach1, ach2)}\n"
                f"Zuletzt: {last1}"
            ),
            inline=True,
        )
        embed.add_field(name="⠀", value="⠀", inline=True)
        embed.add_field(
            name=f"{CLASS_EMOJIS.get(cls2,'⚔️')} {cn2}\n{rn2} · {cls2}",
            value=(
                f"iLvl: **{ilvl2}** {win(ilvl2, ilvl1)}\n"
                f"M+ Score: **{mp2:.0f}** {win(mp2, mp1)}\n"
                f"Achievements: **{ach2:,}** {win(ach2, ach1)}\n"
                f"Zuletzt: {last2}"
            ),
            inline=True,
        )

        # Raid Progression comparison
        if rio1 and rio2:
            prog1 = rio1.get("raid_progression", {})
            prog2 = rio2.get("raid_progression", {})
            all_raids = set(list(prog1.keys()) + list(prog2.keys()))
            raid_lines = []
            for raid in list(all_raids)[:3]:
                p1 = prog1.get(raid, {})
                p2 = prog2.get(raid, {})
                m1 = p1.get("mythic_bosses_killed", 0)
                m2 = p2.get("mythic_bosses_killed", 0)
                nt = p1.get("total_bosses", p2.get("total_bosses", 0))
                raid_lines.append(
                    f"**{raid.replace('-',' ').title()}** (Mythic)\n"
                    f"{cn1}: **{m1}/{nt}** {win(m1,m2)}  ·  {cn2}: **{m2}/{nt}** {win(m2,m1)}"
                )
            if raid_lines:
                embed.add_field(name="🏰 Raid Mythic Vergleich", value="\n\n".join(raid_lines), inline=False)

        # Overall winner
        score1 = (ilvl1 / 700 * 40) + (mp1 / 3500 * 40) + (ach1 / 50000 * 20)
        score2 = (ilvl2 / 700 * 40) + (mp2 / 3500 * 40) + (ach2 / 50000 * 20)
        if score1 > score2 + 1:
            winner = f"🏆 **{cn1}** gewinnt den Vergleich!"
        elif score2 > score1 + 1:
            winner = f"🏆 **{cn2}** gewinnt den Vergleich!"
        else:
            winner = "🟡 Zu knapp — kein klarer Gewinner!"
        embed.add_field(name="🎯 Gesamtbewertung", value=winner, inline=False)

        embed.set_footer(text=f"WoW Bot · /wow compare · {region.upper()}  |  Daten: Blizzard API + RaiderIO")
        await interaction.followup.send(embed=embed)


# ─────────────────────────────────────────
#  ADMIN: /wowsetup
# ─────────────────────────────────────────
class WowSetupGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="wowsetup", description="WoW Bot Channels konfigurieren (nur Admins)")
        self.default_member_permissions = discord.Permissions(administrator=True)

    @app_commands.command(name="news_channel", description="Channel für WoW News & Patch Notes setzen")
    @app_commands.describe(channel_id="Channel ID (Rechtsklick → ID kopieren)")
    async def set_news(self, interaction: discord.Interaction, channel_id: str):
        global news_channel_id
        if not is_admin(interaction):
            return await interaction.response.send_message(embed=error_embed("Nur für Admins."), ephemeral=True)
        try:    cid = int(channel_id)
        except: return await interaction.response.send_message(embed=error_embed("Ungültige Channel ID."), ephemeral=True)
        ch = interaction.guild.get_channel(cid)
        if not ch:
            return await interaction.response.send_message(embed=error_embed(f"Channel `{cid}` nicht gefunden."), ephemeral=True)
        news_channel_id = cid
        save_data()
        embed = discord.Embed(
            title="✅  News Channel gesetzt",
            description=f"📰  WoW News & Patch Notes werden ab jetzt in <#{cid}> gepostet.",
            color=0x00FF98,
        )
        embed.set_footer(text="WoW Bot  ·  Setup erfolgreich")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="reset_channel", description="Channel für Weekly Reset Reminders setzen")
    @app_commands.describe(channel_id="Channel ID")
    async def set_reset(self, interaction: discord.Interaction, channel_id: str):
        global reset_channel_id
        if not is_admin(interaction):
            return await interaction.response.send_message(embed=error_embed("Nur für Admins."), ephemeral=True)
        try:    cid = int(channel_id)
        except: return await interaction.response.send_message(embed=error_embed("Ungültige Channel ID."), ephemeral=True)
        ch = interaction.guild.get_channel(cid)
        if not ch:
            return await interaction.response.send_message(embed=error_embed(f"Channel `{cid}` nicht gefunden."), ephemeral=True)
        reset_channel_id = cid
        save_data()
        embed = discord.Embed(
            title="✅  Reset Channel gesetzt",
            description=f"🔄  Weekly Reset Reminders werden ab jetzt in <#{cid}> gepostet.",
            color=0x00FF98,
        )
        embed.set_footer(text="WoW Bot  ·  Setup erfolgreich")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="maint_channel", description="Channel für Maintenance Warnungen setzen")
    @app_commands.describe(channel_id="Channel ID")
    async def set_maint(self, interaction: discord.Interaction, channel_id: str):
        global maint_channel_id
        if not is_admin(interaction):
            return await interaction.response.send_message(embed=error_embed("Nur für Admins."), ephemeral=True)
        try:    cid = int(channel_id)
        except: return await interaction.response.send_message(embed=error_embed("Ungültige Channel ID."), ephemeral=True)
        ch = interaction.guild.get_channel(cid)
        if not ch:
            return await interaction.response.send_message(embed=error_embed(f"Channel `{cid}` nicht gefunden."), ephemeral=True)
        maint_channel_id = cid
        save_data()
        embed = discord.Embed(
            title="✅  Maintenance Channel gesetzt",
            description=f"🔧  Maintenance-Warnungen werden ab jetzt in <#{cid}> gepostet.",
            color=0x00FF98,
        )
        embed.set_footer(text="WoW Bot  ·  Setup erfolgreich")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="overview", description="Aktuelle WoW Bot Konfiguration anzeigen")
    async def overview(self, interaction: discord.Interaction):
        if not is_admin(interaction):
            return await interaction.response.send_message(embed=error_embed("Nur für Admins."), ephemeral=True)

        def channel_line(cid):
            return f"✅  <#{cid}>" if cid else "⚠️  *Nicht gesetzt*"

        blizzard_status = "✅ Konfiguriert" if (BLIZZARD_CLIENT_ID and BLIZZARD_CLIENT_SECRET) else "❌ Fehlt"
        wcl_status      = "✅ Konfiguriert" if (WCL_CLIENT_ID and WCL_CLIENT_SECRET)           else "❌ Fehlt"

        embed = discord.Embed(
            title="⚙️  WoW Bot  —  Konfigurationsübersicht",
            description=(
                "Aktueller Setup-Status aller Channels, APIs und News-Quellen.\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ),
            color=0x00FF98,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_author(name="🛠️  Admin Control Panel")
        embed.add_field(name="📰  News Channel",        value=channel_line(news_channel_id),  inline=True)
        embed.add_field(name="🔄  Reset Channel",       value=channel_line(reset_channel_id), inline=True)
        embed.add_field(name="🔧  Maintenance Channel", value=channel_line(maint_channel_id), inline=True)
        embed.add_field(
            name="🔑  API-Status",
            value=(
                f"🟦  Blizzard API: **{blizzard_status}**\n"
                f"🟥  Warcraft Logs: **{wcl_status}**"
            ),
            inline=False,
        )
        embed.add_field(
            name="📡  Aktive News-Quellen",
            value=(
                "🔵  **Blizzard Official**  —  Patch Notes & offizielle News\n"
                "📰  **Wowhead**  —  Datamines & Hotfixes\n"
                "🔷  **Bluetracker**  —  Blue Posts *(EU-gefiltert)*\n"
                "*Nur Patch- & Content-relevante Artikel werden gepostet.*"
            ),
            inline=False,
        )
        embed.set_footer(text="WoW Bot  ·  Setup Overview  ·  Nur für Admins sichtbar")
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ─────────────────────────────────────────
#  BACKGROUND TASKS
# ─────────────────────────────────────────

@tasks.loop(hours=1)
async def check_wow_news():
    global seen_news
    if not news_channel_id:
        return
    channel = bot.get_channel(news_channel_id)
    if not channel:
        return

    blizzard_articles, wowhead_articles, bluetracker_articles = await asyncio.gather(
        fetch_news_blizzard(),
        fetch_news_wowhead(),
        fetch_news_bluetracker(),
    )

    for article in blizzard_articles + wowhead_articles + bluetracker_articles:
        uid = article.get("guid", article.get("url", ""))
        if not uid or uid in seen_news:
            continue

        now_ts = int(datetime.now(timezone.utc).timestamp())
        embed = discord.Embed(
            title=article["title"],
            url=article["url"],
            color=article.get("color", 0x0070DD),
            description=f"{article['icon']}  **{article['source']}**  ·  <t:{now_ts}:R>",
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_author(name=f"📢  WoW News Alert  —  {article['source']}")
        if article.get("thumb"):
            embed.set_thumbnail(url=article["thumb"])
        embed.set_footer(text="WoW Bot  ·  Automatischer News-Post  ·  Patch- & Content-Updates")

        try:
            await channel.send(embed=embed)
            seen_news.append(uid)
            if len(seen_news) > 200:
                seen_news = seen_news[-200:]
            save_data()
            print(f"[WOW] News: {article['title']}")
        except Exception as e:
            print(f"[ERROR] News-Post fehlgeschlagen: {e}")


@tasks.loop(minutes=30)
async def weekly_reset_reminder():
    if not reset_channel_id:
        return
    now = datetime.now(timezone.utc)
    if now.weekday() != 1:
        return
    if now.hour == 4 and now.minute < 30:
        channel = bot.get_channel(reset_channel_id)
        if not channel:
            return
        eu_ts = int(now.replace(hour=7,  minute=0, second=0, microsecond=0).timestamp())
        us_ts = int(now.replace(hour=15, minute=0, second=0, microsecond=0).timestamp())
        embed = discord.Embed(
            title="⏰  Weekly Reset  —  Noch 3 Stunden!",
            color=0xFFD700,
            description=(
                "🔔  **Der Weekly Reset steht kurz bevor!**\n"
                "Zeit, noch schnell die wichtigsten Wochenziele abzuhaken.\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ),
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_author(name="🔄  Weekly Reset Reminder")
        embed.add_field(
            name="🇪🇺  EU Reset",
            value=f"🕐 <t:{eu_ts}:t>\n⏳ <t:{eu_ts}:R>",
            inline=True,
        )
        embed.add_field(
            name="🇺🇸  US Reset",
            value=f"🕐 <t:{us_ts}:t>\n⏳ <t:{us_ts}:R>",
            inline=True,
        )
        embed.add_field(name="​", value="​", inline=False)
        embed.add_field(
            name="📋  Endgame-Checkliste",
            value=(
                "🏆  Great Vault öffnen *(M+, Raid, PvP)*\n"
                "⚔️  Wöchentliche Raidbosse\n"
                "🗺️  World Quests & Weekly Quests\n"
                "🎯  PvP Conquest Cap\n"
                "🕳️  Delves & World Bosse"
            ),
            inline=True,
        )
        embed.add_field(
            name="💰  Gold & Gear",
            value=(
                "💎  Catchup-Gear von Weekly Events\n"
                "🪙  Professions Weekly Crafts\n"
                "📦  Wöchentliche Questbelohnungen\n"
                "🎁  Trading Post Bounty\n"
                "🏛️  Reputationen auffüllen"
            ),
            inline=True,
        )
        embed.set_footer(text="WoW Bot  ·  Weekly Reset Reminder  ·  Viel Erfolg bei den Wochenzielen!")
        await channel.send(embed=embed)


@tasks.loop(hours=4)
async def check_maintenance():
    if not maint_channel_id:
        return
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://us.battle.net/support/api/service_status",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                if r.status != 200:
                    return
                data = await r.json()

        wow_status = None
        for service in data.get("services", []):
            if "wow" in service.get("slug", "").lower() or "world-of-warcraft" in service.get("name", "").lower():
                wow_status = service
                break
        if not wow_status:
            return

        status = wow_status.get("status", "")
        if status not in ("maintenance", "partial_outage", "major_outage"):
            return

        channel = bot.get_channel(maint_channel_id)
        if not channel:
            return

        status_map = {
            "maintenance":    ("🔧  Scheduled Maintenance", 0xFFD700, "🟡 Geplant",     "Der Dienst wird planmäßig gewartet. Logins können zeitweise fehlschlagen."),
            "partial_outage": ("⚠️  Partial Outage",        0xFF8000, "🟠 Eingeschränkt", "Teilweise Störung — einige Funktionen sind aktuell nicht verfügbar."),
            "major_outage":   ("🔴  Major Outage",          0xC41E3A, "🔴 Kritisch",    "Schwerwiegende Störung — der Dienst ist aktuell nicht erreichbar."),
        }
        title, color, severity, info = status_map.get(
            status,
            ("⚠️  Service Issue", 0xFF8000, "🟠 Warnung", "Unerwarteter Service-Status gemeldet."),
        )
        embed = discord.Embed(
            title=f"{title}  —  World of Warcraft",
            color=color,
            description=(
                f"{info}\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            ),
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_author(name="📡  Blizzard Service Status")
        embed.add_field(name="📊  Status",    value=status.replace("_", " ").title(), inline=True)
        embed.add_field(name="⚡  Severity",  value=severity,                         inline=True)
        embed.add_field(name="🎮  Service",   value="World of Warcraft",              inline=True)
        embed.add_field(
            name="🔗  Weitere Infos",
            value="[📄 Offizielle Status-Seite](https://us.battle.net/support/en/article/service-status)",
            inline=False,
        )
        embed.set_footer(text="WoW Bot  ·  Blizzard Service Status  ·  Überprüfung alle 4h")
        await channel.send(embed=embed)
    except Exception as e:
        print(f"[ERROR] Maintenance check: {e}")


# ─────────────────────────────────────────
#  BOT EVENTS
# ─────────────────────────────────────────

@bot.command(name="sync")
@commands.is_owner()
async def sync_commands(ctx):
    bot.tree.clear_commands(guild=None)
    bot.tree.add_command(WowGroup())
    bot.tree.add_command(WowSetupGroup())
    synced = await bot.tree.sync()
    await ctx.send(f"✅ {len(synced)} Slash Commands gesynct!", delete_after=5)
    print(f"[INFO] Manuell gesynct von {ctx.author}: {len(synced)} Commands")


@bot.event
async def on_ready():
    bot.tree.clear_commands(guild=None)
    bot.tree.add_command(WowGroup())
    bot.tree.add_command(WowSetupGroup())
    await bot.tree.sync()

    check_wow_news.start()
    weekly_reset_reminder.start()
    check_maintenance.start()

    print(f"[INFO] Logged in as       : {bot.user} (ID: {bot.user.id})")
    print(f"[INFO] Blizzard API       : {'Configured ✓' if BLIZZARD_CLIENT_ID else 'NOT SET ✗'}")
    print(f"[INFO] Warcraft Logs API  : {'Configured ✓' if WCL_CLIENT_ID else 'NOT SET ✗'}")
    print(f"[INFO] Commands           : /wow check · /wow compare · /wowsetup")
    print(f"[INFO] News-Quellen       : Blizzard Official + Wowhead + Bluetracker (EU)")
    print(f"[INFO] News channel       : {news_channel_id  or 'Nicht gesetzt'}")
    print(f"[INFO] Reset channel      : {reset_channel_id or 'Nicht gesetzt'}")
    print(f"[INFO] Maint channel      : {maint_channel_id or 'Nicht gesetzt'}")
    print(f"[INFO] Background tasks   : Gestartet")
    print(f"[INFO] Slash commands     : Synced")


# ─────────────────────────────────────────
#  START
# ─────────────────────────────────────────
if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise RuntimeError("[ERROR] Kein DISCORD_TOKEN in der .env!")
    if not BLIZZARD_CLIENT_ID or not BLIZZARD_CLIENT_SECRET:
        print("[WARNING] Keine Blizzard Credentials — Profil/Gear/Stats/PvP/Achievements fehlen!")
    bot.run(DISCORD_TOKEN)
