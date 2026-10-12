import numpy as np
import pytest
import soundfile as sf
from mutagen.flac import FLAC, Picture
import beets


@pytest.fixture(autouse=True)
def isolated_beets_config(tmp_path, monkeypatch):
    monkeypatch.setenv("BEETSDIR", str(tmp_path))
    beets.config.clear()
    beets.config.read(user=False)


@pytest.fixture
def flac_file(tmp_path):
    path = tmp_path / "example.flac"
    # Actual decodable PCM, independently verified after tag writes.
    samples = (np.sin(np.arange(4096) / 20) * 0.25)
    sf.write(path, samples, 44100, subtype="PCM_16")
    audio = FLAC(path)
    audio["TITLE"] = ["Example"]
    audio["ARTIST"] = ["One; literal semicolon", "Two"]
    picture = Picture()
    picture.type = 3
    picture.mime = "image/png"
    picture.data = b"test-artwork"
    audio.add_picture(picture)
    audio.save()
    return path
