import ast
import gc
import queue
import tempfile
import threading
import time
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import main


class ImportPhotoV36Tests(unittest.TestCase):
    def test_success_color_use_of_color_success_is_never_undefined(self):
        # Historique : un renommage de palette avait laissé un usage de
        # COLOR_SUCCESS (jamais défini) dans le code, provoquant un
        # NameError seulement au moment où l'état "prêt" s'affichait.
        tree = ast.parse(Path(main.__file__).read_text(encoding="utf-8"))
        undefined_success_uses = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and node.id == "COLOR_SUCCESS"
        ]
        self.assertEqual(undefined_success_uses, [])

    def test_new_status_messages_exist_in_every_language(self):
        for key in ("importphoto_ocr_checking", "importphoto_ocr_checking_wait"):
            self.assertIn(key, main.FRENCH_STRINGS)
            for lang in ("en", "es", "de"):
                self.assertIn(key, main.TRANSLATIONS[lang])


class ImportPhotoOcrStatusLiveTests(unittest.TestCase):
    """Instancie réellement ImportFromPhotoWindow pour vérifier que la
    détection Tesseract s'exécute bien en tâche de fond (sans bloquer le
    constructeur ni l'interface), plutôt que d'inspecter le texte source."""

    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.addCleanup(self.root.destroy)
        self.root.withdraw()

    def test_ocr_status_check_runs_in_background_without_blocking_construction(self):
        slow_started = threading.Event()

        def slow_status():
            slow_started.set()
            time.sleep(0.3)
            return {
                "pytesseract": True, "executable": "/usr/bin/tesseract",
                "ready": True, "reason": "", "required_lang": "fra",
                "version": "5.0",
            }

        with patch.object(main, "current_tesseract_status", slow_status):
            start = time.monotonic()
            win = main.ImportFromPhotoWindow(self.root)
            construction_time = time.monotonic() - start
            self.addCleanup(win._close_import_window)

            # Le constructeur ne doit pas attendre current_tesseract_status()
            # (elle prend 0.3s) : il doit seulement programmer self.after(50, ...).
            self.assertLess(construction_time, 0.2)
            self.assertFalse(slow_started.is_set())

            deadline = time.monotonic() + 2.0
            while not slow_started.is_set() and time.monotonic() < deadline:
                win.update()
            self.assertTrue(
                slow_started.is_set(),
                "la vérification Tesseract doit finir par démarrer sur un thread"
            )

            checking_text = main.t("importphoto_ocr_checking")
            deadline = time.monotonic() + 2.0
            while win.ocr_status_label.cget("text") == checking_text and time.monotonic() < deadline:
                win.update()

        self.assertNotEqual(win.ocr_status_label.cget("text"), checking_text)
        self.assertEqual(str(win.ocr_status_label.cget("foreground")), main.COLOR_GREEN)
        self.assertEqual(str(win.extract_button.cget("state")), "disabled")  # aucune photo choisie

    @unittest.skipUnless(main.PIL_AVAILABLE, "Pillow indisponible")
    def test_ocr_worker_runs_safely_on_a_background_thread(self):
        win = main.ImportFromPhotoWindow(self.root)
        self.addCleanup(win._close_import_window)

        with tempfile.TemporaryDirectory() as tmp:
            photo_path = str(Path(tmp) / "photo.jpg")
            main.Image.new("RGB", (40, 20), "white").save(photo_path)
            win._ocr_work_results = queue.Queue()

            # _ocr_worker doit pouvoir s'exécuter entièrement sur un thread
            # d'arrière-plan : s'il touchait un widget Tkinter, Tcl lèverait
            # une erreur d'accès concurrent ou le thread resterait bloqué.
            # On simule la reconnaissance elle-même (le vrai Tesseract/PIL
            # n'est pas thread-safe pour son initialisation paresseuse des
            # plugins de formats d'image, ce qui n'a rien à voir avec ce que
            # ce test vérifie). Le ramasse-miettes cyclique est aussi
            # désactivé le temps du thread : une collecte déclenchée pendant
            # l'exécution en parallèle finalise parfois des objets Tcl/Tk
            # depuis le mauvais thread, ce qui plante l'interpréteur — un
            # problème d'environnement de test, sans rapport avec le code
            # vérifié ici.
            gc_was_enabled = gc.isenabled()
            gc.disable()
            try:
                with patch.object(
                    main, "pytesseract",
                    SimpleNamespace(image_to_string=lambda *a, **k: "Texte simulé"),
                    create=True,
                ), patch.object(main, "detect_ocr_rotation", lambda *a, **k: 0):
                    thread = threading.Thread(
                        target=win._ocr_worker, args=([photo_path], "fra", {})
                    )
                    thread.start()
                    thread.join(timeout=15)
            finally:
                if gc_was_enabled:
                    gc.enable()

        self.assertFalse(thread.is_alive(), "_ocr_worker ne doit jamais bloquer indéfiniment")
        results = []
        while True:
            try:
                results.append(win._ocr_work_results.get_nowait())
            except queue.Empty:
                break
        self.assertEqual(results[-1][0], "done")
        chunks, error = results[-1][1]
        self.assertIsInstance(chunks, list)


if __name__ == "__main__":
    unittest.main()
