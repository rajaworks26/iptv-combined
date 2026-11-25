import collections
import concurrent.futures
import hashlib
import http.client
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from config import (  # noqa: E402
    FORBIDDEN_GROUPS,
    GROUPS,
    GROUP_INDEX,
    GROUP_RANGES,
    NEWS_CATEGORY,
    SPLIT_PLAYLISTS,
)

DATA_DIR = ROOT / "data"
HISTORY_PATH = DATA_DIR / "stream_history.json"
UNMATCHED_EPG_PATH = DATA_DIR / "unmatched_epg.json"
ACTIVE_EPG_PATH = DATA_DIR / "epg_active_ids.json"
CHANNEL_NUMBERS_PATH = ROOT / "channel_numbers.json"
EPG_PUBLIC_URL = "https://raw.githubusercontent.com/rajaworks26/iptv-combined/epg/combined.xml.gz"
OUTPUT_DIR = Path(os.environ.get("IPTV_OUTPUT_DIR", ROOT))

COUNTRIES = {
    "us": "USA",
    "ca": "Canada",
    "in": "India",
    "pk": "Pakistan",
}

SOURCES = [
    ("ca", "https://iptv-org.github.io/iptv/countries/ca.m3u"),
    ("us", "https://iptv-org.github.io/iptv/countries/us.m3u"),
    ("in", "https://iptv-org.github.io/iptv/countries/in.m3u"),
    ("pk", "https://iptv-org.github.io/iptv/countries/pk.m3u"),
    ("ca", "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlists/playlist_canada.m3u8"),
    ("us", "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlists/playlist_usa.m3u8"),
    ("in", "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlists/playlist_india.m3u8"),
]

GLOBAL_ACTIVE_SOURCES = [
    "https://raw.githubusercontent.com/Zaman-Topu/Ip-tv-Collection/main/FINAL_IPTV_ACTIVE.m3u",
]

CATEGORY_SOURCES = [
    "https://iptv-org.github.io/iptv/categories/sports.m3u",
    "https://iptv-org.github.io/iptv/categories/news.m3u",
    "https://iptv-org.github.io/iptv/categories/movies.m3u",
    "https://iptv-org.github.io/iptv/categories/kids.m3u",
    "https://iptv-org.github.io/iptv/categories/documentary.m3u",
    "https://iptv-org.github.io/iptv/categories/music.m3u",
    "https://iptv-org.github.io/iptv/categories/entertainment.m3u",
]

LANGUAGE_SOURCES = [
    "https://iptv-org.github.io/iptv/languages/eng.m3u",
    "https://iptv-org.github.io/iptv/languages/hin.m3u",
    "https://iptv-org.github.io/iptv/languages/urd.m3u",
    "https://iptv-org.github.io/iptv/languages/pan.m3u",
    "https://iptv-org.github.io/iptv/languages/tam.m3u",
    "https://iptv-org.github.io/iptv/languages/tel.m3u",
]

FAST_SOURCES = [
    "https://raw.githubusercontent.com/BuddyChewChew/app-m3u-generator/main/playlists/plutotv_ca.m3u",
    "https://raw.githubusercontent.com/BuddyChewChew/app-m3u-generator/main/playlists/samsungtvplus_ca.m3u",
    "https://raw.githubusercontent.com/BuddyChewChew/app-m3u-generator/main/playlists/samsungtvplus_in.m3u",
    "https://raw.githubusercontent.com/BuddyChewChew/app-m3u-generator/main/playlists/plex_ca.m3u",
    "https://raw.githubusercontent.com/BuddyChewChew/app-m3u-generator/main/playlists/roku_all.m3u",
]

HINDI_PUNJABI_SOURCES = [
    "https://raw.githubusercontent.com/deep2772/Hindi_Punjabi-iptv-playlist/refs/heads/main/Hindi_Punjabi_Merged.m3u",
]

SHOVO_SOURCES = [
    "https://shovo127.github.io/IPTV-By-Shovo/index.m3u",
]

EXTRA_SOURCES = (
    CATEGORY_SOURCES + LANGUAGE_SOURCES + FAST_SOURCES
    + HINDI_PUNJABI_SOURCES + SHOVO_SOURCES
)

COUNTRY_MATCHERS = {
    "ca": ("Canada", [
        "canada", "canadian", "toronto", "cp24", "cbc", "ctv", "citytv",
        "global news", "tvo", "tsn", "sportsnet", "ami-tv", "aptn",
        "chek", "chch",
    ]),
    "us": ("USA", [
        "usa", "united states", "american", "abc", "nbc", "cbs", "fox",
        "pbs", "amc", "hbo", "showtime", "tnt", "tbs", "usa network",
    ]),
    "in": ("India", [
        "india", "indian", "hindi", "punjabi", "tamil", "telugu", "malayalam",
        "bengali", "marathi", "gujarati", "kannada", "star plus",
        "zee tv", "sony sab", "aaj tak", "ndtv", "dd national", "ptc punjabi",
    ]),
    "pk": ("Pakistan", [
        "pakistan", "pakistani", "urdu", "lollywood", "geo news", "geo tv",
        "geo super", "geo entertainment", "ary digital", "ary news", "ary qtv",
        "ary zindagi", "hum tv", "hum news", "hum sitaray", "hum masala",
        "samaa", "ptv", "dunya news", "express news", "bol news", "92 news",
        "aaj news", "dawn news", "sindh tv", "apna channel",
    ]),
}

EXCLUDED_LANG_KEYWORDS = (
    "spanish", "español", "espanol", "latino", "latin", "portuguese", "português",
    "arabic", "russian", "turkish",
    "german", "deutsch", "italian", "italiano", "korean", "japanese", "chinese",
    "mandarin", "cantonese", "vietnamese", "thai", "indonesian", "persian", "farsi",
    "telemundo", "univision", "unimas", "galavision", "azteca", "caracol", "rcn", "telefe",
)

# Explicit channel-family matches take precedence over broad substring rules.
SPORTS_CHANNELS = (
    "espn", "tsn", "sportsnet", "sky sports", "tnt sports", "fox sports",
    "nbc sports", "cbs sports network", "bein sports", "dazn", "willow",
    "ptv sports", "ten sports", "star sports", "sony sports ten", "supersport",
    "euro sport", "eurosport", "golf channel", "nfl network", "nba tv",
    "mlb network", "nhl network", "geo super", "a sports", "t sports",
    "sports", "cricket", "football", "soccer", "tennis", "racing",
)

INTERNATIONAL_NEWS_CHANNELS = (
    "bbc world news", "bbc news", "al jazeera", "aljazeera", "dw",
    "france 24", "euronews", "sky news", "rt", "cgtn", "nhk world",
    "wion", "trt world",
)

MOVIE_CHANNELS = (
    "hbo", "cinemax", "star movies", "sony max", "zee cinema", "colors cineplex",
    "movie", "movies", "cinema", "cineplex", "film", "films", "bollywood",
    "lollywood",
)

MUSIC_CHANNELS = (
    "mtv", "vh1", "9xm", "b4u music", "mtv hits", "mtv live", "vh1 classic",
    "music",
)

KIDS_CHANNELS = (
    "nickelodeon", "nick jr", "nicktoons", "cartoon network", "disney channel",
    "disney junior", "disney xd", "pbs kids", "boomerang", "universal kids",
    "kids", "child", "children",
)

DOCUMENTARY_CHANNELS = (
    "discovery", "national geographic", "nat geo", "nat geo wild", "history",
    "smithsonian", "hgtv", "food network", "tlc", "travel channel",
    "animal planet", "science channel", "cooking channel", "magnolia",
    "documentary", "nature", "science", "travel", "food", "home",
)

US_NEWS_CHANNELS = (
    "cnn", "fox news", "fox business", "msnbc", "cnbc", "bloomberg", "c-span",
    "cspan", "newsmax", "abc news", "cbs news", "nbc news", "news",
)

CANADA_NEWS_CHANNELS = (
    "cbc news network", "ctv news channel", "cp24", "global news", "citynews",
    "news",
)

INDIA_HINDI_CHANNELS = (
    "star plus", "sony entertainment television", "zee tv", "colors", "sab tv",
    "&tv", "dd national", "aaj tak", "abp news", "ndtv india", "republic bharat",
    "hindi",
)

INDIA_PUNJABI_CHANNELS = (
    "ptc punjabi", "ptc news", "ptc chak de", "pitaara", "zee punjabi", "mh one",
    "chardikla time tv", "punjabi", "bengali", "marathi", "gujarati", "malayalam",
    "kannada", "odia", "assamese",
)

INDIA_TAMIL_TELUGU_CHANNELS = (
    "sun tv", "star vijay", "kalaignar", "zee tamil", "colors tamil", "jaya tv",
    "ktv", "etv telugu", "gemini tv", "star maa", "zee telugu", "tv9 telugu",
    "tamil", "telugu",
)

PAKISTAN_CHANNELS = (
    "geo entertainment", "geo news", "ary digital", "ary news", "hum tv",
    "hum news", "express news", "dunya news", "samaa", "ptv home", "ptv news",
    "green entertainment", "urdu", "pakistani", "pakistan",
)

# Explicit overrides win before every rule-based classification path.
CHANNEL_OVERRIDES = {
    "bbc world news": "News | International",
    "bbc news": "News | International",
    "wion": "News | International",
    "cnn": "USA | News & Business",
    "fox news": "USA | News & Business",
    "cbc news network": "Canada | General & News",
    "cp24": "Canada | General & News",
    "chek": "Canada | Sports & Regional",
    "cbc toronto": "Canada | Sports & Regional",
    "pbs kids": "USA | Kids & Family",
    "national geographic": "USA | Documentary & Lifestyle",
    "star plus": "India | Hindi & General",
    "ptc punjabi": "India | Punjabi & Regional",
    "star vijay": "India | South (Tamil & Telugu)",
    "zee telugu": "India | South (Tamil & Telugu)",
    "geo news": "Pakistan",
    "zee cinema": "Movies",
    "pitaara": "Movies",
    "b4u music": "Music",
}

FALLBACK_LOGOS = {
    "Live Sports": "https://img.icons8.com/color/240/trophy.png",
    "News | International": "https://img.icons8.com/color/240/news.png",
    "Canada | General & News": "https://img.icons8.com/color/240/canada-circular.png",
    "Canada | Sports & Regional": "https://img.icons8.com/color/240/canada-circular.png",
    "USA | Networks & Entertainment": "https://img.icons8.com/color/240/usa-circular.png",
    "USA | News & Business": "https://img.icons8.com/color/240/usa-circular.png",
    "USA | Kids & Family": "https://img.icons8.com/color/240/usa-circular.png",
    "USA | Documentary & Lifestyle": "https://img.icons8.com/color/240/usa-circular.png",
    "India | Hindi & General": "https://img.icons8.com/color/240/india-circular.png",
    "India | Punjabi & Regional": "https://img.icons8.com/color/240/india-circular.png",
    "India | South (Tamil & Telugu)": "https://img.icons8.com/color/240/india-circular.png",
    "Pakistan": "https://img.icons8.com/color/240/pakistan-circular.png",
    "Movies": "https://img.icons8.com/color/240/clapperboard.png",
    "Music": "https://img.icons8.com/color/240/music.png",
}

BLOCKED_SITES = {"tvtv.us", "distro.tv"}
SITE_PRIORITY = {
    "tvpassport.com": 5,
    "tvguide.com": 5,
    "ontvtonight.com": 4,
    "i.mjh.nz": 4,
    "tataplay.com": 4,
    "airtelxstream.in": 4,
    "tvhebdo.com": 3,
}

EPG_ALIASES = {
    "CityNewsToronto.ca@SD": ["CitytvToronto.ca@HD", "CitytvToronto.ca@SD", "CitytvToronto.ca"],
    "CityNewsCalgary.ca@SD": ["CitytvCalgary.ca@HD", "CitytvCalgary.ca@SD", "CitytvCalgary.ca"],
    "CityNewsEdmonton.ca@SD": ["CitytvEdmonton.ca@HD", "CitytvEdmonton.ca@SD", "CitytvEdmonton.ca"],
    "CityNewsVancouver.ca@SD": ["CitytvVancouver.ca@HD", "CitytvVancouver.ca@SD", "CitytvVancouver.ca"],
}

CHECK_STREAMS = True
LIVE_TIMEOUT = 5.0
LIVE_WORKERS = 60
MIN_PRIMARY_SOURCES_OK = 5
MIN_CHANNELS = 300
HISTORY_WINDOW = 10
SUPPORTED_RESOLUTIONS = {2160, 1080, 720, 576, 480}
VOD_EXTENSIONS = (".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".m4v")
EXPIRING_TOKEN_MARKERS = ("wmsauthsign=", "hdnea=", "edge-token=", "session_token=")


def get_bytes(url, timeout=90, limit=None, retries=3, extra_headers=None):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Accept": "*/*"}
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, headers=headers)
    last_exc = None
    attempts = 1 if limit else retries
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if getattr(resp, "status", 200) >= 400:
                    raise urllib.error.HTTPError(url, resp.status, "HTTP Error", resp.headers, None)
                try:
                    data = resp.read(limit) if limit else resp.read()
                except http.client.IncompleteRead as ir:
                    if limit and ir.partial:
                        return ir.partial, resp.geturl()
                    raise
                return data, resp.geturl()
        except Exception as exc:
            last_exc = exc
            if attempt + 1 < attempts:
                time.sleep(1.5 * (attempt + 1))
    raise last_exc


def fetch_text(url, timeout=90):
    data, _ = get_bytes(url, timeout=timeout)
    return data.decode("utf-8-sig", errors="ignore")


def is_unreliable_url(url):
    low = url.lower()
    path = urllib.parse.urlparse(low).path
    if path.endswith(VOD_EXTENSIONS) or "/movie/" in path or "/vod/" in path:
        return True
    return any(token in low for token in EXPIRING_TOKEN_MARKERS)


def extract_vlc_headers(extras):
    headers = {}
    for line in extras:
        if line.startswith("#EXTVLCOPT:http-user-agent="):
            headers["User-Agent"] = line.split("=", 1)[1].strip()
        elif line.startswith("#EXTVLCOPT:http-referrer="):
            headers["Referer"] = line.split("=", 1)[1].strip()
    return headers


def build_tivimate_url(url, extras):
    if "|" in url:
        return url
    headers = extract_vlc_headers(extras)
    if not headers:
        return url
    params = urllib.parse.urlencode(headers)
    return f"{url}|{params}"


def parse_max_height(m3u8_text):
    heights = [int(value) for value in re.findall(r"RESOLUTION=\d+x(\d+)", m3u8_text)]
    return max(heights) if heights else 0


def looks_like_markup(data):
    head = data[:512].lstrip(b"\xef\xbb\xbf \r\n\t").lower()
    return head.startswith((b"<", b"{", b"[")) or b"<html" in head or b"<!doctype" in head


def looks_like_media(data):
    if len(data) < 188 or looks_like_markup(data):
        return False
    if data[0] == 0x47 or data[4:8] in (b"ftyp", b"styp", b"moof") or data[:3] in (b"ID3", b"FLV"):
        return True
    sample = data[:256]
    printable = sum(1 for byte in sample if 32 <= byte < 127 or byte in (9, 10, 13))
    return printable / len(sample) < 0.6


def probe_stream(url, extras=None):
    """Return (alive, detected maximum height, latency in milliseconds)."""
    base_url = url.split("|", 1)[0]
    if not base_url.startswith(("http://", "https://")) or is_unreliable_url(base_url):
        return False, 0, 9999
    req_headers = extract_vlc_headers(extras or [])
    started = time.monotonic()
    max_height = 0
    try:
        current_url = base_url
        for _ in range(3):
            data, final_url = get_bytes(current_url, timeout=LIVE_TIMEOUT, limit=65536, extra_headers=req_headers)
            if not data:
                return False, 0, 9999
            text = data.decode("utf-8", errors="ignore")
            if not text.lstrip().startswith("#EXTM3U"):
                alive = looks_like_media(data)
                latency = int((time.monotonic() - started) * 1000) if alive else 9999
                return alive, max_height, latency
            if "#EXT-X-ENDLIST" in text or "PLAYLIST-TYPE:VOD" in text:
                return False, 0, 9999
            max_height = max(max_height, parse_max_height(text))
            next_uri = next(
                (line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")),
                None,
            )
            if not next_uri:
                return False, 0, 9999
            current_url = urllib.parse.urljoin(final_url, next_uri)
            if "#EXT-X-STREAM-INF" not in text and "#EXTINF:" in text:
                segment_data, _ = get_bytes(current_url, timeout=LIVE_TIMEOUT, limit=16384, extra_headers=req_headers)
                alive = looks_like_media(segment_data)
                latency = int((time.monotonic() - started) * 1000) if alive else 9999
                return alive, max_height, latency
        return False, 0, 9999
    except (OSError, ValueError, TimeoutError, urllib.error.URLError, http.client.HTTPException):
        return False, 0, 9999


def load_history():
    if HISTORY_PATH.exists():
        try:
            return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_history(history):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    pruned = {url: bits for url, bits in history.items() if "1" in bits[-HISTORY_WINDOW:]}
    HISTORY_PATH.write_text(json.dumps(pruned, separators=(",", ":")) + "\n", encoding="utf-8")


def compute_score(entry, uptime_ratio, height, latency_ms):
    uptime_points = 45.0 * uptime_ratio
    metadata_points = (15.0 if entry["tvgid"] else 0.0) + (10.0 if entry["logo"] else 0.0)
    if height >= 1080:
        resolution_points = 15.0
    elif height >= 720:
        resolution_points = 11.0
    elif height >= 480:
        resolution_points = 7.0
    else:
        resolution_points = 5.0
    if latency_ms <= 600:
        speed_points = 15.0
    elif latency_ms <= 1500:
        speed_points = 11.0
    elif latency_ms <= 3000:
        speed_points = 7.0
    else:
        speed_points = 3.0
    return round(uptime_points + metadata_points + resolution_points + speed_points, 1)


def attr(line, key):
    match = re.search(r"(?<!\w)" + re.escape(key) + r"=\"([^\"]*)\"", line)
    return match.group(1) if match else ""


def put(line, key, value):
    value = str(value).replace('"', "").replace("\n", " ")
    line = re.sub(r"\s*(?<!\w)" + re.escape(key) + r"=(?:\"[^\"]*\"|'[^']*')", "", line)
    return line.replace("#EXTINF:", f'#EXTINF: {key}="{value}" ', 1)


def set_display_name(line, name):
    return line.rsplit(",", 1)[0] + f",{name}"


def norm_title(name):
    cleaned = re.sub(r"\([^)]*\)|\[[^\]]*\]", "", name.lower())
    cleaned = re.sub(r"\b(hd|sd|fhd|uhd|4k|1080p|720p|live|tv|channel)\b", "", cleaned)
    return re.sub(r"[^a-z0-9]+", "", cleaned)


def norm_epg_name(name):
    cleaned = re.sub(r"\([^)]*\)|\[[^\]]*\]", "", name.lower())
    cleaned = re.sub(r"\b(hd|sd|fhd|uhd|4k|1080p|720p|live|tv|channel|east|west|pacific|atlantic|national)\b", "", cleaned)
    return re.sub(r"[^a-z0-9]+", "", cleaned)


def clean_display_name(name):
    """Normalize clutter while preserving meaningful branding and variants."""
    value = name.strip()
    value = re.sub(r"^\s*(?:US|USA|CA|IN|PK)\s*[:|]\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\[(?:FHD|HD|SD|4K|UHD)\]", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\b(?:FHD|UHD|4K)\b", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\bBACKUP\b", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s{2,}", " ", value)
    value = re.sub(r"\s*[|·]\s*$", "", value)
    return value.strip(" -|").strip()


def resolution_badge(height):
    return f" [{height}p]" if height in SUPPORTED_RESOLUTIONS else ""


def has_word(text, *terms):
    return any(re.search(r"\b" + re.escape(term) + r"\b", text) for term in terms)


def contains_family(text, families):
    normalized = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
    return any(re.search(r"(?:^| )" + re.escape(term) + r"(?: |$)", normalized) for term in families)


def detect_lang(text, country_code=""):
    value = text.lower()
    for word, label in [
        ("urdu", "Urdu"),
        ("punjabi", "Punjabi"),
        ("hindi", "Hindi"),
        ("tamil", "Tamil"),
        ("telugu", "Telugu"),
        ("bengali", "Bengali"),
        ("malayalam", "Malayalam"),
        ("english", "English"),
    ]:
        if word in value:
            return label
    if country_code in ("us", "ca"):
        return "English"
    if country_code == "pk":
        return "Urdu"
    return "Other / Unspecified"


def classify_channel(name, old_group, country_code, language=""):
    """Return (group, category) using deterministic precedence rules."""
    old = (old_group or "").strip().lower()
    text = f"{name} {old_group} {language}".lower()
    normalized = norm_title(name)

    override = CHANNEL_OVERRIDES.get(normalized)
    if override:
        category = NEWS_CATEGORY if "News" in override else ""
        return override, category

    if old == "sports" or contains_family(text, SPORTS_CHANNELS):
        return "Live Sports", ""

    if contains_family(text, INTERNATIONAL_NEWS_CHANNELS):
        return "News | International", NEWS_CATEGORY

    if old == "movies" or contains_family(text, MOVIE_CHANNELS):
        return "Movies", ""

    if old == "music" or contains_family(text, MUSIC_CHANNELS):
        return "Music", ""

    if country_code == "us":
        if contains_family(text, US_NEWS_CHANNELS):
            return "USA | News & Business", NEWS_CATEGORY
        if contains_family(text, KIDS_CHANNELS):
            return "USA | Kids & Family", ""
        if contains_family(text, DOCUMENTARY_CHANNELS):
            return "USA | Documentary & Lifestyle", ""
        return "USA | Networks & Entertainment", ""

    if country_code == "ca":
        if contains_family(text, CANADA_NEWS_CHANNELS):
            return "Canada | General & News", NEWS_CATEGORY
        if contains_family(text, ("chek", "chch", "toronto", "regional", "community", "provincial")):
            return "Canada | Sports & Regional", ""
        return "Canada | General & News", ""

    if country_code == "in":
        if contains_family(text, INDIA_TAMIL_TELUGU_CHANNELS):
            return "India | South (Tamil & Telugu)", ""
        if contains_family(text, INDIA_PUNJABI_CHANNELS):
            return "India | Punjabi & Regional", ""
        return "India | Hindi & General", ""

    if country_code == "pk":
        return "Pakistan", ""

    if old == "news" or "news" in text:
        return "News | International", NEWS_CATEGORY

    return "", ""


def resolve_tvgid(tvgid, name, code, guide_index, scoped_site_to_id, fast=False):
    if fast:
        return tvgid
    if tvgid and (tvgid in guide_index or tvgid.split("@", 1)[0] in guide_index):
        return tvgid
    normalized = norm_epg_name(name)
    for cc in ([code] if code in COUNTRIES else list(COUNTRIES)):
        hit = scoped_site_to_id.get((cc, normalized))
        if hit:
            return hit
    return tvgid


def parse_m3u_blocks(lines):
    for index, line in enumerate(lines):
        if not line.startswith("#EXTINF:"):
            continue
        cursor = index + 1
        extras = []
        while cursor < len(lines) and lines[cursor].startswith("#") and not lines[cursor].startswith("#EXTINF:"):
            extras.append(lines[cursor])
            cursor += 1
        if cursor >= len(lines) or lines[cursor].startswith("#"):
            continue
        yield line, extras, lines[cursor].strip()


def format_extinf(entry, number, group_name):
    display_name = clean_display_name(entry["name"]) + resolution_badge(entry.get("height", 0))
    line = set_display_name(entry["line"], display_name)
    line = put(line, "group-title", group_name)
    line = put(line, "tvg-chno", str(number))
    if not attr(line, "tvg-name"):
        line = put(line, "tvg-name", display_name)
    if entry["tvgid"]:
        line = put(line, "tvg-id", entry["tvgid"])
    logo = entry["logo"] or FALLBACK_LOGOS.get(group_name, FALLBACK_LOGOS["Movies"])
    line = put(line, "tvg-logo", logo)
    final_url = build_tivimate_url(entry["url"], entry["extras"])
    return "\n".join([line, *entry["extras"], final_url]) + "\n"


def write_playlist(path, items):
    path.parent.mkdir(parents=True, exist_ok=True)
    header = f'#EXTM3U x-tvg-url="{EPG_PUBLIC_URL}"\n'
    path.write_text(
        header + "".join(format_extinf(entry, number, group) for entry, number, group in items),
        encoding="utf-8",
    )


def natural_key(value):
    return [int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", value)]


def stable_channel_id(entry):
    if entry["tvgid"]:
        return entry["tvgid"]
    identity = f"{entry.get('code', '')}|{norm_title(entry['name'])}"
    return "local:" + hashlib.sha1(identity.encode("utf-8")).hexdigest()[:16]


def load_active_epg_ids():
    if not ACTIVE_EPG_PATH.exists():
        return set()
    try:
        return set(json.loads(ACTIVE_EPG_PATH.read_text(encoding="utf-8")))
    except Exception:
        return set()


def load_channel_numbers():
    if not CHANNEL_NUMBERS_PATH.exists():
        return {}
    try:
        return json.loads(CHANNEL_NUMBERS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def assign_channel_numbers(entries):
    """Assign stable, collision-free numbers while retaining prior assignments."""
    registry = load_channel_numbers()

    # Clear any stale number on incoming entries and disambiguate duplicate primary IDs
    seen_ids = set()
    for entry in entries:
        entry.pop("number", None)
        base_id = stable_channel_id(entry)
        channel_id = base_id
        suffix = 2
        while channel_id in seen_ids:
            channel_id = f"{base_id}#{suffix}"
            suffix += 1
        seen_ids.add(channel_id)
        entry["_assigned_id"] = channel_id

    used = {}
    for channel_id, record in registry.items():
        group = record.get("group")
        number = record.get("number")
        if group in GROUP_RANGES and isinstance(number, int):
            low, high = GROUP_RANGES[group]
            if low <= number <= high and channel_id not in seen_ids:
                used.setdefault(group, set()).add(number)

    assignments = {}
    # Pass 1: Keep existing valid numbers for channels still in the same group
    for entry in entries:
        channel_id = entry["_assigned_id"]
        group = entry["group"]
        low, high = GROUP_RANGES[group]
        previous = registry.get(channel_id)
        if previous and previous.get("group") == group:
            candidate = previous.get("number")
            if isinstance(candidate, int) and low <= candidate <= high and candidate not in used.get(group, set()):
                used.setdefault(group, set()).add(candidate)
                assignments[channel_id] = {"group": group, "number": candidate}
                entry["number"] = candidate

    # Pass 2: Assign the next free number to new or re-grouped channels
    for entry in entries:
        if "number" in entry:
            continue
        channel_id = entry["_assigned_id"]
        group = entry["group"]
        low, high = GROUP_RANGES[group]
        occupied = used.setdefault(group, set())
        number = next((candidate for candidate in range(low, high + 1) if candidate not in occupied), None)
        if number is None:
            raise RuntimeError(f"Channel-number block exhausted for group: {group} ({low}-{high})")
        occupied.add(number)
        assignments[channel_id] = {"group": group, "number": number}
        entry["number"] = number

    # Retain assignments for temporarily unavailable channels; never recycle them.
    for channel_id, record in registry.items():
        if channel_id not in assignments:
            assignments[channel_id] = record

    numbers = [record["number"] for record in assignments.values()]
    if len(numbers) != len(set(numbers)):
        raise RuntimeError("Duplicate channel numbers detected in persistent registry")

    CHANNEL_NUMBERS_PATH.write_text(
        json.dumps(dict(sorted(assignments.items())), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return assignments


def main():
    guides = json.loads(fetch_text("https://iptv-org.github.io/api/guides.json"))
    guide_index = collections.defaultdict(list)
    scoped_site_to_id = {}

    for guide in guides:
        channel = guide.get("channel")
        feed = guide.get("feed")
        site = guide.get("site")
        site_id = guide.get("site_id")
        site_name = guide.get("site_name") or ""
        if not channel or not site or not site_id:
            continue
        full_id = f"{channel}@{feed}" if feed else channel
        if feed:
            guide_index[full_id].append((True, guide))
        guide_index[channel].append((False, guide))
        if site not in BLOCKED_SITES and site_name:
            normalized_site = norm_epg_name(site_name)
            country_match = re.search(r"\.([a-z]{2})(?:@|$)", full_id.lower())
            country = country_match.group(1) if country_match else ""
            if normalized_site and country in COUNTRIES:
                scoped_site_to_id.setdefault((country, normalized_site), full_id)

    fetched = []
    errors = []
    primary_ok = 0
    name_to_tvgid = {}
    name_to_logo = {}

    for priority, (code, url) in enumerate(SOURCES):
        try:
            lines = fetch_text(url).splitlines()
            primary_ok += 1
        except Exception as exc:
            errors.append(f"{url}: {exc}")
            continue
        for line, extras, stream_url in parse_m3u_blocks(lines):
            if is_unreliable_url(stream_url):
                continue
            name = line.split(",", 1)[-1].strip()
            normalized_epg = norm_epg_name(name)
            normalized_title = norm_title(name)
            tvgid = attr(line, "tvg-id") or scoped_site_to_id.get((code, normalized_epg), "")
            logo = attr(line, "tvg-logo")
            if normalized_epg and tvgid:
                name_to_tvgid.setdefault((code, normalized_epg), tvgid)
                name_to_tvgid.setdefault(("", normalized_epg), tvgid)
            if normalized_title and logo:
                name_to_logo.setdefault(normalized_title, logo)
            old_group = attr(line, "group-title")
            language = detect_lang(f"{name} {old_group} {attr(line, 'tvg-language')}", code)
            group, category = classify_channel(name, old_group, code, language)
            fetched.append({
                "line": line,
                "extras": extras,
                "url": stream_url,
                "name": name,
                "tvgid": tvgid,
                "logo": logo,
                "group": group,
                "category": category,
                "language": language,
                "priority": priority,
                "code": code,
                "fast": False,
            })

    if primary_ok < MIN_PRIMARY_SOURCES_OK:
        raise RuntimeError(f"Only {primary_ok}/{len(SOURCES)} primary sources reachable; aborting to preserve existing playlist")

    for active_url in GLOBAL_ACTIVE_SOURCES + EXTRA_SOURCES:
        try:
            lines = fetch_text(active_url).splitlines()
        except Exception as exc:
            errors.append(f"{active_url}: {exc}")
            continue

        is_ca_fast = any(tag in active_url for tag in ("plutotv_ca", "samsungtvplus_ca", "plex_ca"))
        is_in_source = "Hindi_Punjabi" in active_url or "samsungtvplus_in" in active_url or any(
            tag in active_url for tag in ("/hin.m3u", "/pan.m3u", "/tam.m3u", "/tel.m3u")
        )
        is_pk_source = "/urd.m3u" in active_url

        for line, extras, stream_url in parse_m3u_blocks(lines):
            if is_unreliable_url(stream_url):
                continue
            name = line.split(",", 1)[-1].strip()
            old_group = attr(line, "group-title")
            tvg_language = attr(line, "tvg-language")
            old_lower = old_group.lower().strip()
            normalized_epg = norm_epg_name(name)
            normalized_title = norm_title(name)
            text = f"{name} {old_group} {tvg_language}".lower()

            if has_word(text, *EXCLUDED_LANG_KEYWORDS):
                continue

            matched_code = None
            if is_ca_fast:
                matched_code = "ca"
            elif is_in_source:
                matched_code = "in"
            elif is_pk_source:
                matched_code = "pk"
            else:
                tag_match = re.search(r"[\[\(\|]\s*(ca|us|in|pk)\s*[\]\)\|]", text)
                if tag_match:
                    matched_code = tag_match.group(1)
                else:
                    for code, (_, keywords) in COUNTRY_MATCHERS.items():
                        if has_word(text, *keywords):
                            matched_code = code
                            break

            tvgid = (
                attr(line, "tvg-id")
                or (name_to_tvgid.get((matched_code, normalized_epg)) if matched_code else "")
                or name_to_tvgid.get(("", normalized_epg), "")
            )
            logo = attr(line, "tvg-logo") or name_to_logo.get(normalized_title, "")

            is_sports = old_lower == "sports" or contains_family(text, SPORTS_CHANNELS)
            is_news = old_lower in ("international news", "news bd") or "news" in text
            is_allowed_group = old_lower in ("english", "india")
            is_allowed_category = old_lower in (
                "movies", "kids", "documentary", "music", "entertainment",
                "general", "family", "education", "culture", "comedy", "animation",
            )

            if not (is_sports or is_news or matched_code or is_allowed_group or is_allowed_category):
                continue

            language = detect_lang(text, matched_code or "")
            group, category = classify_channel(name, old_group, matched_code or "", language)
            fetched.append({
                "line": line,
                "extras": extras,
                "url": stream_url,
                "name": name,
                "tvgid": tvgid,
                "logo": logo,
                "group": group,
                "category": category,
                "language": language,
                "priority": 10,
                "code": matched_code or "",
                "fast": active_url in FAST_SOURCES,
            })

    fetched = [entry for entry in fetched if entry["group"]]
    for entry in fetched:
        entry["tvgid"] = resolve_tvgid(
            entry["tvgid"], entry["name"], entry.get("code", ""),
            guide_index, scoped_site_to_id, entry.get("fast", False),
        )
    if not fetched:
        raise RuntimeError("No source playlists available")

    unique_urls = {}
    for entry in fetched:
        unique_urls.setdefault(entry["url"], entry)
    candidates = list(unique_urls.values())

    history = load_history()
    grace_retained = 0

    if CHECK_STREAMS:
        with concurrent.futures.ThreadPoolExecutor(max_workers=LIVE_WORKERS) as pool:
            results = list(pool.map(lambda item: probe_stream(item["url"], item["extras"]), candidates))

        healthy = []
        for entry, (alive, height, latency_ms) in zip(candidates, results):
            url = entry["url"]
            previous_bits = history.get(url, "")[-HISTORY_WINDOW:]
            new_bits = (previous_bits + ("1" if alive else "0"))[-HISTORY_WINDOW:]
            history[url] = new_bits
            uptime_ratio = new_bits.count("1") / len(new_bits)
            keep = alive or (len(previous_bits) >= 3 and uptime_ratio >= 0.70 and previous_bits.endswith("1"))
            if keep:
                if not alive:
                    grace_retained += 1
                entry["score"] = compute_score(entry, uptime_ratio, height, latency_ms)
                entry["height"] = height
                entry["resolution"] = f"{height}p" if height else "unknown"
                healthy.append(entry)
        candidates = healthy
    else:
        for entry in candidates:
            entry["score"] = 50.0
            entry["height"] = 0
            entry["resolution"] = "unknown"

    candidates.sort(key=lambda entry: (-entry["score"], entry["priority"]))
    primary = []
    backups = []
    seen_titles = set()

    for entry in candidates:
        key = (entry["group"], norm_title(entry["name"]) or entry["name"].casefold())
        if key in seen_titles:
            backups.append(entry)
        else:
            seen_titles.add(key)
            primary.append(entry)

    allowed_groups = set(GROUPS)
    primary = [entry for entry in primary if entry["group"] in allowed_groups]

    if len(primary) < MIN_CHANNELS:
        raise RuntimeError(f"Only {len(primary)} unique playable channels (minimum {MIN_CHANNELS})")

    save_history(history)

    active_epg_ids = load_active_epg_ids()
    for entry in primary:
        entry["channel_id"] = stable_channel_id(entry)
        entry["active_epg"] = bool(entry["tvgid"] and entry["tvgid"] in active_epg_ids)

    primary.sort(key=lambda entry: (
        0 if entry["active_epg"] else 1,
        -entry["score"],
        natural_key(clean_display_name(entry["name"])),
        entry["channel_id"],
    ))

    assign_channel_numbers(primary)
    numbered = [(entry, entry["number"], entry["group"]) for entry in primary]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_playlist(OUTPUT_DIR / "combined.m3u", numbered)
    write_playlist(
        OUTPUT_DIR / "alternates.m3u",
        [(entry, 900000 + index, entry["group"]) for index, entry in enumerate(backups, 1)],
    )

    for language_name in ("English", "Hindi", "Urdu", "Punjabi", "Tamil", "Telugu"):
        write_playlist(
            OUTPUT_DIR / f"language-{language_name.lower()}.m3u",
            [
                (entry, number, group)
                for entry, number, group in numbered
                if entry["language"] == language_name
            ],
        )

    for filename, rule in SPLIT_PLAYLISTS.items():
        selected = []
        for entry, number, group in numbered:
            matches = (
                group in rule.get("groups", set())
                or entry.get("code", "") in rule.get("countries", set())
                or entry.get("category", "") in rule.get("categories", set())
            )
            if matches:
                selected.append((entry, number, group))
        write_playlist(OUTPUT_DIR / filename, selected)

    ids = {entry["tvgid"] for entry in primary if entry["tvgid"]}
    selected = {}
    for mapped_id in sorted(ids):
        base_id = mapped_id.split("@", 1)[0]
        lookup_keys = list(dict.fromkeys([
            mapped_id,
            base_id,
            f"{base_id}@HD",
            f"{base_id}@SD",
            f"{base_id}@East",
            f"{base_id}@National",
            *EPG_ALIASES.get(mapped_id, []),
        ]))
        best_score = None
        best_guide = None
        for alias_index, key in enumerate(lookup_keys):
            for exact_feed, guide in guide_index.get(key, []):
                site = guide["site"]
                if site in BLOCKED_SITES:
                    continue
                score = (
                    1 if alias_index == 0 else 0,
                    SITE_PRIORITY.get(site, 1),
                    2 if exact_feed else 1,
                    1 if guide.get("lang") == "en" else 0,
                )
                if best_score is None or score > best_score:
                    best_score = score
                    best_guide = guide
        if best_guide is not None:
            selected[mapped_id] = best_guide

    if not selected:
        raise RuntimeError("No EPG mappings available")

    epg_root = ET.Element("channels")
    for mapped_id, guide in sorted(selected.items()):
        element = ET.SubElement(
            epg_root,
            "channel",
            {
                "site": guide["site"],
                "lang": guide.get("lang") or "en",
                "xmltv_id": mapped_id,
                "site_id": str(guide["site_id"]),
            },
        )
        element.text = guide.get("site_name") or mapped_id

    ET.indent(epg_root)
    (OUTPUT_DIR / "epg.channels.xml").write_bytes(
        ET.tostring(epg_root, encoding="utf-8", xml_declaration=True)
    )

    unmatched = [
        {"name": entry["name"], "group": entry["group"], "tvg_id": entry["tvgid"]}
        for entry in primary
        if not entry["tvgid"] or entry["tvgid"] not in selected
    ]
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UNMATCHED_EPG_PATH.write_text(json.dumps(unmatched[:500], indent=2) + "\n", encoding="utf-8")

    group_counts = collections.Counter(entry["group"] for entry in primary)
    report = {
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "primary_sources_ok": f"{primary_ok}/{len(SOURCES)}",
        "source_entries": len(fetched),
        "unique_urls": len(unique_urls),
        "passed_health_checks": len(candidates),
        "grace_retained_streams": grace_retained,
        "unique_primary_channels": len(primary),
        "alternate_streams_saved": len(backups),
        "average_stream_score": round(sum(entry["score"] for entry in primary) / max(len(primary), 1), 1),
        "groups": {group: group_counts.get(group, 0) for group in GROUPS},
        "unique_tvg_ids": len(ids),
        "epg_mapped_ids": len(selected),
        "epg_mapping_percent": round(100 * len(selected) / max(len(ids), 1), 1),
        "source_errors": errors,
        "epg_final_covered_ids": 0,
        "epg_final_percent": 0.0,
    }
    (OUTPUT_DIR / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(
        f"Generated {len(primary)} primary channels, {len(backups)} backups, "
        f"and {len(SPLIT_PLAYLISTS)} split playlists in {OUTPUT_DIR}"
    )


if __name__ == "__main__":
    main()
