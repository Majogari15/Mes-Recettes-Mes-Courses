import tkinter as tk
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import main
from test_regressions import TempDataMixin

class TkinterDnD2V30Tests(unittest.TestCase):
    def test_old_windnd_backend_removed(self):
        # Vérification d'absence de code mort : une simple recherche dans le
        # fichier suffit, aucune exécution n'apporterait plus d'information.
        source = main.Path(main.__file__).read_text(encoding="utf-8")
        self.assertNotIn("import windnd", source)
        self.assertNotIn("windnd.hook_dropfiles", source)

class TkinterDnD2LiveTests(TempDataMixin, unittest.TestCase):
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
        self.form = main.RecipeFormWindow(self.app, None)
        self.addCleanup(self.form.destroy)

    def test_photo_tab_is_registered_as_drop_target(self):
        # _enable_photo_drop() est appelé depuis __init__ : si tkinterdnd2
        # est disponible (c'est le cas ici), le drop réel doit avoir réussi.
        self.assertTrue(main.TKDND_AVAILABLE)
        self.assertTrue(self.form._photo_drop_enabled)

    def test_drop_callback_splits_tcl_list_and_returns_copy(self):
        captured = []
        def fake_normalise(paths):
            captured.append(list(paths))
            return list(paths)
        # Liste Tcl avec un élément entre accolades contenant un espace :
        # un simple str.split() le découperait en deux, à tort.
        fake_event = SimpleNamespace(data="{un fichier avec espace.jpg} deuxieme.jpg")
        with patch.object(self.form, "_normalise_dropped_photo_paths", side_effect=fake_normalise):
            result = self.form._on_photo_drop_event(fake_event)
            self.assertEqual(result, main.COPY)
            self.form.update()  # laisse after_idle() s'exécuter, patch encore actif
        self.assertEqual(captured[0], ["un fichier avec espace.jpg", "deuxieme.jpg"])

if __name__ == "__main__":
    unittest.main()
