# Correctif import photo v36

Version produit : 1.4.2  
Build interne : 36

## Problème observé

À l’ouverture de « Importer une recette depuis une photo », la détection de
Tesseract prenait du temps. L’initialisation utilisait ensuite la constante
inexistante `COLOR_SUCCESS`, puis essayait de modifier le bouton OCR avant sa
création. La construction s’arrêtait, laissant une grande fenêtre vide.

## Correction

- fenêtre et boutons créés immédiatement ;
- vérification Tesseract lancée ensuite en arrière-plan ;
- état « vérification en cours » affiché sans bloquer la fenêtre ;
- utilisation de la couleur `COLOR_GREEN` existante ;
- bouton OCR activé uniquement lorsque Tesseract et la langue sont prêts ;
- échanges entre le thread OCR et l’interface effectués par une file sûre ;
- messages ajoutés en français, anglais, espagnol et allemand.

## Vérifications

- aucune utilisation restante de `COLOR_SUCCESS` ;
- compilation Python réussie ;
- catalogue de traductions valide et complet ;
- 68 tests automatisés réussis, dont 5 nouveaux tests ciblés v36.

Un test réel sous Windows reste nécessaire pour mesurer le délai de détection
de l’installation locale de Tesseract et vérifier la langue OCR installée.
