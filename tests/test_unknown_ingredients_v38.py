import inspect
import unittest

import main


class UnknownIngredientsV38Tests(unittest.TestCase):
    def test_close_suggestions_put_ail_first_for_gousse_dail(self):
        ranked = main.rank_close_ingredients(
            "Gousse d'ail", ["Tomate", "Ail", "Échalote", "Poivre"]
        )
        self.assertEqual(ranked[0][1], "Ail")

    def test_plural_variant_has_very_high_score(self):
        ranked = main.rank_close_ingredients("Tomates", ["Oignon", "Tomate"])
        self.assertEqual(ranked[0][1], "Tomate")
        self.assertGreaterEqual(ranked[0][0], 0.98)

    def test_save_opens_resolution_before_strict_validation(self):
        source = inspect.getsource(main.RecipeFormWindow.save_recipe)
        self.assertIn("_resolve_unknown_ingredients_before_save", source)
        self.assertLess(
            source.index("_resolve_unknown_ingredients_before_save"),
            source.index("ingredients = []"),
        )

    def test_dialog_offers_create_and_replace(self):
        source = inspect.getsource(main.UnknownIngredientsDialog)
        self.assertIn('value="create"', source)
        self.assertIn('value="replace"', source)
        self.assertIn("rank_close_ingredients", source)

    def test_dialog_uses_its_widget_to_measure_the_screen(self):
        source = inspect.getsource(main.UnknownIngredientsDialog.__init__)
        self.assertIn("get_usable_screen_height(self)", source)
        self.assertNotIn("get_usable_screen_height()", source)

    def test_dialog_labels_exist_in_all_languages(self):
        keys = (
            "common_cancel",
            "unknowningredients_title",
            "unknowningredients_heading",
            "unknowningredients_intro",
            "unknowningredients_create",
            "unknowningredients_replace",
            "unknowningredients_continue",
            "unknowningredients_replacement_required",
        )
        for key in keys:
            self.assertIn(key, main.FRENCH_STRINGS)
            for language in ("en", "es", "de"):
                self.assertIn(key, main.TRANSLATIONS[language])
        self.assertEqual(main.FRENCH_STRINGS["common_cancel"], "Annuler")

    def test_replacement_values_are_alphabetical_and_searchable(self):
        values = ["Tomate", "Échalote", "ail", "Abricot"]
        self.assertEqual(
            main.filter_sorted_ingredient_values(values),
            ["Abricot", "ail", "Échalote", "Tomate"],
        )
        self.assertEqual(main.filter_sorted_ingredient_values(values, "to"), ["Tomate"])
        self.assertEqual(main.filter_sorted_ingredient_values(values, "lote"), ["Échalote"])

    def test_replacement_uses_same_live_suggestion_pattern_as_recipe_form(self):
        source = inspect.getsource(main.UnknownIngredientsDialog)
        self.assertIn("choice = ttk.Entry", source)
        self.assertIn('"<KeyRelease>"', source)
        self.assertIn("_show_replacement_suggestions", source)
        self.assertIn("finalize_suggestion_popup", source)
        self.assertIn("filter_sorted_ingredient_values", source)
        self.assertNotIn("choice = ttk.Combobox", source)

    def test_prefilled_suggestion_is_selected_for_direct_retyping(self):
        source = inspect.getsource(main.UnknownIngredientsDialog._on_replacement_focus_in)
        self.assertIn("select_range(0, tk.END)", source)


if __name__ == "__main__":
    unittest.main()
