from copy import deepcopy

import pytest

from beetsplug.allmbids.core import artist_tags, collect, mbid

A = "11111111-1111-4111-8111-111111111111"
B = "22222222-2222-4222-8222-222222222222"
R = "33333333-3333-4333-8333-333333333333"
W = "44444444-4444-4444-8444-444444444444"
L = "55555555-5555-4555-8555-555555555555"


def relation(kind, identifier=A, **extra):
    return {"type": kind, "target-type": "artist", "artist": {"id": identifier}, **extra}


def test_roles_multivalue_and_immutable_input():
    entity = {"relations": [relation("instrument", attributes=["guitar", "piano", "guest"]),
                            relation("producer"), relation("producer"), relation("producer", B),
                            relation("performer"), relation("vocal"), relation("unknown"),
                            relation("performing orchestra")]}
    original = deepcopy(entity)
    tags = {}
    artist_tags(entity, tags)
    assert entity == original
    assert tags["MUSICBRAINZ_PRODUCER_ID"] == [A, B]
    assert tags["MUSICBRAINZ_PERFORMER_ID"] == [f"{A} (guest guitar)", f"{A} (guest piano)",
                                                 A, f"{A} (vocals)", f"{A} (orchestra)"]


def test_release_medium_scope():
    entity = {"relations": [relation("mix-DJ", attributes=["medium 2"])]}
    tags = {}
    artist_tags(entity, tags, disc=1)
    assert not tags
    artist_tags(entity, tags, disc=2)
    assert tags == {"MUSICBRAINZ_DJMIXER_ID": [A]}


def test_release_recording_work_and_labels():
    calls = []
    work_relation = {"type": "performance", "target-type": "work", "work": {"id": W}}
    entities = {
        "release": {"relations": [relation("producer")], "label-info": [
            {"label": {"id": L}}, {"label": {"id": L}}, {"label": None}]},
        "recording": {"relations": [relation("producer"), relation("producer", B),
                                     work_relation, work_relation]},
        "work": {"relations": [relation("composer"), relation("lyricist", B)]},
    }
    class Client:
        def lookup(self, entity, identifier):
            calls.append((entity, identifier))
            return entities[entity]
    tags = collect(Client(), R, L)
    assert calls == [("release", L), ("recording", R), ("work", W)]
    assert tags["MUSICBRAINZ_PRODUCER_ID"] == [A, B]
    assert tags["MUSICBRAINZ_COMPOSER_ID"] == [A]
    assert tags["MUSICBRAINZ_LYRICIST_ID"] == [B]
    assert tags["MUSICBRAINZ_LABEL_ID"] == [L]


@pytest.mark.parametrize("value", [None, "", "garbage", "https://musicbrainz.org/recording/" + R])
def test_invalid_id(value):
    with pytest.raises((ValueError, TypeError)):
        mbid(value)


def test_attribution_keeps_each_source_and_names_without_extra_lookups():
    calls = []
    producer = relation("producer")
    producer["artist"]["name"] = "Contributor 東京"
    entities = {
        "release": {"id": L, "title": "Release", "relations": [producer],
                    "label-info": [{"label": {"id": B, "name": "Label"}}]},
        "recording": {"id": R, "title": "Recording", "relations": [producer,
            {"type": "performance", "target-type": "work", "work": {"id": W}}]},
        "work": {"id": W, "title": "Work", "relations": [relation("composer")]},
    }
    class Client:
        def lookup(self, kind, identifier):
            calls.append((kind, identifier))
            return entities[kind]
    tags = collect(Client(), R, L)
    assert tags["MUSICBRAINZ_PRODUCER_ID"] == [A]
    details = [d for d in tags.contributors if d["tag"] == "MUSICBRAINZ_PRODUCER_ID"]
    assert [d["source"]["type"] for d in details] == ["release", "recording"]
    assert all(d["name"] == "Contributor 東京" and d["mbid"] == A for d in details)
    assert tags.contributors[-1]["source"] == {"type": "work", "id": W, "title": "Work"}
    assert tags.contributors[-1]["name"] is None
    assert calls == [("release", L), ("recording", R), ("work", W)]


def test_unknown_relationship_does_not_validate_unused_identifier():
    tags = {}
    artist_tags({"relations": [relation("unknown", "unused malformed id")]}, tags)
    assert tags == {}
