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
        idx, card = win._grid_items[0]
        before = (str(card.cget("highlightbackground")), card.cget("highlightthickness"))

        # event_generate("<Enter>") exige un vrai déplacement de la souris
        # suivi par le serveur X, indisponible sous Xvfb sans gestionnaire
        # de fenêtres : on appelle directement le vrai gestionnaire lié au
        # survol, comme le ferait le passage réel du curseur.
        win._on_card_hover_enter(idx, card)
        after_enter = (str(card.cget("highlightbackground")), card.cget("highlightthickness"))

        win._on_card_hover_leave(idx, card)
        after_leave = (str(card.cget("highlightbackground")), card.cget("highlightthickness"))

        self.assertNotEqual(before, after_enter)
        self.assertEqual(before, after_leave)


class RecipeCardKeyboardNavigationTests(AppWindowTestBase):
    """Les cartes de recettes (vue grille, par défaut) n'étaient atteignables
    qu'à la souris — aucun moyen d'y accéder ni de les ouvrir au clavier,
    contrairement à la vue liste (Treeview). Vérifie que Tab, les flèches et
    Entrée/Espace fonctionnent réellement sur de vrais widgets."""

    def setUp(self):
        super().setUp()
        main.save_recipes([
            {
                "id": f"r{i}", "name": f"Recette {i}", "default_persons": 4,
                "category": "Plat", "difficulty": "Facile", "images": [],
                "ingredients": [], "steps": [], "tags": [],
            }
            for i in range(6)
        ])
        self.app.refresh_recipes()

    def test_recipe_card_is_reachable_by_tab(self):
        win = main.ManageRecipesWindow(self.app)
        self.addCleanup(win.destroy)
        _idx, card = win._grid_items[0]
        self.assertEqual(str(card.cget("takefocus")), "1")

    def test_keyboard_focus_shows_the_same_border_as_mouse_hover(self):
        # focus_set()/focus_get() dépendent d'un vrai focus clavier accordé
        # par le système d'exploitation, absent de façon fiable en CI
        # headless (Xvfb sans gestionnaire de fenêtres sous Linux ; confirmé
        # aussi absent sous Windows sans session de premier plan réelle,
        # où focus_set() n'aboutit jamais et focus_get() renvoie None) : on
        # appelle directement le gestionnaire lié à <FocusIn>/<FocusOut>,
        # comme le ferait un vrai changement de focus clavier.
        win = main.ManageRecipesWindow(self.app)
        self.addCleanup(win.destroy)
        idx, card = win._grid_items[0]
        self.assertTrue(card.bind("<FocusIn>"))
        self.assertTrue(card.bind("<FocusOut>"))
        before = (str(card.cget("highlightbackground")), str(card.cget("highlightcolor")))

        win._on_card_hover_enter(idx, card)
        during = (str(card.cget("highlightbackground")), str(card.cget("highlightcolor")))

        win._on_card_hover_leave(idx, card)
        after = (str(card.cget("highlightbackground")), str(card.cget("highlightcolor")))

        self.assertNotEqual(before, during)
        # highlightcolor (utilisé par Tk pour le focus clavier réel, pas
        # highlightbackground qui sert au survol souris) doit lui aussi
        # changer : c'est ce qui rend le focus clavier visible.
        self.assertNotEqual(before[1], during[1])
        self.assertEqual(before, after)

    def test_arrow_right_then_left_moves_focus_between_adjacent_cards(self):
        # win.focus_get() dépend du même vrai focus OS, non fiable en CI
        # headless (voir plus haut) : on vérifie directement quelle carte
        # reçoit l'appel focus_set(), comme le ferait un déplacement réel.
        win = main.ManageRecipesWindow(self.app)
        self.addCleanup(win.destroy)
        self.assertGreaterEqual(len(win._grid_items), 2)
        first_idx, first_card = win._grid_items[0]
        second_idx, second_card = win._grid_items[1]

        focused = []
        with patch.object(second_card, "focus_set", lambda: focused.append(second_card)):
            win._move_grid_focus(first_idx, delta_col=1)
        self.assertEqual(focused, [second_card])

        focused.clear()
        with patch.object(first_card, "focus_set", lambda: focused.append(first_card)):
            win._move_grid_focus(second_idx, delta_col=-1)
        self.assertEqual(focused, [first_card])

    def test_arrow_left_from_the_first_card_does_not_move_focus_away(self):
        win = main.ManageRecipesWindow(self.app)
        self.addCleanup(win.destroy)
        first_idx, first_card = win._grid_items[0]

        called = []
        with patch.object(first_card, "focus_set", lambda: called.append(True)):
            win._move_grid_focus(first_idx, delta_col=-1)

        self.assertEqual(called, [])

    def test_selected_card_keeps_its_border_after_the_mouse_or_focus_leaves(self):
        win = main.ManageRecipesWindow(self.app)
        self.addCleanup(win.destroy)
        idx, card = win._grid_items[0]
        win._select_grid_index(idx)
        selected = (str(card.cget("highlightbackground")), card.cget("highlightthickness"))

        win._on_card_hover_leave(idx, card)

        self.assertEqual(
            (str(card.cget("highlightbackground")), card.cget("highlightthickness")),
            selected,
        )

    def test_enter_key_opens_the_focused_card_recipe(self):
        # event_generate("<Return>") pour une touche exige un vrai focus
        # clavier X11 (routage), indisponible sous Xvfb sans gestionnaire de
        # fenêtres — on appelle directement le vrai gestionnaire lié à la
        # touche, comme le ferait une pression réelle sur Entrée/Espace.
        win = main.ManageRecipesWindow(self.app)
        self.addCleanup(win.destroy)
        idx, card = win._grid_items[0]
        self.assertTrue(card.bind("<Return>"))
        self.assertTrue(card.bind("<space>"))

        opened = []
        with patch.object(win, "_open_index", lambda i: opened.append(i)):
            win._on_card_activate(idx)

        self.assertEqual(opened, [idx])


if __name__ == "__main__":
    unittest.main()
