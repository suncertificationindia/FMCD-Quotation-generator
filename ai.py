"""AI integration point.

Works with zero configuration using regex-based parsing / template summaries.
If ANTHROPIC_API_KEY is set in the environment, upgrades command parsing and
review summaries to use Claude for more flexible natural-language handling.
"""

import os
import re
import json

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

def parse_command_regex(text: str) -> dict:
    is_numbers = re.findall(r"IS\s*[- ]?(\d{4,6})", text, re.I)
    seen = set()
    is_numbers = [x for x in is_numbers if not (x in seen or seen.add(x))]

    country = None
    m = re.search(r"(?:from|in|country[:\s]+)\s+([A-Za-z][A-Za-z .]{2,30}?)(?=[,.]|\s+for\b|\s+with\b|$)", text, re.I)
    if m:
        country = m.group(1).strip()

    client_name = None
    m = re.search(r"(?:for|client)\s+([A-Z][A-Za-z0-9&.,'\- ]{2,50}?)(?:,|\s+(?:for|from|in)\s|$)", text)
    if m:
        client_name = m.group(1).strip().rstrip(",")

    return {"client_name": client_name, "country": country, "is_numbers": is_numbers}


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
