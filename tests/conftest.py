import functools
import gc
import os
import sys
import time
import tkinter as tk

import pytest

# tests/test_finalize_v78.py fait "from test_regressions import TempDataMixin"
# (import direct, pas "from tests.test_regressions import ..."). Ça ne
# fonctionne que si le dossier tests/ est lui-même sur sys.path — ce qui est
# déjà le cas quand pytest est lancé depuis l'intérieur de tests/, mais pas
# quand il est lancé depuis la racine du projet ("pytest tests/"), l'usage le
# plus courant (y compris en CI). L'ajouter ici une fois pour toutes évite
# cette erreur de collecte sans toucher aux tests eux-mêmes.
sys.path.insert(0, os.path.dirname(__file__))

# Runners Windows de GitHub : la lecture des fichiers Tcl échoue parfois un
# instant à la création d'une fenêtre (« Can't find a usable init.tcl »,
# « couldn't read file ... No error » — antivirus du runner). Le test était
# alors ignoré au hasard. Réessai court, limité à ces erreurs passagères :
# toute autre TclError reste immédiate.
_TCL_ERREURS_PASSAGERES = ("usable init.tcl", "couldn't read file", "No error")


def _avec_reessai_tcl(init, essais=3, pause=0.5):
    @functools.wraps(init)
    def _init(self, *args, **kwargs):
        for essai in range(essais):
            try:
                return init(self, *args, **kwargs)
            except tk.TclError as exc:
                if essai == essais - 1 or not any(m in str(exc) for m in _TCL_ERREURS_PASSAGERES):
                    raise
                time.sleep(pause)
    _init._avec_reessai_tcl = True
    return _init


if not getattr(tk.Tk.__init__, "_avec_reessai_tcl", False):
    tk.Tk.__init__ = _avec_reessai_tcl(tk.Tk.__init__)

_DIALOG_NAMES = (
    "showinfo", "showwarning", "showerror",
    "askyesno", "askokcancel", "askretrycancel",
    "askquestion", "askyesnocancel",
)


@pytest.fixture(autouse=True)
def _interdire_dialogues_tk_inattendus(monkeypatch):
    # Convention du projet : toute boîte de dialogue bloquante doit être
    # patchée explicitement par le test qui la déclenche. Sans ce garde-fou,
    # un test qui oublie de la patcher ouvre une vraie fenêtre Tk modale :
    # en local elle attend un clic humain, sous Xvfb/CI personne ne peut
    # cliquer et pytest reste bloqué indéfiniment (flake déjà observé :
    # callback .after()/bind_all orphelin après destruction rapide de
    # fenêtres pendant les tests -> exception -> messagebox surprise).
    # Ce garde-fou transforme ce hang silencieux en échec immédiat avec
    # traceback exploitable. Un test qui patch localement
    # (patch.object(main.messagebox, "showinfo"), etc.) reste inchangé :
    # son patch s'applique par-dessus celui-ci le temps de son "with", puis
    # ce garde-fou est restauré.
    try:
        import main
    except Exception:
        yield
        return

    def _lever(nom):
        def _interne(*args, **kwargs):
            raise AssertionError(
                f"Boîte de dialogue Tk inattendue : messagebox.{nom}("
                f"args={args!r}, kwargs={kwargs!r}). Si ce test déclenche "
                f"volontairement ce dialogue, patchez-le explicitement."
            )
        return _interne

    for nom in _DIALOG_NAMES:
        if hasattr(main.messagebox, nom):
            monkeypatch.setattr(main.messagebox, nom, _lever(nom), raising=False)

    # Le thème par défaut suit Windows : sans ce figeage, les tests
    # changeraient de résultat selon le thème de la machine qui les lance.
    if hasattr(main, "detect_system_dark_mode"):
        monkeypatch.setattr(main, "detect_system_dark_mode", lambda: False)

    # Jamais la vraie webcam pendant les tests (voyant allumé sur le poste du
    # développeur) : un test de scan fournit sa propre fausse caméra.
    if hasattr(main, "open_webcam"):
        monkeypatch.setattr(main, "open_webcam", lambda *a, **k: None)

    yield


@pytest.fixture(autouse=True)
def _liberer_tk_dans_le_thread_principal():
    # Une fenêtre Tk détruite reste souvent en mémoire (cycles de
    # références) jusqu'au prochain passage du ramasse-miettes, qui peut se
    # déclencher dans n'importe quel thread — par exemple celui de la
    # sauvegarde automatique lancé par App(). Tcl libéré hors de son thread
    # = Tcl_Panic, le processus pytest meurt (« Windows fatal exception:
    # code 0x80000003 » observé en CI). Collecter ici, dans le thread
    # principal, après chaque test supprime ce cas.
    yield
    gc.collect()
