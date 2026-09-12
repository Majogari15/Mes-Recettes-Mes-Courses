# Correctifs v35 — Mes Recettes, Mes Courses

Version produit : 1.4.1  
Build interne : 35

## Corrections réalisées

- Journal de cuisine corrigé depuis la fiche et le mode plein écran.
- Compteur, date, note, commentaire, photo, étoiles et personnes enregistrés ensemble.
- Sauvegarde automatique déclenchée même en l’absence de recette si d’autres données existent.
- Détection des JSON illisibles ou structurellement invalides.
- Copie horodatée du fichier endommagé et blocage de son écrasement.
- Proposition de restauration de la dernière sauvegarde automatique valide.
- Transaction avec retour arrière pour recette/corbeille.
- Nouvelles photos supprimées si la recette ne peut pas être enregistrée.
- Anciennes photos supprimées seulement après réussite et uniquement si aucune autre recette ne les utilise.
- Restauration des images en flux sur disque, sans charger toute la photothèque en mémoire.
- Sauvegarde, export et restauration complets exécutés hors de l’interface, avec progression et annulation.
- Limite individuelle d’une entrée d’archive ramenée à 256 Mio.
- Traductions du livre PDF et du bouton Fermer corrigées dans les quatre langues.
- Métadonnées `source_url` et `quantity_basis` conservées après un import Internet.
- Nettoyage des images temporaires anciennes activé au démarrage.
- Lanceur Windows configuré pour exécuter tous les fichiers `test_*.py`.
- Documentation et numéros de version actualisés.

## Vérifications automatiques

- Compilation de `main.py` et `main.pyw` : réussie.
- Validation de tous les JSON : réussie.
- Traductions FR/EN/ES/DE : mêmes clés et mêmes paramètres.
- Suite complète : 63 tests réussis sur 63.
- Export réel du livre PDF : titre, date et sommaire correctement traduits.
- Test de corruption : copie de secours créée et écrasement refusé.
- Test de panne pendant recette/corbeille : retour à l’état initial réussi.
- Test de restauration avec image : contenu restauré à l’identique.
- Test d’annulation d’une sauvegarde : ancienne destination conservée.

## Tests Windows encore indispensables

1. Construire l’EXE avec `Construire_le_exe.bat` sur Windows.
2. Lancer `Executer_les_tests.bat` et vérifier les 63 tests.
3. Tester « J’ai cuisiné ça » depuis la fiche puis depuis le mode cuisine.
4. Tester une sauvegarde et une restauration avec beaucoup de photos, puis le bouton Annuler.
5. Tester la récupération sur une copie de données après corruption volontaire d’un JSON.
6. Vérifier maximisation/restauration à 100, 125, 150 et 200 % de mise à l’échelle.
7. Vérifier Tesseract, glisser-déposer, lecture QR, SAPI5 et impression.
8. Compiler l’installateur Inno 1.4.1 et tester une mise à niveau depuis la version précédente.

Les intégrations Windows ne peuvent pas être certifiées dans l’environnement Linux utilisé pour les contrôles automatiques.
