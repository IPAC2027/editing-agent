#!/usr/bin/env python3
"""Audit a .docx against the JACoW MS Word style guide (what can be checked mechanically).

Usage: python audit_jacow_docx.py paper.docx [--json]
Reports PASS/WARN/FAIL lines. Does not modify the file.
Checks: body justification, 0.33 cm first-line indent, widow control, page size, margins, columns, fonts, font sizes, page-number fields,
Word footnotes, DOI hyperlinks, reference line spacing, title casing.
"""
import re, sys, json, zipfile
from collections import Counter
from docx import Document
from docx.shared import Mm, Pt

ALLOWED_FONTS = {"Times New Roman", "Times", "Symbol", "Liberation Mono"}
TOL_MM = 0.6
results = []

def add(level, msg):
    results.append((level, msg))

def mm(emu):
    return emu / 36000.0 if emu is not None else None

def near(a, b, tol=TOL_MM):
    return a is not None and abs(a - b) <= tol

def check_page(doc):
    for i, s in enumerate(doc.sections, 1):
        w, h = s.page_width.pt, s.page_height.pt
        ok = abs(w - 595) < 2 and abs(h - 792) < 2
        add("PASS" if ok else "FAIL", f"Section {i}: page {w:.0f} x {h:.0f} pt (expected 595 x 792)")
        exp = {"top": 19, "bottom": 19, "left": 20, "right": 20}
        got = {"top": mm(s.top_margin), "bottom": mm(s.bottom_margin),
               "left": mm(s.left_margin), "right": mm(s.right_margin)}
        bad = [f"{k} {v:.1f} mm (want {exp[k]})" for k, v in got.items() if not near(v, exp[k])]
        add("PASS" if not bad else "FAIL", f"Section {i}: margins " + ("OK" if not bad else "; ".join(bad)))
        cols = s._sectPr.xpath("./w:cols")
        if cols:
            c = cols[0]
            num = int(c.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}num", "1"))
            space = c.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}space")
            sp_mm = int(space) * 25.4 / 1440 if space else None
            if num == 2:
                add("PASS" if near(sp_mm, 5.3, 0.8) else "WARN",
                    f"Section {i}: 2 columns, gap {sp_mm if sp_mm is None else round(sp_mm,1)} mm (want 5.3)")
            else:
                add("INFO", f"Section {i}: {num} column(s) (one-column is expected only for full-width figures/title block)")
        else:
            add("INFO", f"Section {i}: single column")

def run_font(run, para):
    return run.font.name or (para.style.font.name if para.style is not None else None)

def check_fonts(doc):
    fonts, sizes = Counter(), Counter()
    for p in doc.paragraphs:
        for r in p.runs:
            if not r.text.strip():
                continue
            f = run_font(r, p)
            sz = r.font.size.pt if r.font.size else (p.style.font.size.pt if p.style is not None and p.style.font.size else None)
            fonts[f] += len(r.text)
            sizes[sz] += len(r.text)
    bad = {f: n for f, n in fonts.items() if f and f not in ALLOWED_FONTS}
    add("PASS" if not bad else "FAIL", "Fonts: " + (", ".join(f"{k or 'default'}={v}" for k, v in fonts.most_common())))
    if bad:
        add("FAIL", "Non-approved fonts: " + ", ".join(bad))
    if None in fonts:
        try:
            sx = zipfile.ZipFile(sys.argv[1]).read("word/styles.xml").decode("utf8", "ignore")
            dd = re.search(r"<w:docDefaults>.*?</w:docDefaults>", sx, re.S)
            fam = re.search(r'w:ascii="([^"]+)"', dd.group(0)) if dd else None
            fam = fam.group(1) if fam else None
        except Exception:
            fam = None
        if fam in ALLOWED_FONTS:
            add("PASS", f"Unset fonts inherit the document default ({fam})")
        else:
            add("WARN", f"Unset fonts inherit the document default ({fam or 'unknown'}); confirm it is Times New Roman")
    common = sizes.most_common(1)[0][0] if sizes else None
    if common is None:
        common = 10  # OOXML default when no size is set anywhere in the style chain
        add("INFO", "No explicit font size on body text; OOXML default (10 pt) applies")
    add("PASS" if common == 10 else "WARN", f"Dominant font size: {common} pt (body should be 10 pt)")

def check_zip(path):
    z = zipfile.ZipFile(path)
    names = z.namelist()
    for n in names:
        if n.startswith("word/footer") or n.startswith("word/header"):
            x = z.read(n).decode("utf8", "ignore")
            if re.search(r"PAGE|NUMPAGES", x) and ("fldChar" in x or "fldSimple" in x):
                add("FAIL", f"Page-number field found in {n} (JACoW forbids page numbers)")
    if "word/footnotes.xml" in names:
        x = z.read("word/footnotes.xml").decode("utf8", "ignore")
        real = re.findall(r'<w:footnote\b(?![^>]*w:type="(?:separator|continuationSeparator|continuationNotice)")[^>]*>', x)
        if real:
            add("FAIL", f"{len(real)} Word footnote(s) present; use text-box pseudo footnotes instead")
    doc_xml = z.read("word/document.xml").decode("utf8", "ignore")
    if "w:footnoteReference" in doc_xml:
        add("FAIL", "Word footnote references used in body")
    add("INFO", "Text boxes present (needed for footnotes): " + ("yes" if ("txbxContent" in doc_xml or "<w:pict" in doc_xml) else "no"))
    emb = ("word/fontTable.xml" in names and b"embedRegular" in z.read("word/fontTable.xml")) or \
          ("word/settings.xml" in names and b"embedTrueTypeFonts" in z.read("word/settings.xml"))
    add("PASS" if emb else "WARN", "Fonts embedded in file" if emb else "No embedded fonts detected; set Word Options -> Save -> Embed fonts in file")

def check_doi_links(doc, path):
    z = zipfile.ZipFile(path)
    rels = z.read("word/_rels/document.xml.rels").decode("utf8", "ignore")
    links = re.findall(r'Target="(https?://[^"]+)"[^>]*TargetMode="External"', rels)
    dois = [l for l in links if "doi.org" in l]
    other = [l for l in links if "doi.org" not in l]
    add("INFO", f"Hyperlinks: {len(dois)} DOI, {len(other)} non-DOI")
    if other:
        add("FAIL", "Non-DOI hyperlinks are prohibited: " + "; ".join(other[:5]))
    text = "\n".join(p.text for p in doc.paragraphs)
    n_doi_text = len(re.findall(r"doi:\s*10\.\d{4,9}/\S+", text, re.I))
    if n_doi_text and len(dois) < n_doi_text:
        add("WARN", f"{n_doi_text} DOI strings in text but only {len(dois)} DOI hyperlinks")
    if n_doi_text and not re.search(r"Liberation Mono", z.read("word/document.xml").decode("utf8", "ignore")):
        add("WARN", "DOIs found but Liberation Mono is not used")

def check_structure(doc):
    paras = [p for p in doc.paragraphs if p.text.strip()]
    if not paras:
        return add("FAIL", "Empty document")
    title = paras[0].text.strip()
    letters = [c for c in title if c.isalpha()]
    upper_ratio = sum(c.isupper() for c in letters) / max(1, len(letters))
    add("PASS" if upper_ratio > 0.7 else "WARN", f"Title mostly uppercase ({upper_ratio:.0%}): {title[:60]!r}")
    sx = zipfile.ZipFile(sys.argv[1]).read("word/styles.xml").decode("utf8", "ignore")
    def style_caps(st):
        while st is not None:
            m = re.search(r'<w:style [^>]*w:styleId="%s".*?</w:style>' % re.escape(st.style_id), sx, re.S)
            if m and "<w:caps/>" in m.group(0):
                return True
            st = st.base_style
        return False
    heads = []
    for p in paras:
        t = p.text.strip()
        if len(t) < 60 and (t.isupper() or (p.style is not None and re.search(r"section heading", p.style.name, re.I) and style_caps(p.style))):
            heads.append(t.upper())
    add("INFO", "Uppercase section headings: " + ", ".join(heads[:15]))
    for need in ("REFERENCES",):
        add("PASS" if need in heads else "WARN", f"{need} section {'found' if need in heads else 'not found'}")
    order = [h for h in heads if h in ("CONCLUSION", "ACKNOWLEDGEMENTS", "ACKNOWLEDGMENTS", "APPENDIX", "REFERENCES")]
    if "CONCLUSION" in order and order.index("CONCLUSION") != 0:
        add("WARN", "CONCLUSION should directly precede ACKNOWLEDGEMENTS/APPENDIX/REFERENCES")
    abs_i = next((i for i, p in enumerate(paras) if p.text.strip().lower() == "abstract"), None)
    if abs_i is not None and abs_i + 1 < len(paras) and re.search(r"\[\d+", paras[abs_i + 1].text):
        add("FAIL", "Abstract contains a citation")
    # citations vs references
    text = "\n".join(p.text for p in paras)
    ref_i = next((i for i, p in enumerate(paras) if p.text.strip() == "REFERENCES"), None)
    if ref_i is not None:
        body = "\n".join(p.text for p in paras[:ref_i])
        refs = [p.text for p in paras[ref_i + 1:] if re.match(r"\s*\[\d+\]", p.text)]
        cited = []
        for grp in re.findall(r"\[([\d,\s\-\u2013]+)\]", body):
            for part in grp.split(","):
                part = part.strip().replace("\u2013", "-")
                if "-" in part:
                    a, b = part.split("-", 1)
                    if a.strip().isdigit() and b.strip().isdigit():
                        cited += list(range(int(a), int(b) + 1))
                elif part.isdigit():
                    cited.append(int(part))
        first_seen = list(dict.fromkeys(cited))
        add("PASS" if first_seen == sorted(first_seen) else "WARN",
            "Citations appear in ascending order of first use" if first_seen == sorted(first_seen) else f"Citation order: {first_seen}")
        uncited = sorted(set(range(1, len(refs) + 1)) - set(cited))
        add("PASS" if not uncited else "WARN", f"{len(refs)} reference entries; uncited: {uncited or 'none'}")
        spacing = [p.paragraph_format.line_spacing for p in paras[ref_i + 1:] if re.match(r"\s*\[\d+\]", p.text)]
        if spacing:
            ok = all(s is not None and hasattr(s, "pt") and abs(s.pt - 10.4) < 0.2 for s in spacing)
            add("PASS" if ok else "WARN", "Reference line spacing exactly 10.4 pt" if ok else "Reference line spacing should be 'exactly 10.4 pt'")
    for m in re.finditer(r"(?<![\w.])(Fig\.|Figure|Tab\.)\s?\d", text):
        if m.group(1) == "Tab.":
            add("FAIL", "'Tab.' used; Table is never abbreviated")
            break


def resolve(par, attr):
    """Resolve a paragraph_format attribute through the style inheritance chain."""
    v = getattr(par.paragraph_format, attr)
    st = par.style
    while v is None and st is not None:
        v = getattr(st.paragraph_format, attr)
        st = st.base_style
    return v

def check_paragraphs(doc):
    """Body paragraphs: justified, 0.33 cm first-line indent, widow/orphan control."""
    paras = [p for p in doc.paragraphs if p.text.strip()]
    start = next((i + 1 for i, p in enumerate(paras) if p.text.strip().lower() == "abstract"), 1)
    end = next((i for i, p in enumerate(paras) if p.text.strip() == "REFERENCES"), len(paras))
    body = []
    for p in paras[start:end]:
        t = p.text.strip()
        if len(t) < 80 or t.isupper() or re.match(r"(Figure|Fig\.|Table)\s*\d", t) or re.match(r"\s*(\[\d+\]|[\u2022\-\*]|\d+[.)])\s", t):
            continue
        if p.style is not None and re.search(r"head|caption|list|title", p.style.name, re.I):
            continue
        body.append(p)
    if not body:
        return add("INFO", "No body paragraphs identified for justification/indent checks")
    not_just, bad_indent, no_wc = [], [], []
    for p in body:
        al = resolve(p, "alignment")
        if al is None or int(al) != 3:  # WD_ALIGN_PARAGRAPH.JUSTIFY == 3
            not_just.append(p)
        fi = resolve(p, "first_line_indent")
        if fi is None or abs(fi.cm - 0.33) > 0.05:
            bad_indent.append(p)
        wc = resolve(p, "widow_control")
        if wc is False:
            no_wc.append(p)
    def snip(lst):
        return "; ".join(repr(p.text[:30]) for p in lst[:3])
    n = len(body)
    add("PASS" if not not_just else "FAIL", f"Body justification: {n - len(not_just)}/{n} paragraphs justified" + (f" (not justified: {snip(not_just)})" if not_just else ""))
    add("PASS" if not bad_indent else "FAIL", f"Body first-line indent 0.33 cm: {n - len(bad_indent)}/{n} paragraphs OK" + (f" (e.g. {snip(bad_indent)})" if bad_indent else ""))
    add("PASS" if not no_wc else "WARN", "Widow/orphan control on for body" if not no_wc else f"Widow/orphan control disabled on {len(no_wc)} paragraph(s); enable it, then check column tops/bottoms by eye")

def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    path = sys.argv[1]
    doc = Document(path)
    check_page(doc); check_fonts(doc); check_zip(path); check_doi_links(doc, path); check_structure(doc); check_paragraphs(doc)
    if "--json" in sys.argv:
        print(json.dumps(results, indent=1))
    else:
        for lvl, msg in results:
            print(f"[{lvl}] {msg}")
        c = Counter(l for l, _ in results)
        print(f"\nSummary: {c.get('FAIL',0)} fail, {c.get('WARN',0)} warn, {c.get('PASS',0)} pass")
        print("Manual checks still needed: caption placement, heading/column breaks, widows/orphans, text-box footnotes, figure fonts.")

if __name__ == "__main__":
    main()
