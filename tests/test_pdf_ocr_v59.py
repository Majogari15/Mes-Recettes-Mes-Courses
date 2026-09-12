import string
import unittest
from unittest.mock import patch
import main


class ExportFilenameTests(unittest.TestCase):
    def test_letters_digits_and_accents_are_preserved(self):
        title = string.ascii_letters + string.digits + ' éèàùêôç & recette'
        self.assertEqual(main.sanitize_windows_filename(title), title)
        title = 'Barramundi en croûte persillée & tomates rôties'
        self.assertEqual(main.sanitize_windows_filename(title), title)

    def test_forbidden_and_control_characters_are_replaced(self):
        for character in '<>:"/\\|?*' + ''.join(chr(i) for i in range(32)):
            self.assertEqual(main.sanitize_windows_filename('A'+character+'B'), 'A_B')
        self.assertEqual(main.sanitize_windows_filename('CON'), '_CON')
        self.assertEqual(main.sanitize_windows_filename('  Cake   citron. '), 'Cake citron')
        self.assertEqual(main.sanitize_windows_filename('...'), 'recette')


class FractionAlignmentTests(unittest.TestCase):
    def test_only_the_verified_measure_is_replaced(self):
        reference = "Par personne : 1 cs de panko et 1/2 cs d'huile."
        for value in ('2', '%', '1/4', ''):
            text = "Par personne : 1 cs de panko et " + value + " cs d'huile."
            result = main.apply_ocr_verified_fractions(text, reference, [('cs', 2, '1/2')])
            self.assertIn('1 cs de panko', result)
            self.assertIn("1/2 cs d'huile", result)

    def test_changed_unit_count_keeps_the_reference(self):
        reference = '1 cs de panko et 1/2 cs huile'
        self.assertEqual(main.apply_ocr_verified_fractions('2 cs huile', reference,
                                                          [('cs', 2, '1/2')]), reference)

    def test_table_fractions_scaled_once(self):
        recipe = main.parse_photo_ocr_recipe("Ingrédients pour 2 personnes\nChapelure panko 1/4 sachet\nHuile d'olive 3 cs")
        self.assertEqual(main.ingredient_quantity_for_persons(recipe['ingredients'][0], 2), .25)
        self.assertEqual(main.ingredient_quantity_for_persons(recipe['ingredients'][1], 2), 3)


@unittest.skipUnless(main.PIL_AVAILABLE and main.PYTESSERACT_AVAILABLE, 'OCR unavailable')
class FractionImageTests(unittest.TestCase):
    def fraction_image(self):
        from PIL import ImageDraw
        image = main.Image.new('L', (45, 45), 255)
        draw = ImageDraw.Draw(image)
        draw.rectangle((5, 4, 9, 16), fill=0)
        draw.line((11, 36, 33, 4), fill=0, width=2)
        draw.rectangle((31, 25, 37, 37), fill=0)
        return image

    def test_requires_two_matching_readings_of_each_digit(self):
        with patch.object(main.pytesseract, 'image_to_string', side_effect=['1','1','4','4']):
            self.assertEqual(main.read_ocr_printed_fraction(self.fraction_image(), 'fra'), '1/4')
        with patch.object(main.pytesseract, 'image_to_string', side_effect=['1','4']):
            self.assertIsNone(main.read_ocr_printed_fraction(self.fraction_image(), 'fra'))

    def test_zero_cannot_turn_percent_into_fraction(self):
        with patch.object(main.pytesseract, 'image_to_string', return_value='0'):
            self.assertIsNone(main.read_ocr_printed_fraction(self.fraction_image(), 'fra'))

    def test_blank_and_integer_do_not_trigger_fraction_recognition(self):
        from PIL import ImageDraw
        image = main.Image.new('L', (40, 40), 255)
        with patch.object(main.pytesseract, 'image_to_string') as recognize:
            self.assertIsNone(main.read_ocr_printed_fraction(image, 'fra'))
            ImageDraw.Draw(image).rectangle((10,5,16,30), fill=0)
            self.assertIsNone(main.read_ocr_printed_fraction(image, 'fra'))
            recognize.assert_not_called()

    def test_timeout_keeps_import_usable_and_cancellation_propagates(self):
        with patch.object(main.pytesseract, 'image_to_string', side_effect=RuntimeError('timeout')):
            self.assertIsNone(main.read_ocr_printed_fraction(self.fraction_image(), 'fra'))
        with self.assertRaises(main.OperationCancelled):
            main.read_ocr_printed_fraction(self.fraction_image(), 'fra', lambda: True)
