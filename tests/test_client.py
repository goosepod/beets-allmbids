import io
import json
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

import pytest

from beetsplug.allmbids.client import MusicBrainzClient
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
    assert "beets-allmbids/0.2.0" in request.get_header("User-agent")
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
