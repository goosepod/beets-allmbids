# Preview-only installation on entertain

Version **0.2.2** is installed in the existing pipx-managed Beets environment.
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

The local source Git repository was moved, with its history, to
`C:\Users\ursasmar\Projects\beets-allmbids`. It has not been published remotely.
