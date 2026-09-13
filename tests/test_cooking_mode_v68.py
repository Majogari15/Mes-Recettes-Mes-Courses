"""Tests ciblés des widgets cuisine, sans chargement des données utilisateur."""
import ast
import json
import math
import re
import threading
from tkinter import font as tkfont
from unittest.mock import patch
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox
import unittest
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]

class CookingModeTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.root.withdraw()
        confirm = patch.object(messagebox, "askyesno", return_value=True)
        confirm.start()
        self.addCleanup(confirm.stop)
        self.errors = []
        self.root.report_callback_exception = lambda *args: self.errors.append(args)
        self.clock = SimpleNamespace(value=100.0)
        strings = json.loads((ROOT/'i18n_desktop.json').read_text(encoding='utf-8'))['fr']
        self.env = dict(tk=tk, ttk=ttk, messagebox=messagebox, math=math, re=re, threading=threading, tkfont=tkfont,
            time=SimpleNamespace(monotonic=lambda: self.clock.value),
            t=lambda key, **kw: strings.get(key, key).format(**kw), sf=lambda v:v, gs=lambda v:v,
            COLOR_CARD='#ffffff', COLOR_BORDER='#cccccc', COLOR_ACCENT_DARK='#a05020', COLOR_ERROR='#ff0000',
            fit_window_to_workarea=lambda win,*args,**kw: win.geometry('1200x800'),
            get_usable_screen_height=lambda win:800,
            translate_ingredient_name=lambda x:x, translate_unit_name=lambda x:x,
            ingredient_quantity_for_persons=lambda ing,p:ing['quantity']*p,
            translate_difficulty_name=lambda x:x, log_internal_error=lambda *a:None)
        tree = ast.parse((ROOT/'main.py').read_text(encoding='utf-8'))
        nodes=[n for n in tree.body if isinstance(n,ast.ClassDef) and n.name in ('TimerRow','CookingModeWindow')]
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'main.py','exec'),self.env)
        recipe=dict(name='Recette test',ingredients=[dict(name='Pommes de terre',quantity=200,unit='g')],
                    description='Préparer et cuire les ingrédients. '*35,personal_notes='Notes de cuisson. '*20)
        self.window=self.env['CookingModeWindow'](self.root,recipe,2)
        self.window.geometry('1400x850')
        self.root.update()
    def tearDown(self):
        if hasattr(self,'root'):
            self.root.destroy()
    def duration(self,row,seconds):
        row.minutes_entry.delete(0,'end');row.minutes_entry.insert(0,'0')
        row.seconds_entry.delete(0,'end');row.seconds_entry.insert(0,str(seconds))
    def test_independent_timers_duration_pause_resume(self):
        w=self.window
        self.assertEqual(len(w.timer_rows),1)
        w.add_timer();a,b=w.timer_rows
        self.duration(a,25);self.duration(b,50)
        a.start();b.start()
        self.assertEqual(a.remaining_seconds,25)
        self.clock.value+=10;a._tick();b._tick()
        self.assertEqual((a.remaining_seconds,b.remaining_seconds),(15,40))
        a.pause();self.clock.value+=5;b._tick()
        self.assertEqual((a.remaining_seconds,b.remaining_seconds),(15,35))
        a.start();self.clock.value+=3;a._tick()
        self.assertEqual(a.remaining_seconds,12)
        a.pause();a.reset();self.duration(a,7);a.start()
        self.assertEqual(a.remaining_seconds,7)
    def test_resize_and_persons_preserve_timers(self):
        w=self.window;row=w.timer_rows[0];row.start()
        w._adjust(1);self.root.update()
        self.assertIs(w.timer_rows[0],row);self.assertTrue(row.running)
        self.assertEqual(int(w.steps_panel.grid_info()['column']),1)
        w.geometry('760x850');self.root.update()
        self.assertEqual(int(w.steps_panel.grid_info()['row']),1)
        for panel in (w.ingredients_panel,w.steps_panel):
            self.assertLessEqual(panel.winfo_width(),w.canvas.winfo_width())
            for label in panel.winfo_children():
                if not isinstance(label, (tk.Label, tk.Checkbutton)):
                    continue
                self.assertLessEqual(int(float(label.cget('wraplength'))),panel.winfo_width())
        w.geometry('1400x850');self.root.update()
        self.assertEqual(int(w.steps_panel.grid_info()['column']),1)
        self.assertLess(w.ingredients_panel.winfo_rootx(),w.steps_panel.winfo_rootx())
        self.assertEqual(self.errors,[])
    def test_finish_remove_and_close(self):
        w=self.window;w.add_timer();a,b=w.timer_rows
        self.duration(a,1);a.start();b.start()
        self.clock.value+=2;a._tick()
        self.assertTrue(a.finished)
        w.remove_timer(a);self.assertFalse(a.winfo_exists());self.assertTrue(b.running)
        w.remove_timer(b);self.assertEqual(len(w.timer_rows),1);self.assertFalse(b.running)
        b.start();w._on_close();self.root.update()
        self.assertFalse(b.running);self.assertEqual(self.errors,[])



class TimerLogicTests(unittest.TestCase):
    def test_duration_independence_pause_finish_cleanup_without_display(self):
        clock=SimpleNamespace(value=100.)
        ns=dict(tk=SimpleNamespace(Frame=object),math=math,
                time=SimpleNamespace(monotonic=lambda:clock.value))
        tree=ast.parse((ROOT/'main.py').read_text(encoding='utf-8'))
        node=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='TimerRow')
        exec(compile(ast.Module(body=[node],type_ignores=[]),'TimerRow','exec'),ns)
        class Field:
            def __init__(self,value=''):self.value=value
            def get(self):return self.value
            def config(self,**kw):pass
        def row(seconds):
            r=object.__new__(ns['TimerRow']);r.running=False;r.finished=False;r._started=False
            r._after_id=None;r._flash_after_id=None;r.remaining_seconds=600
            r.minutes_entry=Field('0');r.seconds_entry=Field(str(seconds))
            r.start_button=Field();r.pause_button=Field();r._refresh_display=lambda:None
            r.after=lambda *a:'tick';r.after_cancel=lambda *a:None
            r._start_flash=lambda:None
            return r
        a,b=row(25),row(50);a.start();b.start()
        self.assertEqual((a.remaining_seconds,b.remaining_seconds),(25,50))
        clock.value+=10;a._tick();b._tick()
        self.assertEqual((a.remaining_seconds,b.remaining_seconds),(15,40))
        a.pause();clock.value+=5;b._tick();a.start()
        self.assertEqual((a.remaining_seconds,b.remaining_seconds),(15,35))
        clock.value+=16;a._tick();self.assertTrue(a.finished)
        b.cancel();self.assertFalse(b.running)

    def test_responsive_column_decision_without_display(self):
        ns=dict(tk=SimpleNamespace(Toplevel=object),gs=lambda x:x)
        tree=ast.parse((ROOT/'main.py').read_text(encoding='utf-8'))
        node=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='CookingModeWindow')
        exec(compile(ast.Module(body=[node],type_ignores=[]),'CookingMode','exec'),ns)
        class Panel:
            def grid_forget(self):pass
            def grid(self,**kw):self.position=kw
            def columnconfigure(self,*a,**kw):pass
        w=object.__new__(ns['CookingModeWindow']);w.ingredients_panel=Panel();w.steps_panel=Panel();w.recipe_columns=Panel()
        for width,row,column in ((1400,0,1),(760,1,0),(1200,0,1)):
            w._layout_recipe(width)
            self.assertEqual((w.steps_panel.position['row'],w.steps_panel.position['column']),(row,column))

if __name__=='__main__':unittest.main()
