# Lanceur Windows sans console. Le code applicatif reste dans main.py.
import sys


def verify_tk_runtime(result_path):
    # Run before importing main: no recipes/settings/personal data are touched.
    import json
    from pathlib import Path
    import tkinter as tk
    from tkinter import ttk

    root = None
    try:
        root = tk.Tk()
        root.withdraw()
        ttk.Label(root, text="Recette : été").pack()
        photo = tk.PhotoImage(width=2, height=2)
        photo.put("#df813e", to=(0, 0, 2, 2))
        root.update_idletasks()
        report = {"ok": True, "tcl": str(root.tk.call("info", "patchlevel")),
                  "tk": str(root.tk.call("package", "require", "Tk"))}
    except Exception as error:
        report = {"ok": False, "error": str(error)}
    finally:
        if root is not None:
            root.destroy()
    Path(result_path).write_text(json.dumps(report), encoding="utf-8")
    return 0 if report["ok"] else 1

if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--verify-tk-runtime":
        sys.exit(verify_tk_runtime(sys.argv[2]))
    if len(sys.argv) == 2 and sys.argv[1] == "--msix-capture":
        # Mode utilise uniquement par MSIX Packaging Tool pour detecter
        # l executable dans Manage First Launch. Aucun fichier utilisateur
        # n est charge ou cree.
        import tkinter as tk
        capture_root = tk.Tk()
        capture_root.title("Mes Recettes, Mes Courses")
        capture_root.geometry("420x150")
        tk.Label(
            capture_root,
            text="Application détectée pour la création du package MSIX.",
            wraplength=360,
            padx=20,
            pady=20,
        ).pack(expand=True)
        tk.Button(capture_root, text="Fermer", command=capture_root.destroy).pack(pady=(0, 15))
        # Le processus reste visible pendant toute la page « Manage First
        # Launch ». L'utilisateur le ferme avant de continuer dans l'outil.
        capture_root.mainloop()
        sys.exit(0)
    from main import App, enable_windows_dpi_awareness

    enable_windows_dpi_awareness()
    app = App()
    app.mainloop()
