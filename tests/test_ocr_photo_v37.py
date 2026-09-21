import tempfile
import tkinter as tk
import types
import unittest
from pathlib import Path
from unittest import mock

import main


class OcrPhotoV37Tests(unittest.TestCase):
    def test_barramundi_fixture_is_structured_and_scaled_once(self):
        source = Path(__file__).with_name(
            "OCR_TEST_Barramundi_en_cro_te_persill_e.txt"
        ).read_text(encoding="utf-8")
        recipe = main.parse_photo_ocr_recipe(source)

        self.assertIn("Barramund", recipe["name"])
        self.assertIn("purée à la ciboulette", recipe["name"])
        self.assertEqual(recipe["default_persons"], 2)
        self.assertEqual(len(recipe["ingredients"]), 10)
        by_name = {item["name"]: item for item in recipe["ingredients"]}
        self.assertEqual(by_name["Pommes de terre"]["quantity"], 250)
        self.assertEqual(by_name["Filet de barramundi"]["quantity"], 1)
        self.assertEqual(by_name["Tomates cerises"]["quantity"], 0.5)
        self.assertIn("Préchauffez le four", recipe["description"])
        self.assertNotIn("Valeurs nutritionnelles", recipe["description"])
        self.assertEqual(recipe["quantity_basis"], "per_person")

    @unittest.skipUnless(main.PIL_AVAILABLE, "Pillow indisponible")
    def test_exif_orientation_is_applied_before_ocr(self):
        image = main.Image.new("RGB", (40, 20), "white")
        image.getexif()[274] = 6
        prepared = main.prepare_image_for_ocr(image, max_dimension=None)
        self.assertEqual(prepared.size, (20, 40))

    @unittest.skipUnless(main.PIL_AVAILABLE, "Pillow indisponible")
    def test_large_smartphone_photo_is_reduced_to_1600_pixels(self):
        image = main.Image.new("RGB", (3000, 4000), "white")
        prepared = main.prepare_image_for_ocr(image)
        self.assertEqual(max(prepared.size), 1600)
        self.assertEqual(prepared.size, (1200, 1600))

    @unittest.skipUnless(main.PIL_AVAILABLE, "Pillow indisponible")
    def test_grid_cells_are_read_row_by_row(self):
        image = main.Image.new("RGB", (300, 200), "white")
        colors = [10, 20, 30, 40, 50, 60]
        for row in range(2):
            for column in range(3):
                value = colors[row * 3 + column]
                for x in range(column * 100, (column + 1) * 100):
                    for y in range(row * 100, (row + 1) * 100):
                        image.putpixel((x, y), (value, value, value))

        def recognize(cell):
            return str(cell.getpixel((cell.width // 2, cell.height // 2))[0])

        result = main.ocr_grid_cells(image, recognize)
        self.assertEqual(result.split("\n\n"), ["10", "20", "30", "40", "50", "60"])

    def test_orientation_detection_requires_confidence(self):
        fake = types.SimpleNamespace(
            Output=types.SimpleNamespace(DICT="dict"),
            image_to_osd=mock.Mock(
                return_value={"rotate": 180, "orientation_conf": 7.5}
            ),
        )
        with mock.patch.object(main, "PYTESSERACT_AVAILABLE", True), mock.patch.object(
            main, "pytesseract", fake, create=True
        ):
            self.assertEqual(main.detect_ocr_rotation(object()), 180)
            fake.image_to_osd.return_value = {
                "rotate": 90,
                "orientation_conf": 1.0,
            }
            self.assertEqual(main.detect_ocr_rotation(object()), 0)

    @unittest.skipUnless(main.PIL_AVAILABLE, "Pillow indisponible")
    def test_photo_window_offers_manual_rotation(self):
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.addCleanup(root.destroy)
        root.withdraw()
        win = main.ImportFromPhotoWindow(root)
        self.addCleanup(win._close_import_window)

        with tempfile.TemporaryDirectory() as tmp:
            photo_path = str(Path(tmp) / "photo.jpg")
            main.Image.new("RGB", (40, 20), "white").save(photo_path)
            win.photo_paths = [photo_path]
            win._refresh_photo_list()
            win.photo_listbox.selection_set(0)

            self.assertEqual(win.photo_rotations.get(photo_path, 0), 0)
            win._rotate_selected_photo(90)
            self.assertEqual(win.photo_rotations[photo_path], 90)
            win._rotate_selected_photo(90)
            self.assertEqual(win.photo_rotations[photo_path], 180)
            # Le bouton "rotation gauche" appelle _rotate_selected_photo(-90) :
            # le modulo doit rester dans [0, 360), jamais négatif.
            win._rotate_selected_photo(-90)
            win._rotate_selected_photo(-90)
            win._rotate_selected_photo(-90)
            self.assertEqual(win.photo_rotations[photo_path], 270)

    def test_new_labels_exist_in_all_languages(self):
        for key in (
            "importphoto_rotate_left_button",
            "importphoto_rotate_right_button",
        ):
            self.assertIn(key, main.FRENCH_STRINGS)
            for language in ("en", "es", "de"):
                self.assertIn(key, main.TRANSLATIONS[language])


if __name__ == "__main__":
    unittest.main()
