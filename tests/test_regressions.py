import json
import os
import tempfile
import tkinter as tk
import unittest
import zipfile
from pathlib import Path
from tkinter import ttk
from unittest.mock import patch

import main

DATA_GLOBALS = {
    "DATA_FILE": "recipes.json",
    "INGREDIENTS_FILE": "ingredients.json",
    "INGREDIENT_OVERRIDES_FILE": "ingredient_custom_data.json",
    "INGREDIENT_PRICES_FILE": "ingredient_prices.json",
    "WEEKLY_PLAN_FILE": "weekly_plan.json",
    "WEEKLY_PLAN_HISTORY_FILE": "weekly_plan_history.json",
    "WEEKLY_PLAN_TEMPLATES_FILE": "weekly_plan_templates.json",
    "MENUS_FILE": "menus.json",
    "TRASH_FILE": "trash.json",
    "RECENT_VIEWS_FILE": "recent_views.json",
    "SETTINGS_FILE": "settings.json",
    "SAVED_SHOPPING_LISTS_FILE": "saved_shopping_lists.json",
    "PANTRY_FILE": "pantry.json",
}

class TempDataMixin:
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        names = ["DATA_DIR", "IMAGES_DIR", "BACKUPS_DIR", "DRAFTS_DIR", "IMPORT_TEMP_DIR", *DATA_GLOBALS]
        self.old = {name: getattr(main, name) for name in names}
        main.DATA_DIR = str(self.base)
        main.IMAGES_DIR = str(self.base / "images")
        main.BACKUPS_DIR = str(self.base / "backups")
        main.DRAFTS_DIR = str(self.base / "drafts")
        main.IMPORT_TEMP_DIR = str(self.base / "import_temp")
        for d in (main.IMAGES_DIR, main.BACKUPS_DIR, main.DRAFTS_DIR, main.IMPORT_TEMP_DIR):
            os.makedirs(d, exist_ok=True)
        for g, filename in DATA_GLOBALS.items():
            setattr(main, g, str(self.base / filename))
        main._nutrition_cache = None
        main._ingredient_allergens_cache = None
        main._ingredient_substitutions_cache = None

    def tearDown(self):
        for g, value in self.old.items():
            setattr(main, g, value)
        self.tmp.cleanup()

class CoreRegressionTests(TempDataMixin, unittest.TestCase):
    def recipe(self, rid="r1", name="Test", persons=4, ingredients=None, images=None, cook_log=None):
        return {
            "id": rid,
            "name": name,
            "default_persons": persons,
            "ingredients": ingredients or [{"name": "Farine", "quantity": 100, "unit": "Gr"}],
            "images": images or [],
            "cook_log": cook_log or [],
        }

    def test_non_finite_numbers_rejected(self):
        for value in ("nan", "NaN", "inf", "-inf", float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                main.parse_positive_number(value)
        with self.assertRaises(ValueError):
            main._atomic_write_json(self.base / "bad.json", {"x": float("nan")})

    def test_recipe_payload_validation_and_safe_images(self):
        with self.assertRaises(ValueError):
            main.validate_recipes_payload({})
        r = self.recipe(images=["ok.jpg", "../evil.jpg", "folder/x.png"])
        r["cook_log"] = [{"photo": "../../bad.png"}, {"photo": "cook.jpg"}]
        clean = main.validate_recipes_payload([r])[0]
        self.assertEqual(clean["images"], ["ok.jpg"])
        self.assertNotIn("photo", clean["cook_log"][0])
        self.assertEqual(clean["cook_log"][1]["photo"], "cook.jpg")
        self.assertIsNone(main.safe_image_filename("../evil.jpg"))

    def test_unit_merging_and_scaling(self):
        r1 = self.recipe("r1", ingredients=[{"name":"Farine","quantity":100,"unit":"Gr"}])
        r2 = self.recipe("r2", name="B", ingredients=[{"name":"Farine","quantity":0.1,"unit":"Kilo"}])
        grouped = main.compute_grouped_totals([(r1, 1), (r2, 1)])
        flat = [(name, qty, unit) for _, items in grouped for name, qty, unit in items]
        self.assertTrue(any(name.lower()=="farine" and abs(float(qty)-200)<1e-6 and unit=="Gr" for name, qty, unit in flat))
        v1 = self.recipe("v1", ingredients=[{"name":"Lait","quantity":10,"unit":"cl"}])
        v2 = self.recipe("v2", name="V2", ingredients=[{"name":"Lait","quantity":100,"unit":"ml"}])
        grouped = main.compute_grouped_totals([(v1, 1), (v2, 1)])
        flat = [(name, qty, unit) for _, items in grouped for name, qty, unit in items]
        self.assertTrue(any(name.lower()=="lait" and abs(float(qty)-20)<1e-6 and unit=="cl" for name, qty, unit in flat))

    def test_pantry_decrement_uses_person_count(self):
        main.save_pantry({"farine": {"name":"Farine","quantity":1000,"unit":"Gr","threshold":None}})
        r = self.recipe(ingredients=[{"name":"Farine","quantity":100,"unit":"Gr"}])
        self.assertEqual(main.decrement_pantry_for_recipe(r, 4), 1)
        self.assertAlmostEqual(main.load_pantry()["farine"]["quantity"], 600)

    def test_pantry_decrement_cross_unit(self):
        main.save_pantry({"farine": {"name":"Farine","quantity":1.0,"unit":"Kilo","threshold":None}})
        r = self.recipe(ingredients=[{"name":"Farine","quantity":250,"unit":"Gr"}])
        main.decrement_pantry_for_recipe(r, 2)
        self.assertAlmostEqual(main.load_pantry()["farine"]["quantity"], 0.5)

    def test_cost_supports_kilo_and_litres(self):
        main.save_ingredient_prices({
            "farine":{"name":"Farine","price":10,"unit":"kg"},
            "lait":{"name":"Lait","price":2,"unit":"L"},
        })
        r = self.recipe(ingredients=[
            {"name":"Farine","quantity":1,"unit":"Kilo"},
            {"name":"Lait","quantity":500,"unit":"ml"},
        ])
        total, known, count = main.compute_recipe_cost(r, 2)
        self.assertAlmostEqual(total, 22.0)
        self.assertEqual((known, count), (2, 2))

    def test_cart_cost_sums_known_prices_and_counts_unknown(self):
        # compute_cart_cost partage la conversion d'unités de
        # compute_recipe_cost, mais part de quantités déjà absolues (liste
        # de courses sommée entre recettes), pas par personne.
        main.save_ingredient_prices({
            "farine": {"name": "Farine", "price": 10, "unit": "kg"},
            "lait": {"name": "Lait", "price": 2, "unit": "L"},
        })
        items = [
            {"name": "Farine", "quantity": 1000, "unit": "Gr", "rayon": "Epicerie"},
            {"name": "Lait", "quantity": 500, "unit": "cl", "rayon": "Cremerie"},
            {"name": "Sel", "quantity": 1, "unit": "pièce", "rayon": "Epicerie"},
        ]
        total, known, count = main.compute_cart_cost(items)
        self.assertAlmostEqual(total, 20.0)  # 1 kg farine (10) + 5 L lait (10)
        self.assertEqual((known, count), (2, 3))

    def test_cart_items_sorted_by_name_ignores_rayon(self):
        items = [
            {"name": "Yaourt", "quantity": 1, "unit": "pièce", "rayon": "Cremerie"},
            {"name": "Abricot", "quantity": 1, "unit": "pièce", "rayon": "Fruits"},
            {"name": "Farine", "quantity": 1, "unit": "Gr", "rayon": "Epicerie"},
        ]
        order = main._cart_items_sorted_by_name(items)
        self.assertEqual([items[i]["name"] for i in order], ["Abricot", "Farine", "Yaourt"])

    def test_plan_old_name_migrates_to_id_and_survives_rename(self):
        r = self.recipe("stable-id", name="Ancien nom")
        main.save_recipes([r])
        Path(main.WEEKLY_PLAN_FILE).write_text(json.dumps({
            "Lundi":{"Dîner — Plat":{"recipe_name":"Ancien nom","persons":4}}
        }, ensure_ascii=False), encoding="utf-8")
        plan = main.load_weekly_plan()
        self.assertEqual(plan["Lundi"]["Dîner — Plat"]["recipe_id"], "stable-id")
        r["name"] = "Nouveau nom"
        main.save_recipes([r])
        plan2 = main.load_weekly_plan()
        self.assertEqual(plan2["Lundi"]["Dîner — Plat"]["recipe_name"], "Nouveau nom")

    def test_menu_old_name_migrates_to_id(self):
        r = self.recipe("stable-id", name="Recette A")
        main.save_recipes([r])
        Path(main.MENUS_FILE).write_text(json.dumps([
            {"name":"Menu","items":[{"recipe_name":"Recette A","persons":2}]}
        ], ensure_ascii=False), encoding="utf-8")
        menus = main.load_menus()
        self.assertEqual(menus[0]["items"][0]["recipe_id"], "stable-id")

    def test_parser_extended_forms(self):
        p = main.parse_ingredient_line("2 x 400 g tomates")
        self.assertAlmostEqual(p["quantity"], 800)
        self.assertEqual(main.canonical_unit(p["unit"]), "gr")
        p = main.parse_ingredient_line("1 c. à soupe de sucre")
        self.assertAlmostEqual(p["quantity"], 1)
        self.assertEqual(main.canonical_unit(p["unit"]), "cuillère à soupe")
        p = main.parse_ingredient_line("sel")
        self.assertEqual(p["unit"], "au goût")
        p = main.parse_ingredient_line("1 1/2 kg de farine")
        self.assertAlmostEqual(p["quantity"], 1.5)
        self.assertEqual(main.canonical_unit(p["unit"]), "kg")

    def test_shared_backup_includes_cook_log_photo(self):
        (Path(main.IMAGES_DIR) / "cook.jpg").write_bytes(b"cook-photo")
        r = self.recipe(cook_log=[{"date":"2026-01-01","photo":"cook.jpg"}])
        main.save_recipes([r])
        main.save_ingredients(["Farine"])
        out = self.base / "shared.zip"
        main.build_shared_backup_zip(str(out))
        with zipfile.ZipFile(out, "r") as z:
            self.assertIn("images/cook.jpg", z.namelist())

    def test_shared_backup_importable_when_renamed_to_txt(self):
        # L'application mobile renomme ce zip en ".txt" avant de le
        # partager (Chromium refuse ".zip" dans son Web Share API, mais
        # accepte ".txt" ; le contenu reste un zip valide à l'octet
        # près). restore_from_shared_zip doit donc lire le fichier par
        # son contenu réel, pas par son extension.
        main.save_recipes([self.recipe(name="Recette partagée")])
        main.save_ingredients(["Farine"])
        zip_path = self.base / "sauvegarde-partagee.zip"
        main.build_shared_backup_zip(str(zip_path))
        disguised_path = self.base / "sauvegarde-partagee.txt"
        os.replace(zip_path, disguised_path)

        main.save_recipes([])
        main.save_ingredients([])
        main.restore_from_shared_zip(str(disguised_path), merge=False)
        self.assertEqual(main.load_recipes()[0]["name"], "Recette partagée")


    def test_cart_selection_uses_recipe_id(self):
        from types import SimpleNamespace
        r1 = self.recipe("id-a", name="Même nom", ingredients=[{"name":"Farine","quantity":100,"unit":"Gr"}])
        r2 = self.recipe("id-b", name="Même nom", ingredients=[{"name":"Farine","quantity":250,"unit":"Gr"}])
        dummy = SimpleNamespace(
            app=SimpleNamespace(recipes=[r1, r2]),
            _recipe_cart_persons={"id-b": 2},
            manual_items=[],
            current_items=[],
            last_chosen_recipes=[],
        )
        main.AllRecipesWindow._rebuild_cart_from_recipe_selection(dummy)
        self.assertEqual(len(dummy.current_items), 1)
        self.assertAlmostEqual(float(dummy.current_items[0]["quantity"]), 500)

    def test_full_restore_rolls_back_on_write_failure(self):
        main.save_recipes([self.recipe("old", "Avant")])
        main.save_pantry({"farine":{"name":"Farine","quantity":1,"unit":"Kilo"}})
        archive = self.base / "rollback.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("recipes.json", json.dumps([self.recipe("new", "Après")], ensure_ascii=False))
            z.writestr("pantry.json", json.dumps({"lait":{"name":"Lait","quantity":2,"unit":"Litre"}}, ensure_ascii=False))
        original = main._atomic_write_json
        calls = {"n": 0}
        def flaky(path, data):
            calls["n"] += 1
            if calls["n"] == 2:
                raise OSError("simulated disk failure")
            return original(path, data)
        main._atomic_write_json = flaky
        try:
            with self.assertRaises(OSError):
                main.restore_from_zip(str(archive), merge=False)
        finally:
            main._atomic_write_json = original
        self.assertEqual(main.load_recipes()[0]["id"], "old")
        self.assertIn("farine", main.load_pantry())

    def test_qr_payload_utf8_and_multi_part_roundtrip(self):
        r = self.recipe(name="Crème brûlée 🍮", ingredients=[
            {"name":"Crème fraîche","quantity":12.5,"unit":"cl"},
            {"name":"Sucre","quantity":25,"unit":"Gr"},
        ])
        r["description"] = "É" * 2200
        payload = main._recipe_to_mobile_qr_payload(r, 4)
        parts = main._split_mobile_qr_parts(payload, max_chunk_bytes=800)
        self.assertGreater(len(parts), 1)
        parsed = [main._parse_multi_qr_fragment(x) for x in parts]
        self.assertTrue(all(x is not None for x in parsed))
        assembled = "".join(x["chunk"] for x in sorted(parsed, key=lambda x: x["part_index"]))
        self.assertEqual(assembled, payload)
        prefill = main._compact_mobile_qr_to_prefill(payload)
        self.assertEqual(prefill["name"], "Crème brûlée 🍮")

    def test_full_restore_replace_clears_absent_files(self):
        main.save_pantry({"farine":{"name":"Farine","quantity":1,"unit":"Kilo"}})
        archive = self.base / "replace.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("recipes.json", json.dumps([self.recipe()], ensure_ascii=False))
        main.restore_from_zip(str(archive), merge=False)
        self.assertEqual(main.load_pantry(), {})
        self.assertEqual(len(main.load_recipes()), 1)

    def test_invalid_restore_does_not_change_existing_data(self):
        main.save_recipes([self.recipe("old", "Avant")])
        archive = self.base / "bad.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("recipes.json", '{"not":"a list"}')
        with self.assertRaises(Exception):
            main.restore_from_zip(str(archive), merge=False)
        self.assertEqual(main.load_recipes()[0]["id"], "old")

class StaticRegressionTests(unittest.TestCase):
    def test_dead_helpers_removed(self):
        src = Path(main.__file__).read_text(encoding="utf-8")
        for name in ("def _safe_sha256(", "def _run_async(", "def _ui_tooltip(",
                     "def convert_to_grams_equivalent(", "def open_recent_selected(",
                     "def open_wishlist_selected(", "def _merge_item_into_current("):
            self.assertNotIn(name, src)

    def test_no_extractall(self):
        self.assertNotIn(".extractall(", Path(main.__file__).read_text(encoding="utf-8"))

    def test_translation_key_coverage(self):
        fr = set(main.FRENCH_STRINGS)
        for lang in ("en","es","de"):
            self.assertEqual(fr, set(main.TRANSLATIONS[lang]))

    def test_shared_import_dialog_accepts_txt(self):
        # L'application mobile déguise ce zip en ".txt" avant de le
        # partager (voir test_shared_backup_importable_when_renamed_to_txt) :
        # le sélecteur de fichier doit donc aussi afficher les ".txt".
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.addCleanup(root.destroy)
        root.withdraw()
        win = main.ImportExportWindow(root)
        self.addCleanup(win.destroy)
        captured = {}
        def fake_askopenfilename(**kwargs):
            captured.update(kwargs)
            return ""
        with patch.object(main.filedialog, "askopenfilename", side_effect=fake_askopenfilename):
            win.import_shared_data()
        filetypes = dict(captured["filetypes"])
        self.assertIn("*.zip *.txt", filetypes.values())

class ContrastAccessibilityTests(unittest.TestCase):
    """Vérifie le ratio de contraste WCAG des combinaisons texte/fond
    réellement utilisées dans configure_app_style(), dans les deux palettes.
    Garde-fou contre une régression comme celle mesurée sur les boutons en
    thème sombre (texte blanc sur fond ACCENT : 2.65:1, sous le seuil AA de
    4.5:1) : ces tests échoueraient si une future modification de couleur
    recassait le contraste sans qu'on le remarque à l'œil."""

    @staticmethod
    def _luminance(hex_color):
        hex_color = hex_color.lstrip("#")
        channels = []
        for i in (0, 2, 4):
            c = int(hex_color[i:i + 2], 16) / 255.0
            channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
        r, g, b = channels
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    @classmethod
    def _contrast(cls, hex_a, hex_b):
        l1, l2 = cls._luminance(hex_a), cls._luminance(hex_b)
        lighter, darker = max(l1, l2), min(l1, l2)
        return (lighter + 0.05) / (darker + 0.05)

    def test_dark_mode_button_text_meets_aa_on_accent_backgrounds(self):
        # Le vrai bug corrigé : texte blanc illisible sur les boutons en
        # thème sombre (2.65:1 sur ACCENT, 2.00:1 sur ACCENT_DARK, tous deux
        # bien sous le seuil AA de 4.5:1). ON_ACCENT y vaut maintenant la
        # couleur de fond sombre (texte foncé), qui offre un vrai contraste.
        for bg_key in ("ACCENT", "ACCENT_DARK"):
            ratio = self._contrast(main.DARK_PALETTE["ON_ACCENT"], main.DARK_PALETTE[bg_key])
            self.assertGreaterEqual(
                ratio, 4.5,
                f"palette sombre : ON_ACCENT sur {bg_key} = {ratio:.2f}:1 (minimum WCAG AA 4.5:1)"
            )

    def test_light_mode_button_text_still_meets_minimum_ui_contrast(self):
        # Le thème clair (texte blanc sur ACCENT/ACCENT_DARK) était déjà
        # limite avant cette session — 3.06:1/4.36:1, sous le seuil AA
        # 4.5:1 pour du texte mais au-dessus du seuil 3:1 applicable aux
        # composants d'interface. Non touché ici (choix de couleur de marque
        # existant, pas une régression) : ce test garde seulement le plancher
        # 3:1 pour repérer une éventuelle aggravation future.
        for bg_key in ("ACCENT", "ACCENT_DARK"):
            ratio = self._contrast(main.LIGHT_PALETTE["ON_ACCENT"], main.LIGHT_PALETTE[bg_key])
            self.assertGreaterEqual(
                ratio, 3.0,
                f"palette claire : ON_ACCENT sur {bg_key} = {ratio:.2f}:1 (minimum 3:1)"
            )

    def test_danger_button_text_meets_aa_on_its_own_background(self):
        # Danger.TButton doit avoir son propre fond (comme Secondary.TButton),
        # pas hériter du fond ACCENT de TButton : sur ACCENT, ERROR tombait à
        # 1.74:1 (clair) / 1.01:1 (sombre) — illisible dans les deux thèmes.
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.addCleanup(root.destroy)
        root.withdraw()
        style = main.configure_app_style(root)
        actual_background = style.lookup("Danger.TButton", "background")
        self.assertNotEqual(
            actual_background, style.lookup("TButton", "background"),
            "Danger.TButton ne doit pas hériter du fond ACCENT de TButton"
        )
        self.assertEqual(actual_background, main.COLOR_CARD)
        for name, palette in (("clair", main.LIGHT_PALETTE), ("sombre", main.DARK_PALETTE)):
            ratio = self._contrast(palette["ERROR"], palette["CARD"])
            self.assertGreaterEqual(ratio, 4.5, f"palette {name} : ERROR sur CARD = {ratio:.2f}:1")

    def test_body_text_meets_aa_on_page_and_card_backgrounds(self):
        for name, palette in (("clair", main.LIGHT_PALETTE), ("sombre", main.DARK_PALETTE)):
            for bg_key in ("BG", "CARD"):
                ratio = self._contrast(palette["TEXT"], palette[bg_key])
                self.assertGreaterEqual(ratio, 4.5, f"palette {name} : TEXT sur {bg_key} = {ratio:.2f}:1")

    def test_secondary_text_colors_meet_aa_on_their_real_backgrounds(self):
        # Étend l'audit de contraste au-delà des boutons (déjà couverts
        # ci-dessus) : TEXT_MUTED, ACCENT_DARK utilisé comme texte, et GREEN
        # sont utilisés respectivement 70, 28 et plusieurs fois dans
        # configure_app_style()/les fenêtres (légendes, libellés de section,
        # pastilles de tag, validations) sur BG, CARD et ACCENT_LIGHT — trois
        # fonds jamais vérifiés jusqu'ici. Mesuré avant correction : jusqu'à
        # 2.98:1 (TEXT_MUTED sur ACCENT_LIGHT en clair), tous sous le seuil
        # WCAG AA 4.5:1 pour du texte normal.
        combos = [
            ("TEXT_MUTED", "BG"), ("TEXT_MUTED", "CARD"), ("TEXT_MUTED", "ACCENT_LIGHT"),
            ("ACCENT_DARK", "BG"), ("ACCENT_DARK", "CARD"), ("ACCENT_DARK", "ACCENT_LIGHT"),
            ("GREEN", "BG"), ("GREEN", "CARD"),
        ]
        for name, palette in (("clair", main.LIGHT_PALETTE), ("sombre", main.DARK_PALETTE)):
            for fg_key, bg_key in combos:
                ratio = self._contrast(palette[fg_key], palette[bg_key])
                self.assertGreaterEqual(
                    ratio, 4.5,
                    f"palette {name} : {fg_key} sur {bg_key} = {ratio:.2f}:1 (minimum WCAG AA 4.5:1)"
                )

    def test_danger_button_hover_text_meets_aa(self):
        # Danger.TButton passe au survol sur ACCENT_LIGHT (voir
        # configure_app_style) avec le texte ERROR par-dessus — un état
        # jamais mesuré par test_danger_button_text_meets_aa_on_its_own_background
        # ci-dessus, qui ne couvre que l'état au repos (fond CARD).
        for name, palette in (("clair", main.LIGHT_PALETTE), ("sombre", main.DARK_PALETTE)):
            ratio = self._contrast(palette["ERROR"], palette["ACCENT_LIGHT"])
            self.assertGreaterEqual(
                ratio, 4.5,
                f"palette {name} : ERROR sur ACCENT_LIGHT (survol Danger.TButton) = {ratio:.2f}:1"
            )

class ShoppingListWidgetTests(TempDataMixin, unittest.TestCase):
    """Instancie réellement les 3 fenêtres liste de courses (Toutes les
    recettes, Planning, Nouveau menu) pour vérifier que le coût total et le
    tri par nom s'affichent bien à l'écran, plutôt que d'inspecter le texte
    source des méthodes (ce que faisait l'ancienne version de ce test :
    elle passait même si le rendu réel était cassé)."""

    def setUp(self):
        super().setUp()
        main.save_recipes([{
            "id": "r1", "name": "Recette test", "default_persons": 2,
            "category": "Plat", "difficulty": "Facile", "images": [],
            "ingredients": [{"name": "Farine", "quantity": 200, "unit": "g"}],
        }])
        main.save_ingredients(["Farine"])
        main.save_ingredient_prices({"farine": {"name": "Farine", "price": 2, "unit": "kg"}})
        for name, value in (
            ("get_disclaimer_accepted", lambda: True),
            ("get_large_text_preference", lambda: False),
            ("get_language_preference", lambda: "fr"),
            ("maybe_create_auto_backup", lambda: None),
        ):
            patcher = patch.object(main, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        try:
            self.app = main.App()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.app.withdraw()
        self.addCleanup(self.app.destroy)

    @staticmethod
    def _descendants(widget):
        found = []
        for child in widget.winfo_children():
            found.append(child)
            found.extend(ShoppingListWidgetTests._descendants(child))
        return found

    def _assert_cost_and_sort_shown(self, win):
        self.addCleanup(win.destroy)
        win.current_items = [
            {"name": "Farine", "quantity": 2000, "unit": "g", "rayon": "Épicerie"},
        ]
        win._render_shopping_list()
        self.app.update()

        widgets = self._descendants(win.result_frame)
        expected_cost_text = main.t("onerecipe_cost_label", cost="4.00", partial="")
        labels = [w for w in widgets if isinstance(w, ttk.Label)]
        self.assertTrue(
            any(lbl.cget("text") == expected_cost_text for lbl in labels),
            f"coût attendu {expected_cost_text!r} absent, labels vus : {[lbl.cget('text') for lbl in labels]}",
        )

        radios = [w for w in widgets if isinstance(w, ttk.Radiobutton)]
        self.assertEqual(sorted(r.cget("value") for r in radios), ["nom", "rayon"])
        rayon_heading = main.translate_rayon_name("Épicerie")
        self.assertTrue(any(isinstance(w, ttk.Label) and w.cget("text") == rayon_heading for w in widgets))

        next(r for r in radios if r.cget("value") == "nom").invoke()
        self.app.update()
        self.assertEqual(win._shopping_sort_var.get(), "nom")
        widgets_after_sort = self._descendants(win.result_frame)
        self.assertFalse(any(
            isinstance(w, ttk.Label) and w.cget("text") == rayon_heading for w in widgets_after_sort
        ), "l'en-tête de rayon ne devrait plus apparaître après le tri par nom")

    def test_all_recipes_window_shows_cost_and_sort(self):
        self._assert_cost_and_sort_shown(main.AllRecipesWindow(self.app))

    def test_weekly_plan_window_shows_cost_and_sort(self):
        self._assert_cost_and_sort_shown(main.WeeklyPlanWindow(self.app))

    def test_menu_form_window_shows_cost_and_sort(self):
        self._assert_cost_and_sort_shown(main.MenuFormWindow(self.app, manager=None, menu_index=None))

if __name__ == "__main__":
    unittest.main(verbosity=2)
