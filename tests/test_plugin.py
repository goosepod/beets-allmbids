from types import SimpleNamespace
import subprocess
import sys

import pytest
from beets import ui
from beets.library import Item, Library
from mediafile import MediaFile

from beetsplug.allmbids import AllMBIDsPlugin
from beetsplug.allmbids.tags import read_values
from test_core import A, R


def test_actual_beets_library_command(audio_file, tmp_path, monkeypatch, capsys):
    library = Library(str(tmp_path / "test.db"))
    item = Item.from_path(str(audio_file))
    item.mb_trackid = R
    library.add(item)
    plugin = AllMBIDsPlugin()
    plugin.config["contact"] = "https://example.org/contact"
    plugin.config["preview_only"] = False
    calls = []
    def collect(client, recording, release, disc):
        calls.append(recording)
        return {"MUSICBRAINZ_PRODUCER_ID": [A]}
    monkeypatch.setattr("beetsplug.allmbids.collect", collect)
    original = audio_file.read_bytes()
    opts = SimpleNamespace(write=False, limit=1)
    plugin.run(library, opts, [f"id:{item.id}"])
    assert '"mode": "preview"' in capsys.readouterr().out
    assert audio_file.read_bytes() == original
    opts.write = True
    plugin.run(library, opts, [f"id:{item.id}"])
    assert read_values(MediaFile(audio_file), "MUSICBRAINZ_PRODUCER_ID") == [A]
    assert calls == [R, R]
    library._close()


def test_query_required():
    with pytest.raises(ui.UserError):
        AllMBIDsPlugin().run(None, SimpleNamespace(write=False, limit=1), [])


def test_beets_cli_loads_plugin(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("plugins: [allmbids]\n", encoding="utf-8")
    result = subprocess.run([sys.executable, "-m", "beets", "-c", str(config),
                             "allmbids", "--help"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "--write" in result.stdout and "--limit" in result.stdout


def test_lookup_error_never_writes(flac_file, tmp_path, monkeypatch):
    library = Library(str(tmp_path / "test.db"))
    item = Item.from_path(str(flac_file))
    item.mb_trackid = R
    library.add(item)
    plugin = AllMBIDsPlugin()
    plugin.config["contact"] = "https://example.org/contact"
    plugin.config["preview_only"] = False
    def fail(*args):
        raise OSError("network unavailable")
    monkeypatch.setattr("beetsplug.allmbids.collect", fail)
    original = flac_file.read_bytes()
    with pytest.raises(ui.UserError):
        plugin.run(library, SimpleNamespace(write=True, limit=1), [f"id:{item.id}"])
    assert flac_file.read_bytes() == original
    assert not flac_file.with_name(flac_file.name + ".allmbids.bak").exists()
    library._close()


def test_preview_only_blocks_write_before_library_access():
    plugin = AllMBIDsPlugin()
    with pytest.raises(ui.UserError, match="preview-only"):
        plugin.run(None, SimpleNamespace(write=True, limit=1), ["id:1"])


def test_mixed_batch_reports_failures_and_continues(flac_file, tmp_path, monkeypatch, capsys):
    import json
    import shutil
    from http.client import IncompleteRead
    from beetsplug.allmbids.core import CollectedTags, add
    from test_core import B, W
    paths = []
    for number in range(5):
        path = tmp_path / f'item-{number}.flac'
        shutil.copy2(flac_file, path)
        paths.append(path)
    items = [SimpleNamespace(id=n, path=str(path).encode(), format='FLAC',
                             mb_trackid=W, mb_albumid='', disc=1)
             for n, path in enumerate(paths)]
    items[0].format = 'WAV'
    items[1].mb_trackid = ''
    items[2].mb_trackid = R
    items[4].mb_trackid = B
    library = SimpleNamespace(items=lambda query: iter(items))
    plugin = AllMBIDsPlugin()
    plugin.config['contact'] = 'https://example.org/contact'
    plugin.config['preview_only'] = False
    def collect(client, recording, release, disc):
        if recording == R:
            raise IncompleteRead(b'partial')
        tags = CollectedTags()
        if recording == W:
            add(tags, 'producer', A, contributor={'id': A, 'name': 'Producer 東京'},
                source={'type': 'recording', 'id': W, 'title': 'Track'}, relationship='producer')
        return tags
    monkeypatch.setattr('beetsplug.allmbids.collect', collect)
    report = tmp_path / 'report.jsonl'
    with pytest.raises(ui.UserError, match='failed for 1 item'):
        plugin.run(library, SimpleNamespace(write=True, limit=0, report=str(report)), ['format::.*'])
    output = capsys.readouterr().out
    assert report.read_text(encoding='utf-8') == output
    records = [json.loads(line) for line in output.splitlines()]
    assert [r['status'] for r in records[:-1]] == ['skipped', 'skipped', 'failed', 'changed', 'unchanged']
    assert records[2]['error']
    assert records[3]['contributors'][0]['name'] == 'Producer 東京'
    assert records[-1]['counts'] == {'changed': 1, 'unchanged': 1, 'skipped': 2, 'failed': 1}
    assert records[-1]['processed'] == 5 and records[-1]['status'] == 'failed'
    for n in (0, 1, 2, 4):
        assert paths[n].read_bytes() == flac_file.read_bytes()
        assert not paths[n].with_name(paths[n].name + '.allmbids.bak').exists()
    assert read_values(MediaFile(paths[3]), 'MUSICBRAINZ_PRODUCER_ID') == [A]


def test_existing_report_blocks_before_library_access(tmp_path):
    report = tmp_path / 'report.jsonl'
    report.write_text('previous report', encoding='utf-8')
    with pytest.raises(ui.UserError, match='Cannot create allmbids report'):
        AllMBIDsPlugin().run(None, SimpleNamespace(write=False, limit=1, report=str(report)), ['id:1'])
    assert report.read_text(encoding='utf-8') == 'previous report'


def test_limits_include_skipped_items_and_no_match_has_summary(capsys):
    import json
    item = SimpleNamespace(id=1, path=b'missing.wav', format='WAV', mb_trackid='')
    plugin = AllMBIDsPlugin()
    plugin.run(SimpleNamespace(items=lambda args: iter([item, item])),
               SimpleNamespace(write=False, limit=1), ['format:WAV'])
    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(records) == 2 and records[-1]['processed'] == 1
    plugin.run(SimpleNamespace(items=lambda args: iter([])),
               SimpleNamespace(write=False, limit=10), ['id:999999'])
    summary = json.loads(capsys.readouterr().out)
    assert summary['processed'] == 0 and summary['status'] == 'complete'


def test_contributor_report_only_explains_new_values(flac_file, monkeypatch, capsys):
    import json
    from beetsplug.allmbids.core import CollectedTags, add
    from beetsplug.allmbids.tags import enrich
    from test_core import B
    enrich(flac_file, {'MUSICBRAINZ_PRODUCER_ID': [A]}, write=True)
    tags = CollectedTags()
    for identifier in (A, B):
        add(tags, 'producer', identifier, contributor={'id': identifier, 'name': identifier},
            source={'type': 'recording', 'id': R}, relationship='producer')
    monkeypatch.setattr('beetsplug.allmbids.collect', lambda *args: tags)
    item = SimpleNamespace(id=1, path=str(flac_file).encode(), format='FLAC',
                           mb_trackid=R, mb_albumid='', disc=1)
    plugin = AllMBIDsPlugin()
    plugin.config['contact'] = 'https://example.org/contact'
    plugin.run(SimpleNamespace(items=lambda args: iter([item])),
               SimpleNamespace(write=False, limit=1), ['id:1'])
    record = json.loads(capsys.readouterr().out.splitlines()[0])
    assert [d['mbid'] for d in record['contributors']] == [B]
