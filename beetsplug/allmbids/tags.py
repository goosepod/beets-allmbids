"""List-valued MediaFile fields and conservative, format-independent writes."""
import os
from pathlib import Path
import shutil
import stat as stat_module
import tempfile

from mediafile import (
    MediaFile, ListMediaField, ListStorageStyle,
    MP3ListDescStorageStyle, MP4ListStorageStyle,
)
from mutagen.id3 import Frame

from .core import MANAGED_TAGS

SUPPORTED_TYPES = frozenset({"flac", "mp3", "aac", "alac", "opus"})
FIELD_NAMES = {key: f"allmbids_{key.lower()}" for key in MANAGED_TAGS}
MP4_PREFIX = "----:com.apple.iTunes:"

# Plugin-specific names keep these distinct from Beets' standard composer IDs.
# All tag reads and writes go through MediaFile's list descriptors.
for key, field in FIELD_NAMES.items():
    MediaFile.add_field(field, ListMediaField(
        ListStorageStyle(key),
        MP3ListDescStorageStyle(desc=key),
        MP4ListStorageStyle(MP4_PREFIX + key),
    ))


def read_values(audio, key):
    return list(getattr(audio, FIELD_NAMES[key]) or [])


def _raw_value(value):
    """Compare unrelated tag contents, allowing ID3 text encoding normalization."""
    if isinstance(value, Frame):
        return (type(value).__name__, {
            name: _raw_value(item) for name, item in vars(value).items()
            if not name.startswith("_") and name != "encoding"
        })
    if isinstance(value, (list, tuple)):
        return [_raw_value(item) for item in value]
    if isinstance(value, bytes):
        return (bytes(value), getattr(value, "dataformat", None))
    return value


def _unrelated_tags(audio, updates):
    excluded = set(updates)
    if audio.type in {"aac", "alac"}:
        excluded = {MP4_PREFIX + key for key in updates}
    result = {}
    for key, value in audio.mgfile.tags.items():
        if audio.type == "mp3":
            if key.startswith("TXXX:") and key[5:].upper() in updates:
                continue
        else:
            storage_key = key.upper() if audio.type in {"flac", "opus"} else key
            if storage_key in excluded:
                continue
        result[key] = _raw_value(value)
    return result


def _stream_info(audio):
    return (audio.type, audio.samplerate, audio.channels, audio.length,
            getattr(audio.mgfile.info, "md5_signature", None))


def _images(audio):
    return [(image.data, image.desc, image.type, image.mime_type) for image in (audio.images or [])]


def changes(audio, desired):
    updates = {}
    for key, values in desired.items():
        if key not in MANAGED_TAGS or not isinstance(values, list) or not all(isinstance(v, str) for v in values):
            raise ValueError(f"Unsupported contributor tag: {key}")
        old = read_values(audio, key)
        merged = list(old)
        for value in values:
            if value not in merged:
                merged.append(value)
        if merged != old:
            updates[key] = {"before": old, "after": merged}
    return updates


def enrich(path, desired, *, write=False):
    path = Path(os.fsdecode(path))
    stat = path.lstat() if write else None
    if write and (not stat_module.S_ISREG(stat.st_mode) or stat.st_nlink != 1):
        raise ValueError("Writes require a regular file without symlinks or hardlinks")
    audio = MediaFile(path)
    if audio.type not in SUPPORTED_TYPES:
        raise ValueError(f"Unsupported audio format: {audio.format}")
    updates = changes(audio, desired)
    if not write or not updates:
        return updates
    backup = path.with_name(path.name + ".allmbids.bak")
    descriptor, temporary = tempfile.mkstemp(prefix=".allmbids-", suffix=path.suffix, dir=path.parent)
    os.close(descriptor)
    try:
        shutil.copy2(path, temporary)
        staged = MediaFile(temporary)
        for key, change in updates.items():
            setattr(staged, FIELD_NAMES[key], change["after"])
        staged.save()
        verified = MediaFile(temporary)
        if _stream_info(verified) != _stream_info(audio):
            raise ValueError("Audio stream properties changed during staging")
        for key, change in updates.items():
            if read_values(verified, key) != change["after"]:
                raise ValueError(f"Tag verification failed: {key}")
        if _unrelated_tags(verified, updates) != _unrelated_tags(audio, updates):
            raise ValueError("Unrelated tags changed during staging")
        if _images(verified) != _images(audio):
            raise ValueError("Embedded pictures changed")
        current = path.lstat()
        if (current.st_ino, current.st_size, current.st_mtime_ns, current.st_ctime_ns) != (
                stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns):
            raise ValueError("Source changed while preparing tags")
        # Exclusive creation: never replace an earlier backup.
        with backup.open("xb") as output:
            try:
                with path.open("rb") as source:
                    shutil.copyfileobj(source, output)
                output.flush()
                os.fsync(output.fileno())
            except BaseException:
                output.close()
                backup.unlink()
                raise
        shutil.copystat(path, backup)
        current = path.lstat()
        if (current.st_ino, current.st_size, current.st_mtime_ns, current.st_ctime_ns) != (
                stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns):
            raise ValueError("Source changed while creating backup; inspect the retained backup")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return updates
