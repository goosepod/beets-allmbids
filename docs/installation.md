# Preview-only installation on entertain

## Current version: 0.3.0

Upgraded on October 12, 2026 after all eight CI jobs and the disposable-copy
NFS/workflow checks passed. The wheel was installed with `--no-deps`; all other
installed package versions and the live configuration stayed unchanged.

Verified after the upgrade:

- The installed module loads from the existing Beets Python environment and
  reports version 0.3.0; command help exposes `--report`.
- `preview_only: true` remains enabled. A write attempt using the live config
  and a disposable database was rejected before accessing audio files.
- A real live-library preview reported seven fields and 17 contributor
  attribution entries, followed by the summary record.
- Checksums confirmed the live database, configuration and five selected source
  files were unchanged. No live audio tags were written.
- The normal `bi` function and import settings were unchanged. Global
  `id3v23: false` remains in place. The new write listener only rejects unsafe
  configured ID3v2.3 writes; it performs no automatic enrichment.

The persistent installed wheel is:

```text
$HOME/.local/share/beets-allmbids/releases/0.3.0/beets_allmbids-0.3.0-py3-none-any.whl
```

Installation logs, before/after package versions, checksums, a configuration
backup, the previous wheel and `report.json` are retained privately at:

```text
$HOME/.local/share/beets-allmbids/install-0.3.0-ikvdfuu3/
```

To roll back the plugin in the existing Beets environment, use the retained
0.2.2 wheel with `--no-deps`; the upgrade did not change configuration:

```sh
"$HOME/.local/share/pipx/venvs/beets/bin/python" -m pip install --no-deps --force-reinstall \
  "$HOME/.local/share/beets-allmbids/releases/0.2.2/beets_allmbids-0.2.2-py3-none-any.whl"
```

This is separate from restoring audio files; live files were never enriched
during the deployment. Keep the preview lock enabled until writes are wanted.

## Historical version: 0.2.2

This is the historical deployment record for **0.2.2** in the pipx-managed Beets
environment before the 0.3.0 upgrade recorded above.
The validated tag writer is unchanged from 0.2.1; this release adds a configuration
lock that rejects write requests before accessing query items. **51 local tests passed.**

The `allmbids` entry was appended to the existing plugin list. All other parsed
configuration values and existing dependencies were preserved. Configuration is:

```yaml
allmbids:
  contact: <the contact used during server validation>
  preview_only: true
```

There are no automatic import or tag-writing hooks. The normal `bi` import
wrapper was not changed. Do not disable `preview_only` until file writes are
explicitly wanted; while true, `--write` exits with a preview-only error.

## Use

```sh
beet allmbids --limit 1 id:7890
beet allmbids --limit 5 'artist:Bill Withers'
```

The command reports before/after tag arrays without applying them. Use a narrow
query first; the default limit is ten matching items. A query is required.

## Verified after installation

- Beets loads the installed package from its own Python environment.
- Help exposes the manual `allmbids` command.
- `allmbids --write --limit 1 id:7890` was rejected by the configuration lock.
- A real preview of item 7890 reported seven fields without applying changes.
- Checksums of the five previously validated source files and live database
  matched their pre-installation values. No music tags or database records changed.
- Existing package versions remained unchanged; only beets-allmbids was added.

The installed module resides at:

```text
$HOME/.local/share/pipx/venvs/beets/lib/python3.12/site-packages/beetsplug/allmbids/
```

The persistent wheel is under `$HOME/.local/share/beets-allmbids/releases/0.2.2/`.
The exact pre-install configuration backup and installation logs/report are under:

```text
$HOME/.local/share/beets-allmbids/install-2e6bz1is/
```

The repository is published at https://github.com/goosepod/beets-allmbids.
Local checkout locations vary by machine; the earlier Windows path is no longer
a deployment requirement.
