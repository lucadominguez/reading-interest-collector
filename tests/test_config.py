import json
import os
import tempfile
import unittest

from collector import config


class ConfigTest(unittest.TestCase):
    def test_missing_file_returns_defaults(self):
        cfg = config.load_config("/nonexistent/config.json")
        self.assertIn("ratings", cfg)
        self.assertEqual(cfg["ratings"]["very_interesting"], "ctrl+alt+1")
        self.assertIn("sampler", cfg)

    def test_default_db_path_expands_tilde(self):
        self.assertTrue(config.default_db_path().startswith(os.path.expanduser("~")))

    def test_partial_config_deep_fills(self):
        d = tempfile.mkdtemp()
        path = os.path.join(d, "config.json")
        with open(path, "w") as fh:
            json.dump({"ratings": {"research": "ctrl+alt+9"},
                       "sampler": {"enabled": False}}, fh)
        cfg = config.load_config(path)
        # provided values kept
        self.assertEqual(cfg["ratings"]["research"], "ctrl+alt+9")
        self.assertFalse(cfg["sampler"]["enabled"])
        # missing keys deep-filled from defaults
        self.assertEqual(cfg["ratings"]["interesting"], "ctrl+alt+2")
        self.assertEqual(cfg["sampler"]["interval_minutes"], 5)
        self.assertTrue(cfg["sampler"]["only_reading_apps"])

    def test_save_roundtrip(self):
        d = tempfile.mkdtemp()
        path = os.path.join(d, "config.json")
        cfg = config.load_config("/nonexistent")
        cfg["ratings"]["research"] = "ctrl+shift+r"
        config.save_config(cfg, path)
        loaded = config.load_config(path)
        self.assertEqual(loaded["ratings"]["research"], "ctrl+shift+r")

    def test_ratings_for_keys(self):
        cfg = config.load_config("/nonexistent")
        rk = config.ratings_for_keys(cfg)
        self.assertEqual(rk["ctrl+alt+1"], "very_interesting")
        self.assertEqual(len(rk), len(cfg["ratings"]))

    def test_pynput_hotkey_normalizes_modifiers(self):
        # Bare modifier names are invalid in pynput HotKey.parse; they must be
        # wrapped in angle brackets. Single chars stay bare.
        self.assertEqual(config.pynput_hotkey("ctrl+alt+1"), "<ctrl>+<alt>+1")
        self.assertEqual(config.pynput_hotkey("ctrl+alt+2"), "<ctrl>+<alt>+2")
        self.assertEqual(config.pynput_hotkey("ctrl+shift+r"), "<ctrl>+<shift>+r")
        # Already-bracketed input is not double-wrapped.
        self.assertEqual(config.pynput_hotkey("<ctrl>+<alt>+1"), "<ctrl>+<alt>+1")
        # Every configured default rating round-trips through pynput syntax.
        for hk in config.DEFAULT_CONFIG["ratings"].values():
            out = config.pynput_hotkey(hk)
            self.assertIn("<ctrl>", out)
            self.assertIn("<alt>", out)


if __name__ == "__main__":
    unittest.main()
