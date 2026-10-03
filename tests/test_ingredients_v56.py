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
        return json.loads((ROOT / 'data' / filename).read_text(encoding='utf-8'))

    def test_catalogue_names_have_complete_records(self):
        # Catalogue repris de l'app mobile (~10 000 ingrédients) : chaque nom
        # a ses allergènes et ses traductions ; quelques-uns n'ont pas de
        # valeurs nutritionnelles connues (absence assumée, jamais inventée).
        names = self.read('ingredients_par_defaut.json')
        self.assertGreater(len(names), 9900)
        self.assertEqual(len(names), len({main.ingredient_sort_key(n) for n in names}))
        self.assertFalse([n for n in names if 'œ' in n.lower()])
        for filename in ['ingredient_allergenes.json'] + [
            f'ingredient_translations_{lang}.json' for lang in ('en', 'es', 'de', 'it', 'pt', 'id', 'no', 'sv')
        ]:
            self.assertEqual(set(names), set(self.read(filename)), filename)
        nutrition = self.read('valeurs_nutritionnelles.json')
        self.assertTrue(set(nutrition) <= set(names))
        self.assertLess(len(names) - len(nutrition), 100)

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
        # Base reprise du mobile : les anciennes estimations non sourcées
        # ont été remplacées par des valeurs CIQUAL/USDA/Open Food Facts.
        sources = ('_ciqual', '_ciqual_extra', '_usda', '_usda_extra', '_openfoodfacts')
        unsourced = [n for n, v in data.items() if not any(s in v for s in sources)]
        self.assertLess(len(unsourced), 20, unsourced)
        self.assertIn('_ciqual', data['Ail des ours'])

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


class LargeCatalogueTests(unittest.TestCase):
    def test_duplicate_scan_skips_catalogue_pairs_but_finds_user_typos(self):
        catalogue = main.load_default_ingredients()
        names = catalogue + ['Tomatte', 'Ma sauce maison']
        pairs = main.find_similar_ingredient_pairs(names, reference_names=catalogue)
        found = {frozenset((a, b)) for a, b, _r in pairs}
        self.assertIn(frozenset(('Tomate', 'Tomatte')), found)
        self.assertTrue(all({a, b} & {'Tomatte', 'Ma sauce maison'} for a, b, _r in pairs))
        # Sans catalogue de référence, comportement d'origine inchangé.
        plain = main.find_similar_ingredient_pairs(['Tomate', 'Tomates', 'Beurre'])
        self.assertEqual([(p[0], p[1]) for p in plain], [('Tomate', 'Tomates')])

    def test_lookup_index_follows_data_changes(self):
        data = {'échalote': 1}
        self.assertEqual(main._lookup_ingredient_data(data, 'Echalote'), 1)
        data['ail des ours'] = 2
        self.assertEqual(main._lookup_ingredient_data(data, 'Ail des Ours '), 2)

    def test_close_ranking_still_prefers_real_match_in_big_list(self):
        ranked = main.rank_close_ingredients('Tomatte', main.load_default_ingredients())
        self.assertEqual(ranked[0][1], 'Tomate')
        self.assertGreaterEqual(ranked[0][0], 0.75)
        self.assertEqual(main.rank_close_ingredients('Tomates', ['Tomate', 'Beurre'])[0], (0.98, 'Tomate'))


if __name__ == '__main__':
    unittest.main()
