import unittest
from unittest.mock import patch
import main


class OCRReviewTests(unittest.TestCase):
    def test_real_damaged_table_keeps_ten_ingredients_without_invented_numbers(self):
        text = """--- Photo 1 ---
y) Barramundi en croûte persillée & tomates rôties
| avec une purée à la ciboulette
À table dans : 35 - 45 Min
--- Photo 2 ---
ingrédients pour 2 personnes
Gousse d'ail 1 pièce(s) Ch
Persil plat et ciboulette* 1 sachet(s)
Pommes de terre 500 g V
Chapelure panko % sachet(s)
Filet de barramundi* 2 pièce(s)
Tomates cerises* 1 barquette(s)
Huile d'olive ES |
Beurre cs .
Lait 1 filet(s)
Poivre et sel selon votre goût
* Conserver au réfrigérateur
Valeurs nutritionnelles
Sel (g) 0,3 0,1
"""
        recipe = main.parse_photo_ocr_recipe(text)
        self.assertTrue(recipe['name'].startswith('Barramundi'))
        self.assertTrue(recipe['name'].endswith('purée à la ciboulette'))
        self.assertEqual(recipe['default_persons'], 2)
        by_name = {i['name']: i for i in recipe['ingredients']}
        self.assertEqual(len(by_name), 10)
        self.assertEqual(by_name['Pommes de terre']['quantity'], 250)
        for name in ('Chapelure panko', "Huile d'olive", 'Beurre'):
            self.assertIsNone(by_name[name]['quantity'])
            self.assertIn(name, recipe['ocr_warnings'])
        self.assertIsNone(by_name['Poivre et sel']['quantity'])
        self.assertNotIn('Poivre et sel', recipe['ocr_warnings'])
        self.assertNotIn('Sel (g)', by_name)
        main.validate_recipes_payload([recipe])

    def test_fraction_units_and_scaling(self):
        for qty in ('¼', '1/4', '1 / 4'):
            with self.subTest(qty=qty):
                row = main.parse_ocr_ingredient_table_line('Chapelure panko '+qty+' sachet(s)')
                self.assertEqual(row['quantity'], .25)
                result=main.parse_photo_ocr_recipe('Ingrédients pour 2 personnes\nChapelure panko '+qty+' sachet(s)')
                self.assertEqual(result['ingredients'][0]['quantity'], .125)
        self.assertEqual(main.parse_ocr_ingredient_table_line('Farine 1 kg')['unit'], 'Kilo')
        self.assertIsNone(main.parse_ocr_ingredient_table_line('Poivre % sachet')['quantity'])
        self.assertEqual(main._parse_ocr_quantity('1 1/2'), 1.5)
        self.assertIsNone(main._parse_ocr_quantity('1/0'))

    def test_furniture_marks_and_notes_do_not_enter_names(self):
        for mark in ('*', '”', '"'):
            self.assertEqual(main.parse_ocr_ingredient_table_line('Filet de barramundi'+mark+' 2 pièce(s)')['name'], 'Filet de barramundi')
        self.assertIsNone(main.parse_ocr_ingredient_table_line('À ajouter vous-même'))

    def test_preparation_reflows_lines_without_merging_steps(self):
        text="""e Préchauffez le four à 210°C
(190°C chaleur tournante).
e Portez une grande casserole d'eau
salée à ébullition.
ss + Incorporez une noix de beurre (voir
L'ASTUCE) et un filet de lait.
+ Placez-yle poisson.
"""
        result=main.clean_ocr_preparation(text)
        self.assertIn("(voir L'ASTUCE)", result)
        self.assertIn("d'eau salée à ébullition", result)
        self.assertIn('\n\nPortez',result)
        self.assertNotIn('ss +',result)
        self.assertIn('Placez-y le poisson',result)

    def test_spacing_only_restores_observed_words(self):
        original = "Ciselez l'ail et les herbes. Coupez les pommes de terre et coupez-les en dés."
        reread = "Ciselez l'ailet les herbes. Coupez les pommes deterreetcoupez-les en dés."
        fixed = main.restore_ocr_spacing(reread, original)
        self.assertIn("l'ail et", fixed)
        self.assertIn("de terre et coupez-les", fixed)
        self.assertEqual(main.restore_ocr_spacing('2 cs', '½ cs'), '2 cs')

    def test_all_language_messages(self):
        for catalog in [main.FRENCH_STRINGS, *main.TRANSLATIONS.values()]:
            for key in ('importphoto_uncertain_quantities','importphoto_measure_check'):
                self.assertIn(key,catalog)


@unittest.skipUnless(main.PYTESSERACT_AVAILABLE and main.PIL_AVAILABLE, "OCR dependencies unavailable")
class OCRRereadTests(unittest.TestCase):
    @staticmethod
    def data(lines):
        data={k: [] for k in ('text','left','top','width','height','conf','block_num','par_num','line_num')}
        for number,line in enumerate(lines,1):
            for text,x in line:
                for k,v in dict(text=text,left=x,top=number*40,width=len(text)*5,height=20,
                                conf=80,block_num=1,par_num=1,line_num=number).items():
                    data[k].append(v)
        return data

    def test_table_reread_cannot_turn_ambiguous_fraction_into_integer(self):
        data=self.data([[('Ingrédients',10),('pour',100),('2',130),('personnes',150)],
                        [('Chapelure',10),('panko',70),('%',360),('sachet',380)]])
        with patch.object(main.pytesseract,'image_to_data',return_value=data), patch.object(
            main.pytesseract,'image_to_string',return_value='Chapelure panko 2 sachets'):
            text=main.ocr_ingredient_table(main.Image.new('RGB',(500,160)), 'fra')
        recipe=main.parse_photo_ocr_recipe(text)
        self.assertIsNone(recipe['ingredients'][0]['quantity'])
        self.assertIn('Chapelure panko',recipe['ocr_warnings'])

    def test_preparation_measure_disagreement_is_visible(self):
        data=self.data([[('Dans un bol ajoutez du persil et cs',10)],
                        [("huile olive puis mélangez le tout",10)]])
        with patch.object(main.pytesseract,'image_to_data',return_value=data), patch.object(
            main.pytesseract,'image_to_string',return_value="Dans un bol ajoutez du persil et 2 cs\nd'huile olive puis mélangez le tout"):
            text=main.ocr_preparation_cell(main.Image.new('RGB',(500,160)), 'fra')
        self.assertNotIn('et 2 cs',text)
        self.assertIn('['+main.t('importphoto_measure_check')+']',text)

if __name__ == "__main__":
    unittest.main()
