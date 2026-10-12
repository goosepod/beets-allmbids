import io
import json
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

import pytest

from beetsplug.allmbids.client import MusicBrainzClient, _RateLimitedRedirectHandler
from beetsplug.allmbids._version import __version__
from urllib.request import Request
from test_core import R, W


def harness(responses):
    now, requests, sleeps = [0.0], [], []
    def sleep(delay):
        sleeps.append(delay)
        now[0] += delay
    def opener(request, timeout):
        requests.append((request, timeout, now[0]))
        result = responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return io.StringIO(json.dumps(result))
    return MusicBrainzClient("https://example.org/contact", opener=opener,
                            clock=lambda: now[0], sleep=sleep), requests, sleeps


def test_cache_includes_user_agent_and_rate_limit():
    client, requests, sleeps = harness([{"id": R}, {"id": W}])
    assert client.lookup("recording", R) == {"id": R}
    client.lookup("recording", R)
    client.lookup("work", W)
    assert len(requests) == 2
    assert requests[1][2] - requests[0][2] >= 1
    request, timeout, _ = requests[0]
    assert parse_qs(urlparse(request.full_url).query)["inc"] == ["artist-rels+work-rels"]
    assert f"beets-allmbids/{__version__}" in request.get_header("User-agent")
    assert timeout == 30


def test_retry_transient_error():
    error = HTTPError("test", 503, "busy", {"Retry-After": "3"}, None)
    client, requests, sleeps = harness([error, {"id": R}])
    client.lookup("recording", R)
    assert len(requests) == 2 and 3 in sleeps


def test_failure_is_not_cached():
    error = HTTPError("test", 404, "missing", {}, None)
    client, requests, _ = harness([error, {"id": R}])
    with pytest.raises(HTTPError):
        client.lookup("recording", R)
    client.lookup("recording", R)
    assert len(requests) == 2


def test_mismatched_entity_rejected():
    client, _, _ = harness([{"id": W}])
    with pytest.raises(ValueError):
        client.lookup("recording", R)


def test_contact_required():
    with pytest.raises(ValueError):
        MusicBrainzClient("")


def test_retries_are_bounded():
    errors = [HTTPError("test", 503, "busy", {}, None) for _ in range(3)]
    client, requests, _ = harness(errors)
    with pytest.raises(HTTPError):
        client.lookup("recording", R)
    assert len(requests) == 3


def test_merged_mbid_redirect_and_canonical_id_are_cached():
    class Response(io.StringIO):
        def geturl(self):
            return f"https://musicbrainz.org/ws/2/recording/{W}?fmt=json"
    calls = []
    def opener(request, timeout):
        calls.append(request)
        return Response(json.dumps({"id": W}))
    client = MusicBrainzClient("https://example.org/contact", opener=opener)
    assert client.lookup("recording", R) == {"id": W}
    assert client.lookup("recording", W) == {"id": W}
    assert client.lookup("recording", R) == {"id": W}
    assert len(calls) == 1


@pytest.mark.parametrize("destination", [
    f"https://other.example/ws/2/recording/{W}",
    f"http://musicbrainz.org/ws/2/recording/{W}",
    f"https://musicbrainz.org/ws/2/work/{W}",
    "https://musicbrainz.org/doc/Recording",
])
def test_unexpected_redirect_endpoint_rejected(destination):
    class Response(io.StringIO):
        def geturl(self):
            return destination
    client = MusicBrainzClient("https://example.org/contact",
                              opener=lambda *args, **kwargs: Response(json.dumps({"id": W})))
    with pytest.raises(ValueError):
        client.lookup("recording", R)


def test_redirect_hop_is_rate_limited():
    client, _, sleeps = harness([])
    client._pace()
    handler = _RateLimitedRedirectHandler(client._pace)
    request = Request(f"https://musicbrainz.org/ws/2/recording/{R}")
    redirected = handler.redirect_request(request, None, 301, "Merged", {},
                                          f"https://musicbrainz.org/ws/2/recording/{W}")
    assert redirected.full_url.endswith(W)
    assert sleeps == [1.1]
