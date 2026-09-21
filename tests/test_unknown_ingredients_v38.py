import tkinter as tk
import unittest
from tkinter import ttk
from types import SimpleNamespace
from unittest.mock import patch

import main
from test_regressions import TempDataMixin


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

    def test_did_you_mean_hint_suggests_close_ingredient_while_typing(self):
        fake = SimpleNamespace(ingredient_names=["Tomate", "Oignon", "Farine"])
        self.assertEqual(main.RecipeFormWindow._did_you_mean_hint(fake, "Tomates"), "Tomate")

    def test_did_you_mean_hint_ignores_already_known_ingredient(self):
        fake = SimpleNamespace(ingredient_names=["Tomate", "Oignon"])
        self.assertIsNone(main.RecipeFormWindow._did_you_mean_hint(fake, "Tomate"))

    def test_did_you_mean_hint_ignores_short_or_unrelated_text(self):
        fake = SimpleNamespace(ingredient_names=["Tomate", "Oignon"])
        self.assertIsNone(main.RecipeFormWindow._did_you_mean_hint(fake, "To"))
        self.assertIsNone(main.RecipeFormWindow._did_you_mean_hint(fake, "Xylophone"))


class UnknownIngredientsDialogTests(unittest.TestCase):
    """Instancie réellement UnknownIngredientsDialog pour vérifier son
    comportement (scoring, suggestions en direct, résultat renvoyé) plutôt
    que d'inspecter le texte source de ses méthodes."""

    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.addCleanup(self.root.destroy)
        self.root.withdraw()

    def test_dialog_scores_confidence_to_prefill_replace_or_create(self):
        dialog = main.UnknownIngredientsDialog(
            self.root, ["Tomates", "Truc bizarre"], ["Tomate", "Oignon"]
        )
        self.addCleanup(dialog.destroy)
        # La construction ne doit lever aucune exception : elle utilise
        # get_usable_screen_height(self) (avec l'argument requis), pas
        # get_usable_screen_height() seul, qui lèverait un TypeError.
        self.assertTrue(dialog.winfo_exists())
        self.assertEqual(len(dialog.rows), 2)

        _, action, choice, _ = next(r for r in dialog.rows if r[0] == "Tomates")
        self.assertIsInstance(choice, ttk.Entry)
        self.assertEqual(action.get(), "replace")
        self.assertEqual(choice.get(), main.translate_ingredient_name("Tomate"))

        _, other_action, _, _ = next(r for r in dialog.rows if r[0] == "Truc bizarre")
        self.assertEqual(other_action.get(), "create")

    def test_accept_maps_each_unknown_name_to_its_chosen_resolution(self):
        dialog = main.UnknownIngredientsDialog(
            self.root, ["Tomates", "Truc bizarre"], ["Tomate", "Oignon"]
        )
        self.addCleanup(dialog.destroy)

        dialog._accept()

        self.assertEqual(
            dialog.result[main.ingredient_sort_key("Tomates")], ("replace", "Tomate")
        )
        self.assertEqual(
            dialog.result[main.ingredient_sort_key("Truc bizarre")],
            ("create", main.normalize_oe("Truc bizarre")),
        )

    def test_replacement_field_is_a_searchable_entry_with_live_suggestions(self):
        dialog = main.UnknownIngredientsDialog(
            self.root, ["Xyz inconnu"], ["Tomate", "Tomate cerise", "Oignon"]
        )
        self.addCleanup(dialog.destroy)
        _, action, choice, _ = dialog.rows[0]

        choice.delete(0, tk.END)
        choice.insert(0, "tom")
        # event_generate() pour KeyRelease exige un vrai focus clavier X11,
        # indisponible sous Xvfb sans gestionnaire de fenêtres : on appelle
        # directement le vrai gestionnaire lié à la touche, comme le ferait
        # la frappe réelle.
        dialog._on_replacement_keyrelease(SimpleNamespace(keysym="m"), choice, action)

        self.assertIsNotNone(choice._suggestion_listbox)
        values = list(choice._suggestion_listbox.get(0, tk.END))
        self.assertIn(main.translate_ingredient_name("Tomate"), values)
        self.assertIn(main.translate_ingredient_name("Tomate cerise"), values)
        self.assertEqual(action.get(), "replace")

    def test_focus_in_selects_prefilled_text_for_direct_retyping(self):
        dialog = main.UnknownIngredientsDialog(self.root, ["Tomates"], ["Tomate", "Oignon"])
        self.addCleanup(dialog.destroy)
        _, _action, choice, _ = dialog.rows[0]
        self.assertEqual(choice.get(), main.translate_ingredient_name("Tomate"))

        choice.event_generate("<FocusIn>")
        dialog.update()

        self.assertEqual(choice.selection_get(), main.translate_ingredient_name("Tomate"))


class RecipeFormIngredientResolutionTests(TempDataMixin, unittest.TestCase):
    """Instancie réellement RecipeFormWindow pour vérifier que la résolution
    des ingrédients inconnus (bouton Enregistrer, suggestions en direct)
    fonctionne effectivement, plutôt que d'inspecter le texte source."""

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

    def test_ingredient_keyrelease_falls_back_to_did_you_mean_hint(self):
        main.save_ingredients(["Tomate", "Oignon", "Farine"])
        self.app.refresh_ingredients()
        form = main.RecipeFormWindow(self.app)
        self.addCleanup(form.destroy)
        name_e, _qty_e, _unit_e, _custom_e = form.ingredient_rows[0]

        name_e.delete(0, tk.END)
        name_e.insert(0, "Tomates")
        # event_generate() pour KeyRelease exige un vrai focus clavier X11,
        # indisponible sous Xvfb sans gestionnaire de fenêtres : on appelle
        # directement le vrai gestionnaire lié à la touche, comme le ferait
        # la frappe réelle.
        form._on_ingredient_keyrelease(SimpleNamespace(keysym="s"), name_e)

        self.assertIsNotNone(name_e._suggestion_listbox)
        values = list(name_e._suggestion_listbox.get(0, tk.END))
        expected = main.t(
            "recipeform_did_you_mean", name=main.translate_ingredient_name("Tomate")
        )
        self.assertEqual(values, [expected])

    def test_save_resolves_unknown_ingredient_before_the_strict_check_rejects_it(self):
        main.save_ingredients(["Farine"])
        self.app.refresh_ingredients()
        form = main.RecipeFormWindow(self.app)
        self.addCleanup(form.destroy)

        form.name_entry.insert(0, "Salade exotique")
        name_e, qty_e, _unit_e, _custom_e = form.ingredient_rows[0]
        name_e.delete(0, tk.END)
        name_e.insert(0, "Fruit du dragon")
        qty_e.delete(0, tk.END)
        qty_e.insert(0, "2")

        class FakeUnknownIngredientsDialog(tk.Toplevel):
            def __init__(fake_self, parent, unknown_names, existing_names):
                super().__init__(parent)
                # Simule l'utilisateur choisissant "créer" pour chaque
                # ingrédient inconnu, sans boîte modale à piloter.
                fake_self.result = {
                    main.ingredient_sort_key(n): ("create", n) for n in unknown_names
                }
                fake_self.after_idle(fake_self.destroy)

        with patch.object(main, "UnknownIngredientsDialog", FakeUnknownIngredientsDialog):
            form.save_recipe()

        # Si la validation stricte ("ingredients = []" / ingrédient inconnu)
        # s'exécutait avant la résolution, save_recipe se serait arrêté sans
        # jamais atteindre save_recipes() : la fenêtre serait restée ouverte
        # et rien n'aurait été enregistré.
        self.assertFalse(form.winfo_exists())
        recipes = main.load_recipes()
        saved = next(r for r in recipes if r["name"] == "Salade exotique")
        self.assertEqual(saved["ingredients"][0]["name"], "Fruit du dragon")
        self.assertIn("Fruit du dragon", main.load_ingredients())


if __name__ == "__main__":
    unittest.main()
