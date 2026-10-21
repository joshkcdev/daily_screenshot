"""The Environment Canada pages captured each day, one Drive folder each.

Each location uploads to its own subfolder of `Weather Scans` so every folder
holds a single date-ordered series, which the verifier's duplicate and
missed-run checks rely on.
"""

from typing import NamedTuple


class Location(NamedTuple):
    slug: str  # used in filenames: weather_<slug>_YYYY-MM-DD.png
    name: str
    url: str
    folder_env: str  # env var holding this location's Drive folder ID


LOCATIONS = [
    Location(
        "duncan",
        "Duncan",
        "https://weather.gc.ca/en/location/index.html?coords=48.779,-123.702",
        "GOOGLE_DRIVE_FOLDER_ID_DUNCAN",
    ),
    Location(
        "lake_cowichan",
        "Lake Cowichan",
        "https://weather.gc.ca/en/location/index.html?coords=48.825,-124.054",
        "GOOGLE_DRIVE_FOLDER_ID_LAKE_COWICHAN",
    ),
]


def get_location(slug: str) -> Location:
    for location in LOCATIONS:
        if location.slug == slug:
            return location
    raise KeyError(f"Unknown location {slug!r}; expected one of {[l.slug for l in LOCATIONS]}")
