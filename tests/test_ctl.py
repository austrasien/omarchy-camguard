#!/usr/bin/env python3

import json
import tempfile
import unittest
import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path


CTL_PATH = Path(__file__).resolve().parents[1] / "bin" / "omarchy-camguardctl"
LOADER = SourceFileLoader("camguardctl", str(CTL_PATH))
SPEC = importlib.util.spec_from_loader("camguardctl", LOADER)
assert SPEC is not None and SPEC.loader is not None
ctl = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ctl)


class LockPublisherTests(unittest.TestCase):
    def test_generation_changes_only_on_state_transition(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            original = ctl.LOCK_STATE_PATH
            ctl.LOCK_STATE_PATH = Path(directory) / "lock-state.json"
            try:
                ctl.publish_lock_state(False)
                first = json.loads(ctl.LOCK_STATE_PATH.read_text())
                ctl.publish_lock_state(False)
                repeated = json.loads(ctl.LOCK_STATE_PATH.read_text())
                ctl.publish_lock_state(True)
                changed = json.loads(ctl.LOCK_STATE_PATH.read_text())
            finally:
                ctl.LOCK_STATE_PATH = original
        self.assertEqual(first["generation"], repeated["generation"])
        self.assertEqual(changed["generation"], first["generation"] + 1)
        self.assertTrue(changed["locked"])

    def test_invalid_previous_generation_is_recovered(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            original = ctl.LOCK_STATE_PATH
            ctl.LOCK_STATE_PATH = Path(directory) / "lock-state.json"
            try:
                ctl.LOCK_STATE_PATH.write_text('{"locked":false,"generation":"bad"}')
                ctl.publish_lock_state(True)
                changed = json.loads(ctl.LOCK_STATE_PATH.read_text())
            finally:
                ctl.LOCK_STATE_PATH = original
        self.assertEqual(changed["generation"], 1)


class PhotoDirectoryTests(unittest.TestCase):
    def test_resolve_rejects_paths_outside_home(self) -> None:
        with self.assertRaises(ValueError):
            ctl.resolve_photo_directory("/tmp/camguard")

    def test_set_photo_directory_writes_config_without_service_update(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original_home = ctl.HOME
            original_config = ctl.CONFIG_PATH
            original_default = ctl.DEFAULT_PHOTO_DIR
            ctl.HOME = root / "home"
            ctl.HOME.mkdir()
            ctl.CONFIG_PATH = ctl.HOME / "config.json"
            ctl.DEFAULT_PHOTO_DIR = ctl.HOME / "Pictures" / "CamGuard"
            try:
                target = ctl.HOME / "Snapshots"
                chosen = ctl.set_photo_directory(target, update_service=False)
                config = json.loads(ctl.CONFIG_PATH.read_text())
                self.assertEqual(chosen, target.resolve())
                self.assertEqual(config["photoDirectory"], str(target.resolve()))
                self.assertTrue(target.exists())
            finally:
                ctl.HOME = original_home
                ctl.CONFIG_PATH = original_config
                ctl.DEFAULT_PHOTO_DIR = original_default

    def test_uri_to_path_decodes_file_uris(self) -> None:
        path = ctl.uri_to_path("file:///home/example/My%20Photos")
        self.assertEqual(path, Path("/home/example/My Photos"))


if __name__ == "__main__":
    unittest.main()
