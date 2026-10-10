@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ================================================
echo   Construction de Mes Recettes, Mes Courses (.exe)
echo ================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [ERREUR] Python n'est pas installe ou n'est pas dans le PATH.
    echo Installez Python depuis https://www.python.org/downloads/
    echo en cochant bien la case "Add Python to PATH", puis relancez ce script.
    pause
    exit /b 1
)

echo Etape 1/5 : Installation des dependances necessaires...
echo   (pillow, reportlab, openpyxl, qrcode, pyzbar, pytesseract, pyttsx3, tkinterdnd2, pyinstaller, pypdfium2, opencv, arabic-reshaper)
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERREUR] L'installation des dependances a echoue.
    pause
    exit /b 1
)

rem Supprime les resultats precedents pour eviter qu'un ancien fichier
rem reste dans l'installeur si une ressource n'est plus produite.
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist dist (
    echo [ERREUR] Impossible de nettoyer dist. Fermez l'application et relancez.
    pause
    exit /b 1
)

echo Etape 2/5 : Preparation des ressources Tcl/Tk...
python build_tk_support.py prepare
if errorlevel 1 (
    echo [ERREUR] Preparation Tcl/Tk impossible. Aucun executable n'a ete produit.
    pause
    exit /b 1
)

echo.
echo Etape 3/5 : Construction de l'executable (peut prendre 1 a 2 minutes)...
python -m PyInstaller --clean --noconfirm --onefile --windowed --name "Mes Recettes, Mes Courses" ^
    --icon="icone_application.ico" ^
    --add-data="build/tk_bundle;." ^
    --hidden-import=pyttsx3.drivers ^
    --hidden-import=pyttsx3.drivers.sapi5 ^
    --additional-hooks-dir=. ^
    --hidden-import=tkinterdnd2 ^
    --hidden-import=windows_printing ^
    --hidden-import=pypdfium2_raw ^
    --collect-data=reportlab ^
    --hidden-import=reportlab.pdfbase.ttfonts ^
    --collect-all=pyzbar ^
    --collect-all=pypdfium2 ^
    --collect-all=pypdfium2_raw ^
    main.pyw
if errorlevel 1 (
    echo [ERREUR] La construction de l'executable a echoue.
    pause
    exit /b 1
)

if not exist "dist\Mes Recettes, Mes Courses.exe" (
    echo [ERREUR] Le fichier dist\Mes Recettes, Mes Courses.exe n'a pas ete cree.
    pause
    exit /b 1
)

echo.
echo Etape 4/5 : Verification des ressources et du lancement de l'interface...
python build_tk_support.py verify "dist\Mes Recettes, Mes Courses.exe"
if errorlevel 1 (
    del /q "dist\Mes Recettes, Mes Courses.exe"
    echo [ERREUR] Executable refuse : le controle Tcl/Tk a echoue.
    pause
    exit /b 1
)
echo.
echo Etape 5/5 : Copie des fichiers necessaires a cote de l'executable...
rem Textes de l'interface (une langue par fichier) et bases d'ingredients :
rem dossiers entiers, une langue ou un fichier ajoute est copie sans
rem modifier ce script.
rem Vide d'abord les anciennes copies : un fichier retire du projet ne doit
rem pas rester dans dist (ni donc dans l'installateur).
if exist dist\i18n rmdir /s /q dist\i18n
if exist dist\data rmdir /s /q dist\data
xcopy /Y /E /I /Q i18n dist\i18n >nul
xcopy /Y /E /I /Q data dist\data >nul
copy /Y LISEZ-MOI.txt dist\LISEZ-MOI.txt >nul

rem Tesseract OCR portable (optionnel) : si un dossier "tesseract-ocr"
rem (contenant tesseract.exe et son sous-dossier tessdata) est present a
rem cote de ce script, il est copie dans dist pour que l'import de recette
rem depuis une photo fonctionne sans que l'utilisateur installe quoi que ce
rem soit separement. Absent, l'application se comporte comme avant (Tesseract
rem doit alors etre installe a part - voir LISEZ-MOI.md).
rem preparer_tesseract.py cree ce dossier a partir du Tesseract installe sur
rem le PC de construction et y ajoute le paquet de chaque langue de
rem l'interface : l'utilisateur final n'a rien a installer.
python preparer_tesseract.py
if errorlevel 1 (
    echo [ERREUR] Paquets de langue Tesseract incomplets. Verifiez la connexion et relancez.
    pause
    exit /b 1
)
if exist tesseract-ocr (
    echo   Dossier tesseract-ocr detecte : copie pour un import photo autonome...
    xcopy /Y /E /I /Q tesseract-ocr dist\tesseract-ocr >nul
) else (
    echo   [INFO] Pas de dossier "tesseract-ocr" a cote de ce script : l'import
    echo   de recette depuis une photo necessitera Tesseract OCR installe a
    echo   part par l'utilisateur ^(voir la section OCR de LISEZ-MOI.md^).
)

if not exist "dist\Mes Recettes, Mes Courses.exe" (
    echo [ERREUR] Ressource manquante dans dist : Mes Recettes, Mes Courses.exe
    pause
    exit /b 1
)
for %%F in (i18n\*.json data\*.json data\*.png data\fonts\*) do (
    if not exist "dist\%%F" (
        echo [ERREUR] Ressource manquante dans dist : %%F
        pause
        exit /b 1
    )
)
for %%F in (LISEZ-MOI.txt) do (
    if not exist "dist\%%F" (
        echo [ERREUR] Ressource manquante dans dist : %%F
        pause
        exit /b 1
    )
)

echo.
echo ================================================
echo   Termine !
echo   Votre application se trouve dans :
echo   dist\Mes Recettes, Mes Courses.exe
echo ================================================
echo.
echo Vous pouvez deplacer le dossier "dist" entier ailleurs
echo (cle USB, autre PC, Bureau...) : il contient tout ce qu'il
echo faut pour fonctionner, sans avoir besoin d'installer Python.
echo Gardez simplement tous les fichiers de ce dossier ensemble.
echo.
if exist dist\tesseract-ocr (
    echo Tesseract OCR est inclus dans dist\tesseract-ocr : l'import de
    echo recette depuis une photo fonctionnera sans rien installer de plus.
) else (
    echo Rappel : l'import de recette depuis une photo necessite Tesseract
    echo OCR, installe separement ^(voir la section OCR de LISEZ-MOI.md^).
)
echo.
pause
