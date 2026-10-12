"""Manual enrichment and a guard against destructive configured ID3v2.3 writes."""
from contextlib import nullcontext
from http.client import HTTPException
import json
from pathlib import Path
from urllib.error import URLError

from beets import config, ui
from beets.library import WriteError
from beets.plugins import BeetsPlugin
from beets.util import syspath
from mutagen import MutagenError
from mediafile import MediaFile, UnreadableFileError

from .client import MusicBrainzClient
from .core import collect
from .tags import FIELD_NAMES, enrich, read_values


class AllMBIDsPlugin(BeetsPlugin):
    def __init__(self):
        super().__init__()
        self.config.add({"contact": "", "preview_only": True})
        self.register_listener("write", self.guard_id3v23)

    def guard_id3v23(self, item, path, tags):
        """Abort before a configured Beets write can join contributor values."""
        if not config["id3v23"].get(bool):
            return
        audio = MediaFile(syspath(path))
        if audio.type == "mp3" and any(
                len(read_values(audio, key)) > 1 for key in FIELD_NAMES):
            raise WriteError(path, ValueError(
                "allmbids contributor lists require ID3v2.4; set id3v23: false before writing"))

    def commands(self):
        command = ui.Subcommand("allmbids", help="preview contributor MBIDs for selected audio files")
        command.parser.add_option("--write", action="store_true", default=False,
                                  help="merge tags into audio files, making exclusive backups")
        command.parser.add_option("--limit", type="int", default=10,
                                  help="maximum matching items (default 10; 0 means unlimited)")
        command.parser.add_option("--report", metavar="PATH",
                                  help="also save JSON Lines output to a new file (never overwrite)")
        command.func = self.run
        return [command]

    def run(self, lib, opts, args):
        if opts.write and self.config["preview_only"].get(bool):
            raise ui.UserError("allmbids is preview-only; --write is disabled by allmbids.preview_only")
        if not args:
            raise ui.UserError("Provide a beets query, e.g. allmbids --limit 1 id:123")
        if opts.limit < 0:
            raise ui.UserError("--limit must be nonnegative")
        report_path = getattr(opts, "report", None)
        try:
            report = Path(report_path).open("x", encoding="utf-8") if report_path else nullcontext(None)
        except OSError as error:
            raise ui.UserError(f"Cannot create allmbids report: {error}") from error
        client = None
        mode = "write" if opts.write else "preview"
        counts = dict.fromkeys(("changed", "unchanged", "skipped", "failed"), 0)
        with report as output:
            def emit(record):
                line = json.dumps(record, ensure_ascii=False)
                # Persist before printing so a report error cannot silently
                # omit a record that stdout claimed was recorded.
                if output is not None:
                    try:
                        output.write(line + "\n")
                        output.flush()
                    except OSError as error:
                        raise ui.UserError(
                            f"Cannot write allmbids report; earlier file writes may have completed: {error}") from error
                ui.print_(line)

            for number, item in enumerate(lib.items(args)):
                if opts.limit and number >= opts.limit:
                    break
                record = {"type": "item", "item_id": item.id, "path": syspath(item.path),
                          "format": item.format, "mode": mode, "status": "unchanged",
                          "changes": {}, "contributors": [], "reason": None, "error": None}
                if item.format not in {"FLAC", "MP3", "AAC", "ALAC", "Opus"}:
                    record.update(status="skipped", reason="unsupported format")
                elif not item.mb_trackid:
                    record.update(status="skipped", reason="missing recording MBID")
                else:
                    try:
                        if client is None:
                            client = MusicBrainzClient(self.config["contact"].get(str))
                        tags = collect(client, item.mb_trackid, item.mb_albumid or None, item.disc)
                        updates = enrich(item.path, tags, write=opts.write)
                        details = [detail for detail in getattr(tags, "contributors", [])
                                   if detail["tag"] in updates
                                   and detail["value"] not in updates[detail["tag"]]["before"]]
                        record.update(changes=updates, contributors=details,
                                      status="changed" if updates else "unchanged")
                    except (OSError, ValueError, URLError, HTTPException,
                            MutagenError, UnreadableFileError) as error:
                        record.update(status="failed", error=str(error))
                        self._log.error("{}: {}", record["path"], error)
                counts[record["status"]] += 1
                emit(record)
            emit({"type": "summary", "mode": mode, "counts": counts,
                  "processed": sum(counts.values()), "limit": opts.limit,
                  "status": "failed" if counts["failed"] else "complete"})
        if counts["failed"]:
            raise ui.UserError(f"allmbids failed for {counts['failed']} item(s); see errors above")
