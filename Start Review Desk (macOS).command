#!/bin/bash
# ---------------------------------------------------------------------------
# JACoW review desk — double-click to start.
#
# For editors: put the folder holding this file wherever you like, then
# double-click this file. A browser window opens with your papers in it.
# When you are finished, close the black window that appeared alongside it.
#
# The first time you run it, it may take a minute to set itself up.
# ---------------------------------------------------------------------------

cd "$(dirname "$0")" || exit 1

# Where are the submissions?  By default a folder called "submissions" next to
# this file; an editor can drop papers straight into it.
PAPERS="${1:-submissions}"
if [ ! -d "$PAPERS" ]; then
  if [ -d "paper_examples" ]; then
    PAPERS="paper_examples"
  else
    mkdir -p submissions
    PAPERS="submissions"
  fi
fi

echo ""
echo "  Starting the JACoW review desk…"
echo "  Papers folder: $PAPERS"
echo ""

run_with_uv() { uv run --quiet python main.py desk "$PAPERS"; }
run_with_python() {
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
      "$candidate" main.py desk "$PAPERS"
      return $?
    fi
  done
  return 127
}

if command -v uv >/dev/null 2>&1; then
  run_with_uv
else
  run_with_python
fi
STATUS=$?

if [ $STATUS -ne 0 ]; then
  echo ""
  echo "  ---------------------------------------------------------------"
  echo "  The review desk could not start."
  echo ""
  echo "  This usually means Python is not installed yet, or the tool's"
  echo "  own packages have not been set up on this computer."
  echo ""
  echo "  Send this whole window to whoever set the tool up for you —"
  echo "  the lines above say what went wrong."
  echo "  ---------------------------------------------------------------"
  echo ""
  echo "  Press Return to close this window."
  read -r _
fi
