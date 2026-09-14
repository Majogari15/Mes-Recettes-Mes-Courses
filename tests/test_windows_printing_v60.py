import ctypes
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import main
import windows_printing as wp


class FakeAPI:
    def __init__(self, first=1, last=2, flags=0, failure=None):
        self.settings = SimpleNamespace(Flags=flags, nFromPage=first, nToPage=last)
        self.events = []
        self.failure = failure
        self.images = []

    def event(self, name):
        self.events.append(name)
        if name == self.failure:
            raise OSError('simulated printer failure')

    def choose(self, owner, count):
        self.event('choose')
        if self.failure == 'cancel':
            raise wp.PrintCancelled()
        return self.settings

    def release(self, settings): self.event('release')
    def caps(self, settings): return (2400, 3200, 300, 300)
    def start(self, settings, title): self.event('start')
    def begin_page(self, settings): self.event('begin')
    def end_page(self, settings): self.event('end_page')
    def finish(self, settings): self.event('finish')
    def abort(self, settings): self.event('abort')
    def draw(self, settings, image, layout):
        self.event('draw')
        self.images.append((image.size, image.convert('RGB').getpixel((image.width//2, image.height//2)), layout))


class LayoutTests(unittest.TestCase):
    def test_layout_preserves_physical_aspect_with_unequal_dpi(self):
        x,y,w,h=wp.page_layout(612,792,2400,6400,300,600)
        self.assertAlmostEqual((w/300)/(h/600),612/792,places=3)
        self.assertGreaterEqual(x,0);self.assertGreaterEqual(y,0)
        self.assertLessEqual(x+w,2400);self.assertLessEqual(y+h,6400)

    def test_portrait_and_landscape_fit(self):
        for a,b in ((595,842),(842,595)):
            x,y,w,h=wp.page_layout(a,b,2200,3200,300,300)
            self.assertLessEqual(x+w,2200);self.assertLessEqual(y+h,3200)

    def test_bad_caps_rejected_and_render_memory_bounded(self):
        with self.assertRaises(ValueError): wp.page_layout(595,842,0,100,300,300)
        for w,h in ((595,842),(10000,30000)):
            scale=wp.render_scale(w,h)
            self.assertLessEqual(scale*scale*w*h,16_000_001)

    def test_win32_struct_layout(self):
        self.assertEqual(ctypes.sizeof(wp.BITMAPINFOHEADER),40)
        self.assertEqual(ctypes.sizeof(wp.PRINTDLGW),120 if ctypes.sizeof(wp.PTR)==8 else 66)

    def test_native_cancel_and_extended_error_are_distinct(self):
        for error in (0,0x1008):
            api=wp.WindowsPrintAPI.__new__(wp.WindowsPrintAPI)
            api.user=Mock();api.dialog=Mock();api.release=Mock()
            api.dialog.PrintDlgW.return_value=0
            api.dialog.CommDlgExtendedError.return_value=error
            with self.assertRaises(OSError if error else wp.PrintCancelled): api.choose(0,2)
            api.release.assert_called_once()

    def test_native_resources_released_once(self):
        api=wp.WindowsPrintAPI.__new__(wp.WindowsPrintAPI)
        api.gdi=Mock();api.kernel=Mock()
        pd=wp.PRINTDLGW();pd.hDC=101;pd.hDevMode=102;pd.hDevNames=103
        api.release(pd);api.release(pd)
        api.gdi.DeleteDC.assert_called_once_with(101)
        self.assertEqual(api.kernel.GlobalFree.call_count,2)


try:
    import pypdfium2
    from reportlab.pdfgen import canvas
    RENDER_AVAILABLE=True
except ImportError:
    RENDER_AVAILABLE=False


@unittest.skipUnless(RENDER_AVAILABLE,'PDF renderer unavailable')
class SpoolTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=str(Path(self.temp.name)/'Recette accentuée.pdf')
        c=canvas.Canvas(self.path,pagesize=(200,300))
        for color in ((1,0,0),(0,0,1)):
            c.setFillColorRGB(*color);c.rect(0,0,200,300,fill=1,stroke=0);c.showPage()
        c.save()

    def tearDown(self): self.temp.cleanup()
    def prepare(self,api):return wp.prepare_windows_print(self.path,api=api,engine=pypdfium2)

    def test_real_pdf_renders_both_pages_and_finishes_before_success(self):
        api=FakeAPI();job=self.prepare(api);progress=[]
        self.assertEqual(job.run(progress=lambda d,t:progress.append((d,t))),'printed')
        self.assertEqual(progress,[(1,2),(2,2)])
        self.assertEqual([i[1] for i in api.images],[(255,0,0),(0,0,255)])
        self.assertEqual(api.events[-2:],['finish','release'])
        self.assertNotIn('abort',api.events)
        job.close();self.assertEqual(api.events.count('release'),1)

    def test_page_range_prints_only_selected_page(self):
        api=FakeAPI(first=2,last=2,flags=wp.PD_PAGENUMS)
        self.prepare(api).run()
        self.assertEqual(len(api.images),1);self.assertEqual(api.images[0][1],(0,0,255))

    def test_invalid_range_releases_context(self):
        api=FakeAPI(first=2,last=5,flags=wp.PD_PAGENUMS)
        with self.assertRaises(ValueError):self.prepare(api)
        self.assertEqual(api.events,['choose','release'])

    def test_cancel_dialog_never_starts_job(self):
        api=FakeAPI(failure='cancel');self.assertIsNone(self.prepare(api))
        self.assertEqual(api.events,['choose'])

    def test_failure_aborts_and_releases(self):
        for failure in ('draw','end_page','finish'):
            api=FakeAPI(failure=failure)
            with self.assertRaises(OSError):self.prepare(api).run()
            self.assertEqual(api.events[-2:],['abort','release'])

    def test_start_failure_does_not_claim_success(self):
        api=FakeAPI(failure='start')
        with self.assertRaises(OSError):self.prepare(api).run()
        self.assertNotIn('draw',api.events);self.assertEqual(api.events[-1],'release')

    def test_cancel_between_pages_aborts(self):
        api=FakeAPI();stop=[False]
        with self.assertRaises(wp.PrintCancelled):
            self.prepare(api).run(lambda:stop[0],lambda d,t:stop.__setitem__(0,True))
        self.assertEqual(len(api.images),1);self.assertEqual(api.events[-2:],['abort','release'])

    def test_cancel_before_start_releases_without_spooling(self):
        api=FakeAPI()
        with self.assertRaises(wp.PrintCancelled):self.prepare(api).run(lambda:True)
        self.assertEqual(api.events,['choose','release'])


class IntegrationTests(unittest.TestCase):
    def test_cancel_does_not_open_reader_or_show_success(self):
        with patch.object(main.os,'name','nt'), patch.object(wp,'prepare_windows_print',return_value=None), \
             patch.object(main.tk,'Toplevel') as window, patch.object(main.messagebox,'showinfo') as info, \
             patch.object(main.os,'startfile',create=True) as open_pdf:
            main.print_document(Mock(),'example.pdf','Recipe')
            window.assert_not_called();info.assert_not_called();open_pdf.assert_not_called()

    def test_error_does_not_open_pdf_without_user_choice(self):
        with patch.object(main,'ask_yes_no',return_value=False), \
             patch.object(main.os,'startfile',create=True) as open_pdf:
            main._report_native_print_error(None,'example.pdf',wp.PrintDependencyError('missing'))
            open_pdf.assert_not_called()

    def test_all_four_print_buttons_use_same_controller(self):
        import inspect
        for cls,method in ((main.OneRecipeWindow,'print_recipe'),):
            self.assertIn('print_document(self, temp_path',inspect.getsource(getattr(cls,method)))
        # Le code source est enregistré en UTF-8.  Sur Windows, pathlib
        # utilise sinon l'encodage ANSI de la console (cp1252), qui échoue
        # dès qu'un caractère UTF-8 non représentable est rencontré.
        source=Path(main.__file__).read_text(encoding="utf-8")
        self.assertEqual(source.count('print_document(self, temp_path,'),4)
        self.assertNotIn('os.startfile(path, "print")',source)

    def test_translated_messages_and_packaging(self):
        for catalog in [main.FRENCH_STRINGS,*main.TRANSLATIONS.values()]:
            for key in ('print_dependency_missing','print_native_failed','print_preparing',
                        'print_cancelling','print_page_progress','print_failed_path','print_reader_opened'):
                self.assertIn(key,catalog)
        root=Path(main.__file__).parent
        self.assertIn('pypdfium2==5.3.0',(root/'requirements.txt').read_text(encoding="utf-8"))
        script=(root/'Construire_le_exe.bat').read_text(encoding="utf-8")
        self.assertIn('--collect-all=pypdfium2_raw',script)

if __name__=='__main__':unittest.main()
