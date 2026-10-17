"""PrismHR employee bundle: one client, three employees.

Edge cases (employee tables, D-077): masked SSN with and without visible digits, declined
answers (D), blank vs missing values, undocumented live codes (filing status M, rate period A),
a client-defined termination type, sentinel effective dates in the pay rate history (D-025), a
terminated contractor, a rehired employee, a pending dependent, emergency contacts of every
contact type, a pay group without a payroll schedule, withholding overrides A, B, F and P, and
the live history wrapper key ``historyRecord`` (D-062).

The bundle also holds the company, setup and payroll inputs (prismhr_company.py,
prismhr_setups.py, prismhr_payroll.py, D-082). Shared responses are extended in place:
getClientCodes carries the pay code, deduction code and location lists, and getEmployee the
direct deposit blocks.
"""
from . import prismhr_company, prismhr_payroll, prismhr_setups
from .common import Builder, routing
from .prismhr_company import CLIENT, OK

R = {
    "list": "/employee/v1/getEmployeeList",
    "employee": "/employee/v1/getEmployee",
    "address": "/employee/v1/getAddressInfo",
    "history": "/employee/v1/getHistory",
    "rates": "/employee/v1/getPayRateHistory",
    "status": "/employee/v1/getStatusHistoryForAdjustment",
    "position": "/employee/v1/getPositionRate",
    "pto": "/benefits/v1/getPaidTimeOff",
    "dependents": "/benefits/v1/getDependents",
    "override": "/payroll/v1/getEmployeeOverrideRates",
    "codes": "/clientMaster/v1/getClientCodes",
    "schedule": "/clientMaster/v1/getPayrollSchedule",
}


def build(seed: int) -> dict:
    b = Builder("prismhr", "900001", seed)
    ids = ["P00001", "P00002", "P00003"]
    b.add(R["list"], {"clientId": CLIENT}, {**OK, "employeeList": {"employeeId": ids}})
    _client_codes(b)
    _schedule(b)
    _employee_1(b)
    _employee_2(b)
    _employee_3(b)
    prismhr_company.add(b)
    prismhr_setups.add(b)
    prismhr_payroll.add(b)
    return b.bundle()


def _item(b: Builder, route: str, path: str, values: dict) -> dict:
    return b.shaped(R[route], path, values)


def _client_codes(b: Builder) -> None:
    def rows(path, items):
        return [_item(b, "codes", f"clientCodes.{path}[]", item) for item in items]

    codes = {
        "clientId": CLIENT,
        "statusCode": rows("statusCode", [
            {"id": "A", "description": "Active", "statusClass": "A"},
            {"id": "LOA", "description": "Leave of absence", "statusClass": "L"},
            {"id": "T", "description": "Terminated", "statusClass": "T"},
        ]),
        "typeCode": rows("typeCode", [
            {"id": "FT", "description": "Full time", "abbrDescription": "FT", "typeClass": "F", "seasonal": False},
            {"id": "PTS", "description": "Part time seasonal", "abbrDescription": "PTS", "typeClass": "P", "seasonal": True},
            {"id": "IC", "description": "Independent contractor", "abbrDescription": "IC", "typeClass": "C", "seasonal": False},
        ]),
        "jobCode": rows("jobCode", [
            {"id": "ACCT", "jobTitle": "Staff Accountant", "jobClass": "PROF", "jobDescription": "Accounting"},
            {"id": "WHSE", "jobTitle": "Warehouse Associate", "jobClass": "LABR", "jobDescription": "Warehouse"},
        ]),
        "positionClass": rows("positionClass", [
            {"id": "PROF", "description": "Professional", "eeoJobClass": "PROFESS", "eeoJobGroup": "2"},
            {"id": "LABR", "description": "Laborer", "eeoJobClass": "LABOR", "eeoJobGroup": "9"},
        ]),
        "departmentCode": rows("departmentCode", [
            {"id": "FIN", "deptName": "Finance"},
            {"id": "OPS", "deptName": "Operations"},
        ]),
        "divisionCode": rows("divisionCode", [{"id": "EAST", "divisionName": "Eastern Division"}]),
        "projectCode": rows("projectCode", [{"id": "PRJ1", "description": "Warehouse expansion"}]),
        "reasonCode": rows("reasonCode", [
            {"id": "VQ", "description": "Voluntary quit", "terminationType": "V", "validActions": "T"},
            {"id": "DEC", "description": "Deceased", "terminationType": "N", "validActions": "T"},
        ]),
        "ethnicCode": rows("ethnicCode", [
            {"id": "W1", "description": "White", "reportCode": "C"},
            {"id": "HL", "description": "Hispanic or Latino", "reportCode": "H"},
            {"id": "NS", "description": "Not specified", "reportCode": "X"},
        ]),
        "citizenshipStatusCodes": rows("citizenshipStatusCodes", [
            {"code": "Z01", "description": "A citizen of the United States"},
            {"code": "Z03", "description": "A lawful permanent resident"},
        ]),
        "relationCodes": rows("relationCodes", [
            {"code": "S", "description": "Spouse"},
            {"code": "C", "description": "Child"},
            {"code": "F", "description": "Friend"},
        ]),
        "skillCodes": rows("skillCodes", [{"code": "FORK", "description": "Forklift operation"}]),
        "payGroups": rows("payGroups", [
            {"payGroupCode": "BW", "description": "Biweekly"},
            {"payGroupCode": "MO", "description": "Monthly (no schedule)"},
        ]),
        "locationCode": prismhr_company.locations(b),
        "payCode": prismhr_company.pay_codes(b),
        "deductionCode": prismhr_company.deduction_codes(b),
    }
    b.add(R["codes"], {"clientId": CLIENT}, {**OK, "clientCodes": codes})


def _schedule(b: Builder) -> None:
    schedules = [
        _item(b, "schedule", "clientPayrollSchedules[]", {"groupId": "BW", "groupDesc": "Biweekly", "payPeriod": "B", "payPeriodDesc": "Bi-Weekly"}),
    ]
    # The demo sends the singular wrapper key (D-062); the fixture follows the live shape.
    b.add(R["schedule"], {"clientId": CLIENT}, {**OK, "clientPayrollSchedule": schedules})


def _common_calls(b: Builder, emp: str, employee: dict, address: dict, history: list, rates: list, statuses: list,
                  pto: list, dependents: list, overrides: list, positions: list) -> None:
    p = {"clientId": CLIENT, "employeeId": emp}
    b.add(R["employee"], p, {**OK, "employee": [employee]})
    b.add(R["address"], p, {**OK, "addressInfo": address})
    # The demo sends the singular wrapper key (D-062); the fixture follows the live shape.
    b.add(R["history"], p, {**OK, "historyRecord": history})
    b.add(R["rates"], p, {**OK, "payRateHistory": {"clientId": CLIENT, "employeeId": emp, "payRate": rates}})
    b.add(R["status"], p, {
        **OK,
        "statusTypeHistory": statuses,
        "hireDates": _item(b, "status", "hireDates", {"lastHireDate": employee["client"]["lastHireDate"]}),
    })
    b.add(R["position"], p, {**OK, "positionRate": positions})
    b.add(R["pto"], p, {**OK, "paidTimeOff": pto})
    b.add(R["dependents"], p, {**OK, "clientId": CLIENT, "employeeId": emp, "dependent": dependents})
    b.add(R["override"], p, {**OK, "overrideRate": _item(b, "override", "overrideRate", {
        "clientId": CLIENT, "employeeId": emp, "checksum": "c1", "sessionId": "", "payCodeRate": overrides,
    })})


def _address(b: Builder, home: dict, w2: dict | None = None, alt: dict | None = None) -> dict:
    empty = {"addressLine1": "", "addressLine2": "", "city": "", "county": "", "stateAbbr": "", "zipCode": "", "zipSuffix": ""}
    return {
        "checksum": "a1",
        "homeGeoCode": "450351000",
        "homeAddress": {**empty, **home},
        "w2Address": {**empty, **(w2 or {})},
        "altAddress": {**empty, **(alt or {})},
    }


def _status(b: Builder, date: str, status: str, status_desc: str, type_code: str, type_desc: str) -> dict:
    return _item(b, "status", "statusTypeHistory[]", {
        "effectiveDate": date, "status": status, "statusDesc": status_desc, "employeeType": type_code,
        "typeDesc": type_desc, "dateUpdated": date, "checksum": "s1",
    })


def _rate(b: Builder, date: str, rate: str, period: str, method: str, hourly: str, annual: str, reason: str, **extra) -> dict:
    return _item(b, "rates", "payRateHistory.payRate[]", {
        "effectiveDate": date, "payRate": rate, "payPeriod": period, "payMethod": method, "hourlyRate": hourly,
        "annualPay": annual, "reason": reason, "standardHours": "80.00", "changePercent": extra.get("pct", "0.00"),
        "changeAmount": extra.get("amt", "0.00"), "percentMidpoint": extra.get("mid", ""),
    })


def _person(b: Builder, values: dict) -> dict:
    return _item(b, "employee", "employee[].person", values)


def _employee_1(b: Builder) -> None:
    """Active salaried employee: masked SSN, declined veteran answer, full withholding setup."""
    first, last = b.name()
    emp = "P00001"
    employee = _item(b, "employee", "employee[]", {
        "id": emp, "firstName": first, "lastName": last, "middleInitial": "J", "preferredName": "Jo",
        "person": _person(b, {
            "birthDate": "1988-04-12", "gender": "F", "ethnicCode": "W1", "maritalStatus": "M", "marriedDate": "2014-06-01",
            "smoker": "N", "handicapped": "N", "blind": "N", "veteran": "D", "vietnamVet": "", "disabledVet": "N",
            "otherProtectedVet": "N", "activeDutyBadgeVet": "N", "recentlySeparatedVet": "N", "serviceMedalVet": "N",
            "deceased": False, "deceasedDate": "", "hispanic": False, "nickname": "Jojo", "peoStartDate": "2016-03-01",
            "employerIds": ["PEO1"], "geoCode": "450351000", "highlyCompensated": False, "keyEmployee": False,
            "preferredLanguage": "EN", "driverLicenseId": "D7654321", "driverState": "UT", "driverLicenseExpireDate": "2028-04-12",
            "driverLicenseClass": "D", "legacyEmployeeId": "L-0001", "taxZipCode": "84101", "hrpCitizenshipCountry": "USA",
            "emergencyContact": [
                {"contactName": f"Sam {last}", "contactInfo": b.phone(), "contactRelationship": "Husband", "contactType": "PHONE", "contactIfDetained": ""},
                {"contactName": f"Alex {last}", "contactInfo": "alex.contact@example.org", "contactRelationship": "Brother", "contactType": "EMAIL"},
                {"contactName": "Pat Lee", "contactInfo": "12 Elm St", "contactRelationship": "", "contactType": "ADDRESS"},
            ],
        }),
        "contactInformation": _item(b, "employee", "employee[].contactInformation", {
            "addressLine1": "100 Maple Ave", "city": "Salt Lake City", "state": "UT", "zipcode": "84101",
            "homePhone": b.phone(), "mobilePhone": b.phone(), "emailAddress": "jo.personal@example.net", "schoolDistrict": "SD4",
        }),
        "client": _item(b, "employee", "employee[].client", {
            "employeeStatus": "A", "statusClass": "A", "statusDate": "2016-03-01", "employeeType": "FT", "typeClass": "F",
            "typeDate": "2016-03-01", "jobCode": "ACCT", "jobStartDate": "2016-03-01", "firstHireDate": "2016-03-01",
            "lastHireDate": "2016-03-01", "seniorityDate": "2016-03-01", "flsaExempt": True, "employee1099": False,
            "rehireOk": "Y", "termReasonCode": "", "termExplanation": "", "clientEmployeeId": "1001-17",
            "lastJobChangeDate": "2021-07-01", "homeDepartment": "FIN", "homeDivision": "EAST", "projCostCenter": "PRJ1",
            "subCostCenter": "SC9", "homeLocation": "SLC", "manager": "P00002", "unionCode": "U12",
            "workEmail": "jo.work@corp.example", "workPhone": "801-555-0120", "workPhoneExt": "12", "preferredPronoun": "she/her",
            "genderDesignation": "", "selfIdDisabilityForm": "N", "benefitEmail": "jo.benefits@example.net", "clockNum": "4411",
            "workShift": "1", "benefitGroup": "STD", "officer": False, "courtOrderMedical": False,
            "childSpouseSupport": False, "childSpouseArrears": False, "clientChecksum": "c1",
            "transferInfo": [{"transferClientId": "1000", "transferEmployeeId": "X9", "transferDate": "2016-02-29", "transferStatus": "C"}],
            "cafeteriaPlan": [{"planAmt": "50.00", "planEffectiveDate": "2024-01-01"}],
        }),
        "compensation": _item(b, "employee", "employee[].compensation", {
            "ssn": "***-**-****", "payGroup": "BW", "payPeriod": "B", "payMethod": "S", "hourlyPayRate": "75000.00",
            "hourlyPayPeriod": "Y", "hourlyPay": "36.0577", "salary": "2884.62", "annualPay": "75000.00",
            "standardHours": "80.00", "effectiveDate": "2024-01-01", "payRate2": "41.00", "payRate3": "", "payRate4": "",
            "citizenshipStatus": "Z01", "fedFilingStatus": "M", "fedWithholdAllowance": "2", "fedMultipleJobs": False,
            "fedDependents": 2000.00, "fedOtherIncome": 0, "fedDeductions": 150.50, "fedOverrideType": "A",
            "fedOverrideAmt": "25.00", "fedTaxCalc": "A", "fedW4Filed": True, "fedW4Year": "2024",
            "stateTax": [_item(b, "employee", "employee[].compensation.stateTax[]", {
                "stateCode": "UT", "filingStatus": "H", "primaryAllowance": "1", "secondaryAllowance": "0",
                "multipleJobs": False, "dependents": 0, "otherIncome": 0, "deductions": 0, "overrideType": "F",
                "overrideAmount": "40.00", "stateW4Filed": "Y", "stateW4Year": "2024",
            })],
            "localTax": [{"authId": "SLC01", "filingStatus": "S", "primaryAllowance": "0", "nonResCert": "N", "addlWithheld": "5.00"}],
            "formI9Filed": True, "formI9RenewDate": "2027-01-01", "nonResAlien": False, "alienRegExpDate": "",
            "notes": "Relocation package agreed", "perfReviewLastRating": "4", "lastChangePct": "3.00",
            "lastChangeAmt": "2184.47", "workShift": "1", "deliverCheckHome": False, "electronicPayStub": True,
            "ficaExempt": False, "compensationChecksum": "k1", "payPeriodsPerWeek": "0.5",
        }),
        "skillsAndEducation": {
            "skillChecksum": "x1", "osha10Certified": True,
            "skill": [{"skillCode": "FORK", "competencyLevel": "80", "certifyDate": "2023-05-01", "renewDate": "2026-05-01", "skillComment": "Certified on site"}],
            "school": [{"schoolName": "Wasatch State University", "degreeEarned": "BS Accounting", "gradYear": "2010", "graduated": True, "schoolYear": "", "schoolComment": ""}],
        },
        "health": _item(b, "employee", "employee[].health", {"bloodType": "O", "bloodDonor": True}),
        # Not read by the employee adapter: directDeposit gives DirectDeposit records (prismhr_setups.py);
        # scheduledDeduction is excluded (getScheduledDeductions is the source). A test shows they leave no trace.
        "directDeposit": prismhr_setups.deposit_block(b, emp),
        "hsa": {"achChecksum": "h1", "hsaDepositSettings": [_item(b, "employee", "employee[].hsa.hsaDepositSettings[]", {
            "transitNum": routing("210009"), "accountNum": "****4321", "accountType": "HE", "method": "F", "amount": 50,
            "status": "D", "bankName": "Sample HSA Bank", "voucherTypeOverride": "R"})]},
        "scheduledDeduction": [{"amount": 25, "checkStubDescription": "Uniform", "deductionCode": "ADJ", "status": "A"}],
        "enrollmentInProgress": {"enrollmentInProgress": True, "enrollmentType": "BE"},
        "benefitEnrollmentCompleted": True,
        "absenceJournalId": ["J-1001", "J-1002"],
    })
    address = _address(
        b,
        {"addressLine1": "100 Maple Ave", "addressLine2": "Unit 2", "city": "Salt Lake City", "county": "Salt Lake",
         "stateAbbr": "UT", "zipCode": "84101", "zipSuffix": "2201", "unincorporatedResidence": False},
        alt={"addressLine1": "45 Lakeshore Rd", "addressLine2": "Floor 3", "city": "Toronto", "county": "York", "stateAbbr": "ON", "zipCode": "M5V2T6",
             "internationalAddress": True, "mailAddressCountry": "CAN"},
    )
    history = [
        {"type": "Position", "effectiveDate": "2021-07-01", "newPositionCode": "ACCT"},
        {"type": "Department", "effectiveDate": "2021-07-01", "departmentChange": {"departmentCode": "FIN"}},
        {"type": "Division", "effectiveDate": "2019-01-01", "divisionChange": {"divisionCode": "EAST"}},
        {"type": "Location", "effectiveDate": "2016-03-01", "locationChange": {"locationCode": "SLC"}},
        {"type": "Leave", "effectiveDate": "2022-05-01", "leave": {"employeeStatusCode": "LOA", "employeeTypeCode": "FT", "expectedReturnDate": "2022-07-01", "reason": "Family leave"}},
        {"type": "Status", "effectiveDate": "2022-07-01", "statusChange": {"employeeStatusCode": "A", "employeeTypeCode": "FT", "reason": "Return from leave"}},
        {"type": "Benefit Group", "effectiveDate": "2016-03-01", "benefitGroupChange": {"benefitGroupCode": "STD"}},
    ]
    rates = [
        _rate(b, "2016-03-01", "65000.00", "A", "S", "31.25", "65000.00", "Hire"),
        _rate(b, "2024-01-01", "75000.00", "A", "S", "36.0577", "75000.00", "Promo", pct="15.38", amt="10000.00", mid="98.5"),
    ]
    statuses = [
        _status(b, "2016-03-01", "A", "Active", "FT", "Full time"),
        _status(b, "2022-05-01", "LOA", "Leave of absence", "FT", "Full time"),
        _status(b, "2022-07-01", "A", "Active", "FT", "Full time"),
    ]
    pto = [_item(b, "pto", "paidTimeOff[]", {
        "ptoPlanId": "VAC", "registerType": "VAC", "registerTypeDescription": "Vacation", "carryOverHours": "16.00",
        "accruedHoursYTD": "61.54", "usedHoursYTD": "24.00", "accruedThru": "2026-09-30", "yearEndDate": "2026-12-31",
        "benefitStart": "2016-03-01", "lastCarryOver": "2026-01-01", "carryOverExpires": "", "carryOverExpireFlag": False,
        "accruedFlag": True, "stopPTOAccruals": False, "journalId": ["J-1001"],
        "priorYear": [{"yearEndDate": "2025-12-31", "yearCarryOverHours": "8.00", "yearAccruedHours": "80.00", "yearUsedHours": "72.00"}],
    })]
    dependents = [
        _item(b, "dependents", "dependent[]", {
            "dependentId": "D1", "relation": "S", "relationshipCodeType": "SP", "spouse": "Y", "relationType": "D",
            "beneficiaryType": "P", "benefitPercent": "100", "status": "A", "statusDate": "2016-03-01",
            "firstName": "Sam", "middleInitial": "Q", "lastName": last, "email": "sam.dep@example.org", "gender": "M",
            "birthdate": "1987-02-02", "ssn": "***-**-5555", "ssnAppliedFor": False, "address": "100 Maple Ave",
            "addressLine2": "Unit 2", "city": "Salt Lake City", "state": "UT", "zip": "84101", "zipSuffix": "2201",
            "country": "USA", "homePhone": b.phone(), "workPhone": b.phone(), "tobaccoUser": False, "checksum": "d1",
        }),
        _item(b, "dependents", "dependent[]", {
            "dependentId": "D2", "relation": "C", "relationshipCodeType": "CH", "spouse": "N", "relationType": "D",
            "beneficiaryType": "", "status": "P", "firstName": "Riley", "lastName": last, "gender": "X",
            "birthdate": "2019-09-09", "ssn": "", "fullTimeStudent": False, "checksum": "d2",
        }),
        _item(b, "dependents", "dependent[]", {
            "dependentId": "D3", "relation": "F", "relationshipCodeType": "", "spouse": "N", "relationType": "B",
            "status": "I", "firstName": "Morgan", "lastName": "Hale", "birthdate": "1970-01-15", "ssn": "666-40-1234",
            "beneficiaryIsATrust": False, "checksum": "d3",
        }),
    ]
    overrides = [{"payCode": "OT", "payCodeDesc": "Overtime", "payRate": 54.0866}]
    positions = [_item(b, "position", "positionRate[]", {"positionCode": "ACCT", "standardPayRate": 36.0577, "checksum": "p1",
                                                          "payCodeRate": [{"payCode": "REG", "payRate": 36.0577, "billRate": 50.0}]})]
    _common_calls(b, emp, employee, address, history, rates, statuses, pto, dependents, overrides, positions)


def _employee_2(b: Builder) -> None:
    """Rehired hourly employee: SSN masked with visible last 4, declined disability answer, an
    undocumented rate period (A), sentinel dates in the rate history, blocked state tax."""
    first, last = b.name()
    emp = "P00002"
    employee = _item(b, "employee", "employee[]", {
        "id": emp, "firstName": first, "lastName": last, "middleInitial": "", "preferredName": "",
        "person": _person(b, {
            "birthDate": "1979-11-30", "gender": "M", "ethnicCode": "HL", "maritalStatus": "C", "smoker": "Y",
            "handicapped": "D", "blind": "", "veteran": "N", "disabledVet": "", "otherProtectedVet": "",
            "activeDutyBadgeVet": "", "recentlySeparatedVet": "", "serviceMedalVet": "", "deceased": False,
            "emergencyContact": [],
        }),
        "contactInformation": _item(b, "employee", "employee[].contactInformation", {"homePhone": b.phone(), "mobilePhone": "", "emailAddress": ""}),
        "client": _item(b, "employee", "employee[].client", {
            "employeeStatus": "A", "statusClass": "A", "statusDate": "2020-02-03", "employeeType": "PTS", "typeClass": "P",
            "jobCode": "WHSE", "firstHireDate": "2012-05-14", "lastHireDate": "2020-02-03", "seniorityDate": "2012-05-14",
            "flsaExempt": False, "employee1099": False, "rehireOk": "", "termReasonCode": "", "clientEmployeeId": "1001-04",
            "lastJobChangeDate": "2020-02-03", "homeDepartment": "OPS", "homeDivision": "", "projCostCenter": "",
            "subCostCenter": "", "homeLocation": "SLC", "manager": "", "unionCode": "", "workEmail": "", "workPhone": "",
        }),
        "compensation": _item(b, "employee", "employee[].compensation", {
            "ssn": "***-**-4321", "payGroup": "BW", "payPeriod": "B", "payMethod": "H", "hourlyPayRate": "22.50",
            "hourlyPayPeriod": "A", "hourlyPay": "22.50", "salary": "", "annualPay": "46800.00", "standardHours": "80",
            "effectiveDate": "2020-02-03", "payRate3": "19.00", "payRate4": "20.00", "citizenshipStatus": "", "fedFilingStatus": "SS", "fedWithholdAllowance": "0",
            "fedMultipleJobs": True, "fedDependents": 0, "fedOtherIncome": 1250.00, "fedDeductions": 0,
            "fedOverrideType": "", "fedOverrideAmt": "",
            "stateTax": [_item(b, "employee", "employee[].compensation.stateTax[]", {
                "stateCode": "UT", "filingStatus": "O", "primaryAllowance": "0", "multipleJobs": True, "dependents": 0,
                "otherIncome": 0, "deductions": 0, "overrideType": "B", "overrideAmount": "",
            })],
            "localTax": [], "formI9Filed": True, "nonResAlien": False,
        }),
        "directDeposit": prismhr_setups.deposit_block(b, emp),
    })
    address = _address(b, {"addressLine1": b.street(), "city": "Ogden", "county": "Weber", "stateAbbr": "UT", "zipCode": "84401", "zipSuffix": ""})
    history = [
        {"type": "Termination", "effectiveDate": "2018-08-31", "termination": {"employeeStatusCode": "T", "employeeTypeCode": "PTS", "reason": "Moved away", "rehireOK": "Y", "explanation": "Relocated to another state"}},
        {"type": "Status", "effectiveDate": "2020-02-03", "statusChange": {"employeeStatusCode": "A", "employeeTypeCode": "PTS", "reason": "Rehire"}},
        {"type": "Position", "effectiveDate": "2020-02-03", "newPositionCode": "WHSE"},
    ]
    rates = [
        _rate(b, "2012-05-14", "15.00", "H", "H", "15.00", "31200.00", "Hire"),
        _rate(b, "9999-12-31", "17.25", "H", "H", "17.25", "35880.00", "Promo"),
        _rate(b, "0000-01-01", "18.00", "H", "H", "18.00", "37440.00", "Promo"),
        _rate(b, "2020-02-03", "22.50", "H", "H", "22.50", "46800.00", "Rehire", pct="25.00", amt="9360.00"),
    ]
    statuses = [
        _status(b, "2012-05-14", "A", "Active", "PTS", "Part time seasonal"),
        _status(b, "2018-08-31", "T", "Terminated", "PTS", "Part time seasonal"),
        _status(b, "2020-02-03", "A", "Active", "PTS", "Part time seasonal"),
    ]
    _common_calls(b, emp, employee, address, history, rates, statuses, [], [], [], [])


def _employee_3(b: Builder) -> None:
    """Terminated 1099 contractor with blanks: blank SSN, gender U, undocumented pay method C,
    a pay group without a payroll schedule, percentage override P, deceased."""
    first, last = b.name()
    emp = "P00003"
    employee = _item(b, "employee", "employee[]", {
        "id": emp, "firstName": first, "lastName": last, "middleInitial": "", "preferredName": "",
        "person": _person(b, {
            "birthDate": "", "gender": "U", "ethnicCode": "NS", "maritalStatus": "", "smoker": "", "handicapped": "Y",
            "veteran": "Y", "disabledVet": "Y", "otherProtectedVet": "Y", "activeDutyBadgeVet": "Y",
            "recentlySeparatedVet": "Y", "serviceMedalVet": "Y", "deceased": True, "deceasedDate": "2025-06-28",
            "emergencyContact": [{"contactName": "Lee Park", "contactInfo": "", "contactRelationship": "Friend", "contactType": "OTHER"}],
        }),
        "contactInformation": _item(b, "employee", "employee[].contactInformation", {}),
        "client": _item(b, "employee", "employee[].client", {
            "employeeStatus": "T", "statusClass": "T", "statusDate": "2025-06-30", "employeeType": "IC", "typeClass": "C",
            "jobCode": "WHSE", "firstHireDate": "2023-01-09", "lastHireDate": "2023-01-09", "seniorityDate": "",
            "flsaExempt": False, "employee1099": True, "rehireOk": "N", "termReasonCode": "DEC",
            "termExplanation": "Estate notified", "clientEmployeeId": "", "homeDepartment": "OPS", "manager": "P00001",
            "homeLocation": "", "lastJobChangeDate": "",
        }),
        "compensation": _item(b, "employee", "employee[].compensation", {
            "ssn": "", "payGroup": "MO", "payPeriod": "M", "payMethod": "C", "hourlyPayRate": "", "hourlyPayPeriod": "",
            "hourlyPay": "", "salary": "", "annualPay": "", "standardHours": "", "effectiveDate": "", "payRate2": "",
            "citizenshipStatus": "Z03", "fedFilingStatus": "H", "fedWithholdAllowance": "", "fedOverrideType": "P",
            "fedOverrideAmt": "10.00", "stateTax": [], "localTax": [], "formI9Filed": False, "nonResAlien": True,
            "alienRegExpDate": "2026-12-31",
        }),
    })
    address = _address(b, {"addressLine1": b.street(), "city": "Provo", "county": "Utah", "stateAbbr": "UT", "zipCode": "84601"},
                       w2={"addressLine1": "PO Box 77", "addressLine2": "Suite 5", "city": "Provo", "county": "Utah", "stateAbbr": "UT", "zipCode": "84603"})
    rates = [_rate(b, "2023-01-09", "1500.00", "M", "C", "", "18000.00", "Contract")]
    statuses = [
        _status(b, "2023-01-09", "A", "Active", "IC", "Independent contractor"),
        _status(b, "2025-06-30", "T", "Terminated", "IC", "Independent contractor"),
    ]
    history = [{"type": "Termination", "effectiveDate": "2025-06-30", "termination": {"employeeStatusCode": "T", "employeeTypeCode": "IC", "reason": "Deceased", "rehireOK": "N"}}]
    _common_calls(b, emp, employee, address, history, rates, statuses, [], [], [], [])
