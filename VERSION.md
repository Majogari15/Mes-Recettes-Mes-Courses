# Version actuelle

## Build 67 — nom d’exécutable aligné sur le nom du produit

- Version produit : **1.6.20** ; version MSIX : **1.6.20.0**.
- L’exécutable généré s’appelle désormais `Mes Recettes, Mes Courses.exe`.
- MSIX Packaging Tool reprend ainsi automatiquement le bon nom dans `VisualElements`, sans correction manuelle du manifeste.

## Build 66 — retour au lancement normal

- Version produit : **1.6.19** ; version MSIX : **1.6.19.0**.
- Retour au lancement normal après installation, comme dans la version qui fonctionnait.
- Seule modification de capture : suppression du raccourci Inno Setup supplémentaire ; le MSIX garde une seule entrée.


## Build 65 — première tâche MSIX persistante

- Version produit : **1.6.18** ; version MSIX : **1.6.18.0**.
- Le mode `--msix-capture` reste ouvert jusqu’à sa fermeture manuelle. MSIX Packaging Tool peut donc le détecter dans « Manage First Launch ».


## Build 64 — détection MSIX sans réglages

- Version produit : **1.6.17** ; version MSIX : **1.6.17.0**.
- Le mode de capture `--msix-capture` permet à MSIX Packaging Tool de détecter l’application dans « Manage First Launch » sans enregistrer de préférence.


## Build 63 — capture sans préférences personnelles

- Version produit : **1.6.16** ; version MSIX : **1.6.16.0**.
- L’installateur Store ne lance plus automatiquement l’application après installation. Aucun `settings.json` personnel n’est ainsi capturé.
- Le premier lancement choisit la langue du système ; sur un Windows français, l’application démarre en français.


## Build 62 — une seule entrée du menu Démarrer

- Version produit : **1.6.15** ; version MSIX à renseigner : **1.6.15.0**.
- L’installateur utilisé pour la capture Store ne crée plus de raccourci. Le MSIX fournit automatiquement l’unique entrée de l’application.
- Cette suppression évite le doublon causé par le raccourci Inno Setup capturé sous `VFS\Programs` et l’extension `desktop7:Shortcut`.
- Recréer le package depuis le nouvel installateur et vérifier qu’il ne contient aucun fichier `.lnk` avant soumission.


## Build 61 — ressources Tcl/Tk dans l’exécutable

- Version produit : **1.6.14** ; version MSIX à renseigner : **1.6.14.0**.
- Copie explicite des ressources Tcl/Tk avec prise en charge des chemins virtuels zipfs de Tcl 9.
- Vérification du contenu de l’exécutable et test automatique de démarrage Tcl/Tk avant de valider la construction.
- L’exécutable est supprimé si ce contrôle échoue.
- Reconstruire le programme et l’installateur sur le PC, puis créer et tester le MSIX dans Hyper-V.
- Validation locale : tests de copie depuis un vrai zipfs Tcl 9, contrôles d’archives PyInstaller complètes/incomplètes/altérées, et rejet du véritable exécutable fourni dans le MSIX 1.6.13.0.
- La compilation et le lancement Windows restent à effectuer sur votre PC ; le script les contrôle automatiquement pour Tcl/Tk.

# Versions précédentes

## Build 60 — impression Windows directe

- Le bouton Imprimer ouvre la boîte d’impression classique Windows et envoie le PDF page par page au pilote sélectionné.
- Le lecteur PDF par défaut n’est utilisé qu’en solution de secours après une erreur explicite.
- Le rendu PDF utilise pypdfium2, inclus dans `requirements.txt` et dans la construction PyInstaller.
- Les quatre boutons d’impression (recette, liste de courses, planning et menu) utilisent le même contrôleur.
- Validation : 160 tests réussis, dont 18 tests d’impression. Le dialogue et le pilote Windows doivent encore être testés sur votre PC.
- Version produit : 1.6.12 ; build interne : 60.

- Produit : **Mes Recettes, Mes Courses**
- Version produit : **1.6.12**
- Build interne : **60**
- Schéma de données : **2**
- Plateforme : Windows

L'historique détaillé des versions est disponible dans `CHANGELOG.md`.

## Build 59 — noms de fichiers et petites fractions OCR

- Correction du motif de nettoyage Windows : les lettres (dont B) et chiffres ne sont plus remplacés à tort par un trait de soulignement. Les caractères interdits restent remplacés.
- Relecture des fractions diagonales par séparation des deux chiffres et de la barre. Deux cadrages doivent donner le même chiffre ; aucune règle propre à cette recette n'est utilisée.
- Une fraction relue est conservée dans le tableau et reportée dans la préparation sans modifier les autres mesures.
- Une lecture illisible, divergente ou expirée reste soumise aux avertissements existants.
- Validation : 142 tests réussis ; import réel des trois photos Barramundi et contrôle d'un PDF exporté. Résultats : 0,25 sachet de chapelure pour 2 personnes, 3 cuillères à soupe d'huile pour 2 personnes, 1/2 cuillère à soupe d'huile par personne dans la préparation.
- Lanceur main.pyw et installateurs alignés sur 1.6.11 / build 59.

## Build 58 — relecture OCR des tableaux et préparation

- Les tableaux d’ingrédients sont relus ligne par ligne à la résolution source (limitée à 2400 pixels), en excluant la colonne voisine.
- Fractions Unicode et fractions écrites 1/4 prises en charge ; % et autres lectures ambiguës restent vides avec un avertissement. Aucun remplacement automatique par 1.
- Les six cases de préparation sont relues comme blocs de texte après localisation de leur zone utile ; les lignes imprimées sont réunies en paragraphes.
- Une mesure perdue au premier passage et devenue un nombre au second est signalée à vérifier (cas ½ lu 2).
- Nettoyage des caractères parasites en début de titre, devant le sous-titre et après les noms.
- L’huile, le beurre et les ingrédients « selon votre goût » sont conservés. Les quantités numériques sont divisées une seule fois par les personnes de la photo.
- Une quantité absente s’affiche comme « Quantité non précisée » et son champ d’édition reste vide, au lieu de contenir le texte None.
- Les avertissements sont traduits en français, anglais, espagnol et allemand.
- main.pyw lance le même code corrigé. Versions du programme et des deux installateurs alignées sur 1.6.10 / build 58.

## Build 57 — compatibilité des quantités mobiles

- Les quantités laissées vides par l'application mobile (`null`) sont acceptées lors de l'import Windows.
- Elles sont conservées et affichées comme « Au goût » au lieu de bloquer toute la sauvegarde.
- La fiche recette, le mode cuisine, l'aperçu URL, l'export PDF et la recherche d'ingrédients ne plantent plus avec une quantité inconnue.
- Les valeurs réellement invalides (négatives, non numériques ou non finies) restent refusées.
- Ajout de tests de non-régression pour les sauvegardes partagées mobile/Windows.

## Build 56 — ingrédients et provenance nutritionnelle

290 références Ciqual 2025, 60 listes d'allergènes et 26 traductions corrigées.
740 estimations nutritionnelles restent non vérifiées. Bilan : `docs/history/AUDIT_INGREDIENTS_v56.md`.

## Build 55 — fenêtres ouvertes et molette locale

- Les textes statiques et paramétrés, onglets, menus, listes, tableaux et canevas déjà ouverts sont rafraîchis lors d'un changement de langue.
- Les couleurs et polices explicites des fenêtres secondaires suivent désormais le thème et le mode « Texte agrandi » sans fermer les formulaires.
- Toutes les zones défilables utilisent une liaison de molette locale ; aucune ne modifie plus la liaison globale des autres fenêtres.

## Build 54 — rafraîchissement des fiches ouvertes

- Les fiches « Voir une recette » reçoivent désormais une notification lors d'un changement de langue, de thème ou de taille de texte.
- La fiche peut reconstruire sa liste et son affichage sans être détruite ni perdre la recette sélectionnée.

## Build 53 — audit i18n et alertes d’accueil

- Le dernier texte d’alerte codé en dur est maintenant traduit dans les quatre langues.
- Ajout de contrôles d’audit pour l’alignement des catalogues et du lanceur de tests.

## Build 52 — largeur réelle du texte du journal

- La largeur des informations du journal est maintenant calculée sur la zone de contenu effectivement affichée, et non sur la largeur initiale de la photo.
- Le recalcul est déclenché après la mise en page et lors des redimensionnements du contenu.

## Build 51 — largeur complète du journal de cuisine

- Les cartes de l'onglet « J'ai cuisiné ça » s'étendent désormais sur toute la largeur disponible.
- Les informations, notes et commentaires recalculent leur largeur lorsque la fenêtre est redimensionnée.

## Build 50 — retour sur la fiche et journal plus lisible

- Après validation de « J'ai cuisiné ça », les dialogues sont rattachés à la fiche et « Voir une recette » revient au premier plan.
- Le même retour est appliqué depuis le mode cuisine lorsqu'il a été ouvert depuis la fiche.
- Les photos du journal sont agrandies et les notes/commentaires s'adaptent à la largeur de la fenêtre.

## Build 49 — onglet journal de cuisine dans la modification

- Un cinquième onglet « J'ai cuisiné ça » est disponible lors de la modification d'une recette existante.
- Il récapitule chaque cuisson enregistrée : date, nombre de personnes, note, commentaire et photo associée.
- Après fermeture du formulaire, la fenêtre « Voir une recette » est relevée et remise au premier plan.

## Build 48 — brouillon réservé aux plantages

- Une fermeture normale par « Enregistrer », « Annuler » ou la croix supprime le brouillon.
- L'auto-sauvegarde reste active pendant l'édition ; un brouillon ne subsiste donc qu'après un arrêt brutal ou un plantage.
- La récupération est proposée uniquement lorsqu'un brouillon issu d'une session interrompue existe.

## Build 47 — brouillon uniquement après modification

- L'état initial du formulaire est mémorisé à l'ouverture de « Modifier ».
- Si la recette est annulée ou enregistrée sans changement, aucun brouillon n'est conservé.
- Le message de récupération apparaît uniquement après une modification réelle.
- Les modifications existantes restent récupérables lors des ouvertures suivantes.

## Build 46 — récupération de brouillon à chaque modification

- Un brouillon est conservé après l'enregistrement d'une recette existante, même si aucun champ n'a été modifié.
- À la prochaine ouverture de « Modifier », la récupération du brouillon est proposée de nouveau.
- Le brouillon est mis à jour juste avant l'enregistrement pour ne jamais conserver une ancienne version des champs.
- Le comportement des nouvelles recettes reste inchangé : le brouillon est supprimé après création réussie.

## Build 45 — journal de cuisine visible et fermeture fiable

- La fiche recharge la recette après « J'ai cuisiné ça » et affiche immédiatement la dernière note, le commentaire, les étoiles et le nombre de personnes.
- La photo de la dernière cuisson apparaît dans la galerie de la fiche, y compris si la recette n'avait pas encore de photo.
- Le journal est rechargé depuis le disque avant son ouverture.
- La bibliothèque des recettes ne tente plus de rafraîchir un champ de recherche détruit pendant la fermeture d'une fiche.

## Build 44 — export groupé des QR multi-parties

- Un bouton permet d'enregistrer toutes les parties QR dans un dossier en une seule opération.
- Les fichiers sont nommés automatiquement `_1surN`, `_2surN`, etc., dans l'ordre de lecture.
- Une seule confirmation est demandée lorsque des fichiers existent déjà.
- Le lot est généré et vérifié avant remplacement, avec restauration des anciens fichiers en cas d'échec.

## Build 43 — décodage indépendant de chaque partie QR

- Chaque QR d'un même lot peut maintenant être réparé selon son propre encodage ZBar.
- Prise en charge des interprétations UTF-8, Latin-1, Windows-1252 et Shift-JIS.
- Les combinaisons sont validées exclusivement avec la somme de contrôle originale.
- Les lots réels Barramundi (3 QR) et Financiers (2 QR) sont reconstitués correctement avec les sorties réelles de ZBar.

## Build 42 — import des QR multi-parties accentués

- Correction des textes UTF-8 que certains lecteurs Windows renvoient sous une forme Latin-1 ou Windows-1252.
- La réparation n'est acceptée que si elle retrouve exactement la somme de contrôle inscrite dans les QR.
- Les véritables fragments altérés continuent donc d'être refusés.
- Le lot Barramundi fourni (3 parties, checksum `12phf2l`) a été décodé et reconstitué avec succès.

## Build 41 — suggestions d'ingrédients affichées pendant la frappe

- Le sélecteur de remplacement utilise désormais le même champ à suggestions que le formulaire d'une nouvelle recette.
- La liste alphabétique apparaît et se filtre immédiatement pendant la saisie, sans clic sur une flèche.
- La proposition initiale est sélectionnée au focus : la première lettre tapée la remplace directement.
- Navigation au clavier conservée avec Flèche bas, Entrée et Échap.

## Build 40 — recherche dans les remplacements d'ingrédients

- Le bouton de fermeture affiche désormais « Annuler » dans les quatre langues.
- Les listes de remplacement sont triées par ordre alphabétique, accents compris.
- Il est possible de taper dans chaque liste pour la filtrer immédiatement.
- La proposition la plus proche reste présélectionnée à l'ouverture.

## Build 39 — ouverture de la fenêtre des ingrédients inconnus

- Correction de l'appel à la hauteur d'écran qui empêchait l'ouverture de la fenêtre.
- Le lancement avec `main.pyw` reste pris en charge.
- Test de non-régression ajouté pour vérifier que la fenêtre est transmise à la fonction de mesure.

## Build 38 — résolution des ingrédients inconnus

- Une fenêtre unique s'ouvre à l'enregistrement lorsque des ingrédients sont inconnus.
- Chaque nom peut être créé ou remplacé par un ingrédient existant.
- Les propositions sont classées par proximité, variantes et pluriels compris.
- « Gousse d'ail » propose notamment « Ail » en premier.
- 80 tests automatisés réussis.

## Build 37 — OCR photo orienté, structuré et multi-colonnes

- Orientation EXIF appliquée avant OCR, complétée par la détection OSD de Tesseract.
- Boutons de rotation manuelle gauche/droite avec aperçu immédiat, sans modifier l'original.
- JPEG de smartphone réduit à 1600 px pour accélérer et stabiliser la reconnaissance.
- Tables d'ingrédients relues avec le mode de segmentation adapté aux lignes nom/quantité.
- Pages HelloFresh en grille découpées en 6 cases, lues dans l'ordre 1, 2, 3, 4, 5, 6.
- Titre, durée, portions, ingrédients et préparation préremplis automatiquement.
- Quantités totales de la photo converties une seule fois en quantités internes par personne.
- Corpus Barramundi validé : 10 ingrédients détectés pour 2 personnes.
- 75 tests automatisés réussis.
