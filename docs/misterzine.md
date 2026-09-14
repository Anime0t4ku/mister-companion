# MisterZine Install Center integration

MisterZine appears under Extras. Its catalog entry is maintained in
`mister-companion-hub`; the desktop handler uses the project's stable Downloader
database with ID `misterzine`.

Installation reuses an existing registration, including
`downloader_misterzine.ini`, and sets an empty per-database filter so global core
filters do not omit application files. Duplicate registrations are reported by
the existing Downloader backend.

Connected installation runs `misterzine launcher enable` after Downloader
succeeds. SD-card installation leaves a message to run **MisterZine-Setup** from
Scripts after booting. Existing display settings and saved data are preserved.

The handler stays outside deferred Downloader batches and generic database
presence overrides: its setup step needs the downloaded executable, and its
status must distinguish downloaded files from completed menu setup. It still
participates in Install Center's update checks and Update All button through the
regular extra handler path.

Removal requires Downloader's native uninstall support. Connected removal uses
MisterZine's installed maintenance helper to check for active processes, remove
its startup hook, and stop its idle menu watcher. SD-card removal removes only
MisterZine's startup lines and menu entries. Downloader then removes the tracked
package and its registration. Favorites, preferences, and cached pictures are
retained. If removal fails after menu cleanup, the output explains how to restore
the menu entry.

## Validation

From the repository root, with application dependencies installed:

```sh
python -m unittest discover -s tests -v
```

To exercise the real public release and official Downloader against a temporary
card folder (requires internet, does not connect to a MiSTer):

```sh
python tests/verify_misterzine_downloader.py
```

This checks all published file hashes, global-filter compatibility, update
detection, saved-data preservation, cleanup, and same-version reinstallation.

Connected validation on a DE10-Nano passed with MisterZine v1.0.32: updating an
existing installation, refusal to remove a running frontend, removal, same-version
reinstallation, all 11 published file hashes, and launching from the menu. Saved
settings, favorites, MiSTer.ini, and unrelated Downloader sources were preserved.
Run the Hub's catalog validation separately.
