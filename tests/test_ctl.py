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


if __name__ == "__main__":
    unittest.main()
