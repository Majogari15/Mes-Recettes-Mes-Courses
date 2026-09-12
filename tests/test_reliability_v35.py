import inspect
import json
import os
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import main


class ReliabilityV35Tests(unittest.TestCase):
    def setUp(self):
        main._clear_corruption_guards()
        main._ALLOW_CORRUPT_OVERWRITE.clear()

    def tearDown(self):
        main._clear_corruption_guards()
        main._ALLOW_CORRUPT_OVERWRITE.clear()

    def test_record_cooking_is_one_complete_recipe_write(self):
        with tempfile.TemporaryDirectory() as td:
            old = main.DATA_FILE
            try:
                main.DATA_FILE = os.path.join(td, "recipes.json")
                main.save_recipes([{
                    "id": "r1", "name": "Soupe", "ingredients": [],
                    "times_cooked": 0, "cooked_dates": [], "cook_log": []
                }])
                current = main.record_recipe_cooking(
                    "r1", "Soupe", "Ma note", "Très bon", None, 4, 3
                )
                self.assertEqual(current["times_cooked"], 1)
                self.assertEqual(len(current["cooked_dates"]), 1)
                self.assertEqual(current["cook_log"][0]["comment"], "Très bon")
                self.assertEqual(current["cook_log"][0]["rating"], 4)
                self.assertEqual(current["cook_log"][0]["persons"], 3)
            finally:
                main.DATA_FILE = old

    def test_both_cooking_entry_points_use_five_argument_callback(self):
        source = inspect.getsource(main.CookingModeWindow.mark_as_cooked)
        self.assertIn(
            "def _on_log_done(note, comment, photo_filename, rating=0, cooked_persons=None)",
            source,
        )
        self.assertIn("persons=cooked_persons_display", source)

    def test_auto_backup_exists_without_recipes_file(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            images = root / "images"
            backups = root / "backups"
            images.mkdir()
            old = {
                name: getattr(main, name)
                for name in ["DATA_DIR", "DATA_FILE", "IMAGES_DIR", "BACKUPS_DIR", "SETTINGS_FILE"]
            }
            old_user = list(main.USER_DATA_FILES)
            try:
                main.DATA_DIR = str(root)
                main.DATA_FILE = str(root / "recipes.json")
                main.IMAGES_DIR = str(images)
                main.BACKUPS_DIR = str(backups)
                main.SETTINGS_FILE = str(root / "settings.json")
                main.USER_DATA_FILES[:] = ["recipes.json", "pantry.json"]
                (root / "pantry.json").write_text('{"riz":{"name":"Riz"}}', encoding="utf-8")
                main.maybe_create_auto_backup()
                archives = list(backups.glob("*.zip"))
                self.assertEqual(len(archives), 1)
                with zipfile.ZipFile(archives[0]) as zf:
                    self.assertIn("pantry.json", zf.namelist())
            finally:
                for name, value in old.items():
                    setattr(main, name, value)
                main.USER_DATA_FILES[:] = old_user

    def test_normal_edit_save_deletes_the_crash_draft(self):
        source = inspect.getsource(main.RecipeFormWindow.save_recipe)
        self.assertIn("self._delete_draft()", source)

    def test_normal_cancel_deletes_the_crash_draft(self):
        source = inspect.getsource(main.RecipeFormWindow._close_without_draft)
        self.assertIn("self._delete_draft()", source)
        self.assertIn("self.after_cancel", source)

    def test_unchanged_edit_does_not_create_a_draft_prompt(self):
        source = inspect.getsource(main.RecipeFormWindow._save_draft_snapshot)
        self.assertIn("_draft_baseline_signature", source)
        self.assertIn("unchanged", source)
        self.assertIn("os.remove(path)", source)

    def test_legacy_unchanged_draft_is_removed_without_prompt(self):
        source = inspect.getsource(main.RecipeFormWindow._maybe_restore_draft)
        self.assertIn("_draft_signature(data)", source)
        self.assertIn("self._delete_draft()", source)

    def test_corrupt_recipes_are_quarantined_and_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as td:
            old = main.DATA_FILE
            try:
                path = Path(td) / "recipes.json"
                path.write_text("{invalid", encoding="utf-8")
                main.DATA_FILE = str(path)
                self.assertEqual(main.load_recipes(), [])
                info = main.get_corrupted_data_files()
                self.assertEqual(len(info), 1)
                self.assertTrue(Path(info[0]["backup"]).exists())
                with self.assertRaises(main.CorruptDataError):
                    main.save_recipes([{"id": "new", "name": "Nouveau", "ingredients": []}])
                self.assertEqual(path.read_text(encoding="utf-8"), "{invalid")
            finally:
                main.DATA_FILE = old

    def test_invalid_recipe_entry_also_blocks_destructive_rewrite(self):
        with tempfile.TemporaryDirectory() as td:
            old = main.DATA_FILE
            try:
                path = Path(td) / "recipes.json"
                path.write_text('[{"name":"Valide","ingredients":[]},42]', encoding="utf-8")
                main.DATA_FILE = str(path)
                loaded = main.load_recipes()
                self.assertEqual(len(loaded), 1)
                with self.assertRaises(main.CorruptDataError):
                    main.save_recipes(loaded)
            finally:
                main.DATA_FILE = old

    def test_delete_to_trash_rolls_back_both_json_files(self):
        with tempfile.TemporaryDirectory() as td:
            old_data, old_trash = main.DATA_FILE, main.TRASH_FILE
            try:
                main.DATA_FILE = os.path.join(td, "recipes.json")
                main.TRASH_FILE = os.path.join(td, "trash.json")
                recipe = {"id": "r1", "name": "Test", "ingredients": []}
                main.save_recipes([recipe])
                main.save_trash([])
                with mock.patch("main.save_recipes", side_effect=OSError("disk full")):
                    with self.assertRaises(OSError):
                        main.delete_recipe_to_trash(recipe_id="r1")
                self.assertEqual(main.load_recipes()[0]["id"], "r1")
                self.assertEqual(main.load_trash(), [])
            finally:
                main.DATA_FILE, main.TRASH_FILE = old_data, old_trash

    def test_full_restore_streams_image_to_disk(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "images").mkdir()
            old = {name: getattr(main, name) for name in ["DATA_DIR", "DATA_FILE", "IMAGES_DIR"]}
            old_user = list(main.USER_DATA_FILES)
            try:
                main.DATA_DIR = str(root)
                main.DATA_FILE = str(root / "recipes.json")
                main.IMAGES_DIR = str(root / "images")
                main.USER_DATA_FILES[:] = ["recipes.json"]
                archive = root / "restore.zip"
                recipes = [{"id": "r1", "name": "R", "ingredients": [], "images": ["photo.jpg"]}]
                payload = b"image-data" * 10000
                with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
                    zf.writestr("recipes.json", json.dumps(recipes))
                    zf.writestr("images/photo.jpg", payload)
                main.restore_from_zip(str(archive), merge=False)
                self.assertEqual((root / "images" / "photo.jpg").read_bytes(), payload)
            finally:
                for name, value in old.items():
                    setattr(main, name, value)
                main.USER_DATA_FILES[:] = old_user

    def test_permanent_delete_preserves_an_image_still_used_elsewhere(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            images = root / "images"
            images.mkdir()
            old = {
                name: getattr(main, name)
                for name in ["DATA_FILE", "TRASH_FILE", "IMAGES_DIR", "DRAFTS_DIR"]
            }
            try:
                main.DATA_FILE = str(root / "recipes.json")
                main.TRASH_FILE = str(root / "trash.json")
                main.IMAGES_DIR = str(images)
                main.DRAFTS_DIR = str(root / "drafts")
                (images / "shared.jpg").write_bytes(b"shared")
                main.save_recipes([{"id": "keep", "name": "Keep", "ingredients": [], "images": ["shared.jpg"]}])
                main.save_trash([{"recipe": {"id": "old", "name": "Old", "ingredients": [], "images": ["shared.jpg"]}}])
                main.permanently_delete_trash_entries([0])
                self.assertTrue((images / "shared.jpg").exists())
            finally:
                for name, value in old.items():
                    setattr(main, name, value)

    def test_cancelled_backup_does_not_replace_destination(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "images").mkdir()
            destination = root / "backup.zip"
            destination.write_bytes(b"previous")
            cancel = threading.Event()
            cancel.set()
            old = {name: getattr(main, name) for name in ["DATA_DIR", "IMAGES_DIR"]}
            old_user = list(main.USER_DATA_FILES)
            try:
                main.DATA_DIR = str(root)
                main.IMAGES_DIR = str(root / "images")
                main.USER_DATA_FILES[:] = ["recipes.json"]
                (root / "recipes.json").write_text("[]", encoding="utf-8")
                with self.assertRaises(main.OperationCancelled):
                    main.build_full_backup_zip(destination, cancel_event=cancel)
                self.assertEqual(destination.read_bytes(), b"previous")
            finally:
                for name, value in old.items():
                    setattr(main, name, value)
                main.USER_DATA_FILES[:] = old_user

    def test_pdf_keys_and_test_launcher_are_complete(self):
        for key in (
            "common_close", "cookbookpdf_title", "cookbookpdf_generated",
            "cookbookpdf_toc_heading",
        ):
            self.assertNotEqual(main.t(key), key)
        launcher = (Path(main.__file__).parent / "Executer_les_tests.bat").read_text(encoding="utf-8")
        self.assertIn("unittest discover", launcher)
        self.assertIn('test_*.py', launcher)


if __name__ == "__main__":
    unittest.main()
