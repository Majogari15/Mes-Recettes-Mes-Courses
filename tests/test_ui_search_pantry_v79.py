import datetime
import tkinter as tk
from tkinter import ttk
import unittest
from pathlib import Path
from types import SimpleNamespace
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


class CommandPaletteTests(AppWindowTestBase):
    """Ctrl+K (QuickSearchWindow) étendu en Command Palette : les actions
    de l'appli (pages, bascules Paramètres) doivent apparaître à côté des
    recettes, filtrables et activables comme elles."""

    def setUp(self):
        super().setUp()
        main.save_recipes([{
            "id": "r1", "name": "Pâtes carbonara", "default_persons": 4,
            "category": "Plat", "difficulty": "Facile", "images": [],
            "ingredients": [], "steps": [], "tags": [],
        }])
        self.app.refresh_recipes()

    def test_empty_query_lists_every_action_alongside_recipes(self):
        win = main.QuickSearchWindow(self.app)
        self.addCleanup(win.destroy)

        labels = [label for label, _command in win.matched_actions]
        self.assertIn(main.t("home_primary_recipes"), labels)
        self.assertEqual(len(win.matched_actions), len(self.app.get_command_palette_actions()))
        self.assertIn("Pâtes carbonara", win.matched_names)
        # Les actions sont listées avant les recettes dans la liste combinée.
        first_row = win.listbox.get(0)
        self.assertTrue(first_row.startswith(win.ACTION_PREFIX))

    def test_query_filters_actions_by_label_substring(self):
        win = main.QuickSearchWindow(self.app)
        self.addCleanup(win.destroy)
        win.search_entry.delete(0, tk.END)
        win.search_entry.insert(0, "sombre")
        win._populate()

        labels = [label for label, _command in win.matched_actions]
        self.assertEqual(labels, [main.t("home_dark_theme")])
        self.assertEqual(win.matched_names, [])  # aucune recette ne contient "sombre"

    def test_selecting_an_action_runs_its_command_and_closes_the_palette(self):
        win = main.QuickSearchWindow(self.app)
        self.addCleanup(win.destroy)
        win.search_entry.delete(0, tk.END)
        win.search_entry.insert(0, "sombre")
        win._populate()
        self.assertFalse(self.app.dark_mode)

        win.listbox.selection_set(0)
        win._open_selected()

        self.assertTrue(self.app.dark_mode)  # toggle_dark_mode() a bien été appelé
        self.assertFalse(win.winfo_exists())

    def test_enter_with_no_selection_runs_the_first_combined_result(self):
        win = main.QuickSearchWindow(self.app)
        win.search_entry.delete(0, tk.END)
        win.search_entry.insert(0, "sombre")
        win._populate()

        win._open_first_or_selected()

        self.assertTrue(self.app.dark_mode)
        self.assertFalse(win.winfo_exists())


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

    def test_single_click_on_a_recipe_card_opens_it_directly(self):
        # Auparavant il fallait double-cliquer une carte pour l'ouvrir (un
        # seul clic ne faisait que la sélectionner) — un seul clic doit
        # maintenant à la fois sélectionner (bordure d'accent) ET ouvrir la
        # recette, sans avoir à double-cliquer.
        win = main.ManageRecipesWindow(self.app)
        self.addCleanup(win.destroy)
        idx, card = win._grid_items[0]
        self.assertTrue(card.bind("<Button-1>"))
        self.assertFalse(card.bind("<Double-Button-1>"))

        opened = []
        with patch.object(win, "_open_index", lambda i: opened.append(i)):
            win._select_and_open_grid_index(idx)

        self.assertEqual(opened, [idx])
        self.assertEqual(win._context_index, idx)
        self.assertEqual(str(card.cget("highlightbackground")), main.COLOR_ACCENT)

    def test_single_click_on_a_list_row_opens_it_directly(self):
        # Même correction que pour la vue grille, côté vue liste (Treeview) :
        # un seul clic sur une ligne doit l'ouvrir, sans double-cliquer.
        win = main.ManageRecipesWindow(self.app)
        self.addCleanup(win.destroy)
        win._toggle_view()
        # bbox() ne renvoie une géométrie qu'une fois le nouveau Treeview
        # réellement dessiné : update_idletasks()/update() forcent ce cycle
        # de layout (sans eux, bbox() renvoie '' de façon fiable sur les
        # runners Windows CI, alors que ça passe sans sur une machine avec
        # un vrai affichage déjà à jour par d'autres évènements).
        win.update_idletasks()
        win.update()
        self.assertEqual(win.view_mode, "list")
        self.assertTrue(win.tree.bind("<Button-1>"))
        self.assertFalse(win.tree.bind("<Double-Button-1>"))
        first_row = win.tree.get_children()[0]
        bbox = win.tree.bbox(first_row)
        self.assertTrue(bbox, "la première ligne doit être visible pour ce test")
        fake_event = SimpleNamespace(y=bbox[1] + bbox[3] // 2)

        opened = []
        with patch.object(win, "_open_index", lambda i: opened.append(i)):
            win._on_tree_row_click(fake_event)

        self.assertEqual(opened, [int(first_row)])
        self.assertEqual(win.tree.selection(), (first_row,))


def _find_widget(root, predicate):
    """Cherche récursivement le premier widget descendant vérifiant predicate."""
    for child in root.winfo_children():
        try:
            if predicate(child):
                return child
        except tk.TclError:
            pass
        found = _find_widget(child, predicate)
        if found is not None:
            return found
    return None


class HomeAccessibilityTests(AppWindowTestBase):
    """La page d'accueil (4 cartes de navigation principales, bandeaux
    d'alerte stock bas/péremption/liste d'envies) n'était accessible qu'à
    la souris, contrairement aux cartes de recettes déjà corrigées."""

    def setUp(self):
        super().setUp()
        # AppWindowTestBase masque self.app (withdraw()) : une fenêtre non
        # mappée ne délivre aucun évènement synthétique, même <FocusIn>
        # (vérifié : sans ce deiconify, les callbacks ne sont simplement
        # jamais appelés — constaté, pas une supposition).
        self.app.deiconify()
        self.app.update()

    def _find_home_card(self, title_text):
        title_lbl = _find_widget(
            self.app, lambda w: isinstance(w, tk.Label) and w.cget("text") == title_text
        )
        self.assertIsNotNone(title_lbl, f"carte d'accueil introuvable : {title_text}")
        return title_lbl.master

    def test_primary_home_card_is_reachable_by_tab_and_has_keyboard_bindings(self):
        # event_generate("<Button-1>") s'est avéré bloquer indéfiniment sur
        # cette carte précise (contrairement à la même simulation qui
        # fonctionne sur les étoiles de note d'un formulaire) — cause non
        # identifiée avec certitude, probablement liée à la géométrie de la
        # fenêtre principale ; on vérifie donc le câblage clavier
        # structurellement (présence des liaisons, sur la même variable
        # "command" que le clic — visible directement dans le code) plutôt
        # que de simuler un clic à risque de blocage.
        card = self._find_home_card(main.t("home_primary_recipes"))
        self.assertEqual(str(card.cget("takefocus")), "1")
        self.assertTrue(card.bind("<Return>"))
        self.assertTrue(card.bind("<space>"))

    def test_primary_home_card_shows_focus_indicator(self):
        card = self._find_home_card(main.t("home_primary_shopping"))
        before = (str(card.cget("highlightbackground")), card.cget("highlightthickness"))

        card.event_generate("<FocusIn>")
        during = (str(card.cget("highlightbackground")), card.cget("highlightthickness"))
        card.event_generate("<FocusOut>")
        after = (str(card.cget("highlightbackground")), card.cget("highlightthickness"))

        self.assertNotEqual(before, during)
        self.assertEqual(before, after)

    def test_low_stock_alert_row_is_reachable_and_wired(self):
        main.save_pantry({"farine": {"name": "Farine", "quantity": 0, "unit": "g", "threshold": 200}})
        # Une 2e instance main.App() réelle en parallèle de self.app casse
        # sur un conflit d'images Tk préexistant ("image pyimageN n'existe
        # pas"), sans rapport avec l'accessibilité : on reconstruit plutôt
        # self.app, exactement comme le fait déjà set_language()/
        # toggle_dark_mode() pour refléter un changement de données.
        for child in list(self.app.winfo_children()):
            if not isinstance(child, tk.Toplevel):
                child.destroy()
        self.app._build_home_ui()
        self.app.update()

        row = _find_widget(
            self.app,
            lambda w: isinstance(w, tk.Label) and str(w.cget("takefocus")) == "1"
                      and "Farine" in str(w.cget("text")),
        )
        self.assertIsNotNone(row, "bandeau d'alerte stock bas introuvable")
        self.assertTrue(row.bind("<Return>"))

        opened = []
        with patch.object(self.app, "_open_low_stock_to_cart", lambda items: opened.append(items)):
            row.event_generate("<Button-1>")
        self.assertEqual(len(opened), 1)


class RecipeFormRatingStarsAccessibilityTests(AppWindowTestBase):
    def setUp(self):
        super().setUp()
        self.form = main.RecipeFormWindow(self.app)
        self.addCleanup(self.form.destroy)

    def test_rating_stars_are_reachable_by_tab(self):
        for star in self.form.rating_star_labels:
            self.assertEqual(str(star.cget("takefocus")), "1")

    def test_rating_star_return_key_is_wired_to_the_same_action_as_a_click(self):
        third_star = self.form.rating_star_labels[2]
        self.assertTrue(third_star.bind("<Return>"))
        self.assertTrue(third_star.bind("<space>"))

        third_star.event_generate("<Button-1>")
        self.assertEqual(self.form.rating_value, 3)

    def test_rating_star_shows_focus_indicator(self):
        star = self.form.rating_star_labels[0]
        self.assertEqual(str(star.cget("style")), "")

        star.event_generate("<FocusIn>")
        self.assertEqual(str(star.cget("style")), "RatingStarFocus.TLabel")

        star.event_generate("<FocusOut>")
        self.assertEqual(str(star.cget("style")), "TLabel")


class ShoppingRayonOrderTests(AppWindowTestBase):
    def _grouped(self):
        recipe = {"id": "r1", "name": "Mix", "default_persons": 1, "ingredients": [
            {"name": "Tomate", "quantity": 1, "unit": "pièce"},
            {"name": "Lait", "quantity": 10, "unit": "cl"},
            {"name": "Farine", "quantity": 100, "unit": "Gr"},
        ]}
        return main.compute_grouped_totals([(recipe, 1)])

    def test_saved_rayon_order_drives_grouping_and_ignores_unknown_values(self):
        main.set_rayon_order(["Épicerie", "Inconnu", "Crèmerie"])
        order = main.get_rayon_order()
        self.assertEqual(order[:2], ["Épicerie", "Crèmerie"])
        self.assertEqual(sorted(order), sorted(main.RAYON_ORDER))
        rayons = [rayon for rayon, _items in self._grouped()]
        # Farine = Boulangerie & Pâtisserie : pas d'Épicerie dans cette liste,
        # Crèmerie passe donc en tête, le reste suit l'ordre par défaut.
        self.assertEqual(rayons, ["Crèmerie", "Fruits & Légumes", "Boulangerie & Pâtisserie"])

    def test_checklist_move_button_reorders_and_remembers(self):
        win = main.ShoppingChecklistWindow(self.app, self._grouped())
        self.addCleanup(win.destroy)
        win.update_idletasks()
        first_rayon, first_group = win.rayon_frames[0]
        win.checks[0][0].set(True)
        win._move_rayon(first_group, 1)
        self.assertEqual(win.rayon_frames[1][0], first_rayon)
        self.assertTrue(win.checks[0][0].get())
        self.assertEqual(main.get_rayon_order().index(first_rayon), 1)
        # Bout de liste : sans effet.
        win._move_rayon(win.rayon_frames[0][1], -1)
        self.assertEqual(win.rayon_frames[1][0], first_rayon)

    def test_checklist_drag_reorders_on_release(self):
        win = main.ShoppingChecklistWindow(self.app, self._grouped())
        self.addCleanup(win.destroy)
        win.deiconify()
        win.update_idletasks()
        win.update()
        dragged_rayon, dragged = win.rayon_frames[0]
        _last_rayon, last = win.rayon_frames[-1]
        win._on_rayon_drag_start(None, dragged)
        y = last.winfo_rooty() + last.winfo_height() // 2
        win._on_rayon_drag_motion(SimpleNamespace(y_root=y))
        win._on_rayon_drag_release(None)
        self.assertEqual(win.rayon_frames[-1][0], dragged_rayon)
        self.assertEqual(
            [r for r in main.get_rayon_order() if r in {r2 for r2, _ in win.rayon_frames}],
            [r for r, _ in win.rayon_frames],
        )


class PantryManualSortTests(AppWindowTestBase):
    def setUp(self):
        super().setUp()
        main.save_pantry({
            "farine": {"name": "Farine", "quantity": 1, "unit": "Kilo", "threshold": None},
            "lait": {"name": "Lait", "quantity": 1, "unit": "L", "threshold": None},
            "sucre": {"name": "Sucre", "quantity": 1, "unit": "Kilo", "threshold": None},
        })
        self.win = main.PantryWindow(self.app)
        self.addCleanup(self.win.destroy)
        self.win.sort_combo.set(main.t("pantry_sort_manual"))
        self.win._populate()

    def _names(self):
        return [self.win._entry_by_iid[iid]["name"] for iid in self.win.tree.get_children()]

    def test_move_buttons_reorder_and_persist_across_reopen(self):
        self.assertEqual(self._names(), ["Farine", "Lait", "Sucre"])
        sucre = self.win.tree.get_children()[2]
        self.win.tree.selection_set(sucre)
        self.win._move_selected(-1)
        self.win._move_selected(-1)
        self.assertEqual(self._names(), ["Sucre", "Farine", "Lait"])
        self.win._populate()
        self.assertEqual(self._names(), ["Sucre", "Farine", "Lait"])

    def test_buttons_disabled_outside_manual_sort(self):
        self.win.sort_combo.set(main.t("pantry_sort_name"))
        self.win._populate()
        self.assertTrue(self.win.move_up_button.instate(["disabled"]))
        self.win.tree.selection_set(self.win.tree.get_children()[2])
        self.win._move_selected(-1)
        self.assertEqual(main.get_pantry_order(), [])

    def test_drag_reorders_rows(self):
        self.win.deiconify()
        self.win.update_idletasks()
        self.win.update()
        first, _second, third = self.win.tree.get_children()
        y_first = self.win.tree.bbox(first)[1] + 2
        y_third = self.win.tree.bbox(third)[1] + 2
        self.win._on_tree_press(SimpleNamespace(y=y_first))
        self.win._on_tree_drag(SimpleNamespace(y=y_third))
        self.win._on_tree_release(None)
        self.assertEqual(self._names(), ["Lait", "Sucre", "Farine"])
        self.assertEqual(main.get_pantry_order(), ["lait", "sucre", "farine"])

    def test_reorder_in_filtered_view_keeps_hidden_items_in_place(self):
        main.set_pantry_order(["farine", "lait", "sucre"])
        self.win.search_var.set("r")  # farine + sucre (lait masqué)
        self.win._populate()
        self.assertEqual(self._names(), ["Farine", "Sucre"])
        self.win.tree.selection_set(self.win.tree.get_children()[1])
        self.win._move_selected(-1)
        self.assertEqual(main.get_pantry_order(), ["sucre", "lait", "farine"])


class ExpirationDateOcrTests(AppWindowTestBase):
    TODAY = datetime.date(2026, 10, 3)

    def test_keyword_beats_earlier_manufacturing_date(self):
        text = "Fabriqué le 01/09/2026\nLot 4521\nÀ consommer de préférence avant le 15.03.2027"
        self.assertEqual(main.extract_expiration_date_from_ocr_text(text, self.TODAY),
                         datetime.date(2027, 3, 15))

    def test_formats_iso_two_digit_year_and_invalid_dates(self):
        extract = main.extract_expiration_date_from_ocr_text
        self.assertEqual(extract("MHD 2027-01-31", self.TODAY), datetime.date(2027, 1, 31))
        self.assertEqual(extract("best before 05/11/26", self.TODAY), datetime.date(2026, 11, 5))
        self.assertIsNone(extract("31/02/2027 99/99/99", self.TODAY))
        self.assertIsNone(extract("", self.TODAY))
        # Sans mot-clé : la date plausible l'emporte sur une date improbable.
        self.assertEqual(extract("12/12/1999 20/12/2026", self.TODAY), datetime.date(2026, 12, 20))

    def test_real_ocr_on_generated_label(self):
        if not main.current_tesseract_status().get("ready") or not main.PIL_AVAILABLE:
            self.skipTest("Tesseract indisponible")
        from PIL import Image, ImageDraw, ImageFont
        img = Image.new("RGB", (900, 220), "white")
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("arial.ttf", 48)
        except OSError:
            font = ImageFont.load_default(size=48)
        draw.text((30, 70), "DLC : 21/11/2026", fill="black", font=font)
        path = self.base / "etiquette.png"
        img.save(path)
        self.assertEqual(main.read_expiration_date_from_photo(str(path)), datetime.date(2026, 11, 21))

    def test_result_fills_entry_and_none_warns(self):
        win = main.PantryWindow(self.app)
        self.addCleanup(win.destroy)
        with patch.object(main.messagebox, "showinfo"):
            win._apply_expiration_photo_result("ok", datetime.date(2027, 2, 1))
        self.assertEqual(win.expiration_entry.get(), "01/02/2027")
        with patch.object(main.messagebox, "showwarning") as warn:
            win._apply_expiration_photo_result("ok", None)
        warn.assert_called_once()
        self.assertEqual(win.expiration_entry.get(), "01/02/2027")
        self.assertTrue(win.expiration_photo_button.instate(["!disabled"]))


class NewLanguagesTests(AppWindowTestBase):
    NEW = ("it", "pt", "id", "no", "sv")

    def test_every_new_language_is_complete_and_switchable(self):
        for lang in self.NEW:
            self.assertEqual(set(main.TRANSLATIONS[lang]), set(main.FRENCH_STRINGS), lang)
            self.app.set_language(lang)
            self.assertEqual(main.CURRENT_LANGUAGE, lang)
            self.assertEqual(main.t("common_cancel"), main.TRANSLATIONS[lang]["common_cancel"])
            self.assertNotEqual(main.translate_unit_name("pièce"), "pièce")
            self.assertNotEqual(main.translate_rayon_name("Crèmerie"), "Crèmerie")
            self.assertIn(lang, self.app.flag_photos)
        self.app.set_language("fr")
        self.assertEqual(main.t("common_cancel"), "Annuler")

    def test_ingredient_names_are_translated_in_new_languages(self):
        for lang in self.NEW:
            translations = main.load_ingredient_translations(lang)
            self.assertGreater(len(translations), 9000, lang)
        self.app.set_language("it")
        self.assertEqual(main.translate_ingredient_name("Tomate").lower(), "pomodoro")
        self.app.set_language("fr")

    def test_system_language_detection_recognizes_new_languages(self):
        cases = {"it_IT": "it", "Italian_Italy": "it", "pt_BR": "pt", "Portuguese_Portugal": "pt",
                 "id_ID": "id", "Indonesian_Indonesia": "id", "nb_NO": "no", "Norwegian_Norway": "no",
                 "sv_SE": "sv", "Swedish_Sweden": "sv", "en_US": "en", "Spanish_Spain": "es",
                 "fr_FR": "fr", "ja_JP": "fr"}
        for code, expected in cases.items():
            with patch("locale.getlocale", return_value=(code, "UTF-8")):
                self.assertEqual(main.detect_system_language(), expected, code)

    def test_expiry_keywords_in_new_languages(self):
        today = datetime.date(2026, 10, 3)
        for text in ("Prodotto il 01/09/2026 — da consumarsi entro il 12/03/2027",
                     "Embalado 01/09/2026 Consumir até 12/03/2027",
                     "Diproduksi 01/09/2026 Baik digunakan sebelum 12/03/2027",
                     "Pakket 01/09/2026 Best før 12.03.2027",
                     "Packad 01/09/2026 Bäst före 12.03.2027"):
            self.assertEqual(main.extract_expiration_date_from_ocr_text(text, today),
                             datetime.date(2027, 3, 12), text)


def _draw_ean13(code, path):
    """Dessine un vrai code EAN-13 (tables de codage standard) pour tester le
    décodage sans dépendance supplémentaire."""
    from PIL import Image, ImageDraw
    left_a = ["0001101", "0011001", "0010011", "0111101", "0100011", "0110001", "0101111", "0111011", "0110111", "0001011"]
    left_b = ["0100111", "0110011", "0011011", "0100001", "0011101", "0111001", "0000101", "0010001", "0001001", "0010111"]
    right = ["1110010", "1100110", "1101100", "1000010", "1011100", "1001110", "1010000", "1000100", "1001000", "1110100"]
    parity = ["AAAAAA", "AABABB", "AABBAB", "AABBBA", "ABAABB", "ABBAAB", "ABBBAA", "ABABAB", "ABABBA", "ABBABA"]
    digits = [int(c) for c in code]
    bits = "101"
    for d, p in zip(digits[1:7], parity[digits[0]]):
        bits += (left_a if p == "A" else left_b)[d]
    bits += "01010" + "".join(right[d] for d in digits[7:]) + "101"
    module, quiet = 4, 40
    img = Image.new("L", (len(bits) * module + 2 * quiet, 160), 255)
    draw = ImageDraw.Draw(img)
    for i, bit in enumerate(bits):
        if bit == "1":
            draw.rectangle([quiet + i * module, 20, quiet + (i + 1) * module - 1, 140], fill=0)
    img.save(path)


class PantryBarcodeTests(AppWindowTestBase):
    def setUp(self):
        super().setUp()
        main.save_ingredients(["Lait", "Lait de coco", "Sucre"])
        self.app.refresh_ingredients()
        self.win = main.PantryWindow(self.app)
        self.addCleanup(self.win.destroy)

    def test_normalize_and_guess(self):
        self.assertEqual(main.normalize_barcode(" 3017 6204-22003 "), "3017620422003")
        self.assertIsNone(main.normalize_barcode("12345"))
        names = ["Lait", "Lait de coco", "Sucre"]
        self.assertEqual(main.guess_known_ingredient("Lait demi-écrémé Lactel", names), "Lait")
        self.assertEqual(main.guess_known_ingredient("LAIT DE COCO bio", names), "Lait de coco")
        self.assertIsNone(main.guess_known_ingredient("Nutella", names))

    def test_real_barcode_photo_is_decoded(self):
        if not main.QRCODE_READER_AVAILABLE or not main.PIL_AVAILABLE:
            self.skipTest("pyzbar indisponible")
        path = self.base / "ean.png"
        _draw_ean13("3017620422003", path)
        self.assertEqual(main.decode_barcode_image(str(path)), "3017620422003")

    def test_found_product_prefills_then_save_remembers_and_next_scan_increments(self):
        with patch.object(main.messagebox, "showinfo"):
            self.win._apply_barcode_lookup("3270190207924", "ok",
                                           {"name": "Lait demi-écrémé UHT", "quantity": "1 L"})
        self.assertEqual(self.win.name_entry.get(), "Lait")
        self.win.qty_entry.delete(0, "end")
        self.win.qty_entry.insert(0, "2")
        self.win.save_item()
        self.assertEqual(main.get_barcode_ingredient("3270190207924")["name"], "Lait")
        with patch.object(main.messagebox, "showinfo") as info:
            self.win.handle_barcode("3270190207924")
        self.assertEqual(main.load_pantry()["lait"]["quantity"], 3)
        self.assertIn("+1", info.call_args.args[1])

    def test_unknown_product_still_remembers_after_save(self):
        with patch.object(main.messagebox, "showinfo"):
            self.win._apply_barcode_lookup("12345670", "error", OSError("hors ligne"))
        self.assertEqual(self.win.name_entry.get(), "")
        self.win.name_entry.insert(0, "Sucre")
        self.win.save_item()
        self.assertEqual(main.get_barcode_ingredient("12345670")["name"], "Sucre")

    def test_dialog_rejects_invalid_code(self):
        dialog = self.win.open_barcode_dialog()
        self.addCleanup(lambda: dialog.winfo_exists() and dialog.destroy())
        dialog.barcode_entry.insert(0, "123")
        dialog.barcode_submit()
        self.assertTrue(dialog.winfo_exists())
        self.assertEqual(dialog.barcode_status.cget("text"), main.t("pantry_barcode_invalid"))


class AuditFixesB1toB4Tests(AppWindowTestBase):
    def _walk(self, widget):
        for child in widget.winfo_children():
            yield child
            yield from self._walk(child)

    def test_import_export_bottom_is_reachable_on_a_short_screen(self):
        # B1 : sans défilement, la section sauvegarde cloud était coupée.
        win = main.ImportExportWindow(self.app)
        self.addCleanup(win.destroy)
        win.geometry("560x500")
        win.update()
        label = win.cloud_folder_label
        self.assertIn(str(win.scroll_body), str(label))
        win.scroll_canvas.yview_moveto(1.0)
        win.update()
        self.assertTrue(label.winfo_ismapped())
        bottom = label.winfo_rooty() + label.winfo_height()
        self.assertLessEqual(bottom, win.winfo_rooty() + win.winfo_height())

    def test_cooking_timers_detect_durations_in_every_language(self):
        # B2 : « Minuten » (de) et les 5 nouvelles langues n'étaient pas lus.
        durations = main.CookingModeWindow._step_durations
        cases = {"10 Minuten backen": 600, "Cuocere 35 minuti": 2100, "Riposare 2 ore": 7200,
                 "Assar 30 minutos": 1800, "Panggang 30 menit": 1800, "Diamkan 2 jam": 7200,
                 "Stek i 30 minutter": 1800, "La heve 2 timer": 7200, "Grädda 30 minuter": 1800,
                 "Låt vila 2 timmar": 7200, "30 detik": 30, "Cuire 1 heure": 3600, "10-15 minuti": 900}
        for text, seconds in cases.items():
            self.assertEqual([s for _, s in durations(text)], [seconds], text)
        self.assertEqual(durations("Mix 3 times"), [])

    def test_url_import_understands_the_new_languages(self):
        # B3 : unités et noms it/pt/id/no/sv ramenés au catalogue.
        cases = {"2 cucchiai di olio": ("Huile", "cuillère à soupe"), "200 g di farina": ("Farine", "Gr"),
                 "3 uova": ("Oeufs", "pièce"), "2 colheres de sopa de azeite": ("Huile d'olive", "cuillère à soupe"),
                 "2 sendok makan minyak": ("Huile", "cuillère à soupe"), "2 butir telur": ("Oeufs", "pièce"),
                 "200 gram tepung": ("Farine", "Gr"), "2 ss olivenolje": ("Huile d'olive", "cuillère à soupe"),
                 "1 tsk salt": ("Sel", "cuillère à café"), "3 ägg": ("Oeufs", "pièce"),
                 "2 tablespoons olive oil": ("Huile d'olive", "cuillère à soupe")}
        for _ in range(2):  # le second passage vérifie que l'index en cache reste intact
            for line, (name, unit) in cases.items():
                parsed = main._parse_url_ingredient(line)
                self.assertEqual((parsed["name"], parsed["unit"]), (name, unit), line)

    def test_allergen_disclaimer_uses_the_accessible_error_color(self):
        # B4 : #FF0000 sur fond clair = 3,7:1, sous le seuil AA de 4,5:1.
        form = main.RecipeFormWindow(self.app)
        self.addCleanup(form.destroy)
        labels = [w for w in self._walk(form) if isinstance(w, ttk.Label)
                  and w.cget("text") == main.t("recipeform_allergens_disclaimer")]
        self.assertEqual(len(labels), 1)
        self.assertEqual(str(labels[0].cget("foreground")), main.COLOR_ERROR)


class CookingModeThemeContrastTests(AppWindowTestBase):
    """B5/B6/C3 : mode cuisine figé en blanc, gris #999 (2,85:1), minuteur
    qui clignotait en blanc sur rouge clair (2,2:1 en sombre)."""

    RECIPE = {"name": "Tarte", "default_persons": 4, "prep_time": 20, "difficulty": "Facile",
              "ingredients": [{"name": "Beurre", "quantity": 30, "unit": "g"}],
              "description": "Cuire 35 minutes.\nServir.", "personal_notes": "Très bon"}

    def _hex(self, color):
        r, g, b = self.app.winfo_rgb(color)
        return "#%02x%02x%02x" % (r // 256, g // 256, b // 256)

    def _contrast(self, fg, bg):
        from test_regressions import ContrastAccessibilityTests as C
        return C._contrast(self._hex(fg), self._hex(bg))

    def _walk(self, widget):
        for child in widget.winfo_children():
            yield child
            yield from self._walk(child)

    def _check_window(self, palette_name):
        win = main.CookingModeWindow(self.app, dict(self.RECIPE), 4)
        self.addCleanup(win.destroy)
        win.update()
        texts = [w for w in self._walk(win) if isinstance(w, (tk.Label, tk.Checkbutton))]
        self.assertGreaterEqual(len(texts), 8)
        for w in [win, *self._walk(win)]:
            if isinstance(w, (tk.Frame, tk.Canvas, tk.Label, tk.Checkbutton, tk.Toplevel)):
                self.assertEqual(self._hex(w.cget("background")), self._hex(main.COLOR_CARD), (palette_name, w))
        for w in texts:
            ratio = self._contrast(w.cget("foreground"), w.cget("background"))
            self.assertGreaterEqual(ratio, 4.5, (palette_name, w.cget("text")[:30], ratio))
        buttons = [w for w in self._walk(win) if isinstance(w, tk.Button)]
        self.assertGreaterEqual(len(buttons), 7)
        for w in buttons:
            self.assertEqual(self._hex(w.cget("background")), self._hex(main.COLOR_ACCENT_LIGHT), (palette_name, w.cget("text")))
            ratio = self._contrast(w.cget("foreground"), w.cget("background"))
            self.assertGreaterEqual(ratio, 4.5, (palette_name, w.cget("text"), ratio))
        for w in texts:
            if isinstance(w, tk.Checkbutton):
                self.assertEqual(self._hex(w.cget("selectcolor")), self._hex(main.COLOR_CARD))
        # Minuteur terminé : texte lisible sur le fond clignotant.
        row = main.TimerRow(win.timer_frame, win, "test", 1)
        row.finished = True
        row._flash_on = False
        row._flash_step()
        label = row.display_label
        self.assertGreaterEqual(self._contrast(label.cget("foreground"), label.cget("background")), 4.5, palette_name)
        win.destroy()

    def test_cooking_mode_follows_all_three_themes_with_readable_text(self):
        self._check_window("clair")
        self.app.toggle_dark_mode()
        self._check_window("sombre")
        self.app.toggle_high_contrast()
        self._check_window("contraste élevé")

    def test_toast_is_readable_in_every_theme(self):
        for _ in range(2):
            main._ui_show_toast(self.app, "ok", duration=10)
            toast = [w for w in self.app.winfo_children() if isinstance(w, tk.Toplevel)][-1]
            label = toast.winfo_children()[0]
            self.assertGreaterEqual(self._contrast(label.cget("foreground"), label.cget("background")), 4.5)
            toast.destroy()
            self.app.toggle_dark_mode()

    def test_no_hardcoded_widget_colors_left(self):
        import re
        source = (Path(main.__file__)).read_text(encoding="utf-8")
        found = re.findall(r"""(?:background|foreground|fg|bg|fill|outline|selectcolor)\s*=\s*["'](?:#[0-9a-fA-F]{3,6}|white|black)["']""", source)
        self.assertEqual(found, [])


class LargeTextLayoutTests(AppWindowTestBase):
    """C2 : avec des marges qui grandissent en « Texte agrandi », le bouton
    principal d'Import photo sortait de la fenêtre ; la légende des
    Statistiques était déjà coupée. Fenêtre volontairement petite."""

    def setUp(self):
        patcher = patch.object(main, "get_large_text_preference", lambda: True)
        patcher.start()
        self.addCleanup(patcher.stop)
        super().setUp()

    def _walk(self, widget):
        for child in widget.winfo_children():
            yield child
            yield from self._walk(child)

    def _visible(self, win, widget):
        top = widget.winfo_rooty() - win.winfo_rooty()
        return widget.winfo_ismapped() and top + widget.winfo_height() <= win.winfo_height()

    def test_import_photo_main_button_stays_visible(self):
        win = main.ImportFromPhotoWindow(self.app)
        self.addCleanup(win.destroy)
        win.geometry("900x600")
        win.update()
        button = [w for w in self._walk(win) if isinstance(w, ttk.Button)
                  and w.cget("text") == main.t("importphoto_create_button")][0]
        self.assertTrue(self._visible(win, button))

    def test_statistics_bottom_is_reachable_by_scrolling(self):
        win = main.StatisticsWindow(self.app)
        self.addCleanup(win.destroy)
        win.geometry("900x600")
        win.update()
        win.scroll_canvas.yview_moveto(1.0)
        win.update()
        legend = [w for w in self._walk(win) if isinstance(w, ttk.Label)
                  and w.cget("text") == main.t("stats_heatmap_legend")][0]
        self.assertTrue(self._visible(win, legend))

class DisclaimerVersionTests(TempDataMixin, unittest.TestCase):
    """Clause v2 : un ancien « oui » (v1) ne suffit plus, le nouveau texte
    est présenté avec la mention de mise à jour ; relecture possible."""

    def test_old_acceptance_requires_accepting_the_new_text(self):
        self.assertFalse(main.get_disclaimer_accepted())
        settings = main.load_settings()
        settings["disclaimer_accepted"] = True  # réglage d'avant la v2
        main.save_settings(settings)
        self.assertEqual(main.get_accepted_disclaimer_version(), 1)
        self.assertFalse(main.get_disclaimer_accepted())
        main.set_disclaimer_accepted(True)
        self.assertEqual(main.get_accepted_disclaimer_version(), main.DISCLAIMER_VERSION)
        self.assertTrue(main.get_disclaimer_accepted())

    def test_clause_text_is_the_desktop_version_in_every_language(self):
        for language in main.UI_LANGUAGES:
            text = main._language_catalog(language)["disclaimer_text"]
            self.assertIn("majogari81@gmail.com", text, language)
            self.assertNotIn("smartphone", text.lower(), language)
            self.assertIn("OneDrive", text, language)
            self.assertEqual(text.count("\n\n"), 16, language)


class DisclaimerWindowModesTests(AppWindowTestBase):
    def _walk(self, widget):
        for child in widget.winfo_children():
            yield child
            yield from self._walk(child)

    def _texts(self, win):
        return [w.cget("text") for w in self._walk(win) if isinstance(w, (ttk.Label, ttk.Button, ttk.Checkbutton))]

    def test_updated_text_is_announced_after_an_old_acceptance(self):
        settings = main.load_settings()
        settings["disclaimer_accepted"] = True
        main.save_settings(settings)
        win = main.DisclaimerWindow(self.app)
        self.addCleanup(win.destroy)
        self.assertIn(main.t("disclaimer_updated_intro"), self._texts(win))
        self.assertIn(main.t("disclaimer_checkbox"), self._texts(win))

    def test_read_only_window_only_offers_close(self):
        win = main.DisclaimerWindow(self.app, read_only=True)
        texts = self._texts(win)
        self.assertIn(main.t("common_close"), texts)
        self.assertNotIn(main.t("disclaimer_checkbox"), texts)
        self.assertNotIn(main.t("disclaimer_quit_button"), texts)
        win.tk.eval(win.protocol("WM_DELETE_WINDOW"))  # fermer ne quitte pas l application
        self.assertFalse(win.winfo_exists())
        self.assertTrue(self.app.winfo_exists())

    def test_import_export_offers_legal_links_and_fits(self):
        win = main.ImportExportWindow(self.app)
        self.addCleanup(win.destroy)
        win.update()
        buttons = {w.cget("text"): w for w in self._walk(win) if isinstance(w, ttk.Button)}
        with patch.object(main.webbrowser, "open") as mock_open:
            buttons[main.t("privacy_policy_link")].invoke()
        mock_open.assert_called_once_with(main.PRIVACY_POLICY_URL)
        before = {str(w) for w in self.app.winfo_children()}
        buttons[main.t("disclaimer_link")].invoke()
        opened = [w for w in self.app.winfo_children() if str(w) not in before]
        self.assertEqual(len(opened), 1)
        self.assertTrue(opened[0].read_only)
        opened[0].destroy()
        # Tout le contenu est dans la zone défilante et tient en largeur.
        self.assertEqual([w for w in win.winfo_children() if not isinstance(w, tk.Toplevel)][0].winfo_children()[0], win.scroll_canvas)
        self.assertEqual(len([w for w in win.winfo_children() if not isinstance(w, tk.Toplevel)]), 1)
        widest = max(c.winfo_reqwidth() for c in win.scroll_body.winfo_children())
        self.assertLessEqual(widest, win.scroll_canvas.winfo_width())


if __name__ == "__main__":
    unittest.main()
