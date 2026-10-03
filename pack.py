"""Builds the client document pack (zip): quotation + About Company PDF + fixed forms.

About Company PDF: the approved PDF in assets/about_company_template.pdf is used as it is,
except for the client-list page, whose text is replaced by the ranked list for this quotation.
"""

import io
import os
import re
import zipfile

import fitz  # PyMuPDF

import clients as client_list
from excel_io import build_workbook, workbook_to_bytes

BASE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(BASE, "assets")
ABOUT_COMPANY_TEMPLATE = os.path.join(ASSETS, "about_company_template.pdf")
FONT_FILE = os.path.join(ASSETS, "fonts", "Carlito-Regular.ttf")  # same metrics as Calibri

CLIENT_PAGE = 3                 # page 4 of the PDF (0-based index)
ROW_PITCH = 28.6                # distance between lines on the page
FIRST_BASELINE = 95.4
FONT_SIZE = 23
COLUMNS = (                     # (bullet x, text x, right edge) of the two columns
    (361.2, 390.7, 806.0),
    (810.0, 839.5, 1272.0),
)
REDACT_AREAS = (fitz.Rect(355, 66, 806, 706), fitz.Rect(806, 66, 1276, 706))


def safe_name(text):
    return re.sub(r'[\\/:*?"<>|]+', " ", text).strip() or "Client"


def build_about_company_pdf(ranked_clients):
    """Return the About Company PDF (bytes) with the client page rebuilt for this quotation."""
    doc = fitz.open(ABOUT_COMPANY_TEMPLATE)
    page = doc[CLIENT_PAGE]

    for area in REDACT_AREAS:
        page.add_redact_annot(area, fill=None)
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE)

    font = fitz.Font(fontfile=FONT_FILE)
    page.insert_font(fontname="carlito", fontfile=FONT_FILE)

    lines = [client_list.display_name(c) for c in ranked_clients]
    if lines:
        lines[-1] += " and many more."
    per_column = (len(lines) + 1) // 2
    for col_index, chunk in enumerate((lines[:per_column], lines[per_column:])):
        bullet_x, text_x, right_edge = COLUMNS[col_index]
        for row, text in enumerate(chunk):
            y = FIRST_BASELINE + row * ROW_PITCH
            size = FONT_SIZE
            while size > 14 and font.text_length(text, fontsize=size) > right_edge - text_x:
                size -= 0.5
            page.insert_text((bullet_x, y), "•", fontname="carlito", fontsize=FONT_SIZE)
            page.insert_text((text_x, y), text, fontname="carlito", fontsize=size)

    out = doc.tobytes(garbage=3, deflate=True)
    doc.close()
    return out


def build_pack(qi, product, industry, extra_files=()):
    """qi: QuotationInput. extra_files: [(file name, bytes)] added to the zip.
    Returns (zip bytes, ranked client list)."""
    ranked = client_list.rank_clients(product, industry, qi.country)
    name = safe_name(qi.client_name)

    files = [
        (f"1 Quotation - {name}.xlsx", workbook_to_bytes(build_workbook(qi))),
        (f"4 About Company - {name}.pdf", build_about_company_pdf(ranked)),
    ]
    for number, filename in ((6, "Application Form.xlsx"), (7, "FMCS Final Checklist.docx")):
        with open(os.path.join(ASSETS, filename), "rb") as f:
            files.append((f"{number} {filename}", f.read()))

    files.extend(extra_files)
    files.sort(key=lambda item: item[0])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for filename, data in files:
            z.writestr(filename, data)
    return buf.getvalue(), ranked
