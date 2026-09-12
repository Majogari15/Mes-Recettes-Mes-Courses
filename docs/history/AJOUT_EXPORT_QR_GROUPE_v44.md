# Export groupé des QR codes — build 44

Lorsqu'une recette est trop longue pour tenir dans un seul QR code, la fenêtre propose maintenant deux actions :

- **Enregistrer cette partie (PNG)** conserve le fonctionnement précédent ;
- **Enregistrer les N QR codes** choisit un dossier une seule fois et y crée tout le lot.

Les fichiers sont numérotés dans l'ordre attendu par l'import :

`qrcode_Nom de la recette_1sur3.png`, `..._2sur3.png`, `..._3sur3.png`.

Si certains fichiers existent déjà, une seule confirmation permet de remplacer l'ensemble. Tous les QR sont générés et vérifiés avant leur installation définitive. En cas d'erreur pendant l'opération, les anciens fichiers sont restaurés et les nouveaux fichiers partiels sont supprimés.
