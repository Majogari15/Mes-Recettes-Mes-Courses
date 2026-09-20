import os
import sys

# tests/test_finalize_v78.py fait "from test_regressions import TempDataMixin"
# (import direct, pas "from tests.test_regressions import ..."). Ça ne
# fonctionne que si le dossier tests/ est lui-même sur sys.path — ce qui est
# déjà le cas quand pytest est lancé depuis l'intérieur de tests/, mais pas
# quand il est lancé depuis la racine du projet ("pytest tests/"), l'usage le
# plus courant (y compris en CI). L'ajouter ici une fois pour toutes évite
# cette erreur de collecte sans toucher aux tests eux-mêmes.
sys.path.insert(0, os.path.dirname(__file__))
