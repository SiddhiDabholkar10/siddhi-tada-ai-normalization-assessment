"""isolved employee bundle: one client, one legal, three employees on two list pages.

Edge cases (employee tables, D-077): masked twins next to unmasked values (contacts), an SSN
still masked in employeesWithSSN, an absent idType, a key absent (gender) vs null (disabled)
vs blank, labels not in the code tables (employment status, filing status FDM2), a rehired
employee with two employments, 404 on jobs (no records, D-011) and on contacts (unknown), an
I-9 completion date sent as a timestamp, accrual amounts without a unit, a manager in another
legal, a job supervisor not among the employees read, and no salary entry in effect.

The bundle also holds the company, setup and payroll inputs (isolved_company.py,
isolved_setups.py, isolved_payroll.py, D-082). The legal record is shared: it carries the
employee fields (work locations, pay groups) and the company fields.
"""
from . import isolved_company, isolved_payroll, isolved_setups
from .common import Builder, page_size, routing
from .isolved_company import CLIENT, LEGAL

API = "/api/clients/{clientId}/legals/{legalId}"
R = {
    "legals": "/api/clients/{clientId}/legals",
    "list": f"{API}/employees",
    "ssn": f"{API}/employeesWithSSN",
    "detail": f"{API}/employees/{{id}}",
    **{name: f"{API}/employees/{{employeeId}}/{name}" for name in (
        "statuses", "categories", "jobs", "payRates", "salaries", "veteranStatus", "contacts", "accruals", "skills",
        "education", "certifications", "training", "priorEmployment")},
    "i9": f"{API}/employees/{{employeeId}}/i9/status",
}


def ts(day: str) -> str:
    """An isolved date: midnight timestamp (CANONICAL_MODEL 1.6)."""
    return f"{day}T00:00:00"


def build(seed: int) -> dict:
    b = Builder("isolved", "900002", seed)
    _legals(b)
    people = [_employee_1(b), _employee_2(b), _employee_3(b)]
    lists = [item for item, _ in people]
    # The list is paged (D-013): two pages, zero-based ``page`` as live.
    size = page_size("isolved", R["list"])
    b.add(R["list"], {"clientId": CLIENT, "legalId": LEGAL, "page": 0, "pageSize": size},
          {"results": lists[:size], "totalItems": 3, "totalPages": 2, "nextPageUrl": "page=1", "previousPageUrl": None})
    b.add(R["list"], {"clientId": CLIENT, "legalId": LEGAL, "page": 1, "pageSize": size},
          {"results": lists[size:], "totalItems": 3, "totalPages": 2, "nextPageUrl": None, "previousPageUrl": "page=0"})
    ssn_rows = [{**item, "ssn": ssn, **({"idType": id_type} if id_type is not None else {})} for item, (ssn, id_type) in people]
    b.add(R["ssn"], {"clientId": CLIENT, "legalId": LEGAL, "page": 0, "pageSize": page_size("isolved", R["ssn"])}, {"results": ssn_rows, "totalItems": 3, "totalPages": 1})
    isolved_company.add(b)
    isolved_setups.add(b)
    names = {item["id"]: f'{item["nameAddress"]["lastName"]}, {item["nameAddress"]["firstName"]}' for item in lists}
    isolved_payroll.add(b, names)
    return b.bundle()


def _legals(b: Builder) -> None:
    b.add(R["legals"], {"clientId": CLIENT}, [isolved_company.legal(b)])


def _list_item(b: Builder, values: dict) -> dict:
    return b.shaped(R["list"], "results[]", values)


def _sub(b: Builder, name: str, employee: int, body, status: int = 200) -> None:
    b.add(R[name], {"clientId": CLIENT, "legalId": LEGAL, "employeeId": employee}, body, status)


def _rows(b: Builder, name: str, items: list[dict]) -> list[dict]:
    return [b.shaped(R[name], "[]", item) for item in items]


def _tax(category: str, description: str, **values) -> dict:
    base = {"id": {"FEDWT": 101, "STATEWT": 102, "CITYWT": 103}[category], "taxCategoryId": category, "taxDescription": description, "additionalAmount": 0,
            "additionalIncomeAmount": 0, "additionalPercent": 0, "deductionExemptionAmount": 0, "dependantExemptionAmount": 0,
            "exemptionAmount": 0, "isBlocked": False, "multipleJobsOrSpouseWorks": False, "primaryExemptions": 0,
            "secondaryExemptions": 0, "alternateCalculation": ""}
    return {**base, **values}


def _employee_1(b: Builder) -> tuple[dict, tuple]:
    """Active hourly employee with every sub-route filled."""
    emp = 70001
    first, last = b.name()
    item = _list_item(b, {
        "id": emp, "employeeNumber": "E-1001", "legalCode": "HSL",
        "nameAddress": {"id": 1, "firstName": first, "middleName": "Lee", "lastName": last, "prefix": "Ms.", "suffix": "",
                        "preferredName": "Mia", "preferredPronouns": "she/her", "address1": b.street(), "address2": "Apt 3",
                        "city": "Portland", "state": "OR", "zipCode": "97201", "residentGeoCode": "380510000", "schoolDistrictCode": 12},
        "personal": {"id": 2, "homePhone": b.phone("503"), "mobilePhone": b.phone("503"), "faxNumber": "", "officePhone": "503-555-0300",
                     "personalEmailAddress": "mia.home@example.com", "preferredPronouns": ""},
        "emailAddress": "mia@example.com", "birthDate": ts("1990-02-14"), "gender": "Female",
        "ethnicOrigin": "Asian (Not Hispanic or Latino)", "maritalStatus": "Married", "citizenship": "Citizen of the United States",
        "militaryStatus": "None", "protectedVeteran": False, "isRecentlySeparatedVeteran": False, "veteranStatusNotSpecified": False,
        "disabled": False, "disabledEffectiveDate": None, "disabledRequiresAccomodation": False, "disabilityDescription": "",
        "tobaccoUse": False, "tobaccoUseEffectiveDate": ts("2020-01-01"), "uniqueId": "UQ-70001", "timeclockId": "TC-11",
        "employmentStatus": "Active", "statusDate": ts("2019-04-01"), "employmentCategoryCode": "FT",
        "employmentCategoryEffectiveDate": ts("2019-04-01"), "employmentCategoryFullTimeEquivalent": 1.0,
        "acaEmploymentStatus": "ACA Full Time", "hireDate": ts("2019-04-01"), "originalHireDate": ts("2019-04-01"),
        "rehireDate": None, "adjustedServiceDate": ts("2019-04-01"), "terminationDate": None, "terminationReason": "",
        "terminationType": "", "eligibleForRehire": True, "isPending": False, "enableSelfService": True, "isManager": False,
        "isSupervisor": False, "isRemoteWorker": True, "jobId": 300, "jobCode": "CLK", "jobTitle": "Clerk",
        "jobEffectiveDate": ts("2021-03-01"), "jobEeoCategory": "Administrative Support Workers", "jobFLSAExempt": False,
        "jobIsSeasonal": False, "jobIsUnion": False, "jobGroup": "Office", "socCode": "43-9061", "workersCompCode": "8810",
        "workLocation": "HQ", "workLocationDashDescription": "HQ - Head office",
        "organizations": [{"id": 1, "organizationId": 10, "displayOrder": 1, "title": "Department", "value": "FIN", "valueDescription": "Finance"}],
        "assignedManager": {"id": 70009, "legalId": 6002, "employeeName": "Other Legal Manager", "employeeNumber": "E-9", "jobTitle": "Lead", "payrollEmploymentStatusCode": "A"},
        "assignedSupervisor": {"id": 70002, "legalId": int(LEGAL), "employeeName": "Supervisor", "employeeNumber": "E-1002"},
        "payType": "Hourly", "payGroup": "Biweekly", "payFrequency": 26, "hourlyRate": 23.75, "annualSalary": 49400.00,
        "perPaySalary": 1900.00, "normalHours": 80.00, "salaryEffectiveDate": ts("2024-01-01"),
        "payRates": [{"payRateName": "Rate 2", "rateValue": 30.0}],
        "taxes": {
            "federal": _tax("FEDWT", "Federal Withholding", filingStatus="FDS", primaryExemptions=1, additionalAmount=15.0,
                            dependantExemptionAmount=500.0, additionalIncomeAmount=100.0, deductionExemptionAmount=50.0, taxState=""),
            "residentState": _tax("STATEWT", "Utah Withholding", filingStatus="UTS", taxState="UT", additionalPercent=1.5),
            "nonResidentState": _tax("STATEWT", "Oregon Withholding", filingStatus="ORM", taxState="OR", multipleJobsOrSpouseWorks=True),
            "residentCity": _tax("CITYWT", "Philadelphia Wage Tax", filingStatus="", taxState="PA", exemptionAmount=6.0, primaryExemptions=6),
        },
        "reciprocityRule": "UT-OR",
        "i9Documents": {"i9Completed": True, "i9CompletedDate": "2019-04-03T13:45:00"},
        # Excluded block (D-081, never sent live; the directdeposits route is the source): in the
        # fixture so a test can show it leaves no trace.
        "directDeposits": [{"id": 1, "accountNumber": "4400921387", "accountType": "Checking", "frequency": "Every Pay",
                            "routingNumber": routing("310002"), "sequenceNumber": 1, "status": "Active", "bankName": "Cascade Bank", "percent": 100}],
        "labors": [], "miscFields": [{"title": "Shirt size", "value": "M"}],
        "wotc": {"applicationDate": ts("2019-04-01")},
    })
    _sub(b, "statuses", emp, _rows(b, "statuses", [
        {"statusId": 1, "employeeEmploymentId": 801, "clientEmploymentStatusId": 1, "clientEmploymentStatusDescription": "Active",
         "effectiveDate": ts("2019-04-01"), "endDate": None, "changeReason": "New hire", "statusBeginNotes": "Started in finance", "isImpliedStatus": False},
    ]))
    _sub(b, "categories", emp, _rows(b, "categories", [
        {"id": 1, "employmentId": 801, "effectiveDate": ts("2019-04-01"), "employmentCategory": {"id": 2, "code": "FT", "description": "Full Time", "acaEmploymentStatus": "ACA Full Time", "isInactive": False},
         "changeReason": {"id": 3, "code": "NH", "description": "New hire", "changeReasonType": {"id": "C", "description": "Category"}},
         "employmentPeriod": "Permanent", "fullTimeEquivalent": 1.0, "corporateOfficer": False},
    ]))
    _sub(b, "jobs", emp, _rows(b, "jobs", [
        {"id": 11, "effectiveDate": ts("2019-04-01"), "clientJob": {"id": 299, "jobCode": "TRN", "jobTitle": "Trainee", "eeoCategory": "Service Workers", "isFLSAExempt": False},
         "manager": {"id": 70002, "firstName": "Sup", "lastName": "Visor"}, "supervisor": {"id": 70099, "firstName": "Gone", "lastName": "Person"},
         "organizations": [{"organizationValue": "OPS", "clientOrganizationField": {"id": 10, "title": "Department", "lookups": [
             {"code": "FIN", "description": "Finance"}, {"code": "OPS", "description": "Operations"}]}}],
         "workersComp": {"id": 4, "code": "8810", "description": "Clerical"}, "comments": "Probation period",
         "changeReason": {"id": 7, "code": "NH", "description": "New hire", "changeReasonType": {"id": "J", "description": "Job"}},
         "compaRatio": "0.95", "shiftNumber": "1"},
        {"id": 12, "effectiveDate": ts("2021-03-01"), "clientJob": {"id": 300, "jobCode": "CLK", "jobTitle": "Clerk", "eeoCategory": "Administrative Support Workers"},
         "organizations": [], "workersComp": {"id": 4, "code": "8810"}, "comments": "",
         "changeReason": {"id": 8, "code": "PR", "description": "Promotion"}},
    ]))
    _sub(b, "payRates", emp, _rows(b, "payRates", [
        {"id": 1, "payRateId": 2, "rateDescription": "Rate 2", "rateValue": 30.0, "laborRates": [{"id": 1, "defaultRate": 31.0, "laborValue": "L1", "title": "Labor"}]},
        {"id": 2, "payRateId": 3, "rateDescription": "Rate 3", "rateValue": None, "laborRates": []},
    ]))
    _sub(b, "salaries", emp, _rows(b, "salaries", [
        {"id": 1, "effectiveDate": ts("2019-04-01"), "payType": {"id": "1", "description": "Hourly"}, "perPaySalary": 1600.00,
         "hourlyRate": 20.00, "frequency": {"id": 24, "description": "Semi-Monthly"}, "payGroup": {"id": 7624, "description": "Semimonthly"},
         "changeReason": {"id": 1, "description": "Hire"}, "isInactive": False, "lifeEvent": False, "normalHours": 80.00, "comments": "Starting rate"},
        {"id": 2, "effectiveDate": ts("2024-01-01"), "payType": {"id": "1", "description": "Hourly"}, "perPaySalary": 1900.00,
         "hourlyRate": 23.75, "frequency": {"id": 26, "description": "Bi-Weekly"}, "payGroup": {"id": 7625, "description": "Biweekly"},
         "changeReason": {"id": 2, "description": "Annual increase"}, "isInactive": False, "lifeEvent": False, "normalHours": 80.00, "comments": ""},
    ]))
    _sub(b, "veteranStatus", emp, {"activeWartimeOrCampaignBadgeVeteran": False, "disabledVeteran": False, "serviceMedalVeteran": True,
                                    "veteranStatus": "Veteran", "activeDutySeparationDate": None})
    _sub(b, "contacts", emp, _rows(b, "contacts", [
        {"id": 9001, "firstName": "Noah", "middleName": "", "lastName": last, "prefix": "Mr.", "suffix": "Jr.", "relationshipCode": "SP",
         "genderCode": "M", "birthDate": "**/**/1988", "birthDateUnmasked": ts("1988-07-20"), "ssn": "*****6789", "ssnUnmasked": "666-22-6789",
         "ssnAppliedFor": False, "isDependent": True, "isBeneficiary": True, "isEmergencyContact": True, "address1": "9 Pine St",
         "address2": "Apt 2", "city": "Portland", "state": "OR", "zipCode": "97202", "useEmployeeAddress": False, "homePhone": b.phone("503"),
         "mobilePhone": b.phone("503"), "workPhone": "503-555-0330", "emailAddress": "noah@example.com", "maritalStatusCode": "M",
         "isDeceased": False, "isDisabled": False, "isStudent": False, "notifyIfArrestedDetained": True, "emergencyCallOrder": 1,
         "hideForSelfService": False, "isChanged": False, "nayyaSyncAuditBatchId": 0},
        {"id": 9002, "firstName": "Ivy", "middleName": "Rae", "lastName": last, "relationshipCode": "CH", "genderCode": "F", "birthDate": "**/**/2018",
         "birthDateUnmasked": ts("2018-03-03"), "ssn": "*****4444", "ssnUnmasked": "*****4444", "isDependent": True,
         "isBeneficiary": False, "isEmergencyContact": False, "useEmployeeAddress": True, "isStudent": True},
    ]))
    _sub(b, "accruals", emp, _rows(b, "accruals", [
        {"id": 77, "planId": 55, "planDescription": "Vacation Salary", "accrualName": "Vacation", "currentBalance": 40.0,
         "availableBalance": "40.00", "carryoverBalance": 8.0, "ytdAccrued": 32.0, "ytdTaken": 0.0, "currentAccrued": 1.54,
         "currentTaken": 0.0, "accrualMethod": "Per Pay", "planBalanceLimit": 120.0, "serviceDate": ts("2019-04-01")},
    ]))
    _sub(b, "skills", emp, _rows(b, "skills", [{"id": 1, "skill": "Spanish", "proficiency": "Fluent", "dateAttained": ts("2019-06-01"),
                                               "experience": "5 years", "lastUsed": "2024", "comments": "Interpreter", "miscellaneous": "Medical terms"}]))
    _sub(b, "education", emp, _rows(b, "education", [{"id": 2, "educationType": "College", "degree": "BA", "school": "Lakeside College",
                                                     "completionDate": ts("2012-05-15"), "major": "History", "minor": "Art", "honors": "Cum laude",
                                                     "graduated": True, "gpa": "3.4", "comments": ""}]))
    _sub(b, "certifications", emp, _rows(b, "certifications", [{"id": 3, "certification": "CPR", "authority": "Red Cross",
                                                               "effectiveDate": ts("2024-01-10"), "expirationDate": ts("2026-01-10"),
                                                               "licenseNumber": "CPR-55120", "cost": 50.0, "reimbursementAmount": 50.0,
                                                               "reimbursementApprovalDate": ts("2024-01-12"), "reimbursementDate": ts("2024-01-30"),
                                                               "comments": "", "miscellaneous": "Renew online"}]))
    _sub(b, "training", emp, _rows(b, "training", [{"id": 4, "title": "Forklift safety", "className": "FS-101", "startDate": ts("2024-03-01"),
                                                   "endDate": ts("2024-03-02"), "expirationDate": ts("2027-03-01"), "isCompleted": True,
                                                   "isMandatory": True, "duration": "4", "creditsEarned": 0.5, "instructor": "A. Smith",
                                                   "location": "Warehouse", "cost": 120.0, "comments": "Passed"}]))
    _sub(b, "priorEmployment", emp, _rows(b, "priorEmployment", [{"id": 5, "employer": "Acme Logistics", "jobTitle": "Driver",
                                                                 "startDate": ts("2015-01-05"), "endDate": ts("2019-03-15"),
                                                                 "endingSalary": 41000.0, "reference": "J. Doe", "changeReason": "Moved"}]))
    _sub(b, "i9", emp, {"hasSignedI9Form": True, "isComplete": True, "isDocumentUploadComplete": None,
                        "uploadedDocuments": [{"id": 1, "documentFileName": "i9-scan.pdf", "documentUploadDate": ts("2019-04-03")}]})
    b.add(R["detail"], {"clientId": CLIENT, "legalId": LEGAL, "id": emp}, {
        **item, "taxExemptStatus": "Exempt from city tax",
        "i9Documents": {**item["i9Documents"], "documentA": {
            "documentCode": "USP", "documentDescription": "U.S. Passport", "documentNumber": "P1234567", "issuingAuthority": "US DOS",
            "expirationDate": ts("2030-05-01"), "documentFileName": "passport.pdf", "documentContent": "", "allowEmployeeAccess": True}},
        "miscDataSets": [{"id": 1, "isDeleted": False, "miscFieldCategory": {"id": 3, "categoryTitle": "Uniform", "isDataSet": True},
                         "fields": [{"id": {"fieldCode": "SIZE", "fieldTitle": "Size", "dataType": "Text", "category": "Uniform"}, "miscValue": "M"}]}],
    })
    return item, ("666-31-0001", "SSN")


def _employee_2(b: Builder) -> tuple[dict, tuple]:
    """Rehired salaried employee: two employments, jobs 404 (no records), contacts 404 (unknown)."""
    emp = 70002
    first, last = b.name()
    item = _list_item(b, {
        "id": emp, "employeeNumber": "E-1002", "legalCode": "HSL",
        "nameAddress": {"id": 3, "firstName": first, "lastName": last, "suffix": "Jr.", "address1": b.street(), "city": "Salem", "state": "OR", "zipCode": "97301"},
        "personal": {"id": 4, "homePhone": "", "mobilePhone": b.phone("503")},
        "birthDate": ts("1975-09-09"), "gender": "Male", "ethnicOrigin": "White (Not Hispanic or Latino)", "maritalStatus": "Single",
        "disabled": True, "disabledEffectiveDate": ts("2020-06-01"), "disabledRequiresAccomodation": True, "disabilityDescription": "Mobility",
        "disabilityNotes": "Standing desk", "tobaccoUse": None,
        "employmentStatus": "Active", "statusDate": ts("2022-01-10"), "employmentCategoryCode": "PT", "hireDate": ts("2022-01-10"),
        "originalHireDate": ts("2010-05-03"), "rehireDate": ts("2022-01-10"), "adjustedServiceDate": ts("2014-02-01"),
        "terminationDate": ts("2021-06-30"), "terminationReason": "Relocation", "terminationType": "Voluntary Termination",
        "eligibleForRehire": True, "jobId": 301, "jobCode": "SUP", "jobTitle": "Supervisor", "jobEffectiveDate": ts("2022-01-10"),
        "jobEeoCategory": "First/Mid Level Officials and Managers", "jobFLSAExempt": True, "jobIsSeasonal": False,
        "workLocation": "ZZ", "organizations": [], "payType": "Salary", "payGroup": "Biweekly", "payFrequency": 26,
        "hourlyRate": 0, "annualSalary": 62400.00, "perPaySalary": 2400.00, "normalHours": 80, "salaryEffectiveDate": ts("2022-01-10"),
        "taxes": {"federal": _tax("FEDWT", "Federal Withholding", filingStatus="FDM", primaryExemptions=3, multipleJobsOrSpouseWorks=True)},
        "i9Documents": {"i9Completed": True, "i9CompletedDate": ts("2022-01-12")},
    })
    _sub(b, "statuses", emp, _rows(b, "statuses", [
        {"statusId": 2, "employeeEmploymentId": 811, "clientEmploymentStatusDescription": "Active", "effectiveDate": ts("2010-05-03"),
         "endDate": ts("2021-06-29"), "changeReason": "New hire", "isImpliedStatus": False},
        {"statusId": 3, "employeeEmploymentId": 811, "clientEmploymentStatusDescription": "Terminated", "effectiveDate": ts("2021-06-30"),
         "endDate": ts("2022-01-09"), "changeReason": "Relocation", "isImpliedStatus": False},
        {"statusId": 4, "employeeEmploymentId": 812, "clientEmploymentStatusDescription": "Active", "effectiveDate": ts("2022-01-10"),
         "endDate": None, "changeReason": "Rehire", "isImpliedStatus": True},
    ]))
    _sub(b, "categories", emp, _rows(b, "categories", [
        {"id": 2, "employmentId": 811, "effectiveDate": ts("2010-05-03"), "employmentCategory": {"id": 2, "code": "FT", "description": "Full Time"}},
        {"id": 3, "employmentId": 812, "effectiveDate": ts("2022-01-10"), "employmentCategory": {"id": 4, "code": "PT", "description": "Part Time"},
         "changeReason": {"id": 9, "description": "Rehire"}},
    ]))
    _sub(b, "jobs", emp, None, status=404)  # no records (D-011)
    _sub(b, "payRates", emp, [])
    _sub(b, "salaries", emp, _rows(b, "salaries", [
        {"id": 3, "effectiveDate": ts("2022-01-10"), "payType": {"id": "2", "description": "Salary"}, "perPaySalary": 2400.00,
         "hourlyRate": 0, "frequency": {"id": 26, "description": "Bi-Weekly"}, "payGroup": {"id": 7625, "description": "Biweekly"},
         "changeReason": {"id": 3, "description": "Rehire"}, "isInactive": False},
    ]))
    _sub(b, "veteranStatus", emp, {"disabledVeteran": False})
    _sub(b, "contacts", emp, None, status=404)  # meaning unknown (D-011)
    for name in ("accruals", "skills", "education", "certifications", "training", "priorEmployment"):
        _sub(b, name, emp, [])
    _sub(b, "i9", emp, {"hasSignedI9Form": True, "isComplete": True, "uploadedDocuments": []})
    b.add(R["detail"], {"clientId": CLIENT, "legalId": LEGAL, "id": emp}, item)
    return item, ("666-31-0002", None)


def _employee_3(b: Builder) -> tuple[dict, tuple]:
    """1099 contractor: gender key absent, unlisted status label, filing status FDM2, blocked
    federal tax, I-9 not completed, SSN masked in employeesWithSSN, no salary entry in effect."""
    emp = 70003
    first, last = b.name()
    item = _list_item(b, {
        "id": emp, "employeeNumber": "C-2001", "legalCode": "HSL",
        "nameAddress": {"id": 5, "firstName": first, "lastName": last, "address1": "", "city": "", "state": "", "zipCode": "97035"},
        "overrideAddress": {"address1": "PO Box 12", "address2": "Unit 9", "city": "Lake Oswego", "state": "OR", "zipCode": "97034", "country": "USA",
                            "useForTaxForms": True, "useForPaychecks": False, "foreignPostalCode": "", "militaryCity": ""},
        "personal": {"id": 6, "faxNumber": "503-555-0399"},
        "ethnicOrigin": "Prefer not to say", "maritalStatus": "None", "disabled": None,
        "employmentStatus": "Leave of Absence", "statusDate": ts("2025-02-01"), "employmentCategoryCode": "PT",
        "hireDate": ts("2024-09-16"), "originalHireDate": ts("2024-09-16"), "terminationDate": None,
        "jobId": None, "jobCode": "", "workLocation": "HQ", "organizations": [], "payType": "1099", "payGroup": "Biweekly",
        "payFrequency": 26, "hourlyRate": 55.00, "salaryEffectiveDate": "2024-09-16T08:30:00",
        "taxes": {"federal": _tax("FEDWT", "Federal Withholding", filingStatus="FDM2", isBlocked=True),
                  "nonResidentCity": _tax("CITYWT", "City tax", filingStatus="", taxState="PA", additionalAmount=2.5)},
        "i9Documents": {"i9Completed": False},
    })
    _sub(b, "statuses", emp, _rows(b, "statuses", [
        {"statusId": 5, "employeeEmploymentId": 821, "clientEmploymentStatusDescription": "Leave of Absence",
         "effectiveDate": ts("2025-02-01"), "endDate": None, "changeReason": ""},
    ]))
    _sub(b, "categories", emp, [])
    _sub(b, "jobs", emp, [])
    _sub(b, "payRates", emp, [])
    _sub(b, "salaries", emp, _rows(b, "salaries", [
        {"id": 4, "effectiveDate": ts("2024-09-16"), "payType": {"id": "1", "description": "Hourly"}, "hourlyRate": 55.00,
         "frequency": {"id": 52, "description": "Weekly"}, "payGroup": {"id": 7626, "description": "Weekly"}, "isInactive": True},
    ]))
    _sub(b, "veteranStatus", emp, {})
    _sub(b, "contacts", emp, [])
    for name in ("accruals", "skills", "education", "certifications", "training", "priorEmployment"):
        _sub(b, name, emp, [])
    _sub(b, "i9", emp, {"hasSignedI9Form": False, "isComplete": False, "uploadedDocuments": []})
    b.add(R["detail"], {"clientId": CLIENT, "legalId": LEGAL, "id": emp}, item)
    return item, ("*****9876", "SSN")
