import json
import os
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

import main


class QrExportV44Tests(unittest.TestCase):
    def test_grouped_paths_are_sanitized_numbered_and_ordered(self):
        paths = main.build_qr_export_paths(
            "C:/Export", 'Recette : test / spécial?', 3
        )
        self.assertEqual(
            [os.path.basename(path) for path in paths],
            [
                "qrcode_Recette _ test _ spécial__1sur3.png",
                "qrcode_Recette _ test _ spécial__2sur3.png",
                "qrcode_Recette _ test _ spécial__3sur3.png",
            ],
        )

    def test_all_parts_are_saved_as_valid_png_files(self):
        parts = ["première partie", "deuxième partie", "troisième partie"]
        with tempfile.TemporaryDirectory() as folder:
            paths = main.build_qr_export_paths(folder, "Ma recette", len(parts))
            main.save_qr_parts_atomically(
                parts, paths, lambda text: Image.new("RGB", (32, 32), "white")
            )
            self.assertEqual(len([path for path in paths if os.path.isfile(path)]), 3)
            for path in paths:
                with Image.open(path) as image:
                    self.assertEqual(image.format, "PNG")
                    image.verify()

    def test_failure_restores_existing_files_and_removes_new_files(self):
        parts = ["partie 1", "partie 2"]
        with tempfile.TemporaryDirectory() as folder:
            paths = main.build_qr_export_paths(folder, "Rollback", len(parts))
            with open(paths[0], "wb") as existing_file:
                existing_file.write(b"ancien fichier")

            real_replace = main.os.replace
            stage_commit_count = 0

            def fail_on_second_stage(source, destination):
                nonlocal stage_commit_count
                if os.path.basename(source).startswith(".qr-stage-"):
                    stage_commit_count += 1
                    if stage_commit_count == 2:
                        raise OSError("échec simulé")
                return real_replace(source, destination)

            with patch.object(main.os, "replace", side_effect=fail_on_second_stage):
                with self.assertRaises(OSError):
                    main.save_qr_parts_atomically(
                        parts,
                        paths,
                        lambda text: Image.new("RGB", (32, 32), "white"),
                    )

            with open(paths[0], "rb") as restored_file:
                self.assertEqual(restored_file.read(), b"ancien fichier")
            self.assertFalse(os.path.exists(paths[1]))
            self.assertFalse(
                any(name.startswith((".qr-stage-", ".qr-backup-")) for name in os.listdir(folder))
            )

    def test_new_labels_exist_in_all_supported_languages(self):
        with open(
            os.path.join(os.path.dirname(main.__file__), "i18n_desktop.json"),
            "r",
            encoding="utf-8",
        ) as translations_file:
            translations = json.load(translations_file)
        keys = {
            "qrcode_save_single_button",
            "qrcode_save_all_button",
            "qrcode_choose_folder_title",
            "qrcode_overwrite_all_confirm",
            "qrcode_saved_all_message",
        }
        languages = {"fr": translations["fr"], **translations["translations"]}
        for language in ("fr", "en", "es", "de"):
            self.assertTrue(keys.issubset(languages[language]), language)


if __name__ == "__main__":
    unittest.main()
