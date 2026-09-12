import json
import math
import os
import tempfile
import unittest
import zipfile
from pathlib import Path

import main


class CoreV23Tests(unittest.TestCase):
    def test_positive_number_rejects_nonfinite_and_nonpositive(self):
        for value in ("nan", "NaN", "inf", "-inf", "0", "-2"):
            with self.assertRaises((ValueError, TypeError)):
                main.parse_positive_number(value)
        self.assertEqual(main.parse_positive_number("4,5"), 4.5)

    def test_atomic_json_rejects_nan(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "x.json"
            with self.assertRaises(ValueError):
                main._atomic_write_json(path, {"x": float("nan")})

    def test_recipe_validation(self):
        with self.assertRaises(ValueError):
            main.validate_recipes_payload({})
        recipe = {
            "name": "Test", "default_persons": 4,
            "ingredients": [{"name": "Farine", "quantity": 100, "unit": "Gr"}],
            "images": ["../../danger.txt", "ok.jpg"],
        }
        out = main.validate_recipes_payload([recipe])[0]
        self.assertTrue(out.get("id"))
        self.assertEqual(out["images"], ["ok.jpg"])
        with self.assertRaises(ValueError):
            main.validate_recipes_payload([{"name":"Bad", "ingredients":[{"name":"X","quantity":float("nan"),"unit":"Gr"}]}])

    def test_cooklog_images_owned(self):
        recipe={"images":["a.jpg"],"cook_log":[{"photo":"b.jpg"},{"photo":"../../x"}]}
        self.assertEqual(main.get_all_recipe_image_refs(recipe), ["a.jpg","b.jpg"])

    def test_unit_conversions_and_totals(self):
        recipe1={"ingredients":[{"name":"Farine","quantity":100,"unit":"Gr"}]}
        recipe2={"ingredients":[{"name":"Farine","quantity":0.1,"unit":"Kilo"}]}
        grouped=main.compute_grouped_totals([(recipe1,1),(recipe2,1)])
        flat=[x for _,items in grouped for x in items]
        flour=[x for x in flat if main.ingredient_sort_key(x[0])==main.ingredient_sort_key("Farine")][0]
        self.assertEqual(flour[1], 200)
        self.assertEqual(flour[2], "Gr")
        self.assertEqual(main.compatible_unit_quantities(10,"cl",100,"ml"), ("volume",100.0,100.0))

    def test_parser_extended_forms(self):
        p=main.parse_ingredient_line("2-3 carottes")
        self.assertEqual((p["quantity"],p["unit"],p["name"]),(2.0,"pièce","Carottes"))
        p=main.parse_ingredient_line("2 x 400 g tomates")
        self.assertEqual((p["quantity"],p["unit"],p["name"]),(800.0,"Gr","Tomates"))
        p=main.parse_ingredient_line("1 c. à soupe de sucre")
        self.assertEqual((p["quantity"],p["unit"],p["name"]),(1.0,"cuillère à soupe","Sucre"))
        p=main.parse_ingredient_line("sel")
        self.assertEqual((p["quantity"],p["unit"],p["name"]),(1,"au goût","Sel"))

    def test_decrement_pantry_persons(self):
        with tempfile.TemporaryDirectory() as td:
            old_file=main.PANTRY_FILE
            try:
                main.PANTRY_FILE=os.path.join(td,"pantry.json")
                main.save_pantry({main.ingredient_sort_key("Farine"):{"name":"Farine","quantity":1000,"unit":"Gr","threshold":None}})
                recipe={"ingredients":[{"name":"Farine","quantity":100,"unit":"Gr"}]}
                self.assertEqual(main.decrement_pantry_for_recipe(recipe,4),1)
                self.assertAlmostEqual(main.load_pantry()[main.ingredient_sort_key("Farine")]["quantity"],600)
            finally:
                main.PANTRY_FILE=old_file

    def test_deep_backup_validators(self):
        with self.assertRaises(ValueError):
            main.validate_pantry_payload({"x":{"name":"X","quantity":float("inf"),"unit":"Gr"}})
        with self.assertRaises(ValueError):
            main.validate_saved_lists_payload([{"name":"L","items":[{"name":"X","quantity":float("nan"),"unit":"Gr"}]}])
        good=main.validate_menus_payload([{"name":"M","items":[{"recipe_name":"R","persons":4}]}])
        self.assertEqual(good[0]["items"][0]["persons"],4.0)

    def test_full_restore_replace_clears_missing_file_and_rolls_back_on_invalid(self):
        with tempfile.TemporaryDirectory() as td:
            td=Path(td)
            old={name:getattr(main,name) for name in ["DATA_DIR","IMAGES_DIR","PANTRY_FILE","DATA_FILE"]}
            old_user=list(main.USER_DATA_FILES)
            try:
                main.DATA_DIR=str(td)
                main.IMAGES_DIR=str(td/"images"); (td/"images").mkdir()
                main.PANTRY_FILE=str(td/"pantry.json")
                main.DATA_FILE=str(td/"recipes.json")
                (td/"pantry.json").write_text(json.dumps({"old":{"name":"Old","quantity":1,"unit":"pièce"}}),encoding="utf8")
                z=td/"good.zip"
                recipes=[{"id":"r1","name":"R","default_persons":1,"ingredients":[{"name":"X","quantity":1,"unit":"pièce"}],"images":[]}]
                with zipfile.ZipFile(z,"w") as f:
                    f.writestr("recipes.json",json.dumps(recipes))
                main.restore_from_zip(str(z),merge=False)
                self.assertFalse((td/"pantry.json").exists())
                self.assertEqual(main.load_recipes()[0]["id"],"r1")

                # Invalid data is rejected before mutation.
                (td/"pantry.json").write_text(json.dumps({"keep":{"name":"Keep","quantity":2,"unit":"pièce"}}),encoding="utf8")
                bad=td/"bad.zip"
                with zipfile.ZipFile(bad,"w") as f:
                    f.writestr("recipes.json",json.dumps(recipes))
                    f.writestr("pantry.json",'{bad json')
                with self.assertRaises(Exception):
                    main.restore_from_zip(str(bad),merge=False)
                self.assertTrue((td/"pantry.json").exists())
            finally:
                for name,val in old.items(): setattr(main,name,val)
                main.USER_DATA_FILES[:] = old_user

    def test_recipe_ref_helpers_survive_rename(self):
        recipes=[{"id":"abc","name":"Nouveau nom","ingredients":[]}]
        ref={"recipe_id":"abc","recipe_name":"Ancien nom","persons":4}
        found=main.find_recipe_by_ref(recipes,ref)
        self.assertEqual(found["name"],"Nouveau nom")
        enriched=main.enrich_recipe_reference(ref,recipes)
        self.assertEqual(enriched["recipe_name"],"Nouveau nom")

    def test_translation_completeness(self):
        fr=set(main.FRENCH_STRINGS)
        for lang in ("en","es","de"):
            self.assertEqual(fr-set(main.TRANSLATIONS.get(lang,{})),set())


if __name__ == '__main__':
    unittest.main()
