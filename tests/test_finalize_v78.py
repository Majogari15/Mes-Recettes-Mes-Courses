"""Cases from the seven user PDFs and the data-safety audit."""
import copy
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock
import zipfile
import main
from test_regressions import TempDataMixin

class FinalizeV78Tests(TempDataMixin, unittest.TestCase):
    def recipe(self, **fields):
        r={'id':'recipe1','name':'Recette','default_persons':4,'ingredients':[{'name':'Farine','quantity':25,'unit':'Gr'}]}
        r.update(fields)
        return r

    def fetch(self, **fields):
        r={'@type':'Recipe','name':'Test','recipeYield':4,'recipeIngredient':['1 egg'],'recipeInstructions':['Mélanger.']}
        r.update(fields)
        page='<script type="application/ld+json">'+json.dumps(r)+'</script>'
        with patch.object(main,'_download_recipe_page',return_value=page):
            return main.fetch_recipe_from_url('https://example.com')

    def test_pdf_ingredients_and_allergens(self):
        for line,qty,unit,food,allergen in [
            ('1 egg',1,'pièce','Oeuf','Œufs'),
            ('1 1/2 to 2 cups milk',1.5,'cup','Lait','Lactose'),
            ('10 ounces (about 2 cups) all-purpose flour',10,'oz','Farine','Gluten'),
            ('1 1/2 cups (about 12 ounces) buttermilk',1.5,'cup','Babeurre','Lactose'),
            ('1 cup (about 8 ounces) sour cream',1,'cup','Crème aigre','Lactose'),
            ('1 (50-55 g) oeuf',1,'pièce','Oeuf','Œufs')]:
            with self.subTest(line=line):
                item=main._parse_url_ingredient(line)
                self.assertEqual((item['quantity'],item['unit']),(qty,unit))
                self.assertTrue(item['name'].startswith(food),item)
                self.assertIn(allergen,main.get_ingredient_allergens(item['name']))
                self.assertNotIn('((',item['name'])

    def test_egg_canonical_name_has_no_duplicate(self):
        names=[main._parse_url_ingredient(x)['name'] for x in ['1 egg','1 oeuf','1 œuf']]
        self.assertEqual(set(names),{'Oeuf'})
        self.assertEqual(main.save_ingredients(names),['Oeuf'])

    def test_ranges_preserve_totals_and_explanation(self):
        r=self.fetch(recipeYield='4 to 6 servings',recipeIngredient=['1½ to 2 cups milk'])
        self.assertEqual(r['default_persons'],4)
        self.assertEqual(r['ingredients'][0]['quantity']*4,1.5)
        self.assertIn('4 to 6 servings',r['personal_notes'])
        self.assertIn('1½ to 2 cups milk',r['personal_notes'])
        self.assertIn('Lactose',r['allergens'])

    def test_notes_and_no_invented_time(self):
        r=self.fetch(recipeInstructions=['Badigeonnez d’huile la poêle.','Enfournez pour 40 min.','Voici les produits particuliers de cette recette ! Conseils.'])
        self.assertIn('huile',r['personal_notes'])
        self.assertIn('40 min',r['personal_notes'])
        self.assertEqual(r['cook_time'],'')
        self.assertNotIn('Voici les produits',r['description'])
        self.assertIn('Voici les produits',r['personal_notes'])

    def test_dietary_qualifiers_retained(self):
        for x in ['(sans gluten) flour','gluten-free flour','vegan sour cream','lactose free milk']:
            self.assertEqual(main.get_ingredient_allergens(x),[])

    def test_draft_containment_and_legacy(self):
        victim=self.base/'outside.json';victim.write_text('keep')
        # recipe_draft_path() compare via os.path.realpath(DRAFTS_DIR) pour sa
        # propre verification de confinement ; certains runners Windows
        # resolvent un composant du chemin temporaire (ex. le dossier du
        # compte utilisateur) sous sa forme courte 8.3 (RUNNER~1) via
        # realpath, alors que main.DRAFTS_DIR (fixe par le test) garde la
        # forme longue d'origine. Comparer ici avec le meme realpath evite un
        # faux echec du au choix de representation, sans rien assouplir a la
        # verification de securite elle-meme.
        drafts_root=os.path.realpath(main.DRAFTS_DIR)
        for rid in ['x/../../outside','..\\..\\outside','a/b','C:\\temp\\x']:
            path=main.recipe_draft_path(rid)
            self.assertEqual(os.path.commonpath([drafts_root,path]),drafts_root)
            main._atomic_write_json(path,{'name':'draft'})
            main.delete_recipe_draft({'id':rid})
            self.assertFalse(Path(path).exists())
            self.assertEqual(victim.read_text(),'keep')
        self.assertEqual(Path(main.recipe_draft_path('abc123')).name,'recipe_abc123.json')

    def test_duplicate_ids_rejected_before_write(self):
        main.save_recipes([self.recipe()]);before=Path(main.DATA_FILE).read_bytes()
        with self.assertRaises(ValueError):main.save_recipes([self.recipe(),self.recipe(name='Autre')])
        self.assertEqual(Path(main.DATA_FILE).read_bytes(),before)

    def test_both_restore_modes_preserve_local_conflict_and_repeat(self):
        for restore in [main.restore_from_shared_zip,main.restore_from_zip]:
            with self.subTest(restore=restore.__name__):
                main.save_recipes([self.recipe(personal_notes='Récent',times_cooked=5)])
                path=self.base/'older.zip'
                with zipfile.ZipFile(path,'w') as z:
                    z.writestr('recipes.json',json.dumps([self.recipe(personal_notes='Ancien',times_cooked=1)]))
                restore(str(path),True)
                recipes=main.load_recipes()
                self.assertEqual(len(recipes),2)
                self.assertEqual(main.find_recipe_by_id(recipes,'recipe1')['personal_notes'],'Récent')
                self.assertEqual(main.find_recipe_by_id(recipes,'recipe1')['times_cooked'],5)
                self.assertEqual(len({r['id'] for r in recipes}),2)
                restore(str(path),True)
                self.assertEqual(len(main.load_recipes()),2)

    def test_full_merge_remaps_imported_menu(self):
        main.save_recipes([self.recipe(personal_notes='Local')])
        path=self.base/'menu.zip'
        with zipfile.ZipFile(path,'w') as z:
            z.writestr('recipes.json',json.dumps([self.recipe(personal_notes='Import')]))
            z.writestr('menus.json',json.dumps([{'name':'Menu','recipes':[{'recipe_id':'recipe1','recipe_name':'Recette','persons':4}]}]))
        main.restore_from_zip(str(path),True)
        recipes=main.load_recipes();imported=next(r for r in recipes if r['id']!='recipe1')
        self.assertIn(imported['id'],Path(main.MENUS_FILE).read_text())

    def test_post_commit_ui_error_preserves_photo(self):
        main.save_recipes([self.recipe()])
        photo=Path(main.IMAGES_DIR)/'journal.jpg';photo.write_bytes(b'photo')
        captured={}
        def dialog(app,name,callback,**kw):captured['callback']=callback
        window=SimpleNamespace(current_recipe=self.recipe(),pers_entry=SimpleNamespace(get=lambda:'4'),app=SimpleNamespace(refresh_recipes=Mock(side_effect=RuntimeError('UI failed'))))
        with patch.object(main,'CookLogEntryDialog',side_effect=dialog):
            main.OneRecipeWindow.mark_as_cooked(window)
        closed=Mock()
        fake=SimpleNamespace(note_text=SimpleNamespace(get=lambda *a:''),comment_text=SimpleNamespace(get=lambda *a:''),photo_path='source',rating_combo=SimpleNamespace(current=lambda:3),on_done=captured['callback'],persons=4,destroy=closed)
        with patch.object(main,'copy_image_to_store',return_value='journal.jpg'),patch.object(main.messagebox,'showwarning'):
            main.CookLogEntryDialog.save(fake)
        self.assertTrue(photo.exists());closed.assert_called_once()
        self.assertEqual(main.load_recipes()[0]['times_cooked'],1)
        self.assertEqual(main.load_recipes()[0]['cook_log'][0]['photo'],'journal.jpg')

    def test_pre_commit_error_cleans_photo(self):
        photo=Path(main.IMAGES_DIR)/'journal.jpg';photo.write_bytes(b'photo')
        fake=SimpleNamespace(note_text=SimpleNamespace(get=lambda *a:''),comment_text=SimpleNamespace(get=lambda *a:''),photo_path='source',rating_combo=SimpleNamespace(current=lambda:3),on_done=Mock(side_effect=OSError('Disk full')),persons=4,destroy=Mock())
        with patch.object(main,'copy_image_to_store',return_value='journal.jpg'),patch.object(main.messagebox,'showerror'):
            main.CookLogEntryDialog.save(fake)
        self.assertFalse(photo.exists());fake.destroy.assert_not_called()

    def test_fraction_pdf_text(self):
        c=main.pdf_canvas.Canvas(io.BytesIO())
        lines=main._pdf_wrap_lines(c,'1⁄4 cup et ½ cuillère',400)
        self.assertEqual(lines,['1/4 cup et 1/2 cuillère'])

    def test_long_notes_not_truncated_in_editor(self):
        text='Conseil utile. '*100
        widget=Mock()
        widget.get.return_value=text
        form=SimpleNamespace(notes_text=widget,notes_counter_label=Mock())
        main.RecipeFormWindow._on_notes_modified(form)
        widget.delete.assert_not_called()
        widget.insert.assert_not_called()
        self.assertIn(str(len(text)),form.notes_counter_label.config.call_args.kwargs['text'])
