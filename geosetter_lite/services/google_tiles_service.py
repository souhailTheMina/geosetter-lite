"""
Google Tiles Service - Sessions for Google's 2D map tiles (Map Tiles API)

Every tile request has to carry a session token, created up front for one map
style. A token stays valid for about two weeks, so tokens are cached on disk and
reused across restarts rather than created on every launch.
See https://developers.google.com/maps/documentation/tile/2d-tiles-overview
"""
import hashlib
import json
import time
from typing import Dict

import requests

from ..core.config import Config


SESSION_URL = 'https://tile.googleapis.com/v1/createSession'
TILE_URL = 'https://tile.googleapis.com/v1/2dtiles/{{z}}/{{x}}/{{y}}?session={session}&key={key}'
VIEWPORT_URL = 'https://tile.googleapis.com/tile/v1/viewport'

# Language of the labels, and the region whose conventions borders and place
# names follow (matching the map's default location)
LANGUAGE = 'en-US'
REGION = 'SA'

# Map styles offered, keyed by id, with the session request for each
LAYER_SATELLITE = 'satellite'
LAYER_HYBRID = 'hybrid'
LAYER_ROADMAP = 'roadmap'
_SESSION_REQUESTS = {
    LAYER_SATELLITE: {'mapType': 'satellite'},
    LAYER_HYBRID: {'mapType': 'satellite', 'layerTypes': ['layerRoadmap']},
    LAYER_ROADMAP: {'mapType': 'roadmap'},
}

CACHE_FILE = Config.CONFIG_DIR / 'google_tile_sessions.json'
# Renew a little before Google expires a token, so one never lapses mid-session
EXPIRY_MARGIN_SECONDS = 24 * 3600
REQUEST_TIMEOUT_SECONDS = 10


class GoogleTilesError(Exception):
    """A session could not be created, with a message fit to show the user"""


def _key_fingerprint(api_key: str) -> str:
    """Identify the key a cache belongs to without writing the key itself"""
    return hashlib.sha256(api_key.encode('utf-8')).hexdigest()


def create_session(api_key: str, layer_id: str) -> Dict[str, str]:
    """
    Create a tile session for one map style

    Returns:
        Dict with 'session' (token) and 'expiry' (unix time, seconds) keys

    Raises:
        GoogleTilesError if Google refuses the request or cannot be reached
    """
    body = dict(_SESSION_REQUESTS[layer_id], language=LANGUAGE, region=REGION,
                highDpi=True)
    try:
        response = requests.post(SESSION_URL, params={'key': api_key}, json=body,
                                 timeout=REQUEST_TIMEOUT_SECONDS)
    except requests.RequestException as e:
        raise GoogleTilesError(f'Could not reach Google: {e}') from e

    if not response.ok:
        # Google explains the refusal (bad key, API not enabled, no billing...)
        try:
            message = response.json()['error']['message']
        except (ValueError, KeyError, TypeError):
            message = response.text.strip() or response.reason
        raise GoogleTilesError(f'Google refused the request ({response.status_code}): {message}')

    data = response.json()
    return {'session': data['session'], 'expiry': str(data['expiry'])}


def load_cached_sessions(api_key: str) -> Dict[str, Dict[str, str]]:
    """Return cached sessions for this key if all are still valid, else an empty dict"""
    try:
        with open(CACHE_FILE, 'r') as f:
            cached = json.load(f)
        if cached.get('key') != _key_fingerprint(api_key):
            return {}
        sessions = cached['sessions']
        renew_after = time.time() + EXPIRY_MARGIN_SECONDS
        if (set(sessions) != set(_SESSION_REQUESTS)
                or any(int(s['expiry']) < renew_after for s in sessions.values())):
            return {}
        return sessions
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {}


def fetch_sessions(api_key: str) -> Dict[str, Dict[str, str]]:
    """
    Create a session for every map style and cache them

    Raises:
        GoogleTilesError if any session cannot be created
    """
    sessions = {layer_id: create_session(api_key, layer_id) for layer_id in _SESSION_REQUESTS}

    Config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, 'w') as f:
        json.dump({'key': _key_fingerprint(api_key), 'sessions': sessions}, f)
    return sessions


def tile_url(api_key: str, session: str) -> str:
    """Leaflet URL template for the tiles of one session"""
    return TILE_URL.format(session=session, key=api_key)
