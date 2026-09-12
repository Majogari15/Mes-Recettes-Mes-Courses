@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Verification de Mes Recettes, Mes Courses...
python -m unittest discover -s tests -p "test_*.py" -v
if errorlevel 1 (
  echo.
  echo ECHEC : au moins un test a echoue.
  pause
  exit /b 1
)
echo.
echo Tous les tests automatiques ont reussi.
pause
