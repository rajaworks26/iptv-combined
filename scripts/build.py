import collections
import concurrent.futures
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
EPG_PUBLIC_URL = 'https://raw.githubusercontent.com/rajaworks26/iptv-combined/main/combined.xml'

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

GROUPS = [
    'Top Picks',
    'Live Sports',
    'International News',
    'Canada',
    'USA',
    'India',
    'Pakistan',
    'Movies | Hollywood & English',
    'Movies | Bollywood & Hindi',
    'Movies | Pakistani & Urdu',
    'Movies | Action & General',
]

TOP_PICKS_KEYWORDS = (
    'cp24', 'cbc news', 'ctv news', 'citynews toronto', 'tsn 1', 'tsn1',
    'sportsnet ontario', 'sportsnet one', 'espn', 'sky sports cricket',
    'star sports 1', 't sports', 'willow', 'cnn', 'bbc world news',
    'al jazeera english', 'geo news', 'ary news', 'hum tv', 'ary digital',
    'geo entertainment', 'star plus', 'colors tv', 'sony entertainment'
)

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

FALLBACK_LOGOS = {
    'Top Picks': 'https://img.icons8.com/color/240/star--v1.png',
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

# Two-tier health check settings: generous 6s timeout for Live TV, fast 2.5s for massive movie list
CHECK_STREAMS = True
LIVE_TIMEOUT = 6.0
LIVE_WORKERS = 60
MOVIE_TIMEOUT = 2.5
MOVIE_WORKERS = 120
MIN_PRIMARY_SOURCES_OK = 5
MIN_CHANNELS = 300


def get_bytes(url, timeout=90, limit=None):
    req = urllib.request.Request(
        url,
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 'Accept': '*/*'},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if getattr(resp, 'status', 200) >= 400:
            raise urllib.error.HTTPError(url, resp.status, 'HTTP Error', resp.headers, None)
        data = resp.read(limit) if limit else resp.read()
        return data, resp.geturl()


def fetch_text(url, timeout=90):
    data, _ = get_bytes(url, timeout=timeout)
    return data.decode('utf-8-sig', errors='ignore')


def is_stream_alive(url, is_live=True):
    if not url.startswith(('http://', 'https://')):
        return False
    timeout = LIVE_TIMEOUT if is_live else MOVIE_TIMEOUT
    try:
        current_url = url
        for _ in range(3 if is_live else 1):
            data, final_url = get_bytes(current_url, timeout=timeout, limit=65536)
            if not data:
                return False
            if not is_live:
                return True
            text = data.decode('utf-8', errors='ignore')
            if not text.lstrip().startswith('#EXTM3U'):
                return True
            next_uri = next(
                (ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith('#')),
                None,
            )
            if not next_uri:
                return False
            current_url = urllib.parse.urljoin(final_url, next_uri)
            if '#EXT-X-STREAM-INF' not in text and '#EXTINF:' in text:
                seg_data, _ = get_bytes(current_url, timeout=timeout, limit=16384)
                return bool(seg_data)
        return False
    except (OSError, ValueError, TimeoutError, urllib.error.URLError):
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


def format_extinf(e, number, group_name):
    line = put(e['line'], 'group-title', group_name)
    line = put(line, 'tvg-chno', str(number))
    if not attr(line, 'tvg-name'):
        line = put(line, 'tvg-name', e['name'])
    if e['tvgid']:
        line = put(line, 'tvg-id', e['tvgid'])
    logo = e['logo'] or FALLBACK_LOGOS.get('Movies' if group_name.startswith('Movies') else group_name, FALLBACK_LOGOS['Top Picks'])
    line = put(line, 'tvg-logo', logo)
    return '\n'.join([line, *e['extras'], e['url']]) + '\n'


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

    # 1. Primary country sources (guard against partial upstream outages)
    for priority, (code, url) in enumerate(SOURCES):
        try:
            lines = fetch_text(url).splitlines()
            primary_ok += 1
        except Exception as exc:
            errors.append(f'{url}: {exc}')
            continue

        for line, extras, stream_url in parse_m3u_blocks(lines):
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
                'is_live': True,
            })

    if primary_ok < MIN_PRIMARY_SOURCES_OK:
        raise RuntimeError(f'Only {primary_ok}/{len(SOURCES)} primary sources reachable; aborting to preserve existing playlist')

    # 2. Zaman-Topu active list (with country-scoped EPG & logo backfill)
    for active_url in GLOBAL_ACTIVE_SOURCES:
        try:
            lines = fetch_text(active_url).splitlines()
        except Exception as exc:
            errors.append(f'{active_url}: {exc}')
            continue

        for line, extras, stream_url in parse_m3u_blocks(lines):
            name = line.split(',', 1)[-1].strip()
            old_group = attr(line, 'group-title')
            og_lower = old_group.lower().strip()
            n_epg = norm_epg_name(name)
            n_title = norm_title(name)
            s = f'{name} {old_group}'.lower()

            matched_code = None
            for code, (_, keywords) in COUNTRY_MATCHERS.items():
                if any(kw in s for kw in keywords):
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

            if not (is_sports or is_news or matched_code or is_allowed_group):
                continue

            fetched.append({
                'line': line,
                'extras': extras,
                'url': stream_url,
                'name': name,
                'tvgid': tvgid,
                'logo': logo,
                'group': classify_live_group(name, old_group, matched_code or ''),
                'language': detect_lang(f'{name} {old_group} {attr(line, "tvg-language")}', matched_code or ''),
                'priority': 10,
                'is_live': True,
            })

    # 3. Movies playlist
    for movie_url in MOVIE_SOURCES:
        try:
            lines = fetch_text(movie_url).splitlines()
        except Exception as exc:
            errors.append(f'{movie_url}: {exc}')
            continue

        for line, extras, stream_url in parse_m3u_blocks(lines):
            name = line.split(',', 1)[-1].strip()
            old_group = attr(line, 'group-title')
            fetched.append({
                'line': put(line, 'tvg-id', ''),
                'extras': extras,
                'url': stream_url,
                'name': name,
                'tvgid': '',
                'logo': attr(line, 'tvg-logo'),
                'group': classify_movie_group(name, old_group),
                'language': detect_lang(f'{name} {old_group} {attr(line, "tvg-language")}'),
                'priority': 20,
                'is_live': False,
            })

    if not fetched:
        raise RuntimeError('No source playlists available')

    unique_urls = {}
    for e in fetched:
        unique_urls.setdefault(e['url'], e)
    candidates = list(unique_urls.values())

    if CHECK_STREAMS:
        live_cands = [e for e in candidates if e['is_live']]
        movie_cands = [e for e in candidates if not e['is_live']]

        with concurrent.futures.ThreadPoolExecutor(max_workers=LIVE_WORKERS) as pool:
            live_ok = list(pool.map(lambda item: is_stream_alive(item['url'], True), live_cands))
        with concurrent.futures.ThreadPoolExecutor(max_workers=MOVIE_WORKERS) as pool:
            movie_ok = list(pool.map(lambda item: is_stream_alive(item['url'], False), movie_cands))

        candidates = [e for e, ok in zip(live_cands, live_ok) if ok] + [e for e, ok in zip(movie_cands, movie_ok) if ok]

    # Prefer source priority, valid tvg-id, and valid tvg-logo; save working mirrors to alternates.m3u
    candidates.sort(key=lambda e: (e['priority'], -bool(e['tvgid']), -bool(e['logo'])))
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

    if len(primary) < MIN_CHANNELS:
        raise RuntimeError(f'Only {len(primary)} unique playable channels (minimum {MIN_CHANNELS})')

    primary.sort(key=lambda e: (GROUPS.index(e['group']) if e['group'] in GROUPS else 99, e['name'].casefold()))

    favorites = [
        e for e in primary
        if not e['group'].startswith('Movies') and any(kw.replace(' ', '') in norm_title(e['name']) for kw in TOP_PICKS_KEYWORDS)
    ][:99]

    numbered = []
    number = 1
    for e in favorites:
        numbered.append((e, number, 'Top Picks'))
        number += 1
    for e in primary:
        numbered.append((e, number, e['group']))
        number += 1

    write_playlist(ROOT / 'combined.m3u', numbered)
    write_playlist(ROOT / 'top-picks.m3u', numbered[:len(favorites)])
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

    report = {
        'generated_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'primary_sources_ok': f'{primary_ok}/{len(SOURCES)}',
        'source_entries': len(fetched),
        'unique_urls': len(unique_urls),
        'passed_health_checks': len(candidates),
        'unique_primary_channels': len(primary),
        'alternate_streams_saved': len(backups),
        'top_picks': len(favorites),
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
