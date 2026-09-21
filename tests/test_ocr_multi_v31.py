import gc
import os
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import main


class OcrMultiV31Tests(unittest.TestCase):
    def test_tesseract_detection_exists(self):
        self.assertTrue(callable(main.detect_tesseract))
        status = main.detect_tesseract("fra")
        self.assertIn("languages", status)
        self.assertIn("ready", status)

    def test_bundled_tesseract_is_tried_before_system_install(self):
        # Une copie portable livrée à côté de l'application (dossier
        # "tesseract-ocr", ajoutée par Construire_le_exe.bat lorsqu'elle est
        # fournie) doit être essayée avant une éventuelle installation
        # système, pour que l'import de recette depuis une photo fonctionne
        # sans rien installer séparément quand elle est présente.
        bundled = os.path.join(main.BASE_DIR, "tesseract-ocr", "tesseract.exe")
        with patch.object(main.os.path, "isfile", side_effect=lambda p: p == bundled), \
             patch.object(main.pytesseract, "get_tesseract_version", return_value="5.0.0"), \
             patch.object(main.pytesseract, "get_languages", return_value=["fra", "eng"]):
            status = main.detect_tesseract("fra")
        self.assertEqual(status["executable"], bundled)
        self.assertTrue(status["ready"])


class ImportFromPhotoMultiTests(unittest.TestCase):
    """Instancie réellement ImportFromPhotoWindow pour vérifier le
    comportement multi-photos (ordre, réorganisation, transmission au
    formulaire), plutôt que d'inspecter le texte source des méthodes."""

    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.addCleanup(self.root.destroy)
        self.root.withdraw()

    @unittest.skipUnless(main.PIL_AVAILABLE, "Pillow indisponible")
    def test_multi_photo_import_keeps_all_sources_in_order(self):
        win = main.ImportFromPhotoWindow(self.root)
        self.addCleanup(win._close_import_window)

        with tempfile.TemporaryDirectory() as tmp:
            path_a = str(Path(tmp) / "a.jpg")
            path_b = str(Path(tmp) / "b.jpg")
            win.photo_paths = [path_a, path_b]
            win.text_box.insert("1.0", "Une recette de test")

            captured = {}

            class FakeRecipeFormWindow(tk.Toplevel):
                def __init__(fake_self, app, recipe_index=None, prefill=None):
                    super().__init__(app)
                    captured["prefill"] = prefill
                    fake_self.after_idle(fake_self.destroy)

            with patch.object(main, "RecipeFormWindow", FakeRecipeFormWindow):
                win.create_recipe()

        self.assertEqual(captured["prefill"]["image_sources"], [path_a, path_b])

    def test_reorder_remove_and_clear_controls_operate_on_the_real_photo_list(self):
        win = main.ImportFromPhotoWindow(self.root)
        self.addCleanup(win._close_import_window)

        with tempfile.TemporaryDirectory() as tmp:
            paths = [str(Path(tmp) / f"{i}.jpg") for i in range(3)]
            for p in paths:
                Path(p).touch()
            win.photo_paths = list(paths)
            win._refresh_photo_list()

            win.photo_listbox.selection_clear(0, tk.END)
            win.photo_listbox.selection_set(0)
            win._move_photo(1)
            self.assertEqual(win.photo_paths, [paths[1], paths[0], paths[2]])

            win.photo_listbox.selection_clear(0, tk.END)
            win.photo_listbox.selection_set(2)
            win._remove_selected_photo()
            self.assertEqual(win.photo_paths, [paths[1], paths[0]])

            win._clear_photos()
            self.assertEqual(win.photo_paths, [])
            self.assertEqual(win.text_box.get("1.0", "end-1c"), "")

    @unittest.skipUnless(main.PIL_AVAILABLE, "Pillow indisponible")
    def test_ocr_processes_a_snapshot_in_order_even_if_the_selection_changes_meanwhile(self):
        win = main.ImportFromPhotoWindow(self.root)
        self.addCleanup(win._close_import_window)
        win._ocr_status_checking = False
        win._ocr_status = {
            "pytesseract": True, "executable": "/usr/bin/tesseract",
            "ready": True, "reason": "", "required_lang": "fra",
        }

        with tempfile.TemporaryDirectory() as tmp:
            path_a = str(Path(tmp) / "a.jpg")
            path_b = str(Path(tmp) / "b.jpg")
            main.Image.new("RGB", (10, 10), "white").save(path_a)
            main.Image.new("RGB", (10, 10), "white").save(path_b)
            win.photo_paths = [path_a, path_b]
            win._refresh_photo_list()

            call_count = [0]

            def fake_image_to_string(image, lang=None, timeout=None):
                call_count[0] += 1
                return f"Texte {call_count[0]}"

            # gc désactivé : une collecte cyclique déclenchée pendant qu'un
            # thread d'arrière-plan compile ce module la toute première fois
            # peut planter l'interpréteur dans cet environnement — sans
            # rapport avec le comportement vérifié ici.
            gc_was_enabled = gc.isenabled()
            gc.disable()
            try:
                with patch.object(
                    main, "pytesseract",
                    SimpleNamespace(image_to_string=fake_image_to_string),
                    create=True,
                ), patch.object(main, "detect_ocr_rotation", lambda *a, **k: 0):
                    win.extract_text()
                    # L'utilisateur vide la sélection PENDANT que l'OCR tourne
                    # déjà en arrière-plan sur l'instantané pris au départ.
                    win.photo_paths = []

                    deadline = time.monotonic() + 5.0
                    final_text = ""
                    while not final_text and time.monotonic() < deadline:
                        win.update()
                        final_text = win.text_box.get("1.0", "end-1c")
            finally:
                if gc_was_enabled:
                    gc.enable()

        self.assertEqual(call_count[0], 2)
        self.assertIn("Texte 1", final_text)
        self.assertIn("Texte 2", final_text)
        self.assertLess(final_text.index("Texte 1"), final_text.index("Texte 2"))


if __name__ == "__main__":
    unittest.main()
