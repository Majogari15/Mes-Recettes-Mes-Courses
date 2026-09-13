import ast
import math
import re
from pathlib import Path
from types import SimpleNamespace
import unittest

class CookingAdditionsTests(unittest.TestCase):
    def setUp(self):
        tree=ast.parse((Path(__file__).resolve().parents[1]/'main.py').read_text(encoding='utf-8'))
        self.ns=dict(tk=SimpleNamespace(Frame=object,Toplevel=object,END='end'),math=math,re=re)
        self.clock=SimpleNamespace(now=100.)
        self.ns['time']=SimpleNamespace(monotonic=lambda:self.clock.now)
        nodes=[n for n in tree.body if isinstance(n,ast.ClassDef) and n.name in ('TimerRow','CookingModeWindow')]
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'cooking','exec'),self.ns)
    def test_explicit_durations_four_languages(self):
        parse=self.ns['CookingModeWindow']._step_durations
        for text,expected in [('Cuire 12-15 min.',900),('Cuire 1 à 2 minutes',120),('Bake 2 hours.',7200),('Cocinar 20 minutos.',1200),('20 Sekunden warten.',20),('2 Stunden garen.',7200)]:
            self.assertEqual(parse(text)[0][1],expected)
        self.assertEqual(parse('Four à 180°C, pour 4 personnes.'),[])
    def test_extend_running_preserves_other_timer_deadline(self):
        row=object.__new__(self.ns['TimerRow']);row.finished=False;row.running=True
        row._deadline=150.;row._refresh_display=lambda:None
        row.extend(60);self.assertEqual(row._deadline,210.);self.assertEqual(row.remaining_seconds,110)
        self.clock.now=130.;row.extend(300);self.assertEqual(row.remaining_seconds,380)
    def test_close_cancel_keeps_timer_running(self):
        w=object.__new__(self.ns['CookingModeWindow'])
        w.timer_rows=[SimpleNamespace(running=True)];w.stop_speech=lambda:self.fail('closed despite cancellation')
        self.ns.update(t=lambda k:k,messagebox=SimpleNamespace(askyesno=lambda *a,**kw:False))
        w._on_close();self.assertTrue(w.timer_rows[0].running)

if __name__=='__main__':unittest.main()
