# IPTV Combined (`rajaworks26/iptv-combined`)

[![Build Status](https://github.com/rajaworks26/iptv-combined/actions/workflows/update.yml/badge.svg)](https://github.com/rajaworks26/iptv-combined/actions/workflows/update.yml)
[![Last Update](https://img.shields.io/github/last-commit/rajaworks26/iptv-combined/main?label=last%20update)](https://github.com/rajaworks26/iptv-combined/commits/main)
[![Live Channels](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2Frajaworks26%2Fiptv-combined%2Fmain%2Freport.json&query=%24.unique_primary_channels&label=live%20channels&color=brightgreen)](https://raw.githubusercontent.com/rajaworks26/iptv-combined/main/report.json)
[![EPG Coverage](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2Frajaworks26%2Fiptv-combined%2Fmain%2Freport.json&query=%24.epg_final_percent&suffix=%25&label=EPG%20coverage&color=blue)](https://raw.githubusercontent.com/rajaworks26/iptv-combined/main/report.json)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

An automatically maintained IPTV playlist and XMLTV EPG aggregator. It combines public sources, probes live streams, retains a 10-run reliability history, deduplicates channels, preserves backup streams, merges EPG data, and publishes clean, neutral playlists for TiviMate and other compatible IPTV players.

## Project overview

- Automated stream health checks and live-media verification.
- 10-run historical reliability scoring; a single successful probe does not replace history.
- Stream deduplication with primary and backup stream selection.
- EPG merging and publication through the orphan `epg` branch.
- EPG-first sorting, followed by historical reliability and natural channel-name ordering.
- Clean channel names and verified resolution badges only when resolution was reliably detected.
- Stable, collision-free channel numbering persisted across builds.
- Regional, category, and language playlists.
- Validation before publication; failed validation preserves the previous valid outputs.

## Playlist URLs

| Playlist | URL |
| :--- | :--- |
| Combined | [combined.m3u](https://raw.githubusercontent.com/rajaworks26/iptv-combined/main/combined.m3u) |
| Backup streams | [alternates.m3u](https://raw.githubusercontent.com/rajaworks26/iptv-combined/main/alternates.m3u) |
| Sports | [sports.m3u](https://raw.githubusercontent.com/rajaworks26/iptv-combined/main/sports.m3u) |
| News | [news.m3u](https://raw.githubusercontent.com/rajaworks26/iptv-combined/main/news.m3u) |
| Canada | [canada.m3u](https://raw.githubusercontent.com/rajaworks26/iptv-combined/main/canada.m3u) |
| USA | [usa.m3u](https://raw.githubusercontent.com/rajaworks26/iptv-combined/main/usa.m3u) |
| India | [india.m3u](https://raw.githubusercontent.com/rajaworks26/iptv-combined/main/india.m3u) |
| Pakistan | [pakistan.m3u](https://raw.githubusercontent.com/rajaworks26/iptv-combined/main/pakistan.m3u) |
| Movies | [movies.m3u](https://raw.githubusercontent.com/rajaworks26/iptv-combined/main/movies.m3u) |
| Music | [music.m3u](https://raw.githubusercontent.com/rajaworks26/iptv-combined/main/music.m3u) |
| English | [language-english.m3u](https://raw.githubusercontent.com/rajaworks26/iptv-combined/main/language-english.m3u) |
| Hindi | [language-hindi.m3u](https://raw.githubusercontent.com/rajaworks26/iptv-combined/main/language-hindi.m3u) |
| Urdu | [language-urdu.m3u](https://raw.githubusercontent.com/rajaworks26/iptv-combined/main/language-urdu.m3u) |
| Punjabi | [language-punjabi.m3u](https://raw.githubusercontent.com/rajaworks26/iptv-combined/main/language-punjabi.m3u) |
| Tamil | [language-tamil.m3u](https://raw.githubusercontent.com/rajaworks26/iptv-combined/main/language-tamil.m3u) |
| Telugu | [language-telugu.m3u](https://raw.githubusercontent.com/rajaworks26/iptv-combined/main/language-telugu.m3u) |
| EPG guide | [combined.xml.gz](https://raw.githubusercontent.com/rajaworks26/iptv-combined/epg/combined.xml.gz) |

## Channel groups

| Order | Group | Description | Channel numbers |
| ---: | :--- | :--- | :--- |
| 1 | Live Sports | Dedicated major sports networks and sports services | 1000–1999 |
| 2 | News \| International | International news networks | 2000–2999 |
| 3 | Canada \| General & News | Canadian entertainment, national networks, public broadcasting, and domestic news | 3000–3999 |
| 4 | Canada \| Sports & Regional | Canadian regional, local, community, provincial, and regional sports channels | 4000–4999 |
| 5 | USA \| Networks & Entertainment | American broadcast and general entertainment channels | 5000–9999 |
| 6 | USA \| News & Business | American news, business, financial, political, and public-affairs channels | 10000–11999 |
| 7 | USA \| Kids & Family | American children’s and family channels | 12000–13999 |
| 8 | USA \| Documentary & Lifestyle | American documentary, educational, science, nature, travel, food, home, and lifestyle channels | 14000–15999 |
| 9 | India \| Hindi & General | Hindi-language and general Indian programming | 16000–17999 |
| 10 | India \| Punjabi & Regional | Punjabi and other eligible Indian regional-language channels | 18000–19999 |
| 11 | India \| South (Tamil & Telugu) | Tamil and Telugu programming | 20000–21999 |
| 12 | Pakistan | Pakistani entertainment, news, religious, regional, and other programming | 22000–23999 |
| 13 | Movies | Dedicated movie channels across supported countries and languages | 24000–29999 |
| 14 | Music | Dedicated music television channels | 30000–34999 |

The combined playlist contains no Top Picks, Favorites, or other subjective curated groups.

## Sorting and numbering

Within each group, primary channels are ordered by:

1. Active EPG availability, descending.
2. Existing 10-run reliability score, descending.
3. Normalized channel name, using natural sorting.
4. Stable channel identifier, as the final deterministic tie-breaker.

Active EPG means the channel has current or upcoming programme listings in the merged EPG data. A populated `tvg-id` alone does not prove active coverage.

Channel numbers are stored in `channel_numbers.json` and persist across builds. A channel keeps its number when its EPG coverage, reliability score, display name, resolution, or primary stream URL changes. Temporarily unavailable channels retain their assignments, and retired numbers are not automatically recycled.

IPTV players may display channels by file order or by `tvg-chno`, depending on the player’s settings.

## IPTV player setup

### TiviMate

1. Open **Settings** → **Playlists** → **Add playlist**.
2. Choose **M3U playlist** and paste the Combined playlist URL.
3. Open **Settings** → **EPG** → **EPG sources** → **Add source**.
4. Paste the EPG guide URL and assign it to the playlist.
5. Set playlist and EPG update intervals to **Every 6 hours**, or **On app start**.

### VLC, Kodi, and IPTV Smarters

Add the Combined playlist URL as an M3U source and add the EPG guide URL as an XMLTV source. In Kodi, enable the PVR IPTV Simple Client add-on and supply both URLs. Player-specific settings may determine whether file order or channel number order takes precedence.

## Automation and reliability

GitHub Actions updates the playlists four times daily at 01:17, 07:17, 13:17, and 19:17 UTC. The workflow runs syntax checks and automated tests before building.

The build probes streams, records the last 10 results in `data/stream_history.json`, scores channels, deduplicates by channel identity, selects the strongest primary stream, and retains suitable runners-up in `alternates.m3u`.

The workflow generates the EPG, merges official FAST XMLTV guides, prunes programmes outside a 12-hour past to 72-hour future window, records channels with active listings, validates all staged outputs, and publishes only after validation succeeds. The compressed EPG is published to the orphan `epg` branch.

## License

The code in this repository is released under the [MIT License](LICENSE).

## Sources & attribution

This project aggregates publicly available third-party playlist and EPG sources (**28 total**: 7 primary country playlists + 21 supplementary global, category, language, and FAST sources). Those sources remain subject to their own terms, licenses, and regional availability. This repository does not host, store, or restream video content.

- **iptv-org** — country, category, and language playlists (`iptv-org/iptv`)
- **Free-TV** — curated country playlists (`Free-TV/IPTV`)
- **Zaman-Topu** — active global playlist (`Zaman-Topu/Ip-tv-Collection`)
- **IPTV-By-Shovo** — curated global playlist (`shovo127/IPTV-By-Shovo`)
- **BuddyChewChew** — FAST platform playlists (`Pluto TV`, `Samsung TV Plus`, `Plex`, `Roku`)
- **Hindi_Punjabi-iptv-playlist** — regional Hindi/Punjabi channels (`deep2772`)
- **i.mjh.nz** — official XMLTV schedules for Pluto TV, Samsung TV Plus, Plex, and Roku

Channel availability, legality, and geographic access vary by location. Use only content you are legally permitted to access in your region.
