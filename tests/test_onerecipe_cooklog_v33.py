import unittest
from datetime import datetime
from unittest.mock import patch

import tkinter as tk

import main
from test_regressions import TempDataMixin


class OneRecipeWindowTestBase(TempDataMixin, unittest.TestCase):
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


class OneRecipeCookLogV33Tests(OneRecipeWindowTestBase):
    def test_onerecipe_has_no_required_fmt_dependency(self):
        self.assertFalse(hasattr(main.OneRecipeWindow, "_fmt"))

    def test_mark_as_cooked_records_cook_log_and_refreshes_canonical_recipe(self):
        main.save_recipes([{
            "id": "r1", "name": "Poulet rôti", "default_persons": 4,
            "category": "Plat", "difficulty": "Facile", "images": [],
            "ingredients": [{"name": "Poulet", "quantity": 1, "unit": "pièce"}],
            "steps": ["Cuire au four."],
        }])
        self.app.refresh_recipes()
        win = main.OneRecipeWindow(self.app, initial_recipe_name="Poulet rôti")
        self.addCleanup(win.destroy)
        self.assertIsNotNone(win.current_recipe)
        win.pers_entry.delete(0, tk.END)
        win.pers_entry.insert(0, "4")

        class FakeCookLogEntryDialog:
            def __init__(self, app, recipe_name, on_done, persons=None):
                # Simule l'utilisateur validant immédiatement le formulaire
                # de journal de cuisson (synchronement, sans boîte modale).
                on_done("Excellent", "Un peu salé", None, rating=5, cooked_persons=persons)

        with patch.object(main, "CookLogEntryDialog", FakeCookLogEntryDialog), \
             patch.object(main.messagebox, "showinfo"), \
             patch.object(main.messagebox, "showerror"):
            win.mark_as_cooked()

        recipes = main.load_recipes()
        target = main.find_recipe_by_id(recipes, "r1")
        self.assertEqual(len(target["cook_log"]), 1)
        entry = target["cook_log"][0]
        self.assertEqual(entry["note"], "Excellent")
        self.assertEqual(entry["comment"], "Un peu salé")
        self.assertEqual(entry["rating"], 5)
        # Les personnes entières doivent être stockées comme int (pas 4.0),
        # c'est ce que "cooked_persons_display" garantit dans mark_as_cooked.
        self.assertEqual(entry["persons"], 4)
        self.assertIsInstance(entry["persons"], int)

        # La fiche doit utiliser l'objet recette canonique rechargé depuis
        # disque (via app.recipes), pas une copie obsolète en mémoire.
        self.assertIs(win.current_recipe, main.find_recipe_by_id(self.app.recipes, "r1"))
        self.assertEqual(len(win.current_recipe["cook_log"]), 1)

        # La fenêtre doit rester active au premier plan après la cuisson.
        self.assertTrue(win.winfo_exists())
        win.deiconify()
        win.lift()
        win.focus_force()
        win.grab_set()

    def test_cooking_photo_is_included_in_recipe_gallery(self):
        recipe = {
            "id": "r2", "name": "Tarte", "default_persons": 4,
            "category": "Dessert", "difficulty": "Facile", "images": [],
            "ingredients": [], "steps": [],
            "cook_log": [
                {"date": "2024-01-01T10:00:00", "photo": None},
                {"date": "2024-03-15T18:30:00", "photo": "cook_photo.jpg"},
            ],
        }
        main.save_recipes([recipe])
        self.app.refresh_recipes()
        win = main.OneRecipeWindow(self.app, initial_recipe_name="Tarte")
        self.addCleanup(win.destroy)

        texts = []
        for cell in win.gallery_frame.winfo_children():
            for grandchild in cell.winfo_children():
                if "text" in grandchild.keys():
                    texts.append(grandchild.cget("text"))
        self.assertIn(main.t("onerecipe_latest_cook_photo"), texts)

    def test_recipe_view_returns_to_foreground_after_edit(self):
        main.save_recipes([{
            "id": "r3", "name": "Soupe", "default_persons": 2,
            "category": "Entrée", "difficulty": "Facile", "images": [],
            "ingredients": [], "steps": [],
        }])
        self.app.refresh_recipes()
        win = main.OneRecipeWindow(self.app, initial_recipe_name="Soupe")
        self.addCleanup(win.destroy)
        index = win.selected_actual_index
        self.assertIsNotNone(index)

        class FakeRecipeFormWindow(tk.Toplevel):
            # _populate() du parent référence RecipeFormWindow.CATEGORY_OPTIONS
            # au niveau module : ce faux remplaçant doit l'exposer aussi.
            CATEGORY_OPTIONS = main.RecipeFormWindow.CATEGORY_OPTIONS

            def __init__(fake_self, app, recipe_index=None):
                super().__init__(app)
                fake_self.after_idle(fake_self.destroy)

        with patch.object(main, "RecipeFormWindow", FakeRecipeFormWindow):
            win._edit_recipe(index)

        self.assertTrue(win.winfo_exists())
        # Aucune exception ne doit être levée par ces appels de premier plan,
        # sinon un TclError serait remonté après la fermeture du formulaire.
        win.deiconify()
        win.lift()
        win.focus_force()
        win.grab_set()

    def test_recipe_view_can_refresh_without_being_destroyed(self):
        main.save_recipes([{
            "id": "r4", "name": "Salade", "default_persons": 2,
            "category": "Entrée", "difficulty": "Facile", "images": [],
            "ingredients": [], "steps": [],
        }])
        self.app.refresh_recipes()
        win = main.OneRecipeWindow(self.app, initial_recipe_name="Salade")
        self.addCleanup(win.destroy)
        before = win.current_recipe
        self.assertIsNotNone(before)

        win.refresh_ui()

        self.assertTrue(win.winfo_exists())
        self.assertEqual(win.current_recipe["name"], "Salade")
        self.assertEqual(win.title(), main.t("onerecipe_window_title"))

    def test_recipe_library_does_not_refresh_after_it_was_closed(self):
        main.save_recipes([{
            "id": "r5", "name": "Ratatouille", "default_persons": 4,
            "category": "Plat", "difficulty": "Facile", "images": [],
            "ingredients": [], "steps": [],
        }])
        self.app.refresh_recipes()
        manage = main.ManageRecipesWindow(self.app)

        class FakeOneRecipeWindow(tk.Toplevel):
            def __init__(fake_self, app, initial_recipe_name=None):
                super().__init__(app)

                def _simulate_closed_while_viewing():
                    # La bibliothèque a pu être fermée (ex : depuis la barre
                    # des tâches) pendant que la fiche recette était affichée.
                    manage.destroy()
                    fake_self.destroy()

                fake_self.after_idle(_simulate_closed_while_viewing)

        with patch.object(main, "OneRecipeWindow", FakeOneRecipeWindow), \
             patch.object(manage, "_populate") as fake_populate, \
             patch.object(self.app, "refresh_recipes") as fake_refresh:
            manage._open_index(0)

        self.assertFalse(manage.winfo_exists())
        fake_populate.assert_not_called()
        fake_refresh.assert_not_called()

    def test_edit_form_exposes_cooking_log_tab(self):
        main.save_recipes([{
            "id": "r6", "name": "Gratin", "default_persons": 4,
            "category": "Plat", "difficulty": "Facile", "images": [],
            "ingredients": [], "steps": [], "cook_log": [],
        }])
        self.app.refresh_recipes()
        form = main.RecipeFormWindow(self.app, recipe_index=0)
        self.addCleanup(form.destroy)

        self.assertTrue(form.editing)
        self.assertTrue(hasattr(form, "tab_cook_log"))
        tabs = form.form_notebook.tabs()
        self.assertIn(str(form.tab_cook_log), tabs)
        self.assertEqual(
            form.form_notebook.tab(form.tab_cook_log, "text"),
            main.t("recipeform_tab_cook_log"),
        )

    def test_edit_form_renders_cooking_history_details_and_photos(self):
        main.save_recipes([{
            "id": "r7", "name": "Curry", "default_persons": 4,
            "category": "Plat", "difficulty": "Facile", "images": [],
            "ingredients": [], "steps": [],
            "cook_log": [{
                "date": datetime(2024, 6, 1, 19, 30).isoformat(),
                "note": "Bien épicé",
                "comment": "À refaire",
                "photo": None,
                "rating": 4,
                "persons": 6,
            }],
        }])
        self.app.refresh_recipes()
        form = main.RecipeFormWindow(self.app, recipe_index=0)
        self.addCleanup(form.destroy)

        texts = []

        def collect(widget):
            if "text" in widget.keys():
                texts.append(widget.cget("text"))
            for child in widget.winfo_children():
                collect(child)

        collect(form.tab_cook_log)

        self.assertIn(main.t("cooklog_entry_persons", persons=6), texts)
        self.assertIn(main.t("cooklog_entry_rating", stars="★★★★☆"), texts)
        self.assertTrue(any("Bien épicé" in text for text in texts))
        self.assertTrue(any("À refaire" in text for text in texts))

    def test_cook_log_tab_rewraps_notes_when_window_is_resized(self):
        long_comment = "Un commentaire assez long pour tester le retour à la ligne. " * 4
        main.save_recipes([{
            "id": "r8", "name": "Risotto", "default_persons": 4,
            "category": "Plat", "difficulty": "Facile", "images": [],
            "ingredients": [], "steps": [],
            "cook_log": [{
                "date": datetime(2024, 6, 1, 19, 30).isoformat(),
                "note": "", "comment": long_comment,
                "photo": None, "rating": 0, "persons": 4,
            }],
        }])
        self.app.refresh_recipes()
        form = main.RecipeFormWindow(self.app, recipe_index=0)
        self.addCleanup(form.destroy)
        self.assertEqual(len(form._cook_log_wrap_labels), 1)
        comment_label = form._cook_log_wrap_labels[0]
        # Le calcul de largeur dépend de winfo_width(), qui n'est mis à jour
        # que pour l'onglet réellement affiché.
        form.form_notebook.select(form.tab_cook_log)

        form.geometry("1400x700")
        form.update()
        wide_wrap = comment_label.cget("wraplength")

        form.geometry("700x500")
        form.update()
        narrow_wrap = comment_label.cget("wraplength")

        self.assertNotEqual(wide_wrap, narrow_wrap)
        self.assertLess(narrow_wrap, wide_wrap)


class CookLogEntryDialogCancelTests(OneRecipeWindowTestBase):
    """Un clic accidentel sur "J'ai cuisiné ça" comptait jusqu'ici toujours
    comme une cuisson réelle (skip() appelait on_done avec des champs
    vides), y compris en fermant la fenêtre via ✕ — aucun vrai moyen
    d'annuler. Vérifie le nouveau bouton "Annuler" et la fermeture ✕."""

    def _make_dialog(self):
        calls = []
        dialog = main.CookLogEntryDialog(
            self.app, "Poulet rôti", lambda *a, **k: calls.append((a, k)), persons=4
        )
        self.addCleanup(lambda: dialog.destroy() if dialog.winfo_exists() else None)
        return dialog, calls

    def test_cancel_does_not_call_on_done(self):
        dialog, calls = self._make_dialog()
        dialog.cancel()
        self.assertEqual(calls, [])
        self.assertFalse(dialog.winfo_exists())

    def test_skip_still_calls_on_done_with_empty_fields(self):
        # Comportement volontairement inchangé : "Passer" enregistre bien
        # la cuisson (juste sans notes), contrairement à "Annuler".
        dialog, calls = self._make_dialog()
        dialog.skip()
        self.assertEqual(len(calls), 1)
        args, _kwargs = calls[0]
        self.assertEqual(args, ("", "", None, 0, 4))

    def test_closing_the_window_cancels_instead_of_recording_a_cooking(self):
        # Garde-fou contre une régression du câblage lui-même (ex. un futur
        # changement qui relierait à nouveau ✕ à skip()) : on invoque la
        # vraie commande Tcl enregistrée par self.protocol(...), pas
        # dialog.cancel() directement.
        dialog, calls = self._make_dialog()
        bound_command = dialog.protocol("WM_DELETE_WINDOW")
        self.assertTrue(bound_command)
        dialog.tk.call(bound_command)
        self.assertEqual(calls, [])
        self.assertFalse(dialog.winfo_exists())


if __name__ == "__main__":
    unittest.main()
