"""Deterministic BIS/FMCS quotation calculation engine.

All formulas here were reverse-engineered from four real Sun Consultants
quotations (1, 2, 3 and 4 IS standards) and confirmed with the client.
Do not "improve" the math without re-validating against those examples.
"""

from dataclasses import dataclass, field
from typing import List, Optional
from countries import classify_country

APPLICATION_FEE_INR_PER_IS = 1000
LICENSE_FEE_INR_PER_IS = 1000
CONTINGENCY_INR_FLAT = 10000
INSPECTION_INR_PER_MAN_DAY = 7000
TRAVEL_OFFICER_INR = {"A": 300000, "B": 200000}
PER_DIEM_USD_PER_DAY = {"A": 400, "B": 300}
PBG_USD_FLAT_PER_IS = 10000
DEFAULT_CONSULTANCY_USD_PER_IS = 5000


@dataclass
class ISItem:
    is_number: str
    product_name: str = ""
    sample_testing_usd: Optional[float] = None   # must be entered by the user
    min_marking_fee_usd: Optional[float] = None  # must be entered by the user
    consultancy_usd: float = DEFAULT_CONSULTANCY_USD_PER_IS
    unit_price_inr: Optional[float] = None
    unit_size: Optional[str] = None
    annual_production: Optional[str] = None


@dataclass
class QuotationInput:
    client_name: str
    country: str
    exchange_rate: float  # INR per 1 USD
    is_items: List[ISItem] = field(default_factory=list)
    product: str = ""   # used only to choose the clients shown in the document pack
    industry: str = ""


def man_days(n):
    return n + 5


def per_diem_days(n):
    return n + 2


def calculate(q: QuotationInput) -> dict:
    n = len(q.is_items)
    if n == 0:
        raise ValueError("At least one IS standard is required")
    if q.exchange_rate <= 0:
        raise ValueError("Exchange rate must be positive")

    for i in q.is_items:
        if i.sample_testing_usd is None or i.min_marking_fee_usd is None:
            raise ValueError(f"Sample Testing and Minimum Marking Fee must be entered for IS {i.is_number}")

    bracket = classify_country(q.country)
    rate = q.exchange_rate

    md = man_days(n)
    pdd = per_diem_days(n)

    # Every line is rounded to 2 decimals first, and the total is the sum of
    # those rounded amounts, so the total always equals what the client sees.
    application_fee_usd = round(APPLICATION_FEE_INR_PER_IS / rate, 2)
    license_fee_usd = round(LICENSE_FEE_INR_PER_IS / rate, 2)
    inspection_usd = round((md * INSPECTION_INR_PER_MAN_DAY) / rate, 2)
    travel_officer_usd = round(TRAVEL_OFFICER_INR[bracket] / rate, 2)
    per_diem_rate = PER_DIEM_USD_PER_DAY[bracket]
    per_diem_usd = round(pdd * per_diem_rate, 2)
    contingency_usd = round(CONTINGENCY_INR_FLAT / rate, 2)

    sample_testing = [round(i.sample_testing_usd, 2) for i in q.is_items]
    min_marking = [round(i.min_marking_fee_usd, 2) for i in q.is_items]
    consultancy = [round(i.consultancy_usd, 2) for i in q.is_items]

    total = (
        n * application_fee_usd
        + inspection_usd
        + travel_officer_usd
        + per_diem_usd
        + contingency_usd
        + sum(sample_testing)
        + sum(min_marking)
        + n * license_fee_usd
        + sum(consultancy)
    )

    return {
        "n": n,
        "bracket": bracket,
        "exchange_rate": rate,
        "man_days": md,
        "per_diem_days": pdd,
        "per_diem_rate": per_diem_rate,
        "travel_officer_inr": TRAVEL_OFFICER_INR[bracket],
        "line_items": {
            "application_fee_usd_each": application_fee_usd,
            "inspection_usd": inspection_usd,
            "travel_officer_usd": travel_officer_usd,
            "per_diem_usd": per_diem_usd,
            "contingency_usd": contingency_usd,
            "sample_testing_per_is": sample_testing,
            "min_marking_per_is": min_marking,
            "license_fee_usd_each": license_fee_usd,
            "pbg_usd_each": PBG_USD_FLAT_PER_IS,
            "consultancy_per_is": consultancy,
        },
        "total_usd": round(total, 2),
    }
