import json
import os
import re
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import font as tkfont, ttk
from unittest.mock import patch
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import main
from test_regressions import TempDataMixin


class AuditV52Tests(unittest.TestCase):
    def test_all_languages_have_same_keys_and_placeholders(self):
        def load(language):
            return json.loads((ROOT / "i18n" / f"{language}.json").read_text(encoding="utf-8"))
        french = load("fr")
        def placeholders(value):
            return sorted(re.findall(r"\{[^{}]+\}", value))
        for language in main.UI_TRANSLATED_LANGUAGES:
            translated = load(language)
            self.assertEqual(set(french), set(translated), language)
            for key in french:
                self.assertEqual(placeholders(french[key]), placeholders(translated[key]), f"{language}:{key}")

    def test_translation_keys_are_all_used_and_all_defined(self):
        # C5 : 59 clés orphelines traînaient dans les 9 langues. Une clé est
        # « utilisée » si elle apparaît littéralement dans main.py ou si un
        # préfixe dynamique (t(f"weekday_{...}"), "x_" + y) la couvre.
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        french = json.loads((ROOT / "i18n" / "fr.json").read_text(encoding="utf-8"))
        used = set(re.findall(r"""\bt\(\s*["']([a-zA-Z0-9_]+)["']""", source))
        self.assertEqual(sorted(used - set(french)), [])
        dynamic = set(re.findall(r"""f["']([a-z][a-z0-9_]*?)\{""", source)) | \
            set(re.findall(r"""["']([a-z][a-z0-9_]+_)["']\s*\+""", source))
        orphans = [k for k in french if f'"{k}"' not in source and f"'{k}'" not in source
                   and not any(k.startswith(p) for p in dynamic if p)]
        self.assertEqual(orphans, [])

    def test_paddings_follow_the_large_text_scale(self):
        # C2 : 900+ marges en nombre fixe ne grandissaient pas en mode
        # « Texte agrandi ». Toute marge non nulle passe par gs(...).
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        literal = re.findall(r"\b(?:padx|pady|ipadx|ipady|padding)\s*=\s*\(?\s*[1-9]\d*\b(?!\s*[*/+-])", source)
        self.assertEqual(literal, [])

    def test_every_language_and_bundled_file_is_shipped(self):
        # Un fichier oublié au packaging ne casse que la version installée :
        # tout fichier référencé doit exister, et les scripts doivent copier
        # les dossiers entiers (une langue ajoutée suit automatiquement).
        for language in ("fr", *main.UI_TRANSLATED_LANGUAGES):
            self.assertTrue((ROOT / "i18n" / f"{language}.json").is_file(), language)
        bundled = [main.DEFAULT_INGREDIENTS_FILE, main.NUTRITION_DATA_FILE,
                   main.INGREDIENT_ALLERGENS_FILE, main.INGREDIENT_SUBSTITUTIONS_FILE,
                   *main.INGREDIENT_SUBSTITUTIONS_TRANSLATION_FILES.values(),
                   *main.INGREDIENT_TRANSLATIONS_FILES.values()]
        for path in bundled + list(main.FLAG_FILES.values()):
            self.assertTrue(os.path.isfile(path), path)
            self.assertEqual(os.path.dirname(path), main.BUNDLED_DATA_DIR)
        self.assertEqual(set(main.FLAG_FILES), set(main.UI_LANGUAGES))
        self.assertEqual(set(main.INGREDIENT_TRANSLATIONS_FILES), set(main.UI_TRANSLATED_LANGUAGES))
        build = (ROOT / "Construire_le_exe.bat").read_text(encoding="utf-8")
        self.assertIn(r"xcopy /Y /E /I /Q i18n dist\i18n", build)
        self.assertIn(r"xcopy /Y /E /I /Q data dist\data", build)
        for script in ("installateur.iss", "installateur_store_capture.iss"):
            text = (ROOT / script).read_text(encoding="utf-8-sig")
            self.assertIn(r'Source: "dist\i18n\*"; DestDir: "{app}\i18n"', text, script)
            self.assertIn(r'Source: "dist\data\*"; DestDir: "{app}\data"', text, script)

    def test_tesseract_packs_cover_every_ui_language(self):
        import tempfile
        import preparer_tesseract as prep
        self.assertEqual(set(prep.LANGUAGES) - {"osd"}, set(main.TESSERACT_LANG_CODES.values()))
        self.assertEqual(set(main.TESSERACT_LANG_CODES), set(main.UI_LANGUAGES))
        self.assertIn("python preparer_tesseract.py", (ROOT / "Construire_le_exe.bat").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            tessdata = Path(tmp) / "tessdata"
            tessdata.mkdir()
            (tessdata / "fra.traineddata").write_bytes(b"x" * prep.MIN_SIZE)
            fetched = []
            def fetch(url, destination):
                fetched.append(url)
                destination.write_bytes(b"x" * (10 if "nor" in url else prep.MIN_SIZE))
            # Paquet tronqué : échec, aucun fichier final ni .part laissé.
            with self.assertRaises(RuntimeError):
                prep.ensure_languages(tessdata, ("fra", "ita", "nor"), fetch)
            self.assertFalse((tessdata / "nor.traineddata").exists())
            self.assertEqual(list(tessdata.glob("*.part")), [])
            # Déjà présents : pas retéléchargés.
            fetched.clear()
            self.assertEqual(prep.ensure_languages(tessdata, ("fra", "ita", "swe"), fetch), ["swe"])
            self.assertEqual(len(fetched), 1)
            # Copie de l'installation système quand le dossier portable manque.
            source = Path(tmp) / "sys"
            (source / "tessdata").mkdir(parents=True)
            (source / "tesseract.exe").write_bytes(b"exe")
            target = Path(tmp) / "portable"
            self.assertFalse(prep.copy_installation(target, [Path(tmp) / "absent"]))
            self.assertTrue(prep.copy_installation(target, [source]))
            self.assertTrue((target / "tesseract.exe").is_file())

    def test_ui_languages_are_loaded_only_when_used(self):
        lazy = main._LazyTranslations()
        self.assertEqual(dict.__len__(lazy), 0)
        self.assertIn("en", lazy)
        self.assertEqual(dict.__len__(lazy), 0)
        self.assertEqual(lazy["de"]["common_close"], main.TRANSLATIONS["de"]["common_close"])
        self.assertEqual(list(dict.keys(lazy)), ["de"])
        self.assertEqual(set(lazy), set(main.UI_TRANSLATED_LANGUAGES))
        self.assertEqual(lazy.get("xx", {}), {})

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

class TkReleasedInMainThreadTests(TempDataMixin, unittest.TestCase):
    def test_destroyed_app_is_freed_by_the_main_thread_collection(self):
        # Le garde-fou de conftest (gc.collect après chaque test) n'est utile
        # que si une App détruite devient bien libérable : sinon elle serait
        # collectée plus tard, au hasard, dans un thread secondaire.
        import gc
        import weakref
        import conftest
        self.assertTrue(hasattr(conftest, "_liberer_tk_dans_le_thread_principal"))
        with patch.object(main, "get_disclaimer_accepted", lambda: True), \
             patch.object(main, "maybe_create_auto_backup", lambda: None):
            try:
                app = main.App()
            except tk.TclError as exc:
                self.skipTest(str(exc))
        app.withdraw()
        app.update()
        ref = weakref.ref(app)
        app.destroy()
        del app
        gc.collect()
        self.assertIsNone(ref())


class TclTransientInitRetryTests(unittest.TestCase):
    def test_transient_tcl_error_is_retried_other_errors_are_not(self):
        import conftest
        self.assertTrue(getattr(tk.Tk.__init__, "_avec_reessai_tcl", False))
        calls = []

        def flaky(self_, fail_times, message):
            calls.append(1)
            if len(calls) <= fail_times:
                raise tk.TclError(message)
            return "ok"
        init = conftest._avec_reessai_tcl(flaky, essais=3, pause=0)
        self.assertEqual(init(None, 2, "Can't find a usable init.tcl in the following directories:"), "ok")
        self.assertEqual(len(calls), 3)
        calls.clear()
        with self.assertRaises(tk.TclError):
            init(None, 5, "couldn't read file \"x\": No error")
        self.assertEqual(len(calls), 3)
        calls.clear()
        with self.assertRaises(tk.TclError):
            init(None, 1, "no display name and no $DISPLAY environment variable")
        self.assertEqual(len(calls), 1)


class PendingAfterCancelTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.addCleanup(self.root.destroy)
        self.root.withdraw()

    def _scheduled(self):
        return set(self.root.tk.splitlist(self.root.tk.call("after", "info")))

    def test_destroying_a_widget_cancels_its_pending_callbacks(self):
        frame = ttk.Frame(self.root)
        calls = []
        idle_id = frame.after_idle(lambda: calls.append("idle"))
        timer_id = frame.after(10, lambda: calls.append("timer"))
        self.assertTrue({idle_id, timer_id} <= self._scheduled())
        frame.destroy()
        self.assertFalse({idle_id, timer_id} & self._scheduled())
        self.root.after(30, lambda: None)
        self.root.update()
        self.root.after(40)
        self.root.update()
        self.assertEqual(calls, [])

    def test_callbacks_still_run_and_are_forgotten_afterwards(self):
        frame = ttk.Frame(self.root)
        self.addCleanup(frame.destroy)
        calls = []
        frame.after_idle(lambda a, b: calls.append(a + b), 1, 2)
        self.root.update()
        self.assertEqual(calls, [3])
        self.assertEqual(frame._pending_after_ids, set())
        # after(ms) sans fonction reste une simple pause.
        self.assertIsNone(frame.after(1))


class OpenWindowRefreshTests(TempDataMixin, unittest.TestCase):
    """Vérifie, en instanciant réellement l'App et une fenêtre secondaire
    déjà ouverte, que changer la langue, le thème ou la taille de texte
    depuis les paramètres se répercute effectivement dessus — sans la
    fermer/rouvrir — plutôt que d'inspecter le texte source des méthodes."""

    def setUp(self):
        super().setUp()
        for name, value in (
            ("get_disclaimer_accepted", lambda: True),
            ("get_large_text_preference", lambda: False),
            ("get_language_preference", lambda: "fr"),
            ("maybe_create_auto_backup", lambda: None),
        ):
            patcher = patch.object(main, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        try:
            self.app = main.App()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.addCleanup(self.app.destroy)
        self.app.withdraw()
        self.diag = main.DiagnosticWindow(self.app)
        self.addCleanup(self.diag.destroy)

    def _close_button(self):
        for child in self.diag.winfo_children():
            if isinstance(child, ttk.Frame):
                for grandchild in child.winfo_children():
                    if isinstance(grandchild, ttk.Button) and grandchild.cget("text") == main.t("common_close"):
                        return grandchild
        self.fail("bouton Fermer introuvable dans DiagnosticWindow")

    def test_set_language_retranslates_already_open_window(self):
        close_button = self._close_button()
        self.assertEqual(close_button.cget("text"), main.FRENCH_STRINGS["common_close"])
        self.app.set_language("en")
        self.assertEqual(close_button.cget("text"), main.TRANSLATIONS["en"]["common_close"])

    def test_toggle_dark_mode_recolors_already_open_window(self):
        before = self.diag.cget("background")
        self.app.toggle_dark_mode()
        after = self.diag.cget("background")
        self.assertNotEqual(before, after)
        self.assertEqual(str(after), main.COLOR_BG)

    def test_toggle_high_contrast_recolors_already_open_window(self):
        # Même mécanique que toggle_dark_mode, mode indépendant (voir
        # apply_palette) : la palette noir/blanc/jaune remplace le thème
        # clair/sombre actif, sans perdre la préférence dark_mode mémorisée.
        self.assertFalse(self.app.high_contrast)
        before = self.diag.cget("background")
        self.app.toggle_high_contrast()
        after = self.diag.cget("background")
        self.assertTrue(self.app.high_contrast)
        self.assertNotEqual(before, after)
        self.assertEqual(str(after), main.COLOR_BG)
        self.assertEqual(main.COLOR_BG, main.HIGH_CONTRAST_PALETTE["BG"])

        # Désactivation : revient au thème clair/sombre mémorisé (pas figé
        # sur la palette contraste élevé).
        dark_mode_before_disable = self.app.dark_mode
        self.app.toggle_high_contrast()
        self.assertFalse(self.app.high_contrast)
        self.assertEqual(self.app.dark_mode, dark_mode_before_disable)
        expected = main.DARK_PALETTE if self.app.dark_mode else main.LIGHT_PALETTE
        self.assertEqual(main.COLOR_BG, expected["BG"])

    def test_repeated_language_and_theme_changes_raise_no_tk_callback_error(self):
        # Cause du flake : un after_idle programmé sur un widget détruit par
        # la reconstruction de l'accueil appelait un nouveau `lambda e:` de
        # même nom Tcl, sans argument (TypeError → boîte « Erreur »).
        errors = []
        self.app.report_callback_exception = lambda exc, val, tb: errors.append(f"{exc.__name__}: {val}")
        for language in ("en", "fr", "de", "fr", "sv", "fr") * 4:
            self.app.set_language(language)
            self.app.toggle_dark_mode()
            self.app.update()
        self.assertEqual(errors, [])

    def test_toggle_large_text_rescales_already_open_window_font(self):
        style = ttk.Style(self.app)
        before_font = tkfont.Font(root=self.app, font=style.lookup("TButton", "font"))
        before_size = before_font.cget("size")
        self.app.toggle_large_text()
        after_font = tkfont.Font(root=self.app, font=style.lookup("TButton", "font"))
        after_size = after_font.cget("size")
        self.assertGreater(main.FONT_SCALE, 1.0)
        self.assertGreater(abs(after_size), abs(before_size))


if __name__ == "__main__":
    unittest.main()
