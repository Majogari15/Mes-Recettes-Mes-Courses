import tkinter as tk
import unittest
from unittest.mock import patch

import main
from test_regressions import TempDataMixin


class FuzzySearchRecipesTests(unittest.TestCase):
    def test_fuzzy_search_finds_recipe_despite_typo(self):
        recipes = [
            {"name": "Pâtes carbonara", "tags": []},
            {"name": "Salade César", "tags": []},
        ]
        results = main.fuzzy_search_recipes("carbonra", recipes)
        self.assertTrue(results)
        self.assertEqual(results[0]["name"], "Pâtes carbonara")

    def test_fuzzy_search_returns_empty_for_empty_query(self):
        self.assertEqual(main.fuzzy_search_recipes("", [{"name": "Test", "tags": []}]), [])

    def test_fuzzy_search_ignores_unrelated_recipes(self):
        recipes = [{"name": "Tarte aux pommes", "tags": []}]
        self.assertEqual(main.fuzzy_search_recipes("carbonara", recipes), [])

    def test_fuzzy_search_matches_on_tags_too(self):
        recipes = [{"name": "Plat mystère", "tags": ["carbonara"]}]
        results = main.fuzzy_search_recipes("carbonra", recipes)
        self.assertEqual(results[0]["name"], "Plat mystère")


class MissingRecipeIngredientsTests(unittest.TestCase):
    def test_missing_recipe_ingredients_filters_pantry_keys(self):
        recipe = {"ingredients": [{"name": "Farine"}, {"name": "Sucre"}, {"name": "Oeuf"}]}
        pantry_keys = {main.ingredient_sort_key("Farine")}
        missing = main.missing_recipe_ingredients(recipe, pantry_keys)
        self.assertEqual(missing, ["Sucre", "Oeuf"])

    def test_missing_recipe_ingredients_empty_when_all_available(self):
        recipe = {"ingredients": [{"name": "Farine"}]}
        pantry_keys = {main.ingredient_sort_key("Farine")}
        self.assertEqual(main.missing_recipe_ingredients(recipe, pantry_keys), [])


class PrimaryButtonStyleTests(unittest.TestCase):
    def test_primary_button_is_visually_distinct_from_default_button(self):
        # "Primary.TButton" était utilisé partout dans l'app sans jamais
        # être défini (donc identique à un TButton normal). Le texte gras
        # (et un padding plus généreux) lui donne enfin une vraie hiérarchie
        # visuelle. Les couleurs restent volontairement identiques à
        # TButton : une combinaison de couleurs différente entre les deux
        # styles s'est avérée provoquer un blocage de l'interface au
        # changement de thème (voir configure_app_style).
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.addCleanup(root.destroy)
        root.withdraw()
        style = main.configure_app_style(root)

        self.assertNotIn("bold", str(style.lookup("TButton", "font")))
        self.assertIn("bold", str(style.lookup("Primary.TButton", "font")))
        self.assertNotEqual(
            style.lookup("Primary.TButton", "padding"),
            style.lookup("TButton", "padding"),
        )


class AppWindowTestBase(TempDataMixin, unittest.TestCase):
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


class QuickSearchFuzzyFallbackTests(AppWindowTestBase):
    def setUp(self):
        super().setUp()
        main.save_recipes([{
            "id": "r1", "name": "Pâtes carbonara", "default_persons": 4,
            "category": "Plat", "difficulty": "Facile", "images": [],
            "ingredients": [], "steps": [], "tags": [],
        }])
        self.app.refresh_recipes()

    def test_typo_falls_back_to_fuzzy_suggestion_with_hint_shown(self):
        win = main.QuickSearchWindow(self.app)
        self.addCleanup(win.destroy)
        win.search_entry.delete(0, tk.END)
        win.search_entry.insert(0, "carbonra")
        win._populate()

        self.assertIn("Pâtes carbonara", win.matched_names)
        self.assertNotEqual(win.fuzzy_hint_label.cget("text"), "")

    def test_exact_match_does_not_show_fuzzy_hint(self):
        win = main.QuickSearchWindow(self.app)
        self.addCleanup(win.destroy)
        win.search_entry.delete(0, tk.END)
        win.search_entry.insert(0, "carbonara")
        win._populate()

        self.assertIn("Pâtes carbonara", win.matched_names)
        self.assertEqual(win.fuzzy_hint_label.cget("text"), "")

    def test_gibberish_query_shows_no_results_without_fuzzy_hint(self):
        win = main.QuickSearchWindow(self.app)
        self.addCleanup(win.destroy)
        win.search_entry.delete(0, tk.END)
        win.search_entry.insert(0, "xyzxyzxyz")
        win._populate()

        self.assertEqual(win.matched_names, [])
        self.assertEqual(win.fuzzy_hint_label.cget("text"), "")


class RecipeCardHoverTests(AppWindowTestBase):
    def setUp(self):
        super().setUp()
        main.save_recipes([{
            "id": "r1", "name": "Ratatouille", "default_persons": 4,
            "category": "Plat", "difficulty": "Facile", "images": [],
            "ingredients": [], "steps": [], "tags": [],
        }])
        self.app.refresh_recipes()

    def test_hovering_a_recipe_card_thickens_its_border(self):
        win = main.ManageRecipesWindow(self.app)
        self.addCleanup(win.destroy)
        self.assertEqual(win.view_mode, "grid")
        self.assertTrue(win._grid_items)
        _idx, card = win._grid_items[0]
        before = (str(card.cget("highlightbackground")), card.cget("highlightthickness"))

        # event_generate("<Enter>") exige un vrai déplacement de la souris
        # suivi par le serveur X, indisponible sous Xvfb sans gestionnaire
        # de fenêtres : on appelle directement le vrai gestionnaire lié au
        # survol, comme le ferait le passage réel du curseur.
        win._on_card_hover_enter(card)
        after_enter = (str(card.cget("highlightbackground")), card.cget("highlightthickness"))

        win._on_card_hover_leave(card)
        after_leave = (str(card.cget("highlightbackground")), card.cget("highlightthickness"))

        self.assertNotEqual(before, after_enter)
        self.assertEqual(before, after_leave)


if __name__ == "__main__":
    unittest.main()
