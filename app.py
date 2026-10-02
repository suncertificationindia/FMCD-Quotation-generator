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

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")

app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
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
    return render_template("generate.html", rate_info=rate_info,
                            default_consultancy=DEFAULT_CONSULTANCY_USD_PER_IS,
                            ai_on=ai.ai_available())


@app.route("/api/parse-command", methods=["POST"])
def api_parse_command():
    text = request.json.get("text", "")
    parsed = ai.parse_command(text)
    return jsonify(parsed)


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
    q = QuotationInput(client_name=client_name, country=country, exchange_rate=rate, is_items=items)
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
    return render_template("quotation_view.html", q=q)


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
