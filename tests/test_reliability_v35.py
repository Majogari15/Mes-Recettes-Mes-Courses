import json
import os
import tempfile
import threading
import tkinter as tk
import unittest
import zipfile
from pathlib import Path
from unittest import mock
from unittest.mock import patch

import main
from test_regressions import TempDataMixin


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


class DraftRecoveryTests(TempDataMixin, unittest.TestCase):
    """Instancie réellement RecipeFormWindow (et CookingModeWindow) pour
    vérifier le système de récupération après plantage (brouillon), plutôt
    que d'inspecter le texte source des méthodes."""

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

    def test_draft_autosave_skips_unchanged_edits_but_saves_real_changes(self):
        main.save_recipes([{
            "id": "e1", "name": "Ragoût", "default_persons": 4,
            "category": "Plat", "difficulty": "Facile", "images": [],
            "ingredients": [{"name": "Boeuf", "quantity": 500, "unit": "Gr"}],
            "steps": [],
        }])
        self.app.refresh_recipes()
        form = main.RecipeFormWindow(self.app, recipe_index=0)
        self.addCleanup(form.destroy)
        draft_path = Path(form._draft_file_path())

        # Rien n'a changé depuis l'ouverture du formulaire : pas de brouillon.
        form._save_draft_snapshot()
        self.assertFalse(draft_path.exists())

        # Une vraie modification doit, elle, produire un brouillon récupérable.
        form.name_entry.delete(0, tk.END)
        form.name_entry.insert(0, "Ragoût modifié")
        form._save_draft_snapshot()
        self.assertTrue(draft_path.exists())
        saved = json.loads(draft_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["name"], "Ragoût modifié")

    def test_legacy_unchanged_draft_is_removed_without_prompt(self):
        main.save_recipes([{
            "id": "e2", "name": "Risotto", "default_persons": 4,
            "category": "Plat", "difficulty": "Facile", "images": [],
            "ingredients": [{"name": "Riz", "quantity": 300, "unit": "Gr"}],
            "steps": [],
        }])
        self.app.refresh_recipes()

        probe = main.RecipeFormWindow(self.app, recipe_index=0)
        snapshot = probe._collect_draft_snapshot()
        draft_path = Path(probe._draft_file_path())
        probe.destroy()

        # Un ancien brouillon strictement identique à l'état non modifié,
        # comme en laissaient d'anciennes versions même sans modification.
        draft_path.write_text(json.dumps(snapshot), encoding="utf-8")
        self.assertTrue(draft_path.exists())

        with patch.object(main, "ask_yes_no") as fake_ask:
            form = main.RecipeFormWindow(self.app, recipe_index=0)
            self.addCleanup(form.destroy)

        fake_ask.assert_not_called()
        self.assertFalse(draft_path.exists())

    def test_normal_edit_save_deletes_the_crash_draft(self):
        # L'ingrédient doit déjà exister dans le catalogue global, sinon
        # save_recipe() ouvrirait une vraie boîte de dialogue de résolution
        # (UnknownIngredientsDialog) qui resterait bloquée sans interaction.
        main.save_ingredients(["Oeuf"])
        main.save_recipes([{
            "id": "e3", "name": "Quiche", "default_persons": 4,
            "category": "Plat", "difficulty": "Facile", "images": [],
            "ingredients": [{"name": "Oeuf", "quantity": 3, "unit": "pièce"}],
            "steps": [],
        }])
        self.app.refresh_recipes()
        self.app.refresh_ingredients()
        form = main.RecipeFormWindow(self.app, recipe_index=0)
        draft_path = Path(form._draft_file_path())
        draft_path.write_text(json.dumps({"saved_at": "2024-01-01T00:00:00"}), encoding="utf-8")
        self.assertTrue(draft_path.exists())

        form.save_recipe()

        self.assertFalse(form.winfo_exists())
        self.assertFalse(draft_path.exists())

    def test_normal_cancel_deletes_the_crash_draft(self):
        main.save_recipes([{
            "id": "e4", "name": "Pâtes", "default_persons": 2,
            "category": "Plat", "difficulty": "Facile", "images": [],
            "ingredients": [], "steps": [],
        }])
        self.app.refresh_recipes()
        form = main.RecipeFormWindow(self.app, recipe_index=0)
        draft_path = Path(form._draft_file_path())
        draft_path.write_text(json.dumps({"saved_at": "2024-01-01T00:00:00"}), encoding="utf-8")
        self.assertTrue(draft_path.exists())
        scheduled_id = form._draft_after_id
        self.assertIsNotNone(scheduled_id)

        form._close_without_draft()

        self.assertFalse(draft_path.exists())
        # after_cancel a bien été appelé : l'identifiant "after" programmé
        # n'existe plus dans la file d'attente Tcl de la fenêtre parente.
        with self.assertRaises(tk.TclError):
            self.app.tk.call("after", "info", scheduled_id)

    def test_cooking_mode_mark_as_cooked_uses_five_argument_callback(self):
        main.save_recipes([{
            "id": "cm1", "name": "Curry", "default_persons": 2,
            "category": "Plat", "difficulty": "Facile", "images": [],
            "ingredients": [], "steps": [],
        }])
        self.app.refresh_recipes()
        recipe = main.find_recipe_by_id(self.app.recipes, "cm1")
        win = main.CookingModeWindow(self.app, recipe, 2)
        self.addCleanup(win.destroy)

        class FakeCookLogEntryDialog:
            def __init__(fake_self, app, recipe_name, on_done, persons=None):
                on_done("Note", "Commentaire", None, rating=4, cooked_persons=persons)

        with patch.object(main, "CookLogEntryDialog", FakeCookLogEntryDialog), \
             patch.object(main.messagebox, "showinfo"), \
             patch.object(main.messagebox, "showerror"):
            win.mark_as_cooked()

        saved = main.find_recipe_by_id(main.load_recipes(), "cm1")
        self.assertEqual(len(saved["cook_log"]), 1)
        entry = saved["cook_log"][0]
        self.assertEqual(entry["comment"], "Commentaire")
        self.assertEqual(entry["rating"], 4)
        self.assertEqual(entry["persons"], 2)
        self.assertIsInstance(entry["persons"], int)


if __name__ == "__main__":
    unittest.main()
