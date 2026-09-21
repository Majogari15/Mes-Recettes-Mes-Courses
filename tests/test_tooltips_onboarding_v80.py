import tkinter as tk
import unittest
from unittest.mock import patch

import main
from test_regressions import TempDataMixin


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


class TooltipHelperTests(AppWindowTestBase):
    """Aucune info-bulle n'existait nulle part dans l'application : les
    boutons composés d'une seule icône (🗑, 👁, 🔄...) n'avaient aucun moyen
    de faire deviner leur action sans cliquer dessus."""

    def test_tooltip_appears_on_show_and_disappears_on_hide(self):
        button = tk.Button(self.app, text="🗑")
        tooltip = main.add_tooltip(button, "Supprimer")
        self.addCleanup(tooltip._hide)

        # _schedule()/_show() appellent widget.after(), qui exige un vrai
        # évènement <Enter> pour se déclencher naturellement — indisponible
        # de façon fiable sous Xvfb sans gestionnaire de fenêtres (même
        # limite déjà rencontrée pour d'autres évènements souris cette
        # session) : on appelle directement _show()/_hide(), comme le
        # ferait le délai après un survol réel.
        self.assertIsNone(tooltip._tip)
        tooltip._show()
        self.assertIsNotNone(tooltip._tip)
        self.assertTrue(tooltip._tip.winfo_exists())
        label = tooltip._tip.winfo_children()[0]
        self.assertEqual(label.cget("text"), "Supprimer")

        tooltip._hide()
        self.assertIsNone(tooltip._tip)

    def test_showing_twice_does_not_create_a_second_popup(self):
        button = tk.Button(self.app, text="🔄")
        tooltip = main.add_tooltip(button, "Réinitialiser")
        self.addCleanup(tooltip._hide)

        tooltip._show()
        first_tip = tooltip._tip
        tooltip._show()
        self.assertIs(tooltip._tip, first_tip)


class RecipesAvailableGuardTests(AppWindowTestBase):
    """Les 9 points d'entrée qui exigeaient au moins une recette affichaient
    un simple message bloquant sans aucune suite possible ("Aucune recette
    enregistrée pour le moment.") — remplacé par une invite qui propose
    d'en créer une tout de suite."""

    def test_declining_the_prompt_leaves_the_feature_closed(self):
        opened = []
        with patch.object(main.messagebox, "askyesno", return_value=False) as mock_ask, \
             patch.object(main, "ManageRecipesWindow", lambda *a, **k: opened.append(True)):
            self.app.open_manage_recipes()

        mock_ask.assert_called_once()
        self.assertEqual(mock_ask.call_args.args[1], main.t("home_empty_prompt_create_recipe"))
        self.assertEqual(opened, [])

    def test_accepting_and_saving_a_recipe_opens_the_requested_feature(self):
        def fake_add_recipe():
            main.save_recipes([{
                "id": "r1", "name": "Omelette", "default_persons": 2,
                "category": "Plat", "difficulty": "Facile", "images": [],
                "ingredients": [], "steps": [],
            }])
            self.app.refresh_recipes()

        opened = []

        class FakeManageRecipesWindow(tk.Toplevel):
            # open_manage_recipes() enchaîne avec self.wait_window(win) :
            # ce faux remplaçant doit rester un vrai Toplevel destructible,
            # sinon wait_window(None) attendrait la destruction de l'App
            # elle-même (jamais atteinte en cours de test).
            def __init__(fake_self, app, quick_filter=None, initial_search=""):
                super().__init__(app)
                opened.append(True)
                fake_self.after_idle(fake_self.destroy)

        with patch.object(main.messagebox, "askyesno", return_value=True), \
             patch.object(self.app, "open_add_recipe", fake_add_recipe), \
             patch.object(main, "ManageRecipesWindow", FakeManageRecipesWindow):
            self.app.open_manage_recipes()

        self.assertEqual(opened, [True])

    def test_accepting_but_not_saving_leaves_the_feature_closed(self):
        opened = []
        with patch.object(main.messagebox, "askyesno", return_value=True), \
             patch.object(self.app, "open_add_recipe", lambda: None), \
             patch.object(main, "ManageRecipesWindow", lambda *a, **k: opened.append(True)):
            self.app.open_manage_recipes()

        self.assertEqual(opened, [])


if __name__ == "__main__":
    unittest.main()
