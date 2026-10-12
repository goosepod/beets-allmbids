# Changelog

## 0.3.0

- Emit JSON Lines for every item outcome and a final count summary; `--report`
  saves the same output to an exclusively created file. Consumers must filter
  `type: "item"` before reading per-file changes.
- Explain additions with contributor names, relationships and source entities.
- Reject configured Beets ID3v2.3 writes that would collapse MP3 contributor lists.
- Retry broken connections, timeouts and truncated response bodies with a bounded
  retry count; continue batches when an item ultimately fails.
- Check source changes before metadata reads and after backup creation; correctly
  handle files without embedded artwork.
- Keep validator checks active under optimized Python and support Python 3.10 hashing.
- Expand preservation, failure and import/scrub lifecycle tests; add macOS, current
  dependency CI and installed-wheel verification.

## 0.2.2

- Add the preview-only configuration lock and record the personal deployment.

## 0.2.1

- Validate disposable server copies and support merged MusicBrainz IDs.

## 0.2.0

- Support FLAC, MP3, AAC/M4A, ALAC/M4A and Opus through list-valued MediaFile fields.
