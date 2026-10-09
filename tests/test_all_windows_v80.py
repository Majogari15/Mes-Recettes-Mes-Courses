"""C1 : ouvre réellement chaque fenêtre de l'application (fr clair, sv sombre).

Beaucoup de fenêtres n'étaient presque jamais instanciées par les tests
(statistiques, comparaison, livre PDF, substitutions, planning…) : une
erreur à l'ouverture n'aurait été vue que par un utilisateur. Toute nouvelle
fenêtre (sous-classe de tk.Toplevel dans main) est couverte automatiquement.
"""
import inspect
import sys
import tkinter as tk
import traceback
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import main  # noqa: E402
from test_regressions import TempDataMixin  # noqa: E402

# Fenêtres ouvertes autrement (premier lancement) ou exigeant un contexte
# que ce test ne peut pas fabriquer.
SKIPPED = {"App", "DisclaimerWindow"}

RECIPES = [
    {"id": "r1", "name": "Tarte aux poireaux", "category": "Plat", "difficulty": "Facile", "default_persons": 4,
     "prep_time": 20, "cook_time": 35, "images": [], "tags": ["légumes"], "rating": 4, "favorite": True,
     "ingredients": [{"name": "Poireau", "quantity": 3, "unit": "pièce"}, {"name": "Beurre", "quantity": 30, "unit": "g"},
                     {"name": "Oeufs", "quantity": 3, "unit": "pièce"}],
     "steps": ["Couper.", "Cuire 35 minutes."], "description": "Couper.\nCuire 35 minutes.",
     "times_cooked": 2, "cooked_dates": ["2026-09-01", "2026-09-20"]},
    {"id": "r2", "name": "Crêpes", "category": "Dessert", "difficulty": "Facile", "default_persons": 4,
     "prep_time": 10, "cook_time": 20, "images": [], "tags": [], "wishlist": True,
     "ingredients": [{"name": "Farine", "quantity": 250, "unit": "g"}, {"name": "Lait", "quantity": 50, "unit": "cl"}],
     "steps": ["Mélanger.", "Cuire."], "description": "Mélanger.\nCuire."},
]


def _arguments(cls, app, recipe):
    """Arguments plausibles d'après les noms des paramètres obligatoires."""
    args = []
    for p in list(inspect.signature(cls.__init__).parameters.values())[1:]:
        if p.default is not inspect._empty or p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
            continue
        n = p.name.lower()
        if n in ("app", "parent", "master", "root", "owner", "target_window", "parent_window", "manager"):
            args.append(app)
        elif n.endswith("callback") or n in ("on_done", "decoder"):
            args.append(lambda *a, **k: None)
        elif n == "on_value":
            args.append(lambda value: (False, None))
        elif n == "hint":
            args.append("test")
        elif n == "persons":
            args.append(4)
        elif n == "grouped_totals":
            args.append([("Fruits et légumes", [{"name": "Poireau", "quantity": 3, "unit": "pièce"}])])
        elif "idx" in n or "index" in n:
            args.append(0)
        elif "recipe" in n:
            args.append(recipe)
        elif "items" in n:
            args.append([{"name": "Farine", "quantity": 1, "unit": "Kilo"}])
        elif "name" in n or "ingredient" in n:
            args.append("Beurre")
        else:
            return None
    return args


class AllWindowsOpenTests(TempDataMixin, unittest.TestCase):
    def _open_all(self, language, dark):
        dialogs = []
        patches = [
            ("get_disclaimer_accepted", lambda: True), ("get_large_text_preference", lambda: False),
            ("get_language_preference", lambda: language), ("maybe_create_auto_backup", lambda: None),
            ("get_dark_mode_preference", lambda: dark),
            # Jamais la vraie caméra pendant les tests : « aucune webcam ».
            ("open_webcam", lambda *a, **k: None),
        ]
        for name, value in patches:
            patcher = patch.object(main, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        for name in ("showinfo", "showwarning", "showerror"):
            patcher = patch.object(main.messagebox, name, lambda *a, _n=name, **k: dialogs.append((_n, a[:2])))
            patcher.start()
            self.addCleanup(patcher.stop)
        for name in ("askyesno", "askokcancel", "askyesnocancel", "askquestion"):
            patcher = patch.object(main.messagebox, name, lambda *a, **k: False)
            patcher.start()
            self.addCleanup(patcher.stop)
        main.save_recipes([dict(r) for r in RECIPES])
        main.save_pantry({"farine": {"name": "Farine", "quantity": 1, "unit": "Kilo", "threshold": 2,
                                     "expiration_date": "2026-10-05"}})
        try:
            app = main.App()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.addCleanup(app.destroy)
        app.withdraw()
        app.update()
        errors = []
        app.report_callback_exception = lambda e, v, tb: errors.append("".join(traceback.format_exception(e, v, tb)))
        recipe = app.recipes[0]
        opened = 0
        for name, cls in sorted(vars(main).items()):
            if not (inspect.isclass(cls) and issubclass(cls, tk.Toplevel) and cls.__module__ == "main") or name in SKIPPED:
                continue
            args = _arguments(cls, app, recipe)
            self.assertIsNotNone(args, f"{name} : paramètre inconnu, compléter _arguments()")
            with self.subTest(window=name, language=language, dark=dark):
                before = len(errors)
                window = cls(*args)
                app.update()
                self.assertTrue(window.winfo_exists())
                window.destroy()
                app.update()
                self.assertEqual(errors[before:], [])
                opened += 1
        self.assertGreaterEqual(opened, 35)
        self.assertEqual([d for d in dialogs if d[0] == "showerror"], [])

    def test_every_window_opens_in_french_light(self):
        self._open_all("fr", False)

    def test_every_window_opens_in_swedish_dark(self):
        self._open_all("sv", True)

    def test_every_window_opens_in_chinese_light(self):
        self._open_all("zh", False)


if __name__ == "__main__":
    unittest.main()
