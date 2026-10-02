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
    sample_testing_usd: float = 0.0
    min_marking_fee_usd: float = 0.0
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

    bracket = classify_country(q.country)
    rate = q.exchange_rate

    md = man_days(n)
    pdd = per_diem_days(n)

    application_fee_usd = APPLICATION_FEE_INR_PER_IS / rate
    license_fee_usd = LICENSE_FEE_INR_PER_IS / rate
    inspection_usd = (md * INSPECTION_INR_PER_MAN_DAY) / rate
    travel_officer_usd = TRAVEL_OFFICER_INR[bracket] / rate
    per_diem_rate = PER_DIEM_USD_PER_DAY[bracket]
    per_diem_usd = pdd * per_diem_rate
    contingency_usd = CONTINGENCY_INR_FLAT / rate

    sample_testing_total = sum(i.sample_testing_usd for i in q.is_items)
    min_marking_total = sum(i.min_marking_fee_usd for i in q.is_items)
    consultancy_total = sum(i.consultancy_usd for i in q.is_items)

    total = (
        n * application_fee_usd
        + inspection_usd
        + travel_officer_usd
        + per_diem_usd
        + contingency_usd
        + sample_testing_total
        + min_marking_total
        + n * license_fee_usd
        + consultancy_total
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
            "application_fee_usd_each": round(application_fee_usd, 2),
            "inspection_usd": round(inspection_usd, 2),
            "travel_officer_usd": round(travel_officer_usd, 2),
            "per_diem_usd": round(per_diem_usd, 2),
            "contingency_usd": round(contingency_usd, 2),
            "sample_testing_per_is": [round(i.sample_testing_usd, 2) for i in q.is_items],
            "min_marking_per_is": [round(i.min_marking_fee_usd, 2) for i in q.is_items],
            "license_fee_usd_each": round(license_fee_usd, 2),
            "pbg_usd_each": PBG_USD_FLAT_PER_IS,
            "consultancy_per_is": [round(i.consultancy_usd, 2) for i in q.is_items],
        },
        "total_usd": round(total, 2),
    }
