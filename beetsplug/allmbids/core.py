"""MusicBrainz JSON relationships and an intentionally small tag vocabulary."""
from uuid import UUID

# Semantic mappings, implemented independently; see docs/design.md for sources.
ROLE_MAP = {
    "arranger": "arranger", "instrument arranger": "arranger",
    "vocal arranger": "arranger", "orchestrator": "arranger",
    "composer": "composer", "lyricist": "lyricist", "librettist": "lyricist",
    "writer": "writer", "conductor": "conductor", "producer": "producer",
    "remixer": "remixer", "mix": "mixer", "mix-DJ": "djmixer",
    "engineer": "engineer", "audio": "engineer", "sound": "engineer",
    "live sound": "engineer", "recording": "engineer", "mastering": "engineer",
    "audio director": "director", "video director": "director",
}
SPECIAL_PERFORMERS = {
    "chorus master": "chorus master", "concertmaster": "concertmaster",
    "performing orchestra": "orchestra",
}
PREFIXES = ("additional", "guest", "minor", "solo")
MANAGED_TAGS = frozenset(
    f"MUSICBRAINZ_{role.upper()}_ID"
    for role in {*ROLE_MAP.values(), "performer", "label"}
)


def mbid(value):
    """Reject URLs and malformed IDs; normalize UUID case."""
    if not isinstance(value, str) or len(value) != 36:
        raise ValueError(f"Invalid MusicBrainz ID: {value!r}")
    result = str(UUID(value))
    if result != value.lower():
        raise ValueError(f"Invalid MusicBrainz ID: {value!r}")
    return result


class CollectedTags(dict):
    """Tag values with display-only attribution; no extra lookup requests."""

    def __init__(self):
        super().__init__()
        self.contributors = []


def add(tags, role, value, *, contributor=None, source=None, relationship=None):
    key = f"MUSICBRAINZ_{role.upper()}_ID"
    values = tags.setdefault(key, [])
    if value not in values:
        values.append(value)
    if isinstance(tags, CollectedTags) and contributor is not None:
        detail = {"tag": key, "value": value, "mbid": mbid(contributor["id"]),
                  "name": contributor.get("name"), "relationship": relationship,
                  "source": source}
        if detail not in tags.contributors:
            tags.contributors.append(detail)


def artist_tags(entity, tags, disc=None, *, source=None):
    for relation in entity.get("relations", []):
        if relation.get("target-type") != "artist":
            continue
        kind = relation.get("type")
        if kind not in ROLE_MAP and kind not in SPECIAL_PERFORMERS and kind not in {"instrument", "vocal", "performer"}:
            continue
        artist = relation.get("artist") or {}
        if not artist.get("id"):
            continue
        identifier = mbid(artist["id"])
        attributes = relation.get("attributes", [])
        # Release relationships can apply only to specified media.
        media = [a for a in attributes if a.startswith("medium ")]
        if media and f"medium {disc}" not in media:
            continue
        def emit(role, value):
            add(tags, role, value, contributor=artist, source=source, relationship=kind)
        if kind in ROLE_MAP:
            emit(ROLE_MAP[kind], identifier)
        elif kind in SPECIAL_PERFORMERS:
            emit("performer", f"{identifier} ({SPECIAL_PERFORMERS[kind]})")
        elif kind in {"instrument", "vocal", "performer"}:
            qualifiers = [p for p in PREFIXES if p in attributes]
            roles = [a for a in attributes if a not in PREFIXES and not a.startswith("medium ")]
            if not roles:
                roles = [{"instrument": "instrument", "vocal": "vocals", "performer": ""}[kind]]
            for role in roles:
                role = " ".join([*qualifiers, role]).strip()
                emit("performer", f"{identifier} ({role})" if role else identifier)


def collect(client, recording_id, release_id=None, disc=None):
    """Fetch all required entities before constructing an update for a file."""
    tags = CollectedTags()
    def source(kind, entity, requested):
        return {"type": kind, "id": entity.get("id", requested), "title": entity.get("title")}
    if release_id:
        release = client.lookup("release", mbid(release_id))
        release_source = source("release", release, release_id)
        artist_tags(release, tags, disc, source=release_source)
        for entry in release.get("label-info", []):
            label = entry.get("label") or {}
            if label.get("id"):
                add(tags, "label", mbid(label["id"]), contributor=label,
                    source=release_source, relationship="label")
    recording = client.lookup("recording", mbid(recording_id))
    artist_tags(recording, tags, disc, source=source("recording", recording, recording_id))
    seen = set()
    for relation in recording.get("relations", []):
        if relation.get("target-type") != "work" or relation.get("type") != "performance":
            continue
        work_id = mbid((relation.get("work") or {}).get("id"))
        if work_id not in seen:
            work = client.lookup("work", work_id)
            artist_tags(work, tags, disc, source=source("work", work, work_id))
            seen.add(work_id)
    return tags
