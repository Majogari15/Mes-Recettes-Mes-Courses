# Livraison v78 — 1.6.31 (MSIX 1.6.31.0)

La v78 reprend la v77 livrée et finalise les corrections issues des PDF. Aucun commit ni envoi GitHub effectué. Projet source à reconstruire ; EXE/MSIX non compilé dans cet environnement.

## Corrections d’import

- Nom canonique Oeuf cohérent avec le catalogue : egg, oeuf et œuf convergent sans doublon simple. Allergène œufs détecté.
- Plages anglaises, fractions mixtes et unités : 1½ to 2 cups milk conserve 1,5 cup comme borne basse, le lait et son allergène, avec indication de la plage originale.
- Reconnaissance des ingrédients précédés d’une équivalence entre parenthèses : farine, babeurre, crème aigre et œuf. Les précisions restent conservées après le nom.
- Plage de portions 4 to 6 servings conservée avec avertissement ; borne basse utilisée.
- Repos et astuces identifiables récupérés ; explications sur les produits des cookies déplacées dans les notes.
- Huile, sel et poivre absents de la liste signalés dans des contextes culinaires ciblés, sans inventer de quantité.
- Durées de cuisson présentes dans les étapes conservées en notes lorsque cookTime manque. Pas de calcul automatique d’un total incertain.
- Notes personnelles, avis familial et pistes d’amélioration : suppression de la troncature à 500 caractères lors de l’enregistrement. Les étapes conservent leur limite préexistante de 12 000 caractères.

## Export PDF

Les fractions non couvertes par la police sont normalisées (1⁄4 devient 1/4, ½ devient 1/2). Un PDF réel a été généré, son texte extrait et sa page rendue puis vérifiée visuellement. Le fichier Verification_PDF_v78.pdf inclus est un contrôle synthétique, pas un réimport complet des sept recettes.

## Protections prioritaires de l’audit

- 01 : noms de brouillons calculés de façon sûre. Les identifiants courants gardent leur chemin historique ; les identifiants inhabituels sont hachés. Lecture/écriture/suppression passent par le même contrôle de confinement.
- 02 : les identifiants dupliqués dans une liste de recettes sont refusés avant sauvegarde/restauration.
- 03 : lors des fusions complète et partagée, une recette différente portant un identifiant existant devient une copie importée avec un nouvel identifiant. La recette locale et son journal sont conservés. Les références importées des menus/plannings sont remappées. Une répétition simple du même import conflictuel réutilise la copie inchangée ; si la copie a été modifiée, une autre copie préserve les deux versions.
- 04 : les deux parcours « J’ai cuisiné ça » distinguent échec d’enregistrement et erreur après réussite. Une erreur d’interface après écriture conserve la photo et ferme le dialogue après avertissement, empêchant une nouvelle validation du même dialogue. En cas d’échec avant écriture, la photo temporairement copiée est nettoyée.
- Les dialogues de fusion précisent que les autres données correspondantes (hors recettes protégées) peuvent être remplacées par l’archive.

## Vérification

- 241 tests exécutés : 232 réussis, 9 ignorés. 13 nouveaux tests permanents dans tests/test_finalize_v78.py.
- Cas testés : ingrédients des PDF, allergènes et exclusions, noms canoniques, plages et quantités, notes, confinement des brouillons, rejet de doublons, fusions complète/partagée et répétition, références des menus, succès persistant suivi d’erreur GUI, échec avant écriture, fractions PDF, notes longues.
- Le test antérieur de la forme Œuf a été harmonisé vers Oeuf ; un nouveau test vérifie réellement la convergence des trois écritures et l’absence de doublon dans le catalogue.
- Dix pages HTML précédemment téléchargées ont été réimportées hors ligne. Sur les cinq françaises, quantités, unités, portions et allergènes antérieurs sont préservés. Ce n’est pas un nouveau test réseau des vingt sites.
- Paramètres et présence des clés de traduction vérifiés FR/EN/ES/DE. Versions application/installateurs alignées.
- Détection Tesseract et parseur microdonnées identiques à la base GitHub de départ.

## Limites et suite de l’audit

Cette livraison ne clôt pas les 31 points de l’audit. Restent notamment : verrouillage interprocessus et snapshots cohérents, enregistrement des formulaires anciens, renommage global des ingrédients, validation profonde de tous les champs, validation QR, couverture des allergènes, densités nutritionnelles, annulation réseau, statut cloud, récupération après coupure brutale et tests Windows interactifs. La fusion protège les conflits de recettes ; elle n’implémente pas un écran de résolution champ par champ pour toutes les données. Le décompte de stock n’est pas une transaction unique avec le journal.

Les refus HTTP 403 ne sont pas contournés. Les anciens PDF/recettes déjà enregistrés ne sont pas automatiquement réparés : réimporter les recettes pour bénéficier du nouveau parseur, en conservant les originaux si nécessaire.

Aucun nouveau module OCR embarqué : la détection existante est préservée. Aucun EXE, installateur ou package Store exécuté sous Windows pendant cette livraison.
