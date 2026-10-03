"""Builds the About BIS PDF from the approved PDF in assets/about_bis_template.pdf.

Only four pages change for each quotation (page numbers of the template):
    7  applicable standards table      8  what the standards cover (Scope pictures)
    13 approved laboratories           14 number of current licensees
Everything else is copied unchanged.
"""

import math
import os

import fitz  # PyMuPDF

BASE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(BASE, "assets", "about_bis_template.pdf")
FONT_REGULAR = os.path.join(BASE, "assets", "fonts", "Carlito-Regular.ttf")   # same metrics as Calibri
FONT_BOLD = os.path.join(BASE, "assets", "fonts", "Carlito-Bold.ttf")
MAX_STANDARDS = 9
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]
BLACK = (0, 0, 0)


class Fonts:
    def __init__(self):
        self.regular = fitz.Font(fontfile=FONT_REGULAR)
        self.bold = fitz.Font(fontfile=FONT_BOLD)
        self.arial = fitz.Font("helv")          # Helvetica: same widths as Arial

    def install(self, page):
        page.insert_font(fontname="carlito", fontfile=FONT_REGULAR)
        page.insert_font(fontname="carlitob", fontfile=FONT_BOLD)


def ordinal(day):
    return "th" if 10 <= day % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")


def is_label(std):
    return f"IS {std['number']}: {std['year']}"


def heading_label(stds):
    """'IS 17632-35 : 2022' for consecutive numbers of one year, else every number listed."""
    if len(stds) == 1:
        return f"IS {stds[0]['number']} : {stds[0]['year']}"
    try:
        nums = [int(s["number"]) for s in stds]
        same_year = len({s["year"] for s in stds}) == 1
        consecutive = all(b == a + 1 for a, b in zip(nums, nums[1:]))
        if same_year and consecutive and len(str(nums[0])) == len(str(nums[-1])):
            return f"IS {nums[0]}-{str(nums[-1])[-2:]} : {stds[0]['year']}"
    except ValueError:
        pass
    return ", ".join(f"IS {s['number']} : {s['year']}" for s in stds)


def _clear(page, rect, images=fitz.PDF_REDACT_IMAGE_NONE):
    page.add_redact_annot(rect, fill=None)
    page.apply_redactions(images=images, graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED)


def _text(page, x, y, text, fonts, size, bold=False):
    page.insert_text((x, y), text, fontname="carlitob" if bold else "carlito", fontsize=size)


def _centered(page, cx, y, text, fonts, size, bold=False):
    font = fonts.bold if bold else fonts.regular
    _text(page, cx - font.text_length(text, fontsize=size) / 2, y, text, fonts, size, bold)


def _line(page, p1, p2):
    page.draw_line(p1, p2, color=BLACK, width=1)


def _grid(page, xs, top, header_bottom, row_h, n):
    bottom = header_bottom + n * row_h
    for x in xs:
        _line(page, (x, top), (x, bottom))
    _line(page, (xs[0], top), (xs[-1], top))
    _line(page, (xs[0], header_bottom), (xs[-1], header_bottom))
    for i in range(1, n + 1):
        _line(page, (xs[0], header_bottom + i * row_h), (xs[-1], header_bottom + i * row_h))
    return bottom


def _date(page, cx, y, d, fonts, size):
    day, suffix, rest = str(d.day), ordinal(d.day), f" {MONTHS[d.month - 1]} {d.year}"
    small = size * 0.67
    w1, w2, w3 = (fonts.regular.text_length(day, fontsize=size),
                  fonts.regular.text_length(suffix, fontsize=small),
                  fonts.regular.text_length(rest, fontsize=size))
    x = cx - (w1 + w2 + w3) / 2
    _text(page, x, y, day, fonts, size)
    _text(page, x + w1, y - size * 0.28, suffix, fonts, small)
    _text(page, x + w1 + w2, y, rest, fonts, size)


def _fit_centered(page, cx, y, text, fonts, size, max_width):
    while size > 12 and fonts.regular.text_length(text, fontsize=size) > max_width:
        size -= 0.5
    _centered(page, cx, y, text, fonts, size)


# ---------------- page 7: applicable standards ----------------

def _page_standards(doc, stds, fonts):
    page = doc[6]
    _clear(page, fitz.Rect(140, 146, 1176, 382))
    fonts.install(page)
    xs = [149, 200, 416, 872, 1164]
    n = len(stds)
    row_h = 36.5 if n <= 6 else 30
    size = 23 if row_h > 31 else 20
    _grid(page, xs, 152, 229, row_h, n)
    _centered(page, 174.5, 190, "S.", fonts, 23, bold=True)
    _centered(page, 174.5, 218, "No.", fonts, 23, bold=True)
    _centered(page, 308, 192, "Indian", fonts, 23)
    _centered(page, 308, 219, "Standard", fonts, 23)
    _centered(page, 644, 191, "Description of Indian Standard", fonts, 23)
    for dy, line in ((172, "Date of Implementation For"), (195, "Foreign applicants/Large"), (218, "scale companies")):
        _centered(page, 1018, dy, line, fonts, 23, bold=True)
    for i, s in enumerate(stds):
        y = 229 + i * row_h + row_h * 0.64
        _centered(page, 174.5, y, str(i + 1), fonts, size)
        _centered(page, 308, y, is_label(s), fonts, size)
        _fit_centered(page, 644, y, s["description"], fonts, size, 440)
        _date(page, 1018, y, s["impl_date"], fonts, size)


# ---------------- page 8: scope pictures ----------------

def _scope_size(std):
    """(width, height) of the scope picture(s) stacked, in page units at scale 1, plus the parts."""
    if std.get("scope_image"):
        pix = fitz.Pixmap(std["scope_image"])
        return pix.width * 0.75, pix.height * 0.75, None
    parts = [(pno, clip) for pno, clip in std["segments"]]
    width = max(c.width for _, c in parts)
    height = sum(c.height for _, c in parts) + 6 * (len(parts) - 1)
    return width, height, parts


def _page_scope(doc, stds, fonts):
    page = doc[7]
    _clear(page, fitz.Rect(150, 90, 1042, 705), images=fitz.PDF_REDACT_IMAGE_REMOVE)
    fonts.install(page)
    n = len(stds)
    cols = 1 if n == 1 else (2 if n <= 4 else 3)
    rows = math.ceil(n / cols)
    x0, x1, y0, y1 = 40, 1040, 92, 700
    cw, ch = (x1 - x0) / cols, (y1 - y0) / rows
    label_size = 28 if cols < 3 else 22
    for i, std in enumerate(stds):
        r, c = divmod(i, cols)
        left, top = x0 + c * cw, y0 + r * ch
        cx = left + cw / 2
        _centered(page, cx, top + label_size, is_label(std), fonts, label_size)
        box_top, box_h, box_w = top + label_size + 12, ch - label_size - 22, cw - 24
        w, h, parts = _scope_size(std)
        scale = min(box_w / w, box_h / h, 2.0)
        draw_w = w * scale
        y = box_top
        if parts is None:
            page.insert_image(fitz.Rect(cx - draw_w / 2, y, cx + draw_w / 2, y + h * scale), stream=std["scope_image"])
        else:
            for pno, clip in parts:
                part_w, part_h = clip.width * scale, clip.height * scale
                page.show_pdf_page(fitz.Rect(cx - part_w / 2, y, cx + part_w / 2, y + part_h),
                                   std["scope_doc"], pno, clip=clip)
                y += part_h + 6 * scale


# ---------------- page 13: laboratories ----------------

def _wrap(text, font, size, max_width):
    words, lines, cur = text.split(), [], ""
    for word in words:
        trial = f"{cur} {word}".strip()
        if cur and font.text_length(trial, fontsize=size) > max_width:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    return lines + [cur]


def _page_labs(doc, stds, labs, etc, fonts):
    page = doc[12]
    _clear(page, fitz.Rect(320, 168, 1000, 600))
    heading = heading_label(stds)
    size = 28
    while size > 16 and fonts.regular.text_length(heading, fontsize=size) > 640:
        size -= 1
    w = fonts.regular.text_length(heading, fontsize=size)
    page.insert_font(fontname="carlito", fontfile=FONT_REGULAR)
    page.insert_text((570 - w / 2, 180), heading, fontname="carlito", fontsize=size)
    _line(page, (570 - w / 2, 184), (570 + w / 2, 184))

    labs = list(labs[:10])
    if labs and etc:
        labs[-1] += ", etc"
    y = 225
    for lab in labs:
        for j, text in enumerate(_wrap(lab, fonts.arial, 24, 590)):
            if j == 0:
                page.draw_circle((336, y - 8), 3, color=BLACK, fill=BLACK)
            page.insert_text((354, y), text, fontname="helv", fontsize=24)
            y += 29.7


# ---------------- page 14: current licensees ----------------

def _page_licensees(doc, stds, fonts):
    page = doc[13]
    _clear(page, fitz.Rect(110, 174, 1120, 404))
    fonts.install(page)
    xs = [121, 181, 410, 847, 950, 1108]
    n = len(stds)
    row_h = 36.5 if n <= 5 else 30
    size = 23 if row_h > 31 else 20
    _grid(page, xs, 180, 257, row_h, n)
    _centered(page, 151, 219, "S. No.", fonts, 22, bold=True)
    _centered(page, 295.5, 220, "Indian Standard", fonts, 23)
    _centered(page, 628.5, 219, "Description of Indian Standard", fonts, 23)
    _centered(page, 898.5, 219, "In India", fonts, 23)
    _centered(page, 1029, 219, "Outside India", fonts, 23)
    _centered(page, 1029, 249, "(FMCS)", fonts, 23)
    for i, s in enumerate(stds):
        y = 257 + i * row_h + row_h * 0.64
        _centered(page, 151, y, str(i + 1), fonts, size)
        _centered(page, 295.5, y, is_label(s), fonts, size)
        _fit_centered(page, 628.5, y, s["description"], fonts, size, 420)
        _centered(page, 898.5, y, f"{int(s['india']):02d}", fonts, size)
        _centered(page, 1029, y, f"{int(s['fmcs']):02d}", fonts, size)


def build_about_bis(stds, labs, labs_etc):
    """stds: list of dicts (number, year, description, impl_date, india, fmcs, scope_doc+segments or scope_image)."""
    if not stds:
        raise ValueError("At least one standard is needed.")
    if len(stds) > MAX_STANDARDS:
        raise ValueError(f"The About BIS PDF supports up to {MAX_STANDARDS} standards at a time.")
    doc = fitz.open(TEMPLATE)
    fonts = Fonts()
    _page_standards(doc, stds, fonts)
    _page_scope(doc, stds, fonts)
    _page_labs(doc, stds, labs, labs_etc, fonts)
    _page_licensees(doc, stds, fonts)
    out = doc.tobytes(garbage=3, deflate=True)
    doc.close()
    return out
