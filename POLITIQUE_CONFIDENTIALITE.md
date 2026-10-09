# Politique de confidentialité — Mes Recettes, Mes Courses (Windows)

*Dernière mise à jour : 4 octobre 2026 — English version below.*

Cette politique concerne l'application **Windows** (installateur et
Microsoft Store). L'application mobile a sa propre politique, sur le site
de l'application mobile.

## En résumé

Toutes vos données restent sur votre ordinateur. L'application n'a ni
compte, ni serveur, ni publicité, ni mesure d'audience. Elle ne se
connecte à Internet que lorsque vous utilisez vous-même une fonction qui
en a besoin (import d'une recette par lien, recherche d'un code-barres,
recherche web, bouton de don).

## Quelles données sont stockées, et où

Vos recettes, photos, garde-manger, listes de courses, planning, menus,
prix, réglages et sauvegardes automatiques sont enregistrés **uniquement
dans un dossier de votre ordinateur** :

- à côté de l'application si ce dossier est accessible en écriture ;
- sinon (notamment pour la version Microsoft Store) dans
  `%LOCALAPPDATA%\MesRecettesMesCourses`.

L'emplacement exact est affiché dans l'écran **Diagnostic**. Les réglages
(`settings.json`) contiennent la langue, le thème, la taille du texte,
l'acceptation de la clause de responsabilité, l'ordre des rayons et du
garde-manger, la recette du jour, les codes-barres déjà associés à un
ingrédient et, si vous l'avez choisi, le dossier de sauvegarde cloud. Un
fichier `error.log` peut y enregistrer des messages techniques d'erreur.

Personne d'autre que vous — ni le développeur, ni un tiers — n'a accès à
ces données. Supprimer ce dossier efface définitivement vos données, sauf
si vous avez fait une sauvegarde.

## Sauvegarde cloud (optionnelle)

Si vous choisissez un **dossier de sauvegarde synchronisé** (OneDrive,
Google Drive, Dropbox…) dans l'écran Importer / Exporter les données,
l'application y dépose une copie de vos sauvegardes. C'est le logiciel de
synchronisation de ce service, installé sur votre ordinateur, qui les
envoie ensuite en ligne, selon sa propre politique de confidentialité.
L'application ne communique jamais directement avec ce service.

## Connexions à Internet

Elles ont toutes lieu **uniquement à votre initiative** :

- **Import d'une recette depuis un lien** : l'application télécharge la
  page de la recette (et sa photo) **directement depuis le site** que vous
  indiquez. Si cette page ne contient pas de recette lisible, l'adresse de
  la page est transmise en dernier recours au service **Jina AI Reader**
  (r.jina.ai), qui renvoie une version texte de la page. Seule cette
  adresse est transmise, jamais vos recettes ni vos données.
- **Recherche d'un code-barres** (garde-manger) : le code-barres est lu
  **sur votre ordinateur** à partir d'une photo que vous choisissez ; seul
  le numéro est envoyé à **Open Food Facts** (world.openfoodfacts.org) pour
  retrouver le nom du produit. Les associations code-barres → ingrédient
  que vous confirmez sont mémorisées dans vos réglages.
- **Recherche d'une recette sur Internet** : ouvre dans votre navigateur
  une recherche **Google** avec les mots que vous saisissez (et des noms de
  sites de recettes ajoutés automatiquement). L'application ne lit pas les
  résultats.
- **Bouton « Faire un don »** : ouvre la page
  https://buymeacoffee.com/majogari dans votre navigateur.
- **Politique de confidentialité** : le bouton correspondant ouvre cette
  page dans votre navigateur.

Ces services ne sont pas exploités par le développeur et appliquent leurs
propres règles ; ils voient, comme pour toute requête sur Internet, votre
adresse IP.

## Ce qui reste entièrement sur votre ordinateur

- **Lecture du texte d'une photo** (import de recette, date de péremption) :
  le moteur Tesseract et ses fichiers de langue sont inclus dans
  l'application ; aucune photo ni aucun texte n'est envoyé.
- **Presse-papiers** : l'application le lit quand vous cliquez sur
  « Coller le lien », et aussi **lorsque vous revenez dans l'application**,
  afin de vous proposer d'importer un lien de recette que vous venez de
  copier. Ce contenu est analysé localement, n'est ni conservé ni transmis,
  et rien n'est importé sans votre clic. Le Diagnostic peut y copier son
  rapport, à votre demande.
- **Lecture à voix haute** (mode cuisine) : voix de synthèse de Windows.
- **Impression, export PDF, QR code, export agenda (.ics), sauvegardes** :
  fichiers créés sur votre ordinateur, que vous partagez ensuite comme vous
  le souhaitez.

## Ce que l'application ne fait pas

- Aucune collecte de données personnelles par le développeur
- Aucun compte ni inscription
- Aucune publicité, aucun outil d'analyse d'audience ou de suivi
- Aucune vente ni transmission de vos recettes ou de vos données

## Vos droits

Le développeur ne détenant aucune de vos données, il n'a rien à vous
communiquer, corriger ou supprimer. Vous gardez la maîtrise complète de vos
données : consultation et modification dans l'application, export à tout
moment (Importer / Exporter les données), suppression en effaçant le dossier
de données.

## Enfants

L'application ne s'adresse pas spécifiquement aux enfants et ne collecte
aucune donnée personnelle, quel que soit l'âge de l'utilisateur.

## Modifications

Cette politique sera mise à jour si une nouvelle fonction implique un
traitement de données. La date de mise à jour figure en haut de ce
document. Les conditions d'utilisation (allergènes, données indicatives,
services tiers) figurent dans la **clause de responsabilité**, affichée au
premier lancement et consultable dans l'écran Importer / Exporter les
données.

## Contact

majogari81@gmail.com — ou une « Issue » sur le dépôt GitHub du projet.

---

# Privacy policy — Mes Recettes, Mes Courses (Windows)

*Last updated: 4 October 2026.*

This policy covers the **Windows** application (installer and Microsoft
Store). The mobile application has its own policy, on the mobile
application's website.

## Summary

All your data stays on your computer. The application has no account, no
server, no advertising and no analytics. It only connects to the Internet
when you yourself use a feature that needs it (importing a recipe from a
link, looking up a barcode, web search, donation button).

## What data is stored, and where

Your recipes, photos, pantry, shopping lists, meal plan, menus, prices,
settings and automatic backups are stored **only in a folder on your
computer**:

- next to the application if that folder is writable;
- otherwise (notably for the Microsoft Store version) in
  `%LOCALAPPDATA%\MesRecettesMesCourses`.

The exact location is shown on the **Diagnostics** screen. The settings
(`settings.json`) contain the language, theme, text size, acceptance of the
disclaimer, aisle and pantry order, the recipe of the day, barcodes already
linked to an ingredient and, if you chose one, the cloud backup folder. An
`error.log` file may record technical error messages.

Nobody but you — neither the developer nor any third party — has access to
this data. Deleting this folder permanently erases your data, unless you
made a backup.

## Cloud backup (optional)

If you choose a **synchronised backup folder** (OneDrive, Google Drive,
Dropbox…) on the Import / Export data screen, the application places a copy
of your backups there. The sync software of that service, installed on your
computer, then uploads them, under its own privacy policy. The application
never communicates with that service directly.

## Internet connections

All of them happen **only at your initiative**:

- **Importing a recipe from a link**: the application downloads the recipe
  page (and its photo) **directly from the website** you enter. If the page
  contains no readable recipe, the page address is sent as a last resort to
  **Jina AI Reader** (r.jina.ai), which returns a text version of the page.
  Only this address is sent, never your recipes or your data.
- **Barcode lookup** (pantry): the barcode is read **on your computer** from
  a photo you choose; only the number is sent to **Open Food Facts**
  (world.openfoodfacts.org) to find the product name. Barcode → ingredient
  links you confirm are remembered in your settings.
- **Searching for a recipe on the Internet**: opens a **Google** search in
  your browser with the words you type (plus recipe website names added
  automatically). The application does not read the results.
- **"Donate" button**: opens https://buymeacoffee.com/majogari in your
  browser.
- **Privacy policy**: the corresponding button opens this page in your
  browser.

These services are not operated by the developer and apply their own rules;
like any Internet request, they see your IP address.

## What stays entirely on your computer

- **Reading text from a photo** (recipe import, expiry date): the Tesseract
  engine and its language files are bundled with the application; no photo
  or text is sent.
- **Clipboard**: the application reads it when you click "Paste link", and
  also **when you come back to the application**, to offer to import a
  recipe link you have just copied. This content is analysed locally, is
  neither kept nor sent, and nothing is imported without your click. The
  Diagnostics screen can copy its report to it, at your request.
- **Read aloud** (cooking mode): Windows speech synthesis.
- **Printing, PDF export, QR code, calendar export (.ics), backups**: files
  created on your computer, which you then share as you wish.

## What the application does not do

- No collection of personal data by the developer
- No account or sign-up
- No advertising, analytics or tracking
- No sale or transfer of your recipes or data

## Your rights

As the developer holds none of your data, there is nothing to provide,
correct or delete. You keep full control: view and edit in the application,
export at any time (Import / Export data), delete by erasing the data
folder.

## Children

The application is not specifically aimed at children and collects no
personal data, whatever the user's age.

## Changes

This policy will be updated if a new feature involves processing data. The
update date is at the top of this document. The terms of use (allergens,
indicative data, third-party services) are in the **disclaimer**, shown at
first launch and available on the Import / Export data screen.

## Contact

majogari81@gmail.com — or an "Issue" on the project's GitHub repository.
