"""Write a ``.docx`` whose changes are Word's own tracked changes.

Why this exists
---------------
Word is the format most JACoW submissions arrive in, and the previous pipeline
abandoned it: for a Word paper it produced an HTML page of before/after cards
and no corrected document at all.  An editor's only option was to read the
suggestion in a browser and retype it into Word by hand.

A ``.docx`` containing ``w:ins`` and ``w:del`` runs opens in Word (and
LibreOffice, and Pages) with the Accept and Reject buttons the editor already
uses every day — one per edit, each attributable, each individually reversible,
with no new interface to learn and no export step.  ``python-docx`` was already
a dependency; it does not model revisions itself, so this module writes the
revision XML directly.

The mapping is deliberately literal:

* one :class:`~src.edits.Edit` becomes one ``w:del`` / ``w:ins`` pair;
* the revision author is ``JACoW prescreen (<CHECK-ID>)``, so Word's reviewing
  pane groups changes by the rule that produced them and the editor can accept
  every ``FMT-UNIT-01`` at once;
* character formatting is carried across from the character each fragment came
  from, so an italic journal title stays italic.
"""

from __future__ import annotations

import copy
import difflib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

try:
    import docx
    from docx.oxml.ns import qn
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "python-docx is required to write tracked changes. "
        "Install with: uv add python-docx"
    ) from exc

from src.edits import Edit

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


@dataclass
class ParagraphRewrite:
    """A whole-paragraph replacement to express as tracked changes."""

    paragraph_index: int
    before: str
    after: str
    author: str = "JACoW prescreen"
    note: str = ""


def _revision_id() -> int:
    """Monotonic revision ids; Word only requires them to be unique."""
    _revision_id.counter += 1  # type: ignore[attr-defined]
    return _revision_id.counter  # type: ignore[attr-defined]


_revision_id.counter = 1000  # type: ignore[attr-defined]


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _char_formats(paragraph) -> list:
    """One ``rPr`` element (or None) per character of the paragraph's text."""
    formats: list = []
    for run in paragraph.runs:
        rpr = run._element.find(qn("w:rPr"))
        formats.extend([rpr] * len(run.text))
    return formats


# python-docx renders a <w:tab/> element as "\t" and a <w:br/> as "\n" when it
# reads a paragraph, so those characters arrive here standing for elements
# rather than for literal text.  Writing them back as literal characters
# inside <w:t> looks right in a text dump but is not the same document: a
# numbered reference list uses a real tab element against a tab stop to get
# its hanging indent, and a literal tab does not honour it.
_ELEMENT_CHARS = {"\t": "w:tab", "\n": "w:br", "\v": "w:br"}


def _make_run(text: str, rpr, *, deleted: bool):
    """Build a ``w:r`` carrying *text*, as delText when *deleted*.

    Tabs and line breaks are emitted as the elements Word uses for them, so a
    rewritten paragraph keeps the layout of the one it replaced.
    """
    from docx.oxml import OxmlElement

    run = OxmlElement("w:r")
    if rpr is not None:
        run.append(copy.deepcopy(rpr))

    buffer: list[str] = []

    def _flush() -> None:
        if not buffer:
            return
        node = OxmlElement("w:delText" if deleted else "w:t")
        node.set(qn("xml:space"), "preserve")
        node.text = "".join(buffer)
        run.append(node)
        buffer.clear()

    for char in text:
        tag = _ELEMENT_CHARS.get(char)
        if tag is None:
            buffer.append(char)
            continue
        _flush()
        run.append(OxmlElement(tag))
    _flush()
    return run


def _runs_for_range(text: str, start_char: int, formats: list, *, deleted: bool) -> list:
    """Split *text* into runs so each keeps the formatting it had in the source.

    Emitting one run for a whole diff segment would flatten formatting: an
    italic journal title inside an unchanged segment would come back upright,
    silently editing the document while claiming to leave it alone.  So the
    segment is cut wherever the character-level ``rPr`` changes.
    """
    if not text:
        return []
    runs = []
    segment_start = 0
    current = formats[start_char] if 0 <= start_char < len(formats) else None
    for offset in range(1, len(text)):
        index = start_char + offset
        rpr = formats[index] if 0 <= index < len(formats) else None
        if rpr is not current:
            runs.append(_make_run(text[segment_start:offset], current, deleted=deleted))
            segment_start = offset
            current = rpr
    runs.append(_make_run(text[segment_start:], current, deleted=deleted))
    return runs


def _wrap_revision(tag: str, runs: list, author: str):
    from docx.oxml import OxmlElement

    element = OxmlElement(tag)
    element.set(qn("w:id"), str(_revision_id()))
    element.set(qn("w:author"), author)
    element.set(qn("w:date"), _timestamp())
    for run in runs:
        element.append(run)
    return element


def _rewrite_paragraph(paragraph, rewrite: ParagraphRewrite) -> int:
    """Replace *paragraph*'s content with a tracked before/after diff.

    Returns the number of revision blocks written.  The diff is computed on
    word boundaries rather than characters so the reviewing pane shows whole
    words changing, which is what an editor wants to judge.
    """
    from docx.oxml import OxmlElement

    formats = _char_formats(paragraph)
    original = "".join(run.text for run in paragraph.runs)
    if original != rewrite.before:
        # The paragraph is not what we diffed against; refuse rather than
        # scramble the document.
        return 0

    def _tokens(text: str) -> list[str]:
        return re.findall(r"\s+|\w+|[^\w\s]", text)

    before_tokens = _tokens(rewrite.before)
    after_tokens = _tokens(rewrite.after)

    # Character offset of each token, so formatting can be looked up.
    offsets: list[int] = []
    position = 0
    for token in before_tokens:
        offsets.append(position)
        position += len(token)

    def _rpr_at(char_index: int):
        if 0 <= char_index < len(formats):
            return formats[char_index]
        return formats[-1] if formats else None

    # Remove existing content, keeping paragraph properties.
    for child in list(paragraph._element):
        if child.tag != qn("w:pPr"):
            paragraph._element.remove(child)

    revisions = 0
    matcher = difflib.SequenceMatcher(a=before_tokens, b=after_tokens, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        anchor = offsets[i1] if i1 < len(offsets) else max(0, len(rewrite.before) - 1)

        if tag == "equal":
            text = "".join(before_tokens[i1:i2])
            for run in _runs_for_range(text, anchor, formats, deleted=False):
                paragraph._element.append(run)
            continue

        if tag in ("replace", "delete"):
            text = "".join(before_tokens[i1:i2])
            if text:
                paragraph._element.append(_wrap_revision(
                    "w:del",
                    _runs_for_range(text, anchor, formats, deleted=True),
                    rewrite.author,
                ))
                revisions += 1
        if tag in ("replace", "insert"):
            text = "".join(after_tokens[j1:j2])
            if text:
                # Inserted text has no source formatting; it inherits the
                # formatting of the character it is being inserted at.
                paragraph._element.append(_wrap_revision(
                    "w:ins",
                    [_make_run(text, _rpr_at(anchor), deleted=False)],
                    rewrite.author,
                ))
                revisions += 1

    return revisions


def _enable_revision_view(document) -> None:
    """Ask Word to show the reviewing pane when the file opens."""
    from docx.oxml import OxmlElement

    settings = document.settings.element
    for tag in ("w:trackChanges",):
        if settings.find(qn(tag)) is None:
            settings.append(OxmlElement(tag))


def write_tracked_docx(
    source_docx: Path,
    out_path: Path,
    rewrites: list[ParagraphRewrite],
) -> tuple[Path, int, list[ParagraphRewrite]]:
    """Copy *source_docx* to *out_path* with *rewrites* as tracked changes.

    Returns ``(path, revisions_written, skipped)``.  A rewrite is skipped when
    the paragraph no longer matches the text it was computed against — the
    document is never edited on a stale assumption.
    """
    document = docx.Document(str(source_docx))
    paragraphs = document.paragraphs
    written = 0
    skipped: list[ParagraphRewrite] = []

    for rewrite in rewrites:
        if not (0 <= rewrite.paragraph_index < len(paragraphs)):
            skipped.append(rewrite)
            continue
        count = _rewrite_paragraph(paragraphs[rewrite.paragraph_index], rewrite)
        if count:
            written += count
        else:
            skipped.append(rewrite)

    if written:
        _enable_revision_view(document)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(out_path))
    return out_path, written, skipped


def rewrites_from_edits(
    edits: list[Edit],
    paragraph_text: dict[int, str],
) -> list[ParagraphRewrite]:
    """Group span edits by paragraph into whole-paragraph rewrites.

    Word revisions are expressed against paragraph content, so several span
    edits inside one reference collapse into one paragraph rewrite — but the
    revision author still names every check that contributed, so the reviewing
    pane stays attributable.
    """
    by_paragraph: dict[int, list[Edit]] = {}
    for edit in edits:
        index = int(edit.file) if edit.file.isdigit() else -1
        by_paragraph.setdefault(index, []).append(edit)

    rewrites: list[ParagraphRewrite] = []
    for index, group in sorted(by_paragraph.items()):
        text = paragraph_text.get(index)
        if text is None:
            continue
        rewritten = text
        for edit in sorted(group, key=lambda e: e.start, reverse=True):
            rewritten = rewritten[:edit.start] + edit.after + rewritten[edit.end:]
        if rewritten == text:
            continue
        checks = ", ".join(sorted({edit.check_id for edit in group}))
        rewrites.append(ParagraphRewrite(
            paragraph_index=index,
            before=text,
            after=rewritten,
            author=f"JACoW prescreen ({checks})",
            note="; ".join(edit.message for edit in group),
        ))
    return rewrites
