# Correctif du journal de cuisine — build 45

Après l'enregistrement d'une cuisson, la fiche de recette recharge désormais l'objet écrit dans `recipes.json`. Le panneau « Description et notes » présente la dernière cuisson (date, personnes, étoiles, note et commentaire) et la galerie montre sa photo la plus récente.

Le bouton « Journal de cuisine » recharge également la recette depuis le disque. Les informations restent donc visibles après une cuisson effectuée depuis le mode cuisine ou une autre fenêtre.

Enfin, le retour vers la bibliothèque est protégé lorsque celle-ci a été fermée pendant l'affichage de la fiche. Cela évite l'appel à un champ Tkinter détruit (`invalid command name ...entry`).
