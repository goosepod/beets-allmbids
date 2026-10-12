# MVP design

## Sources and boundaries

The starting point is the [Picard plugin's documented tag convention](https://github.com/kgarner7/picard-all-mbids):
`musicbrainz_role_id`, with separate `mbid (role)` performer values.
Implementation follows the [MusicBrainz JSON API](https://musicbrainz.org/doc/MusicBrainz_API)
and [Beets plugin namespace and command interface](https://beets.readthedocs.io/en/stable/dev/plugins/index.html).
FLAC access uses [Mutagen's FLAC interface](https://mutagen.readthedocs.io/en/latest/api/flac.html).
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

For each file: read, plan, copy into a sibling temporary file, write, reload and
verify requested tags plus unrelated comments, embedded pictures and the FLAC
stream MD5 header. Check source identity/size/mtime, create an exclusive backup,
then replace the source atomically. Runtime stream identity checks are metadata
checks, not a full PCM decode. Tests independently decode and compare PCM.
Concurrent mutation is unsupported: the stat check is best-effort detection,
not a file lock. Interrupted operations can leave a backup or staging file;
inspect those before retrying. Backup data is flushed; crash durability of the
replacement and directory entry depends on the filesystem.

## Later work

1. Validate a disposable copy through the user's actual import/scrub/tag tools.
2. Decide whether to register fields with MediaFile for persistent Beets integration.
3. Add optional import enrichment only after validating lifecycle ordering.
4. Consider a replace policy with provenance and stale-value handling.
5. Add other formats and wider Beets version compatibility tests.
