@echo off
SETLOCAL

echo 🚀 Iniciando bootstrap del proyecto BOE Oposiciones...

REM 1. Crear venv si no existe
IF NOT EXIST "venv" (
    echo 📦 Creando entorno virtual 'venv'...
    python -m venv venv
) ELSE (
    echo ✅ Entorno virtual 'venv' ya existe.
)

REM 2. Activar venv
echo 🧪 Activando entorno virtual...
CALL venv\Scripts\activate.bat

REM 3. Instalar dependencias
IF EXIST "requirements.txt" (
    echo 📥 Instalando dependencias desde requirements.txt...
    pip install --upgrade pip
    pip install -r requirements.txt
) ELSE (
    echo ⚠️ No se encontró requirements.txt, instalando desde setup.py...
    pip install --upgrade pip
    pip install -e .
)

REM 4. Crear carpetas necesarias
echo 📁 Creando estructura de directorios...
IF NOT EXIST "static\uploads\profiles" (
    mkdir static\uploads\profiles
)

echo ✅ Bootstrap completado.
echo.
echo Para arrancar la aplicación:
echo 1^)^  Activar la venv:    call venv\Scripts\activate.bat
echo 2^)^  Ejecutar:           python run.py

ENDLOCAL
