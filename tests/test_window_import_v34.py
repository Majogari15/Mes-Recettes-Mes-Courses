import inspect
import unittest
from unittest import mock

import main


class WindowAndImportV34Tests(unittest.TestCase):
    def test_import_quantity_is_scaled_for_recipe_persons(self):
        ingredient = {"name": "Haricots", "quantity": 75, "unit": "Gr"}
        self.assertEqual(main.ingredient_quantity_for_persons(ingredient, 8), 600)

    def test_scaling_rejects_invalid_person_count(self):
        ingredient = {"name": "Haricots", "quantity": 75, "unit": "Gr"}
        with self.assertRaises(ValueError):
            main.ingredient_quantity_for_persons(ingredient, 0)

    def test_url_import_round_trip_keeps_per_person_storage_and_total_display(self):
        page = b'''<script type="application/ld+json">{
            "@type": "Recipe",
            "name": "Test huit personnes",
            "recipeYield": "8 personnes",
            "recipeIngredient": ["600 g de haricots"]
        }</script>'''

        class Headers(dict):
            def get_content_charset(self):
                return "utf-8"

        class Response:
            headers = Headers()

            def __init__(self):
                self.offset = 0

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, size=-1):
                if self.offset >= len(page):
                    return b""
                end = len(page) if size < 0 else min(len(page), self.offset + size)
                chunk = page[self.offset:end]
                self.offset = end
                return chunk

        with mock.patch("main.urllib.request.urlopen", return_value=Response()):
            recipe = main.fetch_recipe_from_url("https://example.test/recette")

        self.assertEqual(recipe["default_persons"], 8)
        self.assertEqual(recipe["quantity_basis"], "per_person")
        self.assertEqual(recipe["ingredients"][0]["quantity"], 75)
        self.assertEqual(
            main.ingredient_quantity_for_persons(recipe["ingredients"][0], 8),
            600,
        )

    def test_window_fitting_does_not_cap_native_maximum_size(self):
        fit_source = inspect.getsource(main.fit_window_to_workarea)
        ensure_source = inspect.getsource(main.ensure_window_visible_and_fitted)
        self.assertNotIn(".maxsize(", fit_source)
        self.assertNotIn(".maxsize(", ensure_source)
        self.assertIn('state()).lower() == "zoomed"', ensure_source)


if __name__ == "__main__":
    unittest.main()
