"""isolved payroll runs and checks for the three employees of isolved.py.

Edge cases (payroll table, D-077): the full run history of each pay group (D-050) with a
completed regular run, a data conversion run (D-014), the same run number on another date, a
run not processed, and an unlisted run type; 404 on the second pay group's history (D-014).
Checks are listed on two pages and read from the detail route (D-016, D-081); the run join hits
a completed run, finds only a run not processed, or finds nothing; a listed check whose detail
is an empty list. Lines: memo earnings whose labels are in the memo table and outside it
(D-055), garnishment lines, tax labels in the label table and outside it (OREGON TRANSIT EE,
D-056), benefit lines, non-zero deposit lines (live: always 0) and a check type label outside
the table. netPay = grossPay - taxes - deductions - garnishments, and = checkAmount + deposits.
"""
from datetime import timedelta
from decimal import Decimal

from ..live.client import Reply
from ..live.fetch import WINDOW_DAYS
from ..live.plans import isolved as plan

from .common import FETCH_DATE, Builder, num, page_size
from .isolved_company import CLIENT, DEDUCTION, EARNING, LEGAL, MEMO

API = "/api/clients/{clientId}/legals/{legalId}"
R = {
    "runs": f"{API}/paygroupId/{{paygroupId}}/payrollRunHistory",
    "checks": f"{API}/checks",
    "check": f"{API}/employees/{{employeeId}}/checks/{{id}}",
}
CENT = Decimal("0.01")
TAX_IDS = {"FEDERAL WH": 701, "SOC SEC EE": 702, "MED EE": 703, "UTAH WH": 704, "OREGON TRANSIT EE": 705,
           "SOC SEC ER": 711, "MED ER": 712, "FUTA ER": 713, "UTAH SUI ER": 714}
NUMBERS = {70001: ("E-1001", "666-31-0001"), 70002: ("E-1002", "666-31-0002"), 70003: ("C-2001", "666-31-0003")}


def ts(day: str) -> str:
    return f"{day}T00:00:00"


def d(text: str) -> Decimal:
    return Decimal(text)


def pct(base: Decimal, rate: str) -> Decimal:
    return (base * Decimal(rate)).quantize(CENT)


def add(b: Builder, names: dict[int, str]) -> None:
    """``names``: employee id to the "Last, First" name the check stubs print."""
    b.part("payroll")
    history = _runs(b)
    checks = [
        _check(b, names, 880001, 70001, "2025-01-10", 101, "Regular", "2024-12-22", "2025-01-04", full=True),
        _check(b, names, 880002, 70002, "2025-01-10", 101, "Adjustment", "2024-12-22", "2025-01-04"),
        _check(b, names, 880003, 70001, "2025-01-24", 102, "Regular", "2025-01-05", "2025-01-18"),  # only a run not processed
        _check(b, names, 880004, 70003, "2018-06-15", 5, "Adjustment", "2018-06-01", "2018-06-14", contractor=True),  # conversion run
        _check(b, names, 880005, 70002, "2025-02-07", 103, "Regular", "2025-01-19", "2025-02-01"),  # no run with this number
    ]
    missing = _check(b, names, 880006, 70002, "2025-02-21", 104, "Regular", "2025-02-02", "2025-02-15")
    listed = [{**c, "taxes": []} for c in checks + [missing]]  # the list sends the same model with taxes empty (D-016)
    # Asked for the window the live fetch derives: 12 months to the latest completed run (D-092).
    last = plan.latest_completed([Reply(200, history)], FETCH_DATE)
    size = page_size("isolved", R["checks"])
    window = {"clientId": CLIENT, "legalId": LEGAL, "filter.fromDate": (last - timedelta(days=WINDOW_DAYS)).isoformat(),
              "filter.toDate": last.isoformat(), "filter.pageSize": size}
    b.add(R["checks"], {**window, "filter.page": 0},
          {"results": listed[:size], "totalItems": 6, "totalPages": 2, "nextPageUrl": "page=1", "previousPageUrl": None})
    b.add(R["checks"], {**window, "filter.page": 1},
          {"results": listed[size:], "totalItems": 6, "totalPages": 2, "nextPageUrl": None, "previousPageUrl": "page=0"})
    for check in checks:
        b.add(R["check"], {"clientId": CLIENT, "legalId": LEGAL, "employeeId": check["employeeId"], "id": check["id"]}, check)
    # A listed check whose detail call finds nothing: an empty list body (1 of 27 live).
    b.add(R["check"], {"clientId": CLIENT, "legalId": LEGAL, "employeeId": missing["employeeId"], "id": missing["id"]}, [])


def _runs(b: Builder) -> list[dict]:
    def run(values: dict) -> dict:
        return b.shaped(R["runs"], "[]", {"inputMethod": "Manual", "payOfTheMonth": "1", "processedBy": "payroll.ops", "processApprovedBy": "",
                                          "regularCheckAutoPay": True, "runTime": "14:05", "submittedBy": "", "submittedDate": None,
                                          "submittedTime": "", "suppressPayStubEmailAlert": False, "impoundDate": None, **values})

    history = [
        run({"id": 9001, "runNumber": 5, "payrollRunType": "Data Conversion", "status": "Completed Payroll Run", "payDate": ts("2018-06-15"),
             "scheduledPayDate": ts("2018-06-15"), "runDate": ts("2018-06-20"), "scheduledRunDate": None, "periodBeginDate": ts("2018-06-01"),
             "periodEndDate": ts("2018-06-14"), "payPeriod": 12}),
        # Same run number as 9101 on another date: the join needs the date too (D-050).
        run({"id": 9099, "runNumber": 101, "payrollRunType": "Regular Payroll", "status": "Completed Payroll Run", "payDate": ts("2024-01-12"),
             "scheduledPayDate": ts("2024-01-12"), "runDate": ts("2024-01-10"), "periodBeginDate": ts("2023-12-24"), "periodEndDate": ts("2024-01-06"),
             "payPeriod": 1}),
        run({"id": 9101, "runNumber": 101, "payrollRunType": "Regular Payroll", "status": "Completed Payroll Run", "payDate": ts("2025-01-10"),
             "scheduledPayDate": ts("2025-01-10"), "runDate": ts("2025-01-08"), "scheduledRunDate": ts("2025-01-08"),
             "periodBeginDate": ts("2024-12-22"), "periodEndDate": ts("2025-01-04"), "payPeriod": 1, "impoundDate": ts("2025-01-09"),
             "submittedBy": "lee.admin", "submittedDate": ts("2025-01-08"), "submittedTime": "09:12"}),
        run({"id": 9102, "runNumber": 102, "payrollRunType": "Regular Payroll", "status": "Payroll Not Processed", "payDate": ts("2025-01-24"),
             "scheduledPayDate": ts("2025-01-24"), "runDate": None, "periodBeginDate": ts("2025-01-05"), "periodEndDate": ts("2025-01-18"),
             "payPeriod": 2, "processedBy": ""}),
        # Not in the run type label table: unknown.
        run({"id": 9103, "runNumber": 1, "payrollRunType": "Off Cycle Payroll", "status": "Completed Payroll Run", "payDate": ts("2025-01-17"),
             "scheduledPayDate": None, "runDate": ts("2025-01-16"), "periodBeginDate": ts("2025-01-05"), "periodEndDate": ts("2025-01-18"),
             "payPeriod": 2}),
    ]
    b.add(R["runs"], {"clientId": CLIENT, "legalId": LEGAL, "paygroupId": 7625}, history)
    b.add(R["runs"], {"clientId": CLIENT, "legalId": LEGAL, "paygroupId": 7626}, None, status=404)  # D-014
    return history


def _line(item_id: int, code: str | None, label: str, sequence: int, dollars: Decimal, **extra) -> dict:
    zero = {f"{period}Dollars": num(dollars) for period in ("current", "ptd", "mtd", "qtd", "ytd", "ftd")}
    return {"id": item_id, "itemCode": code, "itemDescription": label, "sequence": sequence, "checkDollars": num(dollars), **zero, **extra}


def _earning(item_id: int, code: str | None, label: str, sequence: int, dollars: Decimal, hours: str = "0", units: str = "0", memo: bool = False) -> dict:
    return _line(item_id, code, label, sequence, dollars, isMemoEarning=memo, checkHours=num(hours), checkUnits=num(units),
                 currentHours=num(hours), currentUnits=num(units), ytdHours=num(hours), ytdUnits=num(units))


def _tax(label: str, sequence: int, wages: Decimal, dollars: Decimal, employee: bool) -> dict:
    return {"id": TAX_IDS[label], "itemCode": None, "itemDescription": label, "sequence": sequence, "isEmployeeTax": employee,
            "checkDollars": num(dollars), "checkTaxableWages": num(wages), "currentDollars": num(dollars), "currentTaxableWages": num(wages),
            "ytdDollars": num(dollars), "ytdTaxableWages": num(wages)}


def _benefit(title: str, eligible: Decimal, employee: Decimal, employer: Decimal) -> dict:
    return {"benefitTitle": title, "benefitDescription": title, "checkEligibleWages": num(eligible), "checkEmployeeCatchUp": 0,
            "checkEmployeeDeduction": num(employee), "checkEmployerContribution": num(employer), "checkMatchEligibleWages": num(eligible),
            "ytdEligibleWages": num(eligible), "ytdEmployeeDeduction": num(employee), "ytdEmployerContribution": num(employer)}


def _check(b: Builder, names: dict[int, str], check_id: int, employee: int, date: str, run_number: int, kind: str, start: str, end: str,
           full: bool = False, contractor: bool = False) -> dict:
    """One CheckModel. ``full``: every line kind (70001 on run 101)."""
    number, ssn = NUMBERS[employee]
    earnings, deductions, garnishments, taxes, benefits, deposits = [], [], [], [], [], []
    if contractor:
        gross = d("550.00")
        earnings = [_earning(EARNING["REG"], "REG", "Regular", 1, gross, hours="10")]
        pretax = section_125 = d("0")
    else:
        regular = d("1900.00") if employee == 70001 else d("2400.00")
        earnings = [_earning(EARNING["REG"], "REG", "Regular", 1, regular, hours="80")]
        gross = regular
        pretax = section_125 = d("0")
        if full:
            ot = d("106.88")
            earnings.append(_earning(EARNING["OT"], "OT", "Overtime", 2, ot, hours="3"))
            gross += ot
            # Memo earnings: in the memo table (employer contributions, D-055) and outside it (stay memo earnings).
            earnings += [_earning(MEMO["401k Match"], "401KM", "401k Match", 3, d("57.00"), memo=True),
                         _earning(MEMO["ER Medical"], "ERMED", "ER Medical", 4, d("310.00"), memo=True),
                         _earning(MEMO["ER Life"], None, "ER Life", 5, d("4.20"), memo=True)]
            k401, med = d("120.41"), d("60.00")
            pretax, section_125 = k401 + med, med
            deductions = [_line(DEDUCTION["401K"], "401K", "401(k)", 1, k401), _line(DEDUCTION["MEDPT"], "MEDPT", "Medical", 2, med)]
            # A garnishment line carries the employee's garnishment id (77) and no item code, as live (D-095).
            garnishments = [_line(77, None, "Federal Tax Levy", 1, d("75.00"))]
            benefits = [_benefit("401(k)", gross, k401, d("57.00")), _benefit("Medical", gross, med, d("310.00"))]
        elif employee == 70002:
            deductions = [_line(DEDUCTION["LOAN"], "LOAN", "401K Loan", 1, d("50.00"))]
        wages = gross - pretax
        fica = gross - section_125  # 401(k) contributions are FICA wages, Section 125 ones are not
        taxes = [_tax("FEDERAL WH", 1, wages, pct(wages, "0.07"), True),
                 _tax("SOC SEC EE", 2, fica, pct(fica, "0.062"), True),
                 _tax("MED EE", 3, fica, pct(fica, "0.0145"), True),
                 _tax("UTAH WH", 4, wages, pct(wages, "0.0455"), True),
                 _tax("SOC SEC ER", 6, fica, pct(fica, "0.062"), False),
                 _tax("MED ER", 7, fica, pct(fica, "0.0145"), False),
                 _tax("FUTA ER", 8, fica, pct(fica, "0.006"), False),
                 _tax("UTAH SUI ER", 9, fica, pct(fica, "0.012"), False)]
        if full:
            taxes.insert(4, _tax("OREGON TRANSIT EE", 5, wages, pct(wages, "0.001"), True))
    employee_taxes = sum((Decimal(str(t["checkDollars"])) for t in taxes if t["isEmployeeTax"]), d("0"))
    withheld = sum((Decimal(str(line["checkDollars"])) for line in deductions + garnishments), d("0"))
    net = gross - employee_taxes - withheld
    check_amount = net
    if full:
        savings = pct(net, "0.25")
        deposits = [{"id": 1, "account": "*****0045", "depositAmount": num(savings), "itemDescription": "Savings"},
                    {"id": 2, "account": "******1387", "depositAmount": num(net - savings), "itemDescription": "Checking"}]
        check_amount = d("0")
    deposit_total = net - check_amount
    return b.shaped(R["check"], "", {
        "id": check_id, "employeeId": employee, "employeeNumber": number, "employeeName": names[employee], "employeeSSN": ssn,
        "employeeAddress1": "10 Cedar St", "employeeAddress2": "", "employeeCity": "Portland", "employeeState": "OR", "employeeZipCode": "97201",
        "employeeFederalFilingStatus": "FDS", "employeeFederalExemptions": 1, "employeeFederalAddlAmountOrPercent": "15.00",
        "employeeStateFilingStatus": "UTS", "employeeStateExemptions": 0, "employeeStateAddlAmountOrPercent": "",
        "vertexResidentGeoCode": "380510000", "vertexWorkGeoCode": "450351000", "vertexSchoolDistrictCode": 0,
        "legalCompanyName": "Harbor Supply LLC", "checkNumber": 50000 + check_id % 1000, "checkSequence": 1, "voucherNumber": f"V{check_id}",
        "checkDate": ts(date), "periodBeginDate": ts(start), "periodEndDate": ts(end), "checkTypeDescription": kind,
        "payrollRunNumber": run_number, "payrollRunType": "Data Conversion" if contractor else "Regular Payroll",
        "reissueCheckDate": None, "reissueCheckNumber": None, "isRemoteWorker": employee == 70001,
        "grossPay": num(gross), "grossWages": num(gross - pretax), "netPay": num(net), "checkAmount": num(check_amount),
        "directDepositAmount": num(deposit_total), "directDeposits": deposits, "earnings": earnings, "deductions": deductions,
        "garnishments": garnishments, "taxes": taxes, "benefits": benefits,
        "accruals": [{"id": 1, "accrualName": "PTO", "amountAccrued": 3.08, "amountTaken": 0.0, "availableBalance": 40.5, "endingBalance": 40.5}] if full else [],
        "employeeOrganizations": [{"id": 1, "organizationId": 10, "displayOrder": 1, "title": "Department", "value": "FIN", "valueDescription": "Finance"}] if full else [],
    })
