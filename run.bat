@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo.
echo ==========================================
echo   RPG AI Player Bot
echo ==========================================
echo.

:: ── Load .env ─────────────────────────────────────────────────────────────────
if exist .env (
    echo [^>] Loading .env file...
    for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
        set "_line=%%A"
        if not "!_line:~0,1!"=="#" (
            if not "%%A"=="" (
                set "%%A=%%B"
            )
        )
    )
    echo [OK] .env loaded
)

:: ── Check Python ──────────────────────────────────────────────────────────────
echo [^>] Checking Python version...
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found.
    echo         Install Python 3.10+ from https://python.org
    echo         During installation: check "Add Python to PATH"
    pause
    exit /b 1
)

for /f "tokens=2 delims= " %%V in ('python --version 2^>^&1') do set PYVER=%%V
echo [OK] Python %PYVER%

:: ── Check ffmpeg ──────────────────────────────────────────────────────────────
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo [WARN] ffmpeg not found -- Whisper STT will not work.
    echo        Download from https://ffmpeg.org/download.html
    echo        Add ffmpeg\bin to your PATH.
    echo.
)

:: ── Create virtual environment if missing ─────────────────────────────────────
if not exist .venv (
    echo [^>] Creating virtual environment...
    python -m venv .venv --without-pip
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created
)

call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo [ERROR] Could not activate virtual environment.
    pause
    exit /b 1
)

:: ── Bootstrap pip (handles missing pip in any venv) ──────────────────────────
python -m pip --version >nul 2>&1
if errorlevel 1 (
    echo [^>] Bootstrapping pip...
    python -m ensurepip --upgrade
    if errorlevel 1 (
        echo [ERROR] Could not bootstrap pip.
        echo         Try: python -m ensurepip --upgrade
        pause
        exit /b 1
    )
    python -m pip install --upgrade pip --quiet
)

:: ── Install / update dependencies ─────────────────────────────────────────────
set STAMP=.venv\.install_stamp
set NEEDS_INSTALL=0

if not exist "%STAMP%" set NEEDS_INSTALL=1

if "!NEEDS_INSTALL!"=="0" (
    :: Compare modification times to detect requirements.txt changes
    for /f "tokens=1,2" %%A in ('dir /tw /o:-d requirements.txt "%STAMP%" 2^>nul ^| findstr /r "[0-9]"') do (
        if "%%A %%B"=="requirements.txt" set NEEDS_INSTALL=1
        goto :check_done
    )
)
:check_done

if "!NEEDS_INSTALL!"=="1" (
    echo [^>] Installing dependencies (first run may take several minutes^^^)...
    python -m pip install --upgrade pip --quiet
    python -m pip install -r requirements.txt --quiet
    if errorlevel 1 (
        echo [ERROR] Dependency installation failed.
        echo         Check your internet connection and try again.
        pause
        exit /b 1
    )
    type nul > "%STAMP%"
    echo [OK] Dependencies installed
) else (
    echo [OK] Dependencies up to date
)

:: ── Validate OpenAI API key ───────────────────────────────────────────────────
if "%OPENAI_API_KEY%"=="" (
    echo.
    echo [ERROR] OPENAI_API_KEY is not set.
    echo.
    echo         Create a .env file in this directory with the content:
    echo           OPENAI_API_KEY=sk-...
    echo.
    echo         Or set it as a Windows environment variable.
    pause
    exit /b 1
)
echo [OK] OPENAI_API_KEY found

:: ── Ensure data directories exist ─────────────────────────────────────────────
if not exist rpg_player\data\game_files mkdir rpg_player\data\game_files

:: ── Launch ─────────────────────────────────────────────────────────────────────
echo.
echo Starting session...
echo Drop game PDFs / DOCX files into:  rpg_player\data\game_files\
echo Press Ctrl+C to end the session.
echo.

cd rpg_player
python main.py

echo.
echo Session ended.
pause
