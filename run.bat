@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo.
echo  ==========================================
echo    ^>^>   RPG AI Player Bot  --  Setup
echo  ==========================================
echo.

:: ── Step 1/5 — Load .env ──────────────────────────────────────────────────────
echo [1/5] Loading environment
if exist .env (
    for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
        set "_ln=%%A"
        if not "!_ln:~0,1!"=="#" if not "%%A"=="" (
            set "%%A=%%B"
        )
    )
    echo   [OK]  .env loaded
) else (
    echo   [..] No .env file -- will check for API key below
)
echo.

:: ── Step 2/5 — System checks ──────────────────────────────────────────────────
echo [2/5] System checks

python --version >nul 2>&1
if errorlevel 1 (
    echo   [ERROR] Python not found.
    echo           Install Python 3.10+ from https://python.org
    echo           During installation check "Add Python to PATH"
    pause & exit /b 1
)
for /f "tokens=2 delims= " %%V in ('python --version 2^>^&1') do set PYVER=%%V
echo   [OK]  Python %PYVER%

ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo   [WARN] ffmpeg not found -- Whisper STT will not work
    echo          Download: https://ffmpeg.org/download.html
    echo          Then add ffmpeg\bin to your PATH
) else (
    echo   [OK]  ffmpeg found
)
echo.

:: ── Step 3/5 — Virtual environment ^& dependencies ───────────────────────────
echo [3/5] Python environment

if not exist .venv (
    echo   [..] Creating virtual environment...
    python -m venv .venv --without-pip
    if errorlevel 1 (
        echo   [ERROR] Failed to create virtual environment.
        pause & exit /b 1
    )
    echo   [OK]  Virtual environment created
)

call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo   [ERROR] Could not activate virtual environment.
    pause & exit /b 1
)

:: Bootstrap pip if missing
python -m pip --version >nul 2>&1
if errorlevel 1 (
    echo   [..] Bootstrapping pip...
    python -m ensurepip --upgrade
    if errorlevel 1 (
        echo   [ERROR] Could not bootstrap pip.
        echo           Try running: python -m ensurepip --upgrade
        pause & exit /b 1
    )
    python -m pip install --upgrade pip --quiet
    echo   [OK]  pip bootstrapped
)

:: Install / update dependencies
set STAMP=.venv\.install_stamp
set NEEDS_INSTALL=0
if not exist "%STAMP%" set NEEDS_INSTALL=1

if "!NEEDS_INSTALL!"=="0" (
    for /f "tokens=1" %%F in ('dir /b /o:-d requirements.txt "%STAMP%" 2^>nul') do (
        if /i "%%F"=="requirements.txt" set NEEDS_INSTALL=1
        goto :stamp_check_done
    )
)
:stamp_check_done

if "!NEEDS_INSTALL!"=="1" (
    echo   [..] Installing dependencies -- pip will show progress below...
    echo.
    python -m pip install --upgrade pip --quiet
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo   [ERROR] Dependency installation failed.
        echo           Check your internet connection and try again.
        pause & exit /b 1
    )
    type nul > "%STAMP%"
    echo.
    echo   [OK]  All dependencies installed
) else (
    echo   [OK]  Dependencies up to date
)
echo.

:: ── Step 4/6 — API key ────────────────────────────────────────────────────────
echo [4/6] OpenAI API key

if "!OPENAI_API_KEY!"=="" (
    echo.
    echo   [!]  OPENAI_API_KEY is not set.
    echo        Get your key from: https://platform.openai.com/api-keys
    echo.
    set /p "OPENAI_API_KEY=   Enter your OpenAI API key (sk-...): "

    if "!OPENAI_API_KEY!"=="" (
        echo   [ERROR] No key entered. Exiting.
        pause & exit /b 1
    )

    echo.
    set /p "SAVE_KEY=   Save key to .env for future runs? [Y/n]: "
    if /i not "!SAVE_KEY!"=="n" (
        :: Remove existing key line if present, then append
        if exist .env (
            findstr /v /b "OPENAI_API_KEY=" .env > .env.tmp
            move /y .env.tmp .env >nul
        )
        echo OPENAI_API_KEY=!OPENAI_API_KEY!>> .env
        echo   [OK]  Key saved to .env
    )
    echo.
)
echo   [OK]  OPENAI_API_KEY set
echo.

:: ── Step 5/6 — Validate connection ───────────────────────────────────────────
echo [5/6] Validating connection
echo.
python scripts\validate_setup.py
if errorlevel 1 (
    echo.
    echo   [ERROR] Validation failed -- fix the errors above and run again.
    pause & exit /b 1
)

:: ── Step 6/6 — Game files ─────────────────────────────────────────────────────
echo.
echo [6/6] Game documents
echo.
python scripts\setup_game_files.py
if errorlevel 1 (
    echo   [ERROR] Game file setup failed unexpectedly.
    pause & exit /b 1
)

:: ── Launch ────────────────────────────────────────────────────────────────────
echo.
echo  ==========================================
echo    Setup complete. Starting session...
echo    Press Ctrl+C to stop.
echo  ==========================================
echo.

python -m rpg_player.main

echo.
echo  Session ended. Press any key to close.
pause >nul
