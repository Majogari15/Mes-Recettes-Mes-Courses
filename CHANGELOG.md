# Build 77 — 1.6.30 (MSIX 1.6.30.0)

Import multilingue : unités, ingrédients, allergènes, rendement, catégories, repos et redirections. Voir RAPPORT_IMPORT_v77.md.

# Build 76 — 1.6.29 (MSIX 1.6.29.0)

Corrections d’import intégrées sur main e9a6c02 ; microdonnées et Tesseract portable préservés. Voir CHANGEMENTS_v76.md.

# Build 75 — 1.6.28

Import : unités, ingrédients balisés manquants, variantes orthographiques des allergènes, rendement en pièces, repos, catégories et notes. Détails et validation dans CHANGEMENTS_v75.txt.

# Build 66 — 1.6.19

Retour au lancement normal de l’application pendant la capture MSIX ; suppression conservée du seul raccourci supplémentaire.

# Build 65 — 1.6.18

Le mode de capture MSIX reste ouvert afin d’être détecté par la page Manage First Launch.

# Build 64 — 1.6.17

Ajout du mode de détection MSIX sans chargement ni écriture de données utilisateur.

# Build 63 — 1.6.16

Le lancement automatique après capture est supprimé pour éviter d’embarquer la langue ou des réglages de la machine de fabrication.

# Build 62 — 1.6.15

Suppression du raccourci Inno Setup dans l’installateur de capture Store afin que le menu Démarrer ne contienne qu’une seule entrée MSIX.

# Build 61 — 1.6.14

Correction de la collecte Tcl/Tk (y compris zipfs) et contrôle bloquant des ressources et du démarrage de l’interface après construction du .exe.

## Build 60 — impression Windows directe

- Le bouton Imprimer ouvre la boîte d’impression classique Windows et envoie le PDF page par page au pilote sélectionné.
- Le lecteur PDF par défaut n’est utilisé qu’en solution de secours après une erreur explicite.
- Le rendu PDF utilise pypdfium2, inclus dans `requirements.txt` et dans la construction PyInstaller.
- Les quatre boutons d’impression (recette, liste de courses, planning et menu) utilisent le même contrôleur.
- Validation : 160 tests réussis, dont 18 tests d’impression. Le dialogue et le pilote Windows doivent encore être testés sur votre PC.
- Version produit : 1.6.12 ; build interne : 60.

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

- Les quantités `null` produites par l'export mobile sont maintenant acceptées et préservées à l'import Windows.
- Les quantités inconnues sont affichées comme « Au goût » dans les fiches, le mode cuisine, l'aperçu d'import URL, les PDF et la recherche d'ingrédients.
- Les calculs nutritionnels ignorent proprement les quantités inconnues et conservent l'indication d'estimation partielle.
- Les valeurs négatives, non numériques ou non finies restent rejetées.
- Ajout d'une couverture de tests dédiée à ce format partagé.

## Build 56 — audit des ingrédients

- 1 030 ingrédients contrôlés pour la couverture et la structure de leurs données.
- 290 fiches nutritionnelles rapprochées de Ciqual 2025, avec référence et état de l'aliment conservés.
- 60 listes d'allergènes et 26 traductions corrigées. La clé historique Lactose s'affiche désormais comme lait, sans modifier les anciennes recettes.
- Recherche des données compatible avec les variantes d'accents, de ligatures et d'apostrophes, sans rapprochement flou.
- Une fiche nutritionnelle partielle n'est plus comptée comme complète en remplaçant implicitement ses champs manquants par zéro.
- 740 anciennes estimations nutritionnelles restent non vérifiées. Voir `docs/history/AUDIT_INGREDIENTS_v56.md` et son journal JSON.

## Build 55 — fenêtres ouvertes et molette locale

- Rafraîchissement non destructif des widgets, onglets, menus, tableaux, listes et textes de canevas lors d'un changement de langue.
- Mise à jour récursive des couleurs et des polices déjà affichées après changement de thème ou de taille de texte.
- Remplacement des sept couples `bind_all/unbind_all` de molette par des bindtags locaux indépendants.

## Build 54 — rafraîchissement des fiches ouvertes

- Ajout du rafraîchissement ciblé des fenêtres « Voir une recette » après changement d'apparence.
- La sélection de recette est conservée pendant ce rafraîchissement.

## Build 53 — audit i18n et alertes d’accueil

- Traduction du message affiché lorsque l’accueil ne contient aucune alerte.
- Ajout de tests de cohérence des quatre catalogues de langue et du lanceur Windows.

## Build 52 — largeur réelle du texte du journal

- Correction du calcul de largeur qui pouvait encore conserver la largeur initiale de la colonne photo.
- Les notes et commentaires utilisent désormais la largeur réelle de la zone intérieure du journal.

## Build 51 — largeur complète du journal de cuisine

- Correction de la largeur du cadre intérieur : les informations du journal ne sont plus limitées à la largeur de la photo.
- Les textes s'adaptent à la fenêtre et à ses redimensionnements.

## Build 50 — retour sur la fiche et journal plus lisible

- Les fenêtres de confirmation de « J'ai cuisiné ça » utilisent désormais la fiche comme parent, puis celle-ci est remise au premier plan.
- Le mode cuisine restitue également la fiche d'origine lorsqu'il a été lancé depuis celle-ci.
- Agrandissement des photos et adaptation dynamique de la largeur des textes dans l'onglet du journal.

## Build 49 — onglet journal de cuisine dans la modification

- Ajout d'un onglet « J'ai cuisiné ça » dans « Modifier une recette » pour consulter l'historique des cuissons, notes, étoiles, personnes et photos.
- La fiche « Voir une recette » revient au premier plan après la fermeture du formulaire de modification.

## Build 48 — brouillon réservé aux plantages

- Suppression du brouillon lors de toute fermeture normale du formulaire.
- Le bouton « Enregistrer », « Annuler » et la croix ferment désormais proprement la session et nettoient son brouillon.
- L'auto-sauvegarde périodique continue de protéger les modifications en cas de plantage ou d'arrêt brutal.

## Build 47 — brouillon uniquement après modification

- Correction du comportement précédent qui créait un brouillon après une simple ouverture puis annulation.
- Une comparaison stable avec l'état initial supprime automatiquement tout brouillon inchangé.
- La récupération reste proposée après une modification réelle, y compris si l'utilisateur enregistre ensuite.

## Build 46 — récupération de brouillon à chaque modification

- Les brouillons des recettes existantes ne sont plus supprimés après un clic sur « Enregistrer ».
- Ils sont enregistrés une dernière fois avec les valeurs actuelles, y compris lorsque la session n'a rien changé.
- La récupération est donc proposée à chaque nouvelle ouverture de la modification, jusqu'à ce que l'utilisateur choisisse de supprimer le brouillon.
- Les brouillons de nouvelles recettes sont toujours nettoyés après une création réussie.

## Build 45 — journal de cuisine visible et fermeture fiable

- Les informations saisies dans « J'ai cuisiné ça » sont maintenant rechargées dans la fiche immédiatement après l'enregistrement.
- La dernière note, le commentaire, la note en étoiles, le nombre de personnes et la date sont visibles dans le panneau « Description et notes ».
- La photo de cuisson la plus récente est affichée dans la galerie sans mélanger les anciennes entrées du journal.
- Le journal utilise les données fraîchement enregistrées, même après une cuisson effectuée depuis une autre fenêtre.
- Correction de l'erreur Tkinter `invalid command name ...entry` lorsque la bibliothèque de recettes a été fermée avant la fiche.

## Build 44 — export groupé des QR multi-parties

- Ajout du bouton « Enregistrer les N QR codes » quand une recette produit plusieurs parties.
- Sélection unique du dossier et noms numérotés automatiquement dans l'ordre de lecture.
- Confirmation d'écrasement unique pour tout le lot et message final unique.
- Génération, vérification PNG et installation transactionnelle de l'ensemble des fichiers.
- Le bouton d'enregistrement de la partie affichée reste disponible.

## Build 43 — décodage indépendant de chaque partie QR

- Correction du cas où ZBar interprète différemment plusieurs images appartenant au même lot.
- Réparation partie par partie des mojibakes Latin-1, Windows-1252 et Shift-JIS, y compris les caractères japonais demi-largeur observés.
- Sélection de la reconstruction uniquement lorsque le checksum mobile correspond exactement.
- Validation avec les sorties ZBar réelles des lots Barramundi et Financiers fournis.

## Build 42 — import des QR multi-parties accentués

- Correction de l'incompatibilité d'encodage entre certains décodages ZBar sous Windows et les QR UTF-8 produits par l'application mobile.
- Réparation réversible Latin-1/Windows-1252 contrôlée par la somme de contrôle du lot.
- Aucun affaiblissement de l'intégrité : une altération réelle reste bloquante.
- Ajout de tests couvrant accents, apostrophes typographiques, descriptions longues, notes et corruption réelle.

## Build 41 — suggestions d'ingrédients affichées pendant la frappe

- Remplacement du Combobox du build 40 par le même champ à suggestions que dans la création d'une recette.
- Affichage et filtrage automatiques de la liste dès les premières lettres, sans action sur une flèche.
- Tri alphabétique conservé et navigation au clavier ajoutée.
- La proposition initiale peut être remplacée directement en commençant à taper.

## Build 40 — recherche dans les remplacements d'ingrédients

- Ajout de la traduction manquante du bouton Annuler en français, anglais, espagnol et allemand.
- Les ingrédients proposés en remplacement sont maintenant triés alphabétiquement.
- Les menus de remplacement acceptent la saisie et filtrent la liste au fil des lettres tapées.
- La proposition la plus proche reste sélectionnée par défaut.

## Build 39 — correction de la fenêtre des ingrédients inconnus

- Correction de l'erreur `get_usable_screen_height() missing 1 required positional argument: 'widget'`.
- La fenêtre de création ou de remplacement des ingrédients inconnus peut maintenant s'ouvrir lors de l'enregistrement d'une recette.
- Ajout d'un test de non-régression ciblé.

## Build 36 — ouverture immédiate de l’import photo

- Correction du crash `name 'COLOR_SUCCESS' is not defined` qui interrompait la construction de la fenêtre et la laissait vide.
- La couleur d’état positif utilise maintenant la couleur verte réellement définie dans la palette.
- Le contrôle Tesseract ne démarre qu’après la création de tous les boutons et zones de la fenêtre.
- La détection de Tesseract est exécutée en arrière-plan : l’ouverture de la fenêtre n’attend plus la recherche de l’exécutable et des langues OCR.
- Le bouton d’extraction reste désactivé avec un message clair pendant la vérification.
- La progression et le résultat de l’OCR transitent par une file contrôlée par Tkinter ; le thread OCR ne manipule plus directement les widgets.

## Build 35 — fiabilisation des données et opérations longues

- Le journal « J’ai cuisiné ça » fonctionne depuis la fiche et le mode cuisine ; compteur, date, commentaire, photo, étoiles et personnes sont enregistrés ensemble.
- La sauvegarde automatique couvre maintenant garde-manger, menus, listes, réglages et photos même sans recette.
- Un JSON utilisateur illisible est copié dans un fichier horodaté, signalé et protégé contre l’écrasement ; la dernière sauvegarde valide peut être restaurée.
- Suppression, restauration et corbeille utilisent des transactions avec retour à l’état précédent en cas d’échec.
- Les nouvelles photos sont annulées si l’enregistrement échoue et les anciennes ne sont supprimées qu’après réussite.
- Les restaurations volumineuses utilisent des fichiers temporaires en flux au lieu de charger toutes les images en mémoire.
- Sauvegarde, export et restauration complets s’exécutent hors de l’interface avec progression et annulation.
- Le livre PDF et le bouton Fermer du diagnostic utilisent désormais des traductions valides.
- Le lanceur Windows exécute toute la suite `test_*.py`.

## Build 34 — maximisation des fenêtres et aperçu des quantités importées

- Le bouton natif de maximisation peut désormais utiliser toute la zone de travail Windows, sans marges imposées par l'application.
- L'ajustement automatique ne redimensionne plus une fenêtre déjà maximisée ou en plein écran.
- L'aperçu d'un import Internet affiche les quantités recalculées pour le nombre de personnes détecté.
- Le formulaire précise clairement que les quantités éditées sont stockées pour une personne et multipliées automatiquement lors de l'affichage de la recette.

## Build 33 — correction « J'ai cuisiné ça »

- Correction du crash `'OneRecipeWindow' object has no attribute '_fmt'`.
- Le formatage du nombre de personnes est maintenant effectué localement
  avant l'ouverture du journal de cuisine.
- Aucun changement fonctionnel sur le journal lui-même : note, commentaire,
  photo, étoiles et nombre de personnes restent conservés.

## Build 32 — journal de cuisine et brouillons après restauration

- Journal de cuisine : Note et Commentaire sont désormais deux champs distincts.
- Le nombre de personnes de la cuisson est enregistré dans chaque entrée.
- Date/heure complète, note, commentaire, appréciation et photo sont conservés.
- Le Journal de cuisine affiche explicitement Note, Commentaire et personnes.
- Les anciens journaux sans champ Commentaire restent compatibles.
- Suppression automatique du brouillon lié lorsqu'une recette part à la corbeille.
- Nettoyage défensif du brouillon lors de la restauration d'une recette créée avec une ancienne version.
- Suppression du brouillon également lors d'une suppression définitive ou du vidage de la corbeille.

## Build 31 — OCR Tesseract et import multi-photos

- Détection précise de pytesseract, de `tesseract.exe`, de sa version et des langues installées.
- Sous Windows, recherche automatique dans les emplacements Tesseract courants même si le PATH n'est pas configuré.
- L'import photo indique clairement si la langue OCR active (fra/eng/spa/deu) est disponible.
- Diagnostic enrichi avec l'état réel de Tesseract et du paquet linguistique.
- Import photo multi-images rendu explicite : ajout de plusieurs lots, liste ordonnée, montée/descente, suppression.
- OCR exécuté sur toutes les photos dans l'ordre choisi, puis texte assemblé en une seule recette.
- Toutes les photos sélectionnées sont transférées au formulaire de recette final.

## Build 30 — remplacement de windnd par TkinterDnD2

- Suppression complète du backend `windnd`, qui continuait à provoquer un
  crash natif de Tcl/Tk lors du dépôt de certains fichiers sur Windows.
- Nouveau backend `tkinterdnd2` / TkDnD2 utilisant le mécanisme OLE2 natif.
- La racine de l'application devient automatiquement `TkinterDnD.Tk`
  lorsque le composant est disponible.
- L'onglet Photos est enregistré comme cible `DND_FILES`.
- Les chemins déposés sont décodés avec `tk.splitlist`, y compris espaces
  et caractères accentués.
- Retour explicite de l'action `COPY` attendu par TkDnD2.
- `windnd` retiré de `requirements.txt` et remplacé par `tkinterdnd2==0.6.3`.
- Ajout du hook PyInstaller `hook-tkinterdnd2.py`.
- `Construire_le_exe.bat` utilise désormais `--additional-hooks-dir=.`.

## Build 29 — correction du crash au glisser-déposer

- Un seul hook windnd est maintenant installé sur la fenêtre Ajouter/Modifier une recette.
- Suppression du hook simultané sur plusieurs widgets enfants.
- Suppression du mode de remplacement forcé du WindowProc.
- Copie immédiate de la liste de fichiers reçue avant traitement.
- Traitement UI différé avec `after_idle` et vérification que la fenêtre existe toujours.
- Ctrl+V et le bouton Ajouter une photo restent inchangés.

## Build 28 — windnd inclus explicitement dans l'EXE

- `windnd==1.0.7` reste figé dans `requirements.txt`.
- Le script `Construire_le_exe.bat` demande maintenant explicitement à
  PyInstaller `--hidden-import=windnd` et `--collect-all=windnd`.
- Ajout d'un contrôle après compilation pour confirmer la création de
  `dist\MesRecettes.exe`.
- Le glisser-déposer ne dépend donc plus d'une détection implicite de PyInstaller.

## Build 27 — Photos : collage et glisser-déposer Windows

- Ctrl+V accepte désormais une vraie image du presse-papiers ET un ou plusieurs
  fichiers image copiés depuis l'Explorateur Windows.
- Le glisser-déposer windnd est accroché à la fenêtre Ajouter/Modifier une recette
  ainsi qu'aux widgets de la galerie Photos pour une meilleure fiabilité.
- Compatibilité avec les variantes de windnd avec/sans paramètre `force`.
- Décodage plus robuste des chemins Windows contenant des accents.
- Suppression des doublons lorsqu'une même photo est déposée/collée plusieurs fois.
- Message visible si windnd n'est pas disponible au lieu d'un échec silencieux.
- Ajout de messages de confirmation non bloquants.

## Build 26 — import URL : noms d'ingrédients normalisés

- Œufs/Oeufs et variantes accentuées sont reconnus comme le même ingrédient.
- Ajout des variantes « c à s » / « c. à s » pour cuillère à soupe.
- Nettoyage des préfixes « sachet de » et « poignée de » lors des imports Web.
- Correction ciblée du cas 750g signalé au test manuel 21.

## Build 25 — import URL : accents et entités HTML

- Correction des descriptions JSON-LD fournies sous forme d'une chaîne unique.
- Décodage robuste des entités HTML (accents, cédille, etc.), y compris doublement encodées.
- Normalisation des espaces insécables.
- Test de régression ajouté avec le cas 750g.

## Build 24 — corrections issues des tests manuels

- Planning : noms des jours recalculés sur les largeurs réelles des colonnes.
- Menus : ajout d'un bouton pour envoyer la liste du menu vers la liste de courses normale.
- Autocomplétion : une proposition unique reste entièrement visible.
- Vérification appliquée aux cinq systèmes d'autocomplétion utilisant ce mécanisme.

# Changelog — Mes Recettes, Mes Courses

## 1.5.1 / build 38

- Dialogue groupé de résolution des ingrédients inconnus avant enregistrement.
- Choix individuel entre création et remplacement par un ingrédient existant.
- Suggestions classées par similarité, inclusion de mots et variante singulier/pluriel.
- Mise à jour immédiate de la liste générale après création.
- Traductions françaises, anglaises, espagnoles et allemandes.
- Suite portée à 80 tests.

## 1.5.0 / build 37

- Import photo : orientation EXIF, détection automatique Tesseract OSD et rotation manuelle.
- Redimensionnement OCR des JPEG à 1600 px, sans altérer les fichiers originaux.
- Second passage spécialisé pour les tables d'ingrédients.
- Découpage OCR des fiches de préparation en grille 3 colonnes × 2 rangées.
- Préremplissage structuré du titre, de la durée, des portions, des ingrédients et des étapes.
- Quantités OCR stockées par personne après une seule division par les portions détectées.
- Cas Barramundi ajouté à la non-régression ; suite portée à 75 tests.

## 1.4.0 / build 23

- Validation stricte des nombres finis (NaN/Infinity refusés).
- Validation plus profonde des recettes et sauvegardes.
- Références stables par ID pour planning, menus, récents, recette du jour et sélection de courses.
- Photos du journal de cuisine incluses dans maintenance, duplication, suppression et sauvegardes.
- Import URL/OCR : images temporaires et callbacks sûrs après fermeture.
- Restauration complète transactionnelle avec rollback et vrai mode « Tout remplacer ».
- Limites distinctes pour sauvegarde partagée mobile et sauvegarde complète Windows.
- Protection renforcée des chemins d'images.
- Calculs et unités centralisés / fiabilisés.
- Parseur Internet enrichi (fractions, plages, multiplications, unités abrégées, « au goût »).
- Fenêtres adaptées aux petits écrans, texte agrandi et multi-écrans Windows.
- Autocomplétion contrainte à la zone visible.
- Planning : en-tête horizontal synchronisé.
- Menus et gestion ingrédients compactés sur petits écrans.
- Traductions externalisées dans i18n_desktop.json.
- Code mort supprimé et main.pyw réduit à un lanceur.
- Dépendances figées dans requirements.txt.
- Installateur Store séparé pour capture MSIX.
- Suite de tests de régression ajoutée.

## Historique antérieur

# Version 22 — Audit correctif complet

- Calcul du garde-manger corrigé selon quantité/personne × nombre de personnes.
- Second ajout d’une même recette aux courses = remplacement, pas cumul.
- Validation stricte des nombres de personnes positifs.
- Fusion g/kg et ml/cl/L dans les listes de courses.
- Coûts et nutrition compatibles kg/L/ml.
- Planning et menus reprennent le nombre de personnes par défaut de la recette.
- « Que puis-je cuisiner ? » tient compte des quantités réellement disponibles.
- Unités Kilo/Litre/ml fiabilisées dans l’éditeur.
- Détection des imports Internet anciens potentiellement concernés par l’ancienne base de quantité.
- Déduplication de la corbeille et des consultations récentes lors des restaurations fusionnées.
- PDF : titres, sommaire, allergènes, ingrédients et paragraphes longs avec retour à la ligne.
- Protection renforcée des petites résolutions et du mode Texte agrandi.
- Traductions de l’accueil complétées en EN/ES/DE.
- Journalisation des erreurs Tkinter dans error.log.

# Version 21 — Sélection complète « Que puis-je cuisiner ? »

- Le nom de la recette fait maintenant partie de la même zone sélectionnable que ses ingrédients manquants.
- Le clic, le double-clic et le bouton « Consulter la recette sélectionnée » fonctionnent sur toute la recette.
- Le surlignage couvre toute la recette, y compris lorsque le texte revient sur plusieurs lignes.

# Version 20 — Checklist et Que puis-je cuisiner

- Liste de courses à cocher : hauteur demandée augmentée de 50 % (600 -> 900),
  toujours plafonnée à la zone de travail Windows sur les petits écrans.
- « Que puis-je cuisiner ? » : largeur augmentée de 50 % (640 -> 960).
- Les résultats partiels utilisent maintenant un affichage avec retour
  automatique à la ligne.
- Les longues listes d'ingrédients manquants restent donc entièrement visibles.
- Double-clic et bouton « Consulter la recette sélectionnée » conservés.

# Version 19 - Lisibilité, suggestions et PDF

- Liste de courses totale : affichage automatique sur 2 colonnes sur grand écran, 1 colonne sur écran étroit.
- « Que puis-je cuisiner ? » : affiche aussi les recettes partielles avec peu d'ingrédients manquants, triées par proximité.
- Export PDF / impression / livre de recettes : une étape ou un paragraphe n'est plus coupé entre deux pages lorsqu'il peut tenir sur une page.
- Autocomplétion : les listes de suggestions restent sous le champ de saisie au lieu d'être recentrées par le système global de cadrage.

# Version 18 — Import URL et Mes courses

- « Toutes les recettes — liste de courses » : le nombre de personnes,
  sa case et les boutons sont maintenant regroupés côte à côte à gauche.
- Import depuis un lien : correction du calcul des quantités.
- Les quantités Schema.org sont désormais converties du total de la recette
  vers le format interne par personne.
- Ajout de la reconnaissance de kg/kilo, L/litre, ml et variantes.
- Reconnaissance des écritures compactes comme 750g, 1kg ou 20cl.
- Correction testée sur le cas du cassoulet Marmiton pour 8 personnes.

# Version 17 — Fenêtres et exports améliorés

- « Voir une recette » : largeur demandée +50 %, toujours limitée à la zone visible de l'écran.
- Export PDF d'une recette : nettoyage automatique du nom de fichier proposé pour Windows.
- « Mes recettes » : hauteur adaptée à toute la zone de travail disponible.
- « Mes courses » : largeur +50 % et lignes réorganisées pour garder nombre de personnes et boutons visibles sur les petits écrans.
- Planning : largeur +50 %.
- Garde-manger : hauteur adaptée à l'écran.
- Import depuis une photo : barre de progression masquée au repos.
- Historique des semaines : largeur +50 % et liste de semaines +35 %.
- Comparaison 2/3 recettes : largeur +30 % et hauteur adaptée à l'écran.
- Accueil : « Comparer deux ou trois recettes ».
- Recherche par ingrédient : largeur doublée.
- Export du livre de recettes : largeur et hauteur +50 %.
- Toutes les dimensions restent plafonnées par la zone de travail Windows afin qu'aucune fenêtre ne sorte de l'écran ou passe sous la barre des tâches.

# Version 16 — Accueil large et outils regroupés

- Correction de la régression v15 qui pouvait rétrécir l'accueil après son premier affichage.
- L'accueil utilise désormais environ 97 % de la largeur réellement disponible de l'écran.
- Le système global de recadrage conserve les dimensions explicitement demandées par les fenêtres.
- Les boutons de l'accueil sont répartis en quatre groupes lisibles :
  - Créer et importer
  - Recettes et ingrédients
  - Organisation
  - Données et outils
- Boutons secondaires disposés verticalement dans chaque groupe, avec davantage d'espacement.
- Titres des nouveaux groupes traduits en français, anglais, espagnol et allemand.
- Le bouton Faire un don reste bien visible en haut de l'accueil.

# Version 15 — Correction globale barre des tâches

- Correction du calcul de hauteur des fenêtres Tkinter sous Windows.
- Réserve explicite pour la barre de titre et les bordures Windows.
- Marge de sécurité supplémentaire au-dessus de la barre des tâches.
- Seconde vérification automatique après création réelle de chaque fenêtre.
- Garde-fou appliqué à la fenêtre principale et à toutes les fenêtres secondaires.
- Les fenêtres qui demandent toute la hauteur de l'écran utilisent désormais
  une hauteur CLIENT plus petite afin que les boutons du bas restent entièrement visibles.
- Fenêtre Ajouter/Modifier une recette conservée large mais avec hauteur sûre.

# Version 14 — Recalage global des fenêtres

- Accueil : largeur demandée augmentée de 50 % (adaptée automatiquement à l'écran).
- Clause de responsabilité : largeur +20 % et hauteur adaptée à toute la zone de travail Windows.
- Import depuis un lien : largeur +50 %, hauteur adaptée à l'écran, aperçu photo plus grand.
- Ajouter/Modifier une recette : largeur +25 %, hauteur adaptée à l'écran.
- Toutes les fenêtres Toplevel sont contrôlées à leur première ouverture : elles sont agrandies si leur contenu le nécessite, puis limitées à la zone visible hors barre des tâches.
- Toutes les anciennes géométries fixes principales sont maintenant contraintes par la zone de travail.
- Le mode cuisine de secours n'utilise plus la hauteur physique incluant la barre des tâches.

# Version 13 — Ajustements d'affichage

- Import URL : barre de progression invisible au repos, visible uniquement pendant la récupération.
- Clause de responsabilité nettement plus grande au premier lancement.
- Page d'accueil plus large dès le premier affichage.
- Fenêtre d'import URL agrandie en hauteur et largeur.
- Photo affichée dans l'aperçu avant import lorsqu'elle est disponible.
- Fenêtre Ajouter/Modifier une recette limitée à la zone visible de Windows.
- Grandes fenêtres automatiquement adaptées à la zone de travail pour éviter les boutons derrière la barre des tâches.

# Version 12 — Audit final

- Audit final de régression et de robustesse après les Lots 1 à 8.
- Restauration complète validée avant toute suppression locale.
- Sauvegardes ZIP complètes et partagées écrites atomiquement.
- Écritures JSON principales rendues atomiques.
- Suppression de l’ancien restaurateur ZIP utilisant extractall().
- Suppression du second système de sauvegarde automatique redondant.
- Protection contre les archives ZIP anormalement volumineuses/corrompues.
- Import URL : description alignée sur la limite actuelle de 12 000 caractères.
- Maintenance reliée au vrai dossier des sauvegardes automatiques.
- Nettoyage des fichiers d’état utilisateur présents par erreur dans le projet source.
- Version Inno Setup portée à 1.3.0.

# Version 11 — Lot 8 Accessibilité, langues et finition

- Prise en charge DPI Windows améliorée (125 %, 150 %, 200 % et écrans haute définition).
- Raccourcis globaux : Ctrl+N, Ctrl+K, Ctrl+Maj+L, Ctrl+Maj+M et F1.
- Navigation clavier renforcée dans la bibliothèque de recettes.
- Focus et lisibilité des tableaux améliorés.
- Correction du rafraîchissement thème / texte agrandi et d’un commentaire/docstring endommagé.
- Traductions FR/EN/ES/DE complétées pour la bibliothèque moderne et la maintenance.
- Correction d’une dépendance pathlib manquante introduite au Lot 7.
- Audit automatique des traductions inclus.

# Version 10 — Lot 7 Robustesse et performances

- Sauvegardes automatiques de sécurité avec rotation (7 archives).
- Vérification d’intégrité des recettes et photos.
- Détection des photos manquantes/orphelines et IDs de recettes dupliqués.
- Écritures JSON atomiques disponibles pour les opérations sensibles.
- Infrastructure générique pour exécuter les tâches longues sans bloquer l’interface.
- Fenêtre Maintenance et intégrité.
- Préparation de barres de progression pour OCR/import/export/restauration.
- Conservation de toutes les améliorations UI et compatibilités précédentes.

# Version 9 — Lot 6 UI/UX

- Harmonisation globale des espacements et contrôles.
- Raccourci Échap sur les fenêtres secondaires quand cela est sûr.
- Treeview plus lisibles et contrôles légèrement plus grands.
- Notifications non bloquantes pour plusieurs opérations réussies.
- Helpers de tooltips et de menus secondaires.
- Rafraîchissement plus cohérent des fenêtres ouvertes lors des changements d’apparence.
- Conservation du bouton Faire un don très visible sur l’accueil.

## Version interne 8 — Lot 5 historique, statistiques et confort Windows
- Journal de cuisine enrichi avec une note par cuisson et moyenne du journal.
- Comparaison étendue jusqu’à trois recettes.
- Export des statistiques en CSV et temps total moyen.
- Collage direct d’images dans l’onglet Photos avec Ctrl+V.
- Raccourci Ctrl+S dans le formulaire de recette.


## Version interne 7 — Lot 4 garde-manger et courses
- Tableau de bord du garde-manger avec statuts, filtres, recherche et tris.
- Ajout direct des stocks faibles à la liste de courses.
- Gestion améliorée des listes de courses enregistrées : renommer et dupliquer.

# Version 6 — Lot 3 bibliothèque moderne

Voir `docs/history/LOT3_AMELIORATIONS_WINDOWS.md`.

# Mes Recettes, Mes Courses — Windows APP_VERSION 5

## Lot 2 — garde-manger, imports et statistiques

Cette version conserve la refonte UI, les sauvegardes/QR compatibles mobile et tout le Lot 1.

### Garde-manger et anti-gaspillage
- Date de consommation/expiration optionnelle par produit (`JJ/MM/AAAA` ou `AAAA-MM-JJ`).
- Signalement visuel des produits expirés, expirant aujourd'hui ou dans les 5 jours.
- Alerte correspondante sur la page d'accueil.
- Nouvelle fenêtre « À cuisiner bientôt » qui classe les recettes utilisant les produits proches de l'expiration et indique le nombre d'ingrédients absents.
- Les anciens fichiers `pantry.json` sans date restent compatibles.

### Import depuis un lien
- La récupération réseau s'exécute hors du thread graphique pour éviter de figer l'interface.
- Aperçu avant création : nom, personnes, temps, ingrédients détectés et extrait de préparation.
- L'utilisateur confirme explicitement avant d'ouvrir le formulaire prérempli.

### Import OCR depuis photo
- Sélection de plusieurs photos/pages en une seule fois.
- OCR exécuté hors du thread graphique avec progression page par page.
- Texte des pages regroupé dans l'ordre choisi, modifiable avant création.
- Toutes les photos sélectionnées sont attachées à la recette.
- La limite de description du formulaire passe de 2 056 à 12 000 caractères pour mieux accueillir les recettes longues/multipages.

### Statistiques
- Fenêtre élargie pour mieux exploiter l'écran du PC.
- Nouveau tableau de bord synthétique en haut : nombre de recettes, cuissons de l'année, cuissons totales, note moyenne et recettes jamais cuisinées.
- Les statistiques détaillées, histogramme mensuel et calendrier d'activité existants sont conservés.

### Vérifications effectuées
- `main.py` et `main.pyw` identiques.
- Compilation Python réussie pour les deux fichiers.
- Test graphique sous affichage virtuel : accueil, garde-manger, statistiques, import URL et import photo.
- Test du parseur de dates de garde-manger et compatibilité des anciennes entrées sans date.

L'application mobile n'a pas été modifiée dans ce lot.
# Build 67 — 1.6.20

Nom du fichier exécutable aligné sur « Mes Recettes, Mes Courses » pour éviter que MSIX Packaging Tool génère `DisplayName="MesRecettes"`.
