# Correctifs v23 — synthèse

Cette version applique dans l'ordre les corrections issues de l'audit complet de la v22.

## Intégrité et données
- NaN et Infinity refusés dans les données utilisateur.
- Écritures JSON strictes (`allow_nan=False`).
- Validation des recettes et des sauvegardes approfondie.
- Noms de fichiers image sécurisés et confinés à `images/`.
- Photos du journal de cuisine prises en compte dans sauvegarde, duplication, suppression et maintenance.
- Références de recettes migrées progressivement vers les IDs stables.
- Numéro de schéma de données ajouté aux réglages.

## Sauvegardes
- Restauration complète avec instantané de rollback.
- « Tout remplacer » efface réellement les données gérées absentes de l'archive.
- Limites différentes pour sauvegarde partagée (mobile) et sauvegarde complète Windows.
- Aperçu de sauvegarde valide réellement les JSON présents.

## Calculs
- Validation finie et positive des personnes/quantités/prix.
- Conversions g/kg et ml/cl/L centralisées.
- Parseur d'ingrédients enrichi pour fractions, multiplications et abréviations.
- Les ingrédients sans quantité explicite utilisent « au goût » plutôt que « 1 pièce ».
- Sélection des recettes pour les courses indexée par ID stable.

## Interface
- Zone de travail calculée sur le moniteur Windows réellement utilisé.
- `minsize` plafonné à la zone visible.
- Autocomplétion placée dessous ou au-dessus du champ selon l'espace disponible.
- Planning : en-tête synchronisé avec le défilement horizontal.
- Gestion ingrédients et édition d'ingrédient rendues plus compactes sur petits écrans.
- Menu de création/édition compacté avec « Plus d'actions ».
- Imports URL/OCR protégés si la fenêtre est fermée pendant le traitement.

## Maintenance du projet
- Traductions UI séparées dans `i18n_desktop.json`.
- Anciennes fonctions mortes supprimées.
- `main.pyw` devient un petit lanceur pour éviter deux copies du programme.
- `requirements.txt` avec versions testées.
- Script Inno spécifique pour la capture Store : `installateur_store_capture.iss`.
- Fichiers temporaires ignorés par Git.
- Tests de régression ajoutés dans `tests/`.

## À tester obligatoirement sur un vrai PC Windows avant publication
- PyInstaller + pyzbar/ZBar.
- Tesseract OCR et langues installées.
- SAPI5 / lecture vocale.
- Glisser-déposer windnd.
- Impression via l'association PDF Windows.
- DPI 125/150/200 % et configuration multi-écrans réelle.
- Inno Setup puis capture MSIX.

## Dernière passe de validation
- Gestion des ingrédients : actions compactées sur écran bas / Texte agrandi afin que Modifier et Supprimer restent accessibles.
- Deux ancres erronées d'autocomplétion supplémentaires ont été corrigées : les suggestions utilisent désormais le champ réellement actif.
- Tests de boutons effectués en 800×600, 1024×600, 1280×720 et 1366×768, en texte normal et agrandi : aucun bouton fixe testé hors fenêtre.
- Tests de démarrage/ouverture des principales fenêtres en 1024×600, 1280×720 et 1366×768, normal et agrandi : réussis.
- 29 tests automatiques de calcul, données, sauvegardes, QR et compatibilité : réussis.
- Tests PDF de contrainte : recette longue sur 2 pages et livre long sur 5 pages générés et rendus sans débordement horizontal visible.
- Tous les JSON de ressources ont été relus ; aucun JSON invalide ni clé JSON dupliquée détectée.
