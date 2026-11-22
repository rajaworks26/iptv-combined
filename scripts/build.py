import collections
import concurrent.futures
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parents[1]

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

MOVIE_SOURCES = [
    'https://raw.githubusercontent.com/Zaman-Topu/Ip-tv-Collection/main/FINAL_MOVIES_COMPLETE.m3u',
]

COUNTRY_MATCHERS = {
    'ca': ('Canada', ['canada', 'canadian', 'ca |', '[ca]', '(ca)', 'toronto', 'cp24', 'cbc', 'ctv', 'citytv', 'global']),
    'us': ('USA', ['usa', 'united states', 'us |', '[us]', '(us)']),
    'in': ('India', ['india', 'indian', 'hindi', 'punjabi', 'tamil', 'telugu', 'malayalam', 'bengali', 'in |', '[in]']),
    'pk': ('Pakistan', ['pakistan', 'pakistani', 'urdu', 'pk |', '[pk]', 'geo', 'ary', 'hum', 'samaa', 'ptv']),
}

SPORTS_KEYWORDS = (
    'sport', 'sports', 'cricket', 'football', 'soccer', 'espn', 'bein',
    'sky sports', 'star sports', 't sports', 'ten sports', 'sony ten',
    'f1', 'formula 1', 'dazn', 'tsn', 'sportsnet', 'ptv sports', 'geo super',
    'a sports', 'willow', 'fox sports', 'cbs sports', 'nbc sports', 'golf', 'tennis', 'racing'
)

NEWS_KEYWORDS = (
    'news', 'cnn', 'bbc', 'al jazeera', 'sky news', 'euronews', 'france 24',
    'dw', 'msnbc', 'fox news', 'cnbc', 'bloomberg', 'cp24', 'cbc news', 'ctv news',
    'citynews', 'geo news', 'ary news', 'hum news', 'samaa', 'dunya news', 'express news',
    'ndtv', 'india today', 'aaj tak', 'republic', 'wion', 'times now'
)

# Deterministic TiviMate sidebar order & channel number blocks
GROUP_ORDER = {
    'Live Sports': (1, 100),
    'International News': (2, 200),
    'Canada': (3, 300),
    'USA': (4, 400),
    'India': (5, 500),
    'Pakistan': (6, 600),
    'Movies | Hollywood & English': (7, 1000),
    'Movies | Bollywood & Hindi': (8, 2000),
    'Movies | Pakistani & Urdu': (9, 3000),
    'Movies | Action & General': (10, 4000),
}

# Set True to keep 1 best stream per channel/movie title (zero duplicate names in TiviMate)
DEDUPLICATE_BY_TITLE = True

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

CHECK_STREAM_HEALTH = True
STREAM_TIMEOUT = 2.5
MAX_WORKERS = 120


def fetch(url, timeout=90):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8-sig', errors='ignore')


def is_stream_alive(url, check_segment=True):
    if not url.startswith(('http://', 'https://')):
        return False
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'Accept': '*/*',
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=STREAM_TIMEOUT) as resp:
            if getattr(resp, 'status', 200) >= 400:
                return False
            if not check_segment:
                return True
            body = resp.read(2048).decode('utf-8', errors='ignore')
            if not body:
                return False
            if body.lstrip().startswith('#EXTM3U'):
                next_uri = next(
                    (ln.strip() for ln in body.splitlines() if ln.strip() and not ln.startswith('#')),
                    None,
                )
                if not next_uri:
                    return False
                seg_url = urljoin(resp.geturl(), next_uri)
                seg_req = urllib.request.Request(seg_url, headers=headers)
                with urllib.request.urlopen(seg_req, timeout=STREAM_TIMEOUT) as seg_resp:
                    return getattr(seg_resp, 'status', 200) < 400 and len(seg_resp.read(256)) > 0
            return True
    except Exception:
        return False


def attr(line, key):
    m = re.search(r'(?<!\w)' + re.escape(key) + r'="([^"]*)"', line)
    return m.group(1) if m else ''


def put(line, key, value):
    value = str(value).replace('"', '').replace('\n', ' ')
    if re.search(r'(?<!\w)' + re.escape(key) + r'="[^"]*"', line):
        return re.sub(
            r'(?<!\w)' + re.escape(key) + r'="[^"]*"',
            lambda m: key + '="' + value + '"',
            line,
            count=1,
        )
    return line.replace('#EXTINF:', f'#EXTINF: {key}="{value}" ', 1)


def normalize_name(name):
    cleaned = re.sub(r'\([^)]*\)|\[[^\]]*\]', '', name.lower())
    cleaned = re.sub(r'\b(hd|sd|fhd|uhd|4k|1080p|720p|live|tv|channel|us|uk|ca|in|pk|usa|india|pakistan|canada)\b', '', cleaned)
    return re.sub(r'[^a-z0-9]+', '', cleaned)


def has_word(text, *terms):
    return any(re.search(r'\b' + re.escape(term) + r'\b', text) for term in terms)


def lang(text, country_code=''):
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
        if country_code == 'pk' or has_word(s, 'pakistani', 'pakistan', 'lollywood', 'urdu'):
            return 'Movies | Pakistani & Urdu'
        if country_code == 'in' or has_word(s, 'bollywood', 'hindi', 'indian', 'punjabi', 'tamil', 'telugu'):
            return 'Movies | Bollywood & Hindi'
        return 'Movies | Hollywood & English'

    if og == 'india' or country_code == 'in':
        return 'India'
    if country_code in COUNTRIES:
        return COUNTRIES[country_code]
    return 'USA'


def classify_movie_group(name, old_group):
    s = f'{name} {old_group}'.lower()
    if has_word(s, 'pakistani', 'pakistan', 'lollywood', 'urdu'):
        return 'Movies | Pakistani & Urdu'
    if has_word(s, 'bollywood', 'hindi', 'indian', 'punjabi', 'tamil', 'telugu', 'malayalam', 'south indian'):
        return 'Movies | Bollywood & Hindi'
    if has_word(s, 'hollywood', 'english', 'american', 'uk'):
        return 'Movies | Hollywood & English'
    return 'Movies | Action & General'


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


raw_entries = []
seen_pairs = set()
seen_urls = set()
name_to_tvgid = {}
name_to_logo = {}
duplicates = 0

# 1. Primary country-specific sources (also builds EPG & logo lookup tables)
for code, source_url in SOURCES:
    try:
        lines = fetch(source_url).splitlines()
    except Exception as exc:
        print(f'Warning: failed to fetch {source_url}: {exc}')
        continue

    for line, extras, url in parse_m3u_blocks(lines):
        name = line.split(',', 1)[-1].strip()
        tvgid = attr(line, 'tvg-id')
        logo = attr(line, 'tvg-logo')
        norm = normalize_name(name)
        if norm:
            if tvgid and norm not in name_to_tvgid:
                name_to_tvgid[norm] = tvgid
            if logo and norm not in name_to_logo:
                name_to_logo[norm] = logo

        key = (tvgid, url)
        if key in seen_pairs or url in seen_urls:
            duplicates += 1
            continue
        seen_pairs.add(key)
        seen_urls.add(url)

        old_group = attr(line, 'group-title')
        menu_group = classify_live_group(name, old_group, code)
        language = lang(f'{name} {old_group} {attr(line, "tvg-language")}', code)
        raw_entries.append((line, extras, url, menu_group, language, name, tvgid, True))

# 2. Secondary global active list (with EPG & logo backfill)
for active_url in GLOBAL_ACTIVE_SOURCES:
    try:
        lines = fetch(active_url).splitlines()
    except Exception as exc:
        print(f'Warning: failed to fetch {active_url}: {exc}')
        continue

    for line, extras, url in parse_m3u_blocks(lines):
        if url in seen_urls:
            duplicates += 1
            continue

        name = line.split(',', 1)[-1].strip()
        old_group = attr(line, 'group-title')
        og_lower = old_group.lower().strip()
        norm = normalize_name(name)
        tvgid = attr(line, 'tvg-id') or name_to_tvgid.get(norm, '')
        logo = attr(line, 'tvg-logo') or name_to_logo.get(norm, '')
        s = f'{name} {old_group}'.lower()

        matched_code = None
        for code, (_, keywords) in COUNTRY_MATCHERS.items():
            if any(kw in f'{s} {tvgid.lower()}' for kw in keywords):
                matched_code = code
                break

        is_sports = og_lower == 'sports' or has_word(s, *SPORTS_KEYWORDS)
        is_news = og_lower in ('international news', 'news bd') or has_word(s, *NEWS_KEYWORDS)
        is_allowed_group = og_lower in ('english', 'india')

        if not (is_sports or is_news or matched_code or is_allowed_group):
            continue

        seen_urls.add(url)
        seen_pairs.add((tvgid, url))
        menu_group = classify_live_group(name, old_group, matched_code or '')
        language = lang(f'{name} {old_group} {attr(line, "tvg-language")}', matched_code or '')
        if tvgid:
            line = put(line, 'tvg-id', tvgid)
        if logo:
            line = put(line, 'tvg-logo', logo)
        raw_entries.append((line, extras, url, menu_group, language, name, tvgid, True))

# 3. Movies consolidated into 4 clean folders (no tvg-id so EPG stays fast)
for movie_url in MOVIE_SOURCES:
    try:
        lines = fetch(movie_url).splitlines()
    except Exception as exc:
        print(f'Warning: failed to fetch {movie_url}: {exc}')
        continue

    for line, extras, url in parse_m3u_blocks(lines):
        if url in seen_urls:
            duplicates += 1
            continue

        seen_urls.add(url)
        name = line.split(',', 1)[-1].strip()
        old_group = attr(line, 'group-title')
        menu_group = classify_movie_group(name, old_group)
        line = put(line, 'tvg-id', '')
        language = lang(f'{name} {old_group} {attr(line, "tvg-language")}')
        raw_entries.append((line, extras, url, menu_group, language, name, '', False))

if not raw_entries:
    raise RuntimeError('No channels found from upstream sources')

dead_removed = 0
if CHECK_STREAM_HEALTH:
    url_check_mode = {}
    for item in raw_entries:
        u, seg = item[2], item[7]
        url_check_mode[u] = url_check_mode.get(u, False) or seg

    check_items = list(url_check_mode.items())
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        results = dict(
            zip(
                (u for u, _ in check_items),
                pool.map(lambda pair: is_stream_alive(pair[0], pair[1]), check_items),
            )
        )
    alive_entries = []
    for item in raw_entries:
        if results.get(item[2], False):
            alive_entries.append(item)
        else:
            dead_removed += 1
else:
    alive_entries = raw_entries

if not alive_entries:
    raise RuntimeError('All streams failed health checks')

# Deduplicate by normalized title within each group (preferring streams with tvg-id & logo)
if DEDUPLICATE_BY_TITLE:
    alive_entries.sort(
        key=lambda e: (
            0 if e[6] else 1,
            0 if attr(e[0], 'tvg-logo') else 1,
        )
    )
    entries = []
    seen_titles = set()
    for item in alive_entries:
        title_key = (item[3], normalize_name(item[5]) or item[5].lower())
        if title_key in seen_titles:
            duplicates += 1
            continue
        seen_titles.add(title_key)
        entries.append(item)
else:
    entries = alive_entries

# Sort entries cleanly by GROUP_ORDER, then alphabetically by name, and assign tvg-chno
entries.sort(key=lambda e: (GROUP_ORDER.get(e[3], (99, 9000))[0], e[5].lower()))

numbered_entries = []
group_counters = {}
for line, extras, url, menu_group, language, name, tvgid, check_seg in entries:
    base_chno = GROUP_ORDER.get(menu_group, (99, 9000))[1]
    chno = group_counters.get(menu_group, base_chno)
    group_counters[menu_group] = chno + 1
    line = put(line, 'group-title', menu_group)
    line = put(line, 'tvg-chno', chno)
    numbered_entries.append((line, extras, url, menu_group, language, name, tvgid))

entries = numbered_entries
ids = {e[6] for e in entries if e[6]}
stats = collections.Counter(e[3] for e in entries)
languages = collections.Counter(e[4] for e in entries)


def write_playlist(path, items):
    path.write_text(
        '#EXTM3U\n' + ''.join('\n'.join([a, *b, c]) + '\n' for a, b, c, *_ in items),
        encoding='utf-8',
    )


write_playlist(ROOT / 'combined.m3u', entries)
write_playlist(
    ROOT / 'favorites.m3u',
    [e for e in entries if e[6] in set(json.loads((ROOT / 'favorites.json').read_text()))]
    if (ROOT / 'favorites.json').exists()
    else [],
)

for language in ['English', 'Hindi', 'Urdu', 'Punjabi', 'Tamil', 'Telugu']:
    write_playlist(
        ROOT / ('language-' + language.lower() + '.m3u'),
        [e for e in entries if e[4] == language],
    )

try:
    guides = json.loads(fetch('https://iptv-org.github.io/api/guides.json'))
except Exception as exc:
    raise RuntimeError('Guide mapping API unavailable; existing published files are untouched') from exc

guide_index = collections.defaultdict(list)
for g in guides:
    channel = g.get('channel')
    feed = g.get('feed')
    site = g.get('site')
    site_id = g.get('site_id')
    if not channel or not site or not site_id:
        continue
    if feed:
        guide_index[f'{channel}@{feed}'].append((True, g))
    guide_index[channel].append((False, g))

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

report = {
    'menu_groups': dict(stats),
    'total_channels': len(entries),
    'duplicate_entries_removed': duplicates,
    'dead_streams_removed': dead_removed,
    'unique_tvg_ids': len(ids),
    'epg_mapped_ids': len(selected),
    'epg_mapping_percent': round(100 * len(selected) / max(len(ids), 1), 1),
    'language_estimates_from_names': dict(languages),
    'note': 'Title-deduplicated, alphabetically sorted, channel-numbered (tvg-chno) playlist with EPG & logo backfill.',
}
(ROOT / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
