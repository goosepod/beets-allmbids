# MVP design

## Sources and boundaries

The starting point is the [Picard plugin's documented tag convention](https://github.com/kgarner7/picard-all-mbids):
`musicbrainz_role_id`, with separate `mbid (role)` performer values.
Implementation follows the [MusicBrainz JSON API](https://musicbrainz.org/doc/MusicBrainz_API)
and [Beets plugin namespace and command interface](https://beets.readthedocs.io/en/stable/dev/plugins/index.html).
Tag access uses [MediaFile](https://github.com/beetbox/mediafile) and its
`ListMediaField`, `ListStorageStyle`, `MP3ListDescStorageStyle` and
`MP4ListStorageStyle` interfaces.
No Picard source code is vendored.

## Retrieval

| Entity | Includes | Purpose |
| --- | --- | --- |
| release (`mb_albumid`, optional) | `artist-rels+labels` | Release contributors and label MBIDs |
| recording (`mb_trackid`, required) | `artist-rels+work-rels` | Track contributors and performed work links |
| each directly performed work | `artist-rels` | Composer, lyricist, writer, arranger relationships |

Release relationships are processed first, then recording, then directly linked
works. Work links must be `performance` relationships. Unknown types are ignored;
malformed IDs fail the item before any write. Missing labels are skipped.
Duplicate works are fetched once and shared entities are cached per invocation.
No work hierarchy traversal, name search, release-group inheritance or artist
credit enrichment is included. Work `instrumental` attributes do not suppress
lyricist IDs: this plugin records work contributors, not lyrics in the performance.
Relationships with `medium N` attributes only apply to the item's matching disc.

[Merged MusicBrainz IDs](https://musicbrainz.org/doc/MusicBrainz_Identifier)
redirect to their current entity. The client accepts a changed response ID only
when it matches the final HTTPS lookup URL for the same entity type on
`musicbrainz.org`. Redirect hops obey the rate limit. Both the requested and
canonical IDs are cached without updating core IDs in files or the database.

## Tag mapping

All output keys below have prefix `MUSICBRAINZ_` and suffix `_ID`.

| Relationship | Role key |
| --- | --- |
| composer | COMPOSER |
| lyricist, librettist | LYRICIST |
| writer | WRITER |
| arranger, instrument arranger, vocal arranger, orchestrator | ARRANGER |
| conductor | CONDUCTOR |
| producer | PRODUCER |
| remixer | REMIXER |
| mix | MIXER |
| mix-DJ | DJMIXER |
| engineer, audio, sound, live sound, recording, mastering | ENGINEER |
| audio director, video director | DIRECTOR |
| instrument, vocal, performer, chorus master, concertmaster, performing orchestra | PERFORMER |
| release label-info | LABEL |

Engineering relationships include recording and mastering in this MVP. The broad
ENGINEER key loses that distinction; finer engineering tags can be added later.
Contributor names are not rewritten or paired positionally with these arrays.
Lookup results also carry display-only contributor names and attribution to
release, recording, or work entities. Duplicate tag values remain deduplicated
while distinct attribution sources are retained. Reports explain only additions,
without writing names or issuing extra lookups.

Performers have one entry per artist and role, e.g. `uuid (piano)` and
`uuid (guitar)`. Prefix attributes (additional, guest, minor, solo) appear in
that order on each role. Vocal with no attributes becomes `uuid (vocals)`;
instrument with no attributes becomes `uuid (instrument)`; generic performer
with no attributes is a bare UUID. Performing orchestra becomes `uuid (orchestra)`.
Attribute text is preserved; localized instrument credits are not resolved.

## Write policy

Merge only; old values retain their order and new unique values are appended.
No clearing on empty results, removal, standard tag rewriting, flexible Beets
fields, database changes or importer hooks. JSON command output preserves arrays
for review. Standard COMPOSERID spelling and the plugin's COMPOSER_ID remain
separate to avoid overwriting established Beets fields.

Registered MediaFile descriptors provide one list interface across FLAC, MP3,
AAC/M4A, ALAC/M4A and Opus. Internal field names have an `allmbids_` prefix and
do not add Item database fields. FLAC/Opus use repeated Vorbis comments, MP3
uses multivalued ID3v2.4 TXXX frames, and AAC/ALAC use multivalued UTF-8 MP4
freeform atoms under the `com.apple.iTunes` namespace. Existing FLAC tag names
are preserved. MP3 writes upgrade v2.3 tags to v2.4; separator characters in
existing values are never interpreted as a serialization format.

For each file: read, plan, copy into a sibling temporary file, write, reload and
verify requested tags, unrelated tag contents, embedded pictures and stream
properties (including the MD5 header for FLAC). Native tag structures are
inspected only for preservation verification; contributor tag access and saving
use MediaFile. ID3 text encoding changes are allowed while field contents must
remain equal. Check source identity/size/mtime, create an exclusive backup,
then replace the source atomically. Runtime stream checks examine metadata,
not a full PCM decode. Tests independently decode and compare PCM with FFmpeg
for each format and additionally inspect native tag lists after saving.
Concurrent mutation is unsupported: the stat check is best-effort detection,
not a file lock. Interrupted operations can leave a backup or staging file;
inspect those before retrying. Backup data is flushed; crash durability of the
replacement and directory entry depends on the filesystem.

Source stat information is captured before the initial metadata read, and
checked both before and after backup creation. A detected change during backup
creation aborts replacement and retains the backup for inspection.

The only automatic write listener is a rejection guard: with global
`id3v23: true`, later Beets writes to MP3s with multiple contributor values
raise `WriteError` before modification. It never performs enrichment or changes
configuration. Beets' event does not include per-call `id3v23` overrides, so
direct API callers and external taggers must retain ID3v2.4 themselves. Normal
Beets writes preserve these fields in every supported format. Scrub intentionally
removes custom fields; enrichment belongs after import/scrub.

The command emits consistent JSON Lines item records and a final summary,
including failures and skips. `--report` creates a new report exclusively before
query processing and flushes each record. Counts include skipped items and honor
the limit. A failed lookup prevents that item's write and processing continues.

The client retries transient HTTP errors, broken connections, timeouts and
truncated bodies at most three times. Validation failures for mismatched IDs
are not retried or cached. The standalone validator uses explicit checks that
remain enabled under optimized Python and bounded-memory Python 3.10 hashing.

## Later work

1. Validate the actual server import wrapper and mount using disposable copies;
   automated singleton import/scrub and subsequent writes now cover all five formats.
2. Decide whether to expose registered MediaFile fields in the Beets database.
3. Add optional import enrichment only after validating lifecycle ordering.
4. Consider a replace policy with provenance and stale-value handling.
5. Extend beyond the library's five formats if needed. CI now covers the pinned
   baseline and current allowed dependencies on Linux, Windows and macOS.
