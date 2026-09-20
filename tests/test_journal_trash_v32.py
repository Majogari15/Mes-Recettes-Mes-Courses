
import inspect
import tempfile
import unittest
from pathlib import Path
import main

class JournalTrashV32Tests(unittest.TestCase):
    def test_cooklog_callback_persists_comment_and_persons(self):
        src = inspect.getsource(main.record_recipe_cooking)
        self.assertIn('"comment": comment', src)
        self.assertIn('"persons": persons', src)
        self.assertIn('now.isoformat(timespec="seconds")', src)

    def test_cooklog_window_displays_comment_and_note(self):
        src = inspect.getsource(main.CookLogWindow)
        self.assertIn('entry.get("comment")', src)
        self.assertIn('cooklog_comment_heading', src)
        self.assertIn('cooklog_note_heading', src)

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

    def test_trash_paths_cleanup_draft(self):
        delete = inspect.getsource(main.delete_recipe_to_trash)
        restore = inspect.getsource(main.restore_recipe_from_trash)
        permanent = inspect.getsource(main.permanently_delete_trash_entries)
        self.assertIn("delete_recipe_draft(removed)", delete)
        self.assertIn("delete_recipe_draft(recipe)", restore)
        self.assertIn("delete_recipe_draft(recipe)", permanent)

if __name__ == "__main__":
    unittest.main()
