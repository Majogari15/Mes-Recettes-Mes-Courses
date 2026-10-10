"""Arabe (ar) : interface, catalogue, recherche, chiffres arabo-indiens,
ingrédients, import, durées, péremption, listes, devise, PDF et voix."""
import datetime
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import main  # noqa: E402
from test_regressions import TempDataMixin  # noqa: E402


class ArabicLanguageTests(TempDataMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.addCleanup(setattr, main, "CURRENT_LANGUAGE", main.CURRENT_LANGUAGE)

    def test_language_and_bundled_files(self):
        self.assertIn("ar", main.UI_LANGUAGES)
        self.assertEqual(main.TESSERACT_LANG_CODES["ar"], "ara")
        for path in (ROOT / "i18n" / "ar.json", ROOT / "data" / "ingredient_translations_ar.json",
                     ROOT / "data" / "ingredient_substitutions_ar.json", ROOT / "data" / "flag_ar.png",
                     ROOT / "data" / "fonts" / "NotoSansArabic-subset.ttf", ROOT / "data" / "fonts" / "OFL-NotoSansArabic.txt"):
            self.assertTrue(path.is_file(), path)
        names = json.loads((ROOT / "data" / "ingredient_translations_ar.json").read_text(encoding="utf-8"))
        main.apply_language("ar")
        self.assertEqual(main.translate_ingredient_name("Beurre"), names["Beurre"])
        self.assertEqual(main.t("common_close"), "إغلاق")
        self.assertEqual(main.resolve_ingredient_input("زبدة", main.load_default_ingredients()), "Beurre")

    def test_search_ignores_vowels_hamza_tatweel_and_alef_maqsura(self):
        key = main.ingredient_sort_key
        self.assertEqual(key("أُرز"), key("ارز"))
        self.assertEqual(key("إبريق"), key("ابريق"))
        self.assertEqual(key("ســكر"), key("سكر"))
        self.assertEqual(key("مستشفى"), key("مستشفي"))

    def test_arabic_indic_digits(self):
        self.assertEqual(main.ascii_digits("٢٫٥"), "2.5")
        self.assertEqual(main.normalize_barcode("٦٢٨١٠٠٧٠٠٠٠٠١"), "6281007000001")
        self.assertEqual(main.parse_pantry_expiration("١٥/٠٣/٢٠٢٧"), datetime.date(2027, 3, 15))

    def test_arabic_ingredient_lines(self):
        cases = {"2 كوب دقيق": ("Farine", 2, "cup"), "دقيق 200 غرام": ("Farine", 200, "Gr"),
                 "نصف كوب حليب": ("Lait", 0.5, "cup"), "كوبين سكر": ("Sucre", 2, "cup"),
                 "ملح حسب الرغبة": ("Sel", None, ""), "3 بيضات": ("Oeufs", 3, "pièce"),
                 "ملعقة كبيرة زيت زيتون": ("Huile d'olive", 1, "cuillère à soupe"),
                 "٢ ملعقة صغيرة ملح": ("Sel", 2, "cuillère à café"), "1 1/2 كوب من الدقيق": ("Farine", 1.5, "cup"),
                 "أرز بسمتي : 2 كوب (طويل الحبة)": ("Riz basmati", 2, "cup"), "البصل : 1 حبة (مقطع)": ("Oignon", 1, "pièce"),
                 "1.5 كيلو جرامات دجاج": ("Poulet", 1.5, "Kilo")}
        for line, expected in cases.items():
            parsed = main.parse_arabic_ingredient_line(line)
            self.assertEqual((parsed["name"], parsed["quantity"], parsed["unit"]), expected, line)
        self.assertEqual(main._parse_url_ingredient("250 غ زبدة")["name"], "Beurre")

    def test_arabic_recipe_text(self):
        text = ("كبسة دجاج\nالمقادير لـ 4 أشخاص\n2 كوب أرز\n2 ملعقة كبيرة زيت زيتون، ملح حسب الرغبة\n"
                "طريقة التحضير\n1. نقلي البصل في الزيت لمدة 5 دقائق\n2. نطبخ الأرز مع الدجاج نصف ساعة")
        recipe = main.parse_photo_ocr_recipe(text)
        self.assertEqual((recipe["name"], recipe["default_persons"]), ("كبسة دجاج", 4))
        self.assertEqual([i["name"] for i in recipe["ingredients"]], ["Riz", "Huile d'olive", "Sel"])
        self.assertEqual(recipe["ingredients"][0]["quantity"], 0.5)
        self.assertEqual(recipe["description"], "1. نقلي البصل في الزيت لمدة 5 دقائق\n2. نطبخ الأرز مع الدجاج نصف ساعة")

    def test_timers_expiry_lists_currency_voice(self):
        durations = main.CookingModeWindow._step_durations
        self.assertEqual(sorted(s for _, s in durations("نطبخ نصف ساعة ثم 10 دقائق وساعتين")), [600, 1800, 7200])
        today = datetime.date(2026, 10, 1)
        self.assertEqual(main.extract_expiration_date_from_ocr_text(
            "تاريخ الإنتاج 01/09/2026 تاريخ الانتهاء ١٥/٠٣/٢٠٢٧", today=today), datetime.date(2027, 3, 15))
        main.CURRENT_LANGUAGE = "ar"
        self.assertEqual(main.list_join(["ملح", "سكر"]), "ملح، سكر")
        self.assertEqual(main.get_currency(), "EUR")
        main.set_currency("SAR")
        self.assertEqual(main.get_currency(), "SAR")
        voices = [SimpleNamespace(id="fr", languages=["fr-FR"]), SimpleNamespace(id="ar", languages=["ar-SA"])]
        self.assertEqual(main.pick_tts_voice_id(voices, "fr", "نقلي البصل"), "ar")

    def test_pdf_line_order_and_arabic_text(self):
        # Ordre d'affichage : la ligne se lit de droite à gauche, nombres et
        # ponctuation à leur place.
        self.assertEqual(main._pdf_visual("Farine 200 g"), "Farine 200 g")
        visual = main._pdf_visual("- أرز : 2.0 cup")
        self.assertTrue(visual.startswith("2.0 cup : "))
        self.assertTrue(visual.endswith(" -"))
        import pypdfium2 as pdfium
        main.CURRENT_LANGUAGE = "ar"
        recipe = {"name": "كبسة دجاج", "category": "Plat", "default_persons": 4, "ingredients": [],
                  "description": "نقلي البصل في الزيت لمدة 5 دقائق حتى يذبل ثم نضيف الدجاج. " * 6}
        path = Path(tempfile.mkdtemp()) / "ar.pdf"
        main.build_cookbook_pdf(str(path), [(recipe, 4)])
        pdf = pdfium.PdfDocument(str(path))
        page = pdf[len(pdf) - 1]
        textpage = page.get_textpage()
        self.assertGreater(textpage.count_chars(), 100)
        right = max(textpage.get_charbox(i)[2] for i in range(textpage.count_chars()))
        self.assertLess(right, page.get_width())
        pdf.close()

    def test_arabic_digits_typed_are_converted(self):
        import tkinter as tk
        from tkinter import ttk
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.addCleanup(root.destroy)
        root.withdraw()
        main.install_arabic_digit_bindings(root)
        self.assertIn("_convert_arabic_digit_key", root.bind_class("TEntry", "<Key>"))
        entry = ttk.Entry(root)
        entry.insert(0, "1")
        for char in "٢٫٥":
            self.assertEqual(main._convert_arabic_digit_key(SimpleNamespace(char=char, widget=entry)), "break")
        self.assertIsNone(main._convert_arabic_digit_key(SimpleNamespace(char="a", widget=entry)))
        self.assertEqual(entry.get(), "12.5")


if __name__ == "__main__":
    unittest.main()
