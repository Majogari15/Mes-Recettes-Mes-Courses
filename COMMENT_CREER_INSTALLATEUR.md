# Créer l'installateur avec Inno Setup

## Étape 1 — Installer Inno Setup (si ce n'est pas déjà fait)

Téléchargez-le gratuitement sur https://jrsoftware.org/isdl.php (choisissez
la version "innosetup-x.x.x.exe", pas la version "-unicode" séparée, la
version actuelle les inclut déjà). Installez-le normalement.

## Étape 2 — Préparer le dossier

Vous devez avoir, dans le **même dossier** :
- `main.pyw`, `icone_application.ico`, et tous les fichiers `.json`/`.png`
  (le contenu de l'archive que je vous ai donnée)
- Le dossier `dist` généré par `Construire_le_exe.bat` (contient déjà
  `MesRecettes.exe` et une copie des fichiers de données — c'est normal,
  Inno Setup ira les chercher là)
- Le fichier `installateur.iss` que je viens de créer

Donc l'ordre est important : **lancez d'abord `Construire_le_exe.bat`**
(pour que le dossier `dist` existe avec la bonne icône dedans), **puis**
Inno Setup.

## Étape 3 — Ouvrir et compiler le script

1. Double-cliquez sur `installateur.iss` — ça devrait ouvrir directement
   l'éditeur de scripts Inno Setup (IDE Inno Setup)
2. Cliquez sur **Build → Compile** dans le menu (ou appuyez sur `Ctrl+F9`,
   ou cliquez sur le bouton avec l'icône d'engrenage/lecture verte dans
   la barre d'outils)
3. Une fenêtre de progression s'affiche, puis se ferme si tout s'est
   bien passé

## Étape 4 — Récupérer l'installateur

Le fichier généré se trouve dans le sous-dossier **`installateur`**
(créé automatiquement à côté de votre script), sous le nom
`MesRecettesMesCourses_Installateur.exe` — c'est ce fichier que vous
distribuez aux utilisateurs (ou que vous utilisez ensuite comme source
pour le MSIX Packaging Tool).

## Ce que fait ce script précisément

- Utilise **votre icône corrigée** pour l'installateur lui-même
- Installe dans le dossier utilisateur (pas besoin des droits
  administrateur — plus simple pour la plupart des gens)
- Crée un raccourci dans le menu Démarrer, et un sur le Bureau (avec une
  case à cocher pour le désactiver si l'utilisateur préfère)
- Les raccourcis créés **héritent automatiquement** de l'icône intégrée
  dans `MesRecettes.exe` — donc si vous avez bien reconstruit l'exe avec
  la correction précédente, les raccourcis seront corrects sans réglage
  supplémentaire ici
- Propose de lancer l'application juste après l'installation

## ⚠️ Corrections suite au refus Microsoft Store (10.1.1.11 / 10.1.1.1)

Deux choses ont été corrigées dans ce script suite à un refus de
soumission :

1. **Nom aligné sur la fiche Store** : `#define MyAppName` est passé de
   "Mes Recettes, Mes Courses" à **"Mes Recettes, Mes Courses"**, pour
   correspondre exactement au nom du produit dans Partner Center.
   Si vous préférez plutôt renommer votre fiche Store pour qu'elle
   corresponde à "Mes Recettes, Mes Courses", faites-le dans Partner
   Center et dites-le-moi pour que je remette l'ancien nom ici à la
   place — les deux doivent juste être identiques, peu importe lequel.

2. **Un seul raccourci désormais** (menu Démarrer uniquement) — en
   créer un second sur le Bureau, même avec le même nom et la même
   icône, provoquait deux entrées distinctes dans le menu Démarrer de
   Windows, rejetées comme des "tuiles en double". Les utilisateurs
   peuvent toujours épingler l'application au Bureau ou à la barre des
   tâches depuis le menu Démarrer une fois installée.

**Pensez aussi à incrémenter le numéro de version** (`#define
MyAppVersion "1.0"` → par exemple `"1.0.1"`) avant de recompiler, sinon
Partner Center refusera d'accepter le nouveau paquet.

## Si vous voulez changer le numéro de version

Modifiez la ligne `#define MyAppVersion "1.0"` tout en haut du fichier
`.iss` avant de compiler, pour que ça corresponde à ce que vous avez
indiqué dans Partner Center.

## Un détail à vérifier

Ce script recrée une version simplifiée de ce qu'on avait probablement
construit ensemble lors d'une session précédente (dont je n'ai plus le
détail exact) — il couvre l'essentiel (installation, raccourcis,
icônes), mais si votre version précédente avait des réglages
particuliers dont vous vous souvenez (page de licence personnalisée,
lien de don, langue supplémentaire...), dites-le-moi et je les ajoute.
