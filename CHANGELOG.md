# Changelog

## 1.2.2 - 2026-10-13

- Fix false "intruder" alerts after a normal password unlock: the notification now
  counts only leftover photos from the **current** lock session, not older files
  still sitting in the photo folder.
- Raise unlock hygiene from 3 to 6 photos so a lid-open burst plus a password
  burst is cleared silently.
- Intruder toast click opens the newest remaining session photo (`omarchy-notification-send --exec xdg-open`).
- Toast thumbnail uses that photo path for `--image` / `-i` instead of the
  unresolved `camera-photo` theme icon (broken checkerboard).

## 1.2.1 - 2026-09-29

- Keep the bar icon on the transparent-bar contrast color so it turns dark on a light background.
- Let a photo folder on a user FUSE mount (pCloud, rclone) be written by the hardened service.
- Sync the systemd unit from `photoDirectory` without putting UTF-8 paths on the Polkit command line.

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
