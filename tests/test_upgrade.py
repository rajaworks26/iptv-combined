import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build import (  # noqa: E402
    assign_channel_numbers,
    classify_channel,
    clean_display_name,
    natural_key,
    resolution_badge,
)
from config import GROUPS, GROUP_RANGES  # noqa: E402


class ClassificationTests(unittest.TestCase):
    def check(self, expected, name, country="", language="", old_group=""):
        group, _ = classify_channel(name, old_group, country, language)
        self.assertEqual(group, expected)

    def test_sports_precedence(self):
        for name, country in [
            ("ESPN", "us"),
            ("TSN 1", "ca"),
            ("Sportsnet Ontario", "ca"),
            ("PTV Sports", "pk"),
            ("Star Sports 1", "in"),
        ]:
            self.check("Live Sports", name, country)

    def test_international_news(self):
        self.check("News | International", "BBC World News")
        self.check("News | International", "WION")

    def test_canadian_channels(self):
        self.check("Canada | General & News", "CBC News Network", "ca")
        self.check("Canada | General & News", "CP24", "ca")
        self.check("Canada | Sports & Regional", "CHEK", "ca")
        self.check("Canada | Sports & Regional", "CBC Toronto", "ca")

    def test_american_channels(self):
        self.check("USA | Networks & Entertainment", "NBC", "us")
        self.check("USA | News & Business", "CNN", "us")
        self.check("USA | News & Business", "Fox News", "us")
        self.check("USA | Kids & Family", "PBS Kids", "us")
        self.check("USA | Documentary & Lifestyle", "National Geographic", "us")

    def test_indian_channels(self):
        self.check("India | Hindi & General", "Star Plus", "in")
        self.check("India | Punjabi & Regional", "PTC Punjabi", "in")
        self.check("India | South (Tamil & Telugu)", "Star Vijay", "in")
        self.check("India | South (Tamil & Telugu)", "Zee Telugu", "in")

    def test_pakistan_category_music(self):
        self.check("Pakistan", "Geo News", "pk")
        self.check("Movies", "Zee Cinema", "in")
        self.check("Movies", "Pitaara", "in")
        self.check("Music", "B4U Music", "in")

    def test_ambiguous_terms_do_not_override_explicit_channels(self):
        self.check("USA | News & Business", "Fox News", "us")
        self.check("Live Sports", "Star Sports 1", "in")


class NameAndSortingTests(unittest.TestCase):
    def test_clean_names(self):
        self.assertEqual(clean_display_name("US: ESPN [FHD]"), "ESPN")
        self.assertEqual(clean_display_name("CA | CBC Toronto [HD]"), "CBC Toronto")
        self.assertEqual(clean_display_name("IN: PTC Punjabi BACKUP"), "PTC Punjabi")

    def test_preserves_meaningful_suffixes(self):
        self.assertEqual(clean_display_name("TSN 2"), "TSN 2")
        self.assertEqual(clean_display_name("HBO East"), "HBO East")
        self.assertEqual(clean_display_name("Star Sports 1 +1"), "Star Sports 1 +1")

    def test_resolution_badges(self):
        self.assertEqual(resolution_badge(1080), " [1080p]")
        self.assertEqual(resolution_badge(720), " [720p]")
        self.assertEqual(resolution_badge(0), "")
        self.assertEqual(resolution_badge(999), "")

    def test_natural_sort(self):
        values = ["TSN 10", "TSN 2", "TSN 1"]
        self.assertEqual(sorted(values, key=natural_key), ["TSN 1", "TSN 2", "TSN 10"])


class ChannelNumberTests(unittest.TestCase):
    def setUp(self):
        self.path = ROOT / "channel_numbers.json"
        self.original = self.path.read_text(encoding="utf-8") if self.path.exists() else None

    def tearDown(self):
        if self.original is None:
            self.path.unlink(missing_ok=True)
        else:
            self.path.write_text(self.original, encoding="utf-8")

    def make_entry(self, name, group, tvgid):
        return {
            "name": name,
            "group": group,
            "tvgid": tvgid,
            "code": "ca",
            "score": 90,
            "height": 1080,
            "url": f"https://example.test/{tvgid}.m3u8",
            "extras": [],
            "line": f'#EXTINF:-1 tvg-id="{tvgid}",{name}',
        }

    def test_stable_numbering_and_recovery(self):
        first = [self.make_entry("ESPN", "Live Sports", "espn"), self.make_entry("TSN 1", "Live Sports", "tsn1")]
        assign_channel_numbers(first)
        first_numbers = {entry["tvgid"]: entry["number"] for entry in first}

        second = [self.make_entry("ESPN", "Live Sports", "espn"), self.make_entry("TSN 1", "Live Sports", "tsn1")]
        assign_channel_numbers(second)
        second_numbers = {entry["tvgid"]: entry["number"] for entry in second}
        self.assertEqual(first_numbers, second_numbers)

    def test_group_change_gets_new_number(self):
        entry = self.make_entry("Example", "Movies", "example")
        assign_channel_numbers([entry])
        old_number = entry["number"]
        entry["group"] = "Music"
        assign_channel_numbers([entry])
        low, high = GROUP_RANGES["Music"]
        self.assertTrue(low <= entry["number"] <= high)
        self.assertNotEqual(entry["number"], old_number)

    def test_duplicate_detection(self):
        first = self.make_entry("A", "Live Sports", "a")
        second = self.make_entry("B", "Live Sports", "b")
        assign_channel_numbers([first, second])
        registry = json.loads((ROOT / "channel_numbers.json").read_text(encoding="utf-8"))
        numbers = [record["number"] for record in registry.values()]
        self.assertEqual(len(numbers), len(set(numbers)))


class GroupConfigTests(unittest.TestCase):
    def test_exact_groups(self):
        self.assertEqual(GROUPS, [
            "Live Sports",
            "News | International",
            "Canada | General & News",
            "Canada | Sports & Regional",
            "USA | Networks & Entertainment",
            "USA | News & Business",
            "USA | Kids & Family",
            "USA | Documentary & Lifestyle",
            "India | Hindi & General",
            "India | Punjabi & Regional",
            "India | South (Tamil & Telugu)",
            "Pakistan",
            "Movies",
            "Music",
        ])

    def test_ranges_do_not_overlap(self):
        ranges = sorted(GROUP_RANGES.values())
        for (_, first_high), (second_low, _) in zip(ranges, ranges[1:]):
            self.assertLess(first_high, second_low)


if __name__ == "__main__":
    unittest.main()
