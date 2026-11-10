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

# Which desk?
#  * Editors working from the chief editor's desk set nothing up here: once
#    this Mac has joined the chief's desk (see the editor guide), this file
#    opens that desk again, and it keeps the papers you take by itself.
#  * Working alone on a folder of papers: name it on the first line of
#    papers_folder.txt next to this file. Otherwise the desk works in a folder
#    called "submissions" next to this file; drop papers straight into it.
PAPERS="$1"
if [ -z "$PAPERS" ] && [ -f papers_folder.txt ]; then
  PAPERS="$(head -n 1 papers_folder.txt | tr -d '\r')"
  if [ ! -d "$PAPERS" ]; then
    echo ""
    echo "  The papers folder named in papers_folder.txt is not available:"
    echo "    $PAPERS"
    echo ""
    echo "  If it is shared from another computer, connect to it first"
    echo "  (Finder > Go > Connect to Server), then start the desk again."
    echo ""
    echo "  Press Return to close this window."
    read -r _
    exit 1
  fi
fi
if [ -n "$PAPERS" ]; then
  ARGS=("$PAPERS")
else
  # No folder named: the chief's desk this Mac joined, else the folder used
  # last, else "submissions" (or the examples shipped with the tool).
  ALONE="submissions"
  if [ ! -d "$ALONE" ] && [ -d "paper_examples" ]; then
    ALONE="paper_examples"
  fi
  ARGS=(--alone-in "$ALONE")
fi

echo ""
echo "  Starting the JACoW review desk…"
[ -n "$PAPERS" ] && echo "  Papers folder: $PAPERS"
echo ""

run_with_uv() { uv run --quiet python main.py "${ARGS[@]}"; }
run_with_python() {
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
      "$candidate" main.py "${ARGS[@]}"
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
