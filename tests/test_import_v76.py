import io,json,unittest,urllib.error
from email.message import Message
from unittest.mock import patch
import main

class ImportV76Tests(unittest.TestCase):
 def response(self, **data):
  d={'@type':'Recipe','name':'Test','recipeYield':4,'recipeIngredient':['1 pincée de sel'],'recipeInstructions':['Mélanger.']};d.update(data)
  r=io.BytesIO(('<script type="application/ld+json">'+json.dumps(d)+'</script>').encode());r.headers=Message();return r
 def fetch(self,page='',**data):
  r=self.response(**data);r=io.BytesIO(page.encode()+r.getvalue());r.headers=Message()
  with patch.object(main.urllib.request,'urlopen',return_value=r):return main.fetch_recipe_from_url('https://example.com')
 def test_measures(self):
  for line,q,name in [('3 pots à yaourt de farine',3,'Farine'),("1/2 pot à yaourt d'huile",.5,'Huile')]:
   self.assertEqual(main._parse_url_ingredient(line),{'name':name,'quantity':q,'unit':'pot de yaourt'})
  self.assertNotIn('mesure',main._parse_url_ingredient('1 c. à soupe de vanille ou 1 sachet de sucre vanillé')['name'])
 def test_double_parentheses(self):
  r=self.fetch('<li itemprop="recipeIngredient">150 g de Beaufort (ou autre fromage)</li>',recipeIngredient=['150 g de Beaufort ((ou autre fromage))'])
  self.assertEqual(len(r['ingredients']),1);self.assertEqual(r['ingredients'][0]['quantity']*4,150)
 def test_stages_retained(self):
  r=self.fetch(recipeIngredient=['100 g de farine','50 g de farine']);self.assertEqual(len(r['ingredients']),2)
 def test_allergens(self):
  for name,a in [('Oeufs entiers','Œufs'),('Oeufs frais (bio de préférence)','Œufs'),('Farine (T110 ici)','Gluten'),('Farine de blé (T55 ou T80)','Gluten'),('Lait légèrement tiède','Lactose'),('Beurre fondu (+ beurre pour la poêle)','Lactose'),('Fromage frais','Lactose')]:
   with self.subTest(name=name):self.assertIn(a,main.get_ingredient_allergens(name))
 def test_dietary_and_override(self):
  for name in ('Farine de riz','Farine (sans gluten)','Lait (sans lactose)','Fromage végétalien'):
   self.assertEqual(main.get_ingredient_allergens(name),[])
  with patch.object(main,'get_ingredient_override',return_value={'allergens':[]}):self.assertEqual(main.get_ingredient_allergens('Oeufs entiers'),[])
 def test_rest(self):
  for text in ('Laissez reposer 30 minutes.','Laisser reposer au moins deux heures au frais.'):
   r=self.fetch(recipeInstructions=[text]);self.assertIn('repos',r['personal_notes']);self.assertIn(text,r['description'])
  r=self.fetch('<div class="wprm-recipe-custom_time">20 minutes min</div>');self.assertNotIn('minutes min',r['personal_notes'])
  self.assertNotIn('repos', self.fetch(totalTime='PT3H')['personal_notes'])
  self.assertIn('180 min', self.fetch(totalTime='PT3H')['personal_notes'])
 def test_yield(self):
  r=self.fetch('<h5>Pour une trentaine de crêpes</h5>',recipeYield='');self.assertIn('trentaine',r['personal_notes'])
  self.assertEqual(self.fetch(recipeYield='15 crêpes – 6 personnes')['default_persons'],6)
 def test_source_conflict(self):
  r=self.fetch(recipeInstructions=['Cassez 2 œufs.']);self.assertIn('2 œufs',r['personal_notes']);self.assertEqual(len(r['ingredients']),1)
 def test_advice(self):
  r=self.fetch('<div class="recipe-advice-content"><h2>Conseils</h2><p>Fouetter longtemps.</p></div><p>Commentaires</p>');self.assertEqual(r['personal_notes'],'Fouetter longtemps.')
 def test_retry(self):
  for e in (TimeoutError(),urllib.error.HTTPError('https://example.com',502,'Bad Gateway',{},None)):
   with patch.object(main.urllib.request,'urlopen',side_effect=[e,self.response()]) as m:
    self.assertEqual(main.fetch_recipe_from_url('https://example.com')['name'],'Test');self.assertEqual(m.call_count,2)
  with patch.object(main.urllib.request,'urlopen',side_effect=TimeoutError()) as m:
   with self.assertRaises(RuntimeError):main.fetch_recipe_from_url('https://example.com')
   self.assertEqual(m.call_count,2)
  with patch.object(main.urllib.request,'urlopen',side_effect=urllib.error.HTTPError('https://example.com',403,'Forbidden',{},None)) as m:
   with self.assertRaises(RuntimeError):main.fetch_recipe_from_url('https://example.com')
   self.assertEqual(m.call_count,1)
