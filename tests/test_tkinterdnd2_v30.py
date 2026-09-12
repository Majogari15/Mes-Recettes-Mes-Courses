
import inspect
import unittest
import main

class TkinterDnD2V30Tests(unittest.TestCase):
    def test_old_windnd_backend_removed(self):
        source = inspect.getsource(main)
        self.assertNotIn("import windnd", source)
        self.assertNotIn("windnd.hook_dropfiles", source)

    def test_photo_tab_is_registered_as_drop_target(self):
        source = inspect.getsource(main.RecipeFormWindow._enable_photo_drop)
        self.assertIn("drop_target_register(DND_FILES)", source)
        self.assertIn('dnd_bind("<<Drop>>"', source)

    def test_drop_callback_splits_tcl_list_and_returns_copy(self):
        source = inspect.getsource(main.RecipeFormWindow._on_photo_drop_event)
        self.assertIn("self.tk.splitlist(event.data)", source)
        self.assertIn("return COPY", source)

if __name__ == "__main__":
    unittest.main()
