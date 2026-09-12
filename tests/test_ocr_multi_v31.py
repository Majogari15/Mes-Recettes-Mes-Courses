
import inspect
import unittest
import main

class OcrMultiV31Tests(unittest.TestCase):
    def test_tesseract_detection_exists(self):
        self.assertTrue(callable(main.detect_tesseract))
        status = main.detect_tesseract("fra")
        self.assertIn("languages", status)
        self.assertIn("ready", status)

    def test_multi_photo_import_keeps_all_sources(self):
        src = inspect.getsource(main.ImportFromPhotoWindow.create_recipe)
        self.assertIn('"image_sources": list(self.photo_paths)', src)

    def test_ocr_uses_snapshot_and_order(self):
        src = inspect.getsource(main.ImportFromPhotoWindow.extract_text)
        self.assertIn("paths_snapshot = list(self.photo_paths)", src)
        worker = inspect.getsource(main.ImportFromPhotoWindow._ocr_worker)
        self.assertIn("for idx, path in enumerate(paths, 1)", worker)

    def test_multi_photo_ui_has_reorder_controls(self):
        src = inspect.getsource(main.ImportFromPhotoWindow)
        self.assertIn("_move_photo", src)
        self.assertIn("_remove_selected_photo", src)
        self.assertIn("_clear_photos", src)

if __name__ == "__main__":
    unittest.main()
