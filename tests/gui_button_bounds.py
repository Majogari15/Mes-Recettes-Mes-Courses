import os, tempfile, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import main, tkinter as tk
from tkinter import ttk

def patch_data():
    base=Path(tempfile.mkdtemp(prefix='mesrecettes_gui_'))
    main.DATA_DIR=str(base)
    mapping={'DATA_FILE':'recipes.json','INGREDIENTS_FILE':'ingredients.json','INGREDIENT_OVERRIDES_FILE':'ingredient_custom_data.json','INGREDIENT_PRICES_FILE':'ingredient_prices.json','WEEKLY_PLAN_FILE':'weekly_plan.json','WEEKLY_PLAN_HISTORY_FILE':'weekly_plan_history.json','WEEKLY_PLAN_TEMPLATES_FILE':'weekly_plan_templates.json','MENUS_FILE':'menus.json','TRASH_FILE':'trash.json','RECENT_VIEWS_FILE':'recent_views.json','SETTINGS_FILE':'settings.json','SAVED_SHOPPING_LISTS_FILE':'saved_shopping_lists.json','PANTRY_FILE':'pantry.json'}
    for g,f in mapping.items(): setattr(main,g,str(base/f))
    main.IMAGES_DIR=str(base/'images'); main.BACKUPS_DIR=str(base/'backups'); main.DRAFTS_DIR=str(base/'drafts'); main.IMPORT_TEMP_DIR=str(base/'import_temp')
    for d in [main.IMAGES_DIR,main.BACKUPS_DIR,main.DRAFTS_DIR,main.IMPORT_TEMP_DIR]: os.makedirs(d,exist_ok=True)
    recipes=[{'id':f'r{i}','name':f'Recette {i}','default_persons':4,'category':'Plat','difficulty':'Facile','ingredients':[{'name':'Farine','quantity':100,'unit':'Gr'}],'images':[]} for i in range(5)]
    main.save_recipes(recipes); main.save_ingredients(['Farine','Lait','Oeuf','Sel','Poivre'])

def descendants(w):
    for c in w.winfo_children():
        yield c
        yield from descendants(c)

def check_buttons(win,name):
    win.update_idletasks(); win.update()
    top=win.winfo_rooty(); left=win.winfo_rootx(); bottom=top+win.winfo_height(); right=left+win.winfo_width()
    bad=[]
    for w in descendants(win):
        if not isinstance(w,(ttk.Button,tk.Button)) or not w.winfo_ismapped(): continue
        # Ignore widgets whose nearest canvas ancestor means they are intentionally scrollable.
        a=w.master; in_canvas=False
        while a is not None and a is not win:
            if isinstance(a,tk.Canvas): in_canvas=True; break
            a=getattr(a,'master',None)
        if in_canvas: continue
        x=w.winfo_rootx(); y=w.winfo_rooty(); x2=x+w.winfo_width(); y2=y+w.winfo_height()
        if x < left-2 or x2 > right+2 or y < top-2 or y2 > bottom+2:
            bad.append((str(w),w.cget('text'),x-left,y-top,w.winfo_width(),w.winfo_height(),win.winfo_width(),win.winfo_height()))
    print(name,'bad',len(bad))
    for b in bad[:20]: print(' ',b)
    if bad: raise AssertionError(name)

def run(large=False):
    patch_data(); main.get_disclaimer_accepted=lambda:True; main.get_large_text_preference=lambda:large; main.get_language_preference=lambda:'fr'; main.maybe_create_auto_backup=lambda:None
    app=main.App(); app.update()
    classes=[('Mes recettes',lambda:main.ManageRecipesWindow(app)),('Mes courses',lambda:main.AllRecipesWindow(app)),('Planning',lambda:main.WeeklyPlanWindow(app)),('Garde-manger',lambda:main.PantryWindow(app)),('Que cuisiner',lambda:main.WhatCanICookWindow(app)),('Gerer ingredients',lambda:main.ManageIngredientsWindow(app)),('Editer ingredient',lambda:main.IngredientEditWindow(app,existing_name='Farine')),('Menu form',lambda:main.MenuFormWindow(app,None,None)),('Ajouter recette',lambda:main.RecipeFormWindow(app,None))]
    for name,f in classes:
        w=f(); app.update(); check_buttons(w,name); w.destroy(); app.update()
    app.destroy()
if __name__=='__main__': run('--large' in sys.argv)
