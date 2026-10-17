"""PrismHR payroll runs and vouchers for the three employees of prismhr.py.

Edge cases (payroll table, D-077): batch types R, V, J and S; batch statuses COMP, INITFAIL and
the unmapped TS.READY; a batch with no getBatchInfo and one whose info type is blank (V, D-081);
the voucher list paged over two calls (D-022) and sent under the live key payrollVoucher
(D-062); a regular voucher with every line kind, deposits masked with and without visible
digits (D-024) and a FRINGE detail while otherEarnAmount is 0 (D-023); a check-paid hourly
voucher with an hours code and a unit code (D-051); a contractor voucher with no taxes; a
reversal voucher (V batch, voidVoucherId and voidDate, D-033); a type J adjustment whose MEMO
earning is offset by a deduction (net 0, D-023); a type A arrears voucher with zero pay that
keeps its benefit and employer contribution lines and null retirement amounts (D-033); a type V
vacation voucher; tax labels in the label table and outside it (UT Income Tax, UT Unemployment,
D-056). Totals hold the live arithmetic: netPay = checkAmt + deposits, and (except the J
voucher) netPay = earnAmount - employee taxes - deductions.
"""
from datetime import timedelta
from decimal import Decimal

from ..live.client import Reply
from ..live.fetch import WINDOW_DAYS
from ..live.plans import prismhr as plan
from .common import FETCH_DATE, Builder, num, page_size, routing
from .prismhr_company import CLIENT, OK

R = {
    "batches": "/payroll/v1/getBatchListByDate",
    "info": "/payroll/v1/getBatchInfo",
    "vouchers": "/payroll/v1/getPayrollVoucherForBatch",
}
CENT = Decimal("0.01")
FIT, SS_EE, MED_EE = "00-10", "00-11", "00-12"
SS_ER, MED_ER, FUTA = "00-21", "00-22", "00-23"
UT_SIT, UT_SUI = "45-10", "45-30"


def add(b: Builder) -> None:
    b.part("payroll")
    batches = [
        _batch(b, "20250110-01", "2025-01-10", "R", "COMP", [("BW", "2024-12-22", "2025-01-04", "1"), ("MO", "2024-12-01", "2024-12-31", "1")]),
        _batch(b, "20250124-01", "2025-01-24", "R", "COMP", [("BW", "2025-01-05", "2025-01-18", "2")]),
        _batch(b, "20250128-V1", "2025-01-28", "V", "COMP", [("BW", "2024-12-22", "2025-01-04", "1")]),
        _batch(b, "20250131-J1", "2025-01-31", "J", "COMP", [("BW", "2025-01-05", "2025-01-18", "2")]),
        _batch(b, "20250207-S1", "2025-02-07", "S", "INITFAIL", [("BW", "2025-01-19", "2025-02-01", "3")]),
        _batch(b, "20250214-S2", "2025-02-14", "S", "TS.READY", [("BW", "2025-02-02", "2025-02-15", "4")]),
    ]
    # Stored under the window the live fetch asks for: 12 months to the latest COMP pay date (D-092).
    last = plan.latest_completed(FETCH_DATE)(Reply(200, {**OK, "batchList": batches}))
    b.add(R["batches"], plan.batch_call(CLIENT, last - timedelta(days=WINDOW_DAYS), last).params, {**OK, "batchList": batches})
    descriptions = {"20250110-01": "Biweekly 1 and December monthly", "20250124-01": "Biweekly 2", "20250128-V1": "Reverse voucher 000102",
                    "20250131-J1": "Memo adjustment", "20250214-S2": "Vacation payout"}
    for batch in batches:
        if batch["batchId"] in descriptions:  # 20250207-S1 has no getBatchInfo in the bundle
            _info(b, batch, descriptions[batch["batchId"]])

    v1 = _salaried(b, "000101", "20250110-01", "2025-01-10", "2024-12-22", "2025-01-04", "1", "900101")
    v2 = _hourly(b, "000102", "20250110-01", "2025-01-10", "2024-12-22", "2025-01-04", "1", "4410")
    v3 = _contractor(b, "000103", "20250110-01", "2025-01-10")
    _page(b, "20250110-01", [v1, v2, v3])
    v4 = _salaried(b, "000104", "20250124-01", "2025-01-24", "2025-01-05", "2025-01-18", "2", "900104", from_arrears=True)
    v5 = _arrears(b, "000105", "20250124-01")
    v6 = _hourly(b, "000106", "20250124-01", "2025-01-24", "2025-01-05", "2025-01-18", "2", "4411")
    _page(b, "20250124-01", [v4, v5, v6])
    _page(b, "20250128-V1", [_reversal(v2, "000107", "20250128-V1", "2025-01-28")])
    _page(b, "20250131-J1", [_adjustment(b, "000108", "20250131-J1")])
    _page(b, "20250207-S1", [])
    _page(b, "20250214-S2", [_vacation(b, "000109", "20250214-S2")])


def _page(b: Builder, batch: str, vouchers: list[dict]) -> None:
    """The voucher list in pages as live sends it (D-022): ``startpage`` is a page index from 0 and
    ``count`` echoes the page size, also on the last page (client 136 batch 202537: total 66,
    page 1 held 16 with count 50). Lists of more than one page test the paging."""
    size = page_size("prismhr", R["vouchers"])
    chunks = [vouchers[i:i + size] for i in range(0, len(vouchers), size)] or [[]]
    for number, chunk in enumerate(chunks):
        b.add(R["vouchers"], {"clientId": CLIENT, "batchId": batch, "count": size, "startpage": number},
              {**OK, "payrollVoucher": chunk, "total": len(vouchers), "startpage": number, "count": size})


def _batch(b: Builder, batch: str, pay_date: str, kind: str, status: str, groups: list[tuple]) -> dict:
    return b.shaped(R["batches"], "batchList[]", {
        "batchId": batch, "payDate": pay_date, "batchType": kind, "batchStatus": status,
        "payGroup": [{"payGroupId": group, "payPeriodStartDate": start, "payPeriodEndDate": end, "weeksWorked": "2" if group == "BW" else "4",
                      "deductPeriod": period} for group, start, end, period in groups],
    })


def _info(b: Builder, batch: dict, description: str) -> None:
    control = b.shaped(R["info"], "batchControl", {
        "batchId": batch["batchId"], "batchStatus": batch["batchStatus"], "payDate": batch["payDate"], "batchDescription": description,
        # The live info type is blank on V batches while the list sends V (D-081).
        "batchType": "" if batch["batchType"] == "V" else batch["batchType"],
        "processor": "pr.ops", "deliveryDate": batch["payDate"], "deliveryMethod": "UPS", "actualShipMethod": "UPS Ground",
        "actualShipDate": batch["payDate"],
        "voucher": [{"payGroupId": g["payGroupId"], "periodStart": g["payPeriodStartDate"], "periodEnd": g["payPeriodEndDate"],
                     "weeksWorked": int(g["weeksWorked"]), "deductPeriod": g["deductPeriod"], "payPeriod": g["deductPeriod"]}
                    for g in batch["payGroup"]],
    })
    b.add(R["info"], {"clientId": CLIENT, "batchId": batch["batchId"]}, {**OK, "batchControl": control})


def d(text: str) -> Decimal:
    return Decimal(text)


def pct(base: Decimal, rate: str) -> Decimal:
    return (base * Decimal(rate)).quantize(CENT)


def _voucher(b: Builder, values: dict) -> dict:
    """A voucher with the live defaults; ``values`` are already JSON values."""
    base = {
        "status": "PRNT", "type": "R", "voidDate": "", "voidVoucherId": "", "payGroup": "BW", "checkNum": "", "payStubType": "E",
        "isManualCheck": False, "hsaPeoMatch": 0, "importBatchNo": "", "otherEarnAmount": 0, "wcHomeClass": "8810", "wcState": "UT",
        "workerComp": [], "earning": [], "otherEarningsDetail": [], "fsaMatch": [], "companyTax": [], "employeeTax": [], "deduction": [],
        "otherDeduction": [], "benefit": [], "directDeposit": [], "employerContributions": [], "taxFilingStatus": [], "fromArrears": [],
        "toArrears": [], "checkAmt": 0, "bankAccount": "****4455", "checkAccountACH": "A",
    }
    return b.shaped(R["vouchers"], "payrollVouchers[]", {**base, **values})


def _retirement(values: dict | None) -> dict:
    fields = ("baseEarnings", "electiveContributionsPreTax", "catchUpContributionsPreTax", "rothContributionsPostTax",
              "rothCatchUpContributionsPostTax", "employeeContributionsPostTax", "employerMatchingContributions",
              "employerNonElectiveContributions", "employerSafeHarborMatchType1", "employerSafeHarborMatchType2", "peoMatchingContribution",
              "employeeRetirementLoanPayments")
    if values is None:  # arrears vouchers: every amount null, not zero (D-033)
        return {"planId": "", "planYearPeriod": "", **{field: None for field in fields}}
    return {"planId": "401K1", "planYearPeriod": values.pop("period"), **{field: num(values.get(field, "0")) for field in fields}}


def _emp_tax(code: str, label: str, taxable: Decimal, amount: Decimal, over: str = "0") -> dict:
    return {"empTaxDeductCode": code, "empTaxDeductCodeDesc": label, "empTaxableAmount": num(taxable), "empTaxAmount": num(amount),
            "empOverLimitAmount": num(over)}


def _com_tax(code: str, label: str, taxable: Decimal, rate: str, kind: str, exempt: str = "0") -> dict:
    return {"comTaxEntity": "1001", "comTaxDeductCode": code, "comTaxDeductCodeDesc": label, "comExemptAmount": num(exempt),
            "comShelteredAmount": 0, "comTaxableAmount": num(taxable), "comTaxType": kind, "comTaxAmount": num(pct(taxable, rate)),
            "comOvrLimit": 0, "comTaxRate": num(rate), "comClientSutaRpt": "Y" if kind == "SUI" else ""}


def _deduction(code: str, description: str, kind: str, amount: Decimal, plan: str = "") -> dict:
    return {"deductCode": code, "deductDescription": description, "deductAmount": num(amount), "deductType": kind, "deductUnionId": "", "planId": plan}


def _salaried(b: Builder, voucher: str, batch: str, pay_date: str, start: str, end: str, period: str, check: str,
              from_arrears: bool = False) -> dict:
    """P00001: salaried, pre-tax 401(k) and Section 125 deductions, a loan and a garnishment,
    taxes in and outside the label table, three deposits, benefit and contribution lines."""
    regular = d("2884.62")
    fringe = d("12.50")
    k401, med, den, ltd, loan, garn = d("173.08"), d("85.40"), d("12.00"), d("9.38"), d("50.00"), d("100.00")
    fit_wages = regular - k401 - med - den
    fica_wages = regular - med - den
    taxes = [
        _emp_tax(FIT, "Federal Income Tax", fit_wages, d("250.00")),
        _emp_tax(SS_EE, "Soc Security - Employee", fica_wages, pct(fica_wages, "0.062")),
        _emp_tax(MED_EE, "Medicare - Employee", fica_wages, pct(fica_wages, "0.0145")),
        _emp_tax(UT_SIT, "UT Income Tax", fit_wages, pct(fit_wages, "0.0455")),
    ]
    deductions = [_deduction("401K", "401(k)", "K", k401), _deduction("MED", "Medical", "C", med, "MED1"),
                  _deduction("DEN", "Dental", "C", den, "DEN1"), _deduction("LTD", "Long-term disability", "P", ltd, "LTD1"),
                  _deduction("LOAN", "Payroll advance", "L", loan), _deduction("GARN", "Child support", "G", garn)]
    total_taxes = sum(Decimal(str(t["empTaxAmount"])) for t in taxes)
    net = regular - total_taxes - (k401 + med + den + ltd + loan + garn)
    fixed = d("200.00")
    percent = ((net - fixed) * d("0.25")).quantize(CENT)
    return _voucher(b, {
        "voucherId": voucher, "batchId": batch, "employeeId": "P00001", "checkNumber": check, "payDate": pay_date, "payPeriod": period,
        "payPeriodStart": start, "payPeriodEnd": end, "dateProcessed": pay_date, "earnAmount": num(regular), "totalEarnings": num(regular + fringe),
        "fitTaxableAmount": num(fit_wages), "netPay": num(net),
        "earning": [{"payCode": "REG", "payClass": "E", "payClassDescription": "Earnings", "chargeDate": end, "hoursUnits": 80, "hoursWorked": 80,
                     "unitRate": num("36.0577"), "payAmount": num(regular), "division": "EAST", "jobCode": "ACCT", "shift": "1",
                     "department": "FIN", "location": "SLC", "glCode": "5000", "workComp": "8810", "projWork": "", "projPhase": ""}],
        # otherEarnAmount stays 0 while the detail list has a FRINGE amount (D-023).
        "otherEarningsDetail": [{"otherEarnCode": "FRINGE", "otherEarnsDesc": "Group term life", "otherEarnAmount": num(fringe)}],
        "employeeTax": taxes,
        "companyTax": [_com_tax(SS_ER, "Soc Security - Employer", fica_wages, "0.062", "FICA"),
                       _com_tax(MED_ER, "Medicare - Employer", fica_wages, "0.0145", "MEDI"),
                       _com_tax(FUTA, "Fed Unemployment", fica_wages, "0.006", "FUTA"),
                       _com_tax(UT_SUI, "UT Unemployment", fica_wages, "0.012", "SUI", exempt="97.40")],
        "deduction": deductions,
        "benefit": [{"planId": "MED1", "premiumAmt": num("420.00"), "premiumCost": num("410.00"), "empContrib": num(med), "empDeduct": num(med),
                     "coveragePeriod": "202501", "adjRef": ""},
                    {"planId": "LTD1", "premiumAmt": num("37.50"), "premiumCost": num("37.50"), "empContrib": num(ltd), "empDeduct": num(ltd),
                     "coveragePeriod": "202501", "adjRef": ""}],
        "employerContributions": [{"code": "MED1", "description": "Medical employer share", "amount": num("334.60")},
                                  {"code": "401K", "description": "401(k) match", "amount": num("86.54")}],
        "retirement": _retirement({"period": "2025-" + period.zfill(2), "baseEarnings": str(regular), "electiveContributionsPreTax": str(k401),
                                   "employerMatchingContributions": "86.54"}),
        "directDeposit": [{"transitNum": routing("210001"), "accountNum": "****", "status": "D*S", "amount": num(fixed)},
                          {"transitNum": routing("210002"), "accountNum": "****6789", "status": "D*C", "amount": num(percent)},
                          {"transitNum": routing("210003"), "accountNum": "****1234", "status": "D*C", "amount": num(net - fixed - percent)}],
        "taxFilingStatus": [{"taxAuthId": FIT, "taxAuthName": "Federal", "filingStatus": "M", "allowances": "2", "overrideType": "A", "overrideAmount": "25.00"},
                            {"taxAuthId": UT_SIT, "taxAuthName": "Utah", "filingStatus": "H", "allowances": "1", "overrideType": "F", "overrideAmount": "40.00"}],
        "workerComp": [{"wcClass": "8810", "wcTaxablePay": num(regular), "wcPremAmount": num("5.77"), "wcBillAmount": num("7.21"), "wcPremBill": num("7.21")}],
        "fromArrears": [{"dedCode": "LTD", "dedDescription": "Long-term disability", "arrearsAmt": "9.38", "arrearsDate": "2024-12-20",
                         "arrearsRefNo": "AR-1", "coveragePeriod": "202412", "planId": "LTD1", "unionId": "", "loanNo": ""}] if from_arrears else [],
    })


def _hourly(b: Builder, voucher: str, batch: str, pay_date: str, start: str, end: str, period: str, check: str) -> dict:
    """P00002: hourly, an hours code (REG, OT) and a unit code (PIECE), an IRS levy (VG), paid by check."""
    reg, ot, piece = d("1800.00"), d("168.75"), d("30.00")
    gross = reg + ot + piece
    char, levy = d("10.00"), d("150.00")
    taxes = [_emp_tax(FIT, "Federal Income Tax", gross, d("160.00")),
             _emp_tax(SS_EE, "Soc Security - Employee", gross, pct(gross, "0.062")),
             _emp_tax(MED_EE, "Medicare - Employee", gross, pct(gross, "0.0145")),
             _emp_tax(UT_SIT, "UT Income Tax", gross, pct(gross, "0.0455"))]
    net = gross - sum(Decimal(str(t["empTaxAmount"])) for t in taxes) - char - levy
    line = {"chargeDate": end, "division": "", "jobCode": "WHSE", "shift": "2", "department": "OPS", "location": "SLC", "glCode": "5100",
            "workComp": "8810", "projWork": "", "projPhase": ""}
    return _voucher(b, {
        "voucherId": voucher, "batchId": batch, "employeeId": "P00002", "checkNumber": check, "payDate": pay_date, "payPeriod": period,
        "payPeriodStart": start, "payPeriodEnd": end, "dateProcessed": pay_date, "earnAmount": num(gross), "totalEarnings": num(gross),
        "fitTaxableAmount": num(gross), "netPay": num(net), "checkAmt": num(net), "payStubType": "P", "bankAccount": "****8812",
        "earning": [{**line, "payCode": "REG", "payClass": "E", "payClassDescription": "Earnings", "hoursUnits": 80, "hoursWorked": 80,
                     "unitRate": num("22.50"), "payAmount": num(reg)},
                    {**line, "payCode": "OT", "payClass": "E", "payClassDescription": "Earnings", "hoursUnits": 5, "hoursWorked": 5,
                     "unitRate": num("33.75"), "payAmount": num(ot)},
                    {**line, "payCode": "PIECE", "payClass": "E", "payClassDescription": "Earnings", "hoursUnits": 120, "hoursWorked": 0,
                     "unitRate": num("0.25"), "payAmount": num(piece)}],
        "employeeTax": taxes,
        "companyTax": [_com_tax(SS_ER, "Soc Security - Employer", gross, "0.062", "FICA"),
                       _com_tax(MED_ER, "Medicare - Employer", gross, "0.0145", "MEDI"),
                       _com_tax(FUTA, "Fed Unemployment", gross, "0.006", "FUTA")],
        "deduction": [_deduction("CHAR", "Charity", "V", char), _deduction("IRS", "IRS Levy", "VG", levy)],
        "retirement": _retirement({"period": "2025-" + period.zfill(2)}),
        "taxFilingStatus": [{"taxAuthId": FIT, "taxAuthName": "Federal", "filingStatus": "SS", "allowances": "0", "overrideType": "", "overrideAmount": ""}],
        "workerComp": [{"wcClass": "8810", "wcTaxablePay": num(gross), "wcPremAmount": num("3.99"), "wcBillAmount": num("5.00"), "wcPremBill": num("5.00")}],
    })


def _contractor(b: Builder, voucher: str, batch: str, pay_date: str) -> dict:
    """P00003: monthly pay group, 1099 contractor, a unit code, no taxes, paid by check."""
    fee = d("1500.00")
    return _voucher(b, {
        "voucherId": voucher, "batchId": batch, "employeeId": "P00003", "checkNumber": "4409", "payDate": pay_date, "payPeriod": "1",
        "payPeriodStart": "2024-12-01", "payPeriodEnd": "2024-12-31", "dateProcessed": pay_date, "payGroup": "MO", "earnAmount": num(fee),
        "totalEarnings": num(fee), "fitTaxableAmount": 0, "netPay": num(fee), "checkAmt": num(fee), "payStubType": "P", "wcHomeClass": "",
        "earning": [{"payCode": "CONTR", "payClass": "E", "payClassDescription": "Earnings", "chargeDate": "2024-12-31", "hoursUnits": 1,
                     "hoursWorked": 0, "unitRate": num(fee), "payAmount": num(fee), "department": "OPS"}],
        "retirement": _retirement({"period": "2025-01"}),
    })


def _arrears(b: Builder, voucher: str, batch: str) -> dict:
    """P00001 type A arrears voucher: zero pay, but benefit and employer contribution lines that
    exist only here, and retirement amounts null (D-033)."""
    return _voucher(b, {
        "voucherId": voucher, "batchId": batch, "employeeId": "P00001", "type": "A", "checkNumber": "", "payDate": "2025-01-24",
        "payPeriod": "2", "payPeriodStart": "2025-01-05", "payPeriodEnd": "2025-01-18", "dateProcessed": "2025-01-23", "earnAmount": 0,
        "totalEarnings": 0, "fitTaxableAmount": 0, "netPay": 0, "checkAmt": 0, "bankAccount": "", "wcHomeClass": "",
        "benefit": [{"planId": "LTD1", "premiumAmt": num("37.50"), "premiumCost": num("37.50"), "empContrib": num("9.38"), "empDeduct": 0,
                     "coveragePeriod": "202412", "adjRef": "ARR-1"}],
        "employerContributions": [{"code": "LTD1", "description": "LTD employer share", "amount": num("28.12")}],
        "toArrears": [{"dedCode": "LTD", "dedDescription": "Long-term disability", "arrearsAmt": "9.38", "coveragePeriod": "202412",
                       "planId": "LTD1", "unionId": "", "loanNo": ""}],
        "retirement": _retirement(None),
    })


def _reversal(original: dict, voucher: str, batch: str, pay_date: str) -> dict:
    """The reversal of ``original`` in a V batch: voucher type stays R (D-033), amounts negated,
    voidVoucherId names the original."""
    def negate(value):
        if isinstance(value, float):
            return -value if value else value
        if isinstance(value, dict):
            return {key: negate(item) if key not in ("comTaxRate", "unitRate") else item for key, item in value.items()}
        if isinstance(value, list):
            return [negate(item) for item in value]
        return value

    reversed_lines = {key: negate(original[key]) for key in ("earning", "employeeTax", "companyTax", "deduction", "workerComp")}
    amounts = {key: negate(original[key]) for key in ("earnAmount", "totalEarnings", "fitTaxableAmount", "netPay", "checkAmt")}
    for line in reversed_lines["earning"]:
        line["hoursUnits"], line["hoursWorked"] = -line["hoursUnits"], -line["hoursWorked"]
    return {**original, **reversed_lines, **amounts, "voucherId": voucher, "batchId": batch, "payDate": pay_date, "dateProcessed": pay_date,
            "voidVoucherId": original["voucherId"], "voidDate": pay_date, "status": "PRNT", "retirement": dict(original["retirement"])}


def _adjustment(b: Builder, voucher: str, batch: str) -> dict:
    """P00002 type J adjustment: a MEMO other earning offset by a deduction, net 0 (D-023)."""
    memo = d("25.00")
    return _voucher(b, {
        "voucherId": voucher, "batchId": batch, "employeeId": "P00002", "type": "J", "checkNumber": "", "payDate": "2025-01-31", "payPeriod": "2",
        "payPeriodStart": "2025-01-05", "payPeriodEnd": "2025-01-18", "dateProcessed": "2025-01-30", "earnAmount": 0, "totalEarnings": num(memo),
        "fitTaxableAmount": 0, "netPay": 0, "checkAmt": 0, "payStubType": "P", "bankAccount": "",
        "otherEarningsDetail": [{"otherEarnCode": "MEMO", "otherEarnsDesc": "Memo", "otherEarnAmount": num(memo)}],
        "deduction": [_deduction("ADJ", "Memo offset", "V", memo)],
        "otherDeduction": [{"otherDeductCode": "ADJ", "otherDeductDescription": "Memo offset (one time)", "otherDeductAmount": 0,
                            "otherDeductOneTimeSwitch": "Y"}],
        "retirement": _retirement({"period": "2025-02"}),
    })


def _vacation(b: Builder, voucher: str, batch: str) -> dict:
    """P00001 type V vacation voucher (not seen live, D-033), paid to the remainder account."""
    vac = d("576.92")
    taxes = [_emp_tax(FIT, "Federal Income Tax", vac, d("57.69")),
             _emp_tax(SS_EE, "Soc Security - Employee", vac, pct(vac, "0.062")),
             _emp_tax(MED_EE, "Medicare - Employee", vac, pct(vac, "0.0145"))]
    net = vac - sum(Decimal(str(t["empTaxAmount"])) for t in taxes)
    return _voucher(b, {
        "voucherId": voucher, "batchId": batch, "employeeId": "P00001", "type": "V", "status": "", "checkNumber": "900109",
        "payDate": "2025-02-14", "payPeriod": "4", "payPeriodStart": "2025-02-02", "payPeriodEnd": "2025-02-15", "dateProcessed": "",
        "earnAmount": num(vac), "totalEarnings": num(vac), "fitTaxableAmount": num(vac), "netPay": num(net),
        "earning": [{"payCode": "VAC", "payClass": "E", "payClassDescription": "Earnings", "chargeDate": "2025-02-14", "hoursUnits": 16,
                     "hoursWorked": 0, "unitRate": num("36.0577"), "payAmount": num(vac), "department": "FIN", "location": "SLC"}],
        "employeeTax": taxes,
        "companyTax": [_com_tax(SS_ER, "Soc Security - Employer", vac, "0.062", "FICA"),
                       _com_tax(MED_ER, "Medicare - Employer", vac, "0.0145", "MEDI")],
        "directDeposit": [{"transitNum": routing("210003"), "accountNum": "****1234", "status": "D*C", "amount": num(net)}],
        "retirement": _retirement({"period": "2025-04", "baseEarnings": str(vac)}),
    })
