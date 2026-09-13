import hashlib
from pathlib import Path
import tempfile
import tkinter
import unittest
import zipfile

import build_tk_support as support

try:
    from PyInstaller.archive.writers import CArchiveWriter
except ImportError:
    CArchiveWriter = None


class TclResourceCopyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.tcl = tkinter.Tcl()

    def test_normal_directory_preserves_nested_files_and_bytes(self):
        source = self.folder / "source été [test]" / "nested"
        source.mkdir(parents=True)
        payload = bytes(range(256))
        (source / "sample.bin").write_bytes(payload)
        target = self.folder / "copie été [test]"
        support.copy_tcl_tree(self.tcl, str(source.parent), target)
        self.assertEqual((target / "nested/sample.bin").read_bytes(), payload)

    def test_zipfs_directory_is_copied_with_tcl_api(self):
        if not self.tcl.call("info", "commands", "zipfs"):
            self.skipTest("Tcl without zipfs; run this test with Tcl 9")
        archive = self.folder / "runtime.zip"
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("lib/init.tcl", "# initialisation été")
            z.writestr("lib/encoding/data.bin", bytes(range(256)))
        self.tcl.call("zipfs", "mount", str(archive), "/mesrecettes_test")
        self.addCleanup(self.tcl.call, "zipfs", "unmount", "/mesrecettes_test")
        source = "//zipfs:/mesrecettes_test/lib"
        self.assertFalse(Path(source).is_dir())
        support.copy_tcl_tree(self.tcl, source, self.folder / "output")
        self.assertEqual((self.folder / "output/init.tcl").read_text(encoding="utf-8"), "# initialisation été")
        self.assertEqual((self.folder / "output/encoding/data.bin").read_bytes(), bytes(range(256)))

    def test_missing_source_is_refused(self):
        with self.assertRaisesRegex(RuntimeError, "introuvable"):
            support.copy_tcl_tree(self.tcl, str(self.folder / "absent"), self.folder / "out")


@unittest.skipIf(CArchiveWriter is None, "PyInstaller is required for archive tests")
class EmbeddedArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def archive(self, files):
        entries = []
        for index, (name, content) in enumerate(files.items()):
            source = self.folder / str(index)
            source.write_bytes(content)
            entries.append((name, str(source), True, "x"))
        output = self.folder / "test.pkg"
        CArchiveWriter(str(output), entries, "python314.dll")
        return output

    def test_complete_archive_accepts_windows_separators_and_hashes(self):
        files = {"_tcl_data\\init.tcl": b"tcl", "_tk_data\\tk.tcl": b"tk", "_tk_data\\ttk\\ttk.tcl": b"ttk"}
        expected = {name.replace("\\", "/"): hashlib.sha256(data).hexdigest() for name, data in files.items()}
        support.verify_archive(self.archive(files), expected)

    def test_original_failure_no_resource_directories(self):
        with self.assertRaisesRegex(RuntimeError, "init.tcl"):
            support.verify_archive(self.archive({"tcl90.dll": b"dll"}))

    def test_missing_tk_is_refused(self):
        with self.assertRaisesRegex(RuntimeError, "tk.tcl"):
            support.verify_archive(self.archive({"_tcl_data/init.tcl": b"tcl"}))

    def test_empty_init_is_refused(self):
        with self.assertRaisesRegex(RuntimeError, "vide"):
            support.verify_archive(self.archive({"_tcl_data/init.tcl": b"", "_tk_data/tk.tcl": b"tk"}))

    def test_other_missing_resource_is_refused(self):
        with self.assertRaisesRegex(RuntimeError, "ttk.tcl"):
            support.verify_archive(self.archive({"_tcl_data/init.tcl": b"tcl", "_tk_data/tk.tcl": b"tk"}),
                                   {"_tk_data/ttk/ttk.tcl": "missing"})

    def test_changed_resource_is_refused(self):
        with self.assertRaisesRegex(RuntimeError, "incorrecte"):
            support.verify_archive(self.archive({"_tcl_data/init.tcl": b"tcl", "_tk_data/tk.tcl": b"tk"}),
                                   {"_tk_data/tk.tcl": hashlib.sha256(b"other").hexdigest()})


if __name__ == "__main__":
    unittest.main()
