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
OutputBaseFilename=MesRecettesMesCourses_StoreCapture
OutputDir=installateur
Compression=lzma
SolidCompression=yes
WizardStyle=modern
; Pas besoin des droits administrateur pour installer dans le dossier
; utilisateur — évite l'invite Windows qui peut freiner certains
; utilisateurs.
PrivilegesRequired=lowest
; Capture MSIX Store : ne crée pas de désinstalleur Win32 visible dans le package.
Uninstallable=no

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

; Aucun raccourci n’est créé par l’installateur de capture.
; Le MSIX crée automatiquement une seule entrée depuis [Applications].

[Run]
; Comportement d’origine : lancement normal détecté par MSIX Packaging Tool.
Filename: "{app}\{#MyAppExeName}"; Description: "Lancer {#MyAppName}"; Flags: nowait postinstall skipifsilent
