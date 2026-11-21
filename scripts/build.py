import collections
import concurrent.futures
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

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

# Set to True to verify stream URLs respond before including them in combined.m3u
CHECK_STREAM_HEALTH = True
STREAM_TIMEOUT = 4
MAX_WORKERS = 32


def fetch(url, timeout=90):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8-sig')


def is_stream_alive(url):
    if not url.startswith(('http://', 'https://')):
        return False
    req = urllib.request.Request(
        url,
        headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'Accept': '*/*',
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=STREAM_TIMEOUT) as resp:
            status = getattr(resp, 'status', 200)
            if status >= 400:
                return False
            # Read a tiny chunk to confirm stream payload actually starts
            chunk = resp.read(256)
            return len(chunk) > 0
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


def lang(name, country_code=''):
    s = name.lower()
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


def category(name, old):
    s = (name + ' ' + old).lower()
    for words, label in [
        (['news', 'current affairs'], 'News'),
        (['sport', 'cricket', 'football'], 'Sports'),
        (['movie', 'cinema', 'film'], 'Movies'),
        (['kids', 'cartoon', 'children'], 'Kids'),
        (['music', 'radio'], 'Music'),
        (['religion', 'islam', 'quran', 'faith', 'christian', 'devotional'], 'Religious'),
        (['education', 'learning'], 'Education'),
        (['entertainment', 'general'], 'Entertainment'),
    ]:
        if any(w in s for w in words):
            return label
    return old or 'General'


raw_entries = []
seen = set()
duplicates = 0

for code, source_url in SOURCES:
    country = COUNTRIES[code]
    try:
        lines = fetch(source_url).splitlines()
    except Exception as exc:
        print(f'Warning: failed to fetch {source_url}: {exc}')
        continue

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

        url = lines[j].strip()
        name = line.split(',', 1)[-1].strip()
        tvgid = attr(line, 'tvg-id')
        key = (tvgid, url)
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)

        group = category(name, attr(line, 'group-title'))
        language = lang(name + ' ' + attr(line, 'group-title'), code)
        line = put(line, 'group-title', f'{country} | {group}')
        raw_entries.append((line, extras, url, country, language, group, tvgid))

if not raw_entries:
    raise RuntimeError('No channels found from upstream sources')

dead_removed = 0
if CHECK_STREAM_HEALTH:
    unique_urls = list({e[2] for e in raw_entries})
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        results = dict(zip(unique_urls, pool.map(is_stream_alive, unique_urls)))
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

# Index guides by candidate ID for fast lookup including aliases
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
    lookup_keys = [mid] + EPG_ALIASES.get(mid, [])
    best_score = None
    best_guide = None

    for alias_idx, key in enumerate(lookup_keys):
        for exact_feed, g in guide_index.get(key, []):
            site = g['site']
            if site in BLOCKED_SITES:
                continue
            score = (
                1 if alias_idx == 0 else 0,          # Prefer direct match over alias
                SITE_PRIORITY.get(site, 1),          # Prefer reliable EPG providers
                2 if exact_feed else 1,              # Prefer exact feed match
                1 if g.get('lang') == 'en' else 0,   # Prefer English metadata
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
    'note': 'Stream reachability probed at build time. Blocked EPG scrapers excluded.',
}
(ROOT / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
