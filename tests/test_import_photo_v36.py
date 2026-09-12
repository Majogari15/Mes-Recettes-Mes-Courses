import ast
import inspect
import unittest
from pathlib import Path

import main


class ImportPhotoV36Tests(unittest.TestCase):
    def test_constructor_finishes_before_tesseract_detection(self):
        source = inspect.getsource(main.ImportFromPhotoWindow.__init__)
        self.assertNotIn("self._ocr_status = current_tesseract_status()", source)
        self.assertIn("self.after(50, self._refresh_ocr_status)", source)
        self.assertIn("self.extract_button = ttk.Button", source)
        self.assertIn("self.refresh_ocr_button = ttk.Button", source)
        self.assertLess(
            source.index("self.extract_button = ttk.Button"),
            source.index("self.after(50, self._refresh_ocr_status)"),
        )

    def test_tesseract_detection_runs_off_the_tkinter_thread(self):
        source = inspect.getsource(main.ImportFromPhotoWindow._refresh_ocr_status)
        self.assertIn("threading.Thread", source)
        self.assertIn("self._ocr_status_results.put(status)", source)
        poll = inspect.getsource(main.ImportFromPhotoWindow._poll_ocr_status)
        self.assertIn("get_nowait", poll)

    def test_ocr_worker_never_calls_tkinter(self):
        source = inspect.getsource(main.ImportFromPhotoWindow._ocr_worker)
        self.assertNotIn("self.after", source)
        self.assertNotIn("winfo_exists", source)
        self.assertIn('self._ocr_work_results.put(("done"', source)

    def test_success_color_is_defined_palette_color(self):
        source = inspect.getsource(main.ImportFromPhotoWindow._display_ocr_status)
        self.assertIn("COLOR_GREEN", source)
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


if __name__ == "__main__":
    unittest.main()
