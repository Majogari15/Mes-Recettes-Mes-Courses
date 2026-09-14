import io
import json
import unittest
from email.message import Message
from unittest.mock import patch
import main

INGREDIENTS=['3 oeufs','1 yaourt nature','1 sachet de levure en poudre (5,5 g)',
 '2 ½ pots de yaourts vides de farine','1 ½ pots de yaourts vide de sucre',
 '1 sachet de sucre vanillé (7,5 g)',"½ pot de yaourt d’huile",'10 g de beurre']

def imported():
    data={'@type':'Recipe','name':'Gâteau au yaourt','recipeCategory':'Dessert',
          'recipeYield':6,'recipeIngredient':INGREDIENTS,'recipeInstructions':['Mélanger.','Cuire.'],
          'prepTime':'PT5M','cookTime':'PT30M'}
    page='<h1>Gâteau</h1><span>Très facile</span><h2>Ingrédients</h2><p>Note de l’auteur :</p><p>Vérifier la cuisson.</p>'
    page+='<script type="application/ld+json">'+json.dumps(data)+'</script>'
    response=io.BytesIO(page.encode());response.headers=Message()
    with patch.object(main.urllib.request,'urlopen',return_value=response):
        return main.fetch_recipe_from_url('https://example.com/gateau')

class MarmitonTests(unittest.TestCase):
    def test_measures_names_and_totals(self):
        r=imported();ings=r['ingredients']
        self.assertEqual([(i['name'],i['unit']) for i in ings[2:7]],[
            ('Levure en poudre','Gr'),('Farine','pot de yaourt'),('Sucre','pot de yaourt'),
            ('Sucre vanillé','Gr'),('Huile','pot de yaourt')])
        for i,total in zip(ings,[3,1,5.5,2.5,1.5,7.5,.5,10]):self.assertAlmostEqual(i['quantity']*6,total)
    def test_unspecified_sachet_weight(self):
        self.assertEqual(main._parse_url_ingredient('2 sachets de levure'),{'name':'Levure','unit':'sachet','quantity':2})
    def test_metadata_and_notes(self):
        r=imported();self.assertEqual(r['category'],'Dessert');self.assertEqual(r['difficulty'],'Très facile')
        self.assertEqual(r['personal_notes'],'Vérifier la cuisson.')
    def test_nutrition_does_not_invent_pot_weights(self):
        r=imported();nutrition,known,total=main.compute_recipe_nutrition(r,6)
        self.assertLess(known,total)
        self.assertIn('Gluten',main.compute_recipe_allergens(r['ingredients']))
    def test_embedded_font(self):
        self.assertEqual(main._pdf_font_name('Helvetica'),'RecipeSans')
        self.assertIn('RecipeSans',main.pdfmetrics.getRegisteredFontNames())

if __name__=='__main__':unittest.main()
