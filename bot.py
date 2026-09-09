import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiohttp
import asyncio
import base64
import html
import json
import os
import re
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
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
    }

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump({
            "news_channel":  news_channel_id,
            "reset_channel": reset_channel_id,
            "maint_channel": maint_channel_id,
            "seen_news":     seen_news,
            "news_schema":   news_schema,
        }, f, indent=2)

_data            = load_data()
news_channel_id  = _data.get("news_channel",  None)
reset_channel_id = _data.get("reset_channel", None)
maint_channel_id = _data.get("maint_channel", None)
seen_news: list  = _data.get("seen_news",     [])
news_schema: int = _data.get("news_schema",   0)

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

async def blizzard_get(path: str, region: str = "eu") -> dict:
    token = await get_blizzard_token(region)
    url   = f"https://{region}.api.blizzard.com{path}"
    params = {"namespace": f"profile-{region}", "locale": "en_GB" if region == "eu" else "en_US"}
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
                raise ValueError("Character not found on Raider.IO.")
            if r.status != 200:
                raise ValueError(f"Raider.IO error ({r.status})")
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
_BLOG_ID_RE  = re.compile(r"/(\d{7,})(?:[/-]|$)")
_LEAD_TAG_RE = re.compile(r"^\s*\[[^\]]{1,24}\]\s*")
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
    """ISO 8601 (Blizzard) or RFC 2822 (RSS) → aware datetime, else None."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (TypeError, ValueError):
        pass
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if parsed is None:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def blog_id_from_url(url: str) -> str:
    """Blizzard blog IDs survive every mirror — the strongest dedupe key we have."""
    match = _BLOG_ID_RE.search(url or "")
    return match.group(1) if match else ""


def title_key(title: str) -> str:
    """'[EU] Tune in to WoW' and 'Tune in to WoW' collapse to the same key."""
    text = _LEAD_TAG_RE.sub("", title or "")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return _SLUG_RE.sub("-", text.lower()).strip("-")


def news_fingerprints(article: dict) -> list:
    """Every identity an article can be recognised by across all three sources."""
    keys = []
    if article.get("blog_id"):
        keys.append(f"blog:{article['blog_id']}")
    guid = article.get("guid") or article.get("url", "")
    if guid:
        keys.append(guid)               # legacy format — keeps old cache entries valid
        keys.append(f"guid:{guid}")
    slug = title_key(article.get("title", ""))
    if slug:
        keys.append(f"title:{slug}")
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
        realm="Realm (e.g. Silvermoon, Stormscale, twisting-nether)",
        region="Region (default: eu)",
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

        char_name  = summary.get("name", name.capitalize()) if summary else (rio or {}).get("name", name.capitalize())
        realm_name = summary.get("realm", {}).get("name", realm) if summary else (rio or {}).get("realm", realm)

        # Thumbnail: WoW Armory render
        thumb_url = None
        if rio and rio.get("thumbnail_url"):
            thumb_url = f"https://render.worldofwarcraft.com/{region}/" + rio["thumbnail_url"]

        embeds = []

        # ══════════════════════════════════
        #  EMBED 1 — PROFILE + GEAR + STATS
        # ══════════════════════════════════
        e1 = discord.Embed(color=color)
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
            readiness   = content_readiness(ilvl_eq)

            last_login_str = "Unknown"
            ts = summary.get("last_login_timestamp")
            if ts:
                dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
                last_login_str = f"<t:{int(dt.timestamp())}:R>"

            e1.add_field(name="📋 Profile", value=(
                f"{faction_ico} **{race}** {char_class} — {spec}\n"
                f"🏛️ {guild_str}\n"
                f"📊 Level **{level}** · iLvl **{ilvl_eq}** *(avg {ilvl_avg})*\n"
                f"🏆 **{ach_pts:,}** Achievement Points\n"
                f"🕒 Last online: {last_login_str}"
            ), inline=False)

            e1.add_field(name="🎯 Content Readiness", value=readiness, inline=False)

        elif rio:
            spec = rio.get("active_spec_name", "?")
            e1.add_field(name="📋 Profile", value=(
                f"{class_emoji} **{char_class}** — {spec}\n"
                f"*(Blizzard API not configured)*"
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

        # ── Secondary stats ─────────────────────────────────────
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

            e1.add_field(name=f"📊 Secondary Stats  *(highest: {top_stat})*", value=(
                f"⚡ Haste:        **{fmt_stat(haste)}**\n"
                f"🎯 Crit:         **{fmt_stat(crit)}**\n"
                f"🔮 Mastery:      **{fmt_stat(mastery)}**\n"
                f"🛡️ Versatility: **{vers_dmg:.1f}% ({vers:,})**"
            ), inline=False)

        e1.set_footer(text="WoW Bot · Page 1/4  —  Profile, Gear & Stats")
        embeds.append(e1)

        # ══════════════════════════════════
        #  EMBED 2 — M+ + RAIDS
        # ══════════════════════════════════
        e2 = discord.Embed(color=color)
        e2.set_author(
            name=f"{class_emoji}  {char_name}  —  Mythic+ & Raids",
            icon_url=thumb_url,
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
                elif all_sc >= 2500: score_badge = "🟣 Advanced"
                elif all_sc >= 2000: score_badge = "🔵 Experienced"
                elif all_sc >= 1500: score_badge = "🟢 Active"
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
                e2.add_field(name="🔗 RaiderIO", value=f"[View profile]({profile_url})", inline=False)
        else:
            e2.description = "*(Raider.IO data unavailable — the character needs a recent login.)*"

        e2.set_footer(text="WoW Bot · Page 2/4  —  Mythic+ & Raids")
        embeds.append(e2)

        # ══════════════════════════════════
        #  EMBED 3 — PvP + ACHIEVEMENTS
        # ══════════════════════════════════
        e3 = discord.Embed(color=color)
        e3.set_author(
            name=f"{class_emoji}  {char_name}  —  PvP & Achievements",
            icon_url=thumb_url,
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
                e3.add_field(name="🏆 PvP Stats", value="*No PvP activity this season.*", inline=False)

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

            header = f"🏅 **{ach_pts:,} points** · {total_done:,} completed\n"
            lines  = []
            for a in recent:
                ts    = a["completed_timestamp"]
                dt    = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
                dts   = f"<t:{int(dt.timestamp())}:d>"
                aname = a.get("achievement", {}).get("name", "Unknown")
                lines.append(f"🏆 **{aname}** — {dts}")

            e3.add_field(
                name="🎖️ Achievements  *(8 most recent)*",
                value=header + "\n".join(lines),
                inline=False,
            )

        e3.set_footer(text="WoW Bot · Page 3/4  —  PvP & Achievements")
        embeds.append(e3)

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
            zr_raw = wcl.get("zoneRankings")
            # zoneRankings comes back as either a JSON string or a dict
            if isinstance(zr_raw, str):
                try:    zr = json.loads(zr_raw)
                except: zr = {}
            else:
                zr = zr_raw or {}

            best_avg   = zr.get("bestPerformanceAverage")
            median_avg = zr.get("medianPerformanceAverage")
            zone_name  = (zr.get("zone") or {}).get("name") if isinstance(zr.get("zone"), dict) else zr.get("zoneName", "Current Raid")
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
                e4.add_field(name="🗡️ Overall Performance", value=header_val, inline=False)

            # Best parse per boss
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

            # Link to the Warcraft Logs profile
            wcl_id = wcl.get("id")
            if wcl_id:
                prof_url = f"https://www.warcraftlogs.com/character/id/{wcl_id}"
                e4.add_field(name="🔗 Warcraft Logs", value=f"[View profile]({prof_url})", inline=False)

            if best_avg is None and not rankings:
                e4.description = "*No raid logs found for this character.*"
        elif not wcl_ok:
            e4.description = "*Warcraft Logs API not configured (set WCL_CLIENT_ID / WCL_CLIENT_SECRET in .env).*"
        else:
            e4.description = "*This character has no public raid logs.*"

        e4.set_footer(text="WoW Bot · Page 4/4  —  Raid Logs  |  Data: Blizzard API + Raider.IO + Warcraft Logs")
        embeds.append(e4)

        await interaction.followup.send(embeds=embeds)

    # ══════════════════════════════════════
    #  /wow compare
    # ══════════════════════════════════════
    @app_commands.command(name="compare", description="Compare two characters side by side")
    @app_commands.describe(
        name1="First character",
        realm1="Realm of the first character",
        name2="Second character",
        realm2="Realm of the second character",
        region="Region (default: eu)",
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


# ─────────────────────────────────────────
#  ADMIN: /wowsetup
# ─────────────────────────────────────────
class WowSetupGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="wowsetup", description="Configure the WoW bot channels (admins only)")
        self.default_member_permissions = discord.Permissions(administrator=True)

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
        if published is not None and published < cutoff:
            continue
        keys = news_fingerprints(article)
        if known.intersection(keys):
            continue
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
