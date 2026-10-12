@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src"
"%~dp0.venv\Scripts\python.exe" -c "import valenza.gui.app; print('Valenza actualizado:', valenza.gui.app.__file__)"
"%~dp0.venv\Scripts\python.exe" -m valenza.gui.app
if errorlevel 1 pause
