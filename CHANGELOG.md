# Changelog

## 1.2.0 - 2026-09-10

- Add a **Directory...** panel button to choose the on-disk photo folder (home only).
- Persist `photoDirectory` and refresh the systemd `ReadWritePaths` via Polkit when it changes.
- Show the current photo directory in the panel status grid.
- Style **Delete photos** with the current Omarchy theme accent color.

## 1.1.0 - 2026-09-09

- Make lock detection compatible with Omarchy 4.0.3 authentication isolation.
- Remove the dependency on a customized Omarchy lock plugin.
- Add portable installation and non-destructive uninstallation.
- Bundle the controller and default configuration.
- Notify the user when session photos remain after unlock cleanup.
- Add public documentation, security notes, tests, and CI.

## 1.0.0 - 2026-09-03

- Initial local release.
