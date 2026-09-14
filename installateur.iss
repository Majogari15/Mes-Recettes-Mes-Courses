; ============================================================
;  Script Inno Setup — Mes Recettes, Mes Courses
;  Génère l'installateur (.exe) à partir des fichiers déjà
;  construits par Construire_le_exe.bat (dossier "dist").
; ============================================================

#define MyAppName "Mes Recettes, Mes Courses"
#define MyAppVersion "1.6.28"
#define MyAppPublisher "Majogari"
#define MyAppExeName "Mes Recettes, Mes Courses.exe"

#ifexist "dist\Mes Recettes, Mes Courses.exe"
#else
#error "dist\Mes Recettes, Mes Courses.exe est absent. Lancez Construire_le_exe.bat avant de compiler l'installateur."
#endif
#ifexist "dist\i18n_desktop.json"
#else
#error "dist\i18n_desktop.json est absent. Relancez Construire_le_exe.bat."
#endif

[Setup]
; Identifiant unique de l'application (généré une seule fois, à garder
; identique à chaque nouvelle version pour que les mises à jour
; s'installent proprement par-dessus l'ancienne).
AppId={{8F3C2A1E-9B4D-4E7A-BC12-5D6E7F8A9B0C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
; Icône de l'installateur lui-même (le .exe qu'on double-clique pour
; installer) — voir le dossier fourni précédemment.
SetupIconFile=icone_application.ico
; Nom du fichier d'installation généré
OutputBaseFilename=MesRecettesMesCourses_Installateur
OutputDir=installateur
Compression=lzma
SolidCompression=yes
WizardStyle=modern
; Pas besoin des droits administrateur pour installer dans le dossier
; utilisateur — évite l'invite Windows qui peut freiner certains
; utilisateurs.
PrivilegesRequired=lowest

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Files]
; L'exécutable et tous les fichiers de données, copiés depuis le
; dossier "dist" généré par Construire_le_exe.bat.
Source: "dist\Mes Recettes, Mes Courses.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\i18n_desktop.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\ingredients_par_defaut.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\valeurs_nutritionnelles.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\ingredient_allergenes.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\ingredient_substitutions.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\ingredient_substitutions_en.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\ingredient_substitutions_es.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\ingredient_substitutions_de.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\ingredient_translations_en.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\ingredient_translations_es.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\ingredient_translations_de.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\flag_fr.png"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\flag_uk.png"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\flag_es.png"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\flag_de.png"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\LISEZ-MOI.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Un seul raccourci (menu Démarrer) — pas de second raccourci Bureau :
; en créer deux, même avec la même icône, provoquait deux entrées
; distinctes dans le menu Démarrer de Windows (refus Microsoft
; 10.1.1.11). Les utilisateurs peuvent épingler l'application au Bureau
; ou à la barre des tâches directement depuis le menu Démarrer une fois
; installée, sans avoir besoin d'un second raccourci créé d'office.
; Pas de "IconFilename" précisé volontairement : il hérite
; automatiquement de l'icône intégrée dans Mes Recettes, Mes Courses.exe (celle
; corrigée via --icon dans Construire_le_exe.bat).
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"

[Run]
; Propose de lancer l'application juste après l'installation.
Filename: "{app}\{#MyAppExeName}"; Description: "Lancer {#MyAppName}"; Flags: nowait postinstall skipifsilent
