import ast
import threading
from pathlib import Path
from types import SimpleNamespace
import unittest

class CookingLifecycleTests(unittest.TestCase):
    def setUp(self):
        tree=ast.parse((Path(__file__).resolve().parents[1]/'main.py').read_text(encoding='utf-8'))
        nodes=[n for n in tree.body if isinstance(n,ast.ClassDef) and n.name in ('CookingModeWindow','TimerRow')]
        self.ns=dict(tk=SimpleNamespace(Toplevel=object,Frame=object,TclError=RuntimeError),
                     threading=threading,t=lambda k:k,sf=lambda x:x,PYTTSX3_AVAILABLE=True,
                     log_internal_error=lambda *a:None)
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'cooking','exec'),self.ns)
    def test_close_while_speech_initializes_no_late_tk_call(self):
        entered,release=threading.Event(),threading.Event()
        calls=[]
        engine=SimpleNamespace(setProperty=lambda *a:None,say=lambda *a:calls.append('say'),
                               runAndWait=lambda:calls.append('run'),stop=lambda:None)
        def init():
            entered.set();release.wait(2);return engine
        self.ns['pyttsx3']=SimpleNamespace(init=init)
        w=object.__new__(self.ns['CookingModeWindow'])
        w.recipe={'description':'Recette'};w._closing=False;w._speech_poll_id=None;w.tts_engine=None
        w.speech_volume=1.;w.speech_button=SimpleNamespace(config=lambda **kw:calls.append('button'))
        main_id=threading.get_ident()
        def after(*args):
            self.assertEqual(threading.get_ident(),main_id)
            return 'poll'
        w.after=after;cancelled=[];w.after_cancel=cancelled.append
        w.start_speech();self.assertTrue(entered.wait(1))
        w._close_speech();before=list(calls)
        release.set();w.tts_thread.join(2)
        self.assertFalse(w.tts_thread.is_alive())
        self.assertEqual(calls,before);self.assertNotIn('say',calls)
        self.assertEqual(cancelled,['poll'])
        w._poll_speech();self.assertEqual(calls,before)
    def test_timer_font_resize_does_not_change_countdown(self):
        row=object.__new__(self.ns['TimerRow'])
        class Font:
            def configure(self,**kw):self.size=kw['size']
        fonts=[Font(),Font(),Font()]
        row._font_sizes=list(zip(fonts,[18,10,-12]))
        row.remaining_seconds=245;row.running=True;row._deadline=500
        row.set_text_size(4)
        self.assertEqual([f.size for f in fonts],[22,14,-16])
        row.set_text_size(-2)
        self.assertEqual([f.size for f in fonts],[16,8,-10])
        self.assertEqual((row.remaining_seconds,row.running,row._deadline),(245,True,500))

if __name__=='__main__':unittest.main()
