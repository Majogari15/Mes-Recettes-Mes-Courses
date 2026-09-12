# Audit correctif v22 — Mes Recettes, Mes Courses

## Objectif

Cette version corrige les anomalies relevées lors de l'audit complet de la v21, sans changer le format général des recettes ni casser la compatibilité des sauvegardes/QR existants.

## Corrections de calcul

- Décrémentation du garde-manger corrigée : quantité par personne × nombre réel de personnes cuisinées.
- Un second ajout de la même recette aux courses remplace le nombre de personnes précédent au lieu de cumuler deux fois la recette.
- Validation stricte des nombres de personnes : zéro et valeurs négatives sont refusés dans les parcours concernés.
- Planning et menus : reprise automatique du nombre de personnes par défaut de la recette sélectionnée.
- Calcul « Que puis-je cuisiner ? » : tient compte des quantités réellement disponibles et du nombre de personnes par défaut.
- Fusion des unités compatibles dans les courses : g/kg et ml/cl/L.
- Coûts, nutrition et garde-manger harmonisés pour g, kg/Kilo, ml, cl et L/Litre.
- Éditeur de recette : Kilo, ml et Litre sont correctement rechargés et les unités personnalisées restent compatibles avec les langues de l'interface.
- Libellé de saisie clarifié : quantité par personne.

## Import Internet

- Reconnaissance améliorée des fractions mixtes (ex. 1 1/2), fractions Unicode et plages simples (ex. 2 à 3).
- Les nouveaux imports sont marqués comme utilisant une quantité interne par personne.
- Les imports Internet anciens dont la base de quantité est inconnue sont signalés dans Maintenance au lieu d'être modifiés automatiquement.

## Sauvegardes et restauration

- Déduplication renforcée de recent_views et de la corbeille lors des fusions répétées.
- Les formats partagés existants restent conservés.

## Fenêtres et petits écrans

- `minsize` est désormais plafonné à la zone de travail réellement disponible.
- Actions compactes pour Mes courses, Voir une recette et le Planning sur les écrans de faible hauteur.
- Garde-manger réorganisé en mode compact et en Texte agrandi.
- Recherche par ingrédient restaurée à sa largeur élargie.
- Les fenêtres principales ont été testées en 1024×600, 1280×720 et 1366×768, en texte normal et agrandi.

## PDF

- Retours automatiques à la ligne pour titres, ingrédients, allergènes, descriptions et sommaire.
- Gestion plus sûre des changements de page et réinitialisation des polices.
- Noms de fichiers de menus nettoyés pour Windows.
- Tests avec titre et ingrédients volontairement très longs : génération et rendu réussis sur plusieurs pages.

## Traductions et diagnostic

- 0 clé française manquante en anglais, espagnol ou allemand dans l'audit automatisé.
- Doublons parasites de traduction supprimés.
- Les exceptions Tkinter non interceptées sont journalisées dans `error.log` dans le dossier de données de l'utilisateur.

## Tests principaux

- 100 g/personne × 4 personnes : retrait de 400 g du garde-manger.
- 100 g/personne dans le planning pour 4 + 2 personnes : 600 g dans les courses.
- 100 g + 0,1 kg : fusion en 200 g.
- 10 cl + 100 ml : fusion en 20 cl.
- Prix 10 €/kg, 2 personnes × 1 kg/personne : 20 €.
- Stock 150 g face à un besoin de 400 g : recette classée partielle, pas réalisable à 100 %.
- Réajout d'une recette 4 puis 6 personnes : la seconde valeur remplace la première.
- Tests géométriques : aucun bouton fixe hors de la zone visible dans les tailles testées.

## Limitation volontaire

Les recettes importées par URL avant la correction v18 ne sont pas recalculées automatiquement : il est impossible de distinguer de façon fiable une ancienne quantité erronée d'une quantité saisie volontairement. Elles sont donc seulement signalées pour vérification/réimport.
