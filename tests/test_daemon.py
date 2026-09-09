#!/usr/bin/env python3

import importlib.util
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock


PLUGIN_DIR = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("camguard_daemon", PLUGIN_DIR / "daemon.py")
camguard = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(camguard)


class LockStateMachineTests(unittest.TestCase):
    def test_unknown_never_changes_confirmed_state(self) -> None:
        state = camguard.LockStateMachine()
        self.assertEqual(state.observe(None), "")
        self.assertIsNone(state.value)
        self.assertEqual(state.observe(True), "locked")
        self.assertTrue(state.value)
        self.assertEqual(state.observe(None), "")
        self.assertTrue(state.value)
        self.assertEqual(state.observe(False), "unlocked")
        self.assertFalse(state.value)

    def test_initial_unlocked_is_not_an_unlock_transition(self) -> None:
        state = camguard.LockStateMachine()
        self.assertEqual(state.observe(False), "")
        self.assertFalse(state.value)


class CaptureScheduleTests(unittest.TestCase):
    def test_activity_resets_plus_five_and_plus_ten(self) -> None:
        schedule = camguard.CaptureSchedule(5)
        self.assertTrue(schedule.trigger("trackpad", 0))
        self.assertFalse(schedule.trigger("keyboard", 2))
        self.assertEqual(schedule.due(6.9), "")
        self.assertEqual(schedule.due(7), "keyboard")
        self.assertEqual(schedule.due(12), "keyboard")
        self.assertFalse(schedule.active)

    def test_new_sequence_gets_one_immediate_capture(self) -> None:
        schedule = camguard.CaptureSchedule(5)
        self.assertTrue(schedule.trigger("mouse", 0))
        self.assertEqual(schedule.due(5), "mouse")
        self.assertEqual(schedule.due(10), "mouse")
        self.assertTrue(schedule.trigger("lid", 20))


class SessionManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.photos = self.root / "photos"
        self.photos.mkdir()
        self.original_session_path = camguard.SESSION_PATH
        camguard.SESSION_PATH = self.root / "state" / "active-session.json"
        self.config = {"photoDirectory": str(self.photos)}

    def tearDown(self) -> None:
        camguard.SESSION_PATH = self.original_session_path
        self.temporary.cleanup()

    def create_and_record(self, name: str) -> Path:
        photo = self.photos / name
        photo.write_bytes(b"png")
        camguard.record_session_photo(str(photo), "keyboard")
        return photo

    def test_unlock_deletes_only_last_three_session_photos(self) -> None:
        camguard.start_or_resume_session(4)
        photos = [self.create_and_record(f"{index}.png") for index in range(4)]
        self.assertEqual(camguard.finish_session(self.config, 3), 3)
        self.assertTrue(photos[0].exists())
        self.assertTrue(all(not photo.exists() for photo in photos[1:]))

    def test_session_without_photos_deletes_nothing_old(self) -> None:
        old_photo = self.photos / "old-evidence.png"
        old_photo.write_bytes(b"png")
        camguard.start_or_resume_session(7)
        self.assertEqual(camguard.finish_session(self.config, 3), 0)
        self.assertTrue(old_photo.exists())

    def test_restart_resumes_manifest_for_same_lock_generation(self) -> None:
        camguard.start_or_resume_session(9)
        photo = self.create_and_record("first.png")
        before = json.loads(camguard.SESSION_PATH.read_text())
        camguard.start_or_resume_session(9)
        after = json.loads(camguard.SESSION_PATH.read_text())
        self.assertEqual(after["id"], before["id"])
        self.assertEqual(after["photos"][0]["path"], str(photo))


class NotificationTests(unittest.TestCase):
    def test_session_photo_detection_requires_a_non_empty_list(self) -> None:
        self.assertFalse(camguard.session_has_photos({}))
        self.assertFalse(camguard.session_has_photos({"photos": []}))
        self.assertTrue(camguard.session_has_photos({"photos": [{"path": "one.png"}]}))

    def test_notification_is_skipped_when_no_photo_remains(self) -> None:
        with mock.patch.object(camguard.subprocess, "run") as run:
            self.assertFalse(camguard.notify_intruder_photos(0))
            run.assert_not_called()

    def test_notification_uses_the_omarchy_session_bus(self) -> None:
        completed = camguard.subprocess.CompletedProcess([], 0, "", "")
        with mock.patch.object(camguard.subprocess, "run", return_value=completed) as run:
            self.assertTrue(camguard.notify_intruder_photos(2))

        command = run.call_args.args[0]
        environment = run.call_args.kwargs["env"]
        self.assertEqual(command[0], "/usr/bin/notify-send")
        self.assertIn("--urgency=critical", command)
        self.assertIn("2 photos restent", command[-1])
        self.assertTrue(environment["DBUS_SESSION_BUS_ADDRESS"].endswith("/bus"))


class RetentionTests(unittest.TestCase):
    def test_cleanup_removes_only_expired_images(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old_photo = root / "old.png"
            recent_photo = root / "recent.JPEG"
            ignored_file = root / "notes.txt"
            old_photo.write_bytes(b"old")
            recent_photo.write_bytes(b"recent")
            ignored_file.write_text("keep")
            old_time = time.time() - 120
            os.utime(old_photo, (old_time, old_time))

            config = {"photoDirectory": str(root), "retentionSeconds": 60}
            camguard.cleanup(config)

            self.assertFalse(old_photo.exists())
            self.assertTrue(recent_photo.exists())
            self.assertTrue(ignored_file.exists())
            self.assertEqual(camguard.stored_photo_count(config), 1)


class LockFileTests(unittest.TestCase):
    def test_missing_and_invalid_lock_files_are_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            original = camguard.LOCK_STATE_PATH
            camguard.LOCK_STATE_PATH = Path(directory) / "lock.json"
            try:
                self.assertEqual(camguard.read_lock_state(), (None, 0))
                camguard.LOCK_STATE_PATH.write_text('{"locked":"yes"}')
                self.assertEqual(camguard.read_lock_state(), (None, 0))
                camguard.LOCK_STATE_PATH.write_text('{"locked":true,"generation":3}')
                self.assertEqual(camguard.read_lock_state(), (True, 3))
            finally:
                camguard.LOCK_STATE_PATH = original


if __name__ == "__main__":
    unittest.main()
