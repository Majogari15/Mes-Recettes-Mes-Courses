import unittest

import main


class NullableIngredientQuantityV57Tests(unittest.TestCase):
    def test_null_quantity_is_preserved_by_recipe_validation(self):
        recipe = {
            "name": "Recette mobile",
            "default_persons": 2,
            "ingredients": [
                {"name": "Sel", "quantity": None, "unit": "pièce"},
                {"name": "Farine", "quantity": 100, "unit": "g"},
            ],
        }
        normalized = main.validate_recipes_payload([recipe])[0]
        self.assertIsNone(normalized["ingredients"][0]["quantity"])
        self.assertEqual(normalized["ingredients"][1]["quantity"], 100)

    def test_null_quantity_does_not_break_scaling_or_nutrition(self):
        ingredient = {"name": "Poivre", "quantity": None, "unit": "pièce"}
        self.assertIsNone(main.ingredient_quantity_for_persons(ingredient, 8))
        recipe = {"name": "Recette", "ingredients": [ingredient]}
        totals, known, total = main.compute_recipe_nutrition(recipe, 8)
        self.assertEqual(totals["kcal"], 0.0)
        self.assertEqual(known, 0)
        self.assertEqual(total, 1)

    def test_invalid_non_empty_quantities_are_still_rejected(self):
        for value in (-1, "abc", "NaN", "Infinity"):
            recipe = {
                "name": "Recette invalide",
                "ingredients": [{"name": "Sel", "quantity": value, "unit": "g"}],
            }
            with self.assertRaises(ValueError):
                main.validate_recipes_payload([recipe])


if __name__ == "__main__":
    unittest.main()
