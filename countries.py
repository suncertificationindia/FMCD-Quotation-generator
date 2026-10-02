"""Country -> pricing bracket classification.

Bracket A (higher rate: $400/day per-diem, INR 3,00,000 travel):
    USA, EU member states, UK, Switzerland, Norway, Turkey
Bracket B (everyone else): $300/day per-diem, INR 2,00,000 travel

A country that is in neither list below is "not recognised": it is still priced
in bracket B, but the app warns the user (see is_known_country).
"""

import re
import unicodedata

# Proper-cased names shown as suggestions in the Country box.
BRACKET_A_NAMES = [
    "United States", "United Kingdom", "England", "Scotland", "Wales", "Northern Ireland",
    "Switzerland", "Norway", "Turkey", "Europe", "European Union",
    "Austria", "Belgium", "Bulgaria", "Croatia", "Cyprus", "Czechia", "Denmark", "Estonia",
    "Finland", "France", "Germany", "Greece", "Hungary", "Ireland", "Italy", "Latvia",
    "Lithuania", "Luxembourg", "Malta", "Netherlands", "Poland", "Portugal", "Romania",
    "Slovakia", "Slovenia", "Spain", "Sweden",
]

# Other spellings that must also be treated as bracket A.
BRACKET_A_ALIASES = [
    "usa", "us", "united states of america", "america", "uk", "great britain", "britain",
    "turkiye", "czech republic", "republic of ireland", "eu", "holland",
]

BRACKET_B_NAMES = [
    "Afghanistan", "Albania", "Algeria", "Andorra", "Angola", "Argentina", "Armenia",
    "Australia", "Azerbaijan", "Bahamas", "Bahrain", "Bangladesh", "Barbados", "Belarus",
    "Belize", "Benin", "Bhutan", "Bolivia", "Bosnia and Herzegovina", "Botswana", "Brazil",
    "Brunei", "Burkina Faso", "Burundi", "Cambodia", "Cameroon", "Canada", "Cape Verde",
    "Central African Republic", "Chad", "Chile", "China", "Colombia", "Comoros", "Congo",
    "Costa Rica", "Cote d'Ivoire", "Cuba", "Democratic Republic of the Congo", "Djibouti",
    "Dominican Republic", "Ecuador", "Egypt", "El Salvador", "Eritrea", "Eswatini",
    "Ethiopia", "Fiji", "Gabon", "Gambia", "Georgia", "Ghana", "Guatemala", "Guinea",
    "Guyana", "Haiti", "Honduras", "Hong Kong", "Iceland", "India", "Indonesia", "Iran",
    "Iraq", "Israel", "Jamaica", "Japan", "Jordan", "Kazakhstan", "Kenya", "Kosovo",
    "Kuwait", "Kyrgyzstan", "Laos", "Lebanon", "Lesotho", "Liberia", "Libya",
    "Liechtenstein", "Macau", "Madagascar", "Malawi", "Malaysia", "Maldives", "Mali",
    "Mauritania", "Mauritius", "Mexico", "Moldova", "Monaco", "Mongolia", "Montenegro",
    "Morocco", "Mozambique", "Myanmar", "Namibia", "Nepal", "New Zealand", "Nicaragua",
    "Niger", "Nigeria", "North Korea", "North Macedonia", "Oman", "Pakistan", "Palestine",
    "Panama", "Papua New Guinea", "Paraguay", "Peru", "Philippines", "Qatar", "Russia",
    "Rwanda", "Saudi Arabia", "Senegal", "Serbia", "Sierra Leone", "Singapore",
    "Somalia", "South Africa", "South Korea", "South Sudan", "Sri Lanka", "Sudan",
    "Suriname", "Syria", "Taiwan", "Tajikistan", "Tanzania", "Thailand", "Togo",
    "Trinidad and Tobago", "Tunisia", "Turkmenistan", "Uganda", "Ukraine",
    "United Arab Emirates", "Uruguay", "Uzbekistan", "Venezuela", "Vietnam", "Yemen",
    "Zambia", "Zimbabwe",
]

BRACKET_B_ALIASES = [
    "uae", "korea", "republic of korea", "viet nam", "ivory coast", "burma", "prc",
    "peoples republic of china", "swaziland", "czech", "dr congo", "drc",
    "republic of the congo", "russian federation", "bosnia", "macao",
]


def normalize_country(country: str) -> str:
    """lower-case, accents and full stops removed, leading 'the' dropped."""
    s = unicodedata.normalize("NFKD", country or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower().replace(".", "").replace("'", "").replace("’", "")
    s = re.sub(r"\s+", " ", s).strip()
    if s.startswith("the "):
        s = s[4:]
    return s


BRACKET_A_COUNTRIES = {normalize_country(c) for c in BRACKET_A_NAMES + BRACKET_A_ALIASES}
_B_ALIASES = {normalize_country(c) for c in BRACKET_B_ALIASES} - BRACKET_A_COUNTRIES
BRACKET_B_COUNTRIES = {normalize_country(c) for c in BRACKET_B_NAMES} | _B_ALIASES
KNOWN_COUNTRIES = BRACKET_A_COUNTRIES | BRACKET_B_COUNTRIES

# Cleaned list shown in the Country drop-down suggestions.
COUNTRY_SUGGESTIONS = sorted(set(BRACKET_A_NAMES) | set(BRACKET_B_NAMES))


def is_known_country(country: str) -> bool:
    return normalize_country(country) in KNOWN_COUNTRIES


def classify_country(country: str) -> str:
    """Returns 'A' (USA/Europe/Turkey higher bracket) or 'B' (everyone else)."""
    return "A" if normalize_country(country) in BRACKET_A_COUNTRIES else "B"
