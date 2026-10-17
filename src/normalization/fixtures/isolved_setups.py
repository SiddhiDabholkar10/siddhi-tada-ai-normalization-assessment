"""isolved deposits, deduction setups and benefit enrollments for the three employees of
isolved.py.

Edge cases (direct_deposit, deduction_setup and benefit_enrollment tables, D-077):
- Deposits: percent, amount and the active sequence 0 remainder account (D-015); an inactive
  sequence 0 account (unknown); a null sequence on an inactive account (live, COVERAGE
  section 2); an unlisted frequency label; 404 with an empty body for 70003 (no records, D-011).
- Setups (D-017, D-081): legal-level entries joined to the per-employee entries; payItemType
  null on the legal list and calcParams shorter there; an Earning entry that is not a setup; a
  negative-id catalog placeholder; an entry with no code (unlinked); Percent, Amount2 and Rate
  parameters kept raw; the live-only balance.
- Garnishments: a federal levy with linked deductions (one not in the catalog), and a type and
  status not in the label tables; 404 for 70003.
- Benefits (spec only, D-049, D-081): plan type and coverage labels with no table (unknown), an
  inactive enrollment (status unknown) with a waive reason, an HSA plan with account numbers
  (sensitive extension), dependents; an empty list and a 404.
"""
from .common import Builder, routing
from .isolved_company import CLIENT, DEDUCTION, EARNING, LEGAL

API = "/api/clients/{clientId}/legals/{legalId}"
R = {
    "deposits": f"{API}/employees/{{employeeId}}/directdeposits",
    "legal_items": f"{API}/payItems",
    "employee_items": f"{API}/employees/{{employeeId}}/payItems",
    "garnishments": f"{API}/employees/{{employeeId}}/garnishments",
    "benefits": f"{API}/employees/{{employeeId}}/benefits",
}


def ts(day: str) -> str:
    return f"{day}T00:00:00"


def add(b: Builder) -> None:
    b.part("setups")
    _deposits(b)
    _pay_items(b)
    _garnishments(b)
    _benefits(b)


def _sub(b: Builder, name: str, employee: int, body, status: int = 200) -> None:
    b.add(R[name], {"clientId": CLIENT, "legalId": LEGAL, "employeeId": employee}, body, status)


def _deposits(b: Builder) -> None:
    def account(values: dict) -> dict:
        return b.shaped(R["deposits"], "[]", {"amount": None, "percent": None, "frequency": "Every Pay", "description": "", **values})

    _sub(b, "deposits", 70001, [
        account({"id": 41, "sequenceNumber": 1, "percent": 25.0, "accountType": "Savings", "status": "Active", "bankName": "Cascade Savings",
                 "routingNumber": routing("310001"), "accountNumber": "88120045", "description": "Rainy day"}),
        # Active sequence 0 ('0 = Net Pay'): the remainder account (D-015).
        account({"id": 42, "sequenceNumber": 0, "accountType": "Checking", "status": "Active", "bankName": "Cascade Bank",
                 "routingNumber": routing("310002"), "accountNumber": "4400921387"}),
        account({"id": 43, "sequenceNumber": 2, "amount": 100.0, "accountType": "Checking", "status": "Inactive", "bankName": "Old Town Bank",
                 "routingNumber": routing("310003"), "accountNumber": "7712"}),
    ])
    _sub(b, "deposits", 70002, [
        # Inactive sequence 0: allocation unknown.
        account({"id": 44, "sequenceNumber": 0, "accountType": "Checking", "status": "Inactive", "bankName": "Cascade Bank",
                 "routingNumber": routing("310004"), "accountNumber": "5500182211"}),
        # Null sequence on an inactive account (seen live on 2 accounts).
        account({"id": 45, "sequenceNumber": None, "amount": 50.0, "accountType": "Savings", "status": "Inactive", "bankName": "Cascade Savings",
                 "routingNumber": routing("310005"), "accountNumber": "5500182212"}),
        # 'Every Other Pay' is not in the frequency label table: unknown.
        account({"id": 46, "sequenceNumber": 1, "amount": 200.0, "accountType": "Checking", "status": "Active", "frequency": "Every Other Pay",
                 "bankName": "Cascade Bank", "routingNumber": routing("310006"), "accountNumber": "5500182213"}),
    ])
    _sub(b, "deposits", 70003, None, status=404)  # no records (D-011)


def _pay_items(b: Builder) -> None:
    def entry(values: dict) -> dict:
        base = {"auditId": 900000 + values["id"] if values["id"] > 0 else 0, "employeeNumber": "", "firstName": "", "lastName": "", "payItemCode": None,
                "payItemId": None, "payItemType": None, "referenceNumber": "", "scheduleOverride": "", "startDate": None, "stopDate": None,
                "calcParams": []}
        return {**base, **values}

    numbers = {70001: "E-1001", 70002: "E-1002"}
    k401 = {"id": 9501, "employeeId": 70001, "employeeNumber": numbers[70001], "payItemCode": "401K", "payItemId": DEDUCTION["401K"],
            "payItemName": "401(k)", "startDate": ts("2019-05-01"), "scheduleOverride": "Every Pay", "referenceNumber": "PLAN-401"}
    med = {"id": 9502, "employeeId": 70001, "employeeNumber": numbers[70001], "payItemCode": "MEDPT", "payItemId": DEDUCTION["MEDPT"],
           "payItemName": "Medical", "startDate": ts("2025-01-01"), "stopDate": ts("2025-12-31")}
    rate = {"id": 9505, "employeeId": 70001, "employeeNumber": numbers[70001], "payItemCode": "REG", "payItemId": EARNING["REG"],
            "payItemName": "Regular", "startDate": ts("2019-04-01")}
    # No code: stays unlinked to the catalog (2 of 7 live entries).
    parking = {"id": 9503, "employeeId": 70002, "employeeNumber": numbers[70002], "payItemName": "Garage parking", "startDate": ts("2023-03-01")}
    loan = {"id": 9504, "employeeId": 70002, "employeeNumber": numbers[70002], "payItemCode": "LOAN", "payItemId": DEDUCTION["LOAN"],
            "payItemName": "401K Loan", "startDate": ts("2024-06-07"), "balance": 1200.0}
    # The legal list: payItemType null and calcParams missing or shorter (D-081).
    legal_list = [entry({**k401}), entry({**med, "calcParams": [{"paramType": "Amount", "paramValue": 60.0}]}), entry({**rate}),
                  entry({**parking, "calcParams": [{"paramType": "Amount", "paramValue": 15.0}]}), entry({**loan})]
    b.add(R["legal_items"], {"clientId": CLIENT, "legalId": LEGAL, "page": 0},
          {"results": legal_list, "totalItems": len(legal_list), "totalPages": 1, "nextPageUrl": None, "previousPageUrl": None})
    _sub(b, "employee_items", 70001, [
        entry({**k401, "payItemType": "Deduction", "calcParams": [{"paramType": "Percent", "paramValue": 6.0}]}),
        entry({**med, "payItemType": "Deduction", "calcParams": [{"paramType": "Amount", "paramValue": 60.0}]}),
        # Earning entries are not setups.
        entry({**rate, "payItemType": "Earning", "calcParams": [{"paramType": "Rate", "paramValue": 23.75}]}),
        # Negative id: a catalog placeholder, not a setup (D-066).
        entry({"id": -1, "employeeId": 70001, "payItemCode": "DENPT", "payItemId": DEDUCTION["DENPT"], "payItemName": "Dental",
               "payItemType": "Deduction"}),
    ])
    _sub(b, "employee_items", 70002, [
        entry({**parking, "payItemType": "Deduction", "calcParams": [{"paramType": "Amount", "paramValue": 15.0}, {"paramType": "Amount2", "paramValue": 5.0}]}),
        entry({**loan, "payItemType": "Deduction", "calcParams": [{"paramType": "Amount", "paramValue": 50.0}]}),
    ])
    _sub(b, "employee_items", 70003, [])


def _garnishments(b: Builder) -> None:
    def order(values: dict) -> dict:
        return b.shaped(R["garnishments"], "[]", {"additionalExemptionAmount": 0.0, "dependentExemption": 0.0, "blockSystemGarnishmentRule": False,
                                                  "resetNotTakenBalanceToZero": False, "overrideFipsCode": "", "stopDate": None, **values})

    _sub(b, "garnishments", 70001, [order({
        "id": 77, "garnishmentType": {"id": "LF", "typeDescription": "Federal Tax Levy"}, "garnishmentDescription": "IRS levy",
        "caseNumber": "IRS-2024-5521", "garnishmentPayee": {"id": 3, "payeeName": "Internal Revenue Service acct 4410"},
        "thirdPartyPayee": {"id": 4, "nameDashPayeeDescription": "IRS - Levy processing"}, "garnishmentSequence": 1,
        "state": {"id": "UT", "stateName": "Utah"}, "amount": 75.0, "percent": 0.0, "percentageOf": "DisposableIncome",
        "maximumAmount": 3000.0, "maximumPercent": 25.0, "feeAmount": 0.0, "arrearsBalance": 0.0, "remainingBalance": 2925.0,
        "applyArrears": False, "isMedicalSupportRequired": False, "limit": 0.0, "ytdLimit": 0.0, "newBalance": 2925.0,
        "updatedArrearsBalance": 0.0, "overrideTakeHomeFactor": 0.0,
        # Linked deductions keep their provider ids; 990 is not in the catalog (0 of 2 join live).
        "selectedDeductions": [{"id": DEDUCTION["401K"], "payItemTitle": "401(k)"}, {"id": 990, "payItemTitle": "Old union dues"}],
        "startDate": ts("2024-09-01"), "status": "Active"})])
    _sub(b, "garnishments", 70002, [order({
        "id": 78, "garnishmentType": {"id": "CS", "typeDescription": "Child Support"}, "garnishmentDescription": "Child support order",
        "caseNumber": "OR-CS-88-1020", "garnishmentPayee": {"id": 5, "payeeName": "Oregon DCS"}, "garnishmentSequence": 2,
        "state": {"id": "OR", "stateName": "Oregon"}, "amount": 0.0, "percent": 20.0, "percentageOf": "NetPay", "maximumAmount": 0.0,
        "maximumPercent": 50.0, "feeAmount": 1.5, "arrearsBalance": 240.0, "remainingBalance": 0.0, "applyArrears": True,
        "isMedicalSupportRequired": True, "selectedDeductions": [], "startDate": ts("2023-02-01"), "stopDate": ts("2030-02-01"),
        # Not in the status label table: unknown.
        "status": "Suspended"})])
    _sub(b, "garnishments", 70003, None, status=404)


def _benefits(b: Builder) -> None:
    def enrollment(values: dict, detail: dict) -> dict:
        return {**b.shaped(R["benefits"], "[]", {
            "benefitType": {"allowBeneficiary": False, "allowPlanUpdates": True, "allowPrimaryCarePhysician": False, "allowProofOfInsurability": False,
                            "autoEnrollDefault": False, "isAcaGroupHealthPlanDefault": False, "requiresEligibleWages": False,
                            "calculation": {"id": 2, "description": "Flat amount"}, "category": {"id": 1, "description": "Health"}},
            "deductionSchedule": "Every Pay", "displayOrder": 1, "employeeBenefitStopDate": None, "planStopDate": None}), **values,
            "employeeBenefitPlanDetail": detail}

    _sub(b, "benefits", 70001, [
        enrollment({"id": 301, "employeeBenefitId": 8301, "planName": "Medical PPO", "planType": "Medical", "planTypeId": 1, "isActive": True,
                    "coverageName": "Employee + Spouse", "employeeBenefitStartDate": ts("2025-01-01"), "effectiveDate": ts("2025-01-01"),
                    "planStartDate": ts("2025-01-01"), "preTax": "Yes", "annualCostContribution": "1560.00", "employeeAnnualAmount": "1560.00",
                    "deductionAmount": ["60.00"], "calcParams": [{"calcParamId": 11, "hasDefault": True, "payItem": "MEDPT", "value": 60.0}]},
                   {"planId": "MED-PPO", "groupId": "G-1001", "waiveReason": "", "coverageLevel": ["Employee", "Spouse"], "coveredEmployeeCode": "ES",
                    "deduction": "60.00", "deductionFrequency": "Every Pay", "employeePCP": "Dr. Lane, 1442", "participantId": "PPO-77120",
                    "startDate": ts("2025-01-01"), "stopDate": None, "calculatedStatus": "Approved", "underwritingStatus": "",
                    "provider": {"id": 9, "code": "CASC", "name": "Cascade Health", "partnerId": 0, "partnerName": ""},
                    "dependents": [{"dependentLabel": "Spouse", "dependentData": "Jamie, 1989-07-02", "enrollmentBeginDate": ts("2025-01-01"),
                                    "enrollmentEndDate": None}],
                    "beneficiaries": []}),
        enrollment({"id": 302, "employeeBenefitId": 8302, "planName": "HSA", "planType": "Health Savings Account", "planTypeId": 7, "isActive": True,
                    "coverageName": "Employee Only", "employeeBenefitStartDate": ts("2025-01-01"), "effectiveDate": ts("2025-01-01"),
                    "preTax": "Yes", "deductionAmount": ["40.00"]},
                   {"planId": "HSA-1", "accountNumber": "HSA00442211", "maskedAccountNumber": "*******2211", "routingNumber": routing("310007"),
                    "accountType": "Checking", "participantId": "HSA-5520", "annualTargetAmount": "1040.00", "startDate": ts("2025-01-01")}),
        enrollment({"id": 303, "employeeBenefitId": 8303, "planName": "Vision", "planType": "Vision", "planTypeId": 3, "isActive": False,
                    "coverageName": "Waived", "employeeBenefitStartDate": ts("2025-01-01"), "employeeBenefitStopDate": ts("2025-01-01"),
                    "effectiveDate": ts("2025-01-01"), "deductionAmount": []},
                   {"planId": "VIS-1", "waiveReason": "Covered elsewhere", "coverageLevel": []}),
    ])
    _sub(b, "benefits", 70002, [])
    _sub(b, "benefits", 70003, None, status=404)
