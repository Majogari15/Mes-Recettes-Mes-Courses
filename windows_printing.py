"""Impression PDF via PrintDlgW / GDI, indépendante du lecteur PDF associé.

La boîte native se prépare sur le thread UI. Le travail GDI et le rendu PDF
s'exécutent ensuite sur un thread de travail, sans accès aux widgets Tk.
"""
import ctypes as ct
import math
import os
from pathlib import Path

U32, U16, I32, PTR = ct.c_uint32, ct.c_uint16, ct.c_int32, ct.c_void_p
PD_PAGENUMS = 0x2
PD_RETURNDC = 0x100
PD_NOSELECTION = 0x4
PD_USEDEVMODECOPIESANDCOLLATE = 0x40000
PD_HIDEPRINTTOFILE = 0x100000


class PrintCancelled(Exception):
    pass


class PrintDependencyError(Exception):
    pass


class PRINTDLGW(ct.Structure):
    # commdlg.h est compacté sur x86, aligné normalement sur x64.
    _pack_ = 1 if ct.sizeof(PTR) == 4 else 8
    _fields_ = [
        ('lStructSize', U32), ('hwndOwner', PTR), ('hDevMode', PTR),
        ('hDevNames', PTR), ('hDC', PTR), ('Flags', U32),
        ('nFromPage', U16), ('nToPage', U16), ('nMinPage', U16),
        ('nMaxPage', U16), ('nCopies', U16), ('hInstance', PTR),
        ('lCustData', ct.c_ssize_t), ('lpfnPrintHook', PTR),
        ('lpfnSetupHook', PTR), ('lpPrintTemplateName', ct.c_wchar_p),
        ('lpSetupTemplateName', ct.c_wchar_p), ('hPrintTemplate', PTR),
        ('hSetupTemplate', PTR),
    ]


class DOCINFOW(ct.Structure):
    _fields_ = [('cbSize', I32), ('lpszDocName', ct.c_wchar_p),
                ('lpszOutput', ct.c_wchar_p), ('lpszDatatype', ct.c_wchar_p),
                ('fwType', U32)]


class BITMAPINFOHEADER(ct.Structure):
    _fields_ = [('biSize', U32), ('biWidth', I32), ('biHeight', I32),
                ('biPlanes', U16), ('biBitCount', U16), ('biCompression', U32),
                ('biSizeImage', U32), ('biXPelsPerMeter', I32),
                ('biYPelsPerMeter', I32), ('biClrUsed', U32), ('biClrImportant', U32)]


def page_layout(page_width, page_height, printable_width, printable_height, dpi_x, dpi_y):
    """Centre la page sans la déformer, même avec deux résolutions différentes."""
    values = (page_width, page_height, printable_width, printable_height, dpi_x, dpi_y)
    if not all(math.isfinite(v) and v > 0 for v in values):
        raise ValueError('Invalid PDF page or printable area')
    fit = min(printable_width / (page_width * dpi_x / 72),
              printable_height / (page_height * dpi_y / 72), 1.0)
    width = max(1, round(page_width * dpi_x / 72 * fit))
    height = max(1, round(page_height * dpi_y / 72 * fit))
    return ((printable_width-width)//2, (printable_height-height)//2, width, height)


def render_scale(width, height):
    # 300 dpi au plus ; limite mémoire pour les pages inhabituellement grandes.
    if width <= 0 or height <= 0 or not math.isfinite(width*height):
        raise ValueError('Invalid PDF page size')
    return min(300 / 72, math.sqrt(16_000_000 / (width * height)))


def load_pdf_engine():
    """Charge le moteur PDF et expose la vraie cause d'un échec de chargement.

    Avec ``main.pyw``, plusieurs installations Python peuvent coexister : le
    détail conservé dans l'exception permet au dialogue d'indiquer précisément
    quel module ou quelle DLL manque, au lieu d'afficher un message générique.
    """
    try:
        import pypdfium2
    except Exception as exc:
        raise PrintDependencyError(
            f"pypdfium2: {type(exc).__name__}: {exc}"
        ) from exc
    try:
        from PIL import Image  # Le rendu final utilise PIL.
    except Exception as exc:
        raise PrintDependencyError(
            f"Pillow: {type(exc).__name__}: {exc}"
        ) from exc
    return pypdfium2


class WindowsPrintAPI:
    def __init__(self):
        if os.name != 'nt':
            raise OSError('Windows printing is available only on Windows')
        self.dialog = ct.WinDLL('comdlg32', use_last_error=True)
        self.gdi = ct.WinDLL('gdi32', use_last_error=True)
        self.kernel = ct.WinDLL('kernel32', use_last_error=True)
        self.user = ct.WinDLL('user32', use_last_error=True)
        def signature(dll, name, result, *args):
            function = getattr(dll, name)
            function.restype, function.argtypes = result, list(args)
        signature(self.dialog, 'PrintDlgW', I32, ct.POINTER(PRINTDLGW))
        signature(self.dialog, 'CommDlgExtendedError', U32)
        signature(self.user, 'GetAncestor', PTR, PTR, U32)
        signature(self.kernel, 'GlobalFree', PTR, PTR)
        signature(self.gdi, 'DeleteDC', I32, PTR)
        signature(self.gdi, 'GetDeviceCaps', I32, PTR, I32)
        signature(self.gdi, 'StartDocW', I32, PTR, ct.POINTER(DOCINFOW))
        for name in ('StartPage', 'EndPage', 'EndDoc', 'AbortDoc'):
            signature(self.gdi, name, I32, PTR)
        signature(self.gdi, 'SetStretchBltMode', I32, PTR, I32)
        signature(self.gdi, 'SetBrushOrgEx', I32, PTR, I32, I32, PTR)
        signature(self.gdi, 'StretchDIBits', I32, PTR, *([I32]*8),
                  PTR, ct.POINTER(BITMAPINFOHEADER), U32, U32)

    def choose(self, owner, page_count):
        pd = PRINTDLGW()
        pd.lStructSize = ct.sizeof(pd)
        pd.hwndOwner = self.user.GetAncestor(owner, 2) or owner if owner else None
        pd.Flags = PD_RETURNDC | PD_NOSELECTION | PD_USEDEVMODECOPIESANDCOLLATE | PD_HIDEPRINTTOFILE
        pd.nMinPage = pd.nFromPage = 1
        pd.nMaxPage = pd.nToPage = page_count
        pd.nCopies = 1
        try:
            if not self.dialog.PrintDlgW(ct.byref(pd)):
                error = self.dialog.CommDlgExtendedError()
                if error:
                    raise OSError(f'PrintDlgW: 0x{error:04X}')
                raise PrintCancelled()
            if not pd.hDC:
                raise OSError('PrintDlgW: no printer context')
            return pd
        except BaseException:
            self.release(pd)
            raise

    def release(self, pd):
        if pd.hDC:
            self.gdi.DeleteDC(pd.hDC)
            pd.hDC = None
        for field in ('hDevMode', 'hDevNames'):
            handle = getattr(pd, field)
            if handle:
                self.kernel.GlobalFree(handle)
                setattr(pd, field, None)

    def caps(self, pd):
        # HORZRES/VERTRES : zone réellement imprimable ; LOGPIXELSX/Y : dpi.
        return tuple(self.gdi.GetDeviceCaps(pd.hDC, cap) for cap in (8, 10, 88, 90))

    def check(self, result, operation):
        if result <= 0:
            raise OSError(f'{operation}: Windows error {ct.get_last_error()}')

    def start(self, pd, title):
        info = DOCINFOW(ct.sizeof(DOCINFOW), title, None, None, 0)
        self.check(self.gdi.StartDocW(pd.hDC, ct.byref(info)), 'StartDocW')

    def begin_page(self, pd):
        self.check(self.gdi.StartPage(pd.hDC), 'StartPage')

    def draw(self, pd, image, layout):
        rgb = image.convert('RGB')
        try:
            data = rgb.tobytes('raw', 'BGRX')
            header = BITMAPINFOHEADER()
            header.biSize = ct.sizeof(header)
            header.biWidth, header.biHeight = rgb.width, -rgb.height
            header.biPlanes, header.biBitCount = 1, 32
            header.biSizeImage = len(data)
            self.gdi.SetStretchBltMode(pd.hDC, 4)  # HALFTONE
            self.gdi.SetBrushOrgEx(pd.hDC, 0, 0, None)
            buffer = ct.create_string_buffer(data)
            result = self.gdi.StretchDIBits(pd.hDC, *layout, 0, 0, rgb.width, rgb.height,
                                            buffer, ct.byref(header), 0, 0x00CC0020)
            if result in (0, -1):
                raise OSError(f'StretchDIBits: Windows error {ct.get_last_error()}')
        finally:
            rgb.close()

    def end_page(self, pd):
        self.check(self.gdi.EndPage(pd.hDC), 'EndPage')

    def finish(self, pd):
        self.check(self.gdi.EndDoc(pd.hDC), 'EndDoc')

    def abort(self, pd):
        self.gdi.AbortDoc(pd.hDC)


class WindowsPrintJob:
    def __init__(self, path, api, settings, engine, pages):
        self.path, self.api, self.settings = path, api, settings
        self.engine, self.pages = engine, pages
        self.closed = False

    def close(self):
        if not self.closed:
            self.closed = True
            self.api.release(self.settings)

    def run(self, cancelled=lambda: False, progress=lambda done, total: None):
        started = False
        try:
            if cancelled():
                raise PrintCancelled()
            with self.engine.PdfDocument(self.path) as document:
                caps = self.api.caps(self.settings)
                # Valider le périphérique avant de commencer un travail.
                page_layout(1, 1, *caps)
                self.api.start(self.settings, Path(self.path).stem)
                started = True
                for done, index in enumerate(self.pages, 1):
                    if cancelled():
                        raise PrintCancelled()
                    page = document[index]
                    try:
                        width, height = page.get_size()
                        bitmap = page.render(scale=render_scale(width, height))
                        try:
                            image = bitmap.to_pil()
                            try:
                                if cancelled():
                                    raise PrintCancelled()
                                self.api.begin_page(self.settings)
                                self.api.draw(self.settings, image, page_layout(width, height, *caps))
                                self.api.end_page(self.settings)
                            finally:
                                image.close()
                        finally:
                            bitmap.close()
                    finally:
                        page.close()
                    progress(done, len(self.pages))
                if cancelled():
                    raise PrintCancelled()
                self.api.finish(self.settings)
                started = False
                return 'printed'
        finally:
            try:
                if started:
                    self.api.abort(self.settings)
            finally:
                self.close()


def prepare_windows_print(path, owner=0, *, api=None, engine=None):
    """Affiche le dialogue ; retourne un travail prêt ou None si Annuler."""
    engine = engine or load_pdf_engine()
    with engine.PdfDocument(str(path)) as document:
        count = len(document)
    if not 1 <= count <= 65535:
        raise ValueError('Unsupported PDF page count')
    api = api or WindowsPrintAPI()
    try:
        settings = api.choose(owner, count)
    except PrintCancelled:
        return None
    try:
        pages = range(count)
        if settings.Flags & PD_PAGENUMS:
            if not 1 <= settings.nFromPage <= settings.nToPage <= count:
                raise ValueError('Invalid print page range')
            pages = range(settings.nFromPage-1, settings.nToPage)
        return WindowsPrintJob(str(path), api, settings, engine, pages)
    except BaseException:
        api.release(settings)
        raise

