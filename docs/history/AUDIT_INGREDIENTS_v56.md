# Audit des ingrédients — build 56

## Résultat et périmètre

La base fournie comporte 1 030 ingrédients. Tous possédaient déjà les quatre
valeurs nutritionnelles et une traduction en anglais, espagnol et allemand.
Il n'y avait donc aucune fiche nutritionnelle entièrement vide à compléter.
Cela ne signifie pas que les valeurs étaient correctes : de nombreuses fiches
partageaient des estimations identiques malgré des compositions différentes.

Cette version apporte :

- 290 fiches nutritionnelles remplacées par des valeurs ANSES Ciqual 2025 ;
- 60 listes d'allergènes corrigées ;
- 26 traductions corrigées parmi les 3 090 libellés relus ;
- la conservation des 1 030 noms français, pour ne pas casser les recettes ;
- une meilleure reconnaissance des accents, ligatures et apostrophes ;
- l'exclusion des fiches nutritionnelles incomplètes des totaux, sans transformer une donnée absente en zéro.

**740 fiches nutritionnelles restent des estimations anciennes non vérifiées.**
La base n'est donc pas certifiée intégralement. Les données personnelles,
les ingrédients ajoutés sur votre ordinateur et leurs surcharges ne sont pas
disponibles ici : ils ne sont pas inclus dans ce bilan et ne sont pas écrasés.

## Exemples corrigés

| Élément | Problème trouvé | Correction |
| --- | --- | --- |
| Ail en poudre | Même profil que l'ail frais | Ciqual 11023 : 346 kcal, 16,6 g de protéines, 63,7 g de glucides, 0,73 g de lipides pour 100 g |
| Groseille à maquereau | Classée poisson | Faux positif retiré |
| Courge spaghetti | Classée gluten | Faux positif retiré |
| Beurre noisette | Classé fruits à coque | Classé lait |
| Lait, beurre, noix | Allergènes non signalés | Catégories correspondantes ajoutées |
| Œufs de saumon | Classés œufs et poisson | Catégorie poisson seulement |
| Quatre épices, anglais | Confusion avec le piment de la Jamaïque | Four-spice blend |
| Sucre en poudre, espagnol | Confusion avec le sucre glace | Azúcar granulado fino |
| Farines T45/T55/T65, allemand | Équivalence nationale présentée comme exacte | Type français conservé explicitement |

## Source nutritionnelle et conventions

Source : **ANSES, Table Ciqual 2025**, publiée le 19 novembre 2025,
[jeu officiel DOI 10.57745/RDMHWY](https://doi.org/10.57745/RDMHWY), fichier
`Table Ciqual 2025_FR_2025_11_03.xlsx`, feuille « composition nutritionnelle ».
Réutilisation sous **Licence Ouverte Etalab 2.0**.

Les valeurs sont celles de la partie comestible pour **100 g**, pas d'une
portion ou d'un aliment entier non épluché. L'énergie suit la colonne du
règlement UE ; les protéines suivent la colonne N × 6,25. Chaque fiche
modifiée conserve son code Ciqual, le nom précis de l'aliment, son état et
l'URL de source dans `_ciqual`, dans `valeurs_nutritionnelles.json`.

Les rapprochements ont été sélectionnés par correspondance exacte relue ou
équivalence explicite. Aucun remplacement flou automatique n'a été appliqué.
Les noms génériques de fruits et légumes sont rapprochés de l'aliment cru,
avec les précisions de partie comestible indiquées par la source. Le lait
entier/demi-écrémé/écrémé utilise la référence UHT, visible dans sa fiche.
Les produits moyens et transformés restent des estimations, pas la composition
exacte de toutes les marques.

Lorsqu'une teneur est « < x », le calcul utilise x comme **borne supérieure**,
et conserve ce qualificatif dans la provenance. Les mentions « traces » et
les valeurs absentes ne sont pas converties en zéros : ces correspondances
ne sont pas appliquées et figurent dans la liste des données restant à vérifier.

Limites du calcul existant : les volumes sont assimilés à 1 g/ml. Cette
approximation est moins adaptée aux huiles, au miel et aux produits en poudre.
Les unités pièce, sachet, barquette, etc., sans poids de référence ne sont
pas comptées. Une valeur apparemment manquante dans une recette peut donc
venir de son unité, et non d'une absence dans la base nutritionnelle.

## Allergènes : précautions indispensables

Les corrections utilisent les catégories présentées par la
[Food Standards Agency](https://www.gov.uk/government/publications/allergen-guidance-for-food-businesses/allergen-guidance-for-food-businesses)
et une revue de la composition usuelle des ingrédients. Il ne s'agit ni d'une
analyse de laboratoire, ni d'une vérification des étiquettes de chaque marque.

L'affichage « Lactose » devient « Lait (dont lactose) ». La clé technique
`Lactose` est conservée pour la compatibilité des filtres et des sauvegardes.
Elle ne renseigne pas la teneur en lactose et ne distingue pas une intolérance
au lactose d'une allergie aux protéines du lait.

Les produits composés (pesto, satay, tapenade, sauces, pâtisseries) sont traités
d'après leur composition usuelle. Vérifier les variantes végétales, sans gluten
et les recettes propres à chaque fabricant. Farine, pâtes et semoules génériques
sont présumées à base de blé ; les variantes doivent avoir une fiche distincte.

**Une liste vide ne garantit jamais l'absence d'allergène.** Les contaminations
croisées, traces, taux de sulfites, huiles raffinées, arômes et formulations
commerciales ne peuvent pas être déduits du seul nom. D'autres ingrédients
hors des 14 catégories peuvent provoquer des allergies. Le pignon de pin, par
exemple, reste un cas à revoir dans le modèle de données : il était regroupé
avec les fruits à coque, sans appartenir aux huit fruits à coque de cette liste.

Les allergènes enregistrés dans d'anciennes recettes ne sont pas réécrits
automatiquement : utiliser « Détecter automatiquement » dans leur éditeur,
puis contrôler les étiquettes et les cases avant l'enregistrement.

## Ce qui reste à vérifier

Le journal `AUDIT_INGREDIENTS_v56.json` contient les changements avant/après,
la provenance de chaque correction et la liste nominative des 740 estimations
nutritionnelles restantes. Il liste aussi les fiches Ciqual incomplètes.

Priorités :

1. Préciser sec/cru/cuit pour les céréales et légumineuses, entier/écrémé pour
   les poudres de lait, et boisson/produit sec pour café et thé.
2. Vérifier les références exactes des sauces, arômes, mélanges d'épices,
   produits composés et ingrédients personnels à partir de leurs étiquettes.
3. Distinguer allergènes certains, possibles et traces dans le modèle de
   données, ainsi que lait et teneur en lactose.
4. Ajouter les poids unitaires et densités par aliment pour fiabiliser les
   calculs en pièces, sachets, cuillères et volumes.
5. Faire valider les termes régionaux par des locuteurs : airelle, nèfle,
   pamplemousse/pomelo, germes et vermicelles dits « de soja » restent ambigus.

Les alias comme Blette/Bette à carde, Arachide/Cacahuète, Lotte/Baudroie et
Pieuvre/Poulpe sont conservés, sans fusion destructive des recettes existantes.

## Installation et vérification

Décompresser dans un nouveau dossier et lancer `main.pyw` comme auparavant.
Ne pas remplacer vos sauvegardes personnelles par des fichiers de démonstration.
Dans « Gérer les ingrédients », ouvrir « Modifier » puis « Nutrition et prix »
pour voir la référence Ciqual ou l'avertissement de donnée non vérifiée.

Les tests automatiques couvrent la structure de toute la base, les corrections
ciblées, la provenance, les variantes d'écriture, les surcharges personnelles
et les calculs. Ils ne constituent pas une certification nutritionnelle ni une
validation visuelle sous Windows.

Résultats : **122 tests réussis**, compilation de `main.py` et `main.pyw`
réussie. Une comparaison indépendante avec le classeur officiel confirme
les 1 160 valeurs numériques des 290 fiches sourcées. Aucun test visuel
de cette version sous Windows n'a été effectué dans cet environnement.
