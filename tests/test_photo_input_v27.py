
import os
import tempfile
import unittest
from pathlib import Path
import main

class PhotoInputV27Tests(unittest.TestCase):
    def test_normalise_photo_paths_accepts_valid_images_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "photo é test.png"
            p.write_bytes(b"fake")
            class Dummy:
                pass
            obj = Dummy()
            method = main.RecipeFormWindow._normalise_dropped_photo_paths
            result = method(obj, [str(p), str(p)])
            self.assertEqual(len(result), 1)
            self.assertEqual(os.path.abspath(str(p)), result[0])

    def test_normalise_photo_paths_rejects_non_images(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "texte.txt"
            p.write_text("x", encoding="utf-8")
            class Dummy:
                pass
            obj = Dummy()
            method = main.RecipeFormWindow._normalise_dropped_photo_paths
            self.assertEqual(method(obj, [str(p)]), [])

if __name__ == "__main__":
    unittest.main()
