"""UKG Ready deposits and benefit enrollments for the three accounts of ukg_ready.py. UKG has
no deduction setup source (the scheduled-deduction route is unavailable, D-030).

Edge cases (direct_deposit and benefit_enrollment tables, D-077):
- Deposits (deprecated route, D-030): every calc method (FULL, FLAT_AMOUNT, NET_PAY,
  GROSS_EARNING, DIRECT_DEPOSIT_PER_OF_REMAINDER); the 2099-12-31 open end and the 1900-12-31
  open start (D-025); every pre-note state shape incl. NA (unmapped); an inactive account; an
  unmapped frequency (HOLIDAY_TABLE) with its holiday profile; a short account number (demo
  data has 1 to 4 characters); an account with no deposits.
- Benefits: coverage labels Employee (employee_only), Waived (status waived), two other
  company labels in the table (unknown) and one outside it; an open coverage end.
"""
from .common import Builder, routing
from .ukg_company import CID

C = "/v2/companies/{cid}"
R = {
    "deposits": f"{C}/employees/{{aid}}/direct-deposits",
    "benefits": f"{C}/employees/{{aid}}/benefits",
}
CALC = {"FULL": "Full", "FLAT_AMOUNT": "Flat Amount", "NET_PAY": "% of Net Pay", "GROSS_EARNING": "% of Gross Earnings",
        "DIRECT_DEPOSIT_PER_OF_REMAINDER": "% of Remainder"}


def add(b: Builder) -> None:
    b.part("setups")
    _deposits(b)
    _benefits(b)


def _deposit(values: dict) -> dict:
    method = values.pop("method")
    frequency = values.pop("frequency", "EVERY_PAY")
    base = {"name": "", "description": "", "type": "DIRECT_DEPOSIT", "active": True, "active_from": "2023-01-01", "active_to": "2099-12-31",
            "calc_method": {"type": method, "display_name": CALC[method]}, "routing_type": "ABA", "cancel_pre_note": False,
            "payroll_frequency": {"type": frequency}, "currency": "USD", "used_in_pay_statement": True, "visible": True, "is_paypal": False,
            "arrearage_function": "DISCARD_UNDERFUNDED_AMOUNT", "_documents_count": 0, "_notes_count": 0,
            "_links": {"self": f"/direct-deposits/{values['id']}"}}
    return {**base, **values}


def _deposits(b: Builder) -> None:
    accounts = {
        1101: [
            _deposit({"id": 61, "sequence": 1, "method": "FLAT_AMOUNT", "amount": 100.0, "account_type": "CHECKING", "name": "Rent",
                      "routing_number": routing("410001"), "account_number": "330011", "pre_note_status": "COMPLETE_OK",
                      "pre_note_sent_date": "2023-01-03", "last_payroll": 100.0, "year_to_date": 100.0}),
            # Open start 1900-12-31 and open end 2099-12-31 (D-025).
            _deposit({"id": 62, "sequence": 2, "method": "NET_PAY", "percentage": 15.0, "account_type": "SAVINGS", "active_from": "1900-12-31",
                      "routing_number": routing("410002"), "account_number": "330012", "pre_note_status": "READY_TO_SEND",
                      "frequency": "EVERY_SCHEDULED_PAY", "pre_note_expiration_date": "2025-02-01"}),
            _deposit({"id": 63, "sequence": 3, "method": "FULL", "account_type": "CHECKING", "routing_number": routing("410003"),
                      "account_number": "7", "pre_note_status": "COMPLETE_OK"}),
        ],
        1102: [
            _deposit({"id": 64, "sequence": 1, "method": "GROSS_EARNING", "percentage": 10.0, "account_type": "CHECKING", "active": False,
                      "active_to": "2024-12-31", "routing_number": routing("410004"), "account_number": "990041", "pre_note_status": "CANCELED",
                      "frequency": "MONTHLY"}),
            _deposit({"id": 65, "sequence": 2, "method": "DIRECT_DEPOSIT_PER_OF_REMAINDER", "percentage": 50.0, "account_type": "SAVINGS",
                      "routing_number": routing("410005"), "account_number": "990042", "pre_note_status": "NA",
                      "payroll_frequency": {"type": "HOLIDAY_TABLE", "holiday_type": "SPECIFIC_HOLIDAY_PROFILE",
                                            "holiday_profile": {"id": 12, "display_name": "Company holidays"}}}),
            _deposit({"id": 66, "sequence": 3, "method": "FULL", "account_type": "CHECKING", "routing_number": routing("410006"),
                      "account_number": "990043", "pre_note_status": "SENT", "pre_note_sent_date": "2025-01-02"}),
        ],
        1103: [],
    }
    for aid, deposits in accounts.items():
        b.add(R["deposits"], {"cid": CID, "aid": aid}, {"deposits": deposits, "_total_count": len(deposits), "_routing_type": "ABA",
                                                        "is_eligible_for_paypal": False, "_links": {"add": f"/employees/{aid}/direct-deposits"}})


def _benefits(b: Builder) -> None:
    def enrollment(aid: int, values: dict) -> dict:
        return {"employee": {"account_id": aid}, "coverage_effective_to": "2099-12-31", **values}

    plans = {
        1101: [
            enrollment(1101, {"id": 71, "name": "Medical PPO", "coverage_level": "Employee", "benefit_plan": {"id": 91, "currency": "USD"},
                              "coverage_effective_from": "2025-01-01"}),
            enrollment(1101, {"id": 72, "name": "Dental", "coverage_level": "Waived", "benefit_plan": {"id": 92, "currency": "USD"},
                              "coverage_effective_from": "2025-01-01", "coverage_effective_to": "2025-12-31"}),
            enrollment(1101, {"id": 73, "name": "401k", "coverage_level": "Enter total annual contribution", "benefit_plan": {"id": 93},
                              "coverage_effective_from": "2023-01-01"}),
            # Not in the coverage label table: unknown.
            enrollment(1101, {"id": 74, "name": "Vision", "coverage_level": "Employee + Family", "benefit_plan": {"id": 94, "currency": "USD"},
                              "coverage_effective_from": "2025-01-01"}),
        ],
        1102: [
            enrollment(1102, {"id": 75, "name": "Life", "coverage_level": "75% Option", "benefit_plan": {"id": 95, "currency": "USD"},
                              "coverage_effective_from": "2024-03-04"}),
        ],
        1103: [],
    }
    for aid, rows in plans.items():
        b.add(R["benefits"], {"cid": CID, "aid": aid}, {"benefits": rows})
