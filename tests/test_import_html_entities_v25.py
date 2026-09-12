import html
import re
import unittest

class ImportHtmlEntitiesV25Tests(unittest.TestCase):
    def clean_text_equivalent(self, value):
        cleaned = re.sub(r"<[^>]+>", " ", str(value or ""))
        for _ in range(3):
            decoded = html.unescape(cleaned)
            if decoded == cleaned:
                break
            cleaned = decoded
        cleaned = cleaned.replace("\xa0", " ")
        return re.sub(r"[ \t]+", " ", cleaned).strip()

    def test_750g_entities_are_decoded(self):
        raw = (
            "M&eacute;langez les ingr&eacute;dients en une p&acirc;te uniforme. "
            "V&eacute;rifiez mais attention &ccedil;a cuit tr&egrave;s vite!"
        )
        got = self.clean_text_equivalent(raw)
        self.assertEqual(
            got,
            "Mélangez les ingrédients en une pâte uniforme. Vérifiez mais attention ça cuit très vite!"
        )

    def test_double_encoded_entities_are_decoded(self):
        self.assertEqual(self.clean_text_equivalent("M&amp;eacute;langez"), "Mélangez")

if __name__ == "__main__":
    unittest.main()
