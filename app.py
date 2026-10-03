import io
import os
import re
import math
import hmac
from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, flash, session

import db
from werkzeug.exceptions import HTTPException
from calc import calculate, QuotationInput, ISItem, DEFAULT_CONSULTANCY_USD_PER_IS
from countries import is_known_country, COUNTRY_SUGGESTIONS
from currency import get_live_inr_per_usd
from excel_io import build_workbook, workbook_to_bytes, parse_uploaded_quotation, diff_against_expected
import ai
import clients as client_list
from pack import build_pack, safe_name
import standards as std_reader
import bisdata
import about_bis
import base64
import datetime

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")

app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["MAX_CONTENT_LENGTH"] = 80 * 1024 * 1024   # uploaded standards (PDF)
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")

db.init_db()


@app.before_request
def require_login():
    if not APP_PASSWORD:
        return None
    if request.endpoint in ("login", "static"):
        return None
    if session.get("ok"):
        return None
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": "Not signed in"}), 401
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        supplied = request.form.get("password", "")
        if APP_PASSWORD and hmac.compare_digest(supplied.encode(), APP_PASSWORD.encode()):
            session["ok"] = True
            return redirect(url_for("dashboard"))
        error = "Wrong password."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
def dashboard():
    quotations = db.list_quotations()[:10]
    clients = db.list_clients()
    return render_template("dashboard.html", quotations=quotations, clients=clients,
                            ai_on=ai.ai_available())


@app.route("/generate")
def generate_page():
    rate_info = get_live_inr_per_usd()
    return render_template("generate.html", rate_info=rate_info, industries=client_list.industries(),
                            default_consultancy=DEFAULT_CONSULTANCY_USD_PER_IS,
                            ai_on=ai.ai_available())


@app.route("/api/exchange-rate")
def api_exchange_rate():
    return jsonify(get_live_inr_per_usd())


def _num(value, label, required=False, default=None):
    """Convert a form value to a non-negative number, with a clear error message."""
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise ValueError(f"{label} is blank. Please enter an amount (type 0 only if there is truly no charge).")
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a number (you entered '{value}').")
    if not math.isfinite(number):
        raise ValueError(f"{label} must be a normal number.")
    if number < 0:
        raise ValueError(f"{label} cannot be negative.")
    return number


def _text(value):
    return str(value).strip() if value not in (None, "") else ""


def build_input(data, strict=True):
    """Validate the form data and build a QuotationInput. Returns (QuotationInput, warnings).

    strict=False is used for already-saved quotations (blank fees count as 0 there).
    """
    if not isinstance(data, dict):
        raise ValueError("No quotation data received.")
    client_name = _text(data.get("client_name"))
    country = _text(data.get("country"))
    if not client_name:
        raise ValueError("Client name is required.")
    if not country:
        raise ValueError("Country is required.")
    rate = _num(data.get("exchange_rate"), "Exchange rate", required=True)
    if rate <= 0:
        raise ValueError("Exchange rate must be greater than zero.")
    product = _text(data.get("product"))
    industry = _text(data.get("industry"))
    if strict and not product:
        raise ValueError("Product is required (for example: Hinges, Chairs, Toughened glass). "
                         "It decides which clients appear in the About Company PDF.")
    if strict and not industry:
        raise ValueError("Please choose the industry (choose Other if none fits).")
    raw_items = data.get("is_items") or []
    if not raw_items:
        raise ValueError("Add at least one IS standard.")

    items, warnings, seen = [], [], set()
    for raw in raw_items:
        is_number = re.sub(r"^\s*IS\s*[:\-.]?\s*", "", _text(raw.get("is_number")), flags=re.I)
        if not is_number:
            raise ValueError("Every IS standard needs an IS number.")
        if is_number in seen:
            warnings.append(f"IS {is_number} is entered more than once. Remove the duplicate unless it is intended.")
        seen.add(is_number)
        tag = f"IS {is_number}"
        items.append(ISItem(
            is_number=is_number,
            product_name=_text(raw.get("product_name")),
            sample_testing_usd=_num(raw.get("sample_testing_usd"), f"Sample Testing Charge ({tag})",
                                    required=strict, default=0.0),
            min_marking_fee_usd=_num(raw.get("min_marking_fee_usd"), f"Minimum Marking Fee ({tag})",
                                     required=strict, default=0.0),
            consultancy_usd=_num(raw.get("consultancy_usd"), f"Consultancy Charge ({tag})",
                                 default=DEFAULT_CONSULTANCY_USD_PER_IS),
            unit_price_inr=_num(raw.get("unit_price_inr"), f"Marking fee unit price ({tag})", default=None),
            unit_size=_text(raw.get("unit_size")) or None,
            annual_production=_text(raw.get("annual_production")) or None,
        ))
    q = QuotationInput(client_name=client_name, country=country, exchange_rate=rate, is_items=items,
                       product=product, industry=industry)
    if not is_known_country(country):
        warnings.append(f"Country '{country}' is not recognised. It is priced at the standard rate "
                        f"(USD 300/day, INR 2,00,000 travel). Check the spelling.")
    return q, warnings


@app.errorhandler(Exception)
def handle_unexpected(e):
    if isinstance(e, HTTPException):
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "error": e.description}), e.code
        return e
    app.logger.exception("Unexpected error")
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": "Something went wrong on the server. Please try again."}), 500
    return "Something went wrong. Please go back and try again.", 500


@app.route("/api/calculate", methods=["POST"])
def api_calculate():
    data = request.get_json(silent=True)
    try:
        q, warnings = build_input(data)
        result = calculate(q)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    result["bracket_label"] = "USA/Europe/Turkey (higher rate)" if result["bracket"] == "A" else "Standard rate"
    result["warnings"] = warnings
    result["country_recognized"] = is_known_country(q.country)
    return jsonify({"ok": True, "result": result})


@app.route("/api/save-quotation", methods=["POST"])
def api_save_quotation():
    data = request.get_json(silent=True)
    try:
        q, _warnings = build_input(data)
        if not is_known_country(q.country) and not data.get("country_confirmed"):
            raise ValueError(f"Country '{q.country}' is not recognised. Tick the confirmation box "
                             f"or correct the country before saving.")
        result = calculate(q)
        result["meta"] = {"product": q.product, "industry": q.industry}
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    client_id = db.get_or_create_client(q.client_name, q.country)
    stored_items = [
        {"is_number": i.is_number, "product_name": i.product_name,
         "sample_testing_usd": i.sample_testing_usd, "min_marking_fee_usd": i.min_marking_fee_usd,
         "consultancy_usd": i.consultancy_usd, "unit_price_inr": i.unit_price_inr,
         "unit_size": i.unit_size, "annual_production": i.annual_production}
        for i in q.is_items
    ]
    qid = db.save_quotation(client_id, q.client_name, q.country, q.exchange_rate,
                            stored_items, result, status="draft")
    return jsonify({"ok": True, "quotation_id": qid})


@app.route("/quotations/<int:qid>")
def view_quotation(qid):
    q = db.get_quotation(qid)
    if not q:
        return "Not found", 404
    meta = q["result"].get("meta") or {}
    ranked = client_list.rank_clients(meta.get("product", ""), meta.get("industry", ""), q["country"])
    return render_template("quotation_view.html", q=q, meta=meta, ranked=ranked)


@app.route("/quotations/<int:qid>/download")
def download_quotation(qid):
    q = db.get_quotation(qid)
    if not q:
        return "Not found", 404
    try:
        qi, _warnings = build_input(q, strict=False)
    except ValueError as e:
        return f"This saved quotation cannot be downloaded: {e}", 400
    wb = build_workbook(qi)
    data = workbook_to_bytes(wb)
    filename = f"Quotation - {q['client_name']}.xlsx"
    return send_file(io.BytesIO(data), as_attachment=True, download_name=filename,
                      mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.route("/quotations/<int:qid>/pack")
def download_pack(qid):
    q = db.get_quotation(qid)
    if not q:
        return "Not found", 404
    try:
        qi, _warnings = build_input(q, strict=False)
    except ValueError as e:
        return f"This saved quotation cannot be downloaded: {e}", 400
    meta = q["result"].get("meta") or {}
    qi.product, qi.industry = meta.get("product", ""), meta.get("industry", "")
    data, _ranked = build_pack(qi, qi.product, qi.industry)
    return send_file(io.BytesIO(data), as_attachment=True,
                     download_name=f"Document pack - {safe_name(q['client_name'])}.zip",
                     mimetype="application/zip")


def stored_quotation_input(q):
    """QuotationInput + product + industry for a saved quotation."""
    qi, _warnings = build_input(q, strict=False)
    meta = q["result"].get("meta") or {}
    qi.product, qi.industry = meta.get("product", ""), meta.get("industry", "")
    return qi


@app.route("/quotations/<int:qid>/about-bis")
def about_bis_page(qid):
    q = db.get_quotation(qid)
    if not q:
        return "Not found", 404
    numbers = [it["is_number"] for it in q["is_items"]]
    return render_template("about_bis.html", q=q, numbers=numbers)


@app.route("/api/standard-info", methods=["POST"])
def api_standard_info():
    f = request.files.get("file")
    expected = request.form.get("expected", "")
    if not f:
        return jsonify({"ok": False, "error": "No file received."}), 400
    data = f.read()
    try:
        info = std_reader.read_standard(data)
        previews = std_reader.scope_previews(data, info["segments"])
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    warnings = list(info["warnings"])
    mismatch = not std_reader.same_standard(expected, info["is_number"])
    if mismatch:
        warnings.insert(0, f"This file is IS {info['is_number']}, but this box is for IS {expected}. "
                           f"Please choose the right file.")
    return jsonify({
        "ok": True, "is_number": info["is_number"], "year": info["year"],
        "description": info["description"], "warnings": warnings, "mismatch": mismatch,
        "previews": ["data:image/png;base64," + base64.b64encode(p).decode() for p in previews],
    })


@app.route("/api/bis-data", methods=["POST"])
def api_bis_data():
    numbers = [str(n) for n in (request.get_json(silent=True) or {}).get("is_numbers", [])][:about_bis.MAX_STANDARDS]
    if not numbers:
        return jsonify({"ok": False, "error": "No IS numbers."}), 400
    found = bisdata.lookup(numbers)
    labs, more = bisdata.allocate_labs(found["labs_by_is"])
    return jsonify({"ok": True, "fmcs": found["fmcs"], "labs": labs, "more": more,
                    "manuals": found["manuals"], "errors": found["errors"]})


def _int_field(form, name, label):
    raw = (form.get(name) or "").strip()
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{label} is missing or not a whole number.")
    if value < 0:
        raise ValueError(f"{label} cannot be negative.")
    return value


@app.route("/quotations/<int:qid>/about-bis/build", methods=["POST"])
def about_bis_build(qid):
    q = db.get_quotation(qid)
    if not q:
        return jsonify({"ok": False, "error": "Quotation not found."}), 404
    form = request.form
    opened = []
    try:
        qi = stored_quotation_input(q)
        count = int(form.get("count", "0"))
        if count < 1 or count != len(qi.is_items):
            raise ValueError("The IS list does not match the quotation.")
        stds, standard_files = [], []
        numbers = [item.is_number for item in qi.is_items]
        downloaded = bisdata.fetch_manuals(numbers)
        for i in range(count):
            number = qi.is_items[i].is_number
            tag = f"IS {number}"
            upload = request.files.get(f"std_{i}")
            if not upload or not upload.filename:
                raise ValueError(f"Please add the BIS standard PDF for {tag}.")
            data = upload.read()
            info = std_reader.read_standard(data)
            if not std_reader.same_standard(number, info["is_number"]):
                raise ValueError(f"The PDF added for {tag} is IS {info['is_number']}. Please add the right file.")
            year = (form.get(f"year_{i}") or info["year"] or "").strip()
            description = (form.get(f"desc_{i}") or info["description"] or "").strip()
            if not year:
                raise ValueError(f"Please type the year of {tag} (for example 2022).")
            if not description:
                raise ValueError(f"Please type the name of {tag} (for example Work chairs).")
            try:
                impl = datetime.date.fromisoformat((form.get(f"date_{i}") or "").strip())
            except ValueError:
                raise ValueError(f"Please choose the implementation date for {tag}.")
            image = request.files.get(f"scope_img_{i}")
            image_bytes = image.read() if image and image.filename else None
            if not image_bytes and not info["segments"]:
                raise ValueError(f"The Scope of {tag} could not be found automatically. "
                                 f"Please upload a picture of its Scope.")
            std = {
                "number": number, "year": year, "description": description, "impl_date": impl,
                "india": _int_field(form, f"india_{i}", f"Licensees in India for {tag}"),
                "fmcs": _int_field(form, f"fmcs_{i}", f"Foreign licensees for {tag}"),
                "segments": info["segments"], "scope_image": image_bytes,
                "scope_doc": std_reader.open_pdf(data),
            }
            opened.append(std["scope_doc"])
            stds.append(std)
            standard_files.append((f"3 Standard - IS {number}.pdf", data))
            manual = request.files.get(f"manual_{i}")
            manual_bytes = manual.read() if manual and manual.filename else downloaded.get(number)
            if not manual_bytes:
                raise ValueError(f"No product manual for {tag} was found on the BIS website. "
                                 f"Please add the product manual PDF in the box for {tag}.")
            standard_files.append((f"2 Product Manual - IS {number}.pdf", manual_bytes))
        labs = [ln.strip() for ln in (form.get("labs") or "").splitlines() if ln.strip()]
        if not labs:
            raise ValueError("The labs list is empty. Click 'Fetch from BIS' or type the lab names.")
        if len(labs) > 10:
            raise ValueError("A maximum of 10 labs fits on the slide. Please remove the extra lines.")
        pdf = about_bis.build_about_bis(stds, labs, form.get("labs_etc") == "1")
        name = safe_name(qi.client_name)
        if form.get("mode") == "pack":
            data, _ranked = build_pack(qi, qi.product, qi.industry,
                                       extra_files=standard_files + [(f"5 About BIS - {name}.pdf", pdf)])
            return send_file(io.BytesIO(data), as_attachment=True,
                             download_name=f"Document pack - {name}.zip", mimetype="application/zip")
        return send_file(io.BytesIO(pdf), as_attachment=True,
                         download_name=f"About BIS - {name}.pdf", mimetype="application/pdf")
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    finally:
        for d in opened:
            d.close()


@app.route("/quotations")
def list_quotations():
    quotations = db.list_quotations()
    return render_template("quotations_list.html", quotations=quotations)


@app.route("/clients")
def list_clients():
    clients = db.list_clients()
    return render_template("clients.html", clients=clients)


@app.route("/review")
def review_page():
    return render_template("review.html", ai_on=ai.ai_available())


@app.route("/api/review", methods=["POST"])
def api_review():
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "No file uploaded. Choose a quotation .xlsx first."}), 400
    if not f.filename.lower().endswith(".xlsx"):
        return jsonify({"ok": False, "error": "Please upload an .xlsx file (Excel 2007 or newer)."}), 400

    try:
        parsed = parse_uploaded_quotation(io.BytesIO(f.read()))
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    # Exchange rate: the rate printed in the file wins; otherwise the box; otherwise ask.
    rate_source = None
    rate = parsed.get("file_exchange_rate")
    if rate:
        rate_source = "the 'Exchange rate used' line in the file"
    else:
        try:
            rate = float(request.form.get("exchange_rate", "").strip())
        except ValueError:
            rate = None
        if rate:
            rate_source = "the rate box"
    if not rate or rate <= 0:
        return jsonify({"ok": False, "need": "exchange_rate",
                        "error": "This file does not show the exchange rate it used. Please type the "
                                 "exchange rate (INR per USD) in the rate box and click Review again."}), 400

    country = request.form.get("country", "").strip() or parsed.get("note_country") or ""
    if not country:
        return jsonify({"ok": False, "need": "country",
                        "error": "The country could not be found in the file. Please type the country "
                                 "in the Country box and click Review again."}), 400

    checks = diff_against_expected(parsed, country, rate)
    summary = ai.summarize_review(checks, context=f"Country: {country}, rate used: {rate}")

    db.save_review(f.filename, {"checks": checks, "summary": summary, "country": country, "rate": rate})

    return jsonify({
        "ok": True,
        "filename": f.filename,
        "country_used": country,
        "rate_used": rate,
        "rate_source": rate_source,
        "is_numbers_detected": parsed.get("is_numbers", []),
        "checks": checks,
        "summary": summary,
        "ai_powered": ai.ai_available(),
    })


@app.route("/api/countries")
def api_countries():
    return jsonify(COUNTRY_SUGGESTIONS)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port, debug=True)
