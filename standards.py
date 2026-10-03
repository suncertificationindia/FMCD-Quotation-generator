"""Reads a BIS standard PDF: its number, year, name, and the position of its '1 SCOPE' section."""

import re

import fitz  # PyMuPDF

IS_RE = re.compile(r"IS\s*(\d{3,6})\s*(?:\(\s*Part\s*(\d+)\s*\))?\s*:\s*(\d{4})", re.I)
SCOPE_RE = re.compile(r"^\s*1\.?\s*SCOPE\b", re.I)
NEXT_HEADING_RE = re.compile(r"^\s*2\.?\s*[A-Z][A-Z]{3,}")   # "2 REFERENCES"
MAX_SCAN_PAGES = 14


def open_pdf(data):
    try:
        return fitz.open(stream=data, filetype="pdf")
    except Exception:
        raise ValueError("This file could not be opened as a PDF.")


def _lines(page):
    """Text lines of a page (without running headers and footers): [(Rect, text)]."""
    out = []
    for block in page.get_text("dict")["blocks"]:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            text = "".join(span["text"] for span in line["spans"]).strip()
            if not text:
                continue
            rect = fitz.Rect(line["bbox"])
            if rect.y0 < 52 or rect.y1 > page.rect.height - 62:
                continue
            out.append((rect, text))
    return out


def _column(page, rect):
    return 0 if rect.x0 < page.rect.width * 0.5 else 1


def find_scope(doc):
    """Return (segments, title_lines). segments = [(page_number, clip Rect), ...] or []."""
    for pno in range(1, min(len(doc), MAX_SCAN_PAGES)):
        page = doc[pno]
        lines = _lines(page)
        heading = next(((r, t) for r, t in lines if SCOPE_RE.match(t)), None)
        if not heading:
            continue
        h_rect = heading[0]
        title_lines = [t for r, t in lines
                       if r.y1 <= h_rect.y0 + 1 and not re.fullmatch(r"[\d\s]*", t)
                       and not IS_RE.search(t) and t.lower() != "indian standard"]

        segments, cur_page, cur_col, start_y = [], pno, _column(page, h_rect), h_rect.y0
        for _ in range(3):
            pg = doc[cur_page]
            in_col = sorted(((r, t) for r, t in _lines(pg)
                             if _column(pg, r) == cur_col and r.y0 >= start_y - 1),
                            key=lambda item: item[0].y0)
            taken, ended = [], False
            for r, t in in_col:
                if taken and NEXT_HEADING_RE.match(t):
                    ended = True
                    break
                taken.append(r)
            if taken:
                clip = fitz.Rect(taken[0])
                for r in taken[1:]:
                    clip |= r
                segments.append((cur_page, clip + (-6, -4, 6, 4)))
            if ended:
                return segments, title_lines
            has_right = cur_col == 0 and any(_column(pg, r) == 1 for r, _ in _lines(pg))
            if has_right:
                cur_col, start_y = 1, 0
            elif cur_page + 1 < len(doc):
                cur_page, cur_col, start_y = cur_page + 1, 0, 0
            else:
                break
        return segments, title_lines      # end heading never found: use what was collected
    return [], []


def clean_title(title_lines):
    """'GENERAL PURPOSE CHAIRS AND STOOLS - SPECIFICATION' -> 'General purpose chairs and stools'."""
    text = " ".join(title_lines)
    text = re.split(r"\s[—–-]\s|—|–", text)[0].strip()
    text = re.sub(r"\s+", " ", text)
    return (text[:1].upper() + text[1:].lower()) if text else ""


def read_standard(data):
    """Returns dict: is_number, year, description, segments, warnings (doc must be opened again to draw)."""
    doc = open_pdf(data)
    warnings = []
    cover = doc[0].get_text() if len(doc) else ""
    m = IS_RE.search(cover)
    info = {"is_number": None, "year": None, "description": "", "segments": [], "warnings": warnings}
    if m:
        info["is_number"] = m.group(1) + (f" (Part {m.group(2)})" if m.group(2) else "")
        info["year"] = m.group(3)
    else:
        warnings.append("Could not read the IS number and year from the first page. Please type the year.")
    segments, title_lines = find_scope(doc)
    info["description"] = clean_title(title_lines)
    if not info["description"]:
        warnings.append("Could not read the name of the standard. Please type it.")
    info["segments"] = segments
    if not segments:
        warnings.append("Could not find the '1 SCOPE' section. Please upload a picture of the Scope instead.")
    doc.close()
    return info


def scope_previews(data, segments, dpi=130):
    """PNG bytes of each scope segment (for the on-screen preview)."""
    doc = open_pdf(data)
    try:
        return [doc[pno].get_pixmap(clip=clip, dpi=dpi).tobytes("png") for pno, clip in segments]
    finally:
        doc.close()


def same_standard(expected, found):
    """True if the typed IS number and the one read from the PDF are the same standard."""
    def digits(s):
        return re.sub(r"\D", "", re.sub(r"(?i)^\s*IS\s*", "", s or "").split("(")[0])
    return not found or digits(expected) == digits(found)
