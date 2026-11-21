import collections, json, re, urllib.request, xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
COUNTRIES={'us':'USA','ca':'Canada','in':'India','pk':'Pakistan'}
def fetch(url):
 req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
 with urllib.request.urlopen(req,timeout=90) as r:return r.read().decode('utf-8-sig')
def attr(line,key):
 m=re.search(r'(?<!\w)'+re.escape(key)+r'="([^"]*)"',line)
 return m.group(1) if m else ''
def put(line,key,value):
 value=value.replace('"','').replace('\n',' ')
 if re.search(r'(?<!\w)'+re.escape(key)+r'="[^"]*"',line):return re.sub(r'(?<!\w)'+re.escape(key)+r'="[^"]*"',lambda m:key+'="'+value+'"',line,count=1)
 return line.replace('#EXTINF:',f'#EXTINF: {key}="{value}" ',1)
def lang(name):
 s=name.lower()
 for word,label in [('urdu','Urdu'),('punjabi','Punjabi'),('hindi','Hindi'),('tamil','Tamil'),('telugu','Telugu'),('bengali','Bengali'),('malayalam','Malayalam'),('english','English')]:
  if word in s:return label
 return 'Other / Unspecified'
def category(name,old):
 s=(name+' '+old).lower()
 for words,label in [(['news','current affairs'],'News'),(['sport','cricket','football'],'Sports'),(['movie','cinema','film'],'Movies'),(['kids','cartoon','children'],'Kids'),(['music','radio'],'Music'),(['religion','islam','quran','faith','christian','devotional'],'Religious'),(['education','learning'],'Education'),(['entertainment','general'],'Entertainment')]:
  if any(w in s for w in words):return label
 return old or 'General'
entries=[]; seen=set(); ids=set(); stats=collections.Counter(); languages=collections.Counter(); duplicates=0
for code,country in COUNTRIES.items():
 lines=fetch(f'https://iptv-org.github.io/iptv/countries/{code}.m3u').splitlines()
 for i,line in enumerate(lines):
  if not line.startswith('#EXTINF:'):continue
  j=i+1; extras=[]
  while j<len(lines) and lines[j].startswith('#') and not lines[j].startswith('#EXTINF:'):
   extras.append(lines[j]);j+=1
  if j>=len(lines) or lines[j].startswith('#'):continue
  url=lines[j].strip(); name=line.split(',',1)[-1].strip()
  key=(attr(line,'tvg-id'),url)
  if key in seen:duplicates+=1;continue
  seen.add(key)
  tvgid=attr(line,'tvg-id')
  if tvgid:ids.add(tvgid)
  group=category(name,attr(line,'group-title'))
  language=lang(name+' '+attr(line,'group-title'))
  line=put(line,'group-title',f'{country} | {group}')
  entries.append((line,extras,url,country,language,group))
  stats[country]+=1;languages[language]+=1
if not entries:raise RuntimeError('No channels found')
def write_playlist(path,items):
 path.write_text('#EXTM3U\n'+''.join('\n'.join([a,*b,c])+'\n' for a,b,c,*_ in items),encoding='utf-8')
write_playlist(ROOT/'combined.m3u',entries)
write_playlist(ROOT/'favorites.m3u',[e for e in entries if attr(e[0],'tvg-id') in set(json.loads((ROOT/'favorites.json').read_text()))] if (ROOT/'favorites.json').exists() else [])
# Language groups are optional alternative playlists; they do not change the main playlist.
for language in ['English','Hindi','Urdu','Punjabi','Tamil','Telugu']:
 write_playlist(ROOT/('language-'+language.lower()+'.m3u'),[e for e in entries if e[4]==language])
try:
 guides=json.loads(fetch('https://iptv-org.github.io/api/guides.json'))
except Exception as exc:raise RuntimeError('Guide mapping API unavailable; existing published files are untouched') from exc
selected={}
for g in guides:
 channel=g.get('channel');feed=g.get('feed');site=g.get('site');site_id=g.get('site_id')
 if not channel or not site or not site_id:continue
 candidates=[channel+'@'+feed,channel] if feed else [channel]
 for mid in candidates:
  if mid not in ids:continue
  score=(2 if feed and mid==channel+'@'+feed else 1,1 if g.get('lang')=='en' else 0)
  if mid not in selected or score>selected[mid][0]:selected[mid]=(score,g)
root=ET.Element('channels')
for mid,(_,g) in sorted(selected.items()):
 el=ET.SubElement(root,'channel',{'site':g['site'],'lang':g.get('lang') or 'en','xmltv_id':mid,'site_id':str(g['site_id'])})
 el.text=g.get('site_name') or mid
ET.indent(root)
ET.ElementTree(root).write(ROOT/'epg.channels.xml',encoding='utf-8',xml_declaration=True)
if not selected:raise RuntimeError('No EPG mappings available')
report={'countries':dict(stats),'total_channels':len(entries),'duplicate_entries_removed':duplicates,'unique_tvg_ids':len(ids),'epg_mapped_ids':len(selected),'epg_mapping_percent':round(100*len(selected)/max(len(ids),1),1),'language_estimates_from_names':dict(languages),'note':'EPG mapping does not guarantee listings; language guesses are approximate. Stream health is not automatically asserted.'}
(ROOT/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
