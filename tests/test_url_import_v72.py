import gzip
import io
import json
import unittest
import zlib
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

    def fetch_html(self, html_body):
        response=io.BytesIO(html_body.encode())
        response.headers=Message()
        with patch.object(main.urllib.request,'urlopen',return_value=response):
            return main.fetch_recipe_from_url('https://example.com/recipe')

    def test_microdata_fallback_when_no_jsonld(self):
        r=self.fetch_html("""
            <div itemscope itemtype="http://schema.org/Recipe">
              <h1 itemprop="name">Tarte microdonnees</h1>
              <li itemprop="recipeIngredient">200 g de farine</li>
              <li itemprop="recipeIngredient">3 pommes</li>
              <li itemprop="recipeInstructions">Melanger.</li>
              <span itemprop="recipeYield">4 personnes</span>
            </div>
        """)
        self.assertEqual(r['name'],'Tarte microdonnees')
        self.assertEqual(r['ingredients'][0]['name'],'Farine')

    def test_no_recipe_and_no_microdata_still_raises(self):
        with self.assertRaises(RuntimeError):
            self.fetch_html('<html><body><p>Pas une recette</p></body></html>')

    def test_request_sends_browser_like_headers(self):
        # Une requête ne portant que User-Agent est parfois jugée suspecte
        # par les protections anti-robot de certains sites et bloquée avec
        # un 403 : la requête doit donc ressembler à un vrai navigateur.
        html_body = self._jsonld_html()
        captured = {}
        def fake_urlopen(request, timeout=None):
            captured['headers'] = {k.lower(): v for k, v in request.header_items()}
            response = io.BytesIO(html_body.encode())
            response.headers = Message()
            return response
        with patch.object(main.urllib.request, 'urlopen', side_effect=fake_urlopen):
            main.fetch_recipe_from_url('https://example.com/recipe')
        headers = captured['headers']
        self.assertIn('accept', headers)
        self.assertIn('accept-language', headers)
        self.assertIn('gzip', headers.get('accept-encoding', ''))

    def _jsonld_html(self, **changes):
        data = {'@type': 'Recipe', 'name': 'Essai', 'recipeYield': '4 personnes',
                'recipeIngredient': ['1 oeuf'], 'recipeInstructions': ['Etape.'],
                'prepTime': 'PT10M', 'cookTime': 'PT20M'}
        data.update(changes)
        return '<script type="application/ld+json">' + json.dumps(data, ensure_ascii=False) + '</script>'

    def test_gzip_content_encoding_is_decompressed(self):
        html_body = self._jsonld_html(name='Recette compressee gzip')
        compressed = gzip.compress(html_body.encode('utf-8'))
        response = io.BytesIO(compressed)
        response.headers = Message()
        response.headers['Content-Encoding'] = 'gzip'
        with patch.object(main.urllib.request, 'urlopen', return_value=response):
            r = main.fetch_recipe_from_url('https://example.com/recipe')
        self.assertEqual(r['name'], 'Recette compressee gzip')

    def test_deflate_content_encoding_is_decompressed(self):
        html_body = self._jsonld_html(name='Recette compressee deflate')
        compressed = zlib.compress(html_body.encode('utf-8'))
        response = io.BytesIO(compressed)
        response.headers = Message()
        response.headers['Content-Encoding'] = 'deflate'
        with patch.object(main.urllib.request, 'urlopen', return_value=response):
            r = main.fetch_recipe_from_url('https://example.com/recipe')
        self.assertEqual(r['name'], 'Recette compressee deflate')

    def test_raw_deflate_without_zlib_header_is_decompressed(self):
        # "deflate" est ambigu : certains serveurs envoient du deflate brut
        # (RFC 1951, sans en-tête zlib) plutôt que la variante zlib (RFC 1950).
        html_body = self._jsonld_html(name='Recette deflate brut')
        compressor = zlib.compressobj(wbits=-zlib.MAX_WBITS)
        compressed = compressor.compress(html_body.encode('utf-8')) + compressor.flush()
        response = io.BytesIO(compressed)
        response.headers = Message()
        response.headers['Content-Encoding'] = 'deflate'
        with patch.object(main.urllib.request, 'urlopen', return_value=response):
            r = main.fetch_recipe_from_url('https://example.com/recipe')
        self.assertEqual(r['name'], 'Recette deflate brut')

if __name__=='__main__':unittest.main()
