import collections, gzip, re
import xml.etree.ElementTree as ET
from pathlib import Path

root = Path(__file__).resolve().parents[1]
GROUPS = {'Live Sports': 100, 'International News': 100, 'Canada': 100, 'USA': 150,
          'India': 100, 'Pakistan': 10, 'Movies': 50}

text = (root / 'combined.m3u').read_text(encoding='utf-8')
assert text.startswith('#EXTM3U'), 'bad header'
counts = collections.Counter(re.findall(r'group-title="([^"]*)"', text))
assert set(counts) <= set(GROUPS), f'unexpected groups: {set(counts) - set(GROUPS)}'
for g, minimum in GROUPS.items():
    assert counts[g] >= minimum, f'{g} has only {counts[g]} channels (min {minimum})'

urls = [l.strip() for l in text.splitlines() if l.strip() and not l.startswith('#')]
vod = ('.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.m4v')
assert not [u for u in urls if u.split('|')[0].lower().split('?')[0].endswith(vod)], 'VOD URL found'

with gzip.open(root / 'combined.xml.gz') as f:
    r = ET.parse(f).getroot()
assert r.tag == 'tv' and len(r.findall('channel')) > 500 and len(r.findall('programme')) > 5000, 'EPG too small'
print('OK', dict(counts))
