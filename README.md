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
- Previews by default. `--write` explicitly enables file writes.
- Merges with existing values, preserves other tags and artwork, verifies staged
  tags, and creates an exclusive `original-filename.allmbids.bak` backup.

This initial version has no automatic import hooks and no database enrichment.
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
```

No installation or configuration change has been made on the live server.

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

First validate on a disposable file copy and a separate scratch Beets database.
Do not point that database at your live library. See [validation](docs/validation.md).
After reviewing a preview for a validated target, write explicitly:

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
```

Tests use generated audio in all five formats, temporary databases and fake HTTP responses;
they do not access your music library or make MusicBrainz requests.
GitHub Actions runs the tests and builds on Windows and Linux.
FFmpeg generates and independently decodes fixtures. The test extra includes
`imageio-ffmpeg` with a bundled executable for systems without FFmpeg on PATH;
FFmpeg is not a runtime requirement for the plugin.

MusicBrainz requests use HTTPS, a contact-bearing User-Agent, 30-second timeouts,
at least 1.1 seconds between requests, bounded transient-error retries and an
in-memory cache for each invocation. Do not run multiple enrichment commands
concurrently against the public service. Metadata quality depends on the
relationships available in MusicBrainz; merge mode deliberately retains stale
IDs rather than removing user data.

Licensed under MIT. This is independently implemented and is not an official
Beets, MusicBrainz or Picard plugin.
