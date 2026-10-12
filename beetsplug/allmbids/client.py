"""Read-only MusicBrainz client with bounded retries and per-run caching."""
import json
import time
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener

from .core import mbid
from ._version import __version__

INCLUDES = {
    "recording": "artist-rels+work-rels",
    "release": "artist-rels+labels",
    "work": "artist-rels",
}


def _lookup_id(url, entity):
    """Accept only the same MusicBrainz entity endpoint, including merged IDs."""
    destination = urlsplit(url)
    if (destination.scheme != "https" or destination.hostname != "musicbrainz.org"
            or destination.port not in {None, 443} or destination.username or destination.password):
        raise ValueError("Unexpected MusicBrainz lookup destination")
    parts = destination.path.strip("/").split("/")
    if len(parts) != 4 or parts[:3] != ["ws", "2", entity]:
        raise ValueError("Unexpected MusicBrainz entity endpoint")
    return mbid(parts[3])


class _RateLimitedRedirectHandler(HTTPRedirectHandler):
    def __init__(self, pace):
        self.pace = pace

    def redirect_request(self, request, response, code, message, headers, newurl):
        entity = urlsplit(request.full_url).path.strip("/").split("/")[2]
        _lookup_id(newurl, entity)
        redirected = super().redirect_request(request, response, code, message, headers, newurl)
        if redirected is not None:
            self.pace()
        return redirected


class MusicBrainzClient:
    def __init__(self, contact, *, opener=None, clock=time.monotonic, sleep=time.sleep):
        if not contact.strip() or "\n" in contact or "\r" in contact:
            raise ValueError("Set allmbids.contact to your email or a contact URL")
        self.user_agent = f"beets-allmbids/{__version__} ({contact})"
        self.clock, self.sleep = clock, sleep
        self.opener = opener or build_opener(_RateLimitedRedirectHandler(self._pace)).open
        self.cache = {}
        self.last_request = None

    def _pace(self):
        if self.last_request is not None:
            self.sleep(max(0, 1.1 - (self.clock() - self.last_request)))
        self.last_request = self.clock()

    def lookup(self, entity, identifier):
        identifier = mbid(identifier)
        key = (entity, identifier)
        if key in self.cache:
            return self.cache[key]
        query = urlencode({"inc": INCLUDES[entity], "fmt": "json"})
        request = Request(f"https://musicbrainz.org/ws/2/{entity}/{identifier}?{query}",
                          headers={"User-Agent": self.user_agent, "Accept": "application/json"})
        for attempt in range(3):
            self._pace()
            try:
                with self.opener(request, timeout=30) as response:
                    final_url = response.geturl() if hasattr(response, "geturl") else request.full_url
                    result = json.load(response)
                canonical_id = _lookup_id(final_url, entity)
                if not isinstance(result, dict) or mbid(result.get("id")) != canonical_id:
                    raise ValueError("MusicBrainz returned an unexpected entity")
                self.cache[key] = result
                self.cache[(entity, canonical_id)] = result
                return result
            except HTTPError as error:
                if error.code not in {429, 502, 503, 504} or attempt == 2:
                    raise
                try:
                    delay = float(error.headers.get("Retry-After", 2 ** (attempt + 1)))
                except (ValueError, TypeError):
                    delay = 2 ** (attempt + 1)
                self.sleep(max(1.1, min(delay, 60)))
            except (HTTPException, URLError, TimeoutError, ConnectionError,
                    json.JSONDecodeError, UnicodeDecodeError):
                # Broken connections and truncated bodies are safe to retry:
                # lookups are read-only and no partial response is cached.
                if attempt == 2:
                    raise
                self.sleep(2 ** (attempt + 1))
