# Initial validation

Read-only inspection of `entertain` found:

- Beets 2.14.1, Python 3.12.3, MediaFile 0.17.0, Mutagen 1.47.0.
- Beets lives in `$HOME/.local/share/pipx/venvs/beets`.
- Configuration is `$HOME/.config/beets/config.yaml`.
- Library is `~/.config/beets/library.db`; music directory is `/mnt/media/media/music`.
- 12,328 FLAC library items, of which 12,235 have nonempty recording MBIDs.
- Additional items: 10,725 MP3 (`.mp3`), 55 AAC (`.m4a`), 60 ALAC (`.m4a`)
  and 31 Opus (`.opus`). A second read-only query confirmed container extensions.
- `bi` runs an audio-quality check before `beet -v import`, with move/write enabled.
- Enabled plugins include musicbrainz, mbsync, scrub and several metadata writers.

These details are environment observations, not required defaults. No server
live configuration, installed packages, live music files or live database records were changed.

Automated validation includes fake MusicBrainz requests, relationships from
release/recording/work, stable deduplication, multiple roles, medium filtering,
rate limiting, caching, retries and errors. Generated audio tests check actual
decoded PCM, separate native tag values, artwork, unrelated tags, byte-for-byte
backups, preview/no-op behavior and failure recovery. A temporary real Beets
database exercises preview and explicit writes through the command function
for each of FLAC, MP3, AAC, ALAC and Opus. Multivalued tags are inspected in
native Vorbis lists, ID3 TXXX text lists and MP4 freeform atom lists as well as
read back through the MediaFile descriptors. A simulated writer that collapses
values is rejected before source replacement in each format. MP3 v2.3 input
is separately checked for a multivalue-preserving upgrade to v2.4.

## Disposable-copy validation procedure

1. Create a scratch directory outside the live library and copy one identified
   file of each library format into it. Keep untouched reference copies.
2. Create a separate Beets config with its own scratch database/directory, only
   `allmbids` enabled, and your MusicBrainz contact. Set `import.copy: false`,
   `import.move: false`, `import.write: false` and `import.autotag: false`.
3. Import only the disposable copy into that scratch database. Check its
   recording MBID and release MBID against the reference copy.
4. Preview `allmbids --limit 1` with that item's ID and inspect the JSON arrays.
5. Run the same query with `--write`; confirm the backup matches the reference,
   decode/compare PCM, and check artwork plus unrelated metadata.
6. Repeat for each format. Preview again: no changes should be needed. Test any normal Beets tag-writing
   steps on the copy, including scrub if applicable, and inspect custom tags.

Disposable-copy validation on the server is now complete; see
[the server report](server-validation.md). Deployment remains separate follow-up
work. Full import/scrub lifecycle ordering and writing on the live music mount
have not been tested.

## Completed local checks

- **50 tests passed** for version 0.2.1, covering all five library formats
  and canonical MusicBrainz merge redirects,
  on Windows with Python 3.12.14, Beets 2.14.1,
  MediaFile 0.17.0 and Mutagen 1.47.0. All files and databases were temporary.
- Source distribution and universal Python wheel built successfully.
- Installed the wheel into an isolated local target and confirmed Beets loads
  the packaged plugin and exposes `allmbids --help` with `--write` and `--limit`.
- GitHub Actions is configured for Windows/Linux and Python 3.10/3.12;
  those remote jobs have not run yet.
- Automated HTTP tests use fixtures. Actual MusicBrainz responses and writes to
  disposable server copies have also passed the separate server validation.
