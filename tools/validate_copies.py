"""Validate real tracks in an isolated workspace, never writing source files.

Run with the existing Beets Python interpreter. The plugin wheel is extracted
only into the workspace; no packages or live configuration are installed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
import zipfile

FORMATS = ("FLAC", "MP3", "AAC", "ALAC", "Opus")


def native_values(audio, key, mp4_prefix):
    if audio.type == "mp3":
        return list(audio.mgfile.tags["TXXX:" + key].text)
    if audio.type in {"aac", "alac"}:
        return [bytes(value).decode("utf-8") for value in audio.mgfile.tags[mp4_prefix + key]]
    return list(audio.mgfile.tags[key])


def validate_storage_fixtures(root, args):
    """Explicit dummy IDs on extra copies, independent of relationship coverage."""
    report_path = root / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if not report.get("validation_passed") or len(report["tracks"]) != len(FORMATS):
        raise ValueError("Complete the live-data disposable-copy run first")
    os.environ["BEETSDIR"] = str(root / "config")
    sys.path.insert(0, str(root / "plugin"))
    from mediafile import MediaFile
    from beetsplug.allmbids.core import MANAGED_TAGS
    from beetsplug.allmbids.tags import enrich, read_values, MP4_PREFIX, _unrelated_tags, _images
    before_database, before_config = hash_file(args.library), hash_file(args.live_config)
    fixture_dir = root / "storage-fixtures"
    fixture_dir.mkdir(exist_ok=False)
    fixture_ids = ["11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222"]
    desired = {key: list(fixture_ids) for key in MANAGED_TAGS}
    desired["MUSICBRAINZ_PERFORMER_ID"] = [
        fixture_ids[0] + " (test piano)", fixture_ids[1] + " (test role; literal / separator)"]
    checks = []
    try:
        for record in report["tracks"]:
            reference = Path(record["reference_path"]).resolve(strict=True)
            if not reference.is_relative_to(root / "references"):
                raise ValueError("Reference must belong to this validation workspace")
            target = fixture_dir / reference.name
            shutil.copy2(reference, target)
            original = hash_file(target)
            before = MediaFile(target)
            preview = enrich(target, desired)
            assert hash_file(target) == original
            updates = enrich(target, desired, write=True)
            assert preview == updates
            after = MediaFile(target)
            for key in MANAGED_TAGS:
                expected = list(dict.fromkeys(read_values(before, key) + desired[key]))
                assert read_values(after, key) == expected
                assert native_values(after, key, MP4_PREFIX) == expected
                assert len(expected) >= 2
            assert pcm_hash(target) == record["pcm_sha256"]
            assert _images(after) == _images(before)
            assert _unrelated_tags(after, updates) == _unrelated_tags(before, updates)
            assert hash_file(str(target) + ".allmbids.bak") == original
            written_hash = hash_file(target)
            assert enrich(target, desired, write=True) == {}
            assert hash_file(target) == written_hash
            checks.append({"format": record["format"], "fixture_path": str(target),
                           "multivalued_fields_verified": len(MANAGED_TAGS),
                           "passed": True, "decoded_audio_unchanged": True,
                           "artwork_unchanged": True, "unrelated_tags_unchanged": True})
            print(f"Verified every multivalued contributor field on the {record['format']} fixture copy", flush=True)
        report["storage_fixtures_passed"] = True
    except Exception as error:
        report["storage_fixtures_passed"] = False
        report["storage_fixture_error"] = str(error)
    finally:
        report["storage_fixture_checks"] = checks
        report["storage_fixtures_use_dummy_ids"] = True
        report["live_sources_unchanged_after_fixtures"] = all(
            hash_file(record["source_path"]) == record["source_sha256"] for record in report["tracks"])
        report["live_database_unchanged_after_fixtures"] = hash_file(args.library) == before_database
        report["live_configuration_unchanged_after_fixtures"] = hash_file(args.live_config) == before_config
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({key: report.get(key) for key in (
            "storage_fixtures_passed", "storage_fixture_error", "live_sources_unchanged_after_fixtures",
            "live_database_unchanged_after_fixtures", "live_configuration_unchanged_after_fixtures")}), flush=True)
    return 0 if report.get("storage_fixtures_passed") and all(report.get(key) for key in (
        "live_sources_unchanged_after_fixtures", "live_database_unchanged_after_fixtures",
        "live_configuration_unchanged_after_fixtures")) else 1


def hash_file(path):
    # Prefer reads that do not update access time when ownership permits it.
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOATIME", 0))
    except PermissionError:
        descriptor = os.open(path, os.O_RDONLY)
    with os.fdopen(descriptor, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def pcm_hash(path):
    process = subprocess.Popen([
        "ffmpeg", "-v", "error", "-xerror", "-i", str(path), "-map", "0:a:0",
        "-f", "s32le", "-c:a", "pcm_s32le", "-",
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    digest = hashlib.file_digest(process.stdout, "sha256").hexdigest()
    errors = process.stderr.read().decode("utf-8", "replace")
    if process.wait() != 0:
        raise RuntimeError(f"Audio decode failed for {path}: {errors}")
    return digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--library", required=True, type=Path)
    parser.add_argument("--live-config", required=True, type=Path)
    parser.add_argument("--music-root", required=True, type=Path)
    parser.add_argument("--contact", required=True)
    parser.add_argument("--storage-fixtures-only", action="store_true",
                        help="verify dummy-ID multivalues on extra copies in an existing validated workspace")
    args = parser.parse_args()
    root = args.workspace.resolve(strict=True)
    music = args.music_root.resolve(strict=True)
    library_path = args.library.resolve(strict=True)
    config_path = args.live_config.resolve(strict=True)
    if root.is_relative_to(music) or music.is_relative_to(root):
        raise ValueError("Validation workspace must be separate from the music directory")
    if library_path.is_relative_to(root) or config_path.is_relative_to(root):
        raise ValueError("The live database/config cannot be inside the validation workspace")
    if args.storage_fixtures_only:
        return validate_storage_fixtures(root, args)
    copies, references, plugin, config_dir = [root / name for name in
                                             ("copies", "references", "plugin", "config")]
    for directory in (copies, references, plugin, config_dir):
        directory.mkdir(exist_ok=False)
    with zipfile.ZipFile(args.wheel) as wheel:
        # Only plugin code is needed; reject unexpected extraction destinations.
        for name in wheel.namelist():
            if name.startswith("beetsplug/") and not name.endswith("/"):
                target = (plugin / name).resolve()
                if not target.is_relative_to(plugin):
                    raise ValueError("Unsafe wheel member")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(wheel.read(name))
    os.environ["BEETSDIR"] = str(config_dir)
    sys.path.insert(0, str(plugin))
    import beets
    import yaml
    from beets.library import Item, Library
    from mediafile import MediaFile
    from beetsplug.allmbids.tags import MP4_PREFIX, read_values, _unrelated_tags, _images
    from beetsplug.allmbids._version import __version__

    beets.config.clear()
    beets.config.read(user=False)
    scratch_db = root / "library.db"
    scratch_config = root / "config.yaml"
    scratch_config.write_text(yaml.safe_dump({
        "directory": str(copies), "library": str(scratch_db),
        "plugins": ["allmbids"], "pluginpath": [str(plugin)],
        "import": {"copy": False, "move": False, "write": False, "autotag": False},
        "allmbids": {"contact": args.contact},
    }), encoding="utf-8")
    before_database, before_config = hash_file(library_path), hash_file(config_path)
    report = {"workspace": str(root), "version": __version__, "tracks": [], "commands": []}
    selected = []
    snapshots = {}
    try:
        connection = sqlite3.connect(library_path.as_uri() + "?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        scratch = Library(str(scratch_db), directory=str(copies))
        try:
            for format in FORMATS:
                rows = connection.execute(
                    "SELECT id,path,format,artist,title,mb_trackid,mb_albumid,disc FROM items "
                    "WHERE format=? AND mb_trackid!='' AND mb_albumid!='' "
                    "AND length BETWEEN 120 AND 420 ORDER BY id LIMIT 100", (format,))
                for row in rows:
                    stored_path = Path(os.fsdecode(row["path"]))
                    source = (stored_path if stored_path.is_absolute() else music / stored_path).resolve(strict=False)
                    if source.is_file() and source.is_relative_to(music):
                        break
                else:
                    raise ValueError(f"No suitable source found for {format}")
                before = hash_file(source)
                stat = source.stat()
                target = copies / (format.lower() + source.suffix.lower())
                reference = references / target.name
                # Independent copies, not hardlinks; source is always opened read-only.
                with source.open("rb") as original, target.open("xb") as output:
                    shutil.copyfileobj(original, output)
                shutil.copystat(source, target)
                shutil.copy2(target, reference)
                assert hash_file(target) == before == hash_file(reference)
                item = Item.from_path(str(target))
                assert item.format == format
                item.mb_trackid, item.mb_albumid, item.disc = row["mb_trackid"], row["mb_albumid"], row["disc"]
                scratch.add(item)
                selected.append((source, before, stat.st_size, stat.st_mtime_ns))
                audio = MediaFile(target)
                snapshots[str(target)] = (audio, pcm_hash(target))
                record = {"format": format, "artist": row["artist"], "title": row["title"],
                          "source_item_id": row["id"], "scratch_item_id": item.id,
                          "source_path": str(source), "copy_path": str(target),
                          "reference_path": str(reference), "source_sha256": before}
                report["tracks"].append(record)
                print(f"Copied and decoded {format}: {row['artist']} - {row['title']}", flush=True)
        finally:
            scratch._close()
            connection.close()

        environment = dict(os.environ, PYTHONPATH=str(plugin))
        # This database contains exactly the five copies. Query a logical field
        # rather than an absolute path, since Beets stores paths relatively.
        query = "format::.*"
        def command(label, write=False):
            print(f"Running {label} against the isolated database", flush=True)
            arguments = [sys.executable, "-m", "beets", "-c", str(scratch_config),
                         "allmbids", "--limit", "0"]
            if write:
                arguments.append("--write")
            result = subprocess.run(arguments + [query], capture_output=True, text=True, env=environment)
            (root / (label + ".stdout.txt")).write_text(result.stdout, encoding="utf-8")
            (root / (label + ".stderr.txt")).write_text(result.stderr, encoding="utf-8")
            report["commands"].append({"name": label, "exit_code": result.returncode})
            if result.returncode:
                raise RuntimeError(f"{label} failed: {result.stderr.strip()}")
            entries = [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]
            if len(entries) != len(FORMATS):
                raise ValueError(f"{label} did not return all five items")
            return {entry["path"]: entry["changes"] for entry in entries}

        preview = command("preview")
        for record in report["tracks"]:
            path = record["copy_path"]
            assert hash_file(path) == record["source_sha256"], "Preview changed a disposable copy"
            record["preview_changes"] = preview[path]
        time.sleep(1.1)
        writes = command("write", write=True)
        for record in report["tracks"]:
            path = record["copy_path"]
            assert writes[path] == preview[path]
            old_audio, before_pcm = snapshots[path]
            after = MediaFile(path)
            assert pcm_hash(path) == before_pcm, "Decoded audio changed"
            assert _images(after) == _images(old_audio), "Artwork changed"
            assert _unrelated_tags(after, writes[path]) == _unrelated_tags(old_audio, writes[path]), "Unrelated tags changed"
            raw_lists = {}
            for key, change in writes[path].items():
                assert read_values(after, key) == change["after"]
                values = native_values(after, key, MP4_PREFIX)
                assert values == change["after"], "Native values collapsed"
                raw_lists[key] = values
            if writes[path]:
                assert hash_file(path + ".allmbids.bak") == record["source_sha256"]
            record.update({"changed_fields": len(writes[path]),
                           "native_values": raw_lists, "pcm_sha256": before_pcm,
                           "decoded_audio_unchanged": True, "artwork_unchanged": True,
                           "unrelated_tags_unchanged": True, "preview_read_only": True})
            print(f"Verified tags, PCM, artwork and backup for {record['format']}", flush=True)
        time.sleep(1.1)
        again = command("preview_after_write")
        assert all(not updates for updates in again.values()), "Second preview was not a no-op"
        report["second_preview_noop"] = True
        report["validation_passed"] = True
    except Exception as error:
        report["validation_passed"] = False
        report["error"] = str(error)
    finally:
        source_checks = []
        for source, before, size, mtime in selected:
            stat = source.stat()
            source_checks.append({"path": str(source), "unchanged":
                                  hash_file(source) == before and stat.st_size == size and stat.st_mtime_ns == mtime})
        report["live_source_checks"] = source_checks
        report["live_database_unchanged"] = hash_file(library_path) == before_database
        report["live_configuration_unchanged"] = hash_file(config_path) == before_config
        report["live_sources_unchanged"] = all(check["unchanged"] for check in source_checks)
        (root / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({key: report.get(key) for key in (
            "workspace", "validation_passed", "error", "live_sources_unchanged",
            "live_database_unchanged", "live_configuration_unchanged")}), flush=True)
    return 0 if report["validation_passed"] and all(report[key] for key in (
        "live_sources_unchanged", "live_database_unchanged", "live_configuration_unchanged")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
