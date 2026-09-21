import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog, font as tkfont
import copy
import csv
import difflib
import filecmp
import gzip
import html
import hashlib
import itertools
import json
import math
import os
import platform
import re
import shutil
import subprocess
import sys
import io
import random
import queue
import threading
import time
import webbrowser
import tempfile
import unicodedata
import urllib.error
import zlib
import urllib.parse
from html.parser import HTMLParser
import urllib.request
import uuid
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

# Numéro de version de l'application — introduit ici pour la première
# fois : aucun système de version n'existait jusqu'ici pour cette
# application (seulement un suivi par date de session au fil du
# développement). Ce numéro 1 marque donc le début d'un suivi formel, à
# incrémenter à chaque changement livré, plutôt que le tout début du
# développement de l'application elle-même (déjà mature à ce stade :
# gestion complète des recettes, planning, garde-manger, substitutions...).
# Convention alignée sur celle déjà en place côté application mobile
# (APP_VERSION dans app.js) : un simple entier incrémenté à chaque
# livraison.
PRODUCT_VERSION = "1.6.31"
APP_BUILD = 78
APP_VERSION = APP_BUILD
DATA_SCHEMA_VERSION = 2


def log_internal_error(context, exc):
    """Journalise silencieusement une erreur interne sans bloquer l'interface."""
    try:
        path = os.path.join(DATA_DIR, "error.log")
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat(timespec='seconds')}] {context}: {type(exc).__name__}: {exc}\n")
    except Exception:
        pass


def install_tk_exception_logger(root):
    """Journalise les exceptions de callbacks Tkinter dans error.log."""
    def handler(exc_type, exc_value, exc_tb):
        log_internal_error("tk_callback", exc_value)
        try:
            messagebox.showerror(t("common_error"), str(exc_value), parent=root)
        except Exception as exc:
            log_internal_error("suppressed_exception", exc)
    root.report_callback_exception = handler


def install_select_all_bindings(root):
    """Fait fonctionner Ctrl+A comme « tout sélectionner » dans les champs
    de saisie, partout dans l'application.

    Par défaut, Tk lie Ctrl+A au déplacement du curseur en début de ligne
    (raccourci historique façon Emacs) aussi bien dans les ``Entry``/
    ``ttk.Entry`` que dans les ``Text`` : un utilisateur Windows habitué à
    Ctrl+A pour tout sélectionner ne peut donc pas remplacer facilement le
    contenu d'un champ. ``bind_class`` s'applique une fois pour toutes les
    instances (présentes et futures) de chaque classe de widget.
    """
    def _select_all_entry(event):
        widget = event.widget
        try:
            widget.select_range(0, tk.END)
            widget.icursor(tk.END)
        except tk.TclError:
            pass
        return "break"

    def _select_all_text(event):
        widget = event.widget
        try:
            widget.tag_add("sel", "1.0", "end-1c")
            widget.mark_set("insert", "end-1c")
            widget.see("insert")
        except tk.TclError:
            pass
        return "break"

    for bindtag in ("Entry", "TEntry", "TCombobox"):
        root.bind_class(bindtag, "<Control-a>", _select_all_entry)
    root.bind_class("Text", "<Control-a>", _select_all_text)


def parse_positive_number(value, *, allow_zero=False):
    """Parse un nombre utilisateur et refuse NaN/Inf ainsi que les valeurs invalides."""
    number = float(str(value).strip().replace(",", "."))
    if not math.isfinite(number):
        raise ValueError("non-finite value")
    if allow_zero:
        if number < 0:
            raise ValueError("negative value")
    elif number <= 0:
        raise ValueError("non-positive value")
    return number


def parse_optional_positive_number(value, *, allow_zero=True):
    """Parse une quantité éventuellement non renseignée.

    Le format partagé mobile encode une quantité laissée vide par ``null``.
    Cette valeur doit rester distincte de zéro : elle signifie que la
    quantité est inconnue ou « au goût », pas que l'ingrédient est absent.
    """
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return parse_positive_number(value, allow_zero=allow_zero)


def parse_finite_number(value, *, allow_negative=True):
    """Convertit une valeur en float fini. Utilisé pour les données importées/calculées."""
    number = float(str(value).strip().replace(",", "."))
    if not math.isfinite(number):
        raise ValueError("non-finite value")
    if not allow_negative and number < 0:
        raise ValueError("negative value")
    return number


def ingredient_quantity_for_persons(ingredient, persons):
    """Recalcule une quantité interne (stockée par personne) pour ``persons``."""
    raw_quantity = ingredient.get("quantity", 0)
    if raw_quantity is None or (isinstance(raw_quantity, str) and not raw_quantity.strip()):
        return None
    quantity = parse_finite_number(raw_quantity, allow_negative=False)
    person_count = parse_positive_number(persons)
    return round(quantity * person_count, 2)
# --- Robustness & performance helpers v35 ---

class CorruptDataError(RuntimeError):
    """Empêche l'écrasement d'un fichier utilisateur détecté comme corrompu."""


class OperationCancelled(RuntimeError):
    """Interruption demandée par l'utilisateur pendant une opération longue."""


def _check_cancelled(cancel_event):
    if cancel_event is not None and cancel_event.is_set():
        raise OperationCancelled("operation_cancelled")


_CORRUPTED_DATA_FILES = {}
_ALLOW_CORRUPT_OVERWRITE = set()


def _corruption_key(path):
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def _register_corrupt_json(path, exc):
    """Conserve une copie de secours et mémorise le blocage d'écriture."""
    key = _corruption_key(path)
    if key in _CORRUPTED_DATA_FILES:
        return _CORRUPTED_DATA_FILES[key]
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    source = Path(path)
    quarantine = source.with_name(f"{source.stem}.corrompu_{stamp}{source.suffix}")
    counter = 2
    while quarantine.exists():
        quarantine = source.with_name(
            f"{source.stem}.corrompu_{stamp}_{counter}{source.suffix}"
        )
        counter += 1
    try:
        shutil.copy2(source, quarantine)
    except OSError as copy_exc:
        log_internal_error("quarantine_corrupt_json", copy_exc)
        quarantine = None
    info = {
        "path": str(source),
        "backup": str(quarantine) if quarantine else "",
        "error": f"{type(exc).__name__}: {exc}",
    }
    _CORRUPTED_DATA_FILES[key] = info
    log_internal_error(f"corrupt_json:{source.name}", exc)
    return info


def get_corrupted_data_files():
    return [dict(info) for info in _CORRUPTED_DATA_FILES.values()]


def _clear_corruption_guards(paths=None):
    if paths is None:
        _CORRUPTED_DATA_FILES.clear()
        return
    for path in paths:
        _CORRUPTED_DATA_FILES.pop(_corruption_key(path), None)


def _read_user_json(path, expected_type, default, *, label=None):
    """Lit un JSON personnel sans confondre absence, type invalide et corruption."""
    if not os.path.exists(path):
        return copy.deepcopy(default)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, expected_type):
            raise ValueError(
                f"{os.path.basename(path)} must contain {expected_type.__name__}"
            )
        return data
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        _register_corrupt_json(path, exc)
        return copy.deepcopy(default)

def _atomic_write_json(path, data):
    path = Path(path)
    key = _corruption_key(path)
    if key in _CORRUPTED_DATA_FILES and key not in _ALLOW_CORRUPT_OVERWRITE:
        raise CorruptDataError(f"blocked_corrupt_file:{path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _run_json_transaction(paths, action):
    """Exécute plusieurs écritures JSON avec restauration exacte en cas d'échec."""
    paths = [os.path.abspath(os.fspath(p)) for p in dict.fromkeys(paths)]
    snapshot = tempfile.mkdtemp(prefix="mesrecettes_transaction_")
    existed = set()
    try:
        for index, path in enumerate(paths):
            if os.path.isfile(path):
                existed.add(path)
                shutil.copy2(path, os.path.join(snapshot, str(index)))
        return action()
    except Exception:
        for index, path in enumerate(paths):
            try:
                if path in existed:
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    rollback_tmp = path + ".rollback.tmp"
                    shutil.copy2(os.path.join(snapshot, str(index)), rollback_tmp)
                    os.replace(rollback_tmp, path)
                elif os.path.isfile(path):
                    os.remove(path)
            except OSError as rollback_exc:
                log_internal_error("json_transaction_rollback", rollback_exc)
        raise
    finally:
        shutil.rmtree(snapshot, ignore_errors=True)


def _count_orphan_images(recipes, images_dir):
    refs = set()
    for recipe in recipes or []:
        for name in get_all_recipe_image_refs(recipe):
            if name:
                refs.add(name)
    missing = []
    orphan = []
    try:
        for name in refs:
            if not (Path(images_dir) / name).exists():
                missing.append(name)
        for p in Path(images_dir).iterdir():
            if p.is_file() and p.name not in refs:
                orphan.append(p.name)
    except Exception as exc:
        log_internal_error("suppressed_exception", exc)
    return missing, orphan


# --- UI polish v9 ---


def _ui_apply_window_defaults(win, geometry=None, resizable=True):
    try:
        if geometry:
            win.geometry(geometry)
        safe_minsize(win, 420, 260)
        win.resizable(resizable, resizable)
    except Exception as exc:
        log_internal_error("suppressed_exception", exc)


def _ui_bind_escape(win):
    try:
        win.bind("<Escape>", lambda e: win.destroy())
    except Exception as exc:
        log_internal_error("suppressed_exception", exc)

def _ui_show_toast(parent, message, duration=2200):
    """Non-blocking success/info notification."""
    try:
        tw = tk.Toplevel(parent)
        tw.wm_overrideredirect(True)
        tw.attributes("-topmost", True)
        tw.configure(bg="#2f2f2f")
        lbl = tk.Label(tw, text=message, bg="#2f2f2f", fg="white",
                       padx=14, pady=9, font=("Segoe UI", 10))
        lbl.pack()
        parent.update_idletasks()
        tw.update_idletasks()
        x = parent.winfo_rootx() + max(10, parent.winfo_width() - tw.winfo_width() - 24)
        y = parent.winfo_rooty() + max(10, parent.winfo_height() - tw.winfo_height() - 48)
        tw.geometry(f"+{x}+{y}")
        tw.after(duration, tw.destroy)
    except Exception as exc:
        log_internal_error("suppressed_exception", exc)


# Pillow est nécessaire pour afficher les photos des recettes.
try:
    from PIL import Image, ImageTk, ImageGrab, ImageOps
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# reportlab est nécessaire pour l'export PDF de la liste de courses.
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas as pdf_canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import reportlab
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

# openpyxl est nécessaire pour l'export Excel de la liste de courses.
try:
    from openpyxl import Workbook
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False

# qrcode est nécessaire pour exporter une recette sous forme de QR code.
try:
    import qrcode
    QRCODE_AVAILABLE = True
except ImportError:
    QRCODE_AVAILABLE = False

# pyzbar est utilisé uniquement pour lire des QR codes enregistrés sous forme
# d'image (notamment ceux générés par l'application mobile). Il s'appuie sur
# Pillow déjà utilisé par l'application et reste bien plus léger qu'OpenCV.
try:
    from pyzbar.pyzbar import decode as decode_barcodes
    QRCODE_READER_AVAILABLE = True
except (ImportError, OSError):
    QRCODE_READER_AVAILABLE = False

# pytesseract est nécessaire pour importer une recette depuis une photo (OCR).
# Il ne suffit pas de l'installer via pip : il nécessite aussi le programme
# Tesseract OCR installé séparément sur le système (voir le LISEZ-MOI).
try:
    import pytesseract
    PYTESSERACT_AVAILABLE = True
except ImportError:
    PYTESSERACT_AVAILABLE = False

# pyttsx3 est nécessaire pour la lecture à voix haute en mode cuisine.
# Fonctionne hors ligne (s'appuie sur la synthèse vocale déjà installée sur
# le système : SAPI5 sous Windows).
try:
    import pyttsx3
    PYTTSX3_AVAILABLE = True
except ImportError:
    PYTTSX3_AVAILABLE = False

# Glisser-déposer natif de fichiers.
# tkinterdnd2 utilise l'extension TkDnD2/OLE2 et évite le remplacement manuel
# du WindowProc Windows effectué par l'ancien module windnd, qui provoquait
# des fermetures natives de Tcl/Tk sur certains PC.
try:
    from tkinterdnd2 import DND_FILES, COPY, TkinterDnD
    TKDND_AVAILABLE = True
except ImportError:
    DND_FILES = None
    COPY = "copy"
    TkinterDnD = None
    TKDND_AVAILABLE = False

# Classe de base de l'application : si tkinterdnd2 est installé, son Tk charge
# automatiquement l'extension tkdnd pour tous les widgets descendants.
APP_TK_BASE = TkinterDnD.Tk if TKDND_AVAILABLE else tk.Tk


if getattr(sys, "frozen", False):
    # Application compilée avec PyInstaller (.exe) : __file__ pointe vers un
    # dossier temporaire d'extraction interne à Windows (pas vers le dossier
    # où se trouve le .exe), donc on utilise plutôt l'emplacement réel de
    # l'exécutable pour que les fichiers de données (recettes, ingrédients,
    # photos...) soient bien lus/écrits à côté du .exe, là où l'utilisateur
    # les voit et les place.
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _compute_data_dir(base_dir):
    """Détermine le dossier où enregistrer les données personnelles de
    l'utilisateur (recettes, garde-manger, réglages, planning...).

    Dans la grande majorité des cas, c'est le même dossier que celui où se
    trouve l'application (base_dir), pour que tout reste ensemble et reste
    facilement déplaçable (clé USB, autre PC...) — c'est le comportement
    historique de l'application.

    Mais certains modes d'installation empaquetée (notamment MSIX, utilisé
    pour la distribution via le Microsoft Store) installent l'application
    dans un dossier en lecture seule pour l'application elle-même. Dans ce
    cas précis, on détecte l'impossibilité d'écrire à côté de l'exécutable
    et on retombe automatiquement sur un dossier accessible en écriture du
    profil de l'utilisateur, sans que l'utilisateur n'ait à s'en soucier ni
    à configurer quoi que ce soit."""
    test_path = os.path.join(base_dir, ".ecriture_test_tmp")
    try:
        with open(test_path, "w", encoding="utf-8") as f:
            f.write("test")
        os.remove(test_path)
        return base_dir
    except OSError:
        fallback = os.path.join(
            os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
            "MesRecettesMesCourses",
        )
        os.makedirs(fallback, exist_ok=True)
        return fallback


# Dossier des données personnelles (recettes, garde-manger, réglages...),
# distinct de BASE_DIR : voir _compute_data_dir() ci-dessus. Les fichiers
# fournis avec l'application elle-même (bases d'ingrédients, traductions,
# drapeaux...) restent, eux, toujours lus depuis BASE_DIR — ils ne sont
# jamais modifiés par l'application, donc aucun souci même si ce dossier
# est en lecture seule.
DATA_DIR = _compute_data_dir(BASE_DIR)

DATA_FILE = os.path.join(DATA_DIR, "recipes.json")
INGREDIENTS_FILE = os.path.join(DATA_DIR, "ingredients.json")
DEFAULT_INGREDIENTS_FILE = os.path.join(BASE_DIR, "ingredients_par_defaut.json")
NUTRITION_DATA_FILE = os.path.join(BASE_DIR, "valeurs_nutritionnelles.json")
INGREDIENT_ALLERGENS_FILE = os.path.join(BASE_DIR, "ingredient_allergenes.json")
INGREDIENT_SUBSTITUTIONS_FILE = os.path.join(BASE_DIR, "ingredient_substitutions.json")
# Fichiers de traduction, par langue autre que le français (langue de
# référence des données, jamais dans ce dictionnaire). Pour ajouter une
# langue supplémentaire à l'avenir, il suffit d'ajouter une entrée ici et
# de fournir les deux fichiers JSON correspondants.
INGREDIENT_SUBSTITUTIONS_TRANSLATION_FILES = {
    "en": os.path.join(BASE_DIR, "ingredient_substitutions_en.json"),
    "es": os.path.join(BASE_DIR, "ingredient_substitutions_es.json"),
    "de": os.path.join(BASE_DIR, "ingredient_substitutions_de.json"),
}
INGREDIENT_TRANSLATIONS_FILES = {
    "en": os.path.join(BASE_DIR, "ingredient_translations_en.json"),
    "es": os.path.join(BASE_DIR, "ingredient_translations_es.json"),
    "de": os.path.join(BASE_DIR, "ingredient_translations_de.json"),
}
FLAG_FILES = {
    "fr": os.path.join(BASE_DIR, "flag_fr.png"),
    "en": os.path.join(BASE_DIR, "flag_uk.png"),
    "es": os.path.join(BASE_DIR, "flag_es.png"),
    "de": os.path.join(BASE_DIR, "flag_de.png"),
}
# Codes de langue attendus par Tesseract OCR (différents des codes ISO à 2
# lettres utilisés partout ailleurs dans l'application) pour l'import de
# recette depuis une photo : suit la langue actuellement sélectionnée dans
# l'interface, sur l'hypothèse que le texte manuscrit ou imprimé photographié
# est dans cette même langue. Nécessite que le paquet linguistique
# correspondant soit installé pour Tesseract (voir LISEZ-MOI).
TESSERACT_LANG_CODES = {
    "fr": "fra",
    "en": "eng",
    "es": "spa",
    "de": "deu",
}


def detect_tesseract(required_lang=None):
    """Détecte Tesseract, sa version et ses langues disponibles.

    Sous Windows, essaie aussi les emplacements d'installation les plus
    courants lorsque tesseract.exe n'est pas dans le PATH.
    """
    status = {
        "pytesseract": PYTESSERACT_AVAILABLE,
        "executable": None,
        "version": None,
        "languages": [],
        "required_lang": required_lang,
        "ready": False,
        "reason": "pytesseract_missing",
    }
    if not PYTESSERACT_AVAILABLE:
        return status

    candidates = []
    try:
        configured = getattr(pytesseract.pytesseract, "tesseract_cmd", None)
        if configured and configured != "tesseract":
            candidates.append(configured)
    except Exception:
        # Simple sonde optionnelle : si la structure interne de pytesseract
        # diffère (autre version, module de test), on continue avec les
        # autres méthodes de détection ci-dessous plutôt que d'échouer.
        pass

    # Copie portable livrée à côté de l'application (dossier "tesseract-ocr",
    # ajoutée par Construire_le_exe.bat / installateur.iss quand elle est
    # fournie) : essayée en priorité sur une installation système, pour que
    # l'import de recette depuis une photo fonctionne sans rien installer
    # séparément. Absente, elle est simplement ignorée et le reste de la
    # détection (installation système, PATH) continue de fonctionner comme
    # avant.
    candidates.append(os.path.join(BASE_DIR, "tesseract-ocr", "tesseract.exe"))

    if os.name == "nt":
        candidates.extend([
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ])
        local = os.environ.get("LOCALAPPDATA")
        if local:
            candidates.append(
                os.path.join(local, "Programs", "Tesseract-OCR", "tesseract.exe")
            )

    # Si le binaire est déjà dans le PATH, pytesseract le trouvera sans chemin.
    candidates.append("tesseract")

    seen = set()
    for candidate in candidates:
        key = os.path.normcase(str(candidate))
        if key in seen:
            continue
        seen.add(key)
        try:
            if candidate != "tesseract" and not os.path.isfile(candidate):
                continue
            pytesseract.pytesseract.tesseract_cmd = candidate
            version = str(pytesseract.get_tesseract_version()).splitlines()[0]
            languages = sorted(set(pytesseract.get_languages(config="")))
            status.update({
                "executable": candidate,
                "version": version,
                "languages": languages,
                "reason": None,
            })
            if required_lang and required_lang not in languages:
                status["reason"] = "language_missing"
                status["ready"] = False
            else:
                status["ready"] = True
            return status
        except Exception as exc:
            status["reason"] = str(exc)

    status["reason"] = "tesseract_not_found"
    return status


def current_tesseract_status():
    return detect_tesseract(TESSERACT_LANG_CODES.get(CURRENT_LANGUAGE, "fra"))

INGREDIENT_OVERRIDES_FILE = os.path.join(DATA_DIR, "ingredient_custom_data.json")
INGREDIENT_PRICES_FILE = os.path.join(DATA_DIR, "ingredient_prices.json")
IMAGES_DIR = os.path.join(DATA_DIR, "images")
WEEKLY_PLAN_FILE = os.path.join(DATA_DIR, "weekly_plan.json")
WEEKLY_PLAN_HISTORY_FILE = os.path.join(DATA_DIR, "weekly_plan_history.json")
WEEKLY_PLAN_TEMPLATES_FILE = os.path.join(DATA_DIR, "weekly_plan_templates.json")
MENUS_FILE = os.path.join(DATA_DIR, "menus.json")
TRASH_FILE = os.path.join(DATA_DIR, "trash.json")
BACKUPS_DIR = os.path.join(DATA_DIR, "backups")
DRAFTS_DIR = os.path.join(DATA_DIR, "drafts")
IMPORT_TEMP_DIR = os.path.join(DATA_DIR, "import_temp")
os.makedirs(IMPORT_TEMP_DIR, exist_ok=True)

RECENT_VIEWS_FILE = os.path.join(DATA_DIR, "recent_views.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")

os.makedirs(IMAGES_DIR, exist_ok=True)
os.makedirs(DRAFTS_DIR, exist_ok=True)

# Fichiers de données personnelles inclus dans une sauvegarde complète (tout
# ce qui n'est pas fourni avec l'application elle-même : les bases
# d'ingrédients/allergènes/nutrition/substitutions ne changent pas d'un
# utilisateur à l'autre et ne sont donc pas incluses).
# Limites de taille pour une restauration de sauvegarde — alignées avec
# l'application mobile (voir MAX_BACKUP_FILE_SIZE / BACKUP_WARNING_SIZE côté
# app.js), qui avait ces limites alors qu'aucune n'existait ici auparavant.
BACKUP_WARNING_SIZE = 50 * 1024 * 1024  # format partagé mobile
MAX_BACKUP_FILE_SIZE = 100 * 1024 * 1024  # format partagé mobile
MAX_BACKUP_UNCOMPRESSED_SIZE = 500 * 1024 * 1024
MAX_BACKUP_ENTRY_SIZE = 100 * 1024 * 1024
FULL_BACKUP_WARNING_SIZE = 1024 * 1024 * 1024  # 1 Go : avertissement seulement
FULL_BACKUP_MAX_FILE_SIZE = 4 * 1024 * 1024 * 1024  # 4 Go
FULL_BACKUP_MAX_UNCOMPRESSED_SIZE = 8 * 1024 * 1024 * 1024
FULL_BACKUP_MAX_ENTRY_SIZE = 256 * 1024 * 1024  # aucune photo/JSON ne doit approcher 4 Gio

def _validate_backup_zip(zf, *, max_entry=MAX_BACKUP_ENTRY_SIZE,
                         max_total=MAX_BACKUP_UNCOMPRESSED_SIZE,
                         verify_crc=True):
    total = 0
    for info in zf.infolist():
        name = info.filename.replace("\\", "/")
        if name.startswith("/") or "../" in f"/{name}" or name.startswith("../"):
            raise ValueError("unsafe_archive_path")
        if info.file_size > max_entry:
            raise ValueError("archive_entry_too_large")
        total += info.file_size
        if total > max_total:
            raise ValueError("archive_uncompressed_too_large")
    if verify_crc:
        bad = zf.testzip()
        if bad is not None:
            raise ValueError("corrupt_archive")


USER_DATA_FILES = [
    "recipes.json", "ingredients.json", "ingredient_custom_data.json",
    "ingredient_prices.json", "ingredient_dismissed_pairs.json",
    "weekly_plan.json", "weekly_plan_history.json", "weekly_plan_templates.json",
    "menus.json", "saved_shopping_lists.json", "pantry.json",
    "trash.json", "recent_views.json", "settings.json",
]


def inspect_backup_archive(zip_path):
    """Retourne un résumé non destructif d'une sauvegarde ZIP avant import.
    Aucun fichier n'est extrait pendant cette inspection."""
    summary = {
        "recipes": 0, "images": 0, "ingredients": 0, "pantry": 0,
        "prices": 0, "menus": 0, "shopping_lists": 0,
        "size_mb": round(os.path.getsize(zip_path) / (1024 * 1024), 1),
    }
    with zipfile.ZipFile(zip_path, "r") as zf:
        _validate_backup_zip(
            zf, max_entry=FULL_BACKUP_MAX_ENTRY_SIZE,
            max_total=FULL_BACKUP_MAX_UNCOMPRESSED_SIZE, verify_crc=False
        )
        names = set(zf.namelist())
        def read_json(name, default):
            if name not in names:
                return default
            try:
                return json.loads(zf.read(name).decode("utf-8"))
            except Exception as exc:
                raise ValueError(f"invalid_json:{name}") from exc
        recipes = read_json("recipes.json", [])
        ingredients = read_json("ingredients.json", [])
        pantry = read_json("pantry.json", {})
        prices = read_json("ingredient_prices.json", {})
        menus = read_json("menus.json", [])
        shopping = read_json("saved_shopping_lists.json", [])
        preview_payloads = {}
        for _name, _value in (("recipes.json", recipes), ("ingredients.json", ingredients),
                              ("pantry.json", pantry), ("ingredient_prices.json", prices),
                              ("menus.json", menus), ("saved_shopping_lists.json", shopping)):
            if _name in names:
                preview_payloads[_name] = _value
        validate_backup_payloads(preview_payloads)
        summary["recipes"] = len(recipes) if isinstance(recipes, list) else 0
        summary["ingredients"] = len(ingredients) if isinstance(ingredients, list) else 0
        summary["pantry"] = len(pantry) if isinstance(pantry, (dict, list)) else 0
        summary["prices"] = len(prices) if isinstance(prices, dict) else 0
        summary["menus"] = len(menus) if isinstance(menus, list) else 0
        summary["shopping_lists"] = len(shopping) if isinstance(shopping, list) else 0
        summary["images"] = sum(1 for n in names if n.startswith("images/") and not n.endswith("/"))
    return summary


def format_backup_preview(summary):
    return t(
        "importexport_preview_message",
        size=summary.get("size_mb", 0), recipes=summary.get("recipes", 0),
        photos=summary.get("images", 0), ingredients=summary.get("ingredients", 0),
        pantry=summary.get("pantry", 0), prices=summary.get("prices", 0),
        menus=summary.get("menus", 0), lists=summary.get("shopping_lists", 0),
    )


def ask_yes_no(title, message, parent=None, **kwargs):
    """Remplace ``messagebox.askyesno`` par une boîte de dialogue dont les
    boutons sont toujours traduits (« Oui » / « Non », etc.).

    La boîte système de ``messagebox`` affiche des boutons dans la langue
    d'affichage de Windows (ou en anglais par défaut sous Linux/macOS),
    indépendamment de la langue choisie dans l'application : un utilisateur
    ayant sélectionné le français pouvait ainsi se retrouver avec des
    boutons "Yes"/"No" au milieu d'un message français. Cette fonction a la
    même signature et le même comportement bloquant (retourne True/False)
    que ``messagebox.askyesno``, mais construit ses propres boutons via
    ``t("common_yes")``/``t("common_no")``.
    """
    root = parent if parent is not None else tk._default_root
    dialog = tk.Toplevel(root)
    dialog.title(title)
    dialog.resizable(False, False)
    if root is not None:
        dialog.transient(root)
    result = {"value": False}

    def _answer(value):
        result["value"] = value
        dialog.destroy()

    body = ttk.Frame(dialog, padding=20)
    body.pack(fill="both", expand=True)
    ttk.Label(body, text=message, wraplength=420, justify="left").pack(anchor="w")

    btn_frame = ttk.Frame(dialog, padding=(20, 0, 20, 16))
    btn_frame.pack(fill="x")
    no_btn = ttk.Button(btn_frame, text=t("common_no"), command=lambda: _answer(False))
    no_btn.pack(side="right", padx=(8, 0))
    yes_btn = ttk.Button(btn_frame, text=t("common_yes"), command=lambda: _answer(True))
    yes_btn.pack(side="right")

    dialog.protocol("WM_DELETE_WINDOW", lambda: _answer(False))
    dialog.bind("<Return>", lambda e: _answer(True))
    dialog.bind("<Escape>", lambda e: _answer(False))

    dialog.update_idletasks()
    try:
        if root is not None and root.winfo_viewable():
            x = root.winfo_rootx() + (root.winfo_width() - dialog.winfo_width()) // 2
            y = root.winfo_rooty() + (root.winfo_height() - dialog.winfo_height()) // 3
            dialog.geometry(f"+{max(0, x)}+{max(0, y)}")
    except tk.TclError:
        pass

    dialog.grab_set()
    yes_btn.focus_set()
    dialog.wait_window()
    return result["value"]


def confirm_backup_preview(parent, zip_path):
    try:
        summary = inspect_backup_archive(zip_path)
    except Exception as e:
        messagebox.showerror(t("common_error"), t("importexport_preview_failed", error=e), parent=parent)
        return False
    return ask_yes_no(
        t("importexport_preview_title"), format_backup_preview(summary), parent=parent
    )


def load_default_ingredients():
    """Charge la liste des 1030 ingrédients de cuisine les plus courants,
    fournie avec l'application (fichier ingredients_par_defaut.json)."""
    if os.path.exists(DEFAULT_INGREDIENTS_FILE):
        try:
            with open(DEFAULT_INGREDIENTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception as exc:
            log_internal_error("load_default_ingredients", exc)
            return []
    return []


def normalize_oe(text):
    """Remplace les ligatures œ/Œ par 'oe'/'Oe' afin qu'un mot comme « Œuf »
    s'affiche et se classe avec les autres mots commençant par « o »."""
    return text.replace("œ", "oe").replace("Œ", "Oe")


def ingredient_sort_key(text):
    """Clé de tri qui ignore les accents (é, è, ê, à, ç...) afin qu'un mot
    comme « Échalote » se classe avec les autres mots en « e », et qui
    convertit d'abord œ/Œ en oe/Oe pour un classement cohérent avec « o »."""
    normalized = normalize_oe(text)
    decomposed = unicodedata.normalize("NFD", normalized)
    stripped = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    return stripped.lower()


def print_file(path):
    """Chemin d'impression POSIX ; Windows utilise print_document()."""
    try:
        subprocess.run(["lp", path], check=True)
        return "printed"
    except Exception:
        try:
            subprocess.run(["xdg-open", path], check=True)
            return "opened"
        except Exception as exc:
            log_internal_error("print_file", exc)
            return None


def report_print_result(result, temp_path, subject, parent=None):
    if result == "cancelled":
        return
    if result == "printed":
        messagebox.showinfo(t("print_title"), t("print_sent", subject=subject), parent=parent)
    elif result == "opened":
        messagebox.showinfo(t("print_title"), t("print_reader_opened", subject=subject), parent=parent)
    else:
        messagebox.showerror(t("print_title"), t("print_failed_path", path=temp_path), parent=parent)


def _report_native_print_error(parent, path, error):
    from windows_printing import PrintDependencyError
    log_internal_error("windows_print", error)
    if isinstance(error, PrintDependencyError):
        # ``main.pyw`` peut être associé à un autre Python que celui utilisé
        # pour installer les dépendances. Afficher l'interpréteur exact évite
        # un aller-retour inutile avec la commande ``python`` par défaut.
        interpreter = sys.executable or "python"
        detail = (
            f"{t('print_dependency_missing')}\n\n"
            f"Interpréteur utilisé : {interpreter}\n"
            f"Commande : \"{interpreter}\" -m pip install -r requirements.txt\n"
            f"Diagnostic : {error}"
        )
    else:
        detail = str(error)
    if ask_yes_no(t("print_title"), t("print_native_failed", error=detail, path=path), parent=parent):
        try:
            os.startfile(path)
        except OSError as exc:
            log_internal_error("print_open_pdf", exc)
            messagebox.showerror(t("print_title"), t("print_failed_path", path=path), parent=parent)


def print_document(parent, path, subject):
    """Ouvre la boîte d'impression classique Windows puis imprime le PDF."""
    if os.name != "nt":
        report_print_result(print_file(path), path, subject, parent)
        return
    from windows_printing import prepare_windows_print, PrintCancelled
    try:
        parent.update_idletasks()
        job = prepare_windows_print(path, owner=parent.winfo_id())
    except Exception as exc:
        _report_native_print_error(parent, path, exc)
        return
    if job is None:
        return
    cancelled = threading.Event()
    messages = queue.Queue()
    try:
        previous_grab = parent.grab_current()
        progress_window = tk.Toplevel(parent)
        progress_window.title(t("print_title"))
        progress_window.transient(parent)
        progress_window.resizable(False, False)
        body = ttk.Frame(progress_window, padding=18)
        body.pack(fill="both", expand=True)
        label = ttk.Label(body, text=t("print_preparing"), wraplength=440)
        label.pack(fill="x", pady=(0, 12))
        bar = ttk.Progressbar(body, mode="indeterminate", length=360)
        bar.pack(fill="x", pady=(0, 12))
        bar.start(30)
        def request_cancel():
            cancelled.set()
            label.configure(text=t("print_cancelling"))
            cancel_button.configure(state="disabled")
        cancel_button = ttk.Button(body, text=t("common_cancel"), command=request_cancel)
        cancel_button.pack(anchor="e")
        progress_window.protocol("WM_DELETE_WINDOW", request_cancel)
        progress_window.bind("<Destroy>", lambda event: cancelled.set()
                             if event.widget is progress_window else None, add="+")
        progress_window.grab_set()
    except Exception:
        job.close()
        raise

    def worker():
        try:
            result = job.run(cancelled.is_set, lambda done, total: messages.put(("progress", (done, total))))
            messages.put(("done", result))
        except PrintCancelled:
            messages.put(("done", "cancelled"))
        except Exception as exc:
            messages.put(("error", exc))

    def finish(kind, value):
        bar.stop()
        progress_window.grab_release()
        progress_window.destroy()
        if parent.winfo_exists():
            if previous_grab is not None and previous_grab.winfo_exists():
                previous_grab.grab_set()
            parent.lift()
            parent.focus_set()
            if kind == "error":
                _report_native_print_error(parent, path, value)
            else:
                report_print_result(value, path, subject, parent)

    def poll():
        if not progress_window.winfo_exists():
            cancelled.set()
            return
        while True:
            try:
                kind, value = messages.get_nowait()
            except queue.Empty:
                break
            if kind == "progress":
                if not cancelled.is_set():
                    label.configure(text=t("print_page_progress", done=value[0], total=value[1]))
            else:
                finish(kind, value)
                return
        progress_window.after(100, poll)

    try:
        threading.Thread(target=worker, daemon=True).start()
    except Exception:
        job.close()
        progress_window.destroy()
        if previous_grab is not None and previous_grab.winfo_exists():
            previous_grab.grab_set()
        raise
    progress_window.after(100, poll)


_WINDOWS_RESERVED_FILENAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def sanitize_windows_filename(name, fallback="recette", max_length=120):
    """Nettoie un nom proposé à l'enregistrement sous Windows.

    Retire les caractères interdits <>:"/\\|?*, les caractères de contrôle,
    les espaces/points finaux et protège aussi les noms réservés (CON, AUX,
    COM1...). Le contenu de la recette n'est évidemment pas modifié.
    """
    value = str(name or "").strip()
    value = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", value)
    value = re.sub(r"\s+", " ", value).strip(" .")
    if not value:
        value = fallback
    stem = value.split(".", 1)[0].upper()
    if stem in _WINDOWS_RESERVED_FILENAMES:
        value = "_" + value
    if len(value) > max_length:
        value = value[:max_length].rstrip(" .")
    return value or fallback


def get_temp_pdf_path(prefix):
    """Crée un chemin unique dans le dossier temporaire du système, utilisé
    pour générer un PDF juste avant de l'envoyer à l'imprimante."""
    return os.path.join(tempfile.gettempdir(), f"{prefix}_{uuid.uuid4().hex}.pdf")


# Classement des ingrédients par rayon de magasin, utilisé pour regrouper la
# liste de courses. Chaque rayon est associé à une liste de mots-clés ; le
# premier rayon dont un mot-clé apparaît dans le nom de l'ingrédient est
# retenu. L'ordre de la liste correspond à un parcours de magasin classique.
RAYON_KEYWORDS = [
    ("Fruits & Légumes", [
        "ail", "oignon", "echalote", "poireau", "carotte", "celeri", "panais",
        "navet", "betterave", "radis", "pomme de terre", "patate", "topinambour",
        "tomate", "concombre", "courgette", "aubergine", "poivron", "piment",
        "chou", "brocoli", "epinard", "blette", "oseille", "roquette", "mache",
        "laitue", "batavia", "endive", "chicoree", "cresson", "pissenlit",
        "fenouil", "artichaut", "asperge", "petit pois", "haricot vert",
        "haricot beurre", "fève", "mais", "courge", "potiron", "citrouille",
        "champignon", "girolle", "cepe", "truffe", "igname", "manioc", "gombo",
        "salsifis", "cardon", "crosne", "chayotte", "cornichon", "avocat",
        "pomme", "poire", "banane", "orange", "clementine", "mandarine",
        "pamplemousse", "pomelo", "citron", "kiwi", "fraise", "framboise",
        "myrtille", "mure", "groseille", "cassis", "cerise", "griotte",
        "abricot", "peche", "nectarine", "prune", "mirabelle", "reine-claude",
        "raisin", "melon", "pasteque", "ananas", "mangue", "papaye",
        "fruit de la passion", "litchi", "grenade", "figue", "datte", "coing",
        "kaki", "rhubarbe", "noix de coco", "kumquat", "goyave", "carambole",
        "persil", "basilic", "thym", "romarin", "origan",
        "marjolaine", "sauge", "laurier", "menthe", "ciboulette", "cerfeuil",
        "estragon", "aneth", "gingembre frais", "curcuma frais", "citronnelle",
        "germe de soja", "pousse", "algue",
    ]),
    ("Viandes & Poissons", [
        "boeuf", "bœuf", "veau", "porc", "lard", "bacon", "jambon", "saucisse",
        "chorizo", "andouille", "boudin", "saucisson", "pancetta", "agneau",
        "mouton", "poulet", "coq", "dinde", "canard", "magret", "confit de",
        "foie gras", "oie", "pintade", "caille", "pigeon", "lapin", "gibier",
        "chevreuil", "sanglier", "cheval", "steak", "viande", "kefta",
        "saumon", "truite", "cabillaud", "morue", "merlu", "colin", "lieu",
        "bar", "loup de mer", "dorade", "daurade", "thon", "espadon",
        "maquereau", "sardine", "anchois", "hareng", "sole", "turbot",
        "flétan", "raie", "rouget", "saint-pierre", "lotte", "baudroie",
        "congre", "anguille", "carpe", "brochet", "perche", "sandre",
        "tilapia", "panga", "poisson", "surimi", "caviar", "tarama",
        "crevette", "gambas", "langoustine", "homard", "langouste", "crabe",
        "tourteau", "etrille", "moule", "huitre", "huître", "palourde",
        "coque", "praire", "bulot", "bigorneau", "couteau", "petoncle",
        "coquille saint-jacques", "calamar", "encornet", "seiche", "poulpe",
        "oursin", "ormeau", "escargot", "grenouille",
    ]),
    ("Crèmerie", [
        "lait", "creme", "crème", "beurre", "margarine", "yaourt",
        "fromage", "faisselle", "petit-suisse", "mascarpone", "ricotta",
        "cottage", "emmental", "gruyere", "comte", "beaufort", "cantal",
        "reblochon", "morbier", "tomme", "camembert", "brie", "coulommiers",
        "munster", "epoisses", "maroilles", "livarot", "pont-l'eveque",
        "roquefort", "bleu", "fourme", "gorgonzola", "chevre", "chèvre",
        "crottin", "feta", "halloumi", "mozzarella", "burrata", "parmesan",
        "pecorino", "grana padano", "provolone", "gouda", "edam", "cheddar",
        "raclette", "fondue", "babeurre", "kefir", "skyr", "oeuf", "œuf",
    ]),
    ("Boulangerie & Pâtisserie", [
        "farine", "levure", "bicarbonate", "chocolat", "cacao", "praline",
        "praliné", "nougat", "caramel", "gelatine", "agar-agar", "pectine",
        "pate feuilletee", "pate brisee", "pate sablee", "pate a choux",
        "pate a pizza", "pate filo", "pate a crepes", "pate a gaufres",
        "genoise", "biscuit", "boudoir", "speculoos", "meringue",
        "poudre d'amande", "poudre de noisette", "amande effilee",
        "fruits confits", "nappage", "glacage", "fondant", "marron glace",
        "chataigne", "châtaigne", "pain", "baguette", "chapelure", "croutons",
        "biscotte", "cracker", "sucre", "cassonade", "vergeoise", "miel",
        "sirop", "melasse", "vanille",
    ]),
    ("Épicerie", [
        "riz", "semoule", "couscous", "boulgour", "quinoa", "epeautre",
        "orge", "sarrasin", "avoine", "ble", "blé", "fecule", "maizena",
        "tapioca", "pate", "spaghetti", "penne", "fusilli", "tagliatelle",
        "macaroni", "lasagne", "nouille", "vermicelle", "lentille",
        "pois chiche", "soja", "haricot rouge", "haricot blanc",
        "haricot noir", "huile", "graisse", "saindoux", "ghee",
        "moutarde", "ketchup", "mayonnaise", "vinaigre", "sauce",
        "concentre de tomate", "coulis", "pesto", "tapenade", "houmous",
        "tahini", "confiture", "marmelade", "gelee", "chutney", "pickles",
        "cornichons au vinaigre", "câpres", "capres", "olive", "raifort",
        "wasabi", "bouillon", "fond de veau", "fumet", "tofu", "seitan",
        "tempeh", "conserve", "boite", "boîte", "chips", "nachos",
        "pop-corn", "biscuit apero", "cacahuete grillee",
    ]),
    ("Herbes & Épices", [
        "poivre", "sel", "paprika", "cumin", "coriandre en", "cannelle",
        "muscade", "girofle", "cardamome", "anis", "curry", "garam masala",
        "ras el hanout", "za'atar", "sumac", "safran", "vanille en poudre",
        "reglisse", "genievre", "moutarde en poudre", "herbes de provence",
        "bouquet garni", "quatre epices", "piment de cayenne",
        "piment d'espelette", "chili en poudre", "epices", "épices",
        "curcuma en poudre", "gingembre en poudre", "sesame", "sésame",
        "graines de", "colorant",
    ]),
    ("Boissons", [
        "vin", "champagne", "porto", "madere", "marsala", "vermouth",
        "cognac", "armagnac", "calvados", "rhum", "whisky", "bourbon", "gin",
        "vodka", "grand marnier", "cointreau", "amaretto", "kirsch",
        "eau de vie", "biere", "bière", "cidre", "cafe", "café", "the", "thé",
        "eau gazeuse", "jus de", "sirop de grenadine", "sirop de menthe",
    ]),
]


def get_ingredient_rayon(name):
    """Retourne le rayon de magasin associé à un ingrédient, en se basant sur
    des mots-clés (recherche insensible aux accents et à la casse). Renvoie
    'Autre' si aucun mot-clé ne correspond."""
    key = ingredient_sort_key(name)
    for rayon, keywords in RAYON_KEYWORDS:
        for kw in keywords:
            if ingredient_sort_key(kw) in key:
                return rayon
    return "Autre"


RAYON_ORDER = [
    "Fruits & Légumes", "Viandes & Poissons", "Crèmerie",
    "Boulangerie & Pâtisserie", "Épicerie", "Herbes & Épices", "Boissons", "Autre",
]

# Table de correspondance des rayons par langue, sur le même principe que
# le dictionnaire d'ingrédients : la donnée réelle (regroupement, tri,
# stockage dans les listes de courses enregistrées) reste toujours le nom
# français ci-dessus, cette table ne sert qu'à l'affichage.
RAYON_TRANSLATIONS = {
    "en": {
        "fruits & légumes": "Fruits & Vegetables",
        "viandes & poissons": "Meat & Fish",
        "crèmerie": "Dairy",
        "boulangerie & pâtisserie": "Bakery & Pastry",
        "épicerie": "Grocery",
        "herbes & épices": "Herbs & Spices",
        "boissons": "Beverages",
        "autre": "Other",
    },
    "es": {
        "fruits & légumes": "Frutas y verduras",
        "viandes & poissons": "Carnes y pescados",
        "crèmerie": "Lácteos",
        "boulangerie & pâtisserie": "Panadería y repostería",
        "épicerie": "Almacén",
        "herbes & épices": "Hierbas y especias",
        "boissons": "Bebidas",
        "autre": "Otro",
    },
    "de": {
        "fruits & légumes": "Obst & Gemüse",
        "viandes & poissons": "Fleisch & Fisch",
        "crèmerie": "Milchprodukte",
        "boulangerie & pâtisserie": "Bäckerei & Konditorei",
        "épicerie": "Lebensmittel",
        "herbes & épices": "Kräuter & Gewürze",
        "boissons": "Getränke",
        "autre": "Sonstiges",
    },
}


def translate_rayon_name(rayon):
    """Retourne le nom d'affichage d'un rayon de magasin dans la langue
    actuellement sélectionnée. Comme translate_ingredient_name(), ne
    change jamais la donnée réelle utilisée pour le regroupement, le tri
    ou le stockage — seulement ce qui est montré à l'écran ou écrit dans
    un export."""
    if not rayon:
        return rayon
    if CURRENT_LANGUAGE == "fr":
        return rayon
    return RAYON_TRANSLATIONS.get(CURRENT_LANGUAGE, {}).get(rayon.strip().lower(), rayon)


# Tables de correspondance pour les catégories et niveaux de difficulté,
# par langue, sur le même principe que les rayons et les ingrédients : la
# donnée réelle stockée dans chaque recette reste toujours en français
# (ces valeurs sont des clés de comparaison/filtre à de nombreux
# endroits), ces tables ne servent qu'à l'affichage et à la résolution
# des menus déroulants (qui sont toujours en liste fermée "readonly",
# donc sans ambiguïté possible contrairement aux noms d'ingrédients en
# texte libre).
CATEGORY_TRANSLATIONS = {
    "en": {
        "petit-déjeuner": "Breakfast",
        "entrée": "Starter",
        "plat": "Main course",
        "dessert": "Dessert",
        "apéro": "Appetizer",
        "boisson": "Drink",
        "sauce": "Sauce",
        "autre": "Other",
    },
    "es": {
        "petit-déjeuner": "Desayuno",
        "entrée": "Entrante",
        "plat": "Plato principal",
        "dessert": "Postre",
        "apéro": "Aperitivo",
        "boisson": "Bebida",
        "sauce": "Salsa",
        "autre": "Otro",
    },
    "de": {
        "petit-déjeuner": "Frühstück",
        "entrée": "Vorspeise",
        "plat": "Hauptgericht",
        "dessert": "Dessert",
        "apéro": "Aperitif",
        "boisson": "Getränk",
        "sauce": "Sauce",
        "autre": "Sonstiges",
    },
}

DIFFICULTY_TRANSLATIONS = {
    "en": {
        "très facile": "Very easy",
        "facile": "Easy",
        "moyen": "Medium",
        "difficile": "Hard",
    },
    "es": {
        "très facile": "Muy fácil",
        "facile": "Fácil",
        "moyen": "Medio",
        "difficile": "Difícil",
    },
    "de": {
        "très facile": "Sehr einfach",
        "facile": "Einfach",
        "moyen": "Mittel",
        "difficile": "Schwer",
    },
}


def translate_category_name(category):
    """Retourne le nom d'affichage d'une catégorie de recette dans la
    langue actuellement sélectionnée. Ne change jamais la donnée réelle
    stockée dans la recette."""
    if not category:
        return category
    if CURRENT_LANGUAGE == "fr":
        return category
    return CATEGORY_TRANSLATIONS.get(CURRENT_LANGUAGE, {}).get(category.strip().lower(), category)


def translate_difficulty_name(difficulty):
    """Retourne le nom d'affichage d'un niveau de difficulté dans la
    langue actuellement sélectionnée. Ne change jamais la donnée réelle
    stockée dans la recette."""
    if not difficulty:
        return difficulty
    if CURRENT_LANGUAGE == "fr":
        return difficulty
    return DIFFICULTY_TRANSLATIONS.get(CURRENT_LANGUAGE, {}).get(difficulty.strip().lower(), difficulty)


def resolve_category_input(displayed_value, category_options):
    """Résout une catégorie sélectionnée dans un menu déroulant (donc
    éventuellement affichée traduite) vers son nom canonique français
    exact. Les menus concernés sont toujours en liste fermée
    (state='readonly'), donc chaque valeur affichée correspond
    exactement à une seule catégorie française : pas d'ambiguïté possible
    ici, contrairement aux noms d'ingrédients en texte libre."""
    if not displayed_value:
        return displayed_value
    for cat in category_options:
        if cat.strip().lower() == displayed_value.strip().lower():
            return cat
    for cat in category_options:
        if translate_category_name(cat).strip().lower() == displayed_value.strip().lower():
            return cat
    return displayed_value


def resolve_difficulty_input(displayed_value, difficulty_options):
    """Équivalent de resolve_category_input() pour le niveau de
    difficulté."""
    if not displayed_value:
        return displayed_value
    for diff in difficulty_options:
        if diff.strip().lower() == displayed_value.strip().lower():
            return diff
    for diff in difficulty_options:
        if translate_difficulty_name(diff).strip().lower() == displayed_value.strip().lower():
            return diff
    return displayed_value


# Table de correspondance pour les options du menu déroulant de tri des
# recettes (RECIPE_SORT_OPTIONS), même principe que les catégories et
# difficultés : liste fermée en lecture seule, la donnée réelle comparée
# dans recipe_sort_key() reste toujours la valeur française d'origine.
SORT_OPTION_TRANSLATIONS = {
    "en": {
        "nom (a-z)": "Name (A-Z)",
        "temps de préparation": "Prep time",
        "temps total": "Total time",
        "difficulté": "Difficulty",
        "note": "Rating",
        "ajoutées récemment": "Recently added",
        "plus cuisinées": "Most cooked",
        "dernière cuisson": "Last cooked",
    },
    "es": {
        "nom (a-z)": "Nombre (A-Z)",
        "temps de préparation": "Tiempo de preparación",
        "temps total": "Tiempo total",
        "difficulté": "Dificultad",
        "note": "Valoración",
        "ajoutées récemment": "Añadidas recientemente",
        "plus cuisinées": "Más cocinadas",
        "dernière cuisson": "Última preparación",
    },
    "de": {
        "nom (a-z)": "Name (A-Z)",
        "temps de préparation": "Zubereitungszeit",
        "temps total": "Gesamtzeit",
        "difficulté": "Schwierigkeit",
        "note": "Bewertung",
        "ajoutées récemment": "Kürzlich hinzugefügt",
        "plus cuisinées": "Am häufigsten gekocht",
        "dernière cuisson": "Zuletzt gekocht",
    },
}


def translate_sort_option(option):
    """Retourne le nom d'affichage d'une option de tri de recette dans la
    langue actuellement sélectionnée. Ne change jamais la valeur comparée
    dans recipe_sort_key()."""
    if not option:
        return option
    if CURRENT_LANGUAGE == "fr":
        return option
    return SORT_OPTION_TRANSLATIONS.get(CURRENT_LANGUAGE, {}).get(option.strip().lower(), option)


def resolve_sort_option_input(displayed_value, sort_options):
    """Résout une option de tri sélectionnée dans le menu déroulant
    (éventuellement affichée traduite) vers sa valeur canonique française
    exacte. Même principe que resolve_category_input() : liste fermée,
    donc sans ambiguïté."""
    if not displayed_value:
        return displayed_value
    for opt in sort_options:
        if opt.strip().lower() == displayed_value.strip().lower():
            return opt
    for opt in sort_options:
        if translate_sort_option(opt).strip().lower() == displayed_value.strip().lower():
            return opt
    return displayed_value


# Table de correspondance pour les unités de mesure des ingrédients
# (UNIT_OPTIONS, PRICE_UNIT_OPTIONS et les quelques unités supplémentaires
# de contenant utilisées dans le garde-manger et l'ajout manuel à la
# liste de courses). Les unités du système métrique (Gr, Kilo, cl, Litre)
# utilisent le même symbole dans les 4 langues (g/kg/cl/L partout dans le
# monde) : elles ne figurent donc pas ici, translate_unit_name() les
# laisse simplement inchangées comme n'importe quel mot sans traduction
# connue. Seuls les mots qui diffèrent réellement d'une langue à l'autre
# ont une entrée.
UNIT_TRANSLATIONS = {
    "en": {
        "gr": "g",
        "kilo": "kg",
        "litre": "L",
        "pièce": "piece",
        "cuillère à soupe": "tbsp",
        "cuillère à café": "tsp",
        "pincée": "pinch", "cuillerée": "spoonful", "filet": "drizzle", "poignée": "handful",
        "pot de yaourt": "yogurt pot", "sachet": "sachet",
        "disque": "disc", "tour de moulin": "turn of the mill", "grosse poignée": "large handful",
        "autre": "other",
        "boîte": "can",
        "paquet": "pack",
        "rouleau": "roll",
        "bouteille": "bottle",
    },
    "es": {
        "gr": "g",
        "kilo": "kg",
        "litre": "L",
        "pièce": "unidad",
        "cuillère à soupe": "cucharada",
        "cuillère à café": "cucharadita",
        "pincée": "pizca", "cuillerée": "cucharada (tamaño sin especificar)", "filet": "chorrito", "poignée": "puñado",
        "pot de yaourt": "vaso de yogur", "sachet": "sobre",
        "disque": "disco", "tour de moulin": "vuelta de molinillo", "grosse poignée": "puñado grande",
        "autre": "otro",
        "boîte": "lata",
        "paquet": "paquete",
        "rouleau": "rollo",
        "bouteille": "botella",
    },
    "de": {
        "gr": "g",
        "kilo": "kg",
        "litre": "L",
        "pièce": "Stück",
        "cuillère à soupe": "EL",
        "cuillère à café": "TL",
        "pincée": "Prise", "cuillerée": "Löffel (Größe nicht angegeben)", "filet": "Schuss", "poignée": "Handvoll",
        "pot de yaourt": "Joghurtbecher", "sachet": "Beutel",
        "disque": "Teigkreis", "tour de moulin": "Mühlenumdrehung", "grosse poignée": "große Handvoll",
        "autre": "andere",
        "boîte": "Dose",
        "paquet": "Packung",
        "rouleau": "Rolle",
        "bouteille": "Flasche",
    },
}


def translate_unit_name(unit):
    """Retourne le nom d'affichage d'une unité de mesure dans la langue
    actuellement sélectionnée. Les unités du système métrique (Gr, Kilo,
    cl, Litre, kg, L) n'ont pas d'entrée dans la table et restent donc
    inchangées : ce sont les mêmes symboles dans toutes les langues
    disponibles. Ne change jamais la donnée réelle stockée dans la
    recette ou le prix d'un ingrédient."""
    if not unit:
        return unit
    if CURRENT_LANGUAGE == "fr":
        return unit
    return UNIT_TRANSLATIONS.get(CURRENT_LANGUAGE, {}).get(unit.strip().lower(), unit)


def resolve_unit_input(displayed_value, unit_options):
    """Résout une unité sélectionnée dans un menu déroulant fermé
    (état 'readonly', donc sans ambiguïté) vers sa valeur canonique
    française exacte. Pour les champs d'unité en texte libre (garde-
    manger, ajout manuel), voir resolve_unit_input_best_effort()
    ci-dessous à la place."""
    if not displayed_value:
        return displayed_value
    for u in unit_options:
        if u.strip().lower() == displayed_value.strip().lower():
            return u
    for u in unit_options:
        if translate_unit_name(u).strip().lower() == displayed_value.strip().lower():
            return u
    return displayed_value


def resolve_unit_input_best_effort(typed_value, unit_options):
    """Équivalent de resolve_unit_input(), mais pour les champs d'unité en
    texte libre : si la valeur tapée ou sélectionnée correspond à une
    unité connue (en français ou traduite), la résout vers son nom
    canonique français ; sinon, la retourne telle quelle, pour ne pas
    entraver la saisie d'une unité personnalisée absente de la liste
    (ex. « sachet »)."""
    if not typed_value:
        return typed_value
    return resolve_unit_input(typed_value, unit_options)


# Tables de correspondance pour les jours de la semaine et les créneaux de
# repas, par langue. Contrairement aux catégories/difficultés, ces
# valeurs servent aussi de CLÉS de dictionnaire dans le planning de la
# semaine et son historique (weekly_plan.json, weekly_plan_history.json,
# weekly_plan_templates.json) : ces tables ne doivent JAMAIS être
# utilisées pour changer une clé de stockage, uniquement pour ce qui est
# affiché à l'écran ou écrit dans un export (planning ICS, PDF...).
WEEKDAY_TRANSLATIONS = {
    "en": {
        "lundi": "Monday",
        "mardi": "Tuesday",
        "mercredi": "Wednesday",
        "jeudi": "Thursday",
        "vendredi": "Friday",
        "samedi": "Saturday",
        "dimanche": "Sunday",
    },
    "es": {
        "lundi": "Lunes",
        "mardi": "Martes",
        "mercredi": "Miércoles",
        "jeudi": "Jueves",
        "vendredi": "Viernes",
        "samedi": "Sábado",
        "dimanche": "Domingo",
    },
    "de": {
        "lundi": "Montag",
        "mardi": "Dienstag",
        "mercredi": "Mittwoch",
        "jeudi": "Donnerstag",
        "vendredi": "Freitag",
        "samedi": "Samstag",
        "dimanche": "Sonntag",
    },
}

MEALSLOT_TRANSLATIONS = {
    "en": {
        "petit-déjeuner": "Breakfast",
        "déjeuner — entrée": "Lunch — Starter",
        "déjeuner — plat": "Lunch — Main",
        "déjeuner — dessert": "Lunch — Dessert",
        "dîner — entrée": "Dinner — Starter",
        "dîner — plat": "Dinner — Main",
        "dîner — dessert": "Dinner — Dessert",
    },
    "es": {
        "petit-déjeuner": "Desayuno",
        "déjeuner — entrée": "Almuerzo — Entrante",
        "déjeuner — plat": "Almuerzo — Plato principal",
        "déjeuner — dessert": "Almuerzo — Postre",
        "dîner — entrée": "Cena — Entrante",
        "dîner — plat": "Cena — Plato principal",
        "dîner — dessert": "Cena — Postre",
    },
    "de": {
        "petit-déjeuner": "Frühstück",
        "déjeuner — entrée": "Mittagessen — Vorspeise",
        "déjeuner — plat": "Mittagessen — Hauptgericht",
        "déjeuner — dessert": "Mittagessen — Dessert",
        "dîner — entrée": "Abendessen — Vorspeise",
        "dîner — plat": "Abendessen — Hauptgericht",
        "dîner — dessert": "Abendessen — Dessert",
    },
}


def translate_weekday_name(day):
    """Retourne le nom d'affichage d'un jour de la semaine dans la langue
    actuellement sélectionnée. Ne doit jamais servir à changer une clé de
    stockage : le planning de la semaine et son historique restent
    toujours indexés par le nom français."""
    if not day:
        return day
    if CURRENT_LANGUAGE == "fr":
        return day
    return WEEKDAY_TRANSLATIONS.get(CURRENT_LANGUAGE, {}).get(day.strip().lower(), day)


def translate_mealslot_name(slot):
    """Retourne le nom d'affichage d'un créneau de repas dans la langue
    actuellement sélectionnée. Même principe que translate_weekday_name()
    : jamais utilisée pour changer une clé de stockage."""
    if not slot:
        return slot
    if CURRENT_LANGUAGE == "fr":
        return slot
    return MEALSLOT_TRANSLATIONS.get(CURRENT_LANGUAGE, {}).get(slot.strip().lower(), slot)


def rating_stars(n):
    """Retourne une représentation textuelle d'une note sur 5 étoiles,
    ex: rating_stars(3) -> '★★★☆☆'."""
    try:
        n = int(n or 0)
    except (TypeError, ValueError):
        n = 0
    n = max(0, min(5, n))
    return "★" * n + "☆" * (5 - n)


def recipe_matches_search(recipe, search_key):
    """Vérifie si une recette correspond à une recherche (déjà normalisée via
    ingredient_sort_key), en comparant le nom ET les étiquettes."""
    if not search_key:
        return True
    if search_key in ingredient_sort_key(recipe["name"]):
        return True
    for tag in recipe.get("tags", []):
        if search_key in ingredient_sort_key(tag):
            return True
    return False


def fuzzy_search_recipes(query, recipes, limit=8, threshold=0.45):
    """Cherche des recettes proches d'une saisie approximative (faute de
    frappe, accent oublié...) quand aucune correspondance exacte n'a été
    trouvée. Même principe que rank_close_ingredients (SequenceMatcher, sans
    dépendance externe), appliqué au nom et aux étiquettes de la recette."""
    query_key = ingredient_sort_key(query)
    if not query_key:
        return []
    scored = []
    for recipe in recipes:
        name_key = ingredient_sort_key(recipe.get("name", ""))
        score = difflib.SequenceMatcher(None, query_key, name_key).ratio()
        for tag in recipe.get("tags", []):
            tag_score = difflib.SequenceMatcher(None, query_key, ingredient_sort_key(tag)).ratio()
            score = max(score, tag_score)
        if score >= threshold:
            scored.append((score, recipe))
    scored.sort(key=lambda item: (-item[0], ingredient_sort_key(item[1].get("name", ""))))
    return [recipe for _score, recipe in scored[:limit]]


RECIPE_SORT_OPTIONS = ["Nom (A-Z)", "Temps de préparation", "Temps total", "Difficulté", "Note", "Ajoutées récemment", "Plus cuisinées", "Dernière cuisson"]
_DIFFICULTY_ORDER = {"Très facile": 0.5, "Facile": 1, "Moyen": 2, "Difficile": 3}


def find_similar_recipes(recipe, all_recipes, limit=5):
    """Suggère des recettes proches d'une recette donnée, en se basant sur
    la même catégorie, les étiquettes en commun et les ingrédients en
    commun (chacun apportant des points, la catégorie comptant le plus).
    Ne retourne que des recettes avec au moins un point de similarité, et
    jamais la recette elle-même."""
    target_name = recipe.get("name")
    target_category = recipe.get("category", "Autre")
    target_tags = {ingredient_sort_key(t) for t in recipe.get("tags", [])}
    target_ingredients = {ingredient_sort_key(ing["name"]) for ing in recipe.get("ingredients", [])}

    scored = []
    for other in all_recipes:
        if other.get("name") == target_name:
            continue
        score = 0
        if other.get("category", "Autre") == target_category:
            score += 2
        other_tags = {ingredient_sort_key(t) for t in other.get("tags", [])}
        score += len(target_tags & other_tags)
        other_ingredients = {ingredient_sort_key(ing["name"]) for ing in other.get("ingredients", [])}
        score += min(len(target_ingredients & other_ingredients), 5)
        if score > 0:
            scored.append((score, other))

    scored.sort(key=lambda pair: (-pair[0], ingredient_sort_key(pair[1]["name"])))
    return [r for score, r in scored[:limit]]


def recipe_sort_key(recipe, option):
    """Retourne une clé de tri pour une recette selon l'option choisie parmi
    RECIPE_SORT_OPTIONS."""
    if option == "Temps de préparation":
        try:
            return float(recipe.get("prep_time") or 0)
        except (TypeError, ValueError):
            return 0.0
    if option == "Temps total":
        try:
            return float(recipe.get("prep_time") or 0) + float(recipe.get("cook_time") or 0)
        except (TypeError, ValueError):
            return 0.0
    if option == "Difficulté":
        return _DIFFICULTY_ORDER.get(recipe.get("difficulty"), 0)
    if option == "Note":
        return -int(recipe.get("rating", 0) or 0)  # négatif : meilleure note en premier
    if option == "Ajoutées récemment":
        return recipe.get("created_at") or ""
    if option == "Plus cuisinées":
        return -int(recipe.get("times_cooked", 0) or 0)
    if option == "Dernière cuisson":
        dates = recipe.get("cooked_dates") or []
        value = max(dates) if dates else ""
        try:
            return -datetime.fromisoformat(value).timestamp() if value else 0
        except (TypeError, ValueError):
            return 0
    return ingredient_sort_key(recipe["name"])


def format_recipe_list_label(recipe):
    """Construit le libellé affiché pour une recette dans les listes de
    sélection : favori, catégorie, nom, note, et — pour qu'on les voie tout
    de suite lors d'un tri — le temps total, la difficulté et les
    allergènes éventuels."""
    cat = translate_category_name(recipe.get("category", "Autre"))
    star = "⭐ " if recipe.get("favorite") else ""
    wish = "💭 " if recipe.get("wishlist") else ""
    rating = recipe.get("rating", 0)
    rating_suffix = f" {rating_stars(rating)}" if rating else ""
    label = f"{star}{wish}[{cat}] {recipe['name']}{rating_suffix}"

    info_bits = []
    prep = recipe.get("prep_time")
    cook = recipe.get("cook_time")
    if prep or cook:
        try:
            total = float(prep or 0) + float(cook or 0)
            total_display = int(total) if total == int(total) else total
        except (TypeError, ValueError):
            total_display = None
        if total_display is not None:
            info_bits.append(f"{total_display} min")
    difficulty = recipe.get("difficulty")
    if difficulty:
        info_bits.append(translate_difficulty_name(difficulty))
    allergens = recipe.get("allergens") or []
    if allergens:
        info_bits.append(f"⚠ {', '.join(translate_allergen_name(a) for a in allergens)}")
    if info_bits:
        label += f"  ({' · '.join(info_bits)})"
    return label



SAFE_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff"}


def safe_image_filename(value):
    """Retourne un nom de fichier image sûr et local, sinon None."""
    if not isinstance(value, str):
        return None
    raw = value.strip().replace("\\", "/")
    if not raw or raw.startswith("/") or "/" in raw or raw in (".", ".."):
        return None
    name = os.path.basename(raw)
    if name != raw or name in ("", ".", ".."):
        return None
    if any(ord(c) < 32 for c in name):
        return None
    ext = os.path.splitext(name)[1].lower()
    if ext and ext not in SAFE_IMAGE_EXTENSIONS:
        return None
    return name


def image_store_path(value):
    """Construit un chemin garanti à l'intérieur d'IMAGES_DIR."""
    name = safe_image_filename(value)
    if not name:
        return None
    root = os.path.realpath(IMAGES_DIR)
    path = os.path.realpath(os.path.join(root, name))
    try:
        if os.path.commonpath([root, path]) != root:
            return None
    except ValueError:
        return None
    return path


def recipe_ref_key(recipe):
    if isinstance(recipe, dict):
        rid = str(recipe.get("id") or "").strip()
        if rid:
            return rid
        return str(recipe.get("name") or "").strip().casefold()
    return str(recipe or "").strip().casefold()


def find_recipe_by_id(recipes, recipe_id):
    rid = str(recipe_id or "").strip()
    if not rid:
        return None
    return next((r for r in recipes if isinstance(r, dict) and str(r.get("id") or "") == rid), None)


def find_recipe_by_ref(recipes, ref):
    """Résout une référence moderne (recipe_id) ou l'ancien nom."""
    if isinstance(ref, dict):
        recipe = find_recipe_by_id(recipes, ref.get("recipe_id") or ref.get("id"))
        if recipe is not None:
            return recipe
        name = ref.get("recipe_name") or ref.get("name")
    else:
        name = ref
    return next((r for r in recipes if isinstance(r, dict) and r.get("name") == name), None)


def _normalize_recipe_inplace(recipe, *, assign_id=True, strict=False):
    """Valide/normalise une recette sans supprimer les champs inconnus."""
    if not isinstance(recipe, dict):
        raise ValueError("recipe_not_object")
    name = recipe.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("recipe_name_missing")
    recipe["name"] = name.strip()
    if assign_id and not str(recipe.get("id") or "").strip():
        recipe["id"] = uuid.uuid4().hex
    elif recipe.get("id") is not None and not isinstance(recipe.get("id"), str):
        recipe["id"] = str(recipe.get("id"))

    persons = recipe.get("default_persons", 4)
    try:
        recipe["default_persons"] = parse_positive_number(persons)
    except (ValueError, TypeError):
        if strict:
            raise ValueError("invalid_default_persons")
        recipe["default_persons"] = 4

    ingredients = recipe.get("ingredients", [])
    if not isinstance(ingredients, list):
        raise ValueError("recipe_ingredients_not_list")
    clean_ingredients = []
    for ing in ingredients:
        if not isinstance(ing, dict):
            continue
        ing_name = ing.get("name")
        if not isinstance(ing_name, str) or not ing_name.strip():
            continue
        out = copy.deepcopy(ing)
        out["name"] = ing_name.strip()
        try:
            # ``null`` est la représentation officielle d'une quantité
            # laissée vide dans les sauvegardes mobiles (« au goût »).
            raw_quantity = out["quantity"] if "quantity" in out else 1
            out["quantity"] = parse_optional_positive_number(raw_quantity, allow_zero=True)
        except (ValueError, TypeError):
            if strict:
                raise ValueError("invalid_ingredient_quantity")
            continue
        unit = out.get("unit", "")
        out["unit"] = str(unit or "").strip()
        clean_ingredients.append(out)
    recipe["ingredients"] = clean_ingredients

    # Noms d'images principaux sûrs uniquement.
    imgs = recipe.get("images")
    if isinstance(imgs, list):
        recipe["images"] = [n for n in (safe_image_filename(x) for x in imgs) if n]
    elif imgs is not None:
        recipe["images"] = []
    legacy = safe_image_filename(recipe.get("image"))
    if recipe.get("image") and not legacy:
        recipe.pop("image", None)
    elif legacy:
        recipe["image"] = legacy

    # Photos du journal de cuisine.
    cook_log = recipe.get("cook_log", [])
    if not isinstance(cook_log, list):
        recipe["cook_log"] = []
    else:
        for entry in cook_log:
            if isinstance(entry, dict) and entry.get("photo"):
                safe = safe_image_filename(entry.get("photo"))
                if safe:
                    entry["photo"] = safe
                else:
                    entry.pop("photo", None)
    return recipe


def validate_recipes_payload(data, *, assign_ids=True):
    if not isinstance(data, list):
        raise ValueError("recipes_not_list")
    out, seen = [], set()
    for recipe in data:
        value = _normalize_recipe_inplace(copy.deepcopy(recipe), assign_id=assign_ids, strict=True)
        rid = value.get('id')
        if rid and rid in seen:
            raise ValueError(t('duplicate_recipe_id', value=rid))
        seen.add(rid)
        out.append(value)
    return out


def enrich_recipe_reference(ref, recipes):
    """Ajoute recipe_id et synchronise le nom tout en lisant les anciens fichiers."""
    if not isinstance(ref, dict):
        return ref
    recipe = find_recipe_by_ref(recipes, ref)
    if recipe is not None:
        ref["recipe_id"] = recipe.get("id")
        ref["recipe_name"] = recipe.get("name")
    return ref

_recipes_cache = None  # (mtime_ns, taille, recettes validées) ; invalidé dès que le fichier change sur disque


def _recipes_disk_key():
    try:
        stat = os.stat(DATA_FILE)
        return (stat.st_mtime_ns, stat.st_size)
    except OSError:
        return None


def load_recipes():
    """Charge les recettes; un JSON corrompu est sauvegardé et protégé.

    load_recipes() est appelé à une trentaine d'endroits du code : sans
    cache, la moindre ouverture de fenêtre revalidait entièrement le fichier
    (mesuré : ~150 ms pour 1000 recettes, ~800 ms pour 5000). Le résultat
    validé est mis en cache tant que le fichier n'a pas changé sur disque
    (date de modification + taille) ; chaque appelant reçoit toujours sa
    propre copie indépendante, exactement comme avant.
    """
    global _recipes_cache
    disk_key = _recipes_disk_key()
    if _recipes_cache is not None and disk_key is not None and _recipes_cache[0] == disk_key:
        return copy.deepcopy(_recipes_cache[1])

    raw = _read_user_json(DATA_FILE, list, [], label="recipes")
    if _corruption_key(DATA_FILE) in _CORRUPTED_DATA_FILES:
        return []
    try:
        recipes = []
        migrated = False
        invalid_entries = []
        for index, item in enumerate(raw):
            try:
                before_id = item.get("id") if isinstance(item, dict) else None
                normalized = _normalize_recipe_inplace(copy.deepcopy(item), assign_id=True)
                if not before_id and normalized.get("id"):
                    migrated = True
                recipes.append(normalized)
            except Exception as exc:
                log_internal_error(f"invalid_recipe_{index}", exc)
                invalid_entries.append((index, exc))
        if invalid_entries:
            first_index, first_error = invalid_entries[0]
            _register_corrupt_json(
                DATA_FILE,
                ValueError(f"invalid recipe at index {first_index}: {first_error}")
            )
        # On n'écrase jamais le fichier si des entrées ont été rejetées : cela
        # préserve le contenu original pour récupération manuelle éventuelle.
        if migrated and len(recipes) == len(raw):
            save_recipes(recipes)
        elif not invalid_entries:
            # Rien à réécrire : le contenu validé peut être mis en cache tel quel.
            _recipes_cache = (_recipes_disk_key(), recipes)
        return recipes
    except Exception as exc:
        log_internal_error("load_recipes_failed", exc)
        return []


def save_recipes(recipes):
    """Sauvegarde uniquement une structure de recettes valide et JSON standard."""
    global _recipes_cache
    validated = validate_recipes_payload(recipes, assign_ids=True)
    _atomic_write_json(DATA_FILE, validated)
    _recipes_cache = (_recipes_disk_key(), validated)


def load_ingredients():
    """Charge la liste des ingrédients connus (triée, sans doublons)."""
    data = _read_user_json(INGREDIENTS_FILE, list, [], label="ingredients")
    return sorted(dict.fromkeys(normalize_oe(i) for i in data if isinstance(i, str)), key=ingredient_sort_key)


def save_ingredients(ingredients):
    """Sauvegarde la liste des ingrédients connus (triée, sans doublons)."""
    cleaned_map = {}
    for i in ingredients:
        name = normalize_oe(i.strip())
        if name:
            cleaned_map.setdefault(name.lower(), name)
    cleaned = sorted(cleaned_map.values(), key=ingredient_sort_key)
    _atomic_write_json(INGREDIENTS_FILE, cleaned)
    return cleaned


def sync_ingredients_from_recipes():
    """S'assure que tout ingrédient déjà utilisé dans une recette existante
    figure bien dans la liste des ingrédients connus (utile lors de la
    première utilisation de cette fonctionnalité, ou après import de
    données). Lors du tout premier lancement (aucun ingredients.json), la
    liste des 1030 ingrédients courants fournis avec l'application est
    utilisée comme point de départ."""
    first_run = not os.path.exists(INGREDIENTS_FILE)
    known = load_default_ingredients() if first_run else load_ingredients()
    if _corruption_key(INGREDIENTS_FILE) in _CORRUPTED_DATA_FILES:
        return load_default_ingredients()
    known_lower = {i.lower() for i in known}
    changed = first_run
    for recipe in load_recipes():
        for ing in recipe.get("ingredients", []):
            name = ing.get("name", "").strip()
            if name and name.lower() not in known_lower:
                known.append(name)
                known_lower.add(name.lower())
                changed = True
    if changed:
        return save_ingredients(known)
    return known


def merge_default_ingredients():
    """Ajoute à la liste actuelle les ingrédients courants fournis avec
    l'application qui ne seraient pas déjà présents. Retourne le nombre
    d'ingrédients réellement ajoutés."""
    current = load_ingredients()
    current_lower = {i.lower() for i in current}
    defaults = load_default_ingredients()
    added = 0
    for name in defaults:
        if name.lower() not in current_lower:
            current.append(name)
            current_lower.add(name.lower())
            added += 1
    save_ingredients(current)
    return added


def rename_ingredient_everywhere(old_name, new_name):
    """Renomme un ingrédient dans toutes les recettes qui l'utilisent."""
    recipes = load_recipes()
    changed = False
    for recipe in recipes:
        for ing in recipe.get("ingredients", []):
            if ing.get("name", "").strip().lower() == old_name.strip().lower():
                ing["name"] = new_name
                changed = True
    if changed:
        save_recipes(recipes)


def count_ingredient_usage(name):
    """Compte le nombre de recettes utilisant cet ingrédient."""
    count = 0
    for recipe in load_recipes():
        for ing in recipe.get("ingredients", []):
            if ing.get("name", "").strip().lower() == name.strip().lower():
                count += 1
                break
    return count


# ---------------------------------------------------------------------------
# Estimation du coût d'une recette : les prix sont renseignés par
# l'utilisateur (aucune source de prix en ligne n'est disponible/fiable pour
# une application locale), un ingrédient par un, dans "Gérer les prix".
# ---------------------------------------------------------------------------

PRICE_UNIT_OPTIONS = ["kg", "L", "pièce", "cuillère à soupe", "cuillère à café"]


def load_ingredient_prices():
    """Retourne {nom_ingredient_en_minuscules: {"name":, "price":, "unit":}}."""
    return _read_user_json(INGREDIENT_PRICES_FILE, dict, {}, label="ingredient_prices")


def save_ingredient_prices(prices):
    _atomic_write_json(INGREDIENT_PRICES_FILE, prices)


def get_ingredient_price(name):
    return load_ingredient_prices().get(name.strip().lower())


def set_ingredient_price(name, price, unit):
    """price=None efface le prix enregistré pour cet ingrédient."""
    prices = load_ingredient_prices()
    key = name.strip().lower()
    if price is None:
        prices.pop(key, None)
    else:
        prices[key] = {"name": name.strip(), "price": price, "unit": unit}
    save_ingredient_prices(prices)


def _ingredient_cost_contribution(name, quantity, unit, prices):
    """Contribution au coût total pour une quantité ABSOLUE déjà mise à
    l'échelle (pas par personne) d'un ingrédient, ou None si son prix est
    inconnu ou son unité incompatible avec celle du prix enregistré.

    Les unités compatibles sont converties correctement : g/kg et ml/cl/L.
    Les unités discrètes (pièce, cuillères...) restent comparées exactement.
    Partagé par compute_recipe_cost (quantités par personne mises à
    l'échelle par l'appelant) et compute_cart_cost (quantités déjà
    absolues, sommées entre recettes sur la liste de courses)."""
    price_info = prices.get(str(name).strip().lower())
    if not price_info:
        return None
    try:
        qty = float(quantity)
        price = float(price_info.get("price", 0))
    except (TypeError, ValueError):
        return None
    ing_unit = str(unit or "").strip()
    price_unit = str(price_info.get("unit", "")).strip()

    # Prix au kg / litre : conversion via la base commune.
    if price_unit.lower() == "kg":
        converted = unit_dimension_value(qty, ing_unit)
        if converted and converted[0] == "mass":
            return (converted[1] / 1000.0) * price
        return None
    if price_unit.lower() in ("l", "litre", "litres"):
        converted = unit_dimension_value(qty, ing_unit)
        if converted and converted[0] == "volume":
            return (converted[1] / 1000.0) * price
        return None
    if canonical_unit(price_unit) == canonical_unit(ing_unit):
        return qty * price
    return None


def compute_recipe_cost(recipe, persons):
    """Retourne (coût_total_estimé, connus, total)."""
    prices = load_ingredient_prices()
    total = 0.0
    known = 0
    total_count = len(recipe.get("ingredients", []))
    try:
        persons = parse_positive_number(persons)
    except (ValueError, TypeError):
        return 0.0, 0, total_count

    for ing in recipe.get("ingredients", []):
        try:
            qty = float(ing.get("quantity", 0)) * persons
        except (TypeError, ValueError):
            continue
        contribution = _ingredient_cost_contribution(ing.get("name", ""), qty, ing.get("unit", ""), prices)
        if contribution is not None:
            total += contribution
            known += 1
    return total, known, total_count


def compute_cart_cost(items):
    """Retourne (coût_total_estimé, connus, total) pour une liste de
    courses à plat [{'name','quantity','unit',...}, ...] (quantités déjà
    absolues, contrairement à compute_recipe_cost qui part de quantités
    par personne)."""
    prices = load_ingredient_prices()
    total = 0.0
    known = 0
    for item in items:
        contribution = _ingredient_cost_contribution(
            item.get("name", ""), item.get("quantity", 0), item.get("unit", ""), prices
        )
        if contribution is not None:
            total += contribution
            known += 1
    return total, known, len(items)


def _cart_items_sorted_by_name(items):
    """Indices de items triés par nom d'ingrédient, à plat (sans regroupement
    par rayon) — utilisé par le tri « Nom » des listes de courses affichées."""
    return sorted(range(len(items)), key=lambda i: ingredient_sort_key(items[i]["name"]))


def _render_cart_cost_summary(parent, items):
    """Ajoute, si au moins un ingrédient de la liste a un prix connu, une
    ligne « Coût estimé » à parent. Partagé par les trois fenêtres qui
    affichent une liste de courses calculée (Toutes les recettes, Planning
    de la semaine, Nouveau menu)."""
    cost, cost_known, cost_total = compute_cart_cost(items)
    if not cost_known:
        return
    partial = "" if cost_known == cost_total else t("onerecipe_cost_partial", known=cost_known, total=cost_total)
    ttk.Label(
        parent, text=t("onerecipe_cost_label", cost=f"{cost:.2f}", partial=partial),
        font=("Segoe UI", sf(9), "bold"), foreground=COLOR_ACCENT_DARK
    ).pack(anchor="w", pady=(0, 4))


def _render_cart_sort_toggle(parent, sort_var, on_change):
    """Petit sélecteur « Trier : Rayon / Nom » pour une liste de courses
    affichée. Partagé par les trois fenêtres concernées (voir
    _render_cart_cost_summary)."""
    frame = ttk.Frame(parent)
    frame.pack(anchor="w", pady=(0, 8))
    ttk.Label(frame, text=t("common_sort_by_label")).pack(side="left", padx=(0, 6))
    ttk.Radiobutton(
        frame, text=t("pantry_col_section"), value="rayon", variable=sort_var, command=on_change
    ).pack(side="left")
    ttk.Radiobutton(
        frame, text=t("pantry_sort_name"), value="nom", variable=sort_var, command=on_change
    ).pack(side="left", padx=(8, 0))


# ---------------------------------------------------------------------------
# Estimation des valeurs nutritionnelles d'une recette, à partir d'une base
# de valeurs typiques par ingrédient (kcal / protéines / glucides / lipides
# pour 100 g ou 100 ml), fournie avec l'application.
# ---------------------------------------------------------------------------

_nutrition_cache = None

# Équivalence approximative de chaque unité de recette vers des grammes (ou
# millilitres, assimilés à des grammes pour les liquides — approximation
# standard). Les unités "pièce" et "autre" ne sont pas converties : le poids
# d'une "pièce" dépend trop de l'ingrédient pour être généralisé.
UNIT_TO_GRAMS = {
    "gr": 1.0, "g": 1.0, "gramme": 1.0, "grammes": 1.0,
    "kilo": 1000.0, "kg": 1000.0, "kilogramme": 1000.0, "kilogrammes": 1000.0,
    "ml": 1.0, "millilitre": 1.0, "millilitres": 1.0,
    "cl": 10.0, "centilitre": 10.0, "centilitres": 10.0,
    "litre": 1000.0, "litres": 1000.0, "l": 1000.0,
    "cuillère à soupe": 15.0,
    "cuillère à café": 5.0,
}

# Conversion dimensionnelle utilisée pour les courses, le garde-manger et les prix.
# Masse => grammes, volume => millilitres. Les unités non convertibles restent exactes.
UNIT_DIMENSIONS = {
    "gr": ("mass", 1.0), "g": ("mass", 1.0), "gramme": ("mass", 1.0), "grammes": ("mass", 1.0),
    "kilo": ("mass", 1000.0), "kg": ("mass", 1000.0), "kilogramme": ("mass", 1000.0), "kilogrammes": ("mass", 1000.0),
    "ml": ("volume", 1.0), "millilitre": ("volume", 1.0), "millilitres": ("volume", 1.0),
    "cl": ("volume", 10.0), "centilitre": ("volume", 10.0), "centilitres": ("volume", 10.0),
    "l": ("volume", 1000.0), "litre": ("volume", 1000.0), "litres": ("volume", 1000.0),
}

UNIT_CANONICAL_ALIASES = {
    "g": "gr", "gr": "gr", "gramme": "gr", "grammes": "gr",
    "kg": "kg", "kilo": "kg", "kilos": "kg", "kilogramme": "kg", "kilogrammes": "kg",
    "ml": "ml", "millilitre": "ml", "millilitres": "ml",
    "cl": "cl", "centilitre": "cl", "centilitres": "cl",
    "l": "l", "litre": "l", "litres": "l",
    "piece": "pièce", "pieces": "pièce", "pièce": "pièce", "pièces": "pièce",
    "cuillere a soupe": "cuillère à soupe", "cuillère à soupe": "cuillère à soupe",
    "cuilleres a soupe": "cuillère à soupe", "cuillères à soupe": "cuillère à soupe",
    "cas": "cuillère à soupe", "c.a.s": "cuillère à soupe", "c. à soupe": "cuillère à soupe",
    "c à s": "cuillère à soupe", "c. à s": "cuillère à soupe", "c a s": "cuillère à soupe",
    "cuillere a cafe": "cuillère à café", "cuillère à café": "cuillère à café",
    "cuilleres a cafe": "cuillère à café", "cuillères à café": "cuillère à café",
    "cac": "cuillère à café", "c. à café": "cuillère à café",
    "au gout": "au goût", "au goût": "au goût",
}


def canonical_unit(unit):
    """Nom canonique d'une unité pour tous les moteurs de calcul."""
    raw = str(unit or "").strip()
    if not raw:
        return ""
    key = ingredient_sort_key(raw)
    # ingredient_sort_key retire les accents/casse ; compare donc aussi les alias normalisés.
    for alias, canonical in UNIT_CANONICAL_ALIASES.items():
        if ingredient_sort_key(alias) == key:
            return canonical
    return raw.lower()



def unit_dimension_value(quantity, unit):
    info = UNIT_DIMENSIONS.get(canonical_unit(unit))
    if info is None:
        return None
    try:
        return info[0], float(quantity) * info[1]
    except (TypeError, ValueError):
        return None


def compatible_unit_quantities(quantity_a, unit_a, quantity_b, unit_b):
    """Retourne les quantités dans une base commune si les unités sont compatibles."""
    a = unit_dimension_value(quantity_a, unit_a)
    b = unit_dimension_value(quantity_b, unit_b)
    if a is None or b is None or a[0] != b[0]:
        return None
    return a[0], a[1], b[1]


PANTRY_FILE = os.path.join(DATA_DIR, "pantry.json")


def load_pantry():
    """Charge le garde-manger : dict {clé normalisée: {"name","quantity","unit"}}."""
    return _read_user_json(PANTRY_FILE, dict, {}, label="pantry")


def save_pantry(pantry):
    _atomic_write_json(PANTRY_FILE, pantry)


def set_pantry_item(name, quantity, unit, threshold=None, expiration_date=None):
    pantry = load_pantry()
    pantry[ingredient_sort_key(name)] = {
        "name": name,
        "quantity": quantity,
        "unit": unit,
        "threshold": threshold,
        "expiration_date": expiration_date or None,
    }
    save_pantry(pantry)
    return pantry


def parse_pantry_expiration(value):
    """Retourne une date pour les formats YYYY-MM-DD ou JJ/MM/AAAA."""
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def get_expiring_pantry_items(days=5, include_expired=True):
    """Articles arrivant à expiration dans ``days`` jours (ou déjà expirés)."""
    today = datetime.now().date()
    result = []
    for entry in load_pantry().values():
        expiry = parse_pantry_expiration(entry.get("expiration_date"))
        if expiry is None:
            continue
        delta = (expiry - today).days
        if (include_expired and delta < 0) or 0 <= delta <= days:
            item = dict(entry)
            item["_days_to_expiry"] = delta
            result.append(item)
    return sorted(result, key=lambda e: (e.get("_days_to_expiry", 99999), ingredient_sort_key(e.get("name", ""))))


def missing_recipe_ingredients(recipe, pantry_keys):
    """Noms des ingrédients d'une recette absents du garde-manger.
    ``pantry_keys`` doit être l'ensemble des clés (ingredient_sort_key) déjà
    présentes dans load_pantry() — à calculer une seule fois par appelant
    plutôt qu'à chaque recette."""
    return [
        ing.get("name", "") for ing in recipe.get("ingredients", [])
        if ingredient_sort_key(ing.get("name", "")) not in pantry_keys
    ]


def get_low_stock_pantry_items():
    """Retourne les articles du garde-manger dont la quantité est passée
    sous le seuil d'alerte défini par l'utilisateur (uniquement ceux où un
    seuil a été renseigné)."""
    pantry = load_pantry()
    return [
        entry for entry in pantry.values()
        if entry.get("threshold") is not None and entry.get("quantity", 0) < entry["threshold"]
    ]


def remove_pantry_item(name):
    pantry = load_pantry()
    pantry.pop(ingredient_sort_key(name), None)
    save_pantry(pantry)
    return pantry




def pantry_stock_status(ingredient_name, needed_qty, needed_unit, pantry):
    entry = pantry.get(ingredient_sort_key(ingredient_name))
    if entry is None:
        return "absent"
    try:
        have_qty = float(entry.get("quantity", 0))
        needed_qty = float(needed_qty)
    except (TypeError, ValueError):
        return "inconnu"
    have_unit = entry.get("unit", "")
    if str(have_unit).strip().lower() == str(needed_unit or "").strip().lower():
        return "suffisant" if have_qty >= needed_qty else "insuffisant"
    converted = compatible_unit_quantities(have_qty, have_unit, needed_qty, needed_unit)
    if converted is None:
        return "inconnu"
    _, have_base, needed_base = converted
    return "suffisant" if have_base >= needed_base else "insuffisant"


def decrement_pantry_for_recipe(recipe, persons):
    """Décompte exactement ``quantité par personne × personnes`` du garde-manger."""
    try:
        persons = parse_positive_number(persons)
    except (ValueError, TypeError):
        return 0
    pantry = load_pantry()
    decremented = 0
    for ing in recipe.get("ingredients", []):
        key = ingredient_sort_key(ing.get("name", ""))
        entry = pantry.get(key)
        if entry is None:
            continue
        try:
            needed_qty = float(ing.get("quantity", 0)) * persons
            have_qty = float(entry.get("quantity", 0))
        except (TypeError, ValueError):
            continue
        have_unit = entry.get("unit", "")
        needed_unit = ing.get("unit", "")
        if str(have_unit).strip().lower() == str(needed_unit).strip().lower():
            entry["quantity"] = max(0.0, have_qty - needed_qty)
            decremented += 1
            continue
        converted = compatible_unit_quantities(have_qty, have_unit, needed_qty, needed_unit)
        if converted is None:
            continue
        family, have_base, needed_base = converted
        remaining_base = max(0.0, have_base - needed_base)
        factor = UNIT_DIMENSIONS.get(canonical_unit(have_unit), (None, 1.0))[1]
        entry["quantity"] = remaining_base / factor if factor else remaining_base
        decremented += 1
    if decremented:
        save_pantry(pantry)
    return decremented


def load_nutrition_data():
    """Charge (une seule fois, en cache) la base de valeurs nutritionnelles
    fournie avec l'application."""
    global _nutrition_cache
    if _nutrition_cache is not None:
        return _nutrition_cache
    data = {}
    if os.path.exists(NUTRITION_DATA_FILE):
        try:
            with open(NUTRITION_DATA_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
                if isinstance(raw, dict):
                    data = {k.strip().lower(): v for k, v in raw.items()}
        except Exception as exc:
            log_internal_error("load_nutrition_data", exc)
            data = {}
    _nutrition_cache = data
    return _nutrition_cache


def _lookup_ingredient_data(data, name):
    """Exact lookup, then unique spelling normalization (never fuzzy matching)."""
    key = str(name or '').strip().lower()
    if key in data:
        return data[key]
    def normalized(value):
        return ' '.join(ingredient_sort_key(value).replace('’', "'").split())
    target = normalized(key)
    matches = [value for stored, value in data.items() if normalized(stored) == target]
    return matches[0] if len(matches) == 1 else None


def get_ingredient_nutrition(name):
    """Retourne le dict nutrition {kcal, protein_g, carbs_g, fat_g} pour un
    ingrédient (pour 100 g/100 ml), ou None si inconnu. Une surcharge
    personnelle est prioritaire sur la base fournie."""
    override = get_ingredient_override(name)
    if override and "nutrition" in override and override["nutrition"]:
        return override["nutrition"]
    return _lookup_ingredient_data(load_nutrition_data(), name)


def compute_recipe_nutrition(recipe, persons):
    """Retourne les totaux nutritionnels pour un nombre positif de personnes."""
    totals = {"kcal": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0}
    try:
        persons = parse_positive_number(persons)
    except (ValueError, TypeError):
        return totals, 0, len(recipe.get("ingredients", []))
    converted = 0
    total_count = len(recipe["ingredients"])
    for ing in recipe["ingredients"]:
        nutri = get_ingredient_nutrition(ing["name"])
        if not nutri or not all(
            isinstance(nutri.get(key), (int, float))
            and not isinstance(nutri.get(key), bool)
            and math.isfinite(nutri[key]) and nutri[key] >= 0
            for key in totals
        ):
            continue
        grams_per_unit = UNIT_TO_GRAMS.get(ing["unit"].strip().lower())
        if grams_per_unit is None:
            continue
        quantity = ing.get("quantity")
        if quantity is None:
            # Une quantité inconnue ne peut pas contribuer à une estimation
            # nutritionnelle, mais l'ingrédient reste compté dans le total
            # afin d'indiquer que l'estimation est partielle.
            continue
        grams = quantity * persons * grams_per_unit
        factor = grams / 100.0
        totals["kcal"] += nutri.get("kcal", 0) * factor
        totals["protein_g"] += nutri.get("protein_g", 0) * factor
        totals["carbs_g"] += nutri.get("carbs_g", 0) * factor
        totals["fat_g"] += nutri.get("fat_g", 0) * factor
        converted += 1
    return totals, converted, total_count


# ---------------------------------------------------------------------------
# Allergènes présents dans chaque ingrédient, à partir d'une base fournie
# avec l'application (les 1030 ingrédients courants). Sert à détecter
# automatiquement les allergènes d'une recette à partir de ses ingrédients.
# ---------------------------------------------------------------------------

_ingredient_allergens_cache = None


def load_ingredient_allergens():
    """Charge (une seule fois, en cache) la base des allergènes par
    ingrédient fournie avec l'application."""
    global _ingredient_allergens_cache
    if _ingredient_allergens_cache is not None:
        return _ingredient_allergens_cache
    data = {}
    if os.path.exists(INGREDIENT_ALLERGENS_FILE):
        try:
            with open(INGREDIENT_ALLERGENS_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
                if isinstance(raw, dict):
                    data = {k.strip().lower(): v for k, v in raw.items()}
        except Exception as exc:
            log_internal_error("load_ingredient_allergens", exc)
            data = {}
    _ingredient_allergens_cache = data
    return _ingredient_allergens_cache


# ---------------------------------------------------------------------------
# Surcharges personnelles par ingrédient (allergènes et/ou valeurs
# nutritionnelles modifiés par l'utilisateur, ou définis pour un ingrédient
# créé par lui). Prioritaires sur les bases fournies avec l'application.
# ---------------------------------------------------------------------------

def load_ingredient_overrides():
    return _read_user_json(INGREDIENT_OVERRIDES_FILE, dict, {}, label="ingredient_overrides")


def save_ingredient_overrides(overrides):
    _atomic_write_json(INGREDIENT_OVERRIDES_FILE, overrides)


def get_ingredient_override(name):
    return _lookup_ingredient_data(load_ingredient_overrides(), name)


def set_ingredient_override(name, allergens=None, nutrition=None, substitutions=None):
    """allergens : liste (peut être vide) ou None pour ne pas y toucher.
    nutrition : dict {kcal, protein_g, carbs_g, fat_g} ou None pour ne pas
    y toucher (passer un dict vide {} pour effacer la surcharge nutrition).
    substitutions : liste de {"nom","note"} ou None pour ne pas y toucher
    (passer une liste vide [] pour effacer la surcharge et revenir à la
    base de substitutions fournie avec l'application, s'il y en a une)."""
    overrides = load_ingredient_overrides()
    key = name.strip().lower()
    entry = overrides.get(key, {})
    if allergens is not None:
        entry["allergens"] = allergens
    if nutrition is not None:
        entry["nutrition"] = nutrition
    if substitutions is not None:
        entry["substitutions"] = substitutions
    if entry:
        overrides[key] = entry
    else:
        overrides.pop(key, None)
    save_ingredient_overrides(overrides)


def rename_ingredient_override(old_name, new_name):
    """Transfère une éventuelle surcharge de l'ancien nom vers le nouveau,
    lors d'un renommage d'ingrédient."""
    overrides = load_ingredient_overrides()
    old_key = old_name.strip().lower()
    new_key = new_name.strip().lower()
    if old_key in overrides and old_key != new_key:
        overrides[new_key] = overrides.pop(old_key)
        save_ingredient_overrides(overrides)


_default_substitutions_cache = None


def load_default_substitutions():
    """Charge (une seule fois, en cache) la base de substitutions courantes
    fournie avec l'application."""
    global _default_substitutions_cache
    if _default_substitutions_cache is not None:
        return _default_substitutions_cache
    data = {}
    if os.path.exists(INGREDIENT_SUBSTITUTIONS_FILE):
        try:
            with open(INGREDIENT_SUBSTITUTIONS_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
                if isinstance(raw, dict):
                    data = {k.strip().lower(): v for k, v in raw.items()}
        except Exception as exc:
            log_internal_error("load_default_substitutions", exc)
            data = {}
    _default_substitutions_cache = data
    return _default_substitutions_cache


_ingredient_translations_cache = {}


def load_ingredient_translations(lang):
    """Charge (une seule fois par langue, en cache) le dictionnaire de
    correspondance des 1030 ingrédients courants vers la langue donnée,
    fourni avec l'application. Un ingrédient absent de ce dictionnaire
    (par exemple un ingrédient personnalisé ajouté par l'utilisateur)
    n'a simplement pas de traduction : voir translate_ingredient_name()."""
    if lang in _ingredient_translations_cache:
        return _ingredient_translations_cache[lang]
    data = {}
    file_path = INGREDIENT_TRANSLATIONS_FILES.get(lang)
    if file_path and os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
                if isinstance(raw, dict):
                    data = {k.strip().lower(): v for k, v in raw.items()}
        except Exception as exc:
            log_internal_error("load_ingredient_translations", exc)
            data = {}
    _ingredient_translations_cache[lang] = data
    return data


def translate_ingredient_name(name):
    """Retourne le nom d'affichage d'un ingrédient dans la langue
    actuellement sélectionnée. La donnée réelle (recherche, tri,
    comparaison, clé de stockage des allergènes/prix/substituts...) reste
    TOUJOURS le nom français d'origine, quelle que soit la langue de
    l'interface : cette fonction ne change que ce qui est affiché à
    l'écran, jamais ce qui est enregistré ou comparé en interne. Un
    ingrédient personnalisé sans traduction connue s'affiche simplement
    dans son nom français d'origine, comme le reste de l'interface pas
    encore traduite."""
    if not name:
        return name
    if CURRENT_LANGUAGE == "fr":
        return name
    translations = load_ingredient_translations(CURRENT_LANGUAGE)
    translated = _lookup_ingredient_data(translations, name)
    return translated if translated else name


_ingredient_reverse_translations_cache = {}


def load_ingredient_reverse_translations(lang):
    """Construit (une seule fois par langue, en cache) la correspondance
    inverse vers le français, à partir du dictionnaire de traduction de
    la langue donnée. Certains noms traduits correspondent à plusieurs
    ingrédients français distincts (ex. « peanut » pour « Arachide » et
    « Cacahuète ») : dans ce cas, le nom français le plus court est
    choisi par convention (à égalité, ordre alphabétique), comme candidat
    le plus généraliste — une approximation raisonnable plutôt qu'une
    ambiguïté bloquante."""
    if lang in _ingredient_reverse_translations_cache:
        return _ingredient_reverse_translations_cache[lang]
    forward = load_ingredient_translations(lang)
    grouped = {}
    for fr_lower, translated_name in forward.items():
        grouped.setdefault(translated_name.strip().lower(), []).append(fr_lower)
    reverse = {}
    for translated_lower, fr_list in grouped.items():
        fr_list.sort(key=lambda s: (len(s), s))
        reverse[translated_lower] = fr_list[0]
    _ingredient_reverse_translations_cache[lang] = reverse
    return reverse


def resolve_ingredient_input(typed_name, ingredient_names):
    """Résout un nom d'ingrédient tapé par l'utilisateur vers son nom
    canonique français exact (tel qu'il apparaît dans ingredient_names),
    quelle que soit la langue dans laquelle il a été tapé. Essaie d'abord
    une correspondance directe (le français reste toujours la langue de
    référence des données), puis, si l'interface n'est pas en français,
    une correspondance via le dictionnaire de traduction inverse de la
    langue courante. Retourne None si rien ne correspond, exactement
    comme l'ancienne logique de correspondance stricte au nom français."""
    if not typed_name:
        return None
    typed_key = ingredient_sort_key(typed_name.strip())
    if not typed_key:
        return None
    # Même comparaison normalisée que pour les recherches : accents, casse et
    # ligatures œ/oe ne doivent jamais transformer un ingrédient connu en
    # « ingrédient inconnu » (ex. Œufs provenant d'un site Web vs Oeufs en base).
    for n in ingredient_names:
        if ingredient_sort_key(n.strip()) == typed_key:
            return n
    if CURRENT_LANGUAGE != "fr":
        reverse = load_ingredient_reverse_translations(CURRENT_LANGUAGE)
        fr_key = reverse.get(typed_name.strip().lower())
        if not fr_key:
            # Les fichiers de traduction peuvent eux aussi contenir œ/oe ou
            # des variantes accentuées : seconde passe normalisée.
            for translated, canonical in reverse.items():
                if ingredient_sort_key(translated) == typed_key:
                    fr_key = canonical
                    break
        if fr_key:
            fr_norm = ingredient_sort_key(fr_key)
            for n in ingredient_names:
                if ingredient_sort_key(n.strip()) == fr_norm:
                    return n
    return None


def get_display_ingredient_values(ingredient_names):
    """Retourne la liste des noms d'ingrédients à proposer dans un champ
    de saisie, une liste déroulante ou un filtre, dans la langue
    actuellement sélectionnée (traduits quand une traduction est connue,
    sinon inchangés). Utilisé pour l'autocomplétion : le nom RÉELLEMENT
    sélectionné ou tapé doit ensuite toujours être résolu via
    resolve_ingredient_input() avant d'être enregistré."""
    if CURRENT_LANGUAGE == "fr":
        return list(ingredient_names)
    return [translate_ingredient_name(n) for n in ingredient_names]


def get_ingredient_substitutions(name):
    """Retourne la liste de substituts connus pour un ingrédient (une
    surcharge personnelle, si vous en avez défini une, est toujours
    prioritaire sur la base fournie avec l'application), ou une liste vide
    si aucun substitut n'est connu. Toujours en français : c'est la
    donnée de référence, utilisée pour toute comparaison ou correspondance
    interne (voir get_display_ingredient_substitutions() pour un
    affichage traduit)."""
    key = name.strip().lower()
    override = load_ingredient_overrides().get(key)
    if override is not None and "substitutions" in override:
        return override["substitutions"]
    return load_default_substitutions().get(key, [])


_default_substitutions_translations_cache = {}


def load_default_substitutions_translated(lang):
    """Charge (une seule fois par langue, en cache) la traduction de la
    base de substitutions courante fournie avec l'application, dans la
    langue donnée."""
    if lang in _default_substitutions_translations_cache:
        return _default_substitutions_translations_cache[lang]
    data = {}
    file_path = INGREDIENT_SUBSTITUTIONS_TRANSLATION_FILES.get(lang)
    if file_path and os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
                if isinstance(raw, dict):
                    data = {k.strip().lower(): v for k, v in raw.items()}
        except Exception as exc:
            log_internal_error("load_default_substitutions_translated", exc)
            data = {}
    _default_substitutions_translations_cache[lang] = data
    return data


def get_display_ingredient_substitutions(name):
    """Retourne la liste de substituts connus pour un ingrédient, dans la
    langue actuellement sélectionnée, pour AFFICHAGE uniquement — ne
    jamais utiliser cette fonction pour une comparaison ou une
    correspondance interne (utiliser get_ingredient_substitutions() dans
    ce cas, qui reste toujours en français). Une surcharge personnelle
    (substituts que vous avez vous-même ajoutés ou modifiés) est toujours
    utilisée telle quelle, jamais traduite automatiquement, puisqu'elle a
    été tapée par vous dans la langue de votre choix."""
    key = name.strip().lower()
    override = load_ingredient_overrides().get(key)
    if override is not None and "substitutions" in override:
        return override["substitutions"]
    if CURRENT_LANGUAGE != "fr":
        translated = load_default_substitutions_translated(CURRENT_LANGUAGE).get(key)
        if translated is not None:
            return translated
    return load_default_substitutions().get(key, [])


def has_known_substitutions():
    """Ensemble des clés normalisées de tous les ingrédients ayant au moins
    un substitut connu (base fournie ou surcharge personnelle)."""
    keys = set(load_default_substitutions().keys())
    overrides = load_ingredient_overrides()
    for key, entry in overrides.items():
        if entry.get("substitutions"):
            keys.add(key)
        elif "substitutions" in entry and not entry["substitutions"]:
            keys.discard(key)  # surcharge vide = substituts explicitement effacés
    return keys


def revert_ingredient_substitutions_to_default(name):
    """Retire complètement la surcharge de substituts d'un ingrédient (sans
    toucher à ses éventuelles surcharges d'allergènes/nutrition), pour
    revenir à ce que propose la base fournie avec l'application — à ne pas
    confondre avec le fait d'enregistrer une liste vide, qui bloquerait au
    contraire tout substitut pour cet ingrédient."""
    overrides = load_ingredient_overrides()
    key = name.strip().lower()
    if key in overrides and "substitutions" in overrides[key]:
        del overrides[key]["substitutions"]
        if not overrides[key]:
            overrides.pop(key)
        save_ingredient_overrides(overrides)


def get_ingredient_allergens(name):
    """Retourne la liste des allergènes connus pour un ingrédient donné
    (liste vide si l'ingrédient n'est pas reconnu ou n'en contient aucun).
    Une surcharge personnelle est prioritaire sur la base fournie."""
    override = get_ingredient_override(name)
    if override and "allergens" in override:
        return override["allergens"]
    data = load_ingredient_allergens()
    found = _lookup_ingredient_data(data, name)
    if found is not None:
        return found
    # Only spelling/plural variants, never approximate food substitutions.
    key = ingredient_sort_key(name).replace('œ', 'oe')
    matches = [value for stored, value in data.items()
               if ingredient_sort_key(stored).replace('œ', 'oe').rstrip('s') == key.rstrip('s')]
    if matches and all(value == matches[0] for value in matches):
        return matches[0]
    translated = _url_food_name(name)
    base = _allergen_food_name(translated)
    if ingredient_sort_key(base) != ingredient_sort_key(name):
        return get_ingredient_allergens(base)
    return []


def _allergen_food_name(name):
    """Recognize preparation details without removing dietary qualifiers."""
    key = ingredient_sort_key(name).replace('œ', 'oe')
    if re.search(r"\b(?:sans|free|sin|ohne|frei|vegan|vegetal|vegetalien|substitut|remplac)\w*\b", key):
        return name
    base = re.split(r'\s+—\s+', key, maxsplit=1)[0]
    while re.search(r"\([^()]*\)", base):
        base = re.sub(r"\([^()]*\)", '', base)
    base = re.split(r"\s+ou\s+", base, maxsplit=1)[0].strip(' ,')
    base = re.sub(r"(?:\s*,?\s+(?:fondu[es]*|rape[es]*|tamise[es]*|battu[es]*|hache[es]*|concasse[es]*|entier[es]*|frais|fraiche[es]*|bio|legerement|tiede[es]*))+$", '', base)
    base = re.sub(r"\s+", ' ', base).strip(' ,')
    return {'farine de ble': 'Farine', 'fromage frais': 'Fromage', 'creme aigre': 'Crème fraîche'}.get(base, base)


def compute_recipe_allergens(ingredients):
    """Retourne l'ensemble des allergènes détectés à partir d'une liste
    d'ingrédients de recette, dans l'ordre de la liste ALLERGENS."""
    detected = set()
    for ing in ingredients:
        detected.update(get_ingredient_allergens(ing["name"]))
    return [a for a in ALLERGENS if a in detected]


def find_similar_ingredient_pairs(names, threshold=0.82):
    """Retourne une liste de paires (nom_a, nom_b, score) d'ingrédients dont
    les noms se ressemblent fortement (accents/casse ignorés), pouvant
    indiquer un doublon ou une faute de frappe (ex. "Tomate" / "Tomates",
    "Echalotte" / "Échalote"). Les ingrédients sont d'abord regroupés par
    leurs deux premières lettres pour limiter le nombre de comparaisons sur
    de grandes listes."""
    normalized = [(n, ingredient_sort_key(n)) for n in names]
    buckets = {}
    for name, key in normalized:
        prefix = key[:2] if len(key) >= 2 else key
        buckets.setdefault(prefix, []).append((name, key))

    pairs = []
    for bucket in buckets.values():
        for i in range(len(bucket)):
            name_a, key_a = bucket[i]
            for j in range(i + 1, len(bucket)):
                name_b, key_b = bucket[j]
                if key_a == key_b:
                    continue
                is_plural_variant = (
                    key_a in (key_b + "s", key_b + "x") or key_b in (key_a + "s", key_a + "x")
                )
                ratio = difflib.SequenceMatcher(None, key_a, key_b).ratio()
                if is_plural_variant or ratio >= threshold:
                    pairs.append((name_a, name_b, ratio if not is_plural_variant else max(ratio, 0.9)))

    pairs.sort(key=lambda t: -t[2])
    return pairs


DISMISSED_DUPLICATE_PAIRS_FILE = os.path.join(DATA_DIR, "ingredient_dismissed_pairs.json")


def load_dismissed_pairs():
    """Retourne l'ensemble des paires d'ingrédients que l'utilisateur a
    explicitement indiquées comme n'étant PAS des doublons, pour ne plus les
    proposer lors des prochaines analyses. Chaque paire est représentée par
    un tuple trié de deux clés normalisées, indépendant de l'ordre."""
    raw = _read_user_json(DISMISSED_DUPLICATE_PAIRS_FILE, list, [], label="dismissed_pairs")
    return {
        tuple(sorted(pair)) for pair in raw
        if isinstance(pair, list) and len(pair) == 2
    }


def save_dismissed_pairs(pairs_set):
    _atomic_write_json(DISMISSED_DUPLICATE_PAIRS_FILE, [list(pair) for pair in sorted(pairs_set)])


def add_dismissed_pair(name_a, name_b):
    pairs = load_dismissed_pairs()
    pairs.add(tuple(sorted([ingredient_sort_key(name_a), ingredient_sort_key(name_b)])))
    save_dismissed_pairs(pairs)


def is_pair_dismissed(name_a, name_b, dismissed_pairs):
    return tuple(sorted([ingredient_sort_key(name_a), ingredient_sort_key(name_b)])) in dismissed_pairs


def find_plural_duplicate(name, existing_names):
    """Retourne le nom déjà présent dans existing_names qui n'est qu'une
    variante singulier/pluriel de `name` (même règle que le vérificateur de
    doublons : suffixe "s" ou "x"), ou None si aucune correspondance. Sert à
    empêcher qu'un même ingrédient se retrouve deux fois dans la liste sous
    deux graphies différentes (ex. "Tomate" et "Tomates")."""
    key = ingredient_sort_key(name)
    for existing in existing_names:
        existing_key = ingredient_sort_key(existing)
        if existing_key == key:
            continue  # correspondance exacte : gérée séparément
        if key in (existing_key + "s", existing_key + "x") or existing_key in (key + "s", key + "x"):
            return existing
    return None


def rank_close_ingredients(name, existing_names):
    """Classe les ingrédients existants par proximité avec un nom inconnu."""
    wanted = ingredient_sort_key(name)
    wanted_words = {w for w in wanted.split() if w not in {"de", "du", "des", "d", "la", "le", "les"}}
    ranked = []
    for existing in existing_names:
        key = ingredient_sort_key(existing)
        score = difflib.SequenceMatcher(None, wanted, key).ratio()
        words = set(key.split())
        if words and words.issubset(wanted_words):
            score = max(score, 0.88)
        plural = find_plural_duplicate(name, [existing])
        if plural:
            score = max(score, 0.98)
        ranked.append((score, existing))
    ranked.sort(key=lambda item: (-item[0], ingredient_sort_key(item[1])))
    return ranked


def filter_sorted_ingredient_values(full_values, typed=""):
    """Trie les ingrédients puis réduit la liste selon le texte saisi."""
    values = sorted(dict.fromkeys(full_values), key=ingredient_sort_key)
    typed_key = ingredient_sort_key((typed or "").strip())
    if not typed_key:
        return values
    starts_with = [value for value in values if ingredient_sort_key(value).startswith(typed_key)]
    if starts_with:
        return starts_with
    return [value for value in values if typed_key in ingredient_sort_key(value)]


def cleanup_stale_import_temp(max_age_days=7):
    try:
        if not os.path.isdir(IMPORT_TEMP_DIR):
            return
        cutoff = datetime.now().timestamp() - max_age_days * 86400
        for name in os.listdir(IMPORT_TEMP_DIR):
            path = os.path.join(IMPORT_TEMP_DIR, name)
            if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                try: os.remove(path)
                except OSError: pass
    except Exception as exc:
        log_internal_error("cleanup_import_temp", exc)


def load_thumbnail_from_path(path, size=(240, 180)):
    if not path or not PIL_AVAILABLE or not os.path.isfile(path):
        return None
    try:
        with Image.open(path) as source:
            img = source.copy()
        img.thumbnail(size)
        return ImageTk.PhotoImage(img)
    except Exception as exc:
        log_internal_error("load_thumbnail_from_path", exc)
        return None


def copy_image_to_store(source_path):
    """Copie une image choisie par l'utilisateur dans le dossier images/
    et retourne le nom de fichier généré (à stocker dans la recette)."""
    ext = os.path.splitext(source_path)[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"):
        ext = ".png"
    new_filename = f"{uuid.uuid4().hex}{ext}"
    dest_path = os.path.join(IMAGES_DIR, new_filename)
    shutil.copy2(source_path, dest_path)
    return new_filename


def delete_image_file(image_filename):
    """Supprime uniquement un fichier réellement situé dans images/."""
    path = image_store_path(image_filename)
    if path and os.path.isfile(path):
        try:
            os.remove(path)
        except OSError as exc:
            log_internal_error("delete_image_file", exc)


def load_thumbnail(image_filename, size=(240, 180)):
    """Retourne un aperçu pour un nom d'image local sûr."""
    if not image_filename or not PIL_AVAILABLE:
        return None
    path = image_store_path(image_filename)
    if not path or not os.path.exists(path):
        return None
    try:
        with Image.open(path) as source:
            img = source.copy()
        img.thumbnail(size)
        return ImageTk.PhotoImage(img)
    except Exception as exc:
        log_internal_error("load_thumbnail", exc)
        return None


def get_recipe_images(recipe):
    """Photos principales de la recette (hors journal de cuisine)."""
    images = recipe.get("images") if isinstance(recipe, dict) else None
    if isinstance(images, list) and images:
        return [n for n in (safe_image_filename(x) for x in images) if n]
    legacy = safe_image_filename(recipe.get("image")) if isinstance(recipe, dict) else None
    return [legacy] if legacy else []


def get_all_recipe_image_refs(recipe):
    """Toutes les photos appartenant à une recette, journal de cuisine inclus."""
    refs = list(get_recipe_images(recipe))
    seen = set(refs)
    for entry in recipe.get("cook_log", []) if isinstance(recipe, dict) else []:
        if not isinstance(entry, dict):
            continue
        photo = safe_image_filename(entry.get("photo"))
        if photo and photo not in seen:
            refs.append(photo)
            seen.add(photo)
    return refs


def remap_recipe_image_refs(recipe, rename_map):
    if not isinstance(recipe, dict):
        return recipe
    if isinstance(recipe.get("images"), list):
        recipe["images"] = [rename_map.get(x, x) for x in recipe["images"] if safe_image_filename(rename_map.get(x, x))]
    if recipe.get("image"):
        mapped = rename_map.get(recipe["image"], recipe["image"])
        if safe_image_filename(mapped): recipe["image"] = mapped
        else: recipe.pop("image", None)
    for entry in recipe.get("cook_log", []) or []:
        if isinstance(entry, dict) and entry.get("photo"):
            mapped = rename_map.get(entry["photo"], entry["photo"])
            if safe_image_filename(mapped): entry["photo"] = mapped
            else: entry.pop("photo", None)
    return recipe


def delete_recipe_images(recipe, protected_recipes=None, protected_trash=None):
    """Supprime uniquement les images qui ne sont plus référencées ailleurs."""
    if protected_recipes is None:
        protected_recipes = load_recipes()
    if protected_trash is None:
        protected_trash = load_trash()
    protected = set()
    for other in protected_recipes or []:
        protected.update(get_all_recipe_image_refs(other))
    for entry in protected_trash or []:
        if isinstance(entry, dict):
            protected.update(get_all_recipe_image_refs(entry.get("recipe", {})))
    for fname in get_all_recipe_image_refs(recipe):
        if fname not in protected:
            delete_image_file(fname)


def duplicate_recipe_images(recipe):
    """Duplique toutes les photos et met à jour aussi les photos du journal."""
    mapping = {}
    for fname in get_all_recipe_image_refs(recipe):
        src = image_store_path(fname)
        if src and os.path.exists(src):
            mapping[fname] = copy_image_to_store(src)
    return mapping


def apply_duplicated_image_mapping(recipe, mapping):
    recipe["images"] = [mapping.get(x, x) for x in get_recipe_images(recipe) if mapping.get(x, x)]
    recipe.pop("image", None)
    for entry in recipe.get("cook_log", []) or []:
        if isinstance(entry, dict) and entry.get("photo") in mapping:
            entry["photo"] = mapping[entry["photo"]]
    return recipe


# ---------------------------------------------------------------------------
# Fonctions partagées de calcul / export de liste de courses, réutilisées par
# "Voir toutes les recettes", le planificateur de repas et les menus.
# ---------------------------------------------------------------------------

def format_quantity_with_unit(qty, unit):
    """Affichage lisible d'une quantité tout en conservant les unités compatibles."""
    unit_lower = canonical_unit(unit)
    try:
        qty = float(qty)
    except (TypeError, ValueError):
        return qty, unit
    dim = UNIT_DIMENSIONS.get(unit_lower)
    if dim:
        family, factor = dim
        base = qty * factor
        if family == "mass":
            if base >= 1000:
                qty, unit = base / 1000.0, "kg"
            else:
                qty, unit = base, "Gr"
        elif family == "volume":
            if base >= 1000:
                qty, unit = base / 1000.0, "L"
            elif base >= 10:
                qty, unit = base / 10.0, "cl"
            else:
                qty, unit = base, "ml"
    qty = round(qty, 2)
    if isinstance(qty, float) and qty == int(qty):
        qty = int(qty)
    return qty, unit


def compute_grouped_totals(recipe_persons_pairs):
    """Calcule les totaux et fusionne g/kg ainsi que ml/cl/L pour un même ingrédient."""
    totals = {}
    for recipe, persons in recipe_persons_pairs:
        try:
            persons = parse_positive_number(persons)
        except (ValueError, TypeError):
            continue
        for ing in recipe.get("ingredients", []):
            name = str(ing.get("name", "")).strip()
            unit = str(ing.get("unit", "")).strip()
            name_key = ingredient_sort_key(name)
            if ing.get("quantity") is None:
                # Conserver l'ingrédient dans la liste même si sa quantité
                # est « au goût » : il ne peut pas être additionné aux
                # quantités chiffrées, mais il ne doit pas disparaître.
                key = (name_key, "unknown:" + unit.lower())
                totals.setdefault(key, {"name": name, "qty": None, "unit": "", "family": "unknown"})
                continue
            try:
                raw_qty = float(ing.get("quantity", 0)) * persons
            except (TypeError, ValueError):
                continue
            dim = UNIT_DIMENSIONS.get(canonical_unit(unit))
            if dim:
                family, factor = dim
                key = (name_key, family)
                totals.setdefault(key, {"name": name, "qty": 0.0, "unit": "Gr" if family == "mass" else "ml", "family": family})
                totals[key]["qty"] += raw_qty * factor
            else:
                key = (name_key, "exact:" + unit.lower())
                totals.setdefault(key, {"name": name, "qty": 0.0, "unit": unit, "family": None})
                totals[key]["qty"] += raw_qty

    by_rayon = {}
    for data in totals.values():
        qty = data["qty"]
        unit = data["unit"]
        # qty est déjà en unité de base pour les dimensions reconnues.
        if data["family"] == "mass":
            display_qty, display_unit = format_quantity_with_unit(qty, "Gr")
        elif data["family"] == "volume":
            display_qty, display_unit = format_quantity_with_unit(qty, "ml")
        elif data["family"] == "unknown":
            # La valeur interne reste ``None`` ; la traduction est appliquée
            # uniquement au moment de l'affichage/export.
            display_qty, display_unit = None, ""
        else:
            display_qty, display_unit = format_quantity_with_unit(qty, unit)
        name = data["name"]
        rayon = get_ingredient_rayon(name)
        by_rayon.setdefault(rayon, []).append((name.capitalize(), display_qty, display_unit))

    grouped_totals = []
    for rayon in RAYON_ORDER:
        if rayon in by_rayon:
            items = sorted(by_rayon[rayon], key=lambda x: ingredient_sort_key(x[0]))
            grouped_totals.append((rayon, items))
    return grouped_totals


def grouped_totals_from_flat_items(items):
    """Reconvertit une liste plate d'ingrédients modifiable
    [{'name','quantity','unit','rayon'}, ...] (utilisée pour l'édition
    ligne par ligne d'une liste de courses déjà calculée) vers le même
    format que compute_grouped_totals : [(rayon, [(nom, qté, unité), ...]), ...]."""
    by_rayon = {}
    for item in items:
        by_rayon.setdefault(item["rayon"], []).append((item["name"], item["quantity"], item["unit"]))
    grouped_totals = []
    for rayon in RAYON_ORDER:
        if rayon in by_rayon:
            entries = sorted(by_rayon[rayon], key=lambda x: ingredient_sort_key(x[0]))
            grouped_totals.append((rayon, entries))
    return grouped_totals


SAVED_SHOPPING_LISTS_FILE = os.path.join(DATA_DIR, "saved_shopping_lists.json")


def load_saved_shopping_lists():
    return _read_user_json(SAVED_SHOPPING_LISTS_FILE, list, [], label="shopping_lists")


def save_saved_shopping_lists(lists):
    _atomic_write_json(SAVED_SHOPPING_LISTS_FILE, lists)


def write_shopping_list_txt(path, title, chosen_recipes, grouped_totals):
    """Écrit une liste de courses au format texte. chosen_recipes est une
    liste de (libellé_affiché, personnes)."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"=== {title} ===\n\n")
        f.write(t("shoppingexport_generated_on", date=datetime.now().strftime("%d/%m/%Y %H:%M")) + "\n\n")
        f.write(t("shoppingexport_selected_recipes") + "\n")
        for label, persons in chosen_recipes:
            f.write(f"- {label} ({persons} pers.)\n")
        for rayon, items in grouped_totals:
            f.write(f"\n{translate_rayon_name(rayon)} :\n")
            for name, qty, unit in items:
                quantity_display = t("quantity_unspecified") if qty is None else qty
                unit_display = f" {translate_unit_name(unit)}" if unit and qty is not None else ""
                f.write(f"- {translate_ingredient_name(name)} : {quantity_display}{unit_display}\n")


def build_shopping_list_workbook(chosen_recipes, grouped_totals):
    """Construit un classeur Excel (openpyxl) pour une liste de courses.
    Nécessite que OPENPYXL_AVAILABLE soit vrai."""
    wb = Workbook()
    ws_recipes = wb.active
    ws_recipes.title = t("shoppingexport_excel_sheet_recipes")
    ws_recipes.append([t("shoppingexport_excel_col_recipe"), t("shoppingexport_excel_col_persons")])
    for label, persons in chosen_recipes:
        ws_recipes.append([label, persons])

    ws_ing = wb.create_sheet(t("shoppingexport_excel_sheet_ingredients"))
    ws_ing.append([
        t("shoppingexport_excel_col_rayon"), t("shoppingexport_excel_col_ingredient"),
        t("shoppingexport_excel_col_total_qty"), t("shoppingexport_excel_col_unit")
    ])
    for rayon, items in grouped_totals:
        for name, qty, unit in items:
            quantity_display = t("quantity_unspecified") if qty is None else qty
            unit_display = "" if qty is None else unit
            ws_ing.append([translate_rayon_name(rayon), translate_ingredient_name(name), quantity_display, unit_display])
    return wb


def build_shopping_list_pdf(path, title, chosen_recipes, grouped_totals):
    c = pdf_canvas.Canvas(path, pagesize=A4)
    width, height = A4
    left, right, bottom = 2*cm, 2*cm, 2*cm
    usable = width-left-right
    y = height-2*cm

    def line(text, *, bold=False, size=10, indent=0, keep=True):
        nonlocal y
        y = _pdf_draw_wrapped(c, text, left+indent, y, usable-indent, height,
                              font_name="Helvetica-Bold" if bold else "Helvetica",
                              font_size=size, line_height=(0.55 if size>=12 else 0.46)*cm,
                              bottom=bottom, keep_together=keep)

    line(title, bold=True, size=18)
    y -= 0.25*cm
    line(t("shoppingexport_generated_on", date=datetime.now().strftime("%d/%m/%Y %H:%M")))
    y -= 0.25*cm
    line(t("shoppingexport_selected_recipes"), bold=True, size=12)
    for label, persons in chosen_recipes:
        line(f"- {label} ({persons} pers.)", indent=0.3*cm)
    for rayon, items in grouped_totals:
        y -= 0.25*cm
        line(f"{translate_rayon_name(rayon)} :", bold=True, size=12)
        for name, qty, unit in items:
            quantity_display = t("quantity_unspecified") if qty is None else qty
            unit_display = f" {translate_unit_name(unit)}" if unit and qty is not None else ""
            line(f"- {translate_ingredient_name(name)} : {quantity_display}{unit_display}", indent=0.3*cm)
    c.save()


ALLERGENS = ["Gluten", "Lactose", "Œufs", "Arachides", "Fruits à coque",
             "Soja", "Poisson", "Crustacés", "Sésame", "Céleri", "Moutarde",
             "Sulfites", "Lupin", "Mollusques"]

# Table de correspondance des allergènes par langue, sur le même principe
# que les catégories et difficultés : la donnée réelle stockée dans
# chaque recette (recipe["allergens"]) reste toujours en français — ces
# valeurs sont comparées lors de la détection automatique et des filtres
# —, cette table ne sert qu'à l'affichage. Les cases à cocher des
# allergènes sont elles aussi toujours en liste fermée, donc sans
# ambiguïté possible.
ALLERGEN_TRANSLATIONS = {
    "en": {
        "gluten": "Gluten",
        "lactose": "Milk (including lactose)",
        "œufs": "Eggs",
        "arachides": "Peanuts",
        "fruits à coque": "Tree nuts",
        "soja": "Soy",
        "poisson": "Fish",
        "crustacés": "Crustaceans",
        "sésame": "Sesame",
        "céleri": "Celery",
        "moutarde": "Mustard",
        "sulfites": "Sulphites",
        "lupin": "Lupin",
        "mollusques": "Molluscs",
    },
    "es": {
        "gluten": "Gluten",
        "lactose": "Leche (incluida la lactosa)",
        "œufs": "Huevos",
        "arachides": "Cacahuetes",
        "fruits à coque": "Frutos de cáscara",
        "soja": "Soja",
        "poisson": "Pescado",
        "crustacés": "Crustáceos",
        "sésame": "Sésamo",
        "céleri": "Apio",
        "moutarde": "Mostaza",
        "sulfites": "Sulfitos",
        "lupin": "Altramuces",
        "mollusques": "Moluscos",
    },
    "de": {
        "gluten": "Gluten",
        "lactose": "Milch (einschließlich Laktose)",
        "œufs": "Eier",
        "arachides": "Erdnüsse",
        "fruits à coque": "Schalenfrüchte",
        "soja": "Soja",
        "poisson": "Fisch",
        "crustacés": "Krebstiere",
        "sésame": "Sesam",
        "céleri": "Sellerie",
        "moutarde": "Senf",
        "sulfites": "Sulfite",
        "lupin": "Lupinen",
        "mollusques": "Weichtiere",
    },
}


def translate_allergen_name(allergen):
    """Retourne le nom d'affichage d'un allergène dans la langue
    actuellement sélectionnée. Ne change jamais la donnée réelle stockée
    dans la recette (recipe["allergens"]), utilisée pour la détection
    automatique et les comparaisons."""
    if not allergen:
        return allergen
    if CURRENT_LANGUAGE == "fr":
        # Historical storage key kept for compatibility with saved recipes.
        return "Lait (dont lactose)" if allergen.strip().lower() == "lactose" else allergen
    return ALLERGEN_TRANSLATIONS.get(CURRENT_LANGUAGE, {}).get(allergen.strip().lower(), allergen)

# Ingrédients de base qu'on a presque toujours sous la main, pré-cochés par
# défaut dans "Que puis-je cuisiner ?" (l'utilisateur reste libre de les
# retirer au cas par cas).
PANTRY_STAPLES = [
    "Sel", "Poivre", "Huile de tournesol", "Huile d'olive", "Beurre",
    "Farine", "Sucre", "Vinaigre", "Moutarde", "Riz", "Pâtes", "Lait",
]


def _pdf_font_name(name):
    mapping = {'Helvetica': ('RecipeSans', 'Vera.ttf'),
               'Helvetica-Bold': ('RecipeSansBold', 'VeraBd.ttf'),
               'Helvetica-Oblique': ('RecipeSansItalic', 'VeraIt.ttf')}
    if name not in mapping:
        return name
    registered, filename = mapping[name]
    if registered not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(registered, os.path.join(os.path.dirname(reportlab.__file__), 'fonts', filename)))
    return registered


def _pdf_wrap_lines(c, text, max_width, font_name="Helvetica", font_size=10):
    """Retourne des lignes qui tiennent toutes dans ``max_width``."""
    font_name = _pdf_font_name(font_name)
    text = _url_fraction_text(text or "")
    words = text.split()
    if not words:
        return [""]
    lines, line = [], ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if line and c.stringWidth(candidate, font_name, font_size) > max_width:
            lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)
    return lines or [""]


def _pdf_new_page(c, height):
    c.showPage()
    return height - 2 * cm


def _pdf_draw_wrapped(c, text, x, y, max_width, height, *, font_name="Helvetica",
                      font_size=10, line_height=0.48 * cm, bottom=2 * cm,
                      color=None, keep_together=False):
    text = str(text or "").replace("⚠", "").replace("\ufe0f", "").strip()
    font_name = _pdf_font_name(font_name)
    lines = _pdf_wrap_lines(c, text, max_width, font_name, font_size)
    needed = len(lines) * line_height
    page_capacity = (height - 2 * cm) - bottom
    if keep_together and needed <= page_capacity and y - needed < bottom:
        y = _pdf_new_page(c, height)
    if color is not None:
        if isinstance(color, (tuple, list)) and len(color) == 3:
            c.setFillColorRGB(*color)
        else:
            c.setFillColor(color)
    c.setFont(font_name, font_size)
    for line in lines:
        if y - line_height < bottom:
            y = _pdf_new_page(c, height)
            if color is not None:
                if isinstance(color, (tuple, list)) and len(color) == 3:
                    c.setFillColorRGB(*color)
                else:
                    c.setFillColor(color)
            c.setFont(font_name, font_size)
        c.drawString(x, y, line)
        y -= line_height
    if color is not None:
        c.setFillColorRGB(0, 0, 0)
    return y


def draw_recipe_content(c, recipe, persons, width, height):
    """Dessine une recette sans couper horizontalement les textes longs."""
    try:
        persons = parse_positive_number(persons)
    except (ValueError, TypeError):
        persons = 1
    left = 2 * cm
    right = 2 * cm
    usable = width - left - right
    y = height - 2 * cm

    star = "* " if recipe.get("favorite") else ""
    y = _pdf_draw_wrapped(c, f"{star}{recipe.get('name','')}", left, y, usable, height,
                          font_name="Helvetica-Bold", font_size=18, line_height=0.72*cm,
                          keep_together=True)
    y -= 0.15 * cm

    cat = translate_category_name(recipe.get("category", "Autre"))
    y = _pdf_draw_wrapped(c, t("recipepdf_category_persons", cat=cat, persons=persons), left, y, usable, height)

    rating = recipe.get("rating", 0)
    if rating:
        y = _pdf_draw_wrapped(c, t("recipepdf_rating", stars=rating_stars(rating)), left, y, usable, height)

    info_bits = []
    if recipe.get("prep_time"):
        info_bits.append(t("recipepdf_prep", time=recipe['prep_time']))
    if recipe.get("cook_time"):
        info_bits.append(t("recipepdf_cook", time=recipe['cook_time']))
    if recipe.get("difficulty"):
        info_bits.append(t("recipepdf_difficulty", value=translate_difficulty_name(recipe['difficulty'])))
    if info_bits:
        y = _pdf_draw_wrapped(c, "   |   ".join(info_bits), left, y, usable, height)

    allergens = recipe.get("allergens") or []
    if allergens:
        y = _pdf_draw_wrapped(
            c, t("recipepdf_allergens", list=", ".join(translate_allergen_name(a) for a in allergens)),
            left, y, usable, height, color=(0.7, 0.2, 0.2)
        )
    y -= 0.18 * cm

    images = get_recipe_images(recipe)
    if images:
        img_path = os.path.join(IMAGES_DIR, images[0])
        if os.path.exists(img_path):
            try:
                img_reader = ImageReader(img_path)
                iw, ih = img_reader.getSize()
                max_w, max_h = 8 * cm, 10 * cm
                scale = min(max_w / iw, max_h / ih)
                draw_w, draw_h = iw * scale, ih * scale
                if y - draw_h < 3 * cm:
                    y = _pdf_new_page(c, height)
                c.drawImage(img_reader, left, y - draw_h, width=draw_w, height=draw_h,
                            preserveAspectRatio=True, mask="auto")
                y -= draw_h + 0.55 * cm
            except Exception as exc:
                log_internal_error("draw_recipe_content.image", exc)

    if y < 4.5 * cm:
        y = _pdf_new_page(c, height)
    y = _pdf_draw_wrapped(c, t("recipepdf_ingredients_heading"), left, y, usable, height,
                          font_name="Helvetica-Bold", font_size=12, line_height=0.58*cm,
                          keep_together=True)
    for ing in recipe.get("ingredients", []):
        qty = ingredient_quantity_for_persons(ing, persons)
        if qty is None:
            qty = t("quantity_unspecified")
            unit = ""
        else:
            unit = f" {translate_unit_name(ing.get('unit',''))}" if ing.get("unit") else ""
        line = f"- {translate_ingredient_name(ing.get('name','')).capitalize()} : {qty}{unit}"
        y = _pdf_draw_wrapped(c, line, left + 0.3*cm, y, usable - 0.3*cm, height,
                              keep_together=True)

    cost, cost_known, cost_total = compute_recipe_cost(recipe, persons)
    nutrition, nutri_known, nutri_total = compute_recipe_nutrition(recipe, persons)
    if cost_known or nutri_known:
        y -= 0.2 * cm
        if cost_known:
            partial = "" if cost_known == cost_total else t("recipepdf_partial_suffix", known=cost_known, total=cost_total)
            y = _pdf_draw_wrapped(c, t("recipepdf_cost", cost=f"{cost:.2f}", partial=partial),
                                  left, y, usable, height, font_name="Helvetica-Oblique", font_size=9)
        if nutri_known:
            partial = "" if nutri_known == nutri_total else t("recipepdf_partial_suffix", known=nutri_known, total=nutri_total)
            nutri_text = t("recipepdf_nutrition", partial=partial,
                           kcal=f"{nutrition['kcal']:.0f}", protein=f"{nutrition['protein_g']:.0f}",
                           carbs=f"{nutrition['carbs_g']:.0f}", fat=f"{nutrition['fat_g']:.0f}")
            y = _pdf_draw_wrapped(c, nutri_text, left, y, usable, height,
                                  font_name="Helvetica-Oblique", font_size=9)
            if nutri_known < nutri_total:
                y = _pdf_draw_wrapped(c, t("nutrition_incomplete_notice"), left, y, usable, height, font_size=9)

    def draw_section(title, body, y):
        if not str(body or "").strip():
            return y
        y -= 0.28 * cm
        if y < 4 * cm:
            y = _pdf_new_page(c, height)
        y = _pdf_draw_wrapped(c, title, left, y, usable, height,
                              font_name="Helvetica-Bold", font_size=12, line_height=0.58*cm,
                              keep_together=True)
        for paragraph in str(body).split("\n"):
            y = _pdf_draw_wrapped(c, paragraph, left, y, usable, height,
                                  font_name="Helvetica", font_size=10, line_height=0.48*cm,
                                  keep_together=True)
            if paragraph.strip():
                y -= 0.07 * cm
        return y

    y = draw_section(t("recipepdf_description_heading"), recipe.get("description", ""), y)
    y = draw_section(t("recipepdf_notes_heading"), recipe.get("personal_notes", ""), y)
    return y


def build_cookbook_pdf(path, recipes_with_persons):
    """Construit un livre PDF avec sommaire, retours à la ligne et pages fiables."""
    c = pdf_canvas.Canvas(path, pagesize=A4)
    width, height = A4
    left, right = 2 * cm, 2 * cm
    usable = width - left - right

    def count_summary_pages():
        dummy = pdf_canvas.Canvas(io.BytesIO(), pagesize=A4)
        y = height - 3 * cm
        pages = 1
        y -= 1.0 * cm  # titre
        y -= 0.7 * cm  # date
        y -= 0.8 * cm  # sommaire
        for recipe, _persons in recipes_with_persons:
            cat = translate_category_name(recipe.get("category", "Autre"))
            label = f"- [{cat}] {recipe.get('name','')}"
            lines = _pdf_wrap_lines(dummy, label, usable - 2.0*cm, "Helvetica", 10)
            need = len(lines) * 0.48 * cm + 0.08*cm
            if y - need < 2 * cm:
                pages += 1
                y = height - 2 * cm
            y -= need
        return pages

    def count_recipe_pages(recipe, persons):
        dummy = pdf_canvas.Canvas(io.BytesIO(), pagesize=A4)
        count = [1]
        real = dummy.showPage
        def show():
            count[0] += 1
            real()
        dummy.showPage = show
        draw_recipe_content(dummy, recipe, persons, width, height)
        return count[0]

    summary_pages = count_summary_pages()
    starts, page = [], summary_pages + 1
    for recipe, persons in recipes_with_persons:
        starts.append(page)
        page += count_recipe_pages(recipe, persons)
    total_pages = max(1, page - 1)

    current = [1]
    real_show = c.showPage
    def numbered_show_page():
        c.setFillColorRGB(0,0,0)
        c.setFont("Helvetica", 8)
        c.drawCentredString(width/2, 1*cm, t("cookbookpdf_page_number", current=current[0], total=total_pages))
        real_show()
        current[0] += 1
    c.showPage = numbered_show_page

    y = height - 3 * cm
    y = _pdf_draw_wrapped(c, t("cookbookpdf_title"), left, y, usable, height,
                          font_name="Helvetica-Bold", font_size=24, line_height=0.9*cm)
    y -= 0.2*cm
    y = _pdf_draw_wrapped(c, t("cookbookpdf_generated", date=datetime.now().strftime("%d/%m/%Y")),
                          left, y, usable, height, font_size=10)
    y -= 0.25*cm
    y = _pdf_draw_wrapped(c, t("cookbookpdf_toc_heading"), left, y, usable, height,
                          font_name="Helvetica-Bold", font_size=14, line_height=0.65*cm)

    for (recipe, _persons), start_page in zip(recipes_with_persons, starts):
        cat = translate_category_name(recipe.get("category", "Autre"))
        label = f"- [{cat}] {recipe.get('name','')}"
        lines = _pdf_wrap_lines(c, label, usable - 2.0*cm, "Helvetica", 10)
        need = len(lines)*0.48*cm + 0.08*cm
        if y - need < 2*cm:
            numbered_show_page(); y = height - 2*cm
        c.setFont("Helvetica",10)
        for i,line in enumerate(lines):
            c.drawString(left, y, line)
            if i == 0:
                c.drawRightString(width-right, y, str(start_page))
            y -= 0.48*cm
        y -= 0.08*cm

    if recipes_with_persons:
        numbered_show_page()
        for idx,(recipe,persons) in enumerate(recipes_with_persons):
            draw_recipe_content(c, recipe, persons, width, height)
            if idx < len(recipes_with_persons)-1:
                numbered_show_page()

    # footer de la dernière page, sans créer une page blanche supplémentaire
    c.setFillColorRGB(0,0,0)
    c.setFont("Helvetica",8)
    c.drawCentredString(width/2, 1*cm, t("cookbookpdf_page_number", current=current[0], total=total_pages))
    c.save()
WEEKDAYS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]


def _normalize_plan_recipe_refs(plan, recipes=None):
    if not isinstance(plan, dict):
        return {}
    recipes = recipes if recipes is not None else load_recipes()
    changed = False
    out = copy.deepcopy(plan)
    for day_data in out.values():
        if not isinstance(day_data, dict):
            continue
        for slot, info in list(day_data.items()):
            if not isinstance(info, dict):
                continue
            before = (info.get("recipe_id"), info.get("recipe_name"))
            enrich_recipe_reference(info, recipes)
            if before != (info.get("recipe_id"), info.get("recipe_name")):
                changed = True
    return out, changed


def load_weekly_plan():
    if os.path.exists(WEEKLY_PLAN_FILE):
        try:
            data = _read_user_json(WEEKLY_PLAN_FILE, dict, {}, label="weekly_plan")
            if _corruption_key(WEEKLY_PLAN_FILE) in _CORRUPTED_DATA_FILES:
                return {}
            if isinstance(data, dict):
                normalized, changed = _normalize_plan_recipe_refs(data)
                if changed:
                    _atomic_write_json(WEEKLY_PLAN_FILE, normalized)
                return normalized
        except Exception as exc:
            log_internal_error("load_weekly_plan", exc)
    return {}


def save_weekly_plan(plan):
    normalized, _ = _normalize_plan_recipe_refs(plan)
    _atomic_write_json(WEEKLY_PLAN_FILE, normalized)


def get_current_week_key():
    """Clé identifiant la semaine calendaire actuelle (année-numéro de
    semaine ISO), utilisée pour qu'un même planning enregistré plusieurs
    fois dans la même semaine ne crée qu'une seule entrée d'historique."""
    year, week, _ = datetime.now().isocalendar()
    return f"{year}-S{week:02d}"


def load_weekly_plan_history():
    """Liste des plannings archivés : [{'week_start','plan','saved_at'}, ...]."""
    if os.path.exists(WEEKLY_PLAN_HISTORY_FILE):
        try:
            data = _read_user_json(WEEKLY_PLAN_HISTORY_FILE, list, [], label="weekly_plan_history")
            if _corruption_key(WEEKLY_PLAN_HISTORY_FILE) in _CORRUPTED_DATA_FILES:
                return []
            if isinstance(data, list):
                if isinstance(data, list):
                    recipes = load_recipes()
                    changed = False
                    for entry in data:
                        if isinstance(entry, dict) and isinstance(entry.get("plan"), dict):
                            plan, ch = _normalize_plan_recipe_refs(entry["plan"], recipes)
                            entry["plan"] = plan
                            changed = changed or ch
                    if changed:
                        _atomic_write_json(WEEKLY_PLAN_HISTORY_FILE, data)
                    return data
        except Exception as exc:
            log_internal_error("suppressed_exception", exc)
    return []


def save_weekly_plan_history(history):
    recipes = load_recipes()
    normalized = []
    for entry in history if isinstance(history, list) else []:
        item = copy.deepcopy(entry)
        if isinstance(item, dict) and isinstance(item.get("plan"), dict):
            item["plan"], _ = _normalize_plan_recipe_refs(item["plan"], recipes)
        normalized.append(item)
    _atomic_write_json(WEEKLY_PLAN_HISTORY_FILE, normalized)


WEEKLY_PLAN_HISTORY_RETENTION = 26  # environ 6 mois d'historique


def archive_current_week(plan):
    """Enregistre un instantané du planning actuel dans l'historique, sous
    la clé de la semaine calendaire en cours : ré-enregistrer plusieurs fois
    dans la même semaine met simplement à jour son entrée, sans créer de
    doublon. Ne fait rien si le planning est entièrement vide."""
    if not any(plan.values()):
        return
    week_key = get_current_week_key()
    history = load_weekly_plan_history()
    history = [h for h in history if h.get("week_start") != week_key]
    history.append({
        "week_start": week_key,
        "plan": plan,
        "saved_at": datetime.now().strftime("%Y-%m-%d"),
    })
    history.sort(key=lambda h: h.get("week_start", ""))
    history = history[-WEEKLY_PLAN_HISTORY_RETENTION:]
    save_weekly_plan_history(history)


def load_weekly_plan_templates():
    """Modèles de semaine réutilisables : {nom_du_modele: plan}."""
    if os.path.exists(WEEKLY_PLAN_TEMPLATES_FILE):
        try:
            data = _read_user_json(WEEKLY_PLAN_TEMPLATES_FILE, dict, {}, label="weekly_plan_templates")
            if _corruption_key(WEEKLY_PLAN_TEMPLATES_FILE) in _CORRUPTED_DATA_FILES:
                return {}
            if isinstance(data, dict):
                if isinstance(data, dict):
                    recipes = load_recipes()
                    changed = False
                    for key, plan in list(data.items()):
                        if isinstance(plan, dict):
                            normalized, ch = _normalize_plan_recipe_refs(plan, recipes)
                            data[key] = normalized
                            changed = changed or ch
                    if changed:
                        _atomic_write_json(WEEKLY_PLAN_TEMPLATES_FILE, data)
                    return data
        except Exception as exc:
            log_internal_error("suppressed_exception", exc)
    return {}


def save_weekly_plan_templates(templates):
    recipes = load_recipes()
    normalized = {}
    for name, plan in (templates.items() if isinstance(templates, dict) else []):
        normalized[name], _ = _normalize_plan_recipe_refs(plan, recipes) if isinstance(plan, dict) else ({}, False)
    _atomic_write_json(WEEKLY_PLAN_TEMPLATES_FILE, normalized)


# ---------------------------------------------------------------------------
# Export du planning de la semaine vers un fichier .ics (iCalendar), lisible
# par Google Agenda, Outlook, Apple Calendrier, etc.
# ---------------------------------------------------------------------------

_ICS_MEAL_TIMES = {
    "Petit-déjeuner": ("0800", "0830"),
    "Déjeuner": ("1230", "1330"),
    "Dîner": ("1930", "2030"),
}
_ICS_MEAL_GROUPS = {
    "Petit-déjeuner": ["Petit-déjeuner"],
    "Déjeuner": ["Déjeuner — Entrée", "Déjeuner — Plat", "Déjeuner — Dessert"],
    "Dîner": ["Dîner — Entrée", "Dîner — Plat", "Dîner — Dessert"],
}
# Traductions pour l'affichage dans le calendrier exporté (.ics)
# uniquement, par langue : ces libellés ne sont ni des clés de
# _ICS_MEAL_GROUPS/_ICS_MEAL_TIMES, ni des créneaux complets de
# MEAL_SLOTS (juste la période du repas, ou juste le type de plat), donc
# traités séparément des autres tables.
_ICS_MEAL_PERIOD_TRANSLATIONS = {
    "en": {"petit-déjeuner": "Breakfast", "déjeuner": "Lunch", "dîner": "Dinner"},
    "es": {"petit-déjeuner": "Desayuno", "déjeuner": "Almuerzo", "dîner": "Cena"},
    "de": {"petit-déjeuner": "Frühstück", "déjeuner": "Mittagessen", "dîner": "Abendessen"},
}
_ICS_COURSE_LABEL_TRANSLATIONS = {
    "en": {"entrée": "Starter", "plat": "Main", "dessert": "Dessert"},
    "es": {"entrée": "Entrante", "plat": "Plato principal", "dessert": "Postre"},
    "de": {"entrée": "Vorspeise", "plat": "Hauptgericht", "dessert": "Dessert"},
}


def _translate_ics_meal_period(period):
    if CURRENT_LANGUAGE == "fr":
        return period
    return _ICS_MEAL_PERIOD_TRANSLATIONS.get(CURRENT_LANGUAGE, {}).get(period.strip().lower(), period)


def _translate_ics_course_label(label):
    if not label or CURRENT_LANGUAGE == "fr":
        return label
    return _ICS_COURSE_LABEL_TRANSLATIONS.get(CURRENT_LANGUAGE, {}).get(label.strip().lower(), label)


def _escape_ics_text(text):
    return (text.replace("\\", "\\\\")
                .replace(";", "\\;")
                .replace(",", "\\,")
                .replace("\n", "\\n"))


def _fold_ics_line(line):
    """Replie une ligne selon la limite de 75 octets recommandée par la
    norme iCalendar (RFC 5545), pour une compatibilité maximale."""
    if len(line.encode("utf-8")) <= 75:
        return line
    parts = []
    current = ""
    for ch in line:
        if len((current + ch).encode("utf-8")) > 74:
            parts.append(current)
            current = " " + ch
        else:
            current += ch
    parts.append(current)
    return "\r\n".join(parts)


def build_weekly_plan_ics(plan):
    """Construit le contenu d'un fichier .ics à partir du planning de la
    semaine : un évènement hebdomadaire récurrent par repas (petit-déjeuner,
    déjeuner, dîner) et par jour où quelque chose est prévu."""
    weekday_index = {d: i for i, d in enumerate(WEEKDAYS)}  # Lundi=0 ... Dimanche=6
    today = datetime.now().date()
    now_stamp = datetime.now().strftime("%Y%m%dT%H%M%S")

    lines = ["BEGIN:VCALENDAR", "VERSION:2.0",
             "PRODID:-//Mes Recettes\\, Mes Courses//FR", "CALSCALE:GREGORIAN"]
    event_count = 0

    for day, slots_data in plan.items():
        if day not in weekday_index or not slots_data:
            continue
        delta_days = (weekday_index[day] - today.weekday()) % 7
        event_date = today + timedelta(days=delta_days)
        date_str = event_date.strftime("%Y%m%d")

        for meal_period, slot_names in _ICS_MEAL_GROUPS.items():
            components = []
            for slot in slot_names:
                info = slots_data.get(slot)
                if info and info.get("recipe_name"):
                    label = _translate_ics_course_label(slot.split(" — ", 1)[1]) if " — " in slot else None
                    components.append(f"{label} : {info['recipe_name']}" if label else info["recipe_name"])
            if not components:
                continue

            start_time, end_time = _ICS_MEAL_TIMES[meal_period]
            summary_names = [c.split(" : ", 1)[1] if " : " in c else c for c in components]
            summary = f"{_translate_ics_meal_period(meal_period)} : " + ", ".join(summary_names)
            description = "\\n".join(components)

            event_count += 1
            uid = f"recette-{event_count}-{uuid.uuid4().hex}@monlivrederecettes"

            lines.append("BEGIN:VEVENT")
            lines.append(_fold_ics_line(f"UID:{uid}"))
            lines.append(f"DTSTAMP:{now_stamp}")
            lines.append(f"DTSTART:{date_str}T{start_time}00")
            lines.append(f"DTEND:{date_str}T{end_time}00")
            lines.append("RRULE:FREQ=WEEKLY")
            lines.append(_fold_ics_line(f"SUMMARY:{_escape_ics_text(summary)}"))
            lines.append(_fold_ics_line(f"DESCRIPTION:{_escape_ics_text(description)}"))
            lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def _normalize_menu_recipe_refs(menus, recipes=None):
    if not isinstance(menus, list):
        return [], False
    recipes = recipes if recipes is not None else load_recipes()
    out = copy.deepcopy(menus)
    changed = False
    for menu in out:
        if not isinstance(menu, dict):
            continue
        items = menu.get("items", [])
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            before = (item.get("recipe_id"), item.get("recipe_name"))
            enrich_recipe_reference(item, recipes)
            if before != (item.get("recipe_id"), item.get("recipe_name")):
                changed = True
    return out, changed


def load_menus():
    if os.path.exists(MENUS_FILE):
        try:
            data = _read_user_json(MENUS_FILE, list, [], label="menus")
            if _corruption_key(MENUS_FILE) in _CORRUPTED_DATA_FILES:
                return []
            if isinstance(data, list):
                normalized, changed = _normalize_menu_recipe_refs(data)
                if changed:
                    _atomic_write_json(MENUS_FILE, normalized)
                return normalized
        except Exception as exc:
            log_internal_error("load_menus", exc)
    return []


def save_menus(menus):
    normalized, _ = _normalize_menu_recipe_refs(menus)
    _atomic_write_json(MENUS_FILE, normalized)


def find_recipe_by_name(recipes, name):
    """Compatibilité ancienne : préférer find_recipe_by_ref pour les nouvelles données."""
    return next((r for r in recipes if isinstance(r, dict) and r.get("name") == name), None)


# ---------------------------------------------------------------------------
# Import d'une recette depuis un lien internet (données structurées
# Schema.org "Recipe", utilisées par la plupart des sites de cuisine).
# ---------------------------------------------------------------------------

_FRACTION_MAP = {"½": 0.5, "¼": 0.25, "¾": 0.75, "⅓": 1 / 3, "⅔": 2 / 3}

_UNIT_ALIASES = {
    "cup": "cup", "boîte": "boîte", "gousse": "gousse", "oz": "oz", "lb": "lb",
    "sachet": "sachet", "sachets": "sachet",
    "filet": "filet", "filets": "filet",
    "rouleau": "rouleau", "rouleaux": "rouleau",
    "poignée": "poignée", "poignées": "poignée",
    "cuillerée": "cuillerée", "cuillerées": "cuillerée",
    "cuillerée à soupe": "cuillère à soupe", "cuillerées à soupe": "cuillère à soupe",
    "cuillerée à café": "cuillère à café", "cuillerées à café": "cuillère à café",
    "disque": "disque", "disques": "disque",
    "tour de moulin": "tour de moulin", "tours de moulin": "tour de moulin",
    "grosse poignée": "grosse poignée", "grosses poignées": "grosse poignée",
    "pot-mesure": "pot de yaourt", "sachet-mesure": "sachet",
    "dl": "dl", "décilitre": "dl", "décilitres": "dl",
    "cc": "cuillère à café", "cuil a café": "cuillère à café",
    "cuil à soupe": "cuillère à soupe", "cuil a soupe": "cuillère à soupe",
    "unité": "pièce", "unités": "pièce",
    "pincée": "pincée", "pincées": "pincée",
    "g": "Gr", "gr": "Gr", "gramme": "Gr", "grammes": "Gr",
    "kg": "Kilo", "kilo": "Kilo", "kilos": "Kilo",
    "kilogramme": "Kilo", "kilogrammes": "Kilo",
    "ml": "ml", "millilitre": "ml", "millilitres": "ml",
    "cl": "cl", "centilitre": "cl", "centilitres": "cl",
    "l": "Litre", "litre": "Litre", "litres": "Litre",
    "cas": "cuillère à soupe", "c.a.s": "cuillère à soupe", "c. à soupe": "cuillère à soupe",
    "c à s": "cuillère à soupe", "c. à s": "cuillère à soupe", "c a s": "cuillère à soupe",
    "c à soupe": "cuillère à soupe", "c. a soupe": "cuillère à soupe",
    "cuillere": "cuillère à soupe", "cuillères": "cuillère à soupe", "cuillère": "cuillère à soupe",
    "cuillere a soupe": "cuillère à soupe", "cuillère à soupe": "cuillère à soupe",
    "cuillères à soupe": "cuillère à soupe", "cuilleres a soupe": "cuillère à soupe",
    "cac": "cuillère à café", "c. à café": "cuillère à café", "c à café": "cuillère à café",
    "c. a cafe": "cuillère à café",
    "cuillere a cafe": "cuillère à café", "cuillère à café": "cuillère à café",
    "cuillères à café": "cuillère à café", "cuilleres a cafe": "cuillère à café",
    "piece": "pièce", "pièce": "pièce", "pièces": "pièce", "pieces": "pièce",
}


def parse_quantity_token(token):
    token = token.strip()
    if token in _FRACTION_MAP:
        return _FRACTION_MAP[token]
    # Plage compacte 2-3 / 2–3 : conserve la borne basse.
    m = re.match(r"^([0-9]+(?:[.,][0-9]+)?)\s*[-–—]\s*([0-9]+(?:[.,][0-9]+)?)$", token)
    if m:
        return float(m.group(1).replace(",", "."))
    m = re.match(r"^(\d+)\s*/\s*(\d+)$", token)
    if m:
        return int(m.group(1)) / int(m.group(2))
    token = token.replace(",", ".")
    try:
        value = float(token)
        return value if math.isfinite(value) else None
    except ValueError:
        return None


def _match_unit_tokens(tokens, start):
    """Essaie de faire correspondre 3, puis 2, puis 1 token(s) à partir de
    `start` à une unité connue (ex. « cuillères à soupe »), en testant la
    séquence la plus longue en premier. Insensible aux accents/à la casse."""
    for length in (4, 3, 2, 1):
        end = start + length
        if end <= len(tokens):
            candidate = " ".join(t.strip(".,") for t in tokens[start:end])
            candidate_key = ingredient_sort_key(candidate)
            for alias, unit in _UNIT_ALIASES.items():
                if ingredient_sort_key(alias) == candidate_key:
                    return unit, end
    return None, start


def parse_ingredient_line(line):
    """Tente d'extraire (nom, quantité, unité) d'une ligne d'ingrédient en
    texte libre, telle que fournie par un site de recettes. Retourne un
    résultat raisonnable même quand le texte ne suit pas un format standard
    (l'utilisateur pourra toujours corriger à la main après import)."""
    original = line.strip()
    if not original:
        return None
    tokens = original.split()
    if not tokens:
        return None

    qty = parse_quantity_token(tokens[0])
    unit = None
    rest_start = 0

    # Quantités mixtes : « 1 1/2 kg », « 2 ½ tasses ».
    if qty is not None and len(tokens) > 1:
        frac = parse_quantity_token(tokens[1])
        if frac is not None and ("/" in tokens[1] or tokens[1] in _FRACTION_MAP):
            qty += frac
            rest_start = 2

    # Quantités multipliées : « 2 x 400 g tomates », « 3 × 125 ml ».
    multiplier_start = rest_start or 1
    if qty is not None and len(tokens) > multiplier_start + 1 and tokens[multiplier_start].lower() in ("x", "×", "*"):
        second_qty = parse_quantity_token(tokens[multiplier_start + 1])
        if second_qty is not None:
            qty *= second_qty
            rest_start = multiplier_start + 2

    # Plages courantes « 2 à 3 carottes » / « 2-3 carottes » : on conserve
    # la borne basse comme valeur prudente et on retire la seconde borne du nom.
    if qty is not None and len(tokens) > rest_start + 2 and tokens[rest_start or 1].lower() in ("à", "a", "-"):
        maybe_high = parse_quantity_token(tokens[(rest_start or 1) + 1])
        if maybe_high is not None:
            rest_start = (rest_start or 1) + 2

    # Certains sites écrivent « 750g », « 1kg » ou « 20cl » sans espace.
    # Dans ce cas, sépare quantité et unité avant d'analyser le reste.
    attached = re.match(
        r"^([0-9]+(?:[.,][0-9]+)?)([a-zA-ZÀ-ÿ]+)$",
        tokens[0]
    )
    if qty is None and attached:
        qty = parse_quantity_token(attached.group(1))
        attached_unit = attached.group(2)
        unit_match, _ = _match_unit_tokens([attached_unit], 0)
        if unit_match:
            unit = unit_match
            rest_start = 1

    if qty is not None:
        if rest_start == 0:
            rest_start = 1
        if len(tokens) > rest_start:
            matched_unit, matched_end = _match_unit_tokens(tokens, rest_start)
            if matched_unit:
                unit, rest_start = matched_unit, matched_end

    name = " ".join(tokens[rest_start:]).strip()
    name = re.sub(r"^(de |d['’]|of )", "", name, flags=re.IGNORECASE).strip()

    # Les sites écrivent souvent « sachet de levure », « poignée de pépites »
    # quand aucune unité structurée n'est fournie. Pour la base interne, le
    # nom canonique est l'aliment lui-même ; on retire donc seulement ces
    # contenants/mesures du début du nom. La quantité reste conservée.
    name = re.sub(
        r"^(?:sachet|sachets|poignée|poignees?|poignées?)\s+(?:de |d['’])?",
        "", name, flags=re.IGNORECASE
    ).strip()

    if not name:
        name = original

    # Un ingrédient sans quantité (« sel », « poivre ») n'est pas une pièce.
    if qty is None:
        qty = 1
        unit = unit or "au goût"
    else:
        unit = unit or "pièce"

    if unit == "dl":
        qty *= 100
        unit = "ml"
    return {"name": name.capitalize(), "quantity": qty, "unit": unit}


# ---------------------------------------------------------------------------
# Import OCR photo (v37)
# ---------------------------------------------------------------------------

OCR_MAX_JPEG_DIMENSION = 1600
OCR_UNICODE_FRACTIONS = {
    **_FRACTION_MAP,
    "⅕": 1 / 5, "⅖": 2 / 5, "⅗": 3 / 5, "⅘": 4 / 5,
    "⅙": 1 / 6, "⅚": 5 / 6, "⅛": 1 / 8, "⅜": 3 / 8,
    "⅝": 5 / 8, "⅞": 7 / 8,
}

OCR_INGREDIENT_BOUNDARY_RE = re.compile(
    r"^(?:valeurs?\s+nutritionnelles?|par\s+portion|pour\s+100\s*g|"
    r"[ée]nergie|lipides?|glucides?|prot[ée]ines?|fibres?|allerg[èe]nes?|"
    r"attention|\*?\s*conserver\s+au\s+r[ée]frig[ée]rateur)",
    re.IGNORECASE,
)
OCR_NON_INGREDIENT_RE = re.compile(
    r"^(?:mes\s+ustensiles|ustensiles|[àa]\s*ajouter\s+vous[\s-]?m[êe]me|"
    r"ajouter\s*vous|par\s+portion|pour\s+100\s*g|valeurs?\s+nutritionnelles?)",
    re.IGNORECASE,
)


def prepare_image_for_ocr(source, manual_rotation=0, max_dimension=OCR_MAX_JPEG_DIMENSION):
    """Normalise une photo sans modifier le fichier d'origine.

    Pillow n'applique pas automatiquement l'orientation EXIF. C'était la
    cause principale des pages reconnues tête-bêche sur certains téléphones.
    La réduction à 1600 px reprend le seuil validé par le corpus OCR mobile :
    elle accélère Tesseract et stabilise sa segmentation sur les JPEG de
    smartphones, tout en conservant assez de définition pour le texte.
    """
    image = ImageOps.exif_transpose(source).convert("RGB")
    rotation = int(manual_rotation or 0) % 360
    if rotation:
        image = image.rotate(-rotation, expand=True)
    if max_dimension and max(image.size) > max_dimension:
        image.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
    return image


def detect_ocr_rotation(image):
    """Retourne la rotation horaire conseillée par Tesseract OSD.

    OSD échoue normalement sur une page contenant trop peu de texte : ce cas
    est volontairement silencieux et laisse l'image inchangée. Un seuil de
    confiance évite de retourner une photo déjà droite sur une estimation
    fragile.
    """
    if not PYTESSERACT_AVAILABLE:
        return 0
    try:
        result = pytesseract.image_to_osd(
            image, output_type=pytesseract.Output.DICT
        )
        rotation = int(result.get("rotate") or 0) % 360
        confidence = float(result.get("orientation_conf") or 0)
        return rotation if rotation in (90, 180, 270) and confidence >= 3.0 else 0
    except Exception:
        return 0


def _ocr_plausible_line_count(text):
    count = 0
    for line in (text or "").splitlines():
        words = re.findall(r"[A-Za-zÀ-ÿ]{2,}", line)
        if len(words) >= 3 and sum(map(len, words)) / len(words) >= 3.0:
            count += 1
    return count


def looks_like_preparation_grid(text):
    """Repère prudemment une page de préparation susceptible d'être en grille."""
    value = text or ""
    normalized = ingredient_sort_key(value)
    if len(value) < 350 or re.search(r"ingredients?\s+pour", normalized):
        return False
    action_markers = (
        "prechauff", "enfourn", "faites", "ajoutez", "melangez", "servez",
        "cuisson", "casserole", "four ", "minutes", " min",
    )
    marker_count = sum(marker in normalized for marker in action_markers)
    return marker_count >= 3 and _ocr_plausible_line_count(value) >= 7


def ocr_grid_cells(image, recognize, columns=3):
    """OCR de 2 x ``columns`` cases, dans l'ordre ligne puis colonne.

    Cette stratégie vient de l'application mobile et corrige l'ordre des
    fiches HelloFresh : un OCR global lit souvent 1,4,2,5,3,6 alors que le
    découpage réel produit bien 1,2,3,4,5,6.
    """
    width, height = image.size
    overlap_x = max(4, round(width * 0.008))
    overlap_y = max(4, round(height * 0.03))
    middle = height // 2
    rows = ((0, min(height, middle + overlap_y)),
            (max(0, middle - overlap_y), height))
    chunks = []
    for y0, y1 in rows:
        for column in range(columns):
            x0 = max(0, round(column * width / columns) - overlap_x)
            x1 = min(width, round((column + 1) * width / columns) + overlap_x)
            text_value = (recognize(image.crop((x0, y0, x1, y1))) or "").strip()
            if text_value:
                chunks.append(text_value)
    return "\n\n".join(chunks)


def _ocr_data_lines(data):
    """Lignes et boîtes Tesseract, sans dépendance à pandas."""
    groups = {}
    for i, word in enumerate(data.get("text", [])):
        if not str(word).strip():
            continue
        key = tuple(data[k][i] for k in ("block_num", "par_num", "line_num"))
        groups.setdefault(key, []).append(i)
    result = []
    for ids in groups.values():
        words = [{"text": str(data["text"][i]), "x": data["left"][i],
                  "y": data["top"][i], "w": data["width"][i],
                  "h": data["height"][i], "conf": float(data["conf"][i])} for i in ids]
        result.append(words)
    return result


def _ocr_line_text(words):
    return " ".join(word["text"] for word in words)


def read_ocr_printed_fraction(image, lang, cancelled=lambda: False):
    """Lit les deux chiffres d'une petite fraction diagonale, sans deviner.

    Il faut trois composantes (numérateur, barre oblique, dénominateur),
    une géométrie compatible et deux cadrages concordants pour chaque chiffre.
    Un pourcentage ou un entier ne doit pas devenir une fraction.
    """
    if image.width < 5 or image.height < 8:
        return None
    # Les candidats sont de petits glyphes, jamais des pages entières.
    crop = ImageOps.autocontrast(ImageOps.grayscale(image))
    if max(crop.size) > 180:
        crop.thumbnail((180, 180))
    width, height = crop.size
    pixels = crop.load()
    seen, components = set(), []
    for y in range(height):
        for x in range(width):
            if (x, y) in seen or pixels[x, y] >= 130:
                continue
            pending, points = [(x, y)], []
            seen.add((x, y))
            while pending:
                a, b = pending.pop()
                points.append((a, b))
                for u, v in ((a-1, b), (a+1, b), (a, b-1), (a, b+1)):
                    if (0 <= u < width and 0 <= v < height
                            and (u, v) not in seen and pixels[u, v] < 130):
                        seen.add((u, v))
                        pending.append((u, v))
            if len(points) >= max(3, width * height * .003):
                components.append(points)
    if len(components) != 3:
        return None
    def bounds(points):
        return (min(x for x, y in points), min(y for x, y in points),
                max(x for x, y in points)+1, max(y for x, y in points)+1)
    slash = max(components, key=lambda p: bounds(p)[3] - bounds(p)[1])
    others = sorted((p for p in components if p is not slash), key=lambda p: bounds(p)[0])
    numerator, denominator = map(bounds, others)
    sb = bounds(slash)
    mx = sum(x for x, y in slash) / len(slash)
    my = sum(y for x, y in slash) / len(slash)
    covariance = sum((x-mx)*(y-my) for x, y in slash) / len(slash)
    if not (covariance < -1 and sb[3]-sb[1] > 1.3 * max(
            numerator[3]-numerator[1], denominator[3]-denominator[1])
            and numerator[0] < denominator[0] and numerator[1] < denominator[1]
            and numerator[3] <= denominator[1] + height * .2):
        return None
    digits = []
    for box in (numerator, denominator):
        readings = []
        for pad in (1, 2):
            if cancelled():
                raise OperationCancelled("operation_cancelled")
            digit = crop.crop((max(0, box[0]-pad), max(0, box[1]-pad),
                               min(width, box[2]+pad), min(height, box[3]+pad)))
            digit = digit.resize((digit.width*12, digit.height*12), Image.Resampling.BICUBIC)
            digit = ImageOps.expand(digit, border=30, fill=255)
            try:
                reading = pytesseract.image_to_string(
                    digit, lang=lang, config="--oem 3 --psm 13 -c tessedit_char_whitelist=0123456789",
                    timeout=8).strip()
            except RuntimeError:
                return None  # Une relecture facultative ne doit pas effacer la page.
            readings.append(reading)
        if readings[0] != readings[1] or not re.fullmatch(r"[1-9]", readings[0]):
            return None
        digits.append(int(readings[0]))
    if digits[0] >= digits[1]:
        return None
    return f"{digits[0]}/{digits[1]}"


_OCR_MEASURE_UNIT = r"cs|cas|cac|g|kg|ml|cl|l|tbsp|tsp"


def repair_ocr_preparation_fractions(image, rows, lang, cancelled=lambda: False):
    """Inspecte le glyphe ou l'espace précédant chaque unité reconnue."""
    fixes, counts = [], {}
    for words in rows:
        for index, word in enumerate(words):
            unit = word['text'].lower()
            if not re.fullmatch(_OCR_MEASURE_UNIT, unit):
                continue
            counts[unit] = counts.get(unit, 0) + 1
            if index == 0:
                continue
            previous = words[index-1]
            numeric = bool(re.fullmatch(r"[0-9%¼½¾/]+", previous['text']))
            if numeric:
                box = (previous['x']-3, previous['y']-3,
                       previous['x']+previous['w']+3, previous['y']+previous['h']+3)
            elif previous['text'].lower() in ('et', ':', 'and', 'y', 'und'):
                line_top = min(w['y'] for w in words)
                line_bottom = max(w['y']+w['h'] for w in words)
                box = (previous['x']+previous['w']+1, line_top-4, word['x']-1, line_bottom+4)
            else:
                continue
            box = (max(0, box[0]), max(0, box[1]), min(image.width, box[2]), min(image.height, box[3]))
            if box[2] <= box[0] or box[3] <= box[1]:
                continue
            fraction = read_ocr_printed_fraction(image.crop(box), lang, cancelled)
            if fraction:
                if numeric:
                    previous['text'] = fraction
                else:
                    word['text'] = fraction + ' ' + word['text']
                fixes.append((unit, counts[unit], fraction))
    return fixes


def apply_ocr_verified_fractions(text, reference, fixes):
    """Reporte les fractions relues uniquement si les unités restent alignées."""
    changes = []
    for unit, occurrence, fraction in fixes:
        pattern = rf"(?<![A-Za-zÀ-ÿ]){re.escape(unit)}\b"
        matches = list(re.finditer(pattern, text, re.I))
        if len(matches) != len(re.findall(pattern, reference, re.I)):
            return reference
        if occurrence > len(matches):
            return reference
        match = matches[occurrence-1]
        prefix = text[:match.start()]
        quantity = re.search(r"(?<![\w/])(?:\d+(?:[.,]\d+)?(?:\s*/\s*\d+)?|[%¼½¾])\s*$", prefix)
        start = quantity.start() if quantity else match.start()
        changes.append((start, match.start(), fraction + ' '))
    for start, end, replacement in sorted(changes, reverse=True):
        text = text[:start] + replacement + text[end:]
    return text


def ocr_ingredient_table(image, lang, cancelled=lambda: False):
    """Relit les lignes à leur résolution source, loin des colonnes voisines.

    La grande séparation nom/quantité permet de cadrer chaque ligne sans
    inclure le début de la colonne de préparation située à sa droite.
    """
    data = pytesseract.image_to_data(image, lang=lang, config="--oem 3 --psm 4",
                                    output_type=pytesseract.Output.DICT, timeout=25)
    rows = _ocr_data_lines(data)
    active, reads, output = False, 0, []
    for words in rows:
        text = _ocr_line_text(words)
        if re.search(r"ingr[eé]dients?\s+(?:pour|for|para|f[uü]r)", text, re.I):
            active = True
            output.append(text)
            continue
        if active and OCR_INGREDIENT_BOUNDARY_RE.search(text):
            active = False
        if not active or reads >= 30:
            output.append(text)
            continue
        gaps = [(words[j]["x"] - words[j-1]["x"] - words[j-1]["w"], j)
                for j in range(1, len(words))]
        gap, split = max(gaps, default=(0, 0))
        if gap < image.width * .16:
            output.append(text)
            continue
        end = len(words)
        for j in range(split + 1, len(words)):
            if words[j]["x"] - words[j-1]["x"] - words[j-1]["w"] > image.width * .05:
                end = j
                break
        selected = words[:end]
        # Relire aussi les fractions reconnues comme « % » ou comme entier.
        quantity_word = words[split]
        fraction = None
        if re.fullmatch(r"[0-9%¼½¾/]+", quantity_word["text"]):
            q = quantity_word
            box = (max(0, q['x']-3), max(0, q['y']-3),
                   min(image.width, q['x']+q['w']+3), min(image.height, q['y']+q['h']+3))
            fraction = read_ocr_printed_fraction(image.crop(box), lang, cancelled)
            if fraction:
                quantity_word['text'] = fraction
        original = _ocr_line_text(selected)
        if fraction:
            output.append(original)
            continue  # Ne pas écraser la fraction vérifiée par une lecture globale.
        x0 = max(0, min(w["x"] for w in selected) - 12)
        x1 = min(image.width, max(w["x"] + w["w"] for w in selected) + 12)
        y0 = max(0, min(w["y"] for w in selected) - 10)
        y1 = min(image.height, max(w["y"] + w["h"] for w in selected) + 10)
        if cancelled():
            raise OperationCancelled("operation_cancelled")
        crop = image.crop((x0, y0, x1, y1))
        crop = ImageOps.autocontrast(ImageOps.grayscale(crop))
        crop = crop.resize((crop.width * 2, crop.height * 2), Image.Resampling.LANCZOS)
        reread = pytesseract.image_to_string(crop, lang=lang,
                                            config="--oem 3 --psm 7", timeout=15).strip()
        reads += 1
        before = parse_ocr_ingredient_table_line(original)
        after = parse_ocr_ingredient_table_line(reread)
        # Ne remplacer une ligne qu'avec un nom compatible et une quantité
        # exploitable. Une fraction ambiguë ne devient jamais un entier.
        before_name = before["name"] if before else _ocr_line_text(words[:split])
        same_name = after and difflib.SequenceMatcher(
            None, ingredient_sort_key(before_name), ingredient_sort_key(after["name"])
        ).ratio() >= .75
        fraction_lost = (re.search(r"[%‰¼½¾⅓⅔]|\d\s*/\s*\d", original)
                         and after and after["quantity"] is not None
                         and float(after["quantity"]).is_integer())
        if same_name and after["quantity"] is not None and not fraction_lost:
            output.append(reread)
        else:
            output.append(original)
    return "\n".join(output)


def restore_ocr_spacing(text, reference):
    """Rétablit seulement les espaces déjà observés dans l'autre lecture.

    Aucun mot ni nombre n'est ajouté. Les suites alphabétiques identiques
    sont rapprochées, pour corriger par exemple « versezunfilet ».
    """
    words = reference.split()
    joined = {}
    for i in range(len(words)):
        for length in range(2, min(6, len(words) - i + 1)):
            group = words[i:i + length]
            if not all(re.fullmatch(r"[A-Za-zÀ-ÿ'’-]+", w) for w in group):
                continue
            key = "".join(group).casefold()
            if len(key) >= 7:
                joined.setdefault(key, " ".join(group))
    return re.sub(r"[A-Za-zÀ-ÿ'’-]+", lambda m: joined.get(m[0].casefold(), m[0]), text)


def ocr_preparation_cell(image, lang, cancelled=lambda: False):
    """Localise le texte d'une case puis le lit comme un seul bloc."""
    if cancelled():
        raise OperationCancelled("operation_cancelled")
    data = pytesseract.image_to_data(image, lang=lang, config="--oem 3 --psm 3",
                                    output_type=pytesseract.Output.DICT, timeout=25)
    rows = _ocr_data_lines(data)
    fraction_fixes = repair_ocr_preparation_fractions(image, rows, lang, cancelled)
    original = "\n".join(_ocr_line_text(row) for row in rows)
    substantial = [row for row in rows if len(_ocr_line_text(row)) >= 30
                   and len(re.findall(r"[A-Za-zÀ-ÿ]{3,}", _ocr_line_text(row))) >= 4]
    if not substantial:
        return original
    top = max(0, min(w["y"] for row in substantial for w in row) - 10)
    readable_words = [w for row in rows for w in row if w["y"] >= top
                      and w["conf"] >= 30 and re.search(r"[A-Za-zÀ-ÿ]{3,}", w["text"])]
    bottom = min(image.height, max(w["y"] + w["h"] for w in readable_words) + 16) if readable_words else image.height
    if cancelled():
        raise OperationCancelled("operation_cancelled")
    crop = image.crop((0, top, image.width, bottom))
    crop = ImageOps.autocontrast(ImageOps.grayscale(crop))
    crop = crop.resize((crop.width * 2, crop.height * 2), Image.Resampling.LANCZOS)
    reread = pytesseract.image_to_string(crop, lang=lang,
                                        config="--oem 3 --psm 6", timeout=20).strip()
    if _ocr_plausible_line_count(reread) >= max(2, _ocr_plausible_line_count(original) * .7):
        # Si la première lecture a perdu une mesure, la seconde peut
        # confondre une fraction avec son seul dénominateur (½ → 2).
        # Signaler cette divergence plutôt que valider le nouveau nombre.
        for match in re.finditer(r"\b(et|:)\s+(cs|cas|cac|ml|cl|g)\b", original, re.I):
            prefix, unit = match.groups()
            pattern = rf"({re.escape(prefix)}\s+)(?:\d+(?:[.,]\d+)?|[%¼½¾])\s*({re.escape(unit)})\b"
            reread = re.sub(pattern, lambda m: m[1] + "[" + t("importphoto_measure_check") + "] " + m[2], reread, flags=re.I)
        reread = apply_ocr_verified_fractions(reread, original, fraction_fixes)
        return restore_ocr_spacing(reread, original)
    return original


def _parse_ocr_quantity(value):
    value = (value or "").strip()
    if not value:
        return None
    if value in OCR_UNICODE_FRACTIONS:
        return OCR_UNICODE_FRACTIONS[value]
    mixed = re.fullmatch(r"(\d+)\s*([%s])" % "".join(OCR_UNICODE_FRACTIONS), value)
    if mixed:
        return int(mixed.group(1)) + OCR_UNICODE_FRACTIONS[mixed.group(2)]
    fraction = re.fullmatch(r"(?:(\d+)\s+)?(\d+)\s*/\s*(\d+)", value)
    if fraction:
        whole, numerator, denominator = fraction.groups()
        if not int(denominator):
            return None
        return int(whole or 0) + int(numerator) / int(denominator)
    return parse_quantity_token(value)


def parse_ocr_ingredient_table_line(line):
    """Analyse le format OCR courant ``nom quantité unité`` de HelloFresh."""
    cleaned = re.sub(r"^[•*+\-]\s*", "", (line or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned or OCR_NON_INGREDIENT_RE.search(cleaned):
        return None
    # Supprime les astérisques de conservation accolés au nom.
    cleaned = re.sub(r"\*+(?=\s|$)", "", cleaned).strip()
    unit_pattern = (
        r"kg|gr|g|ml|cl|l|cas|cac|cs|pi[eèé]ce(?:\(s\)|s)?|"
        r"sachet(?:\(s\)|s)?|barquette(?:\(s\)|s)?|filet(?:\(s\)|s)?|"
        r"bo[iî]te(?:\(s\)|s)?|paquet(?:\(s\)|s)?|tranche(?:\(s\)|s)?"
    )
    quantity_pattern = r"(?:\d+\s+\d+\s*/\s*\d+|\d+\s*/\s*\d+|\d+(?:[.,]\d+)?(?:\s*[{}])?|[{}])".format(
        "".join(OCR_UNICODE_FRACTIONS), "".join(OCR_UNICODE_FRACTIONS)
    )
    match = re.match(
        rf"^(?P<name>.+?)\s+(?P<qty>{quantity_pattern})\s*(?P<unit>{unit_pattern})(?![A-Za-zÀ-ÿ])",
        cleaned,
        re.IGNORECASE,
    )
    if match:
        quantity = _parse_ocr_quantity(match.group("qty"))
        if quantity is None:
            return None
        raw_unit = ingredient_sort_key(match.group("unit")).replace("(s)", "")
        unit_map = {
            "g": "Gr", "gr": "Gr", "kg": "Kilo", "ml": "ml", "cl": "cl",
            "l": "Litre", "cs": "cuillère à soupe", "cas": "cuillère à soupe",
            "cac": "cuillère à café", "piece": "pièce", "pieces": "pièce",
            "sachet": "sachet", "sachets": "sachet", "barquette": "barquette",
            "barquettes": "barquette", "filet": "filet", "filets": "filet",
            "boite": "boîte", "boites": "boîte", "paquet": "paquet",
            "paquets": "paquet", "tranche": "tranche", "tranches": "tranche",
        }
        name = match.group("name").strip(" .:;|[]\"“”")
        if name:
            return {
                "name": name.capitalize(),
                "quantity": quantity,
                "unit": unit_map.get(raw_unit, match.group("unit")),
            }
    # « % » ne permet pas de distinguer ¼, ½ ou ¾. Ne jamais inventer 1.
    # Une relecture ciblée de l'image est tentée en amont ; si elle échoue,
    # le formulaire conserve l'ingrédient avec une quantité vide à vérifier.
    uncertain_fraction = re.match(
        rf"^(?P<name>.+?)\s+[%‰]\s*(?P<unit>{unit_pattern})(?![A-Za-zÀ-ÿ])",
        cleaned,
        re.IGNORECASE,
    )
    if uncertain_fraction:
        return {
            "name": uncertain_fraction.group("name").strip().capitalize(),
            "quantity": None,
            "unit": ingredient_sort_key(uncertain_fraction.group("unit")).replace("(s)", ""),
            "ocr_uncertain": True,
        }
    # Confusion OCR fréquente entre le chiffre « 1 » et les lettres i/l
    # devant « cs » (ex. « Beurre ics » sur la photo de test réelle).
    misread_one = re.match(
        r"^(?P<name>.+?)\s+[il|]cs\b", cleaned, re.IGNORECASE
    )
    if misread_one:
        return {
            "name": misread_one.group("name").strip().capitalize(),
            "quantity": None,
            "unit": "cuillère à soupe",
            "ocr_uncertain": True,
        }
    if re.search(
        r"selon\s+(?:votre\s+)?(?:go[uû]t|[A-Za-zÀ-ÿ]{3,})|au\s+go[uû]t",
        cleaned,
        re.IGNORECASE,
    ):
        name = re.split(r"\s+(?:selon|au)\s+", cleaned, maxsplit=1, flags=re.IGNORECASE)[0]
        return {"name": name.capitalize(), "quantity": None, "unit": "au goût"}
    missing_number = re.match(
        rf"^(?P<name>.+?)\s+(?P<unit>{unit_pattern})(?![A-Za-zÀ-ÿ])(?:\s*[.|]*)$",
        cleaned, re.IGNORECASE,
    )
    if missing_number:
        # Réutilise la conversion des unités, sans conserver la valeur
        # technique temporaire nécessaire pour analyser la ligne.
        parsed = parse_ocr_ingredient_table_line(
            missing_number.group("name") + " 1 " + missing_number.group("unit")
        )
        if parsed:
            parsed.update(quantity=None, ocr_uncertain=True)
        return parsed
    # Un chiffre+unité peut être entièrement déformé (ex. « ES »).
    # Conserver le nom lisible dans le tableau, sans inférer la mesure.
    garbled = re.fullmatch(r"(?P<name>[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'’ -]+?)\s+[A-Z]{1,3}\s*[.|]*", cleaned)
    if garbled:
        return {"name": garbled.group("name").strip().capitalize(),
                "quantity": None, "unit": "", "ocr_uncertain": True}
    return None


def clean_ocr_preparation(text):
    """Rejoint les lignes imprimées, en conservant paragraphes et étapes."""
    paragraphs, current = [], []
    def flush():
        if current:
            paragraphs.append(" ".join(current))
            current.clear()
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            flush()
            continue
        line = re.sub(r"^[^A-Za-zÀ-ÿ0-9]+", "", line)
        line = re.sub(r"^(?:[a-zà-ÿ]{1,2}\s*)?[•+|°*«_]+\s*", "", line)
        line = re.sub(r"^[a-zà-ÿ]{1,2}\s+(?=[A-ZÀ-ÖØ-Þ][a-zà-ÿ]{3})", "", line)
        if not re.search(r"[A-Za-zÀ-ÿ]{2,}|\d", line):
            continue
        if re.match(r"^(?:Veillez|Préchauffez|Portez|Ciselez|Épluchez|Égouttez|Dans un|Versez|Placez|Répartissez|Ajoutez|Enfournez|Réduisez|Incorporez|Servez|Disposez|Ajustez|L['’]ASTUCE DU CHEF)", line):
            flush()
        # Espaces perdus entre un impératif fréquent et son complément.
        line = re.sub(r"\b(Ajoutez|Versez|Réduisez|Incorporez|Placez-y|Épluchez|Ciselez)(?=(?:le|la|les|un|une)\b|l['’])", r"\1 ", line)
        line = re.sub(r"\b(Versez)(un)(filet)\b", r"\1 \2 \3", line)
        line = re.sub(r"^[a-zà-ÿ],\s+", "", line)
        line = re.sub(r"\bunfilet\b", "un filet", line)
        line = re.sub(r"\b([A-Za-zÀ-ÿ]+-les)en\b", r"\1 en", line)
        line = re.sub(r"\bavecun\b", "avec un", line)
        line = re.sub(r"\bpourl['’]onctuosité", "pour l'onctuosité", line)
        current.append(line)
    flush()
    return "\n\n".join(paragraphs)


def parse_photo_ocr_recipe(raw_text):
    """Transforme le texte multi-photo en préremplissage de recette fiable."""
    text_value = (raw_text or "").replace("\r", "")
    lines = [re.sub(r"\s+", " ", line).strip() for line in text_value.splitlines()]
    nonempty = [line for line in lines if line and not re.match(r"^-{2,}.*-{2,}$", line)]

    persons = None
    persons_match = re.search(
        r"\b(?:ingr[eé]dients?\s+pour\s+)?(\d+)\s*"
        r"(?:personnes?|convives?|portions?|parts?)\b",
        text_value, re.IGNORECASE,
    )
    if persons_match:
        persons = max(1, int(persons_match.group(1)))

    prep_time = ""
    time_match = re.search(
        r"(?:[àa]\s+table\s+dans|temps\s+total|pr[eê]t\s+en)\s*:?\s*"
        r"(\d+)\s*(?:[-–—]\s*(\d+))?\s*(?:min|minutes?)",
        text_value, re.IGNORECASE,
    )
    if time_match:
        first_time = int(time_match.group(1))
        second_time = int(time_match.group(2)) if time_match.group(2) else None
        # « 35 » est parfois lu « 385 ». Une durée incohérente placée avant
        # une borne haute plausible ne doit pas remplir le formulaire avec
        # plusieurs centaines de minutes.
        if second_time and first_time > second_time:
            first_time = second_time
        if first_time <= 24 * 60:
            prep_time = str(first_time)

    name = ""
    for index, line in enumerate(nonempty):
        key = ingredient_sort_key(line)
        if any(marker in key for marker in ("ingredients pour", "mes ustensiles", "valeurs nutritionnelles")):
            continue
        if re.search(r"[A-Za-zÀ-ÿ]{3,}.*[A-Za-zÀ-ÿ]{3,}", line) and len(line) <= 110:
            if re.search(r"[àa]\s+table\s+dans", line, re.IGNORECASE):
                continue
            name = line.strip(" )|;:.-")
            name = re.sub(r"^[A-Za-z][)\]]\s+", "", name)
            name = re.sub(
                r"^[^A-Za-zÀ-ÿ]*[A-Za-zÀ-ÿ]\s+(?=[A-ZÀ-ÖØ-Þ])",
                "",
                name,
            )
            for following in nonempty[index + 1:index + 4]:
                following = following.lstrip(" |:;.")
                if re.match(r"^(?:avec|with|con|mit)\b", following, re.IGNORECASE):
                    name += " " + following.strip()
                    break
            break

    ingredients = []
    ingredient_start = next((
        i for i, line in enumerate(lines)
        if re.search(r"ingr[eé]dients?\s+(?:pour|for|para|f[uü]r)", line, re.IGNORECASE)
    ), None)
    if ingredient_start is not None:
        for line in lines[ingredient_start + 1:]:
            if OCR_INGREDIENT_BOUNDARY_RE.search(line):
                break
            parsed = parse_ocr_ingredient_table_line(line)
            if parsed:
                ingredients.append(parsed)

    # Le stockage interne est par personne. La table photographiée contient
    # les totaux pour toute la recette : division unique, après détection du
    # nombre final de personnes (même si ce nombre vient d'une autre photo).
    if persons:
        for ingredient in ingredients:
            if ingredient["quantity"] is not None:
                ingredient["quantity"] = ingredient["quantity"] / persons

    # Ne place plus toute la page de couverture/nutrition dans la préparation.
    # Les pages riches en verbes d'action sont conservées dans leur ordre OCR ;
    # pour HelloFresh, cet ordre a déjà été corrigé par ocr_grid_cells.
    description_pages = []
    pages = re.split(
        r"(?m)^(?:-{2,}|={2,})\s*(?:Photo|Foto)\s+\d+\s*(?:-{2,}|={2,})\s*$",
        text_value,
    )
    for page in pages:
        normalized = ingredient_sort_key(page)
        action_markers = (
            "prechauff", "enfourn", "faites", "ajoutez", "melangez", "servez",
            "cuisson", "egouttez", "epluchez", "repartissez", "disposez",
        )
        actions = sum(marker in normalized for marker in action_markers)
        if (
            actions >= 2
            and _ocr_plausible_line_count(page) >= 4
            and "ingredients pour" not in normalized
            and "valeurs nutritionnelles" not in normalized
        ):
            description_pages.append(clean_ocr_preparation(page))
    description = "\n\n".join(description_pages).strip()

    return {
        "name": name[:100],
        "description": description[:12000],
        "ingredients": ingredients,
        "ocr_warnings": ([i["name"] for i in ingredients if i.get("ocr_uncertain")]
                         + ([t("recipeform_tab_preparation")] if "[" + t("importphoto_measure_check") + "]" in description else [])),
        "prep_time": prep_time,
        "cook_time": "",
        "default_persons": persons or 4,
        "quantity_basis": "per_person",
    }


def parse_iso8601_duration_minutes(duration):
    """Convertit une durée ISO 8601 (ex. 'PT1H30M') en nombre de minutes."""
    if not duration:
        return None
    match = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?)?", str(duration).strip(), re.I)
    if not match:
        return None
    days, hours, minutes, seconds = (float(v or 0) for v in match.groups())
    total = int(days * 1440 + hours * 60 + minutes + seconds / 60 + 0.5)
    return total if total > 0 else None


def _find_recipe_jsonld(data):
    """Cherche récursivement un objet Schema.org de type Recipe dans une
    structure JSON-LD (qui peut être un objet, une liste, ou contenir
    '@graph')."""
    if isinstance(data, dict):
        type_value = data.get("@type")
        types = type_value if isinstance(type_value, list) else [type_value]
        if any(t and "recipe" in str(t).lower() for t in types):
            return data
        if "@graph" in data:
            found = _find_recipe_jsonld(data["@graph"])
            if found:
                return found
        for value in data.values():
            found = _find_recipe_jsonld(value)
            if found:
                return found
    elif isinstance(data, list):
        for item in data:
            found = _find_recipe_jsonld(item)
            if found:
                return found
    return None


_MICRODATA_VOID_TAGS = ('meta', 'img', 'input', 'br', 'hr', 'link', 'source', 'wbr')


class _MicrodataRecipeParser(HTMLParser):
    """Repli pour les sites (souvent plus anciens) qui décrivent leur recette
    avec l'attribut HTML ``itemprop``/``itemscope`` (microdonnées Schema.org)
    plutôt qu'avec un bloc JSON-LD. Reconstruit un dictionnaire de même forme
    que celui retourné par ``_find_recipe_jsonld``, pour être traité ensuite
    exactement de la même façon."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.scope_depth = None
        self.scope_closed = False
        self.active_props = []  # [(prop, depth, [texte...])]
        self.values = {}

    def _record(self, prop, value):
        if value is None:
            return
        self.values.setdefault(prop, []).append(value)

    def handle_starttag(self, tag, attrs):
        if self.scope_closed:
            return
        attrs = dict(attrs)
        is_void = tag in _MICRODATA_VOID_TAGS
        if self.scope_depth is None:
            item_type = attrs.get('itemtype', '')
            if 'itemscope' in attrs and 'recipe' in item_type.lower():
                self.scope_depth = len(self.stack)
        elif len(self.stack) < self.scope_depth:
            self.scope_closed = True
            return

        prop = attrs.get('itemprop')
        if prop and self.scope_depth is not None:
            if 'content' in attrs:
                self._record(prop, attrs['content'])
            elif tag == 'img':
                self._record(prop, attrs.get('src'))
            elif tag == 'time' and attrs.get('datetime'):
                self._record(prop, attrs['datetime'])
            elif not is_void:
                self.active_props.append((prop, len(self.stack), []))

        if not is_void:
            self.stack.append(tag)

    def handle_data(self, data):
        for _, _, buffer in self.active_props:
            buffer.append(data)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i] == tag:
                del self.stack[i:]
                break
        else:
            return
        remaining = []
        for prop, depth, buffer in self.active_props:
            if depth >= len(self.stack):
                text = "".join(buffer).strip()
                if text:
                    self._record(prop, text)
            else:
                remaining.append((prop, depth, buffer))
        self.active_props = remaining
        if self.scope_depth is not None and len(self.stack) <= self.scope_depth:
            self.scope_closed = True


def _extract_microdata_recipe(page_html):
    """Retourne un dictionnaire façon JSON-LD si la page décrit une recette
    en microdonnées (``itemscope``/``itemprop``), ou ``None`` sinon."""
    parser = _MicrodataRecipeParser()
    try:
        parser.feed(page_html)
    except Exception as exc:
        log_internal_error("extract_microdata_recipe", exc)
        return None
    if parser.scope_depth is None:
        return None
    values = parser.values

    def first(prop):
        found = values.get(prop)
        return found[0] if found else None

    def many(prop):
        return values.get(prop) or []

    ingredients = many('recipeIngredient') or many('ingredients')
    if not ingredients:
        return None

    return {
        'name': first('name') or '',
        'description': first('description') or '',
        'recipeIngredient': ingredients,
        'recipeInstructions': many('recipeInstructions'),
        'image': first('image'),
        'prepTime': first('prepTime'),
        'cookTime': first('cookTime'),
        'recipeYield': first('recipeYield'),
        'recipeCategory': first('recipeCategory'),
    }



# Import-only vocabulary: do not change OCR or pantry measurement semantics.
_URL_UNITS = {
 'cup cups taza tazas tasse tassen': 'cup',
 'tbsp tablespoon tablespoons cucharada cucharadas el esslöffel essloffel': 'cuillère à soupe',
 'tsp teaspoon teaspoons cucharadita cucharaditas tl teelöffel teeloffel': 'cuillère à café',
 'pinch pinches pizca pizcas prise prisen': 'pincée',
 'packet packets sobre sobres päckchen packchen': 'sachet',
 'drizzle chorrito chorro schuss': 'filet',
 'roll rolls rollo rollos rolle rollen': 'rouleau',
 'can cans tin tins lata latas dose dosen': 'boîte',
 'clove cloves diente dientes zehe zehen': 'gousse',
 'ounce ounces oz': 'oz', 'pound pounds lb lbs': 'lb',
 'gram grams gramo gramos gramm': 'Gr',
 'milliliter milliliters millilitre millilitres mililitro mililitros': 'ml',
}
_URL_FOOD_ALIASES = {
 '0% fat free greek yoghurt': 'Yaourt', 'huevo': 'Œuf', 'huevos': 'Œufs', 'ei': 'Œuf', 'eier': 'Œufs',
 'egg': 'Œuf', 'eggs': 'Œufs', 'oeuf': 'Œuf', 'oeuf(s)': 'Œufs',
 'buttermilk': 'Babeurre', 'sour cream': 'Crème aigre', 'kosher salt': 'Sel',
 'warm maple syrup': "Sirop d’érable",
 'arroz blanco': 'Riz', 'baking powder': 'Levure chimique',
 'plain flour': 'Farine', 'all-purpose flour': 'Farine', 'all purpose flour': 'Farine',
 'flour': 'Farine', 'large eggs': 'Œufs', 'large egg': 'Œuf',
 'egg yolks': "Jaune d'œuf", 'egg whites': "Blanc d'œuf",
 'semi skimmed milk': 'Lait', 'queso rallado cuatro quesos': 'Fromage',
}

def _url_food_name(name):
    # Qualifiers and alternatives must never be erased by a generic mapping.
    key = ingredient_sort_key(name).replace('œ', 'oe')
    if key in _URL_FOOD_ALIASES:
        return normalize_oe(_URL_FOOD_ALIASES[key])
    if re.search(r"\b(?:sans|free|vegan|vegetal\w*|sin|frei\w*|ohne|or|ou|oder|o)\b", key):
        return name
    leading = re.match(r'^((?:\([^()]*\)\s*)+)(.+)$', key)
    if leading:
        key = leading.group(2).strip()
    base = re.split(r'[,()]', key)[0].strip()
    base = re.sub(r'\s+(?:picado|picada|rallado|rallada|sifted|melted|chopped|beaten)$', '', base)
    canonical = _URL_FOOD_ALIASES.get(base)
    if canonical is None:
        candidates = set()
        for lang in ('en', 'es', 'de'):
            for fr, foreign in load_ingredient_translations(lang).items():
                if ingredient_sort_key(foreign) == base:
                    candidates.add(fr.capitalize())
        if len(candidates) == 1:
            canonical = candidates.pop()
    if not canonical:
        return name
    canonical = normalize_oe(canonical)
    if ingredient_sort_key(canonical) == key and not leading:
        return name
    # Keep source qualifiers available to the cook, with a canonical food prefix.
    return canonical if base == key and not leading else f'{canonical} — {name}'


def _url_fraction_text(text):
    text = str(text).replace('⁄', '/').replace('∕', '/')
    for symbol, replacement in {'½':'1/2','¼':'1/4','¾':'3/4','⅓':'1/3','⅔':'2/3','⅛':'1/8','⅜':'3/8','⅝':'5/8','⅞':'7/8'}.items():
        text = re.sub(r'(?<=\d)' + symbol, ' ' + replacement, text)
        text = text.replace(symbol, replacement)
    return text


def _url_quantity_range(line):
    number = r'(?:\d+\s+\d+/\d+|\d+/\d+|\d+(?:[.,]\d+)?)'
    return re.match(r'^(' + number + r')\s*(?:to|à|a|bis|[-–—])\s*(' + number + r')(?=\s|$)', _url_fraction_text(line), re.I)


def _parse_url_ingredient(line):
    line = _url_fraction_text(line)
    quantity_range = _url_quantity_range(line)
    if quantity_range:
        line = quantity_range.group(1) + line[quantity_range.end():]
    line = re.sub(r"\b(sachet|pincée|cuillerée|filet|rouleau)\(s\)", r"\1", line, flags=re.I)
    line = re.sub(r"^(?:une?|a|an)\s+", "1 ", line.strip(), flags=re.I)
    # A fish/meat fillet is the food itself, unlike a drizzle of oil.
    food_fillet = re.match(r"^(\d+(?:[.,]\d+)?)\s+(filets?\s+(?:de |d['’]).+)$", line, re.I)
    if food_fillet and not re.search(r"\b(?:huile|vinaigre|jus|miel|crème|sauce)\b", food_fillet.group(2), re.I):
        return {'name': food_fillet.group(2).capitalize(), 'quantity': float(food_fillet.group(1).replace(',', '.')), 'unit': 'pièce'}
    # Yogurt pots are volumes of unknown capacity, not weights.
    normalized = re.sub(
        r"\bpots?\s+(?:de|à|a)\s+yaourts?(?:\s+vides?)?\s+(?:de\s+|d['’])",
        "pot-mesure ", line, flags=re.I)
    # An unnamed amount keeps its measure without inventing a count.
    for aliases, canonical in _URL_UNITS.items():
        pattern = r'(?<!\w)(?:' + '|'.join(re.escape(a) for a in aliases.split()) + r')\.?(?=\s|$)'
        # Only the measure slot after a quantity (or at the start).
        match = re.match(r'^(?P<qty>(?:[\d.,/½¼¾⅓⅔]+\s+){0,2})(?P<rest>.*)$', normalized)
        if match:
            normalized = match['qty'] + re.sub(pattern, canonical, match['rest'], count=1, flags=re.I) if re.match(pattern, match['rest'], re.I) else normalized
    tokens = normalized.split()
    unit, end = _match_unit_tokens(tokens, 0)
    if unit and len(tokens) > end:
        name = re.sub(r"^(?:de |d['’])", "", ' '.join(tokens[end:]), flags=re.I)
        return {'name': name.capitalize(), 'quantity': None, 'unit': unit}
    measured = parse_ingredient_line(normalized)
    if not measured:
        return None
    measured['name'] = measured['name'].replace('pot-mesure', 'pot de yaourt')
    # Explicit weight per sachet: retain the food name and use the stated mass.
    if measured['unit'] == 'sachet':
        weight = re.search(r"\s*\((\d+(?:[.,]\d+)?)\s*g\)\s*$", measured['name'], re.I)
        if weight:
            measured['quantity'] *= float(weight.group(1).replace(',', '.'))
            measured['name'] = measured['name'][:weight.start()].strip()
            measured['unit'] = 'Gr'
    measured['name'] = _url_food_name(measured['name'])
    return measured


class _RecipePageMetadata(HTMLParser):
    """Read labelled recipe metadata only, excluding scripts and navigation."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.in_header = False
        self.await_note = False
        self.await_rest = False
        self.values = {'difficulty': [], 'notes': [], 'category': [], 'rest': [], 'yield': []}
        self.ingredients = []
        self.ingredient_depth = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'h1':
            self.in_header = True
        classes = attrs.get('class', '').lower()
        prop = attrs.get('itemprop', '')
        kind = None
        if prop == 'recipeYield':
            kind = 'yield'
        elif prop == 'recipeCategory' or 'recipe-course' in classes:
            kind = 'category'
        elif prop == 'restTime' or any(x in classes for x in ('recipe-rest-time', 'recipe-custom-time', 'recipe-rest_time', 'recipe-custom_time')):
            kind = 'rest'
        elif prop == 'difficulty' or 'recipe-difficulty' in classes or 'recipe-primary__item' in classes:
            kind = 'difficulty'
        elif 'recipe-notes' in attrs.get('id', '').lower() or 'recipe-notes' in classes or 'recipe-note' in classes or 'recipe-author-note' in classes or 'recipe-advice-content' in classes:
            kind = 'notes'
        elif self.await_note and tag in ('p', 'div', 'blockquote'):
            kind = 'notes'
            self.await_note = False
        if self.ingredient_depth is None and (prop == 'recipeIngredient' or
                any(c in classes.split() for c in ('wprm-recipe-ingredient', 'recipe-ingredient'))):
            self.ingredients.append([attrs['content']] if attrs.get('content') else [])
            if tag not in ('meta', 'img', 'input', 'br', 'hr', 'link', 'source', 'wbr'):
                self.ingredient_depth = len(self.stack)
        if tag not in ('meta','img','input','br','hr','link','source','wbr'):
            self.stack.append((tag, kind))
        if kind and attrs.get('content'):
            self.values[kind].append(attrs['content'])

    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                if self.ingredient_depth is not None and len(self.stack) <= self.ingredient_depth:
                    self.ingredient_depth = None
                break

    def handle_data(self, data):
        if any(tag in ('script','style','nav','aside','footer') for tag, _ in self.stack):
            return
        if self.ingredient_depth is not None:
            self.ingredients[-1].append(data)
        key = ingredient_sort_key(data.strip()).strip(' :')
        rest_label = re.fullmatch(r'(?:temps de )?repos\b\s*:?\s*(.*)', data.strip(), re.I)
        if rest_label:
            value = rest_label.group(1).strip()
            if value:
                self.values['rest'].append(value)
            else:
                self.await_rest = True
            return
        if self.await_rest and data.strip():
            if re.fullmatch(r'\d+(?:[.,]\d+)?\s*(?:h(?:eures?)?|min(?:utes?)?|jours?)(?:\s*\d+\s*(?:min(?:utes?)?)?)?', data.strip(), re.I):
                self.values['rest'].append(data.strip())
            self.await_rest = False
        if key == 'ingredients':
            self.in_header = False
        if self.in_header and key in ('tres facile', 'facile', 'moyen', 'difficile'):
            self.values['difficulty'].append(data)
        if key in ('astuces', 'notes', 'tips', 'tipps') and any(tag in ('h2','h3','h4') for tag, _ in self.stack):
            self.await_note = True
            return
        if key in ("note de l'auteur", "note de l’auteur", 'recipe notes', 'author notes', 'notas', 'notas del autor', 'anmerkungen'):
            self.await_note = True
            return
        active = {kind for _, kind in self.stack if kind}
        if self.await_note and data.strip() and key not in ('«', '»'):
            if 'notes' not in active:
                self.values['notes'].append(data)
            self.await_note = False
        if 'notes' in active and key in ('conseils', 'astuces'):
            active.remove('notes')
        if re.search(r'\bpour\s+(?:environ\s+)?(?:une?\s+\w+aine|\d+(?:\s*[-–]\s*\d+)?)\s+(?:de\s+)?(?:crepes?|cookies?|biscuits?)\b', key):
            if any(tag in ('h2', 'h3', 'h4', 'h5', 'h6') for tag, _ in self.stack):
                self.values['yield'].append(data.strip())
        for kind in active:
            self.values[kind].append(data)


def _url_recipe_metadata(data, page, clean):
    parser = _RecipePageMetadata()
    parser.feed(page)
    raw_category = clean(data.get('recipeCategory') or parser.values['category'] or data.get('name'))
    category_key = ingredient_sort_key(raw_category)
    categories = {
        r'petits?[- ]dejeuners?|breakfast|desayunos?|fruhstuck': 'Petit-déjeuner',
        r'quiches?|cakes? sales?|tartes? salees?|dejeuners?|diners?|main courses?|plats?|hauptgerichte?|platos? principales?': 'Plat',
        r'desserts?|gateaux?|cookies?|biscuits?|patisseries?|crepes?|pancakes?|gaufres?|postres?|nachtisch|nachspeisen?': 'Dessert',
        r'entrees?': 'Entrée', r'boissons?': 'Boisson', r'sauces?': 'Sauce',
        r'aperitifs?|aperos?': 'Apéro',
    }
    category = next((value for pattern, value in categories.items()
                     if re.search(r'\b(?:'+pattern+r')\b', category_key)), 'Autre')
    raw_difficulty = clean(data.get('difficulty') or parser.values['difficulty'])
    diff_key = ingredient_sort_key(raw_difficulty)
    difficulties = [('tres facile','Très facile'), ('very easy','Très facile'), ('facile','Facile'),
                    ('easy','Facile'), ('moyen','Moyen'), ('difficile','Difficile')]
    difficulty = next((value for key, value in difficulties if re.search(r'\b'+re.escape(key)+r'\b', diff_key)), '')
    notes = clean(data.get('recipeNotes') or parser.values['notes'])
    rest = clean(data.get('restTime') or parser.values['rest'])
    rest = re.sub(r'\b(minutes?|min)\s+(?:minutes?|min)\b', r'\1', rest, flags=re.I)
    if rest in ('-', '—', '0'):
        rest = ''
    if rest:
        minutes = parse_iso8601_duration_minutes(rest)
        notes = '\n\n'.join(x for x in (notes, t('importurl_rest_note', value=f'{minutes} min' if minutes is not None else rest)) if x)
    return category, difficulty, notes


def _url_ingredient_parts(line):
    """Split explicit additions, never alternatives or parenthesized text."""
    if re.fullmatch(r"sel\s+(?:et|&)\s+poivre(?:\s+au\s+go[ûu]t)?", line, re.I):
        return ['sel', 'poivre']
    parts, start, depth = [], 0, 0
    for match in re.finditer(r"[()]|\s+(?:\+|et)\s+(?=\d|[½¼¾⅓⅔])", line, re.I):
        token = match.group()
        if token == "(":
            depth += 1
        elif token == ")":
            depth = max(0, depth - 1)
        elif depth == 0:
            parts.append(line[start:match.start()].strip())
            start = match.end()
    parts.append(line[start:].strip())
    return [part for part in parts if part]


def _url_ingredient_heading(line):
    # Exact headings only: do not discard real ingredients such as pâte brisée.
    key = ingredient_sort_key(line).strip(" :")
    return key in {"pate", "garniture", "pour la pate", "pour la garniture",
                   "ingredients", "pour la sauce", "pour le decor", "decoration",
                   "for the pancakes", "for the sauce", "for the filling", "to serve",
                   "para la salsa", "para la masa", "para servir", "fur den teig", "zum servieren"}


def _url_instruction_texts(value, clean):
    if isinstance(value, str):
        text = clean(value)
        return [text] if text else []
    if isinstance(value, list):
        return [text for item in value for text in _url_instruction_texts(item, clean)]
    if isinstance(value, dict):
        children = value.get("itemListElement")
        if children:
            return _url_instruction_texts(children, clean)
        return _url_instruction_texts(value.get("text") or value.get("name") or "", clean)
    return []


def _url_clean_steps(steps):
    cooking, notes = [], []
    supplementary = False
    action = re.compile(r"^(?:vous\s+|pr[ée]chauff|faites|m[ée]lang|ajout|vers|coupez|[ée]pluch|mette|enfourn)", re.I)
    for text in steps:
        text = re.sub(r"^\s*\d+[.)]\s+", "", text).strip()
        if re.match(r"^Voici les produits particuliers de cette recette\b", text, re.I):
            notes.append(text)
            continue
        if re.match(r"^(?:variantes?|FAQ|questions fr[ée]quentes|conseils|astuces|tips|recipe notes|notas|tipps)\s*(?::|[\r\n]|$)", text, re.I):
            supplementary = True
        if supplementary:
            notes.append(text)
            continue
        paragraphs = [x.strip() for x in re.split(r"[\r\n]+", text) if x.strip()]
        # Only move a separated introduction before a clearly recognized action.
        if not cooking and len(paragraphs) > 1 and not action.match(paragraphs[0]):
            action_at = next((i for i, x in enumerate(paragraphs) if action.match(x)), None)
            if action_at is not None:
                notes.extend(paragraphs[:action_at])
                text = "\n".join(paragraphs[action_at:])
        if text:
            cooking.append(text)
    return cooking, notes


def _decompress_recipe_page(raw, content_encoding):
    """Décompresse le corps de la réponse selon Content-Encoding.

    Nécessaire uniquement parce que la requête annonce désormais
    Accept-Encoding (voir fetch_recipe_from_url) : certains sites ne
    répondent en 200 qu'à cette condition, sans quoi ils renvoient un
    403 (protection anti-robot qui juge une requête sans cet en-tête
    trop "nue"). "deflate" est ambigu en pratique (RFC 1950 zlib le
    plus souvent, mais RFC 1951 brut chez certains serveurs) : on
    tente les deux plutôt que d'échouer sur un site qui répondrait
    dans l'variante la moins courante."""
    encoding = (content_encoding or "").lower()
    if encoding == "gzip":
        return gzip.decompress(raw)
    if encoding == "deflate":
        try:
            return zlib.decompress(raw)
        except zlib.error:
            return zlib.decompress(raw, -zlib.MAX_WBITS)
    return raw


def _download_recipe_page(request):
    """Retry once on transient failures, never on 403 access denials."""
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                length = response.headers.get("Content-Length")
                if length and int(length) > MAX_WEB_PAGE_BYTES:
                    raise RuntimeError("La page est trop volumineuse pour être importée en sécurité.")
                request.recipe_final_url = response.geturl() if hasattr(response, 'geturl') else request.full_url
                raw = _read_response_limited(response, MAX_WEB_PAGE_BYTES)
                raw = _decompress_recipe_page(raw, response.headers.get("Content-Encoding"))
                charset = response.headers.get_content_charset() or "utf-8"
                return raw.decode(charset, errors="replace")
        except urllib.error.HTTPError as exc:
            if attempt or exc.code not in (502, 503, 504):
                raise
            exc.close()
        except (TimeoutError, urllib.error.URLError) as exc:
            if attempt or not (isinstance(exc, TimeoutError) or isinstance(getattr(exc, 'reason', None), TimeoutError)):
                raise


def fetch_recipe_from_url(url):
    """Télécharge une page de recette et tente d'en extraire le contenu à
    partir des données structurées Schema.org (JSON-LD), un format utilisé
    par la grande majorité des sites de recettes. Lève une exception avec un
    message clair en cas d'échec.

    Les en-têtes visent à ressembler à un vrai navigateur (Accept,
    Accept-Language, Accept-Encoding, puis les en-têtes Fetch Metadata et
    Client Hints ci-dessous) : une requête ne portant que User-Agent est
    parfois jugée suspecte par les protections anti-robot de certains
    sites (Wordfence, Cloudflare...), qui la bloquent avec un 403 même
    quand le User-Agent est crédible. Les en-têtes Sec-Fetch-*/sec-ch-ua
    sont envoyés par tout Chrome récent dès qu'une page est ouverte
    (URL tapée, favori...) ; certains WAF (dont Wordfence) les vérifient
    spécifiquement et bloquent leur absence, même avec un Accept-Encoding
    déjà présent. Malgré cela, certains sites restent bloqués : une
    protection basée sur l'empreinte TLS (JA3) ou la réputation de l'IP
    échappe à toute combinaison d'en-têtes HTTP."""
    request = urllib.request.Request(
        url, headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "sec-ch-ua": '"Not)A;Brand";v="99", "Google Chrome";v="128", "Chromium";v="128"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        }
    )
    try:
        page_html = _download_recipe_page(request)
    except urllib.error.HTTPError as e:
        raise RuntimeError(t("importurl_http_error", code=e.code)) from e
    except TimeoutError as e:
        raise RuntimeError(t("importurl_timeout_error")) from e
    except urllib.error.URLError as e:
        if isinstance(e.reason, TimeoutError):
            raise RuntimeError(t("importurl_timeout_error")) from e
        raise RuntimeError(t("importurl_network_error", detail=str(e.reason))) from e
    except Exception as e:
        raise RuntimeError(f"Erreur lors du téléchargement de la page : {e}") from e

    scripts = re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        page_html, flags=re.DOTALL | re.IGNORECASE
    )

    recipe_data = None
    for script in scripts:
        try:
            parsed = json.loads(script.strip())
        except (json.JSONDecodeError, ValueError):
            # Some publishers put literal newlines in JSON strings (750g).
            # Relax only control-character handling; never evaluate site code.
            try:
                parsed = json.loads(script.strip(), strict=False)
            except (json.JSONDecodeError, ValueError):
                continue
        found = _find_recipe_jsonld(parsed)
        if found:
            recipe_data = found
            break

    if recipe_data is None:
        # Certains sites (souvent plus anciens) décrivent leur recette avec
        # des attributs itemprop/itemscope en HTML plutôt qu'avec un bloc
        # JSON-LD : ce repli évite de rejeter la page à tort.
        recipe_data = _extract_microdata_recipe(page_html)

    if recipe_data is None:
        raise RuntimeError(
            "Aucune recette structurée n'a été trouvée sur cette page.\n\n"
            "Cet import fonctionne avec les sites qui utilisent le format "
            "standard « Schema.org Recipe » (la plupart des grands sites de "
            "cuisine). Vous pouvez toujours créer la recette manuellement."
        )

    def clean_text(value):
        if isinstance(value, list):
            value = " ".join(str(v) for v in value)
        cleaned = re.sub(r"<[^>]+>", " ", str(value or ""))
        # Certains sites (notamment 750g) fournissent encore des entités HTML
        # dans les chaînes JSON-LD, parfois même doublement encodées.
        for _ in range(3):
            decoded = html.unescape(cleaned)
            if decoded == cleaned:
                break
            cleaned = decoded
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)
        cleaned = cleaned.replace("\xa0", " ")
        return re.sub(r"[ \t]+", " ", cleaned).strip()

    final_url = getattr(request, 'recipe_final_url', None) or url
    warnings = []
    if urllib.parse.urlsplit(final_url).netloc.lower() != urllib.parse.urlsplit(url).netloc.lower():
        warnings.append({'key': 'importurl_warning_redirect', 'value': final_url})
    category, difficulty, source_notes = _url_recipe_metadata(recipe_data, page_html, clean_text)
    name = clean_text(recipe_data.get("name", "")) or "Recette importée"

    # Nombre de portions indiqué par le site.
    # L'application stocke ensuite les quantités d'ingrédients par personne.
    yield_parser = _RecipePageMetadata()
    yield_parser.feed(page_html)
    yield_value = recipe_data.get("recipeYield") or yield_parser.values["yield"]
    source_persons = None
    yield_note = ''
    if yield_value:
        yields = yield_value if isinstance(yield_value, list) else [yield_value]
        # Prefer explicit people when a publisher supplies both servings and pieces.
        people = next((v for v in yields if re.search(r'\b(?:personnes?|people|servings?|portions?|personas?|personen|raciones?|ración|pers\.?)(?:\b|$)', str(v), re.I)), None)
        pieces = next((v for v in yields if re.search(r'\b(?:cookies?|biscuits?|pièces?|pieces?|crêpes?|muffins?|pancakes?|stuck|stück|galletas?)\b', str(v), re.I)), None)
        if pieces is None:
            pieces = next((v for v in yields if re.match(r'^(?:makes|yields|ergibt|rinde)\b', str(v), re.I)), None)
        yield_value = people if people is not None else (None if pieces is not None else yields[0])
        if pieces is not None:
            yield_note = t('importurl_yield_note', value=clean_text(pieces))
        match = (re.search(r"(\d+(?:[.,]\d+)?)\s*(?:personnes?|people|servings?|portions?|personas?|personen|raciones?|ración|pers\b)", str(people), re.I)
                 if people is not None else re.search(r"\d+(?:[.,]\d+)?", str(yield_value or "")))
        people_range = _url_quantity_range(str(people or ''))
        if people_range:
            yield_note = '\n\n'.join(x for x in (yield_note, t('importurl_serving_range', value=clean_text(people))) if x)
            warnings.append({'key': 'importurl_serving_range', 'value': clean_text(people)})
        if match:
            try:
                source_persons = float((match.group(1) if people is not None else match.group()).replace(",", "."))
                if people_range:
                    source_persons = parse_quantity_token(people_range.group(1))
                if source_persons <= 0:
                    source_persons = None
            except ValueError:
                source_persons = None

    raw_ingredients = recipe_data.get("recipeIngredient") or recipe_data.get("ingredients") or []
    if isinstance(raw_ingredients, str):
        raw_ingredients = raw_ingredients.splitlines()
    # Supplement only explicitly marked ingredient rows, never prose/reviews.
    ingredient_page = _RecipePageMetadata()
    ingredient_page.feed(page_html)
    raw_ingredients = list(raw_ingredients)
    def ingredient_key(text):
        parsed = _parse_url_ingredient(clean_text(text))
        return re.sub(r'\s+', ' ', ingredient_sort_key(parsed['name']).replace('œ', 'oe').replace('(', ' ').replace(')', ' ')).strip().rstrip('s') if parsed else ''
    known_ingredient_keys = {ingredient_key(line) for line in raw_ingredients}
    for fragments in ingredient_page.ingredients:
        line = clean_text(' '.join(fragments))
        key = ingredient_key(line)
        if key and key not in known_ingredient_keys and not _url_ingredient_heading(line):
            raw_ingredients.append(line)
            known_ingredient_keys.add(key)
    ingredients = []
    # If portions are absent, keep totals consistent with the editable default.
    persons = source_persons or 4
    if not source_persons:
        warnings.append({"key": "importurl_warning_persons"})
    range_notes = []
    for line in raw_ingredients:
        line = clean_text(line)
        if _url_quantity_range(line):
            note = t("importurl_range_note", line=line, persons=persons)
            range_notes.append(note)
            warnings.append({"key": "importurl_warning_range", "line": line})
        if not line or _url_ingredient_heading(line):
            continue
        if re.search(r"\bou\b", line, re.I):
            warnings.append({"key": "importurl_warning_alternative", "line": line})
        for part in _url_ingredient_parts(line):
            parsed_ing = _parse_url_ingredient(part)
            if parsed_ing:
                if parsed_ing['unit'] == 'pièce' and re.match(r'^(?:scoops?|bags?|bundles?|bunches?|handfuls?|puñados?|handevoll)\b', parsed_ing['name'], re.I):
                    warnings.append({'key': 'importurl_warning_unit', 'value': part})
                if parsed_ing["unit"] == "au goût" or parsed_ing["quantity"] is None:
                    parsed_ing["quantity"] = None
                else:
                    parsed_ing["quantity"] = float(parsed_ing["quantity"]) / persons
                ingredients.append(parsed_ing)

    steps = _url_instruction_texts(recipe_data.get("recipeInstructions"), clean_text)
    steps, extra_notes = _url_clean_steps(steps)
    if not re.search(r'(?:repos|rest|ruhe)', source_notes, re.I):
        rest_match = re.search(r"\b(?:laisser|laissez)\s+reposer\s+((?:au moins\s+|environ\s+)?(?:\d+(?:[.,]\d+)?|une?|deux|trois|quatre)\s*(?:heures?|minutes?|jours?))", ' '.join(steps), re.I)
        if rest_match:
            extra_notes.append(t('importurl_rest_note', value=rest_match.group(1)))
    # Copy complete rest sentences: preserve optionality, temperature and context.
    for step in steps:
        for sentence in re.split(r'(?<=[.!?])\s+', step):
            if re.search(r'\b(?:rest|chill|refrigerat\w*|reposar|enfriar|nevera|ruhen|kuhl\w*|kühl\w*|esperamos|overnight)\b', sentence, re.I) and re.search(r'\b(?:\d+|overnight|dia siguiente|día siguiente|nacht)\b', sentence, re.I):
                if sentence not in source_notes:
                    extra_notes.append(t('importurl_rest_note', value=sentence))
    egg_mention = re.search(r"\b\d+\s+(?:(?:large|große)\s+)?(?:œufs?|oeufs?|eggs?|huevos?|eier)\b", ' '.join(steps), re.I)
    if egg_mention and not any(re.match(r'^(?:oeuf|œuf)', ingredient_sort_key(i['name'])) for i in ingredients):
        warning = {'key': 'importurl_warning_missing_ingredient', 'value': egg_mention.group()}
        warnings.append(warning)
        extra_notes.append(t(warning['key'], value=warning['value']))
    for pattern, food, present in (
        (r"(?:badigeonn\w*|graiss\w*|arros\w*)[^.!?]{0,70}\b(?:huile|oil)\b", 'huile', r'\b(?:huile|oil|beurre|butter)\b'),
        (r"\bsalez\b", 'sel', r'\b(?:sel|salt)\b'),
        (r"\bpoivrez\b", 'poivre', r'\b(?:poivre|pepper)\b'),
    ):
        if re.search(pattern, ' '.join(steps), re.I) and not any(re.search(present, i['name'], re.I) for i in ingredients):
            warning = {'key': 'importurl_warning_missing_ingredient', 'value': food}
            warnings.append(warning)
            extra_notes.append(t(warning['key'], value=food))
    if not recipe_data.get('cookTime'):
        for step in steps:
            for sentence in re.split(r'(?<=[.!?])\s+', step):
                if re.search(r'\b(?:enfourne\w*|cuire|cuisson|bake|cook)\b', sentence, re.I) and re.search(r'\d+\s*(?:min|heure|hour)', sentence, re.I):
                    extra_notes.append(t('importurl_step_time', value=sentence))
    source_notes = "\n\n".join(part for part in [source_notes, yield_note, *range_notes, *extra_notes] if part)
    description = "\n".join(f"{i + 1}. {text}" for i, text in enumerate(steps))
    if not steps:
        warnings.append({"key": "importurl_warning_steps"})

    prep_time = parse_iso8601_duration_minutes(recipe_data.get("prepTime"))
    cook_time = parse_iso8601_duration_minutes(recipe_data.get("cookTime"))

    if not prep_time:
        warnings.append({"key": "importurl_warning_prep"})
    if not cook_time:
        warnings.append({"key": "importurl_warning_cook"})
    total_time = parse_iso8601_duration_minutes(recipe_data.get('totalTime'))
    if total_time and (not prep_time or not cook_time):
        source_notes += ('\n\n' if source_notes else '') + t('importurl_total_note', value=total_time)
    default_persons = persons

    if not ingredients:
        raise RuntimeError(
            "Une recette a été trouvée sur cette page, mais aucun ingrédient "
            "n'a pu en être extrait. Vous pouvez créer la recette "
            "manuellement à la place."
        )

    # Récupération de la photo de la recette, si le site en indique une.
    image_sources = []
    image_url = _extract_recipe_image_url(recipe_data.get("image"))
    if image_url:
        image_url = urllib.parse.urljoin(final_url, image_url)
        downloaded = download_image_to_store(image_url, temporary=True, referer=final_url)
        if downloaded:
            image_sources.append(downloaded)

    return {
        "name": name[:100],
        "description": description[:12000],
        "ingredients": ingredients,
        "allergens": compute_recipe_allergens(ingredients),
        "prep_time": str(prep_time) if prep_time else "",
        "cook_time": str(cook_time) if cook_time else "",
        "default_persons": (
            int(default_persons) if default_persons and float(default_persons).is_integer()
            else (default_persons or 4)
        ),
        "images": [],
        "image_sources": image_sources,
        "temporary_image_sources": list(image_sources),
        "source_url": final_url,
        "category": category,
        "difficulty": difficulty,
        "personal_notes": source_notes,
        "quantity_basis": "per_person",
        "import_warnings": warnings,
    }


def _extract_recipe_image_url(image):
    """Extrait une URL d'image utilisable depuis le champ 'image' d'une
    donnée structurée Schema.org, qui peut prendre plusieurs formes :
    chaîne, liste de chaînes, objet ImageObject, ou liste d'objets."""
    if not image:
        return None
    if isinstance(image, list):
        image = image[0] if image else None
    if isinstance(image, dict):
        return image.get("url") or image.get("@id")
    if isinstance(image, str):
        return image.strip() or None
    return None


MAX_WEB_IMAGE_BYTES = 20 * 1024 * 1024
MAX_WEB_PAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 50_000_000


def _read_response_limited(response, limit):
    chunks = []
    total = 0
    while True:
        chunk = response.read(min(1024 * 1024, limit - total + 1))
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise ValueError("download_too_large")
        chunks.append(chunk)
    return b"".join(chunks)


def download_image_to_store(image_url, timeout=15, *, temporary=True, referer=None):
    """Télécharge une image avec limites de taille. Par défaut elle reste temporaire.

    Mêmes en-têtes « vrai navigateur » que fetch_recipe_from_url, plus un
    Referer pointant vers la page d'origine quand il est fourni : beaucoup
    de CDN d'images (constaté sur chefkoch.de) appliquent une protection
    anti-hotlinking qui refuse une image demandée sans Referer, même quand
    la page de la recette elle-même a pu être téléchargée sans problème."""
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
            ),
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate",
        }
        if referer:
            headers["Referer"] = referer
        request = urllib.request.Request(image_url, headers=headers)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content_type = (response.headers.get_content_type() or "").lower()
            if content_type and not content_type.startswith("image/"):
                return None
            length = response.headers.get("Content-Length")
            if length and int(length) > MAX_WEB_IMAGE_BYTES:
                return None
            data = _read_response_limited(response, MAX_WEB_IMAGE_BYTES)
            data = _decompress_recipe_page(data, response.headers.get("Content-Encoding"))
    except Exception as exc:
        log_internal_error("download_recipe_image", exc)
        return None
    if not data:
        return None

    ext_map = {
        "image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png",
        "image/webp": ".webp", "image/gif": ".gif",
    }
    ext = ext_map.get(content_type)
    if not ext:
        guessed = os.path.splitext(image_url.split("?")[0])[1].lower()
        ext = guessed if guessed in SAFE_IMAGE_EXTENSIONS else ".jpg"
    folder = IMPORT_TEMP_DIR if temporary else IMAGES_DIR
    os.makedirs(folder, exist_ok=True)
    dest_path = os.path.join(folder, f"{uuid.uuid4().hex}{ext}")
    try:
        with open(dest_path, "wb") as f:
            f.write(data)
        if PIL_AVAILABLE:
            with Image.open(dest_path) as img:
                if img.width * img.height > MAX_IMAGE_PIXELS:
                    raise ValueError("image_too_many_pixels")
                img.verify()
    except Exception as exc:
        try: os.remove(dest_path)
        except OSError: pass
        log_internal_error("validate_recipe_image", exc)
        return None
    return dest_path if temporary else os.path.basename(dest_path)


# ---------------------------------------------------------------------------
# Corbeille : les recettes supprimées y sont déplacées (avec leurs photos
# conservées) au lieu d'être effacées immédiatement, pour pouvoir les
# récupérer en cas d'erreur.
# ---------------------------------------------------------------------------

def load_trash():
    return _read_user_json(TRASH_FILE, list, [], label="trash")


def save_trash(trash):
    _atomic_write_json(TRASH_FILE, trash)


def recipe_draft_path(recipe_id):
    key = str(recipe_id or 'new_recipe')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,120}', key):
        key = 'hashed_' + hashlib.sha256(key.encode('utf-8')).hexdigest()
    root = os.path.realpath(DRAFTS_DIR)
    path = os.path.join(root, f'recipe_{key}.json')
    if os.path.commonpath([root, os.path.realpath(path)]) != root:
        raise ValueError('unsafe_draft_path')
    return path


def delete_recipe_draft(recipe):
    """Supprime le brouillon automatique lié à une recette.

    Une recette envoyée à la corbeille ou restaurée ne doit pas réactiver un
    ancien brouillon d'édition associé au même identifiant.
    """
    try:
        recipe_id = (recipe or {}).get("id")
        if not recipe_id:
            return
        path = recipe_draft_path(recipe_id)
        if os.path.isfile(path):
            os.remove(path)
    except OSError as exc:
        log_internal_error("delete_recipe_draft", exc)


def move_recipe_to_trash(recipe):
    """Ajoute une recette à la corbeille sans modifier recipes.json."""
    trash = load_trash()
    trash.insert(0, {"recipe": recipe, "deleted_at": datetime.now().isoformat()})
    save_trash(trash)


def delete_recipe_to_trash(recipe_id=None, recipe_index=None):
    """Retire une recette et l'ajoute à la corbeille comme une transaction."""
    recipes = load_recipes()
    index = recipe_index
    if recipe_id:
        index = next((i for i, r in enumerate(recipes) if r.get("id") == recipe_id), None)
    if index is None or not (0 <= index < len(recipes)):
        raise LookupError("recipe_not_found")
    removed = recipes.pop(index)
    trash = load_trash()
    trash.insert(0, {"recipe": copy.deepcopy(removed), "deleted_at": datetime.now().isoformat()})

    def commit():
        save_trash(trash)
        save_recipes(recipes)

    _run_json_transaction([DATA_FILE, TRASH_FILE], commit)
    delete_recipe_draft(removed)
    return removed


def restore_recipe_from_trash(trash_index):
    """Restaure une entrée de corbeille et retire celle-ci atomiquement."""
    trash = load_trash()
    if not (0 <= trash_index < len(trash)):
        raise LookupError("trash_entry_not_found")
    recipe = copy.deepcopy(trash[trash_index]["recipe"])
    recipes = load_recipes()
    existing_names = {r.get("name", "").strip().casefold() for r in recipes}
    if recipe.get("name", "").strip().casefold() in existing_names:
        recipe["name"] = t("trash_restored_suffix", name=recipe.get("name", ""))
    recipes.append(recipe)
    trash.pop(trash_index)

    def commit():
        save_recipes(recipes)
        save_trash(trash)

    _run_json_transaction([DATA_FILE, TRASH_FILE], commit)
    delete_recipe_draft(recipe)
    return recipe


def permanently_delete_trash_entries(indexes=None):
    """Valide d'abord la corbeille, puis supprime les images devenues inutiles."""
    trash = load_trash()
    selected = set(range(len(trash))) if indexes is None else set(indexes)
    removed = [entry for i, entry in enumerate(trash) if i in selected]
    remaining = [entry for i, entry in enumerate(trash) if i not in selected]
    save_trash(remaining)
    protected_recipes = load_recipes()
    for entry in removed:
        recipe = entry.get("recipe", {})
        delete_recipe_draft(recipe)
        delete_recipe_images(
            recipe, protected_recipes=protected_recipes,
            protected_trash=remaining
        )
    return len(removed)


class CookingRecordedError(RuntimeError):
    """Persistence succeeded; only a later UI/stock operation failed."""


def record_recipe_cooking(recipe_id, recipe_name, note="", comment="",
                          photo_filename=None, rating=0, persons=None):
    """Enregistre compteur, date et journal en une seule écriture recipes.json."""
    recipes = load_recipes()
    target = find_recipe_by_id(recipes, recipe_id) or find_recipe_by_name(recipes, recipe_name)
    if target is None:
        raise LookupError("recipe_not_found")
    now = datetime.now()
    target["times_cooked"] = int(target.get("times_cooked", 0) or 0) + 1
    cooked_dates = list(target.get("cooked_dates", []) or [])
    cooked_dates.append(now.strftime("%Y-%m-%d"))
    target["cooked_dates"] = cooked_dates
    cook_log = list(target.get("cook_log", []) or [])
    cook_log.append({
        "date": now.isoformat(timespec="seconds"),
        "note": note,
        "comment": comment,
        "photo": safe_image_filename(photo_filename) if photo_filename else None,
        "rating": max(0, min(5, int(rating or 0))),
        "persons": persons,
    })
    target["cook_log"] = cook_log
    save_recipes(recipes)
    return target


# ---------------------------------------------------------------------------
# Historique des recettes récemment consultées (affiché sur la page d'accueil)
# ---------------------------------------------------------------------------

RECENT_VIEWS_MAX = 8


def _load_recent_view_refs():
    if not os.path.exists(RECENT_VIEWS_FILE):
        return []
    try:
        data = _read_user_json(RECENT_VIEWS_FILE, list, [], label="recent_views")
        if _corruption_key(RECENT_VIEWS_FILE) in _CORRUPTED_DATA_FILES:
            return []
        if not isinstance(data, list):
            return []
        recipes = load_recipes()
        refs = []
        changed = False
        for item in data:
            if isinstance(item, str):
                recipe = find_recipe_by_name(recipes, item)
                refs.append({"recipe_id": recipe.get("id") if recipe else None, "recipe_name": item})
                changed = True
            elif isinstance(item, dict):
                ref = copy.deepcopy(item)
                before = (ref.get("recipe_id"), ref.get("recipe_name"))
                enrich_recipe_reference(ref, recipes)
                if before != (ref.get("recipe_id"), ref.get("recipe_name")):
                    changed = True
                refs.append(ref)
        refs = refs[:RECENT_VIEWS_MAX]
        if changed:
            _atomic_write_json(RECENT_VIEWS_FILE, refs)
        return refs
    except Exception as exc:
        log_internal_error("load_recent_views", exc)
        return []


def load_recent_view_names():
    return [r.get("recipe_name") for r in _load_recent_view_refs() if r.get("recipe_name")]


def record_recipe_view(recipe_or_name):
    recipes = load_recipes()
    recipe = recipe_or_name if isinstance(recipe_or_name, dict) else find_recipe_by_name(recipes, recipe_or_name)
    if recipe is None:
        name = str(recipe_or_name or "").strip()
        if not name:
            return
        new_ref = {"recipe_id": None, "recipe_name": name}
    else:
        new_ref = {"recipe_id": recipe.get("id"), "recipe_name": recipe.get("name")}
    refs = _load_recent_view_refs()
    key = new_ref.get("recipe_id") or (new_ref.get("recipe_name") or "").casefold()
    refs = [r for r in refs if (r.get("recipe_id") or (r.get("recipe_name") or "").casefold()) != key]
    refs.insert(0, new_ref)
    _atomic_write_json(RECENT_VIEWS_FILE, refs[:RECENT_VIEWS_MAX])


# ---------------------------------------------------------------------------
# Palette et style visuel de l'application — une identité chaleureuse et
# gourmande plutôt que le gris par défaut de Windows, appliquée d'un coup à
# toute l'application (fenêtre principale et toutes les fenêtres ouvertes
# ensuite), sans avoir à retoucher chaque écran un par un. Deux palettes
# (clair/sombre) sont disponibles, basculables depuis la page d'accueil.
# ---------------------------------------------------------------------------

LIGHT_PALETTE = {
    "BG": "#FBF6EF",           # fond général, blanc cassé chaleureux
    "CARD": "#FFFFFF",         # fond des zones "carte"
    "BORDER": "#E8DCC8",       # bordures discrètes
    "TEXT": "#332B22",         # texte principal, brun très foncé
    "TEXT_MUTED": "#8A7D68",   # texte secondaire
    "ACCENT": "#D97B3F",       # orange terracotta — actions principales
    "ACCENT_DARK": "#B8622C",  # survol / pression
    "ACCENT_LIGHT": "#F3D9C4",  # fonds légers accentués
    "GREEN": "#5C8A57",        # vert sauge — validations, favoris, succès
    "ERROR": "#B4483A",        # rouge terracotta foncé — erreurs/avertissements
    "ON_ACCENT": "#FFFFFF",    # texte sur un fond ACCENT/ACCENT_DARK (boutons...)
}

DARK_PALETTE = {
    "BG": "#211F1C",           # fond général, brun-noir doux
    "CARD": "#2C2A25",         # fond des zones "carte"
    "BORDER": "#43403A",       # bordures discrètes
    "TEXT": "#EFE8DB",         # texte principal, crème clair
    "TEXT_MUTED": "#AB9F8C",   # texte secondaire
    "ACCENT": "#E08A4F",       # orange terracotta, plus lumineux sur fond sombre
    "ACCENT_DARK": "#F0A868",  # survol / pression (plus clair que ACCENT en sombre)
    "ACCENT_LIGHT": "#4A3B2C",  # fonds légers accentués
    "GREEN": "#7CB273",        # vert sauge, plus lumineux
    "ERROR": "#E0897A",        # rouge corail, plus lumineux
    # Blanc illisible sur ACCENT/ACCENT_DARK en sombre (contraste mesuré
    # 2.65:1 et 2.00:1, sous le seuil WCAG AA de 4.5:1) : on reprend la
    # couleur de fond sombre, qui offre un contraste correct (6.2:1/8.2:1)
    # sans changer la teinte de l'accent lui-même.
    "ON_ACCENT": "#211F1C",
}

COLOR_BG = LIGHT_PALETTE["BG"]
COLOR_CARD = LIGHT_PALETTE["CARD"]
COLOR_BORDER = LIGHT_PALETTE["BORDER"]
COLOR_TEXT = LIGHT_PALETTE["TEXT"]
COLOR_TEXT_MUTED = LIGHT_PALETTE["TEXT_MUTED"]
COLOR_ACCENT = LIGHT_PALETTE["ACCENT"]
COLOR_ACCENT_DARK = LIGHT_PALETTE["ACCENT_DARK"]
COLOR_ACCENT_LIGHT = LIGHT_PALETTE["ACCENT_LIGHT"]
COLOR_GREEN = LIGHT_PALETTE["GREEN"]
COLOR_ERROR = LIGHT_PALETTE["ERROR"]
COLOR_ON_ACCENT = LIGHT_PALETTE["ON_ACCENT"]


def apply_palette(dark):
    """Met à jour les constantes de couleur globales selon le thème choisi.
    Doit être suivi d'un appel à configure_app_style() pour que les styles
    ttk et la base d'options Tk reflètent les nouvelles couleurs."""
    global COLOR_BG, COLOR_CARD, COLOR_BORDER, COLOR_TEXT, COLOR_TEXT_MUTED
    global COLOR_ACCENT, COLOR_ACCENT_DARK, COLOR_ACCENT_LIGHT, COLOR_GREEN, COLOR_ERROR
    global COLOR_ON_ACCENT
    palette = DARK_PALETTE if dark else LIGHT_PALETTE
    COLOR_BG = palette["BG"]
    COLOR_CARD = palette["CARD"]
    COLOR_BORDER = palette["BORDER"]
    COLOR_TEXT = palette["TEXT"]
    COLOR_TEXT_MUTED = palette["TEXT_MUTED"]
    COLOR_ACCENT = palette["ACCENT"]
    COLOR_ACCENT_DARK = palette["ACCENT_DARK"]
    COLOR_ACCENT_LIGHT = palette["ACCENT_LIGHT"]
    COLOR_GREEN = palette["GREEN"]
    COLOR_ERROR = palette["ERROR"]
    COLOR_ON_ACCENT = palette["ON_ACCENT"]


def get_dark_mode_preference():
    return bool(load_settings().get("dark_mode", False))


def set_dark_mode_preference(value):
    settings = load_settings()
    settings["dark_mode"] = bool(value)
    save_settings(settings)


FONT_SCALE = 1.0


def apply_font_scale(large_text):
    """Met à jour l'échelle globale des polices selon le mode « Texte
    agrandi » (accessibilité). Doit être appelé avant la construction de
    toute fenêtre pour que sf() reflète le bon facteur."""
    global FONT_SCALE
    FONT_SCALE = 1.3 if large_text else 1.0


def sf(size):
    """Renvoie une taille de police mise à l'échelle selon le mode « Texte
    agrandi » (accessibilité) — à utiliser à la place d'un nombre littéral
    dans tous les tuples de police, ex. ("Segoe UI", sf(10), "bold")."""
    return round(size * FONT_SCALE)


def gs(size):
    """Renvoie une dimension de fenêtre (largeur, hauteur, ou plafond de
    hauteur) mise à l'échelle selon le mode « Texte agrandi », pour que les
    fenêtres restent assez grandes pour leur contenu affiché en plus gros
    caractères et qu'aucun bouton ne se retrouve coupé ou masqué."""
    return round(size * FONT_SCALE)


# Échelle d'espacement (padx/pady) à multiples de 8, pour un rythme visuel
# cohérent au lieu de valeurs ad hoc (14, 18, 22, 9...) qui ne veulent rien
# dire les unes par rapport aux autres. À passer dans gs(...) comme n'importe
# quelle autre dimension pour qu'il suive le mode « Texte agrandi ».
SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 16
SPACE_LG = 24
SPACE_XL = 32


def get_large_text_preference():
    return bool(load_settings().get("large_text", False))


def set_large_text_preference(value):
    settings = load_settings()
    settings["large_text"] = bool(value)
    save_settings(settings)


CURRENT_LANGUAGE = "fr"

# Traductions disponibles, langue par langue. Le français n'a pas besoin
# d'être dupliqué ici : il sert de texte de secours (voir t() ci-dessous)
# pour toute clé pas encore traduite dans une autre langue — l'application
# reste donc entièrement utilisable pendant qu'on ajoute les traductions
# progressivement, une langue et une fenêtre à la fois.
def _load_ui_translations():
    """Charge les textes UI depuis un fichier séparé, plus simple à auditer.

    Le fichier est livré à côté de l'exécutable comme les autres bases JSON.
    Une erreur de traduction est journalisée et un noyau français minimal
    garde l'application démarrable plutôt que de provoquer un crash opaque.
    """
    path = os.path.join(BASE_DIR, "i18n_desktop.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        fr = payload.get("fr")
        translations = payload.get("translations")
        if not isinstance(fr, dict) or not isinstance(translations, dict):
            raise ValueError("invalid i18n_desktop.json")
        for lang in ("en", "es", "de"):
            if not isinstance(translations.get(lang), dict):
                raise ValueError(f"missing language: {lang}")
        return fr, translations
    except Exception as exc:
        log_internal_error("load_ui_translations", exc)
        return {
            "home_window_title": "Mes Recettes, Mes Courses",
            "common_error": "Erreur",
            "common_info": "Information",
            "common_confirm": "Confirmer",
        }, {"en": {}, "es": {}, "de": {}}


FRENCH_STRINGS, TRANSLATIONS = _load_ui_translations()


def detect_system_language():
    """Détecte la langue du système d'exploitation pour proposer une
    langue de démarrage sensée au tout premier lancement (avant qu'aucune
    préférence n'ait jamais été enregistrée). Ne reconnaît que le
    français, l'anglais, l'espagnol et l'allemand pour l'instant (les
    seules langues disponibles) : toute autre langue système retombe sur
    le français, la langue de référence de l'application. Repose sur
    locale.getlocale()/getdefaultlocale(), qui peuvent échouer ou
    renvoyer None selon la configuration du système — dans ce cas, on
    retombe aussi sur le français plutôt que de risquer une erreur au
    démarrage."""
    try:
        import locale
        lang_code = None
        try:
            lang_code, _ = locale.getlocale()
        except (ValueError, TypeError):
            pass
        if not lang_code:
            try:
                lang_code, _ = locale.getdefaultlocale()
            except (ValueError, TypeError):
                pass
        if lang_code:
            lang_code_lower = lang_code.lower()
            if lang_code_lower.startswith("en"):
                return "en"
            if lang_code_lower.startswith("es"):
                return "es"
            if lang_code_lower.startswith("de"):
                return "de"
    except Exception as exc:
        log_internal_error("suppressed_exception", exc)
    return "fr"


def get_language_preference():
    settings = load_settings()
    if "language" not in settings:
        # Premier lancement : aucune préférence enregistrée pour l'instant,
        # on propose la langue du système plutôt que de toujours démarrer
        # en français. Ce choix devient ensuite la préférence enregistrée,
        # comme si l'utilisateur l'avait choisie lui-même (bascule normale
        # possible à tout moment via le bouton 🌐).
        detected = detect_system_language()
        settings["language"] = detected
        save_settings(settings)
        return detected
    return settings.get("language", "fr")


def set_language_preference(value):
    settings = load_settings()
    settings["language"] = value
    save_settings(settings)


def apply_language(lang):
    global CURRENT_LANGUAGE
    CURRENT_LANGUAGE = lang


def t(key, **kwargs):
    """Retourne le texte de l'interface pour la clé donnée, dans la langue
    actuellement sélectionnée. Si cette clé n'a pas encore été traduite
    dans la langue courante, retourne le texte français de référence — la
    partie pas encore traduite reste donc lisible plutôt que d'afficher un
    identifiant technique."""
    text = None
    if CURRENT_LANGUAGE != "fr":
        text = TRANSLATIONS.get(CURRENT_LANGUAGE, {}).get(key)
    if text is None:
        text = FRENCH_STRINGS.get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return text
    return text


def get_disclaimer_accepted():
    return bool(load_settings().get("disclaimer_accepted", False))


def set_disclaimer_accepted(value):
    settings = load_settings()
    settings["disclaimer_accepted"] = bool(value)
    save_settings(settings)



def _ui_iter_toplevels(root):
    """Parcourt aussi les dialogues dont le parent est une autre fenêtre."""
    try:
        children = root.winfo_children()
    except tk.TclError:
        return
    for child in children:
        if isinstance(child, tk.Toplevel):
            yield child
        yield from _ui_iter_toplevels(child)


def _ui_refresh_open_windows(root):
    """Notifie les fenêtres ouvertes après langue/thème/police.

    Les fenêtres qui possèdent une méthode ``refresh_ui`` peuvent reconstruire
    leur contenu en conservant leur état ; les autres reçoivent un événement
    afin d'évoluer progressivement sans détruire une saisie en cours.
    """
    try:
        for child in _ui_iter_toplevels(root):
            try:
                refresher = getattr(child, "refresh_ui", None)
                if callable(refresher):
                    refresher()
                child.event_generate("<<AppearanceChanged>>", when="tail")
                child.update_idletasks()
            except Exception as exc:
                log_internal_error("suppressed_exception", exc)
    except Exception as exc:
        log_internal_error("suppressed_exception", exc)


def _language_catalog(language):
    """Retourne un catalogue complet, avec le français comme secours."""
    catalog = dict(FRENCH_STRINGS)
    if language != "fr":
        catalog.update(TRANSLATIONS.get(language, {}))
    return catalog


def _ui_translate_open_windows(root, old_language, new_language):
    """Traduit les libellés statiques des fenêtres ouvertes sans les fermer.

    Les champs de saisie ne sont jamais parcourus : seul le texte de widgets
    d'interface (boutons, labels, onglets, menus, en-têtes et listes de choix)
    est remplacé. L'état transitoire des formulaires reste donc intact.
    """
    old_catalog = _language_catalog(old_language)
    new_catalog = _language_catalog(new_language)
    exact = {}
    formatted = []
    for key, old_text in old_catalog.items():
        if not isinstance(old_text, str):
            continue
        if "{" not in old_text:
            exact.setdefault(old_text, new_catalog.get(key, old_text))
            continue
        placeholder_matches = list(re.finditer(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", old_text))
        literal_length = len(re.sub(r"\{[^{}]+\}", "", old_text).strip())
        if not placeholder_matches or literal_length < 4:
            continue
        parts = []
        cursor = 0
        names = set()
        for match in placeholder_matches:
            parts.append(re.escape(old_text[cursor:match.start()]))
            name = match.group(1)
            if name in names:
                parts.append(f"(?P={name})")
            else:
                parts.append(f"(?P<{name}>.*?)")
                names.add(name)
            cursor = match.end()
        parts.append(re.escape(old_text[cursor:]))
        formatted.append((
            len(old_text), re.compile("^" + "".join(parts) + "$", re.DOTALL),
            new_catalog.get(key, old_text)
        ))
    formatted.sort(key=lambda item: item[0], reverse=True)

    old_ingredients = load_ingredient_translations(old_language) if old_language != "fr" else {}
    new_ingredients = load_ingredient_translations(new_language) if new_language != "fr" else {}
    for french_name in load_default_ingredients():
        key = str(french_name).strip().lower()
        old_name = old_ingredients.get(key, french_name)
        new_name = new_ingredients.get(key, french_name)
        exact.setdefault(old_name, new_name)

    def translate_text(value):
        if not isinstance(value, str) or not value:
            return value
        replacement = exact.get(value)
        if replacement is not None:
            return replacement
        for _length, pattern, target_template in formatted:
            match = pattern.match(value)
            if match:
                try:
                    return target_template.format(**match.groupdict())
                except (KeyError, ValueError):
                    return value
        return value

    def visit(widget):
        try:
            if isinstance(widget, tk.Toplevel):
                widget.title(translate_text(widget.title()))
            if not isinstance(widget, (tk.Entry, tk.Text, ttk.Entry)):
                try:
                    current = widget.cget("text")
                    translated = translate_text(current)
                    if translated != current:
                        widget.configure(text=translated)
                except (tk.TclError, TypeError):
                    pass
            if isinstance(widget, ttk.Notebook):
                for tab_id in widget.tabs():
                    current = widget.tab(tab_id, "text")
                    translated = translate_text(current)
                    if translated != current:
                        widget.tab(tab_id, text=translated)
            if isinstance(widget, tk.Menu):
                end = widget.index("end")
                for index in range((end + 1) if end is not None else 0):
                    try:
                        if widget.type(index) == "separator":
                            continue
                        current = widget.entrycget(index, "label")
                        translated = translate_text(current)
                        if translated != current:
                            widget.entryconfigure(index, label=translated)
                    except tk.TclError:
                        pass
            if isinstance(widget, ttk.Combobox):
                values = list(widget.cget("values"))
                translated_values = [translate_text(value) for value in values]
                if translated_values != values:
                    current = widget.get()
                    widget.configure(values=translated_values)
                    translated_current = translate_text(current)
                    if translated_current != current:
                        widget.set(translated_current)
            if isinstance(widget, ttk.Treeview):
                for column in ("#0",) + tuple(widget.cget("columns")):
                    try:
                        current = widget.heading(column, "text")
                        translated = translate_text(current)
                        if translated != current:
                            widget.heading(column, text=translated)
                    except tk.TclError:
                        pass
                pending = list(widget.get_children(""))
                while pending:
                    item_id = pending.pop()
                    pending.extend(widget.get_children(item_id))
                    item = widget.item(item_id)
                    old_item_text = item.get("text", "")
                    new_item_text = translate_text(old_item_text)
                    old_values = list(item.get("values", ()))
                    new_values = [translate_text(str(value)) for value in old_values]
                    if new_item_text != old_item_text or new_values != old_values:
                        widget.item(item_id, text=new_item_text, values=new_values)
            if isinstance(widget, tk.Listbox):
                for index in range(widget.size()):
                    current = widget.get(index)
                    translated = translate_text(current)
                    if translated != current:
                        selected = index in widget.curselection()
                        widget.delete(index)
                        widget.insert(index, translated)
                        if selected:
                            widget.selection_set(index)
            if isinstance(widget, tk.Canvas):
                for item_id in widget.find_all():
                    try:
                        current = widget.itemcget(item_id, "text")
                        translated = translate_text(current)
                        if translated != current:
                            widget.itemconfigure(item_id, text=translated)
                    except tk.TclError:
                        pass
            for child in widget.winfo_children():
                if not isinstance(child, tk.Toplevel):
                    visit(child)
        except tk.TclError:
            return

    for child in _ui_iter_toplevels(root):
        visit(child)


def _ui_recolor_open_windows(root, old_palette, new_palette):
    """Remplace les couleurs de l'ancien thème dans les fenêtres ouvertes."""
    color_map = {
        old_palette[key].lower(): new_palette[key]
        for key in old_palette.keys() & new_palette.keys()
    }
    options = (
        "background", "foreground", "activebackground", "activeforeground",
        "disabledforeground", "highlightbackground", "highlightcolor",
        "selectbackground", "selectforeground", "insertbackground",
    )

    def visit(widget):
        for option in options:
            try:
                current = str(widget.cget(option))
                replacement = color_map.get(current.lower())
                if replacement:
                    widget.configure(**{option: replacement})
            except (tk.TclError, TypeError):
                pass
        if isinstance(widget, tk.Canvas):
            for item_id in widget.find_all():
                for option in ("fill", "outline", "activefill", "activeoutline"):
                    try:
                        current = str(widget.itemcget(item_id, option))
                        replacement = color_map.get(current.lower())
                        if replacement:
                            widget.itemconfigure(item_id, **{option: replacement})
                    except tk.TclError:
                        pass
        for child in widget.winfo_children():
            if not isinstance(child, tk.Toplevel):
                visit(child)

    for child in _ui_iter_toplevels(root):
        try:
            visit(child)
        except tk.TclError:
            pass


def _ui_rescale_open_window_fonts(root, ratio):
    """Redimensionne les polices explicites sans reconstruire les fenêtres."""
    if not ratio or abs(ratio - 1.0) < 0.001:
        return

    def visit(widget):
        try:
            font_spec = widget.cget("font")
            if font_spec:
                current_font = tkfont.Font(root=widget, font=font_spec)
                size = int(current_font.cget("size") or 0)
                if size:
                    current_font.configure(size=max(1, round(size * ratio)))
                    widget.configure(font=current_font)
                    refs = getattr(widget, "_scaled_font_refs", [])
                    refs.append(current_font)
                    widget._scaled_font_refs = refs[-2:]
        except (tk.TclError, TypeError, ValueError):
            pass
        if isinstance(widget, tk.Canvas):
            for item_id in widget.find_all():
                try:
                    font_spec = widget.itemcget(item_id, "font")
                    if not font_spec:
                        continue
                    current_font = tkfont.Font(root=widget, font=font_spec)
                    size = int(current_font.cget("size") or 0)
                    if size:
                        current_font.configure(size=max(1, round(size * ratio)))
                        widget.itemconfigure(item_id, font=current_font)
                        refs = getattr(widget, "_scaled_canvas_font_refs", [])
                        refs.append(current_font)
                        widget._scaled_canvas_font_refs = refs[-50:]
                except (tk.TclError, TypeError, ValueError):
                    pass
        for child in widget.winfo_children():
            if not isinstance(child, tk.Toplevel):
                visit(child)

    for child in _ui_iter_toplevels(root):
        visit(child)


def _ui_bind_local_mousewheel(canvas, container, callback):
    """Lie la molette uniquement aux widgets d'une zone défilable.

    Un bindtag propre à la zone remplace bind_all/unbind_all. Deux fenêtres
    ouvertes ne peuvent ainsi plus supprimer ou détourner leurs événements.
    """
    bindtag = f"LocalMouseWheel:{str(canvas)}"
    prefix = "LocalMouseWheel:"
    canvas.bind_class(bindtag, "<MouseWheel>", callback, add="+")

    def attach(widget):
        try:
            tags = tuple(tag for tag in widget.bindtags()
                         if not str(tag).startswith(prefix))
            widget.bindtags((bindtag,) + tags)
            for child in widget.winfo_children():
                attach(child)
        except tk.TclError:
            pass

    attach(canvas)
    canvas.after_idle(lambda: attach(container))
    canvas.bind(
        "<Destroy>",
        lambda event: canvas.unbind_class(bindtag, "<MouseWheel>")
        if event.widget is canvas else None,
        add="+"
    )
    return bindtag


class _Tooltip:
    """Info-bulle affichée après un court survol, pour les boutons composés
    d'une seule icône sans texte visible (ce que la souris seule permettait
    de deviner par essai-erreur)."""

    DELAY_MS = 500

    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self._after_id = None
        self._tip = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")
        widget.bind("<Destroy>", self._hide, add="+")

    def _schedule(self, _event=None):
        self._hide()
        self._after_id = self.widget.after(self.DELAY_MS, self._show)

    def _show(self):
        self._after_id = None
        if self._tip is not None or not self.widget.winfo_exists():
            return
        x = self.widget.winfo_rootx() + 6
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self._tip = tk.Toplevel(self.widget)
        self._tip.wm_overrideredirect(True)
        try:
            self._tip.wm_attributes("-topmost", True)
        except tk.TclError:
            pass
        self._tip.wm_geometry(f"+{x}+{y}")
        tk.Label(self._tip, text=self.text, background=COLOR_TEXT, foreground=COLOR_BG,
                 font=("Segoe UI", sf(9)), padx=8, pady=4, wraplength=280, justify="left").pack()

    def _hide(self, _event=None):
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None
        if self._tip is not None:
            try:
                self._tip.destroy()
            except tk.TclError:
                pass
            self._tip = None


def add_tooltip(widget, text):
    """Attache une info-bulle à un widget, typiquement un bouton icône-seule
    (🗑, 👁, 🔄...) dont l'action n'est pas devinable sans l'essayer."""
    return _Tooltip(widget, text)


def _ui_attach_more_menu(button, items):
    menu = tk.Menu(button, tearoff=0)
    for label, command in items:
        if label == "---":
            menu.add_separator()
        else:
            menu.add_command(label=label, command=command)
    button.configure(command=lambda: menu.tk_popup(button.winfo_rootx(),
                                                   button.winfo_rooty() + button.winfo_height()))
    return menu


def _integrity_report():
    report = {
        "recipes_json_ok": True,
        "missing_images": [],
        "orphan_images": [],
        "duplicate_recipe_ids": [],
        "legacy_imports_unknown_basis": [],
    }
    try:
        recipes_path = os.path.join(DATA_DIR, "recipes.json")
        recipes = []
        if os.path.exists(recipes_path):
            with open(recipes_path, "r", encoding="utf-8") as f:
                recipes = json.load(f)
        ids = {}
        for r in recipes or []:
            rid = r.get("id")
            if rid:
                ids[rid] = ids.get(rid, 0) + 1
        report["duplicate_recipe_ids"] = [rid for rid, n in ids.items() if n > 1]
        report["legacy_imports_unknown_basis"] = [
            r.get("name", "?") for r in recipes or []
            if isinstance(r, dict) and r.get("source_url") and not r.get("quantity_basis")
        ]
        missing, orphan = _count_orphan_images(recipes, IMAGES_DIR)
        report["missing_images"] = missing
        report["orphan_images"] = orphan
    except Exception as exc:
        log_internal_error("_integrity_report", exc)
        report["recipes_json_ok"] = False
    return report



def enable_windows_dpi_awareness():
    """Enable per-monitor DPI awareness on Windows when supported.

    The calls are deliberately best-effort so older Windows versions and
    non-Windows systems keep working unchanged.
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        # PER_MONITOR_AWARE_V2 (Windows 10 Creators Update+).
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return True
    except Exception:
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor aware
            return True
        except Exception:
            try:
                import ctypes
                ctypes.windll.user32.SetProcessDPIAware()
                return True
            except Exception:
                return False

class MaintenanceWindow:
    def __init__(self, parent):
        self.parent = parent
        self.win = tk.Toplevel(parent)
        _ui_bind_escape(self.win)
        self.win.title(t("maintenance_title"))
        _ui_apply_window_defaults(self.win, "760x560", True)
        outer = ttk.Frame(self.win, padding=18)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text=t("maintenance_title"),
                  font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(
            outer,
            text=t("maintenance_intro"),
            wraplength=700
        ).pack(anchor="w", pady=(4, 14))

        self.report = tk.Text(outer, height=18, wrap="word")
        self.report.pack(fill="both", expand=True)

        btns = ttk.Frame(outer)
        btns.pack(fill="x", pady=(12, 0))
        ttk.Button(btns, text=t("maintenance_recheck"),
                   command=self.refresh).pack(side="left")
        ttk.Button(btns, text=t("maintenance_open_backups"),
                   command=self.open_backups).pack(side="left", padx=(8, 0))
        ttk.Button(btns, text=t("maintenance_close"),
                   command=self.win.destroy).pack(side="right")
        self.refresh()

    def refresh(self):
        rep = _integrity_report()
        lines = []
        lines.append(t("maintenance_recipes_ok", status=t("maintenance_status_ok") if rep["recipes_json_ok"] else t("maintenance_status_error")))
        lines.append(t("maintenance_missing_images", count=len(rep["missing_images"])))
        lines.append(t("maintenance_orphan_images", count=len(rep["orphan_images"])))
        lines.append(t("maintenance_duplicate_ids", count=len(rep["duplicate_recipe_ids"])))
        lines.append(t("maintenance_legacy_imports", count=len(rep.get("legacy_imports_unknown_basis", []))))
        if rep.get("legacy_imports_unknown_basis"):
            lines.append("\n" + t("maintenance_legacy_imports_heading"))
            lines.extend("  - " + x for x in rep["legacy_imports_unknown_basis"][:50])
        if rep["missing_images"]:
            lines.append("\n" + t("maintenance_missing_images_heading"))
            lines.extend("  - " + x for x in rep["missing_images"][:50])
        if rep["orphan_images"]:
            lines.append("\n" + t("maintenance_orphan_images_heading"))
            lines.extend("  - " + x for x in rep["orphan_images"][:50])
        if rep["duplicate_recipe_ids"]:
            lines.append("\n" + t("maintenance_duplicate_ids_heading"))
            lines.extend("  - " + x for x in rep["duplicate_recipe_ids"][:50])
        self.report.config(state="normal")
        self.report.delete("1.0", "end")
        self.report.insert("1.0", "\n".join(lines))
        self.report.config(state="disabled")

    def open_backups(self):
        folder = BACKUPS_DIR
        os.makedirs(folder, exist_ok=True)
        try:
            os.startfile(folder)
        except Exception as exc:
            log_internal_error("open_backups", exc)
            _ui_show_toast(self.win, folder)

class DisclaimerWindow(tk.Toplevel):
    """Clause de responsabilité affichée obligatoirement au tout premier
    lancement de l'application. Tant qu'elle n'est pas acceptée (case cochée
    puis bouton « Continuer »), l'application ne peut pas être utilisée."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.accepted = False
        # La hauteur est plafonnée à l'espace écran réellement disponible
        # (moins une petite marge), pour que le bouton « Continuer » reste
        # toujours visible même sur un écran de petite hauteur ou avec le
        # mode « Texte agrandi » déjà activé lors d'une session précédente.
        # Plus grande au premier lancement pour faciliter la lecture.
        fit_window_to_workarea(self, gs(1080), get_usable_screen_height(self), margin=18)
        safe_minsize(self, gs(700), min(gs(520), get_usable_screen_height(self) - 48))
        self.resizable(True, True)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._quit_app)
        self._build_ui()

    def _build_ui(self):
        # Reconstruit tout le contenu de la fenêtre dans la langue
        # actuellement sélectionnée. Appelée à l'ouverture, puis à chaque
        # fois que la langue est changée via le sélecteur ci-dessous —
        # avant même d'avoir accepté les conditions, une personne
        # anglophone ou hispanophone peut ainsi lire ce texte dans sa
        # propre langue dès le premier lancement.
        previously_checked = self.accept_var.get() if hasattr(self, "accept_var") else False
        for child in self.winfo_children():
            child.destroy()
        self.title(t("disclaimer_title"))

        # ---- Sélecteur de langue, tout en haut : mêmes principe et
        # habillage que le menu déroulant de la page d'accueil. ----
        lang_bar = ttk.Frame(self)
        lang_bar.pack(fill="x", padx=15, pady=(10, 0))
        language_names = {"fr": "Français", "en": "English", "es": "Español", "de": "Deutsch"}
        current_flag = self.app.flag_photos.get(self.app.language)
        menubutton_kwargs = {"text": language_names.get(self.app.language, "Français")}
        if current_flag is not None:
            menubutton_kwargs["image"] = current_flag
            menubutton_kwargs["compound"] = "left"
        else:
            menubutton_kwargs["text"] = "🌐 " + menubutton_kwargs["text"]
        language_menubutton = ttk.Menubutton(lang_bar, style="Secondary.TMenubutton", **menubutton_kwargs)
        language_menu = tk.Menu(language_menubutton, tearoff=False)
        for lang_code in ("fr", "en", "es", "de"):
            item_kwargs = {
                "label": language_names[lang_code],
                "command": lambda lc=lang_code: self._set_language(lc),
            }
            lang_flag = self.app.flag_photos.get(lang_code)
            if lang_flag is not None:
                item_kwargs["image"] = lang_flag
                item_kwargs["compound"] = "left"
            language_menu.add_command(**item_kwargs)
        language_menubutton["menu"] = language_menu
        language_menubutton.pack(side="right")

        ttk.Label(self, text=t("disclaimer_heading"), font=("Segoe UI", sf(14), "bold"),
                  foreground=COLOR_ERROR).pack(pady=(15, 5))
        ttk.Label(self, text=t("disclaimer_intro"),
                  font=("Segoe UI", sf(9)), foreground=COLOR_TEXT_MUTED).pack(pady=(0, 10))

        text_frame = ttk.Frame(self)
        text_frame.pack(fill="both", expand=True, padx=15)
        text_widget = tk.Text(text_frame, wrap="word", padx=10, pady=10, font=("Segoe UI", sf(10)))
        scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=text_widget.yview)
        text_widget.configure(yscrollcommand=scrollbar.set)
        text_widget.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        text_widget.insert("1.0", t("disclaimer_text"))
        text_widget.config(state="disabled")

        self.accept_var = tk.BooleanVar(value=previously_checked)
        check = ttk.Checkbutton(
            self, text=t("disclaimer_checkbox"),
            variable=self.accept_var, command=self._on_toggle
        )
        check.pack(pady=(12, 5))

        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=(0, 15))
        self.continue_button = ttk.Button(
            btn_frame, text=t("disclaimer_continue_button"),
            state="normal" if previously_checked else "disabled", command=self._on_continue
        )
        self.continue_button.grid(row=0, column=0, padx=5)
        ttk.Button(btn_frame, text=t("disclaimer_quit_button"),
                   style="Secondary.TButton", command=self._quit_app).grid(row=0, column=1, padx=5)

    def _set_language(self, lang):
        if lang == self.app.language:
            return
        self.app.language = lang
        set_language_preference(lang)
        apply_language(lang)
        self._build_ui()

    def _on_toggle(self):
        self.continue_button.config(state="normal" if self.accept_var.get() else "disabled")

    def _on_continue(self):
        if not self.accept_var.get():
            return
        self.accepted = True
        set_disclaimer_accepted(True)
        self.destroy()

    def _quit_app(self):
        self.accepted = False
        self.destroy()
        self.app.destroy()
        sys.exit(0)


# Espace vide laissé en bas des listes défilantes (environ 2 cm à 96 DPI),
# pour pouvoir descendre l'ascenseur un peu plus bas que le dernier élément
# et le voir entièrement, même si la fenêtre se termine juste au-dessus de
# la barre des tâches.
SCROLL_BOTTOM_PADDING = 76


def get_usable_screen_rect(widget):
    """Retourne la zone de travail du moniteur qui contient la fenêtre.

    Sous Windows, utilise MonitorFromWindow/GetMonitorInfo afin de respecter
    la barre des tâches du bon écran dans une configuration multi-moniteurs.
    """
    try:
        import ctypes
        from ctypes import wintypes

        class RECT(ctypes.Structure):
            _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                        ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", RECT),
                        ("rcWork", RECT), ("dwFlags", wintypes.DWORD)]

        user32 = ctypes.windll.user32
        hwnd = int(widget.winfo_id())
        monitor = user32.MonitorFromWindow(hwnd, 2)  # MONITOR_DEFAULTTONEAREST
        if monitor:
            info = MONITORINFO()
            info.cbSize = ctypes.sizeof(MONITORINFO)
            if user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
                rect = info.rcWork
                width = rect.right - rect.left
                height = rect.bottom - rect.top
                if width > 0 and height > 0:
                    return rect.left, rect.top, width, height

        # Repli vers la zone de travail principale pour d'anciennes versions
        # de Windows / environnements atypiques.
        rect = RECT()
        SPI_GETWORKAREA = 0x0030
        if user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0):
            width = rect.right - rect.left
            height = rect.bottom - rect.top
            if width > 0 and height > 0:
                return rect.left, rect.top, width, height
    except Exception as exc:
        log_internal_error("get_usable_screen_rect", exc)
    return 0, 0, widget.winfo_screenwidth(), widget.winfo_screenheight()


def get_usable_screen_height(widget):
    return get_usable_screen_rect(widget)[3]


# Réserve pour la décoration Windows (barre de titre + bordures).
# Tkinter exprime la hauteur de geometry() en taille CLIENT, tandis que la
# zone de travail Windows décrit la fenêtre ENTIÈRE. Sans cette réserve,
# les derniers boutons peuvent se retrouver sous la barre des tâches.
WINDOW_NONCLIENT_VERTICAL_RESERVE = 72
WINDOW_NONCLIENT_HORIZONTAL_RESERVE = 20
WINDOW_BOTTOM_SAFETY = 18


def _safe_client_bounds(widget, margin=18):
    """Renvoie les dimensions CLIENT maximales sûres pour une fenêtre Tk."""
    x0, y0, work_w, work_h = get_usable_screen_rect(widget)

    # Double garde-fou :
    # 1) zone de travail Windows (hors barre des tâches) ;
    # 2) hauteur Tk brute moins une marge de sécurité.
    # Le second protège aussi les configurations DPI/écrans multiples où
    # Windows et Tk peuvent arrondir les coordonnées différemment.
    tk_screen_w = max(1, widget.winfo_screenwidth())
    tk_screen_h = max(1, widget.winfo_screenheight())

    safe_work_w = min(work_w, tk_screen_w)
    safe_work_h = min(work_h, tk_screen_h - WINDOW_BOTTOM_SAFETY)

    max_w = max(
        420,
        safe_work_w - margin * 2 - WINDOW_NONCLIENT_HORIZONTAL_RESERVE
    )
    max_h = max(
        320,
        safe_work_h - margin * 2 - WINDOW_NONCLIENT_VERTICAL_RESERVE
    )
    return x0, y0, safe_work_w, safe_work_h, max_w, max_h


def safe_minsize(widget, min_width, min_height, margin=14):
    """Applique une taille minimale sans pouvoir dépasser la zone de travail."""
    try:
        _, _, _, _, max_w, max_h = _safe_client_bounds(widget, margin)
        widget.minsize(min(int(min_width), max_w), min(int(min_height), max_h))
    except Exception as exc:
        log_internal_error("safe_minsize", exc)
        try:
            widget.minsize(int(min_width), int(min_height))
        except Exception as exc:
            log_internal_error("suppressed_exception", exc)


def fit_window_to_workarea(widget, desired_width, desired_height=None, margin=18,
                           center=True):
    """Dimensionne une fenêtre sans jamais masquer ses boutons sous la barre
    des tâches.

    Important : ``geometry()`` fixe la taille de la zone CLIENT, pas la taille
    extérieure complète de la fenêtre Windows. On réserve donc explicitement
    la hauteur de la barre de titre et des bordures.
    """
    x0, y0, work_w, work_h, max_w, max_h = _safe_client_bounds(widget, margin)

    width = min(int(desired_width), max_w)
    height = max_h if desired_height is None else min(int(desired_height), max_h)

    if center:
        x = x0 + max(margin, (work_w - width) // 2)
        # Laisser plus d'espace sous la fenêtre qu'auparavant.
        y = y0 + max(margin, (work_h - height - WINDOW_NONCLIENT_VERTICAL_RESERVE) // 2)
    else:
        x, y = x0 + margin, y0 + margin

    # Mémorise la taille explicitement demandée. Le contrôle automatique
    # exécuté après l'affichage ne doit jamais rétrécir une fenêtre simplement
    # parce que son contenu demande moins de place (cas de l'accueil au premier
    # lancement après la v15).
    widget._desired_workarea_width = width
    widget._desired_workarea_height = height
    widget.geometry(f"{width}x{height}+{x}+{y}")
    return width, height


def ensure_window_visible_and_fitted(widget, margin=14):
    """Ajuste une fenêtre après création de son contenu.

    La taille demandée par les contrôles est respectée autant que possible,
    mais une réserve supplémentaire est toujours conservée en bas de l'écran.
    """
    try:
        widget.update_idletasks()

        # Une fenêtre maximisée ou en plein écran doit rester entièrement sous
        # le contrôle natif de Windows. La redimensionner ici recréerait les
        # marges que l'utilisateur vient précisément de demander à supprimer.
        try:
            if str(widget.state()).lower() == "zoomed" or bool(widget.attributes("-fullscreen")):
                return
        except Exception as exc:
            log_internal_error("suppressed_exception", exc)

        x0, y0, work_w, work_h, max_w, max_h = _safe_client_bounds(widget, margin)

        cur_w = max(1, widget.winfo_width())
        cur_h = max(1, widget.winfo_height())
        req_w = max(1, widget.winfo_reqwidth())
        req_h = max(1, widget.winfo_reqheight())

        desired_w = int(getattr(widget, "_desired_workarea_width", 0) or 0)
        desired_h = int(getattr(widget, "_desired_workarea_height", 0) or 0)

        # Respecte la taille choisie par chaque fenêtre. L'auto-fit peut
        # l'agrandir si le contenu en a besoin ou la réduire si elle dépasse
        # l'écran, mais il ne la réduit plus arbitrairement.
        target_w = min(max_w, max(cur_w, req_w + 20, desired_w))
        target_h = min(max_h, max(cur_h, req_h + 20, desired_h))

        x = x0 + max(margin, (work_w - target_w) // 2)
        y = y0 + max(
            margin,
            (work_h - target_h - WINDOW_NONCLIENT_VERTICAL_RESERVE) // 2
        )
        widget.geometry(f"{target_w}x{target_h}+{x}+{y}")

        # Une deuxième passe après que Windows a réellement créé la barre de
        # titre. Si l'extérieur de la fenêtre mord encore sur la zone sûre,
        # on réduit légèrement la hauteur CLIENT.
        def final_guard():
            try:
                widget.update_idletasks()
                try:
                    if str(widget.state()).lower() == "zoomed" or bool(widget.attributes("-fullscreen")):
                        return
                except Exception as exc:
                    log_internal_error("suppressed_exception", exc)
                _, wy0, _, wh, _, mh = _safe_client_bounds(widget, margin)

                # winfo_rooty() correspond au début de la zone client.
                # La différence avec winfo_y() donne une approximation de la
                # décoration supérieure réellement ajoutée par Windows.
                top_decoration = max(0, widget.winfo_rooty() - widget.winfo_y())
                client_bottom = widget.winfo_rooty() + widget.winfo_height()
                safe_bottom = wy0 + wh - margin - WINDOW_BOTTOM_SAFETY

                overflow = client_bottom - safe_bottom
                if overflow > 0:
                    new_h = max(320, widget.winfo_height() - overflow - top_decoration - 8)
                    new_h = min(new_h, mh)
                    widget._desired_workarea_height = min(
                        int(getattr(widget, "_desired_workarea_height", new_h) or new_h),
                        new_h
                    )
                    widget.geometry(f"{widget.winfo_width()}x{new_h}")
            except Exception as exc:
                log_internal_error("suppressed_exception", exc)

        widget.after(80, final_guard)
    except Exception as exc:
        log_internal_error("suppressed_exception", exc)


def install_window_autofit(root):
    """Applique le garde-fou à la fenêtre principale et à toutes les Toplevel."""
    try:
        def apply_once(w):
            if getattr(w, "_workarea_autofit_done", False):
                return
            # Fenêtres sans décoration (autocomplete, tooltips, toasts,
            # menus flottants...) ont déjà leur position calculée par rapport
            # au widget d'origine. Les recentrer globalement les envoyait au
            # milieu de l'écran.
            try:
                if bool(w.overrideredirect()):
                    return
            except Exception as exc:
                log_internal_error("suppressed_exception", exc)
            w._workarea_autofit_done = True
            w.after_idle(lambda ww=w: ensure_window_visible_and_fitted(ww, 14))

        # Fenêtre principale.
        root.after_idle(lambda: apply_once(root))

        # Toutes les fenêtres secondaires.
        def on_map(event):
            w = event.widget
            if isinstance(w, tk.Toplevel):
                apply_once(w)

        root.bind_class("Toplevel", "<Map>", on_map, add="+")
    except Exception as exc:
        log_internal_error("suppressed_exception", exc)



def position_popup_near_widget(popup, anchor_widget, width, height, gap=2):
    """Place une liste flottante près de son champ sans sortir de l'écran."""
    try:
        anchor_widget.update_idletasks()
        x0, y0, work_w, work_h = get_usable_screen_rect(anchor_widget)
        right = x0 + work_w
        bottom = y0 + work_h
        width = max(120, min(int(width), work_w - 12))
        height = max(40, min(int(height), work_h - 12))
        x = anchor_widget.winfo_rootx()
        below = anchor_widget.winfo_rooty() + anchor_widget.winfo_height() + gap
        above = anchor_widget.winfo_rooty() - height - gap
        y = below if below + height <= bottom - 4 else max(y0 + 4, above)
        x = min(max(x, x0 + 4), max(x0 + 4, right - width - 4))
        popup.wm_geometry(f"{width}x{height}+{int(x)}+{int(y)}")
    except Exception as exc:
        log_internal_error("position_popup_near_widget", exc)
        try:
            popup.wm_geometry(f"{width}x{height}")
        except Exception as inner:
            log_internal_error("position_popup_fallback", inner)


def finalize_suggestion_popup(popup, anchor_widget, listbox, width):
    """Ajuste une liste de suggestions à sa hauteur réelle.

    Une seule proposition garde suffisamment de hauteur pour être entièrement
    lisible, puis la fenêtre est replacée au-dessus ou au-dessous du champ
    sans sortir de l'écran.
    """
    try:
        popup.update_idletasks()
        listbox.update_idletasks()
        requested_height = max(listbox.winfo_reqheight() + 6, gs(34))
        position_popup_near_widget(
            popup, anchor_widget, width, requested_height
        )
    except Exception as exc:
        log_internal_error("finalize_suggestion_popup", exc)


def configure_app_style(root):
    """Configure l'apparence de toute l'application : couleurs ttk (boutons,
    champs, onglets...) ainsi que les widgets Tkinter bruts (Listbox, Text,
    Canvas...) via la base d'options de Tk, qui s'applique automatiquement à
    tous les widgets créés ensuite dans n'importe quelle fenêtre."""
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    base_font = ("Segoe UI", sf(10))

    style.configure(".", background=COLOR_BG, foreground=COLOR_TEXT, font=base_font)
    style.configure("TFrame", background=COLOR_BG)
    style.configure("TLabel", background=COLOR_BG, foreground=COLOR_TEXT)
    style.configure("TCheckbutton", background=COLOR_BG, foreground=COLOR_TEXT)
    style.map("TCheckbutton", background=[("active", COLOR_BG)])

    style.configure("TButton", background=COLOR_ACCENT, foreground=COLOR_ON_ACCENT,
                     font=base_font, padding=(12, 7), borderwidth=0, relief="flat")
    # Keyboard/accessibility: keep a visible focus state and generous rows.
    style.map("TButton", relief=[("focus", "solid")])
    style.configure("Treeview", rowheight=max(gs(28), sf(28)))
    style.configure("Treeview.Heading", font=("Segoe UI", sf(10), "bold"))
    style.map("TButton",
              background=[("active", COLOR_ACCENT_DARK), ("disabled", "#D8CBB8")],
              foreground=[("disabled", "#F4EEE3")])

    style.configure("TEntry", fieldbackground=COLOR_CARD, foreground=COLOR_TEXT,
                     bordercolor=COLOR_BORDER, lightcolor=COLOR_BORDER, darkcolor=COLOR_BORDER,
                     padding=5)
    style.configure("TCombobox", fieldbackground=COLOR_CARD, foreground=COLOR_TEXT,
                     bordercolor=COLOR_BORDER, arrowcolor=COLOR_ACCENT_DARK, padding=5)
    style.map("TCombobox", fieldbackground=[("readonly", COLOR_CARD)])

    style.configure("TLabelframe", background=COLOR_BG, bordercolor=COLOR_BORDER)
    style.configure("TLabelframe.Label", background=COLOR_BG, foreground=COLOR_ACCENT_DARK,
                     font=("Segoe UI", sf(10), "bold"))

    style.configure("TNotebook", background=COLOR_BG, bordercolor=COLOR_BORDER)
    style.configure("TNotebook.Tab", background=COLOR_ACCENT_LIGHT, foreground=COLOR_TEXT,
                     padding=(12, 6), font=base_font)
    style.map("TNotebook.Tab",
              background=[("selected", COLOR_ACCENT)],
              foreground=[("selected", COLOR_ON_ACCENT)])

    style.configure("TScrollbar", background=COLOR_ACCENT, troughcolor=COLOR_BG,
                     bordercolor=COLOR_BG, arrowcolor=COLOR_ON_ACCENT)
    style.map("TScrollbar", background=[("active", COLOR_ACCENT_DARK)])

    style.configure("TSeparator", background=COLOR_BORDER)

    style.configure("TPanedwindow", background=COLOR_BG)

    # Bouton d'action principale (validation, enregistrement...) : jusqu'ici
    # "Primary.TButton" était utilisé partout dans l'app sans jamais être
    # défini, donc visuellement identique à un TButton normal — aucune
    # hiérarchie visuelle entre l'action principale et les actions
    # secondaires d'un même écran. Distingué du TButton normal par un texte
    # gras et un padding plus généreux ; mêmes couleurs (repos/survol/
    # désactivé) que TButton, volontairement, pour rester sur une
    # combinaison déjà utilisée en production.
    style.configure("Primary.TButton", background=COLOR_ACCENT, foreground=COLOR_ON_ACCENT,
                     font=("Segoe UI", sf(10), "bold"), padding=(14, 8), borderwidth=0, relief="flat")
    style.map("Primary.TButton",
              background=[("active", COLOR_ACCENT_DARK), ("disabled", "#D8CBB8")],
              foreground=[("disabled", "#F4EEE3")])

    # Boutons secondaires plus discrets (utilisés pour des actions annexes) :
    # à activer au cas par cas avec style="Secondary.TButton" si besoin plus tard.
    style.configure("Secondary.TButton", background=COLOR_CARD, foreground=COLOR_ACCENT_DARK,
                     padding=(12, 7))
    style.map("Secondary.TButton", background=[("active", COLOR_ACCENT_LIGHT)])

    # Indicateur de focus clavier pour les étoiles de note (ttk.Label ne
    # supporte pas highlightbackground/highlightthickness, contrairement à
    # tk.Label/tk.Frame) : juste un style="TLabel" avec une couleur d'accent
    # échangé au focus/perte de focus, sans style.map (aucun risque du bug
    # de blocage déjà rencontré avec Primary.TButton, spécifique aux "state
    # maps").
    style.configure("RatingStarFocus.TLabel", foreground=COLOR_ACCENT)

    # Menu déroulant de langue : même habillage visuel que les boutons
    # secondaires ci-dessus, pour rester cohérent dans la barre du haut.
    style.configure("Secondary.TMenubutton", background=COLOR_CARD, foreground=COLOR_ACCENT_DARK,
                     padding=(12, 7))
    style.map("Secondary.TMenubutton", background=[("active", COLOR_ACCENT_LIGHT)])

    # Variantes "carte" (fond blanc) pour les encadrés mis en valeur sur la
    # page d'accueil, afin que les widgets ttk placés dedans (Label, Button)
    # aient le même fond que la carte plutôt que le fond général de la page.
    style.configure("Card.TFrame", background=COLOR_CARD)
    style.configure("Card.TLabel", background=COLOR_CARD, foreground=COLOR_TEXT)
    style.configure("Hero.TButton", font=("Segoe UI", sf(11), "bold"), padding=(16, 10))
    # Fond dédié (comme Secondary.TButton) plutôt que d'hériter du fond ACCENT
    # de TButton : texte ERROR sur fond ACCENT tombait à 1.74:1/1.01:1
    # (clair/sombre), bien en dessous du seuil WCAG AA de 4.5:1.
    style.configure("Danger.TButton", background=COLOR_CARD, foreground=COLOR_ERROR, padding=(12, 7))
    style.map("Danger.TButton", background=[("active", COLOR_ACCENT_LIGHT)], foreground=[("active", COLOR_ERROR)])
    style.configure("Title.TLabel", font=("Segoe UI", sf(19), "bold"), foreground=COLOR_TEXT)
    style.configure("Section.TLabel", font=("Segoe UI", sf(12), "bold"), foreground=COLOR_ACCENT_DARK)
    style.configure("Muted.TLabel", foreground=COLOR_TEXT_MUTED)
    style.configure("Toolbar.TFrame", background=COLOR_CARD)

    # ---- Widgets Tkinter bruts (non gérés par ttk) : Listbox, Text, Canvas,
    # Button (celles en tk.Button, ex. mode cuisine), via la base d'options.
    # S'applique à toute fenêtre créée dans l'application, sans exception. ----
    root.option_add("*Font", "{Segoe UI} 10")
    root.option_add("*Background", COLOR_BG)
    root.option_add("*Foreground", COLOR_TEXT)

    root.option_add("*Listbox.Background", COLOR_CARD)
    root.option_add("*Listbox.Foreground", COLOR_TEXT)
    root.option_add("*Listbox.selectBackground", COLOR_ACCENT)
    root.option_add("*Listbox.selectForeground", COLOR_ON_ACCENT)
    root.option_add("*Listbox.borderWidth", 1)
    root.option_add("*Listbox.relief", "solid")
    root.option_add("*Listbox.highlightThickness", 0)

    root.option_add("*Text.Background", COLOR_CARD)
    root.option_add("*Text.Foreground", COLOR_TEXT)
    root.option_add("*Text.borderWidth", 1)
    root.option_add("*Text.relief", "solid")
    root.option_add("*Text.highlightThickness", 0)

    root.option_add("*Canvas.Background", COLOR_BG)
    root.option_add("*Canvas.highlightThickness", 0)

    root.option_add("*Button.Background", COLOR_ACCENT)
    root.option_add("*Button.Foreground", COLOR_ON_ACCENT)
    root.option_add("*Button.activeBackground", COLOR_ACCENT_DARK)
    root.option_add("*Button.activeForeground", COLOR_ON_ACCENT)
    root.option_add("*Button.relief", "flat")
    root.option_add("*Button.borderWidth", 0)
    root.option_add("*Button.padX", 10)
    root.option_add("*Button.padY", 5)

    root.option_add("*Entry.Background", COLOR_CARD)
    root.option_add("*Entry.Foreground", COLOR_TEXT)
    root.option_add("*Entry.relief", "solid")
    root.option_add("*Entry.borderWidth", 1)

    return style


class App(APP_TK_BASE):
    def __init__(self):
        try:
            super().__init__()
        except RuntimeError as exc:
            if not TKDND_AVAILABLE or "tkdnd" not in str(exc).lower():
                raise
            # TkinterDnD.Tk crée d'abord une vraie fenêtre Tk (tkinter.Tk.
            # __init__) puis charge l'extension Tcl tkdnd dans un second
            # temps : cette 2e étape échoue de façon intermittente (constaté
            # plusieurs fois en CI Windows, jamais reproduit localement),
            # sans rapport avec le code de l'application — la fenêtre existe
            # déjà à ce stade. On retente le chargement seul avant
            # d'abandonner le glisser-déposer pour cette fenêtre plutôt que
            # de faire planter toute l'application pour un souci mineur
            # (_enable_photo_drop gère déjà l'absence de tkdnd en dégradé).
            self.TkdndVersion = None
            for _attempt in range(3):
                time.sleep(0.2)
                try:
                    self.TkdndVersion = TkinterDnD._require(self)
                    break
                except RuntimeError:
                    continue
        install_tk_exception_logger(self)
        # Le mode « Texte agrandi » doit être chargé et appliqué AVANT tout
        # calcul de géométrie ci-dessous (via gs()), sans quoi la fenêtre
        # s'ouvrirait à sa taille normale au premier lancement même si ce
        # mode était déjà activé lors d'une session précédente.
        self.large_text = get_large_text_preference()
        apply_font_scale(self.large_text)
        self.language = get_language_preference()
        apply_language(self.language)
        self.title(f"{t('home_window_title')} — {PRODUCT_VERSION} (build {APP_BUILD})")
        # Icônes de drapeaux pour le bouton de langue, chargées une seule
        # fois ici (et non à chaque reconstruction de la page d'accueil)
        # pour éviter de relire le fichier à chaque bascule. Une référence
        # doit être conservée sur self, sans quoi Tkinter "oublierait"
        # l'image (garbage collection) et le bouton se retrouverait sans
        # icône. Si un fichier est absent (ex. copie incomplète de
        # l'application), le bouton reste utilisable, juste sans icône
        # pour cette langue-là.
        self.flag_photos = {}
        for lang_code, flag_path in FLAG_FILES.items():
            try:
                if os.path.exists(flag_path):
                    self.flag_photos[lang_code] = tk.PhotoImage(file=flag_path)
            except tk.TclError:
                pass
        # La hauteur de la fenêtre correspond à la hauteur de l'écran sur
        # lequel l'application est lancée, pour profiter de tout l'espace
        # vertical disponible dès le démarrage. La largeur est fixée pour
        # accueillir les boutons et les cartes "Aujourd'hui"/"Récemment
        # consultées" côte à côte.
        # Accueil : utiliser presque toute la largeur réellement disponible.
        # C'est volontairement indépendant d'une largeur fixe afin d'être
        # confortable aussi bien en 1366 px qu'en 1920/2560 px.
        _wx, _wy, _work_w, _work_h = get_usable_screen_rect(self)
        fit_window_to_workarea(
            self,
            max(gs(1100), int(_work_w * 0.97)),
            get_usable_screen_height(self),
            margin=14
        )
        safe_minsize(self, min(gs(1000), max(820, int(_work_w * 0.72))), gs(500))
        install_window_autofit(self)
        self.resizable(True, True)

        self.dark_mode = get_dark_mode_preference()
        apply_palette(self.dark_mode)
        configure_app_style(self)
        self.configure(background=COLOR_BG)
        install_select_all_bindings(self)

        # ---- Clause de responsabilité : obligatoire au tout premier
        # lancement, l'application reste inutilisable tant qu'elle n'est
        # pas acceptée. ----
        if not get_disclaimer_accepted():
            self.withdraw()
            disclaimer = DisclaimerWindow(self)
            self.wait_window(disclaimer)
            if not disclaimer.accepted:
                return  # _quit_app() a déjà fermé l'application (sys.exit)
            self.deiconify()

        self.recipes = load_recipes()
        self.ingredient_names = sync_ingredients_from_recipes()
        if not get_corrupted_data_files():
            try:
                migrate_data_schema(self.recipes)
            except Exception as exc:
                log_internal_error("migrate_data_schema", exc)
        # Déclenche les migrations rétrocompatibles vers les identifiants stables.
        if not get_corrupted_data_files():
            try:
                load_weekly_plan(); load_weekly_plan_history(); load_weekly_plan_templates(); load_menus(); _load_recent_view_refs()
                get_daily_recipe(self.recipes) if self.recipes else None
            except Exception as exc:
                log_internal_error("recipe_reference_migration", exc)
        self.shopping_selection = {}  # sélection en cours pour la liste de courses (id stable -> personnes)
        self.timers_window = None  # fenêtre unique des minuteurs, créée à la demande

        # Recherche rapide de recette (Ctrl+K), accessible depuis n'importe
        # quelle fenêtre de l'application, y compris par-dessus une fenêtre
        # modale (bind_all s'applique quelle que soit la fenêtre au premier
        # plan).
        self.bind_all("<Control-k>", lambda e: self.open_quick_search())
        self.bind_all("<Control-n>", lambda e: self.open_add_recipe())
        self.bind_all("<Control-Shift-L>", lambda e: self.open_manage_recipes())
        self.bind_all("<Control-Shift-M>", lambda e: MaintenanceWindow(self))
        self.bind_all("<F1>", lambda e: DiagnosticWindow(self))

        # Sauvegarde automatique périodique (silencieuse, ne bloque jamais le démarrage)
        threading.Thread(target=maybe_create_auto_backup, daemon=True).start()

        self._build_home_ui()
        try:
            cleanup_stale_import_temp()
        except Exception as exc:
            log_internal_error("cleanup_stale_import_temp", exc)
        if get_corrupted_data_files():
            self.after(150, self._offer_corrupt_data_recovery)

    def _offer_corrupt_data_recovery(self):
        corrupted = get_corrupted_data_files()
        if not corrupted:
            return
        names = ", ".join(sorted(os.path.basename(item["path"]) for item in corrupted))
        backups = list_auto_backups()
        if backups and ask_yes_no(
                t("corruptdata_title"),
                t("corruptdata_restore_prompt", files=names), parent=self):
            try:
                restore_from_zip(backups[0], merge=False)
                self.recipes = load_recipes()
                self.ingredient_names = sync_ingredients_from_recipes()
                for child in self.winfo_children():
                    if not isinstance(child, tk.Toplevel):
                        child.destroy()
                self._build_home_ui()
                messagebox.showinfo(
                    t("corruptdata_recovered_title"),
                    t("corruptdata_recovered_message"), parent=self
                )
                return
            except Exception as exc:
                log_internal_error("corruptdata_restore_failed", exc)
                messagebox.showerror(
                    t("common_error"),
                    t("corruptdata_restore_failed", error=exc), parent=self
                )
        copies = "\n".join(item.get("backup") or item["path"] for item in corrupted)
        messagebox.showwarning(
            t("corruptdata_title"),
            t("corruptdata_blocked_message", files=names, copies=copies), parent=self
        )

    def _recipes_available(self):
        """Retourne True si au moins une recette existe. Sinon, plutôt
        qu'un message bloquant sans suite possible, propose de créer la
        première recette tout de suite : si l'utilisateur accepte et
        l'enregistre, la fonctionnalité demandée s'ouvre normalement juste
        après avec les données fraîchement créées."""
        if self.recipes:
            return True
        if messagebox.askyesno(t("common_info"), t("home_empty_prompt_create_recipe")):
            self.open_add_recipe()
        return bool(self.recipes)

    def open_quick_search(self):
        if not self._recipes_available():
            return
        QuickSearchWindow(self)

    def open_donate_page(self):
        webbrowser.open("https://buymeacoffee.com/majogari")

    def toggle_dark_mode(self):
        """Bascule entre thème clair et sombre : met à jour la palette, les
        styles ttk (effet immédiat sur toutes les fenêtres déjà ouvertes),
        puis reconstruit entièrement la page d'accueil pour que ses widgets
        Tkinter bruts (bannière, cartes...) reflètent aussi les nouvelles
        couleurs. Les couleurs explicites des fenêtres secondaires sont
        remplacées sans fermer ces fenêtres."""
        old_palette = dict(DARK_PALETTE if self.dark_mode else LIGHT_PALETTE)
        self.dark_mode = not self.dark_mode
        set_dark_mode_preference(self.dark_mode)
        apply_palette(self.dark_mode)
        new_palette = dict(DARK_PALETTE if self.dark_mode else LIGHT_PALETTE)
        configure_app_style(self)
        self.configure(background=COLOR_BG)
        # Ne détruit que les widgets propres à la page d'accueil : les
        # fenêtres secondaires (Toplevel) déjà ouvertes — comme les
        # minuteurs en cours — ne doivent surtout pas être affectées.
        for child in self.winfo_children():
            if not isinstance(child, tk.Toplevel):
                child.destroy()
        self._build_home_ui()
        _ui_recolor_open_windows(self, old_palette, new_palette)
        _ui_refresh_open_windows(self)

    def toggle_large_text(self):
        """Bascule le mode Texte agrandi et rafraîchit l'interface ouverte."""
        old_scale = FONT_SCALE
        self.large_text = not self.large_text
        set_large_text_preference(self.large_text)
        apply_font_scale(self.large_text)
        configure_app_style(self)
        # La fenêtre principale doit être redimensionnée comme au démarrage
        # (gs(1100) dépend de l'échelle de police) : sinon, en agrandissant
        # le texte sans agrandir la fenêtre, la barre du haut (recherche,
        # bouton Paramètres, sélecteur de langue) devient trop étroite pour
        # son propre contenu et son texte se retrouve tronqué.
        _wx, _wy, _work_w, _work_h = get_usable_screen_rect(self)
        fit_window_to_workarea(
            self,
            max(gs(1100), int(_work_w * 0.97)),
            get_usable_screen_height(self),
            margin=14
        )
        for child in self.winfo_children():
            if not isinstance(child, tk.Toplevel):
                child.destroy()
        self._build_home_ui()
        _ui_rescale_open_window_fonts(self, FONT_SCALE / old_scale)
        _ui_refresh_open_windows(self)

    def set_language(self, lang):
        """Change la langue de l'interface vers celle choisie dans le menu.
        Les parties pas encore traduites restent affichées en français.
        Les fenêtres secondaires sont notifiées pour rafraîchir les éléments
        qu'elles savent reconstruire sans perdre une saisie en cours."""
        if lang == self.language:
            return
        old_language = self.language
        self.language = lang
        set_language_preference(self.language)
        apply_language(self.language)
        self.title(f"{t('home_window_title')} — {PRODUCT_VERSION} (build {APP_BUILD})")
        for child in self.winfo_children():
            if not isinstance(child, tk.Toplevel):
                child.destroy()
        self._build_home_ui()
        _ui_translate_open_windows(self, old_language, self.language)
        _ui_refresh_open_windows(self)

    def show_toast(self, message, duration=2400):
        """Petite notification non bloquante pour les réussites courantes."""
        toast = tk.Toplevel(self)
        toast.overrideredirect(True)
        toast.attributes("-topmost", True)
        frame = tk.Frame(toast, background=COLOR_CARD, highlightbackground=COLOR_BORDER, highlightthickness=1)
        frame.pack(fill="both", expand=True)
        tk.Label(frame, text=f"✓  {message}", background=COLOR_CARD, foreground=COLOR_TEXT,
                 font=("Segoe UI", sf(10), "bold"), padx=16, pady=10).pack()
        self.update_idletasks()
        toast.update_idletasks()
        x = self.winfo_rootx() + max(10, self.winfo_width() - toast.winfo_reqwidth() - 24)
        y = self.winfo_rooty() + max(10, self.winfo_height() - toast.winfo_reqheight() - 70)
        toast.geometry(f"+{x}+{y}")
        toast.after(duration, toast.destroy)

    def _open_home_search(self, event=None):
        query = self.home_search_var.get().strip() if hasattr(self, "home_search_var") else ""
        if query and query != t("home_search_placeholder"):
            self.open_manage_recipes(initial_search=query)
        else:
            self.open_quick_search()

    def _build_home_ui(self):
        for child in self.winfo_children():
            if not isinstance(child, tk.Toplevel):
                child.destroy()

        # Barre supérieure : le bouton de don reste volontairement très visible
        # à chaque lancement, conformément au choix de l'éditeur.
        top_bar = tk.Frame(self, background=COLOR_CARD, highlightbackground=COLOR_BORDER, highlightthickness=1)
        top_bar.pack(fill="x")
        ttk.Button(top_bar, text=t("home_donate_button"), style="Hero.TButton",
                   command=self.open_donate_page).pack(side="left", padx=gs(SPACE_MD), pady=gs(SPACE_SM))
        ttk.Label(top_bar, text=t("home_window_title"), font=("Segoe UI", sf(15), "bold"),
                  style="Card.TLabel").pack(side="left", padx=(gs(SPACE_XS), gs(SPACE_MD)))

        # Recherche visible (Ctrl+K reste disponible partout).
        search_wrap = ttk.Frame(top_bar, style="Card.TFrame")
        search_wrap.pack(side="left", fill="x", expand=True, padx=gs(SPACE_SM), pady=gs(SPACE_SM))
        self.home_search_var = tk.StringVar()
        home_search = ttk.Entry(search_wrap, textvariable=self.home_search_var, font=("Segoe UI", sf(10)))
        home_search.pack(side="left", fill="x", expand=True, ipady=4)
        home_search.insert(0, t("home_search_placeholder"))
        home_search.configure(foreground=COLOR_TEXT_MUTED)
        def _search_focus_in(event):
            if self.home_search_var.get() == t("home_search_placeholder"):
                self.home_search_var.set("")
                home_search.configure(foreground=COLOR_TEXT)
        def _search_focus_out(event):
            if not self.home_search_var.get().strip():
                self.home_search_var.set(t("home_search_placeholder"))
                home_search.configure(foreground=COLOR_TEXT_MUTED)
        home_search.bind("<FocusIn>", _search_focus_in)
        home_search.bind("<FocusOut>", _search_focus_out)
        home_search.bind("<Return>", self._open_home_search)
        ttk.Button(search_wrap, text="🔎", width=3, command=self._open_home_search).pack(side="left", padx=(gs(SPACE_SM), 0))

        language_names = {"fr": "Français", "en": "English", "es": "Español", "de": "Deutsch"}
        current_flag = self.flag_photos.get(self.language)
        language_kwargs = {"text": language_names.get(self.language, "Français")}
        if current_flag is not None:
            language_kwargs.update(image=current_flag, compound="left")
        lang_btn = ttk.Menubutton(top_bar, style="Secondary.TMenubutton", **language_kwargs)
        lang_menu = tk.Menu(lang_btn, tearoff=False)
        for code in ("fr", "en", "es", "de"):
            item = {"label": language_names[code], "command": lambda c=code: self.set_language(c)}
            flag = self.flag_photos.get(code)
            if flag is not None:
                item.update(image=flag, compound="left")
            lang_menu.add_command(**item)
        lang_btn["menu"] = lang_menu
        lang_btn.pack(side="right", padx=(gs(SPACE_XS), gs(SPACE_MD)), pady=gs(SPACE_SM))

        settings_btn = ttk.Menubutton(top_bar, text=t("home_settings_button"), style="Secondary.TMenubutton")
        settings_menu = tk.Menu(settings_btn, tearoff=False)
        settings_menu.add_command(label=t("home_light_theme") if self.dark_mode else t("home_dark_theme"), command=self.toggle_dark_mode)
        settings_menu.add_command(label=t("home_large_text_off") if self.large_text else t("home_large_text_on"), command=self.toggle_large_text)
        settings_menu.add_separator()
        settings_menu.add_command(label=t("home_btn_import_export"), command=self.open_import_export)
        settings_menu.add_command(label=t("diagnostic_button"), command=lambda: DiagnosticWindow(self))
        settings_menu.add_command(label=t("keyboard_shortcuts"), command=lambda: messagebox.showinfo(t("keyboard_shortcuts"), t("keyboard_shortcuts_text"), parent=self))
        settings_btn["menu"] = settings_menu
        settings_btn.pack(side="right", padx=gs(SPACE_XS), pady=gs(SPACE_SM))

        outer = ttk.Frame(self)
        outer.pack(fill="both", expand=True)
        canvas = tk.Canvas(outer, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        content = ttk.Frame(canvas)
        window_id = canvas.create_window((0, 0), window=content, anchor="n")
        content.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window_id, width=max(e.width, gs(720))))
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        _ui_bind_local_mousewheel(
            canvas, content,
            lambda ev: canvas.yview_scroll(int(-ev.delta / 120), "units")
        )

        hero = tk.Frame(content, background=COLOR_ACCENT)
        hero.pack(fill="x")
        tk.Label(hero, text=t("home_banner_title"), font=("Segoe UI", sf(22), "bold"),
                 background=COLOR_ACCENT, foreground=COLOR_ON_ACCENT).pack(pady=(gs(SPACE_LG), gs(SPACE_XS)))
        tk.Label(hero, text=t("home_banner_subtitle"), font=("Segoe UI", sf(10)),
                 background=COLOR_ACCENT, foreground=COLOR_ON_ACCENT).pack(pady=(0, gs(SPACE_MD)))

        main = ttk.Frame(content)
        main.pack(fill="x", padx=max(gs(SPACE_LG), gs(34)), pady=gs(SPACE_LG))

        # Quatre entrées principales : toute la carte est cliquable.
        primary = ttk.Frame(main)
        primary.pack(fill="x")
        low_stock = get_low_stock_pantry_items()
        cards = [
            (t("home_primary_recipes"), t("home_primary_recipes_sub", count=len(self.recipes)), self.open_manage_recipes),
            (t("home_primary_shopping"), t("home_primary_shopping_sub"), self.open_all_recipes),
            (t("home_primary_planning"), t("home_primary_planning_sub"), self.open_weekly_plan),
            (t("home_primary_pantry"), t("home_primary_pantry_sub", count=len(low_stock)), self.open_pantry),
        ]
        for col, (title, subtitle, command) in enumerate(cards):
            primary.columnconfigure(col, weight=1, uniform="primary")
            card = tk.Frame(primary, background=COLOR_CARD, highlightbackground=COLOR_BORDER,
                             highlightcolor=COLOR_BORDER, highlightthickness=1, cursor="hand2", takefocus=1)
            card.grid(row=0, column=col, sticky="nsew",
                      padx=(0 if col == 0 else gs(SPACE_SM), 0 if col == 3 else gs(SPACE_SM)), pady=gs(SPACE_XS))
            title_lbl = tk.Label(card, text=title, background=COLOR_CARD, foreground=COLOR_ACCENT_DARK,
                                 font=("Segoe UI", sf(12), "bold"), cursor="hand2")
            title_lbl.pack(padx=gs(SPACE_MD), pady=(gs(SPACE_MD), gs(SPACE_XS)))
            sub_lbl = tk.Label(card, text=subtitle, background=COLOR_CARD, foreground=COLOR_TEXT_MUTED,
                               font=("Segoe UI", sf(9)), cursor="hand2")
            sub_lbl.pack(padx=gs(SPACE_MD), pady=(0, gs(SPACE_MD)))
            for w in (card, title_lbl, sub_lbl):
                w.bind("<Button-1>", lambda e, c=command: c())
            # Ces 4 cartes sont les entrées principales de navigation de
            # l'accueil : atteignables au clavier (Tab) comme les cartes de
            # recettes, avec le même indicateur de focus visible.
            card.bind("<FocusIn>", lambda e, c=card: c.configure(
                highlightbackground=COLOR_ACCENT, highlightcolor=COLOR_ACCENT, highlightthickness=2))
            card.bind("<FocusOut>", lambda e, c=card: c.configure(
                highlightbackground=COLOR_BORDER, highlightcolor=COLOR_BORDER, highlightthickness=1))
            card.bind("<Return>", lambda e, c=command: c())
            card.bind("<space>", lambda e, c=command: c())

        # Filtres rapides, compacts.
        filters = ttk.Frame(main)
        filters.pack(fill="x", pady=(gs(SPACE_MD), 0))
        for text, qf in [
            (t("home_quick_filter_favorites"), "favoris"),
            (t("home_quick_filter_quick"), "rapide"),
            (t("home_quick_filter_vegetarian"), "vegetarien"),
            (t("home_quick_filter_wishlist"), "envie"),
        ]:
            ttk.Button(filters, text=text, style="Secondary.TButton",
                       command=lambda f=qf: self.open_manage_recipes(quick_filter=f)).pack(side="left", padx=(0, gs(SPACE_SM)))

        # Recette du jour : carte large et visuelle.
        daily_recipe = get_daily_recipe(self.recipes)
        if daily_recipe is not None:
            ttk.Label(main, text=t("home_daily_recipe_title"), style="Section.TLabel").pack(anchor="w", pady=(gs(SPACE_LG), gs(SPACE_SM)))
            daily = tk.Frame(main, background=COLOR_CARD, highlightbackground=COLOR_BORDER, highlightthickness=1, cursor="hand2")
            daily.pack(fill="x")
            left = ttk.Frame(daily, style="Card.TFrame")
            left.pack(side="left", fill="both", expand=True, padx=gs(SPACE_MD), pady=gs(SPACE_MD))
            star = "⭐ " if daily_recipe.get("favorite") else ""
            ttk.Label(left, text=f"{star}{daily_recipe['name']}", font=("Segoe UI", sf(14), "bold"), style="Card.TLabel").pack(anchor="w")
            meta = []
            if daily_recipe.get("category"):
                meta.append(translate_category_name(daily_recipe.get("category")))
            try:
                total = float(daily_recipe.get("prep_time") or 0) + float(daily_recipe.get("cook_time") or 0)
                if total: meta.append(f"⏱ {int(total) if total == int(total) else total} min")
            except Exception as exc:
                log_internal_error("suppressed_exception", exc)
            if daily_recipe.get("difficulty"):
                meta.append(translate_difficulty_name(daily_recipe.get("difficulty")))
            ttk.Label(left, text="  •  ".join(meta), style="Card.TLabel", foreground=COLOR_TEXT_MUTED).pack(anchor="w", pady=(gs(SPACE_XS), 0))
            ttk.Button(daily, text=t("home_open_button"), command=lambda r=daily_recipe: self._open_daily_recipe(r)).pack(side="right", padx=gs(SPACE_MD))

        two_col = ttk.Frame(main)
        two_col.pack(fill="x", pady=(gs(SPACE_LG), 0))
        two_col.columnconfigure(0, weight=1, uniform="homecol")
        two_col.columnconfigure(1, weight=1, uniform="homecol")

        today_card = tk.Frame(two_col, background=COLOR_CARD, highlightbackground=COLOR_BORDER, highlightthickness=1)
        today_card.grid(row=0, column=0, sticky="nsew", padx=(0, gs(SPACE_SM)))
        ttk.Label(today_card, text=t("home_today_title"), style="Card.TLabel", font=("Segoe UI", sf(12), "bold")).pack(anchor="w", padx=gs(SPACE_MD), pady=(gs(SPACE_MD), gs(SPACE_SM)))
        self.today_frame = ttk.Frame(today_card, style="Card.TFrame")
        self.today_frame.pack(fill="x", padx=gs(SPACE_MD), pady=(0, gs(SPACE_MD)))
        self._refresh_today_meals()

        recent_card = tk.Frame(two_col, background=COLOR_CARD, highlightbackground=COLOR_BORDER, highlightthickness=1)
        recent_card.grid(row=0, column=1, sticky="nsew", padx=(gs(SPACE_SM), 0))
        ttk.Label(recent_card, text=t("home_recent_title"), style="Card.TLabel", font=("Segoe UI", sf(12), "bold")).pack(anchor="w", padx=gs(SPACE_MD), pady=(gs(SPACE_MD), gs(SPACE_SM)))
        self.recent_frame = ttk.Frame(recent_card, style="Card.TFrame")
        self.recent_frame.pack(fill="x", padx=gs(SPACE_MD), pady=(0, gs(SPACE_MD)))
        self._refresh_recent_views()

        # Alertes utiles regroupées, au lieu de plusieurs bandeaux concurrents.
        ttk.Label(main, text=t("home_alerts_title"), style="Section.TLabel").pack(anchor="w", pady=(gs(SPACE_LG), gs(SPACE_SM)))
        alerts = tk.Frame(main, background=COLOR_CARD, highlightbackground=COLOR_BORDER, highlightthickness=1)
        alerts.pack(fill="x")

        def _make_alert_row_focusable(row, action):
            # Ces bandeaux d'alerte étaient cliquables à la souris
            # uniquement : atteignables au clavier (Tab) désormais, avec un
            # anneau de focus visible (invisible au repos, l'anneau se
            # confond avec le fond de la carte tant que la ligne n'a pas le
            # focus clavier).
            row.configure(highlightbackground=COLOR_CARD, highlightcolor=COLOR_CARD,
                          highlightthickness=2, takefocus=1)
            row.bind("<Return>", lambda e: action())
            row.bind("<space>", lambda e: action())
            row.bind("<FocusIn>", lambda e, r=row: r.configure(
                highlightbackground=COLOR_ACCENT, highlightcolor=COLOR_ACCENT))
            row.bind("<FocusOut>", lambda e, r=row: r.configure(
                highlightbackground=COLOR_CARD, highlightcolor=COLOR_CARD))

        any_alert = False
        if low_stock:
            any_alert = True
            names = ", ".join(sorted(e["name"] for e in low_stock))
            row = tk.Label(alerts, text=t("home_low_stock_reminder", count=len(low_stock), names=names),
                           background=COLOR_CARD, foreground=COLOR_TEXT, anchor="w", justify="left", cursor="hand2",
                           font=("Segoe UI", sf(9)), wraplength=850)
            row.pack(fill="x", padx=gs(SPACE_MD), pady=gs(SPACE_SM))
            row.bind("<Button-1>", lambda e, items=low_stock: self._open_low_stock_to_cart(items))
            _make_alert_row_focusable(row, lambda items=low_stock: self._open_low_stock_to_cart(items))
        expiring = get_expiring_pantry_items(days=5)
        if expiring:
            any_alert = True
            row = tk.Label(alerts, text=t("home_expiring_reminder", count=len(expiring)),
                           background=COLOR_CARD, foreground=COLOR_TEXT, anchor="w", justify="left", cursor="hand2",
                           font=("Segoe UI", sf(9)), wraplength=850)
            row.pack(fill="x", padx=gs(SPACE_MD), pady=gs(SPACE_SM))
            row.bind("<Button-1>", lambda e, items=expiring: UseSoonRecipesWindow(self, items))
            _make_alert_row_focusable(row, lambda items=expiring: UseSoonRecipesWindow(self, items))
        stale = []
        for r in self.recipes:
            if r.get("wishlist") and r.get("wishlist_since"):
                try:
                    if (datetime.now() - datetime.fromisoformat(r["wishlist_since"])).days >= 90:
                        stale.append(r)
                except (ValueError, TypeError):
                    pass
        if stale:
            any_alert = True
            row = tk.Label(alerts, text=t("home_wishlist_reminder", count=len(stale), days=90),
                           background=COLOR_CARD, foreground=COLOR_TEXT, anchor="w", justify="left", cursor="hand2",
                           font=("Segoe UI", sf(9)), wraplength=850)
            row.pack(fill="x", padx=gs(SPACE_MD), pady=gs(SPACE_SM))
            row.bind("<Button-1>", lambda e: self.open_manage_recipes(quick_filter="envie"))
            _make_alert_row_focusable(row, lambda: self.open_manage_recipes(quick_filter="envie"))
        if not any_alert:
            ttk.Label(alerts, text=t("home_no_alerts"), style="Card.TLabel", foreground=COLOR_TEXT_MUTED).pack(anchor="w", padx=gs(SPACE_MD), pady=gs(SPACE_MD))

        # Outils secondaires : regroupés par usage pour éviter une grande
        # grille compacte difficile à parcourir visuellement.
        ttk.Label(main, text=t("home_more_tools"), style="Section.TLabel").pack(
            anchor="w", pady=(gs(SPACE_LG), gs(SPACE_SM))
        )

        tools_grid = ttk.Frame(main)
        tools_grid.pack(fill="x", pady=(0, gs(SPACE_SM)))
        tools_grid.columnconfigure(0, weight=1, uniform="toolgroups")
        tools_grid.columnconfigure(1, weight=1, uniform="toolgroups")

        tool_groups = [
            (
                t("home_tools_create_import"),
                [
                    (t("home_btn_add_recipe"), self.open_add_recipe),
                    (t("home_btn_import_url"), self.open_import_from_url),
                    (t("home_btn_import_photo"), self.open_import_from_photo),
                    (t("home_btn_import_qr"), self.open_import_from_qr),
                ],
            ),
            (
                t("home_tools_recipes_ingredients"),
                [
                    (t("home_btn_view_one_recipe"), self.open_one_recipe),
                    (t("home_btn_compare_recipes"), self.open_compare_recipes),
                    (t("home_btn_manage_ingredients"), self.open_manage_ingredients),
                    (t("home_btn_ingredient_search"), self.open_ingredient_search),
                    (t("home_btn_what_can_i_cook"), self.open_what_can_i_cook),
                    (t("home_btn_unit_converter"), self.open_unit_converter),
                ],
            ),
            (
                t("home_tools_organization"),
                [
                    (t("home_btn_weekly_history"), self.open_weekly_plan_history),
                    (t("home_btn_menus"), self.open_menus),
                ],
            ),
            (
                t("home_tools_data"),
                [
                    (t("home_btn_statistics"), self.open_statistics),
                    (t("home_btn_export_cookbook"), self.open_cookbook_export),
                    (t("home_btn_trash"), self.open_trash),
                ],
            ),
        ]

        for group_index, (group_title, items) in enumerate(tool_groups):
            row = group_index // 2
            col = group_index % 2
            group = ttk.LabelFrame(tools_grid, text=group_title, padding=gs(SPACE_MD))
            group.grid(
                row=row, column=col, sticky="nsew",
                padx=(0, gs(SPACE_SM)) if col == 0 else (gs(SPACE_SM), 0),
                pady=(0, gs(SPACE_MD))
            )
            group.columnconfigure(0, weight=1)
            # Boutons verticaux : beaucoup plus faciles à lire que l'ancienne
            # matrice de 3 colonnes.
            for i, (label, command) in enumerate(items):
                ttk.Button(
                    group, text=label, style="Secondary.TButton",
                    command=command
                ).grid(
                    row=i, column=0, sticky="ew",
                    padx=2, pady=4, ipady=2
                )

        warnings = []
        if not PIL_AVAILABLE: warnings.append(t("warning_pillow"))
        if not REPORTLAB_AVAILABLE: warnings.append(t("warning_reportlab"))
        if not OPENPYXL_AVAILABLE: warnings.append(t("warning_openpyxl"))
        if not QRCODE_AVAILABLE: warnings.append(t("warning_qrcode"))
        if not PYTESSERACT_AVAILABLE: warnings.append(t("warning_pytesseract"))
        if warnings:
            ttk.Label(main, text="\n".join(warnings), foreground=COLOR_ERROR, justify="center").pack(pady=gs(SPACE_SM))

        self.footer = ttk.Label(self, text=t("home_footer_recipe_count", count=len(self.recipes)), font=("Segoe UI", sf(9)))
        self.footer.pack(side="bottom", pady=gs(SPACE_SM))

    def refresh_recipes(self):
        self.recipes = load_recipes()
        self.footer.config(text=t("home_footer_recipe_count", count=len(self.recipes)))
        # Synchronise les fiches ouvertes avec la recette fraîchement
        # rechargée (notamment après une cuisson enregistrée depuis le mode
        # cuisine), afin d'éviter une fiche restée en mémoire.
        for child in list(self.winfo_children()):
            if not isinstance(child, OneRecipeWindow) or not child.winfo_exists():
                continue
            current = getattr(child, "current_recipe", None)
            if current is None:
                continue
            refreshed = find_recipe_by_id(self.recipes, current.get("id")) or find_recipe_by_name(
                self.recipes, current.get("name", "")
            )
            if refreshed is None:
                continue
            child.current_recipe = refreshed
            try:
                child._display_recipe(refreshed)
            except tk.TclError as exc:
                log_internal_error("refresh_open_recipe", exc)

    def _refresh_today_meals(self):
        for child in self.today_frame.winfo_children():
            child.destroy()

        today_name = WEEKDAYS[datetime.now().weekday()]  # 0=Lundi ... 6=Dimanche
        plan = load_weekly_plan()
        day_data = plan.get(today_name) or {}

        entries = []
        for slot in WeeklyPlanWindow.MEAL_SLOTS:
            slot_data = day_data.get(slot)
            if slot_data and slot_data.get("recipe_name"):
                entries.append((slot, slot_data["recipe_name"], slot_data.get("persons", 1)))

        if not entries:
            ttk.Label(
                self.today_frame,
                text=t("home_nothing_planned", day=(
                    translate_weekday_name(today_name).lower() if CURRENT_LANGUAGE == "fr"
                    else translate_weekday_name(today_name)
                )),
                font=("Segoe UI", sf(9)), foreground=COLOR_TEXT_MUTED, wraplength=560, justify="left",
                style="Card.TLabel"
            ).pack(anchor="w", pady=3)
            return

        ttk.Label(self.today_frame, text=translate_weekday_name(today_name), font=("Segoe UI", sf(9), "bold"),
                  foreground=COLOR_TEXT_MUTED, style="Card.TLabel").pack(anchor="w")
        for slot, recipe_name, persons in entries:
            row = ttk.Frame(self.today_frame, style="Card.TFrame")
            row.pack(fill="x", pady=1)
            ttk.Label(row, text=f"{translate_mealslot_name(slot)} :", width=18, anchor="w", style="Card.TLabel").pack(side="left")
            ttk.Label(row, text=f"{recipe_name} ({persons} pers.)", anchor="w",
                      style="Card.TLabel").pack(side="left")
            preview_btn = ttk.Button(row, text="👁", width=3,
                       command=lambda n=recipe_name: self._open_today_recipe(n))
            preview_btn.pack(side="left", padx=5)
            add_tooltip(preview_btn, t("tooltip_preview_recipe"))

    def _open_today_recipe(self, recipe_name):
        win = OneRecipeWindow(self, initial_recipe_name=recipe_name)
        self.wait_window(win)
        self._refresh_recent_views()

    def _refresh_recent_views(self):
        if not hasattr(self, "recent_frame"):
            return
        for child in self.recent_frame.winfo_children():
            child.destroy()
        names = load_recent_view_names()
        self._recent_recipes = []
        for name in names[:5]:
            recipe = find_recipe_by_name(self.recipes, name)
            if recipe is not None:
                self._recent_recipes.append(recipe)
        if not self._recent_recipes:
            ttk.Label(self.recent_frame, text=t("home_recent_empty_title"), style="Card.TLabel",
                      font=("Segoe UI", sf(10), "bold")).pack(anchor="w")
            ttk.Label(self.recent_frame, text=t("home_recent_empty_sub"), style="Card.TLabel",
                      foreground=COLOR_TEXT_MUTED).pack(anchor="w", pady=(2, 0))
            return
        for recipe in self._recent_recipes:
            row = tk.Frame(self.recent_frame, background=COLOR_CARD, cursor="hand2")
            row.pack(fill="x", pady=2)
            name_lbl = tk.Label(row, text=recipe.get("name", ""), background=COLOR_CARD, foreground=COLOR_TEXT,
                                font=("Segoe UI", sf(9), "bold"), anchor="w", cursor="hand2")
            name_lbl.pack(side="left", fill="x", expand=True)
            meta = translate_category_name(recipe.get("category", "Autre"))
            meta_lbl = tk.Label(row, text=meta, background=COLOR_CARD, foreground=COLOR_TEXT_MUTED,
                                font=("Segoe UI", sf(8)), cursor="hand2")
            meta_lbl.pack(side="right")
            for w in (row, name_lbl, meta_lbl):
                w.bind("<Button-1>", lambda e, r=recipe: self._open_daily_recipe(r))

    def _open_daily_recipe(self, recipe):
        OneRecipeWindow(self, initial_recipe_name=recipe["name"])

    def _open_low_stock_to_cart(self, items):
        win = AllRecipesWindow(self)
        # Le seuil d'alerte sert de quantité suggérée à racheter (une
        # estimation raisonnable de « combien en garder en stock »).
        to_add = [{"name": e["name"], "quantity": e["threshold"], "unit": e["unit"]} for e in items]
        win.add_manual_items(to_add)


    def _refresh_wishlist_sample(self):
        """Tire au sort jusqu'à 10 recettes parmi celles de la liste d'envies
        (« à essayer »), pour donner une nouvelle idée à chaque tirage plutôt
        que de toujours montrer les mêmes en premier."""
        self.wishlist_listbox.delete(0, tk.END)
        candidates = [r for r in self.recipes if r.get("wishlist")]
        if not candidates:
            self.wishlist_listbox.insert(tk.END, t("home_no_wishlist_recipe"))
            self.wishlist_sample = []
            return
        sample_size = min(10, len(candidates))
        self.wishlist_sample = random.sample(candidates, sample_size)
        for r in self.wishlist_sample:
            cat = translate_category_name(r.get("category", "Autre"))
            self.wishlist_listbox.insert(tk.END, f"[{cat}] {r['name']}")


    def refresh_ingredients(self):
        self.ingredient_names = load_ingredients()

    # ---------- Ajouter une recette ----------
    def open_add_recipe(self):
        win = RecipeFormWindow(self, recipe_index=None)
        self.wait_window(win)
        self._build_home_ui()

    # ---------- Voir toutes les recettes ----------
    def open_all_recipes(self):
        if not self._recipes_available():
            return
        AllRecipesWindow(self)

    # ---------- Voir une recette précise ----------
    def open_one_recipe(self):
        if not self._recipes_available():
            return
        win = OneRecipeWindow(self)
        self.wait_window(win)
        self._refresh_recent_views()

    # ---------- Modifier / Supprimer une recette ----------
    def open_manage_recipes(self, quick_filter=None, initial_search=""):
        if not self._recipes_available():
            return
        win = ManageRecipesWindow(self, quick_filter=quick_filter, initial_search=initial_search)
        self.wait_window(win)
        self._refresh_recent_views()

    # ---------- Gérer les ingrédients ----------
    def open_manage_ingredients(self):
        ManageIngredientsWindow(self)

    # ---------- Corbeille ----------
    def open_trash(self):
        win = TrashWindow(self)
        self.wait_window(win)
        self._refresh_recent_views()

    # ---------- Recherche par ingrédient ----------
    def open_ingredient_search(self):
        IngredientSearchWindow(self)

    # ---------- Comparer deux ou trois recettes ----------
    def open_compare_recipes(self):
        if len(self.recipes) < 2:
            messagebox.showinfo(t("common_info"), t("compare_need_two_recipes"))
            return
        CompareRecipesWindow(self)

    # ---------- Importer une recette depuis un lien ----------
    def open_import_from_url(self):
        ImportFromUrlWindow(self)

    # ---------- Importer une recette depuis une photo ----------
    def open_import_from_photo(self):
        ImportFromPhotoWindow(self)

    # ---------- Importer une recette depuis un QR code mobile ----------
    def open_import_from_qr(self):
        if not QRCODE_READER_AVAILABLE:
            messagebox.showerror(t("common_module_missing"), t("qrimport_reader_missing"))
            return
        paths = filedialog.askopenfilenames(
            title=t("qrimport_choose_title"),
            filetypes=[(t("qrimport_filetypes"), "*.png *.jpg *.jpeg *.bmp *.webp"), ("Tous les fichiers", "*.*")]
        )
        if not paths:
            return
        try:
            prefill = import_recipe_prefill_from_qr_images(paths)
        except QrImportIncompleteError as e:
            messagebox.showwarning(
                t("qrimport_title"),
                t("qrimport_incomplete", received=e.received, total=e.total)
            )
            return
        except QrImportMixedBatchesError:
            messagebox.showwarning(t("qrimport_title"), t("qrimport_mixed_batches"))
            return
        except QrImportChecksumError:
            messagebox.showerror(t("common_error"), t("qrimport_checksum_error"))
            return
        except Exception as e:
            messagebox.showerror(t("common_error"), t("qrimport_decode_error", error=e))
            return
        if not prefill:
            messagebox.showwarning(t("qrimport_title"), t("qrimport_no_code"))
            return
        self.show_toast(t("qrimport_success_prefill"))
        RecipeFormWindow(self, recipe_index=None, prefill=prefill)

    # ---------- Importer / Exporter les données ----------
    def open_import_export(self):
        ImportExportWindow(self)

    # ---------- Que puis-je cuisiner ? ----------
    def open_what_can_i_cook(self):
        if not self._recipes_available():
            return
        WhatCanICookWindow(self)

    # ---------- Mon garde-manger ----------
    def open_pantry(self):
        win = PantryWindow(self)
        self.wait_window(win)
        self._build_home_ui()

    def open_unit_converter(self):
        UnitConverterWindow(self)

    def open_weekly_plan_history(self):
        WeeklyPlanHistoryWindow(self)

    # ---------- Planning de la semaine ----------
    def open_weekly_plan(self):
        if not self._recipes_available():
            return
        win = WeeklyPlanWindow(self)
        self.wait_window(win)
        self._refresh_today_meals()

    # ---------- Mes menus ----------
    def open_menus(self):
        if not self._recipes_available():
            return
        MenuManagerWindow(self)

    # ---------- Statistiques ----------
    def open_statistics(self):
        if not self._recipes_available():
            return
        StatisticsWindow(self)

    # ---------- Exporter le livre de recettes ----------
    def open_cookbook_export(self):
        if not self._recipes_available():
            return
        CookbookExportWindow(self)


class UnknownIngredientsDialog(tk.Toplevel):
    """Résout en une fois les ingrédients inconnus avant l'enregistrement."""

    def __init__(self, parent, unknown_names, existing_names):
        super().__init__(parent)
        self.result = None
        self.title(t("unknowningredients_title"))
        fit_window_to_workarea(
            self,
            gs(820),
            min(gs(760), get_usable_screen_height(self)),
            margin=24,
        )
        safe_minsize(self, gs(650), gs(420))
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        ttk.Label(self, text=t("unknowningredients_heading"), style="Title.TLabel").pack(
            anchor="w", padx=18, pady=(16, 4)
        )
        ttk.Label(
            self, text=t("unknowningredients_intro"), wraplength=760,
            justify="left", foreground=COLOR_TEXT_MUTED
        ).pack(fill="x", padx=18, pady=(0, 12))
        ttk.Label(
            self, text=t("common_filter_hint"),
            foreground=COLOR_TEXT_MUTED,
        ).pack(anchor="w", padx=18, pady=(0, 8))

        outer = ttk.Frame(self)
        outer.pack(fill="both", expand=True, padx=18)
        canvas = tk.Canvas(outer, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        content = ttk.Frame(canvas)
        window_id = canvas.create_window((0, 0), window=content, anchor="nw")
        content.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window_id, width=e.width))
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.rows = []
        seen = set()
        for raw_name in unknown_names:
            key = ingredient_sort_key(raw_name)
            if key in seen:
                continue
            seen.add(key)
            ranked = rank_close_ingredients(raw_name, existing_names)
            ordered = [name for _score, name in ranked]
            top_score = ranked[0][0] if ranked else 0
            box = ttk.LabelFrame(content, text=f"  {raw_name}  ", padding=10)
            box.pack(fill="x", pady=5)
            action = tk.StringVar(value="replace" if top_score >= 0.75 else "create")
            ttk.Radiobutton(
                box, text=t("unknowningredients_create", name=raw_name),
                variable=action, value="create"
            ).pack(anchor="w")
            replace_line = ttk.Frame(box)
            replace_line.pack(fill="x", pady=(5, 0))
            ttk.Radiobutton(
                replace_line, text=t("unknowningredients_replace"),
                variable=action, value="replace"
            ).pack(side="left")
            display_to_canonical = {}
            for canonical in existing_names:
                display_to_canonical.setdefault(translate_ingredient_name(canonical), canonical)
            display_values = filter_sorted_ingredient_values(display_to_canonical.keys())
            # Même champ à suggestions que le choix d'ingrédient du formulaire
            # de recette : la liste apparaît et se filtre pendant la frappe.
            choice = ttk.Entry(replace_line, width=38)
            choice.full_values = display_values
            choice._suggestion_popup = None
            choice._suggestion_listbox = None
            choice._skip_focus_popup = False
            closest = translate_ingredient_name(ordered[0]) if ordered else ""
            if closest:
                choice.insert(0, closest)
            choice.pack(side="left", padx=(8, 0), fill="x", expand=True)
            choice.bind(
                "<KeyRelease>",
                lambda event, entry=choice, selected_action=action:
                    self._on_replacement_keyrelease(event, entry, selected_action),
            )
            choice.bind(
                "<FocusIn>",
                lambda event, entry=choice, selected_action=action:
                    self._on_replacement_focus_in(event, entry, selected_action),
            )
            choice.bind(
                "<FocusOut>",
                lambda event, entry=choice: self._on_replacement_focus_out(event, entry),
            )
            self.rows.append((raw_name, action, choice, display_to_canonical))

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=18, pady=16)
        ttk.Button(buttons, text=t("common_cancel"), command=self._cancel).pack(side="right")
        ttk.Button(
            buttons, text=t("unknowningredients_continue"), style="Primary.TButton",
            command=self._accept
        ).pack(side="right", padx=(0, 8))

    def _hide_replacement_suggestions(self, entry):
        popup = getattr(entry, "_suggestion_popup", None)
        if popup is not None:
            try:
                popup.destroy()
            except tk.TclError:
                pass
            entry._suggestion_popup = None
            entry._suggestion_listbox = None

    def _show_replacement_suggestions(self, entry, filtered, action):
        self._hide_replacement_suggestions(entry)
        if not filtered:
            return
        popup = tk.Toplevel(entry)
        popup.wm_overrideredirect(True)
        try:
            popup.wm_attributes("-topmost", True)
        except tk.TclError:
            pass
        width = max(entry.winfo_width(), gs(180))
        listbox = tk.Listbox(
            popup,
            height=min(6, len(filtered)),
            exportselection=False,
            font=("Segoe UI", sf(9)),
        )
        listbox.pack(fill="both", expand=True)
        for value in filtered:
            listbox.insert(tk.END, value)
        finalize_suggestion_popup(popup, entry, listbox, width)

        def choose(_event=None):
            selection = listbox.curselection()
            if selection:
                entry.delete(0, tk.END)
                entry.insert(0, listbox.get(selection[0]))
                action.set("replace")
            self._hide_replacement_suggestions(entry)
            entry._skip_focus_popup = True
            entry.focus_set()
            entry.icursor(tk.END)

        listbox.bind("<ButtonRelease-1>", choose)
        listbox.bind("<Return>", choose)
        entry._suggestion_popup = popup
        entry._suggestion_listbox = listbox

    def _on_replacement_keyrelease(self, event, entry, action):
        if event.keysym == "Down":
            listbox = getattr(entry, "_suggestion_listbox", None)
            if listbox is not None:
                listbox.focus_set()
                listbox.selection_set(0)
            return
        if event.keysym == "Escape":
            self._hide_replacement_suggestions(entry)
            return
        if event.keysym in (
            "Return", "Tab", "Shift_L", "Shift_R", "Control_L", "Control_R",
            "Caps_Lock", "Alt_L", "Alt_R", "Left", "Right", "Up",
        ):
            return
        action.set("replace")
        filtered = filter_sorted_ingredient_values(entry.full_values, entry.get())
        if filtered:
            self._show_replacement_suggestions(entry, filtered, action)
        else:
            self._hide_replacement_suggestions(entry)

    def _on_replacement_focus_in(self, _event, entry, action):
        if getattr(entry, "_skip_focus_popup", False):
            entry._skip_focus_popup = False
            return
        # La proposition présélectionnée est remplacée dès la première lettre,
        # sans que l'utilisateur ait à l'effacer manuellement.
        entry.after_idle(lambda: entry.select_range(0, tk.END))
        filtered = filter_sorted_ingredient_values(entry.full_values, entry.get())
        if filtered:
            self._show_replacement_suggestions(entry, filtered, action)

    def _on_replacement_focus_out(self, _event, entry):
        def hide_if_focus_left_suggestions():
            try:
                focused = self.focus_get()
                if focused in (entry, getattr(entry, "_suggestion_listbox", None)):
                    return
            except tk.TclError:
                pass
            self._hide_replacement_suggestions(entry)

        entry.after(200, hide_if_focus_left_suggestions)

    def _accept(self):
        result = {}
        for raw_name, action, choice, display_to_canonical in self.rows:
            if action.get() == "replace":
                selected = display_to_canonical.get(choice.get())
                if not selected:
                    selected = resolve_ingredient_input(
                        choice.get(), list(display_to_canonical.values())
                    )
                if not selected:
                    messagebox.showerror(
                        t("common_error"),
                        t("unknowningredients_replacement_required", name=raw_name),
                        parent=self,
                    )
                    return
                result[ingredient_sort_key(raw_name)] = ("replace", selected)
            else:
                result[ingredient_sort_key(raw_name)] = ("create", normalize_oe(raw_name.strip()))
        self.result = result
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


class RecipeFormWindow(tk.Toplevel):
    """Fenêtre d'ajout OU de modification d'une recette (nom, catégorie, photo,
    description, ingrédients pour 1 personne). Si recipe_index est fourni, la
    fenêtre s'ouvre en mode modification, pré-remplie avec la recette
    existante."""

    CATEGORY_OPTIONS = ["Petit-déjeuner", "Entrée", "Plat", "Dessert", "Apéro", "Boisson", "Sauce", "Autre"]
    DIFFICULTY_OPTIONS = ["Très facile", "Facile", "Moyen", "Difficile"]
    MAX_DESC_LEN = 12000
    MAX_NOTES_LEN = 500

    def __init__(self, app, recipe_index=None, prefill=None):
        super().__init__(app)
        self.app = app
        self.recipe_index = recipe_index
        self.editing = recipe_index is not None
        self.existing_recipe = app.recipes[recipe_index] if self.editing else None
        self.prefill = prefill if not self.editing else None
        self.ingredient_names = load_ingredients()

        # Galerie de photos : chaque élément est ("existing", nom_de_fichier)
        # pour une photo déjà enregistrée, ou ("new", chemin_source) pour une
        # photo qui vient d'être choisie et sera copiée lors de l'enregistrement.
        self.gallery_items = []
        if self.editing:
            self.gallery_items = [("existing", fname) for fname in get_recipe_images(self.existing_recipe)]
        elif self.prefill:
            self.gallery_items = [("existing", fname) for fname in self.prefill.get("images", [])]
            self.gallery_items += [("new", path) for path in self.prefill.get("image_sources", []) if os.path.isfile(path)]
        self._temporary_import_sources = set(self.prefill.get("temporary_image_sources", []) if self.prefill else [])
        self._gallery_thumb_refs = []  # garder une référence pour éviter le garbage collector

        self.title(t("recipeform_title_edit") if self.editing else t("recipeform_title_add"))
        # Le bas de la fenêtre reste toujours au-dessus de la barre des tâches.
        fit_window_to_workarea(self, gs(1400), get_usable_screen_height(self), margin=18)
        safe_minsize(self, gs(760), min(gs(520), get_usable_screen_height(self) - 36))
        self.grab_set()

        # ---- Conteneur scrollable pour tout le formulaire ----
        # Tout le contenu (nom, catégorie, photo, description, ingrédients,
        # boutons) est placé dans ce conteneur qui défile d'un bloc : ainsi,
        # les boutons "+ Ajouter un ingrédient" / "Enregistrer" restent
        # toujours juste après le dernier ingrédient, où qu'il soit.
        outer = ttk.Frame(self)
        outer.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(outer, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=self.canvas.yview)
        self.content_frame = ttk.Frame(self.canvas)
        self.content_frame.bind(
            "<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas_window = self.canvas.create_window((0, 0), window=self.content_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.canvas_window, width=e.width))
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        ttk.Label(self.content_frame, text=t("recipeform_title_edit") if self.editing else t("recipeform_title_add"),
                  style="Title.TLabel").pack(anchor="w", padx=20, pady=(16, 2))
        self.draft_status_label = ttk.Label(self.content_frame, text=t("recipeform_draft_hint"), style="Muted.TLabel")
        self.draft_status_label.pack(anchor="w", padx=20, pady=(0, 10))
        self.form_notebook = ttk.Notebook(self.content_frame)
        self.form_notebook.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        self.tab_info = ttk.Frame(self.form_notebook, padding=16)
        self.tab_ingredients = ttk.Frame(self.form_notebook, padding=16)
        self.tab_preparation = ttk.Frame(self.form_notebook, padding=16)
        self.tab_photos = ttk.Frame(self.form_notebook, padding=16)
        self.form_notebook.add(self.tab_info, text=t("recipeform_tab_info"))
        self.form_notebook.add(self.tab_ingredients, text=t("recipeform_tab_ingredients"))
        self.form_notebook.add(self.tab_preparation, text=t("recipeform_tab_preparation"))
        self.form_notebook.add(self.tab_photos, text=t("recipeform_tab_photos"))
        if self.editing:
            self.tab_cook_log = ttk.Frame(self.form_notebook, padding=16)
            self.form_notebook.add(self.tab_cook_log, text=t("recipeform_tab_cook_log"))
            self._build_cook_log_tab()

        # Les allergènes sont importants et doivent être visibles dès l'onglet
        # Informations, au même endroit que les caractéristiques principales.
        row1_left = self.tab_info
        row1_right = self.tab_info

        ttk.Label(row1_left, text=t("recipeform_name_label"),
                  font=("Segoe UI", sf(11), "bold")).pack(pady=(15, 5))
        self.name_entry = ttk.Entry(row1_left, width=42)
        self.name_entry.pack()
        if self.editing:
            self.name_entry.insert(0, self.existing_recipe["name"])
        elif self.prefill:
            self.name_entry.insert(0, self.prefill.get("name", ""))

        self.favorite_var = tk.BooleanVar(
            value=self.existing_recipe.get("favorite", False) if self.editing else False
        )
        ttk.Checkbutton(row1_left, text=t("recipeform_favorite_checkbox"),
                         variable=self.favorite_var).pack(pady=(8, 0))

        self.wishlist_var = tk.BooleanVar(
            value=self.existing_recipe.get("wishlist", False) if self.editing else False
        )
        ttk.Checkbutton(row1_left, text=t("recipeform_wishlist_checkbox"),
                         variable=self.wishlist_var).pack(pady=(4, 0))

        # ---- Note personnelle (1 à 5 étoiles, cliquables) ----
        self.rating_value = self.existing_recipe.get("rating", 0) if self.editing else 0
        rating_frame = ttk.Frame(row1_left)
        rating_frame.pack(pady=(8, 0))
        ttk.Label(rating_frame, text=t("recipeform_rating_label")).pack(side="left", padx=(0, 5))
        self.rating_star_labels = []
        for i in range(1, 6):
            lbl = ttk.Label(rating_frame, text="☆", font=("Segoe UI", sf(14)), cursor="hand2", takefocus=1)
            lbl.pack(side="left")
            lbl.bind("<Button-1>", lambda e, i=i: self._set_rating(i))
            # Les étoiles n'avaient aucun équivalent clavier : impossible de
            # noter une recette sans souris. Atteignables au Tab désormais,
            # Entrée/Espace valident comme un clic, et le style change au
            # focus pour rester visible (pas de highlightthickness sur les
            # widgets ttk).
            lbl.bind("<Return>", lambda e, i=i: self._set_rating(i))
            lbl.bind("<space>", lambda e, i=i: self._set_rating(i))
            lbl.bind("<FocusIn>", lambda e, w=lbl: w.configure(style="RatingStarFocus.TLabel"))
            lbl.bind("<FocusOut>", lambda e, w=lbl: w.configure(style="TLabel"))
            self.rating_star_labels.append(lbl)
        self._refresh_rating_stars()

        ttk.Label(row1_left, text=t("recipeform_category_label"),
                  font=("Segoe UI", sf(11), "bold")).pack(pady=(15, 5))
        self.category_combo = ttk.Combobox(row1_left, values=[translate_category_name(c) for c in self.CATEGORY_OPTIONS],
                                            state="readonly", width=20)
        self.category_combo.set(
            translate_category_name(self.existing_recipe.get("category", "Plat") if self.editing else (self.prefill or {}).get("category", "Plat"))
        )
        self.category_combo.pack()

        # ---- Temps de préparation / cuisson / difficulté ----
        times_frame = ttk.Frame(row1_left)
        times_frame.pack(pady=(15, 5))
        ttk.Label(times_frame, text=t("recipeform_prep_time_label")).grid(row=0, column=0, padx=3, sticky="e")
        self.prep_time_entry = ttk.Entry(times_frame, width=6)
        self.prep_time_entry.grid(row=0, column=1, padx=3)
        ttk.Label(times_frame, text=t("recipeform_cook_time_label")).grid(row=0, column=2, padx=3, sticky="e")
        self.cook_time_entry = ttk.Entry(times_frame, width=6)
        self.cook_time_entry.grid(row=0, column=3, padx=3)
        if self.editing:
            self.prep_time_entry.insert(0, str(self.existing_recipe.get("prep_time", "") or ""))
            self.cook_time_entry.insert(0, str(self.existing_recipe.get("cook_time", "") or ""))
        elif self.prefill:
            self.prep_time_entry.insert(0, str(self.prefill.get("prep_time", "") or ""))
            self.cook_time_entry.insert(0, str(self.prefill.get("cook_time", "") or ""))

        difficulty_frame = ttk.Frame(row1_left)
        difficulty_frame.pack(pady=(5, 5))
        ttk.Label(difficulty_frame, text=t("recipeform_difficulty_label")).pack(side="left", padx=3)
        self.difficulty_combo = ttk.Combobox(difficulty_frame, values=[translate_difficulty_name(d) for d in self.DIFFICULTY_OPTIONS],
                                              state="readonly", width=15)
        if self.editing:
            difficulty_value = self.existing_recipe.get("difficulty", "Facile")
        elif self.prefill:
            difficulty_value = self.prefill.get("difficulty", "")
        else:
            difficulty_value = "Facile"
        self.difficulty_combo.set(translate_difficulty_name(difficulty_value))
        self.difficulty_combo.pack(side="left", padx=3)
        ttk.Label(difficulty_frame, text=t("recipeform_default_persons_label")).pack(side="left", padx=(10, 3))
        self.default_persons_entry = ttk.Entry(difficulty_frame, width=5)
        if self.editing:
            default_persons_value = str(self.existing_recipe.get("default_persons", 4))
        elif self.prefill:
            default_persons_value = str(self.prefill.get("default_persons", 4))
        else:
            default_persons_value = "4"
        self.default_persons_entry.insert(0, default_persons_value)
        self.default_persons_entry.pack(side="left")

        # ---- Étiquettes libres ----
        ttk.Label(row1_left, text=t("recipeform_tags_label"),
                  font=("Segoe UI", sf(11), "bold")).pack(pady=(15, 5))
        self.tags_entry = ttk.Entry(row1_left, width=42)
        self.tags_entry.pack()
        if self.editing and self.existing_recipe.get("tags"):
            self.tags_entry.insert(0, ", ".join(self.existing_recipe["tags"]))
        ttk.Label(row1_left, text=t("recipeform_tags_example"),
                  font=("Segoe UI", sf(8)), foreground=COLOR_TEXT_MUTED).pack()

        # ---- Allergènes ----
        allergens_header = ttk.Frame(row1_right)
        allergens_header.pack(fill="x", padx=10, pady=(15, 5))
        ttk.Label(allergens_header, text=t("recipeform_allergens_label"),
                  font=("Segoe UI", sf(11), "bold")).pack(side="left")
        ttk.Button(allergens_header, text=t("recipeform_detect_allergens_button"),
                   command=self.detect_allergens_from_ingredients).pack(side="right")
        ttk.Label(
            row1_right,
            text=t("recipeform_allergens_disclaimer"),
            font=("Segoe UI", sf(8), "bold"), foreground="#FF0000", justify="center"
        ).pack(pady=(0, 8))
        allergens_frame = ttk.Frame(row1_right)
        allergens_frame.pack()
        if self.editing:
            existing_allergens = set(self.existing_recipe.get("allergens", []))
        elif self.prefill:
            # Import URL ou QR : conserve les allergènes explicitement transmis
            # et complète avec la détection locale à partir des ingrédients.
            existing_allergens = set(self.prefill.get("allergens", []))
            if self.prefill.get("ingredients"):
                existing_allergens.update(compute_recipe_allergens(self.prefill["ingredients"]))
        else:
            existing_allergens = set()
        self.allergen_vars = {}
        for i, allergen in enumerate(ALLERGENS):
            var = tk.BooleanVar(value=allergen in existing_allergens)
            self.allergen_vars[allergen] = var
            ttk.Checkbutton(allergens_frame, text=translate_allergen_name(allergen), variable=var).grid(
                row=i // 2, column=i % 2, sticky="w", padx=8, pady=2
            )
        # Sert à ne jamais décocher un allergène que l'utilisateur aurait
        # coché lui-même sans lien avec un ingrédient détecté : on ne
        # décoche automatiquement que ce que la détection a elle-même coché.
        if self.editing:
            self._auto_detected_allergens = set(
                compute_recipe_allergens(self.existing_recipe.get("ingredients", []))
            )
        elif self.prefill and self.prefill.get("ingredients"):
            self._auto_detected_allergens = set(compute_recipe_allergens(self.prefill["ingredients"]))
        else:
            self._auto_detected_allergens = set()
        ttk.Label(
            row1_right,
            text=t("recipeform_allergens_auto_note"),
            font=("Segoe UI", sf(8)), foreground=COLOR_TEXT_MUTED, justify="center"
        ).pack(pady=(0, 5))

        # ---- Photos (galerie) ----
        # Le bouton et les astuces sont placés avant la galerie (et non
        # expand=True) afin de rester visibles sans défiler, même quand la
        # galerie est vide et que l'onglet dispose de beaucoup de hauteur.
        ttk.Label(self.tab_photos, text=t("recipeform_photos_label"),
                  font=("Segoe UI", sf(11), "bold")).pack(pady=(15, 5))
        ttk.Button(self.tab_photos, text=t("recipeform_add_photo_button"),
                   command=self.choose_images).pack(pady=5)
        self.drop_status_label = ttk.Label(
            self.tab_photos,
            text=t("recipeform_drop_photos_hint"),
            style="Muted.TLabel"
        )
        self.drop_status_label.pack(pady=(2, 1))
        ttk.Label(
            self.tab_photos,
            text=t("recipeform_paste_photo_hint"),
            style="Muted.TLabel"
        ).pack(pady=(0, 8))

        gallery_outer = ttk.Frame(self.tab_photos)
        gallery_outer.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        # Grande galerie : la hauteur est ajustée en fonction de la taille des
        # aperçus et la largeur disponible est exploitée au maximum.
        self.gallery_canvas = tk.Canvas(gallery_outer, height=380, highlightthickness=0)
        gallery_scrollbar = ttk.Scrollbar(gallery_outer, orient="horizontal",
                                           command=self.gallery_canvas.xview)
        self.gallery_frame = ttk.Frame(self.gallery_canvas)
        self.gallery_frame.bind(
            "<Configure>", lambda e: self.gallery_canvas.configure(scrollregion=self.gallery_canvas.bbox("all"))
        )
        self.gallery_canvas.create_window((0, 0), window=self.gallery_frame, anchor="nw")
        self.gallery_canvas.configure(xscrollcommand=gallery_scrollbar.set)
        self.gallery_canvas.pack(fill="both", expand=True)
        gallery_scrollbar.pack(fill="x")
        self._refresh_gallery()
        self._enable_photo_drop()
        self.bind("<Control-v>", self._paste_photo_from_clipboard, add="+")

        # Sections séparées pour alléger le formulaire : ingrédients et préparation
        # ne se concurrencent plus visuellement sur la même page.
        row2_left = self.tab_ingredients
        row2_right = self.tab_preparation

        # ---- Description ----
        # La zone de préparation occupe désormais réellement la largeur de
        # l'application et offre beaucoup plus de hauteur pour les recettes
        # détaillées.
        ttk.Label(row2_right, text=t("recipeform_description_label"),
                  font=("Segoe UI", sf(11), "bold")).pack(anchor="w", padx=10, pady=(15, 5))
        desc_frame = ttk.Frame(row2_right)
        desc_frame.pack(fill="both", expand=True, padx=10)
        desc_scroll = ttk.Scrollbar(desc_frame, orient="vertical")
        self.description_text = tk.Text(
            desc_frame, height=18, wrap="word", font=("Segoe UI", sf(10)),
            yscrollcommand=desc_scroll.set
        )
        desc_scroll.config(command=self.description_text.yview)
        self.description_text.pack(side="left", fill="both", expand=True)
        desc_scroll.pack(side="right", fill="y")
        if self.editing and self.existing_recipe.get("description"):
            self.description_text.insert("1.0", self.existing_recipe["description"])
        elif self.prefill and self.prefill.get("description"):
            self.description_text.insert("1.0", self.prefill["description"])
        self.desc_counter_label = ttk.Label(row2_right, text="", font=("Segoe UI", sf(8)),
                                             foreground=COLOR_TEXT_MUTED)
        self.desc_counter_label.pack(anchor="e", padx=10, pady=(2, 8))
        self.description_text.bind("<<Modified>>", self._on_description_modified)
        self._on_description_modified()

        # ---- Notes personnelles ----
        # Les notes concernent directement la préparation et sont donc placées
        # juste sous la description au lieu d'être isolées dans Compléments.
        ttk.Label(row2_right, text=t("recipeform_notes_label"),
                  font=("Segoe UI", sf(11), "bold")).pack(anchor="w", padx=10, pady=(8, 5))
        notes_frame = ttk.Frame(row2_right)
        notes_frame.pack(fill="x", padx=10)
        notes_scroll = ttk.Scrollbar(notes_frame, orient="vertical")
        self.notes_text = tk.Text(
            notes_frame, height=7, wrap="word", font=("Segoe UI", sf(10)),
            yscrollcommand=notes_scroll.set
        )
        notes_scroll.config(command=self.notes_text.yview)
        self.notes_text.pack(side="left", fill="x", expand=True)
        notes_scroll.pack(side="right", fill="y")
        if self.editing and self.existing_recipe.get("personal_notes"):
            self.notes_text.insert("1.0", self.existing_recipe["personal_notes"])
        elif self.prefill and self.prefill.get("personal_notes"):
            self.notes_text.insert("1.0", self.prefill["personal_notes"])
        self.notes_counter_label = ttk.Label(row2_right, text="", font=("Segoe UI", sf(8)),
                                              foreground=COLOR_TEXT_MUTED)
        self.notes_counter_label.pack(anchor="e", padx=10, pady=(2, 10))
        self.notes_text.bind("<<Modified>>", self._on_notes_modified)
        self._on_notes_modified()

        # ---- Retour après cuisson (aligné sur l'application mobile) ----
        ttk.Label(row2_right, text=t("recipeform_family_opinion_label"),
                  font=("Segoe UI", sf(11), "bold")).pack(anchor="w", padx=10, pady=(8, 5))
        self.family_opinion_text = tk.Text(row2_right, height=4, wrap="word", font=("Segoe UI", sf(10)))
        self.family_opinion_text.pack(fill="x", padx=10)
        if self.editing and self.existing_recipe.get("family_opinion"):
            self.family_opinion_text.insert("1.0", self.existing_recipe.get("family_opinion", ""))
        elif self.prefill and self.prefill.get("family_opinion"):
            self.family_opinion_text.insert("1.0", self.prefill.get("family_opinion", ""))

        ttk.Label(row2_right, text=t("recipeform_improvement_notes_label"),
                  font=("Segoe UI", sf(11), "bold")).pack(anchor="w", padx=10, pady=(8, 5))
        self.improvement_notes_text = tk.Text(row2_right, height=4, wrap="word", font=("Segoe UI", sf(10)))
        self.improvement_notes_text.pack(fill="x", padx=10)
        if self.editing and self.existing_recipe.get("improvement_notes"):
            self.improvement_notes_text.insert("1.0", self.existing_recipe.get("improvement_notes", ""))
        elif self.prefill and self.prefill.get("improvement_notes"):
            self.improvement_notes_text.insert("1.0", self.prefill.get("improvement_notes", ""))

        actual_diff_frame = ttk.Frame(row2_right)
        actual_diff_frame.pack(fill="x", padx=10, pady=(8, 12))
        ttk.Label(actual_diff_frame, text=t("recipeform_actual_difficulty_label"),
                  font=("Segoe UI", sf(10), "bold")).pack(side="left")
        self.actual_difficulty_combo = ttk.Combobox(
            actual_diff_frame, values=[""] + [translate_difficulty_name(d) for d in self.DIFFICULTY_OPTIONS],
            state="readonly", width=18
        )
        actual_value = ""
        if self.editing:
            actual_value = self.existing_recipe.get("actual_difficulty", "") or ""
        elif self.prefill:
            actual_value = self.prefill.get("actual_difficulty", "") or ""
        self.actual_difficulty_combo.set(translate_difficulty_name(actual_value) if actual_value else "")
        self.actual_difficulty_combo.pack(side="left", padx=(10, 0))

        # ---- Ingrédients ----
        ing_header_frame = ttk.Frame(row2_left)
        ing_header_frame.pack(fill="x", padx=10, pady=(15, 5))
        ttk.Label(ing_header_frame, text=t("recipeform_ingredients_label"),
                  font=("Segoe UI", sf(11), "bold"), wraplength=900,
                  justify="left").pack(side="left")
        ttk.Button(ing_header_frame, text=t("recipeform_new_ingredient_button"),
                   command=self.add_new_ingredient_global).pack(side="right")

        if not self.ingredient_names:
            ttk.Label(row2_left,
                      text=t("recipeform_no_ingredients_registered"),
                      font=("Segoe UI", sf(8)), foreground=COLOR_ERROR, justify="center").pack()

        if self.prefill and self.prefill.get("ocr_warnings"):
            ttk.Label(row2_left, text=t("importphoto_uncertain_quantities",
                      names=", ".join(self.prefill["ocr_warnings"])),
                      wraplength=850, justify="left", foreground=COLOR_ERROR).pack(
                          fill="x", padx=10, pady=6)
        self.rows_frame = ttk.Frame(row2_left)
        self.rows_frame.pack(fill="x", padx=10)

        header = ttk.Frame(self.rows_frame)
        header.pack(fill="x", pady=2)
        ttk.Label(header, text=t("recipeform_header_ingredient"), width=17,
                  font=("Segoe UI", sf(9), "bold")).grid(row=0, column=0)
        ttk.Label(header, text=t("recipeform_header_quantity"), width=9,
                  font=("Segoe UI", sf(9), "bold")).grid(row=0, column=1)
        ttk.Label(header, text=t("recipeform_header_unit"), width=15,
                  font=("Segoe UI", sf(9), "bold")).grid(row=0, column=2)
        ttk.Label(header, text=t("recipeform_header_other"), width=10,
                  font=("Segoe UI", sf(9), "bold")).grid(row=0, column=3)

        self.ingredient_rows = []
        if self.editing and self.existing_recipe["ingredients"]:
            for ing in self.existing_recipe["ingredients"]:
                self.add_ingredient_row(ing["name"], ing["quantity"], ing["unit"])
        elif self.prefill and self.prefill.get("ingredients"):
            for ing in self.prefill["ingredients"]:
                self.add_ingredient_row(ing["name"], ing["quantity"], ing["unit"])
        else:
            self.add_ingredient_row()

        # Ces deux éléments sont recréés/déplacés à chaque ajout de ligne afin
        # de toujours rester juste en dessous du dernier ingrédient.
        self.add_ingredient_button = ttk.Button(
            self.rows_frame, text=t("recipeform_add_ingredient_button"), command=lambda: self.add_ingredient_row()
        )
        self.add_ingredient_button.pack(pady=10)

        self.bottom_actions_frame = ttk.Frame(self, padding=(16, 10))
        self.bottom_actions_frame.pack(fill="x", side="bottom")
        if self.editing:
            ttk.Button(self.bottom_actions_frame, text=t("recipeform_delete_button"), style="Danger.TButton",
                       command=self.delete_recipe).pack(side="left")
        ttk.Button(self.bottom_actions_frame, text=t("recipeform_save_button"), style="Hero.TButton",
                   command=self.save_recipe).pack(side="right")
        ttk.Button(self.bottom_actions_frame, text=t("recipeform_cancel_button"), style="Secondary.TButton",
                   command=self._close_without_draft).pack(side="right", padx=(0, 8))

        self.bind("<Control-s>", lambda e: (self.save_recipe(), "break"))
        self.protocol("WM_DELETE_WINDOW", self._close_without_draft)
        self._draft_after_id = None
        # Référence de comparaison : un formulaire ouvert puis fermé sans
        # aucune modification ne doit pas devenir un faux brouillon.
        self._draft_baseline_signature = self._draft_signature(
            self._collect_draft_snapshot()
        )
        self._maybe_restore_draft()
        self._schedule_draft_autosave()

    def _draft_file_path(self):
        recipe_id = None
        if self.editing and self.existing_recipe:
            recipe_id = self.existing_recipe.get("id")
        if not recipe_id and self.prefill:
            recipe_id = self.prefill.get("id")
        key = recipe_id or "new_recipe"
        return recipe_draft_path(key)

    @staticmethod
    def _entry_set(widget, value):
        widget.delete(0, tk.END)
        widget.insert(0, "" if value is None else str(value))

    @staticmethod
    def _draft_signature(data):
        """Signature stable des champs éditables, sans l'horodatage."""
        comparable = dict(data)
        comparable.pop("saved_at", None)
        return json.dumps(comparable, ensure_ascii=False, sort_keys=True, default=str)

    def _collect_draft_snapshot(self):
        ingredients = []
        for name_e, qty_e, unit_e, custom_e in self.ingredient_rows:
            ingredients.append({
                "name": name_e.get(), "quantity": qty_e.get(),
                "unit_choice": unit_e.get(), "custom_unit": custom_e.get(),
            })
        return {
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "name": self.name_entry.get(), "favorite": self.favorite_var.get(),
            "wishlist": self.wishlist_var.get(), "rating": self.rating_value,
            "category": self.category_combo.get(), "prep_time": self.prep_time_entry.get(),
            "cook_time": self.cook_time_entry.get(), "difficulty": self.difficulty_combo.get(),
            "default_persons": self.default_persons_entry.get(), "tags": self.tags_entry.get(),
            "allergens": [a for a, var in self.allergen_vars.items() if var.get()],
            "description": self.description_text.get("1.0", "end-1c"),
            "personal_notes": self.notes_text.get("1.0", "end-1c"),
            "family_opinion": self.family_opinion_text.get("1.0", "end-1c"),
            "improvement_notes": self.improvement_notes_text.get("1.0", "end-1c"),
            "actual_difficulty": self.actual_difficulty_combo.get(),
            "ingredients": ingredients, "gallery_items": self.gallery_items,
        }

    def _draft_has_content(self, data):
        # Une recette existante constitue toujours un brouillon récupérable,
        # même si tous ses champs sont encore vides. Cela permet de proposer
        # la récupération à chaque nouvelle ouverture de « Modifier ».
        if self.editing and self.existing_recipe:
            return True
        return bool(
            str(data.get("name", "")).strip() or str(data.get("description", "")).strip()
            or str(data.get("personal_notes", "")).strip()
            or str(data.get("family_opinion", "")).strip()
            or str(data.get("improvement_notes", "")).strip()
            or any(str(i.get("name", "")).strip() for i in data.get("ingredients", []))
            or data.get("gallery_items")
        )

    def _save_draft_snapshot(self):
        try:
            data = self._collect_draft_snapshot()
            path = self._draft_file_path()
            unchanged = (
                self.editing
                and self._draft_signature(data) == getattr(
                    self, "_draft_baseline_signature", None
                )
            )
            if not self._draft_has_content(data) or unchanged:
                if os.path.exists(path):
                    os.remove(path)
                return
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
            if self.winfo_exists():
                self.draft_status_label.config(text=t("recipeform_draft_saved", time=datetime.now().strftime("%H:%M")))
        except Exception as exc:
            log_internal_error("suppressed_exception", exc)

    def _schedule_draft_autosave(self):
        if not self.winfo_exists():
            return
        self._save_draft_snapshot()
        self._draft_after_id = self.after(4000, self._schedule_draft_autosave)

    def _delete_draft(self):
        try:
            path = self._draft_file_path()
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass

    def _maybe_restore_draft(self):
        path = self._draft_file_path()
        if not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            stamp = data.get("saved_at", "?").replace("T", " ")
        except Exception as exc:
            log_internal_error("_maybe_restore_draft", exc)
            return
        # Nettoie aussi les brouillons identiques laissés par les versions
        # précédentes, qui les créaient même après une annulation sans changement.
        if self.editing and self._draft_signature(data) == getattr(
            self, "_draft_baseline_signature", None
        ):
            self._delete_draft()
            return
        if ask_yes_no(
            t("recipeform_draft_restore_title"),
            t("recipeform_draft_restore_message", date=stamp), parent=self
        ):
            self._apply_draft_snapshot(data)
        else:
            self._delete_draft()

    def _apply_draft_snapshot(self, data):
        self._entry_set(self.name_entry, data.get("name", ""))
        self.favorite_var.set(bool(data.get("favorite")))
        self.wishlist_var.set(bool(data.get("wishlist")))
        self.rating_value = int(data.get("rating") or 0)
        self._refresh_rating_stars()
        if data.get("category"): self.category_combo.set(data.get("category"))
        self._entry_set(self.prep_time_entry, data.get("prep_time", ""))
        self._entry_set(self.cook_time_entry, data.get("cook_time", ""))
        if data.get("difficulty"): self.difficulty_combo.set(data.get("difficulty"))
        self._entry_set(self.default_persons_entry, data.get("default_persons", 4))
        self._entry_set(self.tags_entry, data.get("tags", ""))
        selected = set(data.get("allergens", []))
        for allergen, var in self.allergen_vars.items(): var.set(allergen in selected)
        for widget, key in [
            (self.description_text, "description"), (self.notes_text, "personal_notes"),
            (self.family_opinion_text, "family_opinion"), (self.improvement_notes_text, "improvement_notes")
        ]:
            widget.delete("1.0", tk.END); widget.insert("1.0", data.get(key, ""))
        self.actual_difficulty_combo.set(data.get("actual_difficulty", "") or "")
        for name_e, qty_e, unit_e, custom_e in self.ingredient_rows:
            self._entry_set(name_e, ""); self._entry_set(qty_e, "")
            unit_e.set("Gr"); self._entry_set(custom_e, "")
        for idx, ing in enumerate(data.get("ingredients", [])):
            if idx >= len(self.ingredient_rows): self.add_ingredient_row()
            name_e, qty_e, unit_e, custom_e = self.ingredient_rows[idx]
            self._entry_set(name_e, ing.get("name", "")); self._entry_set(qty_e, ing.get("quantity", ""))
            unit_e.set(ing.get("unit_choice", "Gr") or "Gr"); self._entry_set(custom_e, ing.get("custom_unit", ""))
        restored_gallery = []
        for item in data.get("gallery_items", []):
            if not isinstance(item, (list, tuple)) or len(item) != 2: continue
            kind, ref = item
            if kind == "existing" and os.path.isfile(os.path.join(IMAGES_DIR, ref)):
                restored_gallery.append((kind, ref))
            elif kind == "new" and os.path.isfile(ref):
                restored_gallery.append((kind, ref))
        self.gallery_items = restored_gallery
        self._refresh_gallery()

    def _close_without_draft(self):
        """Ferme proprement le formulaire et supprime le brouillon."""
        if self._draft_after_id is not None:
            try:
                self.after_cancel(self._draft_after_id)
            except tk.TclError:
                pass
            self._draft_after_id = None
        self._delete_draft()
        self.destroy()

    def _on_description_modified(self, event=None):
        self.description_text.edit_modified(False)
        content = self.description_text.get("1.0", "end-1c")
        if len(content) > self.MAX_DESC_LEN:
            content = content[: self.MAX_DESC_LEN]
            self.description_text.delete("1.0", "end")
            self.description_text.insert("1.0", content)
            self.description_text.edit_modified(False)
        self.desc_counter_label.config(text=t("recipeform_char_counter", count=len(content), max=self.MAX_DESC_LEN))

    def _on_notes_modified(self, event=None):
        self.notes_text.edit_modified(False)
        content = self.notes_text.get("1.0", "end-1c")
        self.notes_counter_label.config(text=t("recipeform_notes_count", count=len(content)))

    def _set_rating(self, value):
        self.rating_value = 0 if self.rating_value == value else value
        self._refresh_rating_stars()

    def _refresh_rating_stars(self):
        for i, lbl in enumerate(self.rating_star_labels, start=1):
            lbl.config(text="★" if i <= self.rating_value else "☆")

    def detect_allergens_from_ingredients(self):
        current_ingredients = []
        for name_e, qty_e, unit_e, custom_e in self.ingredient_rows:
            ing_name = name_e.get().strip()
            if ing_name:
                current_ingredients.append({"name": ing_name})
        if not current_ingredients:
            messagebox.showinfo(t("common_info"), t("recipeform_add_ingredients_first"))
            return

        before = {a for a, var in self.allergen_vars.items() if var.get()}
        self._sync_allergens_from_ingredients()
        after = {a for a, var in self.allergen_vars.items() if var.get()}

        added = sorted(after - before)
        removed = sorted(before - after)
        if added or removed:
            parts = []
            if added:
                parts.append(t("recipeform_allergens_updated_added", list=", ".join(translate_allergen_name(a) for a in added)))
            if removed:
                parts.append(t("recipeform_allergens_updated_removed", list=", ".join(translate_allergen_name(a) for a in removed)))
            messagebox.showinfo(
                t("recipeform_allergens_updated_title"),
                t("recipeform_allergens_updated_message", parts=" ; ".join(parts))
            )
        else:
            messagebox.showinfo(t("common_info"), t("recipeform_allergens_no_change"))

    def choose_images(self):
        paths = filedialog.askopenfilenames(
            title=t("recipeform_choose_photos_title"),
            filetypes=[("Images", "*.png *.jpg *.jpeg *.gif *.bmp *.webp")]
        )
        for path in paths:
            self.gallery_items.append(("new", path))
        if paths:
            self._refresh_gallery()

    def _paste_photo_from_clipboard(self, event=None):
        if not PIL_AVAILABLE:
            return

        # Ne détourne pas le collage normal dans les champs de saisie.
        try:
            widget = self.focus_get()
            if isinstance(widget, (tk.Entry, ttk.Entry, tk.Text, ttk.Combobox)):
                return
        except Exception as exc:
            log_internal_error("suppressed_exception", exc)

        try:
            grabbed = ImageGrab.grabclipboard()
        except Exception as exc:
            log_internal_error("clipboard_grab", exc)
            grabbed = None

        # Cas 1 : une vraie image est dans le presse-papiers
        # (outil Capture d'écran, certaines applications graphiques, etc.).
        if isinstance(grabbed, Image.Image):
            try:
                tmp_dir = os.path.join(DATA_DIR, "clipboard_temp")
                os.makedirs(tmp_dir, exist_ok=True)
                path = os.path.join(tmp_dir, f"clipboard_{uuid.uuid4().hex}.png")

                image = grabbed
                if image.mode not in ("RGB", "RGBA"):
                    image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
                image.save(path, "PNG")

                self.gallery_items.append(("new", path))
                self._refresh_gallery()
                self.app.show_toast(t("recipeform_paste_photo_success"))
                return "break"
            except Exception as exc:
                log_internal_error("clipboard_image_save", exc)

        # Cas 2 : sous Windows, Ctrl+C sur un fichier image dans l'Explorateur
        # renvoie souvent une LISTE de chemins, pas un objet Image Pillow.
        if isinstance(grabbed, (list, tuple)):
            accepted = self._normalise_dropped_photo_paths(grabbed)
            if accepted:
                existing = {os.path.normcase(os.path.abspath(ref))
                            for kind, ref in self.gallery_items if kind == "new"}
                added = 0
                for path in accepted:
                    key = os.path.normcase(os.path.abspath(path))
                    if key not in existing:
                        self.gallery_items.append(("new", path))
                        existing.add(key)
                        added += 1
                if added:
                    self._refresh_gallery()
                    self.app.show_toast(t("recipeform_paste_files_success", count=added))
                    return "break"

        messagebox.showinfo(
            t("common_info"),
            t("recipeform_paste_photo_failed_detailed"),
            parent=self
        )
        return "break"

    def _normalise_dropped_photo_paths(self, files):
        """Transforme les chemins fournis par TkDnD2/ImageGrab en chemins valides."""
        accepted = []
        allowed = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}

        for raw in files or []:
            path = None
            if isinstance(raw, os.PathLike):
                path = os.fspath(raw)
            elif isinstance(raw, str):
                path = raw
            elif isinstance(raw, (bytes, bytearray)):
                raw_bytes = bytes(raw)

                # Les différentes sources de chemins peuvent fournir des bytes ou du texte ;
                # Python/Windows. On tente d'abord l'encodage du système puis
                # quelques replis sans jamais planter sur un nom accentué.
                encodings = []
                fsenc = sys.getfilesystemencoding()
                if fsenc:
                    encodings.append(fsenc)
                if os.name == "nt":
                    encodings.extend(["mbcs", "utf-8", "cp1252"])
                else:
                    encodings.extend(["utf-8", "cp1252"])

                for enc in encodings:
                    try:
                        path = raw_bytes.decode(enc)
                        if os.path.exists(path.strip().strip('"')):
                            break
                    except (LookupError, UnicodeDecodeError):
                        continue

                if path is None:
                    path = raw_bytes.decode("utf-8", errors="replace")
            else:
                path = str(raw)

            path = str(path or "").strip().strip('"')
            if (path and os.path.isfile(path)
                    and os.path.splitext(path)[1].lower() in allowed):
                accepted.append(os.path.abspath(path))

        # Supprime les doublons tout en gardant l'ordre.
        unique = []
        seen = set()
        for path in accepted:
            key = os.path.normcase(path)
            if key not in seen:
                seen.add(key)
                unique.append(path)
        return unique

    def _enable_photo_drop(self):
        self._photo_drop_enabled = False

        if not TKDND_AVAILABLE:
            try:
                self.drop_status_label.config(
                    text=t("recipeform_drop_unavailable")
                )
            except Exception:
                # Mise à jour purement cosmétique : si le widget a déjà été
                # détruit (fermeture concurrente de la fenêtre), rien à faire.
                pass
            return

        # TkDnD2 : un seul drop-target, uniquement sur l'onglet Photos.
        # Contrairement à windnd, aucun WindowProc n'est remplacé manuellement.
        try:
            self.tab_photos.drop_target_register(DND_FILES)
            self.tab_photos.dnd_bind("<<Drop>>", self._on_photo_drop_event)
            self._photo_drop_enabled = True
        except Exception as exc:
            log_internal_error("tkinterdnd2_hook", exc)
            self._photo_drop_enabled = False

        try:
            self.drop_status_label.config(
                text=t("recipeform_drop_photos_hint")
                if self._photo_drop_enabled
                else t("recipeform_drop_unavailable")
            )
        except Exception:
            # Idem : mise à jour cosmétique, sans conséquence si le widget
            # n'existe déjà plus.
            pass

    def _on_photo_drop_event(self, event):
        """Callback TkDnD2 : event.data est une liste Tcl de chemins.

        tk.splitlist est indispensable pour les noms contenant espaces,
        accents ou accolades.
        """
        try:
            raw_files = list(self.tk.splitlist(event.data))
        except Exception as exc:
            log_internal_error("tkinterdnd2_splitlist", exc)
            raw_files = []

        def apply_files():
            try:
                if not self.winfo_exists():
                    return
            except tk.TclError:
                return

            accepted = self._normalise_dropped_photo_paths(raw_files)
            if not accepted:
                self.app.show_toast(t("recipeform_drop_no_valid_image"))
                return

            existing = {
                os.path.normcase(os.path.abspath(ref))
                for kind, ref in self.gallery_items
                if kind == "new"
            }
            added = 0
            for path in accepted:
                key = os.path.normcase(os.path.abspath(path))
                if key not in existing:
                    self.gallery_items.append(("new", path))
                    existing.add(key)
                    added += 1

            if added:
                self._refresh_gallery()
                self.app.show_toast(
                    t("recipeform_drop_success", count=added)
                )

        try:
            self.after_idle(apply_files)
        except tk.TclError:
            pass

        # TkDnD2 attend qu'un événement Drop retourne une action.
        return COPY

    def _remove_gallery_item(self, index):
        if 0 <= index < len(self.gallery_items):
            self.gallery_items.pop(index)
            self._refresh_gallery()

    def _refresh_gallery(self):
        for child in self.gallery_frame.winfo_children():
            child.destroy()
        self._gallery_thumb_refs = []

        if not self.gallery_items:
            ttk.Label(self.gallery_frame, text=t("recipeform_no_photo")).pack(side="left", padx=20, pady=30)
            self.gallery_canvas.configure(height=300)
            return

        # Taille calculée à partir de la largeur réelle disponible. Une photo
        # seule devient une grande prévisualisation ; avec plusieurs photos,
        # deux grandes vignettes tiennent généralement côte à côte et la
        # galerie reste défilable horizontalement si nécessaire.
        self.update_idletasks()
        available = self.gallery_canvas.winfo_width()
        if available <= 10:
            available = max(gs(760), self.winfo_width() - gs(100))
        count = len(self.gallery_items)
        if count == 1:
            thumb_w = max(gs(420), min(gs(820), available - gs(50)))
        else:
            thumb_w = max(gs(280), min(gs(430), (available - gs(60)) // 2))
        thumb_h = max(gs(210), min(gs(520), int(thumb_w * 0.68)))
        self.gallery_canvas.configure(height=thumb_h + gs(70))

        for idx, (kind, ref) in enumerate(self.gallery_items):
            cell = ttk.Frame(self.gallery_frame)
            cell.pack(side="left", padx=8, pady=8)

            thumb = None
            if PIL_AVAILABLE:
                try:
                    if kind == "existing":
                        thumb = load_thumbnail(ref, size=(thumb_w, thumb_h))
                    else:
                        img = Image.open(ref)
                        img.thumbnail((thumb_w, thumb_h))
                        thumb = ImageTk.PhotoImage(img)
                except Exception as exc:
                    log_internal_error("gallery_thumbnail", exc)
                    thumb = None

            if thumb is not None:
                self._gallery_thumb_refs.append(thumb)
                ttk.Label(cell, image=thumb).pack()
            else:
                ttk.Label(
                    cell, text=t("recipeform_preview_unavailable"), justify="center",
                    width=max(24, thumb_w // 12)
                ).pack(ipady=max(4, thumb_h // 20))

            ttk.Button(
                cell, text=t("recipeform_remove_photo_button"), style="Secondary.TButton",
                command=lambda i=idx: self._remove_gallery_item(i)
            ).pack(fill="x", pady=(6, 0))

    def _build_cook_log_tab(self):
        """Affiche les cuissons enregistrées et leurs photos dans l'édition."""
        ttk.Label(self.tab_cook_log, text=t("recipeform_cook_log_heading"),
                  font=("Segoe UI", sf(12), "bold")).pack(anchor="w", pady=(0, 4))
        entries = [entry for entry in (self.existing_recipe.get("cook_log", []) or [])
                   if isinstance(entry, dict)]
        ttk.Label(self.tab_cook_log, text=t("recipeform_cook_log_count", count=len(entries)),
                  foreground=COLOR_TEXT_MUTED).pack(anchor="w", pady=(0, 10))
        outer = ttk.Frame(self.tab_cook_log)
        outer.pack(fill="both", expand=True)
        canvas = tk.Canvas(outer, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        content = ttk.Frame(canvas)
        content.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        content_window = canvas.create_window((0, 0), window=content, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self._cook_log_thumb_refs = []
        self._cook_log_wrap_labels = []

        def update_wraplength(_event=None):
            # Le cadre intérieur doit toujours prendre toute la largeur du
            # canvas. Sinon Tkinter lui donne seulement la largeur de son
            # enfant le plus large (souvent la photo), ce qui laisse un grand
            # espace vide et force les textes à être inutilement étroits.
            # Selon le moment où Tkinter termine la géométrie, le canvas peut
            # encore annoncer sa largeur demandée (ancienne largeur de la
            # photo). Le cadre intérieur connaît, lui, la largeur réellement
            # attribuée à la zone visible : on privilégie donc sa mesure.
            window_width = max(gs(760), self.winfo_width() - gs(60))
            canvas_width = max(1, canvas.winfo_width(), min(content.winfo_width(), window_width))
            canvas.itemconfigure(content_window, width=canvas_width)
            width = max(gs(320), canvas_width - gs(45))
            for label in self._cook_log_wrap_labels:
                try:
                    label.configure(wraplength=width)
                except tk.TclError:
                    pass

        canvas.bind("<Configure>", update_wraplength)
        content.bind("<Configure>", update_wraplength, add="+")
        entries.sort(key=lambda entry: entry.get("date", ""), reverse=True)
        if not entries:
            ttk.Label(content, text=t("recipeform_cook_log_empty"),
                      foreground=COLOR_TEXT_MUTED).pack(pady=30)
            return
        for entry in entries:
            card = tk.Frame(content, background=COLOR_CARD, highlightbackground=COLOR_BORDER,
                            highlightthickness=1)
            card.pack(fill="x", pady=6, padx=2)
            date_value = entry.get("date", "?")
            try:
                date_value = datetime.fromisoformat(date_value).strftime("%d/%m/%Y à %H:%M")
            except (TypeError, ValueError):
                date_value = str(date_value or "?")
            ttk.Label(card, text=date_value, style="Card.TLabel",
                      font=("Segoe UI", sf(10), "bold"), foreground=COLOR_ACCENT_DARK).pack(
                          anchor="w", padx=10, pady=(8, 2))
            persons = entry.get("persons")
            if persons not in (None, ""):
                ttk.Label(card, text=t("cooklog_entry_persons", persons=persons),
                          style="Card.TLabel", foreground=COLOR_TEXT_MUTED).pack(
                              anchor="w", padx=10, pady=(0, 3))
            rating = int(entry.get("rating", 0) or 0)
            if rating:
                ttk.Label(card, text=t("cooklog_entry_rating", stars="★" * rating + "☆" * (5 - rating)),
                          style="Card.TLabel", foreground=COLOR_ACCENT_DARK).pack(
                              anchor="w", padx=10, pady=(2, 3))
            photo = entry.get("photo")
            if photo:
                available = self.winfo_width()
                if available <= 100:
                    available = gs(900)
                photo_w = max(gs(420), min(gs(820), available - gs(120)))
                thumb = load_thumbnail(photo, size=(photo_w, int(photo_w * 0.68)))
                if thumb is not None:
                    self._cook_log_thumb_refs.append(thumb)
                    ttk.Label(card, image=thumb).pack(anchor="w", padx=10, pady=4)
            note = str(entry.get("note") or "").strip()
            comment = str(entry.get("comment") or "").strip()
            if note:
                note_label = ttk.Label(card, text=t("cooklog_note_heading") + " " + note,
                                       style="Card.TLabel", justify="left")
                note_label.pack(anchor="w", padx=10, pady=(3, 3))
                self._cook_log_wrap_labels.append(note_label)
            if comment:
                comment_label = ttk.Label(card, text=t("cooklog_comment_heading") + " " + comment,
                                          style="Card.TLabel", justify="left")
                comment_label.pack(anchor="w", padx=10, pady=(3, 8))
                self._cook_log_wrap_labels.append(comment_label)
            if not note and not comment:
                ttk.Label(card, text=t("cooklog_no_note"), style="Card.TLabel",
                          foreground=COLOR_TEXT_MUTED).pack(anchor="w", padx=10, pady=(3, 8))
        self.after_idle(update_wraplength)
        self.after(150, update_wraplength)

    UNIT_OPTIONS = ["Gr", "Kilo", "ml", "cl", "Litre", "pièce", "cuillère à soupe", "cuillère à café", "pincée", "pot de yaourt", "sachet", "disque", "tour de moulin", "grosse poignée", "poignée", "filet", "rouleau", "cuillerée", "cup", "oz", "lb", "boîte", "gousse", "autre"]

    @staticmethod
    def _map_unit_for_edit(unit):
        """Convertit une unité stockée (éventuellement héritée d'une ancienne
        version) vers (valeur du menu déroulant, texte personnalisé)."""
        u = (unit or "").strip()
        u_lower = u.lower()
        if u_lower in ("gr", "g", "gramme", "grammes"):
            return "Gr", ""
        if u_lower in ("kilo", "kg", "kilogramme", "kilogrammes"):
            return "Kilo", ""
        if u_lower in ("ml", "millilitre", "millilitres"):
            return "ml", ""
        if u_lower in ("cl", "centilitre", "centilitres"):
            return "cl", ""
        if u_lower in ("litre", "litres", "l"):
            return "Litre", ""
        if u_lower in ("pièce", "piece", "pieces", "pièces"):
            return "pièce", ""
        if u_lower in ("cuillère à soupe", "cuillere a soupe", "c. à soupe", "cas"):
            return "cuillère à soupe", ""
        if u_lower in ("cuillère à café", "cuillere a café", "cuillere a cafe", "c. à café", "cac"):
            return "cuillère à café", ""
        if u == "":
            return "Gr", ""
        if u == "autre":
            return "autre", ""
        return "autre", u

    @staticmethod
    def _filter_ingredients(full_values, typed):
        if not typed:
            return full_values
        typed_key = ingredient_sort_key(typed)
        filtered = [v for v in full_values if ingredient_sort_key(v).startswith(typed_key)]
        if not filtered:
            filtered = [v for v in full_values if typed_key in ingredient_sort_key(v)]
        return filtered

    def _hide_suggestions(self, entry):
        popup = getattr(entry, "_suggestion_popup", None)
        if popup is not None:
            try:
                popup.destroy()
            except tk.TclError:
                pass
            entry._suggestion_popup = None
            entry._suggestion_listbox = None

    def _show_suggestions(self, entry, filtered, value_map=None):
        self._hide_suggestions(entry)
        if not filtered:
            return
        popup = tk.Toplevel(entry)
        popup.wm_overrideredirect(True)
        try:
            popup.wm_attributes("-topmost", True)
        except tk.TclError:
            pass
        width = max(entry.winfo_width(), gs(180))

        listbox = tk.Listbox(popup, height=min(6, len(filtered)), exportselection=False, font=("Segoe UI", sf(9)))
        listbox.pack(fill="both", expand=True)
        for v in filtered:
            listbox.insert(tk.END, v)
        finalize_suggestion_popup(popup, entry, listbox, width)

        def choose(event=None):
            sel = listbox.curselection()
            if sel:
                value = listbox.get(sel[0])
                # value_map sert au repli « Vouliez-vous dire... ? » : la
                # ligne affichée est une phrase complète, pas le nom
                # d'ingrédient à insérer tel quel.
                if value_map:
                    value = value_map.get(value, value)
                entry.delete(0, tk.END)
                entry.insert(0, value)
                self._sync_allergens_from_ingredients()
            self._hide_suggestions(entry)
            entry.focus_set()

        listbox.bind("<ButtonRelease-1>", choose)
        listbox.bind("<Return>", choose)
        entry._suggestion_popup = popup
        entry._suggestion_listbox = listbox

    def _sync_allergens_from_ingredients(self):
        """Recalcule les allergènes détectés à partir de TOUS les ingrédients
        actuellement saisis, et coche/décoche les cases en conséquence. Ne
        décoche jamais une case pour un allergène que l'utilisateur aurait
        cochée lui-même sans qu'un ingrédient détecté ne soit à l'origine
        (seuls les allergènes que la détection a elle-même cochés peuvent
        être décochés automatiquement par la suite)."""
        if not hasattr(self, "allergen_vars"):
            return
        current_ingredients = []
        for name_e, qty_e, unit_e, custom_e in self.ingredient_rows:
            typed_name = name_e.get().strip()
            if typed_name:
                # Le champ peut afficher le nom traduit dans la langue
                # actuellement sélectionnée (ex. « Ground beef » en
                # anglais) : la base d'allergènes est indexée en français,
                # donc on résout d'abord vers le nom canonique avant toute
                # recherche, sans quoi la détection échouerait
                # silencieusement dans une langue autre que le français.
                resolved_name = resolve_ingredient_input(typed_name, self.app.ingredient_names) or typed_name
                current_ingredients.append({"name": resolved_name})
        detected = set(compute_recipe_allergens(current_ingredients))

        for allergen in self._auto_detected_allergens - detected:
            if allergen in self.allergen_vars:
                self.allergen_vars[allergen].set(False)
        for allergen in detected:
            if allergen in self.allergen_vars:
                self.allergen_vars[allergen].set(True)

        self._auto_detected_allergens = detected

    def _on_ingredient_keyrelease(self, event, entry):
        if event.keysym == "Down":
            listbox = getattr(entry, "_suggestion_listbox", None)
            if listbox is not None:
                listbox.focus_set()
                listbox.selection_set(0)
            return
        if event.keysym in ("Escape",):
            self._hide_suggestions(entry)
            return
        if event.keysym in ("Return", "Tab", "Shift_L", "Shift_R", "Control_L", "Control_R",
                              "Caps_Lock", "Alt_L", "Alt_R", "Left", "Right"):
            return
        full_values = getattr(entry, "full_values", [])
        typed = entry.get()
        filtered = self._filter_ingredients(full_values, typed)
        if filtered:
            self._show_suggestions(entry, filtered)
            return
        hint = self._did_you_mean_hint(typed)
        if hint:
            display_hint = translate_ingredient_name(hint)
            label = t("recipeform_did_you_mean", name=display_hint)
            self._show_suggestions(entry, [label], value_map={label: display_hint})
        else:
            self._hide_suggestions(entry)

    def _did_you_mean_hint(self, typed):
        """Repère un ingrédient déjà connu très proche du texte tapé (typo,
        variante singulier/pluriel...) pour proposer de le réutiliser plutôt
        que d'en créer un nouveau par erreur — même seuil de proximité que
        UnknownIngredientsDialog (0.75), mais affiché en temps réel pendant
        la frappe plutôt qu'à l'enregistrement. Ne se déclenche que quand
        aucune suggestion normale (préfixe/sous-chaîne) ne correspond déjà."""
        typed = typed.strip()
        if len(typed) < 3 or resolve_ingredient_input(typed, self.ingredient_names) is not None:
            return None
        ranked = rank_close_ingredients(typed, self.ingredient_names)
        if ranked and ranked[0][0] >= 0.75:
            return ranked[0][1]
        return None

    def _on_ingredient_focus_in(self, event, entry):
        full_values = getattr(entry, "full_values", [])
        typed = entry.get()
        filtered = self._filter_ingredients(full_values, typed)
        if filtered:
            self._show_suggestions(entry, filtered)

    def _on_ingredient_focus_out(self, event, entry):
        # Recalcule les allergènes à partir de l'ensemble des ingrédients
        # actuellement saisis (coche ou décoche selon le résultat).
        self._sync_allergens_from_ingredients()
        # Petit délai pour laisser le temps à un clic dans la liste de
        # suggestions de s'exécuter avant qu'elle ne soit masquée.
        entry.after(200, lambda: self._hide_suggestions(entry))

    def add_ingredient_row(self, name="", qty="", unit=""):
        # On détache temporairement les boutons de fin de liste pour que la
        # nouvelle ligne s'insère bien avant eux, puis on les replace après.
        has_controls = hasattr(self, "add_ingredient_button")
        if has_controls:
            self.add_ingredient_button.pack_forget()

        row = ttk.Frame(self.rows_frame)
        row.pack(fill="x", pady=2)
        values = list(self.ingredient_names)
        if name and name not in values:
            values = sorted(values + [name], key=ingredient_sort_key)
        name_e = ttk.Entry(row, width=17)  # champ libre avec suggestions déroulantes personnalisées
        name_e.full_values = get_display_ingredient_values(values)
        name_e._suggestion_popup = None
        name_e._suggestion_listbox = None
        if name:
            name_e.insert(0, translate_ingredient_name(name))
        name_e.grid(row=0, column=0, padx=2)
        name_e.bind("<KeyRelease>", lambda e, ent=name_e: self._on_ingredient_keyrelease(e, ent))
        name_e.bind("<FocusIn>", lambda e, ent=name_e: self._on_ingredient_focus_in(e, ent))
        name_e.bind("<FocusOut>", lambda e, ent=name_e: self._on_ingredient_focus_out(e, ent))
        qty_e = ttk.Entry(row, width=9)
        qty_e.insert(0, "" if qty in ("", None) else str(qty))
        qty_e.grid(row=0, column=1, padx=2)

        combo_value, custom_text = self._map_unit_for_edit(unit)
        unit_e = ttk.Combobox(row, width=15, state="readonly",
                               values=[translate_unit_name(u) for u in self.UNIT_OPTIONS])
        unit_e.set(translate_unit_name(combo_value))
        unit_e.grid(row=0, column=2, padx=2)

        custom_e = ttk.Entry(row, width=10)
        custom_e.insert(0, custom_text)
        custom_e.grid(row=0, column=3, padx=2)
        if combo_value != "autre":
            custom_e.grid_remove()

        def on_unit_change(event, u=unit_e, c=custom_e):
            if resolve_unit_input(u.get(), self.UNIT_OPTIONS) == "autre":
                c.grid()
            else:
                c.delete(0, tk.END)
                c.grid_remove()

        unit_e.bind("<<ComboboxSelected>>", on_unit_change)
        self.ingredient_rows.append((name_e, qty_e, unit_e, custom_e))

        if has_controls:
            self.add_ingredient_button.pack(pady=10)
            # Fait défiler la fenêtre pour amener la nouvelle ligne en vue.
            # yview_moveto(1.0) irait tout en bas de la zone de défilement
            # PARTAGÉE par tous les onglets du formulaire (celle-ci reste
            # haute même sur l'onglet Ingrédients, car self.canvas couvre
            # tout le notebook) : cela amenait un grand vide sous le bouton
            # au lieu de la ligne ajoutée. On calcule donc précisément la
            # position du bouton (juste après la nouvelle ligne) et on ne
            # défile que jusqu'à la faire apparaître en bas de la vue.
            self.update_idletasks()
            try:
                bbox = self.canvas.bbox("all")
                total_height = bbox[3] - bbox[1] if bbox else 0
                visible_height = self.canvas.winfo_height()
                if total_height > visible_height:
                    button_bottom = (
                        self.add_ingredient_button.winfo_rooty()
                        - self.content_frame.winfo_rooty()
                        + self.add_ingredient_button.winfo_height()
                    )
                    target_top = max(0, button_bottom - visible_height)
                    self.canvas.yview_moveto(min(1.0, target_top / total_height))
            except (tk.TclError, ZeroDivisionError):
                pass

    def add_new_ingredient_global(self):
        new_name = simpledialog.askstring(
            t("recipeform_new_ingredient_dialog_title"), t("recipeform_new_ingredient_dialog_prompt"), parent=self
        )
        if not new_name:
            return
        new_name = normalize_oe(new_name.strip())
        if not new_name:
            return
        existing_match = resolve_ingredient_input(new_name, self.ingredient_names)
        if existing_match is not None:
            messagebox.showinfo(
                t("common_info"), t("recipeform_ingredient_already_exists", name=existing_match)
            )
            return

        ingredients = load_ingredients()
        ingredients.append(new_name)
        self.ingredient_names = save_ingredients(ingredients)
        self.app.refresh_ingredients()

        # Met à jour les suggestions déjà affichées dans cette fenêtre
        for name_e, qty_e, unit_e, custom_e in self.ingredient_rows:
            name_e.full_values = get_display_ingredient_values(self.ingredient_names)

        messagebox.showinfo(
            t("recipeform_ingredient_added_title"),
            t("recipeform_ingredient_added_message", name=new_name)
        )

    @staticmethod
    def _validate_time_field(raw_value, label):
        """Valide un champ de temps optionnel (minutes). Retourne
        (valeur_normalisée, ok). Une valeur vide est acceptée (temps non
        renseigné)."""
        raw_value = raw_value.strip()
        if not raw_value:
            return "", True
        try:
            value = parse_finite_number(raw_value)
            if value < 0:
                raise ValueError
        except (ValueError, TypeError):
            return None, False
        if value == int(value):
            return str(int(value)), True
        return str(value), True

    def _resolve_unknown_ingredients_before_save(self):
        unknown = []
        for name_e, _qty_e, _unit_e, _custom_e in self.ingredient_rows:
            raw_name = name_e.get().strip()
            if raw_name and resolve_ingredient_input(raw_name, self.ingredient_names) is None:
                unknown.append(raw_name)
        if not unknown:
            return True

        dialog = UnknownIngredientsDialog(self, unknown, self.ingredient_names)
        self.wait_window(dialog)
        if dialog.result is None:
            return False

        created = []
        for name_e, _qty_e, _unit_e, _custom_e in self.ingredient_rows:
            raw_name = name_e.get().strip()
            decision = dialog.result.get(ingredient_sort_key(raw_name))
            if not decision:
                continue
            action, canonical = decision
            if action == "create" and resolve_ingredient_input(canonical, self.ingredient_names) is None:
                self.ingredient_names.append(canonical)
                created.append(canonical)
            name_e.delete(0, tk.END)
            name_e.insert(0, translate_ingredient_name(canonical))

        if created:
            self.ingredient_names = save_ingredients(self.ingredient_names)
            self.app.refresh_ingredients()
        display_values = get_display_ingredient_values(self.ingredient_names)
        for name_e, _qty_e, _unit_e, _custom_e in self.ingredient_rows:
            name_e.full_values = display_values
        return True

    def save_recipe(self):
        name = self.name_entry.get().strip()
        if not name:
            messagebox.showerror(t("common_error"), t("recipeform_error_name_required"))
            return

        # Les identifiants sont stables, mais un nom en double reste très ambigu
        # dans les listes et les échanges. On avertit sans interdire le cas volontaire.
        duplicate_name = next(
            (r for r in load_recipes()
             if r.get("name", "").strip().casefold() == name.casefold()
             and (not self.editing or r.get("id") != self.existing_recipe.get("id"))),
            None
        )
        if duplicate_name and not ask_yes_no(
                t("recipeform_duplicate_name_title"),
                t("recipeform_duplicate_name_message", name=name), parent=self):
            return

        try:
            default_persons = parse_positive_number(self.default_persons_entry.get())
        except (ValueError, TypeError):
            messagebox.showerror(t("common_error"), t("recipeform_error_default_persons"), parent=self)
            return
        if default_persons == int(default_persons):
            default_persons = int(default_persons)

        prep_time, ok_prep = self._validate_time_field(self.prep_time_entry.get(), "préparation")
        if not ok_prep:
            messagebox.showerror(t("common_error"), t("recipeform_error_prep_time"))
            return
        cook_time, ok_cook = self._validate_time_field(self.cook_time_entry.get(), "cuisson")
        if not ok_cook:
            messagebox.showerror(t("common_error"), t("recipeform_error_cook_time"))
            return

        if not self._resolve_unknown_ingredients_before_save():
            return

        ingredients = []
        for name_e, qty_e, unit_e, custom_e in self.ingredient_rows:
            ing_name_raw = name_e.get().strip()
            qty_str = qty_e.get().strip().replace(",", ".")
            unit_choice = resolve_unit_input(unit_e.get().strip(), self.UNIT_OPTIONS)
            if not ing_name_raw:
                continue
            canonical = resolve_ingredient_input(ing_name_raw, self.ingredient_names)
            if canonical is None:
                messagebox.showerror(
                    t("recipeform_unknown_ingredient_title"),
                    t("recipeform_unknown_ingredient_message", name=ing_name_raw)
                )
                return
            ing_name = canonical
            try:
                qty = parse_optional_positive_number(qty_str, allow_zero=True)
            except ValueError:
                messagebox.showerror(t("common_error"), t("recipeform_error_invalid_quantity", name=ing_name))
                return
            if unit_choice == "autre":
                unit = custom_e.get().strip()
                if not unit:
                    messagebox.showerror(
                        t("common_error"), t("recipeform_error_custom_unit_required", name=ing_name)
                    )
                    return
            else:
                unit = unit_choice
            ingredients.append({"name": ing_name, "quantity": qty, "unit": unit})

        if not ingredients:
            messagebox.showerror(t("common_error"), t("recipeform_error_no_valid_ingredient"))
            return

        # Détection de doublons : le même ingrédient saisi dans plusieurs
        # lignes est presque toujours une erreur de saisie (copier-coller,
        # ligne ajoutée deux fois par mégarde). On prévient avant
        # d'enregistrer, mais sans bloquer complètement — au cas où ce
        # serait volontaire (deux quantités séparées pour un même
        # ingrédient utilisé à deux endroits différents de la recette).
        seen_keys = set()
        duplicate_names = []
        for ing in ingredients:
            key = ingredient_sort_key(ing["name"])
            if key in seen_keys:
                if ing["name"] not in duplicate_names:
                    duplicate_names.append(ing["name"])
            else:
                seen_keys.add(key)
        if duplicate_names:
            duplicate_display = ", ".join(translate_ingredient_name(n) for n in duplicate_names)
            if not ask_yes_no(
                t("recipeform_duplicate_ingredient_title"),
                t("recipeform_duplicate_ingredient_message", list=duplicate_display)
            ):
                return

        # Construit la liste finale des photos : celles déjà enregistrées qui
        # n'ont pas été retirées, plus celles nouvellement choisies (copiées
        # sur le disque à ce moment-là).
        final_images = []
        newly_copied_images = []
        for kind, ref in self.gallery_items:
            if kind == "existing":
                safe = safe_image_filename(ref)
                if safe:
                    final_images.append(safe)
            else:
                try:
                    copied = copy_image_to_store(ref)
                except Exception as exc:
                    log_internal_error("copy_recipe_image", exc)
                    copied = None
                if copied:
                    final_images.append(copied)
                    newly_copied_images.append(copied)
                else:
                    for fname in newly_copied_images:
                        delete_image_file(fname)
                    messagebox.showerror(
                        t("common_error"), t("recipeform_photo_copy_failed"), parent=self
                    )
                    return

        raw_tags = [t.strip() for t in self.tags_entry.get().split(",") if t.strip()]
        # Déduplique les étiquettes identiques à la casse près (ex. « rapide »
        # et « Rapide » tapées par erreur toutes les deux), en conservant la
        # première graphie rencontrée et l'ordre de saisie.
        tags = []
        seen_tag_keys = set()
        for tag in raw_tags:
            tag_key = ingredient_sort_key(tag)
            if tag_key not in seen_tag_keys:
                seen_tag_keys.add(tag_key)
                tags.append(tag)

        # La date de mise en liste d'envies n'est (re)fixée que lors du
        # passage de "pas en liste" à "en liste", pour pouvoir signaler plus
        # tard les recettes qui y attendent depuis longtemps.
        was_wishlist = self.existing_recipe.get("wishlist", False) if self.editing else False
        now_wishlist = self.wishlist_var.get()
        if now_wishlist and was_wishlist:
            wishlist_since = self.existing_recipe.get("wishlist_since") or datetime.now().isoformat()
        elif now_wishlist:
            wishlist_since = datetime.now().isoformat()
        else:
            wishlist_since = None

        recipes = load_recipes()
        recipe_data = {
            "id": self.existing_recipe.get("id") if self.editing and self.existing_recipe.get("id") else uuid.uuid4().hex,
            "name": name,
            "category": resolve_category_input(self.category_combo.get(), self.CATEGORY_OPTIONS),
            "favorite": self.favorite_var.get(),
            "wishlist": now_wishlist,
            "wishlist_since": wishlist_since,
            "rating": self.rating_value,
            "prep_time": prep_time,
            "cook_time": cook_time,
            "difficulty": resolve_difficulty_input(self.difficulty_combo.get(), self.DIFFICULTY_OPTIONS),
            "default_persons": default_persons,
            "tags": tags,
            "allergens": [a for a, var in self.allergen_vars.items() if var.get()],
            "description": self.description_text.get("1.0", "end-1c").strip()[: self.MAX_DESC_LEN],
            "personal_notes": self.notes_text.get("1.0", "end-1c").strip(),
            "family_opinion": self.family_opinion_text.get("1.0", "end-1c").strip(),
            "improvement_notes": self.improvement_notes_text.get("1.0", "end-1c").strip(),
            "actual_difficulty": resolve_difficulty_input(self.actual_difficulty_combo.get(), self.DIFFICULTY_OPTIONS) if self.actual_difficulty_combo.get() else "",
            "ingredients": ingredients,
            "images": final_images,
            "created_at": self.existing_recipe.get("created_at") if self.editing else datetime.now().isoformat(),
            "times_cooked": self.existing_recipe.get("times_cooked", 0) if self.editing else 0,
            "cooked_dates": self.existing_recipe.get("cooked_dates", []) if self.editing else [],
        }
        # Préserve les champs provenant de l'autre application (et les futurs
        # champs encore inconnus de cette interface) lorsqu'une recette importée
        # est simplement modifiée sous Windows.
        if self.editing and self.existing_recipe:
            for _key, _value in self.existing_recipe.items():
                if _key not in recipe_data:
                    recipe_data[_key] = copy.deepcopy(_value)
        elif self.prefill:
            # Conserve notamment source_url et quantity_basis fournis par
            # l'import URL, ainsi que les futurs champs compatibles.
            for _key, _value in self.prefill.items():
                if _key not in recipe_data and _key not in {
                    "image_sources", "temporary_image_sources"
                }:
                    recipe_data[_key] = copy.deepcopy(_value)
        if not recipe_data["created_at"]:
            recipe_data["created_at"] = datetime.now().isoformat()

        if self.editing:
            recipes[self.recipe_index] = recipe_data
        else:
            recipes.append(recipe_data)

        try:
            save_recipes(recipes)
        except Exception:
            # La recette n'a pas été modifiée : retirer seulement les nouvelles
            # copies afin de ne laisser aucune photo orpheline.
            for fname in newly_copied_images:
                delete_image_file(fname)
            raise

        # Les anciennes photos ne sont retirées qu'après la réussite du JSON.
        if self.editing:
            for fname in get_recipe_images(self.existing_recipe):
                if fname not in final_images:
                    delete_recipe_images(
                        {"images": [fname]}, protected_recipes=recipes,
                        protected_trash=load_trash()
                    )
        # Une fermeture normale ne doit pas laisser de brouillon ; celui-ci
        # est réservé aux arrêts brutaux ou aux plantages.
        self._delete_draft()
        for _tmp_source in list(getattr(self, "_temporary_import_sources", set())):
            try:
                if os.path.isfile(_tmp_source): os.remove(_tmp_source)
            except OSError as exc:
                log_internal_error("cleanup_saved_import_temp", exc)
        self._temporary_import_sources.clear()
        self.app.refresh_recipes()
        self.app.show_toast(t("recipeform_saved_message", name=name))
        self.destroy()

    def delete_recipe(self):
        if not ask_yes_no(
            t("common_confirm"),
            t("recipeform_delete_confirm_message", name=self.existing_recipe['name'])
        ):
            return
        delete_recipe_to_trash(recipe_id=self.existing_recipe.get("id"), recipe_index=self.recipe_index)
        self._delete_draft()
        self.app.refresh_recipes()
        messagebox.showinfo(t("recipeform_deleted_title"), t("recipeform_deleted_message"))
        self.destroy()



class ManageRecipesWindow(tk.Toplevel):
    """Bibliothèque moderne : grille/liste, recherche, filtres combinables,
    tris enrichis, tags cliquables et menu contextuel complet."""

    PAGE_SIZE = 60

    def __init__(self, app, quick_filter=None, initial_search=""):
        super().__init__(app)
        self.app = app
        self.quick_filter = quick_filter
        self.filtered_indices = []
        self.display_limit = self.PAGE_SIZE
        self._grid_refs = []
        self._grid_items = []
        self._grid_columns = 1
        self._resize_after = None
        self._context_index = None
        settings = load_settings()
        self.view_mode = settings.get("recipe_library_view", "grid")
        if self.view_mode not in ("grid", "list"):
            self.view_mode = "grid"

        self.title(t("managerecipes_library_title"))
        screen_h = get_usable_screen_height(self)
        fit_window_to_workarea(self, gs(1180), screen_h, margin=18)
        safe_minsize(self, gs(820), gs(540))
        self.grab_set()

        header = ttk.Frame(self, padding=(20, 16, 20, 8))
        header.pack(fill="x")
        ttk.Label(header, text=t("managerecipes_library_title"), style="Title.TLabel").pack(side="left")
        ttk.Button(header, text=t("managerecipes_new_button"), style="Hero.TButton",
                   command=self._new_recipe).pack(side="right")

        searchbar = ttk.Frame(self, padding=(20, 4, 20, 6))
        searchbar.pack(fill="x")
        ttk.Label(searchbar, text=t("managerecipes_search_label")).pack(side="left")
        self.search_entry = ttk.Entry(searchbar, font=("Segoe UI", sf(10)))
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(8, 10), ipady=4)
        if initial_search:
            self.search_entry.insert(0, initial_search)
        self.search_entry.bind("<KeyRelease>", lambda e: self._filters_changed())

        self.sort_combo = ttk.Combobox(searchbar, values=[translate_sort_option(o) for o in RECIPE_SORT_OPTIONS],
                                       state="readonly", width=20)
        self.sort_combo.set(translate_sort_option(RECIPE_SORT_OPTIONS[0]))
        self.sort_combo.pack(side="left", padx=(0, 8))
        self.sort_combo.bind("<<ComboboxSelected>>", lambda e: self._filters_changed())

        self.view_button = ttk.Button(searchbar, style="Secondary.TButton", command=self._toggle_view)
        self.view_button.pack(side="right")
        self._update_view_button()

        # Filtres rapides historiques.
        chips = ttk.Frame(self, padding=(20, 0, 20, 6))
        chips.pack(fill="x")
        for text, qf in [(t("home_quick_filter_favorites"), "favoris"),
                         (t("home_quick_filter_quick"), "rapide"),
                         (t("home_quick_filter_vegetarian"), "vegetarien"),
                         (t("home_quick_filter_wishlist"), "envie")]:
            ttk.Button(chips, text=text, style="Secondary.TButton",
                       command=lambda f=qf: self._set_quick_filter(f)).pack(side="left", padx=(0, 6))

        # Filtres combinables : catégorie, temps, difficulté, favoris,
        # jamais cuisinées, disponibilité garde-manger et étiquette.
        filters = ttk.LabelFrame(self, text=t("managerecipes_more_filters"), padding=(12, 8))
        filters.pack(fill="x", padx=20, pady=(0, 8))
        ttk.Label(filters, text=t("managerecipes_category_label")).grid(row=0, column=0, padx=(0, 4), pady=3, sticky="w")
        self.category_filter_combo = ttk.Combobox(
            filters, values=[t("common_all_categories")] + [translate_category_name(c) for c in RecipeFormWindow.CATEGORY_OPTIONS],
            state="readonly", width=17)
        self.category_filter_combo.set(t("common_all_categories"))
        self.category_filter_combo.grid(row=0, column=1, padx=(0, 12), pady=3, sticky="w")
        self.category_filter_combo.bind("<<ComboboxSelected>>", lambda e: self._filters_changed())

        ttk.Label(filters, text=t("managerecipes_max_time")).grid(row=0, column=2, padx=(0, 4), pady=3, sticky="w")
        self.time_combo = ttk.Combobox(filters, values=[t("managerecipes_all_times"), "≤ 30 min", "≤ 60 min", "≤ 90 min", "≤ 120 min"],
                                       state="readonly", width=14)
        self.time_combo.set(t("managerecipes_all_times"))
        self.time_combo.grid(row=0, column=3, padx=(0, 12), pady=3, sticky="w")
        self.time_combo.bind("<<ComboboxSelected>>", lambda e: self._filters_changed())

        self.difficulty_combo = ttk.Combobox(filters,
            values=[t("managerecipes_all_difficulties")] + [translate_difficulty_name(x) for x in RecipeFormWindow.DIFFICULTY_OPTIONS],
            state="readonly", width=18)
        self.difficulty_combo.set(t("managerecipes_all_difficulties"))
        self.difficulty_combo.grid(row=0, column=4, padx=(0, 12), pady=3, sticky="w")
        self.difficulty_combo.bind("<<ComboboxSelected>>", lambda e: self._filters_changed())

        ttk.Label(filters, text=t("managerecipes_tags")).grid(row=0, column=5, padx=(0, 4), pady=3, sticky="w")
        self.tag_entry = ttk.Entry(filters, width=18)
        self.tag_entry.grid(row=0, column=6, padx=(0, 8), pady=3, sticky="ew")
        self.tag_entry.bind("<KeyRelease>", lambda e: self._filters_changed())
        filters.columnconfigure(6, weight=1)

        self.favorite_var = tk.BooleanVar(value=False)
        self.never_cooked_var = tk.BooleanVar(value=False)
        self.pantry_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(filters, text=t("managerecipes_only_favorites"), variable=self.favorite_var,
                        command=self._filters_changed).grid(row=1, column=0, columnspan=2, sticky="w", pady=(5, 2))
        ttk.Checkbutton(filters, text=t("managerecipes_never_cooked"), variable=self.never_cooked_var,
                        command=self._filters_changed).grid(row=1, column=2, columnspan=2, sticky="w", pady=(5, 2))
        ttk.Checkbutton(filters, text=t("managerecipes_pantry_80"), variable=self.pantry_var,
                        command=self._filters_changed).grid(row=1, column=4, columnspan=2, sticky="w", pady=(5, 2))
        ttk.Button(filters, text=t("managerecipes_clear_filters"), style="Secondary.TButton",
                   command=self._clear_all_filters).grid(row=1, column=6, sticky="e", pady=(5, 2))

        # Zone de contenu commune aux deux modes.
        self.content_outer = ttk.Frame(self, padding=(20, 2, 20, 2))
        self.content_outer.pack(fill="both", expand=True)

        footer = ttk.Frame(self, padding=(20, 8, 20, 14))
        footer.pack(fill="x")
        self.count_label = ttk.Label(footer, text="", style="Muted.TLabel")
        self.count_label.pack(side="left")
        self.load_more_button = ttk.Button(footer, text=t("managerecipes_load_more"), style="Secondary.TButton",
                                           command=self._load_more)
        self.load_more_button.pack(side="right")

        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label=t("managerecipes_open"), command=self.open_selected)
        self.context_menu.add_command(label=t("managerecipes_cooking_mode"), command=self._context_cooking_mode)
        self.context_menu.add_separator()
        self.context_menu.add_command(label=t("managerecipes_edit_button"), command=self.edit_selected)
        self.context_menu.add_command(label=t("managerecipes_duplicate_button"), command=self.duplicate_selected)
        self.context_menu.add_command(label=t("managerecipes_add_shopping"), command=self._context_add_shopping)
        self.context_menu.add_command(label=t("managerecipes_open_planning"), command=self._context_open_planning)
        self.context_menu.add_separator()
        self.context_menu.add_command(label=t("managerecipes_show_qr"), command=self._context_qr)
        self.context_menu.add_command(label=t("managerecipes_export_pdf"), command=self._context_export_pdf)
        self.context_menu.add_separator()
        self.context_menu.add_command(label=t("managerecipes_delete_button"), command=self.delete_selected)

        self.bind("<Configure>", self._on_resize)
        self._populate()
        self.bind("<Return>", self._keyboard_open_selected, add="+")
        self.search_entry.focus_set()

    def _keyboard_open_selected(self, event=None):
        # Do not steal Enter from text-entry/combobox controls.
        focused = self.focus_get()
        if isinstance(focused, (tk.Entry, ttk.Entry, ttk.Combobox, tk.Text)):
            return None
        try:
            self.open_selected()
            return "break"
        except Exception as exc:
            log_internal_error("keyboard_open_selected", exc)
            return None

    def _new_recipe(self):
        self.destroy()
        RecipeFormWindow(self.app, recipe_index=None)

    def _save_view_preference(self):
        settings = load_settings()
        settings["recipe_library_view"] = self.view_mode
        save_settings(settings)

    def _update_view_button(self):
        # Le bouton indique l'autre vue disponible.
        self.view_button.config(text=t("managerecipes_view_list") if self.view_mode == "grid" else t("managerecipes_view_grid"))

    def _toggle_view(self):
        self.view_mode = "list" if self.view_mode == "grid" else "grid"
        self._save_view_preference()
        self._update_view_button()
        self._render_results()

    def _filters_changed(self):
        self.display_limit = self.PAGE_SIZE
        self._populate()

    def _set_quick_filter(self, value):
        self.quick_filter = None if self.quick_filter == value else value
        self._filters_changed()

    def _clear_all_filters(self):
        self.quick_filter = None
        self.search_entry.delete(0, tk.END)
        self.category_filter_combo.set(t("common_all_categories"))
        self.time_combo.set(t("managerecipes_all_times"))
        self.difficulty_combo.set(t("managerecipes_all_difficulties"))
        self.tag_entry.delete(0, tk.END)
        self.favorite_var.set(False)
        self.never_cooked_var.set(False)
        self.pantry_var.set(False)
        self._filters_changed()

    @staticmethod
    def _total_minutes(recipe):
        try:
            return float(recipe.get("prep_time") or 0) + float(recipe.get("cook_time") or 0)
        except (TypeError, ValueError):
            return 0.0

    def _matches_quick_filter(self, recipe):
        if self.quick_filter == "favoris":
            return bool(recipe.get("favorite"))
        if self.quick_filter == "rapide":
            total = self._total_minutes(recipe)
            return 0 < total <= 30
        if self.quick_filter == "vegetarien":
            tag_keys = {ingredient_sort_key(x) for x in recipe.get("tags", [])}
            return bool(tag_keys & {"vegetarien", "vegetarienne", "vegetarian", "vegetariano", "vegetariana", "vegetarisch"})
        if self.quick_filter == "envie":
            return bool(recipe.get("wishlist"))
        return True

    def _pantry_ratio(self, recipe):
        ingredients = [ingredient_sort_key(i.get("name", "")) for i in recipe.get("ingredients", []) if i.get("name")]
        if not ingredients:
            return 0.0
        pantry = load_pantry()
        have = {ingredient_sort_key(v.get("name", "")) for v in pantry.values() if v.get("name")}
        # Les produits de base comptent également comme disponibles, comme
        # dans « Que puis-je cuisiner ? ».
        have |= {ingredient_sort_key(x) for x in PANTRY_STAPLES}
        return sum(1 for x in ingredients if x in have) / len(ingredients)

    def _recipe_matches_advanced(self, recipe):
        cat = resolve_category_input(self.category_filter_combo.get(), RecipeFormWindow.CATEGORY_OPTIONS)
        if cat and cat != t("common_all_categories") and recipe.get("category", "Autre") != cat:
            return False

        time_text = self.time_combo.get()
        if time_text != t("managerecipes_all_times"):
            m = re.search(r"(\d+)", time_text)
            if m and (self._total_minutes(recipe) <= 0 or self._total_minutes(recipe) > int(m.group(1))):
                return False

        diff_text = self.difficulty_combo.get()
        if diff_text != t("managerecipes_all_difficulties"):
            diff = resolve_difficulty_input(diff_text, RecipeFormWindow.DIFFICULTY_OPTIONS)
            if recipe.get("difficulty") != diff:
                return False

        if self.favorite_var.get() and not recipe.get("favorite"):
            return False
        if self.never_cooked_var.get() and int(recipe.get("times_cooked", 0) or 0) > 0:
            return False
        if self.pantry_var.get() and self._pantry_ratio(recipe) < 0.8:
            return False

        tag = ingredient_sort_key(self.tag_entry.get().strip())
        if tag:
            recipe_tags = [ingredient_sort_key(x) for x in recipe.get("tags", [])]
            if not any(tag in x for x in recipe_tags):
                return False
        return True

    def _populate(self):
        search = self.search_entry.get().strip() if hasattr(self, "search_entry") else ""
        search_key = ingredient_sort_key(search) if search else ""
        option = resolve_sort_option_input(self.sort_combo.get(), RECIPE_SORT_OPTIONS)
        indexed = [(i, r) for i, r in enumerate(self.app.recipes)
                   if recipe_matches_search(r, search_key)
                   and self._matches_quick_filter(r)
                   and self._recipe_matches_advanced(r)]
        reverse = option in ("Ajoutées récemment",)
        indexed.sort(key=lambda pair: recipe_sort_key(pair[1], option), reverse=reverse)
        self._all_filtered = indexed
        self.filtered_indices = [i for i, r in indexed[:self.display_limit]]
        self._render_results()

    def _clear_content(self):
        for child in self.content_outer.winfo_children():
            child.destroy()
        self._grid_refs = []
        self._grid_items = []
        self.tree = None

    def _render_results(self):
        self._clear_content()
        shown = self._all_filtered[:self.display_limit] if hasattr(self, "_all_filtered") else []
        self.filtered_indices = [idx for idx, _ in shown]
        total = len(getattr(self, "_all_filtered", []))
        self.count_label.config(text=t("managerecipes_results_count", shown=len(shown), total=total))
        if total > len(shown):
            self.load_more_button.pack(side="right")
        else:
            self.load_more_button.pack_forget()

        if not shown:
            empty = tk.Frame(self.content_outer, background=COLOR_CARD, highlightbackground=COLOR_BORDER, highlightthickness=1)
            empty.pack(fill="both", expand=True, padx=2, pady=8)
            tk.Label(empty, text="📖", font=("Segoe UI Emoji", sf(34)), background=COLOR_CARD).pack(pady=(70, 8))
            tk.Label(empty, text=t("managerecipes_empty_title"), font=("Segoe UI", sf(14), "bold"),
                     background=COLOR_CARD, foreground=COLOR_TEXT).pack()
            tk.Label(empty, text=t("managerecipes_empty_hint"), font=("Segoe UI", sf(10)),
                     background=COLOR_CARD, foreground=COLOR_TEXT_MUTED).pack(pady=6)
            ttk.Button(empty, text=t("managerecipes_new_button"), style="Hero.TButton", command=self._new_recipe).pack(pady=12)
            return

        if self.view_mode == "list":
            self._render_list(shown)
        else:
            self._render_grid(shown)

    def _render_list(self, shown):
        wrap = ttk.Frame(self.content_outer)
        wrap.pack(fill="both", expand=True)
        cols = ("name", "category", "time", "difficulty", "rating", "cooked")
        self.tree = ttk.Treeview(wrap, columns=cols, show="headings", selectmode="browse")
        headings = {
            "name": t("managerecipes_col_name"), "category": t("managerecipes_col_category"),
            "time": t("managerecipes_col_time"), "difficulty": t("managerecipes_col_difficulty"),
            "rating": t("managerecipes_col_rating"), "cooked": "Cuisinée",
        }
        widths = {"name": 320, "category": 130, "time": 90, "difficulty": 110, "rating": 100, "cooked": 80}
        for col in cols:
            self.tree.heading(col, text=headings[col])
            self.tree.column(col, width=widths[col], anchor="w" if col in ("name", "category") else "center")
        vs = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vs.pack(side="right", fill="y")
        for idx, r in shown:
            total = self._total_minutes(r)
            total_text = f"{int(total) if total == int(total) else total} min" if total else "—"
            rating = max(0, min(5, int(r.get("rating") or 0)))
            stars = "★" * rating + "☆" * (5 - rating)
            name = ("⭐ " if r.get("favorite") else "") + ("💭 " if r.get("wishlist") else "") + r.get("name", "")
            self.tree.insert("", "end", iid=str(idx), values=(name, translate_category_name(r.get("category", "Autre")), total_text,
                            translate_difficulty_name(r.get("difficulty", "Facile")), stars, int(r.get("times_cooked", 0) or 0)))
        self.tree.bind("<Double-Button-1>", lambda e: self.open_selected())
        self.tree.bind("<Return>", lambda e: self.open_selected())
        self.tree.bind("<Button-3>", self._show_tree_context)

    def _render_grid(self, shown):
        wrap = ttk.Frame(self.content_outer)
        wrap.pack(fill="both", expand=True)
        self.grid_canvas = tk.Canvas(wrap, highlightthickness=0)
        vs = ttk.Scrollbar(wrap, orient="vertical", command=self.grid_canvas.yview)
        self.grid_frame = tk.Frame(self.grid_canvas, background=COLOR_BG)
        window_id = self.grid_canvas.create_window((0, 0), window=self.grid_frame, anchor="nw")
        self.grid_frame.bind("<Configure>", lambda e: self.grid_canvas.configure(scrollregion=self.grid_canvas.bbox("all")))
        self.grid_canvas.bind("<Configure>", lambda e: self.grid_canvas.itemconfigure(window_id, width=e.width))
        self.grid_canvas.configure(yscrollcommand=vs.set)
        self.grid_canvas.pack(side="left", fill="both", expand=True)
        vs.pack(side="right", fill="y")
        _ui_bind_local_mousewheel(self.grid_canvas, self.grid_frame, self._grid_mousewheel)
        self._render_grid_cards(shown)

    def _grid_mousewheel(self, event):
        try:
            self.grid_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except tk.TclError:
            pass

    def _on_card_hover_enter(self, idx, card):
        """Effet de survol/focus ("élévation") : la bordure de la carte
        devient plus marquée au survol de la souris OU quand elle reçoit le
        focus clavier (Tab), qu'il s'agisse du cadre lui-même ou de l'un de
        ses enfants (qui recouvrent presque toute sa surface visible).
        highlightbackground sert à la bordure hors focus (survol souris),
        highlightcolor à la bordure quand le widget a réellement le focus
        clavier — les deux sont mis à jour pour couvrir les deux cas."""
        try:
            card.configure(highlightbackground=COLOR_ACCENT, highlightcolor=COLOR_ACCENT,
                            highlightthickness=2)
        except tk.TclError:
            pass

    def _on_card_hover_leave(self, idx, card):
        # La carte sélectionnée (dernier clic gauche/clic droit) garde sa
        # bordure d'accent même quand la souris s'en éloigne ou qu'elle perd
        # le focus clavier.
        if idx == self._context_index:
            return
        try:
            card.configure(highlightbackground=COLOR_BORDER, highlightcolor=COLOR_BORDER,
                            highlightthickness=1)
        except tk.TclError:
            pass

    def _on_card_activate(self, idx, _event=None):
        """Ouvre la recette d'une carte activée au clavier (Entrée/Espace),
        même action que le double-clic ou le Retour en vue liste."""
        self._open_index(idx)

    def _move_grid_focus(self, current_idx, delta_row=0, delta_col=0):
        """Déplace le focus clavier vers la carte adjacente (haut/bas/
        gauche/droite) dans la grille, sans effet si on est déjà au bord."""
        positions = [idx for idx, _card in self._grid_items]
        if current_idx not in positions:
            return
        pos = positions.index(current_idx)
        columns = self._grid_columns or 1
        row, col = divmod(pos, columns)
        new_row, new_col = row + delta_row, col + delta_col
        if new_col < 0 or new_col >= columns:
            return
        new_pos = new_row * columns + new_col
        if not (0 <= new_pos < len(positions)):
            return
        _idx, card = self._grid_items[new_pos]
        card.focus_set()

    def _render_grid_cards(self, shown):
        for child in self.grid_frame.winfo_children():
            child.destroy()
        self._grid_refs = []
        self._grid_items = []
        available = max(gs(760), self.winfo_width() - gs(70))
        card_target = gs(285)
        columns = max(2, min(4, available // card_target))
        self._grid_columns = columns
        for c in range(columns):
            self.grid_frame.grid_columnconfigure(c, weight=1, uniform="recipe_cards")

        for pos, (idx, recipe) in enumerate(shown):
            row, col = divmod(pos, columns)
            # takefocus=1 : sans lui, une carte (tk.Frame) n'est jamais
            # atteignable au clavier (Tab) — seule la vue liste l'était
            # jusqu'ici. La bordure d'accent (survol/sélection) sert aussi
            # d'indicateur de focus clavier visible.
            card = tk.Frame(self.grid_frame, background=COLOR_CARD, highlightbackground=COLOR_BORDER,
                            highlightcolor=COLOR_BORDER, highlightthickness=1, cursor="hand2", takefocus=1)
            card.grid(row=row, column=col, padx=7, pady=7, sticky="nsew")
            self._grid_items.append((idx, card))

            photo_box = tk.Frame(card, background=COLOR_ACCENT_LIGHT, height=gs(155))
            photo_box.pack(fill="x")
            photo_box.pack_propagate(False)
            images = get_recipe_images(recipe)
            thumb = load_thumbnail(images[0], size=(gs(280), gs(155))) if images else None
            if thumb is not None:
                self._grid_refs.append(thumb)
                photo = tk.Label(photo_box, image=thumb, background=COLOR_ACCENT_LIGHT, cursor="hand2")
            else:
                photo = tk.Label(photo_box, text=t("managerecipes_no_photo"), background=COLOR_ACCENT_LIGHT,
                                 foreground=COLOR_TEXT_MUTED, font=("Segoe UI", sf(10)), justify="center", cursor="hand2")
            photo.pack(fill="both", expand=True)

            body = tk.Frame(card, background=COLOR_CARD, padx=12, pady=9)
            body.pack(fill="both", expand=True)
            title = ("⭐ " if recipe.get("favorite") else "") + recipe.get("name", "")
            title_label = tk.Label(body, text=title, background=COLOR_CARD, foreground=COLOR_TEXT,
                                   font=("Segoe UI", sf(11), "bold"), anchor="w", justify="left",
                                   wraplength=gs(245), cursor="hand2")
            title_label.pack(fill="x")
            total = self._total_minutes(recipe)
            meta=[]
            cat=translate_category_name(recipe.get("category", "Autre"))
            if cat: meta.append(cat)
            if total: meta.append(f"{int(total) if total == int(total) else total} min")
            if recipe.get("difficulty"): meta.append(translate_difficulty_name(recipe.get("difficulty")))
            tk.Label(body, text=" · ".join(meta), background=COLOR_CARD, foreground=COLOR_TEXT_MUTED,
                     font=("Segoe UI", sf(9)), anchor="w", cursor="hand2").pack(fill="x", pady=(3, 2))
            rating = int(recipe.get("rating", 0) or 0)
            stat = f"{rating_stars(rating) if rating else '☆☆☆☆☆'}    🍳 {int(recipe.get('times_cooked', 0) or 0)}"
            tk.Label(body, text=stat, background=COLOR_CARD, foreground=COLOR_ACCENT_DARK,
                     font=("Segoe UI", sf(9)), anchor="w", cursor="hand2").pack(fill="x")

            tags = [str(x).strip() for x in recipe.get("tags", []) if str(x).strip()][:3]
            if tags:
                tags_frame = tk.Frame(body, background=COLOR_CARD)
                tags_frame.pack(fill="x", pady=(6, 0))
                for tag in tags:
                    lab=tk.Label(tags_frame, text=f"  {tag}  ", background=COLOR_ACCENT_LIGHT,
                                 foreground=COLOR_ACCENT_DARK, font=("Segoe UI", sf(8)), cursor="hand2")
                    lab.pack(side="left", padx=(0,4))
                    lab.bind("<Button-1>", lambda e, value=tag: self._filter_by_tag(value))

            for widget in (card, photo_box, photo, body, title_label):
                widget.bind("<Button-1>", lambda e, i=idx: self._select_grid_index(i))
                widget.bind("<Double-Button-1>", lambda e, i=idx: self._open_index(i))
                widget.bind("<Button-3>", lambda e, i=idx: self._show_context(e, i))
                widget.bind("<Enter>", lambda e, i=idx, c=card: self._on_card_hover_enter(i, c))
                widget.bind("<Leave>", lambda e, i=idx, c=card: self._on_card_hover_leave(i, c))
            # Bind all non-tag labels inside body to opening/context as well.
            for widget in body.winfo_children():
                if isinstance(widget, tk.Label) and widget.master is body:
                    widget.bind("<Double-Button-1>", lambda e, i=idx: self._open_index(i))
                    widget.bind("<Button-3>", lambda e, i=idx: self._show_context(e, i))
                    widget.bind("<Enter>", lambda e, i=idx, c=card: self._on_card_hover_enter(i, c))
                    widget.bind("<Leave>", lambda e, i=idx, c=card: self._on_card_hover_leave(i, c))

            # Navigation clavier : la carte elle-même est l'unique arrêt de
            # tabulation (ses enfants ne prennent jamais le focus). Entrée
            # et Espace ouvrent la recette, comme un double-clic ; les
            # flèches déplacent le focus vers la carte adjacente, comme dans
            # une vraie grille.
            card.bind("<FocusIn>", lambda e, i=idx, c=card: self._on_card_hover_enter(i, c))
            card.bind("<FocusOut>", lambda e, i=idx, c=card: self._on_card_hover_leave(i, c))
            card.bind("<Return>", lambda e, i=idx: self._on_card_activate(i))
            card.bind("<space>", lambda e, i=idx: self._on_card_activate(i))
            card.bind("<Left>", lambda e, i=idx: self._move_grid_focus(i, delta_col=-1))
            card.bind("<Right>", lambda e, i=idx: self._move_grid_focus(i, delta_col=1))
            card.bind("<Up>", lambda e, i=idx: self._move_grid_focus(i, delta_row=-1))
            card.bind("<Down>", lambda e, i=idx: self._move_grid_focus(i, delta_row=1))

    def _on_resize(self, event):
        if event.widget is not self or self.view_mode != "grid":
            return
        if self._resize_after is not None:
            # Anti-rebond du redimensionnement : annuler un after() déjà
            # exécuté lève une TclError sans conséquence, à ignorer.
            try: self.after_cancel(self._resize_after)
            except Exception: pass
        self._resize_after = self.after(180, self._rerender_grid_after_resize)

    def _rerender_grid_after_resize(self):
        self._resize_after = None
        if self.view_mode == "grid" and hasattr(self, "_all_filtered"):
            self._render_results()

    def _filter_by_tag(self, tag):
        self.tag_entry.delete(0, tk.END)
        self.tag_entry.insert(0, tag)
        self._filters_changed()

    def _select_grid_index(self, idx):
        self._context_index = idx
        # Bordure d'accent sur la carte sélectionnée (highlightcolor est
        # aussi mis à jour : c'est cette option, et non highlightbackground,
        # que Tk affiche pour une carte qui a par ailleurs le focus clavier).
        for i, card in self._grid_items:
            color = COLOR_ACCENT if i == idx else COLOR_BORDER
            card.configure(highlightbackground=color, highlightcolor=color,
                           highlightthickness=2 if i == idx else 1)

    def _show_tree_context(self, event):
        row = self.tree.identify_row(event.y)
        if row:
            self.tree.selection_set(row)
            self.tree.focus(row)
            self._context_index = int(row)
            self.context_menu.tk_popup(event.x_root, event.y_root)

    def _show_context(self, event, idx):
        self._select_grid_index(idx)
        self._context_index = idx
        self.context_menu.tk_popup(event.x_root, event.y_root)

    def _selected_index(self, silent=False):
        if self.view_mode == "list" and self.tree is not None:
            sel = self.tree.selection()
            if sel:
                return int(sel[0])
        elif self._context_index is not None:
            return self._context_index
        if not silent:
            messagebox.showinfo(t("common_info"), t("managerecipes_select_recipe_first"))
        return None

    def _open_index(self, idx):
        if idx is None or idx >= len(self.app.recipes):
            return
        name=self.app.recipes[idx].get("name", "")
        try: self.grab_release()
        except tk.TclError: pass
        win=OneRecipeWindow(self.app, initial_recipe_name=name)
        self.wait_window(win)
        # La bibliothèque peut avoir été fermée pendant que la fiche était
        # ouverte (par exemple depuis la barre des tâches). Dans ce cas son
        # champ de recherche n'existe plus : ne pas tenter de la repeupler.
        if not self.winfo_exists():
            return
        try: self.grab_set()
        except tk.TclError: pass
        self.app.refresh_recipes()
        self._populate()

    def open_selected(self):
        self._open_index(self._selected_index())

    def edit_selected(self):
        idx = self._selected_index()
        if idx is None: return
        self.destroy()
        RecipeFormWindow(self.app, recipe_index=idx)

    def duplicate_selected(self):
        idx = self._selected_index()
        if idx is None: return
        recipes = load_recipes(); original = recipes[idx]; new_recipe = copy.deepcopy(original)
        new_recipe["id"] = uuid.uuid4().hex
        new_recipe["name"] = f"{original['name']} {t('managerecipes_duplicate_suffix')}"
        image_mapping = duplicate_recipe_images(original)
        apply_duplicated_image_mapping(new_recipe, image_mapping)
        recipes.append(new_recipe)
        try:
            save_recipes(recipes)
        except Exception:
            for duplicated_name in image_mapping.values():
                delete_image_file(duplicated_name)
            raise
        self.app.refresh_recipes(); self._populate()
        self.app.show_toast(t("managerecipes_duplicated_message", original=original['name'], new=new_recipe['name']))

    def delete_selected(self):
        idx = self._selected_index()
        if idx is None: return
        recipe = self.app.recipes[idx]
        if not ask_yes_no(t("common_confirm"), t("managerecipes_delete_confirm_message", name=recipe['name'])): return
        delete_recipe_to_trash(recipe_id=recipe.get("id"), recipe_index=idx)
        self._context_index=None
        self.app.refresh_recipes(); self._populate(); self.app.show_toast(t("managerecipes_deleted_message"))

    def _context_add_shopping(self):
        idx=self._selected_index()
        if idx is None: return
        recipe=self.app.recipes[idx]
        persons=recipe.get("default_persons", 1) or 1
        self.app.shopping_selection[recipe_ref_key(recipe)] = persons
        self.app.show_toast(t("managerecipes_added_shopping", name=recipe["name"], persons=persons))

    def _context_open_planning(self):
        idx=self._selected_index()
        if idx is None: return
        name=self.app.recipes[idx]["name"]
        try: self.grab_release()
        except tk.TclError: pass
        win=WeeklyPlanWindow(self.app)
        self.app.show_toast(t("managerecipes_planning_hint", name=name))
        self.wait_window(win)
        try: self.grab_set()
        except tk.TclError: pass

    def _context_cooking_mode(self):
        idx=self._selected_index()
        if idx is None: return
        recipe=self.app.recipes[idx]
        persons=float(recipe.get("default_persons", 1) or 1)
        try: self.grab_release()
        except tk.TclError: pass
        CookingModeWindow(self.app, recipe, persons)

    def _context_qr(self):
        idx=self._selected_index()
        if idx is None: return
        if not QRCODE_AVAILABLE or not PIL_AVAILABLE:
            messagebox.showerror(t("common_module_missing"), t("onerecipe_qr_module_missing"))
            return
        recipe=self.app.recipes[idx]
        QRCodeWindow(self.app, recipe, float(recipe.get("default_persons", 1) or 1))

    def _context_export_pdf(self):
        idx=self._selected_index()
        if idx is None: return
        if not REPORTLAB_AVAILABLE:
            messagebox.showerror(t("common_module_missing"), t("onerecipe_pdf_module_missing"))
            return
        recipe=self.app.recipes[idx]
        path=filedialog.asksaveasfilename(title=t("managerecipes_export_pdf_title"), defaultextension=".pdf",
                                          filetypes=[("Fichier PDF", "*.pdf")], initialfile=f"{sanitize_windows_filename(recipe.get('name'), 'recette')}.pdf")
        if not path: return
        try:
            OneRecipeWindow._build_recipe_pdf(path, recipe, float(recipe.get("default_persons", 1) or 1))
        except Exception as e:
            messagebox.showerror(t("common_error"), str(e)); return
        self.app.show_toast(t("managerecipes_export_pdf_done", path=path))

    def _load_more(self):
        self.display_limit += self.PAGE_SIZE
        self._render_results()


class TrashWindow(tk.Toplevel):
    """Corbeille : liste les recettes supprimées récemment, avec la
    possibilité de les restaurer ou de les effacer définitivement."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title(t("trash_title"))
        fit_window_to_workarea(self, gs(560), gs(520), margin=14)
        self.grab_set()

        ttk.Label(self, text=t("trash_heading"), font=("Segoe UI", sf(13), "bold")).pack(pady=(15, 5))
        ttk.Label(
            self,
            text=t("trash_intro"),
            justify="center", font=("Segoe UI", sf(9)), foreground=COLOR_TEXT_MUTED
        ).pack(pady=(0, 10))

        list_frame = ttk.Frame(self)
        list_frame.pack(padx=15, pady=5, fill="both", expand=True)
        self.listbox = tk.Listbox(list_frame, width=56, height=14, font=("Segoe UI", sf(9)))
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scrollbar.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self._populate()

        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=12)
        ttk.Button(btn_frame, text=t("trash_restore_button"), command=self.restore_selected).grid(row=0, column=0, padx=5)
        ttk.Button(btn_frame, text=t("trash_delete_forever_button"),
                   command=self.delete_selected_forever).grid(row=0, column=1, padx=5)
        ttk.Button(btn_frame, text=t("trash_empty_button"),
                   command=self.empty_trash).grid(row=0, column=2, padx=5)

    def _populate(self):
        self.listbox.delete(0, tk.END)
        self.trash = load_trash()
        for entry in self.trash:
            recipe = entry.get("recipe", {})
            try:
                deleted_at = datetime.fromisoformat(entry.get("deleted_at", ""))
                date_display = deleted_at.strftime("%d/%m/%Y à %H:%M")
            except ValueError:
                date_display = t("trash_unknown_date")
            self.listbox.insert(
                tk.END,
                t("trash_entry_line", name=recipe.get('name', t('trash_unnamed_recipe')), date=date_display)
            )
        if not self.trash:
            self.listbox.insert(tk.END, t("trash_is_empty"))

    def _selected_index(self):
        sel = self.listbox.curselection()
        if not sel or not self.trash:
            messagebox.showinfo(t("common_info"), t("trash_select_recipe_first"))
            return None
        return sel[0]

    def restore_selected(self):
        idx = self._selected_index()
        if idx is None:
            return
        recipe = restore_recipe_from_trash(idx)

        self.app.refresh_recipes()
        self._populate()
        messagebox.showinfo(t("trash_restored_title"), t("trash_restored_message", name=recipe['name']))

    def delete_selected_forever(self):
        idx = self._selected_index()
        if idx is None:
            return
        entry = self.trash[idx]
        recipe = entry["recipe"]
        if not ask_yes_no(
            t("common_confirm"),
            t("trash_delete_forever_confirm", name=recipe['name'])
        ):
            return
        permanently_delete_trash_entries([idx])
        self._populate()
        messagebox.showinfo(t("trash_deleted_title"), t("trash_deleted_message"))

    def empty_trash(self):
        trash = load_trash()
        if not trash:
            messagebox.showinfo(t("common_info"), t("trash_already_empty"))
            return
        if not ask_yes_no(
            t("common_confirm"),
            t("trash_empty_confirm", count=len(trash))
        ):
            return
        permanently_delete_trash_entries()
        self._populate()
        messagebox.showinfo(t("trash_emptied_title"), t("trash_emptied_message"))


class ManageIngredientsWindow(tk.Toplevel):
    """Fenêtre pour ajouter, renommer ou supprimer un ingrédient de la liste
    réutilisable dans les recettes."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title(t("manageing_title"))
        fit_window_to_workarea(self, gs(420), gs(680), margin=18)
        self.grab_set()

        ttk.Label(self, text=t("manageing_list_label"),
                  font=("Segoe UI", sf(11), "bold")).pack(pady=(10, 5))

        search_frame = ttk.Frame(self)
        search_frame.pack(pady=(0, 5), fill="x", padx=15)
        ttk.Label(search_frame, text=t("common_search_label")).pack(side="left")
        self.search_entry = ttk.Entry(search_frame, width=28)
        self.search_entry.pack(side="left", padx=5, fill="x", expand=True)
        self.search_entry.bind("<KeyRelease>", lambda e: self._populate())

        list_frame = ttk.Frame(self)
        list_frame.pack(pady=5, padx=15, fill="both", expand=True)
        self.listbox = tk.Listbox(list_frame, width=36, height=14, font=("Segoe UI", sf(9)))
        list_scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=list_scrollbar.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        list_scrollbar.pack(side="right", fill="y")
        self.listbox.bind("<Double-Button-1>", lambda e: self.edit_selected())
        self._populate()

        add_frame = ttk.Frame(self)
        add_frame.pack(pady=10)
        self.new_entry = ttk.Entry(add_frame, width=25)
        self.new_entry.grid(row=0, column=0, padx=5)
        ttk.Button(add_frame, text=t("manageing_add_button"), command=self.add_ingredient).grid(row=0, column=1)
        self.new_entry.bind("<Return>", lambda e: self.add_ingredient())

        # Sur les écrans bas ou en mode Texte agrandi, les deux boutons
        # d'édition du bas faisaient dépasser la fenêtre. Ils restent visibles
        # sur un écran confortable et passent dans « Plus d'outils » sur les
        # petits écrans afin de ne jamais être cachés.
        compact_actions = (get_usable_screen_height(self) < gs(700) or FONT_SCALE > 1.0)
        if not compact_actions:
            btn_frame = ttk.Frame(self)
            btn_frame.pack(pady=8)
            ttk.Button(btn_frame, text=t("manageing_edit_button"), command=self.edit_selected).grid(row=0, column=0, padx=5)
            ttk.Button(btn_frame, text=t("manageing_delete_button"), command=self.delete_selected).grid(row=0, column=1, padx=5)

        tools_button = ttk.Button(self, text=t("manageing_more_tools_button"))
        tools_button.pack(pady=(4, 8), padx=15, fill="x")
        tools_menu = tk.Menu(tools_button, tearoff=0)
        if compact_actions:
            tools_menu.add_command(label=t("manageing_edit_button"), command=self.edit_selected)
            tools_menu.add_command(label=t("manageing_delete_button"), command=self.delete_selected)
            tools_menu.add_separator()
        tools_menu.add_command(label=t("manageing_load_defaults_button"), command=self.load_defaults)
        tools_menu.add_command(label=t("manageing_spell_check_button"), command=self.open_spell_check)
        tools_menu.add_command(label=t("manageing_prices_button"), command=self.open_prices)
        tools_menu.add_command(label=t("manageing_substitutions_button"), command=self.open_substitutions)
        tools_button.configure(command=lambda: tools_menu.tk_popup(
            tools_button.winfo_rootx(), tools_button.winfo_rooty() + tools_button.winfo_height()))

        ttk.Label(self, text=t("manageing_edit_hint"),
                  font=("Segoe UI", sf(8)), foreground=COLOR_TEXT_MUTED, justify="center").pack(pady=(0, 10))

    def _populate(self):
        self.listbox.delete(0, tk.END)
        search = self.search_entry.get().strip() if hasattr(self, "search_entry") else ""
        if search:
            search_key = ingredient_sort_key(search)
            names = [
                n for n in self.app.ingredient_names
                if search_key in ingredient_sort_key(n) or search_key in ingredient_sort_key(translate_ingredient_name(n))
            ]
        else:
            names = self.app.ingredient_names
        self._names = names
        for name in names:
            self.listbox.insert(tk.END, translate_ingredient_name(name))

    def _selected_name(self):
        sel = self.listbox.curselection()
        if not sel:
            messagebox.showinfo(t("common_info"), t("manageing_select_ingredient_first"))
            return None
        return self._names[sel[0]]

    def add_ingredient(self):
        prefill_name = normalize_oe(self.new_entry.get().strip())
        self.new_entry.delete(0, tk.END)
        IngredientEditWindow(self.app, manage_window=self, existing_name=None,
                              prefill_name=prefill_name)

    def edit_selected(self):
        name = self._selected_name()
        if name is None:
            return
        IngredientEditWindow(self.app, manage_window=self, existing_name=name)

    def delete_selected(self):
        name = self._selected_name()
        if name is None:
            return
        usage = count_ingredient_usage(name)
        message = t("manageing_delete_confirm_message", name=translate_ingredient_name(name))
        if usage:
            message += t("manageing_delete_usage_warning", count=usage)
        if not ask_yes_no(t("common_confirm"), message):
            return
        ingredients = [n for n in load_ingredients() if n.lower() != name.lower()]
        self.app.ingredient_names = save_ingredients(ingredients)
        self._populate()

    def load_defaults(self):
        if not os.path.exists(DEFAULT_INGREDIENTS_FILE):
            messagebox.showerror(
                t("manageing_missing_file_title"),
                t("manageing_missing_file_message")
            )
            return
        added = merge_default_ingredients()
        self.app.ingredient_names = load_ingredients()
        self._populate()
        if added:
            messagebox.showinfo(
                t("manageing_done_title"),
                t("manageing_defaults_added_message", count=added)
            )
        else:
            messagebox.showinfo(t("manageing_done_title"), t("manageing_defaults_none_added"))

    def open_spell_check(self):
        IngredientSpellCheckWindow(self.app, manage_window=self)

    def open_prices(self):
        IngredientPricesWindow(self.app)

    def open_substitutions(self):
        ManageSubstitutionsWindow(self.app)


class SubstitutionEditWindow(tk.Toplevel):
    """Fenêtre pour consulter/modifier la liste des substituts suggérés pour
    un ingrédient précis."""

    def __init__(self, app, ingredient_name, parent_window=None):
        super().__init__(parent_window or app)
        self.app = app
        self.ingredient_name = ingredient_name
        self.title(t("subedit_title", name=ingredient_name))
        fit_window_to_workarea(self, gs(480), gs(650), margin=18)
        safe_minsize(self, gs(420), gs(550))
        self.resizable(True, True)
        self.grab_set()

        ttk.Label(self, text=t("subedit_heading", name=ingredient_name),
                  font=("Segoe UI", sf(12), "bold"), wraplength=440, justify="center").pack(pady=(15, 5))
        ttk.Label(
            self, text=t("subedit_disclaimer"),
            font=("Segoe UI", sf(8)), foreground=COLOR_TEXT_MUTED, justify="center"
        ).pack(pady=(0, 10))

        self.current_list = [dict(s) for s in get_ingredient_substitutions(ingredient_name)]

        list_frame = ttk.Frame(self)
        list_frame.pack(padx=15, pady=5, fill="both", expand=True)
        self.listbox = tk.Listbox(list_frame, height=6, font=("Segoe UI", sf(9)))
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scrollbar.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self._refresh_listbox()

        ttk.Button(self, text=t("subedit_remove_button"),
                   command=self.remove_selected).pack(pady=(0, 10))

        add_frame = ttk.LabelFrame(self, text=t("subedit_add_frame_title"))
        add_frame.pack(padx=15, pady=(0, 10), fill="x")
        ttk.Label(add_frame, text=t("subedit_name_label")).grid(row=0, column=0, padx=5, pady=5, sticky="e")
        self.new_name_entry = ttk.Entry(add_frame, width=28)
        self.new_name_entry.full_values = get_display_ingredient_values(sorted(self.app.ingredient_names, key=ingredient_sort_key))
        self.new_name_entry.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        self.new_name_entry.bind("<KeyRelease>", lambda e: self._on_name_entry_keyrelease(e))
        self.new_name_entry.bind("<FocusIn>", lambda e: self._on_name_entry_focus_in(e))
        self.new_name_entry.bind("<FocusOut>", lambda e: self._on_name_entry_focus_out(e))
        ttk.Label(add_frame, text=t("subedit_note_label")).grid(row=1, column=0, padx=5, pady=5, sticky="e")
        self.new_note_entry = ttk.Entry(add_frame, width=28)
        self.new_note_entry.grid(row=1, column=1, padx=5, pady=5, sticky="w")
        ttk.Button(add_frame, text=t("subedit_add_to_list_button"), command=self.add_substitute).grid(
            row=2, column=0, columnspan=2, pady=(5, 5))

        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text=t("common_save_button"), command=self.save_and_close).grid(row=0, column=0, padx=5)
        if load_default_substitutions().get(ingredient_name.strip().lower()):
            ttk.Button(btn_frame, text=t("subedit_revert_button"),
                       command=self.revert_to_default).grid(row=0, column=1, padx=5)
        ttk.Button(btn_frame, text=t("subedit_cancel_button"), style="Secondary.TButton",
                   command=self.destroy).grid(row=0, column=2, padx=5)

        tk.Frame(self, height=SCROLL_BOTTOM_PADDING, background=COLOR_BG).pack(fill="x")

    def _refresh_listbox(self):
        self.listbox.delete(0, tk.END)
        if not self.current_list:
            self.listbox.insert(tk.END, t("subedit_no_substitute_yet"))
            return
        for sub in self.current_list:
            note = f" — {sub['note']}" if sub.get("note") else ""
            self.listbox.insert(tk.END, f"{sub['nom']}{note}")

    def add_substitute(self):
        nom = self.new_name_entry.get().strip()
        if not nom:
            messagebox.showerror(t("common_error"), t("subedit_error_name_required"))
            return
        note = self.new_note_entry.get().strip()
        self.current_list.append({"nom": nom, "note": note})
        self._refresh_listbox()
        self.new_name_entry.delete(0, tk.END)
        self.new_note_entry.delete(0, tk.END)
        self.new_name_entry.focus_set()

    def remove_selected(self):
        sel = self.listbox.curselection()
        if not sel or not self.current_list:
            messagebox.showinfo(t("common_info"), t("subedit_select_to_remove"))
            return
        del self.current_list[sel[0]]
        self._refresh_listbox()

    def save_and_close(self):
        set_ingredient_override(self.ingredient_name, substitutions=self.current_list)
        self.destroy()

    def revert_to_default(self):
        if ask_yes_no(
            t("common_confirm"),
            t("subedit_revert_confirm_message", name=self.ingredient_name)
        ):
            revert_ingredient_substitutions_to_default(self.ingredient_name)
            self.destroy()

    # ---- Autocomplétion du champ Nom (même principe que les autres listes
    # déroulantes d'ingrédients de l'application) ----

    def _hide_name_suggestions(self):
        popup = getattr(self.new_name_entry, "_suggestion_popup", None)
        if popup is not None:
            try:
                popup.destroy()
            except tk.TclError:
                pass
            self.new_name_entry._suggestion_popup = None
            self.new_name_entry._suggestion_listbox = None

    def _show_name_suggestions(self, filtered):
        self._hide_name_suggestions()
        if not filtered:
            return
        entry = self.new_name_entry
        popup = tk.Toplevel(entry)
        popup.wm_overrideredirect(True)
        try:
            popup.wm_attributes("-topmost", True)
        except tk.TclError:
            pass
        width = max(entry.winfo_width(), gs(180))

        listbox = tk.Listbox(popup, height=min(6, len(filtered)), exportselection=False, font=("Segoe UI", sf(9)))
        listbox.pack(fill="both", expand=True)
        for v in filtered:
            listbox.insert(tk.END, v)
        finalize_suggestion_popup(popup, entry, listbox, width)

        def choose(event=None):
            sel = listbox.curselection()
            if sel:
                value = listbox.get(sel[0])
                entry.delete(0, tk.END)
                entry.insert(0, value)
            self._hide_name_suggestions()
            entry.focus_set()

        listbox.bind("<ButtonRelease-1>", choose)
        listbox.bind("<Return>", choose)
        entry._suggestion_popup = popup
        entry._suggestion_listbox = listbox

    def _on_name_entry_keyrelease(self, event):
        if event.keysym == "Down":
            listbox = getattr(self.new_name_entry, "_suggestion_listbox", None)
            if listbox is not None:
                listbox.focus_set()
                listbox.selection_set(0)
            return
        if event.keysym == "Escape":
            self._hide_name_suggestions()
            return
        if event.keysym == "Return":
            self._hide_name_suggestions()
            self.add_substitute()
            return
        if event.keysym in ("Tab", "Shift_L", "Shift_R", "Control_L", "Control_R",
                            "Caps_Lock", "Alt_L", "Alt_R", "Left", "Right"):
            return
        filtered = self._filter_ingredient_values(self.new_name_entry.full_values, self.new_name_entry.get())
        if filtered:
            self._show_name_suggestions(filtered)
        else:
            self._hide_name_suggestions()

    def _on_name_entry_focus_in(self, event):
        filtered = self._filter_ingredient_values(self.new_name_entry.full_values, self.new_name_entry.get())
        if filtered:
            self._show_name_suggestions(filtered)

    def _on_name_entry_focus_out(self, event):
        self.new_name_entry.after(200, self._hide_name_suggestions)

    @staticmethod
    def _filter_ingredient_values(full_values, typed):
        if not typed:
            return full_values
        typed_key = ingredient_sort_key(typed)
        filtered = [v for v in full_values if ingredient_sort_key(v).startswith(typed_key)]
        if not filtered:
            filtered = [v for v in full_values if typed_key in ingredient_sort_key(v)]
        return filtered


class ManageSubstitutionsWindow(tk.Toplevel):
    """Fenêtre pour consulter et gérer les substituts d'ingrédients suggérés
    par l'application, ou en ajouter/modifier pour vos propres besoins."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title(t("managesub_title"))
        fit_window_to_workarea(self, gs(480), gs(700), margin=18)
        safe_minsize(self, gs(420), gs(460))
        self.resizable(True, True)
        self.grab_set()

        ttk.Label(self, text=t("managesub_heading"), font=("Segoe UI", sf(14), "bold")).pack(pady=(15, 5))
        ttk.Label(
            self, text=t("managesub_intro"),
            font=("Segoe UI", sf(8)), foreground=COLOR_TEXT_MUTED, justify="center"
        ).pack(pady=(0, 10))

        search_frame = ttk.Frame(self)
        search_frame.pack(pady=(0, 5), fill="x", padx=15)
        ttk.Label(search_frame, text=t("common_search_label")).pack(side="left")
        self.search_entry = ttk.Entry(search_frame)
        self.search_entry.pack(side="left", padx=5, fill="x", expand=True)
        self.search_entry.bind("<KeyRelease>", lambda e: self._populate())

        list_frame = ttk.Frame(self)
        list_frame.pack(pady=5, padx=15, fill="both", expand=True)
        self.listbox = tk.Listbox(list_frame, font=("Segoe UI", sf(9)))
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scrollbar.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.listbox.bind("<Double-Button-1>", lambda e: self.edit_selected())

        self.displayed_names = []
        self._populate()

        add_frame = ttk.Frame(self)
        add_frame.pack(pady=(5, 5), padx=15, fill="x")
        ttk.Label(add_frame, text=t("common_ingredient_label")).pack(side="left")
        self.name_entry = ttk.Entry(add_frame, width=20)
        self.name_entry.full_values = get_display_ingredient_values(sorted(self.app.ingredient_names, key=ingredient_sort_key))
        self.name_entry.pack(side="left", padx=5, fill="x", expand=True)
        self.name_entry.bind("<KeyRelease>", lambda e: self._on_name_entry_keyrelease(e))
        self.name_entry.bind("<FocusIn>", lambda e: self._on_name_entry_focus_in(e))
        self.name_entry.bind("<FocusOut>", lambda e: self._on_name_entry_focus_out(e))
        ttk.Button(add_frame, text=t("managesub_manage_button"), command=self.edit_typed).pack(side="left", padx=(5, 0))

        ttk.Label(
            self, text=t("managesub_hint"),
            font=("Segoe UI", sf(8)), foreground=COLOR_TEXT_MUTED, justify="center"
        ).pack(pady=(10, 5))

        tk.Frame(self, height=SCROLL_BOTTOM_PADDING, background=COLOR_BG).pack(fill="x")

    def _populate(self):
        self.listbox.delete(0, tk.END)
        search = self.search_entry.get().strip()
        search_key = ingredient_sort_key(search) if search else ""
        keys_with_subs = has_known_substitutions()
        name_by_key = {ingredient_sort_key(n): n for n in self.app.ingredient_names}
        self.displayed_names = []
        for key in sorted(keys_with_subs):
            name = name_by_key.get(key, key.capitalize())
            if search_key and search_key not in ingredient_sort_key(name) \
                    and search_key not in ingredient_sort_key(translate_ingredient_name(name)):
                continue
            self.displayed_names.append(name)
        if not self.displayed_names:
            self.listbox.insert(tk.END, t("managesub_none_with_substitute"))
            return
        for name in self.displayed_names:
            count = len(get_ingredient_substitutions(name))
            plural = "s" if count > 1 else ""
            self.listbox.insert(
                tk.END, t("managesub_substitute_count", name=translate_ingredient_name(name), count=count, plural=plural)
            )

    def edit_selected(self):
        sel = self.listbox.curselection()
        if not sel or not self.displayed_names:
            messagebox.showinfo(t("common_info"), t("manageing_select_ingredient_first"))
            return
        name = self.displayed_names[sel[0]]
        self._open_editor(name)

    def edit_typed(self):
        typed = normalize_oe(self.name_entry.get().strip())
        if not typed:
            messagebox.showerror(t("common_error"), t("managesub_error_ingredient_required"))
            return
        canonical = resolve_ingredient_input(typed, self.app.ingredient_names)
        if canonical is None:
            messagebox.showerror(
                t("common_unknown_ingredient_title"),
                t("managesub_unknown_ingredient_message", name=typed)
            )
            return
        self._open_editor(canonical)

    def _open_editor(self, name):
        win = SubstitutionEditWindow(self.app, name, parent_window=self)
        self.wait_window(win)
        self._populate()

    # ---- Autocomplétion du champ ingrédient (même principe que les autres
    # listes déroulantes d'ingrédients de l'application) ----

    def _hide_name_suggestions(self):
        popup = getattr(self.name_entry, "_suggestion_popup", None)
        if popup is not None:
            try:
                popup.destroy()
            except tk.TclError:
                pass
            self.name_entry._suggestion_popup = None
            self.name_entry._suggestion_listbox = None

    def _show_name_suggestions(self, filtered):
        self._hide_name_suggestions()
        if not filtered:
            return
        entry = self.name_entry
        popup = tk.Toplevel(entry)
        popup.wm_overrideredirect(True)
        try:
            popup.wm_attributes("-topmost", True)
        except tk.TclError:
            pass
        width = max(entry.winfo_width(), gs(180))

        listbox = tk.Listbox(popup, height=min(6, len(filtered)), exportselection=False, font=("Segoe UI", sf(9)))
        listbox.pack(fill="both", expand=True)
        for v in filtered:
            listbox.insert(tk.END, v)
        finalize_suggestion_popup(popup, entry, listbox, width)

        def choose(event=None):
            sel = listbox.curselection()
            if sel:
                value = listbox.get(sel[0])
                entry.delete(0, tk.END)
                entry.insert(0, value)
            self._hide_name_suggestions()
            entry.focus_set()

        listbox.bind("<ButtonRelease-1>", choose)
        listbox.bind("<Return>", choose)
        entry._suggestion_popup = popup
        entry._suggestion_listbox = listbox

    def _on_name_entry_keyrelease(self, event):
        if event.keysym == "Down":
            listbox = getattr(self.name_entry, "_suggestion_listbox", None)
            if listbox is not None:
                listbox.focus_set()
                listbox.selection_set(0)
            return
        if event.keysym == "Escape":
            self._hide_name_suggestions()
            return
        if event.keysym == "Return":
            self._hide_name_suggestions()
            self.edit_typed()
            return
        if event.keysym in ("Tab", "Shift_L", "Shift_R", "Control_L", "Control_R",
                            "Caps_Lock", "Alt_L", "Alt_R", "Left", "Right"):
            return
        filtered = self._filter_ingredient_values(self.name_entry.full_values, self.name_entry.get())
        if filtered:
            self._show_name_suggestions(filtered)
        else:
            self._hide_name_suggestions()

    def _on_name_entry_focus_in(self, event):
        filtered = self._filter_ingredient_values(self.name_entry.full_values, self.name_entry.get())
        if filtered:
            self._show_name_suggestions(filtered)

    def _on_name_entry_focus_out(self, event):
        self.name_entry.after(200, self._hide_name_suggestions)

    @staticmethod
    def _filter_ingredient_values(full_values, typed):
        if not typed:
            return full_values
        typed_key = ingredient_sort_key(typed)
        filtered = [v for v in full_values if ingredient_sort_key(v).startswith(typed_key)]
        if not filtered:
            filtered = [v for v in full_values if typed_key in ingredient_sort_key(v)]
        return filtered


class IngredientPricesWindow(tk.Toplevel):
    """Fenêtre pour renseigner le prix de vos ingrédients, utilisé ensuite
    pour estimer le coût de vos recettes. Les prix sont saisis par vous —
    aucune source de prix en ligne n'est utilisée."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title(t("ingprices_title"))
        fit_window_to_workarea(self, gs(480), gs(620), margin=18)
        self.grab_set()

        ttk.Label(self, text=t("ingprices_heading"), font=("Segoe UI", sf(13), "bold")).pack(pady=(15, 5))
        ttk.Label(
            self,
            text=t("ingprices_intro"),
            justify="center", font=("Segoe UI", sf(9))
        ).pack(pady=(0, 10))

        search_frame = ttk.Frame(self)
        search_frame.pack(pady=(0, 5), fill="x", padx=15)
        ttk.Label(search_frame, text=t("common_search_label")).pack(side="left")
        self.search_entry = ttk.Entry(search_frame, width=28)
        self.search_entry.pack(side="left", padx=5, fill="x", expand=True)
        self.search_entry.bind("<KeyRelease>", lambda e: self._populate())

        list_frame = ttk.Frame(self)
        list_frame.pack(pady=5, padx=15, fill="both", expand=True)
        self.listbox = tk.Listbox(list_frame, width=48, height=13, font=("Segoe UI", sf(9)))
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scrollbar.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.listbox.bind("<<ListboxSelect>>", lambda e: self._load_selected_price())
        self._populate()

        edit_frame = ttk.Frame(self)
        edit_frame.pack(pady=10, padx=15, fill="x")
        ttk.Label(edit_frame, text=t("ingprices_price_label")).grid(row=0, column=0, padx=3)
        self.price_entry = ttk.Entry(edit_frame, width=8)
        self.price_entry.grid(row=0, column=1, padx=3)
        ttk.Label(edit_frame, text=t("ingprices_for_one_label")).grid(row=0, column=2, padx=3)
        self.unit_combo = ttk.Combobox(edit_frame, values=[translate_unit_name(u) for u in PRICE_UNIT_OPTIONS],
                                        state="readonly", width=15)
        self.unit_combo.set(translate_unit_name(PRICE_UNIT_OPTIONS[0]))
        self.unit_combo.grid(row=0, column=3, padx=3)

        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text=t("ingprices_save_button"),
                   command=self.save_price).grid(row=0, column=0, padx=5)
        ttk.Button(btn_frame, text=t("ingprices_clear_button"),
                   command=self.clear_price).grid(row=0, column=1, padx=5)

        ttk.Label(
            self,
            text=t("ingprices_units_note"),
            font=("Segoe UI", sf(8)), foreground=COLOR_TEXT_MUTED, justify="center"
        ).pack(pady=(0, 10))

    def _populate(self):
        self.listbox.delete(0, tk.END)
        search = self.search_entry.get().strip()
        search_key = ingredient_sort_key(search) if search else ""
        self._names = []
        for name in self.app.ingredient_names:
            if search_key and search_key not in ingredient_sort_key(name) \
                    and search_key not in ingredient_sort_key(translate_ingredient_name(name)):
                continue
            self._names.append(name)
            price_info = get_ingredient_price(name)
            if price_info:
                suffix = t("ingprices_price_suffix", price=f"{price_info['price']:.2f}", unit=price_info['unit'])
            else:
                suffix = t("ingprices_no_price_set")
            self.listbox.insert(tk.END, f"{translate_ingredient_name(name)}{suffix}")

    def _selected_name(self):
        sel = self.listbox.curselection()
        if not sel or not self._names:
            return None
        return self._names[sel[0]]

    def _load_selected_price(self):
        name = self._selected_name()
        if name is None:
            return
        price_info = get_ingredient_price(name)
        self.price_entry.delete(0, tk.END)
        if price_info:
            self.price_entry.insert(0, str(price_info["price"]))
            self.unit_combo.set(translate_unit_name(price_info["unit"]))
        else:
            self.unit_combo.set(translate_unit_name(PRICE_UNIT_OPTIONS[0]))

    def save_price(self):
        name = self._selected_name()
        if name is None:
            messagebox.showinfo(t("common_info"), t("manageing_select_ingredient_first"))
            return
        raw_price = self.price_entry.get().strip().replace(",", ".")
        try:
            price = float(raw_price)
            if price < 0:
                raise ValueError
        except ValueError:
            messagebox.showerror(t("common_error"), t("ingprices_error_invalid_price"))
            return
        set_ingredient_price(name, price, resolve_unit_input(self.unit_combo.get(), PRICE_UNIT_OPTIONS))
        self._populate()
        messagebox.showinfo(t("allrecipes_list_saved_title"), t("ingprices_saved_message", name=name))

    def clear_price(self):
        name = self._selected_name()
        if name is None:
            messagebox.showinfo(t("common_info"), t("manageing_select_ingredient_first"))
            return
        set_ingredient_price(name, None, None)
        self.price_entry.delete(0, tk.END)
        self._populate()


class IngredientEditWindow(tk.Toplevel):
    """Fenêtre unifiée pour ajouter un nouvel ingrédient ou modifier un
    ingrédient existant : nom, allergènes, valeurs nutritionnelles et prix."""

    def __init__(self, app, manage_window=None, existing_name=None, prefill_name="", parent_window=None):
        super().__init__(parent_window or app)
        self.app = app
        self.manage_window = manage_window
        self.existing_name = existing_name
        self.editing = existing_name is not None
        self.title(t("ingedit_title_edit") if self.editing else t("ingedit_title_new"))
        fit_window_to_workarea(self, gs(560), gs(620), margin=18)
        safe_minsize(self, gs(460), gs(440))
        self.grab_set()

        ttk.Label(self, text=t("ingedit_heading_edit") if self.editing else t("ingedit_heading_new"),
                  font=("Segoe UI", sf(13), "bold")).pack(pady=(12, 8))

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=14, pady=(0, 8))
        general_tab = ttk.Frame(notebook, padding=14)
        nutrition_tab = ttk.Frame(notebook, padding=14)
        notebook.add(general_tab, text=t("ingedit_tab_general"))
        notebook.add(nutrition_tab, text=t("ingedit_tab_nutrition_price"))

        ttk.Label(general_tab, text=t("ingedit_name_label"), font=("Segoe UI", sf(10), "bold")).pack()
        self.name_entry = ttk.Entry(general_tab, width=40)
        self.name_entry.pack(pady=(2, 12), fill="x")
        self.name_entry.insert(0, existing_name if self.editing else prefill_name)

        ttk.Label(general_tab, text=t("ingedit_allergens_label"), font=("Segoe UI", sf(10), "bold")).pack(pady=(5, 5))
        allergens_frame = ttk.Frame(general_tab)
        allergens_frame.pack(fill="x")
        existing_allergens = set(get_ingredient_allergens(existing_name)) if self.editing else set()
        self.allergen_vars = {}
        for i, allergen in enumerate(ALLERGENS):
            var = tk.BooleanVar(value=allergen in existing_allergens)
            self.allergen_vars[allergen] = var
            ttk.Checkbutton(allergens_frame, text=translate_allergen_name(allergen), variable=var).grid(
                row=i // 3, column=i % 3, sticky="w", padx=8, pady=2
            )

        ttk.Label(nutrition_tab, text=t("ingedit_nutrition_label"),
                  font=("Segoe UI", sf(10), "bold")).pack(pady=(2, 5))
        nutri_frame = ttk.Frame(nutrition_tab)
        nutri_frame.pack()
        existing_nutri = (get_ingredient_nutrition(existing_name) or {}) if self.editing else {}
        nutri_labels = [("kcal", t("ingedit_nutri_kcal")), ("protein_g", t("ingedit_nutri_protein")),
                         ("carbs_g", t("ingedit_nutri_carbs")), ("fat_g", t("ingedit_nutri_fat"))]
        self.nutri_entries = {}
        for i, (key, label) in enumerate(nutri_labels):
            ttk.Label(nutri_frame, text=f"{label} :").grid(row=i, column=0, sticky="e", padx=5, pady=4)
            entry = ttk.Entry(nutri_frame, width=12)
            if key in existing_nutri:
                entry.insert(0, str(existing_nutri[key]))
            entry.grid(row=i, column=1, sticky="w", padx=5, pady=4)
            self.nutri_entries[key] = entry
        ttk.Label(nutrition_tab, text=t("ingedit_nutrition_hint"), wraplength=460,
                  font=("Segoe UI", sf(8)), foreground=COLOR_TEXT_MUTED).pack(pady=(4, 10))
        source = existing_nutri.get("_ciqual", {})
        if source:
            source_text = t("ingedit_ciqual_source", code=source["code"], food=source["food"])
            if source.get("qualifiers"):
                source_text += "\n" + t("ingedit_ciqual_bounds")
        elif existing_nutri and (get_ingredient_override(existing_name) or {}).get("nutrition"):
            source_text = t("ingedit_personal_nutrition")
        else:
            source_text = t("ingedit_unverified_nutrition")
        ttk.Label(nutrition_tab, text=source_text, wraplength=460,
                  foreground=COLOR_TEXT_MUTED).pack(fill="x", pady=(0, 8))

        ttk.Label(nutrition_tab, text=t("ingedit_price_label"), font=("Segoe UI", sf(10), "bold")).pack(pady=(8, 5))
        price_frame = ttk.Frame(nutrition_tab)
        price_frame.pack()
        existing_price = get_ingredient_price(existing_name) if self.editing else None
        ttk.Label(price_frame, text=t("ingprices_price_label")).grid(row=0, column=0, padx=3)
        self.price_entry = ttk.Entry(price_frame, width=9)
        if existing_price:
            self.price_entry.insert(0, str(existing_price["price"]))
        self.price_entry.grid(row=0, column=1, padx=3)
        ttk.Label(price_frame, text=t("ingprices_for_one_label")).grid(row=0, column=2, padx=3)
        self.unit_combo = ttk.Combobox(price_frame, values=[translate_unit_name(u) for u in PRICE_UNIT_OPTIONS], state="readonly", width=15)
        self.unit_combo.set(translate_unit_name(existing_price["unit"]) if existing_price else translate_unit_name(PRICE_UNIT_OPTIONS[0]))
        self.unit_combo.grid(row=0, column=3, padx=3)

        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=(0, 12))
        ttk.Button(btn_frame, text=t("ingedit_save_button"), style="Primary.TButton", command=self.save).grid(row=0, column=0, padx=5)
        if self.editing:
            ttk.Button(btn_frame, text=t("ingedit_delete_button"), command=self.delete_ingredient).grid(row=0, column=1, padx=5)

    def _parse_float_or_none(self, entry, field_label):
        raw = entry.get().strip().replace(",", ".")
        if not raw:
            return None, True
        try:
            value = float(raw)
            if not math.isfinite(value) or value < 0:
                raise ValueError
            return value, True
        except ValueError:
            messagebox.showerror(t("common_error"), t("ingedit_error_invalid_field", field=field_label))
            return None, False

    def save(self):
        new_name = normalize_oe(self.name_entry.get().strip())
        if not new_name:
            messagebox.showerror(t("common_error"), t("ingedit_error_name_required"))
            return

        other_names = [
            n for n in self.app.ingredient_names
            if not (self.editing and n.lower() == self.existing_name.lower())
        ]
        if new_name.lower() in [n.lower() for n in other_names]:
            messagebox.showerror(t("common_error"), t("ingedit_error_already_exists", name=new_name))
            return

        plural_match = find_plural_duplicate(new_name, other_names)
        if plural_match:
            messagebox.showerror(
                t("common_error"),
                t("ingedit_error_plural_duplicate", name=new_name, existing=plural_match)
            )
            return

        nutrition = {}
        nutri_field_labels = {"kcal": t("ingedit_nutri_field_kcal"), "protein_g": t("ingedit_nutri_field_protein"),
                               "carbs_g": t("ingedit_nutri_field_carbs"), "fat_g": t("ingedit_nutri_field_fat")}
        for key, entry in self.nutri_entries.items():
            value, ok = self._parse_float_or_none(entry, nutri_field_labels[key])
            if not ok:
                return
            if value is not None:
                nutrition[key] = value

        previous_nutrition = get_ingredient_nutrition(self.existing_name) if self.editing else None
        if previous_nutrition and previous_nutrition.get("_ciqual") and all(
            nutrition.get(key) == previous_nutrition.get(key) for key in nutri_field_labels
        ):
            nutrition["_ciqual"] = previous_nutrition["_ciqual"]

        raw_price = self.price_entry.get().strip().replace(",", ".")
        price = None
        if raw_price:
            try:
                price = float(raw_price)
                if not math.isfinite(price) or price < 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror(t("common_error"), t("ingedit_error_invalid_price"))
                return

        allergens = [a for a, var in self.allergen_vars.items() if var.get()]

        if self.editing:
            old_name = self.existing_name
            if new_name.lower() != old_name.lower():
                ingredients = [new_name if n.lower() == old_name.lower() else n
                               for n in load_ingredients()]
                self.app.ingredient_names = save_ingredients(ingredients)
                rename_ingredient_everywhere(old_name, new_name)
                rename_ingredient_override(old_name, new_name)
                old_price = get_ingredient_price(old_name)
                if old_price:
                    set_ingredient_price(old_name, None, None)
                    set_ingredient_price(new_name, old_price["price"], old_price["unit"])
                self.app.refresh_recipes()
        else:
            ingredients = load_ingredients()
            ingredients.append(new_name)
            self.app.ingredient_names = save_ingredients(ingredients)

        set_ingredient_override(new_name, allergens=allergens, nutrition=nutrition)
        if raw_price:
            set_ingredient_price(new_name, price, resolve_unit_input(self.unit_combo.get(), PRICE_UNIT_OPTIONS))
        elif self.editing:
            set_ingredient_price(new_name, None, None)

        if self.manage_window is not None:
            self.manage_window.app.ingredient_names = self.app.ingredient_names
            self.manage_window._populate()

        messagebox.showinfo(t("allrecipes_list_saved_title"), t("ingedit_saved_message", name=new_name))
        self.destroy()

    def delete_ingredient(self):
        name = self.existing_name
        usage = count_ingredient_usage(name)
        message = t("manageing_delete_confirm_message", name=translate_ingredient_name(name))
        if usage:
            message += t("manageing_delete_usage_warning", count=usage)
        if not ask_yes_no(t("common_confirm"), message):
            return
        ingredients = [n for n in load_ingredients() if n.lower() != name.lower()]
        self.app.ingredient_names = save_ingredients(ingredients)
        set_ingredient_override(name, allergens=[], nutrition={})
        set_ingredient_price(name, None, None)
        if self.manage_window is not None:
            self.manage_window.app.ingredient_names = self.app.ingredient_names
            self.manage_window._populate()
        self.destroy()


class IngredientSpellCheckWindow(tk.Toplevel):
    """Détecte les paires d'ingrédients qui se ressemblent fortement (90 % de
    similarité ou plus — pluriels non fusionnés, fautes de frappe) et propose
    de les fusionner, une par une ou plusieurs à la fois."""

    SIMILARITY_THRESHOLD = 0.90

    def __init__(self, app, manage_window=None):
        super().__init__(app)
        self.app = app
        self.manage_window = manage_window
        self.title(t("spellcheck_title"))
        fit_window_to_workarea(self, gs(580), gs(560), margin=14)
        self.grab_set()

        ttk.Label(
            self,
            text=t("spellcheck_heading"),
            font=("Segoe UI", sf(11), "bold"), justify="center"
        ).pack(pady=10)
        ttk.Label(
            self,
            text=t("spellcheck_multi_select_hint"),
            font=("Segoe UI", sf(8)), foreground=COLOR_TEXT_MUTED, justify="center"
        ).pack(pady=(0, 5))

        list_frame = ttk.Frame(self)
        list_frame.pack(padx=15, pady=5, fill="both", expand=True)
        self.listbox = tk.Listbox(list_frame, width=64, height=16, selectmode="extended", font=("Segoe UI", sf(9)))
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scrollbar.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.pairs = []
        self._scan()

        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text=t("spellcheck_merge_button"),
                   command=self.merge_selected).grid(row=0, column=0, padx=5)
        ttk.Button(btn_frame, text=t("spellcheck_not_duplicate_button"),
                   command=self.dismiss_selected).grid(row=0, column=1, padx=5)
        ttk.Button(btn_frame, text=t("spellcheck_rerun_button"),
                   command=self._scan).grid(row=0, column=2, padx=5)

        ttk.Label(
            self,
            text=t("spellcheck_footer_hint"),
            font=("Segoe UI", sf(8)), foreground=COLOR_TEXT_MUTED, justify="center"
        ).pack(pady=(0, 10))

    def _scan(self):
        self.listbox.delete(0, tk.END)
        all_pairs = find_similar_ingredient_pairs(
            self.app.ingredient_names, threshold=self.SIMILARITY_THRESHOLD
        )
        dismissed = load_dismissed_pairs()
        self.pairs = [
            (name_a, name_b, ratio) for (name_a, name_b, ratio) in all_pairs
            if not is_pair_dismissed(name_a, name_b, dismissed)
        ]
        if not self.pairs:
            self.listbox.insert(tk.END, t("spellcheck_none_found"))
            return
        for name_a, name_b, ratio in self.pairs:
            self.listbox.insert(tk.END, t("spellcheck_pair_line", a=name_a, b=name_b, percent=int(ratio * 100)))

    def dismiss_selected(self):
        sel = self.listbox.curselection()
        if not sel or not self.pairs:
            messagebox.showinfo(t("common_info"), t("spellcheck_select_pair_first"))
            return
        selected_pairs = [self.pairs[i] for i in sel]
        for name_a, name_b, ratio in selected_pairs:
            add_dismissed_pair(name_a, name_b)
        self._scan()
        messagebox.showinfo(
            t("common_info"),
            t("spellcheck_dismissed_message", count=len(selected_pairs))
        )

    def _merge_pair(self, keep, remove):
        ingredients = [n for n in load_ingredients() if n.lower() != remove.lower()]
        self.app.ingredient_names = save_ingredients(ingredients)
        rename_ingredient_everywhere(remove, keep)

    def merge_selected(self):
        sel = self.listbox.curselection()
        if not sel or not self.pairs:
            messagebox.showinfo(t("common_info"), t("spellcheck_select_pair_first"))
            return
        selected_pairs = [self.pairs[i] for i in sel]

        if len(selected_pairs) == 1:
            name_a, name_b, ratio = selected_pairs[0]
            choice = messagebox.askyesnocancel(
                t("spellcheck_merge_dialog_title"),
                t("spellcheck_merge_dialog_message", a=name_a, b=name_b)
            )
            if choice is None:
                return
            keep, remove = (name_a, name_b) if choice else (name_b, name_a)
            self._merge_pair(keep, remove)
            self.app.refresh_recipes()
            if self.manage_window is not None:
                self.manage_window.app.ingredient_names = self.app.ingredient_names
                self.manage_window._populate()
            messagebox.showinfo(t("spellcheck_merged_title"), t("spellcheck_merged_one_message", removed=remove, kept=keep))
        else:
            if not ask_yes_no(
                t("common_confirm"),
                t("spellcheck_merge_multi_confirm", count=len(selected_pairs))
            ):
                return
            for name_a, name_b, ratio in selected_pairs:
                usage_a = count_ingredient_usage(name_a)
                usage_b = count_ingredient_usage(name_b)
                if usage_a > usage_b:
                    keep, remove = name_a, name_b
                elif usage_b > usage_a:
                    keep, remove = name_b, name_a
                else:
                    keep, remove = sorted([name_a, name_b], key=ingredient_sort_key)
                self._merge_pair(keep, remove)
            self.app.refresh_recipes()
            if self.manage_window is not None:
                self.manage_window.app.ingredient_names = self.app.ingredient_names
                self.manage_window._populate()
            messagebox.showinfo(t("spellcheck_merged_title"), t("spellcheck_merged_multi_message", count=len(selected_pairs)))

        self._scan()



def _finite_number(value, *, minimum=None, allow_none=False, field="number"):
    if value is None and allow_none:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"invalid_{field}")
    if not math.isfinite(number) or (minimum is not None and number < minimum):
        raise ValueError(f"invalid_{field}")
    return number


def validate_ingredients_list_payload(data):
    if not isinstance(data, list):
        raise ValueError("invalid_ingredients")
    out, seen = [], set()
    for value in data:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("invalid_ingredient_name")
        name = value.strip()
        key = ingredient_sort_key(name)
        if key not in seen:
            seen.add(key); out.append(name)
    return out


def validate_pantry_payload(data):
    if not isinstance(data, dict):
        raise ValueError("invalid_pantry")
    out = {}
    for raw_key, raw in data.items():
        if not isinstance(raw, dict):
            raise ValueError("invalid_pantry_entry")
        name = str(raw.get("name") or raw_key).strip()
        if not name:
            raise ValueError("invalid_pantry_name")
        quantity = _finite_number(raw.get("quantity", 0), minimum=0, field="pantry_quantity")
        threshold = raw.get("threshold")
        if threshold in ("", None): threshold = None
        else: threshold = _finite_number(threshold, minimum=0, field="pantry_threshold")
        entry = copy.deepcopy(raw)
        entry.update({"name": name, "quantity": quantity, "unit": str(raw.get("unit") or "").strip(), "threshold": threshold})
        out[ingredient_sort_key(name)] = entry
    return out


def validate_prices_payload(data):
    if not isinstance(data, dict):
        raise ValueError("invalid_prices")
    out = {}
    for raw_key, raw in data.items():
        if not isinstance(raw, dict):
            raise ValueError("invalid_price_entry")
        name = str(raw.get("name") or raw_key).strip()
        if not name: raise ValueError("invalid_price_name")
        price = _finite_number(raw.get("price"), minimum=0, field="price")
        unit = str(raw.get("unit") or "").strip()
        if not unit: raise ValueError("invalid_price_unit")
        out[ingredient_sort_key(name)] = {"name": name, "price": price, "unit": unit}
    return out


def validate_saved_lists_payload(data):
    if not isinstance(data, list): raise ValueError("invalid_saved_shopping_lists")
    out=[]
    for record in data:
        if not isinstance(record, dict) or not str(record.get("name") or "").strip():
            raise ValueError("invalid_saved_list")
        copy_record=copy.deepcopy(record); items=[]
        for item in record.get("items", []) or []:
            if not isinstance(item, dict) or not str(item.get("name") or "").strip(): raise ValueError("invalid_saved_list_item")
            item=copy.deepcopy(item)
            raw_quantity = item["quantity"] if "quantity" in item else 0
            item["quantity"] = parse_optional_positive_number(raw_quantity, allow_zero=True)
            items.append(item)
        copy_record["items"]=items; out.append(copy_record)
    return out


def validate_plan_payload(data, recipes=None):
    if not isinstance(data, dict): raise ValueError("invalid_weekly_plan")
    out=copy.deepcopy(data)
    for day, slots in list(out.items()):
        if slots in (None, {}): continue
        if not isinstance(slots, dict): raise ValueError("invalid_plan_day")
        for slot, ref in list(slots.items()):
            if not isinstance(ref, dict): raise ValueError("invalid_plan_slot")
            ref["persons"]=_finite_number(ref.get("persons",1),minimum=1e-12,field="plan_persons")
            if recipes is not None: slots[slot]=enrich_recipe_reference(ref,recipes)
    return out


def validate_menus_payload(data, recipes=None):
    if not isinstance(data, list): raise ValueError("invalid_menus")
    out=[]
    for menu in data:
        if not isinstance(menu, dict) or not str(menu.get("name") or "").strip(): raise ValueError("invalid_menu")
        copy_menu=copy.deepcopy(menu); items=[]
        for item in menu.get("items",[]) or []:
            if not isinstance(item,dict): raise ValueError("invalid_menu_item")
            item=copy.deepcopy(item); item["persons"]=_finite_number(item.get("persons",1),minimum=1e-12,field="menu_persons")
            if recipes is not None: item=enrich_recipe_reference(item,recipes)
            items.append(item)
        copy_menu["items"]=items; out.append(copy_menu)
    return out


def validate_recent_payload(data):
    if not isinstance(data,list): raise ValueError("invalid_recent_views")
    out=[]
    for ref in data:
        if isinstance(ref,str) and ref.strip(): out.append(ref.strip())
        elif isinstance(ref,dict): out.append({k:v for k,v in ref.items() if k in ("recipe_id","recipe_name") and isinstance(v,str) and v.strip()})
        else: raise ValueError("invalid_recent_view")
    return out


def validate_trash_payload(data):
    if not isinstance(data,list): raise ValueError("invalid_trash")
    out=[]
    for entry in data:
        if not isinstance(entry,dict) or not isinstance(entry.get("recipe"),dict): raise ValueError("invalid_trash_entry")
        item=copy.deepcopy(entry); item["recipe"]=validate_recipes_payload([item["recipe"]],assign_ids=True)[0]; out.append(item)
    return out


def validate_history_payload(data, recipes=None):
    if not isinstance(data,list): raise ValueError("invalid_weekly_plan_history")
    out=[]
    for entry in data:
        if not isinstance(entry,dict): raise ValueError("invalid_history_entry")
        item=copy.deepcopy(entry)
        plan=item.get("plan", item.get("data", {}))
        if plan is not None:
            valid=validate_plan_payload(plan,recipes)
            if "plan" in item: item["plan"]=valid
            elif "data" in item: item["data"]=valid
        out.append(item)
    return out


def validate_templates_payload(data, recipes=None):
    if not isinstance(data,dict): raise ValueError("invalid_weekly_plan_templates")
    return {str(name): validate_plan_payload(plan,recipes) for name,plan in data.items() if str(name).strip()}


def validate_backup_payloads(parsed):
    """Validation profonde commune avant toute restauration complète."""
    recipes = validate_recipes_payload(parsed.get("recipes.json", []), assign_ids=True) if "recipes.json" in parsed else load_recipes()
    if "recipes.json" in parsed: parsed["recipes.json"] = recipes
    if "ingredients.json" in parsed: parsed["ingredients.json"] = validate_ingredients_list_payload(parsed["ingredients.json"])
    if "pantry.json" in parsed: parsed["pantry.json"] = validate_pantry_payload(parsed["pantry.json"])
    if "ingredient_prices.json" in parsed: parsed["ingredient_prices.json"] = validate_prices_payload(parsed["ingredient_prices.json"])
    if "saved_shopping_lists.json" in parsed: parsed["saved_shopping_lists.json"] = validate_saved_lists_payload(parsed["saved_shopping_lists.json"])
    if "weekly_plan.json" in parsed: parsed["weekly_plan.json"] = validate_plan_payload(parsed["weekly_plan.json"], recipes)
    if "weekly_plan_history.json" in parsed: parsed["weekly_plan_history.json"] = validate_history_payload(parsed["weekly_plan_history.json"], recipes)
    if "weekly_plan_templates.json" in parsed: parsed["weekly_plan_templates.json"] = validate_templates_payload(parsed["weekly_plan_templates.json"], recipes)
    if "menus.json" in parsed: parsed["menus.json"] = validate_menus_payload(parsed["menus.json"], recipes)
    if "recent_views.json" in parsed: parsed["recent_views.json"] = validate_recent_payload(parsed["recent_views.json"])
    if "trash.json" in parsed: parsed["trash.json"] = validate_trash_payload(parsed["trash.json"])
    if "settings.json" in parsed and not isinstance(parsed["settings.json"],dict): raise ValueError("invalid_settings")
    if "ingredient_custom_data.json" in parsed and not isinstance(parsed["ingredient_custom_data.json"],dict): raise ValueError("invalid_overrides")
    return parsed

# ---------------------------------------------------------------------------
# Format de sauvegarde partagé avec l'application mobile — recettes (avec
# leurs photos), ingrédients connus, garde-manger et personnalisations.
# Utilise les mêmes noms de fichiers que la sauvegarde complète existante
# (voir plus bas), mais se limite à ce sous-ensemble : le planning
# hebdomadaire, les menus et les listes de courses enregistrées ne sont pas
# encore inclus dans ce format — des différences de conception réelles entre
# les deux applications (le planning Windows peut contenir plusieurs créneaux par jour ;
# par nom de recette ; application mobile : trois créneaux par jour
# référencés par identifiant) demanderaient une réflexion dédiée avant
# d'être unifiées correctement, plutôt qu'une correspondance approximative
# risquant de mélanger des plannings incohérents.
# ---------------------------------------------------------------------------

def _normalize_shared_override(record):
    """Convertit une surcharge ingrédient vers le format partagé canonique."""
    if not isinstance(record, dict):
        record = {}
    out = copy.deepcopy(record)
    out.pop("name", None)
    # Le format partagé utilise "substitutions". Les anciennes sauvegardes
    # mobiles pouvaient employer "substitutes".
    if "substitutions" not in out and "substitutes" in out:
        out["substitutions"] = out.pop("substitutes")
    else:
        out.pop("substitutes", None)
    # Le prix voyage désormais dans ingredient_prices.json, qui correspond
    # directement au stockage natif de l'application Windows.
    out.pop("price", None)
    return out


def build_shared_backup_zip(zip_path):
    """Sauvegarde au format partagé avec l'application mobile, de façon atomique."""
    recipes = load_recipes()
    referenced_images = set()
    for r in recipes:
        referenced_images.update(get_all_recipe_image_refs(r))

    overrides = load_ingredient_overrides()
    shared_overrides = {
        str(name).strip().lower(): _normalize_shared_override(record)
        for name, record in overrides.items()
        if str(name).strip()
    }

    tmp_path = str(zip_path) + ".tmp"
    try:
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("recipes.json", json.dumps(recipes, ensure_ascii=False, indent=2, allow_nan=False))
            zf.writestr("ingredients.json", json.dumps(load_ingredients(), ensure_ascii=False, indent=2, allow_nan=False))
            zf.writestr("pantry.json", json.dumps(load_pantry(), ensure_ascii=False, indent=2, allow_nan=False))
            zf.writestr("ingredient_custom_data.json", json.dumps(shared_overrides, ensure_ascii=False, indent=2, allow_nan=False))
            zf.writestr("ingredient_prices.json", json.dumps(load_ingredient_prices(), ensure_ascii=False, indent=2, allow_nan=False))
            if os.path.isdir(IMAGES_DIR):
                for fname in referenced_images:
                    full = os.path.join(IMAGES_DIR, fname)
                    if os.path.isfile(full):
                        zf.write(full, arcname=f"images/{fname}")
        with zipfile.ZipFile(tmp_path, "r") as check:
            _validate_backup_zip(check)
        os.replace(tmp_path, zip_path)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def prepare_recipe_merge(imported, existing):
    by_id = {r.get('id'): r for r in existing}
    remapped = {}
    for recipe in imported:
        rid = recipe.get('id')
        if rid not in by_id or by_id[rid] == recipe:
            continue
        digest = hashlib.sha256(json.dumps(recipe, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()
        replacement = uuid.uuid5(uuid.NAMESPACE_URL, 'mesrecettes-conflict:' + digest).hex
        remapped[rid] = replacement
        recipe['id'] = replacement
        recipe['name'] += t('import_conflict_suffix')
        # If that deterministic copy was edited locally, retain it too.
        if replacement in by_id and by_id[replacement] != recipe:
            recipe['id'] = uuid.uuid4().hex
            remapped[rid] = recipe['id']
    return remapped


def remap_imported_recipe_references(value, mapping):
    if isinstance(value, dict):
        if value.get('recipe_id') in mapping:
            value['recipe_id'] = mapping[value['recipe_id']]
        for child in value.values():
            remap_imported_recipe_references(child, mapping)
    elif isinstance(value, list):
        for child in value:
            remap_imported_recipe_references(child, mapping)


def restore_from_shared_zip(zip_path, merge):
    """Restaure une archive partagée Windows/mobile.

    Les JSON sont tous lus et validés avant la première suppression locale.
    En fusion, une photo existante portant le même nom et le même contenu est
    réutilisée au lieu d'être copiée sous un nouveau nom.
    """
    if os.path.getsize(zip_path) > MAX_BACKUP_FILE_SIZE:
        raise ValueError("file_too_large")

    with zipfile.ZipFile(zip_path, "r") as zf:
        _validate_backup_zip(zf)
        names = set(zf.namelist())

        def read_json(name, default):
            if name not in names:
                return copy.deepcopy(default)
            return json.loads(zf.read(name).decode("utf-8"))

        # ---- 1. Lecture et validation complètes avant toute modification ----
        imported_recipes = validate_recipes_payload(read_json("recipes.json", []), assign_ids=True)
        if merge:
            prepare_recipe_merge(imported_recipes, load_recipes())

        imported_ingredients = validate_ingredients_list_payload(read_json("ingredients.json", []))

        imported_pantry = validate_pantry_payload(read_json("pantry.json", {}))

        imported_overrides = read_json("ingredient_custom_data.json", {})
        if not isinstance(imported_overrides, dict):
            raise ValueError("invalid_overrides")

        normalized_overrides = {}
        legacy_prices = {}
        for raw_name, raw_record in imported_overrides.items():
            key = str(raw_name).strip().lower()
            if not key:
                continue
            record = copy.deepcopy(raw_record) if isinstance(raw_record, dict) else {}
            if "substitutions" not in record and "substitutes" in record:
                record["substitutions"] = record.pop("substitutes")
            else:
                record.pop("substitutes", None)

            # Compatibilité avec les archives mobiles v196 et antérieures :
            # le prix était intégré à ingredient_custom_data.json.
            price = record.pop("price", None)
            if isinstance(price, dict):
                amount = price.get("amount")
                unit = price.get("unit")
                if amount is not None and unit:
                    legacy_prices[key] = {
                        "name": record.get("name") or raw_name,
                        "price": amount,
                        "unit": unit,
                    }
            record.pop("name", None)
            normalized_overrides[key] = record

        imported_prices = read_json("ingredient_prices.json", {})
        for key, value in legacy_prices.items():
            imported_prices.setdefault(key, value)
        imported_prices = validate_prices_payload(imported_prices)

        image_payloads = {}
        for entry in names:
            if entry.startswith("images/") and not entry.endswith("/"):
                rel = entry[len("images/"):]
                fname = safe_image_filename(rel)
                if fname and rel == fname:
                    image_payloads[fname] = zf.read(entry)
                else:
                    raise ValueError("unsafe_image_name")

        # ---- 2. Prépare la correspondance des noms de photos ----
        os.makedirs(IMAGES_DIR, exist_ok=True)
        rename_map = {}
        for old_fname, payload in image_payloads.items():
            dest_path = os.path.join(IMAGES_DIR, old_fname)
            if merge and os.path.isfile(dest_path):
                try:
                    with open(dest_path, "rb") as existing_img:
                        identical = existing_img.read() == payload
                except OSError:
                    identical = False
                if identical:
                    new_fname = old_fname
                else:
                    ext = os.path.splitext(old_fname)[1]
                    new_fname = f"{uuid.uuid4().hex}{ext}"
            else:
                new_fname = old_fname
            rename_map[old_fname] = new_fname

        for recipe in imported_recipes:
            remap_recipe_image_refs(recipe, rename_map)


    def _apply_shared_changes():
        # ---- 3. Applique la restauration seulement après validation ----
        if not merge and os.path.isdir(IMAGES_DIR):
            keep = set(rename_map.values())
            for fname in os.listdir(IMAGES_DIR):
                full = os.path.join(IMAGES_DIR, fname)
                if os.path.isfile(full) and fname not in keep:
                    os.remove(full)

        for old_fname, payload in image_payloads.items():
            new_fname = rename_map[old_fname]
            dest_path = os.path.join(IMAGES_DIR, new_fname)
            if os.path.isfile(dest_path):
                try:
                    with open(dest_path, "rb") as existing_img:
                        if existing_img.read() == payload:
                            continue
                except OSError:
                    pass
            with open(dest_path, "wb") as out:
                out.write(payload)

        if "recipes.json" in names:
            if merge:
                existing_by_id = {
                    recipe.get("id"): recipe
                    for recipe in load_recipes()
                    if recipe.get("id")
                }
                for recipe in imported_recipes:
                    existing_by_id[recipe["id"]] = recipe
                save_recipes(list(existing_by_id.values()))
            else:
                save_recipes(imported_recipes)

        if "ingredients.json" in names:
            if merge:
                existing = load_ingredients()
                existing_lower = {name.lower() for name in existing}
                for name in imported_ingredients:
                    if name.lower() not in existing_lower:
                        existing.append(name)
                        existing_lower.add(name.lower())
                save_ingredients(sorted(existing, key=ingredient_sort_key))
            else:
                save_ingredients(sorted(imported_ingredients, key=ingredient_sort_key))

        if "pantry.json" in names:
            if merge:
                existing = load_pantry()
                existing.update(imported_pantry)
                save_pantry(existing)
            else:
                save_pantry(imported_pantry)

        if "ingredient_custom_data.json" in names:
            if merge:
                existing = load_ingredient_overrides()
                existing.update(normalized_overrides)
                save_ingredient_overrides(existing)
            else:
                save_ingredient_overrides(normalized_overrides)

        if "ingredient_prices.json" in names or legacy_prices:
            if merge:
                existing = load_ingredient_prices()
                existing.update(imported_prices)
                save_ingredient_prices(existing)
            else:
                save_ingredient_prices(imported_prices)


    snapshot = _snapshot_user_data_for_restore()
    try:
        _apply_shared_changes()
    except Exception:
        _rollback_user_data(snapshot)
        raise
    finally:
        shutil.rmtree(snapshot, ignore_errors=True)

def build_full_backup_zip(path, cancel_event=None, progress=None):
    """Construit atomiquement une archive ZIP complète des données utilisateur."""
    tmp_path = str(path) + ".tmp"
    try:
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for filename in USER_DATA_FILES:
                _check_cancelled(cancel_event)
                filepath = os.path.join(DATA_DIR, filename)
                if os.path.exists(filepath):
                    zf.write(filepath, arcname=filename)
            if os.path.isdir(IMAGES_DIR):
                for fname in os.listdir(IMAGES_DIR):
                    _check_cancelled(cancel_event)
                    full = os.path.join(IMAGES_DIR, fname)
                    if os.path.isfile(full):
                        zf.write(full, arcname=f"images/{fname}")
            if progress:
                progress()
        _check_cancelled(cancel_event)
        with zipfile.ZipFile(tmp_path, "r") as check:
            _validate_backup_zip(check, max_entry=FULL_BACKUP_MAX_ENTRY_SIZE,
                                 max_total=FULL_BACKUP_MAX_UNCOMPRESSED_SIZE)
        if os.path.getsize(tmp_path) > FULL_BACKUP_MAX_FILE_SIZE:
            raise ValueError("full_backup_too_large")
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def _snapshot_user_data_for_restore():
    """Copie les données actuelles avant restauration pour permettre un rollback complet."""
    snapshot = tempfile.mkdtemp(prefix="mesrecettes_restore_")
    for filename in USER_DATA_FILES:
        src = os.path.join(DATA_DIR, filename)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(snapshot, filename))
    if os.path.isdir(IMAGES_DIR):
        shutil.copytree(IMAGES_DIR, os.path.join(snapshot, "images"), dirs_exist_ok=True)
    return snapshot


def _rollback_user_data(snapshot):
    # Efface seulement les fichiers gérés par l'application, puis restaure l'instantané.
    for filename in USER_DATA_FILES:
        path = os.path.join(DATA_DIR, filename)
        try:
            if os.path.isfile(path): os.remove(path)
        except OSError: pass
    if os.path.isdir(IMAGES_DIR):
        shutil.rmtree(IMAGES_DIR, ignore_errors=True)
    os.makedirs(IMAGES_DIR, exist_ok=True)
    for filename in USER_DATA_FILES:
        src = os.path.join(snapshot, filename)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(DATA_DIR, filename))
    imgsrc = os.path.join(snapshot, "images")
    if os.path.isdir(imgsrc):
        shutil.copytree(imgsrc, IMAGES_DIR, dirs_exist_ok=True)


def restore_from_zip(path, merge, cancel_event=None, progress=None):
    """Restaure une sauvegarde complète après validation intégrale.

    Aucun fichier local n'est supprimé ou remplacé avant que tous les JSON
    et toutes les images de l'archive aient été lus avec succès. En mode
    fusion, les recettes sont fusionnées par identifiant stable et les
    images identiques sont réutilisées au lieu d'être dupliquées.
    """
    if os.path.getsize(path) > FULL_BACKUP_MAX_FILE_SIZE:
        raise ValueError("file_too_large")

    expected = {
        "recipes.json": list,
        "ingredients.json": list,
        "ingredient_custom_data.json": dict,
        "ingredient_prices.json": dict,
        "ingredient_dismissed_pairs.json": list,
        "weekly_plan.json": dict,
        "weekly_plan_history.json": list,
        "weekly_plan_templates.json": dict,
        "menus.json": list,
        "saved_shopping_lists.json": list,
        "pantry.json": dict,
        "trash.json": list,
        "recent_views.json": list,
        "settings.json": dict,
    }

    with zipfile.ZipFile(path, "r") as zf:
        _check_cancelled(cancel_event)
        _validate_backup_zip(
            zf, max_entry=FULL_BACKUP_MAX_ENTRY_SIZE,
            max_total=FULL_BACKUP_MAX_UNCOMPRESSED_SIZE, verify_crc=False
        )
        names = set(zf.namelist())
        parsed = {}
        for filename, expected_type in expected.items():
            _check_cancelled(cancel_event)
            if filename not in names:
                continue
            data = json.loads(zf.read(filename).decode("utf-8"))
            if not isinstance(data, expected_type):
                raise ValueError(f"invalid_{filename}")
            parsed[filename] = data

        parsed = validate_backup_payloads(parsed)
        imported_recipes = parsed.get("recipes.json", [])
        if merge:
            mapping = prepare_recipe_merge(imported_recipes, load_recipes())
            for filename, value in parsed.items():
                if filename != "recipes.json":
                    remap_imported_recipe_references(value, mapping)
        imported_ingredients = parsed.get("ingredients.json", [])

        image_entries = {}
        for entry in names:
            if entry.startswith("images/") and not entry.endswith("/"):
                rel = entry[len("images/"):]
                fname = safe_image_filename(rel)
                if not fname or rel != fname:
                    raise ValueError("unsafe_image_name")
                image_entries[fname] = entry

    # Les images sont déposées sur disque une par une : la RAM ne dépend plus
    # de la taille totale de la photothèque.
    image_stage = tempfile.mkdtemp(prefix="mesrecettes_restore_images_")
    image_payloads = {}
    try:
        with zipfile.ZipFile(path, "r") as zf:
            for index, (fname, entry) in enumerate(image_entries.items()):
                _check_cancelled(cancel_event)
                staged = os.path.join(image_stage, str(index))
                with zf.open(entry, "r") as source, open(staged, "wb") as target:
                    shutil.copyfileobj(source, target, length=1024 * 1024)
                image_payloads[fname] = staged
                if progress:
                    progress()
    except Exception:
        shutil.rmtree(image_stage, ignore_errors=True)
        raise

    def _apply_restore_changes():
        if not merge:
            # « Tout remplacer » remet réellement à zéro l'ensemble des fichiers
            # utilisateur gérés, y compris ceux absents de l'archive.
            for _filename in USER_DATA_FILES:
                _path = os.path.join(DATA_DIR, _filename)
                if os.path.isfile(_path):
                    os.remove(_path)
        # Tout est valide à partir d'ici : préparation des noms d'images.
        os.makedirs(IMAGES_DIR, exist_ok=True)
        rename_map = {}
        for old_fname, staged_path in image_payloads.items():
            _check_cancelled(cancel_event)
            dest = os.path.join(IMAGES_DIR, old_fname)
            if merge and os.path.isfile(dest):
                try:
                    identical = filecmp.cmp(dest, staged_path, shallow=False)
                except OSError:
                    identical = False
                if identical:
                    new_fname = old_fname
                else:
                    ext = os.path.splitext(old_fname)[1]
                    new_fname = f"{uuid.uuid4().hex}{ext}"
            else:
                new_fname = old_fname
            rename_map[old_fname] = new_fname

        for recipe in imported_recipes:
            remap_recipe_image_refs(recipe, rename_map)

        if not merge:
            keep = set(rename_map.values())
            if os.path.isdir(IMAGES_DIR):
                for fname in os.listdir(IMAGES_DIR):
                    full = os.path.join(IMAGES_DIR, fname)
                    if os.path.isfile(full) and fname not in keep:
                        os.remove(full)

        for old_fname, staged_path in image_payloads.items():
            _check_cancelled(cancel_event)
            dest = os.path.join(IMAGES_DIR, rename_map[old_fname])
            if os.path.isfile(dest):
                try:
                    if filecmp.cmp(dest, staged_path, shallow=False):
                        continue
                except OSError:
                    pass
            tmp = dest + ".tmp"
            with open(staged_path, "rb") as source, open(tmp, "wb") as target:
                shutil.copyfileobj(source, target, length=1024 * 1024)
                target.flush()
                os.fsync(target.fileno())
            os.replace(tmp, dest)

        if "recipes.json" in parsed:
            if merge:
                by_id = {r.get("id"): r for r in load_recipes() if isinstance(r, dict) and r.get("id")}
                unnamed = [r for r in load_recipes() if not (isinstance(r, dict) and r.get("id"))]
                for r in imported_recipes:
                    by_id[r["id"]] = r
                save_recipes(unnamed + list(by_id.values()))
            else:
                save_recipes(imported_recipes)

        if "ingredients.json" in parsed:
            save_ingredients(load_ingredients() + imported_ingredients if merge else imported_ingredients)

        dict_merge_files = [
            "ingredient_custom_data.json", "ingredient_prices.json", "pantry.json",
            "weekly_plan_templates.json",
        ]
        named_list_merge_files = {
            "saved_shopping_lists.json": "name",
            "menus.json": "name",
            "weekly_plan_history.json": "week_start",
        }
        simple_list_merge_files = ["trash.json", "recent_views.json"]
        replace_only_files = ["settings.json", "weekly_plan.json"]

        def read_existing(filename, expected_type):
            filepath = os.path.join(DATA_DIR, filename)
            if not os.path.exists(filepath):
                return expected_type()
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data if isinstance(data, expected_type) else expected_type()
            except Exception as exc:
                log_internal_error("restore_read_existing", exc)
                return expected_type()

        for filename in dict_merge_files:
            if filename not in parsed:
                continue
            data = copy.deepcopy(parsed[filename])
            if merge:
                existing = read_existing(filename, dict)
                existing.update(data)
                data = existing
            _atomic_write_json(os.path.join(DATA_DIR, filename), data)

        for filename, key_field in named_list_merge_files.items():
            if filename not in parsed:
                continue
            data = copy.deepcopy(parsed[filename])
            if merge:
                existing = read_existing(filename, list)
                keyed, no_key = {}, []
                for item in existing + data:
                    if isinstance(item, dict) and item.get(key_field) is not None:
                        keyed[item.get(key_field)] = item
                    else:
                        no_key.append(item)
                data = no_key + list(keyed.values())
            _atomic_write_json(os.path.join(DATA_DIR, filename), data)

        for filename in simple_list_merge_files:
            if filename not in parsed:
                continue
            data = copy.deepcopy(parsed[filename])
            if merge:
                combined = read_existing(filename, list) + data
                if filename == "recent_views.json":
                    deduped, seen = [], set()
                    for ref in combined:
                        if isinstance(ref, dict):
                            key = ref.get("recipe_id") or (ref.get("recipe_name") or "").casefold()
                        else:
                            key = str(ref).casefold()
                        if not key or key in seen:
                            continue
                        seen.add(key)
                        deduped.append(ref)
                    data = deduped[:RECENT_VIEWS_MAX]
                elif filename == "trash.json":
                    deduped, seen = [], set()
                    for entry in combined:
                        recipe = entry.get("recipe", {}) if isinstance(entry, dict) else {}
                        key = recipe.get("id") or (
                            recipe.get("name"), entry.get("deleted_at") if isinstance(entry, dict) else None
                        )
                        if key in seen:
                            continue
                        seen.add(key)
                        deduped.append(entry)
                    data = deduped
                else:
                    data = combined
            _atomic_write_json(os.path.join(DATA_DIR, filename), data)

        if "ingredient_dismissed_pairs.json" in parsed:
            imported_pairs = parsed["ingredient_dismissed_pairs.json"]
            pairs = {tuple(sorted(p)) for p in imported_pairs if isinstance(p, list) and len(p) == 2}
            if merge:
                pairs |= load_dismissed_pairs()
            save_dismissed_pairs(pairs)

        if not merge:
            for filename in replace_only_files:
                if filename in parsed:
                    _atomic_write_json(os.path.join(DATA_DIR, filename), parsed[filename])

    guarded_keys = set(_CORRUPTED_DATA_FILES)
    _ALLOW_CORRUPT_OVERWRITE.update(guarded_keys)
    snapshot = None
    restored = False
    try:
        snapshot = _snapshot_user_data_for_restore()
        _apply_restore_changes()
        restored = True
    except Exception:
        if snapshot:
            _rollback_user_data(snapshot)
        raise
    finally:
        if snapshot:
            shutil.rmtree(snapshot, ignore_errors=True)
        shutil.rmtree(image_stage, ignore_errors=True)
        _ALLOW_CORRUPT_OVERWRITE.difference_update(guarded_keys)
        if restored:
            _clear_corruption_guards()


# ---------------------------------------------------------------------------
# Paramètres de l'application (dossier de sauvegarde cloud, etc.)
# ---------------------------------------------------------------------------

def load_settings():
    return _read_user_json(SETTINGS_FILE, dict, {}, label="settings")


def save_settings(settings):
    if not isinstance(settings, dict):
        raise ValueError("settings must be a dict")
    settings = dict(settings)
    settings["data_schema_version"] = DATA_SCHEMA_VERSION
    _atomic_write_json(SETTINGS_FILE, settings)


def migrate_data_schema(recipes=None):
    """Applique les migrations de données idempotentes connues.

    Le schéma 2 formalise les IDs stables de recettes et les références
    planning/menu/récents introduites progressivement dans les versions 22/23.
    """
    settings = load_settings()
    try:
        current = int(settings.get("data_schema_version", 1) or 1)
    except (TypeError, ValueError):
        current = 1
    if current < 2:
        recipes = recipes if recipes is not None else load_recipes()
        # Ces chargeurs migrent déjà de façon transparente les anciennes
        # références par nom vers les références contenant recipe_id.
        load_weekly_plan()
        load_weekly_plan_history()
        load_weekly_plan_templates()
        load_menus()
        _load_recent_view_refs()
        get_daily_recipe(recipes) if recipes else None
        settings = load_settings()
        settings["data_schema_version"] = 2
        save_settings(settings)
    elif settings.get("data_schema_version") != DATA_SCHEMA_VERSION:
        settings["data_schema_version"] = DATA_SCHEMA_VERSION
        save_settings(settings)


def get_daily_recipe(recipes):
    """Retourne la recette du jour : la même toute la journée (mémorisée
    dans settings.json), renouvelée aléatoirement chaque nouveau jour, parmi
    toutes les recettes (pas seulement la liste d'envies)."""
    if not recipes:
        return None
    settings = load_settings()
    today = datetime.now().strftime("%Y-%m-%d")
    if settings.get("daily_recipe_date") == today:
        match = find_recipe_by_id(recipes, settings.get("daily_recipe_id"))
        if match is None:
            match = find_recipe_by_name(recipes, settings.get("daily_recipe_name"))
        if match is not None:
            # Migration transparente de l'ancien réglage basé uniquement sur le nom.
            settings["daily_recipe_id"] = match.get("id")
            settings["daily_recipe_name"] = match.get("name")
            save_settings(settings)
            return match
    chosen = random.choice(recipes)
    settings["daily_recipe_date"] = today
    settings["daily_recipe_id"] = chosen.get("id")
    settings["daily_recipe_name"] = chosen["name"]
    save_settings(settings)
    return chosen


def get_cloud_backup_folder():
    folder = load_settings().get("cloud_backup_folder") or ""
    return folder if folder and os.path.isdir(folder) else ""


def set_cloud_backup_folder(path):
    settings = load_settings()
    if path:
        settings["cloud_backup_folder"] = path
    else:
        settings.pop("cloud_backup_folder", None)
    save_settings(settings)


AUTO_BACKUP_RETENTION = 10  # nombre de sauvegardes automatiques conservées
AUTO_BACKUP_MIN_INTERVAL_HOURS = 24  # fréquence minimale entre deux sauvegardes auto
# Préfixe distinctif des fichiers de sauvegarde, pour ne jamais les confondre
# avec ceux d'un autre programme dans un même dossier (ex. cloud partagé).
AUTO_BACKUP_PREFIX = "sauvegarde_auto_mesrecettes_"


def list_auto_backups():
    """Retourne la liste des sauvegardes automatiques existantes
    (chemin complet), les plus récentes en premier."""
    if not os.path.isdir(BACKUPS_DIR):
        return []
    files = [
        os.path.join(BACKUPS_DIR, f) for f in os.listdir(BACKUPS_DIR)
        if f.startswith(AUTO_BACKUP_PREFIX) and f.endswith(".zip")
    ]
    files.sort(key=os.path.getmtime, reverse=True)
    return files


def create_auto_backup(cancel_event=None, progress=None):
    """Crée une nouvelle sauvegarde automatique horodatée, puis supprime les
    plus anciennes au-delà de AUTO_BACKUP_RETENTION. Si un dossier cloud est
    configuré (Google Drive, OneDrive, Dropbox...), une copie y est aussi
    déposée : le client cloud déjà installé sur le PC se charge ensuite de
    l'envoyer en ligne automatiquement."""
    os.makedirs(BACKUPS_DIR, exist_ok=True)
    filename = f"{AUTO_BACKUP_PREFIX}{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.zip"
    path = os.path.join(BACKUPS_DIR, filename)
    build_full_backup_zip(path, cancel_event=cancel_event, progress=progress)

    existing = list_auto_backups()
    for old_path in existing[AUTO_BACKUP_RETENTION:]:
        try:
            os.remove(old_path)
        except OSError:
            pass

    cloud_folder = get_cloud_backup_folder()
    if cloud_folder:
        try:
            cloud_path = os.path.join(cloud_folder, filename)
            shutil.copy2(path, cloud_path)
            cloud_backups = sorted(
                [os.path.join(cloud_folder, f) for f in os.listdir(cloud_folder)
                 if f.startswith(AUTO_BACKUP_PREFIX) and f.endswith(".zip")],
                key=os.path.getmtime, reverse=True
            )
            for old_cloud_path in cloud_backups[AUTO_BACKUP_RETENTION:]:
                try:
                    os.remove(old_cloud_path)
                except OSError:
                    pass
        except Exception as exc:
            log_internal_error("suppressed_exception", exc)  # un souci côté dossier cloud ne doit jamais faire échouer la sauvegarde locale

    return path


def migrate_old_backup_filenames():
    """Renomme les sauvegardes créées avant l'ajout du préfixe distinctif
    'mesrecettes' (ex. 'sauvegarde_auto_2026-01-01_120000.zip') vers le
    nouveau format, pour qu'elles restent reconnues par l'application au
    lieu de devenir invisibles."""
    if not os.path.isdir(BACKUPS_DIR):
        return
    old_pattern = re.compile(r"^sauvegarde_auto_(\d{4}-\d{2}-\d{2}_\d{6})\.zip$")
    for fname in os.listdir(BACKUPS_DIR):
        match = old_pattern.match(fname)
        if match:
            new_path = os.path.join(BACKUPS_DIR, f"{AUTO_BACKUP_PREFIX}{match.group(1)}.zip")
            if not os.path.exists(new_path):
                try:
                    os.rename(os.path.join(BACKUPS_DIR, fname), new_path)
                except OSError:
                    pass


def maybe_create_auto_backup():
    """Crée automatiquement une sauvegarde si aucune n'existe encore ou si la
    dernière date de plus de AUTO_BACKUP_MIN_INTERVAL_HOURS. Ne fait jamais
    planter l'application en cas de problème (disque plein, permissions...)."""
    try:
        migrate_old_backup_filenames()
        if get_corrupted_data_files():
            return  # ne jamais sauvegarder automatiquement des données suspectes
        has_file_data = any(
            os.path.isfile(os.path.join(DATA_DIR, filename))
            for filename in USER_DATA_FILES
        )
        has_images = os.path.isdir(IMAGES_DIR) and any(
            os.path.isfile(os.path.join(IMAGES_DIR, filename))
            for filename in os.listdir(IMAGES_DIR)
        )
        if not has_file_data and not has_images:
            return  # véritable premier lancement : aucune donnée utilisateur
        existing = list_auto_backups()
        if existing:
            last_mtime = os.path.getmtime(existing[0])
            age_hours = (datetime.now().timestamp() - last_mtime) / 3600
            if age_hours < AUTO_BACKUP_MIN_INTERVAL_HOURS:
                return
        create_auto_backup()
    except Exception as exc:
        log_internal_error("suppressed_exception", exc)


class ImportExportWindow(tk.Toplevel):
    """Fenêtre pour exporter ou importer l'ensemble des données (recettes,
    ingrédients et photos) sous forme d'une seule archive ZIP, et pour
    consulter/restaurer les sauvegardes automatiques."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title(t("importexport_title"))
        fit_window_to_workarea(self, gs(480), gs(940), margin=18)
        safe_minsize(self, gs(440), gs(500))
        self.resizable(True, True)
        self.grab_set()

        header_row = ttk.Frame(self)
        header_row.pack(fill="x", padx=18, pady=(12, 6))
        ttk.Label(header_row, text=t("importexport_heading"),
                  font=("Segoe UI", sf(13), "bold")).pack(side="left")
        ttk.Button(header_row, text=t("diagnostic_button"), style="Secondary.TButton",
                   command=lambda: DiagnosticWindow(self.app, self)).pack(side="right")

        ttk.Label(
            self,
            text=t("importexport_export_intro"),
            justify="center", font=("Segoe UI", sf(9))
        ).pack(pady=(0, 10))

        ttk.Button(self, text=t("importexport_export_button"),
                   width=42, command=self.export_data).pack(pady=6)

        ttk.Label(
            self,
            text=t("importexport_import_intro"),
            justify="center", font=("Segoe UI", sf(9))
        ).pack(pady=(10, 10))

        ttk.Button(self, text=t("importexport_import_button"),
                   width=42, command=self.import_data).pack(pady=6)

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=20, pady=15)

        ttk.Label(self, text=t("importexport_mobile_exchange_heading"),
                  font=("Segoe UI", sf(11), "bold")).pack(pady=(0, 6))
        ttk.Label(
            self, text=t("importexport_mobile_exchange_intro"),
            justify="center", font=("Segoe UI", sf(9)), wraplength=390
        ).pack(pady=(0, 10))
        qr_row = ttk.Frame(self)
        qr_row.pack(pady=(0, 6))
        ttk.Button(qr_row, text=t("importexport_mobile_qr_import"),
                   command=self.import_mobile_qr).pack(side="left", padx=4)
        ttk.Button(qr_row, text=t("importexport_mobile_qr_export"),
                   command=self.choose_recipe_for_qr).pack(side="left", padx=4)
        ttk.Label(self, text=t("importexport_shared_intro"),
                  justify="center", font=("Segoe UI", sf(8)), wraplength=390).pack(pady=(3, 8))
        ttk.Button(self, text=t("importexport_export_shared_button"),
                   width=42, command=self.export_shared_data).pack(pady=6)
        ttk.Button(self, text=t("importexport_import_shared_button"),
                   width=42, command=self.import_shared_data).pack(pady=6)

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=20, pady=15)

        ttk.Label(self, text=t("importexport_auto_backups_heading"), font=("Segoe UI", sf(12), "bold")).pack()
        ttk.Label(
            self,
            text=t("importexport_auto_backups_intro", hours=AUTO_BACKUP_MIN_INTERVAL_HOURS, retention=AUTO_BACKUP_RETENTION),
            justify="center", font=("Segoe UI", sf(9))
        ).pack(pady=(5, 10))

        list_frame = ttk.Frame(self)
        list_frame.pack(padx=15, fill="both", expand=True)
        self.backup_listbox = tk.Listbox(list_frame, height=8, font=("Segoe UI", sf(9)))
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.backup_listbox.yview)
        self.backup_listbox.configure(yscrollcommand=scrollbar.set)
        self.backup_listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self._populate_backups()

        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text=t("importexport_backup_now_button"),
                   command=self.backup_now).grid(row=0, column=0, padx=5)
        ttk.Button(btn_frame, text=t("importexport_restore_selected_button"),
                   command=self.restore_selected).grid(row=0, column=1, padx=5)

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=20, pady=15)

        ttk.Label(self, text=t("importexport_cloud_heading"),
                  font=("Segoe UI", sf(12), "bold")).pack()
        ttk.Label(
            self,
            text=t("importexport_cloud_intro"),
            justify="center", font=("Segoe UI", sf(9))
        ).pack(pady=(5, 8))

        self.cloud_folder_label = ttk.Label(self, text="", font=("Segoe UI", sf(9), "bold"),
                                             foreground="#266", wraplength=400, justify="center")
        self.cloud_folder_label.pack(pady=(0, 8))
        self._refresh_cloud_label()

        cloud_btn_frame = ttk.Frame(self)
        cloud_btn_frame.pack(pady=(0, 15))
        ttk.Button(cloud_btn_frame, text=t("importexport_choose_cloud_button"),
                   command=self.choose_cloud_folder).grid(row=0, column=0, padx=5)
        ttk.Button(cloud_btn_frame, text=t("importexport_disable_button"),
                   command=self.disable_cloud_backup).grid(row=0, column=1, padx=5)

        tk.Frame(self, height=SCROLL_BOTTOM_PADDING, background=COLOR_BG).pack(fill="x")

    def import_mobile_qr(self):
        self.destroy()
        self.app.after(50, self.app.open_import_from_qr)

    def choose_recipe_for_qr(self):
        self.destroy()
        if not self.app.recipes:
            messagebox.showinfo(t("common_info"), t("home_recent_empty_title"), parent=self.app)
            return
        # La fiche recette permet de choisir la recette puis d'afficher le QR.
        self.app.after(50, self.app.open_one_recipe)

    def _refresh_cloud_label(self):
        folder = get_cloud_backup_folder()
        if folder:
            self.cloud_folder_label.config(text=t("importexport_cloud_enabled", folder=folder))
        else:
            self.cloud_folder_label.config(text=t("importexport_cloud_not_configured"), foreground=COLOR_TEXT_MUTED)

    def choose_cloud_folder(self):
        folder = filedialog.askdirectory(
            title=t("importexport_choose_folder_title")
        )
        if not folder:
            return
        set_cloud_backup_folder(folder)
        self._refresh_cloud_label()
        if ask_yes_no(
            t("importexport_cloud_configured_title"),
            t("importexport_cloud_configured_message", folder=folder)
        ):
            self.backup_now()

    def disable_cloud_backup(self):
        if not get_cloud_backup_folder():
            return
        set_cloud_backup_folder(None)
        self._refresh_cloud_label()
        messagebox.showinfo(t("importexport_disabled_title"), t("importexport_disabled_message"))

    def _populate_backups(self):
        self.backup_listbox.delete(0, tk.END)
        self.backups = list_auto_backups()
        for path in self.backups:
            mtime = datetime.fromtimestamp(os.path.getmtime(path))
            size_kb = os.path.getsize(path) / 1024
            self.backup_listbox.insert(
                tk.END, t("importexport_backup_date_line", date=mtime.strftime('%d/%m/%Y à %H:%M'), size=f"{size_kb:.0f}")
            )
        if not self.backups:
            self.backup_listbox.insert(tk.END, t("importexport_no_backups"))

    def _run_background_task(self, task, on_success, failure_key):
        """Exécute une sauvegarde/restauration hors du thread Tkinter."""
        cancel_event = threading.Event()
        results = queue.Queue(maxsize=1)
        dialog = tk.Toplevel(self)
        dialog.title(t("backgroundtask_title"))
        dialog.transient(self)
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.protocol("WM_DELETE_WINDOW", lambda: cancel_event.set())
        ttk.Label(dialog, text=t("backgroundtask_running"), padding=(22, 16, 22, 8)).pack()
        bar = ttk.Progressbar(dialog, mode="indeterminate", length=320)
        bar.pack(padx=22, pady=8)
        bar.start(12)
        cancel_button = ttk.Button(
            dialog, text=t("backgroundtask_cancel"),
            command=lambda: (cancel_event.set(), cancel_button.configure(state="disabled"))
        )
        cancel_button.pack(pady=(4, 16))
        dialog.update_idletasks()
        x = self.winfo_rootx() + max(0, (self.winfo_width() - dialog.winfo_width()) // 2)
        y = self.winfo_rooty() + max(0, (self.winfo_height() - dialog.winfo_height()) // 2)
        dialog.geometry(f"+{x}+{y}")

        def worker():
            try:
                results.put((True, task(cancel_event)))
            except Exception as exc:
                results.put((False, exc))

        threading.Thread(target=worker, daemon=True).start()

        def poll():
            try:
                ok, value = results.get_nowait()
            except queue.Empty:
                if dialog.winfo_exists():
                    dialog.after(100, poll)
                return
            bar.stop()
            dialog.destroy()
            try:
                self.grab_set()
            except tk.TclError:
                pass
            if ok:
                on_success(value)
            elif not isinstance(value, OperationCancelled):
                log_internal_error("background_data_task", value)
                messagebox.showerror(
                    t("common_error"), t(failure_key, error=value), parent=self
                )

        dialog.after(100, poll)

    def backup_now(self):
        def done(_path):
            self._populate_backups()
            messagebox.showinfo(
                t("importexport_backup_created_title"),
                t("importexport_backup_created_message"), parent=self
            )
        self._run_background_task(
            lambda cancel: create_auto_backup(cancel_event=cancel),
            done, "importexport_backup_failed"
        )

    def restore_selected(self):
        sel = self.backup_listbox.curselection()
        if not sel or not self.backups:
            messagebox.showinfo(t("common_info"), t("importexport_select_backup_first"))
            return
        path = self.backups[sel[0]]
        if not confirm_backup_preview(self, path):
            return

        mode = messagebox.askyesnocancel(
            t("importexport_restore_mode_title"),
            t("importexport_restore_mode_message")
        )
        if mode is None:
            return
        def done(_value):
            self.app.refresh_recipes()
            self.app.refresh_ingredients()
            messagebox.showinfo(
                t("importexport_restore_done_title"),
                t("importexport_restore_done_message"), parent=self
            )
            self.destroy()
        self._run_background_task(
            lambda cancel: restore_from_zip(path, merge=bool(mode), cancel_event=cancel),
            done, "importexport_restore_failed"
        )

    def export_data(self):
        path = filedialog.asksaveasfilename(
            title=t("importexport_export_data_title"),
            defaultextension=".zip",
            filetypes=[("Archive ZIP", "*.zip")],
            initialfile="mes_recettes_export.zip"
        )
        if not path:
            return
        self._run_background_task(
            lambda cancel: build_full_backup_zip(path, cancel_event=cancel),
            lambda _value: messagebox.showinfo(
                t("common_export_success_title"),
                t("importexport_export_data_success", path=path), parent=self
            ),
            "common_export_failed"
        )

    def import_data(self):
        path = filedialog.askopenfilename(
            title=t("importexport_choose_archive_title"),
            filetypes=[("Archive ZIP", "*.zip")]
        )
        if not path:
            return
        if not confirm_backup_preview(self, path):
            return

        mode = messagebox.askyesnocancel(
            t("importexport_import_mode_title"),
            t("importexport_import_mode_message")
        )
        if mode is None:
            return

        def done(_value):
            self.app.refresh_recipes()
            self.app.refresh_ingredients()
            messagebox.showinfo(
                t("importexport_import_done_title"),
                t("importexport_import_done_message"), parent=self
            )
            self.destroy()
        self._run_background_task(
            lambda cancel: restore_from_zip(path, merge=bool(mode), cancel_event=cancel),
            done, "importexport_import_failed"
        )

    def export_shared_data(self):
        """Export au format compatible avec l'application mobile — voir
        build_shared_backup_zip."""
        path = filedialog.asksaveasfilename(
            title=t("importexport_export_shared_title"),
            defaultextension=".zip",
            filetypes=[("Archive ZIP", "*.zip")],
            initialfile="sauvegarde_partagee.zip"
        )
        if not path:
            return
        try:
            build_shared_backup_zip(path)
        except Exception as e:
            messagebox.showerror(t("common_error"), t("common_export_failed", error=e))
            return
        messagebox.showinfo(t("common_export_success_title"), t("importexport_export_data_success", path=path))

    def import_shared_data(self):
        """Import depuis le format compatible avec l'application mobile —
        voir restore_from_shared_zip.

        L'application mobile renomme parfois ce zip en ".txt" (Chromium
        refuse de partager un ".zip" via son Web Share API, mais accepte
        un ".txt" — le contenu reste un zip valide à l'octet près). Ce
        filtre affiche donc aussi les ".txt" ; zipfile lit le fichier par
        son contenu réel, pas par son extension, donc aucun renommage
        n'est nécessaire ici."""
        path = filedialog.askopenfilename(
            title=t("importexport_choose_archive_title"),
            filetypes=[
                (t("importexport_shared_archive_filetypes"), "*.zip *.txt"),
                ("Tous les fichiers", "*.*"),
            ]
        )
        if not path:
            return

        file_size = os.path.getsize(path)
        if file_size > MAX_BACKUP_FILE_SIZE:
            size_mb = MAX_BACKUP_FILE_SIZE // (1024 * 1024)
            messagebox.showerror(t("common_error"), t("importexport_file_too_large", size=size_mb))
            return
        if file_size > BACKUP_WARNING_SIZE:
            current_mb = round(file_size / (1024 * 1024))
            if not ask_yes_no(
                t("common_confirm"),
                t("importexport_large_file_warning", size=current_mb)
            ):
                return

        if not confirm_backup_preview(self, path):
            return
        mode = messagebox.askyesnocancel(
            t("importexport_import_mode_title"),
            t("importexport_import_mode_message")
        )
        if mode is None:
            return

        try:
            restore_from_shared_zip(path, merge=bool(mode))
        except ValueError as e:
            if str(e) == "file_too_large":
                size_mb = MAX_BACKUP_FILE_SIZE // (1024 * 1024)
                messagebox.showerror(t("common_error"), t("importexport_file_too_large", size=size_mb))
            else:
                messagebox.showerror(t("common_error"), t("importexport_import_failed", error=e))
            return
        except Exception as e:
            messagebox.showerror(t("common_error"), t("importexport_import_failed", error=e))
            return

        self.app.refresh_recipes()
        self.app.refresh_ingredients()
        messagebox.showinfo(t("importexport_import_done_title"), t("importexport_import_done_message"))
        self.destroy()


class DiagnosticWindow(tk.Toplevel):
    """Diagnostic lisible/copiable, sans nom de recette ni donnée personnelle."""
    def __init__(self, app, parent=None):
        super().__init__(parent or app)
        self.app = app
        self.title(t("diagnostic_title"))
        fit_window_to_workarea(self, gs(680), gs(560), margin=14)
        safe_minsize(self, gs(560), gs(460))
        self.resizable(True, True)
        self.grab_set()

        ttk.Label(self, text=t("diagnostic_heading"), style="Title.TLabel").pack(anchor="w", padx=18, pady=(16, 8))
        self.text = tk.Text(self, wrap="word", font=("Consolas", sf(9)), height=18)
        self.text.pack(fill="both", expand=True, padx=18, pady=(0, 10))
        self.report = self._build_report()
        self.text.insert("1.0", self.report)
        self.text.configure(state="disabled")

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=18, pady=(0, 16))
        ttk.Button(buttons, text=t("diagnostic_copy"), command=self.copy_report).pack(side="left")
        ttk.Button(buttons, text=t("diagnostic_open_data"), command=self.open_data_folder).pack(side="left", padx=8)
        ttk.Button(buttons, text=t("common_close"), command=self.destroy).pack(side="right")

    def _build_report(self):
        recipes = load_recipes()
        photos = 0
        try:
            photos = sum(1 for n in os.listdir(IMAGES_DIR) if os.path.isfile(os.path.join(IMAGES_DIR, n)))
        except OSError:
            pass
        total_size = 0
        for base, dirs, files in os.walk(DATA_DIR):
            for f in files:
                try: total_size += os.path.getsize(os.path.join(base, f))
                except OSError: pass
        if total_size >= 1024 * 1024:
            size_text = f"{total_size / (1024*1024):.1f} Mo"
        else:
            size_text = f"{total_size / 1024:.0f} Ko"
        backups = list_auto_backups()
        if backups:
            last_backup = datetime.fromtimestamp(os.path.getmtime(backups[0])).strftime("%d/%m/%Y %H:%M")
        else:
            last_backup = t("diagnostic_never")
        tess_status = current_tesseract_status()
        if not tess_status["pytesseract"]:
            tess = t("diagnostic_tesseract_pytesseract_missing")
        elif not tess_status["executable"]:
            tess = t("diagnostic_tesseract_exe_missing")
        elif not tess_status["ready"]:
            tess = t(
                "diagnostic_tesseract_lang_missing",
                version=tess_status.get("version") or "?",
                lang=tess_status.get("required_lang") or "?"
            )
        else:
            tess = t(
                "diagnostic_tesseract_ready",
                version=tess_status.get("version") or "?",
                lang=tess_status.get("required_lang") or "?"
            )
        return t(
            "diagnostic_text", version=APP_VERSION,
            system=f"{platform.system()} {platform.release()} ({platform.machine()})",
            data_dir=DATA_DIR, recipes=len(recipes), photos=photos, data_size=size_text,
            last_backup=last_backup, tesseract=tess,
            qr=t("diagnostic_yes") if QRCODE_READER_AVAILABLE else t("diagnostic_no"),
            qrgen=t("diagnostic_yes") if QRCODE_AVAILABLE else t("diagnostic_no"),
        )

    def copy_report(self):
        self.clipboard_clear(); self.clipboard_append(self.report); self.update()
        self.app.show_toast(t("diagnostic_copied"))

    def open_data_folder(self):
        try:
            if os.name == "nt": os.startfile(DATA_DIR)
            elif sys.platform == "darwin": subprocess.Popen(["open", DATA_DIR])
            else: subprocess.Popen(["xdg-open", DATA_DIR])
        except Exception as e:
            messagebox.showerror(t("common_error"), str(e), parent=self)


class ShoppingChecklistWindow(tk.Toplevel):
    """Affiche une liste de courses déjà calculée sous forme de cases à
    cocher, pour pointer les articles au fur et à mesure des courses."""

    def __init__(self, app, grouped_totals, title=None):
        super().__init__(app)
        self.app = app
        if title is None:
            title = t("allrecipes_shopping_list_title")
        self.title(f"☑️ {title}")
        fit_window_to_workarea(self, gs(960), gs(900), margin=18)
        self.grab_set()

        ttk.Label(self, text=f"☑️ {title}", font=("Segoe UI", sf(14), "bold")).pack(pady=(15, 5))
        ttk.Label(self, text=t("checklist_instruction"),
                  font=("Segoe UI", sf(9)), foreground=COLOR_TEXT_MUTED).pack(pady=(0, 10))

        container = ttk.Frame(self)
        container.pack(fill="both", expand=True, padx=15)
        canvas = tk.Canvas(container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        rows_frame = ttk.Frame(canvas)
        rows_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=rows_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.checks = []
        for rayon, items in grouped_totals:
            ttk.Label(rows_frame, text=translate_rayon_name(rayon), font=("Segoe UI", sf(11), "bold")).pack(
                anchor="w", pady=(12, 3))
            for name, qty, unit in items:
                unit_display = f" {translate_unit_name(unit)}" if unit else ""
                var = tk.BooleanVar()
                lbl_text = f"{translate_ingredient_name(name)} : {qty}{unit_display}"
                chk = ttk.Checkbutton(rows_frame, text=lbl_text, variable=var,
                                       command=lambda: None)
                chk.pack(anchor="w", padx=10, pady=1)
                self.checks.append((var, chk, lbl_text))
                var.trace_add("write", lambda *args, v=var, c=chk: self._update_style(v, c))

        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text=t("checklist_check_all_button"), command=self.check_all).grid(row=0, column=0, padx=5)
        ttk.Button(btn_frame, text=t("checklist_uncheck_all_button"), command=self.uncheck_all).grid(row=0, column=1, padx=5)

        self.progress_label = ttk.Label(self, text="", font=("Segoe UI", sf(9)), foreground=COLOR_TEXT_MUTED)
        self.progress_label.pack(pady=(0, 10))
        self._update_progress()

    def _update_style(self, var, chk):
        style_name = "Checked.TCheckbutton" if var.get() else "TCheckbutton"
        try:
            style = ttk.Style(self)
            style.configure("Checked.TCheckbutton", foreground="#999")
            chk.configure(style=style_name)
        except tk.TclError:
            pass
        self._update_progress()

    def _update_progress(self):
        total = len(self.checks)
        done = sum(1 for var, chk, text in self.checks if var.get())
        self.progress_label.config(text=t("checklist_progress_label", done=done, total=total))

    def check_all(self):
        for var, chk, text in self.checks:
            var.set(True)

    def uncheck_all(self):
        for var, chk, text in self.checks:
            var.set(False)


class ExportFormatDialog(tk.Toplevel):
    """Petite fenêtre pour choisir le format d'export (texte, Excel ou PDF)
    d'une liste de courses, réutilisable depuis n'importe quelle fenêtre qui
    propose ces 3 exports (« Toutes les recettes », « Planning de la
    semaine », « Nouveau menu »)."""

    def __init__(self, parent_window, export_txt_callback, export_excel_callback, export_pdf_callback):
        super().__init__(parent_window)
        self.title(t("exportformat_title"))
        fit_window_to_workarea(self, gs(380), gs(280), margin=14)
        self.resizable(False, False)
        self.grab_set()

        ttk.Label(self, text=t("exportformat_heading"),
                  font=("Segoe UI", sf(12), "bold"), wraplength=340, justify="center").pack(pady=(20, 5))
        ttk.Label(self, text=t("exportformat_choose_label"),
                  font=("Segoe UI", sf(9)), foreground=COLOR_TEXT_MUTED).pack(pady=(0, 15))

        ttk.Button(self, text=t("exportformat_txt_button"),
                   command=lambda: self._run(export_txt_callback)).pack(pady=6, padx=40, fill="x")
        ttk.Button(self, text=t("exportformat_excel_button"),
                   command=lambda: self._run(export_excel_callback)).pack(pady=6, padx=40, fill="x")
        ttk.Button(self, text=t("exportformat_pdf_button"),
                   command=lambda: self._run(export_pdf_callback)).pack(pady=6, padx=40, fill="x")
        ttk.Button(self, text=t("exportformat_cancel_button"), style="Secondary.TButton",
                   command=self.destroy).pack(pady=(15, 10))

    def _run(self, callback):
        self.destroy()
        callback()


class AddManualIngredientDialog(tk.Toplevel):
    """Permet d'ajouter un ou plusieurs ingrédients (avec quantité) directement
    à une liste de courses, indépendamment des recettes sélectionnées — par
    exemple pour du papier essuie-tout ou tout autre article à ne pas
    oublier. Réutilisable depuis "Toutes les recettes", "Planning de la
    semaine" et "Nouveau menu" : `target_window` doit juste exposer une
    méthode `add_manual_items(items)`."""

    def __init__(self, app, target_window):
        super().__init__(target_window)
        self.app = app
        self.target_window = target_window
        self.staged_items = []  # ingrédients ajoutés à la liste d'attente, pas encore validés
        self.title(t("addmanual_title"))
        fit_window_to_workarea(self, gs(600), gs(560), margin=14)
        safe_minsize(self, gs(420), gs(480))
        self.resizable(True, True)
        self.grab_set()

        ttk.Label(self, text=t("addmanual_heading"),
                  font=("Segoe UI", sf(12), "bold"), wraplength=420, justify="center").pack(pady=(15, 5))
        ttk.Label(
            self, text=t("addmanual_intro"),
            font=("Segoe UI", sf(8)), foreground=COLOR_TEXT_MUTED, justify="center"
        ).pack(pady=(0, 10))

        name_frame = ttk.Frame(self)
        name_frame.pack(pady=5)
        ttk.Label(name_frame, text=t("common_ingredient_label")).grid(row=0, column=0, padx=5, sticky="e")
        self.name_combo = ttk.Combobox(name_frame, values=get_display_ingredient_values(sorted(self.app.ingredient_names, key=ingredient_sort_key)),
                                        width=26)
        self.name_combo.grid(row=0, column=1, padx=5)
        ttk.Button(name_frame, text=t("addmanual_new_ingredient_button"),
                   command=self.create_new_ingredient).grid(row=0, column=2, padx=5)

        qty_frame = ttk.Frame(self)
        qty_frame.pack(pady=10)
        ttk.Label(qty_frame, text=t("common_quantity_label")).grid(row=0, column=0, padx=5)
        self.qty_entry = ttk.Entry(qty_frame, width=8)
        self.qty_entry.insert(0, "1")
        self.qty_entry.grid(row=0, column=1, padx=5)
        ttk.Label(qty_frame, text=t("common_unit_label")).grid(row=0, column=2, padx=5)
        self.unit_options = RecipeFormWindow.UNIT_OPTIONS[:-1] + ["boîte", "paquet", "rouleau", "bouteille"]
        self.unit_combo = ttk.Combobox(qty_frame, values=[translate_unit_name(u) for u in self.unit_options], width=14)  # texte libre autorisé
        self.unit_combo.set(translate_unit_name("pièce"))
        self.unit_combo.grid(row=0, column=3, padx=5)
        ttk.Button(qty_frame, text=t("addmanual_add_to_list_button"),
                   command=self.stage_item).grid(row=0, column=4, padx=(10, 0))
        self.name_combo.bind("<Return>", lambda e: self.stage_item())
        self.qty_entry.bind("<Return>", lambda e: self.stage_item())

        ttk.Label(self, text=t("addmanual_staged_label"),
                  font=("Segoe UI", sf(10), "bold")).pack(pady=(10, 3))
        staged_frame = ttk.Frame(self)
        staged_frame.pack(padx=15, fill="both", expand=True)
        self.staged_listbox = tk.Listbox(staged_frame, height=10, font=("Segoe UI", sf(9)))
        staged_scrollbar = ttk.Scrollbar(staged_frame, orient="vertical", command=self.staged_listbox.yview)
        self.staged_listbox.configure(yscrollcommand=staged_scrollbar.set)
        self.staged_listbox.pack(side="left", fill="both", expand=True)
        staged_scrollbar.pack(side="right", fill="y")
        ttk.Button(self, text=t("addmanual_remove_staged_button"),
                   command=self.remove_staged).pack(pady=(5, 0))

        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=15)
        ttk.Button(btn_frame, text=t("addmanual_confirm_all_button"),
                   command=self.confirm_all).grid(row=0, column=0, padx=5)
        ttk.Button(btn_frame, text=t("addmanual_close_button"), style="Secondary.TButton",
                   command=self.close).grid(row=0, column=1, padx=5)
        self.protocol("WM_DELETE_WINDOW", self.close)

    def close(self):
        self.destroy()
        # Sans ceci, la fenêtre d'origine (ex. "Toutes les recettes") peut
        # se retrouver derrière la page d'accueil une fois cette fenêtre
        # fermée, plutôt que de rester au premier plan.
        self.target_window.lift()
        self.target_window.focus_force()

    def create_new_ingredient(self):
        typed = normalize_oe(self.name_combo.get().strip())
        win = IngredientEditWindow(self.app, manage_window=None, existing_name=None,
                                    prefill_name=typed, parent_window=self)
        self.wait_window(win)
        self.name_combo["values"] = get_display_ingredient_values(sorted(self.app.ingredient_names, key=ingredient_sort_key))

    def stage_item(self):
        name = normalize_oe(self.name_combo.get().strip())
        if not name:
            messagebox.showerror(t("common_error"), t("pantry_error_ingredient_required"))
            return
        # Cette liste accepte aussi des articles hors base de données (ex.
        # essuie-tout) : si le nom tapé correspond à un ingrédient connu
        # (en français ou en anglais), on le normalise vers son nom
        # canonique français ; sinon, on garde le texte tel quel.
        canonical = resolve_ingredient_input(name, self.app.ingredient_names)
        if canonical is not None:
            name = canonical
        try:
            quantity = parse_positive_number(self.qty_entry.get())
        except ValueError:
            messagebox.showerror(t("common_error"), t("allrecipes_invalid_quantity"))
            return
        unit = resolve_unit_input_best_effort(self.unit_combo.get().strip(), self.unit_options)
        self.staged_items.append({"name": name, "quantity": quantity, "unit": unit})
        unit_display = f" {translate_unit_name(unit)}" if unit else ""
        self.staged_listbox.insert(tk.END, f"{translate_ingredient_name(name)} : {quantity}{unit_display}")

        # Prêt pour la saisie suivante : on vide juste le nom et la
        # quantité repasse à 1, pour enchaîner rapidement plusieurs ajouts.
        self.name_combo.set("")
        self.qty_entry.delete(0, tk.END)
        self.qty_entry.insert(0, "1")
        self.name_combo.focus_set()

    def remove_staged(self):
        sel = self.staged_listbox.curselection()
        if not sel:
            messagebox.showinfo(t("common_info"), t("addmanual_select_staged_first"))
            return
        for i in reversed(sel):
            self.staged_listbox.delete(i)
            del self.staged_items[i]

    def confirm_all(self):
        if not self.staged_items:
            messagebox.showinfo(t("common_info"), t("addmanual_add_staged_first"))
            return
        self.target_window.add_manual_items(self.staged_items)
        messagebox.showinfo(t("onerecipe_added_to_shopping_title"), t("addmanual_confirmed_message", count=len(self.staged_items)))
        self.close()


class SavedShoppingListsWindow(tk.Toplevel):
    """Gestion moderne des listes de courses enregistrées : chargement,
    renommage, duplication et suppression."""
    def __init__(self, app, target_window):
        super().__init__(target_window)
        self.app = app; self.target_window = target_window
        self.title(t("savedlists_title")); fit_window_to_workarea(self, gs(720), gs(500), margin=14)
        safe_minsize(self, gs(600), gs(420)); self.resizable(True, True); self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.close)
        ttk.Label(self, text=t("savedlists_heading"), font=("Segoe UI", sf(14), "bold")).pack(pady=(15,10))
        frame=ttk.Frame(self); frame.pack(fill="both", expand=True, padx=15)
        self.tree=ttk.Treeview(frame, columns=("name","items","date"), show="headings", selectmode="browse")
        for c,txt,w in (("name",t("savedlists_col_name"),330),("items",t("savedlists_col_items"),90),("date",t("savedlists_col_date"),180)):
            self.tree.heading(c,text=txt); self.tree.column(c,width=gs(w),anchor="w" if c!="items" else "center")
        sb=ttk.Scrollbar(frame,orient="vertical",command=self.tree.yview); self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left",fill="both",expand=True); sb.pack(side="right",fill="y")
        self.tree.bind("<Double-1>",lambda e:self.load_selected())
        btn=ttk.Frame(self); btn.pack(pady=15)
        ttk.Button(btn,text=t("savedlists_load_button"),style="Primary.TButton",command=self.load_selected).grid(row=0,column=0,padx=4)
        ttk.Button(btn,text=t("savedlists_rename_button"),command=self.rename_selected).grid(row=0,column=1,padx=4)
        ttk.Button(btn,text=t("savedlists_duplicate_button"),command=self.duplicate_selected).grid(row=0,column=2,padx=4)
        ttk.Button(btn,text=t("savedlists_delete_button"),command=self.delete_selected).grid(row=0,column=3,padx=4)
        ttk.Button(btn,text=t("addmanual_close_button"),style="Secondary.TButton",command=self.close).grid(row=0,column=4,padx=4)
        self.saved_lists=[]; self._populate()
    def _populate(self):
        for iid in self.tree.get_children(): self.tree.delete(iid)
        self.saved_lists=load_saved_shopping_lists(); self.saved_lists.sort(key=lambda entry:entry.get("created_at",""), reverse=True)
        for i,saved in enumerate(self.saved_lists): self.tree.insert("", "end", iid=str(i), values=(saved.get("name",""),len(saved.get("items",[])),saved.get("created_at","?")))
    def _selected(self):
        sel=self.tree.selection()
        if not sel or not self.saved_lists:
            messagebox.showinfo(t("common_info"),t("savedlists_select_list_first"),parent=self); return None
        return self.saved_lists[int(sel[0])]
    def load_selected(self):
        saved=self._selected()
        if saved is not None: self.target_window.load_saved_list(saved.get("items",[])); self.close()
    def rename_selected(self):
        saved=self._selected()
        if saved is None:return
        name=simpledialog.askstring(t("savedlists_title"),t("savedlists_rename_prompt"),initialvalue=saved.get("name",""),parent=self)
        if not name or not name.strip():return
        all_lists=load_saved_shopping_lists()
        for entry in all_lists:
            if entry.get("name")==saved.get("name") and entry.get("created_at")==saved.get("created_at"): entry["name"]=name.strip(); break
        save_saved_shopping_lists(all_lists); self._populate()
    def duplicate_selected(self):
        import copy
        saved=self._selected()
        if saved is None:return
        all_lists=load_saved_shopping_lists(); base=saved.get("name","")+t("savedlists_duplicate_suffix")
        existing={entry.get("name","").lower() for entry in all_lists}; name=base; n=2
        while name.lower() in existing: name=f"{base} {n}"; n+=1
        dup=copy.deepcopy(saved); dup["name"]=name; dup["created_at"]=datetime.now().strftime("%Y-%m-%d %H:%M")
        all_lists.append(dup); save_saved_shopping_lists(all_lists); self._populate()
    def delete_selected(self):
        saved=self._selected()
        if saved is None:return
        if not ask_yes_no(t("common_confirm"),t("savedlists_delete_confirm",name=saved.get("name","")),parent=self):return
        all_lists=load_saved_shopping_lists(); removed=False; kept=[]
        for entry in all_lists:
            if not removed and entry.get("name")==saved.get("name") and entry.get("created_at")==saved.get("created_at"): removed=True; continue
            kept.append(entry)
        save_saved_shopping_lists(kept); self._populate()
    def close(self):
        self.destroy(); self.target_window.lift(); self.target_window.focus_force()


class ShoppingCartRenderMixin:
    """Rendu commun de la liste de courses éditable, partagé par
    AllRecipesWindow, WeeklyPlanWindow et MenuFormWindow : ces trois fenêtres
    affichaient un rendu quasi identique (regroupement par rayon, tri par
    nom, coût total, quantité éditable, suppression) recopié trois fois.
    Seule AllRecipesWindow redéfinit _render_shopping_items, pour sa mise en
    page en grille à colonnes (1 ou 2 selon la largeur de la fenêtre)."""

    _shopping_empty_message_key = None
    _shopping_heading_key = None

    def _on_shopping_list_render_start(self):
        """Point d'extension appelé avant le nettoyage de result_frame."""

    def _grouped_current_items(self):
        """Regroupe self.current_items par rayon, en conservant l'ordre des
        rayons et le tri alphabétique au sein de chaque rayon. Retourne une
        liste de (rayon, [indices dans self.current_items, triés])."""
        by_rayon = {}
        for i, item in enumerate(self.current_items):
            by_rayon.setdefault(item["rayon"], []).append(i)
        grouped = []
        for rayon in RAYON_ORDER:
            if rayon in by_rayon:
                idxs = sorted(by_rayon[rayon], key=lambda i: ingredient_sort_key(self.current_items[i]["name"]))
                grouped.append((rayon, idxs))
        return grouped

    def _update_item_quantity(self, index, entry):
        if index >= len(self.current_items):
            return
        try:
            new_qty = parse_optional_positive_number(entry.get(), allow_zero=False)
        except ValueError:
            messagebox.showerror(t("common_error"), t("allrecipes_invalid_quantity"))
            entry.delete(0, tk.END)
            entry.insert(0, "" if self.current_items[index]["quantity"] is None else str(self.current_items[index]["quantity"]))
            return
        self.current_items[index]["quantity"] = new_qty

    def _delete_item(self, index):
        del self.current_items[index]
        self._render_shopping_list()

    def _render_shopping_list(self):
        self._on_shopping_list_render_start()
        for child in self.result_frame.winfo_children():
            child.destroy()

        if not self.current_items:
            ttk.Label(
                self.result_frame,
                text=t(self._shopping_empty_message_key),
                foreground=COLOR_TEXT_MUTED, justify="center"
            ).pack(pady=20)
            return

        ttk.Label(self.result_frame, text=t(self._shopping_heading_key),
                  font=("Segoe UI", sf(11), "bold")).pack(anchor="w", pady=(5, 2))
        if self.manual_items:
            ttk.Label(
                self.result_frame,
                text=t("allrecipes_manual_items_note", count=len(self.manual_items)),
                font=("Segoe UI", sf(8)), foreground=COLOR_TEXT_MUTED
            ).pack(anchor="w")
        _render_cart_cost_summary(self.result_frame, self.current_items)
        _render_cart_sort_toggle(self.result_frame, self._shopping_sort_var, self._render_shopping_list)

        self._render_shopping_items()

        tk.Frame(self.result_frame, height=SCROLL_BOTTOM_PADDING, background=COLOR_BG).pack(fill="x")

    def _render_shopping_items(self):
        """Mise en page par défaut : une ligne par ingrédient, sans colonnes.
        AllRecipesWindow redéfinit cette méthode pour sa grille à colonnes."""
        def render_row(idx):
            item = self.current_items[idx]
            row = ttk.Frame(self.result_frame)
            row.pack(fill="x", pady=1)
            ttk.Label(row, text=f"- {translate_ingredient_name(item['name'])}", width=30, anchor="w").pack(side="left")
            qty_entry = ttk.Entry(row, width=8)
            qty_entry.insert(0, "" if item["quantity"] is None else str(item["quantity"]))
            qty_entry.pack(side="left", padx=3)
            qty_entry.bind("<FocusOut>", lambda e, i=idx, ent=qty_entry: self._update_item_quantity(i, ent))
            qty_entry.bind("<Return>", lambda e, i=idx, ent=qty_entry: self._update_item_quantity(i, ent))
            ttk.Label(row, text=(t("quantity_unspecified") if item["quantity"] is None else translate_unit_name(item["unit"])), width=18, anchor="w").pack(side="left", padx=3)
            delete_btn = ttk.Button(row, text="🗑", width=3,
                       command=lambda i=idx: self._delete_item(i))
            delete_btn.pack(side="left", padx=3)
            add_tooltip(delete_btn, t("tooltip_delete_item"))

        if self._shopping_sort_var.get() == "nom":
            for idx in _cart_items_sorted_by_name(self.current_items):
                render_row(idx)
        else:
            for rayon, idxs in self._grouped_current_items():
                ttk.Label(self.result_frame, text=translate_rayon_name(rayon), font=("Segoe UI", sf(10), "bold"),
                          foreground=COLOR_ACCENT_DARK).pack(anchor="w", pady=(12, 4))
                for idx in idxs:
                    render_row(idx)


class AllRecipesWindow(ShoppingCartRenderMixin, tk.Toplevel):
    """Fenêtre listant toutes les recettes avec sélection + nombre de personnes,
    pour calculer et exporter en PDF la quantité totale d'ingrédients nécessaire."""

    SORT_OPTIONS = RECIPE_SORT_OPTIONS
    _shopping_empty_message_key = "allrecipes_empty_list_message"
    _shopping_heading_key = "allrecipes_total_list_heading"

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title(t("allrecipes_title"))
        screen_height = get_usable_screen_height(self)
        fit_window_to_workarea(self, gs(1830), screen_height, margin=18)
        safe_minsize(self, gs(720), gs(500))
        self.resizable(True, True)
        self.grab_set()
        self.manual_items = []  # ingrédients ajoutés manuellement (hors recettes) : [{"name","quantity","unit"}]
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        ttk.Label(self, text=t("allrecipes_select_label"),
                  font=("Segoe UI", sf(11), "bold")).pack(pady=(10, 5))

        compact_layout = self.winfo_screenwidth() < 1100 or FONT_SCALE > 1.0
        top_frame = ttk.Frame(self)
        top_frame.pack(pady=(0, 5), fill="x", padx=15)
        self.search_entry = ttk.Entry(top_frame, width=20)
        self.sort_combo = ttk.Combobox(top_frame, values=[translate_sort_option(o) for o in self.SORT_OPTIONS], state="readonly", width=18)
        self.sort_combo.set(translate_sort_option(self.SORT_OPTIONS[0]))
        self.category_filter_combo = ttk.Combobox(
            top_frame, values=[t("common_all_categories")] + [translate_category_name(c) for c in RecipeFormWindow.CATEGORY_OPTIONS],
            state="readonly", width=16
        )
        self.category_filter_combo.set(t("common_all_categories"))
        if compact_layout:
            ttk.Label(top_frame, text=t("common_search_label")).grid(row=0, column=0, sticky="w")
            self.search_entry.grid(row=0, column=1, columnspan=3, padx=(5, 0), sticky="ew")
            ttk.Label(top_frame, text=t("common_sort_by_label")).grid(row=1, column=0, sticky="w", pady=(5, 0))
            self.sort_combo.grid(row=1, column=1, padx=(5, 10), pady=(5, 0), sticky="ew")
            ttk.Label(top_frame, text=t("common_category_label")).grid(row=1, column=2, sticky="w", pady=(5, 0))
            self.category_filter_combo.grid(row=1, column=3, padx=(5, 0), pady=(5, 0), sticky="ew")
            top_frame.columnconfigure(1, weight=1)
            top_frame.columnconfigure(3, weight=1)
        else:
            ttk.Label(top_frame, text=t("common_search_label")).pack(side="left")
            self.search_entry.pack(side="left", padx=5, fill="x", expand=True)
            ttk.Label(top_frame, text=t("common_sort_by_label")).pack(side="left", padx=(10, 2))
            self.sort_combo.pack(side="left")
            ttk.Label(top_frame, text=t("common_category_label")).pack(side="left", padx=(10, 2))
            self.category_filter_combo.pack(side="left")
        self.search_entry.bind("<KeyRelease>", lambda e: self._filter_rows())
        self.sort_combo.bind("<<ComboboxSelected>>", lambda e: self._apply_sort())
        self.category_filter_combo.bind("<<ComboboxSelected>>", lambda e: self._filter_rows())

        ingredient_filter_frame = ttk.LabelFrame(self, text=t("allrecipes_ingredient_filter_title"))
        ingredient_filter_frame.pack(pady=(0, 8), padx=15, fill="x")
        ingredient_values = get_display_ingredient_values(sorted(self.app.ingredient_names, key=ingredient_sort_key))

        self.want_entries = [self._make_ingredient_filter_entry(ingredient_filter_frame, ingredient_values) for _ in range(2)]
        self.exclude_entries = [self._make_ingredient_filter_entry(ingredient_filter_frame, ingredient_values) for _ in range(2)]
        self.all_tags = sorted({tag for r in self.app.recipes for tag in r.get("tags", [])}, key=ingredient_sort_key)
        self.tag_filter_entries = [self._make_ingredient_filter_entry(ingredient_filter_frame, self.all_tags) for _ in range(2)]

        if compact_layout:
            groups = [
                (t("common_want_label"), self.want_entries),
                (t("common_exclude_label"), self.exclude_entries),
                (t("common_tags_filter_label"), self.tag_filter_entries),
            ]
            for row_i, (label_text, entries) in enumerate(groups):
                ttk.Label(ingredient_filter_frame, text=label_text).grid(row=row_i, column=0, sticky="w", padx=5, pady=3)
                entries[0].grid(row=row_i, column=1, padx=5, pady=3, sticky="ew")
                entries[1].grid(row=row_i, column=2, padx=5, pady=3, sticky="ew")
            ingredient_filter_frame.columnconfigure(1, weight=1)
            ingredient_filter_frame.columnconfigure(2, weight=1)
            ttk.Button(ingredient_filter_frame, text=t("common_reset_button"),
                       command=self._reset_ingredient_filters).grid(row=3, column=0, padx=5, pady=(3, 5), sticky="w")
            ttk.Label(ingredient_filter_frame, text=t("common_filter_hint"),
                      font=("Segoe UI", sf(8)), foreground=COLOR_TEXT_MUTED).grid(
                row=3, column=1, columnspan=2, sticky="w", padx=5, pady=(3, 5))
        else:
            ttk.Label(ingredient_filter_frame, text=t("common_want_label")).grid(row=0, column=0, sticky="w", padx=5, pady=3)
            for i, entry in enumerate(self.want_entries): entry.grid(row=0, column=1+i, padx=5, pady=3)
            ttk.Label(ingredient_filter_frame, text=t("common_exclude_label")).grid(row=1, column=0, sticky="w", padx=5, pady=3)
            for i, entry in enumerate(self.exclude_entries): entry.grid(row=1, column=1+i, padx=5, pady=3)
            ttk.Label(ingredient_filter_frame, text=t("common_tags_filter_label")).grid(row=2, column=0, sticky="w", padx=5, pady=3)
            for i, entry in enumerate(self.tag_filter_entries): entry.grid(row=2, column=1+i, padx=5, pady=3)
            ttk.Button(ingredient_filter_frame, text=t("common_reset_button"),
                       command=self._reset_ingredient_filters).grid(row=0, column=3, rowspan=3, padx=8)
            ttk.Label(ingredient_filter_frame, text=t("common_filter_hint"),
                      font=("Segoe UI", sf(8)), foreground=COLOR_TEXT_MUTED).grid(
                row=3, column=0, columnspan=4, sticky="w", padx=5, pady=(0, 3))

        container = ttk.Frame(self)
        container.pack(fill="both", expand=True, padx=10)

        canvas = tk.Canvas(container, height=240, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        rows_frame = ttk.Frame(canvas)
        rows_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        rows_window_id = canvas.create_window((0, 0), window=rows_frame, anchor="nw")
        canvas.bind(
            "<Configure>",
            lambda e: canvas.itemconfigure(rows_window_id, width=max(1, e.width))
        )
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.checks = []
        self.current_items = []       # liste plate éditable [{'name','quantity','unit','rayon'}, ...]
        self._shopping_sort_var = tk.StringVar(value="rayon")
        self.last_chosen_recipes = []  # recettes ajoutées au panier (pour les en-têtes d'export)
        self._recipe_cart_persons = {}  # id stable -> personnes ; un second ajout remplace le précédent
        rows_frame.columnconfigure(0, weight=1)
        for row_index, recipe in enumerate(self.app.recipes):
            row = ttk.Frame(rows_frame, padding=(8, 5))
            row.grid(row=row_index, column=0, sticky="ew", pady=3)
            row.columnconfigure(0, weight=1)

            # Le nom occupe une ligne complète. Les contrôles sont placés
            # dessous : ils restent donc visibles même sur un écran étroit.
            ttk.Label(
                row, text=format_recipe_list_label(recipe), anchor="w",
                font=("Segoe UI", sf(9), "bold")
            ).grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 4))

            controls = ttk.Frame(row)
            controls.grid(row=1, column=0, columnspan=4, sticky="w", pady=(0, 2))

            ttk.Label(controls, text=t("allrecipes_persons_count_label")).pack(
                side="left"
            )
            pers_entry = ttk.Entry(controls, width=7)

            # Préremplit à partir d'une sélection faite depuis "Voir une
            # recette précise" (bouton "Ajouter à la liste de courses"),
            # sinon utilise le nombre de personnes par défaut de la recette.
            preselected = self.app.shopping_selection.get(recipe_ref_key(recipe))
            if preselected is not None:
                pers_entry.insert(0, str(preselected))
            else:
                pers_entry.insert(0, str(recipe.get("default_persons") or 1))
            pers_entry.pack(side="left", padx=(6, 10))
            ttk.Button(
                controls, text=t("allrecipes_add_to_cart_button"),
                command=lambda r=recipe, e=pers_entry: self._add_recipe_to_cart(r, e)
            ).pack(side="left", padx=(0, 6))
            ttk.Button(
                controls, text=t("common_edit_button"),
                command=lambda idx=row_index: self._edit_recipe(idx)
            ).pack(side="left")
            self.checks.append((recipe, pers_entry, row))

        tk.Frame(rows_frame, height=SCROLL_BOTTOM_PADDING, background=COLOR_BG).grid(
            row=len(self.app.recipes), column=0, sticky="ew")

        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=6)
        for col in range(4):
            btn_frame.columnconfigure(col, weight=1)
        compact_actions = screen_height < 800 or self.winfo_screenwidth() < 1100
        ttk.Button(btn_frame, text=t("allrecipes_checklist_mode_button"),
                   command=self.open_checklist).grid(row=0, column=0, padx=4, pady=2, sticky="ew")
        ttk.Button(btn_frame, text=t("allrecipes_clear_list_button"),
                   command=self.clear_selection).grid(row=0, column=1, padx=4, pady=2, sticky="ew")
        ttk.Button(btn_frame, text=t("allrecipes_export_button"),
                   command=self.open_export_dialog).grid(row=0, column=2, padx=4, pady=2, sticky="ew")
        ttk.Button(btn_frame, text=t("allrecipes_print_button"),
                   command=self.print_shopping_list).grid(row=0, column=3, padx=4, pady=2, sticky="ew")
        if compact_actions:
            more = ttk.Button(btn_frame, text=t("weekplan_more_actions"), style="Secondary.TButton")
            more.grid(row=1, column=0, columnspan=4, padx=4, pady=2, sticky="ew")
            _ui_attach_more_menu(more, [
                (t("allrecipes_add_manual_ingredient_button"), self.open_add_manual_ingredient),
                (t("allrecipes_save_list_button"), self.save_list_for_later),
                (t("allrecipes_load_list_button"), self.open_saved_lists),
            ])
        else:
            ttk.Button(btn_frame, text=t("allrecipes_add_manual_ingredient_button"),
                       command=self.open_add_manual_ingredient).grid(row=1, column=0, columnspan=4, padx=4, pady=2, sticky="ew")
            ttk.Button(btn_frame, text=t("allrecipes_save_list_button"),
                       command=self.save_list_for_later).grid(row=2, column=0, columnspan=2, padx=4, pady=2, sticky="ew")
            ttk.Button(btn_frame, text=t("allrecipes_load_list_button"),
                       command=self.open_saved_lists).grid(row=2, column=2, columnspan=2, padx=4, pady=2, sticky="ew")

        # ---- Zone de résultat éditable : chaque ingrédient peut voir sa
        # quantité modifiée ou être retiré, sans devoir tout recalculer. ----
        result_container = ttk.Frame(self)
        result_container.pack(pady=10, padx=15, fill="both", expand=True)
        result_canvas = tk.Canvas(result_container, highlightthickness=0)
        result_scrollbar = ttk.Scrollbar(result_container, orient="vertical", command=result_canvas.yview)
        self.result_frame = ttk.Frame(result_canvas)
        self._shopping_columns = 1
        self._shopping_resize_job = None
        self.result_frame.bind(
            "<Configure>", lambda e: result_canvas.configure(scrollregion=result_canvas.bbox("all"))
        )
        result_window_id = result_canvas.create_window((0, 0), window=self.result_frame, anchor="nw")
        result_canvas.bind(
            "<Configure>",
            lambda e: (
                result_canvas.itemconfigure(result_window_id, width=max(1, e.width)),
                self._on_shopping_result_resize(e.width)
            )
        )
        result_canvas.configure(yscrollcommand=result_scrollbar.set)
        result_canvas.pack(side="left", fill="both", expand=True)
        result_scrollbar.pack(side="right", fill="y")

        def _on_result_mousewheel(event):
            result_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        _ui_bind_local_mousewheel(result_canvas, self.result_frame, _on_result_mousewheel)

        # Ajoute automatiquement au panier les recettes présélectionnées
        # depuis "Voir une recette précise" (bouton "🛒 Ajouter à la liste de
        # courses"), pour ne pas perdre cette présélection maintenant qu'il
        # n'y a plus de case à cocher à valider soi-même.
        for recipe, pers_entry, row in self.checks:
            if recipe_ref_key(recipe) in self.app.shopping_selection:
                self._add_recipe_to_cart(recipe, pers_entry)

        self._render_shopping_list()

    def open_add_manual_ingredient(self):
        AddManualIngredientDialog(self.app, self)

    def open_export_dialog(self):
        ExportFormatDialog(self, self.export_txt, self.export_excel, self.export_pdf)

    def add_manual_items(self, items):
        self.manual_items.extend(items)
        self._rebuild_cart_from_recipe_selection()
        self._render_shopping_list()

    def _edit_recipe(self, index):
        win = RecipeFormWindow(self.app, recipe_index=index)
        self.wait_window(win)
        if not self.winfo_exists():
            return
        self.app.refresh_recipes()
        # La modification peut avoir changé le nom, les temps, les
        # allergènes... : on reconstruit la fenêtre pour que tout
        # s'affiche à jour (libellés, tri, filtres).
        self.destroy()
        AllRecipesWindow(self.app)

    def _apply_sort(self):
        option = resolve_sort_option_input(self.sort_combo.get(), self.SORT_OPTIONS)
        reverse = option in ("Ajoutées récemment",)
        ordered = sorted(self.checks, key=lambda t: recipe_sort_key(t[0], option), reverse=reverse)
        for new_index, (recipe, pers_entry, row) in enumerate(ordered):
            row.grid(row=new_index, column=0, sticky="ew", pady=4)
        self.checks = ordered
        self._filter_rows()

    def _on_close(self):
        if getattr(self, "current_items", None):
            if not ask_yes_no(
                t("allrecipes_close_confirm_title"),
                t("allrecipes_close_confirm_message"),
                icon="warning"
            ):
                return  # l'utilisateur annule la fermeture
        self.destroy()

    def clear_selection(self):
        self.app.shopping_selection.clear()
        self.manual_items = []
        self.current_items = []
        self.last_chosen_recipes = []
        self._recipe_cart_persons = {}
        self._render_shopping_list()

    def _filter_rows(self):
        search = self.search_entry.get().strip()
        search_key = ingredient_sort_key(search) if search else ""
        category_filter = resolve_category_input(self.category_filter_combo.get(), RecipeFormWindow.CATEGORY_OPTIONS)

        known_keys = {ingredient_sort_key(n) for n in self.app.ingredient_names}
        known_tag_keys = {ingredient_sort_key(t) for t in self.all_tags}

        def valid_typed_names(entries, known, resolve_as_ingredient=False):
            names = []
            for e in entries:
                txt = e.get().strip()
                if not txt:
                    continue
                if resolve_as_ingredient:
                    resolved = resolve_ingredient_input(txt, self.app.ingredient_names)
                    if resolved is not None:
                        names.append(resolved)
                elif ingredient_sort_key(txt) in known:
                    names.append(txt)
            return names

        want_names = valid_typed_names(self.want_entries, known_keys, resolve_as_ingredient=True)
        exclude_names = valid_typed_names(self.exclude_entries, known_keys, resolve_as_ingredient=True)
        want_keys = {ingredient_sort_key(n) for n in want_names}
        exclude_keys = {ingredient_sort_key(n) for n in exclude_names}
        tag_names = valid_typed_names(self.tag_filter_entries, known_tag_keys)
        tag_keys = {ingredient_sort_key(n) for n in tag_names}

        for recipe, pers_entry, row in self.checks:
            if not recipe_matches_search(recipe, search_key):
                row.grid_remove()
                continue
            if category_filter and category_filter != t("common_all_categories") and recipe.get("category", "Autre") != category_filter:
                row.grid_remove()
                continue
            if tag_keys:
                recipe_tag_keys = {ingredient_sort_key(t) for t in recipe.get("tags", [])}
                if not tag_keys.issubset(recipe_tag_keys):
                    row.grid_remove()
                    continue

            recipe_ing_keys = {ingredient_sort_key(ing["name"]) for ing in recipe["ingredients"]}
            if want_keys and not want_keys.issubset(recipe_ing_keys):
                row.grid_remove()
                continue
            if exclude_keys and (exclude_keys & recipe_ing_keys):
                row.grid_remove()
                continue

            row.grid()

    def _reset_ingredient_filters(self):
        for entry in self.want_entries + self.exclude_entries + self.tag_filter_entries:
            entry.delete(0, tk.END)
        self._filter_rows()

    # ---- Autocomplétion des champs de filtre par ingrédient (même principe
    # que le choix d'ingrédient dans le formulaire de recette) ----

    def _make_ingredient_filter_entry(self, parent, values):
        entry = ttk.Entry(parent, width=22)
        entry.full_values = values
        entry.bind("<KeyRelease>", lambda e: self._on_filter_entry_keyrelease(e, entry))
        entry.bind("<FocusIn>", lambda e: self._on_filter_entry_focus_in(e, entry))
        entry.bind("<FocusOut>", lambda e: self._on_filter_entry_focus_out(e, entry))
        return entry

    def _hide_filter_suggestions(self, entry):
        popup = getattr(entry, "_suggestion_popup", None)
        if popup is not None:
            try:
                popup.destroy()
            except tk.TclError:
                pass
            entry._suggestion_popup = None
            entry._suggestion_listbox = None

    def _show_filter_suggestions(self, entry, filtered):
        self._hide_filter_suggestions(entry)
        if not filtered:
            return
        popup = tk.Toplevel(entry)
        popup.wm_overrideredirect(True)
        try:
            popup.wm_attributes("-topmost", True)
        except tk.TclError:
            pass
        width = max(entry.winfo_width(), gs(180))

        listbox = tk.Listbox(popup, height=min(6, len(filtered)), exportselection=False, font=("Segoe UI", sf(9)))
        listbox.pack(fill="both", expand=True)
        for v in filtered:
            listbox.insert(tk.END, v)
        finalize_suggestion_popup(popup, entry, listbox, width)

        def choose(event=None):
            sel = listbox.curselection()
            if sel:
                value = listbox.get(sel[0])
                entry.delete(0, tk.END)
                entry.insert(0, value)
            self._hide_filter_suggestions(entry)
            entry.focus_set()
            self._filter_rows()

        listbox.bind("<ButtonRelease-1>", choose)
        listbox.bind("<Return>", choose)
        entry._suggestion_popup = popup
        entry._suggestion_listbox = listbox

    def _on_filter_entry_keyrelease(self, event, entry):
        if event.keysym == "Down":
            listbox = getattr(entry, "_suggestion_listbox", None)
            if listbox is not None:
                listbox.focus_set()
                listbox.selection_set(0)
            return
        if event.keysym in ("Escape",):
            self._hide_filter_suggestions(entry)
            return
        if event.keysym in ("Return", "Tab", "Shift_L", "Shift_R", "Control_L", "Control_R",
                              "Caps_Lock", "Alt_L", "Alt_R", "Left", "Right"):
            return
        full_values = getattr(entry, "full_values", [])
        typed = entry.get()
        filtered = self._filter_ingredients(full_values, typed)
        if filtered:
            self._show_filter_suggestions(entry, filtered)
        else:
            self._hide_filter_suggestions(entry)

    def _on_filter_entry_focus_in(self, event, entry):
        full_values = getattr(entry, "full_values", [])
        typed = entry.get()
        filtered = self._filter_ingredients(full_values, typed)
        if filtered:
            self._show_filter_suggestions(entry, filtered)

    def _on_filter_entry_focus_out(self, event, entry):
        entry.after(200, lambda: self._hide_filter_suggestions(entry))
        self._filter_rows()

    @staticmethod
    def _filter_ingredients(full_values, typed):
        if not typed:
            return full_values
        typed_key = ingredient_sort_key(typed)
        filtered = [v for v in full_values if ingredient_sort_key(v).startswith(typed_key)]
        if not filtered:
            filtered = [v for v in full_values if typed_key in ingredient_sort_key(v)]
        return filtered


    def _rebuild_cart_from_recipe_selection(self):
        pairs = []
        chosen = []
        for recipe_key, persons in self._recipe_cart_persons.items():
            recipe = find_recipe_by_id(self.app.recipes, recipe_key)
            if recipe is None:
                # Compatibilité transitoire avec une ancienne sélection en mémoire.
                recipe = find_recipe_by_name(self.app.recipes, recipe_key)
            if recipe is None:
                continue
            pairs.append((recipe, persons))
            chosen.append((recipe.get("name", ""), persons))
        if self.manual_items:
            pairs.append(({"ingredients": list(self.manual_items)}, 1))
        grouped_totals = compute_grouped_totals(pairs)
        self.current_items = [
            {"name": name, "quantity": qty, "unit": unit, "rayon": rayon}
            for rayon, items in grouped_totals for name, qty, unit in items
        ]
        self.last_chosen_recipes = chosen

    def _add_recipe_to_cart(self, recipe, pers_entry):
        try:
            persons = parse_positive_number(pers_entry.get())
        except ValueError:
            messagebox.showerror(t("common_error"), t("allrecipes_invalid_persons", name=recipe['name']))
            return
        self._recipe_cart_persons[recipe_ref_key(recipe)] = persons
        self._rebuild_cart_from_recipe_selection()
        self._render_shopping_list()

    def _on_shopping_result_resize(self, width):
        """Bascule automatiquement la liste totale en 1 ou 2 colonnes.

        Deux ingrédients par ligne sur grand écran, une seule colonne sur
        écran étroit. On ne reconstruit l'affichage que lorsque le seuil est
        réellement franchi afin d'éviter les rafraîchissements permanents.
        """
        wanted = 2 if int(width or 0) >= gs(1050) else 1
        if wanted == getattr(self, "_shopping_columns", 1):
            return
        self._shopping_columns = wanted
        if self._shopping_resize_job is not None:
            try:
                self.after_cancel(self._shopping_resize_job)
            except Exception as exc:
                log_internal_error("suppressed_exception", exc)
        self._shopping_resize_job = self.after(80, self._render_shopping_list)

    def _on_shopping_list_render_start(self):
        self._shopping_resize_job = None

    def _render_shopping_items(self):
        columns = max(1, int(getattr(self, "_shopping_columns", 1)))

        def render_cell(parent, idx, row_no, col_no):
            item = self.current_items[idx]
            cell = ttk.Frame(parent, padding=(5, 3))
            cell.grid(row=row_no, column=col_no, sticky="ew", padx=(0, 8), pady=1)
            cell.columnconfigure(0, weight=1)

            ttk.Label(
                cell, text=f"- {translate_ingredient_name(item['name'])}",
                anchor="w"
            ).grid(row=0, column=0, sticky="ew", padx=(0, 4))
            qty_entry = ttk.Entry(cell, width=7)
            qty_entry.insert(0, "" if item["quantity"] is None else str(item["quantity"]))
            qty_entry.grid(row=0, column=1, padx=3)
            qty_entry.bind("<FocusOut>", lambda e, i=idx, ent=qty_entry: self._update_item_quantity(i, ent))
            qty_entry.bind("<Return>", lambda e, i=idx, ent=qty_entry: self._update_item_quantity(i, ent))
            ttk.Label(
                cell, text=(t("quantity_unspecified") if item["quantity"] is None else translate_unit_name(item["unit"])), anchor="w"
            ).grid(row=0, column=2, padx=3, sticky="w")
            delete_btn = ttk.Button(
                cell, text="🗑", width=3,
                command=lambda i=idx: self._delete_item(i)
            )
            delete_btn.grid(row=0, column=3, padx=(3, 0))
            add_tooltip(delete_btn, t("tooltip_delete_item"))

        if self._shopping_sort_var.get() == "nom":
            items_frame = ttk.Frame(self.result_frame)
            items_frame.pack(fill="x", pady=(10, 2))
            for c in range(columns):
                items_frame.columnconfigure(c, weight=1, uniform="shopping_items")
            for pos, idx in enumerate(_cart_items_sorted_by_name(self.current_items)):
                row_no, col_no = divmod(pos, columns)
                render_cell(items_frame, idx, row_no, col_no)
        else:
            for rayon, idxs in self._grouped_current_items():
                section = ttk.Frame(self.result_frame)
                section.pack(fill="x", pady=(10, 2))
                ttk.Label(
                    section, text=translate_rayon_name(rayon),
                    font=("Segoe UI", sf(10), "bold"), foreground=COLOR_ACCENT_DARK
                ).grid(row=0, column=0, columnspan=columns, sticky="w", pady=(2, 5))

                items_frame = ttk.Frame(section)
                items_frame.grid(row=1, column=0, columnspan=columns, sticky="ew")
                for c in range(columns):
                    items_frame.columnconfigure(c, weight=1, uniform="shopping_items")

                for pos, idx in enumerate(idxs):
                    row_no, col_no = divmod(pos, columns)
                    render_cell(items_frame, idx, row_no, col_no)

    def save_list_for_later(self):
        if not self.current_items:
            messagebox.showinfo(t("common_info"), t("allrecipes_calculate_list_first"),
                                 parent=self)
            return
        name = simpledialog.askstring(
            t("allrecipes_save_list_dialog_title"), t("allrecipes_save_list_dialog_prompt"), parent=self
        )
        if not name:
            self.lift()
            self.focus_force()
            return
        name = name.strip()
        if not name:
            self.lift()
            self.focus_force()
            return
        lists = load_saved_shopping_lists()
        lists = [entry for entry in lists if entry["name"].lower() != name.lower()]  # remplace une liste de même nom
        lists.append({
            "name": name,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "items": [dict(item) for item in self.current_items],
        })
        save_saved_shopping_lists(lists)
        messagebox.showinfo(t("allrecipes_list_saved_title"), t("allrecipes_list_saved_message", name=name), parent=self)
        # Une messagebox sans fenêtre parente peut parfois faire remonter la
        # page d'accueil au premier plan une fois fermée : on force cette
        # fenêtre à revenir au premier plan par sécurité.
        self.lift()
        self.focus_force()

    def open_saved_lists(self):
        SavedShoppingListsWindow(self.app, self)

    def load_saved_list(self, items):
        self.current_items = [dict(item) for item in items]
        self.last_chosen_recipes = []  # une liste chargée n'est pas liée à une sélection de recettes
        self._recipe_cart_persons = {}
        self.manual_items = []
        self._render_shopping_list()

    def _current_export_data(self):
        """Renvoie (chosen_recipes, grouped_totals) à partir de la liste
        actuellement affichée (self.current_items), en tenant compte des
        modifications de quantité et des suppressions faites à la main."""
        if not self.current_items:
            messagebox.showinfo(t("common_info"), t("allrecipes_empty_list_for_export"))
            return None
        grouped_totals = grouped_totals_from_flat_items(self.current_items)
        return self.last_chosen_recipes, grouped_totals

    def export_txt(self):
        result = self._current_export_data()
        if result is None:
            return
        chosen_recipes, grouped_totals = result

        path = filedialog.asksaveasfilename(
            title=t("allrecipes_export_txt_title"),
            defaultextension=".txt",
            filetypes=[("Fichier texte", "*.txt")],
            initialfile="liste_de_courses.txt"
        )
        if not path:
            return
        try:
            write_shopping_list_txt(path, t("allrecipes_shopping_list_title"), chosen_recipes, grouped_totals)
        except Exception as e:
            messagebox.showerror(t("common_error"), t("common_export_failed", error=e))
            return
        messagebox.showinfo(t("common_export_success_title"), t("allrecipes_export_saved_message", path=path))

    def export_excel(self):
        if not OPENPYXL_AVAILABLE:
            messagebox.showerror(t("common_module_missing"), t("allrecipes_excel_module_missing"))
            return

        result = self._current_export_data()
        if result is None:
            return
        chosen_recipes, grouped_totals = result

        path = filedialog.asksaveasfilename(
            title=t("allrecipes_export_excel_title"),
            defaultextension=".xlsx",
            filetypes=[("Fichier Excel", "*.xlsx")],
            initialfile="liste_de_courses.xlsx"
        )
        if not path:
            return

        try:
            wb = build_shopping_list_workbook(chosen_recipes, grouped_totals)
            wb.save(path)
        except Exception as e:
            messagebox.showerror(t("common_error"), t("common_export_failed", error=e))
            return
        messagebox.showinfo(t("common_export_success_title"), t("allrecipes_export_saved_message", path=path))

    def export_pdf(self):
        if not REPORTLAB_AVAILABLE:
            messagebox.showerror(t("common_module_missing"), t("allrecipes_pdf_module_missing"))
            return

        result = self._current_export_data()
        if result is None:
            return
        chosen_recipes, grouped_totals = result

        path = filedialog.asksaveasfilename(
            title=t("allrecipes_export_pdf_title"),
            defaultextension=".pdf",
            filetypes=[("Fichier PDF", "*.pdf")],
            initialfile="liste_de_courses.pdf"
        )
        if not path:
            return

        try:
            build_shopping_list_pdf(path, t("allrecipes_shopping_list_title"), chosen_recipes, grouped_totals)
        except Exception as e:
            messagebox.showerror(t("common_error"), t("common_export_failed", error=e))
            return
        messagebox.showinfo(t("common_export_success_title"), t("allrecipes_export_saved_message", path=path))

    def print_shopping_list(self):
        if not REPORTLAB_AVAILABLE:
            messagebox.showerror(t("common_module_missing"), t("allrecipes_print_module_missing"))
            return

        result = self._current_export_data()
        if result is None:
            return
        chosen_recipes, grouped_totals = result

        temp_path = get_temp_pdf_path("liste_de_courses")
        try:
            build_shopping_list_pdf(temp_path, t("allrecipes_shopping_list_title"), chosen_recipes, grouped_totals)
        except Exception as e:
            messagebox.showerror(t("common_error"), t("common_print_failed", error=e))
            return

        print_document(self, temp_path, t("allrecipes_print_label"))

    def open_checklist(self):
        result = self._current_export_data()
        if result is None:
            return
        chosen_recipes, grouped_totals = result
        ShoppingChecklistWindow(self.app, grouped_totals, title=t("allrecipes_shopping_list_title"))


class QuickSearchWindow(tk.Toplevel):
    """Recherche rapide de recette, accessible depuis n'importe quelle
    fenêtre de l'application via le raccourci Ctrl+K."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title(t("quicksearch_title"))
        fit_window_to_workarea(self, gs(480), gs(420), margin=14)
        safe_minsize(self, gs(400), gs(360))
        self.resizable(True, True)
        self.grab_set()
        try:
            self.attributes("-topmost", True)
        except tk.TclError:
            pass

        ttk.Label(self, text=t("quicksearch_heading"),
                  font=("Segoe UI", sf(12), "bold")).pack(pady=(15, 5))
        self.search_entry = ttk.Entry(self, font=("Segoe UI", sf(11)))
        self.search_entry.pack(padx=15, pady=(0, 10), fill="x")
        self.search_entry.focus_set()
        self.search_entry.bind("<KeyRelease>", lambda e: self._populate())
        self.search_entry.bind("<Return>", lambda e: self._open_first_or_selected())
        self.search_entry.bind("<Down>", lambda e: self.listbox.focus_set())
        self.bind("<Escape>", lambda e: self.destroy())

        self.fuzzy_hint_label = ttk.Label(
            self, text="", foreground=COLOR_TEXT_MUTED, font=("Segoe UI", sf(8))
        )
        self.fuzzy_hint_label.pack(padx=15, pady=(0, 2), fill="x")

        list_frame = ttk.Frame(self)
        list_frame.pack(padx=15, pady=(0, 10), fill="both", expand=True)
        self.listbox = tk.Listbox(list_frame, font=("Segoe UI", sf(9)))
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scrollbar.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.listbox.bind("<Return>", lambda e: self._open_selected())
        self.listbox.bind("<Double-Button-1>", lambda e: self._open_selected())

        self.matched_names = []
        self._populate()

        ttk.Label(self, text=t("quicksearch_footer_hint"),
                  font=("Segoe UI", sf(8)), foreground=COLOR_TEXT_MUTED).pack(pady=(0, 10))

    def _populate(self):
        self.listbox.delete(0, tk.END)
        search = self.search_entry.get().strip()
        search_key = ingredient_sort_key(search) if search else ""
        self.matched_names = []
        self.fuzzy_hint_label.configure(text="")
        for recipe in self.app.recipes:
            if search_key and not recipe_matches_search(recipe, search_key):
                continue
            self.listbox.insert(tk.END, format_recipe_list_label(recipe))
            self.matched_names.append(recipe["name"])
        # Aucune correspondance exacte : propose les recettes les plus
        # proches (faute de frappe, accent oublié...) plutôt que de laisser
        # l'utilisateur face à une liste vide.
        if not self.matched_names and search_key and len(search) >= 3:
            suggestions = fuzzy_search_recipes(search, self.app.recipes)
            if suggestions:
                self.fuzzy_hint_label.configure(
                    text=t("quicksearch_fuzzy_hint", query=search)
                )
                for recipe in suggestions:
                    self.listbox.insert(tk.END, format_recipe_list_label(recipe))
                    self.matched_names.append(recipe["name"])
        if not self.matched_names:
            self.listbox.insert(tk.END, t("quicksearch_no_results"))

    def _open_selected(self):
        sel = self.listbox.curselection()
        if not sel or sel[0] >= len(self.matched_names):
            return
        name = self.matched_names[sel[0]]
        self.destroy()
        OneRecipeWindow(self.app, initial_recipe_name=name)

    def _open_first_or_selected(self):
        sel = self.listbox.curselection()
        if sel:
            self._open_selected()
        elif self.matched_names:
            name = self.matched_names[0]
            self.destroy()
            OneRecipeWindow(self.app, initial_recipe_name=name)


class OneRecipeWindow(tk.Toplevel):
    """Fenêtre pour afficher une recette précise (avec ses photos), avec
    quantités recalculées selon le nombre de personnes choisi."""

    def __init__(self, app, initial_recipe_name=None):
        super().__init__(app)
        self.app = app
        self.title(t("onerecipe_window_title"))
        screen_height = get_usable_screen_height(self)
        fit_window_to_workarea(self, gs(1650), screen_height, margin=18)
        safe_minsize(self, gs(760), gs(500))
        self.resizable(True, True)
        self.grab_set()
        self._gallery_thumb_refs = []
        self.current_recipe = None
        self.filtered_indices = []
        self._compact_vertical = screen_height < 760 or self.winfo_screenheight() < 760

        ttk.Label(self, text=t("onerecipe_choose_recipe_label"), font=("Segoe UI", sf(11), "bold")).pack(pady=(10, 5))

        top_frame = ttk.Frame(self)
        top_frame.pack(pady=(0, 5), fill="x", padx=15)
        ttk.Label(top_frame, text=t("onerecipe_search_label")).pack(side="left")
        self.search_entry = ttk.Entry(top_frame, width=16)
        self.search_entry.pack(side="left", padx=5, fill="x", expand=True)
        self.search_entry.bind("<KeyRelease>", lambda e: self._populate())
        ttk.Label(top_frame, text=t("onerecipe_sort_label")).pack(side="left", padx=(5, 2))
        self.sort_combo = ttk.Combobox(top_frame, values=[translate_sort_option(o) for o in RECIPE_SORT_OPTIONS], state="readonly", width=16)
        self.sort_combo.set(translate_sort_option(RECIPE_SORT_OPTIONS[0]))
        self.sort_combo.pack(side="left")
        self.sort_combo.bind("<<ComboboxSelected>>", lambda e: self._populate())
        ttk.Label(top_frame, text=t("onerecipe_category_label")).pack(side="left", padx=(5, 2))
        self.category_filter_combo = ttk.Combobox(
            top_frame, values=[t("common_all_categories")] + [translate_category_name(c) for c in RecipeFormWindow.CATEGORY_OPTIONS],
            state="readonly", width=14
        )
        self.category_filter_combo.set(t("common_all_categories"))
        self.category_filter_combo.pack(side="left")
        self.category_filter_combo.bind("<<ComboboxSelected>>", lambda e: self._populate())

        list_frame = ttk.Frame(self)
        list_frame.pack(pady=5, padx=15, fill="both")
        list_canvas = tk.Canvas(list_frame, height=80 if self._compact_vertical else 170, highlightthickness=0)
        list_scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=list_canvas.yview)
        self.rows_frame = ttk.Frame(list_canvas)
        self.rows_frame.bind("<Configure>", lambda e: list_canvas.configure(scrollregion=list_canvas.bbox("all")))
        list_canvas.create_window((0, 0), window=self.rows_frame, anchor="nw")
        list_canvas.configure(yscrollcommand=list_scrollbar.set)
        list_canvas.pack(side="left", fill="both", expand=True)
        list_scrollbar.pack(side="right", fill="y")
        self.selected_actual_index = None
        self._selected_row_widgets = None
        self._row_widgets = []  # [(actual_index, row_frame, label_widget), ...] pour la ligne affichée
        self._populate()

        # ---- Galerie de photos ----
        gallery_outer = ttk.Frame(self)
        gallery_outer.pack(fill="x", padx=15, pady=(10, 0))
        self.gallery_canvas = tk.Canvas(gallery_outer, height=80 if self._compact_vertical else 140, highlightthickness=0)
        gallery_scrollbar = ttk.Scrollbar(gallery_outer, orient="horizontal",
                                           command=self.gallery_canvas.xview)
        self.gallery_frame = ttk.Frame(self.gallery_canvas)
        self.gallery_frame.bind(
            "<Configure>", lambda e: self.gallery_canvas.configure(scrollregion=self.gallery_canvas.bbox("all"))
        )
        self.gallery_canvas.create_window((0, 0), window=self.gallery_frame, anchor="nw")
        self.gallery_canvas.configure(xscrollcommand=gallery_scrollbar.set)
        self.gallery_canvas.pack(fill="x")
        gallery_scrollbar.pack(fill="x")

        # ---- Nombre de personnes + ajustement rapide ----
        persons_frame = ttk.Frame(self)
        persons_frame.pack(pady=(10, 5))
        ttk.Label(persons_frame, text=t("onerecipe_persons_label")).grid(row=0, column=0, columnspan=4, pady=(0, 5))
        self.pers_entry = ttk.Entry(persons_frame, width=8)
        self.pers_entry.insert(0, "1")
        self.pers_entry.grid(row=1, column=0, padx=3)
        ttk.Button(persons_frame, text="−1", width=4,
                   command=lambda: self._adjust_persons(delta=-1)).grid(row=1, column=1, padx=3)
        ttk.Button(persons_frame, text="+1", width=4,
                   command=lambda: self._adjust_persons(delta=1)).grid(row=1, column=2, padx=3)
        ttk.Button(persons_frame, text="÷2", width=4,
                   command=lambda: self._adjust_persons(factor=0.5)).grid(row=1, column=3, padx=3)
        ttk.Button(persons_frame, text="×2", width=4,
                   command=lambda: self._adjust_persons(factor=2)).grid(row=1, column=4, padx=3)

        # ---- Actions : compactées sur les écrans peu hauts afin de ne jamais
        # repousser les contrôles sous la barre des tâches. ----
        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=5, padx=15, fill="x")
        primary_actions = [
            (t("onerecipe_btn_show"), self.show_recipe),
            (t("onerecipe_btn_add_to_shopping"), self.add_to_shopping_list),
            (t("onerecipe_btn_cooked"), self.mark_as_cooked),
            (t("onerecipe_btn_cooking_mode"), self.open_cooking_mode),
        ]
        secondary_actions = [
            (t("onerecipe_btn_export_pdf"), self.export_recipe_pdf),
            (t("onerecipe_btn_print"), self.print_recipe),
            (t("onerecipe_btn_qr"), self.show_qr_code),
            (t("onerecipe_btn_timers"), self.open_timers),
            (t("onerecipe_btn_cook_log"), self.open_cook_log),
            (t("onerecipe_btn_substitutions"), self.show_substitutions),
        ]
        for col in range(5 if self._compact_vertical else 4):
            btn_frame.columnconfigure(col, weight=1)
        if self._compact_vertical:
            for col, (label, command) in enumerate(primary_actions):
                ttk.Button(btn_frame, text=label, command=command).grid(row=0, column=col, padx=3, pady=2, sticky="ew")
            more = ttk.Button(btn_frame, text=t("onerecipe_more_actions"), style="Secondary.TButton")
            more.grid(row=0, column=4, padx=3, pady=2, sticky="ew")
            _ui_attach_more_menu(more, secondary_actions)
        else:
            action_buttons = primary_actions + secondary_actions
            for i, (label, command) in enumerate(action_buttons):
                row, col = divmod(i, 4)
                ttk.Button(btn_frame, text=label, command=command).grid(row=row, column=col, padx=4, pady=3, sticky="ew")

        # ---- Deux panneaux côte à côte : ingrédients/infos à gauche,
        # description/notes à droite. ----
        results_frame = ttk.Frame(self)
        results_frame.pack(pady=5, padx=15, fill="both", expand=True)

        left_results = ttk.Frame(results_frame)
        left_results.pack(side="left", fill="both", expand=True, padx=(0, 8))
        ttk.Label(left_results, text=t("onerecipe_ingredients_info_label"),
                  font=("Segoe UI", sf(9), "bold")).pack(anchor="w")
        self.result_text = tk.Text(left_results, width=48, height=7 if self._compact_vertical else 14, wrap="word", font=("Segoe UI", sf(10)))
        self.result_text.pack(fill="both", expand=True)

        right_results = ttk.Frame(results_frame)
        right_results.pack(side="left", fill="both", expand=True, padx=(8, 0))
        ttk.Label(right_results, text=t("onerecipe_description_notes_label"),
                  font=("Segoe UI", sf(9), "bold")).pack(anchor="w")
        self.description_result_text = tk.Text(right_results, width=48, height=7 if self._compact_vertical else 14, wrap="word", font=("Segoe UI", sf(10)))
        self.description_result_text.pack(fill="both", expand=True)

        # ---- Recettes similaires : suggestions basées sur la catégorie, les
        # étiquettes et les ingrédients en commun. ----
        self.similar_frame = ttk.Frame(self)
        self.similar_frame.pack(pady=(0, 10), padx=15, fill="x")

        # Espace vide en bas de la fenêtre, pour que "Recettes similaires"
        # ne se retrouve jamais collé au bord inférieur (ou caché derrière
        # la barre des tâches sur certains systèmes).
        tk.Frame(self, height=SCROLL_BOTTOM_PADDING, background=COLOR_BG).pack(fill="x")

        if initial_recipe_name:
            for idx, row, label in self._row_widgets:
                if self.app.recipes[idx]["name"] == initial_recipe_name:
                    self._select_row(idx, row, show=True)
                    break

    def _populate(self):
        for child in self.rows_frame.winfo_children():
            child.destroy()
        self._row_widgets = []
        self.filtered_indices = []
        search = self.search_entry.get().strip()
        search_key = ingredient_sort_key(search) if search else ""
        option = resolve_sort_option_input(self.sort_combo.get(), RECIPE_SORT_OPTIONS)
        category_filter = resolve_category_input(self.category_filter_combo.get(), RecipeFormWindow.CATEGORY_OPTIONS)
        indexed = list(enumerate(self.app.recipes))
        indexed = [pair for pair in indexed if recipe_matches_search(pair[1], search_key)]
        if category_filter and category_filter != t("common_all_categories"):
            indexed = [pair for pair in indexed if pair[1].get("category", "Autre") == category_filter]
        reverse = option in ("Ajoutées récemment",)
        indexed.sort(key=lambda pair: recipe_sort_key(pair[1], option), reverse=reverse)
        for row_index, (idx, recipe) in enumerate(indexed):
            row = tk.Frame(self.rows_frame, background=COLOR_BG)
            row.grid(row=row_index, column=0, sticky="ew", pady=1)
            label = tk.Label(row, text=format_recipe_list_label(recipe), background=COLOR_BG,
                              anchor="w", cursor="hand2", padx=4, font=("Segoe UI", sf(10)))
            label.pack(side="left", fill="x", expand=True)
            label.bind("<Button-1>", lambda e, i=idx, r=row: self._select_row(i, r))
            label.bind("<Double-Button-1>", lambda e, i=idx, r=row: self._select_row(i, r, show=True))
            ttk.Button(row, text=t("onerecipe_edit_button"), width=10,
                       command=lambda i=idx: self._edit_recipe(i)).pack(side="right", padx=4)
            self._row_widgets.append((idx, row, label))
            self.filtered_indices.append(idx)
        if self.selected_actual_index is not None:
            for idx, row, label in self._row_widgets:
                if idx == self.selected_actual_index:
                    row.configure(background=COLOR_ACCENT_LIGHT)
                    label.configure(background=COLOR_ACCENT_LIGHT)
                    self._selected_row_widgets = (row, label)
                    break

    def _select_row(self, actual_index, row, show=False):
        if self._selected_row_widgets is not None:
            prev_row, prev_label = self._selected_row_widgets
            try:
                prev_row.configure(background=COLOR_BG)
                prev_label.configure(background=COLOR_BG)
            except tk.TclError:
                pass  # la ligne précédente a pu être détruite par un _populate entre-temps
        label = None
        for idx, r, lbl in self._row_widgets:
            if r is row:
                label = lbl
                break
        row.configure(background=COLOR_ACCENT_LIGHT)
        if label is not None:
            label.configure(background=COLOR_ACCENT_LIGHT)
        self._selected_row_widgets = (row, label)
        self.selected_actual_index = actual_index
        if show:
            self.show_recipe()

    def _edit_recipe(self, index):
        win = RecipeFormWindow(self.app, recipe_index=index)
        self.wait_window(win)
        if not self.winfo_exists():
            return
        self.app.refresh_recipes()
        was_displaying_this = (
            self.current_recipe is not None
            and self.selected_actual_index == index
        )
        self._populate()
        if was_displaying_this and index < len(self.app.recipes):
            self.current_recipe = self.app.recipes[index]
            self._display_recipe(self.current_recipe)
        # Le formulaire modal pouvait passer devant cette fenêtre ; après sa
        # fermeture, la fiche doit redevenir la fenêtre active.
        try:
            self.deiconify()
            self.lift()
            self.focus_force()
            self.grab_set()
        except tk.TclError:
            pass

    def refresh_ui(self):
        """Rafraîchit la fiche sans détruire la fenêtre ni sa sélection."""
        if not self.winfo_exists():
            return
        self.title(t("onerecipe_window_title"))
        current_key = recipe_ref_key(self.current_recipe) if self.current_recipe else None
        self._populate()
        if current_key:
            for actual_index in self.filtered_indices:
                if actual_index < len(self.app.recipes) and recipe_ref_key(self.app.recipes[actual_index]) == current_key:
                    self.selected_actual_index = actual_index
                    self.current_recipe = self.app.recipes[actual_index]
                    self._display_recipe(self.current_recipe)
                    break

    def _refresh_gallery(self, recipe):
        for child in self.gallery_frame.winfo_children():
            child.destroy()
        self._gallery_thumb_refs = []

        images = get_recipe_images(recipe)
        if not images:
            ttk.Label(self.gallery_frame, text=t("onerecipe_no_photo")).pack(side="left", padx=10, pady=10)
        else:
            for fname in images:
                thumb = load_thumbnail(fname, size=(160, 120))
                cell = ttk.Frame(self.gallery_frame)
                cell.pack(side="left", padx=5, pady=5)
                if thumb is not None:
                    self._gallery_thumb_refs.append(thumb)
                    ttk.Label(cell, image=thumb).pack()
                else:
                    ttk.Label(cell, text=t("onerecipe_preview_unavailable")).pack()

        # Une photo ajoutée dans « J'ai cuisiné ça » reste distincte des
        # photos de la recette, mais elle doit être visible immédiatement
        # dans cette fiche. On n'affiche que la plus récente pour éviter de
        # transformer la galerie en journal complet.
        cook_log = sorted(
            [entry for entry in recipe.get("cook_log", []) if isinstance(entry, dict) and entry.get("photo")],
            key=lambda entry: entry.get("date", ""),
            reverse=True,
        )
        if cook_log:
            latest_photo = cook_log[0].get("photo")
            thumb = load_thumbnail(latest_photo, size=(160, 120))
            cell = ttk.Frame(self.gallery_frame)
            cell.pack(side="left", padx=5, pady=5)
            ttk.Label(cell, text=t("onerecipe_latest_cook_photo")).pack()
            if thumb is not None:
                self._gallery_thumb_refs.append(thumb)
                ttk.Label(cell, image=thumb).pack()
            else:
                ttk.Label(cell, text=t("onerecipe_preview_unavailable")).pack()

    def _adjust_persons(self, factor=None, delta=None):
        try:
            current = parse_positive_number(self.pers_entry.get())
        except (ValueError, TypeError):
            current = 1.0
        if delta is not None:
            current = current + delta
        if factor is not None:
            current = current * factor
        current = max(0.5, current)
        if current == int(current):
            current = int(current)
        self.pers_entry.delete(0, tk.END)
        self.pers_entry.insert(0, str(current))
        if self.current_recipe is not None:
            self._display_recipe(self.current_recipe)

    def show_recipe(self):
        if self.selected_actual_index is None or self.selected_actual_index >= len(self.app.recipes):
            messagebox.showinfo(t("common_info"), t("onerecipe_select_recipe_first"))
            return
        idx = self.selected_actual_index
        recipe = self.app.recipes[idx]
        is_new_selection = self.current_recipe is not recipe
        self.current_recipe = recipe
        if is_new_selection:
            self.pers_entry.delete(0, tk.END)
            self.pers_entry.insert(0, str(recipe.get("default_persons", 1) or 1))
            record_recipe_view(recipe)
        self._display_recipe(recipe)

    def add_to_shopping_list(self):
        if self.current_recipe is None:
            messagebox.showinfo(t("common_info"), t("onerecipe_display_first"))
            return
        try:
            persons = parse_positive_number(self.pers_entry.get())
        except ValueError:
            messagebox.showerror(t("common_error"), t("onerecipe_invalid_persons"))
            return
        self.app.shopping_selection[recipe_ref_key(self.current_recipe)] = persons
        messagebox.showinfo(
            t("onerecipe_added_to_shopping_title"),
            t("onerecipe_added_to_shopping_message", name=self.current_recipe['name'], persons=persons)
        )

    def mark_as_cooked(self):
        if self.current_recipe is None:
            messagebox.showinfo(t("common_info"), t("onerecipe_display_first"))
            return
        try:
            persons = parse_positive_number(self.pers_entry.get())
        except (ValueError, TypeError):
            messagebox.showerror(t("common_error"), t("onerecipe_invalid_persons"), parent=self)
            return

        target_name = self.current_recipe.get("name")
        target_id = self.current_recipe.get("id")
        recipes = load_recipes()
        target = find_recipe_by_id(recipes, target_id) or find_recipe_by_name(recipes, target_name)
        if target is None:
            messagebox.showerror(t("common_error"), t("onerecipe_display_first"), parent=self)
            return

        def _on_log_done(note, comment, photo_filename, rating=0, cooked_persons=None):
            current = record_recipe_cooking(
                target_id, target_name, note, comment, photo_filename,
                rating, cooked_persons
            )
            try:
                self.app.refresh_recipes()
                # refresh_recipes recharge les objets depuis recipes.json ; la
                # fiche doit utiliser cette instance canonique, sinon elle peut
                # continuer à afficher l'ancien journal en mémoire.
                refreshed = find_recipe_by_id(self.app.recipes, target_id) or find_recipe_by_name(self.app.recipes, target_name)
                self.current_recipe = refreshed or current
                if self.selected_actual_index is not None:
                    self._populate()
                self._display_recipe(self.current_recipe)
                pantry = load_pantry()
                if pantry and ask_yes_no(
                        t("onerecipe_pantry_decrement_title"),
                        t("onerecipe_pantry_decrement_prompt", name=target_name, persons=persons),
                        parent=self):
                    count = decrement_pantry_for_recipe(current, persons)
                    if count:
                        messagebox.showinfo(t("onerecipe_pantry_updated_title"),
                                            t("onerecipe_pantry_updated_message", count=count), parent=self)
                    else:
                        messagebox.showinfo(t("common_info"), t("onerecipe_pantry_none_decremented"), parent=self)
                messagebox.showinfo(
                    t("onerecipe_marked_title"),
                    t("onerecipe_marked_message", name=target_name),
                    parent=self
                )
                try:
                    self.deiconify()
                    self.lift()
                    self.focus_force()
                    self.grab_set()
                except tk.TclError:
                    pass
            except Exception as exc:
                raise CookingRecordedError(str(exc)) from exc

        cooked_persons_display = (
            int(persons) if float(persons).is_integer() else persons
        )
        CookLogEntryDialog(
            self.app, target_name, _on_log_done,
            persons=cooked_persons_display
        )

    def open_cook_log(self):
        if self.current_recipe is None:
            messagebox.showinfo(t("common_info"), t("onerecipe_display_first"))
            return
        # Recharge la recette pour refléter une cuisson enregistrée depuis
        # une autre fenêtre ou juste avant l'ouverture du journal.
        latest_recipes = load_recipes()
        latest = find_recipe_by_id(latest_recipes, self.current_recipe.get("id")) or find_recipe_by_name(
            latest_recipes, self.current_recipe.get("name", "")
        )
        CookLogWindow(self.app, latest or self.current_recipe)

    def show_substitutions(self):
        if self.current_recipe is None:
            messagebox.showinfo(t("common_info"), t("onerecipe_display_first"))
            return
        recipe = self.current_recipe
        entries = []
        seen_keys = set()
        for ing in recipe["ingredients"]:
            key = ingredient_sort_key(ing["name"])
            if key in seen_keys:
                continue
            subs = get_display_ingredient_substitutions(ing["name"])
            if subs:
                seen_keys.add(key)
                entries.append((ing["name"], subs))
        if not entries:
            messagebox.showinfo(
                t("onerecipe_no_substitutes_title"),
                t("onerecipe_no_substitutes_message")
            )
            return

        win = tk.Toplevel(self)

        _ui_bind_escape(win)
        win.title(t("onerecipe_substitutes_title", name=recipe['name']))
        fit_window_to_workarea(win, gs(520), gs(520), margin=14)
        safe_minsize(win, 440, 400)
        win.resizable(True, True)
        win.grab_set()

        ttk.Label(win, text=t("onerecipe_substitutes_heading", name=recipe['name']),
                  font=("Segoe UI", sf(12), "bold"), wraplength=480, justify="center").pack(pady=(15, 5))
        ttk.Label(
            win, text=t("onerecipe_substitutes_disclaimer"),
            font=("Segoe UI", sf(8)), foreground=COLOR_TEXT_MUTED, justify="center"
        ).pack(pady=(0, 10))

        container = ttk.Frame(win)
        container.pack(fill="both", expand=True, padx=15, pady=5)
        canvas = tk.Canvas(container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        for ing_name, subs in entries:
            ttk.Label(inner, text=translate_ingredient_name(ing_name).capitalize(), font=("Segoe UI", sf(10), "bold"),
                      foreground=COLOR_ACCENT_DARK).pack(anchor="w", pady=(10, 2))
            for sub in subs:
                note = f" — {sub['note']}" if sub.get("note") else ""
                ttk.Label(inner, text=f"  • {sub['nom']}{note}", wraplength=440,
                          justify="left").pack(anchor="w")

        tk.Frame(win, height=SCROLL_BOTTOM_PADDING, background=COLOR_BG).pack(fill="x")
        ttk.Button(win, text=t("onerecipe_close_button"), command=win.destroy).pack(pady=10)

    def _display_recipe(self, recipe):
        try:
            persons = parse_positive_number(self.pers_entry.get())
        except ValueError:
            messagebox.showerror(t("common_error"), t("onerecipe_invalid_persons"))
            return

        self._refresh_gallery(recipe)

        self.result_text.delete("1.0", tk.END)
        self.description_result_text.delete("1.0", tk.END)
        cat = translate_category_name(recipe.get("category", "Autre"))
        star = "⭐ " if recipe.get("favorite") else ""
        self.result_text.insert(tk.END, f"=== {star}[{cat}] {recipe['name']} ({persons} pers.) ===\n\n")

        rating = recipe.get("rating", 0)
        if rating:
            self.result_text.insert(tk.END, t("onerecipe_rating_label", stars=rating_stars(rating)) + "\n\n")

        info_bits = []
        if recipe.get("prep_time"):
            info_bits.append(t("onerecipe_prep_label", time=recipe['prep_time']))
        if recipe.get("cook_time"):
            info_bits.append(t("onerecipe_cook_label", time=recipe['cook_time']))
        if recipe.get("difficulty"):
            info_bits.append(t("onerecipe_difficulty_label", value=translate_difficulty_name(recipe['difficulty'])))
        if info_bits:
            self.result_text.insert(tk.END, " | ".join(info_bits) + "\n\n")

        allergens = recipe.get("allergens") or []
        if allergens:
            self.result_text.insert(tk.END, t("onerecipe_allergens_label", list=", ".join(translate_allergen_name(a) for a in allergens)) + "\n\n")

        for ing in recipe["ingredients"]:
            qty = ingredient_quantity_for_persons(ing, persons)
            if qty is None:
                quantity_display = t("quantity_unspecified")
                unit = ""
            else:
                quantity_display = qty
                unit = f" {translate_unit_name(ing['unit'])}" if ing["unit"] else ""
            self.result_text.insert(tk.END, f"- {translate_ingredient_name(ing['name']).capitalize()} : {quantity_display}{unit}\n")

        cost, cost_known, cost_total = compute_recipe_cost(recipe, persons)
        if cost_known:
            partial = "" if cost_known == cost_total else t("onerecipe_cost_partial", known=cost_known, total=cost_total)
            self.result_text.insert(tk.END, "\n" + t("onerecipe_cost_label", cost=f"{cost:.2f}", partial=partial) + "\n")

        nutrition, nutri_known, nutri_total = compute_recipe_nutrition(recipe, persons)
        if nutri_known:
            partial = "" if nutri_known == nutri_total else t(
                "onerecipe_nutrition_partial", known=nutri_known, total=nutri_total
            )
            self.result_text.insert(
                tk.END,
                t(
                    "onerecipe_nutrition_label", partial=partial,
                    kcal=f"{nutrition['kcal']:.0f}", protein=f"{nutrition['protein_g']:.0f}",
                    carbs=f"{nutrition['carbs_g']:.0f}", fat=f"{nutrition['fat_g']:.0f}"
                )
            )

        if nutri_known < nutri_total:
            self.result_text.insert(tk.END, "\n" + t("nutrition_incomplete_notice") + "\n")

        description = recipe.get("description", "").strip()
        if description:
            self.description_result_text.insert(tk.END, t("onerecipe_description_heading", text=description))
        personal_notes = recipe.get("personal_notes", "").strip()
        if personal_notes:
            self.description_result_text.insert(tk.END, t("onerecipe_notes_heading", text=personal_notes))
        family_opinion = (recipe.get("family_opinion") or "").strip()
        improvement_notes = (recipe.get("improvement_notes") or "").strip()
        actual_difficulty = (recipe.get("actual_difficulty") or "").strip()
        if family_opinion:
            self.description_result_text.insert(tk.END, t("onerecipe_family_opinion_heading", text=family_opinion))
        if improvement_notes:
            self.description_result_text.insert(tk.END, t("onerecipe_improvement_notes_heading", text=improvement_notes))
        if actual_difficulty:
            self.description_result_text.insert(tk.END, t("onerecipe_actual_difficulty_heading", value=translate_difficulty_name(actual_difficulty)))

        # Affichage immédiat de la dernière cuisson enregistrée dans la fiche
        # (le journal complet reste accessible par son bouton dédié).
        cook_log = sorted(
            [entry for entry in recipe.get("cook_log", []) if isinstance(entry, dict)],
            key=lambda entry: entry.get("date", ""),
            reverse=True,
        )
        if cook_log:
            latest = cook_log[0]
            self.description_result_text.insert(
                tk.END,
                t("onerecipe_latest_cook_heading", count=recipe.get("times_cooked", 0) or 0),
            )
            date_value = latest.get("date", "")
            try:
                date_value = datetime.fromisoformat(date_value).strftime("%d/%m/%Y à %H:%M")
            except (TypeError, ValueError):
                date_value = str(date_value or "?")
            self.description_result_text.insert(
                tk.END, t("onerecipe_latest_cook_date", date=date_value) + "\n"
            )
            cooked_persons = latest.get("persons")
            if cooked_persons not in (None, ""):
                self.description_result_text.insert(
                    tk.END, t("cooklog_entry_persons", persons=cooked_persons) + "\n"
                )
            entry_rating = int(latest.get("rating", 0) or 0)
            if entry_rating:
                self.description_result_text.insert(
                    tk.END,
                    t("cooklog_entry_rating", stars="★" * entry_rating + "☆" * (5 - entry_rating)) + "\n",
                )
            latest_note = (latest.get("note") or "").strip()
            latest_comment = (latest.get("comment") or "").strip()
            if latest_note:
                self.description_result_text.insert(
                    tk.END, t("cooklog_note_heading") + " " + latest_note + "\n"
                )
            if latest_comment:
                self.description_result_text.insert(
                    tk.END, t("cooklog_comment_heading") + " " + latest_comment + "\n"
                )
            self.description_result_text.insert(tk.END, "\n")
        if not description and not personal_notes and not family_opinion and not improvement_notes and not actual_difficulty:
            if not cook_log:
                self.description_result_text.insert(tk.END, t("onerecipe_no_description_notes"))

        self._render_similar_recipes(recipe)

    def _render_similar_recipes(self, recipe):
        for child in self.similar_frame.winfo_children():
            child.destroy()
        similar = find_similar_recipes(recipe, self.app.recipes, limit=5)
        if not similar:
            return
        ttk.Label(self.similar_frame, text=t("onerecipe_similar_label"),
                  font=("Segoe UI", sf(9), "bold"), foreground=COLOR_ACCENT_DARK).pack(anchor="w")
        links_frame = ttk.Frame(self.similar_frame)
        links_frame.pack(anchor="w", pady=(2, 0))
        for other in similar:
            cat = translate_category_name(other.get("category", "Autre"))
            btn = tk.Label(
                links_frame, text=f"[{cat}] {other['name']}", foreground=COLOR_ACCENT_DARK,
                cursor="hand2", font=("Segoe UI", sf(9), "underline")
            )
            btn.pack(side="left", padx=(0, 12))
            btn.bind("<Button-1>", lambda e, name=other["name"]: self._open_similar_recipe(name))

    def _open_similar_recipe(self, recipe_name):
        for idx, row, label in self._row_widgets:
            if self.app.recipes[idx]["name"] == recipe_name:
                self._select_row(idx, row, show=True)
                return
        # La recette n'est pas dans la liste actuellement filtrée (recherche/
        # catégorie en cours) : on réinitialise les filtres pour la retrouver.
        self.search_entry.delete(0, tk.END)
        self.category_filter_combo.set(t("common_all_categories"))
        self._populate()
        for idx, row, label in self._row_widgets:
            if self.app.recipes[idx]["name"] == recipe_name:
                self._select_row(idx, row, show=True)
                return

    @staticmethod
    def _build_recipe_pdf(path, recipe, persons):
        c = pdf_canvas.Canvas(path, pagesize=A4)
        width, height = A4
        draw_recipe_content(c, recipe, persons, width, height)
        c.save()

    def export_recipe_pdf(self):
        if not REPORTLAB_AVAILABLE:
            messagebox.showerror(t("common_module_missing"), t("onerecipe_pdf_module_missing"))
            return
        if self.current_recipe is None:
            messagebox.showinfo(t("common_info"), t("onerecipe_display_first"))
            return
        try:
            persons = parse_positive_number(self.pers_entry.get())
        except ValueError:
            messagebox.showerror(t("common_error"), t("onerecipe_invalid_persons"))
            return

        recipe = self.current_recipe
        path = filedialog.asksaveasfilename(
            title=t("onerecipe_export_pdf_title"),
            defaultextension=".pdf",
            filetypes=[("Fichier PDF", "*.pdf")],
            initialfile=f"{sanitize_windows_filename(recipe.get('name'), 'recette')}.pdf"
        )
        if not path:
            return

        try:
            self._build_recipe_pdf(path, recipe, persons)
        except Exception as e:
            messagebox.showerror(t("common_error"), t("onerecipe_export_failed", error=e))
            return
        messagebox.showinfo(t("onerecipe_export_success_title"), t("onerecipe_export_success_message", path=path))

    def print_recipe(self):
        if not REPORTLAB_AVAILABLE:
            messagebox.showerror(t("common_module_missing"), t("onerecipe_print_module_missing"))
            return
        if self.current_recipe is None:
            messagebox.showinfo(t("common_info"), t("onerecipe_display_first"))
            return
        try:
            persons = parse_positive_number(self.pers_entry.get())
        except ValueError:
            messagebox.showerror(t("common_error"), t("onerecipe_invalid_persons"))
            return

        recipe = self.current_recipe
        temp_path = get_temp_pdf_path("recette")
        try:
            self._build_recipe_pdf(temp_path, recipe, persons)
        except Exception as e:
            messagebox.showerror(t("common_error"), t("onerecipe_print_failed", error=e))
            return

        print_document(self, temp_path, f"« {recipe['name']} »")

    def show_qr_code(self):
        if not QRCODE_AVAILABLE:
            messagebox.showerror(
                t("common_module_missing"),
                t("onerecipe_qr_module_missing")
            )
            return
        if not PIL_AVAILABLE:
            messagebox.showerror(t("common_module_missing"), t("onerecipe_qr_pillow_missing"))
            return
        if self.current_recipe is None:
            messagebox.showinfo(t("common_info"), t("onerecipe_display_first"))
            return
        try:
            persons = parse_positive_number(self.pers_entry.get())
        except ValueError:
            messagebox.showerror(t("common_error"), t("onerecipe_invalid_persons"))
            return
        QRCodeWindow(self.app, self.current_recipe, persons)

    def open_timers(self):
        recipe = self.current_recipe
        label_text = recipe["name"] if recipe else t("onerecipe_default_timer_label")
        default_minutes = 10
        if recipe is not None:
            try:
                if recipe.get("cook_time"):
                    default_minutes = max(1, round(float(recipe["cook_time"])))
                elif recipe.get("prep_time"):
                    default_minutes = max(1, round(float(recipe["prep_time"])))
            except (TypeError, ValueError):
                pass

        # Cette fenêtre est modale (grab_set), ce qui bloquerait toute autre
        # fenêtre de l'application — y compris la fenêtre des minuteurs, qui
        # doit rester utilisable en même temps qu'on consulte la recette.
        # On relâche donc le grab ici ; les deux fenêtres restent ensuite
        # utilisables librement en parallèle.
        try:
            self.grab_release()
        except tk.TclError:
            pass

        # Une seule fenêtre de minuteurs pour toute l'application : si elle
        # est déjà ouverte, on y ajoute simplement un minuteur de plus au
        # lieu d'en ouvrir une deuxième.
        existing = getattr(self.app, "timers_window", None)
        if existing is not None and existing.winfo_exists():
            existing.add_timer(label_text, default_minutes)
            existing.deiconify()
            existing.lift()
            existing.focus_force()
        else:
            self.app.timers_window = TimersWindow(self.app, label_text, default_minutes)

    def open_cooking_mode(self):
        if self.current_recipe is None:
            messagebox.showinfo(t("common_info"), t("onerecipe_display_first"))
            return
        try:
            persons = parse_positive_number(self.pers_entry.get())
        except ValueError:
            messagebox.showerror(t("common_error"), t("onerecipe_invalid_persons"))
            return
        # CookingModeWindow n'a pas son propre grab_set() : sans relâcher
        # celui de cette fenêtre, le mode cuisine serait inutilisable (même
        # pas fermable) tant que "Voir une recette précise" reste ouverte.
        try:
            self.grab_release()
        except tk.TclError:
            pass
        CookingModeWindow(self.app, self.current_recipe, persons, owner=self)


class CookingModeWindow(tk.Toplevel):
    """Affichage plein écran, en gros caractères et sans menus, d'une
    recette — pratique à consulter en cuisinant, posé à côté des
    fourneaux."""

    def __init__(self, app, recipe, persons, owner=None):
        super().__init__(app)
        self.app = app
        self.recipe = recipe
        self.persons = persons
        self.owner_window = owner
        self.title(t("cookingmode_title", name=recipe['name']))
        self.configure(bg="white")
        self._is_fullscreen = False
        # Une fenêtre maximisée (plutôt qu'un vrai plein écran) s'ouvre
        # instantanément : le vrai plein écran provoque, sur certains
        # systèmes Windows, un blocage de plusieurs secondes le temps que la
        # transition d'affichage se fasse. Le plein écran natif reste
        # disponible via F11 pour qui le souhaite.
        try:
            self.state("zoomed")
        except tk.TclError:
            fit_window_to_workarea(self, self.winfo_screenwidth(), get_usable_screen_height(self), margin=0, center=False)
        self.tts_engine = None
        self.tts_thread = None
        self._speech_poll_id = None
        self._speech_stop = threading.Event()
        self._speech_done = threading.Event()
        self._closing = False
        self.bind("<Destroy>", self._speech_window_destroyed, add="+")
        self.speech_volume = 1.0       # 0.0 (muet) à 1.0 (plein volume)
        self.bind("<Escape>", lambda e: self._on_close())
        self.bind("<F11>", lambda e: self._toggle_fullscreen())
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        top_bar = tk.Frame(self, bg="white")
        top_bar.pack(fill="x", pady=10)
        tk.Button(top_bar, text=t("cookingmode_close_button"), font=("Segoe UI", sf(13)),
                  command=self._on_close).pack(side="right", padx=30)
        tk.Button(top_bar, text=t("cookingmode_cooked_button"), font=("Segoe UI", sf(13)),
                  command=self.mark_as_cooked).pack(side="right", padx=(10, 0))
        tk.Label(top_bar, text=t("cookingmode_fullscreen_hint"), font=("Segoe UI", sf(9)),
                 bg="white", fg="#999").pack(side="right", padx=10)

        volume_frame = tk.Frame(top_bar, bg="white")
        volume_frame.pack(side="right", padx=(10, 0))
        tk.Button(volume_frame, text="🔊+", font=("Segoe UI", sf(11)), width=4,
                  command=lambda: self._adjust_volume(0.1)).pack(side="right")
        self.volume_label = tk.Label(volume_frame, text=t("cookingmode_volume_percent", percent=100), font=("Segoe UI", sf(10)),
                                      bg="white", fg="#666", width=5)
        self.volume_label.pack(side="right", padx=3)
        tk.Button(volume_frame, text="🔉−", font=("Segoe UI", sf(11)), width=4,
                  command=lambda: self._adjust_volume(-0.1)).pack(side="right")

        self.speech_button = tk.Button(top_bar, text=t("cookingmode_speech_button"), font=("Segoe UI", sf(13)),
                                        command=self.toggle_speech)
        self.speech_button.pack(side="right", padx=(10, 0))

        pers_frame = tk.Frame(top_bar, bg="white")
        pers_frame.pack(side="left", padx=30)
        tk.Button(pers_frame, text="−", font=("Segoe UI", sf(14), "bold"), width=3,
                  command=lambda: self._adjust(-1)).pack(side="left")
        self.pers_label = tk.Label(pers_frame, text=t("cookingmode_persons_suffix", persons=self._fmt(persons)),
                                    font=("Segoe UI", sf(14)), bg="white")
        self.pers_label.pack(side="left", padx=10)
        tk.Button(pers_frame, text="+", font=("Segoe UI", sf(14), "bold"), width=3,
                  command=lambda: self._adjust(1)).pack(side="left")

        outer = tk.Frame(self, bg="white")
        outer.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(outer, bg="white", highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=self.canvas.yview)
        self.content = tk.Frame(self.canvas, bg="white")
        self.content.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self._content_id = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.canvas.bind("<Configure>", self._resize_content)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True, padx=16)
        scrollbar.pack(side="right", fill="y")

        self._text_size = 0
        self._checks = {}
        self.timer_section = tk.Frame(self, bg="white")
        self.timer_section.pack(fill="x", before=outer, padx=16)
        self.timer_rows = []
        self._timer_number = 0
        timer_heading = tk.Frame(self.timer_section, bg="white")
        timer_heading.pack(fill="x", pady=(6, 4))
        tk.Label(timer_heading, text=t("timers_title"), bg="white",
                 font=("Segoe UI", sf(18), "bold")).pack(side="left")
        ttk.Button(timer_heading, text="+", width=3, command=self.add_timer).pack(side="left", padx=12)
        ttk.Button(timer_heading, text="A−", width=4,
                   command=lambda: self._change_text_size(-2)).pack(side="right")
        ttk.Button(timer_heading, text="A+", width=4,
                   command=lambda: self._change_text_size(2)).pack(side="right", padx=6)
        self.timer_canvas = tk.Canvas(self.timer_section, bg="white", height=180, highlightthickness=0)
        timer_scroll = ttk.Scrollbar(self.timer_section, orient="vertical", command=self.timer_canvas.yview)
        timer_scroll.pack(side="right", fill="y")
        self.timer_canvas.pack(fill="x", expand=True)
        self.timer_canvas.configure(yscrollcommand=timer_scroll.set)
        self.timer_frame = tk.Frame(self.timer_canvas, bg="white")
        self._timer_window_id = self.timer_canvas.create_window((0, 0), window=self.timer_frame, anchor="nw")
        self._timer_columns = 0
        self.timer_canvas.bind("<Configure>", self._timer_canvas_resized)
        self.timer_frame.bind("<Configure>", self._resize_timers)
        self.recipe_content = tk.Frame(self.content, bg="white")
        self.recipe_content.pack(fill="x")
        self.add_timer()
        self._render()

    def add_timer(self, seconds=None, label=None):
        self._timer_number += 1
        row = TimerRow(self.timer_frame, self,
                       label or t("cookingmode_timer_number", number=self._timer_number), 10)
        row.set_text_size(self._text_size)
        row.grid(row=len(self.timer_rows), column=0, sticky="new", padx=6, pady=6)
        self.timer_rows.append(row)
        if seconds is not None:
            minutes, secs = divmod(seconds, 60)
            row.minutes_entry.delete(0, tk.END)
            row.minutes_entry.insert(0, str(minutes))
            row.seconds_entry.delete(0, tk.END)
            row.seconds_entry.insert(0, str(secs))
            row.reset()
        # Le minuteur est prepare : l'utilisateur choisit quand le demarrer.
        self.timer_canvas.after_idle(self._layout_timers)

    @staticmethod
    def _timer_grid_size(width, card_width, card_height, count, available_height):
        columns = max(1, min(max(1, count), width // max(1, card_width)))
        rows = max(1, math.ceil(count / columns))
        visible_rows = min(rows, 2, max(1, available_height // max(1, card_height)))
        return columns, visible_rows * card_height + 12

    def _timer_canvas_resized(self, event):
        self.timer_canvas.itemconfigure(self._timer_window_id, width=max(1, event.width))
        self._layout_timers()

    def _layout_timers(self):
        if not self.timer_rows or not self.timer_canvas.winfo_exists():
            return
        # Mesurer les controles reels, notamment avec la mise a l'echelle Windows.
        card_width = max(gs(380), max(row.winfo_reqwidth() for row in self.timer_rows) + 12)
        card_height = max(row.winfo_reqheight() for row in self.timer_rows) + 12
        columns, height = self._timer_grid_size(
            self.timer_canvas.winfo_width(), card_width, card_height,
            len(self.timer_rows), max(180, self.winfo_height() // 3))
        for column in range(max(columns, self._timer_columns)):
            self.timer_frame.columnconfigure(column, weight=1 if column < columns else 0,
                                             uniform="timers" if column < columns else "")
        self._timer_columns = columns
        for index, row in enumerate(self.timer_rows):
            row.grid(row=index // columns, column=index % columns,
                     sticky="new", padx=6, pady=6)
        self.timer_canvas.configure(height=max(180, height))

    def _resize_timers(self, event):
        self.timer_canvas.configure(scrollregion=self.timer_canvas.bbox("all"))
        self._layout_timers()

    def _change_text_size(self, delta):
        self._text_size = max(-4, min(12, self._text_size + delta))
        for row in self.timer_rows:
            row.set_text_size(self._text_size)
        self._render()
        self.timer_canvas.after_idle(self._layout_timers)

    def _recipe_font(self, size):
        return sf(size + self._text_size)

    def _check(self, key):
        if key not in self._checks:
            self._checks[key] = tk.BooleanVar(self, value=False)
        return self._checks[key]

    @staticmethod
    def _step_durations(text):
        # Durees entieres explicites ; pour une plage, proposer la borne haute.
        pattern = r"(?<![\d.,])\b(\d+)(?:\s*[-–àa]\s*(\d+))?\s*(minutes?|mins?|minutos?|heures?|hours?|hrs?|stunden?|horas?|secondes?|seconds?|secs?|segundos?|sekunden?|h|s)\b"
        result = []
        for match in re.finditer(pattern, text, re.IGNORECASE):
            unit = match.group(3).lower()
            factor = 3600 if unit.startswith(('h', 'stund')) else 1 if unit.startswith('s') else 60
            seconds = int(match.group(2) or match.group(1)) * factor
            if seconds > 0:
                result.append((match.group(0), seconds))
        return result

    def remove_timer(self, row):
        if row not in self.timer_rows:
            return
        if len(self.timer_rows) == 1:
            row.reset()
            return
        row.cancel()
        self.timer_rows.remove(row)
        row.destroy()
        self._layout_timers()

    def _resize_content(self, event):
        self.canvas.itemconfigure(self._content_id, width=max(1, event.width))
        self._layout_recipe(event.width)

    def _layout_recipe(self, width):
        if not hasattr(self, "ingredients_panel"):
            return
        wide = width >= gs(1000)
        if getattr(self, "_wide_recipe", None) == wide:
            return
        self._wide_recipe = wide
        self.ingredients_panel.grid_forget()
        self.steps_panel.grid_forget()
        self.recipe_columns.columnconfigure(0, weight=2 if wide else 1, uniform="recipe")
        self.recipe_columns.columnconfigure(1, weight=3 if wide else 0, uniform="recipe" if wide else "")
        self.ingredients_panel.grid(row=0, column=0, sticky="new", padx=(0, 24 if wide else 0))
        self.steps_panel.grid(row=0 if wide else 1, column=1 if wide else 0, sticky="new")

    @staticmethod
    def _wrap_panel(event):
        for label in event.widget.winfo_children():
            if isinstance(label, (tk.Label, tk.Checkbutton)):
                label.configure(wraplength=max(1, event.width - 12))

    def mark_as_cooked(self):
        try:
            persons = parse_positive_number(self.persons)
        except (ValueError, TypeError):
            messagebox.showerror(t("common_error"), t("onerecipe_invalid_persons"), parent=self)
            return
        target_name = self.recipe.get("name")
        target_id = self.recipe.get("id")
        recipes = load_recipes()
        target = find_recipe_by_id(recipes, target_id) or find_recipe_by_name(recipes, target_name)
        if target is None:
            return
        def _on_log_done(note, comment, photo_filename, rating=0, cooked_persons=None):
            current = record_recipe_cooking(
                target_id, target_name, note, comment, photo_filename,
                rating, cooked_persons
            )
            try:
                self.app.refresh_recipes()
                refreshed = find_recipe_by_id(self.app.recipes, target_id) or find_recipe_by_name(
                    self.app.recipes, target_name
                )
                self.recipe = refreshed or current
                pantry = load_pantry()
                if pantry and ask_yes_no(
                        t("onerecipe_pantry_decrement_title"),
                        t("onerecipe_pantry_decrement_prompt", name=target_name, persons=self._fmt(persons)),
                        parent=self):
                    count = decrement_pantry_for_recipe(self.recipe, persons)
                    if count:
                        messagebox.showinfo(t("onerecipe_pantry_updated_title"),
                                            t("onerecipe_pantry_updated_message", count=count), parent=self)
                    else:
                        messagebox.showinfo(t("common_info"), t("onerecipe_pantry_none_decremented"), parent=self)
                messagebox.showinfo(t("onerecipe_marked_title"), t("onerecipe_marked_message", name=target_name), parent=self)
                target_window = self.owner_window if self.owner_window is not None else self
                try:
                    target_window.deiconify()
                    target_window.lift()
                    target_window.focus_force()
                    target_window.grab_set()
                except tk.TclError:
                    pass
            except Exception as exc:
                raise CookingRecordedError(str(exc)) from exc

        cooked_persons_display = int(persons) if float(persons).is_integer() else persons
        CookLogEntryDialog(
            self.app, target_name, _on_log_done,
            persons=cooked_persons_display
        )

    def toggle_speech(self):
        if self.tts_thread is not None and self.tts_thread.is_alive():
            self.stop_speech()
        else:
            self.start_speech()

    def start_speech(self):
        if not PYTTSX3_AVAILABLE:
            messagebox.showerror(
                t("common_module_missing"),
                t("cookingmode_tts_module_missing")
            )
            return
        text = (self.recipe.get("description") or "").strip()
        if not text:
            messagebox.showinfo(
                t("common_info"), t("cookingmode_no_description_to_read")
            )
            return

        if self._closing:
            return
        if self._speech_poll_id is not None:
            self.after_cancel(self._speech_poll_id)
            self._speech_poll_id = None
        self._speech_stop = threading.Event()
        self._speech_done = threading.Event()
        stop_event, done_event = self._speech_stop, self._speech_done
        self.speech_button.config(text=t("cookingmode_speech_stop_button"))

        def _run():
            try:
                engine = pyttsx3.init()
                engine.setProperty("volume", self.speech_volume)
                self.tts_engine = engine
                if not stop_event.is_set():
                    engine.say(text)
                    if not stop_event.is_set():
                        engine.runAndWait()
                    else:
                        engine.stop()
            except Exception as exc:
                log_internal_error("suppressed_exception", exc)
            finally:
                self.tts_engine = None
                # Aucun appel Tk depuis le thread vocal, meme apres fermeture.
                done_event.set()

        self.tts_thread = threading.Thread(target=_run, daemon=True)
        self.tts_thread.start()
        self._poll_speech()

    def _poll_speech(self):
        self._speech_poll_id = None
        if self._closing:
            return
        if self._speech_done.is_set():
            self.speech_button.config(text=t("cookingmode_speech_button"))
        else:
            self._speech_poll_id = self.after(100, self._poll_speech)

    def _speech_window_destroyed(self, event):
        if event.widget is self:
            self._close_speech()

    def _close_speech(self):
        self._closing = True
        self._speech_stop.set()
        if self._speech_poll_id is not None:
            try:
                self.after_cancel(self._speech_poll_id)
            except tk.TclError:
                pass
            self._speech_poll_id = None
        self.stop_speech()

    def stop_speech(self):
        self._speech_stop.set()
        if self.tts_engine is not None:
            try:
                self.tts_engine.stop()
            except Exception as exc:
                log_internal_error("suppressed_exception", exc)
        if not self._closing:
            try:
                self.speech_button.config(text=t("cookingmode_speech_button"))
            except tk.TclError:
                pass

    def _adjust_volume(self, delta):
        self.speech_volume = round(max(0.0, min(1.0, self.speech_volume + delta)), 2)
        self.volume_label.config(text=t("cookingmode_volume_percent", percent=round(self.speech_volume * 100)))
        if self.tts_engine is not None:
            try:
                self.tts_engine.setProperty("volume", self.speech_volume)
            except Exception as exc:
                log_internal_error("suppressed_exception", exc)

    def _on_close(self):
        if any(row.running for row in self.timer_rows):
            if not ask_yes_no(t("timers_title"), t("cookingmode_close_running"), parent=self):
                return
        self._close_speech()
        for row in self.timer_rows:
            row.cancel()
        self.destroy()

    def _toggle_fullscreen(self):
        self._is_fullscreen = not self._is_fullscreen
        try:
            self.attributes("-fullscreen", self._is_fullscreen)
        except tk.TclError:
            self._is_fullscreen = False

    @staticmethod
    def _fmt(value):
        return int(value) if value == int(value) else value

    def _adjust(self, delta):
        self.persons = max(0.5, self.persons + delta)
        self.pers_label.config(text=t("cookingmode_persons_suffix", persons=self._fmt(self.persons)))
        self._render()

    def _render(self):
        for child in self.recipe_content.winfo_children():
            child.destroy()

        recipe = self.recipe
        star = "⭐ " if recipe.get("favorite") else ""
        tk.Label(self.recipe_content, text=f"{star}{recipe['name']}", font=("Segoe UI", self._recipe_font(34), "bold"),
                 bg="white", wraplength=1000, justify="center").pack(pady=(10, 5))

        info_bits = []
        if recipe.get("prep_time"):
            info_bits.append(t("cookingmode_prep_label", time=recipe['prep_time']))
        if recipe.get("cook_time"):
            info_bits.append(t("cookingmode_cook_label", time=recipe['cook_time']))
        if recipe.get("difficulty"):
            info_bits.append(t("cookingmode_difficulty_label", value=translate_difficulty_name(recipe['difficulty'])))
        if info_bits:
            tk.Label(self.recipe_content, text="   |   ".join(info_bits), font=("Segoe UI", self._recipe_font(16)),
                     bg="white", fg="#555").pack(pady=(0, 20))

        self.recipe_content.bind("<Configure>", self._wrap_panel)
        self.recipe_columns = tk.Frame(self.recipe_content, bg="white")
        self.recipe_columns.pack(fill="x", pady=(0, 30))
        self.ingredients_panel = tk.Frame(self.recipe_columns, bg="white")
        self.steps_panel = tk.Frame(self.recipe_columns, bg="white")
        self.ingredients_panel.bind("<Configure>", self._wrap_panel)
        self.steps_panel.bind("<Configure>", self._wrap_panel)
        self._wide_recipe = None

        tk.Label(self.ingredients_panel, text=t("cookingmode_ingredients_heading"), font=("Segoe UI", self._recipe_font(22), "bold"),
                 bg="white").pack(pady=(10, 8), anchor="w", fill="x")
        for index, ing in enumerate(recipe["ingredients"]):
            qty = ingredient_quantity_for_persons(ing, self.persons)
            if qty is None:
                quantity_display = t("quantity_unspecified")
                unit = ""
            else:
                quantity_display = qty
                unit = f" {translate_unit_name(ing['unit'])}" if ing["unit"] else ""
            tk.Checkbutton(self.ingredients_panel, variable=self._check(("ingredient", index)), text=f"{translate_ingredient_name(ing['name']).capitalize()} : {quantity_display}{unit}",
                     font=("Segoe UI", self._recipe_font(18)), bg="white", anchor="w", justify="left",
                     wraplength=1000).pack(fill="x", pady=3, anchor="w")

        description = recipe.get("description", "").strip()
        if description:
            tk.Label(self.steps_panel, text=t("cookingmode_preparation_heading"), font=("Segoe UI", self._recipe_font(22), "bold"),
                     bg="white").pack(pady=(10, 8), anchor="w", fill="x")
            steps = [part.strip() for part in description.splitlines() if part.strip()]
            for index, step in enumerate(steps):
                tk.Checkbutton(self.steps_panel, text=step, variable=self._check(("step", index)),
                               font=("Segoe UI", self._recipe_font(16)), bg="white", justify="left",
                               anchor="w", wraplength=1000).pack(fill="x", anchor="w", pady=6)
                for duration, seconds in self._step_durations(step):
                    ttk.Button(self.steps_panel, text="⏱ " + duration,
                               command=lambda sec=seconds, label=duration: self.add_timer(sec, label)).pack(anchor="w", padx=24, pady=2)

        personal_notes = recipe.get("personal_notes", "").strip()
        if personal_notes:
            tk.Label(self.steps_panel, text=t("cookingmode_personal_notes_heading"), font=("Segoe UI", self._recipe_font(20), "bold"),
                     bg="white", fg="#555").pack(pady=(20, 8), anchor="w", fill="x")
            tk.Label(self.steps_panel, text=personal_notes, font=("Segoe UI", self._recipe_font(14)), bg="white",
                     fg="#555", justify="left", anchor="w", wraplength=1000).pack(fill="x", anchor="w")

        self._layout_recipe(self.canvas.winfo_width())


class IngredientSearchWindow(tk.Toplevel):
    """Recherche inversée : à partir d'un ingrédient, retrouver toutes les
    recettes qui l'utilisent."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title(t("ingsearch_title"))
        fit_window_to_workarea(self, gs(960), gs(600), margin=18)
        self.grab_set()

        ttk.Label(self, text=t("ingsearch_question_label"),
                  font=("Segoe UI", sf(11), "bold")).pack(pady=(10, 5))

        search_frame = ttk.Frame(self)
        search_frame.pack(fill="x", padx=15, pady=(0, 5))
        ttk.Label(search_frame, text="🔍").pack(side="left")
        self.search_entry = ttk.Entry(search_frame)
        self.search_entry.pack(side="left", fill="x", expand=True, padx=5)
        self.search_entry.bind("<KeyRelease>", lambda e: self._populate_ingredients())

        list_frame = ttk.Frame(self)
        list_frame.pack(fill="both", padx=15, pady=5)
        self.ing_listbox = tk.Listbox(list_frame, height=10, font=("Segoe UI", sf(9)))
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.ing_listbox.yview)
        self.ing_listbox.configure(yscrollcommand=scrollbar.set)
        self.ing_listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.ing_listbox.bind("<Double-Button-1>", lambda e: self.search_recipes())
        self._populate_ingredients()

        ttk.Button(self, text=t("ingsearch_view_recipes_button"),
                   command=self.search_recipes).pack(pady=8)

        self.result_label = ttk.Label(self, text="", font=("Segoe UI", sf(9)), foreground=COLOR_TEXT_MUTED)
        self.result_label.pack(padx=15, anchor="w")

        result_frame = ttk.Frame(self)
        result_frame.pack(pady=5, padx=15, fill="both", expand=True)
        self.result_listbox = tk.Listbox(result_frame, height=12, font=("Segoe UI", sf(9)))
        result_scrollbar = ttk.Scrollbar(result_frame, orient="vertical", command=self.result_listbox.yview)
        self.result_listbox.configure(yscrollcommand=result_scrollbar.set)
        self.result_listbox.pack(side="left", fill="both", expand=True)
        result_scrollbar.pack(side="right", fill="y")
        self.result_listbox.bind("<Double-Button-1>", lambda e: self.open_selected_recipe())
        self.matched_recipe_names = []

        ttk.Button(self, text=t("ingsearch_view_selected_button"),
                   command=self.open_selected_recipe).pack(pady=(5, 10))

    def _populate_ingredients(self):
        search = self.search_entry.get().strip()
        search_key = ingredient_sort_key(search) if search else ""
        self.ing_listbox.delete(0, tk.END)
        self.displayed_ing_names = []
        for name in self.app.ingredient_names:
            if search_key and search_key not in ingredient_sort_key(name) \
                    and search_key not in ingredient_sort_key(translate_ingredient_name(name)):
                continue
            self.ing_listbox.insert(tk.END, translate_ingredient_name(name))
            self.displayed_ing_names.append(name)

    def search_recipes(self):
        sel = self.ing_listbox.curselection()
        if not sel:
            messagebox.showinfo(t("common_info"), t("manageing_select_ingredient_first"))
            return
        target_name = self.displayed_ing_names[sel[0]]
        target_key = ingredient_sort_key(target_name)

        matches = []
        for recipe in self.app.recipes:
            for ing in recipe["ingredients"]:
                if ingredient_sort_key(ing["name"]) == target_key:
                    matches.append((recipe, ing))
                    break

        self.result_listbox.delete(0, tk.END)
        self.matched_recipe_names = []
        if not matches:
            self.result_label.config(text=t("ingsearch_no_recipe_uses", name=translate_ingredient_name(target_name)))
            return

        self.result_label.config(
            text=t("ingsearch_recipes_using", name=translate_ingredient_name(target_name), count=len(matches))
        )
        for recipe, ing in matches:
            star = "⭐ " if recipe.get("favorite") else ""
            cat = translate_category_name(recipe.get("category", "Autre"))
            qty = ing["quantity"]
            if qty is None:
                qty = t("quantity_unspecified")
            elif qty == int(qty):
                qty = int(qty)
            unit = f" {translate_unit_name(ing['unit'])}" if ing["unit"] and ing["quantity"] is not None else ""
            self.result_listbox.insert(
                tk.END, t("ingsearch_result_line", star=star, cat=cat, name=recipe['name'], qty=qty, unit=unit)
            )
            self.matched_recipe_names.append(recipe["name"])

    def open_selected_recipe(self):
        sel = self.result_listbox.curselection()
        if not sel:
            messagebox.showinfo(t("common_info"), t("ingsearch_select_result_first"))
            return
        recipe_name = self.matched_recipe_names[sel[0]]
        OneRecipeWindow(self.app, initial_recipe_name=recipe_name)


class TimerRow(tk.Frame):
    """Un minuteur réglable et indépendant, affiché comme une ligne à
    l'intérieur de TimersWindow. Quand il arrive à zéro, la ligne clignote
    en rouge et un signal sonore retentit jusqu'à ce que l'utilisateur
    interagisse avec elle (démarrer, réinitialiser, ou simplement cliquer
    dessus)."""

    def __init__(self, parent, timers_window, label=None, minutes=10):
        super().__init__(parent, background=COLOR_CARD, highlightbackground=COLOR_BORDER,
                          highlightthickness=1)
        if label is None:
            label = t("onerecipe_default_timer_label")
        self.timers_window = timers_window
        self.remaining_seconds = max(0, int(minutes) * 60)
        self.running = False
        self._started = False
        self._deadline = None
        self.finished = False
        self._after_id = None
        self._flash_after_id = None
        self._flash_on = False

        top_row = tk.Frame(self, background=COLOR_CARD)
        top_row.pack(fill="x", padx=8, pady=(8, 2))
        self.name_entry = ttk.Entry(top_row, width=18)
        self.name_entry.insert(0, label)
        self.name_entry.pack(side="left")
        self.display_label = tk.Label(top_row, text=self._format_time(), font=("Segoe UI", sf(18), "bold"),
                                       background=COLOR_CARD, foreground=COLOR_ACCENT_DARK, width=7)
        self.display_label.pack(side="left", padx=10)
        delete_timer_btn = ttk.Button(top_row, text="🗑", width=3,
                   command=lambda: self.timers_window.remove_timer(self))
        delete_timer_btn.pack(side="right")
        add_tooltip(delete_timer_btn, t("tooltip_delete_timer"))

        bottom_row = tk.Frame(self, background=COLOR_CARD)
        bottom_row.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Label(bottom_row, text=t("timerrow_minutes_label"), style="Card.TLabel").pack(side="left")
        self.minutes_entry = ttk.Entry(bottom_row, width=4)
        self.minutes_entry.insert(0, str(minutes))
        self.minutes_entry.pack(side="left", padx=(2, 8))
        ttk.Label(bottom_row, text=t("timerrow_seconds_label"), style="Card.TLabel").pack(side="left")
        self.seconds_entry = ttk.Entry(bottom_row, width=4)
        self.seconds_entry.insert(0, "0")
        self.seconds_entry.pack(side="left", padx=(2, 8))

        self.start_button = ttk.Button(bottom_row, text="▶️", width=3, command=self.start)
        self.start_button.pack(side="left", padx=2)
        add_tooltip(self.start_button, t("tooltip_start_timer"))
        self.pause_button = ttk.Button(bottom_row, text="⏸️", width=3, command=self.pause, state="disabled")
        self.pause_button.pack(side="left", padx=2)
        add_tooltip(self.pause_button, t("tooltip_pause_timer"))
        reset_btn = ttk.Button(bottom_row, text="🔄", width=3, command=self.reset)
        reset_btn.pack(side="left", padx=2)
        add_tooltip(reset_btn, t("tooltip_reset_timer"))

        extend_row = tk.Frame(self, background=COLOR_CARD)
        extend_row.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(extend_row, text="+1 min", command=lambda: self.extend(60)).pack(side="left", padx=2)
        ttk.Button(extend_row, text="+5 min", command=lambda: self.extend(300)).pack(side="left", padx=2)

        # Cliquer n'importe où sur la ligne (ou sur le gros affichage du
        # temps) fait taire l'alarme si le minuteur est terminé.
        self.bind("<Button-1>", lambda e: self._stop_flash())
        self.display_label.bind("<Button-1>", lambda e: self._stop_flash())

        self._refresh_display()
        self.bind("<Destroy>", lambda e: self.cancel() if e.widget is self else None, add="+")

    def set_text_size(self, delta):
        """Adapter textes et controles de cette carte sans recreer le minuteur."""
        if not hasattr(self, "_font_sizes"):
            self._font_sizes = []
            style = ttk.Style(self)
            pending = list(self.winfo_children())
            while pending:
                widget = pending.pop()
                pending.extend(widget.winfo_children())
                if isinstance(widget, (ttk.Button, ttk.Label, ttk.Entry)):
                    base_style = widget.cget("style") or widget.winfo_class()
                    spec = (widget.cget("font") if isinstance(widget, ttk.Entry)
                            else style.lookup(base_style, "font")) or "TkDefaultFont"
                    font = tkfont.Font(root=self, font=spec)
                    if isinstance(widget, ttk.Entry):
                        widget.configure(font=font)
                    else:
                        custom_style = "CookingTimer_" + str(widget).replace(".", "_") + "." + base_style
                        style.configure(custom_style, font=font)
                        widget.configure(style=custom_style)
                elif isinstance(widget, tk.Label):
                    font = tkfont.Font(root=self, font=widget.cget("font"))
                    widget.configure(font=font)
                else:
                    continue
                self._font_sizes.append((font, int(font.actual("size"))))
        for font, base in self._font_sizes:
            size = max(6, abs(base) + sf(delta))
            font.configure(size=-size if base < 0 else size)

    def _format_time(self):
        mins, secs = divmod(max(0, self.remaining_seconds), 60)
        return f"{mins:02d}:{secs:02d}"

    def _refresh_display(self):
        self.display_label.config(text=self._format_time())

    def start(self):
        if self.finished:
            self._stop_flash()
        if self.running:
            return
        if not self._started or self.remaining_seconds <= 0:
            try:
                minutes = int(self.minutes_entry.get().strip() or 0)
                seconds = int(self.seconds_entry.get().strip() or 0)
            except ValueError:
                messagebox.showerror(t("common_error"), t("timerrow_error_invalid_duration"))
                return
            if minutes < 0 or seconds < 0:
                messagebox.showerror(t("common_error"), t("timerrow_error_invalid_duration"), parent=self.winfo_toplevel())
                return
            self.remaining_seconds = minutes * 60 + seconds
            if self.remaining_seconds <= 0:
                messagebox.showinfo(t("common_info"), t("timerrow_set_duration_first"))
                return
        self._started = True
        self._deadline = time.monotonic() + self.remaining_seconds
        self.running = True
        self.minutes_entry.config(state="disabled")
        self.seconds_entry.config(state="disabled")
        self.start_button.config(state="disabled")
        self.pause_button.config(state="normal")
        self._tick()

    def extend(self, seconds):
        if self.finished:
            self._stop_flash()
        if self.running:
            self._deadline += seconds
            self.remaining_seconds = max(0, math.ceil(self._deadline - time.monotonic()))
        else:
            if not self._started:
                try:
                    minutes = int(self.minutes_entry.get().strip() or 0)
                    secs = int(self.seconds_entry.get().strip() or 0)
                    if minutes < 0 or secs < 0:
                        raise ValueError()
                except ValueError:
                    messagebox.showerror(t("common_error"), t("timerrow_error_invalid_duration"), parent=self.winfo_toplevel())
                    return
                self.remaining_seconds = minutes * 60 + secs
            self.remaining_seconds += seconds
            self._started = False
            minutes, secs = divmod(self.remaining_seconds, 60)
            for field, value in ((self.minutes_entry, minutes), (self.seconds_entry, secs)):
                field.config(state="normal")
                field.delete(0, tk.END)
                field.insert(0, str(value))
        self._refresh_display()

    def _tick(self):
        self._after_id = None
        if not self.running:
            return
        self.remaining_seconds = max(0, math.ceil(self._deadline - time.monotonic()))
        self._refresh_display()
        if self.remaining_seconds <= 0:
            self._on_finished()
            return
        self._after_id = self.after(200, self._tick)

    def pause(self):
        if self.running:
            self.remaining_seconds = max(0, math.ceil(self._deadline - time.monotonic()))
            self._refresh_display()
        self.running = False
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except Exception as exc:
                log_internal_error("suppressed_exception", exc)
            self._after_id = None
        self.start_button.config(state="normal")
        self.pause_button.config(state="disabled")

    def reset(self):
        self._started = False
        self.running = False
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except Exception as exc:
                log_internal_error("suppressed_exception", exc)
            self._after_id = None
        self._stop_flash()
        self.minutes_entry.config(state="normal")
        self.seconds_entry.config(state="normal")
        self.start_button.config(state="normal")
        self.pause_button.config(state="disabled")
        try:
            minutes = int(self.minutes_entry.get().strip() or 0)
            seconds = int(self.seconds_entry.get().strip() or 0)
        except ValueError:
            minutes, seconds = 0, 0
        self.remaining_seconds = max(0, minutes * 60 + seconds)
        self._refresh_display()

    def _on_finished(self):
        self.running = False
        self.finished = True
        self._after_id = None
        self.pause_button.config(state="disabled")
        self.start_button.config(state="normal")
        self.minutes_entry.config(state="normal")
        self.seconds_entry.config(state="normal")
        self._refresh_display()
        self._start_flash()

    def _set_children_bg(self, widget, color):
        for child in widget.winfo_children():
            if isinstance(child, tk.Frame):
                child.configure(background=color)
                self._set_children_bg(child, color)
            elif isinstance(child, tk.Label):
                child.configure(background=color)

    def _start_flash(self):
        self._flash_on = False
        self._flash_step()

    def _flash_step(self):
        if not self.finished:
            return
        self._flash_on = not self._flash_on
        color = COLOR_ERROR if self._flash_on else COLOR_CARD
        text_color = "white" if self._flash_on else COLOR_ACCENT_DARK
        self.configure(background=color)
        self._set_children_bg(self, color)
        self.display_label.config(background=color, foreground=text_color)
        try:
            self.bell()
        except tk.TclError:
            pass
        self._flash_after_id = self.after(500, self._flash_step)

    def _stop_flash(self):
        if not self.finished and self._flash_after_id is None:
            return
        self.finished = False
        if self._flash_after_id is not None:
            try:
                self.after_cancel(self._flash_after_id)
            except Exception as exc:
                log_internal_error("suppressed_exception", exc)
            self._flash_after_id = None
        self.configure(background=COLOR_CARD)
        self._set_children_bg(self, COLOR_CARD)
        self.display_label.config(background=COLOR_CARD, foreground=COLOR_ACCENT_DARK)

    def cancel(self):
        """Arrête tout minuterie/clignotement en cours (appelé à la
        fermeture de la fenêtre ou à la suppression de cette ligne)."""
        self.running = False
        self.finished = False
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except Exception as exc:
                log_internal_error("suppressed_exception", exc)
        if self._flash_after_id is not None:
            try:
                self.after_cancel(self._flash_after_id)
            except Exception as exc:
                log_internal_error("suppressed_exception", exc)



class CookLogEntryDialog(tk.Toplevel):
    """Ajoute les informations d'une cuisson au journal de la recette."""

    def __init__(self, app, recipe_name, on_done, persons=None):
        super().__init__(app)
        self.app = app
        self.on_done = on_done
        self.persons = persons
        self.photo_path = None
        self.title(t("cooklogentry_title"))
        fit_window_to_workarea(self, gs(560), gs(620), margin=14)
        safe_minsize(self, gs(480), gs(500))
        self.resizable(True, True)
        self.grab_set()

        ttk.Label(
            self, text=t("cooklogentry_heading", name=recipe_name),
            font=("Segoe UI", sf(12), "bold"),
            wraplength=520, justify="center"
        ).pack(pady=(15, 2))
        ttk.Label(
            self, text=t("cooklogentry_intro_v32"),
            font=("Segoe UI", sf(8)), foreground=COLOR_TEXT_MUTED,
            justify="center", wraplength=520
        ).pack(pady=(0, 10))

        form = ttk.Frame(self)
        form.pack(fill="both", expand=True, padx=18)

        if persons is not None:
            ttk.Label(
                form,
                text=t("cooklogentry_persons_label", persons=persons),
                font=("Segoe UI", sf(9), "bold")
            ).pack(anchor="w", pady=(0, 8))

        ttk.Label(
            form, text=t("cooklogentry_note_label"),
            font=("Segoe UI", sf(9), "bold")
        ).pack(anchor="w")
        self.note_text = tk.Text(
            form, height=4, wrap="word", font=("Segoe UI", sf(10))
        )
        self.note_text.pack(fill="x", pady=(3, 10))

        ttk.Label(
            form, text=t("cooklogentry_comment_label"),
            font=("Segoe UI", sf(9), "bold")
        ).pack(anchor="w")
        self.comment_text = tk.Text(
            form, height=4, wrap="word", font=("Segoe UI", sf(10))
        )
        self.comment_text.pack(fill="x", pady=(3, 10))

        rating_frame = ttk.Frame(form)
        rating_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(
            rating_frame, text=t("cooklogentry_rating_label"),
            font=("Segoe UI", sf(9), "bold")
        ).pack(side="left")
        self.rating_combo = ttk.Combobox(
            rating_frame,
            values=["—", "★", "★★", "★★★", "★★★★", "★★★★★"],
            state="readonly", width=10
        )
        self.rating_combo.current(0)
        self.rating_combo.pack(side="left", padx=(10, 0))

        photo_frame = ttk.Frame(form)
        photo_frame.pack(fill="x", pady=(0, 10))
        self.photo_label = ttk.Label(
            photo_frame, text=t("cooklogentry_no_photo_chosen"),
            foreground=COLOR_TEXT_MUTED
        )
        self.photo_label.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ttk.Button(
            photo_frame, text=t("cooklogentry_choose_photo_button"),
            command=self.choose_photo
        ).pack(side="right")

        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=(5, 15))
        ttk.Button(
            btn_frame, text=t("common_save_button"),
            style="Primary.TButton", command=self.save
        ).grid(row=0, column=0, padx=5)
        ttk.Button(
            btn_frame, text=t("cooklogentry_skip_button"),
            style="Secondary.TButton", command=self.skip
        ).grid(row=0, column=1, padx=5)

        self.protocol("WM_DELETE_WINDOW", self.skip)

    def choose_photo(self):
        path = filedialog.askopenfilename(
            title=t("cooklogentry_choose_photo_title"),
            filetypes=[("Images", "*.jpg *.jpeg *.png *.webp *.gif *.bmp")]
        )
        if path:
            self.photo_path = path
            self.photo_label.config(
                text=os.path.basename(path), foreground=COLOR_TEXT
            )

    def save(self):
        note = self.note_text.get("1.0", "end-1c").strip()
        comment = self.comment_text.get("1.0", "end-1c").strip()
        photo_filename = (
            copy_image_to_store(self.photo_path) if self.photo_path else None
        )
        rating = max(0, self.rating_combo.current())
        try:
            self.on_done(note, comment, photo_filename, rating, self.persons)
        except CookingRecordedError as exc:
            log_internal_error('cook_log_post_commit', exc)
            messagebox.showwarning(t('common_info'), t('cooklog_saved_followup_failed', error=exc), parent=self)
            self.destroy()
            return
        except Exception as exc:
            if photo_filename:
                delete_image_file(photo_filename)
            log_internal_error("save_cook_log", exc)
            messagebox.showerror(
                t("common_error"), t("cooklogentry_save_failed", error=exc), parent=self
            )
            return
        self.destroy()

    def skip(self):
        try:
            self.on_done("", "", None, 0, self.persons)
        except CookingRecordedError as exc:
            log_internal_error('cook_log_post_commit', exc)
            messagebox.showwarning(t('common_info'), t('cooklog_saved_followup_failed', error=exc), parent=self)
            self.destroy()
            return
        except Exception as exc:
            log_internal_error("save_cook_log", exc)
            messagebox.showerror(
                t("common_error"), t("cooklogentry_save_failed", error=exc), parent=self
            )
            return
        self.destroy()


class CookLogWindow(tk.Toplevel):
    """Affiche l'historique des fois où une recette a été cuisinée, avec les
    notes et photos éventuellement ajoutées à chaque fois (la plus récente
    en premier)."""

    def __init__(self, app, recipe):
        super().__init__(app)
        self.app = app
        self.recipe = recipe
        self.title(t("cooklog_title", name=recipe['name']))
        fit_window_to_workarea(self, gs(480), gs(600), margin=18)
        safe_minsize(self, gs(400), gs(400))
        self.resizable(True, True)
        self.grab_set()

        ttk.Label(self, text=t("cooklog_heading", name=recipe['name']), font=("Segoe UI", sf(13), "bold"),
                  wraplength=440, justify="center").pack(pady=(15, 2))
        times_cooked = recipe.get("times_cooked", 0)
        ttk.Label(self, text=t("cooklog_times_cooked", count=times_cooked),
                  font=("Segoe UI", sf(9)), foreground=COLOR_TEXT_MUTED).pack(pady=(0, 2))
        rated_entries = [int(e.get("rating", 0) or 0) for e in recipe.get("cook_log", []) if int(e.get("rating", 0) or 0) > 0]
        if rated_entries:
            ttk.Label(self, text=t("cooklog_rating_summary", avg=f"{sum(rated_entries)/len(rated_entries):.1f}", count=len(rated_entries)),
                      font=("Segoe UI", sf(9), "bold"), foreground=COLOR_ACCENT_DARK).pack(pady=(0, 10))

        container = ttk.Frame(self)
        container.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        canvas = tk.Canvas(container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        rows_frame = ttk.Frame(canvas)
        rows_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=rows_frame, anchor="n")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        _ui_bind_local_mousewheel(canvas, rows_frame, _on_mousewheel)

        self._thumb_refs = []
        cook_log = list(recipe.get("cook_log", []))
        cook_log.sort(key=lambda e: e.get("date", ""), reverse=True)

        if not cook_log:
            ttk.Label(
                rows_frame,
                text=t("cooklog_no_entry"),
                foreground=COLOR_TEXT_MUTED, justify="center"
            ).pack(pady=30)

        for entry in cook_log:
            entry_card = tk.Frame(rows_frame, background=COLOR_CARD, highlightbackground=COLOR_BORDER,
                                   highlightthickness=1)
            entry_card.pack(fill="x", pady=6, padx=2)
            try:
                date_display = datetime.fromisoformat(entry["date"]).strftime("%d/%m/%Y")
            except (KeyError, ValueError, TypeError):
                date_display = entry.get("date", "?")
            ttk.Label(entry_card, text=date_display, font=("Segoe UI", sf(10), "bold"),
                      style="Card.TLabel", foreground=COLOR_ACCENT_DARK).pack(anchor="w", padx=10, pady=(8, 2))

            persons = entry.get("persons")
            if persons not in (None, ""):
                ttk.Label(
                    entry_card,
                    text=t("cooklog_entry_persons", persons=persons),
                    style="Card.TLabel",
                    foreground=COLOR_TEXT_MUTED,
                    font=("Segoe UI", sf(8))
                ).pack(anchor="w", padx=10, pady=(0, 4))

            photo_filename = entry.get("photo")
            if photo_filename:
                thumb = load_thumbnail(photo_filename, size=(220, 160))
                if thumb is not None:
                    self._thumb_refs.append(thumb)
                    tk.Label(entry_card, image=thumb, background=COLOR_CARD).pack(padx=10, pady=4)

            entry_rating = int(entry.get("rating", 0) or 0)
            if entry_rating > 0:
                ttk.Label(entry_card, text=t("cooklog_entry_rating", stars="★" * entry_rating + "☆" * (5-entry_rating)),
                          style="Card.TLabel", foreground=COLOR_ACCENT_DARK, font=("Segoe UI", sf(9), "bold")).pack(anchor="w", padx=10, pady=(2, 4))

            note = (entry.get("note") or "").strip()
            if note:
                ttk.Label(
                    entry_card, text=t("cooklog_note_heading"),
                    style="Card.TLabel", font=("Segoe UI", sf(8), "bold"),
                    foreground=COLOR_ACCENT_DARK
                ).pack(anchor="w", padx=10, pady=(2, 1))
                ttk.Label(
                    entry_card, text=note, style="Card.TLabel",
                    wraplength=420, justify="left"
                ).pack(anchor="w", padx=10, pady=(0, 6))

            comment = (entry.get("comment") or "").strip()
            if comment:
                ttk.Label(
                    entry_card, text=t("cooklog_comment_heading"),
                    style="Card.TLabel", font=("Segoe UI", sf(8), "bold"),
                    foreground=COLOR_ACCENT_DARK
                ).pack(anchor="w", padx=10, pady=(2, 1))
                ttk.Label(
                    entry_card, text=comment, style="Card.TLabel",
                    wraplength=420, justify="left"
                ).pack(anchor="w", padx=10, pady=(0, 8))

            if not note and not comment:
                ttk.Label(
                    entry_card, text=t("cooklog_no_note"),
                    style="Card.TLabel", foreground=COLOR_TEXT_MUTED,
                    font=("Segoe UI", sf(8))
                ).pack(anchor="w", padx=10, pady=(0, 8))


class TimersWindow(tk.Toplevel):
    """Fenêtre unique regroupant plusieurs minuteurs indépendants et
    réglables, pour chronométrer différentes étapes d'une recette en même
    temps (ex. un pour les pâtes, un pour la sauce...). Le bouton
    "➕ Ajouter un minuteur" empile un nouveau minuteur sous les précédents."""

    def __init__(self, app, initial_label=None, initial_minutes=10):
        super().__init__(app)
        self.app = app
        if initial_label is None:
            initial_label = t("onerecipe_default_timer_label")
        self.title(t("timers_title"))
        fit_window_to_workarea(self, gs(380), gs(560), margin=14)
        safe_minsize(self, gs(340), gs(300))
        self.resizable(True, True)
        # Reste visible au premier plan même par-dessus une autre fenêtre
        # maximisée (ex. le mode cuisine) : on veut toujours voir les
        # minuteurs en cours, quoi qu'on affiche par ailleurs.
        try:
            self.attributes("-topmost", True)
        except tk.TclError:
            pass

        ttk.Label(self, text=t("timers_title"), font=("Segoe UI", sf(13), "bold")).pack(pady=(15, 5))
        ttk.Label(
            self, text=t("timers_intro"),
            font=("Segoe UI", sf(8)), foreground=COLOR_TEXT_MUTED, justify="center"
        ).pack(pady=(0, 8))

        container = ttk.Frame(self)
        container.pack(fill="both", expand=True, padx=10)
        canvas = tk.Canvas(container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        self.rows_frame = ttk.Frame(canvas)
        self.rows_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.rows_frame, anchor="n")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.timer_rows = []
        self.add_timer(initial_label, initial_minutes)

        ttk.Button(self, text=t("timers_add_button"),
                   command=lambda: self.add_timer()).pack(pady=10)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def add_timer(self, label=None, minutes=10):
        if label is None:
            label = t("onerecipe_default_timer_label")
        row = TimerRow(self.rows_frame, self, label, minutes)
        row.pack(fill="x", pady=6, padx=4)
        self.timer_rows.append(row)
        self.update_idletasks()

    def remove_timer(self, row):
        row.cancel()
        row.destroy()
        if row in self.timer_rows:
            self.timer_rows.remove(row)

    def _on_close(self):
        for row in list(self.timer_rows):
            row.cancel()
        if getattr(self.app, "timers_window", None) is self:
            self.app.timers_window = None
        self.destroy()



MULTI_QR_PREFIX = "MRQ1"
MOBILE_QR_MAX_BYTES = 800


class QrImportIncompleteError(Exception):
    def __init__(self, received, total):
        super().__init__(f"incomplete QR set: {received}/{total}")
        self.received = received
        self.total = total


class QrImportMixedBatchesError(Exception):
    pass


class QrImportChecksumError(Exception):
    pass


def _base36(number):
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
    number = int(number)
    if number == 0:
        return "0"
    chars = []
    while number:
        number, rem = divmod(number, 36)
        chars.append(alphabet[rem])
    return "".join(reversed(chars))


def _mobile_qr_checksum(text_value):
    """Exact equivalent du computeChecksum() JavaScript mobile.

    JavaScript charCodeAt() travaille sur des unités UTF-16 ; on reproduit ce
    comportement afin que les lots contenant aussi des emoji ou caractères
    hors BMP aient exactement la même somme de contrôle sur Windows/mobile.
    """
    data = text_value.encode("utf-16-le")
    hash_value = 5381
    for i in range(0, len(data), 2):
        code_unit = data[i] | (data[i + 1] << 8)
        hash_value = ((hash_value << 5) + hash_value + code_unit) & 0xFFFFFFFF
    return _base36(hash_value)


def _qr_mojibake_score(text_value):
    """Mesure les marqueurs typiques d'un mauvais décodage QR UTF-8."""
    score = 100 * text_value.count("\ufffd")
    for char in text_value:
        if char in "ÃÂâð":
            score += 8
        elif "\uff61" <= char <= "\uff9f":  # katakana demi-largeur issu de Shift-JIS
            score += 12
        elif "\x80" <= char <= "\x9f":
            score += 12
    return score


def _qr_chunk_repair_candidates(text_value):
    """Retourne les lectures réversibles possibles d'une partie de QR.

    ZBar peut choisir un encodage différent pour chaque image d'un même lot :
    UTF-8 correct, Latin-1, Windows-1252 ou Shift-JIS. Chaque conversion reste
    un simple candidat ; seule la somme de contrôle du contenu complet permet
    ensuite de l'accepter.
    """
    candidates = [text_value]
    for mistaken_encoding in ("latin-1", "cp1252", "shift_jis"):
        try:
            candidate = text_value.encode(mistaken_encoding).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        if candidate not in candidates:
            candidates.append(candidate)
    # Les textes présentant le moins de traces de mojibake sont essayés en
    # premier. L'ordre initial départage les égalités sans modifier les données.
    initial_order = {candidate: index for index, candidate in enumerate(candidates)}
    return sorted(
        candidates,
        key=lambda candidate: (_qr_mojibake_score(candidate), initial_order[candidate]),
    )


def _split_mobile_qr_parts(content, max_chunk_bytes=MOBILE_QR_MAX_BYTES):
    if len(content.encode("utf-8")) <= max_chunk_bytes:
        return [content]

    chunks = []
    current = []
    current_bytes = 0
    for ch in content:
        size = len(ch.encode("utf-8"))
        if current and current_bytes + size > max_chunk_bytes:
            chunks.append("".join(current))
            current = []
            current_bytes = 0
        current.append(ch)
        current_bytes += size
    if current:
        chunks.append("".join(current))

    batch_id = uuid.uuid4().hex[:12]
    checksum = _mobile_qr_checksum(content)
    total = len(chunks)
    return [
        f"{MULTI_QR_PREFIX}|{batch_id}|{index}|{total}|{checksum}|{chunk}"
        for index, chunk in enumerate(chunks, start=1)
    ]


def _parse_multi_qr_fragment(text_value):
    if not isinstance(text_value, str) or not text_value.startswith(MULTI_QR_PREFIX + "|"):
        return None
    parts = text_value.split("|", 5)
    if len(parts) != 6:
        return None
    _, batch_id, part_index, total_parts, checksum, chunk = parts
    try:
        part_index = int(part_index)
        total_parts = int(total_parts)
    except ValueError:
        return None
    if not batch_id or not checksum or part_index < 1 or part_index > total_parts:
        return None
    return {
        "batch_id": batch_id,
        "part_index": part_index,
        "total_parts": total_parts,
        "checksum": checksum,
        "chunk": chunk,
    }


def _recipe_to_mobile_qr_payload(recipe, persons):
    """Construit exactement le JSON compact v1 utilisé par l'app mobile."""
    payload = {
        "v": 1,
        "n": recipe.get("name", ""),
        "p": persons,
    }
    if recipe.get("difficulty"):
        payload["d"] = recipe["difficulty"]
    if recipe.get("prep_time"):
        payload["pt"] = recipe["prep_time"]
    if recipe.get("cook_time"):
        payload["ct"] = recipe["cook_time"]
    if recipe.get("allergens"):
        payload["a"] = recipe["allergens"]
    if recipe.get("description"):
        payload["de"] = recipe["description"]
    if recipe.get("personal_notes"):
        payload["no"] = recipe["personal_notes"]

    payload["i"] = []
    for ing in recipe.get("ingredients", []):
        qty = ing.get("quantity")
        if qty is not None:
            try:
                qty = round(float(qty) * persons, 2)
                if qty == int(qty):
                    qty = int(qty)
            except (TypeError, ValueError):
                qty = None
        payload["i"].append([ing.get("name", ""), qty, ing.get("unit") or ""])
    # separators reproduit JSON.stringify() (pas d'espaces superflus) et
    # ensure_ascii=False laisse qrcode encoder directement le vrai UTF-8.
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _compact_mobile_qr_to_prefill(text_value):
    try:
        data = json.loads((text_value or "").strip())
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict) or data.get("v") != 1 or not isinstance(data.get("n"), str) or not isinstance(data.get("i"), list):
        return None
    try:
        persons = float(data.get("p", 4))
        if persons <= 0:
            persons = 4
    except (TypeError, ValueError):
        persons = 4

    ingredients = []
    for item in data["i"]:
        if not isinstance(item, list) or not item or not isinstance(item[0], str) or not item[0].strip():
            continue
        qty = item[1] if len(item) > 1 else None
        try:
            qty = float(qty) / persons if qty is not None else None
        except (TypeError, ValueError, ZeroDivisionError):
            qty = None
        ingredients.append({
            "name": item[0].strip(),
            "quantity": qty,
            "unit": (item[2] if len(item) > 2 else "") or "",
        })

    default_persons = int(persons) if persons == int(persons) else persons
    return {
        "name": data.get("n", ""),
        "ingredients": ingredients,
        "prep_time": data.get("pt"),
        "cook_time": data.get("ct"),
        "difficulty": data.get("d") or "Facile",
        "allergens": data.get("a") if isinstance(data.get("a"), list) else [],
        "description": data.get("de") if isinstance(data.get("de"), str) else "",
        "personal_notes": data.get("no") if isinstance(data.get("no"), str) else "",
        "default_persons": default_persons,
    }


def _legacy_recipe_qr_to_prefill(text_value):
    """Compatibilité avec les anciens QR texte du bureau."""
    lines = [line.strip() for line in (text_value or "").replace("\r\n", "\n").split("\n") if line.strip()]
    if len(lines) < 2:
        return None
    marker_index = next((i for i, line in enumerate(lines) if re.search(r"ingr|zutat", line, re.I)), -1)
    if marker_index < 1:
        return None

    persons_match = re.search(r"\d+", lines[marker_index])
    persons = int(persons_match.group()) if persons_match else 4
    ingredients = []
    for line in lines[marker_index + 1:]:
        cleaned = re.sub(r"^[-•*]\s*", "", line).strip()
        match = re.match(r"^(.+?)\s*:\s*([\d.,]+)\s*(\S*)$", cleaned)
        if not match:
            continue
        qty = float(match.group(2).replace(",", "."))
        ingredients.append({
            "name": match.group(1).strip(),
            "quantity": qty / max(1, persons),
            "unit": match.group(3) or "",
        })
    if not ingredients:
        return None
    return {
        "name": lines[0],
        "ingredients": ingredients,
        "default_persons": persons,
        "description": "",
        "personal_notes": "",
        "allergens": [],
    }


def _decode_qr_image_file(path):
    if not QRCODE_READER_AVAILABLE or not PIL_AVAILABLE:
        return None
    # Pillow gère correctement les chemins Windows Unicode ; pyzbar est très
    # robuste sur les QR denses/multi-parties produits par l'app mobile.
    with Image.open(path) as image:
        results = decode_barcodes(image)
    for result in results:
        if getattr(result, "type", "") == "QRCODE":
            try:
                return result.data.decode("utf-8")
            except UnicodeDecodeError:
                # Conserve chaque octet pour permettre une réparation contrôlée
                # après réassemblage, au lieu d'insérer des caractères � qui
                # rendraient le contenu irrécupérable.
                return result.data.decode("latin-1")
    return None


def import_recipe_prefill_from_qr_images(paths):
    decoded_values = []
    for path in paths:
        value = _decode_qr_image_file(path)
        if value:
            decoded_values.append(value)
    if not decoded_values:
        return None

    # Un QR compact simple est immédiatement importable.
    for value in decoded_values:
        if not value.startswith(MULTI_QR_PREFIX + "|"):
            parsed = _compact_mobile_qr_to_prefill(value)
            if parsed:
                return parsed
            legacy = _legacy_recipe_qr_to_prefill(value)
            if legacy:
                return legacy

    fragments = [_parse_multi_qr_fragment(value) for value in decoded_values]
    fragments = [f for f in fragments if f]
    if not fragments:
        return None

    batch_ids = {f["batch_id"] for f in fragments}
    if len(batch_ids) != 1:
        raise QrImportMixedBatchesError()

    total_values = {f["total_parts"] for f in fragments}
    checksum_values = {f["checksum"] for f in fragments}
    if len(total_values) != 1 or len(checksum_values) != 1:
        raise QrImportMixedBatchesError()

    total = fragments[0]["total_parts"]
    by_index = {f["part_index"]: f["chunk"] for f in fragments}
    if len(by_index) < total or any(i not in by_index for i in range(1, total + 1)):
        raise QrImportIncompleteError(len(by_index), total)

    expected_checksum = fragments[0]["checksum"]
    candidate_lists = [
        _qr_chunk_repair_candidates(by_index[index])
        for index in range(1, total + 1)
    ]

    # Le meilleur candidat de chaque partie suffit dans les cas ZBar observés.
    full = "".join(candidates[0] for candidates in candidate_lists)
    if _mobile_qr_checksum(full) != expected_checksum:
        full = None
        # Repli borné pour les rares fragments ambigus. Cette limite évite
        # qu'un lot artificiel contenant énormément de variantes monopolise
        # l'application tout en couvrant largement les recettes normales.
        for attempt, combination in enumerate(itertools.product(*candidate_lists), start=1):
            if attempt > 4096:
                break
            candidate_full = "".join(combination)
            if _mobile_qr_checksum(candidate_full) == expected_checksum:
                full = candidate_full
                break
        if full is None:
            raise QrImportChecksumError()
    return _compact_mobile_qr_to_prefill(full)


def safe_qr_filename_component(recipe_name):
    """Retourne un nom de recette utilisable dans un nom de fichier Windows."""
    safe_name = re.sub(r'[\\/:*?"<>|]', "_", str(recipe_name or ""))
    safe_name = safe_name.strip(" .")[:120].rstrip(" .")
    return safe_name or "recette"


def build_qr_export_paths(folder, recipe_name, total_parts):
    """Construit les noms ordonnés d'un export QR simple ou multi-parties."""
    if total_parts < 1:
        raise ValueError("total_parts must be positive")
    safe_name = safe_qr_filename_component(recipe_name)
    if total_parts == 1:
        return [os.path.join(folder, f"qrcode_{safe_name}.png")]
    return [
        os.path.join(folder, f"qrcode_{safe_name}_{index}sur{total_parts}.png")
        for index in range(1, total_parts + 1)
    ]


def save_qr_parts_atomically(parts, target_paths, make_qr):
    """Génère, vérifie puis installe un lot de QR sans laisser de lot partiel."""
    if not parts or len(parts) != len(target_paths):
        raise ValueError("QR parts and paths must have the same non-zero length")

    staged_paths = []
    backup_paths = {}
    committed_paths = []
    try:
        for part, target_path in zip(parts, target_paths):
            folder = os.path.dirname(target_path) or os.curdir
            fd, staged_path = tempfile.mkstemp(
                prefix=".qr-stage-", suffix=".png", dir=folder
            )
            os.close(fd)
            staged_paths.append(staged_path)
            make_qr(part).save(staged_path, format="PNG")
            with Image.open(staged_path) as verification:
                verification.verify()

        for target_path in target_paths:
            if os.path.exists(target_path):
                folder = os.path.dirname(target_path) or os.curdir
                fd, backup_path = tempfile.mkstemp(
                    prefix=".qr-backup-", suffix=".png", dir=folder
                )
                os.close(fd)
                shutil.copy2(target_path, backup_path)
                backup_paths[target_path] = backup_path

        for staged_path, target_path in zip(staged_paths, target_paths):
            os.replace(staged_path, target_path)
            committed_paths.append(target_path)
    except Exception:
        for target_path in reversed(committed_paths):
            try:
                backup_path = backup_paths.pop(target_path, None)
                if backup_path:
                    os.replace(backup_path, target_path)
                elif os.path.exists(target_path):
                    os.remove(target_path)
            except Exception as rollback_error:
                log_internal_error("qr_export_rollback", rollback_error)
        raise
    finally:
        for temporary_path in staged_paths + list(backup_paths.values()):
            try:
                if os.path.exists(temporary_path):
                    os.remove(temporary_path)
            except Exception as cleanup_error:
                log_internal_error("qr_export_cleanup", cleanup_error)


class QRCodeWindow(tk.Toplevel):
    """QR d'une recette au format compact compatible avec l'app mobile."""

    def __init__(self, app, recipe, persons):
        super().__init__(app)
        self.app = app
        self.recipe = recipe
        self.persons = persons
        self.title(t("qrcode_title", name=recipe["name"]))
        fit_window_to_workarea(self, gs(500), gs(620), margin=18)
        safe_minsize(self, gs(460), gs(580))
        self.resizable(True, True)
        self.grab_set()

        self.payload = _recipe_to_mobile_qr_payload(recipe, persons)
        self.parts = _split_mobile_qr_parts(self.payload)
        self.current_part = 0
        self._qr_img = None
        self._photo = None

        ttk.Label(
            self, text=t("qrcode_title", name=recipe["name"]),
            font=("Segoe UI", sf(12), "bold"), wraplength=440, justify="center"
        ).pack(pady=(12, 6))

        self.qr_label = ttk.Label(self)
        self.qr_label.pack(fill="both", expand=True, padx=18, pady=6)

        ttk.Label(
            self, text=t("qrcode_mobile_compatible"),
            font=("Segoe UI", sf(8)), foreground=COLOR_TEXT_MUTED,
            justify="center", wraplength=440
        ).pack(pady=(2, 8))

        self.nav_frame = ttk.Frame(self)
        if len(self.parts) > 1:
            self.nav_frame.pack(fill="x", padx=18, pady=(0, 6))
            ttk.Button(
                self.nav_frame, text=t("qrcode_part_prev"),
                command=self._previous_part
            ).pack(side="left")
            self.part_label = ttk.Label(self.nav_frame, text="")
            self.part_label.pack(side="left", expand=True)
            ttk.Button(
                self.nav_frame, text=t("qrcode_part_next"),
                command=self._next_part
            ).pack(side="right")
        else:
            self.part_label = None

        save_buttons = ttk.Frame(self)
        save_buttons.pack(pady=(4, 12))
        ttk.Button(
            save_buttons,
            text=t(
                "qrcode_save_button"
                if len(self.parts) > 1 else "qrcode_save_single_button"
            ),
            command=self.save_image,
        ).pack(side="left", padx=4)
        if len(self.parts) > 1:
            ttk.Button(
                save_buttons,
                text=t("qrcode_save_all_button", count=len(self.parts)),
                command=self.save_all_images,
                style="Primary.TButton",
            ).pack(side="left", padx=4)

        self._render_current_part()

    def _make_qr(self, text_value):
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=7,
            border=4,  # zone blanche minimale standard : 4 modules
        )
        qr.add_data(text_value)
        qr.make(fit=True)
        return qr.make_image(fill_color="black", back_color="white").convert("RGB")

    def _render_current_part(self):
        self._qr_img = self._make_qr(self.parts[self.current_part])
        display = self._qr_img.copy()
        # L'aperçu reste grand sans modifier le fichier QR réellement enregistré.
        max_side = gs(390)
        display.thumbnail((max_side, max_side), Image.Resampling.NEAREST)
        self._photo = ImageTk.PhotoImage(display)
        self.qr_label.configure(image=self._photo)
        if self.part_label is not None:
            self.part_label.configure(
                text=t(
                    "qrcode_part_indicator",
                    current=self.current_part + 1,
                    total=len(self.parts)
                )
            )

    def _previous_part(self):
        if self.current_part > 0:
            self.current_part -= 1
            self._render_current_part()

    def _next_part(self):
        if self.current_part < len(self.parts) - 1:
            self.current_part += 1
            self._render_current_part()

    def save_image(self):
        safe_name = safe_qr_filename_component(self.recipe["name"])
        suffix = (
            f"_{self.current_part + 1}sur{len(self.parts)}"
            if len(self.parts) > 1 else ""
        )
        path = filedialog.asksaveasfilename(
            title=t("qrcode_save_dialog_title"),
            defaultextension=".png",
            filetypes=[("Image PNG", "*.png")],
            initialfile=f"qrcode_{safe_name}{suffix}.png"
        )
        if not path:
            return
        try:
            self._qr_img.save(path, format="PNG")
        except Exception as e:
            messagebox.showerror(t("common_error"), t("qrcode_save_failed", error=e))
            return
        messagebox.showinfo(
            t("allrecipes_list_saved_title"),
            t("qrcode_saved_message", path=path)
        )

    def save_all_images(self):
        folder = filedialog.askdirectory(
            title=t("qrcode_choose_folder_title"),
            mustexist=True,
            parent=self,
        )
        if not folder:
            return

        target_paths = build_qr_export_paths(
            folder, self.recipe["name"], len(self.parts)
        )
        existing_count = sum(os.path.exists(path) for path in target_paths)
        if existing_count and not ask_yes_no(
            t("common_confirm"),
            t("qrcode_overwrite_all_confirm", count=existing_count),
            parent=self,
        ):
            return

        try:
            save_qr_parts_atomically(self.parts, target_paths, self._make_qr)
        except Exception as error:
            messagebox.showerror(
                t("common_error"),
                t("qrcode_save_failed", error=error),
                parent=self,
            )
            return
        messagebox.showinfo(
            t("allrecipes_list_saved_title"),
            t("qrcode_saved_all_message", count=len(target_paths), path=folder),
            parent=self,
        )


CONVERTER_UNIT_KEYS = [
    ("unitconv_gram", 1.0),
    ("unitconv_kilogram", 1000.0),
    ("unitconv_ounce", 28.35),
    ("unitconv_pound", 453.6),
    ("unitconv_milliliter", 1.0),
    ("unitconv_centiliter", 10.0),
    ("unitconv_liter", 1000.0),
    ("unitconv_teaspoon", 5.0),
    ("unitconv_tablespoon", 15.0),
    ("unitconv_cup", 240.0),
]


class UnitConverterWindow(tk.Toplevel):
    """Petit outil de conversion d'unités indépendant de toute recette,
    pratique pour une recette trouvée ailleurs (ex. en tasses/onces)."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title(t("unitconv_title"))
        fit_window_to_workarea(self, gs(440), gs(460), margin=14)
        safe_minsize(self, gs(400), gs(400))
        self.resizable(True, True)
        self.grab_set()

        # Construit les unités traduites à l'exécution (dans la langue
        # actuellement sélectionnée), plutôt qu'un dictionnaire figé en
        # français au chargement du module.
        self.converter_units = {t(key): factor for key, factor in CONVERTER_UNIT_KEYS}

        ttk.Label(self, text=t("unitconv_heading"), font=("Segoe UI", sf(14), "bold")).pack(pady=(15, 5))
        ttk.Label(
            self,
            text=t("unitconv_intro"),
            font=("Segoe UI", sf(8)), foreground=COLOR_TEXT_MUTED, justify="center"
        ).pack(pady=(0, 15))

        form = ttk.Frame(self)
        form.pack(pady=5)
        ttk.Label(form, text=t("unitconv_quantity_label")).grid(row=0, column=0, padx=5, pady=5, sticky="e")
        self.qty_entry = ttk.Entry(form, width=10)
        self.qty_entry.insert(0, "1")
        self.qty_entry.grid(row=0, column=1, padx=5, pady=5)

        unit_names = list(self.converter_units.keys())
        ttk.Label(form, text=t("unitconv_from_label")).grid(row=1, column=0, padx=5, pady=5, sticky="e")
        self.from_combo = ttk.Combobox(form, values=unit_names, state="readonly", width=22)
        self.from_combo.set(unit_names[0])
        self.from_combo.grid(row=1, column=1, padx=5, pady=5)

        ttk.Label(form, text=t("unitconv_to_label")).grid(row=2, column=0, padx=5, pady=5, sticky="e")
        self.to_combo = ttk.Combobox(form, values=unit_names, state="readonly", width=22)
        self.to_combo.set(unit_names[1])
        self.to_combo.grid(row=2, column=1, padx=5, pady=5)

        ttk.Button(self, text=t("unitconv_convert_button"), command=self.convert).pack(pady=10)
        self.result_label = ttk.Label(self, text="", font=("Segoe UI", sf(12), "bold"),
                                       foreground=COLOR_ACCENT_DARK)
        self.result_label.pack(pady=5)

        self.qty_entry.bind("<Return>", lambda e: self.convert())

    def convert(self):
        try:
            quantity = parse_positive_number(self.qty_entry.get())
        except (ValueError, TypeError):
            messagebox.showerror(t("common_error"), t("unitconv_error_invalid_quantity"))
            return
        from_unit = self.from_combo.get()
        to_unit = self.to_combo.get()
        grams_equivalent = quantity * self.converter_units[from_unit]
        result = grams_equivalent / self.converter_units[to_unit]
        result_display = round(result, 3)
        if result_display == int(result_display):
            result_display = int(result_display)
        self.result_label.config(
            text=t("unitconv_result", quantity=quantity, from_unit=from_unit, result=result_display, to_unit=to_unit)
        )


class PantryWindow(tk.Toplevel):
    """Tableau de bord du garde-manger avec recherche, statuts et filtres."""
    def __init__(self, app):
        super().__init__(app); self.app=app; self.title(t("pantry_title"))
        screen_height = get_usable_screen_height(self)
        fit_window_to_workarea(self, gs(1050), get_usable_screen_height(self), margin=18)
        safe_minsize(self, gs(820),gs(560)); self.resizable(True, True); self.grab_set()
        ttk.Label(self,text=t("pantry_heading"),font=("Segoe UI",sf(15),"bold")).pack(pady=(14,3))
        self.summary_label=ttk.Label(self,text="",foreground=COLOR_TEXT_MUTED); self.summary_label.pack(pady=(0,8))
        compact = self.winfo_screenwidth() < 1200 or screen_height < 700 or FONT_SCALE > 1.0
        add=ttk.LabelFrame(self,text=t("common_save_button")); add.pack(fill="x",padx=15,pady=(0,6))
        self.name_entry=ttk.Entry(add,width=24); self.name_entry.full_values=get_display_ingredient_values(sorted(self.app.ingredient_names,key=ingredient_sort_key))
        self.qty_entry=ttk.Entry(add,width=7); self.qty_entry.insert(0,"1")
        self.unit_options=RecipeFormWindow.UNIT_OPTIONS[:-1]+["boîte","paquet","rouleau","bouteille"]
        self.unit_combo=ttk.Combobox(add,values=[translate_unit_name(u) for u in self.unit_options],width=13); self.unit_combo.set(translate_unit_name("pièce"))
        self.threshold_entry=ttk.Entry(add,width=7)
        self.expiration_entry=ttk.Entry(add,width=12)
        if compact:
            ttk.Label(add,text=t("common_ingredient_label")).grid(row=0,column=0,padx=4,pady=4,sticky="e"); self.name_entry.grid(row=0,column=1,padx=4,sticky="ew")
            ttk.Label(add,text=t("common_quantity_label")).grid(row=0,column=2,padx=4); self.qty_entry.grid(row=0,column=3,padx=4)
            self.unit_combo.grid(row=0,column=4,padx=4)
            ttk.Label(add,text=t("pantry_threshold_label")).grid(row=1,column=0,padx=4,pady=4,sticky="e"); self.threshold_entry.grid(row=1,column=1,padx=4,sticky="w")
            ttk.Label(add,text=t("pantry_expiration_label")).grid(row=1,column=2,padx=4,pady=4,sticky="e"); self.expiration_entry.grid(row=1,column=3,padx=4,sticky="w")
            ttk.Button(add,text=t("common_save_button"),style="Primary.TButton",command=self.save_item).grid(row=2,column=0,columnspan=2,padx=4,pady=4,sticky="ew")
            ttk.Button(add,text=t("common_new_ingredient_button"),command=self.create_new_ingredient).grid(row=2,column=2,columnspan=3,padx=4,pady=4,sticky="ew")
            add.columnconfigure(1,weight=1)
        else:
            ttk.Label(add,text=t("common_ingredient_label")).grid(row=0,column=0,padx=5,pady=6,sticky="e"); self.name_entry.grid(row=0,column=1,padx=5)
            ttk.Label(add,text=t("common_quantity_label")).grid(row=0,column=2,padx=5); self.qty_entry.grid(row=0,column=3,padx=5); self.unit_combo.grid(row=0,column=4,padx=5)
            ttk.Label(add,text=t("pantry_threshold_label")).grid(row=1,column=0,padx=5,pady=6,sticky="e"); self.threshold_entry.grid(row=1,column=1,padx=5,sticky="w")
            ttk.Label(add,text=t("pantry_expiration_label")).grid(row=1,column=2,padx=5,pady=6,sticky="e"); self.expiration_entry.grid(row=1,column=3,padx=5,sticky="w")
            ttk.Button(add,text=t("common_save_button"),style="Primary.TButton",command=self.save_item).grid(row=1,column=4,padx=5)
            ttk.Button(add,text=t("common_new_ingredient_button"),command=self.create_new_ingredient).grid(row=0,column=5,rowspan=2,padx=8)
        self.name_entry.bind("<KeyRelease>",lambda e:self._on_name_entry_keyrelease(e)); self.name_entry.bind("<FocusIn>",lambda e:self._on_name_entry_focus_in(e)); self.name_entry.bind("<FocusOut>",lambda e:self._on_name_entry_focus_out(e))
        tools=ttk.Frame(self); tools.pack(fill="x",padx=15,pady=(0,6))
        self.search_var=tk.StringVar(); ent=ttk.Entry(tools,textvariable=self.search_var,width=22); ent.bind("<KeyRelease>",lambda e:self._populate())
        self.filter_combo=ttk.Combobox(tools,state="readonly",width=17,values=[t("pantry_filter_all"),t("pantry_filter_low"),t("pantry_filter_expiring"),t("pantry_filter_expired")]); self.filter_combo.set(t("pantry_filter_all")); self.filter_combo.bind("<<ComboboxSelected>>",lambda e:self._populate())
        self.sort_combo=ttk.Combobox(tools,state="readonly",width=15,values=[t("pantry_sort_name"),t("pantry_sort_expiry"),t("pantry_sort_status")]); self.sort_combo.set(t("pantry_sort_name")); self.sort_combo.bind("<<ComboboxSelected>>",lambda e:self._populate())
        if compact:
            ttk.Label(tools,text=t("pantry_search_label")).grid(row=0,column=0,sticky="w"); ent.grid(row=0,column=1,padx=(4,10),sticky="ew")
            ttk.Label(tools,text=t("pantry_filter_label")).grid(row=0,column=2,sticky="w"); self.filter_combo.grid(row=0,column=3,padx=4,sticky="ew")
            ttk.Label(tools,text=t("pantry_sort_label")).grid(row=1,column=0,sticky="w",pady=(4,0)); self.sort_combo.grid(row=1,column=1,padx=(4,10),pady=(4,0),sticky="ew")
            tools.columnconfigure(1,weight=1); tools.columnconfigure(3,weight=1)
        else:
            ttk.Label(tools,text=t("pantry_search_label")).pack(side="left"); ent.pack(side="left",padx=(4,12))
            ttk.Label(tools,text=t("pantry_filter_label")).pack(side="left"); self.filter_combo.pack(side="left",padx=4)
            ttk.Label(tools,text=t("pantry_sort_label")).pack(side="left",padx=(12,0)); self.sort_combo.pack(side="left",padx=4)
        frame=ttk.Frame(self); frame.pack(fill="both",expand=True,padx=15,pady=(0,8))
        cols=("name","qty","threshold","expiry","status","section"); self.tree=ttk.Treeview(frame,columns=cols,show="headings",selectmode="browse")
        specs=(("name",t("pantry_col_name"),260,"w"),("qty",t("pantry_col_qty"),110,"center"),("threshold",t("pantry_col_threshold"),100,"center"),("expiry",t("pantry_col_expiry"),120,"center"),("status",t("pantry_col_status"),160,"center"),("section",t("pantry_col_section"),150,"w"))
        for c,txt,w,a in specs:self.tree.heading(c,text=txt);self.tree.column(c,width=gs(w),anchor=a)
        sb=ttk.Scrollbar(frame,orient="vertical",command=self.tree.yview); self.tree.configure(yscrollcommand=sb.set); self.tree.pack(side="left",fill="both",expand=True); sb.pack(side="right",fill="y")
        self.tree.bind("<<TreeviewSelect>>",lambda e:self._load_selected_for_edit())
        btn=ttk.Frame(self); btn.pack(pady=(0,10),fill="x",padx=15)
        for c in range(2 if compact else 4): btn.columnconfigure(c,weight=1)
        actions=[
            (t("pantry_use_soon_button"),self.show_use_soon,"Primary.TButton"),
            (t("pantry_add_selected_shopping"),self.add_selected_to_shopping,None),
            (t("pantry_add_low_shopping"),self.add_low_to_shopping,None),
            (t("pantry_remove_button"),self.remove_selected,None),
        ]
        for i,(label,command,style) in enumerate(actions):
            kwargs={"text":label,"command":command}
            if style: kwargs["style"]=style
            ttk.Button(btn,**kwargs).grid(row=(i//2 if compact else 0),column=(i%2 if compact else i),padx=3,pady=2,sticky="ew")
        self.pantry_entries_ordered=[]; self._entry_by_iid={}; self._populate()
    def _status_for(self,entry):
        qty=float(entry.get("quantity",0) or 0); threshold=entry.get("threshold"); expiry=parse_pantry_expiration(entry.get("expiration_date")); days=(expiry-datetime.now().date()).days if expiry else None
        if days is not None and days<0:return "expired",t("pantry_status_expired")
        if days is not None and days<=5:return "expiring",t("pantry_status_expiring")
        if threshold is not None and qty<float(threshold):return "low",t("pantry_status_low")
        return "ok",t("pantry_status_ok")
    def _populate(self):
        for iid in self.tree.get_children():self.tree.delete(iid)
        pantry=load_pantry(); all_entries=list(pantry.values()); low=sum(1 for e in all_entries if self._status_for(e)[0]=="low"); exp=sum(1 for e in all_entries if self._status_for(e)[0] in ("expiring","expired")); self.summary_label.configure(text=t("pantry_summary",count=len(all_entries),low=low,expiring=exp))
        q=ingredient_sort_key(self.search_var.get()) if hasattr(self,"search_var") else ""; f=self.filter_combo.get() if hasattr(self,"filter_combo") else t("pantry_filter_all")
        entries=[]
        for e in all_entries:
            code,label=self._status_for(e)
            if q and q not in ingredient_sort_key(e.get("name","")):continue
            if f==t("pantry_filter_low") and code!="low":continue
            if f==t("pantry_filter_expiring") and code!="expiring":continue
            if f==t("pantry_filter_expired") and code!="expired":continue
            entries.append(e)
        sortv=self.sort_combo.get() if hasattr(self,"sort_combo") else t("pantry_sort_name")
        if sortv==t("pantry_sort_expiry"): entries.sort(key=lambda e:(parse_pantry_expiration(e.get("expiration_date")) or datetime.max.date(),ingredient_sort_key(e.get("name",""))))
        elif sortv==t("pantry_sort_status"): entries.sort(key=lambda e:({"expired":0,"expiring":1,"low":2,"ok":3}[self._status_for(e)[0]],ingredient_sort_key(e.get("name",""))))
        else: entries.sort(key=lambda e:ingredient_sort_key(e.get("name","")))
        self.pantry_entries_ordered=entries; self._entry_by_iid={}
        for i,e in enumerate(entries):
            iid=str(i); self._entry_by_iid[iid]=e; qty=e.get("quantity",0); qtytxt=str(int(qty)) if isinstance(qty,(int,float)) and float(qty).is_integer() else str(round(float(qty),2)); unit=translate_unit_name(e.get("unit","")); thr=e.get("threshold"); thrtxt="—" if thr is None else str(thr); expiry=parse_pantry_expiration(e.get("expiration_date")); exptxt=expiry.strftime("%d/%m/%Y") if expiry else "—"; status=self._status_for(e)[1]; section=translate_rayon_name(get_ingredient_rayon(e.get("name","")))
            self.tree.insert("","end",iid=iid,values=(translate_ingredient_name(e.get("name","")).capitalize(),f"{qtytxt} {unit}".strip(),thrtxt,exptxt,status,section))
    def _shopping_qty(self,e):
        threshold=e.get("threshold")
        if threshold is not None and float(threshold)>float(e.get("quantity",0) or 0): return max(float(threshold)-float(e.get("quantity",0) or 0),1)
        return max(float(threshold or 1),1)
    def _open_shopping_with(self,entries):
        if not entries:return
        win=AllRecipesWindow(self.app); items=[{"name":e["name"],"quantity":self._shopping_qty(e),"unit":e.get("unit","")} for e in entries]; win.add_manual_items(items); messagebox.showinfo(t("common_info"),t("pantry_added_to_shopping",count=len(items)),parent=win)
    def add_selected_to_shopping(self):
        sel=self.tree.selection()
        if not sel: messagebox.showinfo(t("common_info"),t("pantry_select_for_shopping"),parent=self); return
        e=self._entry_by_iid.get(sel[0]); self._open_shopping_with([e] if e else [])
    def add_low_to_shopping(self):
        entries=[e for e in load_pantry().values() if self._status_for(e)[0]=="low"]
        if not entries: messagebox.showinfo(t("common_info"),t("pantry_none_low"),parent=self); return
        self._open_shopping_with(entries)
    def create_new_ingredient(self):
        typed = normalize_oe(self.name_entry.get().strip())
        win = IngredientEditWindow(self.app, manage_window=None, existing_name=None,
                                    prefill_name=typed, parent_window=self)
        self.wait_window(win)
        self.name_entry.full_values = get_display_ingredient_values(sorted(self.app.ingredient_names, key=ingredient_sort_key))

    def _prefill_existing(self):
        typed = self.name_entry.get().strip()
        canonical = resolve_ingredient_input(typed, self.app.ingredient_names)
        if canonical is None:
            return
        pantry = load_pantry()
        entry = pantry.get(ingredient_sort_key(canonical))
        if entry:
            self.qty_entry.delete(0, tk.END)
            self.qty_entry.insert(0, str(entry["quantity"]))
            self.unit_combo.set(translate_unit_name(entry["unit"]))
            self.threshold_entry.delete(0, tk.END)
            if entry.get("threshold") is not None:
                self.threshold_entry.insert(0, str(entry["threshold"]))
            self.expiration_entry.delete(0, tk.END)
            expiry = parse_pantry_expiration(entry.get("expiration_date"))
            if expiry:
                self.expiration_entry.insert(0, expiry.strftime("%d/%m/%Y"))

    def _load_selected_for_edit(self):
        sel = self.tree.selection()
        if not sel or not self.pantry_entries_ordered:
            return
        entry = self._entry_by_iid.get(sel[0])
        if entry is None:
            return
        self.name_entry.delete(0, tk.END)
        self.name_entry.insert(0, translate_ingredient_name(entry["name"]))
        self.qty_entry.delete(0, tk.END)
        self.qty_entry.insert(0, str(entry["quantity"]))
        self.unit_combo.set(translate_unit_name(entry["unit"]))
        self.threshold_entry.delete(0, tk.END)
        if entry.get("threshold") is not None:
            self.threshold_entry.insert(0, str(entry["threshold"]))
        self.expiration_entry.delete(0, tk.END)
        expiry = parse_pantry_expiration(entry.get("expiration_date"))
        if expiry:
            self.expiration_entry.insert(0, expiry.strftime("%d/%m/%Y"))

    # ---- Autocomplétion du champ ingrédient (même principe que les autres
    # listes déroulantes d'ingrédients de l'application) ----

    def _hide_name_suggestions(self):
        popup = getattr(self.name_entry, "_suggestion_popup", None)
        if popup is not None:
            try:
                popup.destroy()
            except tk.TclError:
                pass
            self.name_entry._suggestion_popup = None
            self.name_entry._suggestion_listbox = None

    def _show_name_suggestions(self, filtered):
        self._hide_name_suggestions()
        if not filtered:
            return
        entry = self.name_entry
        popup = tk.Toplevel(entry)
        popup.wm_overrideredirect(True)
        try:
            popup.wm_attributes("-topmost", True)
        except tk.TclError:
            pass
        width = max(entry.winfo_width(), gs(180))

        listbox = tk.Listbox(popup, height=min(6, len(filtered)), exportselection=False, font=("Segoe UI", sf(9)))
        listbox.pack(fill="both", expand=True)
        for v in filtered:
            listbox.insert(tk.END, v)
        finalize_suggestion_popup(popup, entry, listbox, width)

        def choose(event=None):
            sel = listbox.curselection()
            if sel:
                value = listbox.get(sel[0])
                entry.delete(0, tk.END)
                entry.insert(0, value)
                self._prefill_existing()
            self._hide_name_suggestions()
            entry.focus_set()

        listbox.bind("<ButtonRelease-1>", choose)
        listbox.bind("<Return>", choose)
        entry._suggestion_popup = popup
        entry._suggestion_listbox = listbox

    def _on_name_entry_keyrelease(self, event):
        if event.keysym == "Down":
            listbox = getattr(self.name_entry, "_suggestion_listbox", None)
            if listbox is not None:
                listbox.focus_set()
                listbox.selection_set(0)
            return
        if event.keysym == "Escape":
            self._hide_name_suggestions()
            return
        if event.keysym == "Return":
            self._hide_name_suggestions()
            self.save_item()
            return
        if event.keysym in ("Tab", "Shift_L", "Shift_R", "Control_L", "Control_R",
                            "Caps_Lock", "Alt_L", "Alt_R", "Left", "Right"):
            return
        filtered = self._filter_ingredient_values(self.name_entry.full_values, self.name_entry.get())
        if filtered:
            self._show_name_suggestions(filtered)
        else:
            self._hide_name_suggestions()

    def _on_name_entry_focus_in(self, event):
        filtered = self._filter_ingredient_values(self.name_entry.full_values, self.name_entry.get())
        if filtered:
            self._show_name_suggestions(filtered)

    def _on_name_entry_focus_out(self, event):
        self.name_entry.after(200, self._hide_name_suggestions)

    @staticmethod
    def _filter_ingredient_values(full_values, typed):
        if not typed:
            return full_values
        typed_key = ingredient_sort_key(typed)
        filtered = [v for v in full_values if ingredient_sort_key(v).startswith(typed_key)]
        if not filtered:
            filtered = [v for v in full_values if typed_key in ingredient_sort_key(v)]
        return filtered

    def save_item(self):
        name = normalize_oe(self.name_entry.get().strip())
        if not name:
            messagebox.showerror(t("common_error"), t("pantry_error_ingredient_required"))
            return
        canonical = resolve_ingredient_input(name, self.app.ingredient_names)
        if canonical is None:
            messagebox.showerror(
                t("common_unknown_ingredient_title"),
                t("common_unknown_ingredient_simple_message", name=name)
            )
            return
        try:
            quantity = parse_positive_number(self.qty_entry.get(), allow_zero=True)
        except ValueError:
            messagebox.showerror(t("common_error"), t("pantry_error_invalid_quantity"))
            return
        threshold_str = self.threshold_entry.get().strip()
        threshold = None
        if threshold_str:
            try:
                threshold = parse_positive_number(threshold_str, allow_zero=True)
            except ValueError:
                messagebox.showerror(t("common_error"), t("pantry_error_invalid_threshold"))
                return
        expiration_raw = self.expiration_entry.get().strip()
        expiration = None
        if expiration_raw:
            expiration_date = parse_pantry_expiration(expiration_raw)
            if expiration_date is None:
                messagebox.showerror(t("common_error"), t("pantry_error_invalid_expiration"))
                return
            expiration = expiration_date.isoformat()
        unit = resolve_unit_input_best_effort(self.unit_combo.get().strip(), self.unit_options)
        set_pantry_item(canonical, quantity, unit, threshold, expiration)
        self._populate()
        self.name_entry.delete(0, tk.END)
        self.qty_entry.delete(0, tk.END)
        self.qty_entry.insert(0, "1")
        self.threshold_entry.delete(0, tk.END)
        self.expiration_entry.delete(0, tk.END)

    def show_use_soon(self):
        items = get_expiring_pantry_items(days=5)
        if not items:
            messagebox.showinfo(t("common_info"), t("pantry_no_expiring_items"))
            return
        UseSoonRecipesWindow(self.app, items, parent_window=self)

    def remove_selected(self):
        sel = self.tree.selection()
        if not sel or not self.pantry_entries_ordered:
            messagebox.showinfo(t("common_info"), t("pantry_select_ingredient_first"), parent=self)
            return
        entry = self._entry_by_iid.get(sel[0])
        if entry is None:
            return
        if not ask_yes_no(t("common_confirm"), t("pantry_remove_confirm_message", name=entry['name'])):
            return
        remove_pantry_item(entry["name"])
        self._populate()


class UseSoonRecipesWindow(tk.Toplevel):
    """Propose les recettes qui utilisent les produits bientôt périmés."""

    def __init__(self, app, expiring_items=None, parent_window=None):
        super().__init__(parent_window or app)
        self.app = app
        self.items = expiring_items or get_expiring_pantry_items(days=5)
        self.title(t("use_soon_title"))
        fit_window_to_workarea(self, gs(760), gs(620), margin=18)
        safe_minsize(self, gs(620), gs(480))
        self.grab_set()

        ttk.Label(self, text=t("use_soon_heading"), font=("Segoe UI", sf(14), "bold")).pack(pady=(15, 5))
        names = ", ".join(translate_ingredient_name(e.get("name", "")).capitalize() for e in self.items)
        ttk.Label(self, text=t("use_soon_intro", names=names), foreground=COLOR_TEXT_MUTED,
                  justify="center", wraplength=680).pack(padx=20, pady=(0, 12))

        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=15, pady=(0, 10))
        self.tree = ttk.Treeview(frame, columns=("uses", "missing", "time"), show="headings", selectmode="browse")
        self.tree.heading("uses", text=t("use_soon_col_recipe"))
        self.tree.heading("missing", text=t("use_soon_col_products"))
        self.tree.heading("time", text=t("use_soon_col_missing"))
        self.tree.column("uses", width=260, anchor="w")
        self.tree.column("missing", width=260, anchor="w")
        self.tree.column("time", width=120, anchor="center")
        sb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda e: self.open_selected())
        self.recipe_by_iid = {}
        self._populate()
        ttk.Button(self, text=t("use_soon_open"), style="Primary.TButton", command=self.open_selected).pack(pady=(0, 15))

    def _populate(self):
        exp_keys = {ingredient_sort_key(e.get("name", "")): e for e in self.items}
        pantry_keys = set(load_pantry().keys())
        scored = []
        for recipe in self.app.recipes:
            recipe_keys = {ingredient_sort_key(i.get("name", "")) for i in recipe.get("ingredients", [])}
            used = [e for k, e in exp_keys.items() if k in recipe_keys]
            if not used:
                continue
            missing = missing_recipe_ingredients(recipe, pantry_keys)
            scored.append((len(used), len(missing), recipe, used, missing))
        scored.sort(key=lambda x: (-x[0], x[1], ingredient_sort_key(x[2].get("name", ""))))
        for _, _, recipe, used, missing in scored:
            iid = self.tree.insert("", "end", values=(
                recipe.get("name", ""),
                ", ".join(translate_ingredient_name(e.get("name", "")).capitalize() for e in used),
                len(missing),
            ))
            self.recipe_by_iid[iid] = recipe.get("name")
        if not scored:
            iid = self.tree.insert("", "end", values=(t("use_soon_no_recipe"), "", ""))
            self.recipe_by_iid[iid] = None

    def open_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        name = self.recipe_by_iid.get(sel[0])
        if name:
            OneRecipeWindow(self.app, initial_recipe_name=name)


class WhatCanICookWindow(tk.Toplevel):
    """Fenêtre pour indiquer les ingrédients qu'on a sous la main, et voir
    quelles recettes sont réalisables (ou presque)."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title(t("cook_title"))
        fit_window_to_workarea(self, gs(960), gs(660), margin=18)
        self.grab_set()
        # Pré-coche les ingrédients de base qu'on a presque toujours sous la
        # main (correspondance exacte, insensible à la casse, avec la liste
        # d'ingrédients de l'utilisateur — un ingrédient de base absent de sa
        # liste est simplement ignoré ici).
        available_lower = {n.lower(): n for n in self.app.ingredient_names}
        self.have_names = [
            available_lower[staple.lower()] for staple in PANTRY_STAPLES
            if staple.lower() in available_lower
        ]

        ttk.Label(self, text=t("cook_instructions_label"),
                  font=("Segoe UI", sf(11), "bold")).pack(pady=(10, 2))
        ttk.Label(
            self,
            text=t("cook_staples_hint"),
            font=("Segoe UI", sf(8)), foreground=COLOR_TEXT_MUTED, justify="center"
        ).pack(pady=(0, 5))

        columns = ttk.Frame(self)
        columns.pack(fill="both", expand=False, padx=15, pady=5)

        left = ttk.Frame(columns)
        left.pack(side="left", fill="both", expand=True, padx=(0, 10))
        ttk.Label(left, text=t("cook_all_ingredients_label")).pack()
        search_frame = ttk.Frame(left)
        search_frame.pack(fill="x", pady=3)
        ttk.Label(search_frame, text="🔍").pack(side="left")
        self.search_entry = ttk.Entry(search_frame)
        self.search_entry.pack(side="left", fill="x", expand=True, padx=3)
        self.search_entry.bind("<KeyRelease>", lambda e: self._populate_all())
        self.all_listbox = tk.Listbox(left, height=14, font=("Segoe UI", sf(9)))
        self.all_listbox.pack(fill="both", expand=True)
        self.all_listbox.bind("<Double-Button-1>", lambda e: self._add_selected())
        ttk.Button(left, text=t("cook_add_button"), command=self._add_selected).pack(pady=5)

        right = ttk.Frame(columns)
        right.pack(side="left", fill="both", expand=True)
        ttk.Label(right, text=t("cook_have_label")).pack()
        self.have_listbox = tk.Listbox(right, height=16, font=("Segoe UI", sf(9)))
        self.have_listbox.pack(fill="both", expand=True, pady=(3, 0))
        self.have_listbox.bind("<Double-Button-1>", lambda e: self._remove_selected())
        ttk.Button(right, text=t("cook_remove_button"), command=self._remove_selected).pack(pady=5)
        ttk.Button(right, text=t("cook_load_from_pantry_button"),
                   command=self._load_from_pantry).pack(pady=(0, 5))

        self._populate_all()
        self._populate_have()

        ttk.Button(self, text=t("cook_compute_button"),
                   command=self.compute_feasible).pack(pady=8)

        result_frame = ttk.Frame(self)
        result_frame.pack(pady=5, padx=15, fill="both", expand=True)

        # Text plutôt que Listbox : les recettes partielles peuvent contenir
        # plusieurs ingrédients manquants et doivent revenir automatiquement
        # à la ligne lorsque la fenêtre est étroite.
        self.result_text = tk.Text(
            result_frame, height=14, wrap="word",
            font=("Segoe UI", sf(9)), cursor="arrow",
            padx=8, pady=6
        )
        result_scrollbar = ttk.Scrollbar(
            result_frame, orient="vertical", command=self.result_text.yview
        )
        self.result_text.configure(yscrollcommand=result_scrollbar.set)
        self.result_text.pack(side="left", fill="both", expand=True)
        result_scrollbar.pack(side="right", fill="y")
        self.result_text.bind("<Double-Button-1>", self._open_result_at_event)

        # Une entrée par ligne logique du widget Text. Même si la ligne se
        # replie visuellement sur 2 ou 3 lignes, elle pointe toujours vers
        # la même recette.
        self._result_recipe_ranges = []  # (début, fin, nom de recette)
        self._selected_result_recipe = None
        self.result_text.bind("<ButtonRelease-1>", self._select_result_at_event)

        ttk.Button(self, text=t("cook_open_selected_button"),
                   command=self.open_selected_recipe).pack(pady=(5, 10))

    def _populate_all(self):
        search = self.search_entry.get().strip()
        search_key = ingredient_sort_key(search) if search else ""
        self.all_listbox.delete(0, tk.END)
        self.displayed_all_names = []
        for name in self.app.ingredient_names:
            if name in self.have_names:
                continue
            if search_key and search_key not in ingredient_sort_key(name) \
                    and search_key not in ingredient_sort_key(translate_ingredient_name(name)):
                continue
            self.all_listbox.insert(tk.END, translate_ingredient_name(name))
            self.displayed_all_names.append(name)

    def _populate_have(self):
        self.have_listbox.delete(0, tk.END)
        for name in self.have_names:
            self.have_listbox.insert(tk.END, translate_ingredient_name(name))

    def _add_selected(self):
        sel = self.all_listbox.curselection()
        for i in sel:
            name = self.displayed_all_names[i]
            if name not in self.have_names:
                self.have_names.append(name)
        self._populate_have()
        self._populate_all()

    def _remove_selected(self):
        sel = self.have_listbox.curselection()
        names_to_remove = {self.have_names[i] for i in sel}
        self.have_names = [n for n in self.have_names if n not in names_to_remove]
        self._populate_have()
        self._populate_all()

    def _load_from_pantry(self):
        pantry = load_pantry()
        if not pantry:
            messagebox.showinfo(t("cook_pantry_empty_title"), t("cook_pantry_empty_message"))
            return
        added = 0
        for entry in pantry.values():
            if entry["name"] not in self.have_names:
                self.have_names.append(entry["name"])
                added += 1
        self._populate_have()
        self._populate_all()
        messagebox.showinfo(t("cook_loaded_title"), t("cook_loaded_message", count=added))

    def compute_feasible(self):
        have_keys = {ingredient_sort_key(n) for n in self.have_names}
        if not have_keys:
            messagebox.showinfo(t("common_info"), t("cook_add_ingredient_first"))
            return

        pantry = load_pantry()
        results = []
        for recipe in self.app.recipes:
            seen = set()
            missing = []
            try:
                persons = parse_positive_number(recipe.get("default_persons", 1) or 1)
            except ValueError:
                persons = 1
            for ing in recipe.get("ingredients", []):
                key = ingredient_sort_key(ing.get("name", ""))
                if key in seen:
                    continue
                seen.add(key)
                if key not in have_keys:
                    missing.append(ing.get("name", ""))
                    continue
                # Si l'ingrédient provient du garde-manger, vérifier aussi la
                # quantité réellement disponible pour le nombre de personnes
                # par défaut de la recette.
                if key in pantry and ing.get("quantity") is not None:
                    needed = ingredient_quantity_for_persons(ing, persons)
                    status = pantry_stock_status(ing.get("name", ""), needed, ing.get("unit", ""), pantry)
                    if status == "insuffisant":
                        missing.append(ing.get("name", ""))
            results.append((recipe, missing))

        feasible = [r for r in results if not r[1]]
        remaining = []
        for recipe, missing in results:
            if not missing:
                continue
            unique_total = len({ingredient_sort_key(i["name"]) for i in recipe.get("ingredients", [])})
            coverage = 0.0 if unique_total <= 0 else (unique_total - len(missing)) / unique_total
            if len(missing) <= 5 or (coverage >= 0.70 and len(missing) <= 6):
                remaining.append((recipe, missing, coverage))

        # Pour les recettes avec 1 à 3 ingrédients manquants, vérifie si un
        # substitut connu pour l'ingrédient manquant est déjà dans "Ce que
        # j'ai" : si TOUS les ingrédients manquants ont un substitut
        # disponible, la recette devient réalisable avec substitution.
        substitutable = []
        almost = []
        for recipe, missing, coverage in remaining:
            subs_used = {}
            all_covered = True
            for ing_name in missing:
                sub_name = None
                for sub in get_ingredient_substitutions(ing_name):
                    if ingredient_sort_key(sub["nom"]) in have_keys:
                        sub_name = sub["nom"]
                        break
                if sub_name:
                    subs_used[ing_name] = sub_name
                else:
                    all_covered = False
            if all_covered:
                substitutable.append((recipe, missing, subs_used, coverage))
            else:
                almost.append((recipe, missing, coverage))

        self.result_text.config(state="normal")
        self.result_text.delete("1.0", tk.END)
        self._result_recipe_ranges = []
        self._selected_result_recipe = None

        def add_result(text_value, recipe_name=None, header=False):
            if self.result_text.get("1.0", "end-1c"):
                self.result_text.insert(tk.END, "\n")
            start_index = self.result_text.index("end-1c")
            self.result_text.insert(tk.END, text_value)
            end_index = self.result_text.index("end-1c")
            if recipe_name:
                # Toute la recette est une seule zone : nom + détails +
                # ingrédients manquants, même si elle se replie visuellement.
                self._result_recipe_ranges.append((start_index, end_index, recipe_name))
                self.result_text.tag_add("recipe_row", start_index, end_index)
            elif header:
                self.result_text.tag_add("result_header", start_index, end_index)

        self.result_text.tag_configure(
            "result_header", font=("Segoe UI", sf(9), "bold"),
            foreground=COLOR_ACCENT_DARK, spacing1=5, spacing3=2
        )
        self.result_text.tag_configure(
            "recipe_row", lmargin1=12, lmargin2=28, spacing1=2, spacing3=2
        )

        def add_header(text_value):
            add_result(text_value, header=True)

        if feasible:
            add_header(t("cook_feasible_header"))
            pantry = load_pantry()
            for recipe, missing in sorted(feasible, key=lambda pair: ingredient_sort_key(pair[0]["name"])):
                star = "⭐ " if recipe.get("favorite") else ""
                warning = ""
                if pantry:
                    insufficient = [
                        translate_ingredient_name(ing["name"]).capitalize() for ing in recipe["ingredients"]
                        if ing.get("quantity") is not None and pantry_stock_status(
                            ing["name"],
                            ingredient_quantity_for_persons(ing, recipe.get("default_persons", 1) or 1),
                            ing["unit"], pantry
                        ) == "insuffisant"
                    ]
                    if insufficient:
                        warning = t("cook_insufficient_quantity", list=", ".join(insufficient))
                add_result(
                    f"   {star}{recipe['name']}{warning}",
                    recipe_name=recipe["name"]
                )
        else:
            add_header(t("cook_none_feasible"))

        if substitutable:
            add_header("")
            add_header(t("cook_substitutable_header"))
            for recipe, missing, subs_used, coverage in sorted(
                    substitutable, key=lambda pair: ingredient_sort_key(pair[0]["name"])):
                details = ", ".join(
                    f"{translate_ingredient_name(m).capitalize()} → {translate_ingredient_name(subs_used[m])}"
                    for m in missing
                )
                add_result(
                    f"   {recipe['name']} ({details})",
                    recipe_name=recipe["name"]
                )

        if almost:
            add_header("")
            add_header(t("cook_almost_header"))
            for recipe, missing, coverage in sorted(
                    almost, key=lambda pair: (len(pair[1]), -pair[2], ingredient_sort_key(pair[0]["name"]))):
                missing_display = ", ".join(
                    translate_ingredient_name(m).capitalize() for m in missing
                )
                pct = int(round(coverage * 100))
                add_result(
                    t("cook_missing_label", name=recipe['name'], list=missing_display)
                    + f"  [{pct}%]",
                    recipe_name=recipe["name"]
                )

        if not feasible and not substitutable and not almost:
            add_header(t("cook_no_results"))

        self.result_text.config(state="disabled")

    def _result_range_at_event(self, event):
        try:
            index = self.result_text.index(f"@{event.x},{event.y}")
            for start_index, end_index, recipe_name in self._result_recipe_ranges:
                if (self.result_text.compare(index, ">=", start_index) and
                        self.result_text.compare(index, "<=", end_index)):
                    return start_index, end_index, recipe_name
        except Exception as exc:
            log_internal_error("suppressed_exception", exc)
        return None

    def _recipe_at_result_event(self, event):
        found = self._result_range_at_event(event)
        return found[2] if found else None

    def _select_result_at_event(self, event):
        found = self._result_range_at_event(event)
        self._selected_result_recipe = found[2] if found else None
        try:
            self.result_text.tag_remove("selected_recipe", "1.0", tk.END)
            if found:
                start_index, end_index, _recipe_name = found
                self.result_text.tag_configure(
                    "selected_recipe", background=COLOR_ACCENT_LIGHT
                )
                self.result_text.tag_add(
                    "selected_recipe", start_index, end_index
                )
        except Exception as exc:
            log_internal_error("suppressed_exception", exc)

    def _open_result_at_event(self, event):
        recipe_name = self._recipe_at_result_event(event)
        if recipe_name:
            OneRecipeWindow(self.app, initial_recipe_name=recipe_name)
            return "break"

    def open_selected_recipe(self):
        recipe_name = self._selected_result_recipe
        if not recipe_name:
            messagebox.showinfo(
                t("common_info"), t("cook_select_recipe_from_results")
            )
            return
        OneRecipeWindow(self.app, initial_recipe_name=recipe_name)


class WeeklyPlanHistoryWindow(tk.Toplevel):
    """Fenêtre pour consulter les plannings de semaines passées (jusqu'à 26
    semaines d'historique), et éventuellement en recharger un dans le
    planning actuel — pratique pour éviter de refaire deux fois la même
    chose de trop près."""

    def __init__(self, app, parent_window=None):
        super().__init__(parent_window or app)
        self.app = app
        self.parent_window = parent_window
        self.title(t("weekhistory_title"))
        fit_window_to_workarea(self, gs(930), gs(760), margin=18)
        safe_minsize(self, gs(500), gs(500))
        self.resizable(True, True)
        self.grab_set()

        ttk.Label(self, text=t("weekhistory_heading"),
                  font=("Segoe UI", sf(14), "bold")).pack(pady=(15, 5))
        ttk.Label(
            self, text=t("weekhistory_intro"),
            font=("Segoe UI", sf(8)), foreground=COLOR_TEXT_MUTED, justify="center"
        ).pack(pady=(0, 10))

        list_frame = ttk.Frame(self)
        list_frame.pack(padx=15, pady=5, fill="both", expand=True)
        self.week_listbox = tk.Listbox(list_frame, width=22, font=("Segoe UI", sf(9)))
        week_scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.week_listbox.yview)
        self.week_listbox.configure(yscrollcommand=week_scrollbar.set)
        self.week_listbox.pack(side="left", fill="y")
        week_scrollbar.pack(side="left", fill="y")
        self.week_listbox.bind("<<ListboxSelect>>", lambda e: self._show_week_detail())

        self.detail_text = tk.Text(list_frame, wrap="word", width=40, height=18, font=("Segoe UI", sf(9)))
        self.detail_text.pack(side="left", fill="both", expand=True, padx=(10, 0))

        self.history = []
        self._populate()

        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text=t("weekhistory_reload_button"),
                   command=self.reload_selected).grid(row=0, column=0, padx=5)
        ttk.Button(btn_frame, text=t("weekhistory_delete_button"),
                   command=self.delete_selected).grid(row=0, column=1, padx=5)

        tk.Frame(self, height=SCROLL_BOTTOM_PADDING, background=COLOR_BG).pack(fill="x")

    def _populate(self):
        self.week_listbox.delete(0, tk.END)
        self.detail_text.delete("1.0", tk.END)
        self.history = sorted(load_weekly_plan_history(), key=lambda h: h.get("week_start", ""), reverse=True)
        if not self.history:
            self.week_listbox.insert(tk.END, t("weekhistory_no_archived_weeks"))
            return
        for entry in self.history:
            self.week_listbox.insert(tk.END, t("weekhistory_week_label", week=entry.get('week_start', '?')))

    def _show_week_detail(self):
        self.detail_text.delete("1.0", tk.END)
        sel = self.week_listbox.curselection()
        if not sel or not self.history or sel[0] >= len(self.history):
            return
        entry = self.history[sel[0]]
        plan = entry.get("plan", {})
        self.detail_text.insert(tk.END, t("weekhistory_saved_on", date=entry.get('saved_at', '?')))
        has_content = False
        for day in WEEKDAYS:
            day_data = plan.get(day) or {}
            filled_slots = {slot: info for slot, info in day_data.items() if info}
            if not filled_slots:
                continue
            has_content = True
            self.detail_text.insert(tk.END, t("weekhistory_day_heading", day=translate_weekday_name(day)))
            for slot, info in filled_slots.items():
                self.detail_text.insert(
                    tk.END,
                    t("weekhistory_slot_line", slot=translate_mealslot_name(slot), recipe=info.get('recipe_name', '?'),
                      persons=info.get('persons', '?'))
                )
            self.detail_text.insert(tk.END, "\n")
        if not has_content:
            self.detail_text.insert(tk.END, t("weekhistory_empty_week"))

    def reload_selected(self):
        sel = self.week_listbox.curselection()
        if not sel or not self.history or sel[0] >= len(self.history):
            messagebox.showinfo(t("common_info"), t("weekhistory_select_week_first"))
            return
        entry = self.history[sel[0]]
        if not ask_yes_no(
            t("common_confirm"),
            t("weekhistory_reload_confirm_message", week=entry.get('week_start', '?'))
        ):
            return
        if self.parent_window is not None and hasattr(self.parent_window, "apply_plan"):
            self.parent_window.apply_plan(entry.get("plan", {}))
        else:
            save_weekly_plan(entry.get("plan", {}))
            self.app.show_toast(t("weekhistory_reloaded_home"))
        self.destroy()

    def delete_selected(self):
        sel = self.week_listbox.curselection()
        if not sel or not self.history or sel[0] >= len(self.history):
            messagebox.showinfo(t("common_info"), t("weekhistory_select_week_first"))
            return
        entry = self.history[sel[0]]
        week_key = entry.get("week_start")
        if not ask_yes_no(
            t("common_confirm"), t("weekhistory_delete_confirm_message", week=week_key)
        ):
            return
        all_history = load_weekly_plan_history()
        all_history = [h for h in all_history if h.get("week_start") != week_key]
        save_weekly_plan_history(all_history)
        self._populate()


class WeeklyPlanTemplatesWindow(tk.Toplevel):
    """Fenêtre pour enregistrer le planning actuel comme modèle réutilisable
    (ex. « Semaine légère », « Semaine végétarienne »), et pour appliquer
    d'un clic un modèle déjà enregistré à un planning vide."""

    def __init__(self, app, parent_window):
        super().__init__(parent_window)
        self.app = app
        self.parent_window = parent_window
        self.title(t("weektemplates_title"))
        fit_window_to_workarea(self, gs(560), gs(700), margin=18)
        safe_minsize(self, gs(460), gs(460))
        self.resizable(True, True)
        self.grab_set()

        ttk.Label(self, text=t("weektemplates_heading"), font=("Segoe UI", sf(14), "bold")).pack(pady=(15, 5))
        ttk.Label(
            self, text=t("weektemplates_intro"),
            font=("Segoe UI", sf(8)), foreground=COLOR_TEXT_MUTED, justify="center"
        ).pack(pady=(0, 10))

        save_frame = ttk.Frame(self)
        save_frame.pack(pady=(0, 10), padx=15, fill="x")
        ttk.Label(save_frame, text=t("weektemplates_name_label")).pack(side="left")
        self.new_name_entry = ttk.Entry(save_frame)
        self.new_name_entry.pack(side="left", padx=5, fill="x", expand=True)
        ttk.Button(save_frame, text=t("weektemplates_save_button"),
                   command=self.save_as_template).pack(side="left", padx=(5, 0))

        list_frame = ttk.Frame(self)
        list_frame.pack(padx=15, pady=5, fill="both", expand=True)
        self.listbox = tk.Listbox(list_frame, font=("Segoe UI", sf(9)))
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scrollbar.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.listbox.bind("<Double-Button-1>", lambda e: self.apply_selected())

        self.template_names = []
        self._populate()

        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text=t("weektemplates_apply_button"),
                   command=self.apply_selected).grid(row=0, column=0, padx=5)
        ttk.Button(btn_frame, text=t("weektemplates_delete_button"),
                   command=self.delete_selected).grid(row=0, column=1, padx=5)

        tk.Frame(self, height=SCROLL_BOTTOM_PADDING, background=COLOR_BG).pack(fill="x")

    def _populate(self):
        self.listbox.delete(0, tk.END)
        templates = load_weekly_plan_templates()
        self.template_names = sorted(templates.keys(), key=ingredient_sort_key)
        if not self.template_names:
            self.listbox.insert(tk.END, t("weektemplates_none_saved"))
            return
        for name in self.template_names:
            self.listbox.insert(tk.END, name)

    def save_as_template(self):
        name = self.new_name_entry.get().strip()
        if not name:
            messagebox.showerror(t("common_error"), t("weektemplates_error_name_required"))
            return
        plan, _ = self.parent_window._collect_selection()
        if plan is None:
            return
        if not any(plan.values()):
            messagebox.showinfo(t("common_info"), t("weektemplates_empty_plan"))
            return
        templates = load_weekly_plan_templates()
        templates[name] = plan
        save_weekly_plan_templates(templates)
        self.new_name_entry.delete(0, tk.END)
        self._populate()
        messagebox.showinfo(t("allrecipes_list_saved_title"), t("weektemplates_saved_message", name=name))

    def apply_selected(self):
        sel = self.listbox.curselection()
        if not sel or not self.template_names or sel[0] >= len(self.template_names):
            messagebox.showinfo(t("common_info"), t("weektemplates_select_template_first"))
            return
        name = self.template_names[sel[0]]
        if not ask_yes_no(
            t("common_confirm"),
            t("weektemplates_apply_confirm_message", name=name)
        ):
            return
        templates = load_weekly_plan_templates()
        self.parent_window.apply_plan(templates.get(name, {}))
        self.destroy()

    def delete_selected(self):
        sel = self.listbox.curselection()
        if not sel or not self.template_names or sel[0] >= len(self.template_names):
            messagebox.showinfo(t("common_info"), t("weektemplates_select_template_first"))
            return
        name = self.template_names[sel[0]]
        if not ask_yes_no(t("common_confirm"), t("weektemplates_delete_confirm_message", name=name)):
            return
        templates = load_weekly_plan_templates()
        templates.pop(name, None)
        save_weekly_plan_templates(templates)
        self._populate()


class WeeklyPlanWindow(ShoppingCartRenderMixin, tk.Toplevel):
    """Planning des repas de la semaine (petit-déjeuner, déjeuner en 3 temps,
    dîner en 3 temps), avec génération automatique de la liste de courses
    pour l'ensemble des recettes planifiées."""

    _shopping_empty_message_key = "weekplan_empty_list_message"
    _shopping_heading_key = "weekplan_total_list_heading"

    MEAL_SLOTS = [
        "Petit-déjeuner",
        "Déjeuner — Entrée", "Déjeuner — Plat", "Déjeuner — Dessert",
        "Dîner — Entrée", "Dîner — Plat", "Dîner — Dessert",
    ]

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title(t("weekplan_title"))
        screen_height = get_usable_screen_height(self)
        fit_window_to_workarea(self, gs(1620), screen_height, margin=18)
        safe_minsize(self, gs(600), gs(400))
        self.resizable(True, True)
        self.grab_set()

        self.manual_items = []  # ingrédients ajoutés manuellement (hors planning) : [{"name","quantity","unit"}]
        self.plan = load_weekly_plan()  # {jour: {créneau: {'recipe_name':.., 'persons':..}}}
        recipe_names = [r["name"] for r in self.app.recipes]

        ttk.Label(self, text=t("weekplan_title"), font=("Segoe UI", sf(14), "bold")).pack(pady=10)
        ttk.Label(self, text=t("weekplan_subtitle"),
                  font=("Segoe UI", sf(8)), foreground=COLOR_TEXT_MUTED).pack()

        # Largeurs de colonnes forcées identiquement dans l'en-tête fixe et
        # dans la grille défilante en dessous, pour qu'elles restent alignées
        # verticalement quel que soit le contenu de chaque cellule.
        COL0_WIDTH = 140
        DAY_COL_WIDTH = 130
        # Largeur approximative de l'ascenseur vertical de la grille, pour
        # compenser côté en-tête et garder les colonnes de jours bien alignées
        # avec celles de la grille (qui dispose d'un peu moins de largeur
        # utile à cause de cet ascenseur).
        SCROLLBAR_WIDTH_ESTIMATE = 18

        # ---- En-tête des jours de la semaine, fixe : reste toujours visible
        # à l'écran, même en faisant défiler la grille vers le bas. ----
        header_canvas = tk.Canvas(self, height=gs(38), highlightthickness=0)
        header_canvas.pack(fill="x", padx=(10, 10 + SCROLLBAR_WIDTH_ESTIMATE))
        # Les jours sont dessinés après calcul des dimensions réelles des
        # colonnes du calendrier : plus de décalage entre en-tête et cellules.
        self._planning_header_canvas = header_canvas
        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=10)

        grid_container = ttk.Frame(self)
        grid_container.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        h_scrollbar = ttk.Scrollbar(grid_container, orient="horizontal")
        v_scrollbar = ttk.Scrollbar(grid_container, orient="vertical")
        def _on_plan_xscroll(first, last):
            h_scrollbar.set(first, last)
            try:
                header_canvas.xview_moveto(first)
            except Exception as exc:
                log_internal_error("planning_header_scroll", exc)
        canvas = tk.Canvas(grid_container, highlightthickness=0,
                            xscrollcommand=_on_plan_xscroll, yscrollcommand=v_scrollbar.set)
        def _sync_xview(*args):
            canvas.xview(*args)
            header_canvas.xview(*args)
        h_scrollbar.config(command=_sync_xview)
        v_scrollbar.config(command=canvas.yview)
        v_scrollbar.pack(side="right", fill="y")
        h_scrollbar.pack(side="bottom", fill="x")
        canvas.pack(side="left", fill="both", expand=True)

        calendar_frame = ttk.Frame(canvas)
        calendar_frame.grid_columnconfigure(0, minsize=COL0_WIDTH)
        for col in range(1, len(WEEKDAYS) + 1):
            calendar_frame.grid_columnconfigure(col, minsize=DAY_COL_WIDTH)
        def _sync_planning_header(_event=None):
            try:
                calendar_frame.update_idletasks()
                header_canvas.delete("all")
                total_width = 0
                for col in range(0, len(WEEKDAYS) + 1):
                    bbox = calendar_frame.grid_bbox(col, 0)
                    if not bbox:
                        continue
                    x, _y, width, _height = bbox
                    total_width = max(total_width, x + width)
                    if col == 0:
                        continue
                    day = WEEKDAYS[col - 1]
                    header_canvas.create_text(
                        x + width / 2, gs(18),
                        text=translate_weekday_name(day),
                        font=("Segoe UI", sf(9), "bold"),
                        fill=COLOR_ACCENT_DARK,
                        anchor="center",
                    )
                header_canvas.configure(
                    scrollregion=(0, 0, max(1, total_width), gs(38))
                )
            except Exception as exc:
                log_internal_error("planning_header_alignment", exc)

        def _on_calendar_configure(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            _sync_planning_header()

        calendar_frame.bind("<Configure>", _on_calendar_configure)
        canvas.create_window((0, 0), window=calendar_frame, anchor="nw")

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        _ui_bind_local_mousewheel(canvas, calendar_frame, _on_mousewheel)

        # Les créneaux de repas (lignes), sans ligne d'en-tête ici puisqu'elle
        # est maintenant affichée séparément, fixe, au-dessus de la grille.
        self.widgets = {}  # (jour, créneau) -> (combo, pers_entry)
        for row_index, slot in enumerate(self.MEAL_SLOTS):
            ttk.Label(calendar_frame, text=translate_mealslot_name(slot), font=("Segoe UI", sf(9)), anchor="w",
                      width=17, wraplength=120, justify="left").grid(
                row=row_index, column=0, padx=(2, 6), pady=4, sticky="w")
            for col, day in enumerate(WEEKDAYS, start=1):
                cell = tk.Frame(calendar_frame, background=COLOR_CARD, highlightbackground=COLOR_BORDER,
                                 highlightthickness=1)
                cell.grid(row=row_index, column=col, padx=2, pady=2, sticky="nsew")
                day_data = self.plan.get(day) or {}
                slot_data = day_data.get(slot) or {}
                combo = ttk.Combobox(cell, values=[t("common_none_option")] + recipe_names,
                                      state="readonly", width=13)
                combo.set(slot_data.get("recipe_name") or t("common_none_option"))
                combo.pack(padx=3, pady=(3, 1))
                pers_frame = ttk.Frame(cell, style="Card.TFrame")
                pers_frame.pack(padx=3, pady=(0, 3))
                ttk.Label(pers_frame, text="👤", style="Card.TLabel").pack(side="left")
                pers_entry = ttk.Entry(pers_frame, width=4)
                selected_name = slot_data.get("recipe_name")
                selected_recipe = find_recipe_by_name(self.app.recipes, selected_name) if selected_name else None
                default_for_recipe = (selected_recipe or {}).get("default_persons", 4) or 4
                pers_entry.insert(0, str(slot_data.get("persons", default_for_recipe)))
                pers_entry.pack(side="left")
                combo.bind(
                    "<<ComboboxSelected>>",
                    lambda e, c=combo, p=pers_entry: self._sync_slot_default_persons(c, p)
                )
                self.widgets[(day, slot)] = (combo, pers_entry)

        self.after_idle(_sync_planning_header)

        tk.Frame(calendar_frame, height=SCROLL_BOTTOM_PADDING, background=COLOR_BG).grid(
            row=len(self.MEAL_SLOTS), column=0, columnspan=len(WEEKDAYS) + 1, sticky="ew")

        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=5)
        for col in range(5):
            btn_frame.columnconfigure(col, weight=1)
        compact_actions = screen_height < 760 or self.winfo_screenheight() < 760
        ttk.Button(btn_frame, text=t("weekplan_save_button"), command=self.save_plan).grid(row=0,column=0,padx=3,pady=2,sticky="ew")
        ttk.Button(btn_frame, text=t("weekplan_clear_button"), command=self.clear_plan).grid(row=0,column=1,padx=3,pady=2,sticky="ew")
        ttk.Button(btn_frame, text=t("weekplan_compute_button"), command=self.compute).grid(row=0,column=2,padx=3,pady=2,sticky="ew")
        ttk.Button(btn_frame, text=t("weekplan_checklist_button"), command=self.open_checklist).grid(row=0,column=3,padx=3,pady=2,sticky="ew")
        if compact_actions:
            more = ttk.Button(btn_frame, text=t("weekplan_more_actions"), style="Secondary.TButton")
            more.grid(row=0,column=4,padx=3,pady=2,sticky="ew")
            _ui_attach_more_menu(more, [
                (t("weekplan_export_ics_button"), self.export_ics),
                (t("allrecipes_export_button"), self.open_export_dialog),
                (t("allrecipes_print_button"), self.print_list),
                (t("allrecipes_add_manual_ingredient_button"), self.open_add_manual_ingredient),
                (t("allrecipes_save_list_button"), self.save_list_for_later),
                (t("allrecipes_load_list_button"), self.open_saved_lists),
                (t("weekhistory_heading"), self.open_history),
                (t("weektemplates_heading"), self.open_templates),
            ])
        else:
            ttk.Button(btn_frame, text=t("weekplan_export_ics_button"), command=self.export_ics).grid(row=0,column=4,padx=3,pady=2,sticky="ew")
            ttk.Button(btn_frame, text=t("allrecipes_export_button"), command=self.open_export_dialog).grid(row=1,column=0,columnspan=2,padx=3,pady=2,sticky="ew")
            ttk.Button(btn_frame, text=t("allrecipes_print_button"), command=self.print_list).grid(row=1,column=2,columnspan=2,padx=3,pady=2,sticky="ew")
            more = ttk.Button(btn_frame, text=t("weekplan_more_actions"), style="Secondary.TButton")
            more.grid(row=1,column=4,padx=3,pady=2,sticky="ew")
            _ui_attach_more_menu(more, [
                (t("allrecipes_add_manual_ingredient_button"), self.open_add_manual_ingredient),
                (t("allrecipes_save_list_button"), self.save_list_for_later),
                (t("allrecipes_load_list_button"), self.open_saved_lists),
                (t("weekhistory_heading"), self.open_history),
                (t("weektemplates_heading"), self.open_templates),
            ])

        # ---- Zone de résultat éditable : chaque ingrédient peut voir sa
        # quantité modifiée ou être retiré, sans devoir tout recalculer. ----
        self.current_items = []       # liste plate éditable [{'name','quantity','unit','rayon'}, ...]
        self._shopping_sort_var = tk.StringVar(value="rayon")
        self.last_chosen_recipes = []  # recettes utilisées lors du dernier calcul (pour les exports)

        result_container = ttk.Frame(self)
        result_container.pack(pady=10, padx=15, fill="both", expand=True)
        result_canvas = tk.Canvas(result_container, highlightthickness=0)
        result_scrollbar = ttk.Scrollbar(result_container, orient="vertical", command=result_canvas.yview)
        self.result_frame = ttk.Frame(result_canvas)
        self.result_frame.bind(
            "<Configure>", lambda e: result_canvas.configure(scrollregion=result_canvas.bbox("all"))
        )
        result_canvas.create_window((0, 0), window=self.result_frame, anchor="nw")
        result_canvas.configure(yscrollcommand=result_scrollbar.set)
        result_canvas.pack(side="left", fill="both", expand=True)
        result_scrollbar.pack(side="right", fill="y")

        def _on_result_mousewheel(event):
            result_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        _ui_bind_local_mousewheel(result_canvas, self.result_frame, _on_result_mousewheel)

        self._render_shopping_list()

    def open_add_manual_ingredient(self):
        AddManualIngredientDialog(self.app, self)

    def open_export_dialog(self):
        ExportFormatDialog(self, self.export_txt, self.export_excel, self.export_pdf)

    def add_manual_items(self, items):
        self.manual_items.extend(items)
        self.compute()  # actualise immédiatement la liste de courses affichée

    def save_list_for_later(self):
        if not self.current_items:
            messagebox.showinfo(t("common_info"), t("allrecipes_calculate_list_first"),
                                 parent=self)
            return
        name = simpledialog.askstring(
            t("allrecipes_save_list_dialog_title"), t("allrecipes_save_list_dialog_prompt"), parent=self
        )
        if not name:
            self.lift()
            self.focus_force()
            return
        name = name.strip()
        if not name:
            self.lift()
            self.focus_force()
            return
        lists = load_saved_shopping_lists()
        lists = [entry for entry in lists if entry["name"].lower() != name.lower()]
        lists.append({
            "name": name,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "items": [dict(item) for item in self.current_items],
        })
        save_saved_shopping_lists(lists)
        messagebox.showinfo(t("allrecipes_list_saved_title"), t("allrecipes_list_saved_message", name=name), parent=self)
        self.lift()
        self.focus_force()

    def open_saved_lists(self):
        SavedShoppingListsWindow(self.app, self)

    def load_saved_list(self, items):
        self.current_items = [dict(item) for item in items]
        self.last_chosen_recipes = []
        self._render_shopping_list()

    def _current_export_data(self):
        if not self.current_items:
            messagebox.showinfo(t("common_info"), t("weekplan_calculate_list_for_export"))
            return None
        grouped_totals = grouped_totals_from_flat_items(self.current_items)
        return self.last_chosen_recipes, grouped_totals

    def _sync_slot_default_persons(self, combo, pers_entry):
        name = combo.get()
        if not name or name == t("common_none_option"):
            return
        recipe = find_recipe_by_name(self.app.recipes, name)
        if recipe is None:
            return
        value = recipe.get("default_persons", 4) or 4
        pers_entry.delete(0, tk.END)
        pers_entry.insert(0, str(value))

    def _collect_selection(self):
        new_plan = {}
        pairs = []
        for day in WEEKDAYS:
            for slot in self.MEAL_SLOTS:
                combo, pers_entry = self.widgets[(day, slot)]
                name = combo.get()
                if not name or name == t("common_none_option"):
                    continue
                try:
                    persons = parse_positive_number(pers_entry.get())
                except ValueError:
                    messagebox.showerror(
                        t("common_error"),
                        t("weekplan_invalid_persons_for_slot", day=translate_weekday_name(day), slot=translate_mealslot_name(slot))
                    )
                    return None, None
                recipe = find_recipe_by_name(self.app.recipes, name)
                if recipe is None:
                    continue
                new_plan.setdefault(day, {})[slot] = {
                    "recipe_id": recipe.get("id"), "recipe_name": recipe.get("name"),
                    "persons": persons
                }
                pairs.append((recipe, persons))
        return new_plan, pairs

    def save_plan(self):
        new_plan, pairs = self._collect_selection()
        if new_plan is None:
            return
        save_weekly_plan(new_plan)
        archive_current_week(new_plan)
        self.plan = new_plan
        messagebox.showinfo(t("allrecipes_list_saved_title"), t("weekplan_saved_message"))

    def clear_plan(self):
        if not ask_yes_no(t("common_confirm"), t("weekplan_clear_confirm_message")):
            return
        for (day, slot), (combo, pers_entry) in self.widgets.items():
            combo.set(t("common_none_option"))
        save_weekly_plan({})
        self.plan = {}

    def apply_plan(self, plan):
        """Recharge un planning donné (depuis l'historique ou un modèle)
        dans les cases actuellement affichées, sans reconstruire la
        fenêtre. Ne l'enregistre pas automatiquement : il faut toujours
        cliquer sur « 💾 Enregistrer le planning » pour le conserver."""
        for (day, slot), (combo, pers_entry) in self.widgets.items():
            day_data = plan.get(day) or {}
            slot_data = day_data.get(slot) or {}
            combo.set(slot_data.get("recipe_name") or t("common_none_option"))
            pers_entry.delete(0, tk.END)
            selected_name = slot_data.get("recipe_name")
            selected_recipe = find_recipe_by_ref(self.app.recipes, slot_data) if selected_name or slot_data.get("recipe_id") else None
            default_for_recipe = (selected_recipe or {}).get("default_persons", 4) or 4
            pers_entry.insert(0, str(slot_data.get("persons", default_for_recipe)))

    def open_history(self):
        WeeklyPlanHistoryWindow(self.app, self)

    def open_templates(self):
        WeeklyPlanTemplatesWindow(self.app, self)

    def export_ics(self):
        new_plan, pairs = self._collect_selection()
        if new_plan is None:
            return
        if not new_plan:
            messagebox.showinfo(t("common_info"), t("weekplan_assign_recipe_first"))
            return
        path = filedialog.asksaveasfilename(
            title=t("weekplan_export_ics_title"),
            defaultextension=".ics",
            filetypes=[("Fichier calendrier (.ics)", "*.ics")],
            initialfile="planning_repas.ics"
        )
        if not path:
            return
        try:
            content = build_weekly_plan_ics(new_plan)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            messagebox.showerror(t("common_error"), t("common_export_failed", error=e))
            return
        messagebox.showinfo(
            t("common_export_success_title"),
            t("weekplan_ics_export_success_message", path=path)
        )

    def compute(self):
        new_plan, pairs = self._collect_selection()
        if new_plan is None:
            return None
        if not pairs and not self.manual_items:
            messagebox.showinfo(t("common_info"), t("weekplan_assign_or_manual"))
            return None

        if self.manual_items:
            pairs = list(pairs) + [({"ingredients": list(self.manual_items)}, 1)]

        grouped_totals = compute_grouped_totals(pairs)
        day_order = {d: i for i, d in enumerate(WEEKDAYS)}
        slot_order = {s: i for i, s in enumerate(self.MEAL_SLOTS)}
        chosen_recipes = []
        for day, slots in new_plan.items():
            for slot, info in slots.items():
                chosen_recipes.append((f"{day} — {slot} : {info['recipe_name']}", info["persons"]))
        chosen_recipes.sort(
            key=lambda t: (day_order.get(t[0].split(" — ")[0], 99),
                            slot_order.get(t[0].split(" — ")[1].split(" : ")[0], 99))
        )

        self.current_items = []
        for rayon, items in grouped_totals:
            for name, qty, unit in items:
                self.current_items.append({"name": name, "quantity": qty, "unit": unit, "rayon": rayon})
        self.last_chosen_recipes = chosen_recipes
        self._render_shopping_list()

        return chosen_recipes, grouped_totals

    def export_txt(self):
        result = self._current_export_data()
        if result is None:
            return
        chosen_recipes, grouped_totals = result
        path = filedialog.asksaveasfilename(
            title=t("weekplan_export_shopping_list_title"), defaultextension=".txt",
            filetypes=[("Fichier texte", "*.txt")], initialfile="liste_de_courses_semaine.txt"
        )
        if not path:
            return
        try:
            write_shopping_list_txt(path, t("weekplan_shopping_list_title"), chosen_recipes, grouped_totals)
        except Exception as e:
            messagebox.showerror(t("common_error"), t("common_export_failed", error=e))
            return
        messagebox.showinfo(t("common_export_success_title"), t("weekplan_list_saved_message", path=path))

    def export_excel(self):
        if not OPENPYXL_AVAILABLE:
            messagebox.showerror(t("common_module_missing"), t("weekplan_excel_module_missing"))
            return
        result = self._current_export_data()
        if result is None:
            return
        chosen_recipes, grouped_totals = result
        path = filedialog.asksaveasfilename(
            title=t("weekplan_export_shopping_list_title"), defaultextension=".xlsx",
            filetypes=[("Fichier Excel", "*.xlsx")], initialfile="liste_de_courses_semaine.xlsx"
        )
        if not path:
            return
        try:
            wb = build_shopping_list_workbook(chosen_recipes, grouped_totals)
            wb.save(path)
        except Exception as e:
            messagebox.showerror(t("common_error"), t("common_export_failed", error=e))
            return
        messagebox.showinfo(t("common_export_success_title"), t("weekplan_list_saved_message", path=path))

    def export_pdf(self):
        if not REPORTLAB_AVAILABLE:
            messagebox.showerror(t("common_module_missing"), t("weekplan_pdf_module_missing"))
            return
        result = self._current_export_data()
        if result is None:
            return
        chosen_recipes, grouped_totals = result
        path = filedialog.asksaveasfilename(
            title=t("weekplan_export_shopping_list_title"), defaultextension=".pdf",
            filetypes=[("Fichier PDF", "*.pdf")], initialfile="liste_de_courses_semaine.pdf"
        )
        if not path:
            return
        try:
            build_shopping_list_pdf(path, t("weekplan_shopping_list_title"), chosen_recipes, grouped_totals)
        except Exception as e:
            messagebox.showerror(t("common_error"), t("common_export_failed", error=e))
            return
        messagebox.showinfo(t("common_export_success_title"), t("weekplan_list_saved_message", path=path))

    def print_list(self):
        if not REPORTLAB_AVAILABLE:
            messagebox.showerror(t("common_module_missing"), t("weekplan_print_module_missing"))
            return
        result = self._current_export_data()
        if result is None:
            return
        chosen_recipes, grouped_totals = result
        temp_path = get_temp_pdf_path("planning_semaine")
        try:
            build_shopping_list_pdf(temp_path, t("weekplan_shopping_list_title"), chosen_recipes, grouped_totals)
        except Exception as e:
            messagebox.showerror(t("common_error"), t("common_print_failed", error=e))
            return
        print_document(self, temp_path, t("weekplan_print_label"))

    def open_checklist(self):
        result = self._current_export_data()
        if result is None:
            return
        chosen_recipes, grouped_totals = result
        ShoppingChecklistWindow(self.app, grouped_totals, title=t("weekplan_shopping_list_title"))


class MenuManagerWindow(tk.Toplevel):
    """Gestion des menus (combinaisons de plusieurs recettes) : création,
    édition, suppression."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title(t("menumanager_title"))
        fit_window_to_workarea(self, gs(420), gs(480), margin=14)
        self.grab_set()

        ttk.Label(self, text=t("menumanager_list_label"), font=("Segoe UI", sf(11), "bold")).pack(pady=(10, 5))

        self.listbox = tk.Listbox(self, width=40, height=14, font=("Segoe UI", sf(9)))
        self.listbox.pack(pady=5, padx=15, fill="both", expand=True)
        self.menus = []
        self._populate()

        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text=t("menumanager_new_button"), command=self.new_menu).grid(row=0, column=0, padx=5)
        ttk.Button(btn_frame, text=t("home_open_button"), command=self.open_menu).grid(row=0, column=1, padx=5)
        ttk.Button(btn_frame, text=t("managerecipes_delete_button"), command=self.delete_menu).grid(row=0, column=2, padx=5)

    def _populate(self):
        self.listbox.delete(0, tk.END)
        self.menus = load_menus()
        for menu in self.menus:
            self.listbox.insert(tk.END, t("menumanager_recipe_count", name=menu['name'], count=len(menu.get('items', []))))

    def _selected_index(self):
        sel = self.listbox.curselection()
        if not sel:
            messagebox.showinfo(t("common_info"), t("menumanager_select_menu_first"))
            return None
        return sel[0]

    def new_menu(self):
        MenuFormWindow(self.app, self, menu_index=None)

    def open_menu(self):
        idx = self._selected_index()
        if idx is None:
            return
        MenuFormWindow(self.app, self, menu_index=idx)

    def delete_menu(self):
        idx = self._selected_index()
        if idx is None:
            return
        menus = load_menus()
        name = menus[idx]["name"]
        if not ask_yes_no(t("common_confirm"), t("menumanager_delete_confirm", name=name)):
            return
        menus.pop(idx)
        save_menus(menus)
        self._populate()


class MenuFormWindow(ShoppingCartRenderMixin, tk.Toplevel):
    """Fenêtre de création/édition d'un menu : nom + liste de recettes avec
    nombre de personnes, export/impression de sa liste de courses."""

    _shopping_empty_message_key = "menuform_empty_list_message"
    _shopping_heading_key = "menuform_total_list_heading"

    CATEGORY_ORDER = {"Apéro": 0, "Entrée": 1, "Plat": 2, "Sauce": 3,
                       "Dessert": 4, "Boisson": 5, "Autre": 6}

    def __init__(self, app, manager, menu_index=None):
        super().__init__(app)
        self.app = app
        self.manager = manager
        self.menu_index = menu_index
        self.editing = menu_index is not None
        menus = load_menus()
        self.existing_menu = menus[menu_index] if self.editing else None

        self.title(t("menuform_title_edit") if self.editing else t("menuform_title_new"))
        screen_height = get_usable_screen_height(self)
        fit_window_to_workarea(self, gs(700), screen_height, margin=18)
        safe_minsize(self, gs(560), gs(400))
        self.resizable(True, True)
        self.grab_set()

        self.manual_items = []  # ingrédients ajoutés manuellement (hors menu) : [{"name","quantity","unit"}]

        ttk.Label(self, text=t("menuform_name_label"), font=("Segoe UI", sf(11), "bold")).pack(pady=(10, 5))
        self.name_entry = ttk.Entry(self, width=40)
        self.name_entry.pack()
        if self.editing:
            self.name_entry.insert(0, self.existing_menu["name"])

        self.items = [dict(it) for it in self.existing_menu.get("items", [])] if self.editing else []

        ttk.Label(self, text=t("menuform_add_recipe_label"), font=("Segoe UI", sf(10), "bold")).pack(pady=(15, 5))
        add_frame = ttk.Frame(self)
        add_frame.pack(padx=15, fill="x")
        recipe_names = [r["name"] for r in self.app.recipes]
        self.recipe_combo = ttk.Combobox(add_frame, values=recipe_names, state="readonly", width=26)
        self.recipe_combo.pack(side="left", padx=(0, 5))
        if recipe_names:
            self.recipe_combo.current(0)
        ttk.Label(add_frame, text=t("menuform_persons_short_label")).pack(side="left")
        self.add_persons_entry = ttk.Entry(add_frame, width=5)
        initial_persons = 4
        if recipe_names:
            first_recipe = find_recipe_by_name(self.app.recipes, recipe_names[0])
            initial_persons = (first_recipe or {}).get("default_persons", 4) or 4
        self.add_persons_entry.insert(0, str(initial_persons))
        self.add_persons_entry.pack(side="left", padx=5)
        self.recipe_combo.bind("<<ComboboxSelected>>", lambda e: self._sync_menu_default_persons())
        ttk.Button(add_frame, text=t("menuform_add_button"), command=self.add_item).pack(side="left", padx=5)

        ttk.Label(self, text=t("menuform_recipes_label"), font=("Segoe UI", sf(10), "bold")).pack(pady=(15, 5))
        self.items_listbox = tk.Listbox(self, width=55, height=7, font=("Segoe UI", sf(9)))
        self.items_listbox.pack(padx=15, fill="x")
        self._refresh_items_listbox()
        ttk.Button(self, text=t("menuform_remove_button"), command=self.remove_item).pack(pady=5)

        export_frame = ttk.Frame(self)
        export_frame.pack(pady=6, padx=15, fill="x")
        for col in range(4):
            export_frame.columnconfigure(col, weight=1)
        ttk.Button(export_frame, text=t("menuform_save_button"), style="Primary.TButton",
                   command=self.save_menu).grid(row=0, column=0, padx=4, sticky="ew")
        ttk.Button(export_frame, text=t("menuform_compute_button"),
                   command=self.compute).grid(row=0, column=1, padx=4, sticky="ew")
        ttk.Button(export_frame, text=t("weekplan_checklist_button"),
                   command=self.open_checklist).grid(row=0, column=2, padx=4, sticky="ew")
        more_button = ttk.Button(export_frame, text=t("menuform_more_actions"))
        more_button.grid(row=0, column=3, padx=4, sticky="ew")
        ttk.Button(
            export_frame,
            text=t("menuform_send_to_normal_shopping"),
            style="Secondary.TButton",
            command=self.send_to_normal_shopping_list
        ).grid(row=1, column=0, columnspan=4, padx=4, pady=(6, 0), sticky="ew")
        more_menu = tk.Menu(more_button, tearoff=0)
        more_menu.add_command(label=t("allrecipes_export_button"), command=self.open_export_dialog)
        more_menu.add_command(label=t("allrecipes_print_button"), command=self.print_list)
        more_menu.add_separator()
        more_menu.add_command(label=t("allrecipes_add_manual_ingredient_button"), command=self.open_add_manual_ingredient)
        more_menu.add_command(label=t("allrecipes_save_list_button"), command=self.save_list_for_later)
        more_menu.add_command(label=t("allrecipes_load_list_button"), command=self.open_saved_lists)
        more_button.configure(command=lambda: more_menu.tk_popup(
            more_button.winfo_rootx(), more_button.winfo_rooty() + more_button.winfo_height()))

        # ---- Zone de résultat éditable : chaque ingrédient peut voir sa
        # quantité modifiée ou être retiré, sans devoir tout recalculer. ----
        self.current_items = []       # liste plate éditable [{'name','quantity','unit','rayon'}, ...]
        self._shopping_sort_var = tk.StringVar(value="rayon")
        self.last_chosen_recipes = []  # recettes utilisées lors du dernier calcul (pour les exports)

        result_container = ttk.Frame(self)
        result_container.pack(pady=10, padx=15, fill="both", expand=True)
        result_canvas = tk.Canvas(result_container, highlightthickness=0)
        result_scrollbar = ttk.Scrollbar(result_container, orient="vertical", command=result_canvas.yview)
        self.result_frame = ttk.Frame(result_canvas)
        self.result_frame.bind(
            "<Configure>", lambda e: result_canvas.configure(scrollregion=result_canvas.bbox("all"))
        )
        result_canvas.create_window((0, 0), window=self.result_frame, anchor="nw")
        result_canvas.configure(yscrollcommand=result_scrollbar.set)
        result_canvas.pack(side="left", fill="both", expand=True)
        result_scrollbar.pack(side="right", fill="y")

        def _on_result_mousewheel(event):
            result_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        _ui_bind_local_mousewheel(result_canvas, self.result_frame, _on_result_mousewheel)

        self._render_shopping_list()

    def open_add_manual_ingredient(self):
        AddManualIngredientDialog(self.app, self)

    def open_export_dialog(self):
        ExportFormatDialog(self, self.export_txt, self.export_excel, self.export_pdf)

    def add_manual_items(self, items):
        self.manual_items.extend(items)
        self.compute()  # actualise immédiatement la liste de courses affichée

    def save_list_for_later(self):
        if not self.current_items:
            messagebox.showinfo(t("common_info"), t("allrecipes_calculate_list_first"),
                                 parent=self)
            return
        name = simpledialog.askstring(
            t("allrecipes_save_list_dialog_title"), t("allrecipes_save_list_dialog_prompt"), parent=self
        )
        if not name:
            self.lift()
            self.focus_force()
            return
        name = name.strip()
        if not name:
            self.lift()
            self.focus_force()
            return
        lists = load_saved_shopping_lists()
        lists = [entry for entry in lists if entry["name"].lower() != name.lower()]
        lists.append({
            "name": name,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "items": [dict(item) for item in self.current_items],
        })
        save_saved_shopping_lists(lists)
        messagebox.showinfo(t("allrecipes_list_saved_title"), t("allrecipes_list_saved_message", name=name), parent=self)
        self.lift()
        self.focus_force()

    def open_saved_lists(self):
        SavedShoppingListsWindow(self.app, self)

    def load_saved_list(self, items):
        self.current_items = [dict(item) for item in items]
        self.last_chosen_recipes = []
        self._render_shopping_list()

    def _current_export_data(self):
        if not self.current_items:
            messagebox.showinfo(t("common_info"), t("menuform_calculate_list_for_export"))
            return None
        grouped_totals = grouped_totals_from_flat_items(self.current_items)
        return self.last_chosen_recipes, grouped_totals

    def _refresh_items_listbox(self):
        self.items_listbox.delete(0, tk.END)
        for item in self.items:
            recipe = find_recipe_by_ref(self.app.recipes, item)
            cat = translate_category_name(recipe.get("category", "Autre")) if recipe else "?"
            self.items_listbox.insert(
                tk.END, t("menuform_item_row_label", cat=cat, name=item['recipe_name'], persons=item['persons'])
            )

    def _sync_menu_default_persons(self):
        recipe = find_recipe_by_name(self.app.recipes, self.recipe_combo.get())
        if recipe is None:
            return
        value = recipe.get("default_persons", 4) or 4
        self.add_persons_entry.delete(0, tk.END)
        self.add_persons_entry.insert(0, str(value))

    def add_item(self):
        name = self.recipe_combo.get()
        if not name:
            return
        try:
            persons = parse_positive_number(self.add_persons_entry.get())
        except ValueError:
            messagebox.showerror(t("common_error"), t("onerecipe_invalid_persons"))
            return
        recipe = find_recipe_by_name(self.app.recipes, name)
        self.items.append({"recipe_id": recipe.get("id") if recipe else None, "recipe_name": name, "persons": persons})
        self._refresh_items_listbox()

    def remove_item(self):
        sel = self.items_listbox.curselection()
        if not sel:
            messagebox.showinfo(t("common_info"), t("menuform_select_recipe_to_remove"))
            return
        self.items.pop(sel[0])
        self._refresh_items_listbox()

    def save_menu(self):
        name = self.name_entry.get().strip()
        if not name:
            messagebox.showerror(t("common_error"), t("menuform_error_name_required"))
            return
        if not self.items:
            messagebox.showerror(t("common_error"), t("menuform_error_no_recipe"))
            return
        menus = load_menus()
        menu_data = {"name": name, "items": self.items}
        if self.editing:
            menus[self.menu_index] = menu_data
        else:
            menus.append(menu_data)
        save_menus(menus)
        self.manager._populate()
        messagebox.showinfo(t("allrecipes_list_saved_title"), t("menuform_saved_message", name=name))

    def _collect_pairs(self):
        pairs = []
        chosen_recipes = []
        sorted_items = sorted(
            self.items,
            key=lambda it: self.CATEGORY_ORDER.get(
                (find_recipe_by_ref(self.app.recipes, it) or {}).get("category", "Autre"), 4
            )
        )
        for item in sorted_items:
            recipe = find_recipe_by_ref(self.app.recipes, item)
            if recipe is None:
                continue
            try:
                persons = parse_positive_number(item.get("persons", 0))
            except ValueError:
                messagebox.showerror(t("common_error"), t("onerecipe_invalid_persons"), parent=self)
                return [], []
            pairs.append((recipe, persons))
            cat = translate_category_name(recipe.get("category", "Autre"))
            chosen_recipes.append((f"{cat} — {recipe['name']}", persons))
        return pairs, chosen_recipes

    def compute(self):
        pairs, chosen_recipes = self._collect_pairs()
        if not pairs and not self.manual_items:
            messagebox.showinfo(
                t("common_info"), t("menuform_add_recipe_or_manual")
            )
            return None
        if self.manual_items:
            pairs = list(pairs) + [({"ingredients": list(self.manual_items)}, 1)]
        grouped_totals = compute_grouped_totals(pairs)

        self.current_items = []
        for rayon, items in grouped_totals:
            for name, qty, unit in items:
                self.current_items.append({"name": name, "quantity": qty, "unit": unit, "rayon": rayon})
        self.last_chosen_recipes = chosen_recipes
        self._render_shopping_list()

        return chosen_recipes, grouped_totals

    def send_to_normal_shopping_list(self):
        """Ouvre Mes courses avec la liste calculée du menu déjà chargée."""
        if not self.current_items:
            result = self.compute()
            if result is None and not self.current_items:
                return
        items = [dict(item) for item in self.current_items]
        win = AllRecipesWindow(self.app)
        win.load_saved_list(items)
        win.lift()
        win.focus_force()
        self.app.show_toast(
            t("menuform_sent_to_normal_shopping", count=len(items))
        )

    def export_txt(self):
        result = self._current_export_data()
        if result is None:
            return
        chosen_recipes, grouped_totals = result
        menu_name = self.name_entry.get().strip() or "menu"
        path = filedialog.asksaveasfilename(
            title=t("weekplan_export_shopping_list_title"), defaultextension=".txt",
            filetypes=[("Fichier texte", "*.txt")], initialfile=f"{sanitize_windows_filename(menu_name, 'menu')}.txt"
        )
        if not path:
            return
        try:
            write_shopping_list_txt(path, t("menuform_shopping_list_title", name=menu_name), chosen_recipes, grouped_totals)
        except Exception as e:
            messagebox.showerror(t("common_error"), t("common_export_failed", error=e))
            return
        messagebox.showinfo(t("common_export_success_title"), t("weekplan_list_saved_message", path=path))

    def export_excel(self):
        if not OPENPYXL_AVAILABLE:
            messagebox.showerror(t("common_module_missing"), t("weekplan_excel_module_missing"))
            return
        result = self._current_export_data()
        if result is None:
            return
        chosen_recipes, grouped_totals = result
        menu_name = self.name_entry.get().strip() or "menu"
        path = filedialog.asksaveasfilename(
            title=t("weekplan_export_shopping_list_title"), defaultextension=".xlsx",
            filetypes=[("Fichier Excel", "*.xlsx")], initialfile=f"{sanitize_windows_filename(menu_name, 'menu')}.xlsx"
        )
        if not path:
            return
        try:
            wb = build_shopping_list_workbook(chosen_recipes, grouped_totals)
            wb.save(path)
        except Exception as e:
            messagebox.showerror(t("common_error"), t("common_export_failed", error=e))
            return
        messagebox.showinfo(t("common_export_success_title"), t("weekplan_list_saved_message", path=path))

    def export_pdf(self):
        if not REPORTLAB_AVAILABLE:
            messagebox.showerror(t("common_module_missing"), t("weekplan_pdf_module_missing"))
            return
        result = self._current_export_data()
        if result is None:
            return
        chosen_recipes, grouped_totals = result
        menu_name = self.name_entry.get().strip() or "menu"
        path = filedialog.asksaveasfilename(
            title=t("weekplan_export_shopping_list_title"), defaultextension=".pdf",
            filetypes=[("Fichier PDF", "*.pdf")], initialfile=f"{sanitize_windows_filename(menu_name, 'menu')}.pdf"
        )
        if not path:
            return
        try:
            build_shopping_list_pdf(path, t("menuform_shopping_list_title", name=menu_name), chosen_recipes, grouped_totals)
        except Exception as e:
            messagebox.showerror(t("common_error"), t("common_export_failed", error=e))
            return
        messagebox.showinfo(t("common_export_success_title"), t("weekplan_list_saved_message", path=path))

    def print_list(self):
        if not REPORTLAB_AVAILABLE:
            messagebox.showerror(t("common_module_missing"), t("weekplan_print_module_missing"))
            return
        result = self._current_export_data()
        if result is None:
            return
        chosen_recipes, grouped_totals = result
        menu_name = self.name_entry.get().strip() or "menu"
        temp_path = get_temp_pdf_path("menu")
        try:
            build_shopping_list_pdf(temp_path, t("menuform_shopping_list_title", name=menu_name), chosen_recipes, grouped_totals)
        except Exception as e:
            messagebox.showerror(t("common_error"), t("common_print_failed", error=e))
            return
        print_document(self, temp_path, t("menuform_print_label", name=menu_name))

    def open_checklist(self):
        result = self._current_export_data()
        if result is None:
            return
        chosen_recipes, grouped_totals = result
        menu_name = self.name_entry.get().strip() or "menu"
        ShoppingChecklistWindow(self.app, grouped_totals, title=t("menuform_shopping_list_title", name=menu_name))


class ImportFromUrlWindow(tk.Toplevel):
    """Importe une recette depuis un lien, avec aperçu avant création."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.recipe_data = None
        self.title(t("importurl_title"))
        # Plus grande pour l'aperçu texte + photo.
        fit_window_to_workarea(self, gs(1380), get_usable_screen_height(self), margin=18)
        safe_minsize(self, gs(720), min(gs(580), get_usable_screen_height(self) - 48))
        self.resizable(True, True)
        self.grab_set()
        self._closed = False
        self._handoff = False
        self.protocol("WM_DELETE_WINDOW", self._close_import_window)

        ttk.Label(self, text=t("importurl_heading"), font=("Segoe UI", sf(13), "bold")).pack(pady=(15, 5))
        ttk.Label(self, text=t("importurl_intro"), justify="center", font=("Segoe UI", sf(9)), wraplength=640).pack(pady=(0, 10))
        self.url_entry = ttk.Entry(self, width=70)
        self.url_entry.pack(pady=5, padx=20, fill="x")
        self.url_entry.bind("<Return>", lambda e: self.fetch())

        action = ttk.Frame(self)
        action.pack(fill="x", padx=20, pady=5)
        self.fetch_button = ttk.Button(action, text=t("importurl_fetch_button"), command=self.fetch)
        self.fetch_button.pack(side="left")
        self.status_label = ttk.Label(action, text="", foreground=COLOR_TEXT_MUTED)
        self.status_label.pack(side="left", padx=12)
        self.progress = ttk.Progressbar(action, mode="indeterminate", length=180)
        # Masquée au repos : elle n'apparaît que pendant la récupération.
        self._progress_visible = False

        preview = ttk.LabelFrame(self, text=t("importurl_preview_heading"), padding=10)
        preview.pack(fill="both", expand=True, padx=20, pady=10)

        self.preview_photo_label = ttk.Label(preview, anchor="n")
        self._preview_photo_ref = None

        preview_text_frame = ttk.Frame(preview)
        preview_text_frame.pack(side="left", fill="both", expand=True)
        self.preview_text = tk.Text(preview_text_frame, wrap="word", height=20,
                                    font=("Segoe UI", sf(9)), state="disabled")
        sb = ttk.Scrollbar(preview_text_frame, orient="vertical", command=self.preview_text.yview)
        self.preview_text.configure(yscrollcommand=sb.set)
        self.preview_text.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=20, pady=(0, 15))
        ttk.Button(bottom, text=t("recipeform_cancel_button"), command=self._close_import_window).pack(side="right", padx=(8, 0))
        self.import_button = ttk.Button(bottom, text=t("importurl_confirm_button"), style="Primary.TButton",
                                        command=self.confirm_import, state="disabled")
        self.import_button.pack(side="right")

    def fetch(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showinfo(t("common_info"), t("importurl_paste_url_first"))
            return
        if not url.lower().startswith(("http://", "https://")):
            url = "https://" + url
        self.fetch_button.config(state="disabled")
        self.import_button.config(state="disabled")
        self.status_label.config(text=t("importurl_fetching"))
        if not self._progress_visible:
            self.progress.pack(side="right")
            self._progress_visible = True
        self.progress.start(10)
        threading.Thread(target=self._fetch_worker, args=(url,), daemon=True).start()

    def _fetch_worker(self, url):
        try:
            data = fetch_recipe_from_url(url)
            try:
                if not self._closed and self.winfo_exists():
                    self.after(0, lambda: self._fetch_done(data, None))
            except tk.TclError:
                return
        except Exception as exc:
            try:
                if not self._closed and self.winfo_exists():
                    self.after(0, lambda exc=exc: self._fetch_done(None, exc))
            except tk.TclError:
                return

    def _fetch_done(self, recipe_data, error):
        if self._closed or not self.winfo_exists():
            return
        self.progress.stop()
        if self._progress_visible:
            self.progress.pack_forget()
            self._progress_visible = False
        self.status_label.config(text="")
        self.fetch_button.config(state="normal")
        if error is not None:
            messagebox.showerror(t("importurl_failed_title"), str(error))
            return
        self.recipe_data = recipe_data
        ingredients = recipe_data.get("ingredients", [])
        preview_persons = recipe_data.get("default_persons") or 1
        lines = [
            t("importurl_preview_name", value=recipe_data.get("name") or "—"),
            t("importurl_preview_persons", value=preview_persons),
            t("importurl_preview_times", prep=recipe_data.get("prep_time") or "—", cook=recipe_data.get("cook_time") or "—"),
            t("importurl_preview_ingredients_for_persons", count=len(ingredients), persons=preview_persons),
            "",
        ]
        warnings = recipe_data.get("import_warnings") or []
        if warnings:
            lines += [t("importurl_warning_heading")]
            for warning in warnings:
                lines.append("• " + t(warning["key"], **{k: v for k, v in warning.items() if k != "key"}))
            lines.append("")
        for ing in ingredients[:12]:
            try:
                displayed_quantity = ingredient_quantity_for_persons(ing, preview_persons)
            except (TypeError, ValueError):
                displayed_quantity = ing.get("quantity", "")
            if displayed_quantity is None:
                displayed_quantity = t("quantity_unspecified")
                unit_display = f" {translate_unit_name(ing.get('unit', ''))}" if ing.get('unit') not in ('', 'au goût', None) else ""
            else:
                unit_display = f" {translate_unit_name(ing.get('unit', ''))}" if ing.get("unit") else ""
            lines.append(f"• {displayed_quantity}{unit_display} {translate_ingredient_name(ing.get('name', ''))}".strip())
        if len(ingredients) > 12:
            lines.append(t("importurl_preview_more", count=len(ingredients)-12))
        if recipe_data.get('personal_notes'):
            lines += ['', recipe_data['personal_notes']]
        desc = (recipe_data.get("description") or "").strip()
        if desc:
            lines += ["", t("importurl_preview_description"), desc[:700] + ("…" if len(desc) > 700 else "")]
        self.preview_text.config(state="normal")
        self.preview_text.delete("1.0", tk.END)
        self.preview_text.insert("1.0", "\n".join(lines))
        self.preview_text.config(state="disabled")

        # Afficher la photo récupérée dans l'aperçu lorsqu'elle existe.
        self.preview_photo_label.pack_forget()
        self._preview_photo_ref = None
        image_sources = recipe_data.get("image_sources", []) or []
        images = recipe_data.get("images", []) or []
        if (image_sources or images) and PIL_AVAILABLE:
            try:
                thumb = (load_thumbnail_from_path(image_sources[0], size=(430, 340))
                         if image_sources else load_thumbnail(images[0], size=(430, 340)))
                if thumb is not None:
                    self._preview_photo_ref = thumb
                    self.preview_photo_label.configure(image=thumb)
                    self.preview_photo_label.pack(side="left", padx=(0, 14),
                                                  pady=(2, 0), anchor="n")
            except Exception as exc:
                log_internal_error("suppressed_exception", exc)

        self.import_button.config(state="normal")

    def _close_import_window(self):
        self._closed = True
        if not self._handoff and self.recipe_data:
            for path in self.recipe_data.get("temporary_image_sources", []) or []:
                try:
                    if path and os.path.isfile(path) and os.path.commonpath([os.path.abspath(path), os.path.abspath(IMPORT_TEMP_DIR)]) == os.path.abspath(IMPORT_TEMP_DIR):
                        os.remove(path)
                except Exception as exc:
                    log_internal_error("cleanup_url_import_temp", exc)
        self.destroy()

    def confirm_import(self):
        if not self.recipe_data:
            return
        recipe_data = self.recipe_data
        known_lower = {n.lower() for n in self.app.ingredient_names}
        ingredients_list = load_ingredients()
        changed = False
        for ing in recipe_data.get("ingredients", []):
            if ing.get("name", "").lower() in known_lower:
                continue
            plural_match = find_plural_duplicate(ing.get("name", ""), ingredients_list)
            if plural_match:
                ing["name"] = plural_match
                continue
            if ing.get("name"):
                ingredients_list.append(ing["name"])
                known_lower.add(ing["name"].lower())
                changed = True
        if changed:
            self.app.ingredient_names = save_ingredients(ingredients_list)
        self._handoff = True
        self._closed = True
        self.destroy()
        RecipeFormWindow(self.app, recipe_index=None, prefill=recipe_data)


class ImportFromPhotoWindow(tk.Toplevel):
    """Import OCR depuis une ou plusieurs photos, dans l'ordre choisi."""

    IMAGE_FILETYPES = [
        ("Images", "*.jpg *.jpeg *.png *.webp *.bmp *.tiff *.tif"),
        ("Tous les fichiers", "*.*"),
    ]

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title(t("importphoto_title"))
        fit_window_to_workarea(
            self, gs(980), get_usable_screen_height(self), margin=18
        )
        safe_minsize(self, gs(760), gs(560))
        self.resizable(True, True)
        self.grab_set()
        self._closed = False
        self.protocol("WM_DELETE_WINDOW", self._close_import_window)

        self.photo_paths = []
        self.photo_rotations = {}
        self._preview_ref = None
        self._ocr_status = {
            "pytesseract": PYTESSERACT_AVAILABLE,
            "executable": None,
            "ready": False,
            "reason": "checking",
            "required_lang": TESSERACT_LANG_CODES.get(CURRENT_LANGUAGE, "fra"),
        }
        self._ocr_status_checking = False
        self._ocr_status_results = queue.Queue(maxsize=1)
        self._ocr_work_results = queue.Queue()

        ttk.Label(
            self, text=t("importphoto_heading"),
            font=("Segoe UI", sf(13), "bold")
        ).pack(pady=(14, 3))
        ttk.Label(
            self, text=t("importphoto_intro_multi_v31"),
            font=("Segoe UI", sf(8)), foreground=COLOR_TEXT_MUTED,
            justify="center", wraplength=900
        ).pack(pady=(0, 7))

        self.ocr_status_label = ttk.Label(
            self, text=t("importphoto_ocr_checking"),
            foreground=COLOR_TEXT_MUTED, justify="center", wraplength=900
        )
        self.ocr_status_label.pack(pady=(0, 8))

        # -------- Photos sélectionnées --------
        photos_box = ttk.LabelFrame(
            self, text=t("importphoto_selected_photos_heading"), padding=8
        )
        photos_box.pack(fill="x", padx=15, pady=(2, 8))
        photos_box.columnconfigure(0, weight=1)

        list_area = ttk.Frame(photos_box)
        list_area.grid(row=0, column=0, rowspan=2, sticky="nsew")
        list_area.columnconfigure(0, weight=1)

        self.photo_listbox = tk.Listbox(
            list_area, height=5, exportselection=False,
            font=("Segoe UI", sf(9))
        )
        photo_scroll = ttk.Scrollbar(
            list_area, orient="vertical", command=self.photo_listbox.yview
        )
        self.photo_listbox.configure(yscrollcommand=photo_scroll.set)
        self.photo_listbox.grid(row=0, column=0, sticky="nsew")
        photo_scroll.grid(row=0, column=1, sticky="ns")
        self.photo_listbox.bind("<<ListboxSelect>>", self._on_photo_selected)

        buttons = ttk.Frame(photos_box)
        buttons.grid(row=0, column=1, sticky="n", padx=(10, 0))
        ttk.Button(
            buttons, text=t("importphoto_add_photos_button"),
            command=self.choose_photo
        ).pack(fill="x", pady=2)
        ttk.Button(
            buttons, text=t("importphoto_move_up_button"),
            command=lambda: self._move_photo(-1)
        ).pack(fill="x", pady=2)
        ttk.Button(
            buttons, text=t("importphoto_move_down_button"),
            command=lambda: self._move_photo(1)
        ).pack(fill="x", pady=2)
        ttk.Button(
            buttons, text=t("importphoto_rotate_left_button"),
            command=lambda: self._rotate_selected_photo(-90)
        ).pack(fill="x", pady=2)
        ttk.Button(
            buttons, text=t("importphoto_rotate_right_button"),
            command=lambda: self._rotate_selected_photo(90)
        ).pack(fill="x", pady=2)
        ttk.Button(
            buttons, text=t("importphoto_remove_photo_button"),
            command=self._remove_selected_photo
        ).pack(fill="x", pady=2)
        ttk.Button(
            buttons, text=t("importphoto_clear_photos_button"),
            command=self._clear_photos
        ).pack(fill="x", pady=2)

        self.preview_label = ttk.Label(
            photos_box, text=t("importphoto_no_photo_chosen"),
            foreground=COLOR_TEXT_MUTED, anchor="center"
        )
        self.preview_label.grid(
            row=1, column=1, sticky="ew", padx=(10, 0), pady=(6, 0)
        )

        # -------- OCR --------
        control = ttk.Frame(self)
        control.pack(fill="x", padx=15, pady=5)
        self.extract_button = ttk.Button(
            control, text=t("importphoto_extract_all_button"),
            command=self.extract_text, state="disabled"
        )
        self.extract_button.pack(side="left")
        self.refresh_ocr_button = ttk.Button(
            control, text=t("importphoto_refresh_ocr_button"),
            command=self._refresh_ocr_status
        )
        self.refresh_ocr_button.pack(side="left", padx=(8, 0))
        self.status_label = ttk.Label(
            control, text="", foreground=COLOR_TEXT_MUTED
        )
        self.status_label.pack(side="left", padx=10)
        self.progress = ttk.Progressbar(
            control, mode="determinate", maximum=100, length=220
        )
        self._progress_visible = False

        ttk.Label(
            self, text=t("importphoto_extracted_text_label"),
            font=("Segoe UI", sf(9), "bold")
        ).pack(pady=(8, 3))

        text_frame = ttk.Frame(self)
        text_frame.pack(fill="both", expand=True, padx=15, pady=(0, 10))
        self.text_box = tk.Text(
            text_frame, height=18, wrap="word",
            font=("Segoe UI", sf(10))
        )
        sb = ttk.Scrollbar(
            text_frame, orient="vertical", command=self.text_box.yview
        )
        self.text_box.configure(yscrollcommand=sb.set)
        self.text_box.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        ttk.Button(
            self, text=t("importphoto_create_button"),
            style="Primary.TButton", command=self.create_recipe
        ).pack(pady=(0, 14))

        # La fenêtre et tous ses boutons existent avant de lancer la détection,
        # qui peut prendre plusieurs secondes sur certains postes Windows.
        self.after(50, self._refresh_ocr_status)

    def _refresh_ocr_status(self):
        if self._closed or self._ocr_status_checking:
            return
        self._ocr_status_checking = True
        self.ocr_status_label.config(
            text=t("importphoto_ocr_checking"), foreground=COLOR_TEXT_MUTED
        )
        self.extract_button.config(state="disabled")
        self.refresh_ocr_button.config(state="disabled")

        def worker():
            try:
                status = current_tesseract_status()
            except Exception as exc:
                status = {
                    "pytesseract": PYTESSERACT_AVAILABLE,
                    "executable": None,
                    "ready": False,
                    "reason": str(exc),
                    "required_lang": TESSERACT_LANG_CODES.get(CURRENT_LANGUAGE, "fra"),
                }
            self._ocr_status_results.put(status)

        threading.Thread(target=worker, daemon=True).start()
        self.after(100, self._poll_ocr_status)

    def _poll_ocr_status(self):
        if self._closed or not self.winfo_exists():
            return
        try:
            status = self._ocr_status_results.get_nowait()
        except queue.Empty:
            self.after(100, self._poll_ocr_status)
            return
        self._ocr_status_checking = False
        self._ocr_status = status
        self.refresh_ocr_button.config(state="normal")
        self._display_ocr_status(status)

    def _display_ocr_status(self, status):
        if not status["pytesseract"]:
            msg = t("importphoto_ocr_pytesseract_missing")
            color = COLOR_ERROR
        elif not status["executable"]:
            msg = t("importphoto_ocr_exe_missing")
            color = COLOR_ERROR
        elif not status["ready"]:
            msg = t(
                "importphoto_ocr_lang_missing",
                lang=status.get("required_lang") or "?"
            )
            color = COLOR_ERROR
        else:
            msg = t(
                "importphoto_ocr_ready",
                version=status.get("version") or "?",
                lang=status.get("required_lang") or "?"
            )
            color = COLOR_GREEN
        self.ocr_status_label.config(text=msg, foreground=color)
        self._update_extract_button()

    def _update_extract_button(self):
        state = (
            "normal"
            if self.photo_paths and self._ocr_status.get("ready")
            else "disabled"
        )
        self.extract_button.config(state=state)

    def choose_photo(self):
        paths = filedialog.askopenfilenames(
            title=t("importphoto_choose_photo_title"),
            filetypes=self.IMAGE_FILETYPES
        )
        if not paths:
            return
        existing = {os.path.normcase(os.path.abspath(p)) for p in self.photo_paths}
        for path in paths:
            full = os.path.abspath(path)
            key = os.path.normcase(full)
            if key not in existing:
                self.photo_paths.append(full)
                existing.add(key)
        self._refresh_photo_list(select_last=True)

    def _refresh_photo_list(self, select_last=False):
        self.photo_listbox.delete(0, tk.END)
        for index, path in enumerate(self.photo_paths, 1):
            rotation = self.photo_rotations.get(path, 0) % 360
            suffix = f"  ({rotation}°)" if rotation else ""
            self.photo_listbox.insert(
                tk.END, f"{index}. {os.path.basename(path)}{suffix}"
            )
        if self.photo_paths:
            pos = len(self.photo_paths) - 1 if select_last else 0
            self.photo_listbox.selection_set(pos)
            self.photo_listbox.activate(pos)
            self.photo_listbox.see(pos)
            self._show_preview(pos)
        else:
            self._preview_ref = None
            self.preview_label.config(
                image="", text=t("importphoto_no_photo_chosen")
            )
        self._update_extract_button()

    def _on_photo_selected(self, _event=None):
        sel = self.photo_listbox.curselection()
        if sel:
            self._show_preview(sel[0])

    def _show_preview(self, index):
        if not (0 <= index < len(self.photo_paths)):
            return
        path = self.photo_paths[index]
        self.preview_label.config(
            text=t(
                "importphoto_photo_position",
                current=index + 1, total=len(self.photo_paths)
            )
        )
        if PIL_AVAILABLE:
            try:
                with Image.open(path) as source:
                    img = ImageOps.exif_transpose(source).convert("RGB")
                rotation = self.photo_rotations.get(path, 0) % 360
                if rotation:
                    img = img.rotate(-rotation, expand=True)
                img.thumbnail((260, 150))
                self._preview_ref = ImageTk.PhotoImage(img)
                self.preview_label.config(
                    image=self._preview_ref, compound="top"
                )
            except Exception as exc:
                log_internal_error("importphoto_preview", exc)

    def _move_photo(self, delta):
        sel = self.photo_listbox.curselection()
        if not sel:
            return
        old = sel[0]
        new = old + delta
        if not (0 <= new < len(self.photo_paths)):
            return
        self.photo_paths[old], self.photo_paths[new] = (
            self.photo_paths[new], self.photo_paths[old]
        )
        self._refresh_photo_list()
        self.photo_listbox.selection_clear(0, tk.END)
        self.photo_listbox.selection_set(new)
        self.photo_listbox.activate(new)
        self.photo_listbox.see(new)
        self._show_preview(new)

    def _rotate_selected_photo(self, delta):
        sel = self.photo_listbox.curselection()
        if not sel:
            return
        index = sel[0]
        path = self.photo_paths[index]
        self.photo_rotations[path] = (
            self.photo_rotations.get(path, 0) + delta
        ) % 360
        self._refresh_photo_list()
        self.photo_listbox.selection_clear(0, tk.END)
        self.photo_listbox.selection_set(index)
        self.photo_listbox.activate(index)
        self.photo_listbox.see(index)
        self._show_preview(index)

    def _remove_selected_photo(self):
        sel = self.photo_listbox.curselection()
        if not sel:
            return
        path = self.photo_paths.pop(sel[0])
        self.photo_rotations.pop(path, None)
        self._refresh_photo_list()

    def _clear_photos(self):
        self.photo_paths = []
        self.photo_rotations = {}
        self._refresh_photo_list()
        self.text_box.delete("1.0", tk.END)

    def extract_text(self):
        if not self.photo_paths:
            messagebox.showinfo(
                t("common_info"), t("importphoto_choose_first")
            )
            return

        if self._ocr_status_checking:
            messagebox.showinfo(
                t("common_info"), t("importphoto_ocr_checking_wait"), parent=self
            )
            return
        if not self._ocr_status.get("ready"):
            status = self._ocr_status
            if status.get("reason") == "language_missing":
                messagebox.showerror(
                    t("common_module_missing"),
                    t(
                        "importphoto_ocr_lang_missing_detail",
                        lang=status.get("required_lang") or "?"
                    ),
                    parent=self
                )
            else:
                messagebox.showerror(
                    t("common_module_missing"),
                    t("importphoto_ocr_tesseract_missing_detail"),
                    parent=self
                )
            return

        self.extract_button.config(state="disabled")
        self.progress["value"] = 0
        if not self._progress_visible:
            self.progress.pack(side="right")
            self._progress_visible = True
        self.status_label.config(text=t("importphoto_ocr_running"))
        paths_snapshot = list(self.photo_paths)
        rotations_snapshot = dict(self.photo_rotations)
        lang = self._ocr_status.get("required_lang") or "fra"
        self._ocr_work_results = queue.Queue()
        threading.Thread(
            target=self._ocr_worker,
            args=(paths_snapshot, lang, rotations_snapshot),
            daemon=True
        ).start()
        self.after(100, self._poll_ocr_worker)

    def _ocr_worker(self, paths, lang, rotations=None):
        chunks = []
        error = None
        rotations = rotations or {}
        try:
            total = len(paths)
            for idx, path in enumerate(paths, 1):
                if self._closed:
                    return
                if PIL_AVAILABLE:
                    with Image.open(path) as source:
                        image = prepare_image_for_ocr(
                            source, rotations.get(path, 0), max_dimension=2400
                        )
                    # La rotation manuelle prime. Sans correction manuelle,
                    # OSD rattrape les photos dont l'orientation EXIF est
                    # absente ou erronée.
                    if not rotations.get(path, 0):
                        auto_rotation = detect_ocr_rotation(prepare_image_for_ocr(image))
                        if auto_rotation:
                            image = image.rotate(-auto_rotation, expand=True)
                    def recognize(candidate):
                        return pytesseract.image_to_string(candidate, lang=lang, timeout=25)
                    raw_text = recognize(prepare_image_for_ocr(image)).strip()
                    text_value = raw_text
                    # Le mode de segmentation 4 respecte mieux les lignes
                    # d'une table nom/quantité. Sur la photo Barramundi réelle,
                    # le mode automatique plaçait « 1 barquette » avant
                    # « Tomates cerises » ; ce second passage les réunit.
                    if re.search(
                        r"ingr[eé]dients?\s+(?:pour|for|para|f[uü]r)",
                        raw_text,
                        re.IGNORECASE,
                    ):
                        try:
                            table_text = ocr_ingredient_table(image, lang, lambda: self._closed).strip()
                        except OperationCancelled:
                            return
                        except (RuntimeError, ValueError) as exc:
                            log_internal_error("ocr.table_refinement", exc)
                            table_text = ""
                        if table_text:
                            text_value = table_text
                    elif looks_like_preparation_grid(raw_text):
                        try:
                            grid_text = ocr_grid_cells(
                                image, lambda cell: ocr_preparation_cell(cell, lang, lambda: self._closed)
                            )
                        except OperationCancelled:
                            return
                        except (RuntimeError, ValueError) as exc:
                            log_internal_error("ocr.grid_refinement", exc)
                            grid_text = ""
                        # Le découpage n'est retenu que si plusieurs cases ont
                        # livré un texte substantiel. Le texte brut reste le
                        # repli sûr pour une page classique à une colonne.
                        substantial = [
                            part for part in grid_text.split("\n\n")
                            if len(part.strip()) >= 45
                        ]
                        if len(substantial) >= 4 and len(grid_text) >= len(raw_text) * 0.55:
                            text_value = grid_text.strip()
                else:
                    text_value = pytesseract.image_to_string(
                        path, lang=lang, timeout=25
                    ).strip()

                if text_value:
                    chunks.append(
                        t("importphoto_page_heading", number=idx)
                        + "\n" + text_value
                    )
                pct = int(idx * 100 / total)
                self._ocr_work_results.put(("progress", (pct, idx, total)))
        except Exception as exc:
            error = exc
        self._ocr_work_results.put(("done", (chunks, error)))

    def _poll_ocr_worker(self):
        if self._closed or not self.winfo_exists():
            return
        finished = False
        while True:
            try:
                kind, payload = self._ocr_work_results.get_nowait()
            except queue.Empty:
                break
            if kind == "progress":
                self._ocr_progress(*payload)
            elif kind == "done":
                self._ocr_done(*payload)
                finished = True
        if not finished:
            self.after(100, self._poll_ocr_worker)

    def _ocr_progress(self, pct, idx, total):
        if self._closed or not self.winfo_exists():
            return
        self.progress["value"] = pct
        self.status_label.config(
            text=t(
                "importphoto_ocr_progress",
                current=idx, total=total
            )
        )

    def _ocr_done(self, chunks, error):
        if self._closed or not self.winfo_exists():
            return
        if self._progress_visible:
            self.progress.pack_forget()
            self._progress_visible = False
        self.status_label.config(text="")
        self._update_extract_button()

        if error is not None:
            messagebox.showerror(
                t("importphoto_extraction_failed_title"),
                t("importphoto_extraction_failed_message", error=error),
                parent=self
            )
            return

        self.text_box.delete("1.0", tk.END)
        if chunks:
            self.text_box.insert("1.0", "\n\n".join(chunks))
            warnings = parse_photo_ocr_recipe("\n\n".join(chunks)).get("ocr_warnings", [])
            if warnings:
                self.status_label.config(text=t("importphoto_uncertain_quantities", names=", ".join(warnings)))
        else:
            messagebox.showinfo(
                t("common_info"), t("importphoto_no_text_extracted"),
                parent=self
            )

    def _close_import_window(self):
        self._closed = True
        self.destroy()

    def create_recipe(self):
        raw_text = self.text_box.get("1.0", "end-1c").strip()
        if not raw_text and not ask_yes_no(
            t("importphoto_no_text_title"),
            t("importphoto_no_text_confirm"),
            parent=self
        ):
            return

        # Toutes les photos sélectionnées sont transmises au formulaire
        # final, dans le même ordre que celui utilisé pour l'OCR.
        parsed_prefill = parse_photo_ocr_recipe(raw_text)
        if not parsed_prefill.get("description"):
            if not parsed_prefill.get("ingredients"):
                parsed_prefill["description"] = raw_text[:12000]
        prefill = {
            **parsed_prefill,
            "images": [],
            "image_sources": list(self.photo_paths),
            "temporary_image_sources": [],
        }
        self._closed = True
        self.destroy()
        RecipeFormWindow(self.app, recipe_index=None, prefill=prefill)


class CookbookExportWindow(tk.Toplevel):
    """Exporte plusieurs recettes réunies en un seul PDF façon livre de
    cuisine (page de sommaire puis une recette par page)."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title(t("cookbookexport_title"))
        fit_window_to_workarea(self, gs(840), gs(900), margin=18)
        self.grab_set()

        ttk.Label(self, text=t("cookbookexport_heading"),
                  font=("Segoe UI", sf(13), "bold")).pack(pady=(15, 5))
        ttk.Label(
            self,
            text=t("cookbookexport_intro"),
            justify="center", font=("Segoe UI", sf(9))
        ).pack(pady=(0, 10))

        filter_frame = ttk.Frame(self)
        filter_frame.pack(pady=(0, 5), fill="x", padx=15)
        ttk.Label(filter_frame, text=t("cookbookexport_filter_label")).pack(side="left")
        self.category_filter = ttk.Combobox(
            filter_frame, values=[t("common_all_categories")] + [translate_category_name(c) for c in RecipeFormWindow.CATEGORY_OPTIONS],
            state="readonly", width=15
        )
        self.category_filter.set(t("common_all_categories"))
        self.category_filter.pack(side="left", padx=5)
        self.category_filter.bind("<<ComboboxSelected>>", lambda e: self._populate())
        ttk.Button(filter_frame, text=t("cookbookexport_check_all_button"), command=self.check_all).pack(side="left", padx=5)
        ttk.Button(filter_frame, text=t("cookbookexport_uncheck_all_button"), command=self.uncheck_all).pack(side="left")

        list_frame = ttk.Frame(self)
        list_frame.pack(padx=15, pady=5, fill="both", expand=True)
        canvas = tk.Canvas(list_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        self.rows_frame = ttk.Frame(canvas)
        self.rows_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.rows_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.checks = []  # (var, recipe)
        self._populate()

        ttk.Button(self, text=t("cookbookexport_generate_button"),
                   command=self.export_pdf).pack(pady=15)

    def _populate(self):
        for child in self.rows_frame.winfo_children():
            child.destroy()
        self.checks = []
        category = resolve_category_input(self.category_filter.get(), RecipeFormWindow.CATEGORY_OPTIONS)
        for recipe in self.app.recipes:
            if category != t("common_all_categories") and recipe.get("category", "Autre") != category:
                continue
            var = tk.BooleanVar(value=True)
            ttk.Checkbutton(self.rows_frame, text=format_recipe_list_label(recipe),
                             variable=var).pack(anchor="w", pady=2)
            self.checks.append((var, recipe))

    def check_all(self):
        for var, recipe in self.checks:
            var.set(True)

    def uncheck_all(self):
        for var, recipe in self.checks:
            var.set(False)

    def export_pdf(self):
        if not REPORTLAB_AVAILABLE:
            messagebox.showerror(
                t("common_module_missing"),
                t("onerecipe_pdf_module_missing")
            )
            return
        selected = [(recipe, recipe.get("default_persons", 4) or 4)
                    for var, recipe in self.checks if var.get()]
        if not selected:
            messagebox.showinfo(t("common_info"), t("cookbookexport_error_select_recipe"))
            return

        path = filedialog.asksaveasfilename(
            title=t("cookbookexport_save_dialog_title"),
            defaultextension=".pdf",
            filetypes=[("Fichier PDF", "*.pdf")],
            initialfile="mon_livre_de_recettes.pdf"
        )
        if not path:
            return
        try:
            build_cookbook_pdf(path, selected)
        except Exception as e:
            messagebox.showerror(t("common_error"), t("common_export_failed", error=e))
            return
        messagebox.showinfo(t("common_export_success_title"), t("cookbookexport_saved_message", path=path))


class CompareRecipesWindow(tk.Toplevel):
    """Compare jusqu'à trois recettes côte à côte."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title(t("compare_title"))
        fit_window_to_workarea(self, gs(1456), get_usable_screen_height(self), margin=18)
        safe_minsize(self, gs(900), gs(600))
        self.grab_set()
        recipe_names = [r["name"] for r in self.app.recipes]
        picker = ttk.Frame(self)
        picker.pack(pady=12, padx=15, fill="x")
        self.combos=[]
        labels=[t("compare_recipe_a_label"), t("compare_recipe_b_label"), t("compare_recipe_c_label")]
        for i,label in enumerate(labels):
            ttk.Label(picker,text=label,font=("Segoe UI",sf(9),"bold")).grid(row=i,column=0,sticky="w",pady=3)
            cb=ttk.Combobox(picker,values=[""]+recipe_names,state="readonly",width=38)
            cb.grid(row=i,column=1,padx=6,pady=3,sticky="w")
            if i < len(recipe_names): cb.current(i+1)
            self.combos.append(cb)
        ttk.Button(picker,text=t("compare_three_button"),style="Hero.TButton",command=self.compare).grid(row=0,column=2,rowspan=3,padx=18)
        container=ttk.Frame(self); container.pack(fill="both",expand=True,padx=15,pady=(0,15))
        canvas=tk.Canvas(container,highlightthickness=0); sb=ttk.Scrollbar(container,orient="vertical",command=canvas.yview)
        self.result_frame=ttk.Frame(canvas); self.result_frame.bind("<Configure>",lambda e:canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0,0),window=self.result_frame,anchor="nw"); canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left",fill="both",expand=True); sb.pack(side="right",fill="y")

    def compare(self):
        names=[cb.get().strip() for cb in self.combos if cb.get().strip()]
        names=list(dict.fromkeys(names))
        if len(names)<2:
            messagebox.showinfo(t("common_info"),t("compare_choose_each_list")); return
        recipes=[find_recipe_by_name(self.app.recipes,n) for n in names]
        recipes=[r for r in recipes if r is not None]
        for child in self.result_frame.winfo_children(): child.destroy()
        table=ttk.Frame(self.result_frame); table.pack(fill="x",pady=(0,15))
        table.columnconfigure(0,weight=0)
        for i in range(len(recipes)): table.columnconfigure(i+1,weight=1)
        ttk.Label(table,text="",width=18).grid(row=0,column=0)
        for i,r in enumerate(recipes):
            ttk.Label(table,text=r['name'],font=("Segoe UI",sf(10),"bold"),foreground=COLOR_ACCENT_DARK,wraplength=250).grid(row=0,column=i+1,padx=8,pady=(0,6),sticky="w")
        ttk.Separator(table,orient="horizontal").grid(row=1,column=0,columnspan=len(recipes)+1,sticky="ew",pady=(0,6))
        row=[2]
        def line(label,vals,best=None,lower=False):
            rr=row[0]; ttk.Label(table,text=label,font=("Segoe UI",sf(9),"bold")).grid(row=rr,column=0,sticky="w",pady=3,padx=(0,8))
            comparable=[v for v in vals if isinstance(v,(int,float))]
            bestval=(min(comparable) if lower else max(comparable)) if comparable and best else None
            for i,v in enumerate(vals):
                display=v
                if best and isinstance(v,(int,float)):
                    suffix=("  "+t("compare_best_marker")) if v==bestval and len(set(comparable))>1 else ""
                    display=best(v)+suffix
                ttk.Label(table,text=str(display),wraplength=250,justify="left").grid(row=rr,column=i+1,sticky="w",padx=8,pady=3)
            row[0]+=1
        line(t("compare_field_category"),[translate_category_name(r.get('category','Autre')) for r in recipes])
        line(t("compare_field_favorite"),[t("compare_yes") if r.get('favorite') else t("compare_no") for r in recipes])
        line(t("compare_field_rating"),[float(r.get('rating',0) or 0) for r in recipes],best=lambda v: rating_stars(v) if v else '—')
        line(t("compare_field_difficulty"),[translate_difficulty_name(r.get('difficulty')) or '—' for r in recipes])
        def total(r):
            try:return float(r.get('prep_time') or 0)+float(r.get('cook_time') or 0)
            except Exception:return 0
        line(t("compare_field_total_time"),[total(r) for r in recipes],best=lambda v:f"{v:.0f} min" if v else '—',lower=True)
        line(t("compare_field_cooked"),[int(r.get('times_cooked',0) or 0) for r in recipes],best=lambda v:t("compare_times_suffix",count=v))
        costs=[]; kcals=[]
        for r in recipes:
            persons=r.get('default_persons',1) or 1
            c,known,_=compute_recipe_cost(r,persons); costs.append((c/persons) if known else None)
            n,knownn,_=compute_recipe_nutrition(r,persons); kcals.append((n['kcal']/persons) if knownn else None)
        def metric_line(label,vals,fmt,lower=True):
            nums=[v for v in vals if isinstance(v,(int,float))]; bv=min(nums) if nums and lower else (max(nums) if nums else None)
            disp=[]
            for v in vals:
                if v is None: disp.append('—')
                else: disp.append(fmt(v)+(("  "+t("compare_best_marker")) if bv is not None and v==bv and len(set(nums))>1 else ""))
            line(label,disp)
        metric_line(t("compare_field_cost"),costs,lambda v:f"{v:.2f} € / p.")
        metric_line(t("compare_field_nutrition"),kcals,lambda v:f"{v:.0f} kcal / p.")
        line(t("compare_field_ingredient_count"),[len(r.get('ingredients',[])) for r in recipes],best=lambda v:str(v),lower=True)

        ing_frame=ttk.Frame(self.result_frame); ing_frame.pack(fill="x")
        maps=[]
        for r in recipes: maps.append({ing.get('name','').strip().lower():ing.get('name','') for ing in r.get('ingredients',[]) if ing.get('name')})
        common=set(maps[0])
        for m in maps[1:]: common &= set(m)
        common_col=ttk.Frame(ing_frame); common_col.pack(side="left",fill="both",expand=True,padx=8,anchor="n")
        ttk.Label(common_col,text=t("compare_common_ingredients",count=len(common)),font=("Segoe UI",sf(9),"bold"),foreground=COLOR_ACCENT_DARK).pack(anchor="w")
        for k in sorted(common,key=ingredient_sort_key): ttk.Label(common_col,text="• "+translate_ingredient_name(maps[0][k]).capitalize()).pack(anchor="w")
        for idx,(r,m) in enumerate(zip(recipes,maps)):
            unique=set(m) - set().union(*(set(x) for j,x in enumerate(maps) if j!=idx))
            col=ttk.Frame(ing_frame); col.pack(side="left",fill="both",expand=True,padx=8,anchor="n")
            ttk.Label(col,text=f"{r['name']} ({len(unique)})",font=("Segoe UI",sf(9),"bold"),foreground=COLOR_ACCENT_DARK,wraplength=220).pack(anchor="w")
            for k in sorted(unique,key=ingredient_sort_key): ttk.Label(col,text="• "+translate_ingredient_name(m[k]).capitalize(),wraplength=220).pack(anchor="w")


class StatisticsWindow(tk.Toplevel):
    """Fenêtre affichant des statistiques simples sur les recettes."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title(t("stats_title"))
        fit_window_to_workarea(self, gs(920), gs(840), margin=18)
        safe_minsize(self, gs(720), gs(560))
        self.resizable(True, True)
        self.grab_set()

        recipes = self.app.recipes
        total = len(recipes)
        total_cooked = sum(int(r.get("times_cooked", 0) or 0) for r in recipes)
        year_prefix = str(datetime.now().year)
        cooked_this_year = sum(
            1 for r in recipes for d in (r.get("cooked_dates") or [])
            if isinstance(d, str) and d.startswith(year_prefix)
        )
        rated = [float(r.get("rating", 0) or 0) for r in recipes if r.get("rating")]
        avg_rating_card = (sum(rated) / len(rated)) if rated else 0
        never_cooked_count = sum(1 for r in recipes if not r.get("times_cooked", 0))

        ttk.Label(self, text=t("stats_dashboard_heading"), font=("Segoe UI", sf(15), "bold")).pack(pady=(14, 8))
        cards = ttk.Frame(self)
        cards.pack(fill="x", padx=15, pady=(0, 10))
        card_data = [
            (t("stats_card_recipes"), str(total)),
            (t("stats_card_cooked_year"), str(cooked_this_year)),
            (t("stats_card_total_cooked"), str(total_cooked)),
            (t("stats_card_rating"), f"{avg_rating_card:.1f}/5" if rated else "—"),
            (t("stats_card_never"), str(never_cooked_count)),
        ]
        for i, (label, value) in enumerate(card_data):
            cards.columnconfigure(i, weight=1, uniform="stats")
            card = tk.Frame(cards, background=COLOR_CARD, highlightbackground=COLOR_BORDER, highlightthickness=1)
            card.grid(row=0, column=i, sticky="nsew", padx=4)
            tk.Label(card, text=value, background=COLOR_CARD, foreground=COLOR_ACCENT_DARK,
                     font=("Segoe UI", sf(17), "bold")).pack(pady=(10, 2))
            tk.Label(card, text=label, background=COLOR_CARD, foreground=COLOR_TEXT_MUTED,
                     font=("Segoe UI", sf(8)), wraplength=130, justify="center").pack(padx=6, pady=(0, 10))

        actions = ttk.Frame(self)
        actions.pack(fill="x", padx=15, pady=(0, 4))
        ttk.Button(actions, text=t("stats_export_csv"), style="Secondary.TButton", command=self.export_csv).pack(side="right")

        text_frame = ttk.Frame(self)
        text_frame.pack(fill="both", expand=True, padx=15, pady=(15, 5))
        text = tk.Text(text_frame, wrap="word", height=22, font=("Segoe UI", sf(9)))
        text_scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=text_scrollbar.set)
        text.pack(side="left", fill="both", expand=True)
        text_scrollbar.pack(side="right", fill="y")

        text.insert(tk.END, t("stats_heading"))
        text.insert(tk.END, t("stats_total_recipes", count=total))

        cat_counts = {}
        for r in recipes:
            cat = r.get("category", "Autre")
            cat_counts[cat] = cat_counts.get(cat, 0) + 1
        text.insert(tk.END, t("stats_by_category"))
        for cat in RecipeFormWindow.CATEGORY_OPTIONS:
            if cat in cat_counts:
                text.insert(tk.END, t("stats_category_line", category=translate_category_name(cat), count=cat_counts[cat]))
        text.insert(tk.END, "\n")

        diff_counts = {}
        for r in recipes:
            diff = r.get("difficulty") or t("stats_difficulty_unspecified")
            diff_counts[diff] = diff_counts.get(diff, 0) + 1
        text.insert(tk.END, t("stats_by_difficulty"))
        for diff in ["Facile", "Moyen", "Difficile", t("stats_difficulty_unspecified")]:
            if diff in diff_counts:
                text.insert(tk.END, t("stats_difficulty_line", difficulty=translate_difficulty_name(diff), count=diff_counts[diff]))
        text.insert(tk.END, "\n")

        fav_count = sum(1 for r in recipes if r.get("favorite"))
        text.insert(tk.END, t("stats_favorites_count", count=fav_count))

        rated = [r.get("rating", 0) for r in recipes if r.get("rating")]
        if rated:
            avg_rating = sum(rated) / len(rated)
            text.insert(tk.END, t("stats_avg_rating", avg=f"{avg_rating:.1f}", count=len(rated)))
        else:
            text.insert(tk.END, t("stats_no_rated_recipe"))

        best_rated = [r for r in recipes if r.get("rating", 0) == 5]
        if best_rated:
            text.insert(tk.END, t("stats_five_star_heading"))
            for r in best_rated[:10]:
                text.insert(tk.END, t("stats_recipe_line", name=r['name']))
            text.insert(tk.END, "\n")

        cooked = sorted(
            (r for r in recipes if r.get("times_cooked", 0) > 0),
            key=lambda r: r.get("times_cooked", 0), reverse=True
        )
        text.insert(tk.END, t("stats_most_cooked_heading"))
        if cooked:
            for r in cooked[:10]:
                text.insert(tk.END, t("stats_cooked_line", name=r['name'], count=r['times_cooked']))
        else:
            text.insert(tk.END, t("stats_none_cooked_yet"))
        text.insert(tk.END, "\n")

        tag_counts = {}
        for r in recipes:
            for tag in r.get("tags", []):
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        if tag_counts:
            text.insert(tk.END, t("stats_most_used_tags_heading"))
            for tag, count in sorted(tag_counts.items(), key=lambda pair: -pair[1])[:10]:
                text.insert(tk.END, t("stats_tag_line", tag=tag, count=count))
            text.insert(tk.END, "\n")

        # ---- Recettes oubliées ----
        never_cooked = [r for r in recipes if r.get("times_cooked", 0) == 0]
        text.insert(tk.END, t("stats_never_cooked_heading"))
        if never_cooked:
            shown = never_cooked[:15]
            for r in shown:
                text.insert(tk.END, t("stats_recipe_line", name=r['name']))
            remaining = len(never_cooked) - len(shown)
            if remaining > 0:
                text.insert(tk.END, t("stats_and_others", count=remaining))
        else:
            text.insert(tk.END, t("stats_all_cooked"))
        text.insert(tk.END, "\n")

        stale_cutoff_days = 90
        now = datetime.now()
        stale = []
        for r in recipes:
            cooked_dates = r.get("cooked_dates") or []
            if not cooked_dates:
                continue
            try:
                last_date = max(datetime.fromisoformat(d) for d in cooked_dates)
            except ValueError:
                continue
            if (now - last_date).days >= stale_cutoff_days:
                stale.append((r, (now - last_date).days))
        stale.sort(key=lambda pair: -pair[1])
        text.insert(tk.END, t("stats_stale_heading", days=stale_cutoff_days))
        if stale:
            for r, days in stale[:15]:
                text.insert(tk.END, t("stats_stale_line", name=r['name'], days=days))
        else:
            text.insert(tk.END, t("stats_no_stale_recipe"))
        text.insert(tk.END, "\n")

        # ---- Coût moyen ----
        costs_per_person = []
        for r in recipes:
            persons = r.get("default_persons", 1) or 1
            cost, known, _ = compute_recipe_cost(r, persons)
            if known > 0:
                costs_per_person.append(cost / persons)
        text.insert(tk.END, t("stats_avg_cost_heading"))
        if costs_per_person:
            avg_cost = sum(costs_per_person) / len(costs_per_person)
            without_price = total - len(costs_per_person)
            text.insert(
                tk.END,
                t("stats_avg_cost_line", avg=f"{avg_cost:.2f}", count=len(costs_per_person), without_price=without_price)
            )
        else:
            text.insert(tk.END, t("stats_no_priced_recipe"))
        text.insert(tk.END, "\n")

        # ---- Calories moyennes ----
        kcal_per_person = []
        for r in recipes:
            persons = r.get("default_persons", 1) or 1
            nutrition, known, _ = compute_recipe_nutrition(r, persons)
            if known > 0:
                kcal_per_person.append(nutrition["kcal"] / persons)
        text.insert(tk.END, t("stats_avg_kcal_heading"))
        if kcal_per_person:
            avg_kcal = sum(kcal_per_person) / len(kcal_per_person)
            text.insert(
                tk.END,
                t("stats_avg_kcal_line", avg=f"{avg_kcal:.0f}", count=len(kcal_per_person))
            )
        else:
            text.insert(tk.END, t("stats_no_recognized_recipe"))
        text.insert(tk.END, "\n")

        total_times=[]
        for r in recipes:
            try:
                minutes=float(r.get("prep_time") or 0)+float(r.get("cook_time") or 0)
            except (TypeError,ValueError):
                minutes=0
            if minutes>0: total_times.append(minutes)
        text.insert(tk.END, t("stats_avg_total_time_heading"))
        if total_times:
            text.insert(tk.END, t("stats_avg_total_time_line", avg=f"{sum(total_times)/len(total_times):.0f}", count=len(total_times)))

        text.config(state="disabled")

        # ---- Graphique d'évolution mensuelle des recettes cuisinées ----
        ttk.Label(self, text=t("stats_monthly_chart_title"),
                  font=("Segoe UI", sf(10), "bold")).pack(pady=(8, 2))
        chart_canvas = tk.Canvas(self, height=180, background=COLOR_CARD, highlightthickness=1,
                                  highlightbackground=COLOR_BORDER)
        chart_canvas.pack(fill="x", padx=15, pady=(0, 15))
        self.after(50, lambda: self._draw_monthly_chart(chart_canvas, recipes))

        # ---- Calendrier visuel (façon contributions GitHub) ----
        ttk.Label(self, text=t("stats_heatmap_title"),
                  font=("Segoe UI", sf(10), "bold")).pack(pady=(0, 2))
        heatmap_container = ttk.Frame(self)
        heatmap_container.pack(fill="x", padx=15, pady=(0, 5))
        heatmap_canvas = tk.Canvas(heatmap_container, height=120, background=COLOR_CARD,
                                    highlightthickness=1, highlightbackground=COLOR_BORDER)
        heatmap_hscroll = ttk.Scrollbar(heatmap_container, orient="horizontal", command=heatmap_canvas.xview)
        heatmap_canvas.configure(xscrollcommand=heatmap_hscroll.set)
        heatmap_canvas.pack(fill="x")
        heatmap_hscroll.pack(fill="x")
        ttk.Label(self, text=t("stats_heatmap_legend"), font=("Segoe UI", sf(8)),
                  foreground=COLOR_TEXT_MUTED).pack(pady=(0, 15))
        self.after(50, lambda: self._draw_cooking_heatmap(heatmap_canvas, recipes))

    def export_csv(self):
        path = filedialog.asksaveasfilename(title=t("stats_export_csv_title"), defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w=csv.writer(f, delimiter=";")
                w.writerow(["Recette","Catégorie","Difficulté","Note","Cuissons","Dernière cuisson","Temps total (min)","Coût/pers (€)","Calories/pers","Tags"])
                for r in self.app.recipes:
                    try: total=float(r.get('prep_time') or 0)+float(r.get('cook_time') or 0)
                    except Exception: total=0
                    dates=r.get('cooked_dates') or []; last=max(dates) if dates else ''
                    persons=r.get('default_persons',1) or 1
                    cost,known,_=compute_recipe_cost(r,persons); nutrition,nknown,_=compute_recipe_nutrition(r,persons)
                    w.writerow([r.get('name',''),translate_category_name(r.get('category','Autre')),translate_difficulty_name(r.get('difficulty')) or '',r.get('rating',0),r.get('times_cooked',0),last,f"{total:.0f}" if total else '',f"{cost/persons:.2f}" if known else '',f"{nutrition['kcal']/persons:.0f}" if nknown else '',", ".join(r.get('tags',[]))])
            messagebox.showinfo(t("common_info"), t("stats_export_csv_done", path=path))
        except Exception as e:
            messagebox.showerror(t("common_error"), str(e))

    def _draw_cooking_heatmap(self, canvas, recipes):
        """Dessine un calendrier visuel façon « contributions GitHub » des
        jours où au moins une recette a été cuisinée, sur les 12 derniers
        mois (toutes recettes confondues)."""
        counts = {}
        for r in recipes:
            for date_str in r.get("cooked_dates") or []:
                counts[date_str] = counts.get(date_str, 0) + 1

        today = datetime.now().date()
        start = today - timedelta(days=today.weekday())  # lundi de la semaine actuelle
        start = start - timedelta(weeks=52)

        cell_size, cell_gap = 12, 3
        margin_left, margin_top = 22, 16
        max_count = max(counts.values(), default=0) or 1

        def color_for_count(count):
            if count == 0:
                return COLOR_BORDER
            ratio = count / max_count
            if ratio < 0.34:
                return COLOR_ACCENT_LIGHT
            elif ratio < 0.67:
                return COLOR_ACCENT
            return COLOR_ACCENT_DARK

        canvas.delete("all")
        day_labels = t("stats_day_labels").split(",")
        for row in range(7):
            canvas.create_text(
                margin_left - 12, margin_top + row * (cell_size + cell_gap) + cell_size / 2,
                text=day_labels[row], font=("Segoe UI", sf(7)), fill=COLOR_TEXT_MUTED
            )

        month_labels_fr = t("stats_month_labels_short").split(",")
        current = start
        week_index = 0
        last_month = None
        while current <= today:
            if current.day <= 7 and current.month != last_month:
                canvas.create_text(
                    margin_left + week_index * (cell_size + cell_gap), margin_top - 9,
                    text=month_labels_fr[current.month - 1], font=("Segoe UI", sf(7)),
                    fill=COLOR_TEXT_MUTED, anchor="w"
                )
                last_month = current.month

            row = current.weekday()
            date_str = current.strftime("%Y-%m-%d")
            count = counts.get(date_str, 0)
            x0 = margin_left + week_index * (cell_size + cell_gap)
            y0 = margin_top + row * (cell_size + cell_gap)
            canvas.create_rectangle(
                x0, y0, x0 + cell_size, y0 + cell_size,
                fill=color_for_count(count), outline=COLOR_BG
            )
            if row == 6:
                week_index += 1
            current += timedelta(days=1)

        canvas.configure(scrollregion=canvas.bbox("all"))
        # Fait défiler la vue tout à droite (les semaines les plus récentes),
        # pour que l'utilisateur voie d'emblée les jours les plus récents.
        canvas.xview_moveto(1.0)

    def _draw_monthly_chart(self, canvas, recipes):
        """Dessine un histogramme simple (sans dépendance externe) du nombre
        de recettes cuisinées par mois, sur les 12 derniers mois."""
        now = datetime.now()
        months = []
        for i in range(11, -1, -1):
            year, month = now.year, now.month - i
            while month <= 0:
                month += 12
                year -= 1
            months.append((year, month))

        counts = {ym: 0 for ym in months}
        for r in recipes:
            for date_str in r.get("cooked_dates") or []:
                try:
                    d = datetime.fromisoformat(date_str)
                except (ValueError, TypeError):
                    continue
                ym = (d.year, d.month)
                if ym in counts:
                    counts[ym] += 1

        canvas.update_idletasks()
        width = max(canvas.winfo_width(), 480)
        height = 180
        margin_bottom, margin_top = 28, 14
        chart_height = height - margin_bottom - margin_top
        max_count = max(max(counts.values(), default=0), 1)
        bar_width = (width - 20) / len(months)

        month_labels_fr = t("stats_month_labels_lower").split(",")

        canvas.delete("all")
        for i, ym in enumerate(months):
            count = counts[ym]
            bar_height = (count / max_count) * chart_height
            x0 = 10 + i * bar_width + 3
            x1 = 10 + (i + 1) * bar_width - 3
            y1 = height - margin_bottom
            y0 = y1 - bar_height
            canvas.create_rectangle(x0, y0, x1, y1, fill=COLOR_ACCENT, outline="")
            if count > 0:
                canvas.create_text((x0 + x1) / 2, y0 - 8, text=str(count),
                                    font=("Segoe UI", sf(8)), fill=COLOR_TEXT)
            canvas.create_text((x0 + x1) / 2, y1 + 12, text=month_labels_fr[ym[1] - 1],
                                font=("Segoe UI", sf(7)), fill=COLOR_TEXT_MUTED)


if __name__ == "__main__":
    enable_windows_dpi_awareness()
    app = App()
    app.mainloop()
