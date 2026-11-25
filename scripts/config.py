"""Shared, authoritative configuration for IPTV Combined.

This module is the single source of truth for group names, ordering, reserved
channel-number ranges, and split-playlist membership. Both the builder and
validator must import these values.
"""

GROUPS = [
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
]

GROUP_INDEX = {name: index for index, name in enumerate(GROUPS)}

GROUP_RANGES = {
    "Live Sports": (1000, 1999),
    "News | International": (2000, 2999),
    "Canada | General & News": (3000, 3999),
    "Canada | Sports & Regional": (4000, 4999),
    "USA | Networks & Entertainment": (5000, 9999),
    "USA | News & Business": (10000, 11999),
    "USA | Kids & Family": (12000, 13999),
    "USA | Documentary & Lifestyle": (14000, 15999),
    "India | Hindi & General": (16000, 17999),
    "India | Punjabi & Regional": (18000, 19999),
    "India | South (Tamil & Telugu)": (20000, 21999),
    "Pakistan": (22000, 23999),
    "Movies": (24000, 29999),
    "Music": (30000, 34999),
}

# A channel may belong to one combined-playlist group but also appear in one or
# more standalone regional/category playlists. These rules use the original
# country metadata and an explicit news category, not the final group name.
SPLIT_PLAYLISTS = {
    "sports.m3u": {"groups": {"Live Sports"}},
    "news.m3u": {"categories": {"news"}},
    "canada.m3u": {"countries": {"ca"}},
    "usa.m3u": {"countries": {"us"}},
    "india.m3u": {"countries": {"in"}},
    "pakistan.m3u": {"countries": {"pk"}},
    "movies.m3u": {"groups": {"Movies"}},
    "music.m3u": {"groups": {"Music"}},
}

NEWS_CATEGORY = "news"

# Names that must no longer appear in generated playlists or validation rules.
OBSOLETE_GROUPS = {
    "International News",
    "Canada",
    "USA",
    "India",
}

# Subjective playlists are intentionally prohibited in this public repository.
FORBIDDEN_GROUPS = {
    "Top Picks",
    "Favorites",
}

assert len(GROUPS) == len(set(GROUPS))
assert set(GROUP_RANGES) == set(GROUPS)
assert all(low <= high for low, high in GROUP_RANGES.values())
