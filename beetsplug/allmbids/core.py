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


def add(tags, role, value):
    key = f"MUSICBRAINZ_{role.upper()}_ID"
    values = tags.setdefault(key, [])
    if value not in values:
        values.append(value)


def artist_tags(entity, tags, disc=None):
    for relation in entity.get("relations", []):
        if relation.get("target-type") != "artist":
            continue
        artist = relation.get("artist") or {}
        if not artist.get("id"):
            continue
        identifier = mbid(artist["id"])
        kind = relation.get("type")
        attributes = relation.get("attributes", [])
        # Release relationships can apply only to specified media.
        media = [a for a in attributes if a.startswith("medium ")]
        if media and f"medium {disc}" not in media:
            continue
        if kind in ROLE_MAP:
            add(tags, ROLE_MAP[kind], identifier)
        elif kind in SPECIAL_PERFORMERS:
            add(tags, "performer", f"{identifier} ({SPECIAL_PERFORMERS[kind]})")
        elif kind in {"instrument", "vocal", "performer"}:
            qualifiers = [p for p in PREFIXES if p in attributes]
            roles = [a for a in attributes if a not in PREFIXES and not a.startswith("medium ")]
            if not roles:
                roles = [{"instrument": "instrument", "vocal": "vocals", "performer": ""}[kind]]
            for role in roles:
                role = " ".join([*qualifiers, role]).strip()
                add(tags, "performer", f"{identifier} ({role})" if role else identifier)


def collect(client, recording_id, release_id=None, disc=None):
    """Fetch all required entities before constructing an update for a file."""
    tags = {}
    if release_id:
        release = client.lookup("release", mbid(release_id))
        artist_tags(release, tags, disc)
        for entry in release.get("label-info", []):
            label = entry.get("label") or {}
            if label.get("id"):
                add(tags, "label", mbid(label["id"]))
    recording = client.lookup("recording", mbid(recording_id))
    artist_tags(recording, tags, disc)
    seen = set()
    for relation in recording.get("relations", []):
        if relation.get("target-type") != "work" or relation.get("type") != "performance":
            continue
        work_id = mbid((relation.get("work") or {}).get("id"))
        if work_id not in seen:
            artist_tags(client.lookup("work", work_id), tags, disc)
            seen.add(work_id)
    return tags

