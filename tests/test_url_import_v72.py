import gzip
import io
import json
import unittest
import zlib
from email.message import Message
from pathlib import Path
from unittest.mock import patch
import main
from PIL import Image
from test_regressions import TempDataMixin

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

    def test_falls_back_to_reader_text_when_no_structured_data(self):
        # Comparaison avec l'app mobile (qui fait de même via Jina AI
        # Reader) : si aucune donnée structurée n'est trouvée, on retente
        # via une version texte de la page, réanalysée par le même
        # analyseur que l'import OCR photo (parse_photo_ocr_recipe, dont le
        # format de sortie exact est testé ailleurs) — ici on vérifie
        # seulement le branchement : texte de secours -> analyseur OCR ->
        # utilisé si des ingrédients en ressortent.
        fake_parsed = {"name": "Tarte aux pommes", "ingredients": [{"name": "Farine", "quantity": 50, "unit": "g"}],
                       "description": "", "prep_time": "", "cook_time": "", "default_persons": 4,
                       "quantity_basis": "per_person", "ocr_warnings": []}
        with patch.object(main, "_fetch_recipe_reader_text", return_value="texte quelconque"), \
             patch.object(main, "parse_photo_ocr_recipe", return_value=fake_parsed) as mocked_parse:
            r = self.fetch_html('<html><body><p>Pas une recette</p></body></html>')
        mocked_parse.assert_called_once_with("texte quelconque")
        self.assertEqual(r, fake_parsed)

    def test_reader_fallback_failure_still_raises_the_normal_error(self):
        with patch.object(main, "_fetch_recipe_reader_text", side_effect=RuntimeError("boom")):
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
        # En-têtes Fetch Metadata / Client Hints envoyés par tout Chrome
        # récent, spécifiquement vérifiés par certains WAF (Wordfence...)
        # en plus de l'Accept-Encoding déjà testé ci-dessus.
        self.assertEqual(headers.get('sec-fetch-mode'), 'navigate')
        self.assertEqual(headers.get('sec-fetch-dest'), 'document')
        self.assertIn('sec-ch-ua', headers)

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

class RecipeImageDownloadTests(TempDataMixin, unittest.TestCase):
    def _jsonld_html(self, **changes):
        data = {'@type': 'Recipe', 'name': 'Essai', 'recipeYield': '4 personnes',
                'recipeIngredient': ['1 oeuf'], 'recipeInstructions': ['Etape.'],
                'prepTime': 'PT10M', 'cookTime': 'PT20M'}
        data.update(changes)
        return '<script type="application/ld+json">' + json.dumps(data, ensure_ascii=False) + '</script>'

    def _png_bytes(self):
        buf = io.BytesIO()
        Image.new('RGB', (2, 2), color='red').save(buf, format='PNG')
        return buf.getvalue()

    def test_image_download_sends_referer_and_decompresses(self):
        # Constaté sur chefkoch.de : la page se télécharge sans problème,
        # mais l'image de la recette échoue si elle est demandée sans
        # Referer (protection anti-hotlinking côté CDN d'images).
        html_body = self._jsonld_html(image='https://cdn.example.com/photo.png')
        image_bytes = gzip.compress(self._png_bytes())
        calls = []
        def fake_urlopen(request, timeout=None):
            calls.append(request)
            if len(calls) == 1:
                response = io.BytesIO(html_body.encode())
                response.headers = Message()
                return response
            response = io.BytesIO(image_bytes)
            response.headers = Message()
            response.headers['Content-Type'] = 'image/png'
            response.headers['Content-Encoding'] = 'gzip'
            return response
        with patch.object(main.urllib.request, 'urlopen', side_effect=fake_urlopen):
            r = main.fetch_recipe_from_url('https://example.com/recipe')
        self.assertEqual(len(calls), 2)
        image_headers = {k.lower(): v for k, v in calls[1].header_items()}
        self.assertEqual(image_headers.get('referer'), 'https://example.com/recipe')
        self.assertIn('image', image_headers.get('accept', ''))
        self.assertEqual(len(r['image_sources']), 1)
        self.assertTrue(Path(r['image_sources'][0]).exists())

if __name__=='__main__':unittest.main()
