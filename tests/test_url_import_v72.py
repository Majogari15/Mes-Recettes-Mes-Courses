import io
import json
import unittest
from email.message import Message
from unittest.mock import patch
import main

class ImportTests(unittest.TestCase):
    def fetch(self, **changes):
        data={'@type':'Recipe','name':'Essai','recipeYield':'4 personnes',
              'recipeIngredient':['200 g de farine'], 'recipeInstructions':['Mélanger.'],
              'prepTime':'PT10M','cookTime':'PT20M'}
        data.update(changes)
        payload=json.dumps(data,ensure_ascii=False)
        if getattr(self,'literal_newline',False):
            payload=payload.replace('Mélanger.', 'Mélanger.\nPuis cuire.')
        response=io.BytesIO(('<script type="application/ld+json">'+payload+'</script>').encode())
        response.headers=Message()
        with patch.object(main.urllib.request,'urlopen',return_value=response):
            return main.fetch_recipe_from_url('https://example.com/recipe')

    def test_units_and_totals(self):
        r=self.fetch(recipeIngredient=['1 dl de lait','1 cc de levure','1 cuil a soupe de fécule','2 unités oeuf','2 pincées de sel'])
        self.assertEqual([(i['name'], i['quantity']*4,i['unit']) for i in r['ingredients']],
          [('Lait',100,'ml'),('Levure',1,'cuillère à café'),('Fécule',1,'cuillère à soupe'),('Oeuf',2,'pièce'),('Sel',2,'pincée')])

    def test_sections_additions_and_alternatives(self):
        r=self.fetch(recipeIngredient=['Pâte :','Garniture','1 pâte brisée','80 g de vergeoise + 50 g de sucre (ou 120 g de sucre)','1 cc de levure et 1 cc de bicarbonate','Sel'])
        self.assertEqual(len(r['ingredients']),6)
        self.assertEqual(r['ingredients'][1]['name'],'Vergeoise')
        self.assertEqual(r['ingredients'][2]['quantity']*4,50)
        self.assertIsNone(r['ingredients'][-1]['quantity'])
        self.assertTrue(any(w['key']=='importurl_warning_alternative' for w in r['import_warnings']))
        self.assertEqual(main._url_ingredient_parts('100 g de beurre ou 80 g de margarine'),['100 g de beurre ou 80 g de margarine'])
        self.assertEqual(main._url_ingredient_parts('1 sachet (2 g + 3 g)'),['1 sachet (2 g + 3 g)'])

    def test_literal_newline_in_json(self):
        self.literal_newline=True
        self.assertIn('Puis cuire.',self.fetch()['description'])

    def test_nested_steps_and_encoded_html(self):
        r=self.fetch(recipeInstructions=[{'@type':'HowToSection','name':'Pâte','itemListElement':[{'@type':'HowToStep','text':'&lt;b&gt;Mélanger&lt;/b&gt;.'},{'text':'Cuire.'}]}])
        self.assertEqual(r['description'],'1. Mélanger .\n2. Cuire.')

    def test_missing_fields_keep_total_and_warn(self):
        r=self.fetch(recipeYield=None,prepTime=None,cookTime=None,recipeInstructions=[])
        self.assertEqual(r['ingredients'][0]['quantity']*r['default_persons'],200)
        self.assertEqual(len(r['import_warnings']),4)

if __name__=='__main__':unittest.main()
