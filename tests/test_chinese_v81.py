"""Chinois simplifié (zh) : interface, catalogue, saisie, import, OCR,
durées, dates, devise, listes, PDF et voix — repris de l'app mobile."""
import datetime
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import main  # noqa: E402
from test_regressions import TempDataMixin  # noqa: E402


class ChineseLanguageTests(TempDataMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self._language = main.CURRENT_LANGUAGE
        self.addCleanup(setattr, main, "CURRENT_LANGUAGE", self._language)

    def test_language_and_bundled_files(self):
        self.assertIn("zh", main.UI_LANGUAGES)
        self.assertEqual(main.TESSERACT_LANG_CODES["zh"], "chi_sim")
        for path in (ROOT / "i18n" / "zh.json", ROOT / "data" / "ingredient_translations_zh.json",
                     ROOT / "data" / "ingredient_substitutions_zh.json", ROOT / "data" / "flag_zh.png",
                     ROOT / "data" / "fonts" / "NotoSansSC-subset.ttf", ROOT / "data" / "fonts" / "OFL-NotoSansSC.txt"):
            self.assertTrue(path.is_file(), path)
        names = json.loads((ROOT / "data" / "ingredient_translations_zh.json").read_text(encoding="utf-8"))
        self.assertEqual(len(names), len(json.loads((ROOT / "data" / "ingredient_translations_en.json").read_text(encoding="utf-8"))))
        main.apply_language("zh")
        self.assertEqual(main.translate_ingredient_name("Beurre"), names["Beurre"])
        self.assertEqual(main.resolve_ingredient_input("鸡蛋", main.load_default_ingredients()), "Oeufs")
        self.assertEqual(main.t("common_close"), "关闭")

    def test_chinese_ingredient_lines(self):
        cases = {"面粉 200克": ("Farine", 200, "Gr"), "200克面粉": ("Farine", 200, "Gr"),
                 "鸡蛋两个": ("Oeufs", 2, "pièce"), "盐 适量": ("Sel", None, ""), "猪肉半斤": ("Porc", 250, "Gr"),
                 "牛奶 400毫升": ("Lait", 400, "ml"), "生抽 1汤匙": ("Sauce soja légère", 1, "cuillère à soupe"),
                 "中筋面粉 135～140克": ("Farine", 135, "Gr"), "猪油 65克(60克做油酥用)": ("Saindoux", 65, "Gr")}
        for line, expected in cases.items():
            parsed = main.parse_chinese_ingredient_line(line)
            self.assertEqual((parsed["name"], parsed["quantity"], parsed["unit"]), expected, line)

    def test_ocr_text_is_parsed_with_spaces_between_characters(self):
        text = ("红 烧 肉 的 做 法\n3 人份\n用 料\n五 花 肉 600克 、 冰 糖 30克 、 生 抽 2汤匙\n葱 少 许\n"
                "做 法\n1. 五 花 肉 切 块 焯 水\n2. 小 火 炖 一 个 小 时")
        recipe = main.parse_photo_ocr_recipe(text)
        self.assertEqual((recipe["name"], recipe["default_persons"]), ("红烧肉", 3))
        self.assertEqual([i["name"] for i in recipe["ingredients"]],
                         ["Poitrine de porc", "Sucre candi", "Sauce soja légère", "Ciboule ou ciboulette, fraîche"])
        self.assertEqual(recipe["ingredients"][0]["quantity"], 200)  # 600 g pour 3 personnes
        self.assertEqual(recipe["description"], "1. 五花肉切块焯水\n2. 小火炖一个小时")

    def test_chinese_web_page_without_structured_recipe(self):
        # Structure réelle de 美食天下 : menu du site contenant « 食材 », bloc
        # 食材明细 nom/quantité sur deux lignes, métadonnées, étapes, bas de page.
        page = """<html><head><title>无水蛋糕的做法_无水蛋糕怎么做_美食天下</title></head><body>
        <div>首页</div><div>食材</div><div>菜谱</div><div>热菜</div>
        <fieldset><legend>食材明细</legend><div>主料</div><div>面粉</div><div>500克</div><div>鸡蛋</div><div>2个</div>
        <div>辅料(装饰)</div><div>牛奶</div><div>400毫升</div><div>调料</div><div>无</div><div>适量</div></fieldset>
        <div>半小时</div><div>耗时</div><div>初级</div><div>难度</div>
        <h2>无水蛋糕的做法步骤</h2><div>1</div><div>用鸡蛋牛奶和发酵粉和成发面</div><div>2</div><div>蒸半小时后关火</div>
        <div>来自美食天下的作品</div><div>所属分类:</div><div>糕点</div></body></html>"""
        recipe = main.parse_chinese_recipe_text(main.html_to_text(page))
        self.assertEqual(recipe["name"], "无水蛋糕")
        self.assertEqual([(i["name"], i["quantity"], i["unit"]) for i in recipe["ingredients"]],
                         [("Farine", 125, "Gr"), ("Oeufs", 0.5, "pièce"), ("Lait", 100, "ml")])
        self.assertEqual(recipe["description"], "1. 用鸡蛋牛奶和发酵粉和成发面\n2. 蒸半小时后关火")
        self.assertEqual((recipe["prep_time"], recipe["difficulty"], recipe["category"]), ("30", "Facile", "Dessert"))
        with patch.object(main, "_download_recipe_page", lambda request: page), \
             patch.object(main, "_fetch_recipe_reader_text", side_effect=AssertionError("service tiers non utilisé")):
            imported = main.fetch_recipe_from_url("https://home.meishichina.com/recipe-1.html")
        self.assertEqual(imported["name"], "无水蛋糕")

    def test_cooking_timers_in_chinese(self):
        durations = main.CookingModeWindow._step_durations
        cases = {"大火煮10分钟": 600, "小火炖两小时": 7200, "焖十五分钟": 900, "煮10到15分钟": 900,
                 "腌制半小时": 1800, "炖一个半小时": 5400, "静置30秒": 30}
        for text, seconds in cases.items():
            self.assertEqual([s for _, s in durations(text)], [seconds], text)
        self.assertEqual([main.chinese_number(x) for x in ("十", "十五", "二十五", "两", "二百五十")], [10, 15, 25, 2, 250])

    def test_expiry_dates_on_chinese_labels(self):
        today = datetime.date(2026, 10, 1)
        extract = main.extract_expiration_date_from_ocr_text
        self.assertEqual(extract("生产日期2026.09.01 保质期至2027年3月15日", today=today), datetime.date(2027, 3, 15))
        self.assertEqual(extract("生产日期：2026.09.30\n保质期：12个月", today=today), datetime.date(2027, 9, 30))
        self.assertEqual(main.parse_pantry_expiration("2027年3月15日"), datetime.date(2027, 3, 15))
        self.assertEqual(main.parse_pantry_expiration("2027/03/15"), datetime.date(2027, 3, 15))
        main.CURRENT_LANGUAGE = "zh"
        self.assertEqual(main.format_display_date(datetime.datetime(2027, 3, 5, 14, 7), with_time=True), "2027/03/05 14:07")
        main.CURRENT_LANGUAGE = "fr"
        self.assertEqual(main.format_display_date(datetime.date(2027, 3, 5)), "05/03/2027")

    def test_currency_lists_and_voice(self):
        main.CURRENT_LANGUAGE = "zh"
        self.assertEqual((main.get_currency(), main.format_price(2.5)), ("CNY", "¥2.50"))
        self.assertEqual(main.list_join(["盐", "糖"]), "盐，糖")
        main.set_currency("EUR")
        self.assertEqual(main.get_currency(), "EUR")  # un choix explicite l'emporte
        main.CURRENT_LANGUAGE = "fr"
        self.assertEqual(main.list_join(["sel", "sucre"]), "sel, sucre")
        voices = [SimpleNamespace(id="fr", languages=["fr-FR"]), SimpleNamespace(id="zh", languages=["zh-CN"])]
        self.assertEqual(main.pick_tts_voice_id(voices, "fr", "Cuire 10 min"), "fr")
        self.assertEqual(main.pick_tts_voice_id(voices, "fr", "大火煮10分钟"), "zh")
        self.assertIsNone(main.pick_tts_voice_id(voices[:1], "zh", "煮"))

    def test_open_food_facts_asks_for_the_chinese_name(self):
        seen = []

        def fake(request, timeout=None):
            seen.append(request.full_url)
            raise main.urllib.error.URLError("hors ligne")
        with patch.object(main.urllib.request, "urlopen", fake), self.assertRaises(main.urllib.error.URLError):
            main.lookup_open_food_facts("6901234567892")
        self.assertIn("product_name_zh", seen[0])

    @unittest.skipUnless(main.REPORTLAB_AVAILABLE if hasattr(main, "REPORTLAB_AVAILABLE") else True, "reportlab absent")
    def test_pdf_contains_chinese_text_within_the_page(self):
        import pypdfium2 as pdfium
        main.CURRENT_LANGUAGE = "fr"  # recette chinoise dans une interface française
        recipe = {"name": "红烧肉", "category": "Plat", "default_persons": 4, "ingredients": [],
                  "description": "五花肉切成约三厘米见方的块，冷水下锅焯水，撇去浮沫后捞出沥干。" * 6}
        path = Path(tempfile.mkdtemp()) / "zh.pdf"
        main.build_cookbook_pdf(str(path), [(recipe, 4)])
        pdf = pdfium.PdfDocument(str(path))
        text = "".join(pdf[i].get_textpage().get_text_range() for i in range(len(pdf)))
        self.assertIn("红烧肉", text)
        self.assertIn("焯水", text)
        page = pdf[len(pdf) - 1]
        textpage = page.get_textpage()
        right = max(textpage.get_charbox(i)[2] for i in range(textpage.count_chars()))
        self.assertLess(right, page.get_width())
        pdf.close()


if __name__ == "__main__":
    unittest.main()
