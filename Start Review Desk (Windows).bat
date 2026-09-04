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

REM Where are the submissions?  By default a folder called "submissions" next
REM to this file; an editor can drop papers straight into it.
set PAPERS=%1
if "%PAPERS%"=="" set PAPERS=submissions
if not exist "%PAPERS%\" (
  if exist "paper_examples\" (
    set PAPERS=paper_examples
  ) else (
    mkdir submissions
    set PAPERS=submissions
  )
)

echo.
echo   Starting the JACoW review desk...
echo   Papers folder: %PAPERS%
echo.

where uv >nul 2>nul
if %errorlevel%==0 (
  uv run --quiet python main.py desk "%PAPERS%"
) else (
  where py >nul 2>nul
  if %errorlevel%==0 (
    py main.py desk "%PAPERS%"
  ) else (
    python main.py desk "%PAPERS%"
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
