import io
import os
import hmac
from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, flash, session

import db
from calc import calculate, QuotationInput, ISItem, DEFAULT_CONSULTANCY_USD_PER_IS
from countries import classify_country, BRACKET_A_COUNTRIES
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


@app.route("/api/calculate", methods=["POST"])
def api_calculate():
    data = request.json
    try:
        is_items = [
            ISItem(
                is_number=it["is_number"],
                product_name=it.get("product_name", ""),
                sample_testing_usd=float(it.get("sample_testing_usd") or 0),
                min_marking_fee_usd=float(it.get("min_marking_fee_usd") or 0),
                consultancy_usd=float(it.get("consultancy_usd") or DEFAULT_CONSULTANCY_USD_PER_IS),
            )
            for it in data["is_items"]
        ]
        q = QuotationInput(
            client_name=data["client_name"],
            country=data["country"],
            exchange_rate=float(data["exchange_rate"]),
            is_items=is_items,
        )
        result = calculate(q)
        result["bracket_label"] = "USA/Europe/Turkey (higher rate)" if result["bracket"] == "A" else "Standard rate"
        return jsonify({"ok": True, "result": result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/save-quotation", methods=["POST"])
def api_save_quotation():
    data = request.json
    is_items = [
        ISItem(
            is_number=it["is_number"],
            product_name=it.get("product_name", ""),
            sample_testing_usd=float(it.get("sample_testing_usd") or 0),
            min_marking_fee_usd=float(it.get("min_marking_fee_usd") or 0),
            consultancy_usd=float(it.get("consultancy_usd") or DEFAULT_CONSULTANCY_USD_PER_IS),
        )
        for it in data["is_items"]
    ]
    q = QuotationInput(
        client_name=data["client_name"],
        country=data["country"],
        exchange_rate=float(data["exchange_rate"]),
        is_items=is_items,
    )
    result = calculate(q)
    client_id = db.get_or_create_client(data["client_name"], data["country"])
    qid = db.save_quotation(
        client_id, data["client_name"], data["country"], float(data["exchange_rate"]),
        data["is_items"], result, status="draft",
    )
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
    is_items = [
        ISItem(
            is_number=it["is_number"],
            product_name=it.get("product_name", ""),
            sample_testing_usd=float(it.get("sample_testing_usd") or 0),
            min_marking_fee_usd=float(it.get("min_marking_fee_usd") or 0),
            consultancy_usd=float(it.get("consultancy_usd") or DEFAULT_CONSULTANCY_USD_PER_IS),
        )
        for it in q["is_items"]
    ]
    qi = QuotationInput(client_name=q["client_name"], country=q["country"],
                         exchange_rate=q["exchange_rate"], is_items=is_items)
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
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "No file uploaded"}), 400
    f = request.files["file"]
    country = request.form.get("country", "")
    rate = request.form.get("exchange_rate", "")
    try:
        rate = float(rate)
    except (TypeError, ValueError):
        rate = get_live_inr_per_usd()["rate"]

    file_bytes = f.read()
    parsed = parse_uploaded_quotation(io.BytesIO(file_bytes))

    if not country and parsed.get("note_country"):
        country = parsed["note_country"]

    checks = diff_against_expected(parsed, country or "Unknown", rate)
    summary = ai.summarize_review(checks, context=f"Country: {country}, rate used: {rate}")

    db.save_review(f.filename, {"checks": checks, "summary": summary, "country": country, "rate": rate})

    return jsonify({
        "ok": True,
        "filename": f.filename,
        "country_used": country,
        "rate_used": rate,
        "is_numbers_detected": parsed.get("is_numbers", []),
        "checks": checks,
        "summary": summary,
        "ai_powered": ai.ai_available(),
    })


@app.route("/api/countries")
def api_countries():
    return jsonify(sorted(BRACKET_A_COUNTRIES))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port, debug=True)
