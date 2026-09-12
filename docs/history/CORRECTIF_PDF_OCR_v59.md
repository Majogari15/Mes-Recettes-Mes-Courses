# Correction Windows v59 (1.6.11)

Décompressez cette version dans un nouveau dossier, puis lancez main.pyw.
La correction du nom s'applique au prochain export PDF (elle ne renomme pas les fichiers déjà créés).
Pour bénéficier de la lecture des fractions, réimportez les photos. Les recettes déjà enregistrées ne sont pas réécrites automatiquement.

## Votre recette Barramundi

- Chapelure panko : 1/4 de sachet au total pour 2 personnes. La base interne pour 1 personne est 0,125 sachet.
- Huile d'olive : 3 cuillères à soupe au total pour 2 personnes. La base pour 1 personne est 1,5 cuillère à soupe.
- Dans le mélange de la croûte : par personne, 1 cuillère à soupe de chapelure panko et 1/2 cuillère à soupe d'huile d'olive. Le reste de l'huile sert aux autres étapes.
- Le poids du sachet n'est pas indiqué sur la photo : aucune conversion en grammes n'est ajoutée.

La lecture a retrouvé ces valeurs sur vos trois photos. Elle repose sur la séparation des petits chiffres, avec deux cadrages concordants par chiffre, et non sur un remplacement automatique du signe % par 1/4.

## Vérifications et limites

142 tests automatisés réussis. Import réel des trois photos avec Tesseract français, contrôle du nom et du texte du PDF généré, inspection de ses deux pages. Les tests s'exécutent sous Linux ; le dialogue natif d'enregistrement Windows n'a pas été exécuté ici.

Cela ne garantit pas toutes les fractions sur toutes les photographies : une vérification reste nécessaire en cas d'image floue ou de lecture ambiguë. Quelques erreurs de texte non liées aux mesures subsistent sur l'exemple, notamment un « on » parasite après « eau de cuisson » ; elles restent modifiables dans l'aperçu. La correction ne certifie pas les allergènes ni les estimations nutritionnelles.

L'ancienne notice v58 décrit les limites de cette version précédente ; la présente notice la remplace pour les fractions testées.
