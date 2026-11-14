@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

rem --- NeuroSpartan setup ---------------------------------------------------
rem Creates a local venv and installs the project dependencies from
rem requirements.txt. Safe to re-run: it reuses a good venv, replaces a broken
rem one, and picks a Python that actually has wheels for pygame.
rem
rem Why the version check matters: pygame needs prebuilt wheels. Checked
rem against PyPI for the pinned version - pygame-2.6.1 ships cp37-cp313
rem win_amd64 wheels and nothing for 3.14/3.15. On Python 3.15 (this machine's
rem default "python") pip therefore falls back to the source tarball and dies
rem with "No module named 'distutils.msvccompiler'", because distutils' MSVC
rem support was removed. 3.12 was verified working here; 3.13 has a wheel but
rem was not tested. requirements.txt alone is not enough - the interpreter
rem has to be chosen deliberately.
rem --------------------------------------------------------------------------

set "PY="

rem Preferred: the launcher's known-good versions, newest first.
for %%V in (3.13 3.12 3.11 3.10 3.9) do (
    if not defined PY (
        py -%%V -c "pass" >nul 2>nul && set "PY=py -%%V"
    )
)

rem Fallback: plain "python", accepted only if the interpreter reports a
rem supported minor version (3.9 - 3.13). Letting Python do the comparison
rem avoids brittle batch string parsing.
if not defined PY (
    where python >nul 2>nul
    if errorlevel 1 (
        echo [ERROR] Python was not found on PATH.
        echo         Install Python 3.9 - 3.13 from python.org and re-run.
        pause
        exit /b 1
    )
    python -c "import sys; raise SystemExit(0 if 9 <= sys.version_info[1] <= 13 else 1)" >nul 2>nul
    if not errorlevel 1 (set "PY=python")
)

if not defined PY (
    echo [ERROR] No usable Python found.
    echo         NeuroSpartan needs Python 3.9 - 3.13 for pygame wheels.
    echo         Your default "python" is too new or too old.
    echo         Install 3.12:  https://www.python.org/downloads/release/python-31210/
    pause
    exit /b 1
)

for /f "delims=" %%I in ('%PY% -c "import sys;print(sys.version.split()[0])"') do set "PV=%%I"
echo Using Python %PV%

rem Reuse the venv only if its OWN interpreter is inside the supported band.
rem Checking merely "does it run" is not enough: a venv built on Python 3.15
rem runs fine, gets reused, and then pygame has no wheel for it and the whole
rem install fails - with this script happily reporting "Using Python 3.12".
set "VENV_OK="
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys; raise SystemExit(0 if 9 <= sys.version_info[1] <= 13 else 1)" >nul 2>nul && set "VENV_OK=1"
)
if not defined VENV_OK (
    if exist ".venv" (
        echo Existing .venv is broken or built on an unsupported Python:
        ".venv\Scripts\python.exe" -c "import sys; print('   it uses', sys.version.split()[0])" 2>nul
        echo Recreating it with the interpreter chosen above ...
        rd /s /q ".venv" 2>nul
        rem If deletion failed, a running app is holding python.exe. Recreating
        rem on top of a half-deleted venv is how broken environments get made.
        if exist ".venv\Scripts\python.exe" (
            echo [ERROR] Could not delete .venv - it is still in use.
            echo         Close every running NeuroSpartan window, then re-run this.
            echo         ^(Task Manager ^> look for python.exe running from .venv^)
            pause
            exit /b 1
        )
    )
    echo Creating virtual environment .venv ...
    %PY% -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Could not create the venv. Close any running app windows and retry.
        pause
        exit /b 1
    )
)

".venv\Scripts\python.exe" -c "import sys; print('venv is Python', sys.version.split()[0])"

echo Upgrading pip ...
".venv\Scripts\python.exe" -m pip install --upgrade pip --no-input --disable-pip-version-check

echo Installing dependencies from requirements.txt ...
".venv\Scripts\python.exe" -m pip install -r requirements.txt --no-input --disable-pip-version-check
if errorlevel 1 (
    echo [ERROR] Dependency install failed. Check the messages above.
    pause
    exit /b 1
)

echo Sanity check - importing the three libraries ...
".venv\Scripts\python.exe" -c "import PySide6, pygame, requests; print('  PySide6', PySide6.__version__); print('  pygame', pygame.version.ver); print('  requests', requests.__version__)"
if errorlevel 1 (
    echo [ERROR] Libraries installed but do not import. The venv is inconsistent.
    pause
    exit /b 1
)

call ".venv\Scripts\activate.bat"

echo.
echo Setup complete. Start the app with:  python main.py
pause
