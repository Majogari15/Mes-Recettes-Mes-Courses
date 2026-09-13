# Correctif de construction Tcl/Tk — version 1.6.14

1. Sur le PC habituel, extraire cette archive dans un nouveau dossier et lancer `Construire_le_exe.bat`.
2. Attendre les confirmations du contrôle des fichiers Tcl/Tk et du démarrage de l’interface, puis le message « Termine ! ».
3. Ouvrir `dist\Mes Recettes, Mes Courses.exe` et vérifier l’écran d’accueil.
4. Compiler `installateur_store_capture.iss` avec Inno Setup sur ce même PC (version 1.6.19 déjà renseignée).
5. Transférer le nouvel installateur `installateur\MesRecettesMesCourses_StoreCapture.exe` dans une machine Hyper-V propre, avant de lancer la capture. Créer un NOUVEAU MSIX à partir de cet installateur, version **1.6.20.0**. Le nom affiché sera repris automatiquement depuis `Mes Recettes, Mes Courses.exe`.
6. Tester une copie signée du nouveau MSIX dans la VM, y compris le lancement de l’application. Conserver la copie destinée au Store selon la procédure habituelle.

La préparation Tcl/Tk utilise les ressources du Python employé pour compiler. Les chemins zipfs sont lus avec Tcl lui-même. Aucun Python n’est à installer dans Hyper-V pour faire fonctionner le résultat.
Les fichiers `build_tk_support.py` et `main.pyw` fournis doivent rester dans le dossier du projet. Le contrôle de démarrage ne lit ni ne modifie les recettes ou paramètres personnels.

---

# Créer l'installateur avec Inno Setup

Ce guide correspond à la version **1.6.12 / build 60** du projet.

## 1. Préparer l'exécutable Windows

Décompressez l'archive complète dans un dossier. Gardez ensemble `main.py`,
`main.pyw`, `windows_printing.py`, `requirements.txt`, `Construire_le_exe.bat`,
`hook-tkinterdnd2.py`, `icone_application.ico`, les fichiers JSON et les PNG.

Sur votre PC Windows, lancez d'abord `Construire_le_exe.bat`. Il construit
`dist\Mes Recettes, Mes Courses.exe` et copie les ressources nécessaires dans `dist`,
notamment `i18n_desktop.json`, les bases et traductions, les drapeaux et
`LISEZ-MOI.txt`. Testez cet exécutable avant de créer l'installateur.

Installez ensuite [Inno Setup depuis son site officiel](https://jrsoftware.org/isdl.php)
si vous ne l'avez pas déjà.

## 2. Choisir le bon script

| Usage | Script à compiler | Fichier produit dans `installateur\` |
| --- | --- | --- |
| Installation Windows classique | `installateur.iss` | `MesRecettesMesCourses_Installateur.exe` |
| Installation à capturer avec MSIX Packaging Tool pour le Store | `installateur_store_capture.iss` | `MesRecettesMesCourses_StoreCapture.exe` |

La variante de capture utilise `Uninstallable=no` : elle ne crée pas de
désinstalleur Win32. Utilisez-la pour la capture MSIX, pas comme installateur
classique à distribuer directement. Le script standard conserve le mécanisme
de désinstallation d'Inno Setup.

Les deux scripts créent **un seul raccourci de l'application, dans le menu
Démarrer**, et aucun raccourci automatique sur le Bureau. Celui-ci utilise
l'icône intégrée à `Mes Recettes, Mes Courses.exe`. Ce choix du projet ne constitue pas une
interdiction générale des raccourcis Bureau par Microsoft.

Ils utilisent `PrivilegesRequired=lowest` et `DefaultDirName={autopf}\{#MyAppName}`.
En mode d'installation non administrateur, Inno Setup résout `{autopf}` vers
le dossier de programmes de l'utilisateur. Voir les
[constantes automatiques Inno Setup](https://jrsoftware.org/ishelp/topic_consts.htm).

## 3. Compiler

1. Ouvrez le script choisi dans Inno Setup.
2. Choisissez **Build → Compile**.
3. Si la compilation réussit, récupérez le fichier correspondant dans
   le sous-dossier `installateur` du projet.

L'installateur copie l'exécutable et les ressources, crée le raccourci du
menu Démarrer et propose de lancer l'application après l'installation.
Tesseract OCR reste une installation séparée pour l'import photo.

## 4. Nom et numéros de version

Les deux scripts contiennent actuellement :

```ini
#define MyAppName "Mes Recettes, Mes Courses"
#define MyAppVersion "1.6.12"
#define MyAppPublisher "Majogari"
```

Le nom affiché doit être cohérent avec la fiche du produit. Ce guide ne
prétend pas reconstituer un ancien renommage ni vérifier la fiche actuellement
en ligne dans Partner Center.

`MyAppVersion` est la version de l'installateur Inno Setup. La version du
paquet MSIX est définie séparément lors de sa création : modifier le `.iss`
ne modifie pas automatiquement un MSIX déjà créé.

Pour une mise à jour, conservez l'identité de l'application publiée et
choisissez une version de paquet supérieure à celle distribuée aux utilisateurs
visés. `1.6.13.0` n'est utilisable comme nouvelle version que si cette condition
est satisfaite. Consultez les
[exigences et règles de version Microsoft](https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/msix/app-package-requirements).

## 5. Vérifier avant la soumission

La compilation réussie de l'installateur ne garantit pas la certification.
Installez le MSIX final sur Windows et testez le lancement, les quatre langues,
les données conservées lors d'une mise à jour, les sauvegardes et restaurations,
les imports et les exports. Contrôlez le nom, l'icône et les entrées du menu Démarrer.

Exécutez également le Windows App Certification Kit recommandé dans les
[exigences Microsoft](https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/msix/app-package-requirements).

Pour corriger ultérieurement le programme, mettez à jour les sources et les
versions, reconstruisez `dist`, puis l'installateur et enfin le MSIX. Ne
réutilisez pas un ancien exécutable sous prétexte que la documentation a changé.
