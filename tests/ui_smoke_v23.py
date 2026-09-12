import os, sys, tempfile, tkinter as tk
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import main

# Never touch user data during UI smoke tests.
td = tempfile.TemporaryDirectory()
base = td.name
main.DATA_DIR = base
main.DATA_FILE = os.path.join(base, 'recipes.json')
main.INGREDIENTS_FILE = os.path.join(base, 'ingredients.json')
main.PANTRY_FILE = os.path.join(base, 'pantry.json')
main.MENUS_FILE = os.path.join(base, 'menus.json')
main.WEEKLY_PLAN_FILE = os.path.join(base, 'weekly_plan.json')
main.WEEKLY_PLAN_HISTORY_FILE = os.path.join(base, 'weekly_plan_history.json')
main.WEEKLY_PLAN_TEMPLATES_FILE = os.path.join(base, 'weekly_plan_templates.json')
main.SAVED_SHOPPING_LISTS_FILE = os.path.join(base, 'saved_shopping_lists.json')
main.SETTINGS_FILE = os.path.join(base, 'settings.json')
main.IMAGES_DIR = os.path.join(base, 'images'); os.makedirs(main.IMAGES_DIR, exist_ok=True)

recipes = [
    {'id':'r1','name':'Poulet curry','category':'Plat','default_persons':4,'ingredients':[{'name':'Poulet','quantity':150,'unit':'Gr'},{'name':'Riz','quantity':75,'unit':'Gr'}], 'images':[]},
    {'id':'r2','name':'Tarte aux pommes','category':'Dessert','default_persons':6,'ingredients':[{'name':'Pomme','quantity':1,'unit':'pièce'},{'name':'Farine','quantity':40,'unit':'Gr'}], 'images':[]},
    {'id':'r3','name':'Soupe','category':'Entrée','default_persons':2,'ingredients':[{'name':'Carotte','quantity':2,'unit':'pièce'}], 'images':[]},
]
main.save_recipes(recipes)
main.save_ingredients(['Poulet','Riz','Pomme','Farine','Carotte','Sel'])
main.save_pantry({})
main.apply_font_scale(os.environ.get('LARGE_TEXT') == '1')
main.apply_palette(False)

class FakeApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.recipes = main.load_recipes()
        self.ingredient_names = main.load_ingredients()
        self.shopping_selection = {}
        self.dark_mode = False
        self.large_text = os.environ.get('LARGE_TEXT') == '1'
        main.configure_app_style(self)
    def refresh_recipes(self): self.recipes = main.load_recipes()
    def refresh_ingredients(self): self.ingredient_names = main.load_ingredients()
    def show_toast(self,*a,**k): pass

root=FakeApp(); root.geometry('700x500+0+0'); root.update()

class Manager:
    def _populate(self): pass
manager=Manager()

windows=[]
constructors=[
    ('Mes recettes', lambda: main.ManageRecipesWindow(root)),
    ('Toutes les recettes', lambda: main.AllRecipesWindow(root)),
    ('Planning', lambda: main.WeeklyPlanWindow(root)),
    ('Garde-manger', lambda: main.PantryWindow(root)),
    ('Gérer ingrédients', lambda: main.ManageIngredientsWindow(root)),
    ('Éditer ingrédient', lambda: main.IngredientEditWindow(root, existing_name='Farine')),
    ('Menu', lambda: main.MenuFormWindow(root, manager)),
    ('Comparer', lambda: main.CompareRecipesWindow(root)),
    ('Recherche ingrédient', lambda: main.IngredientSearchWindow(root)),
    ('Que cuisiner', lambda: main.WhatCanICookWindow(root)),
    ('Livre PDF', lambda: main.CookbookExportWindow(root)),
    ('Voir recette', lambda: main.OneRecipeWindow(root)),
]

failed=[]
for name, ctor in constructors:
    try:
        w=ctor(); w.update_idletasks(); w.update()
        sw=w.winfo_screenwidth(); sh=w.winfo_screenheight()
        x=w.winfo_rootx(); y=w.winfo_rooty(); ww=w.winfo_width(); hh=w.winfo_height()
        # Client bounds must fit the virtual display; Windows gets an extra work-area guard.
        ok=(x >= -5 and y >= -5 and x+ww <= sw+5 and y+hh <= sh+5)
        if not ok: failed.append((name,x,y,ww,hh,sw,sh))
        w.destroy(); root.update()
    except Exception as exc:
        failed.append((name, type(exc).__name__, str(exc)))

root.destroy(); td.cleanup()
if failed:
    print('FAIL', failed)
    raise SystemExit(1)
print('UI_SMOKE_OK', root if False else '', 'large=',os.environ.get('LARGE_TEXT'))
