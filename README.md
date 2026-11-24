# IPTV Combined (`rajaworks26/iptv-combined`)

[![Build Status](https://github.com/rajaworks26/iptv-combined/actions/workflows/update.yml/badge.svg)](https://github.com/rajaworks26/iptv-combined/actions/workflows/update.yml)
[![Last Update](https://img.shields.io/github/last-commit/rajaworks26/iptv-combined/main?label=last%20update)](https://github.com/rajaworks26/iptv-combined/commits/main)
[![Live Channels](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2Frajaworks26%2Fiptv-combined%2Fmain%2Freport.json&query=%24.unique_primary_channels&label=live%20channels&color=brightgreen)](https://raw.githubusercontent.com/rajaworks26/iptv-combined/main/report.json)
[![EPG Coverage](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2Frajaworks26%2Fiptv-combined%2Fmain%2Freport.json&query=%24.epg_final_percent&suffix=%25&label=EPG%20coverage&color=blue)](https://raw.githubusercontent.com/rajaworks26/iptv-combined/main/report.json)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

An automated, self-maintaining IPTV playlist and XMLTV EPG aggregator built for modern IPTV players. Every 6 hours, GitHub Actions fetches public streams across **28 sources** (7 primary + 21 supplementary), probes each stream down to the live media segment, scores and deduplicates channels, merges official FAST + `iptv-org` TV guides, and publishes lightweight outputs to GitHub.

---

## Quick Setup (Player URLs)

Copy and paste these two URLs into your IPTV player:

| Type | URL | Notes |
| :--- | :--- | :--- |
| **Primary Playlist (M3U)** | `https://raw.githubusercontent.com/rajaworks26/iptv-combined/main/combined.m3u` | Main deduplicated live TV playlist (7 groups) |
| **EPG TV Guide (Gzipped XMLTV)** | `https://raw.githubusercontent.com/rajaworks26/iptv-combined/epg/combined.xml.gz` | Force-pushed orphan `epg` branch (keeps `main` history small) |

### Additional Playlists

| Playlist | URL |
| :--- | :--- |
| **Backup Streams** | `https://raw.githubusercontent.com/rajaworks26/iptv-combined/main/alternates.m3u` |
| **English** | `https://raw.githubusercontent.com/rajaworks26/iptv-combined/main/language-english.m3u` |
| **Hindi** | `https://raw.githubusercontent.com/rajaworks26/iptv-combined/main/language-hindi.m3u` |
| **Urdu** | `https://raw.githubusercontent.com/rajaworks26/iptv-combined/main/language-urdu.m3u` |
| **Punjabi** | `https://raw.githubusercontent.com/rajaworks26/iptv-combined/main/language-punjabi.m3u` |
| **Tamil** | `https://raw.githubusercontent.com/rajaworks26/iptv-combined/main/language-tamil.m3u` |
| **Telugu** | `https://raw.githubusercontent.com/rajaworks26/iptv-combined/main/language-telugu.m3u` |

### Setup
1. **Add Playlist:** Settings → Playlists → Add playlist → M3U playlist → paste the **Primary Playlist** URL above.
2. **Assign EPG:** Settings → EPG → EPG sources → Add source → paste the **EPG TV Guide** URL (`.../epg/combined.xml.gz`) and assign it to the playlist.
3. **Update Interval:** Set both Playlist and EPG update intervals to **Every 6 hours** (or **On app start**).

---

## Playlist Structure

Channels are strictly classified into **7 groups** (unplaceable channels are dropped rather than falling back to `USA`):

1. **Live Sports**
2. **International News**
3. **Canada**
4. **USA**
5. **India**
6. **Pakistan**
7. **Movies**

---

## How It Works

* **Strict Live Stream Probing (`scripts/build.py`):** Rejects VOD extensions (`.mp4`, `.mkv`, `.avi`), expiring token URLs (`wmsAuthSign=`, `hdnea=`), HTTP 200 HTML/JSON error pages, VOD playlists (`#EXT-X-ENDLIST` / `PLAYLIST-TYPE:VOD`), and verifies actual binary media segments.
* **10-Run Reliability Scoring & Deduplication:** Tracks stream uptime in `data/stream_history.json` across the last 10 runs and ranks duplicates on a 0–100 scale (**Uptime 45 pts**, **EPG/Logo Metadata 25 pts**, **Resolution 15 pts**, **Latency 15 pts**). The highest-scoring stream goes into `combined.m3u`; runners-up go into `alternates.m3u`.
* **Merged XMLTV EPG (`epg` branch):** Resolves EPG IDs by exact `tvg-id` and normalized channel name, generates `iptv-org` guide schedules, merges official XMLTV feeds (`i.mjh.nz` for Pluto TV, Samsung TV Plus, Plex, and Roku), prunes stale programmes (12h back / 72h ahead), and force-pushes `combined.xml.gz` to the orphan `epg` branch.
* **Validation Gate (`scripts/validate.py`):** Verifies group counts, minimum channel thresholds, and `epg_final_percent` in `report.json` before committing. If an upstream outage occurs, the job aborts before touching the live playlist.

---

## License

The code in this repository is released under the [MIT License](LICENSE).

## Sources & Attribution

This project aggregates publicly available third-party playlist and EPG sources (**28 total**: 7 primary country playlists + 21 supplementary global, category, language, and FAST sources). Those sources remain subject to their own terms, licenses, and regional availability. This repository does not host, store, or restream video content.

* **iptv-org** — country, category, and language playlists (`iptv-org/iptv`)
* **Free-TV** — curated country playlists (`Free-TV/IPTV`)
* **Zaman-Topu** — active global playlist (`Zaman-Topu/Ip-tv-Collection`)
* **IPTV-By-Shovo** — curated global playlist (`shovo127/IPTV-By-Shovo`)
* **BuddyChewChew** — FAST platform playlists (`Pluto TV`, `Samsung TV Plus`, `Plex`, `Roku`)
* **Hindi_Punjabi-iptv-playlist** — regional Hindi/Punjabi channels (`deep2772`)
* **i.mjh.nz** — official XMLTV schedules for Pluto TV, Samsung TV Plus, Plex, and Roku

Channel availability, legality, and geographic access vary by location. Use only content you are legally permitted to access in your region.
