# Deploying the Quotation Suite (guide for the interns)

This is a small Flask app (Python 3.9+, SQLite). Goal: put it online so Sun Consultants staff can open
one URL, sign in with a shared password, create quotations and download .xlsx files.
No Claude accounts are needed by staff.

## 1. Run it locally first (5 minutes)
```bash
cd app
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
APP_PASSWORD=test123 python3 app.py      # opens on http://localhost:5050
```
Check: login works, Generate -> Calculate -> Save -> Download .xlsx works, Review tab accepts an .xlsx.

## 2. Push to GitHub
Create a **private** repo and push the contents of the `app/` folder as the repo root
(so `app.py`, `requirements.txt`, `render.yaml` sit at the top level). `.gitignore` already
excludes the database and venv.

## 3. Deploy on Render
1. render.com -> New -> Blueprint -> pick the repo (it reads `render.yaml`).
2. When prompted, set **APP_PASSWORD** (the shared staff password). `SECRET_KEY` is generated automatically.
   `ANTHROPIC_API_KEY` is optional - leave empty to use the rule-based parser (all pricing math is identical).
3. Plan: `render.yaml` uses a paid plan because saved quotations live in SQLite on a persistent disk
   (`/var/data`). On the free plan there is no disk, so data resets on every deploy/restart -
   fine only for testing (see the comment inside `render.yaml`).
4. Open the Render URL, sign in, and run the same checks as step 1.

## 4. Things to know
- Auth is one shared password (env var `APP_PASSWORD`). If it is unset the app has NO login - never deploy that way.
- The exchange rate is fetched live from free public APIs; if they fail the form falls back to 91 and the
  user can type the rate manually.
- All pricing rules live in `calc.py` (one place). Do not change them without re-checking against real quotations.
  Country brackets are in `countries.py`.
- Backups: download `/var/data/data.sqlite3` from the Render shell periodically.
- Sample Testing / Minimum Marking Fee are always entered by the user per IS - by design.
