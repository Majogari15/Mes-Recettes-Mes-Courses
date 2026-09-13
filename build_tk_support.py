"""Prepare and verify Tcl/Tk resources for the Windows one-file build.

Use Tcl's file API: Python 3.14 on Windows may return a zipfs path,
which pathlib/shutil and older PyInstaller hooks cannot read.
This module is a build tool, not an application dependency.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

PROJECT = Path(__file__).resolve().parent
STAGING = PROJECT / "build" / "tk_bundle"
INVENTORY = PROJECT / "build" / "tk_bundle_files.json"


def copy_tcl_tree(interpreter, source, destination):
    """Copy ordinary directories and Tcl zipfs directories identically."""
    destination = Path(destination)
    if not interpreter.call("file", "isdirectory", source):
        raise RuntimeError(f"Dossier Tcl/Tk introuvable : {source}")
    if destination.exists():
        raise RuntimeError(f"Le dossier temporaire existe deja : {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Separate arguments preserve spaces, accents and Tcl-special characters.
    interpreter.call("file", "copy", "--", source, str(destination))


def prepare():
    import tkinter

    INVENTORY.unlink(missing_ok=True)
    if STAGING.exists():
        shutil.rmtree(STAGING)
    root = tkinter.Tk()
    root.withdraw()
    try:
        tcl_dir = str(root.tk.call("info", "library"))
        tk_dir = str(root.tk.getvar("tk_library"))
        copy_tcl_tree(root.tk, tcl_dir, STAGING / "_tcl_data")
        copy_tcl_tree(root.tk, tk_dir, STAGING / "_tk_data")
        major = str(root.tk.call("info", "tclversion")).split(".")[0]
        modules = root.tk.call("file", "join", root.tk.call("file", "dirname", tcl_dir), "tcl" + major)
        if root.tk.call("file", "isdirectory", modules):
            copy_tcl_tree(root.tk, modules, STAGING / ("tcl" + major))
    finally:
        root.destroy()
    for name in ("_tcl_data/init.tcl", "_tk_data/tk.tcl"):
        path = STAGING / name
        if not path.is_file() or not path.stat().st_size:
            raise RuntimeError(f"Ressource Tcl/Tk absente ou vide : {name}")
    inventory = {
        path.relative_to(STAGING).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(STAGING.rglob("*")) if path.is_file()
    }
    INVENTORY.write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    print(f"[OK] {len(inventory)} fichiers Tcl/Tk prepares pour l'executable.")


def verify_archive(executable, expected=None):
    from PyInstaller.archive.readers import CArchiveReader

    archive = CArchiveReader(str(executable))
    names = {name.replace("\\", "/"): name for name in archive.toc}
    for required in ("_tcl_data/init.tcl", "_tk_data/tk.tcl"):
        if required not in names or not archive.extract(names[required]):
            raise RuntimeError(f"Executable incomplet : {required} manque ou est vide.")
    for name, digest in (expected or {}).items():
        if name not in names:
            raise RuntimeError(f"Executable incomplet : {name} manque.")
        if hashlib.sha256(archive.extract(names[name])).hexdigest() != digest:
            raise RuntimeError(f"Ressource integree incorrecte : {name}")


def verify_runtime(executable):
    # A new empty working directory prevents fallback to project data.
    env = os.environ.copy()
    for name in ("TCL_LIBRARY", "TK_LIBRARY", "TCLLIBPATH", "PYTHONHOME", "PYTHONPATH"):
        env.pop(name, None)
    with tempfile.TemporaryDirectory(prefix="mesrecettes_tk_test_") as directory:
        result_path = Path(directory) / "result.json"
        result = subprocess.run(
            [str(Path(executable).resolve()), "--verify-tk-runtime", str(result_path)],
            cwd=directory, env=env, timeout=60, check=False,
        )
        report = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else {}
        if result.returncode != 0 or report.get("ok") is not True:
            raise RuntimeError("Le test de lancement Tcl/Tk a echoue : " + str(report.get("error", result.returncode)))


def main():
    try:
        if sys.argv[1:] == ["prepare"]:
            prepare()
        elif len(sys.argv) == 3 and sys.argv[1] == "verify":
            expected = json.loads(INVENTORY.read_text(encoding="utf-8"))
            if not expected:
                raise RuntimeError("Inventaire Tcl/Tk vide. Relancez la construction.")
            verify_archive(sys.argv[2], expected)
            print("[OK] Tous les fichiers Tcl/Tk sont integres et identiques aux originaux.")
            verify_runtime(sys.argv[2])
            print("[OK] L'interface Tcl/Tk de l'executable demarre correctement.")
        else:
            raise RuntimeError("Usage : build_tk_support.py prepare | verify chemin_executable")
    except Exception as error:
        print(f"[ERREUR] {error}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
