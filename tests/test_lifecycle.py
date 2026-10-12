"""Exercise Beets import and automatic scrub on disposable audio only."""
from types import SimpleNamespace
import subprocess
import sys

from beets.library import Library
from mediafile import MediaFile

from beetsplug.allmbids import AllMBIDsPlugin
from beetsplug.allmbids.tags import enrich, read_values
from test_core import A, B, R
from test_formats import decoded_pcm

TAG = 'MUSICBRAINZ_PRODUCER_ID'


def test_import_scrub_then_enrich_preserves_audio_and_art(audio_file, tmp_path, monkeypatch, ffmpeg):
    audio = MediaFile(audio_file)
    audio.mb_trackid = R
    audio.save()
    enrich(audio_file, {TAG: [A, B]}, write=True)
    original = audio_file.read_bytes()
    pcm = decoded_pcm(ffmpeg, audio_file)
    art = [(i.data, i.type) for i in MediaFile(audio_file).images]
    music = tmp_path / 'library-music'
    database = tmp_path / 'import.db'
    config = tmp_path / 'import.yaml'
    import yaml
    config.write_text(yaml.safe_dump({
        'plugins': ['allmbids', 'scrub'], 'directory': str(music), 'library': str(database),
        'id3v23': False, 'import': {'copy': True, 'move': False, 'write': True},
        'scrub': {'auto': True},
    }), encoding='utf-8')
    result = subprocess.run([sys.executable, '-m', 'beets', '-c', str(config),
                             'import', '-s', '-A', '-q', str(audio_file)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert audio_file.read_bytes() == original
    library = Library(str(database), directory=str(music))
    try:
        item = list(library.items())[0]
        assert item.mb_trackid == R
        imported = MediaFile(item.path)
        assert read_values(imported, TAG) == []  # Scrub intentionally removes custom tags.
        assert [(i.data, i.type) for i in imported.images] == art
        monkeypatch.setattr('beetsplug.allmbids.collect', lambda *args: {TAG: [A, B]})
        plugin = AllMBIDsPlugin()
        plugin.config['contact'] = 'https://example.org/contact'
        plugin.config['preview_only'] = False
        plugin.run(library, SimpleNamespace(write=True, limit=1), [f'id:{item.id}'])
        item.write()
        after = MediaFile(item.path)
        assert read_values(after, TAG) == [A, B]
        assert [(i.data, i.type) for i in after.images] == art
        from beets.util import syspath
        assert decoded_pcm(ffmpeg, syspath(item.path)) == pcm
    finally:
        library._close()
