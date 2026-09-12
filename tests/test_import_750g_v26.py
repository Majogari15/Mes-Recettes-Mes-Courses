import unittest
import main

class Import750gV26Tests(unittest.TestCase):
    def test_oe_ligature_resolves(self):
        self.assertEqual(main.resolve_ingredient_input("Œufs", ["Oeufs"]), "Oeufs")

    def test_c_a_s_is_tablespoon(self):
        p = main.parse_ingredient_line("8 c à s de farine")
        self.assertEqual(p["unit"], "cuillère à soupe")
        self.assertEqual(p["name"], "Farine")
        self.assertEqual(p["quantity"], 8)

    def test_sachet_and_poignee_names_are_cleaned(self):
        self.assertEqual(main.parse_ingredient_line("1 sachet de levure chimique")["name"], "Levure chimique")
        self.assertEqual(main.parse_ingredient_line("1 poignée de pépites de chocolat")["name"], "Pépites de chocolat")

if __name__ == "__main__":
    unittest.main()
