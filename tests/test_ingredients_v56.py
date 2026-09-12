import json
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import main


class IngredientDataTests(unittest.TestCase):
    def read(self, filename):
        return json.loads((ROOT / filename).read_text(encoding='utf-8'))

    def test_all_1030_names_have_complete_records(self):
        names = self.read('ingredients_par_defaut.json')
        self.assertEqual(1030, len(names))
        self.assertEqual(len(names), len(set(names)))
        for filename in ['valeurs_nutritionnelles.json', 'ingredient_allergenes.json'] + [
            f'ingredient_translations_{lang}.json' for lang in ('en', 'es', 'de')
        ]:
            self.assertEqual(set(names), set(self.read(filename)))

    def test_all_nutrients_are_finite_nonnegative(self):
        for name, entry in self.read('valeurs_nutritionnelles.json').items():
            for key in ('kcal', 'protein_g', 'carbs_g', 'fat_g'):
                self.assertIsInstance(entry[key], (int, float), (name, key))
                self.assertTrue(math.isfinite(entry[key]) and entry[key] >= 0, (name, key))

    def test_confirmed_allergen_regressions(self):
        data = self.read('ingredient_allergenes.json')
        for name in ('Groseille à maquereau', 'Courge spaghetti'):
            self.assertEqual([], data[name])
        for name in ('Lait', 'Beurre', 'Beurre noisette', 'Ghee'):
            self.assertEqual(['Lactose'], data[name])
        self.assertEqual(['Fruits à coque'], data['Noix'])
        self.assertEqual(['Poisson'], data['Oeufs de saumon'])
        self.assertIn('Gluten', data['Épeautre'])
        self.assertIn('Poisson', data['Anchoïade'])
        for flags in data.values():
            self.assertTrue(set(flags) <= set(main.ALLERGENS))

    def test_ciqual_reference_values_and_provenance(self):
        data = self.read('valeurs_nutritionnelles.json')
        self.assertEqual(346, data['Ail en poudre']['kcal'])
        self.assertEqual(63.7, data['Ail en poudre']['carbs_g'])
        self.assertEqual('11023', data['Ail en poudre']['_ciqual']['code'])
        self.assertNotEqual(data['Ail']['kcal'], data['Ail en poudre']['kcal'])
        audit = self.read('AUDIT_INGREDIENTS_v56.json')
        sourced = {n for n,v in data.items() if '_ciqual' in v}
        self.assertEqual(audit['coverage']['ciqual_matches'], len(sourced))
        self.assertEqual(set(data) - sourced, set(audit['nutrition_still_unverified']))
        for change in audit['nutrition_changes']:
            self.assertEqual(change['after'], data[change['ingredient']])
            self.assertEqual('100g', change['after']['_ciqual']['basis'])

    def test_translation_fixes(self):
        self.assertEqual('Four-spice blend', self.read('ingredient_translations_en.json')['Quatre épices'])
        self.assertEqual('Azúcar granulado fino', self.read('ingredient_translations_es.json')['Sucre en poudre'])
        self.assertIn('T65', self.read('ingredient_translations_de.json')['Farine de blé T65'])

    def test_spelling_variants_are_not_unknown(self):
        with patch.object(main, 'get_ingredient_override', return_value=None):
            self.assertEqual(main.get_ingredient_nutrition('Échalote'), main.get_ingredient_nutrition('echalote'))
            self.assertEqual(main.get_ingredient_allergens('Oeufs'), main.get_ingredient_allergens('Œufs'))
            self.assertIsNone(main.get_ingredient_nutrition('un aliment inconnu'))

    def test_unique_normalization_only(self):
        self.assertIsNone(main._lookup_ingredient_data({'Ail': 1}, 'Ail en poudre'))
        self.assertIsNone(main._lookup_ingredient_data({'É': 1, 'E': 2}, 'e'))

    def test_personal_values_remain_priority(self):
        override = {'nutrition': {'kcal': 10, 'protein_g': 2, 'carbs_g': 3, 'fat_g': 0}, 'allergens': []}
        with patch.object(main, 'get_ingredient_override', return_value=override):
            self.assertEqual(override['nutrition'], main.get_ingredient_nutrition('Lait'))
            self.assertEqual([], main.get_ingredient_allergens('Lait'))

    def test_unknown_macros_are_not_silently_zero(self):
        recipe = {'ingredients': [{'name':'test', 'unit':'g', 'quantity':100}]}
        with patch.object(main, 'get_ingredient_nutrition', return_value={'kcal': 80}):
            totals, count, total = main.compute_recipe_nutrition(recipe, 1)
            self.assertEqual((0,1), (count,total))
        with patch.object(main, 'get_ingredient_nutrition', return_value={'kcal':0,'protein_g':0,'carbs_g':0,'fat_g':0}):
            totals, count, total = main.compute_recipe_nutrition(recipe, 1)
            self.assertEqual(1,count)

    def test_ciqual_recipe_totals_scale_correctly(self):
        recipe = {'ingredients':[{'name':'Ail en poudre','unit':'g','quantity':10}]}
        with patch.object(main, 'get_ingredient_override', return_value=None):
            totals, count, total = main.compute_recipe_nutrition(recipe, 2)
        self.assertAlmostEqual(69.2, totals['kcal'])
        self.assertEqual((1,1), (count,total))

    def test_milk_display_keeps_legacy_storage_key(self):
        for lang in ('fr','en','es','de'):
            with patch.object(main,'CURRENT_LANGUAGE',lang):
                self.assertNotEqual('Lactose',main.translate_allergen_name('Lactose'))
        self.assertIn('Lactose',main.ALLERGENS)


if __name__ == '__main__':
    unittest.main()
