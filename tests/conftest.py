import os
import sys

import pytest

# tests/test_finalize_v78.py fait "from test_regressions import TempDataMixin"
# (import direct, pas "from tests.test_regressions import ..."). Ça ne
# fonctionne que si le dossier tests/ est lui-même sur sys.path — ce qui est
# déjà le cas quand pytest est lancé depuis l'intérieur de tests/, mais pas
# quand il est lancé depuis la racine du projet ("pytest tests/"), l'usage le
# plus courant (y compris en CI). L'ajouter ici une fois pour toutes évite
# cette erreur de collecte sans toucher aux tests eux-mêmes.
sys.path.insert(0, os.path.dirname(__file__))

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

    yield
