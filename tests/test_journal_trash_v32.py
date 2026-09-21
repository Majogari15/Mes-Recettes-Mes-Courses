import tempfile
import tkinter as tk
import unittest
from pathlib import Path

import main
from test_regressions import TempDataMixin


class JournalTrashV32Tests(TempDataMixin, unittest.TestCase):
    def test_cooklog_callback_persists_comment_and_persons(self):
        main.save_recipes([{
            "id": "r1", "name": "Quiche", "default_persons": 4,
            "category": "Plat", "difficulty": "Facile", "images": [],
            "ingredients": [], "steps": [],
        }])
        main.record_recipe_cooking(
            "r1", "Quiche", note="Note", comment="Un peu trop cuite",
            photo_filename=None, rating=3, persons=6,
        )
        recipe = main.find_recipe_by_id(main.load_recipes(), "r1")
        entry = recipe["cook_log"][0]
        self.assertEqual(entry["comment"], "Un peu trop cuite")
        self.assertEqual(entry["persons"], 6)
        # Précision à la seconde (pas de microsecondes) pour rester lisible
        # une fois affiché/trié dans CookLogWindow.
        self.assertRegex(entry["date"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")

    def test_cooklog_window_displays_comment_and_note(self):
        recipe = {
            "id": "r2", "name": "Tarte", "times_cooked": 1,
            "cook_log": [{
                "date": "2024-05-01T12:00:00",
                "note": "Note de test bien visible",
                "comment": "Commentaire de test bien visible",
                "rating": 0, "persons": None, "photo": None,
            }],
        }
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.addCleanup(root.destroy)
        root.withdraw()
        win = main.CookLogWindow(root, recipe)
        self.addCleanup(win.destroy)

        texts = []

        def collect(widget):
            if "text" in widget.keys():
                texts.append(widget.cget("text"))
            for child in widget.winfo_children():
                collect(child)

        collect(win)

        self.assertIn(main.t("cooklog_note_heading"), texts)
        self.assertIn(main.t("cooklog_comment_heading"), texts)
        self.assertIn("Note de test bien visible", texts)
        self.assertIn("Commentaire de test bien visible", texts)

    def test_recipe_draft_can_be_removed(self):
        old_drafts = main.DRAFTS_DIR
        try:
            with tempfile.TemporaryDirectory() as d:
                main.DRAFTS_DIR = d
                recipe = {"id": "abc123", "name": "Test"}
                p = Path(d) / "recipe_abc123.json"
                p.write_text("{}", encoding="utf-8")
                self.assertTrue(p.exists())
                main.delete_recipe_draft(recipe)
                self.assertFalse(p.exists())
        finally:
            main.DRAFTS_DIR = old_drafts

    def _write_draft(self, recipe_id):
        path = Path(main.recipe_draft_path(recipe_id))
        path.write_text("{}", encoding="utf-8")
        return path

    def test_delete_to_trash_cleans_up_the_draft(self):
        main.save_recipes([{"id": "d1", "name": "Soupe", "images": []}])
        draft = self._write_draft("d1")
        self.assertTrue(draft.exists())

        main.delete_recipe_to_trash(recipe_id="d1")

        self.assertFalse(draft.exists())

    def test_restore_from_trash_cleans_up_the_draft(self):
        main.save_recipes([])
        main.save_trash([{
            "recipe": {"id": "d2", "name": "Salade", "images": []},
            "deleted_at": "2024-01-01T00:00:00",
        }])
        draft = self._write_draft("d2")
        self.assertTrue(draft.exists())

        main.restore_recipe_from_trash(0)

        self.assertFalse(draft.exists())

    def test_permanent_delete_cleans_up_the_draft(self):
        main.save_recipes([])
        main.save_trash([{
            "recipe": {"id": "d3", "name": "Gratin", "images": []},
            "deleted_at": "2024-01-01T00:00:00",
        }])
        draft = self._write_draft("d3")
        self.assertTrue(draft.exists())

        main.permanently_delete_trash_entries()

        self.assertFalse(draft.exists())


if __name__ == "__main__":
    unittest.main()
