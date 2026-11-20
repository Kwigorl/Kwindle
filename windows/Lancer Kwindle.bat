@echo off
rem Kwindle - lanceur Windows
cd /d "%~dp0"

set "PY="
set "PYW="
rem 1) de preference un Python 3.13 a 3.10 (necessaire pour les torrents)
for %%v in (3.13 3.12 3.11 3.10) do (
  if not defined PY (
    py -%%v -c "import sys" >nul 2>nul && (
      set "PY=py -%%v"
      set "PYW=pyw -%%v"
    )
  )
)
rem 2) sinon n'importe quel Python 3.9 ou plus (tout marche sauf les torrents)
if not defined PY (
  py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul && (
    set "PY=py -3"
    set "PYW=pyw -3"
  )
)
if not defined PY (
  python -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul && (
    set "PY=python"
    set "PYW=pythonw"
  )
)
if not defined PY goto pas_de_python

%PY% -c "import lxml, mobi, PIL, keyring" >nul 2>nul
if errorlevel 1 (
  echo.
  echo  Premiere ouverture : installation des composants de Kwindle...
  echo  ^(ca prend une minute, ca ne se fait qu'une fois^)
  echo.
  %PY% -m pip install --user --disable-pip-version-check -r requirements.txt
  if errorlevel 1 (
    echo.
    echo  L'installation a echoue. Verifie ta connexion internet puis relance.
    pause
    exit /b 1
  )
)
rem composants facultatifs : glisser-deposer et torrents
%PY% -c "import tkinterdnd2" >nul 2>nul || %PY% -m pip install --user --disable-pip-version-check -q tkinterdnd2 >nul 2>nul
%PY% -c "import sys; sys.exit(0 if (3, 10) <= sys.version_info[:2] <= (3, 13) else 1)" >nul 2>nul && (
  %PY% -c "import libtorrent" >nul 2>nul || (
    echo  Installation du module torrent...
    %PY% -m pip install --user --disable-pip-version-check -q "libtorrent>=2.0"
  )
)

start "" %PYW% "%~dp0kwindle.py"
exit /b 0

:pas_de_python
echo.
echo  Python n'est pas installe sur cet ordinateur.
echo  Kwindle a besoin de Python 3.13 (ou 3.10 a 3.12) pour tout faire, torrents compris.
echo.
where winget >nul 2>nul || goto telechargement
choice /c ON /m " L'installer maintenant"
if errorlevel 2 goto telechargement
winget install -e --id Python.Python.3.13 --scope user --accept-package-agreements --accept-source-agreements
echo.
echo  C'est fait. Ferme cette fenetre et relance "Lancer Kwindle.bat".
pause
exit /b 0

:telechargement
echo  1. Installe Python 3.13 depuis la page qui va s'ouvrir.
echo     Pendant l'installation, coche bien "Add python.exe to PATH".
echo  2. Relance ce fichier.
echo.
start "" https://www.python.org/downloads/windows/
pause
exit /b 1
