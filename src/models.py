"""Shared Pydantic data models."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field


class Severity(str, Enum):
    ERROR = "error"      # must fix before acceptance
    WARNING = "warning"  # should fix; editor decides
    INFO = "info"        # informational only


class Finding(BaseModel):
    check_id: str
    severity: Severity
    line: int | None = None        # 1-based source line, if known
    original: str | None = None    # original text snippet
    suggested: str | None = None   # proposed replacement
    message: str
    auto_fixed: bool = False


class Reference(BaseModel):
    n: int
    key: str                       # BibTeX key or "[n]" label
    ref_type: str = "unknown"      # proceedings|journal|arxiv|book|...
    authors: list[str] = Field(default_factory=list)
    title: str = ""
    container_title: str | None = None
    venue_location: str | None = None
    date: str | None = None
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None
    doi: str | None = None
    url: str | None = None
    paper_id: str | None = None
    notes: list[str] = Field(default_factory=list)
    raw_text: str = ""


class Paper(BaseModel):
    paper_id: str
    source_path: Path
    title: str = ""
    authors: list[str] = Field(default_factory=list)
    references: list[Reference] = Field(default_factory=list)
    # BibTeX keys in the order they first appear in the body text
    citation_order: list[str] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
