# Rafraîchissement des fenêtres et molette locale — build 55

## Fenêtres déjà ouvertes

- Les textes des boutons, labels, onglets, menus, listes, tableaux et canevas sont traduits sans fermer la fenêtre.
- Les textes contenant des valeurs dynamiques conservent ces valeurs pendant la traduction.
- Les couleurs Tkinter explicites sont converties vers la nouvelle palette.
- Les polices déjà créées sont redimensionnées lorsque le mode « Texte agrandi » change.
- Les champs de saisie et leur contenu utilisateur ne sont jamais remplacés.

## Molette

- Chaque zone défilable possède désormais un bindtag local.
- La molette n'utilise plus `bind_all` ni `unbind_all`.
- Fermer ou survoler une fenêtre ne peut donc plus désactiver le défilement d'une autre.
