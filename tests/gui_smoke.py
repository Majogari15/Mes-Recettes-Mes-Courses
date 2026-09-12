import os, tempfile, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main

def patch_data():
    base=Path(tempfile.mkdtemp(prefix='mesrecettes_gui_'))
    main.DATA_DIR=str(base)
    mapping={
        'DATA_FILE':'recipes.json','INGREDIENTS_FILE':'ingredients.json','INGREDIENT_OVERRIDES_FILE':'ingredient_custom_data.json',
        'INGREDIENT_PRICES_FILE':'ingredient_prices.json','WEEKLY_PLAN_FILE':'weekly_plan.json','WEEKLY_PLAN_HISTORY_FILE':'weekly_plan_history.json',
        'WEEKLY_PLAN_TEMPLATES_FILE':'weekly_plan_templates.json','MENUS_FILE':'menus.json','TRASH_FILE':'trash.json',
        'RECENT_VIEWS_FILE':'recent_views.json','SETTINGS_FILE':'settings.json','SAVED_SHOPPING_LISTS_FILE':'saved_shopping_lists.json',
        'PANTRY_FILE':'pantry.json'}
    for g,f in mapping.items(): setattr(main,g,str(base/f))
    main.IMAGES_DIR=str(base/'images'); main.BACKUPS_DIR=str(base/'backups'); main.DRAFTS_DIR=str(base/'drafts'); main.IMPORT_TEMP_DIR=str(base/'import_temp')
    for d in [main.IMAGES_DIR,main.BACKUPS_DIR,main.DRAFTS_DIR,main.IMPORT_TEMP_DIR]: os.makedirs(d,exist_ok=True)
    recipes=[]
    for i in range(8):
        recipes.append({'id':f'r{i}','name':f'Recette {i}','default_persons':4,'category':'Plat','difficulty':'Facile','ingredients':[{'name':'Farine','quantity':100+i,'unit':'Gr'},{'name':'Lait','quantity':10,'unit':'cl'}],'images':[]})
    main.save_recipes(recipes); main.save_ingredients(['Farine','Lait','Oeuf','Sel','Poivre'])
    return base

def check_top(win, name):
    win.update_idletasks(); win.update()
    sw,sh=win.winfo_screenwidth(),win.winfo_screenheight()
    x,y,w,h=win.winfo_x(),win.winfo_y(),win.winfo_width(),win.winfo_height()
    if x < -5 or y < -5 or x+w > sw+5 or y+h > sh+5:
        raise AssertionError(f'{name}: geometry {x},{y},{w},{h} outside {sw}x{sh}')
    print(f'OK {name}: {w}x{h} at {x},{y} / {sw}x{sh}')

def run(large=False):
    patch_data()
    main.get_disclaimer_accepted=lambda: True
    main.get_large_text_preference=lambda: large
    main.get_language_preference=lambda: 'fr'
    main.maybe_create_auto_backup=lambda: None
    app=main.App(); app.update(); check_top(app,'Accueil')
    classes=[
        ('Mes recettes', lambda: main.ManageRecipesWindow(app)),
        ('Mes courses', lambda: main.AllRecipesWindow(app)),
        ('Planning', lambda: main.WeeklyPlanWindow(app)),
        ('Garde-manger', lambda: main.PantryWindow(app)),
        ('Que cuisiner', lambda: main.WhatCanICookWindow(app)),
        ('Recherche ingredient', lambda: main.IngredientSearchWindow(app)),
        ('Comparer', lambda: main.CompareRecipesWindow(app)),
        ('Livre PDF', lambda: main.CookbookExportWindow(app)),
        ('Gerer ingredients', lambda: main.ManageIngredientsWindow(app)),
        ('Editer ingredient', lambda: main.IngredientEditWindow(app, existing_name='Farine')),
        ('Menu manager', lambda: main.MenuManagerWindow(app)),
        ('Menu formulaire', lambda: main.MenuFormWindow(app, manager=None, menu_index=None)),
        ('Ajouter recette', lambda: main.RecipeFormWindow(app, recipe_index=None)),
    ]
    for name,create in classes:
        try:
            w=create(); app.update(); check_top(w,name); w.destroy(); app.update()
        except Exception as e:
            print('FAIL',name,type(e).__name__,e); raise
    app.destroy()

if __name__=='__main__':
    import sys
    run('--large' in sys.argv)
