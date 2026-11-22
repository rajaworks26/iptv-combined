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

# Primary (iptv-org) and curated secondary (Free-TV/IPTV) M3U sources
SOURCES = [
    ('us', 'https://iptv-org.github.io/iptv/countries/us.m3u'),
    ('ca', 'https://iptv-org.github.io/iptv/countries/ca.m3u'),
    ('in', 'https://iptv-org.github.io/iptv/countries/in.m3u'),
    ('pk', 'https://iptv-org.github.io/iptv/countries/pk.m3u'),
    ('us', 'https://raw.githubusercontent.com/Free-TV/IPTV/master/playlists/playlist_usa.m3u8'),
    ('ca', 'https://raw.githubusercontent.com/Free-TV/IPTV/master/playlists/playlist_canada.m3u8'),
    ('in', 'https://raw.githubusercontent.com/Free-TV/IPTV/master/playlists/playlist_india.m3u8'),
]

# Secondary global active playlist (filtered to target countries + Global Sports & Intl News)
GLOBAL_ACTIVE_SOURCES = [
    'https://raw.githubusercontent.com/Zaman-Topu/Ip-tv-Collection/main/FINAL_IPTV_ACTIVE.m3u',
]

# Movies playlist merged directly into combined.m3u under "Movies | ..." groups
MOVIE_SOURCES = [
    'https://raw.githubusercontent.com/Zaman-Topu/Ip-tv-Collection/main/FINAL_MOVIES_COMPLETE.m3u',
]

COUNTRY_MATCHERS = {
    'us': ('USA', ['usa', 'united states', 'us |', '[us]', '(us)']),
    'ca': ('Canada', ['canada', 'canadian', 'ca |', '[ca]', '(ca)']),
    'in': ('India', ['india', 'indian', 'hindi', 'punjabi', 'tamil', 'telugu', 'malayalam', 'bengali', 'in |', '[in]']),
    'pk': ('Pakistan', ['pakistan', 'pakistani', 'urdu', 'pk |', '[pk]']),
}

# Broken or Cloudflare-blocked EPG scrapers to avoid when alternatives exist
BLOCKED_SITES = {'tvtv.us', 'distro.tv'}

# Preferred reliable EPG providers (higher number = higher priority)
SITE_PRIORITY = {
    'tvpassport.com': 5,
    'tvguide.com': 5,
    'ontvtonight.com': 4,
    'i.mjh.nz': 4,
    'tataplay.com': 4,
    'airtelxstream.in': 4,
    'tvhebdo.com': 3,
}

# Regional EPG aliases so local CityNews feeds map to their local Citytv schedules
EPG_ALIASES = {
    'CityNewsToronto.ca@SD': ['CitytvToronto.ca@HD', 'CitytvToronto.ca@SD', 'CitytvToronto.ca'],
    'CityNewsCalgary.ca@SD': ['CitytvCalgary.ca@HD', 'CitytvCalgary.ca@SD', 'CitytvCalgary.ca'],
    'CityNewsEdmonton.ca@SD': ['CitytvEdmonton.ca@HD', 'CitytvEdmonton.ca@SD', 'CitytvEdmonton.ca'],
    'CityNewsVancouver.ca@SD': ['CitytvVancouver.ca@HD', 'CitytvVancouver.ca@SD', 'CitytvVancouver.ca'],
}

# Fast parallel stream health verification settings (Option A)
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
            # If HLS playlist (.m3u8), verify first sub-playlist or .ts segment actually opens
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
    value = value.replace('"', '').replace('\n', ' ')
    if re.search(r'(?<!\w)' + re.escape(key) + r'="[^"]*"', line):
        return re.sub(
            r'(?<!\w)' + re.escape(key) + r'="[^"]*"',
            lambda m: key + '="' + value + '"',
            line,
            count=1,
        )
    return line.replace('#EXTINF:', f'#EXTINF: {key}="{value}" ', 1)


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


def category(name, old, country_code=''):
    s = (name + ' ' + old).lower()

    def has(*terms):
        return any(re.search(r'\b' + re.escape(term) + r'\b', s) for term in terms)

    if has('news', 'current affairs'):
        return 'News'
    if has('sport', 'sports', 'cricket', 'football', 'soccer', 'racing', 'golf', 'tennis'):
        return 'Sports'

    is_movie = has('movie', 'movies', 'cinema', 'film', 'films', 'bollywood', 'lollywood')
    is_drama = has('drama', 'dramas', 'serial', 'series', 'soap opera', 'tv shows')
    if is_movie:
        if country_code == 'pk' or has('pakistani', 'pakistan', 'lollywood', 'urdu'):
            return 'Pakistani Movies'
        if country_code == 'in' or has('bollywood', 'hindi', 'indian', 'punjabi', 'tamil', 'telugu'):
            return 'Bollywood & Indian Movies'
        return 'Hollywood & English Movies'
    if is_drama:
        if country_code == 'pk' or has('pakistani', 'pakistan', 'urdu'):
            return 'Pakistani Dramas'
        if country_code == 'in' or has('indian', 'hindi', 'punjabi', 'tamil', 'telugu'):
            return 'Indian TV Series'
        return 'English TV Series'

    for words, label in [
        (['kids', 'cartoon', 'children'], 'Kids'),
        (['music', 'radio'], 'Music'),
        (['religion', 'islam', 'quran', 'faith', 'christian', 'devotional'], 'Religious'),
        (['education', 'learning'], 'Education'),
        (['entertainment', 'general'], 'Entertainment'),
    ]:
        if has(*words):
            return label
    return old or 'General'


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


# Tuple format: (line, extras, url, section, language, group, tvgid, check_segment)
raw_entries = []
seen_pairs = set()
seen_urls = set()
duplicates = 0

# 1. Primary country-specific sources
for code, source_url in SOURCES:
    country = COUNTRIES[code]
    try:
        lines = fetch(source_url).splitlines()
    except Exception as exc:
        print(f'Warning: failed to fetch {source_url}: {exc}')
        continue

    for line, extras, url in parse_m3u_blocks(lines):
        name = line.split(',', 1)[-1].strip()
        tvgid = attr(line, 'tvg-id')
        key = (tvgid, url)
        if key in seen_pairs or url in seen_urls:
            duplicates += 1
            continue
        seen_pairs.add(key)
        seen_urls.add(url)

        old_group = attr(line, 'group-title')
        group = category(name, old_group, code)
        language = lang(f'{name} {old_group} {attr(line, "tvg-language")}', code)
        line = put(line, 'group-title', f'{country} | {group}')
        raw_entries.append((line, extras, url, country, language, group, tvgid, True))

# 2. Secondary global active list: [SPORTS] Sports, [INTL-NEWS] News, + target countries
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
        old_group_lower = old_group.lower()
        tvgid = attr(line, 'tvg-id')
        haystack = f'{name} {old_group} {tvgid}'.lower()

        # Check country match first
        matched_code = None
        matched_country = None
        for code, (country_label, keywords) in COUNTRY_MATCHERS.items():
            if any(kw in haystack for kw in keywords):
                matched_code = code
                matched_country = country_label
                break

        if matched_country:
            seen_urls.add(url)
            seen_pairs.add((tvgid, url))
            group = category(name, old_group, matched_code)
            language = lang(f'{name} {old_group} {attr(line, "tvg-language")}', matched_code)
            line = put(line, 'group-title', f'{matched_country} | {group}')
            raw_entries.append((line, extras, url, matched_country, language, group, tvgid, True))
        elif '[sports]' in old_group_lower or 'sports' in old_group_lower:
            seen_urls.add(url)
            seen_pairs.add((tvgid, url))
            language = lang(f'{name} {old_group} {attr(line, "tvg-language")}')
            line = put(line, 'group-title', 'Sports | Live Sports')
            raw_entries.append((line, extras, url, 'Sports', language, 'Sports', tvgid, True))
        elif '[intl-news]' in old_group_lower or 'intl-news' in old_group_lower:
            seen_urls.add(url)
            seen_pairs.add((tvgid, url))
            language = lang(f'{name} {old_group} {attr(line, "tvg-language")}')
            line = put(line, 'group-title', 'News | International News')
            raw_entries.append((line, extras, url, 'Intl News', language, 'News', tvgid, True))

# 3. Movies merged into the same combined.m3u under "Movies | ..." (single-hop check for speed)
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
        old_group = attr(line, 'group-title') or 'All Movies'
        # Strip any bogus tvg-id so EPG generator doesn't look up TV schedules for movies
        line = put(line, 'tvg-id', '')
        line = put(line, 'group-title', f'Movies | {old_group}')
        language = lang(f'{name} {old_group} {attr(line, "tvg-language")}')
        raw_entries.append((line, extras, url, 'Movies', language, 'Movies', '', False))

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
    entries = []
    for item in raw_entries:
        if results.get(item[2], False):
            entries.append(item)
        else:
            dead_removed += 1
else:
    entries = raw_entries

if not entries:
    raise RuntimeError('All streams failed health checks')

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
    'countries': dict(stats),
    'total_channels': len(entries),
    'duplicate_entries_removed': duplicates,
    'dead_streams_removed': dead_removed,
    'unique_tvg_ids': len(ids),
    'epg_mapped_ids': len(selected),
    'epg_mapping_percent': round(100 * len(selected) / max(len(ids), 1), 1),
    'language_estimates_from_names': dict(languages),
    'note': 'Merged live TV + Sports + Intl News + verified movies into single combined.m3u.',
}
(ROOT / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
