@echo off
rem Cree un raccourci "Rekindle" (avec son icone) sur le Bureau
cd /d "%~dp0"
set "PYW="
for %%v in (3.13 3.12 3.11 3.10 3) do (
  if not defined PYW (
    for /f "delims=" %%i in ('py -%%v -c "import sys,os;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))" 2^>nul') do set "PYW=%%i"
  )
)
if not defined PYW for /f "delims=" %%i in ('python -c "import sys,os;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))" 2^>nul') do set "PYW=%%i"
if not defined PYW (
  echo Python est introuvable : lance d'abord "Lancer Rekindle.bat".
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -Command "$d=[Environment]::GetFolderPath('Desktop'); Remove-Item -LiteralPath ($d+'\Kwindle.lnk') -ErrorAction SilentlyContinue; $s=(New-Object -ComObject WScript.Shell).CreateShortcut($d+'\Rekindle.lnk'); $s.TargetPath='%PYW%'; $s.Arguments=[char]34+'%~dp0rekindle.py'+[char]34; $s.WorkingDirectory='%~dp0'; $s.IconLocation='%~dp0icone.ico'; $s.Description='Rekindle - tes livres vers ta Kindle'; $s.Save()"
if errorlevel 1 (
  echo Le raccourci n'a pas pu etre cree.
  pause
  exit /b 1
)
echo Raccourci "Rekindle" cree sur le Bureau.
timeout /t 3 >nul
