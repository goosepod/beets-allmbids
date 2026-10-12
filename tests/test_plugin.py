from types import SimpleNamespace
import subprocess
import sys

import pytest
from beets import ui
from beets.library import Item, Library
from mutagen.flac import FLAC

from beetsplug.allmbids import AllMBIDsPlugin
from test_core import A, R


def test_actual_beets_library_command(flac_file, tmp_path, monkeypatch, capsys):
    library = Library(str(tmp_path / "test.db"))
    item = Item.from_path(str(flac_file))
    item.mb_trackid = R
    library.add(item)
    plugin = AllMBIDsPlugin()
    plugin.config["contact"] = "https://example.org/contact"
    calls = []
    def collect(client, recording, release, disc):
        calls.append(recording)
        return {"MUSICBRAINZ_PRODUCER_ID": [A]}
    monkeypatch.setattr("beetsplug.allmbids.collect", collect)
    original = flac_file.read_bytes()
    opts = SimpleNamespace(write=False, limit=1)
    plugin.run(library, opts, [f"id:{item.id}"])
    assert '"mode": "preview"' in capsys.readouterr().out
    assert flac_file.read_bytes() == original
    opts.write = True
    plugin.run(library, opts, [f"id:{item.id}"])
    assert FLAC(flac_file)["MUSICBRAINZ_PRODUCER_ID"] == [A]
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
    def fail(*args):
        raise OSError("network unavailable")
    monkeypatch.setattr("beetsplug.allmbids.collect", fail)
    original = flac_file.read_bytes()
    with pytest.raises(ui.UserError):
        plugin.run(library, SimpleNamespace(write=True, limit=1), [f"id:{item.id}"])
    assert flac_file.read_bytes() == original
    assert not flac_file.with_name(flac_file.name + ".allmbids.bak").exists()
    library._close()
