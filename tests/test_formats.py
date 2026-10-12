"""Independent storage and decoded-audio checks for every library format."""
import subprocess

import pytest
from mediafile import MediaFile
from mutagen.id3 import TXXX

from beetsplug.allmbids.core import MANAGED_TAGS
from beetsplug.allmbids.tags import FIELD_NAMES, MP4_PREFIX, enrich, read_values
from test_core import A, B

PRODUCER = "MUSICBRAINZ_PRODUCER_ID"
PERFORMER = "MUSICBRAINZ_PERFORMER_ID"
CUSTOM = "ALLMBIDS_TEST_UNRELATED"


def raw_values(audio, key):
    # Inspect on-disk structures independently of the plugin's descriptors.
    if audio.type == "mp3":
        return list(audio.mgfile.tags["TXXX:" + key].text)
    if audio.type in {"aac", "alac"}:
        return [bytes(value).decode("utf-8") for value in audio.mgfile.tags[MP4_PREFIX + key]]
    return list(audio.mgfile.tags[key])


def seed_unknown_tag(audio):
    values = ["Keep; this / string", "東京"]
    if audio.type == "mp3":
        audio.mgfile.tags.add(TXXX(encoding=3, desc=CUSTOM, text=values))
    elif audio.type in {"aac", "alac"}:
        audio.mgfile.tags[MP4_PREFIX + CUSTOM] = [value.encode("utf-8") for value in values]
    else:
        audio.mgfile.tags[CUSTOM] = values
    audio.save()
    return values


def decoded_pcm(ffmpeg, path):
    return subprocess.run([ffmpeg, "-v", "error", "-i", str(path), "-map", "0:a:0",
                           "-f", "s16le", "-c:a", "pcm_s16le", "-"],
                          check=True, capture_output=True).stdout


def test_all_role_fields_preserve_separate_values_audio_art_and_custom_tags(audio_file, ffmpeg):
    audio = MediaFile(audio_file)
    setattr(audio, FIELD_NAMES[PRODUCER], [A])
    unknown = seed_unknown_tag(audio)
    original = audio_file.read_bytes()
    pcm = decoded_pcm(ffmpeg, audio_file)
    artists = MediaFile(audio_file).artists
    artwork = [(image.data, image.desc, image.type) for image in MediaFile(audio_file).images]
    desired = {key: [A, B, A] for key in MANAGED_TAGS}
    desired[PERFORMER] = [f"{A} (piano)", f"{A} (guitar)", f"{B} (rôle; solo / voix)"]
    updates = enrich(audio_file, desired, write=True)
    assert updates[PRODUCER] == {"before": [A], "after": [A, B]}
    result = MediaFile(audio_file)
    for key in MANAGED_TAGS:
        expected = desired[PERFORMER] if key == PERFORMER else [A, B]
        assert read_values(result, key) == expected
        assert raw_values(result, key) == expected
    assert result.title == "Example" and result.artists == artists
    assert raw_values(result, CUSTOM) == unknown
    assert [(image.data, image.desc, image.type) for image in result.images] == artwork
    assert decoded_pcm(ffmpeg, audio_file) == pcm
    assert audio_file.with_name(audio_file.name + ".allmbids.bak").read_bytes() == original
    current = audio_file.read_bytes()
    assert enrich(audio_file, desired, write=True) == {}
    assert audio_file.read_bytes() == current


def test_preview_leaves_each_format_untouched(audio_file):
    original = audio_file.read_bytes()
    updates = enrich(audio_file, {PRODUCER: [A, B], PERFORMER: [f"{A} (piano)"]})
    assert updates[PRODUCER]["after"] == [A, B]
    assert audio_file.read_bytes() == original
    assert not audio_file.with_name(audio_file.name + ".allmbids.bak").exists()


def test_collapsed_values_abort_before_replacing_source(audio_file, monkeypatch):
    original = audio_file.read_bytes()
    save = MediaFile.save
    def collapse(self, **kwargs):
        setattr(self, FIELD_NAMES[PRODUCER], ["; ".join(read_values(self, PRODUCER))])
        save(self, **kwargs)
    monkeypatch.setattr(MediaFile, "save", collapse)
    with pytest.raises(ValueError, match="Tag verification failed"):
        enrich(audio_file, {PRODUCER: [A, B]}, write=True)
    assert audio_file.read_bytes() == original
    assert not audio_file.with_name(audio_file.name + ".allmbids.bak").exists()
    assert not list(audio_file.parent.glob(".allmbids-*"))


def test_mp3_id3v23_input_is_upgraded_without_splitting_literal_separators(audio_templates, tmp_path):
    import shutil
    path = tmp_path / "legacy.mp3"
    shutil.copy2(audio_templates["MP3"], path)
    audio = MediaFile(path, id3v23=True)
    setattr(audio, FIELD_NAMES[PRODUCER], [A])
    audio.title = "Literal / slash; semicolon"
    audio.save()
    assert MediaFile(path).mgfile.tags.version == (2, 3, 0)
    enrich(path, {PRODUCER: [A, B]}, write=True)
    result = MediaFile(path)
    assert result.mgfile.tags.version == (2, 4, 0)
    assert raw_values(result, PRODUCER) == [A, B]
    assert result.title == "Literal / slash; semicolon"


@pytest.mark.parametrize('corruption', ['title', 'artwork'])
def test_unrelated_corruption_aborts_before_backup(audio_file, monkeypatch, corruption):
    original = audio_file.read_bytes()
    save = MediaFile.save
    def corrupt(self, **kwargs):
        if corruption == 'title':
            self.title = 'Unexpected change'
        else:
            self.images = []
        save(self, **kwargs)
    monkeypatch.setattr(MediaFile, 'save', corrupt)
    with pytest.raises(ValueError, match='Unrelated tags changed|Embedded pictures changed'):
        enrich(audio_file, {PRODUCER: [A, B]}, write=True)
    assert audio_file.read_bytes() == original
    assert not audio_file.with_name(audio_file.name + '.allmbids.bak').exists()
    assert not list(audio_file.parent.glob('.allmbids-*'))


def test_later_beets_write_preserves_all_contributor_lists(audio_file, ffmpeg):
    from beets.library import Item
    from beetsplug.allmbids import AllMBIDsPlugin
    AllMBIDsPlugin()
    desired = {key: [A, B] for key in MANAGED_TAGS}
    desired[PERFORMER] = [f'{A} (piano)', f'{B} (role / literal; separator)']
    enrich(audio_file, desired, write=True)
    pcm = decoded_pcm(ffmpeg, audio_file)
    item = Item.from_path(str(audio_file))
    item.title = 'A later Beets write'
    item.write()
    audio = MediaFile(audio_file)
    for key, values in desired.items():
        assert read_values(audio, key) == values
        assert raw_values(audio, key) == values
    assert decoded_pcm(ffmpeg, audio_file) == pcm


def test_configured_id3v23_write_is_blocked_before_file_change(audio_templates, tmp_path):
    import beets
    import shutil
    from beets.library import Item, WriteError
    from beetsplug.allmbids import AllMBIDsPlugin
    AllMBIDsPlugin()
    path = tmp_path / 'enriched.mp3'
    shutil.copy2(audio_templates['MP3'], path)
    enrich(path, {PRODUCER: [A, B]}, write=True)
    original = path.read_bytes()
    beets.config['id3v23'] = True
    item = Item.from_path(str(path))
    item.title = 'Should not be written'
    with pytest.raises(WriteError, match='set id3v23: false'):
        item.write()
    assert path.read_bytes() == original
    beets.config['id3v23'] = False
    item.write()
    assert raw_values(MediaFile(path), PRODUCER) == [A, B]


def test_id3v23_guard_allows_unenriched_mp3(audio_templates, tmp_path):
    import beets
    import shutil
    from beets.library import Item
    from beetsplug.allmbids import AllMBIDsPlugin
    AllMBIDsPlugin()
    path = tmp_path / 'unenriched.mp3'
    shutil.copy2(audio_templates['MP3'], path)
    beets.config['id3v23'] = True
    Item.from_path(str(path)).write()
    assert MediaFile(path).mgfile.tags.version == (2, 3, 0)


def test_files_without_artwork_can_be_enriched(audio_file):
    audio = MediaFile(audio_file)
    audio.images = []
    audio.save()
    enrich(audio_file, {PRODUCER: [A, B]}, write=True)
    assert read_values(MediaFile(audio_file), PRODUCER) == [A, B]
    assert not MediaFile(audio_file).images
