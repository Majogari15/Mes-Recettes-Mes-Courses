
import inspect
import unittest
import main

class OneRecipeCookLogV33Tests(unittest.TestCase):
    def test_mark_as_cooked_does_not_use_missing_fmt_method(self):
        src = inspect.getsource(main.OneRecipeWindow.mark_as_cooked)
        self.assertNotIn("self._fmt(", src)
        self.assertIn("cooked_persons_display", src)
        self.assertIn("persons=cooked_persons_display", src)

    def test_onerecipe_has_no_required_fmt_dependency(self):
        self.assertFalse(hasattr(main.OneRecipeWindow, "_fmt"))

    def test_cooking_refreshes_canonical_recipe_and_visible_summary(self):
        source = inspect.getsource(main.OneRecipeWindow.mark_as_cooked)
        self.assertIn("refreshed = find_recipe_by_id", source)
        self.assertIn("self._display_recipe(self.current_recipe)", source)

    def test_cooking_photo_is_included_in_recipe_gallery(self):
        source = inspect.getsource(main.OneRecipeWindow._refresh_gallery)
        self.assertIn("onerecipe_latest_cook_photo", source)
        self.assertIn("cook_log", source)

    def test_recipe_library_does_not_refresh_after_it_was_closed(self):
        source = inspect.getsource(main.ManageRecipesWindow._open_index)
        self.assertIn("if not self.winfo_exists():", source)

    def test_edit_form_exposes_cooking_log_tab(self):
        source = inspect.getsource(main.RecipeFormWindow.__init__)
        self.assertIn("tab_cook_log", source)
        self.assertIn("recipeform_tab_cook_log", source)

    def test_edit_form_renders_cooking_history_details_and_photos(self):
        source = inspect.getsource(main.RecipeFormWindow._build_cook_log_tab)
        for token in ("cook_log", "cooklog_entry_persons", "cooklog_entry_rating", "load_thumbnail"):
            self.assertIn(token, source)

    def test_recipe_view_returns_to_foreground_after_edit(self):
        source = inspect.getsource(main.OneRecipeWindow._edit_recipe)
        self.assertIn("self.lift()", source)
        self.assertIn("self.focus_force()", source)
        self.assertIn("self.grab_set()", source)

    def test_recipe_view_can_refresh_without_being_destroyed(self):
        source = inspect.getsource(main.OneRecipeWindow.refresh_ui)
        self.assertIn("self._populate()", source)
        self.assertIn("self._display_recipe", source)

    def test_cooking_confirmation_keeps_recipe_view_active(self):
        source = inspect.getsource(main.OneRecipeWindow.mark_as_cooked)
        self.assertIn("parent=self", source)
        self.assertIn("self.deiconify()", source)

    def test_cook_log_uses_large_photos_and_responsive_text(self):
        source = inspect.getsource(main.RecipeFormWindow._build_cook_log_tab)
        self.assertIn("photo_w", source)
        self.assertIn("update_wraplength", source)
        self.assertIn("_cook_log_wrap_labels", source)
        self.assertIn("content_window", source)
        self.assertIn("canvas.itemconfigure", source)
        self.assertIn("content.winfo_width()", source)

if __name__ == "__main__":
    unittest.main()
