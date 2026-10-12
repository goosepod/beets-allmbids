"""Read-only MusicBrainz client with bounded retries and per-run caching."""
import json
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .core import mbid

INCLUDES = {
    "recording": "artist-rels+work-rels",
    "release": "artist-rels+labels",
    "work": "artist-rels",
}


class MusicBrainzClient:
    def __init__(self, contact, *, opener=urlopen, clock=time.monotonic, sleep=time.sleep):
        if not contact.strip() or "\n" in contact or "\r" in contact:
            raise ValueError("Set allmbids.contact to your email or a contact URL")
        self.user_agent = f"beets-allmbids/0.1.0 ({contact})"
        self.opener, self.clock, self.sleep = opener, clock, sleep
        self.cache = {}
        self.last_request = None

    def lookup(self, entity, identifier):
        identifier = mbid(identifier)
        key = (entity, identifier)
        if key in self.cache:
            return self.cache[key]
        query = urlencode({"inc": INCLUDES[entity], "fmt": "json"})
        request = Request(f"https://musicbrainz.org/ws/2/{entity}/{identifier}?{query}",
                          headers={"User-Agent": self.user_agent, "Accept": "application/json"})
        for attempt in range(3):
            if self.last_request is not None:
                self.sleep(max(0, 1.1 - (self.clock() - self.last_request)))
            self.last_request = self.clock()
            try:
                with self.opener(request, timeout=30) as response:
                    result = json.load(response)
                if not isinstance(result, dict) or mbid(result.get("id")) != identifier:
                    raise ValueError("MusicBrainz returned an unexpected entity")
                self.cache[key] = result
                return result
            except HTTPError as error:
                if error.code not in {429, 502, 503, 504} or attempt == 2:
                    raise
                try:
                    delay = float(error.headers.get("Retry-After", 2 ** (attempt + 1)))
                except (ValueError, TypeError):
                    delay = 2 ** (attempt + 1)
                self.sleep(max(1.1, min(delay, 60)))
