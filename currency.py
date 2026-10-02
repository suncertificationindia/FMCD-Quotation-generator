"""Live INR/USD exchange rate lookup, with graceful fallback."""

import requests

FALLBACK_RATE = 91.0  # used only if all live sources fail
_cache = {"rate": None}


def get_live_inr_per_usd() -> dict:
    """Returns {'rate': float, 'source': str, 'live': bool}."""
    sources = [
        ("https://api.frankfurter.app/latest?from=USD&to=INR", lambda d: d["rates"]["INR"]),
        ("https://open.er-api.com/v6/latest/USD", lambda d: d["rates"]["INR"]),
    ]
    for url, extractor in sources:
        try:
            resp = requests.get(url, timeout=5)
            resp.raise_for_status()
            rate = float(extractor(resp.json()))
            if rate > 0:
                _cache["rate"] = rate
                return {"rate": round(rate, 4), "source": url, "live": True}
        except Exception:
            continue
    if _cache["rate"]:
        return {"rate": _cache["rate"], "source": "cached", "live": False}
    return {"rate": FALLBACK_RATE, "source": "fallback", "live": False}
