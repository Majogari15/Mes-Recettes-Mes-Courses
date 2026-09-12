# Import photo — Windows 58

Fermer l’application, extraire cette archive puis lancer main.pyw. Les améliorations s’appliquent aux nouveaux imports ; une recette déjà enregistrée doit être corrigée ou réimportée.

## Vérification sur les fichiers fournis

Les trois photos barramundi (2).jpg ont été relues avec Tesseract 5 et son modèle français tessdata_fast, sans service OCR distant. Le test restaure le titre et le sous-titre, conserve les dix lignes d’ingrédients et l’ordre des six cases de préparation.

Pour 2 personnes : pommes de terre 500 g ; huile d’olive 3 cuillères à soupe ; beurre 1 cuillère à soupe ; filets de barramundi 2 pièces. Sel et poivre restent sans quantité numérique.

## Points nécessitant une relecture

- La photo indique ¼ de sachet de chapelure pour 2 personnes. Tesseract le lit encore comme %. L’application laisse cette quantité vide et avertit. Dans le texte extrait, remplacer % par 1/4 avant de créer la recette. Dans le formulaire dont les quantités sont pour 1 personne, saisir 0,125 sachet.
- Dans la préparation, la photo indique ½ cuillère à soupe d’huile par personne. Le moteur peut lire 2 ou perdre le nombre. La divergence est remplacée par [quantité à vérifier] ; remplacer ce marqueur par ½ après relecture.
- Quelques espaces ou mots peuvent rester imparfaits : l’OCR doit être relu, en particulier les nombres. Les deux remarques ci-dessus viennent de l’inspection des photos et ne sont pas des valeurs codées en dur pour cette recette.

L’ancien PDF contient huit ingrédients et un sachet entier de chapelure. Il n’a pas été modifié. Le nouveau code préserve dix ingrédients et signale les lectures incertaines au lieu de produire une quantité arbitraire.

## Validation

133 tests réussis. Compilation Python, cohérence des quatre langues et suite de non-régression. Test réel des trois photos avec le worker utilisé par la fenêtre d’import. Rendu natif des fenêtres Windows non testé dans cet environnement.
