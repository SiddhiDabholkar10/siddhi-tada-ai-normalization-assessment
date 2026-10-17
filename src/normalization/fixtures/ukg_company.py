"""UKG Ready company inputs: tax entities and code lookups, plus the pay period profiles shared
with the employee adapter (added by ukg_ready.py). There is no company resource (D-029).

Edge cases (company table, D-077): two EINs returned in full (sensitive, D-044), deduction codes
with the live-only id (D-031), profiles of every documented period type shape: every_n_weeks 2
(biweekly), a 3-week cycle not in the table (unknown), user_defined (unmapped), an inactive
profile, and an open-start sentinel 1900-12-31 (D-025).
"""
from .common import Builder

CID = "7001"
C = "/v2/companies/{cid}"
R = {
    "eins": f"{C}/lookup/eins",
    "deduction-codes": f"{C}/lookup/deduction-codes",
    "earning-codes": f"{C}/lookup/earning-codes",
    "pay-period-profiles": f"{C}/lookup/pay-period-profiles",
}
EINS = {501: ("Harbor Kitchens Inc", "84-2210457"), 502: ("Harbor Catering LLC", "84-2210458")}
DEDUCTION_CODES = {"401K": 801, "MED": 802, "DEN": 803, "401KL1": 804, "GARN": 805}
DEDUCTION_NAMES = {"401K": "401(k)", "MED": "Medical", "DEN": "Dental", "401KL1": "401K Loan 1", "GARN": "Garnishment"}
EARNING_CODES = {"REG": 701, "OT": 702, "GTL": 703, "TIPS": 704, "SAL": 705, "FEE": 706}
EARNING_NAMES = {"REG": "Regular", "OT": "Overtime", "GTL": "Group Term Life", "TIPS": "Tips", "SAL": "Salary", "FEE": "Contractor fee"}


def profiles() -> list[dict]:
    """lookup/pay-period-profiles items. 9001 and 9002 are the profiles employees link to."""
    return [
        {"id": 9001, "name": "Biweekly", "description": "Kitchen staff", "active": True, "effective_from": "1900-12-31", "effective_to": "2099-12-31",
         "is_user_profile": False, "period_type": {"type": "every_n_weeks", "params": {"num_weeks": 2, "start_date": "2024-01-05"}}},
        {"id": 9002, "name": "Weekly", "active": True, "period_type": {"type": "weekly", "params": {"week_day": "FRIDAY"}}},
        # A 3-week cycle: raw code every_n_weeks:3, not in the period type table (unknown).
        {"id": 9003, "name": "Three-weekly (retired)", "active": False, "effective_from": "2020-01-01", "effective_to": "2022-12-31",
         "is_user_profile": False, "period_type": {"type": "every_n_weeks", "params": {"num_weeks": 3, "start_date": "2020-01-03"}}},
        {"id": 9004, "name": "Seasonal calendar", "active": True, "is_user_profile": True, "period_type": {"type": "user_defined", "params": {}}},
        {"id": 9005, "name": "Semi-monthly", "active": True, "period_type": {"type": "semi_monthly", "params": {"starting_on_first": 1, "starting_on_sec": 16}}},
    ]


def add(b: Builder) -> None:
    b.part("company")
    b.add(R["eins"], {"cid": CID}, {"items": [
        {"id": ein, "ein_name": name, "ein_tax_id": tax_id, "ein_country_id": "USA", "ein_currency_code": "USD"} for ein, (name, tax_id) in EINS.items()]})
    # The documented lookup has no id; the demo sends one and statement lines refer to it (D-031, live-only row).
    b.add(R["deduction-codes"], {"cid": CID}, {"items": [
        {"id": code_id, "code": code, "name": DEDUCTION_NAMES[code], "external_id": f"D-{code}" if code != "GARN" else ""}
        for code, code_id in DEDUCTION_CODES.items()]})
    b.add(R["earning-codes"], {"cid": CID}, {"items": [
        {"id": code_id, "code": code, "name": EARNING_NAMES[code], **({"external_id": f"E-{code}"} if code in ("REG", "OT") else {})}
        for code, code_id in EARNING_CODES.items()]})
