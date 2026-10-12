# Disposable-copy validation on entertain

## Version 0.3.0: NFS mount and configured workflow

Passed on October 12, 2026 with Beets 2.14.1, Python 3.12.3,
MediaFile 0.17.0 and Mutagen 1.47.0. The workspace is a sibling of the music
directory on the same NFSv4 mount:

```text
/mnt/media/media/.allmbids-validation-0.3.0-vP4gxi/
```

- Real recording/release/work lookups, preview/write/no-op previews, decoded PCM,
  artwork, unrelated metadata and exclusive backups passed for all five formats.
- Additional fixture copies verified every multivalued contributor field in all
  formats using explicit dummy IDs and literal separator characters.
- The actual `bi` function exercised its quality gate, continuation prompt,
  cache cleanup and Beets import. Its directory, database, log, state, plugin
  path and credential state were redirected to the private workspace. The full
  configured plugin set loaded successfully. The quality gate flagged a possible
  transcode, and validation continued only on disposable copies.
- Scratch import used singleton/as-is settings to retain known identities;
  interactive album candidate selection was excluded. Move/write behavior and
  all configured import plugins were exercised.
- The server has `scrub.auto: false`; import correctly retained the fixture
  contributor fields. Explicit manual scrub removed them. Enrichment afterward
  added the real MusicBrainz relationships and produced reports with attribution.
- Later Beets writes preserved contributor lists, decoded audio and artwork.
  The final preview was a no-op. A separate dummy-ID MP3 case verified the
  configured ID3v2.3 guard rejected the write without changing file bytes.
- Checksums confirmed that the live database, configuration and all selected
  live source files remained unchanged throughout validation.

The workspace retains `report.json`, `workflow-report.json`, per-command logs,
reference/copy files, backups, storage fixtures and the exact workflow harness.
Harness attempts are retained separately. Reports, copied credentials and
library paths stay outside Git in the private workspace. Files containing
dummy IDs must remain outside the music library.

## Historical version 0.2.1 validation

**Passed with plugin version 0.2.1**, using the existing Beets 2.14.1,
Python 3.12.3, MediaFile 0.17.0 and Mutagen 1.47.0 environment.
The plugin was loaded from an isolated directory; no packages were installed
into the live Beets environment and no live configuration was changed.

## Real MusicBrainz lookup and command tests

Each source was copied into an isolated workspace with an untouched reference
copy, separate Beets database/configuration and only the `allmbids` plugin.
The command was run in preview mode, write mode, then preview mode again.

| Format | Disposable source track | Contributor fields added | Fields with multiple values |
| --- | --- | ---: | ---: |
| FLAC | Big Bad Voodoo Daddy — Jumpin' Jack | 7 | 3 |
| MP3 | Bill Withers — I Don't Know | 3 | 0 |
| AAC/M4A | Nina Simone — Black Is the Color of My True Love's Hair | 6 | 1 |
| ALAC/M4A | Snap! — Rhythm Is a Dancer | 2 | 1 |
| Opus | Glenn Miller and His Orchestra — Chattanooga Choo Choo | 0 | 0 |

The Opus recording and release had no supported contributor data, so it
correctly remained unchanged. Read-only lookups of 28 duration-filtered Opus
candidates from that compilation likewise returned no supported relationships.
This is a MusicBrainz data-coverage limitation, not a storage failure.

All five disposable files passed:

- Preview caused no byte changes and the post-write preview was a no-op.
- Independent FFmpeg decoding before/after produced the same SHA-256 of PCM.
- Artwork and unrelated native tag contents were preserved.
- Each changed field matched both MediaFile's list and native tag arrays.
- Backups for changed files matched the untouched reference byte for byte.

## Multivalue storage tests independent of relationship coverage

Extra copies under `storage-fixtures/` used two explicit dummy UUIDs to verify
all **13 contributor fields** in every format, including MP3 and Opus where the
real MusicBrainz results did not demonstrate multivalues. Performer fixture
values also included literal slash and semicolon characters.

FLAC and Opus retained separate Vorbis values, MP3 retained separate ID3 TXXX
text values, and AAC/ALAC retained separate MP4 freeform UTF-8 values. All five
passed preview, merge, native-value roundtrip, decoded audio, artwork, unrelated
metadata, backup and no-op checks. These copies contain **test data**, not valid
contributor attribution, and must remain outside the music library.

## Bug found and fixed

The Nina Simone recording's stored ID
`ac02bf5e-541f-4f0b-aa84-299943215acf` redirects to canonical recording
`55f5c44f-78f5-48e3-97d7-925942023137`. Version 0.2.0 rejected the changed
response ID. Version 0.2.1 validates and accepts same-entity MusicBrainz merge
redirects, rate limits redirect hops, and caches both IDs. Regression tests
cover the merge, caching, rejected endpoint changes and redirect pacing.
The original core recording ID is preserved in the copies and live library.

## Live-library isolation

SHA-256 checks confirmed that all five live source files, the live library
database and the live configuration stayed unchanged, both after the lookup
tests and after fixture writes. Source file size and modification time were
also unchanged in the lookup run. Source paths were read only; all tag writes
targeted regular independent copies, never hardlinks.

The retained server workspace is:

```text
$HOME/.local/share/beets-allmbids-validation/run-fynnqbum/
```

It contains `copies/`, `references/`, `storage-fixtures/`, per-command logs,
backups, the isolated plugin/config/database and `report.json` with full
checksums and tag arrays. Raw reports include private library paths and are
kept outside the Git project. This verifies the manual command on disposable
server files. At that time, import/scrub ordering and live-mount writes were
untested; the 0.3.0 validation above adds those disposable-copy checks.
