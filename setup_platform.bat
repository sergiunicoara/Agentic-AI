@echo off
SET ROOT_DIR=ai-native-data-platform

echo Creating directory structure for %ROOT_DIR%...

:: Create Folders
mkdir "%ROOT_DIR%"
mkdir "%ROOT_DIR%\app"
mkdir "%ROOT_DIR%\scripts"

:: Create Root Files
type nul > "%ROOT_DIR%\docker-compose.yml"
type nul > "%ROOT_DIR%\.env.example"
type nul > "%ROOT_DIR%\requirements.txt"
type nul > "%ROOT_DIR%\README.md"

:: Create App Files
type nul > "%ROOT_DIR%\app\__init__.py"
type nul > "%ROOT_DIR%\app\config.py"
type nul > "%ROOT_DIR%\app\db.py"
type nul > "%ROOT_DIR%\app\models.py"
type nul > "%ROOT_DIR%\app\schemas.py"
type nul > "%ROOT_DIR%\app\chunking.py"
type nul > "%ROOT_DIR%\app\embedder.py"
type nul > "%ROOT_DIR%\app\retrieval.py"
type nul > "%ROOT_DIR%\app\worker.py"
type nul > "%ROOT_DIR%\app\main.py"

:: Create Script Files
type nul > "%ROOT_DIR%\scripts\init_db.sql"

echo.
echo Structure created successfully:
echo --------------------------------
tree "%ROOT_DIR%" /f
echo --------------------------------
pause