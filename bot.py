import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiohttp
import asyncio
import base64
import html
import io
import json
import os
import re
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from dotenv import load_dotenv

import gear_render
import render_util
import mplus_render
import wcl_render

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
    (636, "✅ Ready for **Mythic Raid**"),
    (619, "✅ Ready for **Heroic Raid** & high M+"),
    (606, "✅ Ready for **Normal Raid** & M+ 10+"),
    (593, "✅ Ready for **M+ 5+** & LFR"),
    (580, "⚠️ Ready for **M+ 2-4** & LFR"),
    (0,   "🔰 Still gearing up — M0 & World Quests recommended"),
]

# ─────────────────────────────────────────
#  DATA PERSISTENCE
# ─────────────────────────────────────────
def load_data() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {
        "news_channel":  None,
        "reset_channel": None,
        "maint_channel": None,
        "seen_news":     [],
        "news_schema":   0,
        "characters":    {},
    }

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump({
            "news_channel":  news_channel_id,
            "reset_channel": reset_channel_id,
            "maint_channel": maint_channel_id,
            "seen_news":     seen_news,
            "news_schema":   news_schema,
            "characters":    character_history,
        }, f, indent=2)

_data            = load_data()
news_channel_id  = _data.get("news_channel",  None)
reset_channel_id = _data.get("reset_channel", None)
maint_channel_id = _data.get("maint_channel", None)
seen_news: list  = _data.get("seen_news",     [])
news_schema: int = _data.get("news_schema",   0)
character_history: dict = _data.get("characters", {})

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
        title="❌  Error",
        description=msg,
        color=0xC41E3A,
    )
    embed.set_footer(text="WoW Bot  ·  Error")
    return embed

def is_admin(interaction: discord.Interaction) -> bool:
    return interaction.user.guild_permissions.administrator

RAID_DIFFICULTIES = (
    ("normal_bosses_killed", "Normal"),
    ("heroic_bosses_killed", "Heroic"),
    ("mythic_bosses_killed", "Mythic"),
)


def mplus_ranks(rio: dict) -> dict:
    """World, region and realm placing; Raider.IO writes 0 for unranked."""
    overall = ((rio or {}).get("mythic_plus_ranks") or {}).get("overall") or {}
    return {key: (overall.get(key) or 0) or None for key in ("world", "region", "realm")}


def stat_percent(value) -> str:
    """The percentage alone: the rating beside it is often reported as zero."""
    if isinstance(value, dict):
        return f"{value.get('value', value.get('rating_bonus_value', 0)):.1f}%"
    return f"{value:.1f}%" if isinstance(value, (int, float)) else str(value)


def raid_cell(rio: dict):
    """(raid name, progress) — the name labels the cell so the value stays short."""
    best_score, best = -1, ("Raid", "—")
    for raid_name, progress in ((rio or {}).get("raid_progression") or {}).items():
        total = progress.get("total_bosses") or 0
        if not total:
            continue
        for weight, (key, label) in enumerate(RAID_DIFFICULTIES):
            killed = progress.get(key) or 0
            if not killed:
                continue
            score = weight * 1000 + killed
            if score > best_score:
                best_score = score
                best = (raid_name.replace(chr(45), chr(32)).title(),
                        f"{killed}/{total} {label}")
    return best


def raid_status(rio: dict) -> str:
    """Furthest the character has got in any current raid, hardest mode first."""
    best_score, best_text = -1, ""
    for raid_name, progress in ((rio or {}).get("raid_progression") or {}).items():
        total = progress.get("total_bosses") or 0
        if not total:
            continue
        for weight, (key, label) in enumerate(RAID_DIFFICULTIES):
            killed = progress.get(key) or 0
            if not killed:
                continue
            score = weight * 1000 + killed
            if score > best_score:
                best_score = score
                best_text  = (f"**{killed}/{total}** {label} — "
                              f"{raid_name.replace(chr(45), chr(32)).title()}")
    return best_text


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
                raise ValueError(f"Blizzard auth failed ({r.status})")
            data = await r.json()
            _blizzard_token        = data["access_token"]
            _blizzard_token_expiry = now + data["expires_in"]
            return _blizzard_token

async def blizzard_get(path: str, region: str = "eu", namespace: str = "") -> dict:
    token = await get_blizzard_token(region)
    url   = f"https://{region}.api.blizzard.com{path}"
    params = {
        "namespace": namespace or f"profile-{region}",
        "locale": "en_GB" if region == "eu" else "en_US",
    }
    async with aiohttp.ClientSession() as s:
        async with s.get(url, params=params, headers={"Authorization": f"Bearer {token}"}) as r:
            if r.status == 404:
                raise ValueError("Character not found. Check the name and realm.")
            if r.status != 200:
                raise ValueError(f"Blizzard API error ({r.status})")
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

async def get_character_media(realm: str, name: str, region: str) -> dict:
    return await blizzard_get(f"/profile/wow/character/{realm_slug(realm)}/{name.lower()}/character-media", region)

# ─────────────────────────────────────────
#  GEAR ASSETS — icons, realm list, enchant wording
# ─────────────────────────────────────────
ICON_CACHE_SIZE = 400
REALM_CACHE_TTL = 6 * 3600     # realm lists barely move; refresh a few times a day
ASSET_TIMEOUT   = aiohttp.ClientTimeout(total=12)
PORTRAIT_MAX    = 2_000_000    # a full-body render is well under 1 MB

_icon_cache: dict  = {}
_realm_cache: dict = {}

SECONDARY_STATS = {
    "CRIT_RATING":    "Crit",
    "HASTE_RATING":   "Haste",
    "MASTERY_RATING": "Mastery",
    "VERSATILITY":    "Vers",
}

# One region's CDN occasionally returns 403 for a file the others serve.
_ICON_REGION_RE = re.compile(r"/(eu|us|kr|tw)/icons/")

# "|A:Professions-ChatIcon-Quality-12-Tier2:20:20|a" is a WoW texture atlas tag
# the API leaves inside the display string.
_ATLAS_RE   = re.compile(r"\|A:[^|]*\|a")
_ENCHANT_RE = re.compile(r"^Enchanted:\s*(?:Enchant\s+[\w\- ]+?\s+-\s+)?")


def enchant_label(display_string: str) -> str:
    """Strips the atlas tag and the "Enchanted: Enchant Ring - " boilerplate."""
    return _ENCHANT_RE.sub("", _ATLAS_RE.sub("", display_string or "")).strip()


def plain_display(display_string: str) -> str:
    return _ATLAS_RE.sub("", display_string or "").strip()


async def download_bytes(url: str, limit: int = PORTRAIT_MAX):
    """Whole asset or nothing — a partial image is worse than no image."""
    try:
        async with aiohttp.ClientSession(timeout=ASSET_TIMEOUT) as session:
            async with session.get(url) as response:
                if response.status != 200:
                    return None
                if (response.content_length or 0) > limit:
                    return None
                data = await response.read()
                return data if len(data) <= limit else None
    except Exception:
        return None


def icon_url_variants(url: str) -> list:
    """The same icon on every regional host, primary first."""
    match = _ICON_REGION_RE.search(url or "")
    if not match:
        return [url] if url else []
    variants = [url]
    for other in ("us", "eu", "kr"):
        if other != match.group(1):
            variants.append(url[:match.start(1)] + other + url[match.end(1):])
    return variants


STAT_SHORT = {
    "Strength": "Str", "Agility": "Agi", "Intellect": "Int", "Stamina": "Sta",
    "Critical Strike": "Crit", "Versatility": "Vers", "Haste": "Haste", "Mastery": "Mastery",
}


def item_stat_line(item: dict) -> str:
    """Every stat the tooltip shows, minus the ones flagged as off-spec."""
    parts = []
    for stat in item.get("stats", []):
        if stat.get("is_negated"):
            continue
        text = ((stat.get("display") or {}).get("display_string") or "").strip()
        if not text:
            continue
        for long_name, short in STAT_SHORT.items():
            if text.endswith(long_name):
                text = text[: -len(long_name)] + short
                break
        parts.append(text)
    return " · ".join(parts)


def secondary_stat_line(item: dict) -> str:
    """'+79 Haste · +112 Vers' — off-spec stats are flagged and left out."""
    found = []
    for stat in item.get("stats", []):
        if stat.get("is_negated"):
            continue
        short = SECONDARY_STATS.get((stat.get("type") or {}).get("type", ""))
        if short:
            found.append((stat.get("value", 0) or 0, short))
    # Two fit the column; a necklace can carry four and would overflow.
    found.sort(key=lambda pair: pair[0], reverse=True)
    return " · ".join(f"+{value} {name}" for value, name in found[:2])


async def get_item_icon(item_id: int, region: str):
    """Icon bytes for an item, cached — the media lookup costs one call each."""
    if not item_id:
        return None
    if item_id in _icon_cache:
        return _icon_cache[item_id]
    icon = None
    try:
        media = await blizzard_get(f"/data/wow/media/item/{item_id}", region, f"static-{region}")
        for asset in media.get("assets", []):
            if asset.get("key") != "icon":
                continue
            for candidate in icon_url_variants(asset["value"]):
                icon = await download_bytes(candidate)
                if icon:
                    break
            break
    except Exception:
        icon = None
    _icon_cache[item_id] = icon
    if len(_icon_cache) > ICON_CACHE_SIZE:
        _icon_cache.pop(next(iter(_icon_cache)))
    return icon


async def get_realms(region: str) -> list:
    """(name, slug) for every realm in the region, refreshed a few times a day."""
    now    = datetime.now(timezone.utc).timestamp()
    cached = _realm_cache.get(region)
    if cached and now < cached[0]:
        return cached[1]
    try:
        data   = await blizzard_get("/data/wow/realm/index", region, f"dynamic-{region}")
        realms = sorted(
            (r["name"], r["slug"]) for r in data.get("realms", [])
            if isinstance(r.get("name"), str) and r.get("slug")
        )
    except Exception as exc:
        print(f"[WARN] Realm index failed for {region}: {exc}")
        return cached[1] if cached else []
    _realm_cache[region] = (now + REALM_CACHE_TTL, realms)
    return realms


CHARACTER_HISTORY_MAX = 50      # per guild, most recently looked up first


def remember_character(guild_id, name: str, realm: str, region: str, realm_name: str = ""):
    """Record a lookup so the next person can pick the name from a list."""
    if not guild_id or not name:
        return
    key   = str(guild_id)
    entry = {"name": name, "realm": realm, "region": region, "realm_name": realm_name or realm,
             "last_used": datetime.now(timezone.utc).date().isoformat()}
    ident = (name.lower(), realm.lower(), region)
    kept  = [
        e for e in character_history.get(key, [])
        if (e.get("name", "").lower(), e.get("realm", "").lower(), e.get("region")) != ident
    ]
    kept.insert(0, entry)
    character_history[key] = kept[:CHARACTER_HISTORY_MAX]
    save_data()


def recall_character(guild_id, name: str):
    """The most recent realm this guild used for that character name."""
    for entry in character_history.get(str(guild_id), []):
        if entry.get("name", "").lower() == (name or "").lower():
            return entry
    return None


async def character_autocomplete(interaction: discord.Interaction, current: str) -> list:
    """Characters this server has looked up before, most recent first."""
    entries = character_history.get(str(interaction.guild_id), [])
    needle  = current.strip().lower()
    if needle:
        entries = [e for e in entries if needle in e.get("name", "").lower()]
    return [
        app_commands.Choice(
            name=f"{e['name']} — {e.get('realm_name') or e['realm']} ({(e.get('region') or 'eu').upper()})"[:100],
            value=e["name"],
        )
        for e in entries[:25]
    ]


async def realm_autocomplete(interaction: discord.Interaction, current: str) -> list:
    """Realm suggestions for whichever region is selected in the same command."""
    region = getattr(interaction.namespace, "region", None) or "eu"
    realms = await get_realms(region if region in ("eu", "us") else "eu")
    needle = current.strip().lower()
    if needle:
        realms = [r for r in realms if needle in r[0].lower()]
        realms.sort(key=lambda r: (not r[0].lower().startswith(needle), r[0]))
    return [app_commands.Choice(name=name, value=slug) for name, slug in realms[:25]]


async def build_gear_slots(equipment: dict, region: str):
    """Slot data for the sheet renderer plus the enchant and gem summary."""
    items = {item["slot"]["type"]: item for item in equipment.get("equipped_items", [])}

    # Every icon in one round trip rather than sixteen sequential lookups.
    wanted = []
    for item in items.values():
        wanted.append((item.get("item") or {}).get("id"))
        for socket in item.get("sockets", []):
            wanted.append((socket.get("item") or {}).get("id"))
    unique  = [i for i in dict.fromkeys(wanted) if i]
    fetched = await asyncio.gather(*(get_item_icon(i, region) for i in unique))
    icons   = dict(zip(unique, fetched))

    slots, enchant_lines, gem_lines = {}, [], []
    total_ilvl = count = 0

    for slot_type in SLOT_ORDER:
        item  = items.get(slot_type)
        label = slot_type.replace("_", " ").title()
        if not item:
            slots[slot_type] = {"label": label}
            continue

        label    = (item.get("slot") or {}).get("name") or label
        ilvl     = (item.get("level") or {}).get("value", 0)
        enchants = [enchant_label(e.get("display_string", "")) for e in item.get("enchantments", [])]
        enchants = [e for e in enchants if e]

        slots[slot_type] = {
            "label":    label,
            "name":     item.get("name", ""),
            "ilvl":     ilvl,
            "quality":  (item.get("quality") or {}).get("type", "COMMON"),
            "icon":     icons.get((item.get("item") or {}).get("id")),
            "enchants": enchants,
            "gems":     [
                icons[(socket.get("item") or {}).get("id")]
                for socket in item.get("sockets", [])
                if icons.get((socket.get("item") or {}).get("id"))
            ],
        }

        if ilvl:
            total_ilvl += ilvl
            count      += 1
        for text in enchants:
            enchant_lines.append(f"✨ **{label}** — {text}")
        for socket in item.get("sockets", []):
            bonus = plain_display(socket.get("display_string", ""))
            if bonus:
                gem_lines.append(f"💎 **{label}** — {bonus}")

    avg_ilvl = round(total_ilvl / count) if count else 0
    return slots, enchant_lines, gem_lines, avg_ilvl

# ─────────────────────────────────────────
#  RAIDERIO API
# ─────────────────────────────────────────
RAIDERIO_TIMEOUT = aiohttp.ClientTimeout(total=15)


async def get_raiderio(realm: str, name: str, region: str) -> dict:
    """Raider.IO rate limits and occasionally times out, so give it a second go."""
    params = {
        "region": region, "realm": realm, "name": name,
        "fields": ("mythic_plus_scores_by_season:current,mythic_plus_ranks,"
                   "raid_progression,mythic_plus_best_runs,gear"),
    }
    last_error = None
    for attempt in range(2):
        try:
            async with aiohttp.ClientSession(timeout=RAIDERIO_TIMEOUT) as session:
                async with session.get("https://raider.io/api/v1/characters/profile",
                                       params=params) as response:
                    if response.status == 400:
                        raise ValueError("Character not found on Raider.IO.")
                    if response.status == 429:
                        last_error = ValueError("Raider.IO rate limit (429)")
                    elif response.status != 200:
                        last_error = ValueError(f"Raider.IO error ({response.status})")
                    else:
                        return await response.json()
        except asyncio.TimeoutError:
            last_error = ValueError("Raider.IO timed out")
        if attempt == 0:
            await asyncio.sleep(1.5)
    raise last_error or ValueError("Raider.IO unavailable")

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
                raise ValueError(f"Warcraft Logs auth failed ({r.status})")
            data = await r.json()
            _wcl_token        = data["access_token"]
            _wcl_token_expiry = now + data["expires_in"]
            return _wcl_token

async def get_wcl_character(realm: str, name: str, region: str) -> dict:
    """Best parses in the current raid zone, plus the profile link."""
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
                raise ValueError(f"Warcraft Logs API error ({r.status})")
            data = await r.json()
            char = (data.get("data") or {}).get("characterData", {}).get("character")
            if not char:
                raise ValueError("Character not found on Warcraft Logs.")
            return char

def wcl_parse_emoji(pct: float) -> str:
    if pct >= 99: return "🟠"   # Artifact / Legendary
    if pct >= 95: return "🟣"   # Epic
    if pct >= 75: return "🔵"   # Rare
    if pct >= 50: return "🟢"   # Uncommon
    if pct >= 25: return "⚪"   # Common
    return "⬜"                  # Poor


WCL_ENDPOINT   = "https://www.warcraftlogs.com/api/v2/client"
WCL_METRICS    = ("dps", "hps", "playerspeed")   # Damage, Healing, Speed
MPLUS_ZONE_TTL = 12 * 3600

_mplus_zone: dict = {}


async def wcl_query(query: str, variables: dict) -> dict:
    token = await get_wcl_token()
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
        async with session.post(WCL_ENDPOINT,
                                headers={"Authorization": f"Bearer {token}"},
                                json={"query": query, "variables": variables}) as response:
            if response.status != 200:
                raise ValueError(f"Warcraft Logs API error ({response.status})")
            payload = await response.json()
    if payload.get("errors"):
        raise ValueError(payload["errors"][0].get("message", "Warcraft Logs rejected the query"))
    return payload.get("data") or {}


async def current_mplus_zone() -> int:
    """Newest "Mythic+ Season" zone, so a new season needs no code change."""
    now = datetime.now(timezone.utc).timestamp()
    if _mplus_zone.get("expires", 0) > now:
        return _mplus_zone["id"]
    data  = await wcl_query("query { worldData { zones { id name } } }", {})
    zones = (data.get("worldData") or {}).get("zones") or []
    seasons = [z for z in zones if z.get("name", "").startswith("Mythic+ Season")]
    if not seasons:
        raise ValueError("No Mythic+ zone found on Warcraft Logs")
    newest = max(seasons, key=lambda z: z["id"])
    _mplus_zone.update(id=newest["id"], expires=now + MPLUS_ZONE_TTL)
    return newest["id"]


async def dungeon_rankings(realm: str, name: str, region: str):
    """(summary, rows) for the Mythic+ page: one request carries score and damage."""
    zone  = await current_mplus_zone()
    query = """
    query($name:String!,$server:String!,$region:String!,$zone:Int!,$metric:CharacterPageRankingMetricType!){
      characterData { character(name:$name, serverSlug:$server, serverRegion:$region) {
        zoneRankings(zoneID:$zone, metric:$metric)
      }}
    }"""
    data = await wcl_query(query, {
        "name": name.capitalize(), "server": realm_slug(realm),
        "region": region.upper(), "zone": zone, "metric": "points_and_damage",
    })
    character = (data.get("characterData") or {}).get("character") or {}
    blob = character.get("zoneRankings")
    if isinstance(blob, str):
        try:
            blob = json.loads(blob)
        except ValueError:
            blob = {}
    blob = blob or {}

    # The damage columns live beside the score ones, keyed by encounter id.
    throughput = blob.get("throughputRankings") or {}
    rows = []
    for entry in blob.get("rankings") or []:
        encounter = entry.get("encounter") or {}
        damage    = throughput.get(str(encounter.get("id"))) or {}
        stars     = entry.get("allStars") or {}
        rows.append({
            "id":      encounter.get("id"),
            "dungeon": encounter.get("name", "?"),
            "level":   wcl_number(damage.get("best_level")),
            "runs":    wcl_number(entry.get("totalKills")) or 0,
            "points":  wcl_number(stars.get("points")),
            "rank":    wcl_number(stars.get("rank")),
            "dps":     wcl_number(damage.get("best_per_second_amount")),
            "best":    wcl_number(damage.get("best_historical_percentile")),
            "median":  wcl_number(damage.get("median_historical_percentile")),
        })
    rows.sort(key=lambda row: row["dungeon"])

    overall = (blob.get("allStars") or [{}])[0]
    summary = {
        "score":      wcl_number(overall.get("points")),
        "spec_rank":  wcl_number(overall.get("rank")),
        "best_avg":   wcl_number(blob.get("bestPerformanceAverage")),
        "median_avg": wcl_number(blob.get("medianPerformanceAverage")),
        "runs":       sum(row["runs"] for row in rows),
    }
    return summary, rows


DUNGEON_RUNS_SHOWN = 12


async def last_dungeon_runs(realm: str, name: str, region: str, dungeons: list):
    """(dungeon, summary, runs) for whichever dungeon was played most recently.

    zoneRankings only carries a character's best run per dungeon; the single
    runs, with their key level and real duration, live under encounterRankings.
    """
    query = """
    query($name:String!,$server:String!,$region:String!,$enc:Int!){
      characterData { character(name:$name, serverSlug:$server, serverRegion:$region) {
        encounterRankings(encounterID:$enc, metric: dps)
      }}
    }"""
    base = {"name": name.capitalize(), "server": realm_slug(realm), "region": region.upper()}

    async def one(dungeon: dict):
        if not dungeon.get("id"):
            return dungeon, {}
        try:
            data = await wcl_query(query, dict(base, enc=dungeon["id"]))
        except Exception as exc:
            print(f"[WARN] Runs for {dungeon.get('dungeon')} failed: {exc}")
            return dungeon, {}
        character = (data.get("characterData") or {}).get("character") or {}
        blob = character.get("encounterRankings")
        if isinstance(blob, str):
            try:
                blob = json.loads(blob)
            except ValueError:
                blob = {}
        return dungeon, blob or {}

    newest = None
    for dungeon, blob in await asyncio.gather(*(one(d) for d in dungeons)):
        ranks = blob.get("ranks") or []
        if not ranks:
            continue
        latest = max(wcl_number(rank.get("startTime")) or 0 for rank in ranks)
        if newest is None or latest > newest[0]:
            newest = (latest, dungeon, blob)
    if newest is None:
        return None

    _, dungeon, blob = newest
    runs = sorted(
        (
            {
                "level":    wcl_number(rank.get("bracketData")),
                "duration": wcl_number(rank.get("duration")),
                "dps":      wcl_number(rank.get("amount")),
                "percent":  wcl_number(rank.get("historicalPercent")),
                "started":  wcl_number(rank.get("startTime")),
            }
            for rank in blob.get("ranks") or []
        ),
        key=lambda run: run["started"] or 0,
        reverse=True,
    )

    durations = [run["duration"] for run in runs if run["duration"]]
    summary = {
        # fastestKill is a negative placeholder for keystones, so take the
        # quickest run we actually have.
        "fastest_ms": min(durations) if durations else None,
        "median":     wcl_number(blob.get("medianPerformance")),
        "average":    wcl_number(blob.get("averagePerformance")),
        "kills":      wcl_number(blob.get("totalKills")) or len(runs),
        "best_dps":   wcl_number(blob.get("bestAmount")),
        "points":     wcl_number(dungeon.get("points")),
        "rank":       wcl_number(dungeon.get("rank")),
    }
    return dungeon.get("dungeon", "?"), summary, runs[:DUNGEON_RUNS_SHOWN]


ART_CACHE_SIZE = 60
_art_cache: dict = {}


async def get_artwork(url: str):
    """Dungeon splash art, cached — each one is a third of a megabyte."""
    if not url:
        return None
    if url not in _art_cache:
        _art_cache[url] = await download_bytes(url)
        if len(_art_cache) > ART_CACHE_SIZE:
            _art_cache.pop(next(iter(_art_cache)))
    return _art_cache[url]


async def build_mplus_runs(rio: dict) -> list:
    """Best run per dungeon with its artwork, ready for the panel."""
    runs = (rio or {}).get("mythic_plus_best_runs", [])[:8]
    art  = await asyncio.gather(*(get_artwork(r.get("background_image_url", "")) for r in runs))
    return [
        {
            "short_name": run.get("short_name", ""),
            "dungeon":    run.get("dungeon", ""),
            "level":      run.get("mythic_level", 0),
            "score":      run.get("score", 0),
            "upgrades":   run.get("num_keystone_upgrades", 0),
            "art":        image,
        }
        for run, image in zip(runs, art)
    ]


def read_zone_rankings(wcl: dict) -> dict:
    """zoneRankings comes back as either a JSON string or a dict."""
    raw = (wcl or {}).get("zoneRankings")
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except ValueError:
            return {}
    return raw or {}


def wcl_number(value):
    """Warcraft Logs writes "-" where a character is unranked."""
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def wcl_table_data(zone: dict):
    """(summary, rows) shaped the way the Warcraft Logs character page reads."""
    rows = []
    for entry in zone.get("rankings") or []:
        stars = entry.get("allStars") or {}
        rows.append({
            "boss":       (entry.get("encounter") or {}).get("name", "?"),
            "best":       wcl_number(entry.get("rankPercent")),
            "median":     wcl_number(entry.get("medianPercent")),
            "dps":        wcl_number(entry.get("bestAmount")) or 0,
            "kills":      wcl_number(entry.get("totalKills")) or 0,
            "fastest_ms": wcl_number(entry.get("fastestKill")),
            "points":     wcl_number(stars.get("points")),
            "rank":       wcl_number(stars.get("rank")),
        })
    summary = {
        "best":   zone.get("bestPerformanceAverage"),
        "median": zone.get("medianPerformanceAverage"),
        "kills":  sum(r["kills"] for r in rows),
        "points": sum(r["points"] or 0 for r in rows),
        "rank":   min((r["rank"] for r in rows if r["rank"]), default=0) if rows else 0,
    }
    return summary, rows


def analyse_logs(summary: dict, rows: list) -> list:
    """(lead, detail, colour) lines read off the parses, drawn onto the table."""
    killed = [r for r in rows if (r["kills"] or 0) > 0 and r["best"] is not None]
    if not killed:
        return []

    green, red, amber, grey = (30, 200, 60), (230, 80, 80), (255, 180, 60), (150, 150, 150)
    best    = max(killed, key=lambda r: r["best"])
    worst   = min(killed, key=lambda r: r["best"])
    missing = [r["boss"] for r in rows if not (r["kills"] or 0)]
    notes   = [("Strongest", f"{best['boss']}  ({best['best']:.0f})", green)]

    if worst["boss"] != best["boss"]:
        notes.append(("Weakest",
                      f"{worst['boss']}  ({worst['best']:.0f})  —  most room to gain",
                      red))

    # A wide best-to-median gap means single good pulls, not a reliable floor.
    spread = [r["best"] - r["median"] for r in killed if r["median"] is not None]
    if spread:
        average = sum(spread) / len(spread)
        if average >= 20:
            notes.append(("Inconsistent",
                          f"best runs sit {average:.0f} points above the median", amber))
        elif average <= 8:
            notes.append(("Consistent",
                          f"only {average:.0f} points between best and median", green))
    if missing and len(notes) < 3:
        notes.append(("Not killed", ", ".join(missing[:4]), grey))
    return notes





# ─────────────────────────────────────────
#  NEWS SOURCES
#  1. worldofwarcraft.blizzard.com  — official news & patch notes
#  2. wowhead.com                   — datamines, hotfixes, guides
#  3. bluetracker.gg                — blue posts (EU only)
#
#  All three mirror each other, so every article is reduced to a set of
#  fingerprints and only the first source that carries it gets posted.
# ─────────────────────────────────────────
BLIZZARD_NEWS_URL = "https://worldofwarcraft.blizzard.com/en-gb/news"
WOWHEAD_RSS_URL   = "https://www.wowhead.com/news/rss/all"
BLUETRACKER_RSS   = "https://www.bluetracker.gg/rss/wow/"

# Wowhead publishes dozens of items a day, so it is the only feed we filter.
NEWS_KEYWORDS = [
    "patch", "hotfix", "update", "maintenance", "notes",
    "season", "fix", "change", "nerf", "buff", "class",
]

NEWS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) WoWDiscordBot/2.0",
    "Accept-Language": "en-GB,en;q=0.9",
}
NEWS_TIMEOUT       = aiohttp.ClientTimeout(total=15)
NEWS_MAX_AGE_DAYS  = 3        # anything older is treated as already covered
NEWS_MAX_PER_RUN   = 4        # keeps a single cycle from flooding the channel
NEWS_CACHE_SIZE    = 600      # fingerprints kept in wow_bot_data.json
NEWS_SCHEMA        = 2        # bump to silently re-seed the dedupe cache
NEWS_SUMMARY_CHARS = 280
NEWS_PAGE_BYTES    = 262144   # only the <head> is needed for preview images
NEWS_PREVIEW_CACHE = 200

ICON_WOW     = ("https://assets-bwa.worldofwarcraft.blizzard.com/static/"
                "wow-icon-32x32.1a38d7c1c3d8df560d53f5c2ad5442c0401edf83.png")
ICON_WOWHEAD = "https://wow.zamimg.com/apple-touch-icon.png"

NEWS_SOURCES = {
    "blizzard":    {"label": "Blizzard Official", "color": 0x00AEFF, "icon": ICON_WOW},
    "wowhead":     {"label": "Wowhead",           "color": 0xF0A020, "icon": ICON_WOWHEAD},
    "bluetracker": {"label": "Blue Post · EU",     "color": 0x3B82F6, "icon": ICON_WOW},
}

RSS_MEDIA_CONTENT = "{http://search.yahoo.com/mrss/}content"

_TAG_RE      = re.compile(r"<[^>]+>")
_WS_RE       = re.compile(r"\s+")
_META_RE     = re.compile(r"<meta\b[^>]*>", re.I)
_ATTR_RE     = re.compile(r"""([\w:.\-]+)\s*=\s*(?:"([^"]*)"|'([^']*)')""")
_IMG_SRC_RE  = re.compile(r"""<img[^>]+src\s*=\s*["']([^"']+)["']""", re.I)
_BLOG_ID_RE  = re.compile(r"/(\d{8,})(?:[/-]|$)")
_LEAD_TAG_RE = re.compile(r"^\s*\[[^\]]{1,40}\]\s*")
_SLUG_RE     = re.compile(r"[^a-z0-9]+")

_preview_cache: dict = {}


# ─── text & url helpers ──────────────────────────────
def plain_text(raw: str, limit: int = NEWS_SUMMARY_CHARS) -> str:
    """HTML or RSS snippet → one clean paragraph, cut on a word boundary."""
    if not raw:
        return ""
    text = html.unescape(_TAG_RE.sub(" ", raw))
    text = _WS_RE.sub(" ", text).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(" ,.;:–—-") + "…"


def https_url(url: str) -> str:
    """Protocol-relative and http image URLs → https; anything else is dropped."""
    if not url:
        return ""
    url = url.strip()
    if url.startswith("//"):
        url = f"https:{url}"
    elif url.startswith("http://"):
        url = f"https://{url[7:]}"
    return url if url.startswith("https://") else ""


def parse_published(value: str):
    """ISO 8601 (Blizzard) or RFC 2822 (RSS) → aware UTC datetime, else None."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
    if parsed is None:
        return None
    # A feed that omits the offset means UTC. astimezone() on a naive value
    # would read it as the host's local time and shift the age cutoff.
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def blog_id_from_url(url: str) -> str:
    """A Blizzard blog ID survives every mirror, so it is the strongest key we
    have. Blue Tracker reuses it verbatim for blog mirrors but numbers its own
    forum topics far lower, hence the 8-digit floor."""
    match = _BLOG_ID_RE.search(url or "")
    return match.group(1) if match else ""


def title_key(title: str) -> str:
    """'[EU] Tune in to WoW' and 'Tune in to WoW' collapse to the same key."""
    text = _LEAD_TAG_RE.sub("", title or "")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return _SLUG_RE.sub("-", text.lower()).strip("-")


def title_fingerprint(article: dict, day_offset: int = 0) -> str:
    """Blue posts reuse titles for weeks ("Realm Restarts"), so a title only
    identifies an article together with the day it was published on."""
    slug = title_key(article.get("title", ""))
    if not slug:
        return ""
    published = article.get("published")
    if published is None:
        return f"title:{slug}"
    return f"title:{slug}:{(published + timedelta(days=day_offset)).date().isoformat()}"


def stored_fingerprints(article: dict) -> list:
    """The identities of an article as they are written to the cache."""
    keys = []
    if article.get("blog_id"):
        keys.append(f"blog:{article['blog_id']}")
    guid = article.get("guid") or article.get("url", "")
    if guid:
        keys.append(f"guid:{guid}")
    title = title_fingerprint(article)
    if title:
        keys.append(title)
    return keys


def lookup_fingerprints(article: dict) -> list:
    """Everything worth testing against the cache, including looser matches:
    a mirror can land either side of midnight from the original, and bare
    guids are what the cache held before fingerprints existed."""
    keys = stored_fingerprints(article)
    guid = article.get("guid") or article.get("url", "")
    if guid:
        keys.append(guid)
    for offset in (-1, 1):
        neighbour = title_fingerprint(article, offset)
        if neighbour:
            keys.append(neighbour)
    return keys


def is_relevant(title: str, summary: str = "") -> bool:
    haystack = f"{title} {summary}".lower()
    return any(keyword in haystack for keyword in NEWS_KEYWORDS)


# ─── http ───────────────────────────────────────
async def fetch_text(url: str, byte_limit: int = 0) -> str:
    async with aiohttp.ClientSession(headers=NEWS_HEADERS, timeout=NEWS_TIMEOUT) as session:
        async with session.get(url) as response:
            if response.status != 200:
                raise ValueError(f"HTTP {response.status}")
            if byte_limit:
                raw = await response.content.read(byte_limit)
                return raw.decode(response.charset or "utf-8", "replace")
            return await response.text()


def meta_image(page: str) -> str:
    """OpenGraph / Twitter card image of an article page."""
    wanted = ("og:image", "og:image:url", "og:image:secure_url",
              "twitter:image", "twitter:image:src")
    for tag in _META_RE.findall(page):
        attrs = {}
        for match in _ATTR_RE.finditer(tag):
            attrs[match.group(1).lower()] = match.group(2) if match.group(2) is not None else match.group(3)
        key = (attrs.get("property") or attrs.get("name") or "").lower()
        if key not in wanted:
            continue
        content = (attrs.get("content") or "").strip()
        # Blizzard ships an unresolved template placeholder instead of a URL.
        if content.startswith("//") or "://" in content:
            return content
    return ""


_GENERIC_IMAGE_HINTS = ("/logo", "favicon", "apple-touch-icon", "placeholder", "default-share")


def is_generic_image(url: str) -> bool:
    """Some sites serve their own logo as the OpenGraph image of every page."""
    return any(hint in url.lower() for hint in _GENERIC_IMAGE_HINTS)


def body_image(page: str) -> str:
    """Blue Tracker mirrors Blizzard's CMS images but ships no OpenGraph tags."""
    for src in _IMG_SRC_RE.findall(page):
        if any(marker in src for marker in ("blog_header", "blog_thumbnail", "content_entry_media")):
            return src
    return ""


async def fetch_preview_image(url: str) -> str:
    """Preview image of an article page, cached per URL."""
    if not url:
        return ""
    if url in _preview_cache:
        return _preview_cache[url]
    image = ""
    try:
        page      = await fetch_text(url, byte_limit=NEWS_PAGE_BYTES)
        candidate = meta_image(page)
        if not candidate or is_generic_image(candidate):
            candidate = body_image(page) or ""
        image = https_url(candidate)
    except Exception as exc:
        print(f"[WARN] Preview image failed for {url}: {exc}")
    _preview_cache[url] = image
    if len(_preview_cache) > NEWS_PREVIEW_CACHE:
        _preview_cache.pop(next(iter(_preview_cache)))
    return image


# ─── sources ────────────────────────────────────
async def fetch_news_blizzard() -> list:
    """The official news page ships its article list as an embedded JSON blob."""
    marker = '"blogList":'
    try:
        page  = await fetch_text(BLIZZARD_NEWS_URL)
        start = page.find(marker)
        if start < 0:
            print("[WARN] Blizzard news: blogList blob not found")
            return []
        blob, _ = json.JSONDecoder().raw_decode(page, start + len(marker))
    except Exception as exc:
        print(f"[WARN] Blizzard news fetch failed: {exc}")
        return []

    results = []
    for blog in blob.get("blogs", [])[:12]:
        title = (blog.get("title") or "").strip()
        path  = blog.get("url") or ""
        if not title or not path or blog.get("draft"):
            continue
        results.append({
            "source":    "blizzard",
            "title":     title,
            "url":       f"https://worldofwarcraft.blizzard.com/en-gb{path}",
            "guid":      f"blizzard:{blog.get('id')}",
            "blog_id":   str(blog.get("id") or ""),
            "summary":   plain_text(blog.get("description") or blog.get("content") or ""),
            "image":     https_url((blog.get("image") or {}).get("url", "")),
            "published": parse_published(blog.get("published") or ""),
        })
    return results


async def fetch_news_wowhead() -> list:
    try:
        text  = await fetch_text(WOWHEAD_RSS_URL)
        items = ET.fromstring(text).findall(".//item")
    except Exception as exc:
        print(f"[WARN] Wowhead news fetch failed: {exc}")
        return []

    results = []
    for item in items[:20]:
        title = (item.findtext("title") or "").strip()
        link  = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        summary = plain_text(item.findtext("description") or "")
        if not is_relevant(title, summary):
            continue
        media = item.find(RSS_MEDIA_CONTENT)
        results.append({
            "source":    "wowhead",
            "title":     title,
            "url":       link,
            "guid":      (item.findtext("guid") or link).strip(),
            "blog_id":   "",
            "summary":   summary,
            "image":     https_url(media.get("url", "")) if media is not None else "",
            "published": parse_published(item.findtext("pubDate") or ""),
        })
        if len(results) >= 8:
            break
    return results


async def fetch_news_bluetracker() -> list:
    """EU blue posts only — the US mirror of the same article is a duplicate."""
    try:
        text  = await fetch_text(BLUETRACKER_RSS)
        items = ET.fromstring(text).findall(".//item")
    except Exception as exc:
        print(f"[WARN] Blue Tracker fetch failed: {exc}")
        return []

    results = []
    for item in items:
        title = (item.findtext("title") or "").strip()
        link  = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        if "/eu-en/" not in link and not title.upper().startswith("[EU]"):
            continue
        results.append({
            "source":    "bluetracker",
            "title":     _LEAD_TAG_RE.sub("", title),
            "url":       link,
            "guid":      (item.findtext("guid") or link).strip(),
            "blog_id":   blog_id_from_url(link),
            "summary":   plain_text(item.findtext("description") or ""),
            "image":     "",
            "published": parse_published(item.findtext("pubDate") or ""),
        })
        if len(results) >= 8:
            break
    return results


# ─── embed ──────────────────────────────────────
def build_news_embed(article: dict) -> discord.Embed:
    source = NEWS_SOURCES.get(article.get("source", ""), NEWS_SOURCES["blizzard"])
    embed  = discord.Embed(
        title=article["title"][:250],
        url=article["url"],
        description=article.get("summary") or None,
        color=source["color"],
        timestamp=article.get("published") or datetime.now(timezone.utc),
    )
    embed.set_author(name=source["label"], url=article["url"], icon_url=source["icon"])
    if article.get("image"):
        embed.set_image(url=article["image"])
    embed.set_footer(text="WoW News")
    return embed


async def collect_news() -> list:
    """All sources merged, in source-priority order: official beats mirrors."""
    batches = await asyncio.gather(
        fetch_news_blizzard(),
        fetch_news_wowhead(),
        fetch_news_bluetracker(),
    )
    return [article for batch in batches for article in batch]


def trim_seen_news():
    global seen_news
    if len(seen_news) > NEWS_CACHE_SIZE:
        seen_news = seen_news[-NEWS_CACHE_SIZE:]


# ─────────────────────────────────────────
#  /wow check
# ─────────────────────────────────────────
class WowGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="wow", description="WoW Character Commands")

    # ══════════════════════════════════════
    #  /wow check
    # ══════════════════════════════════════
    @app_commands.command(name="check", description="Full character check: profile, gear, stats, M+, raids, PvP, achievements")
    @app_commands.describe(
        name="Character Name",
        realm="Realm — pick from the list; leave empty to reuse the last one",
        region="Region (default: eu)",
    )
    @app_commands.choices(region=[
        app_commands.Choice(name="🇪🇺 EU", value="eu"),
        app_commands.Choice(name="🇺🇸 US", value="us"),
    ])
    @app_commands.autocomplete(name=character_autocomplete, realm=realm_autocomplete)
    async def check(self, interaction: discord.Interaction, name: str, realm: str = "", region: str = "eu"):
        await interaction.response.defer()

        # A name picked from the history already knows where it lives.
        if not realm:
            remembered = recall_character(interaction.guild_id, name)
            if not remembered:
                return await interaction.followup.send(embed=error_embed(
                    f"No realm given for **{name}**, and this server has not looked it up before.\n"
                    "Pick a realm from the list."
                ))
            realm  = remembered["realm"]
            region = remembered.get("region") or region

        blizzard_ok = bool(BLIZZARD_CLIENT_ID and BLIZZARD_CLIENT_SECRET)
        wcl_ok      = bool(WCL_CLIENT_ID and WCL_CLIENT_SECRET)

        async def safe(coro, label: str = ""):
            """A missing source must not sink the command, but it must be visible."""
            try:
                return await coro
            except Exception as exc:
                print(f"[WARN] {label or 'lookup'} failed for {name}-{realm}: "
                      f"{type(exc).__name__}: {exc}")
                return None

        if blizzard_ok:
            summary, equipment, statistics, achievements, pvp, char_media, rio, wcl = await asyncio.gather(
                safe(get_summary(realm, name, region), "summary"),
                safe(get_equipment(realm, name, region), "equipment"),
                safe(get_statistics(realm, name, region), "statistics"),
                safe(get_achievements(realm, name, region), "achievements"),
                safe(get_pvp_summary(realm, name, region), "pvp"),
                safe(get_character_media(realm, name, region), "character media"),
                safe(get_raiderio(realm, name, region), "raider.io"),
                safe(get_wcl_character(realm, name, region), "warcraft logs") if wcl_ok else asyncio.sleep(0, result=None),
            )
        else:
            summary = equipment = statistics = achievements = pvp = char_media = None
            rio, wcl = await asyncio.gather(
                safe(get_raiderio(realm, name, region), "raider.io"),
                safe(get_wcl_character(realm, name, region), "warcraft logs") if wcl_ok else asyncio.sleep(0, result=None),
            )

        if not summary and not rio:
            return await interaction.followup.send(embed=error_embed(
                f"**{name}** was not found on **{realm}-{region.upper()}**.\n"
                "Check the name and realm — the character must be on a Retail server."
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

        raid_standing = raid_status(rio)
        rank_standing = mplus_ranks(rio)
        char_name  = summary.get("name", name.capitalize()) if summary else (rio or {}).get("name", name.capitalize())
        realm_name = summary.get("realm", {}).get("name", realm) if summary else (rio or {}).get("realm", realm)

        # Thumbnail: WoW Armory render
        thumb_url = None
        if rio and rio.get("thumbnail_url"):
            thumb_url = f"https://render.worldofwarcraft.com/{region}/" + rio["thumbnail_url"]

        embeds      = []
        attachments = []

        # ══════════════════════════════════
        #  EMBED 1 — PROFILE + GEAR + STATS
        # ══════════════════════════════════
        e1 = discord.Embed(color=color)
        # The description sits directly under the author line, which is the
        # most visible spot an embed has for a link.
        profile_links = []
        if rio and rio.get("profile_url"):
            profile_links.append(f"**[▸ Raider.IO]({rio['profile_url']})**")
        if wcl and wcl.get("id"):
            profile_links.append(
                "**[▸ Warcraft Logs]"
                f"(https://www.warcraftlogs.com/character/id/{wcl['id']})**")
        if profile_links:
            e1.description = ("  ".join(profile_links)
                              if profile_links else None)
        e1.set_author(
            name=f"{class_emoji}  {char_name}  —  {realm_name} ({region.upper()})",
            icon_url=thumb_url,
        )
        if thumb_url:
            e1.set_thumbnail(url=thumb_url)

        # ── Profile ────────────────────────────────────────────
        if summary:
            spec        = summary.get("active_spec", {}).get("name", "?")
            race        = summary.get("race",         {}).get("name", "?")
            faction     = summary.get("faction",      {}).get("name", "?")
            faction_ico = FACTION_EMOJIS.get(faction, "⚪")
            guild       = summary.get("guild",        {}).get("name", "")
            guild_str   = f"**<{guild}>**" if guild else "*No guild*"
            level       = summary.get("level", "?")
            ilvl_eq     = summary.get("equipped_item_level", 0)
            ilvl_avg    = summary.get("average_item_level",  0)
            ach_pts     = summary.get("achievement_points",  0)

            last_login_str = "Unknown"
            ts = summary.get("last_login_timestamp")
            if ts:
                dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
                last_login_str = f"<t:{int(dt.timestamp())}:R>"

        elif rio:
            spec = rio.get("active_spec_name", "?")
            e1.add_field(name="📋 Profile", value=(
                f"{class_emoji} **{char_class}** — {spec}\n"
                f"*(Blizzard API not configured)*"
            ), inline=False)

        sheet_stats = []
        # ── Figures for the sheet ─────────────────────
        if statistics:
            haste    = statistics.get("haste",    {})
            crit     = statistics.get("crit",     {})
            mastery  = statistics.get("mastery",  {})
            vers     = statistics.get("versatility", 0)
            vers_dmg = statistics.get("versatility_damage_done_bonus", 0)

            ratings = {
                "Haste":       haste.get("rating", 0) if isinstance(haste, dict) else 0,
                "Crit":        crit.get("rating", 0) if isinstance(crit, dict) else 0,
                "Mastery":     mastery.get("rating", 0) if isinstance(mastery, dict) else 0,
                "Versatility": vers if isinstance(vers, int) else 0,
            }
            top_stat = max(ratings, key=ratings.get)

            # Rendered onto the sheet instead of listed as fields, so page one
            # reads like every other panel.
            ranks = mplus_ranks(rio)
            raid_name, raid_done = raid_cell(rio)
            plain = render_util.TEXT
            sheet_stats = [
                ("Guild",        guild.strip() or "No guild", plain),
                ("Spec",         spec, plain),
                ("Level",        str(level), plain),
                ("Achievements", f"{ach_pts:,}", plain),
                ("M+ Rating",    f"{mp_score:.0f}" if mp_score else "—",
                 render_util.score_colour(mp_score)),
                ("World",        f"#{ranks['world']:,}" if ranks["world"] else "—",
                 render_util.rank_colour(ranks["world"])),
                ("Realm",        f"#{ranks['realm']:,}" if ranks["realm"] else "—",
                 render_util.rank_colour(ranks["realm"])),
                (raid_name,      raid_done, plain),
                ("Haste",        stat_percent(haste), plain),
                ("Crit",         stat_percent(crit), plain),
                ("Mastery",      stat_percent(mastery), plain),
                ("Versatility",  f"{vers_dmg:.1f}%", plain),
            ]

        # ── Gear ──────────────────────────────────────────
        # Discord cannot place images inside field text, so the gear leaves as
        # one rendered character sheet attached to this embed.
        if equipment:
            slots, enchant_lines, gem_lines, avg_ilvl = await build_gear_slots(equipment, region)

            portrait = None
            for asset in (char_media or {}).get("assets", []):
                if asset.get("key") == "main-raw":
                    portrait = await download_bytes(asset["value"])
                    break

            sheet = gear_render.render_sheet(
                header={
                    "title":    f"{char_name} — {realm_name} ({region.upper()})",
                    "subtitle": (f"{char_class}  ·  Ø {avg_ilvl} iLvl"
                                 + (f"  ·  M+ {mp_score:.0f}" if mp_score else "")),
                },
                slots=slots,
                portrait=portrait,
                stats=sheet_stats,
            )

            if sheet:
                attachments.append(discord.File(io.BytesIO(sheet), filename="character.png"))
                e1.set_image(url="attachment://character.png")
                e1.set_thumbnail(url=None)   # the sheet already shows the full body
            else:
                # Pillow unavailable — fall back to the list so gear is never lost.
                lines_out = [
                    f"**{slots[s]['label']}** {slots[s].get('name', '')} `{slots[s].get('ilvl', 0)}`"
                    for s in SLOT_ORDER if slots.get(s, {}).get("name")
                ]
                half = len(lines_out) // 2 or len(lines_out)
                e1.add_field(name=f"🛡️ Gear  *(Ø {avg_ilvl} iLvl)*",
                             value="\n".join(lines_out[:half]) or "—", inline=True)
                if lines_out[half:]:
                    e1.add_field(name="​", value="\n".join(lines_out[half:]), inline=True)





        embeds.append(e1)

        # ══════════════════════════════════
        # ══════════════════════════════════
        #  EMBED 2 — M+ + RAIDS
        # ══════════════════════════════════
        e2 = discord.Embed(color=color)
        e2.set_author(
            name=f"{class_emoji}  {char_name}  —  Mythic+",
            icon_url=thumb_url,
        )
        if thumb_url:
            e2.set_thumbnail(url=thumb_url)

        if rio:
            runs_for_panel = await build_mplus_runs(rio)
            seasons = rio.get("mythic_plus_scores_by_season", [])
            scores  = seasons[0].get("scores", {}) if seasons else {}
            panel = mplus_render.render_mplus(
                header={
                    "title":    f"{char_name} — Mythic+",
                    "subtitle": (seasons[0].get("season", "") if seasons else "").replace("-", " ").title(),
                },
                score=scores,
                runs=runs_for_panel,
            )
            if panel:
                attachments.append(discord.File(io.BytesIO(panel), filename="mplus.png"))
                e2.set_image(url="attachment://mplus.png")
                e2.set_thumbnail(url=None)
            else:
                for run in runs_for_panel[:5]:
                    e2.add_field(name=f"🔑 +{run['level']} {run['dungeon']}",
                                 value=f"`{run['score']:.0f} pts`", inline=True)

        else:
            e2.description = "*(Raider.IO data unavailable — the character needs a recent login.)*"

        embeds.append(e2)

        # ══════════════════════════════════
        #  DUNGEON LOGS — Mythic+ on Warcraft Logs
        # ══════════════════════════════════
        dungeon_rows, dungeon_summary = [], {}
        if wcl_ok:
            try:
                dungeon_summary, dungeon_rows = await dungeon_rankings(realm, name, region)
            except Exception as exc:
                print(f"[WARN] Dungeon rankings failed: {exc}")
        if dungeon_rows:
            e_dungeons = discord.Embed(color=color)
            e_dungeons.set_author(name=f"{class_emoji}  {char_name}  —  Dungeon Logs",
                                  icon_url=thumb_url)
            dungeon_table = wcl_render.render_dungeons(
                header={"title": f"{char_name} — Mythic+ Dungeons",
                        "subtitle": "Points & Damage by level"},
                summary=dungeon_summary,
                rows=dungeon_rows,
            )
            if dungeon_table:
                attachments.append(discord.File(io.BytesIO(dungeon_table), filename="dungeons.png"))
                e_dungeons.set_image(url="attachment://dungeons.png")
            else:
                for row in dungeon_rows[:6]:
                    e_dungeons.add_field(
                        name=f"+{row['level'] or 0} {row['dungeon']}",
                        value=f"`{row['points'] or 0:.0f} pts`  ·  best `{row['best'] or 0:.0f}%`",
                        inline=True)
            embeds.append(e_dungeons)

        # ══════════════════════════════════
        #  LAST DUNGEON — every run of the one played most recently
        # ══════════════════════════════════
            latest = None
            try:
                latest = await last_dungeon_runs(realm, name, region, dungeon_rows)
            except Exception as exc:
                print(f"[WARN] Last dungeon lookup failed: {exc}")
            if latest:
                dungeon_name, run_summary, runs = latest
                e_runs = discord.Embed(color=color)
                e_runs.set_author(name=f"{class_emoji}  {char_name}  —  {dungeon_name}",
                                  icon_url=thumb_url)
                runs_table = wcl_render.render_runs(
                    header={"title": dungeon_name, "subtitle": "most recently played"},
                    summary=run_summary,
                    runs=runs,
                )
                if runs_table:
                    attachments.append(discord.File(io.BytesIO(runs_table),
                                                    filename="runs.png"))
                    e_runs.set_image(url="attachment://runs.png")
                else:
                    for run in runs[:6]:
                        e_runs.add_field(
                            name=f"+{run['level'] or 0}",
                            value=f"`{(run['dps'] or 0) / 1000:.1f}K`  ·  "
                                  f"`{run['percent'] or 0:.0f}%`",
                            inline=True)
                embeds.append(e_runs)

        # ══════════════════════════════════



        # ══════════════════════════════════
        #  EMBED 4 — WARCRAFT LOGS
        # ══════════════════════════════════
        e4 = discord.Embed(color=color)
        e4.set_author(
            name=f"{class_emoji}  {char_name}  —  Raid Logs (Warcraft Logs)",
            icon_url=thumb_url,
        )
        if thumb_url:
            e4.set_thumbnail(url=thumb_url)

        if wcl:
            zone = read_zone_rankings(wcl)
            zone_field = zone.get("zone")
            zone_name = (zone_field.get("name") if isinstance(zone_field, dict)
                         else zone.get("zoneName", "Current Raid"))
            difficulty = {3: "Normal", 4: "Heroic", 5: "Mythic"}.get(zone.get("difficulty"), "")
            summary, boss_rows = wcl_table_data(zone)

            table = wcl_render.render_wcl(
                header={
                    "title":    f"{char_name} — {zone_name}",
                    "subtitle": difficulty or "All difficulties",
                },
                summary=summary,
                bosses=boss_rows,
                notes=analyse_logs(summary, boss_rows),
            ) if boss_rows else None

            if table:
                attachments.append(discord.File(io.BytesIO(table), filename="logs.png"))
                e4.set_image(url="attachment://logs.png")
                e4.set_thumbnail(url=None)

            if summary.get("best") is None and not boss_rows:
                e4.description = "*No raid logs found for this character.*"



        elif not wcl_ok:
            e4.description = "*Warcraft Logs API not configured (set WCL_CLIENT_ID / WCL_CLIENT_SECRET in .env).*"
        else:
            e4.description = "*This character has no public raid logs.*"

        embeds.append(e4)

        await interaction.followup.send(embeds=embeds, files=attachments or discord.utils.MISSING)

        # Only a lookup that actually resolved is worth suggesting next time.
        remember_character(interaction.guild_id, char_name, realm, region, realm_name)



# ─────────────────────────────────────────
#  ADMIN: /wowsetup
# ─────────────────────────────────────────
class WowSetupGroup(app_commands.Group):
    def __init__(self):
        # Must be passed in: assigning the attribute afterwards sets a name
        # discord.py does not read, which left the group visible to everyone.
        super().__init__(
            name="wowsetup",
            description="WoW bot administration",
            default_permissions=discord.Permissions(administrator=True),
        )

    # ══════════════════════════════════════
    #  /wow compare
    # ══════════════════════════════════════
    @app_commands.command(name="compare", description="Compare two characters side by side")
    @app_commands.describe(
        name1="First character",
        realm1="Realm of the first character — pick from the list",
        name2="Second character",
        realm2="Realm of the second character — pick from the list",
        region="Region (default: eu)",
    )
    @app_commands.choices(region=[
        app_commands.Choice(name="🇪🇺 EU", value="eu"),
        app_commands.Choice(name="🇺🇸 US", value="us"),
    ])
    @app_commands.autocomplete(
        name1=character_autocomplete, realm1=realm_autocomplete,
        name2=character_autocomplete, realm2=realm_autocomplete,
    )
    async def compare(
        self,
        interaction: discord.Interaction,
        name1: str, realm1: str,
        name2: str, realm2: str,
        region: str = "eu",
    ):
        if not is_admin(interaction):
            return await interaction.response.send_message(
                embed=error_embed("Administrators only."), ephemeral=True)
        await interaction.response.defer()

        async def safe(coro, label: str = ""):
            try:
                return await coro
            except Exception as exc:
                print(f"[WARN] compare {label or 'lookup'} failed: {type(exc).__name__}: {exc}")
                return None

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
            return await interaction.followup.send(embed=error_embed(f"**{name1}** was not found on **{realm1}**."))
        if not s2 and not rio2:
            return await interaction.followup.send(embed=error_embed(f"**{name2}** was not found on **{realm2}**."))

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
                f"Last seen: {last1}"
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
                f"Last seen: {last2}"
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
                embed.add_field(name="🏰 Mythic Raid Comparison", value="\n\n".join(raid_lines), inline=False)

        # Overall winner
        score1 = (ilvl1 / 700 * 40) + (mp1 / 3500 * 40) + (ach1 / 50000 * 20)
        score2 = (ilvl2 / 700 * 40) + (mp2 / 3500 * 40) + (ach2 / 50000 * 20)
        if score1 > score2 + 1:
            winner = f"🏆 **{cn1}** wins the comparison!"
        elif score2 > score1 + 1:
            winner = f"🏆 **{cn2}** wins the comparison!"
        else:
            winner = "🟡 Too close to call — no clear winner!"
        embed.add_field(name="🎯 Overall Verdict", value=winner, inline=False)

        embed.set_footer(text=f"WoW Bot · /wow compare · {region.upper()}  |  Data: Blizzard API + Raider.IO")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="news_channel", description="Set the channel for WoW news & patch notes")
    @app_commands.describe(channel_id="Channel ID (right-click → Copy ID)")
    async def set_news(self, interaction: discord.Interaction, channel_id: str):
        global news_channel_id
        if not is_admin(interaction):
            return await interaction.response.send_message(embed=error_embed("Administrators only."), ephemeral=True)
        try:    cid = int(channel_id)
        except: return await interaction.response.send_message(embed=error_embed("Invalid channel ID."), ephemeral=True)
        ch = interaction.guild.get_channel(cid)
        if not ch:
            return await interaction.response.send_message(embed=error_embed(f"Channel `{cid}` was not found."), ephemeral=True)
        news_channel_id = cid
        save_data()
        embed = discord.Embed(
            title="✅  News Channel Set",
            description=f"📰  WoW news & patch notes will now be posted in <#{cid}>.",
            color=0x00FF98,
        )
        embed.set_footer(text="WoW Bot  ·  Setup complete")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="reset_channel", description="Set the channel for weekly reset reminders")
    @app_commands.describe(channel_id="Channel ID")
    async def set_reset(self, interaction: discord.Interaction, channel_id: str):
        global reset_channel_id
        if not is_admin(interaction):
            return await interaction.response.send_message(embed=error_embed("Administrators only."), ephemeral=True)
        try:    cid = int(channel_id)
        except: return await interaction.response.send_message(embed=error_embed("Invalid channel ID."), ephemeral=True)
        ch = interaction.guild.get_channel(cid)
        if not ch:
            return await interaction.response.send_message(embed=error_embed(f"Channel `{cid}` was not found."), ephemeral=True)
        reset_channel_id = cid
        save_data()
        embed = discord.Embed(
            title="✅  Reset Channel Set",
            description=f"🔄  Weekly reset reminders will now be posted in <#{cid}>.",
            color=0x00FF98,
        )
        embed.set_footer(text="WoW Bot  ·  Setup complete")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="maint_channel", description="Set the channel for maintenance alerts")
    @app_commands.describe(channel_id="Channel ID")
    async def set_maint(self, interaction: discord.Interaction, channel_id: str):
        global maint_channel_id
        if not is_admin(interaction):
            return await interaction.response.send_message(embed=error_embed("Administrators only."), ephemeral=True)
        try:    cid = int(channel_id)
        except: return await interaction.response.send_message(embed=error_embed("Invalid channel ID."), ephemeral=True)
        ch = interaction.guild.get_channel(cid)
        if not ch:
            return await interaction.response.send_message(embed=error_embed(f"Channel `{cid}` was not found."), ephemeral=True)
        maint_channel_id = cid
        save_data()
        embed = discord.Embed(
            title="✅  Maintenance Channel Set",
            description=f"🔧  Maintenance alerts will now be posted in <#{cid}>.",
            color=0x00FF98,
        )
        embed.set_footer(text="WoW Bot  ·  Setup complete")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="overview", description="Show the current WoW bot configuration")
    async def overview(self, interaction: discord.Interaction):
        if not is_admin(interaction):
            return await interaction.response.send_message(embed=error_embed("Administrators only."), ephemeral=True)

        def channel_line(cid):
            return f"✅  <#{cid}>" if cid else "⚠️  *Not set*"

        blizzard_status = "✅ Configured" if (BLIZZARD_CLIENT_ID and BLIZZARD_CLIENT_SECRET) else "❌ Missing"
        wcl_status      = "✅ Configured" if (WCL_CLIENT_ID and WCL_CLIENT_SECRET)           else "❌ Missing"

        embed = discord.Embed(
            title="⚙️  WoW Bot  —  Configuration Overview",
            description=(
                "Current setup status of all channels, APIs and news sources.\n"
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
            name="🔑  API Status",
            value=(
                f"🟦  Blizzard API: **{blizzard_status}**\n"
                f"🟥  Warcraft Logs: **{wcl_status}**"
            ),
            inline=False,
        )
        embed.add_field(
            name="📡  Active News Sources",
            value=(
                "🔵  **Blizzard Official**  —  patch notes & official news\n"
                "📰  **Wowhead**  —  datamines & hotfixes *(filtered)*\n"
                "🔷  **Blue Posts**  —  Blizzard forum replies *(EU only)*\n"
                "*Articles mirrored across sources are posted only once.*"
            ),
            inline=False,
        )
        embed.set_footer(text="WoW Bot  ·  Setup Overview  ·  Visible to admins only")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="health", description="Show what the bot is holding in memory and on disk")
    async def health(self, interaction: discord.Interaction):
        if not is_admin(interaction):
            return await interaction.response.send_message(embed=error_embed("Administrators only."), ephemeral=True)

        report = runtime_report()
        embed  = discord.Embed(
            title="🧮  WoW Bot  —  Runtime",
            description=("Nothing the bot renders is written to disk; images are built in memory "
                         "and handed straight to Discord.\n"
                         + "━" * 46),
            color=0x00FF98,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="🖼️ Item icons",
                        value=f"**{report['icons']}** / {ICON_CACHE_SIZE}", inline=True)
        embed.add_field(name="🏞️ Dungeon art",
                        value=f"**{report['artwork']}** / {ART_CACHE_SIZE}", inline=True)
        embed.add_field(name="📰 News previews",
                        value=f"**{report['previews']}** / {NEWS_PREVIEW_CACHE}", inline=True)
        embed.add_field(name="🔑 News keys",
                        value=f"**{report['news_keys']}** / {NEWS_CACHE_SIZE}", inline=True)
        embed.add_field(name="👥 Characters",
                        value=f"**{report['characters']}** in {report['guilds']} guilds", inline=True)
        embed.add_field(name="💾 Data file",
                        value=f"**{report['data_kb']} KB**", inline=True)
        embed.add_field(
            name="⚙️ Housekeeping",
            value=(f"Runs every **{HOUSEKEEPING_HOURS}h**: clears dungeon art, trims the caches "
                   f"to their caps and forgets characters unused for {HISTORY_MAX_AGE} days."
                   + (f"\nPeak memory **{report['memory_mb']} MB**." if report["memory_mb"] else "")),
            inline=False,
        )
        embed.set_footer(text="WoW Bot  ·  Runtime  ·  Visible to admins only")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="news_test", description="Preview the latest news post without publishing it")
    async def news_test(self, interaction: discord.Interaction):
        if not is_admin(interaction):
            return await interaction.response.send_message(embed=error_embed("Administrators only."), ephemeral=True)
        await interaction.response.defer(ephemeral=True)

        articles = await collect_news()
        if not articles:
            return await interaction.followup.send(
                embed=error_embed("No news source returned an article right now."), ephemeral=True
            )

        oldest  = datetime.min.replace(tzinfo=timezone.utc)
        article = max(articles, key=lambda a: a.get("published") or oldest)
        if not article.get("image"):
            article["image"] = await fetch_preview_image(article["url"])
        await interaction.followup.send(embed=build_news_embed(article), ephemeral=True)


# ─────────────────────────────────────────
#  BACKGROUND TASKS
# ─────────────────────────────────────────

HOUSEKEEPING_HOURS  = 6
HISTORY_MAX_AGE     = 90      # days a remembered character stays suggestable


def runtime_report() -> dict:
    """What the bot is holding on to, in numbers fit for a one-line log."""
    report = {
        "icons":      len(_icon_cache),
        "artwork":    len(_art_cache),
        "previews":   len(_preview_cache),
        "news_keys":  len(seen_news),
        "characters": sum(len(v) for v in character_history.values()),
        "guilds":     len(character_history),
        "data_kb":    round(os.path.getsize(DATA_FILE) / 1024, 1) if os.path.exists(DATA_FILE) else 0.0,
        "memory_mb":  0.0,
    }
    try:                                      # Linux only, and only a hint
        import resource
        report["memory_mb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
    except (ImportError, AttributeError):
        pass
    return report


def prune_history() -> int:
    """Forget characters nobody has looked up in a season."""
    cutoff  = (datetime.now(timezone.utc) - timedelta(days=HISTORY_MAX_AGE)).date().isoformat()
    removed = 0
    for guild, entries in list(character_history.items()):
        # Entries written before dates existed are kept; they age from now on.
        kept = [e for e in entries if e.get("last_used", cutoff) >= cutoff][:CHARACTER_HISTORY_MAX]
        removed += len(entries) - len(kept)
        if kept:
            character_history[guild] = kept
        else:
            del character_history[guild]
    return removed


@tasks.loop(hours=HOUSEKEEPING_HOURS)
async def housekeeping():
    """Keep the caches and the data file from drifting past their limits."""
    global seen_news

    # Dungeon art is the heavy one and is cheap to fetch again.
    freed_art = len(_art_cache)
    _art_cache.clear()

    while len(_icon_cache) > ICON_CACHE_SIZE:
        _icon_cache.pop(next(iter(_icon_cache)))
    while len(_preview_cache) > NEWS_PREVIEW_CACHE:
        _preview_cache.pop(next(iter(_preview_cache)))

    dropped = prune_history()
    before  = len(seen_news)
    trim_seen_news()
    save_data()

    report = runtime_report()
    print(f"[INFO] Housekeeping: released {freed_art} artwork, "
          f"dropped {dropped} stale characters, trimmed {before - len(seen_news)} news keys | "
          f"icons {report['icons']} · news {report['news_keys']} · "
          f"characters {report['characters']} in {report['guilds']} guilds · "
          f"data {report['data_kb']} KB · peak memory {report['memory_mb']} MB")


@tasks.loop(hours=1)
async def check_wow_news():
    global seen_news, news_schema

    if not news_channel_id:
        return
    channel = bot.get_channel(news_channel_id)
    if not channel:
        return

    articles = await collect_news()
    cutoff   = datetime.now(timezone.utc) - timedelta(days=NEWS_MAX_AGE_DAYS)

    known   = set(seen_news)
    pending = []
    for article in articles:
        published = article.get("published")
        if published is None:
            # Undated articles still get posted — going silent on a feed format
            # change would be worse — but the cutoff cannot vouch for them.
            print(f"[WARN] No publish date on: {article['title'][:80]}")
        elif published < cutoff:
            continue
        if known.intersection(lookup_fingerprints(article)):
            continue
        keys = stored_fingerprints(article)
        # Claim the keys right away so a mirror of the same story further down
        # this very batch cannot slip through behind the first copy.
        known.update(keys)
        pending.append((article, keys))

    # First run on the new dedupe format: learn what is already out there and
    # post nothing, so an update never dumps a wall of back-dated articles.
    if news_schema < NEWS_SCHEMA:
        for _, keys in pending:
            seen_news.extend(keys)
        news_schema = NEWS_SCHEMA
        trim_seen_news()
        save_data()
        print(f"[INFO] News cache seeded with {len(pending)} articles — nothing posted this run")
        return

    for article, keys in pending[:NEWS_MAX_PER_RUN]:
        if not article.get("image"):
            article["image"] = await fetch_preview_image(article["url"])
        try:
            await channel.send(embed=build_news_embed(article))
        except Exception as exc:
            print(f"[ERROR] News post failed: {exc}")
            continue
        seen_news.extend(keys)
        trim_seen_news()
        save_data()
        print(f"[INFO] News posted: {article['title']}")


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
            title="⏰  Weekly Reset  —  3 Hours To Go!",
            color=0xFFD700,
            description=(
                "🔔  **The weekly reset is right around the corner.**\n"
                "Last chance to tick off this week's most important goals.\n"
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
            name="📋  Endgame Checklist",
            value=(
                "🏆  Open the Great Vault *(M+, raid, PvP)*\n"
                "⚔️  Weekly raid bosses\n"
                "🗺️  World quests & weekly quests\n"
                "🎯  PvP conquest cap\n"
                "🕳️  Delves & world bosses"
            ),
            inline=True,
        )
        embed.add_field(
            name="💰  Gold & Gear",
            value=(
                "💎  Catch-up gear from weekly events\n"
                "🪙  Weekly profession crafts\n"
                "📦  Weekly quest rewards\n"
                "🎁  Trading Post bounty\n"
                "🏛️  Top up your reputations"
            ),
            inline=True,
        )
        embed.set_footer(text="WoW Bot  ·  Weekly Reset Reminder  ·  Good luck with this week's goals!")
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
            "maintenance":    ("🔧  Scheduled Maintenance", 0xFFD700, "🟡 Planned",  "The service is undergoing scheduled maintenance. Logins may fail temporarily."),
            "partial_outage": ("⚠️  Partial Outage",        0xFF8000, "🟠 Degraded", "Partial disruption — some features are currently unavailable."),
            "major_outage":   ("🔴  Major Outage",          0xC41E3A, "🔴 Critical", "Major disruption — the service is currently unreachable."),
        }
        title, color, severity, info = status_map.get(
            status,
            ("⚠️  Service Issue", 0xFF8000, "🟠 Warning", "An unexpected service status was reported."),
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
            name="🔗  More Info",
            value="[📄 Official status page](https://us.battle.net/support/en/article/service-status)",
            inline=False,
        )
        embed.set_footer(text="WoW Bot  ·  Blizzard Service Status  ·  Checked every 4h")
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
    await ctx.send(f"✅ Synced {len(synced)} slash commands!", delete_after=5)
    print(f"[INFO] Manual sync by {ctx.author}: {len(synced)} commands")


@bot.event
async def on_ready():
    bot.tree.clear_commands(guild=None)
    bot.tree.add_command(WowGroup())
    bot.tree.add_command(WowSetupGroup())
    await bot.tree.sync()

    check_wow_news.start()
    housekeeping.start()
    weekly_reset_reminder.start()
    check_maintenance.start()

    print(f"[INFO] Logged in as       : {bot.user} (ID: {bot.user.id})")
    print(f"[INFO] Blizzard API       : {'Configured ✓' if BLIZZARD_CLIENT_ID else 'NOT SET ✗'}")
    print(f"[INFO] Warcraft Logs API  : {'Configured ✓' if WCL_CLIENT_ID else 'NOT SET ✗'}")
    print(f"[INFO] Commands           : /wow check · /wow compare · /wowsetup")
    print(f"[INFO] News sources       : Blizzard Official + Wowhead + Blue Posts (EU)")
    print(f"[INFO] News channel       : {news_channel_id  or 'Not set'}")
    print(f"[INFO] Reset channel      : {reset_channel_id or 'Not set'}")
    print(f"[INFO] Maint channel      : {maint_channel_id or 'Not set'}")
    print(f"[INFO] Background tasks   : Started")
    print(f"[INFO] Slash commands     : Synced")


# ─────────────────────────────────────────
#  START
# ─────────────────────────────────────────
if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise RuntimeError("[ERROR] DISCORD_TOKEN is missing from .env!")
    if not BLIZZARD_CLIENT_ID or not BLIZZARD_CLIENT_SECRET:
        print("[WARNING] No Blizzard credentials — profile/gear/stats/PvP/achievements will be missing!")
    bot.run(DISCORD_TOKEN)
