import unittest
from unittest.mock import patch

import main


class QrImportV42Tests(unittest.TestCase):
    def _payload(self):
        recipe = {
            "name": "Barramundi en croûte persillée & tomates rôties",
            "default_persons": 2,
            "difficulty": "Facile",
            "description": "Préchauffez à 210 °C. Ajoutez l’huile d’olive. " * 45,
            "personal_notes": "À servir immédiatement.",
            "ingredients": [
                {"name": "Échalote", "quantity": 1, "unit": "pièce"},
                {"name": "Crème fraîche", "quantity": 10, "unit": "cl"},
            ],
        }
        return main._recipe_to_mobile_qr_payload(recipe, 2)

    def test_latin1_mojibake_is_repaired_only_with_matching_checksum(self):
        payload = self._payload()
        parts = main._split_mobile_qr_parts(payload, max_chunk_bytes=260)
        mojibake_parts = [part.encode("utf-8").decode("latin-1") for part in parts]
        with patch.object(main, "_decode_qr_image_file", side_effect=mojibake_parts):
            prefill = main.import_recipe_prefill_from_qr_images(
                [f"part-{index}.png" for index in range(len(parts))]
            )
        self.assertEqual(
            prefill["name"], "Barramundi en croûte persillée & tomates rôties"
        )
        self.assertIn("huile d’olive", prefill["description"])
        self.assertEqual(prefill["personal_notes"], "À servir immédiatement.")

    def test_real_corruption_is_still_rejected(self):
        payload = self._payload()
        parts = main._split_mobile_qr_parts(payload, max_chunk_bytes=260)
        parts[1] = parts[1][:-1] + ("X" if parts[1][-1] != "X" else "Y")
        with patch.object(main, "_decode_qr_image_file", side_effect=parts):
            with self.assertRaises(main.QrImportChecksumError):
                main.import_recipe_prefill_from_qr_images(
                    [f"part-{index}.png" for index in range(len(parts))]
                )

    def test_each_part_can_use_a_different_zbar_encoding(self):
        recipe = {
            "name": "Financiers",
            "default_persons": 2,
            "description": "Mélanger " + ("a" * 760),
            "ingredients": [
                {"name": "Framboises fraîches", "quantity": 62.5, "unit": "Gr"},
                {"name": "Citron vert", "quantity": 0.5, "unit": "pièce"},
            ],
        }
        payload = main._recipe_to_mobile_qr_payload(recipe, 2)
        parts = main._split_mobile_qr_parts(payload, max_chunk_bytes=800)
        self.assertEqual(len(parts), 2)
        # Comportements réellement constatés avec ZBar sur les deux images :
        # première partie interprétée en Latin-1, seconde en Shift-JIS.
        decoded_parts = [
            parts[0].encode("utf-8").decode("latin-1"),
            parts[1].encode("utf-8").decode("shift_jis"),
        ]
        with patch.object(main, "_decode_qr_image_file", side_effect=decoded_parts):
            prefill = main.import_recipe_prefill_from_qr_images(["part-1.png", "part-2.png"])
        self.assertEqual(prefill["name"], "Financiers")
        self.assertEqual(prefill["ingredients"][0]["name"], "Framboises fraîches")
        self.assertEqual(prefill["ingredients"][1]["unit"], "pièce")

    def test_shift_jis_halfwidth_markers_are_repaired(self):
        damaged = "fraîches".encode("utf-8").decode("shift_jis")
        self.assertIn("fraîches", main._qr_chunk_repair_candidates(damaged))


if __name__ == "__main__":
    unittest.main()
