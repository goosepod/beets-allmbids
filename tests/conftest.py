import numpy as np
import pytest
import soundfile as sf
from mutagen.flac import FLAC, Picture
import beets
import shutil
import subprocess
from base64 import b64decode
from mediafile import MediaFile, Image, ImageType

FORMATS = ["FLAC", "MP3", "AAC", "ALAC", "Opus"]
CODECS = {
    "FLAC": ("flac", ".flac"), "MP3": ("libmp3lame", ".mp3"),
    "AAC": ("aac", ".m4a"), "ALAC": ("alac", ".m4a"),
    "Opus": ("libopus", ".opus"),
}
PNG = b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX1kAAAAASUVORK5CYII=")


@pytest.fixture(scope="session")
def ffmpeg():
    import imageio_ffmpeg
    return shutil.which("ffmpeg") or imageio_ffmpeg.get_ffmpeg_exe()


@pytest.fixture(scope="session")
def audio_templates(tmp_path_factory, ffmpeg):
    directory = tmp_path_factory.mktemp("generated-audio")
    files = {}
    for format, (codec, suffix) in CODECS.items():
        path = directory / (format.lower() + suffix)
        subprocess.run([ffmpeg, "-v", "error", "-f", "lavfi", "-i",
                        "sine=frequency=440:sample_rate=48000:duration=0.2",
                        "-ac", "2", "-c:a", codec, "-map_metadata", "-1", str(path)],
                       check=True, capture_output=True)
        audio = MediaFile(path)
        assert audio.format == format
        audio.title = "Example"
        audio.artists = ["One; literal semicolon", "Two / 演奏者"]
        audio.images = [Image(PNG, type=ImageType.front)]
        audio.save()
        files[format] = path
    return files


@pytest.fixture(params=FORMATS)
def audio_file(request, audio_templates, tmp_path):
    template = audio_templates[request.param]
    path = tmp_path / template.name
    shutil.copy2(template, path)
    return path


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
