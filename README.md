# Sun Consultants — FMCS/BIS Quotation Suite

A small internal CRM for generating and reviewing BIS/FMCS certification quotations.

- **Generate** — describe a request in plain English (or fill the form), enter the
  per-standard testing/marking fees, and get a priced quotation ready to download as
  an .xlsx matching your existing client-facing format.
- **Review** — upload an existing quotation .xlsx and it's checked line-by-line
  against the pricing formula (man-days, per-diem, brackets, totals) with mismatches
  flagged.
- All pricing logic lives in `calc.py` — one deterministic engine, no AI required for
  the math itself. AI (Claude API) is used only to make the command box and review
  summaries handle free-form language better; without an API key the app falls back
  to a rule-based parser and template summaries, and still works fully.

## Running locally

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 app.py
```

Open http://localhost:5050

## Enabling AI-assisted parsing (optional)

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python3 app.py
```

Without this set, the command box still works using a regex-based parser for common
phrasing ("Create a quotation for X in Y for IS Z"), and the review tab produces a
plain-template summary instead of an AI-written one. All the pricing math and the
line-by-line review checks are identical either way — the AI only affects language
flexibility, not correctness.

## Deploying so employees can access it online

### Option A — Render (recommended, free tier available)
1. Push this folder to a GitHub repo.
2. In Render: New → Blueprint → point at the repo (it will read `render.yaml`
   automatically), or New → Web Service if you prefer to configure manually:
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn app:app --bind 0.0.0.0:$PORT`
3. Add environment variable `ANTHROPIC_API_KEY` if you want AI-assisted parsing.
4. Render gives you a public URL (e.g. `https://fmcs-quotation-suite.onrender.com`)
   — share that with your employees.
5. `render.yaml` already provisions a small persistent disk so the SQLite database
   (clients/quotations) survives restarts and deploys.

### Option B — Railway / Fly.io / any Python host
Same idea: install `requirements.txt`, run `gunicorn app:app --bind 0.0.0.0:$PORT`,
set `DATABASE_PATH` to a path on a persistent volume if the platform offers one
(otherwise the SQLite file resets on redeploy — fine for testing, not for production
data).

### Authentication
This build has no login screen — anyone with the URL can use it. Before sharing
broadly, put it behind your host's basic-auth / access-control feature, or ask and
I'll add a simple login.

## Business rules encoded (for reference — see calc.py)

- Application Fee & License Fee: ₹1,000 per IS standard each, summed across all IS on
  the quotation.
- Inspection Charge: (N + 5) man-days × ₹7,000, N = number of IS standards.
- Travel expenses of BIS officer: ₹3,00,000 for USA/Europe/Turkey, else ₹2,00,000 (flat,
  once per quotation).
- Per Diem: (N + 2) days × $400/day (USA/Europe/Turkey) or $300/day (elsewhere).
- Contingency funds: flat ₹10,000 regardless of N.
- Sample Testing Charges & Minimum Marking Fee: always asked from the user per IS —
  never invented, since these come from external lab/BIS lookups.
- Consultancy Charges: $5,000 per IS by default (editable), summed across all IS.
- PBG ($10,000 flat per IS) and "Travel expenses of company's representative"
  ("As per actuals") are shown on the quotation but excluded from the total.
- No GST on any line item.
- Country bracket: USA + EU states + UK + Switzerland + Norway + Turkey = higher
  bracket; everyone else = standard bracket (see `countries.py` to edit the list).

These rules were reverse-engineered from four real client quotations and confirmed
with Sun Consultants directly — don't change them without re-checking.
