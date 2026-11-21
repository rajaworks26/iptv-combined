from pathlib import Path
import xml.etree.ElementTree as ET
root=Path(__file__).resolve().parents[1]
playlist=(root/'combined.m3u').read_text(encoding='utf-8')
assert playlist.startswith('#EXTM3U') and '#EXTINF:' in playlist
p=root/'combined.xml'
assert p.exists() and p.stat().st_size>100
r=ET.parse(p).getroot()
assert r.tag=='tv' and len(r.findall('channel'))>0 and len(r.findall('programme'))>0, 'EPG has no channels or programmes'
print('Validated combined.m3u and combined.xml')
