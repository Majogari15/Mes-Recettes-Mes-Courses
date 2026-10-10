"""Prépare la copie portable de Tesseract OCR embarquée par Construire_le_exe.bat.

Outil de construction, pas une dépendance de l'application : l'utilisateur
final n'a rien à installer pour lire une photo dans l'une des 11 langues.
- Sans dossier "tesseract-ocr" à côté de ce script, copie l'installation
  Tesseract du PC de construction (emplacements Windows habituels).
- Complète ensuite tessdata avec le paquet de chaque langue de l'interface
  (dépôt officiel tesseract-ocr/tessdata), sans toucher aux fichiers présents.
"""
import os
from pathlib import Path
import shutil
import sys
import tempfile
import urllib.request

PROJECT = Path(__file__).resolve().parent
TARGET = PROJECT / "tesseract-ocr"
# Mêmes codes que TESSERACT_LANG_CODES dans main.py (vérifié par les tests),
# plus "osd" (détection d'orientation de la page).
LANGUAGES = ("fra", "eng", "spa", "deu", "ita", "por", "ind", "nor", "swe", "chi_sim", "ara", "osd")
# Modèles "fast" : quelques Mo par langue au lieu de ~15 Mo, précision
# suffisante pour des recettes (ce sont aussi ceux de l'installeur Windows).
TESSDATA_URL = "https://github.com/tesseract-ocr/tessdata_fast/raw/main/{code}.traineddata"
MIN_SIZE = 100_000  # un vrai paquet de langue pèse plusieurs Mo


def system_installations():
    paths = [Path(r"C:\Program Files\Tesseract-OCR"), Path(r"C:\Program Files (x86)\Tesseract-OCR")]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        paths.append(Path(local) / "Programs" / "Tesseract-OCR")
    return paths


def skip_unneeded(directory, names):
    """Outils d'entraînement, pages d'aide et désinstalleur : ~100 Mo inutiles
    à l'application, qui n'appelle que tesseract.exe (et ses DLL)."""
    return [name for name in names
            if (name.endswith(".exe") and name != "tesseract.exe")
            or name.endswith((".html", ".jar"))]


def copy_installation(target=TARGET, candidates=None):
    """Copie la première installation trouvée ; False si aucune."""
    if (target / "tesseract.exe").is_file():
        return True
    for source in candidates if candidates is not None else system_installations():
        if (source / "tesseract.exe").is_file():
            print(f"  Copie de Tesseract depuis {source}")
            shutil.copytree(source, target, dirs_exist_ok=True, ignore=skip_unneeded)
            return True
    return False


def download(url, destination):
    with urllib.request.urlopen(url, timeout=120) as response:
        destination.write_bytes(response.read())


def ensure_languages(tessdata, codes=LANGUAGES, fetch=download):
    """Télécharge les paquets absents ; renvoie la liste des codes ajoutés.

    Écriture dans un fichier temporaire puis renommage : un téléchargement
    interrompu ne laisse jamais un paquet tronqué que Tesseract refuserait.
    """
    tessdata = Path(tessdata)
    tessdata.mkdir(parents=True, exist_ok=True)
    added = []
    for code in codes:
        final = tessdata / f"{code}.traineddata"
        if final.is_file() and final.stat().st_size >= MIN_SIZE:
            continue
        print(f"  Téléchargement du paquet de langue {code}...")
        handle, temporary = tempfile.mkstemp(dir=tessdata, suffix=".part")
        os.close(handle)
        temporary = Path(temporary)
        try:
            fetch(TESSDATA_URL.format(code=code), temporary)
            if temporary.stat().st_size < MIN_SIZE:
                raise RuntimeError(f"paquet {code} incomplet ({temporary.stat().st_size} octets)")
            os.replace(temporary, final)
        finally:
            temporary.unlink(missing_ok=True)
        added.append(code)
    return added


def main():
    if not copy_installation():
        print("  [INFO] Tesseract introuvable sur ce PC et pas de dossier tesseract-ocr :")
        print("  l'import photo demandera d'installer Tesseract à part.")
        return 0
    try:
        added = ensure_languages(TARGET / "tessdata")
    except Exception as exc:
        print(f"  [ERREUR] Paquets de langue Tesseract : {exc}")
        return 1
    print(f"  Langues OCR prêtes ({len(LANGUAGES) - 1}) ; ajoutées : {', '.join(added) or 'aucune'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
