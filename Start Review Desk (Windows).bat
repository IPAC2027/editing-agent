@echo off
REM ---------------------------------------------------------------------------
REM JACoW review desk - double-click to start.
REM
REM For editors: double-click this file. A browser window opens with your
REM papers in it. When you are finished, close the black window that appeared
REM alongside it.
REM
REM The first time you run it, it may take a minute to set itself up.
REM ---------------------------------------------------------------------------

cd /d "%~dp0"
setlocal EnableDelayedExpansion

REM Which desk?
REM  * Editors working from the chief editor's desk set nothing up here: once
REM    this PC has joined the chief's desk (see the editor guide), this file
REM    opens that desk again, and it keeps the papers you take by itself.
REM  * Working alone on a folder of papers: name it on the first line of
REM    papers_folder.txt next to this file. Otherwise the desk works in a
REM    folder called "submissions" next to this file; drop papers into it.
set "PAPERS=%~1"
set "FROM_FILE="
if "!PAPERS!"=="" if exist "papers_folder.txt" (
  set /p PAPERS=<papers_folder.txt
  set "FROM_FILE=1"
)
if defined FROM_FILE if not exist "!PAPERS!\" (
  echo.
  echo   The papers folder named in papers_folder.txt is not available:
  echo     "!PAPERS!"
  echo.
  echo   If it is shared from another computer, connect to it first,
  echo   then start the desk again.
  echo.
  pause
  exit /b 1
)
REM No folder named: the chief's desk this PC joined, else the folder used
REM last, else "submissions" (or the examples shipped with the tool).
if "!PAPERS!"=="" (
  set "ALONE=submissions"
  if not exist "submissions\" if exist "paper_examples\" set "ALONE=paper_examples"
  set ARGS=--alone-in "!ALONE!"
) else (
  set ARGS="!PAPERS!"
)

echo.
echo   Starting the JACoW review desk...
if not "!PAPERS!"=="" echo   Papers folder: !PAPERS!
echo.

where uv >nul 2>nul
if %errorlevel%==0 (
  uv run --quiet python main.py !ARGS!
) else (
  where py >nul 2>nul
  if %errorlevel%==0 (
    py main.py !ARGS!
  ) else (
    python main.py !ARGS!
  )
)

if errorlevel 1 (
  echo.
  echo   ---------------------------------------------------------------
  echo   The review desk could not start.
  echo.
  echo   This usually means Python is not installed yet, or the tool's
  echo   own packages have not been set up on this computer.
  echo.
  echo   Send this whole window to whoever set the tool up for you -
  echo   the lines above say what went wrong.
  echo   ---------------------------------------------------------------
  echo.
  pause
)
