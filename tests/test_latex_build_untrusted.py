"""A submission must not be able to run code through the LaTeX build.

Regression: every file the author sent was copied into the build directory
and latexmk was run there.  latexmk reads ``latexmkrc``/``.latexmkrc`` from
its working directory, and those files are Perl.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from src import latex_build


def test_rc_files_from_a_submission_are_deleted(tmp_path: Path):
    (tmp_path / "latexmkrc").write_text("system('touch pwned');", encoding="utf-8")
    (tmp_path / ".latexmkrc").write_text("system('touch pwned');", encoding="utf-8")
    nested = tmp_path / "figs"
    nested.mkdir()
    (nested / "LATEXMKRC").write_text("system('touch pwned');", encoding="utf-8")
    (tmp_path / "paper.tex").write_text("\\documentclass{article}", encoding="utf-8")

    removed = latex_build._remove_untrusted_config(tmp_path)

    assert len(removed) == 3
    assert not (tmp_path / "latexmkrc").exists()
    assert not (tmp_path / ".latexmkrc").exists()
    assert (tmp_path / "paper.tex").exists()


def test_latexmk_is_run_without_any_rc_file_and_without_shell_escape(tmp_path, monkeypatch):
    seen: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(latex_build.subprocess, "run", fake_run)
    latex_build._run_latexmk(tmp_path / "paper.tex", tmp_path)

    cmd = seen[0]
    assert cmd[0] == "latexmk" and "-norc" in cmd
    assert any("-no-shell-escape" in part for part in cmd)


def test_the_pdflatex_fallback_disables_shell_escape(tmp_path, monkeypatch):
    seen: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(latex_build.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(latex_build.subprocess, "run", fake_run)
    latex_build._run_pdflatex_sequence(tmp_path / "paper.tex", tmp_path, use_biblatex=False)

    pdflatex_calls = [c for c in seen if c[0] == "pdflatex"]
    assert pdflatex_calls and all("-no-shell-escape" in c for c in pdflatex_calls)
