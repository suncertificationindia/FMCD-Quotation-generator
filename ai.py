"""AI integration point.

Works with zero configuration using regex-based parsing / template summaries.
If ANTHROPIC_API_KEY is set in the environment, upgrades command parsing and
review summaries to use Claude for more flexible natural-language handling.
"""

import os
import re
import json

from countries import is_known_country

API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()


def _get_client():
    if not API_KEY:
        return None
    try:
        import anthropic
        return anthropic.Anthropic(api_key=API_KEY)
    except Exception:
        return None


def ai_available() -> bool:
    return bool(API_KEY)


# ---------------- Command parsing ----------------

_IS_RUN = re.compile(
    r"\bIS\s*[:\-.]?\s*\d{4,6}(?:\s*(?:,|&|/|\band\b)\s*(?:IS\s*[:\-.]?\s*)?\d{4,6})*", re.I)
_COUNTRY_PREP = re.compile(
    r"\b(?:based\s+in|located\s+in|country\s*[:\-]?|from|in)\s+(?:the\s+)?"
    r"([^\W\d_][\w.'\- ]{1,40}?)(?=\s*[,;()]|\s+(?:for|with|IS)\b|\s*$)", re.I)


def _nice_case(text: str) -> str:
    """Tidy capitalisation only when the user typed everything in lower case."""
    if text and text == text.lower():
        return text.upper() if len(text) <= 3 else text.title()
    return text


def parse_command_regex(text: str) -> dict:
    text = " ".join((text or "").split())

    # IS numbers: "IS 17632", "IS:17632", "IS 17632, 17633 and IS 17634"
    is_numbers = []
    for run in _IS_RUN.finditer(text):
        for num in re.findall(r"\d{4,6}", run.group(0)):
            if num not in is_numbers:
                is_numbers.append(num)

    # Country: prefer a phrase after in/from whose text is a known country.
    country = None
    country_start = None
    fallback = None
    for m in _COUNTRY_PREP.finditer(text):
        name = m.group(1).strip(" .")
        if is_known_country(name):
            country, country_start = name, m.start()
            break
        if fallback is None:
            fallback = (name, m.start())
    if country is None:
        for m in re.finditer(r"\(([A-Za-z.' \-]{2,40})\)", text):   # "Beta Corp (Turkey)"
            if is_known_country(m.group(1)):
                country, country_start = m.group(1).strip(), m.start()
                break
    if country is None:
        for seg in re.finditer(r"[^,;()]+", text):                    # "Acme Corp, Germany, IS 17632"
            if is_known_country(seg.group(0).strip(" .")):
                country, country_start = seg.group(0).strip(" ."), seg.start()
                break
    if country is None and fallback:
        country, country_start = fallback

    # Client: text after "for" / "client", up to the country, a comma, "for", "with" or the IS list.
    client_name = None
    m = re.search(r"\b(?:for|client\s*[:\-]?)\s+(?!IS\b)(.+)", text, re.I)
    if m:
        rest = m.group(1)
        offset = m.start(1)
        cuts = [len(rest)]
        if country_start is not None and country_start >= offset:
            cuts.append(country_start - offset)
        for pat in (r",", r"\(", r"\s+(?:for|with)\s", r"\bIS\s*[:\-.]?\s*\d"):
            c = re.search(pat, rest, re.I)
            if c:
                cuts.append(c.start())
        name = rest[:min(cuts)].strip(" ,.-")
        if name:
            client_name = _nice_case(name)

    return {"client_name": client_name,
            "country": _nice_case(country) if country else None,
            "is_numbers": is_numbers}


def parse_command_ai(text: str) -> dict:
    client = _get_client()
    if not client:
        return parse_command_regex(text)
    try:
        resp = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=400,
            messages=[{
                "role": "user",
                "content": (
                    "Extract quotation request fields from this instruction as strict JSON with keys "
                    "client_name (string or null), country (string or null), is_numbers (array of strings). "
                    f"Instruction: {text}\n\nRespond with ONLY the JSON object, nothing else."
                ),
            }],
        )
        raw = resp.content[0].text.strip()
        raw = re.sub(r"^```json\s*|\s*```$", "", raw.strip())
        data = json.loads(raw)
        data.setdefault("client_name", None)
        data.setdefault("country", None)
        data.setdefault("is_numbers", [])
        return data
    except Exception:
        return parse_command_regex(text)


def parse_command(text: str) -> dict:
    if ai_available():
        return parse_command_ai(text)
    return parse_command_regex(text)


# ---------------- Review narrative ----------------

def summarize_review_template(checks: list) -> str:
    mismatches = [c for c in checks if c.get("status") == "mismatch"]
    missing = [c for c in checks if c.get("status") == "missing"]
    warnings = [c for c in checks if c.get("status") == "warning"]
    if not mismatches and not missing and not warnings:
        return "Everything checks out — all fee items match the standard formula for this country and IS count."
    lines = []
    if mismatches:
        lines.append(f"{len(mismatches)} item(s) don't match the expected formula:")
        for c in mismatches:
            lines.append(f"  - {c['item']}: found {c['found']}, expected {c['expected']}")
    if missing:
        lines.append(f"{len(missing)} item(s) could not be found in the file:")
        for c in missing:
            lines.append(f"  - {c['item']} (expected {c['expected']})")
    if warnings:
        for c in warnings:
            lines.append(f"Note: {c['item']} — {c.get('note', '')}")
    return "\n".join(lines)


def summarize_review_ai(checks: list, context: str = "") -> str:
    client = _get_client()
    if not client:
        return summarize_review_template(checks)
    try:
        resp = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=500,
            messages=[{
                "role": "user",
                "content": (
                    "You are reviewing a BIS/FMCS certification quotation for correctness against a fixed "
                    "pricing formula. Here are the automated check results (JSON):\n"
                    f"{json.dumps(checks, indent=2)}\n\n"
                    f"Context: {context}\n\n"
                    "Write a short, direct summary (max 150 words) for the consultant preparing this quotation: "
                    "what's wrong (if anything), and what to fix. Do not restate items that are 'ok'. "
                    "If everything is fine, say so in one line."
                ),
            }],
        )
        return resp.content[0].text.strip()
    except Exception:
        return summarize_review_template(checks)


def summarize_review(checks: list, context: str = "") -> str:
    if ai_available():
        return summarize_review_ai(checks, context)
    return summarize_review_template(checks)
