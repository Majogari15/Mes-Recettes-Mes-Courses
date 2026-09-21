import json
import re
import unittest
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import main


class AuditV52Tests(unittest.TestCase):
    def test_all_languages_have_same_keys_and_placeholders(self):
        catalog = json.loads((ROOT / "i18n_desktop.json").read_text(encoding="utf-8"))
        french = catalog["fr"]
        def placeholders(value):
            return sorted(re.findall(r"\{[^{}]+\}", value))
        for language in ("en", "es", "de"):
            translated = catalog["translations"][language]
            self.assertEqual(set(french), set(translated), language)
            for key in french:
                self.assertEqual(placeholders(french[key]), placeholders(translated[key]), f"{language}:{key}")

    def test_home_empty_alert_is_translated(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertIn('t("home_no_alerts")', source)
        self.assertNotIn('text="✓ Aucun rappel important pour le moment."', source)

    def test_windows_test_launcher_discovers_full_suite(self):
        launcher = (ROOT / "Executer_les_tests.bat").read_text(encoding="utf-8")
        self.assertIn("unittest discover -s tests -p \"test_*.py\" -v", launcher)

    def test_mousewheel_is_never_bound_globally(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertNotIn('bind_all("<MouseWheel>"', source)
        self.assertNotIn('unbind_all("<MouseWheel>"', source)
        self.assertIn("_ui_bind_local_mousewheel", source)

    def test_language_catalog_keeps_complete_french_fallback(self):
        for language in ("fr", "en", "es", "de"):
            catalog = main._language_catalog(language)
            self.assertEqual(set(main.FRENCH_STRINGS), set(catalog), language)

    def test_open_window_refresh_helpers_are_called_by_settings(self):
        for method_name, helper in (
            ("set_language", "_ui_translate_open_windows"),
            ("toggle_dark_mode", "_ui_recolor_open_windows"),
            ("toggle_large_text", "_ui_rescale_open_window_fonts"),
        ):
            import inspect
            self.assertIn(helper, inspect.getsource(getattr(main.App, method_name)))


if __name__ == "__main__":
    unittest.main()
