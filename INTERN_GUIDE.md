# Deploying the Quotation Suite (guide for the interns)

This is a small Flask app (Python 3.9+, SQLite). Staff open one URL, sign in with a shared password,
create quotations and download .xlsx files. No Claude accounts are needed by staff.

## Current setup (already live - do not redo)
- GitHub repo: `suncertificationindia/FMCD-Quotation-generator`, branch `main`, files at the repo root.
- Render **free plan**, created from `render.yaml` (Blueprint). URL: https://fmcs-quotation-suite.onrender.com
- Environment variables on Render: `APP_PASSWORD` (shared staff password, set by Sun Consultants) and
  `SECRET_KEY` (generated automatically). `ANTHROPIC_API_KEY` is optional and not set.
- Any change committed to `main` on GitHub redeploys automatically in about 1 minute.

## How to put a change live
1. Open the repo on GitHub, click the file (or drag new files onto the repo page).
2. Replace the content or upload the new file, then **Commit changes** to `main`.
3. In Render, open the service and wait until Events shows the deploy as Live (about 1 minute).
4. Open the site, sign in and run the checks below.

## Checks after every deploy
- Wrong password is refused; correct password signs in.
- Generate: enter client, country, one IS with Sample Testing and Minimum Marking Fee -> Calculate -> Save -> Download .xlsx.
  Reference example: IS 18297, Vietnam, rate 90.91, testing 268, marking 1930, consultancy 6000 -> total 11,891.98 USD.
- Review: upload the downloaded .xlsx; every line should say ok.

## Free plan limits
- The site sleeps when idle; the first load takes about a minute.
- Saved quotations and clients (SQLite) are **erased on every restart or redeploy**. Downloads are not affected.
- To keep data: paid plan + persistent disk mounted at `/var/data` + environment variable
  `DATABASE_PATH=/var/data/data.sqlite3`. Then back up `/var/data/data.sqlite3` from time to time.

## Things to know
- If `APP_PASSWORD` is unset the app has NO login - never leave it unset on Render.
- The exchange rate comes from free public APIs; if they fail the form shows a fallback of 91 and the user can type the rate.
- All pricing rules live in `calc.py` (one place). Do not change them without re-checking against real quotations.
  Country lists are in `countries.py`.
- Sample Testing / Minimum Marking Fee are always typed by the user per IS - by design.
- Running locally (optional): `pip install -r requirements.txt`, then `APP_PASSWORD=test123 python3 app.py`
  and open http://localhost:5050
