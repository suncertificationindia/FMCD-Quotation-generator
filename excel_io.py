"""Generate a client-ready .xlsx quotation, and parse an uploaded one for review."""

import io
import re
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

from calc import calculate, QuotationInput, ISItem, DEFAULT_CONSULTANCY_USD_PER_IS
from countries import is_known_country

HEADER_FILL = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
HEADER_FONT = Font(bold=True, color="FFFFFF")
TITLE_FONT = Font(bold=True, size=14)
BOLD = Font(bold=True)
THIN = Side(style="thin", color="999999")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
LEFT_WRAP = Alignment(horizontal="left", vertical="center", wrap_text=True)

NOTES = [
    "In-house lab as per the standard has to be mandatorily present at the manufacturing unit.",
    "All the charges mentioned above in INR are to be transferred in equivalent USD to BIS, only USD payments are acceptable.",
    None,  # filled dynamically with country/rate note
    "Any change in the structure of govt. fee to be borne by the manufacturer.",
    "Samples to be sent to Indian laboratory by the manufacturer after samples are sealed during the audit.",
    "The charges above are calculated on the assumption that all the licenses are applied together, if separately applied, fee structure will differ.",
    "If multiple samples are required to be tested to cover various varieties, then the testing cost will increase accordingly.",
    "PBG must have a validity of 6 months more than the last date of validity of the license, and this will be released by BIS post license withdrawal.",
    "PBG must be submitted within 45 days of grant of license, and PBG is per license.",
]


def _title(is_numbers):
    if len(is_numbers) == 1:
        return f"Quotation for BIS - IS {is_numbers[0]}"
    if len(is_numbers) == 2:
        return f"Quotation for BIS - IS {is_numbers[0]} & IS {is_numbers[1]}"
    head = ", ".join(f"IS {x}" for x in is_numbers[:-1])
    return f"Quotation for BIS - {head}, & IS {is_numbers[-1]}"


def build_workbook(q: QuotationInput) -> Workbook:
    result = calculate(q)
    n = result["n"]
    li = result["line_items"]
    is_numbers = [i.is_number for i in q.is_items]

    wb = Workbook()
    ws = wb.active
    ws.title = "Quotation"

    n_amount_cols = n
    total_cols = 2 + n_amount_cols + 2  # S.No, Description, [Amounts...], Stage, Paid to
    last_col_letter = get_column_letter(total_cols)

    ws.merge_cells(f"A1:{last_col_letter}1")
    ws["A1"] = _title(is_numbers)
    ws["A1"].font = TITLE_FONT
    ws["A1"].alignment = CENTER

    ws.merge_cells(f"A2:{last_col_letter}2")
    ws["A2"] = "All amounts are in USD"
    ws["A2"].alignment = CENTER

    headers = ["S.NO", "Description of Fee"] + [f"Amount (IS {x})" for x in is_numbers] + ["Stage of Payment", "Paid to"]
    for idx, h in enumerate(headers, start=1):
        c = ws.cell(row=3, column=idx, value=h)
        c.font = HEADER_FONT
        c.fill = HEADER_FILL
        c.alignment = CENTER
        c.border = BORDER

    row = 4
    sno = 1

    def write_row(desc, amounts, stage="", paid_to="", bold=False):
        nonlocal row, sno
        ws.cell(row=row, column=1, value=sno).alignment = CENTER
        dcell = ws.cell(row=row, column=2, value=desc)
        dcell.alignment = LEFT_WRAP
        for i, amt in enumerate(amounts):
            cell = ws.cell(row=row, column=3 + i, value=amt)
            cell.alignment = CENTER
        ws.cell(row=row, column=3 + n_amount_cols, value=stage).alignment = LEFT_WRAP
        ws.cell(row=row, column=4 + n_amount_cols, value=paid_to).alignment = LEFT_WRAP
        for col in range(1, total_cols + 1):
            ws.cell(row=row, column=col).border = BORDER
        if bold:
            for col in range(1, total_cols + 1):
                ws.cell(row=row, column=col).font = BOLD
        row += 1
        sno += 1

    bis_paid = "Bureau of Indian Standards (Government Fee)"

    write_row("Application Fee", [round(li["application_fee_usd_each"], 2)] * n,
               "Stage 1 - Payment along with application submission", bis_paid)

    write_row(
        f"Inspection Charge @ 7000 / Man day – {result['man_days']} Man Day ( Incl. travel time)",
        [round(li["inspection_usd"], 2)] + [""] * (n - 1),
        "Stage-2 - After appointment of BIS auditor for audit at factory", bis_paid,
    )
    write_row("Travel expenses of BIS officer ( Flight, VISA, Stay,etc) ",
               [round(li["travel_officer_usd"], 2)] + [""] * (n - 1), "", bis_paid)
    write_row(
        f"Per Diem Expenses as per the level of the officer ( Depending on the rank of visiting officer ), "
        f"{result['per_diem_rate']} USD/day ({result['per_diem_days']} days)",
        [round(li["per_diem_usd"], 2)] + [""] * (n - 1), "", bis_paid,
    )
    write_row("Contingency funds", [round(li["contingency_usd"], 2)] + [""] * (n - 1), "", bis_paid)

    write_row(
        "Sample Testing Charges paid to concern laboratory / BIS per sample Approx.( As per actuals, depends on the lab selected during audit.)",
        li["sample_testing_per_is"],
        "Stage-3 -  After completion of audit", bis_paid,
    )
    has_marking_ref = any(i.unit_price_inr or i.unit_size or i.annual_production for i in q.is_items)
    write_row("Minimum Marking Fee / Year" + (" *" if has_marking_ref else ""),
               li["min_marking_per_is"], "", bis_paid)
    write_row("License Fee", [round(li["license_fee_usd_each"], 2)] * n,
               "", bis_paid)
    write_row("Performance Bank Guarantee ( PBG/licence )", [li["pbg_usd_each"]] * n,
               "Stage-4 -  After grant of license", bis_paid)

    write_row("Travel expenses of our company's representative ( Flight, VISA, Stay,etc)",
               ["As per actuals"] * n, "Payable after audit to Sun", "Sun Consultants")
    write_row(
        "Consultancy Charges", li["consultancy_per_is"],
        "25% Advance\n25% After application submission\n25% After Completion of audit\n25% After grant of license",
        "Sun Consultants",
    )

    ws.cell(row=row, column=1, value=sno).alignment = CENTER
    ws.cell(row=row, column=2, value="Total (Excluding PBG)").alignment = LEFT_WRAP
    total_cell = ws.cell(row=row, column=3, value=result["total_usd"])
    total_cell.alignment = CENTER
    total_cell.number_format = "#,##0.00"
    for col in range(1, total_cols + 1):
        ws.cell(row=row, column=col).border = BORDER
        ws.cell(row=row, column=col).font = BOLD
    row += 2

    # Marking fee reference table (optional section)
    if has_marking_ref:
        ws.cell(row=row, column=2, value="* Marking Fee ( Per Unit Price )").font = BOLD
        row += 1
        for h, col in zip(["Indian Standard ( IS )", "Product Name", "Per unit price", "Per Year Production"], range(2, 6)):
            ws.cell(row=row, column=col, value=h).font = BOLD
        row += 1
        for it in q.is_items:
            ws.cell(row=row, column=2, value=it.is_number)
            ws.cell(row=row, column=3, value=it.product_name)
            if it.unit_price_inr:
                price = f"INR {it.unit_price_inr:g}"
                ws.cell(row=row, column=4, value=f"{price} per {it.unit_size}" if it.unit_size else price)
            else:
                ws.cell(row=row, column=4, value=it.unit_size or "")
            ws.cell(row=row, column=5, value=it.annual_production or "")
            row += 1
        row += 1

    ws.cell(row=row, column=2, value="Note:").font = BOLD
    row += 1
    region_note = (
        f"For {q.country}, according to our previous audits it was {result['per_diem_rate']} USD/day, "
        f"therefore we have used the same in this calculation."
    )
    note_num = 1
    for note in NOTES:
        text = region_note if note is None else note
        ws.cell(row=row, column=2, value=f"{note_num}.) {text}")
        row += 1
        note_num += 1

    ws.cell(row=row + 1, column=2, value=f"Exchange rate used: 1 USD = INR {q.exchange_rate:.2f}").font = Font(italic=True, size=9)

    widths = {1: 6, 2: 46}
    for i in range(n):
        widths[3 + i] = 16
    widths[3 + n] = 30
    widths[4 + n] = 24
    for col, w in widths.items():
        ws.column_dimensions[get_column_letter(col)].width = w

    return wb


def workbook_to_bytes(wb) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------- Parsing uploaded quotations for review ----------------

LABEL_PATTERNS = {
    "application_fee": r"application fee",
    "inspection": r"inspection charge",
    "travel_officer": r"travel expenses of bis officer",
    "per_diem": r"per diem",
    "contingency": r"contingency fund",
    "sample_testing": r"sample testing charges",
    "min_marking": r"minimum marking fee",
    "license_fee": r"license fee",
    "pbg": r"performance bank guarantee",
    "rep_travel": r"travel\s*expenses of our company",
    "consultancy": r"consultancy charges",
    "total": r"^total",
}


def _to_number(val):
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if not s or s.lower() in ("at actuals", "as per actuals"):
        return None
    s = re.sub(r"[^0-9.\-]", "", s.replace(",", ""))
    try:
        return float(s)
    except ValueError:
        return None


def parse_uploaded_quotation(file_stream) -> dict:
    """Best-effort extraction of an uploaded quotation's structure and values."""
    try:
        wb = load_workbook(file_stream, data_only=True)
        ws = wb.active
    except Exception:
        raise ValueError("This is not a valid .xlsx Excel file. Please upload the quotation saved as .xlsx "
                         "(older .xls files and renamed files do not work).")

    all_text = []
    for row in ws.iter_rows():
        for cell in row:
            if isinstance(cell.value, str):
                all_text.append(cell.value)
    full_text = "\n".join(all_text)

    is_numbers = re.findall(r"IS\s*[- ]?(\d{4,6})", full_text)
    seen = set()
    is_numbers = [x for x in is_numbers if not (x in seen or seen.add(x))]

    # Find header row containing "Description of Fee"
    header_row_idx = None
    desc_col = None
    amount_cols = []
    for row in ws.iter_rows():
        for cell in row:
            if isinstance(cell.value, str) and "description of fee" in cell.value.lower():
                header_row_idx = cell.row
                desc_col = cell.column
                break
        if header_row_idx:
            break

    if header_row_idx:
        header_cells = [c for c in ws[header_row_idx] if c.value is not None]
        stage_col = None
        paidto_col = None
        for cell in header_cells:
            if isinstance(cell.value, str):
                low = cell.value.strip().lower()
                if low.startswith("stage of payment") and stage_col is None:
                    stage_col = cell.column
                elif low.startswith("paid to") and paidto_col is None:
                    paidto_col = cell.column

        boundary_candidates = [c for c in (stage_col, paidto_col) if c and c > desc_col]
        boundary_col = min(boundary_candidates) if boundary_candidates else None

        for cell in header_cells:
            if cell.column <= desc_col:
                continue
            if boundary_col and cell.column >= boundary_col:
                continue
            label = str(cell.value).strip().lower()
            if label.startswith("amount") or re.search(r"\bis\b", label) or re.match(r"^\(?\d{4,6}\)?$", label):
                amount_cols.append(cell.column)

        # Fallback: no recognizable amount headers but a boundary was found —
        # treat every column between description and boundary as an amount column.
        if not amount_cols and boundary_col:
            amount_cols = list(range(desc_col + 1, boundary_col))

    findings = {"is_numbers": is_numbers, "amount_columns_detected": len(amount_cols), "rows": {}}

    if header_row_idx and desc_col and amount_cols:
        for row in ws.iter_rows(min_row=header_row_idx + 1):
            desc_cell = row[desc_col - 1] if len(row) >= desc_col else None
            if not desc_cell or not isinstance(desc_cell.value, str):
                continue
            label_text = desc_cell.value.lower()
            for key, pattern in LABEL_PATTERNS.items():
                if re.search(pattern, label_text):
                    values = []
                    for col in amount_cols:
                        if col - 1 < len(row):
                            values.append(_to_number(row[col - 1].value))
                    findings["rows"][key] = {"label": desc_cell.value, "values": values}
                    break

    # Exchange rate printed on the quotation: "Exchange rate used: 1 USD = INR 90.91"
    rate_line = re.search(r"exchange rate[^0-9\n]*?1\s*USD\s*=\s*(?:INR|Rs\.?|\u20b9)?\s*([0-9][0-9,]*\.?[0-9]*)",
                          full_text, re.I)
    if rate_line:
        try:
            findings["file_exchange_rate"] = float(rate_line.group(1).replace(",", ""))
        except ValueError:
            pass

    # Try to recover exchange rate context from notes
    rate_note = re.search(r"for\s+([a-zA-Z ]+?)[,]?\s+according to our previous audits it was\s+(\d+)\s*usd/day", full_text, re.I)
    if rate_note:
        findings["note_country"] = rate_note.group(1).strip()
        findings["note_per_diem_rate"] = int(rate_note.group(2))

    return findings


def diff_against_expected(parsed: dict, country: str, exchange_rate: float) -> list:
    """Recompute expected values (using rule engine) and diff against the parsed workbook."""
    n = max(parsed.get("amount_columns_detected", 0), len(parsed.get("is_numbers", [])), 1)
    is_items = []
    rows = parsed.get("rows", {})

    sample_vals = rows.get("sample_testing", {}).get("values", [])
    marking_vals = rows.get("min_marking", {}).get("values", [])
    consultancy_vals = rows.get("consultancy", {}).get("values", [])

    for i in range(n):
        is_items.append(ISItem(
            is_number=parsed["is_numbers"][i] if i < len(parsed.get("is_numbers", [])) else f"#{i+1}",
            sample_testing_usd=(sample_vals[i] if i < len(sample_vals) else None) or 0,
            min_marking_fee_usd=(marking_vals[i] if i < len(marking_vals) else None) or 0,
            consultancy_usd=(consultancy_vals[i] if i < len(consultancy_vals) and consultancy_vals[i] is not None
                             else DEFAULT_CONSULTANCY_USD_PER_IS),
        ))

    q = QuotationInput(client_name="uploaded", country=country, exchange_rate=exchange_rate, is_items=is_items)
    expected = calculate(q)
    li = expected["line_items"]

    checks = []

    if not is_known_country(country):
        checks.append({"item": "Country", "status": "warning",
                        "note": f"Country '{country}' is not recognised - it was treated as the standard "
                                f"bracket (USD 300/day, INR 2,00,000 travel). Check the spelling."})

    def cmp_single(key, expected_val, label, tolerance_pct=0.005):
        actual_list = rows.get(key, {}).get("values", [])
        actual = next((v for v in actual_list if v is not None), None)
        if actual is None:
            checks.append({"item": label, "status": "missing", "expected": round(expected_val, 2), "found": None})
            return
        tol = max(abs(expected_val) * tolerance_pct, 1)
        if abs(actual - expected_val) > tol:
            checks.append({"item": label, "status": "mismatch", "expected": round(expected_val, 2), "found": actual})
        else:
            checks.append({"item": label, "status": "ok", "expected": round(expected_val, 2), "found": actual})

    def cmp_sum(key, expected_val, label, tolerance_pct=0.005):
        vals = [v for v in rows.get(key, {}).get("values", []) if v is not None]
        if not vals:
            checks.append({"item": label, "status": "missing", "expected": round(expected_val, 2), "found": None})
            return
        actual = sum(vals)
        tol = max(abs(expected_val) * tolerance_pct, 1)
        if abs(actual - expected_val) > tol:
            checks.append({"item": label, "status": "mismatch", "expected": round(expected_val, 2), "found": round(actual, 2)})
        else:
            checks.append({"item": label, "status": "ok", "expected": round(expected_val, 2), "found": round(actual, 2)})

    cmp_sum("application_fee", n * li["application_fee_usd_each"], "Application Fee (total across IS)")
    cmp_single("inspection", li["inspection_usd"], f"Inspection Charge ({expected['man_days']} man-days)")
    cmp_single("travel_officer", li["travel_officer_usd"], "Travel expenses of BIS officer")
    cmp_single("per_diem", li["per_diem_usd"], f"Per Diem ({expected['per_diem_days']} days @ {expected['per_diem_rate']} USD/day)")
    cmp_single("contingency", li["contingency_usd"], "Contingency funds")
    cmp_sum("license_fee", n * li["license_fee_usd_each"], "License Fee (total across IS)")

    pbg_vals = [v for v in rows.get("pbg", {}).get("values", []) if v is not None]
    if pbg_vals and any(abs(v - 10000) > 1 for v in pbg_vals):
        checks.append({"item": "Performance Bank Guarantee", "status": "mismatch", "expected": 10000, "found": pbg_vals})

    total_row = rows.get("total", {}).get("values", [])
    total_found = next((v for v in total_row if v is not None), None)
    checks.append({
        "item": "Grand Total (Excluding PBG)",
        "status": "info",
        "expected": expected["total_usd"],
        "found": total_found,
    })

    if not rows.get("sample_testing"):
        checks.append({"item": "Sample Testing Charges", "status": "warning",
                        "note": "Could not locate this row — verify manually, this value is client/lab-specific and not auto-checked."})
    if not rows.get("min_marking"):
        checks.append({"item": "Minimum Marking Fee", "status": "warning",
                        "note": "Could not locate this row — verify manually, this value is client/lab-specific and not auto-checked."})

    return checks
