# Lot 4 — Garde-manger et listes de courses

Version interne : 7

## Garde-manger
- Nouvelle vue tableau avec colonnes ingrédient, quantité, stock minimum, péremption, statut et rayon.
- Statuts visuels : OK, stock faible, bientôt périmé, périmé.
- Recherche instantanée.
- Filtres Tous / Stock faible / Bientôt périmés / Périmés.
- Tri par nom, péremption ou statut.
- Résumé du nombre de produits, stocks faibles et produits à surveiller.
- Ajout direct d'un produit sélectionné à la liste de courses.
- Ajout en un clic de tous les stocks faibles à la liste de courses.
- Quantité suggérée à racheter calculée à partir du stock minimum.
- Conservation de la fonction « À cuisiner bientôt » du Lot 2.

## Listes de courses enregistrées
- Remplacement de la liste simple par un tableau plus lisible.
- Affichage du nom, du nombre d'articles et de la date de création.
- Renommage d'une liste.
- Duplication d'une liste avec nom automatique « copie ».
- Suppression et chargement conservés.

## Compatibilité
- Le champ `threshold` existant reste le stock minimum : aucun format de données incompatible n'est introduit.
- Les anciennes listes de courses enregistrées restent lisibles.
- Traductions ajoutées en français, anglais, espagnol et allemand.
