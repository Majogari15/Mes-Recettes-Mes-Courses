"""Disposition droite-gauche en arabe : pack, grid, ancres, tableaux et cadres
défilants mis en miroir ; aucune différence dans les autres langues."""
import sys
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import main  # noqa: E402


class RtlLayoutTests(unittest.TestCase):
    def _window(self, rtl):
        main.install_rtl_layout()
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.addCleanup(root.destroy)
        root.withdraw()
        root._mrmc_rtl = rtl
        root.geometry("400x300")
        return root

    def _build(self, root):
        bar = ttk.Frame(root)
        bar.pack(fill="x")
        first, second = ttk.Label(bar, text="أ"), ttk.Label(bar, text="ب")
        first.pack(side="left", padx=(5, 20))
        second.pack(side="left")
        grid = ttk.Frame(root)
        grid.pack(fill="x")
        grid.columnconfigure(1, weight=1)
        a, b = ttk.Label(grid, text="الاسم"), ttk.Entry(grid)
        a.grid(row=0, column=0, sticky="w")
        b.grid(row=0, column=1, sticky="ew")
        tree = ttk.Treeview(root, columns=("name", "qty"), show="headings")
        tree.column("name", anchor="w")
        tree.pack()
        canvas = tk.Canvas(root, width=300, height=50)
        canvas.pack(fill="x")
        inner = ttk.Label(canvas, text="محتوى")
        item = canvas.create_window((0, 0), window=inner, anchor="nw")
        root.deiconify(); root.update()
        return first, second, a, b, tree, canvas, item, grid

    def test_arabic_window_is_mirrored(self):
        root = self._window(True)
        first, second, a, b, tree, canvas, item, grid = self._build(root)
        self.assertEqual(first.pack_info()["side"], "right")
        self.assertEqual(first.pack_info()["padx"], (20, 5))
        self.assertGreater(first.winfo_x(), second.winfo_x())
        self.assertGreater(a.winfo_x(), b.winfo_x())
        self.assertEqual(a.grid_info()["sticky"], "e")
        self.assertGreater(b.winfo_width(), 100)  # la colonne extensible reste extensible
        self.assertEqual(str(a.cget("justify")), "right")
        self.assertEqual(list(tree.cget("displaycolumns")), ["qty", "name"])
        self.assertEqual(str(tree.column("name", "anchor")), "e")
        self.assertEqual(canvas.itemcget(item, "anchor"), "ne")
        self.assertEqual(canvas.coords(item)[0], canvas.winfo_width())
        self.assertIsNotNone(grid.grid_bbox(1, 0))
        self.assertEqual(grid.grid_slaves(row=0, column=0), [a])

    def test_other_languages_unchanged(self):
        root = self._window(False)
        first, second, a, b, tree, canvas, item, _grid = self._build(root)
        self.assertEqual(first.pack_info()["side"], "left")
        self.assertLess(first.winfo_x(), second.winfo_x())
        self.assertLess(a.winfo_x(), b.winfo_x())
        self.assertEqual(int(a.grid_info()["column"]), 0)
        self.assertEqual(str(a.cget("justify")), "left")
        self.assertEqual(canvas.itemcget(item, "anchor"), "nw")


if __name__ == "__main__":
    unittest.main()
