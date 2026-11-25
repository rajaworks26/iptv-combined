"""Validate generated IPTV playlists, channel numbering, and report integrity."""

import argparse
import collections
import gzip
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from config import (  # noqa: E402
    FORBIDDEN_GROUPS,
    GROUPS,
    GROUP_INDEX,
    GROUP_RANGES,
    OBSOLETE_GROUPS,
    SPLIT_PLAYLISTS,
)

VOD_EXTENSIONS = (".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".m4v")
REPORT_FIELDS = {
    "generated_utc", "primary_sources_ok", "source_entries", "unique_urls",
    "passed_health_checks", "grace_retained_streams", "unique_primary_channels",
    "alternate_streams_saved", "average_stream_score", "groups",
    "unique_tvg_ids", "epg_mapped_ids", "epg_mapping_percent", "source_errors",
    "epg_final_covered_ids", "epg_final_percent",
}


def fail(message):
    raise AssertionError(message)


def parse_m3u(path):
    if not path.exists():
        fail(f"Missing required playlist: {path.name}")
    text = path.read_text(encoding="utf-8")
    if not text.startswith("#EXTM3U"):
        fail(f"Invalid M3U header: {path.name}")
    entries = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not line.startswith("#EXTINF:"):
            continue
        cursor = index + 1
        while cursor < len(lines) and lines[cursor].startswith("#"):
            cursor += 1
        if cursor >= len(lines):
            fail(f"#EXTINF without URL in {path.name}")
        url = lines[cursor].strip()
        if not url.startswith(("http://", "https://")):
            fail(f"Missing or invalid stream URL in {path.name}: {url}")
        name = line.rsplit(",", 1)[-1].strip()
        entries.append({
            "name": name,
            "url": url,
            "group": re.search(r'group-title="([^"]*)"', line).group(1) if 'group-title="' in line else "",
            "number": int(re.search(r'tvg-chno="([^"]*)"', line).group(1)) if 'tvg-chno="' in line else None,
            "tvgid": re.search(r'tvg-id="([^"]*)"', line).group(1) if 'tvg-id="' in line else "",
        })
    return text, entries


def validate_combined(root):
    text, entries = parse_m3u(root / "combined.m3u")
    groups = [entry["group"] for entry in entries]
    invalid = set(groups) - set(GROUPS)
    if invalid:
        fail(f"Unexpected groups in combined.m3u: {sorted(invalid)}")
    forbidden = set(groups) & FORBIDDEN_GROUPS
    if forbidden:
        fail(f"Forbidden subjective groups found: {sorted(forbidden)}")
    obsolete = set(groups) & OBSOLETE_GROUPS
    if obsolete:
        fail(f"Obsolete groups found: {sorted(obsolete)}")

    seen_order = []
    for group in groups:
        if group not in seen_order:
            seen_order.append(group)
    if seen_order != [group for group in GROUPS if group in seen_order]:
        fail("Combined playlist group order does not match the configured group order")

    numbers = [entry["number"] for entry in entries]
    if any(number is None for number in numbers):
        fail("Every primary channel must have tvg-chno")
    if len(numbers) != len(set(numbers)):
        fail("Duplicate primary channel numbers in combined.m3u")
    for entry in entries:
        low, high = GROUP_RANGES[entry["group"]]
        if not low <= entry["number"] <= high:
            fail(f"Channel number {entry['number']} is outside range for {entry['group']}")

    urls = [entry["url"].split("|")[0].lower().split("?")[0] for entry in entries]
    vod = [url for url in urls if url.endswith(VOD_EXTENSIONS)]
    if vod:
        fail("VOD URL found in combined.m3u")

    if (root / "combined.xml.gz").exists():
        with gzip.open(root / "combined.xml.gz") as handle:
            epg_root = ET.parse(handle).getroot()
        if epg_root.tag != "tv" or len(epg_root.findall("channel")) <= 500 or len(epg_root.findall("programme")) <= 5000:
            fail("EPG too small")

    return entries


def validate_split_playlists(root, combined_entries):
    combined_by_id = {}
    for entry in combined_entries:
        identity = (entry["tvgid"], entry["name"].casefold())
        combined_by_id[identity] = entry

    for filename, rule in SPLIT_PLAYLISTS.items():
        _, entries = parse_m3u(root / filename)
        identities = []
        numbers = []
        for entry in entries:
            identity = (entry["tvgid"], entry["name"].casefold())
            if identity not in combined_by_id:
                fail(f"Channel in {filename} is absent from combined.m3u: {entry['name']}")
            primary = combined_by_id[identity]
            if entry["number"] != primary["number"]:
                fail(f"Channel number mismatch between combined.m3u and {filename}: {entry['name']}")
            group = primary["group"]
            matches = (
                group in rule.get("groups", set())
                or entry.get("code", "") in rule.get("countries", set())
                or entry.get("category", "") in rule.get("categories", set())
            )
            if not matches:
                fail(f"Channel does not meet split-playlist rule for {filename}: {entry['name']}")
            identities.append(identity)
            numbers.append(entry["number"])
        if len(identities) != len(set(identities)):
            fail(f"Duplicate primary channel in {filename}")
        if len(numbers) != len(set(numbers)):
            fail(f"Duplicate channel number in {filename}")


def validate_report(root, combined_entries):
    report_path = root / "report.json"
    if not report_path.exists():
        fail("Missing report.json")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    missing = REPORT_FIELDS - set(report)
    if missing:
        fail(f"report.json is missing fields: {sorted(missing)}")
    if set(report["groups"]) != set(GROUPS):
        fail("report.json groups do not match the configured 14 groups")
    if sum(report["groups"].values()) != len(combined_entries):
        fail("report.json group totals do not reconcile with primary channel count")
    if report["unique_primary_channels"] != len(combined_entries):
        fail("report.json primary channel count does not match combined.m3u")


def validate_language_playlists(root, combined_entries):
    combined_by_id = {
        (entry["tvgid"], entry["name"].casefold()): entry
        for entry in combined_entries
    }
    for path in sorted(root.glob("language-*.m3u")):
        _, entries = parse_m3u(path)
        for entry in entries:
            identity = (entry["tvgid"], entry["name"].casefold())
            if identity not in combined_by_id:
                fail(f"Language playlist channel absent from combined.m3u: {entry['name']}")
            if entry["number"] != combined_by_id[identity]["number"]:
                fail(f"Channel number mismatch in {path.name}: {entry['name']}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT), help="Directory containing generated outputs")
    args = parser.parse_args()
    root = Path(args.root).resolve()

    combined_entries = validate_combined(root)
    validate_split_playlists(root, combined_entries)
    validate_language_playlists(root, combined_entries)
    validate_report(root, combined_entries)

    counts = collections.Counter(entry["group"] for entry in combined_entries)
    print("OK", dict(counts))


if __name__ == "__main__":
    main()
