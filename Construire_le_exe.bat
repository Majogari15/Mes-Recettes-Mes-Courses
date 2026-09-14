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
echo   (pillow, reportlab, openpyxl, qrcode, pyzbar, pytesseract, pyttsx3, tkinterdnd2, pyinstaller, pypdfium2)
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
copy /Y i18n_desktop.json dist\i18n_desktop.json >nul
copy /Y ingredients_par_defaut.json dist\ingredients_par_defaut.json >nul
copy /Y valeurs_nutritionnelles.json dist\valeurs_nutritionnelles.json >nul
copy /Y ingredient_allergenes.json dist\ingredient_allergenes.json >nul
copy /Y ingredient_substitutions.json dist\ingredient_substitutions.json >nul
copy /Y ingredient_substitutions_en.json dist\ingredient_substitutions_en.json >nul
copy /Y ingredient_substitutions_es.json dist\ingredient_substitutions_es.json >nul
copy /Y ingredient_substitutions_de.json dist\ingredient_substitutions_de.json >nul
copy /Y ingredient_translations_en.json dist\ingredient_translations_en.json >nul
copy /Y ingredient_translations_es.json dist\ingredient_translations_es.json >nul
copy /Y ingredient_translations_de.json dist\ingredient_translations_de.json >nul
copy /Y flag_fr.png dist\flag_fr.png >nul
copy /Y flag_uk.png dist\flag_uk.png >nul
copy /Y flag_es.png dist\flag_es.png >nul
copy /Y flag_de.png dist\flag_de.png >nul
copy /Y LISEZ-MOI.txt dist\LISEZ-MOI.txt >nul

rem Tesseract OCR portable (optionnel) : si un dossier "tesseract-ocr"
rem (contenant tesseract.exe et son sous-dossier tessdata) est present a
rem cote de ce script, il est copie dans dist pour que l'import de recette
rem depuis une photo fonctionne sans que l'utilisateur installe quoi que ce
rem soit separement. Absent, l'application se comporte comme avant (Tesseract
rem doit alors etre installe a part - voir LISEZ-MOI.md).
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
for %%F in (i18n_desktop.json ingredients_par_defaut.json valeurs_nutritionnelles.json ingredient_allergenes.json ingredient_substitutions.json ingredient_substitutions_en.json ingredient_substitutions_es.json ingredient_substitutions_de.json ingredient_translations_en.json ingredient_translations_es.json ingredient_translations_de.json flag_fr.png flag_uk.png flag_es.png flag_de.png LISEZ-MOI.txt) do (
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
