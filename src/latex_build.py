"""Compile the auto-fixed .tex into a PDF inside the aiagent_prescreen/ folder.

Build strategy
--------------
1. Create ``<out_dir>/build/`` and copy into it:
   - all files from ``Source_Files/`` (original .tex + any included files)
   - all files from ``Supporting_files_for_papers/`` (images, etc.)
   - the BibTeX file (from ``BibTeX_file_only_for_LaTeX_papers/``) if present
   - the latest ``jacow.cls``, ``jacow.bbx``, ``jacow.cbx`` from the asset cache
   - the edited .tex (overwrites the original so the build uses the fixed source)
2. Run ``latexmk -pdf`` (preferred) or fall back to ``pdflatex`` + ``biber`` /
   ``pdflatex`` (twice) in the build directory.
3. Copy the produced PDF to ``<out_dir>/<paper_id>_edited.pdf``.
4. Return a ``BuildResult`` with success flag, log excerpt, and PDF path.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class BuildResult:
    success: bool
    pdf_path: Path | None = None
    log_excerpt: str = ""
    errors: list[str] = field(default_factory=list)


def compile_tex(
    paper_folder: Path,
    edited_tex: Path,
    paper_id: str,
    out_dir: Path,
    *,
    use_biblatex: bool = False,
) -> BuildResult:
    """Compile *edited_tex* and place the PDF in *out_dir*.

    Parameters
    ----------
    paper_folder:
        Root submission folder (contains ``Source_Files/``, etc.).
    edited_tex:
        Path to the auto-fixed ``.tex`` file (inside ``out_dir``).
    paper_id:
        Short paper identifier, used to name the output PDF.
    out_dir:
        The ``aiagent_prescreen/`` directory.
    use_biblatex:
        When ``True`` the build uses ``biber`` for bibliography processing.
    """
    # --- 1. Ensure class files are available ---
    from src.assets.cls_manager import ensure_cls_files
    try:
        cls_dir = ensure_cls_files()
    except RuntimeError as exc:
        return BuildResult(success=False, errors=[str(exc)])

    # --- 2. Set up build directory (always clean to avoid stale artefacts) ---
    build_dir = out_dir / "build"
    if build_dir.exists():
        shutil.rmtree(build_dir)
    build_dir.mkdir()

    # Collect image files from supporting dirs before copying
    image_files: list[Path] = []
    for src_subdir in ("Source_Files", "Supporting_files_for_papers"):
        src_path = paper_folder / src_subdir
        if src_path.is_dir():
            _copy_dir_contents(src_path, build_dir)
            for f in src_path.iterdir():
                if f.is_file() and f.suffix.lower() in {
                    ".png", ".jpg", ".jpeg", ".pdf", ".eps", ".svg"
                }:
                    image_files.append(f)

    # Copy bib file
    bib_dir = paper_folder / "BibTeX_file_only_for_LaTeX_papers"
    if bib_dir.is_dir():
        _copy_dir_contents(bib_dir, build_dir)

    # Copy JACoW class files
    # (bib name-fix happens after edited .tex is in place — see below)
    for cls_file in cls_dir.iterdir():
        if cls_file.suffix in {".cls", ".bbx", ".cbx"}:
            shutil.copy2(cls_file, build_dir / cls_file.name)

    # Copy edited .tex (overwrites original in build dir)
    shutil.copy2(edited_tex, build_dir / f"{paper_id}.tex")

    # Resolve \addbibresource name mismatches: if the tex names a .bib file
    # that isn't present in the build dir, copy the actual bib under that name.
    _fix_bib_resource_names(build_dir / f"{paper_id}.tex", build_dir)

    # Extract any zip archives (e.g. zipped figure bundles) into the build dir
    # preserving their internal directory structure (figs/, images/, …)
    image_files.extend(_extract_zips(build_dir))

    # Mirror images into every subdirectory referenced by \includegraphics
    _setup_figure_dirs(build_dir / f"{paper_id}.tex", build_dir, image_files)

    # --- 3. Run LaTeX ---
    tex_file = build_dir / f"{paper_id}.tex"
    result = _run_latex(tex_file, build_dir, use_biblatex=use_biblatex)

    # --- 4. Copy PDF to out_dir ---
    built_pdf = build_dir / f"{paper_id}.pdf"
    if built_pdf.exists():
        dest = out_dir / f"{paper_id}_edited.pdf"
        shutil.copy2(built_pdf, dest)
        result.pdf_path = dest

    return result


def _setup_figure_dirs(tex: Path, build_dir: Path, image_files: list[Path]) -> None:
    """Create subdirs expected by ``\\includegraphics`` and populate with images.

    Authors often submit figures in a flat ``Supporting_files_for_papers/``
    folder but reference them via a relative path like ``figures/fig1.png``.
    This scans the compiled tex for all such prefixes and mirrors every image
    into each required subdirectory so the build can resolve them.
    """
    if not image_files:
        return
    content = tex.read_text(encoding="utf-8", errors="replace")

    # Collect unique directory prefixes from \includegraphics{path/to/img}
    subdirs: set[str] = set()
    for m in re.finditer(r'\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}', content):
        parent = Path(m.group(1)).parent
        if str(parent) not in {".", ""}:
            subdirs.add(str(parent))

    # Also honour explicit \graphicspath{{dir1/}{dir2/}}
    for gm in re.finditer(r'\\graphicspath\{(.*?)\}', content, re.DOTALL):
        for dm in re.finditer(r'\{([^}]+)\}', gm.group(1)):
            d = dm.group(1).strip("/").strip()
            if d and d != ".":
                subdirs.add(d)

    for subdir in subdirs:
        target = build_dir / subdir
        target.mkdir(parents=True, exist_ok=True)
        for img in image_files:
            dest = target / img.name
            if not dest.exists():
                shutil.copy2(img, dest)


def _fix_bib_resource_names(tex: Path, build_dir: Path) -> None:
    """Ensure every ``\\addbibresource{name.bib}`` in *tex* resolves in *build_dir*.

    Authors sometimes name the bib file differently from what they declare in
    ``\\addbibresource`` (e.g. submit ``MOP030.bib`` but write
    ``\\addbibresource{references.bib}``).  When there is exactly one ``.bib``
    in *build_dir* and the expected name is missing, copy the bib under the
    expected name so Biber / BibTeX can find it.
    """
    content = tex.read_text(encoding="utf-8", errors="replace")
    expected_names = re.findall(r'\\addbibresource\{([^}]+\.bib)\}', content)
    if not expected_names:
        return

    present_bibs = list(build_dir.glob("*.bib"))
    if not present_bibs:
        return

    for name in expected_names:
        target = build_dir / name
        if not target.exists():
            # Use the first (usually only) bib present as the source
            shutil.copy2(present_bibs[0], target)


def _extract_zips(build_dir: Path) -> list[Path]:
    """Extract every .zip archive found directly inside *build_dir* in place.

    The zip's internal directory structure is preserved, so a bundle like
    ``MOP030_fig.zip`` that contains ``figs/fig1.png`` will produce
    ``build_dir/figs/fig1.png`` — exactly where ``\\includegraphics{figs/fig1}``
    expects to find it.

    Returns a list of image files unpacked from the archives so they can be
    added to the ``image_files`` pool consumed by ``_setup_figure_dirs``.
    """
    _IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".pdf", ".eps", ".svg"}
    extracted: list[Path] = []

    for zip_path in list(build_dir.glob("*.zip")):
        try:
            with zipfile.ZipFile(zip_path) as zf:
                members = zf.infolist()
                zf.extractall(build_dir)
            for info in members:
                p = build_dir / info.filename
                if p.is_file() and p.suffix.lower() in _IMAGE_EXTS:
                    extracted.append(p)
        except Exception:
            pass  # corrupt / unsupported zip — skip silently

    return extracted


def _copy_dir_contents(src: Path, dst: Path) -> None:
    """Copy all files from *src* (flat) into *dst*, preserving nothing."""
    for item in src.iterdir():
        if item.is_file():
            shutil.copy2(item, dst / item.name)
        elif item.is_dir():
            # Recurse one level for typical image subdirs
            sub_dst = dst / item.name
            sub_dst.mkdir(exist_ok=True)
            for sub_item in item.iterdir():
                if sub_item.is_file():
                    shutil.copy2(sub_item, sub_dst / sub_item.name)


def _run_latex(tex: Path, cwd: Path, *, use_biblatex: bool) -> BuildResult:
    """Try latexmk first, then fall back to a manual pdflatex/biber sequence."""
    latexmk = shutil.which("latexmk")
    if latexmk:
        return _run_latexmk(tex, cwd)
    return _run_pdflatex_sequence(tex, cwd, use_biblatex=use_biblatex)


# ---- latexmk ---------------------------------------------------------------

def _run_latexmk(tex: Path, cwd: Path) -> BuildResult:
    cmd = [
        "latexmk", "-pdf",
        "-interaction=nonstopmode",
        "-halt-on-error",
        tex.name,
    ]
    proc = subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=120
    )
    log_excerpt = _extract_errors(proc.stdout + proc.stderr)
    errors = _parse_latex_errors(proc.stdout + proc.stderr)
    return BuildResult(
        success=proc.returncode == 0,
        log_excerpt=log_excerpt,
        errors=errors,
    )


# ---- manual pdflatex sequence ----------------------------------------------

def _run_pdflatex_sequence(
    tex: Path, cwd: Path, *, use_biblatex: bool
) -> BuildResult:
    pdflatex = shutil.which("pdflatex")
    if not pdflatex:
        return BuildResult(
            success=False,
            errors=["Neither latexmk nor pdflatex found. "
                    "Install a LaTeX distribution (e.g. TeX Live, MiKTeX)."],
        )

    def _pdf(extra_args: list[str] | None = None) -> subprocess.CompletedProcess:
        cmd = ["pdflatex", "-interaction=nonstopmode"] + (extra_args or []) + [tex.name]
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                                 encoding="utf-8", errors="replace", timeout=120)

    # First pass
    r1 = _pdf()
    combined = r1.stdout + r1.stderr

    if use_biblatex:
        biber = shutil.which("biber")
        if biber:
            stem = tex.stem
            subprocess.run(["biber", stem], cwd=cwd,
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60)
        else:
            combined += "\nWarning: biber not found; bibliography may be incomplete."
    else:
        # bibtex pass
        bibtex = shutil.which("bibtex")
        if bibtex:
            subprocess.run(["bibtex", tex.stem], cwd=cwd,
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60)

    # Second pass
    r2 = _pdf()
    combined += r2.stdout + r2.stderr

    # Third pass for cross-references
    r3 = _pdf()
    combined += r3.stdout + r3.stderr

    return BuildResult(
        success=r3.returncode == 0,
        log_excerpt=_extract_errors(combined),
        errors=_parse_latex_errors(combined),
    )


# ---- log helpers -----------------------------------------------------------

_ERROR_PAT = re.compile(r'^! .*', re.MULTILINE)
_WARN_PAT  = re.compile(r'^LaTeX Warning:.*', re.MULTILINE)


def _extract_errors(log: str) -> str:
    """Return the last 40 lines of the log."""
    lines = log.splitlines()
    return "\n".join(lines[-40:])


def _parse_latex_errors(log: str) -> list[str]:
    errors = _ERROR_PAT.findall(log)
    return errors[:20]  # cap to avoid huge lists
