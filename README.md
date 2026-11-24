# IPTV Combined (`rajaworks26/iptv-combined`)

An automated, self-healing Live TV M3U playlist and XMLTV EPG generator built for any IPTV player that supports M3U playlists and XMLTV guides (such as Kodi, VLC, OTT Navigator, Sparkle TV, Televizo, UHF, or IPTVnator). Every 6 hours, GitHub Actions aggregates 28 curated public IPTV and FAST sources, probes every stream down to the video segment, scores and deduplicates channels using rolling uptime history, and merges multi-source TV guide data.

---

## Quick Setup Links

| File | Raw GitHub URL | Purpose |
| :--- | :--- | :--- |
| **Main Playlist** | `https://raw.githubusercontent.com/rajaworks26/iptv-combined/main/combined.m3u` | Primary Live TV playlist (7 clean groups, dead links pruned) |
| **Compressed EPG (Recommended)** | `https://raw.githubusercontent.com/rajaworks26/iptv-combined/main/combined.xml.gz` | Fast-loading XMLTV guide (`iptv-org` + Pluto, Plex, Samsung TV Plus & Roku) |
| **Uncompressed EPG** | `https://raw.githubusercontent.com/rajaworks26/iptv-combined/main/combined.xml` | Standard XMLTV guide for players that do not decompress `.gz` files |
| **Backup Mirrors** | `https://raw.githubusercontent.com/rajaworks26/iptv-combined/main/alternates.m3u` | Secondary working stream links for duplicate channels |
| **Build Report** | `https://raw.githubusercontent.com/rajaworks26/iptv-combined/main/report.json` | Live metrics, channel counts per group, and EPG coverage stats |

### Recommended Player Settings
1. **Playlist:** Add `combined.m3u` → enable **Update playlist on app start** and set the refresh interval to **Every 8 hours** (or **12 hours**).
2. **EPG:** Add `combined.xml.gz` (or `combined.xml`) as your EPG source → enable **Update EPG on app start** and set the refresh interval to **Every 8 hours** (or **12 hours**).

---

## Playlist Structure (7 Live TV Groups)

Focused strictly on reliable Live TV playback (zero `.mp4`/`.mkv` VOD file clutter, and US-only geo-blocked FAST feeds excluded):

1. **Live Sports** — Cricket, football/soccer, F1, TSN, Sportsnet, ESPN, Sky Sports, Star Sports, Willow, Ten Sports, and PTV Sports.
2. **International News** — CP24, CBC News, CTV News, CityNews, CNN, BBC World News, Al Jazeera English, Geo News, ARY News, NDTV, and WION.
3. **Canada** — Canadian national/local broadcasts plus Pluto TV Canada, Samsung TV Plus Canada, and Plex Canada FAST channels.
4. **USA** — US broadcast and cable networks (with US-only geo-blocked FAST lists excluded).
5. **India** — Hindi, Punjabi, Tamil, Telugu, and regional Indian networks plus Samsung TV Plus India.
6. **Pakistan** — Pakistani entertainment, news, and Urdu networks (with strict word-boundary filtering to prevent foreign-language leaks).
7. **Movies** — 24/7 linear movie TV channels (on-demand VOD movie files are stripped automatically).

*Language-specific playlists (`language-english.m3u`, `language-hindi.m3u`, `language-urdu.m3u`, `language-punjabi.m3u`, `language-tamil.m3u`, `language-telugu.m3u`) are also generated automatically.*

---

## How It Works

### 1. Multi-Stage Stream Validation & Dead-Link Pruning
* **Pre-Filtering:** Strips VOD extensions (`.mp4`, `.mkv`, `.avi`), expiring session tokens (`wmsAuthSign=`, `hdnea=`), US-only geo-blocked FAST lists, and non-target foreign-language streams.
* **3-Hop HLS Probe:** Follows HTTP redirects, parses master `.m3u8` manifests (`#EXT-X-STREAM-INF`), and verifies actual `.ts`/`.m4s` media segment bytes before marking a stream alive.
* **Player Header Compatibility:** Preserves `#EXTVLCOPT` lines and appends `url|User-Agent=...&Referer=...` pipe parameters for ExoPlayer/VLC-based clients.

### 2. Rolling Uptime History & 0–100 Stream Scoring
* Tracks a rolling 10-run pass/fail history per URL in `data/stream_history.json`.
* **Outage Grace:** High-reliability streams ($\ge 70\%$ uptime) are retained for 1 grace run during temporary server hiccups before being pruned.
* **Duplicate Ranking:** When multiple sources provide the same channel, each stream is scored out of 100 (**45%** historical uptime, **25%** EPG/logo metadata, **15%** HLS manifest resolution `1080p > 720p > SD`, **15%** startup latency). The highest-scoring stream enters `combined.m3u`; runners-up go to `alternates.m3u`.

### 3. Hybrid EPG Pipeline
* Maps primary channels against `iptv-org` TV guide metadata (`epg.channels.xml`) and generates `combined.xml`.
* Merges official XMLTV schedules from `i.mjh.nz` for **Pluto TV (CA)**, **Samsung TV Plus (CA & IN)**, **Plex (CA)**, and **Roku**, then compresses the final guide into `combined.xml.gz`.
* Logs unmapped channels in `data/unmatched_epg.json` for ongoing alias tuning.

---

## Sources Aggregated (28 Playlists)
* **Country Lists:** `iptv-org` (`ca`, `us`, `in`, `pk`) & `Free-TV` (`ca`, `us`, `in`)
* **Global Curated:** `Zaman-Topu` (`FINAL_IPTV_ACTIVE.m3u`) & `IPTV-By-Shovo`
* **Categories (`iptv-org`):** `sports`, `news`, `movies`, `kids`, `documentary`, `music`, `entertainment`
* **Languages (`iptv-org` & Community):** `eng`, `hin`, `urd`, `pan`, `tam`, `tel` & `Hindi_Punjabi_Merged.m3u`
* **FAST Platforms (`BuddyChewChew`):** `plutotv_ca`, `samsungtvplus_ca`, `samsungtvplus_in`, `plex_ca`, `roku_all`

---

## Automation Schedule
* **Workflow:** `.github/workflows/update.yml`
* **Schedule:** Runs automatically every **6 hours** (`17 1,7,13,19 * * *` UTC) and supports manual runs via **Actions → Update IPTV Playlist and EPG → Run workflow**.
* **Outage Guard:** Aborts before overwriting existing files if fewer than 5 primary sources respond or fewer than 300 playable channels pass validation.
