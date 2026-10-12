import numpy as np
import pytest
import soundfile as sf
from mutagen.flac import FLAC

from beetsplug.allmbids.tags import enrich
from mediafile import MediaFile
from test_core import A, B

TAG = "MUSICBRAINZ_PRODUCER_ID"


def test_preview_does_not_write(flac_file):
    original = flac_file.read_bytes()
    changes = enrich(flac_file, {TAG: [A, B]})
    assert changes[TAG] == {"before": [], "after": [A, B]}
    assert flac_file.read_bytes() == original
    assert not flac_file.with_name(flac_file.name + ".allmbids.bak").exists()


def test_multivalue_audio_art_and_backup_preserved(flac_file):
    audio = FLAC(flac_file)
    audio[TAG] = [A]
    audio.save()
    original = flac_file.read_bytes()
    pcm, rate = sf.read(flac_file)
    artwork = [p.write() for p in audio.pictures]
    enrich(flac_file, {TAG: [A, B, B]}, write=True)
    result = FLAC(flac_file)
    assert result[TAG] == [A, B]
    assert result["artist"] == ["One; literal semicolon", "Two"]
    assert [p.write() for p in result.pictures] == artwork
    after, after_rate = sf.read(flac_file)
    assert rate == after_rate and np.array_equal(pcm, after)
    assert flac_file.with_name(flac_file.name + ".allmbids.bak").read_bytes() == original
    current = flac_file.read_bytes()
    assert enrich(flac_file, {TAG: [A, B]}, write=True) == {}
    assert flac_file.read_bytes() == current


def test_existing_backup_blocks_new_change(flac_file):
    backup = flac_file.with_name(flac_file.name + ".allmbids.bak")
    backup.write_bytes(b"older backup")
    original = flac_file.read_bytes()
    with pytest.raises(FileExistsError):
        enrich(flac_file, {TAG: [A]}, write=True)
    assert original == flac_file.read_bytes()
    assert backup.read_bytes() == b"older backup"
    assert not list(flac_file.parent.glob(".allmbids-*"))


def test_failed_save_leaves_original_untouched(flac_file, monkeypatch):
    original = flac_file.read_bytes()
    def fail(*args, **kwargs):
        raise OSError("test disk error")
    monkeypatch.setattr(MediaFile, "save", fail)
    with pytest.raises(OSError):
        enrich(flac_file, {TAG: [A]}, write=True)
    assert flac_file.read_bytes() == original
    assert not list(flac_file.parent.glob(".allmbids-*"))


def test_unmanaged_tag_rejected(flac_file):
    with pytest.raises(ValueError):
        enrich(flac_file, {"TITLE": ["Oops"]}, write=True)


def test_replace_failure_preserves_original_and_backup(flac_file, monkeypatch):
    original = flac_file.read_bytes()
    def fail(*args):
        raise OSError("test replace error")
    monkeypatch.setattr("beetsplug.allmbids.tags.os.replace", fail)
    with pytest.raises(OSError):
        enrich(flac_file, {TAG: [A]}, write=True)
    assert flac_file.read_bytes() == original
    assert flac_file.with_name(flac_file.name + ".allmbids.bak").read_bytes() == original
    assert not list(flac_file.parent.glob(".allmbids-*"))


def test_hardlink_write_rejected(flac_file):
    import os
    sibling = flac_file.with_name("hardlink.flac")
    try:
        os.link(flac_file, sibling)
    except OSError:
        pytest.skip("Hardlinks are not available on this filesystem")
    original = flac_file.read_bytes()
    with pytest.raises(ValueError):
        enrich(flac_file, {TAG: [A]}, write=True)
    assert flac_file.read_bytes() == original == sibling.read_bytes()
