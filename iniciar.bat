@echo off
cd /d "%~dp0"
if not exist "venv\Scripts\python.exe" (
    echo Primera vez: creando el entorno e instalando dependencias...
    python -m venv venv || goto :error
    call "venv\Scripts\python.exe" -m pip install --upgrade pip
    call "venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :error
)
call "venv\Scripts\python.exe" app.py
goto :eof
:error
echo.
echo ERROR en la instalacion. Revisar el mensaje de arriba.
pause
