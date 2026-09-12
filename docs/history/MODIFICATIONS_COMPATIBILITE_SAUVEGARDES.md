# Compatibilité sauvegardes Windows ↔ mobile

Corrections intégrées dans cette archive :

- nouvel identifiant lors de la duplication d'une recette sous Windows ;
- conservation des champs propres au mobile lors d'une modification sous Windows ;
- prix d'ingrédients échangés via `ingredient_prices.json` ;
- conversion `substitutes` ↔ `substitutions` ;
- conservation des photos Windows supplémentaires lors d'un aller-retour par le mobile ;
- avertissement Windows au-dessus de 50 Mo et refus au-dessus de 100 Mo ;
- absence de duplication d'une photo déjà identique lors d'une fusion Windows ;
- validation des données de l'archive partagée avant suppression des anciennes données Windows ;
- compatibilité maintenue avec les anciennes archives mobiles où prix et substituts étaient intégrés dans `ingredient_custom_data.json`.

Vérifications effectuées : compilation syntaxique de `main.py` et `main.pyw`, test isolé export/restauration du format partagé et test d'import d'une archive mobile ancienne.
