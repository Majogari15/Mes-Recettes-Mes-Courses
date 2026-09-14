"""Offline publisher fixtures: full URL-import pipeline, no live network."""
import io
import json
import unittest
from email.message import Message
from unittest.mock import patch
import main

class ImportV75Tests(unittest.TestCase):
    def fetch(self, page='', **values):
        data = {'@type': 'Recipe', 'name': 'Cookies', 'recipeYield': '4 personnes',
                'recipeIngredient': ['200 g de farine'], 'recipeInstructions': ['Mélanger.'],
                'prepTime': 'PT10M', 'cookTime': 'PT20M'}
        data.update(values)
        response = io.BytesIO((page + '<script type="application/ld+json">' + json.dumps(data) + '</script>').encode())
        response.headers = Message()
        with patch.object(main.urllib.request, 'urlopen', return_value=response):
            return main.fetch_recipe_from_url('https://example.com/recipe')

    def test_measures(self):
        for text, name, unit, qty in [
            ('2 sachets de levure chimique', 'Levure chimique', 'sachet', 2),
            ('une pincée de sel', 'Sel', 'pincée', 1),
            ('2 pincées de sel', 'Sel', 'pincée', 2),
            ('1 cuillerée de sucre', 'Sucre', 'cuillerée', 1),
            ('2 cuillerées à café de sucre', 'Sucre', 'cuillère à café', 2),
            ('1 cuillerée à soupe de farine', 'Farine', 'cuillère à soupe', 1),
            ("un filet d’huile", 'Huile', 'filet', 1),
            ('1 rouleau de pâte brisée', 'Pâte brisée', 'rouleau', 1),
            ('2 rouleaux de pâte feuilletée', 'Pâte feuilletée', 'rouleau', 2),
            ('1 sachet(s) de sucre vanillé', 'Sucre vanillé', 'sachet', 1),
            ('pincée de sel', 'Sel', 'pincée', None),
            ("filet d'huile", 'Huile', 'filet', None),
            ('sachet de levure', 'Levure', 'sachet', None),
            ('2 filets de saumon', 'Filets de saumon', 'pièce', 2),
        ]:
            with self.subTest(text=text):
                self.assertEqual(main._parse_url_ingredient(text), {'name':name, 'unit':unit, 'quantity':qty})

    def test_cookies_not_people(self):
        r = self.fetch(recipeYield='20 cookies')
        self.assertNotEqual(r['default_persons'], 20)
        self.assertIn('20 cookies', r['personal_notes'])
        self.assertIn({'key':'importurl_warning_persons'}, r['import_warnings'])
        self.assertEqual(r['ingredients'][0]['quantity'] * r['default_persons'], 200)
        self.assertEqual(r['category'], 'Dessert')

    def test_yield_list(self):
        for value in [['20 cookies', '5 personnes'], ['20', '20 cookies', '5 personnes']]:
            r=self.fetch(recipeYield=value)
            self.assertEqual(r['default_persons'], 5)
            self.assertEqual(r['ingredients'][0]['quantity'], 40)
            self.assertIn('20 cookies', r['personal_notes'])

    def test_explicit_rest(self):
        r=self.fetch(restTime='PT2H', totalTime='PT3H')
        self.assertIn('120 min', r['personal_notes'])
        self.assertEqual(r['prep_time'], '10')
        self.assertEqual(r['cook_time'], '20')
        self.assertNotIn('repos', self.fetch(totalTime='PT3H')['personal_notes'])
        self.assertIn('1 heure', self.fetch(page='<div class="wprm-recipe-rest-time">1 heure</div>')['personal_notes'])

    def test_rest_label_and_meta_ingredients(self):
        r=self.fetch(page='<span>Temps de repos :</span><span>1 h 30</span><meta itemprop="recipeIngredient" content="1 œuf"><p>Texte sans rapport</p>')
        self.assertIn('1 h 30', r['personal_notes'])
        self.assertEqual([i['name'] for i in r['ingredients']], ['Farine', 'Œuf'])
        self.assertIn('Lactose', main.get_ingredient_allergens('Beurre fondu'))
        self.assertNotIn('Gluten', main.get_ingredient_allergens('Farine sans gluten tamisée'))

    def test_multisegment_author_notes(self):
        r=self.fetch(page='<h2>Note de l’auteur :</h2><p>Bien <strong>laisser refroidir</strong> avant de servir.</p><h2>Commentaires</h2><p>Texte étranger</p>')
        self.assertEqual(r['personal_notes'], 'Bien laisser refroidir avant de servir.')

    def test_missing_structured_ingredients_and_salt_pepper(self):
        page='<li itemprop="recipeIngredient">200 g de farine</li><li itemprop="recipeIngredient">2 œufs</li><li class="wprm-recipe-ingredient"><span>1</span> <span>yaourt nature</span></li><p>3 tomates</p>'
        r=self.fetch(page=page, recipeIngredient=['200 g de farine', 'Sel et poivre'])
        self.assertEqual([i['name'] for i in r['ingredients']], ['Farine','Sel','Poivre','Œufs','Yaourt nature'])
        self.assertEqual(set(r['allergens']), {'Gluten', 'Œufs', 'Lactose'})
        self.assertIsNone(r['ingredients'][1]['quantity'])

    def test_allergens_no_approximate_food_matching(self):
        self.assertIn('Œufs', main.get_ingredient_allergens('œuf'))
        self.assertIn('Œufs', main.get_ingredient_allergens('oeuf'))
        self.assertNotIn('Gluten', main.get_ingredient_allergens('Farine sans gluten'))
        self.assertNotIn('Gluten', main.get_ingredient_allergens('Farine de riz'))
        self.assertEqual(main.get_ingredient_allergens('Ingrédient inconnu'), [])
        with patch.object(main, 'get_ingredient_override', return_value={'allergens': []}):
            self.assertEqual(main.get_ingredient_allergens('œuf'), [])

    def test_duration(self):
        self.assertEqual(main.parse_iso8601_duration_minutes('P1DT2H'), 1560)
        self.assertEqual(main.parse_iso8601_duration_minutes('PT1.5H'), 90)
        self.assertIsNone(main.parse_iso8601_duration_minutes('invalid PT1H'))

    def test_translations(self):
        for lang in ('fr','en','es','de'):
            with patch.object(main, 'CURRENT_LANGUAGE', lang):
                for key in ('importurl_rest_note','importurl_yield_note'):
                    self.assertNotEqual(main.t(key, value='20'), key)

if __name__ == '__main__':
    unittest.main()
