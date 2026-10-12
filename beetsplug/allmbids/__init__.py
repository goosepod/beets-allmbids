"""Manual, preview-first beets command; no importer or database write hooks."""
import json
from urllib.error import URLError

from beets import ui
from beets.plugins import BeetsPlugin
from beets.util import syspath
from mutagen import MutagenError
from mediafile import UnreadableFileError

from .client import MusicBrainzClient
from .core import collect
from .tags import enrich


class AllMBIDsPlugin(BeetsPlugin):
    def __init__(self):
        super().__init__()
        self.config.add({"contact": ""})

    def commands(self):
        command = ui.Subcommand("allmbids", help="preview contributor MBIDs for selected audio files")
        command.parser.add_option("--write", action="store_true", default=False,
                                  help="merge tags into audio files, making exclusive backups")
        command.parser.add_option("--limit", type="int", default=10,
                                  help="maximum matching items (default 10; 0 means unlimited)")
        command.func = self.run
        return [command]

    def run(self, lib, opts, args):
        if not args:
            raise ui.UserError("Provide a beets query, e.g. allmbids --limit 1 id:123")
        if opts.limit < 0:
            raise ui.UserError("--limit must be nonnegative")
        client = None
        failures = 0
        for number, item in enumerate(lib.items(args)):
            if opts.limit and number >= opts.limit:
                break
            path = syspath(item.path)
            if item.format not in {"FLAC", "MP3", "AAC", "ALAC", "Opus"}:
                ui.print_(f"skip (unsupported format {item.format}): {path}")
                continue
            if not item.mb_trackid:
                ui.print_(f"skip (missing recording MBID): {path}")
                continue
            try:
                if client is None:
                    client = MusicBrainzClient(self.config["contact"].get(str))
                tags = collect(client, item.mb_trackid, item.mb_albumid or None, item.disc)
                updates = enrich(item.path, tags, write=opts.write)
                ui.print_(json.dumps({"path": path, "mode": "write" if opts.write else "preview",
                                      "changes": updates}, ensure_ascii=False))
            except (OSError, ValueError, URLError, MutagenError, UnreadableFileError) as error:
                failures += 1
                self._log.error("{}: {}", path, error)
        if failures:
            raise ui.UserError(f"allmbids failed for {failures} item(s); see errors above")
