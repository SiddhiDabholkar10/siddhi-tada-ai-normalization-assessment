"""PrismHR deposits, deduction setups and benefit enrollments for the three employees of
prismhr.py.

Edge cases (direct_deposit, deduction_setup and benefit_enrollment tables, D-077):
- Deposits (getEmployee directDeposit, shared with the employee response): methods F, FS, P,
  PN and B; account types C, S and IP; statuses P, D and I; an account masked with no visible
  digit and one showing its last 4 (D-024); an item voucherTypeOverride next to the block's
  voucherType; P00003 has no deposit block.
- Setups: percent and amount setups, flat and percent employer match, a code repeated in one
  response (unstable_id), a loan joined by loanOrGarnishId and a loan with its own setup, loan
  dates (documented YYYY-DD-MM, D-083) valid one way only, the same both ways, and valid both
  ways with different dates (ambiguous), retirement loans for the client,
  arrears matching a setup and arrears matching none, scheduled deductions with the unmapped
  status O, PrismHR 404 "no records" bodies (D-021).
- Garnishments: details for P00001 (spec only: the demo refuses the route, D-081) with an
  unmapped category (SP) and percent basis; details refused (403) with checkForGarnishments
  enrolled for P00002 (presence_only setup, D-048); not enrolled for P00003.
- Benefits: every status letter, an unmapped insClass (O), two plan detail rows, the live-only
  coverageBasis, dependents and beneficiaries, a waived plan, premiums for two plans.
"""
from .common import FETCH_DATE, Builder, num, routing
from .prismhr_company import CLIENT, OK

R = {
    "employee": "/employee/v1/getEmployee",
    "deductions": "/deductions/v1/getDeductions",
    "scheduled": "/employee/v1/getScheduledDeductions",
    "loans": "/deductions/v1/getEmployeeLoans",
    "arrears": "/deductions/v1/getDeductionArrears",
    "garnishments": "/deductions/v1/getGarnishmentDetails",
    "garnishment_check": "/employee/v1/checkForGarnishments",
    "retirement_loans": "/benefits/v1/getRetirementLoans",
    "plans": "/benefits/v1/getBenefitPlans",
    "premium": "/benefits/v1/getEmployeePremium",
}
EMPLOYEES = ("P00001", "P00002", "P00003")
NO_RECORDS = {"errorCode": "DE-0040", "errorMessage": "No deduction arrears found for this employee."}
REFUSED = {"errorCode": "403", "errorMessage": "User is not authorized for the method getGarnishmentDetails."}


def deposit_block(b: Builder, employee: str) -> dict | None:
    """getEmployee employee[].directDeposit for ``employee`` (None: the block is not sent)."""
    def item(values: dict) -> dict:
        return b.shaped(R["employee"], "employee[].directDeposit.achVoucher[]", {"limit": 0, "voucherTypeOverride": "", **values})

    def block(voucher_type: str, items: list[dict]) -> dict:
        return b.shaped(R["employee"], "employee[].directDeposit", {
            "achStatus": "A", "voucherType": voucher_type, "suppressAccountPrint": False, "directDepositChecksum": f"dd-{employee}", "achVoucher": items})

    if employee == "P00001":
        return block("RVS", [
            item({"transitNum": routing("210001"), "accountNum": "****", "accountType": "S", "method": "F", "amount": 200, "limit": 200,
                  "status": "D", "bankName": "Canyon Savings", "voucherTypeOverride": "R"}),
            item({"transitNum": routing("210002"), "accountNum": "****6789", "accountType": "C", "method": "PN", "amount": 25,
                  "status": "D", "bankName": "Canyon Credit Union"}),
            item({"transitNum": routing("210003"), "accountNum": "****1234", "accountType": "C", "method": "B", "amount": 0,
                  "status": "D", "bankName": "Canyon Credit Union", "voucherTypeOverride": "RV"}),
            item({"transitNum": routing("210004"), "accountNum": "****5150", "accountType": "IP", "method": "P", "amount": 10,
                  "status": "P", "bankName": "Instant Pay Card"}),
        ])
    if employee == "P00002":
        return block("R", [
            item({"transitNum": routing("210005"), "accountNum": "****0042", "accountType": "C", "method": "FS", "amount": 150,
                  "status": "I", "bankName": "Wasatch Bank"}),
            item({"transitNum": routing("210006"), "accountNum": "****0043", "accountType": "S", "method": "B", "amount": 0,
                  "status": "P", "bankName": "Wasatch Bank"}),
        ])
    return None


def add(b: Builder) -> None:
    b.part("setups")
    _deductions(b)
    _scheduled(b)
    _loans(b)
    _arrears(b)
    _garnishments(b)
    _benefits(b)


def _params(employee: str) -> dict:
    return {"clientId": CLIENT, "employeeId": employee}


def _deductions(b: Builder) -> None:
    def item(values: dict) -> dict:
        return b.shaped(R["deductions"], "employeeDeductions.deduction[]", {
            "usePercent": False, "loanOrGarnishId": "", "benefitPlanId": "", "lastDedPerAdj": 0, "limit": 0, "maximum": 0, "basis": "",
            "trackArrears": False, "stopDate": "", "glOverrideAcct": "", "mandatory": False, "matchMethod": "", "matchAmount": 0,
            "matchDescription": "", "cutbackPayeeCode": "", "rateTableId": "", "rateTier": "", "achOption": "", **values})

    rows = {
        "P00001": [
            item({"deductionCode": "401K", "description": "401(k)", "deductionType": "K", "deductionMethod": "K", "usePercent": True, "amount": 6,
                  "period": "12", "maximum": 23500, "basis": "A", "startDate": "2016-03-01", "matchMethod": "P", "matchAmount": 50,
                  "matchDescription": "50% of the first 6%", "detailsChecksum": "k1"}),
            item({"deductionCode": "MED", "description": "Medical", "deductionType": "C", "deductionMethod": "F", "amount": num("85.40"),
                  "period": "12", "benefitPlanId": "MED1", "startDate": "2024-01-01", "matchMethod": "F", "matchAmount": num("334.60"),
                  "matchDescription": "Employer medical share", "detailsChecksum": "k2"}),
            item({"deductionCode": "DEN", "description": "Dental", "deductionType": "C", "deductionMethod": "F", "amount": 12, "period": "12",
                  "benefitPlanId": "DEN1", "startDate": "2024-01-01", "detailsChecksum": "k3"}),
            item({"deductionCode": "LTD", "description": "Long-term disability", "deductionType": "P", "deductionMethod": "F", "amount": num("9.38"),
                  "period": "1", "benefitPlanId": "LTD1", "trackArrears": True, "startDate": "2024-01-01", "detailsChecksum": "k4"}),
            item({"deductionCode": "LOAN", "description": "Payroll advance", "deductionType": "L", "deductionMethod": "F", "amount": 50, "period": "12",
                  "loanOrGarnishId": "LN-1", "limit": 50, "startDate": "2024-11-01", "stopDate": "2025-10-31", "lastDedPerAdj": 1, "detailsChecksum": "k5"}),
            item({"deductionCode": "GARN", "description": "Child support", "deductionType": "G", "deductionMethod": "G", "amount": 0, "period": "12",
                  "startDate": "2024-06-01", "mandatory": True, "cutbackPayeeCode": "UT-ORS", "detailsChecksum": "k6"}),
        ],
        "P00002": [
            item({"deductionCode": "CHAR", "description": "Charity", "deductionType": "V", "deductionMethod": "PE", "amount": 10, "period": "1",
                  "startDate": "2020-02-03", "stopDate": "2024-12-31", "rateTableId": "RT1", "rateTier": "A", "achOption": "N", "detailsChecksum": "k7"}),
            item({"deductionCode": "CHAR", "description": "Charity", "deductionType": "V", "deductionMethod": "PE", "amount": 10, "period": "1",
                  "startDate": "2025-01-01", "glOverrideAcct": "6100", "detailsChecksum": "k8"}),
            item({"deductionCode": "IRS", "description": "IRS Levy", "deductionType": "VG", "deductionMethod": "G", "amount": 150, "period": "12",
                  "maximum": 5000, "basis": "L", "startDate": "2024-09-01", "mandatory": True, "detailsChecksum": "k9"}),
        ],
        "P00003": [],
    }
    for employee in EMPLOYEES:
        b.add(R["deductions"], _params(employee), {**OK, "employeeDeductions": {"deduction": rows[employee]}})


def _scheduled(b: Builder) -> None:
    def item(values: dict) -> dict:
        return b.shaped(R["scheduled"], "scheduledDeduction[]", {"cutbackPayeeCode": "", **values})

    rows = {
        "P00001": [item({"deductionCode": "ADJ", "checkStubDescription": "Uniform", "status": "O", "amount": 45, "startDate": "2025-01-24", "stopDate": "2025-01-24"})],
        "P00002": [item({"deductionCode": "CHAR", "checkStubDescription": "Food drive", "status": "A", "amount": 5, "startDate": "2025-01-01",
                         "stopDate": "2025-03-31", "cutbackPayeeCode": "UWAY"})],
        "P00003": [],
    }
    for employee in EMPLOYEES:
        b.add(R["scheduled"], _params(employee), {**OK, "sessionId": "", "clientId": CLIENT, "employeeId": employee, "checksum": f"s-{employee}",
                                                   "scheduledDeduction": rows[employee]})


def _loans(b: Builder) -> None:
    def loan(values: dict) -> dict:
        return b.shaped(R["loans"], "employeeLoanDetail[]", {"paymentFreq": "E", "glOverrideAccount": "", **values})

    loans = [
        # Joins the getDeductions LOAN setup through loanOrGarnishId. startDate 2024-11-01 is valid both
        # ways with different dates (ambiguous, D-083); loanDate and stopDate are valid one way only.
        loan({"loanId": "LN-1", "checksum": "l1", "deductionCode": "LOAN", "loanAmount": 600, "paymentAmount": 50, "paybackAmount": 600,
              "paidAmount": 150, "loanDate": "2024-10-15", "startDate": "2024-11-01", "stopDate": "2025-10-31", "loanReason": "Moving costs",
              "paymentHistory": [b.shaped(R["loans"], "employeeLoanDetail[].paymentHistory[]", {"paymentDate": date, "paymentVoucherId": voucher, "paymentAmount": 50})
                                 for date, voucher in (("2024-11-08", "000091"), ("2024-11-22", "000095"), ("2024-12-06", "000098"))]}),
        # No setup names it: its own setup. loanDate 2024-31-01 is valid only as YYYY-DD-MM (2024-01-31);
        # stopDate 2025-12-12 reads the same both ways (D-083).
        loan({"loanId": "LN-2", "checksum": "l2", "deductionCode": "LOAN", "loanAmount": 300, "paymentAmount": 25, "paybackAmount": 300,
              "paidAmount": 0, "loanDate": "2024-31-01", "startDate": "2025-01-24", "stopDate": "2025-12-12", "loanReason": "",
              "paymentHistory": []}),
    ]
    for employee, rows in (("P00001", loans), ("P00002", []), ("P00003", [])):
        b.add(R["loans"], _params(employee), {**OK, "sessionId": "", "clientId": CLIENT, "employeeId": employee, "employeeLoanDetail": rows})
    retirement = [
        b.shaped(R["retirement_loans"], "retirementLoan[]", {
            "loanId": "RL-7", "employeeId": "P00001", "loanAmount": 5000, "loanDate": "2023-04-03", "interestRate": "8.5", "loanReason": "Home repair",
            "paymentAmount": num("104.17"), "paybackAmount": num("5625.00"), "amtPaidBackToDate": num("1979.23"), "planId401k": "401K1",
            "tpaLoanId": "TPA-5521", "deductionStarts": "2023-04-14", "checksum": "r1",
            "paidbackAdjust": [{"adjustedByWhom": "admin", "adjustedAmount": num("104.17"), "adjustedAt": "2024-02-01T10:15:00"}]}),
        b.shaped(R["retirement_loans"], "retirementLoan[]", {
            "loanId": "RL-9", "employeeId": "P00001", "loanAmount": 1200, "loanDate": "2025-01-06", "paymentAmount": 50, "paybackAmount": 1300,
            "amtPaidBackToDate": 0, "planId401k": "401K1", "overridePaymentAmt": 75, "overridePayFrom": "2025-03-01",
            "overridePayTo": "2025-06-30", "deductionStarts": "2025-01-24", "checksum": "r2", "paidbackAdjust": []}),
    ]
    b.add(R["retirement_loans"], {"clientId": CLIENT}, {**OK, "retirementLoan": retirement})


def _arrears(b: Builder) -> None:
    def entry(values: dict) -> dict:
        return b.shaped(R["arrears"], "deductionArrears[]", {"unionId": "", **values})

    rows = [
        # Matches the LTD setup.
        entry({"arrearsDate": "2024-12-20", "dedCode": "LTD", "dedDescription": "Long-term disability", "amount": "9.38", "transaction": "TO",
               "benefitPlan": "LTD1", "planDescription": "Long-term disability", "coveragePeriod": "202412", "batchNumber": "20241220-01",
               "voucherNumber": "000099", "checksum": "a1"}),
        # Matches no setup: Phase 5 keeps it on the employee.
        entry({"arrearsDate": "2024-12-20", "dedCode": "VIS", "dedDescription": "Vision", "amount": "4.10", "transaction": "TO",
               "benefitPlan": "VIS1", "planDescription": "Vision", "coveragePeriod": "202412", "batchNumber": "20241220-01",
               "voucherNumber": "000099", "checksum": "a2"}),
    ]
    b.add(R["arrears"], _params("P00001"), {**OK, "deductionArrears": rows})
    for employee in ("P00002", "P00003"):
        b.add(R["arrears"], _params(employee), NO_RECORDS, status=404)


def _garnishments(b: Builder) -> None:
    def detail(values: dict) -> dict:
        return b.shaped(R["garnishments"], "garnishmentDetails[]", values)

    details = [
        detail({"deductionCode": "GARN", "category": "C", "docketNumber": "UT-CS-2024-0912", "receiptDate": "2024-05-20", "payee": "UT-ORS",
                "issuingAuthority": "Utah Office of Recovery Services", "stateId": "CS-55120", "startDate": "2024-06-01", "stopDate": "",
                "totalGarnishmentAmount": "100.00", "flatAmount": "100.00", "withholdAmt": "", "percentNet": "", "percentOf": "",
                "garnishmentFee": "2.00", "exemptAmt": "", "payPeriodLimit": "250.00", "maxPercent": "50", "annotation1": "Case worker 14",
                "annotation2": "", "monthlyLimit": "500.00", "headOfHousehold": "N"}),
        # Spousal support (SP, unmapped) on a code with no getDeductions setup: its own setup.
        detail({"deductionCode": "SPOUSE", "category": "SP", "docketNumber": "UT-SS-2025-0007", "receiptDate": "2025-01-02", "payee": "COURT3",
                "issuingAuthority": "Third District Court", "stateId": "", "startDate": "2025-01-10", "stopDate": "2026-01-09",
                "totalGarnishmentAmount": "", "percentNet": "15", "percentOf": "S", "garnishmentFee": "", "exemptAmt": "",
                "payPeriodLimit": "", "maxPercent": "", "annotation1": "", "annotation2": ""}),
    ]
    b.add(R["garnishments"], _params("P00001"), {**OK, "garnishmentDetails": details})
    for employee in ("P00002", "P00003"):
        b.add(R["garnishments"], _params(employee), REFUSED, status=403)
    for employee, enrolled, active in (("P00001", True, True), ("P00002", True, True), ("P00003", False, False)):
        b.add(R["garnishment_check"], _params(employee), {**OK, "enrolled": enrolled, "active": active})


def _benefits(b: Builder) -> None:
    def plan(values: dict) -> dict:
        return b.shaped(R["plans"], "benefitPlan[]", {"cobraStart": "", "overrideCoverageEnd": "", "rateGuaranty": [], "groupTermLife": [], **values})

    def detail(values: dict) -> dict:
        return b.shaped(R["plans"], "benefitPlan[].planDetail[]", {"dependent": [], "beneficiary": [], **values})

    plans = {
        "P00001": [
            plan({"planId": "MED1", "description": "Medical PPO", "status": "A", "insClass": "M", "coverageStart": "2024-01-01", "coverageEnd": "",
                  "deductionStart": "2024-01-01", "deductionEnd": "", "section125": True, "carrierPlanId": "PPO-500", "networkId": "NW1",
                  "carrierEmployeeId": "CAR-88120", "doctorId": "DR-4410", "seenByDoctor": True, "providerId": "PRV-1",
                  "rateGuaranty": [{"rateGuarantyStart": "2024-01-01", "rateGuarantyEnd": "2025-12-31"}],
                  "planDetail": [
                      detail({"effectiveDate": "2024-01-01", "planType": "EE", "coverage": "0", "employeePremium": "410.00", "employeeContrib": "75.40",
                              "eePremiumContrib": "75.40", "peoPremium": "0.00", "dependentPremium": "0.00", "cobraFee": "8.20"}),
                      detail({"effectiveDate": "2025-01-01", "planType": "ES", "coverage": "0", "employeePremium": "420.00", "employeeContrib": "85.40",
                              "eePremiumContrib": "85.40", "peoPremium": "0.00", "dependentPremium": "180.00", "cobraFee": "8.40",
                              "dependent": [{"dependentId": "D1", "coverageStart": "2025-01-01", "coverageEnd": "", "doctorId": "DR-4411", "seenByDoctor": False}]}),
                  ]}),
            plan({"planId": "DEN1", "description": "Dental", "status": "A", "insClass": "N", "coverageStart": "2024-01-01", "coverageEnd": "",
                  "deductionStart": "2024-01-01", "deductionEnd": "", "section125": True,
                  "planDetail": [detail({"effectiveDate": "2024-01-01", "planType": "E1", "coverage": "0", "employeePremium": "38.00",
                                         "employeeContrib": "12.00", "eePremiumContrib": "12.00", "peoPremium": "0.00", "dependentPremium": "0.00"})]}),
            plan({"planId": "LTD1", "description": "Long-term disability", "status": "A", "insClass": "D", "coverageStart": "2024-01-01", "coverageEnd": "",
                  "deductionStart": "2024-01-01", "deductionEnd": "", "section125": False,
                  "planDetail": [detail({"effectiveDate": "2024-01-01", "planType": "EE", "coverage": "4500.00", "coverageBasis": "75000.00",
                                         "employeePremium": "37.50", "employeeContrib": "9.38", "eePremiumContrib": "9.38", "peoPremium": "28.12",
                                         "dependentPremium": "0.00",
                                         "beneficiary": [{"benefId": "D1", "benefType": "P", "benefPercent": "100", "benefPrecedence": "1"}]})]}),
            plan({"planId": "VIS1", "description": "Vision", "status": "W", "insClass": "V", "coverageStart": "2024-01-01", "coverageEnd": "2024-01-01",
                  "deductionStart": "", "deductionEnd": "", "section125": True, "waiveReason": "Covered by spouse", "waiveReasonCode": "SP",
                  "planDetail": []}),
            plan({"planId": "LIFE1", "description": "Basic life", "status": "C", "insClass": "L", "coverageStart": "2022-01-01", "coverageEnd": "2023-12-31",
                  "deductionStart": "2022-01-01", "deductionEnd": "2023-12-31", "cobraStart": "2024-01-01", "cobraTermFlag": "N",
                  "groupTermLife": [{"gtlTaxYear": "2023", "gtlAccruedYTD": "64.80"}], "gtlVoucherNumber": ["000077"],
                  "planDetail": [detail({"effectiveDate": "2022-01-01", "planType": "EE", "coverage": "50000.00", "employeePremium": "5.40",
                                         "employeeContrib": "0.00", "eePremiumContrib": "0.00", "peoPremium": "5.40", "dependentPremium": "0.00"})]}),
            plan({"planId": "EAP1", "description": "Employee assistance", "status": "E", "insClass": "O", "coverageStart": "2024-01-01",
                  "coverageEnd": "", "deductionStart": "", "deductionEnd": "", "planDetail": []}),
        ],
        "P00002": [
            plan({"planId": "MED1", "description": "Medical PPO", "status": "E", "insClass": "M", "coverageStart": "", "coverageEnd": "",
                  "deductionStart": "", "deductionEnd": "", "section125": True, "planDetail": []}),
            plan({"planId": "DEN1", "description": "Dental", "status": "T", "insClass": "N", "coverageStart": "2020-03-01", "coverageEnd": "2024-12-31",
                  "deductionStart": "2020-03-01", "deductionEnd": "2024-12-31", "section125": True,
                  "planDetail": [detail({"effectiveDate": "2020-03-01", "planType": "EE", "coverage": "0", "employeePremium": "38.00",
                                         "employeeContrib": "12.00", "eePremiumContrib": "12.00", "peoPremium": "0.00", "dependentPremium": "0.00"})]}),
        ],
        "P00003": [],
    }
    for employee in EMPLOYEES:
        b.add(R["plans"], _params(employee), {**OK, "benefitPlan": plans[employee]})
    for plan_id, rates in (("MED1", ("420.00", "420.00", "0.00", "420.00", "420.00", "0.00", "85.40", "85.40", "0.00")),
                           ("LTD1", ("37.50", "37.50", "0.00", "37.50", "37.50", "0.00", "9.38", "9.38", "0.00"))):
        b.add(R["premium"], {**_params("P00001"), "effectiveDate": FETCH_DATE.isoformat(), "planId": plan_id}, {**OK,
              "billingRates": {"totalAmount": num(rates[0]), "employeeAmount": num(rates[1]), "dependentsAmount": num(rates[2])},
              "premiumRates": {"totalAmount": num(rates[3]), "employeeAmount": num(rates[4]), "dependentsAmount": num(rates[5])},
              "contributionRates": {"contribAmount": num(rates[6]), "employeePremiumContribAmount": num(rates[7]), "hawaiiMax15Amount": num(rates[8])}})
