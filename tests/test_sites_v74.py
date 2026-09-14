import io,json,unittest,urllib.error
from email.message import Message
from unittest.mock import patch
import main

class SitesTests(unittest.TestCase):
 def fetch(self, **kw):
  d={'@type':'Recipe','name':'Test','recipeYield':2,'recipeIngredient':['6-8 figues'],'recipeInstructions':['Mélanger.'],'recipeCategory':'Déjeuner, Dîner'};d.update(kw)
  r=io.BytesIO(('<script type="application/ld+json">'+json.dumps(d)+'</script>').encode());r.headers=Message()
  with patch.object(main.urllib.request,'urlopen',return_value=r):return main.fetch_recipe_from_url('https://example.com/r')
 def test_categories(self):
  for value,expected in [('Quiche','Plat'),('Desserts américains','Dessert'),('gâteau au yaourt','Dessert'),(['Déjeuner','Dîner'],'Plat'),('Petit-déjeuner','Petit-déjeuner')]:
   self.assertEqual(self.fetch(recipeCategory=value)['category'],expected)
 def test_units(self):
  for text,name,unit,qty in [('1 sachet Levure chimique','Levure chimique','sachet',1),('2 grosses poignées de mesclun','Mesclun','grosse poignée',2),('1 disque de pâte feuilletée','Pâte feuilletée','disque',1),('1 tour de moulin de poivre noir','Poivre noir','tour de moulin',1),('pincée Sel','Sel','pincée',None)]:
   self.assertEqual(main._parse_url_ingredient(text),{'name':name,'unit':unit,'quantity':qty})
 def test_range_preserved(self):
  r=self.fetch();self.assertEqual(r['ingredients'][0]['quantity'],3)
  self.assertIn('6-8 figues',r['personal_notes']);self.assertEqual(r['import_warnings'][0]['key'],'importurl_warning_range')
 def test_steps_and_notes(self):
  steps,notes=main._url_clean_steps(['Présentation du gâteau.\r \r Vous préchauffez le four.','1. Mélanger.','2. Cuire.','Variantes\r Ajouter du miel.','Ajouter des noix.','FAQ\r Comment conserver ? Au frais.'])
  self.assertEqual(steps,['Vous préchauffez le four.','Mélanger.','Cuire.'])
  self.assertEqual(len(notes),4)
  self.assertEqual(main._url_clean_steps(['1.5 g de sel suffisent.'])[0],['1.5 g de sel suffisent.'])
 def test_errors_are_distinct(self):
  messages=[]
  for error in [TimeoutError(),urllib.error.HTTPError('https://example.com',403,'Forbidden',{},None)]:
   with patch.object(main.urllib.request,'urlopen',side_effect=error):
    with self.assertRaises(RuntimeError) as cm:main.fetch_recipe_from_url('https://example.com')
    messages.append(str(cm.exception))
  self.assertNotEqual(*messages);self.assertIn('403',messages[1])

if __name__=='__main__':unittest.main()
