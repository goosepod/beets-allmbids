"""Merge-only FLAC writes, staged beside the original and backed up first."""
import os
from pathlib import Path
import shutil
import stat as stat_module
import tempfile

from mutagen.flac import FLAC

from .core import MANAGED_TAGS


def changes(audio, desired):
    updates = {}
    for key, values in desired.items():
        if key not in MANAGED_TAGS or not isinstance(values, list) or not all(isinstance(v, str) for v in values):
            raise ValueError(f"Unsupported contributor tag: {key}")
        old = list(audio.get(key, []))
        merged = list(old)
        for value in values:
            if value not in merged:
                merged.append(value)
        if merged != old:
            updates[key] = {"before": old, "after": merged}
    return updates


def enrich(path, desired, *, write=False):
    path = Path(os.fsdecode(path))
    audio = FLAC(path)
    updates = changes(audio, desired)
    if not write or not updates:
        return updates
    stat = path.lstat()
    if not stat_module.S_ISREG(stat.st_mode) or path.is_symlink() or stat.st_nlink != 1:
        raise ValueError("Writes require a regular file without symlinks or hardlinks")
    backup = path.with_name(path.name + ".allmbids.bak")
    descriptor, temporary = tempfile.mkstemp(prefix=".allmbids-", suffix=".flac", dir=path.parent)
    os.close(descriptor)
    try:
        shutil.copy2(path, temporary)
        staged = FLAC(temporary)
        for key, change in updates.items():
            staged[key] = change["after"]
        staged.save()
        verified = FLAC(temporary)
        if verified.info.md5_signature != audio.info.md5_signature:
            raise ValueError("FLAC stream identity changed during staging")
        for key, change in updates.items():
            if verified.get(key) != change["after"]:
                raise ValueError(f"Tag verification failed: {key}")
        # Preserve every unrelated Vorbis value, including artwork stored as comments.
        for key, values in (audio.tags or {}).items():
            if key.upper() not in updates and verified.get(key) != values:
                raise ValueError(f"Unrelated tag changed: {key}")
        if [p.write() for p in audio.pictures] != [p.write() for p in verified.pictures]:
            raise ValueError("Embedded pictures changed")
        current = path.lstat()
        if (current.st_ino, current.st_size, current.st_mtime_ns) != (stat.st_ino, stat.st_size, stat.st_mtime_ns):
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
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return updates
