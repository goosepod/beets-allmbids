# beets-allmbids

A personal-use plugin for enriching audio tags with MusicBrainz contributor MBIDs.
Inspired by [Picard All MBIDs](https://github.com/kgarner7/picard-all-mbids).
Uses existing Beets recording (`mb_trackid`) and release (`mb_albumid`) IDs;
does not guess identities from contributor names.

## What it does

- Retrieves artist relationships for recordings, their directly performed works,
  and the selected release, plus labels from release `label-info`.
- Adds roles such as composer, lyricist, arranger, producer, engineer, mixer,
  remixer, conductor, DJ mixer and performer. See [design](docs/design.md).
- Uses Beets' MediaFile layer for custom `MUSICBRAINZ_<ROLE>_ID` fields,
  storing lists of separate values rather than joined strings.
- Previews by default. The `preview_only` lock rejects `--write` until explicitly disabled.
- Merges with existing values, preserves other tags and artwork, verifies staged
  tags, and creates an exclusive `original-filename.allmbids.bak` backup.
- Reports contributor names and source entities alongside proposed additions.
- Blocks configured Beets ID3v2.3 writes that would collapse contributor lists.

Enrichment is manual, with no automatic import enrichment or database enrichment.
It supports every format found in the inspected library: FLAC, MP3, AAC in M4A,
ALAC in M4A, and Opus. It does not change names, core artist IDs, `COMPOSER`,
`PERFORMER`, or Beets' own `MUSICBRAINZ_COMPOSERID` spelling.

## Format storage

Contributor lookup and merge behavior are shared across formats. MediaFile
selects how each list is stored:

| Library format | Container | List storage |
| --- | --- | --- |
| FLAC | `.flac` | Repeated Vorbis comments named `MUSICBRAINZ_<ROLE>_ID` |
| MP3 | `.mp3` | ID3v2.4 `TXXX` frame with description `MUSICBRAINZ_<ROLE>_ID` and multiple text values |
| AAC | `.m4a` | Multiple UTF-8 values in `----:com.apple.iTunes:MUSICBRAINZ_<ROLE>_ID` |
| ALAC | `.m4a` | Same MP4 freeform atom storage as AAC |
| Opus | `.opus` | Repeated Vorbis comments named `MUSICBRAINZ_<ROLE>_ID` |

The plugin registers `ListMediaField` descriptors under internal
`allmbids_musicbrainz_<role>_id` names. It reads and writes contributor fields
through MediaFile; format-specific storage is handled by its storage styles.
The lookup code has no dependency on audio codecs or containers.

MP3 writes use MediaFile's default ID3v2.4 output, including for existing
ID3v2.3 files, to retain separate text values. Old values containing a literal
slash or semicolon are preserved as single values, never split by guessing.
Keep Beets' global `id3v23: false` for subsequent tag writes. While `allmbids`
is loaded, its `write` event guard rejects configured ID3v2.3 writes to MP3s
with multiple contributor values before modifying the file. Beets does not
pass explicit `Item.write(id3v23=True)` overrides to that event: code using
that API, direct MediaFile writes, and external taggers must retain ID3v2.4.
AAC here means the M4A container actually present in the library; raw ADTS
`.aac` streams are outside MediaFile's supported tagging interface.

## Install and enable

Requires Python 3.10+ and Beets 2.14.1+ (below 3.0). Validated against Beets 2.14.1,
MediaFile 0.17.0 and Mutagen 1.47.0, matching the inspected `entertain` installation.
Earlier Beets versions are outside this MVP's supported range.

Install into the **same Python environment** as Beets. For a pipx installation,
from the directory containing this project:

```sh
pipx inject beets ./beets-allmbids
```

For a conventional virtual environment:

```sh
python -m pip install ./beets-allmbids
```

Append `allmbids` to the existing Beets `plugins` list, preserving other plugins.
Add a contact address or URL for the MusicBrainz User-Agent:

```yaml
allmbids:
  contact: 'mailto:your-address@example.com'  # replace with your actual contact
  preview_only: true
id3v23: false
```

The recorded 0.2.2 deployment on `entertain` enabled `allmbids` with
`preview_only: true`. This checkout has not been redeployed there.
See the [historical installation details](docs/installation.md).

## Preview and write

Always begin with a narrow query:

```sh
beet allmbids --limit 1 id:123
```

Replace `123` with a Beets item ID. Output shows the file path and each tag's
before/after arrays. A query is required. The default limit is ten matching
items, **including skipped items**; `--limit 0` explicitly removes the limit.
Formats outside this supported set and recordings without MBIDs are skipped. Failed lookups prevent
writing that item; processing continues and the command exits with an error.
An empty changes object means no additions were found.

Output is JSON Lines: one `type: "item"` record per processed item, followed by
a `type: "summary"` record with counts and total processed. Item statuses are
`changed`, `unchanged`, `skipped`, or `failed`; in preview mode `changed` means
additions are proposed. All item records have `changes`, `contributors`,
`reason`, and `error` fields. Each contributor entry identifies the tag/value,
MBID, name (or null), relationship, and source entity type/ID/title. Only newly
added values are explained; multiple sources for the same addition are retained.
Names come from the same responses and cause no extra requests or tag changes.

Save the same records with `--report`; an existing report is never overwritten,
and an uncreatable report stops the command before accessing query items:

```sh
beet allmbids --limit 5 --report preview.jsonl 'artist:Bill Withers'
```

Failed batches still include the final summary and exit nonzero. Report records
are flushed after each item; an interruption may leave a partial report. If
report writing fails during a write batch, earlier file updates remain applied.

First validate on a disposable file copy and a separate scratch Beets database.
Do not point that database at your live library. See [validation](docs/validation.md).
After reviewing a preview for a validated target, set
`allmbids.preview_only: false` in your configuration before using `--write`.
Leave it `true` for a preview-only installation.

```sh
beet allmbids --write --limit 1 id:123
```

Each changed file gets a byte-for-byte backup beside it before replacement.
An existing backup blocks further changes to that file rather than overwriting
your recovery copy. A no-op write succeeds without changing the file or backup.
Keep or move the earlier backup somewhere safe before making a later change.
Files with symlinks or multiple hardlinks are rejected for writes.

The writer stages in the same directory, requiring space for two extra copies
of each changed file. Updates are per file, not an all-or-nothing batch.
Atomic replacement is best suited to local filesystems; verify behavior on your
music mount before using it. Avoid concurrent imports, tag edits or moves.
Inode identity and modification times may change; ownership follows the writing
user. Filesystem-specific ACLs and extended attributes are not guaranteed.

To restore, stop processes editing the file, verify the backup, then copy it back
over the corresponding audio file using your usual file tools. The plugin never
deletes backups. Beets' `scrub` plugin can remove these custom tags; run this
command **after** import/scrub. Re-run a preview after any later tag-writing
workflow to check whether enrichment is still present.

## Development

```sh
python -m venv .venv
# Activate the environment using your operating system's normal instructions.
python -m pip install -e '.[test]'
python -m pytest -q
python -m build
python tools/check_wheel.py dist
```

Tests use generated audio in all five formats, temporary databases and fake HTTP responses;
they do not access your music library or make MusicBrainz requests.
GitHub Actions tests Windows, Linux and macOS, retaining the pinned dependency
baseline on Python 3.10/3.12 and testing current allowed dependencies on Python
3.14. It also installs the built wheel into a separate environment and loads
the plugin outside the source checkout. Tests cover real Beets singleton
import with automatic scrub, enrichment after import, and later Beets writes.
FFmpeg generates and independently decodes fixtures. The test extra includes
`imageio-ffmpeg` with a bundled executable for systems without FFmpeg on PATH;
FFmpeg is not a runtime requirement for the plugin.

MusicBrainz requests use HTTPS, a contact-bearing User-Agent, 30-second timeouts,
at least 1.1 seconds between requests, bounded transient-error retries and an
in-memory cache for each invocation. Do not run multiple enrichment commands
concurrently against the public service. Metadata quality depends on the
relationships available in MusicBrainz; merge mode deliberately retains stale
IDs rather than removing user data.

Merged MusicBrainz IDs are supported: redirects to the same entity type on
MusicBrainz are validated and rate limited, and both old and current IDs share
the response cache. Existing recording/release tags are not rewritten.

## Server validation

Version 0.2.1 was tested on `entertain` with disposable copies of one actual
library file per format, an isolated database/configuration and live MusicBrainz
lookups. All five passed audio, artwork and metadata preservation checks.
Separate fixture copies verified every multivalued contributor field using
clearly marked dummy IDs. The selected Opus recording had no contributor data,
so the real lookup correctly made no changes. See [the server report](docs/server-validation.md).

The repeatable validator is [tools/validate_copies.py](tools/validate_copies.py).
It requires an existing fresh workspace, a plugin wheel, explicit live-library
and music-root paths, a live-config path for checksum verification, and a contact.
It opens the source database read-only and writes only isolated copies and a
scratch database. `--storage-fixtures-only` adds deterministic multivalue checks
to a completed validation workspace. The live Beets installation is not modified.
The validator supports Python 3.10+; preservation checks also run under `python -O`.
Its audio checks require FFmpeg on PATH. Historical server validation does not
replace validation of this version on the target mount and actual import wrapper.

Licensed under MIT. This is independently implemented and is not an official
Beets, MusicBrainz or Picard plugin.
