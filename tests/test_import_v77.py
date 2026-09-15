"""Import regressions independent of live site availability."""
import json
import unittest
from unittest.mock import patch
import main

class InternationalImportTests(unittest.TestCase):
    def fetch(self, **fields):
        data = {'@type': 'Recipe', 'name': 'Test', 'recipeYield': '4 servings',
                'recipeIngredient': ['100 g flour'], 'recipeInstructions': ['Mix.'],
                'prepTime': 'PT10M', 'cookTime': 'PT20M'}
        data.update(fields)
        page = '<script type="application/ld+json">' + json.dumps(data) + '</script>'
        with patch.object(main, '_download_recipe_page', return_value=page):
            return main.fetch_recipe_from_url('https://example.com/recipe')

    def test_units_four_languages(self):
        for line, qty, unit in [
            ('1 1/2 cups flour', 1.5, 'cup'), ('¾ cup butter', .75, 'cup'),
            ('2 tbsp milk', 2, 'cuillère à soupe'), ('1 tsp baking powder', 1, 'cuillère à café'),
            ('1 lata de guisantes', 1, 'boîte'), ('1 diente ajo picado', 1, 'gousse'),
            ('2 EL Milch', 2, 'cuillère à soupe'), ('1 TL Salz', 1, 'cuillère à café'),
            ('1 Prise Salz', 1, 'pincée'), ('1 sachet de levure', 1, 'sachet'),
            ('2 rouleaux de pâte', 2, 'rouleau'), ('1 filet d’huile', 1, 'filet'),
            ('2 filets de poulet', 2, 'pièce'), ('1 cuillerée de sucre', 1, 'cuillerée')]:
            with self.subTest(line=line):
                parsed = main._parse_url_ingredient(line)
                self.assertEqual((parsed['quantity'], parsed['unit']), (qty, unit))

    def test_allergens_and_qualifiers(self):
        for word, expected in [('Huevo', 'Œufs'), ('eggs', 'Œufs'), ('Eier', 'Œufs'),
                               ('milk', 'Lactose'), ('Leche', 'Lactose'), ('Milch', 'Lactose'),
                               ('plain flour', 'Gluten'), ('Butter, melted', 'Lactose')]:
            with self.subTest(word=word):
                self.assertIn(expected, main.get_ingredient_allergens(word))
        for word in ('gluten-free flour', 'lactose free milk', 'leche sin lactosa',
                     'Milch ohne Laktose', 'vegan butter', 'Farine (sans gluten)'):
            self.assertEqual(main.get_ingredient_allergens(word), [])

    def test_yields_and_scaling(self):
        for value in ('Makes 12', '12 cookies', 'Ergibt 12 Stück', '12 galletas'):
            r = self.fetch(recipeYield=value)
            self.assertIn('importurl_warning_persons', str(r['import_warnings']))
            self.assertIn(value, r['personal_notes'])
            self.assertEqual(r['ingredients'][0]['quantity'] * r['default_persons'], 100)
        for value in ('6 personas', '6 Personen', '6 raciones', '6 servings', '6 personnes'):
            r = self.fetch(recipeYield=value)
            self.assertEqual(r['default_persons'], 6)
            self.assertAlmostEqual(r['ingredients'][0]['quantity'] * 12, 200)

    def test_sections(self):
        r = self.fetch(recipeIngredient=['For the pancakes:', '100 g flour', 'To serve:', '1 egg'])
        self.assertEqual(len(r['ingredients']), 2)
        self.assertEqual(main._url_ingredient_heading('pâte brisée'), False)

    def test_categories_rest_and_total(self):
        self.assertEqual(self.fetch(recipeCategory='Postres')['category'], 'Dessert')
        self.assertEqual(self.fetch(recipeCategory='Hauptgericht')['category'], 'Plat')
        for step in ('Rest for 30 minutes if you have time.',
                     'Esperamos hasta el día siguiente para servir.',
                     '30 Minuten ruhen lassen.'):
            r = self.fetch(recipeInstructions=[step])
            self.assertIn(step, r['personal_notes'])
            self.assertIn(step, r['description'])
        self.assertEqual(self.fetch(totalTime='PT3H')['personal_notes'], '')

    def test_redirect(self):
        def download(request):
            request.recipe_final_url = 'https://other.example/recipe'
            return '<script type="application/ld+json">'+json.dumps({'@type':'Recipe','name':'Other','recipeIngredient':['1 egg']})+'</script>'
        with patch.object(main, '_download_recipe_page', side_effect=download):
            r = main.fetch_recipe_from_url('https://example.com/recipe')
        self.assertEqual(r['source_url'], 'https://other.example/recipe')
        self.assertIn('importurl_warning_redirect', str(r['import_warnings']))

    def test_warning_translation(self):
        for lang in ('fr','en','es','de'):
            with patch.object(main, 'CURRENT_LANGUAGE', lang):
                for key in ('importurl_warning_redirect','importurl_warning_unit','importurl_total_note'):
                    self.assertNotEqual(main.t(key, value='TEST'), key)
