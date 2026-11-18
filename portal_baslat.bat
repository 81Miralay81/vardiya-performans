@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Ilk seferde gerekli paketleri kurar, sonra web portalini baslatir. Portu degistirmek icin: portal_baslat.bat 9000
python -m pip install --quiet -r requirements-web.txt
if "%1"=="" (python main_web.py) else (python main_web.py --port %1)
pause
