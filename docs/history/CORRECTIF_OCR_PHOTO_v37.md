# Correctif OCR photo v37

Version produit : 1.5.0  
Build interne : 37

## Problèmes reproduits

- Certaines photos prises avec un téléphone étaient affichées correctement par Windows,
  mais envoyées à Tesseract dans le sens stocké dans le JPEG : le résultat semblait lu
  à l'envers ou tête-bêche.
- Une table d'ingrédients pouvait séparer le nom et la quantité sur deux lignes ou les
  remettre dans le mauvais ordre.
- Une fiche HelloFresh en 3 colonnes et 2 rangées était lue verticalement
  (1, 4, 2, 5, 3, 6) au lieu de suivre les étapes imprimées.
- Le bouton final transférait seulement le texte brut dans la préparation : nom,
  portions, durée et ingrédients restaient vides.

## Corrections apportées

1. L'orientation EXIF est appliquée avant l'OCR.
2. Tesseract OSD peut corriger automatiquement une rotation restante lorsque sa
   confiance est suffisante.
3. Deux boutons permettent toujours de tourner manuellement la photo à gauche ou à
   droite ; l'aperçu reflète la rotation, sans toucher au fichier original.
4. Les JPEG sont ramenés à 1600 px maximum uniquement en mémoire pour l'OCR. Ce seuil
   reprend celui validé dans l'application mobile sur les mêmes photos Barramundi.
5. Une page reconnue comme table d'ingrédients reçoit un second passage Tesseract en
   mode PSM 4, plus adapté aux lignes nom/quantité.
6. Une page de préparation qui ressemble à une grille est découpée en six images,
   reconnues dans l'ordre ligne par ligne : 1, 2, 3, puis 4, 5, 6.
7. Le texte est analysé pour préremplir le titre, la durée, le nombre de personnes,
   les ingrédients et la préparation.
8. Les quantités photographiées sont considérées comme les totaux de la recette et
   divisées une seule fois par le nombre de personnes détecté. Le stockage interne
   reste donc cohérent avec tous les autres écrans de l'application.
9. Les fractions mal reconnues (par exemple `¼` lu `%`) et les confusions `1`/`i`
   sont conservées prudemment plutôt que de supprimer l'ingrédient. La relecture du
   formulaire final reste nécessaire, car aucun OCR ne garantit chaque caractère.

## Validation effectuée

- Les trois photos Barramundi fournies ont été exécutées avec le Tesseract disponible
  dans l'environnement de test (modèle anglais seulement ici).
- Orientation trouvée : 0° sur les trois copies normalisées reçues.
- La page de préparation déclenche bien le découpage en grille.
- La table fournit les 10 ingrédients attendus, y compris tomates cerises, beurre,
  huile d'olive et poivre/sel malgré plusieurs erreurs OCR résiduelles.
- Pour 2 personnes : pommes de terre stockées à 250 g par personne et filet de
  barramundi à 1 pièce par personne.
- 75 tests automatisés sur 75 réussis.

## Limite de la validation

L'environnement de test ne possède pas le modèle français `fra.traineddata`, seulement
`eng` et `osd`. La structure et les photos réelles ont donc été vérifiées, mais la
qualité exacte des accents avec le modèle français doit encore être confirmée sur le PC
Windows où Tesseract français est installé.
