"""Country -> pricing bracket classification.

Bracket A (higher rate: $400/day per-diem, INR 3,00,000 travel):
    USA, EU member states, UK, Switzerland, Norway, Turkey
Bracket B (everyone else): $300/day per-diem, INR 2,00,000 travel
"""

BRACKET_A_COUNTRIES = {
    "united states", "united states of america", "usa", "us",
    "austria", "belgium", "bulgaria", "croatia", "cyprus", "czechia",
    "czech republic", "denmark", "estonia", "finland", "france", "germany",
    "greece", "hungary", "ireland", "italy", "latvia", "lithuania",
    "luxembourg", "malta", "netherlands", "poland", "portugal", "romania",
    "slovakia", "slovenia", "spain", "sweden",
    "united kingdom", "uk", "great britain",
    "switzerland", "norway", "turkey", "turkiye",
    "europe", "european union", "eu",
}


def classify_country(country: str) -> str:
    """Returns 'A' (USA/Europe/Turkey higher bracket) or 'B' (everyone else)."""
    if not country:
        return "B"
    return "A" if country.strip().lower() in BRACKET_A_COUNTRIES else "B"
