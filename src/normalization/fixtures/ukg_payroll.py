"""UKG Ready payrolls and pay statements for the three accounts of ukg_ready.py.

Edge cases (payroll table, D-077): payroll statuses OPEN, FINALIZED (with date_finalized on
the detail), OPEN_FAILED and NEW; a type label outside the table; a payroll with no statements;
two EINs referenced by payrolls (D-029). Statements: hours in milliseconds (D-028); an earning
and a cash payment with the ee_amount key absent (null, never zero, so net pay is not derived:
reconciliation_incomplete, D-052, D-053); a Fringe payment (non-cash) and a fringe earning;
deduction lines with an employer amount (employer contribution lines); taxes with employee and
employer sides, a side with wages but no amount, names in the label table and outside it
('Wisconsin') and the OASDI alias; every earning type label; a statement type outside the table; messages.
"""
from datetime import timedelta
from decimal import Decimal

from ..live.client import Reply
from ..live.fetch import WINDOW_DAYS
from ..live.plans import ukg_ready as plan

from .common import FETCH_DATE, Builder, num
from .ukg_company import CID, DEDUCTION_CODES, DEDUCTION_NAMES, EARNING_CODES, EARNING_NAMES, EINS

C = "/v2/companies/{cid}"
R = {
    "payrolls": f"{C}/payrolls",
    "payroll": f"{C}/payrolls/{{id}}",
    "batches": f"{C}/payrolls/{{id}}/batches",
    "statements": f"{C}/payrolls/{{id}}/pay-statements",
    "statement": f"{C}/payrolls/{{id}}/pay-statements/{{id}}",
}
HOUR_MS = 3_600_000
CENT = Decimal("0.01")
TAXES = {"Federal Income Tax": (601, "FIT"), "Social Security": (602, "SS"), "OASDI": (608, "OASDI"), "Medicare": (603, "MED"), "Additional Medicare": (604, "AMED"),
         "Federal Unemployment Tax": (605, "FUTA"), "Wisconsin": (606, "WI"), "ER SUTA Wisconsin": (607, "WISUI")}


def d(text: str) -> Decimal:
    return Decimal(text)


def pct(base: Decimal, rate: str) -> Decimal:
    return (base * Decimal(rate)).quantize(CENT)


def add(b: Builder) -> None:
    b.part("payroll")
    payrolls = [
        _payroll(3001, "Biweekly 2025-01", "2024-12-22", "2025-01-04", "2025-01-10", "OPEN", 501),
        _payroll(3002, "Biweekly 2024-26", "2024-12-08", "2024-12-21", "2024-12-27", "FINALIZED", 501),
        _payroll(3003, "Catering 2025-01", "2024-12-22", "2025-01-04", "2025-01-10", "OPEN_FAILED", 502),
        # Not in the payroll type label table: unknown.
        _payroll(3004, "Year-end bonus", "2024-12-01", "2024-12-31", "2025-01-15", "NEW", 502, kind=(4, "Bonus")),
    ]
    # Asked for the window the live fetch derives: 12 months to the latest pay date (D-092).
    last = plan.latest_payroll(FETCH_DATE)(Reply(200, {"payrolls": payrolls}))
    b.add(R["payrolls"], plan.payroll_list(CID, last - timedelta(days=WINDOW_DAYS), last).params, {"payrolls": payrolls})
    detail_keys = ("id", "name", "start_date", "end_date", "pay_date", "type", "status", "ein", "billable")
    for payroll in payrolls[:3]:  # the detail repeats the list entry and adds only date_finalized (D-081)
        detail = {key: payroll[key] for key in detail_keys}
        if payroll["status"] == "FINALIZED":
            detail["date_finalized"] = "2024-12-26"
        b.add(R["payroll"], {"cid": CID, "id": payroll["id"]}, detail)
    b.add(R["batches"], {"cid": CID, "id": 3001}, {"batches": [
        {"id": 4001, "display_name": "Main batch", "status": "OPEN", "master": True, "type": {"id": 1, "display_name": "Regular", "active": True}},
        {"id": 4002, "display_name": "Tips import", "status": "CLOSED", "master": False, "type": {"id": 3, "display_name": "Import", "active": True}}]})

    statements = {
        3001: [_hourly(5001, "2025-01-10", "2024-12-22", "2025-01-04"), _contractor(5002)],
        3002: [_finalized(5003)],
        3003: [_salaried(5004)],
        3004: [],
    }
    for payroll_id, items in statements.items():
        listed = [{key: value for key, value in s.items() if key in ("id", "employee", "pay_date", "status", "type", "pay_period_start",
                                                                       "pay_period_end", "calcUpto", "emptyEarning")}
                  | {"_links": {"self": f"/payrolls/{payroll_id}/pay-statements/{s['id']}"}} for s in items]
        b.add(R["statements"], {"cid": CID, "id": payroll_id}, {"pay_statements": listed})
        for statement in items:
            # The template names both parameters {id}: the payroll id is kept as payroll_id (D-082).
            b.add(R["statement"], {"cid": CID, "payroll_id": payroll_id, "id": statement["id"]}, statement)


def _payroll(payroll_id: int, name: str, start: str, end: str, pay_date: str, status: str, ein: int, kind: tuple = (1, "Regular")) -> dict:
    ein_name, tax_id = EINS[ein]
    return {"id": payroll_id, "name": name, "start_date": start, "end_date": end, "pay_date": pay_date,
            "type": {"id": kind[0], "display_name": kind[1]}, "status": status,
            "ein": {"id": ein, "ein_name": ein_name, "ein_tax_id": tax_id, "ein_country_id": "USA"},
            "billable": True, "direct_deposit_date": pay_date, "dflt_pay_statement_type_id": 18432, "dflt_pay_stub_note": "",
            "_links": {"self": f"/payrolls/{payroll_id}"}}


BATCH = {"id": 4001, "display_name": "Main batch"}


def _earning(line_id: int, code: str, type_name: str, hours: str | None, rate: str | None, amount: Decimal | None) -> dict:
    line = {"id": line_id, "type_name": type_name, "batch": BATCH, "earning": {"id": EARNING_CODES[code], "code": code, "name": EARNING_NAMES[code]},
            "workers_comp_code": {"external_id": "9079"}, "shift": {"id": 1, "name": "Day"}, "cost_centers": [{"index": 0, "value": {"id": 8100}}]}
    if hours is not None:
        line["hours"] = int(Decimal(hours) * HOUR_MS)
        line["quantity"] = 0
    if rate is not None:
        line["base_rate"] = num(rate)
    if amount is not None:  # an absent key is a missing amount, never zero (D-053)
        line["ee_amount"] = num(amount)
    return line


def _deduction(line_id: int, code: str, type_name: str, ee: Decimal, er: Decimal | None = None, vendor: dict | None = None) -> dict:
    line = {"id": line_id, "type_name": type_name, "batch": BATCH, "deduction": {"id": DEDUCTION_CODES[code], "code": code, "name": DEDUCTION_NAMES[code]},
            "cost_centers": [], "workers_comp_code": {"external_id": "9079"}, "ee_amount": num(ee), "quantity": 0, "base_rate": 0}
    if er is not None:
        line["er_amount"] = num(er)
    if vendor:
        line["vendor"] = vendor
    return line


def _tax(line_id: int, name: str, ee: Decimal | None = None, er: Decimal | None = None, ee_wage: Decimal | None = None,
         er_wage: Decimal | None = None) -> dict:
    tax_id, code = TAXES[name]
    line = {"id": line_id, "type_name": "Tax", "batch": BATCH,
            "company_tax": {"id": tax_id, "code": code, "name": name, "abbrev": code, "external_id": f"T-{code}"}}
    for side, amount, wage in (("ee", ee, ee_wage), ("er", er, er_wage)):
        if amount is not None:
            line[f"{side}_amount"] = num(amount)
        if wage is not None:  # a side may send wages without an amount (CANONICAL_MODEL 8.4)
            line[f"{side}_subject_wage"] = num(wage)
            line[f"{side}_gross_wage"] = num(wage)
            line[f"{side}_gross_subject_wage"] = num(wage)
    return line


def _payment(line_id: int, type_name: str, amount: Decimal | None) -> dict:
    line = {"id": line_id, "type_name": type_name, "batch": BATCH, "hours": 0, "quantity": 0}
    if amount is not None:
        line["ee_amount"] = num(amount)
    return line


def _statement(statement_id: int, aid: int, pay_date: str, start: str, end: str, status: str = "OPEN", kind: str = "Regular", **lines) -> dict:
    return {"id": statement_id, "employee": {"account_id": aid}, "pay_date": pay_date, "status": status,
            "type": {"id": 18432 if kind == "Regular" else 18433, "display_name": kind}, "pay_period_start": start, "pay_period_end": end,
            "calcUpto": "NET", "emptyEarning": False, "earnings": [], "deductions": [], "taxes": [], "payments": [], "messages": [], **lines}


def _hourly(statement_id: int, pay_date: str, start: str, end: str) -> dict:
    """Account 1101: hours in ms, a fringe earning, a tips line with no amount, employer
    deduction amounts, taxes on both sides, deposits and a Fringe payment."""
    reg, ot, gtl = d("1560.00"), d("58.50"), d("3.10")
    cash = reg + ot
    k401, med, loan, garn = pct(cash, "0.06"), d("45.00"), d("25.00"), d("50.00")
    taxable = cash - k401 - med
    fit, ss, mc, wi = d("120.00"), pct(cash - med, "0.062"), pct(cash - med, "0.0145"), pct(taxable, "0.053")
    net = cash - (k401 + med + loan + garn) - (fit + ss + mc + wi)
    flat = d("100.00")
    return _statement(statement_id, 1101, pay_date, start, end, earnings=[
        _earning(1, "REG", "Earning", "80", "19.50", reg),
        _earning(2, "OT", "Earning (Auto)", "2", "29.25", ot),
        _earning(3, "GTL", "Earning (Fringe, Auto)", None, None, gtl),
        # Tips reported without an amount: null, never zero.
        _earning(4, "TIPS", "Earning (Auto Reduce)", "0", None, None),
    ], deductions=[
        _deduction(11, "401K", "Deduction", k401, er=pct(k401, "0.5"), vendor={"id": 7, "name": "Harbor 401k Trust"}),
        _deduction(12, "MED", "Deduction", med, er=d("150.00")),
        _deduction(13, "401KL1", "Deduction", loan),
        _deduction(14, "GARN", "Garnishment", garn),
    ], taxes=[
        _tax(21, "Federal Income Tax", ee=fit, ee_wage=taxable),
        _tax(22, "Social Security", ee=ss, er=ss, ee_wage=cash - med, er_wage=cash - med),
        _tax(23, "Medicare", ee=mc, er=mc, ee_wage=cash - med, er_wage=cash - med),
        # Wages without an amount on the employee side.
        _tax(24, "Additional Medicare", ee_wage=cash - med),
        _tax(25, "Federal Unemployment Tax", er=pct(cash - med, "0.006"), er_wage=cash - med),
        _tax(26, "Wisconsin", ee=wi, ee_wage=taxable),
        _tax(27, "ER SUTA Wisconsin", er=pct(cash - med, "0.031"), er_wage=cash - med),
    ], payments=[
        _payment(31, "Direct Deposit", flat),
        _payment(32, "Direct Deposit", net - flat),
        _payment(33, "Fringe", gtl),
    ])


def _contractor(statement_id: int) -> dict:
    """Account 1103: a fee and a check payment whose amount key is absent (net pay not derived)."""
    return _statement(statement_id, 1103, "2025-01-10", "2024-12-22", "2025-01-04", earnings=[
        _earning(1, "FEE", "Earning", None, None, d("1000.00")),
    ], payments=[_payment(31, "Check", None)])


def _finalized(statement_id: int) -> dict:
    """Account 1101 in the finalized payroll; a statement type outside the table."""
    reg = d("1482.00")
    fit, ss, mc = d("110.00"), pct(reg, "0.062"), pct(reg, "0.0145")
    net = reg - fit - ss - mc
    return _statement(statement_id, 1101, "2024-12-27", "2024-12-08", "2024-12-21", status="FINALIZED", kind="Manual", earnings=[
        _earning(1, "REG", "Earning", "76", "19.50", reg),
    ], taxes=[
        _tax(21, "Federal Income Tax", ee=fit, ee_wage=reg),
        _tax(22, "OASDI", ee=ss, er=ss, ee_wage=reg, er_wage=reg),
        _tax(23, "Medicare", ee=mc, er=mc, ee_wage=reg, er_wage=reg),
    ], payments=[_payment(31, "Direct Deposit", net)])


def _salaried(statement_id: int) -> dict:
    """Account 1102 under the second EIN: a salary line with no hours, a dental deduction, a
    payroll message."""
    sal = d("1846.15")
    den = d("12.50")
    fit, ss, mc = d("190.00"), pct(sal - den, "0.062"), pct(sal - den, "0.0145")
    net = sal - den - fit - ss - mc
    statement = _statement(statement_id, 1102, "2025-01-10", "2024-12-22", "2025-01-04", earnings=[
        _earning(1, "SAL", "Earning", None, "1846.15", sal),
    ], deductions=[_deduction(11, "DEN", "Deduction", den)], taxes=[
        _tax(21, "Federal Income Tax", ee=fit, ee_wage=sal - den),
        _tax(22, "Social Security", ee=ss, er=ss, ee_wage=sal - den, er_wage=sal - den),
        _tax(23, "Medicare", ee=mc, er=mc, ee_wage=sal - den, er_wage=sal - den),
    ], payments=[_payment(31, "Direct Deposit", net)])
    statement["messages"] = [{"id": 1, "type_name": "Warning", "message": {"text": "Payroll failed to open for one EIN", "severity": "WARNING"},
                              "batch": BATCH}]
    return statement
