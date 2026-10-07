"""
Imagery Service - Historical satellite imagery releases from Esri World Imagery Wayback

Esri archives every published version of World Imagery. Each archived release is
served as its own tile set, which lets the map show an area as it looked in a
given year rather than only the current imagery.
See https://livingatlas.arcgis.com/wayback/
"""
import json
import re
import time
from typing import List, Dict

import requests

from ..core.config import Config


WAYBACK_CONFIG_URL = ('https://s3-us-west-2.amazonaws.com/config.maptiles.arcgis.com/'
                      'waybackconfig.json')
WAYBACK_TILE_URL = ('https://wayback.maptiles.arcgis.com/arcgis/rest/services/World_Imagery/'
                    'WMTS/1.0.0/default028mm/MapServer/tile/{release}/{{z}}/{{y}}/{{x}}')

# Esri publishes a new release every few weeks, so a weekly refresh is plenty
CACHE_FILE = Config.CONFIG_DIR / 'imagery_releases.json'
CACHE_MAX_AGE_SECONDS = 7 * 24 * 3600
REQUEST_TIMEOUT_SECONDS = 10

_RELEASE_DATE = re.compile(r'(\d{4})-(\d{2})-(\d{2})')

# Last release of each year as of October 2026, as (year, date, release number).
# Offered when the list has never been downloaded, such as on a network that
# blocks the Wayback configuration file, so the year selector is never empty.
# Archived releases do not change, so these stay valid; only newer years are
# missing until a download succeeds.
_BUILTIN_RELEASES = (
    ('2026', '2026-09-24', '63116'),
    ('2025', '2025-12-18', '13192'),
    ('2024', '2024-12-12', '16453'),
    ('2023', '2023-12-07', '56102'),
    ('2022', '2022-12-14', '45134'),
    ('2021', '2021-12-21', '26120'),
    ('2020', '2020-12-16', '29260'),
    ('2019', '2019-12-12', '4756'),
    ('2018', '2018-12-14', '23448'),
    ('2017', '2017-11-16', '25521'),
    ('2016', '2016-12-20', '18966'),
    ('2015', '2015-12-16', '28163'),
    ('2014', '2014-12-30', '5844'),
)


def _parse_yearly_releases(wayback_config: dict) -> List[Dict[str, str]]:
    """
    Reduce the full release list to the last release of each year

    Returns:
        Dicts with 'year', 'date' and 'url' keys, newest year first
    """
    latest_by_year: Dict[str, tuple] = {}
    for release, item in wayback_config.items():
        match = _RELEASE_DATE.search(item.get('itemTitle', ''))
        if not match or not str(release).isdigit():
            continue
        date = match.group(0)
        year = match.group(1)
        if year not in latest_by_year or date > latest_by_year[year][0]:
            latest_by_year[year] = (date, release)

    return [
        {'year': year, 'date': date, 'url': WAYBACK_TILE_URL.format(release=release)}
        for year, (date, release) in sorted(latest_by_year.items(), reverse=True)
    ]


def load_cached_releases() -> List[Dict[str, str]]:
    """Return the releases saved by the last successful fetch, else the built-in list"""
    try:
        with open(CACHE_FILE, 'r') as f:
            releases = json.load(f).get('releases', [])
        if releases:
            return releases
    except (OSError, ValueError, AttributeError):
        pass
    return [
        {'year': year, 'date': date, 'url': WAYBACK_TILE_URL.format(release=release)}
        for year, date, release in _BUILTIN_RELEASES
    ]


def cache_is_fresh() -> bool:
    """Whether the cached release list is recent enough to skip a fetch"""
    try:
        return time.time() - CACHE_FILE.stat().st_mtime < CACHE_MAX_AGE_SECONDS
    except OSError:
        return False


def fetch_releases() -> List[Dict[str, str]]:
    """
    Download the current release list and cache it

    Raises:
        requests.RequestException or ValueError if the list cannot be retrieved
    """
    response = requests.get(WAYBACK_CONFIG_URL, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    releases = _parse_yearly_releases(response.json())
    if not releases:
        raise ValueError('No imagery releases found in Wayback configuration')

    Config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, 'w') as f:
        json.dump({'releases': releases}, f)
    return releases
