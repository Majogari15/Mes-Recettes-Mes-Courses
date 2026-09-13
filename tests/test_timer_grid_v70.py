"""Geometrie des minuteurs selon les dimensions mesurees des controles."""
import ast
import math
from pathlib import Path
from types import SimpleNamespace
import unittest

class TimerGridTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree=ast.parse((Path(__file__).resolve().parents[1]/'main.py').read_text(encoding='utf-8'))
        node=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='CookingModeWindow')
        ns={'tk':SimpleNamespace(Toplevel=object),'math':math}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'cooking','exec'),ns)
        cls.geometry=staticmethod(ns['CookingModeWindow']._timer_grid_size)
    def test_wide_three_timers_share_a_row(self):
        columns,height=self.geometry(1500,400,190,3,360)
        self.assertEqual(columns,3)
        self.assertGreaterEqual(height,190)
    def test_narrow_complete_rows(self):
        columns,height=self.geometry(600,400,190,3,500)
        self.assertEqual(columns,1)
        self.assertEqual(height,2*190+12)
    def test_large_fonts_never_clip_single_timer(self):
        columns,height=self.geometry(1100,550,320,1,200)
        self.assertEqual(columns,1)
        self.assertGreaterEqual(height,320)
    def test_return_to_one_timer(self):
        self.assertEqual(self.geometry(1800,400,190,1,400),(1,202))

if __name__=='__main__':unittest.main()
