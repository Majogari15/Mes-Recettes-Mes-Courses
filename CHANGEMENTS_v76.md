# Build 76 — version 1.6.29

Base : branche main, commit e9a6c02113f08538acef3ef1636fff7af0c6eb2a, récupérée le 15 septembre 2026.
Dépôt : https://github.com/Majogari15/Mes-Recettes-Mes-Courses

## Modifications préservées

Le parseur _MicrodataRecipeParser et detect_tesseract ont été comparés au code du dépôt : leurs arbres syntaxiques sont identiques. Le script Construire_le_exe.bat est inchangé. Les deux scripts Inno Setup ne changent que de numéro de version ; leur gestion du dossier tesseract-ocr reste présente. Les autres corrections d'interface du dépôt sont conservées.

## Corrections de l'import

- Pots à yaourt reconnus comme mesures ; aucun poids n'est inventé.
- Suppression de la fuite du marqueur interne sachet-mesure dans les noms.
- Parenthèses normalisées pour comparer les ingrédients HTML et JSON-LD : le Beaufort et le basilic de Clem Foodie ne sont plus doublés. Les répétitions déjà présentes dans une liste pour des étapes différentes sont conservées.
- Reconnaissance des allergènes améliorée pour les noms détaillés (œufs entiers ou frais, farine de blé, lait tiède, beurre fondu, fromage frais). Les précisions restent affichées ; les corrections personnelles sont prioritaires. Les mentions sans gluten, sans lactose ou végétales ne sont pas supprimées pour forcer un rapprochement.
- Rendement en crêpes conservé depuis les titres balisés ; un libellé combinant 15 crêpes et 6 personnes utilise bien 6 personnes. En l'absence de convives explicitement indiqués, le défaut de 4 reste signalé et modifiable.
- Temps de repos explicitement mentionnés dans les instructions copiés dans les notes ; aucune soustraction du temps total pour inventer un repos.
- Suppression du doublon d'unité « minutes min » ; conseils 750g récupérés.
- Avertissement traduit dans les quatre langues quand des œufs chiffrés sont mentionnés dans les étapes sans figurer dans les ingrédients. La liste n'est pas complétée silencieusement. Cette détection ciblée n'est pas une analyse universelle des ingrédients implicites.
- Une seule nouvelle tentative après expiration ou HTTP 502/503/504. Les refus HTTP 403 restent signalés, sans contournement.

## Validation

221 tests exécutés : 212 réussis, 9 ignorés, aucun échec. Sortie complète dans TESTS_v76.txt.
Les nouveaux tests couvrent les régressions ci-dessus ; les tests du repli microdonnées et de Tesseract portable du dépôt passent aussi.
Cinq pages HTML réelles ont été téléchargées le 15 septembre, puis analysées par le pipeline final. La récupération d'image a été neutralisée pour ces contrôles de contenu : ce n'est pas un test d'installation ou d'interface Windows.

- [750g](https://www.750g.com/gateau-au-yaourt-moelleux-r205119.htm) : contrôles ciblés réussis, 7 ingrédients.
- [Chef Simon](https://chefsimon.com/gourmets/chef-simon/recettes/la-pate-a-crepes) : contrôles ciblés réussis, 5 ingrédients.
- [Hervé Cuisine](https://www.hervecuisine.com/recette/crepes-de-la-chandeleur/) : contrôles ciblés réussis, 8 ingrédients.
- [Clem Foodie](https://clemfoodie.com/2025/08/24/tarte-facile-au-fromage-et-tomates/) : contrôles ciblés réussis, 9 ingrédients.
- [Mes Recettes Faciles](https://www.mesrecettesfaciles.fr/recipe/salade-de-figues-et-fromage-frais) : contrôles ciblés réussis, 8 ingrédients.

Les blocages des cinq autres sites du précédent audit ne sont pas déclarés résolus. Les contrôles ciblés ne prouvent pas que toutes les recettes d'un site seront parfaitement importées. L'interface Windows et la compilation EXE/MSIX restent à vérifier sur Windows.

## Utilisation

Cette archive contient les sources complètes, pas un EXE précompilé. Utiliser les scripts habituels pour reconstruire. Le dossier portable tesseract-ocr reste facultatif et n'est pas fourni dans cette archive.
Réimporter les recettes concernées pour appliquer les corrections aux données enregistrées. Aucune modification n'a été poussée sur GitHub.
