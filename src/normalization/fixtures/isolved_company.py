"""isolved company inputs: the client list, the legal record (shared with the employee
adapter, built here and added by isolved.py), the legal's miscellaneous fields and the client
pay item catalog.

Edge cases (company table, D-077): the EIN returned in full (sensitive), a pay group whose
frequency integer is not in the label table (52) and that is inactive, an inactive work
location, catalog items of every payItemType, an item with no code, system benefit types in
the label table and outside it ('Other Deduction'), and the 'Leave Accrual' type that maps to
no category.
"""
from .common import Builder, page_size

CLIENT, LEGAL = "5001", "6001"
R = {
    "clients": "/api/clients",
    "legals": "/api/clients/{clientId}/legals",
    "misc": "/api/clients/{clientId}/legals/{legalId}/miscellaneousFields",
    "catalog": "/api/clients/{clientId}/payItems",
}
# Client pay item catalog ids (D-066): check lines carry these ids, setups link by code.
EARNING = {"REG": 501, "OT": 502, "MILE": 503}
MEMO = {"401k Match": 520, "ER Medical": 521, "HSA ER": 522, "ER Life": 523}
DEDUCTION = {"401K": 601, "MEDPT": 602, "DENPT": 603, "HSA": 604, "FSA": 605, "GTL": 606, "LOAN": 607, "PTO": 608, "UNIF": 609, "LEVY": 610}


def legal(b: Builder) -> dict:
    """The legal record of /legals: the employee fields (work locations, pay groups) and the
    company fields."""
    def location(values: dict) -> dict:
        return b.shaped(R["legals"], "[].workLocations[]", values)

    def pay_group(values: dict) -> dict:
        return b.shaped(R["legals"], "[].payGroups[]", {"enableiSolvedPayroll": True, "enableiSolvedTime": False, "inputMethod": "Manual",
                                                        "payrollType": "Regular", **values})

    return b.shaped(R["legals"], "[]", {
        "id": int(LEGAL), "legalName": "Harbor Supply LLC", "dbaName": "Harbor Supply", "legalCode": "HSL", "status": "Active",
        "federalEIN": "98-7654321", "naicsCode": "423840", "allowRemoteWorkers": True, "forceDirectDepositPrenote": False,
        "iSolvedTimeEnabled": False, "logoData": None,
        "legalAddress": {"addressDescription": "Head office", "streetAddress1": "77 Juniper Way", "streetAddress2": "Floor 2", "city": "Portland",
                         "state": "OR", "zipCode": "97204", "phoneNumber": "503-555-1200"},
        "client": {"id": int(CLIENT), "clientCode": "HSG", "clientName": "Harbor Supply Group"},
        "services": [{"code": "PAYROLL", "startDate": "2018-01-01T00:00:00", "endDate": None}],
        "compensationPlans": [{"id": 1, "code": "STD", "description": "Standard plan"}],
        "workersComps": [{"workersCompId": 4, "workersCompCode": "8810", "workersCompDescription": "Clerical", "state": "OR", "isInactive": False}],
        "workLocations": [
            location({"id": 410, "workLocationCode": "HQ", "workLocationDescription": "Head office", "address1": "77 Juniper Way",
                      "address2": "Floor 2", "city": "Portland", "state": "OR", "zipCode": "97204", "isInactive": False, "geoCode": "380510000",
                      "timeZone": "Pacific", "isRemoteWorkersOnly": False, "includeWorkSiteTaxFiling": True}),
            location({"id": 411, "workLocationCode": "WH2", "workLocationDescription": "Old warehouse", "address1": "5 Quarry Ln", "address2": "",
                      "city": "Salem", "state": "OR", "zipCode": "97301", "isInactive": True}),
        ],
        "payGroups": [
            pay_group({"id": 7625, "payGroupName": "Biweekly", "payFrequency": 26, "isInactive": False, "normalHours": 80.0}),
            # 52 is not in the frequency label table (unknown); the group is inactive.
            pay_group({"id": 7626, "payGroupName": "Weekly", "payFrequency": 52, "isInactive": True, "normalHours": 40.0}),
        ],
    })


def add(b: Builder) -> None:
    b.part("company")
    b.add(R["clients"], {"page": 0, "pageSize": page_size("isolved", R["clients"])}, {
        "results": [b.shaped(R["clients"], "results[]", {"id": int(CLIENT), "clientCode": "HSG", "clientName": "Harbor Supply Group"})],
        "totalItems": 1, "totalPages": 1, "nextPageUrl": None, "previousPageUrl": None})
    b.add(R["misc"], {"clientId": CLIENT, "legalId": LEGAL}, [{"id": 1, "value": "Region West"}, {"id": 2, "value": ""}])

    def item(values: dict) -> dict:
        return b.shaped(R["catalog"], "[]", {"isInactive": False, "hasDecliningBalance": False, "scheduleDefault": "Every Pay", "calcParams": [],
                                             "payees": [], **values})

    catalog = [
        item({"id": EARNING["REG"], "code": "REG", "title": "Regular", "description": "Regular hours", "payItemType": "Earning",
              "systemBenefitType": "None", "systemPayItemType": "Regular", "sequenceNumber": 1, "calcParams": [{"paramType": "Rate"}]}),
        item({"id": EARNING["OT"], "code": "OT", "title": "Overtime", "payItemType": "Earning", "systemBenefitType": "None",
              "systemPayItemType": "Overtime", "sequenceNumber": 2}),
        item({"id": EARNING["MILE"], "code": "MILE", "title": "Mileage", "payItemType": "Earning", "systemBenefitType": "None",
              "systemPayItemType": "Reimbursement", "sequenceNumber": 3, "isInactive": True}),
        item({"id": MEMO["401k Match"], "code": "401KM", "title": "401k Match", "payItemType": "Memo Calc", "systemBenefitType": "401(k)",
              "systemPayItemType": "Memo", "sequenceNumber": 20}),
        item({"id": MEMO["ER Medical"], "code": "ERMED", "title": "ER Medical", "payItemType": "Memo Calc", "systemBenefitType": "Medical Pre-Tax 125",
              "systemPayItemType": "Memo", "sequenceNumber": 21}),
        item({"id": MEMO["HSA ER"], "code": "HSAER", "title": "HSA ER", "payItemType": "Memo Calc", "systemBenefitType": "Health Savings Account",
              "systemPayItemType": "Memo", "sequenceNumber": 22}),
        item({"id": MEMO["ER Life"], "code": None, "title": "ER Life", "payItemType": "Memo Calc", "systemBenefitType": "Group Term Life",
              "systemPayItemType": "Memo", "sequenceNumber": 23}),
        item({"id": DEDUCTION["401K"], "code": "401K", "title": "401(k)", "payItemType": "Deduction", "systemBenefitType": "401(k)",
              "systemPayItemType": "Deduction", "sequenceNumber": 30, "calcParams": [{"paramType": "Percent"}],
              "payees": [{"payeeName": "Harbor 401k Trust", "legalCompanyName": "Harbor Supply LLC"}]}),
        item({"id": DEDUCTION["MEDPT"], "code": "MEDPT", "title": "Medical", "payItemType": "Deduction", "systemBenefitType": "Medical Pre-Tax 125",
              "systemPayItemType": "Deduction", "sequenceNumber": 31, "calcParams": [{"paramType": "Amount"}]}),
        item({"id": DEDUCTION["DENPT"], "code": "DENPT", "title": "Dental", "payItemType": "Deduction", "systemBenefitType": "Dental Pre-Tax 125",
              "systemPayItemType": "Deduction", "sequenceNumber": 32}),
        item({"id": DEDUCTION["HSA"], "code": "HSA", "title": "HSA", "payItemType": "Deduction", "systemBenefitType": "Health Savings Account",
              "systemPayItemType": "Deduction", "sequenceNumber": 33}),
        item({"id": DEDUCTION["FSA"], "code": "FSA", "title": "Medical FSA", "payItemType": "Deduction", "systemBenefitType": "FSA Medical",
              "systemPayItemType": "Deduction", "sequenceNumber": 34, "hasDecliningBalance": True}),
        item({"id": DEDUCTION["GTL"], "code": "GTL", "title": "Group term life", "payItemType": "Deduction", "systemBenefitType": "Group Term Life",
              "systemPayItemType": "Deduction", "sequenceNumber": 35}),
        item({"id": DEDUCTION["LOAN"], "code": "LOAN", "title": "401K Loan", "payItemType": "Deduction", "systemBenefitType": "None",
              "systemPayItemType": "Deduction", "sequenceNumber": 36, "hasDecliningBalance": True}),
        item({"id": DEDUCTION["PTO"], "code": "PTO", "title": "PTO buyback", "payItemType": "Deduction", "systemBenefitType": "Leave Accrual",
              "systemPayItemType": "Deduction", "sequenceNumber": 37}),
        # 'Other Deduction' is not in the system benefit type table: unknown with unknown_code.
        item({"id": DEDUCTION["UNIF"], "code": "UNIF", "title": "Uniform", "payItemType": "Deduction", "systemBenefitType": "Other Deduction",
              "systemPayItemType": "Deduction", "sequenceNumber": 38}),
        item({"id": DEDUCTION["LEVY"], "code": "LEVY", "title": "Federal Tax Levy", "payItemType": "Deduction", "systemBenefitType": "None",
              "systemPayItemType": "Garnishment", "sequenceNumber": 39}),
    ]
    b.add(R["catalog"], {"clientId": CLIENT}, catalog)
