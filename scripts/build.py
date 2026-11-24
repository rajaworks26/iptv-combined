import collections
import concurrent.futures
import http.client
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / 'data'
HISTORY_PATH = DATA_DIR / 'stream_history.json'
UNMATCHED_EPG_PATH = DATA_DIR / 'unmatched_epg.json'
EPG_PUBLIC_URL = 'https://raw.githubusercontent.com/rajaworks26/iptv-combined/epg/combined.xml.gz'

COUNTRIES = {
    'us': 'USA',
    'ca': 'Canada',
    'in': 'India',
    'pk': 'Pakistan',
}

SOURCES = [
    ('ca', 'https://iptv-org.github.io/iptv/countries/ca.m3u'),
    ('us', 'https://iptv-org.github.io/iptv/countries/us.m3u'),
    ('in', 'https://iptv-org.github.io/iptv/countries/in.m3u'),
    ('pk', 'https://iptv-org.github.io/iptv/countries/pk.m3u'),
    ('ca', 'https://raw.githubusercontent.com/Free-TV/IPTV/master/playlists/playlist_canada.m3u8'),
    ('us', 'https://raw.githubusercontent.com/Free-TV/IPTV/master/playlists/playlist_usa.m3u8'),
    ('in', 'https://raw.githubusercontent.com/Free-TV/IPTV/master/playlists/playlist_india.m3u8'),
]

GLOBAL_ACTIVE_SOURCES = [
    'https://raw.githubusercontent.com/Zaman-Topu/Ip-tv-Collection/main/FINAL_IPTV_ACTIVE.m3u',
]

CATEGORY_SOURCES = [
    'https://iptv-org.github.io/iptv/categories/sports.m3u',
    'https://iptv-org.github.io/iptv/categories/news.m3u',
    'https://iptv-org.github.io/iptv/categories/movies.m3u',
    'https://iptv-org.github.io/iptv/categories/kids.m3u',
    'https://iptv-org.github.io/iptv/categories/documentary.m3u',
    'https://iptv-org.github.io/iptv/categories/music.m3u',
    'https://iptv-org.github.io/iptv/categories/entertainment.m3u',
]

LANGUAGE_SOURCES = [
    'https://iptv-org.github.io/iptv/languages/eng.m3u',
    'https://iptv-org.github.io/iptv/languages/hin.m3u',
    'https://iptv-org.github.io/iptv/languages/urd.m3u',
    'https://iptv-org.github.io/iptv/languages/pan.m3u',
    'https://iptv-org.github.io/iptv/languages/tam.m3u',
    'https://iptv-org.github.io/iptv/languages/tel.m3u',
]

# Canadian, Indian & global FAST lists (excludes US-only lists that geo-block in Ontario)
FAST_SOURCES = [
    'https://raw.githubusercontent.com/BuddyChewChew/app-m3u-generator/main/playlists/plutotv_ca.m3u',
    'https://raw.githubusercontent.com/BuddyChewChew/app-m3u-generator/main/playlists/samsungtvplus_ca.m3u',
    'https://raw.githubusercontent.com/BuddyChewChew/app-m3u-generator/main/playlists/samsungtvplus_in.m3u',
    'https://raw.githubusercontent.com/BuddyChewChew/app-m3u-generator/main/playlists/plex_ca.m3u',
    'https://raw.githubusercontent.com/BuddyChewChew/app-m3u-generator/main/playlists/roku_all.m3u',
]

HINDI_PUNJABI_SOURCES = [
    'https://raw.githubusercontent.com/deep2772/Hindi_Punjabi-iptv-playlist/refs/heads/main/Hindi_Punjabi_Merged.m3u',
]

SHOVO_SOURCES = [
    'https://shovo127.github.io/IPTV-By-Shovo/index.m3u',
]

EXTRA_SOURCES = (
    CATEGORY_SOURCES + LANGUAGE_SOURCES + FAST_SOURCES
    + HINDI_PUNJABI_SOURCES + SHOVO_SOURCES
)

GROUPS = [
    'Live Sports',
    'International News',
    'Canada',
    'USA',
    'India',
    'Pakistan',
    'Movies',
]

COUNTRY_MATCHERS = {
    'ca': ('Canada', [
        'canada', 'canadian', 'toronto', 'cp24', 'cbc', 'ctv', 'citytv',
        'global news', 'tvo', 'tsn', 'sportsnet', 'ami-tv', 'aptn'
    ]),
    'us': ('USA', [
        'usa', 'united states', 'american', 'abc', 'nbc', 'cbs', 'fox',
        'pbs', 'amc', 'hbo', 'showtime', 'tnt', 'tbs', 'usa network'
    ]),
    'in': ('India', [
        'india', 'indian', 'hindi', 'punjabi', 'tamil', 'telugu', 'malayalam',
        'bengali', 'marathi', 'gujarati', 'kannada', 'star plus',
        'zee tv', 'sony sab', 'aaj tak', 'ndtv', 'dd national', 'ptc punjabi'
    ]),
    'pk': ('Pakistan', [
        'pakistan', 'pakistani', 'urdu', 'lollywood', 'geo news', 'geo tv',
        'geo super', 'geo entertainment', 'ary digital', 'ary news', 'ary qtv',
        'ary zindagi', 'hum tv', 'hum news', 'hum sitaray', 'hum masala',
        'samaa', 'ptv', 'dunya news', 'express news', 'bol news', '92 news',
        'aaj news', 'dawn news', 'sindh tv', 'apna channel'
    ]),
}

EXCLUDED_LANG_KEYWORDS = (
    'spanish', 'español', 'espanol', 'latino', 'latin', 'portuguese', 'português',
    'arabic', 'russian', 'turkish',
    'german', 'deutsch', 'italian', 'italiano', 'korean', 'japanese', 'chinese',
    'mandarin', 'cantonese', 'vietnamese', 'thai', 'indonesian', 'persian', 'farsi',
    'telemundo', 'univision', 'unimas', 'galavision', 'azteca', 'caracol', 'rcn', 'telefe'
)

SPORTS_KEYWORDS = (
    'sport', 'sports', 'cricket', 'football', 'soccer', 'espn', 'bein',
    'sky sports', 'star sports', 't sports', 'ten sports', 'sony ten',
    'formula 1', 'dazn', 'tsn', 'sportsnet', 'ptv sports', 'geo super',
    'a sports', 'willow', 'fox sports', 'cbs sports', 'nbc sports', 'golf', 'tennis', 'racing'
)

NEWS_KEYWORDS = (
    'news', 'cnn', 'bbc', 'al jazeera', 'sky news', 'euronews', 'france 24',
    'msnbc', 'fox news', 'cnbc', 'bloomberg', 'cp24', 'cbc news', 'ctv news',
    'citynews', 'geo news', 'ary news', 'hum news', 'samaa', 'dunya news', 'express news',
    'ndtv', 'india today', 'aaj tak', 'republic', 'wion', 'times now'
)

VOD_EXTENSIONS = ('.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.m4v')
EXPIRING_TOKEN_MARKERS = ('wmsauthsign=', 'hdnea=', 'edge-token=', 'session_token=')

FALLBACK_LOGOS = {
    'Live Sports': 'https://img.icons8.com/color/240/trophy.png',
    'International News': 'https://img.icons8.com/color/240/news.png',
    'Canada': 'https://img.icons8.com/color/240/canada-circular.png',
    'USA': 'https://img.icons8.com/color/240/usa-circular.png',
    'India': 'https://img.icons8.com/color/240/india-circular.png',
    'Pakistan': 'https://img.icons8.com/color/240/pakistan-circular.png',
    'Movies': 'https://img.icons8.com/color/240/clapperboard.png',
}

BLOCKED_SITES = {'tvtv.us', 'distro.tv'}

SITE_PRIORITY = {
    'tvpassport.com': 5,
    'tvguide.com': 5,
    'ontvtonight.com': 4,
    'i.mjh.nz': 4,
    'tataplay.com': 4,
    'airtelxstream.in': 4,
    'tvhebdo.com': 3,
}

EPG_ALIASES = {
    'CityNewsToronto.ca@SD': ['CitytvToronto.ca@HD', 'CitytvToronto.ca@SD', 'CitytvToronto.ca'],
    'CityNewsCalgary.ca@SD': ['CitytvCalgary.ca@HD', 'CitytvCalgary.ca@SD', 'CitytvCalgary.ca'],
    'CityNewsEdmonton.ca@SD': ['CitytvEdmonton.ca@HD', 'CitytvEdmonton.ca@SD', 'CitytvEdmonton.ca'],
    'CityNewsVancouver.ca@SD': ['CitytvVancouver.ca@HD', 'CitytvVancouver.ca@SD', 'CitytvVancouver.ca'],
}

CHECK_STREAMS = True
LIVE_TIMEOUT = 5.0
LIVE_WORKERS = 60
MIN_PRIMARY_SOURCES_OK = 5
MIN_CHANNELS = 300
HISTORY_WINDOW = 10


def get_bytes(url, timeout=90, limit=None, retries=3, extra_headers=None):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 'Accept': '*/*'}
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, headers=headers)
    last_exc = None
    attempts = 1 if limit else retries
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if getattr(resp, 'status', 200) >= 400:
                    raise urllib.error.HTTPError(url, resp.status, 'HTTP Error', resp.headers, None)
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
    return data.decode('utf-8-sig', errors='ignore')


def is_unreliable_url(url):
    low = url.lower()
    path = urllib.parse.urlparse(low).path
    if path.endswith(VOD_EXTENSIONS) or '/movie/' in path or '/vod/' in path:
        return True
    if any(tok in low for tok in EXPIRING_TOKEN_MARKERS):
        return True
    return False


def extract_vlc_headers(extras):
    headers = {}
    for line in extras:
        if line.startswith('#EXTVLCOPT:http-user-agent='):
            headers['User-Agent'] = line.split('=', 1)[1].strip()
        elif line.startswith('#EXTVLCOPT:http-referrer='):
            headers['Referer'] = line.split('=', 1)[1].strip()
    return headers


def build_tivimate_url(url, extras):
    if '|' in url:
        return url
    headers = extract_vlc_headers(extras)
    if not headers:
        return url
    params = '&'.join(f'{k}={urllib.parse.quote(v, safe="")}' for k, v in headers.items())
    return f'{url}|{params}'


def parse_max_height(m3u8_text):
    heights = [int(h) for h in re.findall(r'RESOLUTION=\d+x(\d+)', m3u8_text)]
    return max(heights) if heights else 0


def looks_like_markup(data):
    head = data[:512].lstrip(b'\xef\xbb\xbf \r\n\t').lower()
    return head.startswith((b'<', b'{', b'[')) or b'<html' in head or b'<!doctype' in head


def looks_like_media(data):
    if len(data) < 188 or looks_like_markup(data):
        return False
    if data[0] == 0x47 or data[4:8] in (b'ftyp', b'styp', b'moof') or data[:3] in (b'ID3', b'FLV'):
        return True
    sample = data[:256]
    printable = sum(1 for b in sample if 32 <= b < 127 or b in (9, 10, 13))
    return printable / len(sample) < 0.6  # encrypted/binary segments


def probe_stream(url, extras=None):
    """Returns (alive: bool, max_height: int, latency_ms: int)."""
    base_url = url.split('|', 1)[0]
    if not base_url.startswith(('http://', 'https://')) or is_unreliable_url(base_url):
        return False, 0, 9999
    req_headers = extract_vlc_headers(extras or [])
    t0 = time.monotonic()
    max_height = 0
    try:
        current_url = base_url
        for _ in range(3):
            data, final_url = get_bytes(current_url, timeout=LIVE_TIMEOUT, limit=65536, extra_headers=req_headers)
            if not data:
                return False, 0, 9999
            text = data.decode('utf-8', errors='ignore')
            if not text.lstrip().startswith('#EXTM3U'):
                ok = looks_like_media(data)
                return ok, max_height, int((time.monotonic() - t0) * 1000) if ok else 9999
            if '#EXT-X-ENDLIST' in text or 'PLAYLIST-TYPE:VOD' in text:
                return False, 0, 9999  # VOD, not live
            max_height = max(max_height, parse_max_height(text))
            next_uri = next(
                (ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith('#')),
                None,
            )
            if not next_uri:
                return False, 0, 9999
            current_url = urllib.parse.urljoin(final_url, next_uri)
            if '#EXT-X-STREAM-INF' not in text and '#EXTINF:' in text:
                seg_data, _ = get_bytes(current_url, timeout=LIVE_TIMEOUT, limit=16384, extra_headers=req_headers)
                if looks_like_media(seg_data):
                    return True, max_height, int((time.monotonic() - t0) * 1000)
                return False, 0, 9999
        return False, 0, 9999
    except (OSError, ValueError, TimeoutError, urllib.error.URLError, http.client.HTTPException):
        return False, 0, 9999


def load_history():
    if HISTORY_PATH.exists():
        try:
            return json.loads(HISTORY_PATH.read_text(encoding='utf-8'))
        except Exception:
            return {}
    return {}


def save_history(history):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    # Keep only active/recent streams to avoid repository bloat
    pruned = {u: bits for u, bits in history.items() if '1' in bits[-HISTORY_WINDOW:]}
    HISTORY_PATH.write_text(json.dumps(pruned, separators=(',', ':')) + '\n', encoding='utf-8')


def compute_score(entry, uptime_ratio, height, latency_ms):
    """Score stream 0-100: Uptime (45), Metadata (25), Resolution (15), Speed (15)."""
    uptime_pts = 45.0 * uptime_ratio
    meta_pts = (15.0 if entry['tvgid'] else 0.0) + (10.0 if entry['logo'] else 0.0)
    if height >= 1080:
        res_pts = 15.0
    elif height >= 720:
        res_pts = 11.0
    elif height >= 480:
        res_pts = 7.0
    else:
        res_pts = 5.0
    if latency_ms <= 600:
        speed_pts = 15.0
    elif latency_ms <= 1500:
        speed_pts = 11.0
    elif latency_ms <= 3000:
        speed_pts = 7.0
    else:
        speed_pts = 3.0
    return round(uptime_pts + meta_pts + res_pts + speed_pts, 1)


def attr(line, key):
    m = re.search(r'(?<!\w)' + re.escape(key) + r'="([^"]*)"', line)
    return m.group(1) if m else ''


def put(line, key, value):
    value = str(value).replace('"', '').replace('\n', ' ')
    line = re.sub(r'\s*(?<!\w)' + re.escape(key) + r'=(?:"[^"]*"|\'[^\']*\')', '', line)
    return line.replace('#EXTINF:', f'#EXTINF: {key}="{value}" ', 1)


def norm_title(name):
    cleaned = re.sub(r'\([^)]*\)|\[[^\]]*\]', '', name.lower())
    cleaned = re.sub(r'\b(hd|sd|fhd|uhd|4k|1080p|720p|live|tv|channel)\b', '', cleaned)
    return re.sub(r'[^a-z0-9]+', '', cleaned)


def norm_epg_name(name):
    cleaned = re.sub(r'\([^)]*\)|\[[^\]]*\]', '', name.lower())
    cleaned = re.sub(r'\b(hd|sd|fhd|uhd|4k|1080p|720p|live|tv|channel|east|west|pacific|atlantic|national)\b', '', cleaned)
    return re.sub(r'[^a-z0-9]+', '', cleaned)


def has_word(text, *terms):
    return any(re.search(r'\b' + re.escape(term) + r'\b', text) for term in terms)


def detect_lang(text, country_code=''):
    s = text.lower()
    for word, label in [
        ('urdu', 'Urdu'),
        ('punjabi', 'Punjabi'),
        ('hindi', 'Hindi'),
        ('tamil', 'Tamil'),
        ('telugu', 'Telugu'),
        ('bengali', 'Bengali'),
        ('malayalam', 'Malayalam'),
        ('english', 'English'),
    ]:
        if word in s:
            return label
    if country_code in ('us', 'ca'):
        return 'English'
    if country_code == 'pk':
        return 'Urdu'
    return 'Other / Unspecified'


def classify_live_group(name, old_group, country_code=''):
    og = (old_group or '').strip().lower()
    s = f'{name} {og}'.lower()

    if og == 'sports' or has_word(s, *SPORTS_KEYWORDS):
        return 'Live Sports'
    if og in ('international news', 'news bd') or has_word(s, *NEWS_KEYWORDS):
        return 'International News'
    if og == 'movies' or has_word(s, 'movie', 'movies', 'cinema', 'film', 'films', 'bollywood', 'lollywood'):
        return 'Movies'
    if og == 'india':
        return 'India'
    return COUNTRIES.get(country_code)  # None -> dropped, no USA default


def resolve_tvgid(tvgid, name, code, guide_index, scoped_site_to_id, fast=False):
    if fast:
        return tvgid
    if tvgid and (tvgid in guide_index or tvgid.split('@', 1)[0] in guide_index):
        return tvgid
    n = norm_epg_name(name)
    for cc in ([code] if code in COUNTRIES else list(COUNTRIES)):
        hit = scoped_site_to_id.get((cc, n))
        if hit:
            return hit
    return tvgid


def parse_m3u_blocks(lines):
    for i, line in enumerate(lines):
        if not line.startswith('#EXTINF:'):
            continue
        j = i + 1
        extras = []
        while j < len(lines) and lines[j].startswith('#') and not lines[j].startswith('#EXTINF:'):
            extras.append(lines[j])
            j += 1
        if j >= len(lines) or lines[j].startswith('#'):
            continue
        yield line, extras, lines[j].strip()


def format_extinf(e, number, group_name):
    line = put(e['line'], 'group-title', group_name)
    line = put(line, 'tvg-chno', str(number))
    if not attr(line, 'tvg-name'):
        line = put(line, 'tvg-name', e['name'])
    if e['tvgid']:
        line = put(line, 'tvg-id', e['tvgid'])
    logo = e['logo'] or FALLBACK_LOGOS.get(group_name, FALLBACK_LOGOS['Movies'])
    line = put(line, 'tvg-logo', logo)
    final_url = build_tivimate_url(e['url'], e['extras'])
    return '\n'.join([line, *e['extras'], final_url]) + '\n'


def write_playlist(path, items):
    header = f'#EXTM3U x-tvg-url="{EPG_PUBLIC_URL}"\n'
    path.write_text(
        header + ''.join(format_extinf(e, num, grp) for e, num, grp in items),
        encoding='utf-8',
    )


def main():
    guides = json.loads(fetch_text('https://iptv-org.github.io/api/guides.json'))
    guide_index = collections.defaultdict(list)
    scoped_site_to_id = {}

    for g in guides:
        channel = g.get('channel')
        feed = g.get('feed')
        site = g.get('site')
        site_id = g.get('site_id')
        site_name = g.get('site_name') or ''
        if not channel or not site or not site_id:
            continue
        full_id = f'{channel}@{feed}' if feed else channel
        if feed:
            guide_index[full_id].append((True, g))
        guide_index[channel].append((False, g))

        if site not in BLOCKED_SITES and site_name:
            nsn = norm_epg_name(site_name)
            cc_match = re.search(r'\.([a-z]{2})(?:@|$)', full_id.lower())
            cc = cc_match.group(1) if cc_match else ''
            if nsn and cc in COUNTRIES:
                scoped_site_to_id.setdefault((cc, nsn), full_id)

    fetched = []
    errors = []
    primary_ok = 0
    name_to_tvgid = {}
    name_to_logo = {}

    # 1. Primary country sources
    for priority, (code, url) in enumerate(SOURCES):
        try:
            lines = fetch_text(url).splitlines()
            primary_ok += 1
        except Exception as exc:
            errors.append(f'{url}: {exc}')
            continue

        for line, extras, stream_url in parse_m3u_blocks(lines):
            if is_unreliable_url(stream_url):
                continue
            name = line.split(',', 1)[-1].strip()
            n_epg = norm_epg_name(name)
            n_title = norm_title(name)
            tvgid = attr(line, 'tvg-id') or scoped_site_to_id.get((code, n_epg), '')
            logo = attr(line, 'tvg-logo')
            if n_epg and tvgid:
                name_to_tvgid.setdefault((code, n_epg), tvgid)
                name_to_tvgid.setdefault(('', n_epg), tvgid)
            if n_title and logo:
                name_to_logo.setdefault(n_title, logo)

            old_group = attr(line, 'group-title')
            fetched.append({
                'line': line,
                'extras': extras,
                'url': stream_url,
                'name': name,
                'tvgid': tvgid,
                'logo': logo,
                'group': classify_live_group(name, old_group, code),
                'language': detect_lang(f'{name} {old_group} {attr(line, "tvg-language")}', code),
                'priority': priority,
                'code': code,
                'fast': False,
            })

    if primary_ok < MIN_PRIMARY_SOURCES_OK:
        raise RuntimeError(f'Only {primary_ok}/{len(SOURCES)} primary sources reachable; aborting to preserve existing playlist')

    # 2. Global active & extra live TV sources
    for active_url in GLOBAL_ACTIVE_SOURCES + EXTRA_SOURCES:
        try:
            lines = fetch_text(active_url).splitlines()
        except Exception as exc:
            errors.append(f'{active_url}: {exc}')
            continue

        is_ca_fast = any(tag in active_url for tag in ('plutotv_ca', 'samsungtvplus_ca', 'plex_ca'))
        is_in_source = 'Hindi_Punjabi' in active_url or 'samsungtvplus_in' in active_url or any(tag in active_url for tag in ('/hin.m3u', '/pan.m3u', '/tam.m3u', '/tel.m3u'))
        is_pk_source = '/urd.m3u' in active_url

        for line, extras, stream_url in parse_m3u_blocks(lines):
            if is_unreliable_url(stream_url):
                continue
            name = line.split(',', 1)[-1].strip()
            old_group = attr(line, 'group-title')
            tvg_lang = attr(line, 'tvg-language')
            og_lower = old_group.lower().strip()
            n_epg = norm_epg_name(name)
            n_title = norm_title(name)
            s = f'{name} {old_group} {tvg_lang}'.lower()

            if has_word(s, *EXCLUDED_LANG_KEYWORDS):
                continue

            matched_code = None
            if is_ca_fast:
                matched_code = 'ca'
            elif is_in_source:
                matched_code = 'in'
            elif is_pk_source:
                matched_code = 'pk'
            else:
                tag_match = re.search(r'[\[\(\|]\s*(ca|us|in|pk)\s*[\]\)\|]', s)
                if tag_match:
                    matched_code = tag_match.group(1)
                else:
                    for code, (_, keywords) in COUNTRY_MATCHERS.items():
                        if has_word(s, *keywords):
                            matched_code = code
                            break

            tvgid = (
                attr(line, 'tvg-id')
                or (name_to_tvgid.get((matched_code, n_epg)) if matched_code else '')
                or name_to_tvgid.get(('', n_epg), '')
            )
            logo = attr(line, 'tvg-logo') or name_to_logo.get(n_title, '')

            is_sports = og_lower == 'sports' or has_word(s, *SPORTS_KEYWORDS)
            is_news = og_lower in ('international news', 'news bd') or has_word(s, *NEWS_KEYWORDS)
            is_allowed_group = og_lower in ('english', 'india')
            is_allowed_category = og_lower in (
                'movies', 'kids', 'documentary', 'music', 'entertainment',
                'general', 'family', 'education', 'culture', 'comedy', 'animation',
            )

            if not (is_sports or is_news or matched_code or is_allowed_group or is_allowed_category):
                continue

            fetched.append({
                'line': line,
                'extras': extras,
                'url': stream_url,
                'name': name,
                'tvgid': tvgid,
                'logo': logo,
                'group': classify_live_group(name, old_group, matched_code or ''),
                'language': detect_lang(s, matched_code or ''),
                'priority': 10,
                'code': matched_code or '',
                'fast': active_url in FAST_SOURCES,
            })

    fetched = [e for e in fetched if e['group']]
    for e in fetched:
        e['tvgid'] = resolve_tvgid(e['tvgid'], e['name'], e.get('code', ''),
                                   guide_index, scoped_site_to_id, e.get('fast', False))
    if not fetched:
        raise RuntimeError('No source playlists available')

    unique_urls = {}
    for e in fetched:
        unique_urls.setdefault(e['url'], e)
    candidates = list(unique_urls.values())

    history = load_history()
    grace_retained = 0

    if CHECK_STREAMS:
        with concurrent.futures.ThreadPoolExecutor(max_workers=LIVE_WORKERS) as pool:
            results = list(pool.map(lambda item: probe_stream(item['url'], item['extras']), candidates))

        healthy = []
        for e, (alive, height, latency_ms) in zip(candidates, results):
            u = e['url']
            prev_bits = history.get(u, '')[-HISTORY_WINDOW:]
            new_bits = (prev_bits + ('1' if alive else '0'))[-HISTORY_WINDOW:]
            history[u] = new_bits
            uptime_ratio = new_bits.count('1') / len(new_bits)

            # Retain high-reliability streams for 1 grace run on temporary hiccups
            keep = alive or (len(prev_bits) >= 3 and uptime_ratio >= 0.70 and prev_bits.endswith('1'))
            if keep:
                if not alive:
                    grace_retained += 1
                e['score'] = compute_score(e, uptime_ratio, height, latency_ms)
                e['resolution'] = f'{height}p' if height else 'unknown'
                healthy.append(e)
        candidates = healthy
    else:
        for e in candidates:
            e['score'] = 50.0
            e['resolution'] = 'unknown'

    # Rank duplicates by highest reliability score first, then source priority
    candidates.sort(key=lambda e: (-e['score'], e['priority']))
    primary = []
    backups = []
    seen_titles = set()

    for e in candidates:
        key = (e['group'], norm_title(e['name']) or e['name'].casefold())
        if key in seen_titles:
            backups.append(e)
        else:
            seen_titles.add(key)
            primary.append(e)

    # Filter out any stray group names not in the allowed 7 GROUPS
    allowed_groups = set(GROUPS)
    primary = [e for e in primary if e['group'] in allowed_groups]

    if len(primary) < MIN_CHANNELS:
        raise RuntimeError(f'Only {len(primary)} unique playable channels (minimum {MIN_CHANNELS})')

    save_history(history)

    primary.sort(key=lambda e: (GROUPS.index(e['group']), e['name'].casefold()))

    numbered = [(e, number, e['group']) for number, e in enumerate(primary, 1)]

    write_playlist(ROOT / 'combined.m3u', numbered)
    write_playlist(ROOT / 'alternates.m3u', [(e, i, e['group']) for i, e in enumerate(backups, 1)])
    for lang_name in ['English', 'Hindi', 'Urdu', 'Punjabi', 'Tamil', 'Telugu']:
        write_playlist(
            ROOT / f'language-{lang_name.lower()}.m3u',
            [(e, n, g) for e, n, g in numbered if e['language'] == lang_name],
        )

    ids = {e['tvgid'] for e in primary if e['tvgid']}
    selected = {}
    for mid in sorted(ids):
        base_id = mid.split('@', 1)[0]
        lookup_keys = list(dict.fromkeys([
            mid,
            base_id,
            f'{base_id}@HD',
            f'{base_id}@SD',
            f'{base_id}@East',
            f'{base_id}@National',
            *EPG_ALIASES.get(mid, []),
        ]))

        best_score = None
        best_guide = None
        for alias_idx, key in enumerate(lookup_keys):
            for exact_feed, g in guide_index.get(key, []):
                site = g['site']
                if site in BLOCKED_SITES:
                    continue
                score = (
                    1 if alias_idx == 0 else 0,
                    SITE_PRIORITY.get(site, 1),
                    2 if exact_feed else 1,
                    1 if g.get('lang') == 'en' else 0,
                )
                if best_score is None or score > best_score:
                    best_score = score
                    best_guide = g

        if best_guide is not None:
            selected[mid] = best_guide

    if not selected:
        raise RuntimeError('No EPG mappings available')

    root = ET.Element('channels')
    for mid, g in sorted(selected.items()):
        el = ET.SubElement(
            root,
            'channel',
            {
                'site': g['site'],
                'lang': g.get('lang') or 'en',
                'xmltv_id': mid,
                'site_id': str(g['site_id']),
            },
        )
        el.text = g.get('site_name') or mid

    ET.indent(root)
    ET.ElementTree(root).write(ROOT / 'epg.channels.xml', encoding='utf-8', xml_declaration=True)

    unmatched = [
        {'name': e['name'], 'group': e['group'], 'tvg_id': e['tvgid']}
        for e in primary
        if not e['tvgid'] or e['tvgid'] not in selected
    ]
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UNMATCHED_EPG_PATH.write_text(json.dumps(unmatched[:500], indent=2) + '\n', encoding='utf-8')

    report = {
        'generated_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'primary_sources_ok': f'{primary_ok}/{len(SOURCES)}',
        'source_entries': len(fetched),
        'unique_urls': len(unique_urls),
        'passed_health_checks': len(candidates),
        'grace_retained_streams': grace_retained,
        'unique_primary_channels': len(primary),
        'alternate_streams_saved': len(backups),
        'average_stream_score': round(sum(e['score'] for e in primary) / max(len(primary), 1), 1),
        'groups': dict(collections.Counter(e['group'] for e in primary)),
        'unique_tvg_ids': len(ids),
        'epg_mapped_ids': len(selected),
        'epg_mapping_percent': round(100 * len(selected) / max(len(ids), 1), 1),
        'source_errors': errors,
    }
    (ROOT / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'BUILD FAILED: {exc}', file=sys.stderr)
        sys.exit(1)
