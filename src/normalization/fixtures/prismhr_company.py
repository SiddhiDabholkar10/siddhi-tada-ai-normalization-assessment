"""PrismHR company inputs: the client list and client masters, plus the pay code, deduction code
and location lists that extend the shared getClientCodes response (built in prismhr.py).

Edge cases (company table, D-077): an EIN masked with no visible digit and an empty one (D-024),
a pending client whose status class has no canonical value (P, unmapped) and whose code
routes are absent from the bundle, the live-only reverseWireAccount, pay codes of every pay
class with a unit (U) reason and an empty rate class, an undocumented deduction type (VG,
D-026), an unmapped calculation method (U), an obsolete code and an obsolete location.
"""
from .common import Builder

CLIENT = "1001"
PENDING_CLIENT = "1002"
OK = {"errorCode": "0", "errorMessage": ""}
R = {
    "clients": "/clientMaster/v1/getClientList",
    "master": "/clientMaster/v1/getClientMaster",
    "codes": "/clientMaster/v1/getClientCodes",
}


def add(b: Builder) -> None:
    b.part("company")
    b.add(R["clients"], {}, {**OK, "clientListResult": {"clientList": [
        b.shaped(R["clients"], "clientListResult.clientList[]", {"clientId": CLIENT, "clientName": "Wasatch Outfitters", "legalName": "Wasatch Outfitters Inc", "status": "ACT"}),
        b.shaped(R["clients"], "clientListResult.clientList[]", {"clientId": PENDING_CLIENT, "clientName": "Bonneville Labs", "legalName": "Bonneville Labs LLC", "status": "PEND"}),
    ]}})
    b.add(R["master"], {"clientId": CLIENT}, {**OK, "clientMaster": _master(b, {
        "id": CLIENT, "clientName": "Wasatch Outfitters", "legalName": "Wasatch Outfitters Inc", "status": "ACT", "statusClass": "A",
        "statusDate": "2015-07-01", "addressLine1": "400 Quarry Ln", "addressLine2": "Suite 210", "city": "Salt Lake City",
        "stateCode": "UT", "zipCode": "84111", "zipSuffix": "3302", "mainPhone": f"801-555-{b.rng.randint(1000, 1999)}",
        "emailAddress": "payroll@wasatch.example", "federalIdNumber": "*********", "serviceType": "PEO", "sicCode": "5941",
        "naicsCode": "451110", "corporationType": "C", "payrollDate": "2025-01-10", "contractDate": "2015-07-01",
        "payCardAccount": "PC-77120", "instantPayAccount": "IP-55301", "reverseWireAccount": "RW-90012",
        "clientTax": [b.shaped(R["master"], "clientMaster.clientTax[]", {
            "suiState": "UT", "suiStateEmpId": "UT-4471-22", "stateTaxId": "UT-WH-9031", "ctrStartDate": "2015-07-01", "ctrEndDate": ""})],
        "altEmployer": [b.shaped(R["master"], "clientMaster.altEmployer[]", {
            "altEmployerId": "ALT1", "altDisplayName": "Wasatch Retail", "altAchAcct": "ACH-3301", "altCheckingAcct": "CHK-3302"})],
    })})
    # A pending client with no visible EIN and no code routes in the bundle (Phase 5: source_unavailable).
    b.add(R["master"], {"clientId": PENDING_CLIENT}, {**OK, "clientMaster": _master(b, {
        "id": PENDING_CLIENT, "clientName": "Bonneville Labs", "legalName": "Bonneville Labs LLC", "status": "PEND", "statusClass": "P",
        "statusDate": "2025-03-01", "addressLine1": "9 Harbor Rd", "city": "Ogden", "stateCode": "UT", "zipCode": "84401",
        "federalIdNumber": "",
    })})


def _master(b: Builder, values: dict) -> dict:
    return b.shaped(R["master"], "clientMaster", values)


def pay_codes(b: Builder) -> list[dict]:
    """getClientCodes payCode[]: every pay code the vouchers use (D-023), one per pay class."""
    def code(values: dict) -> dict:
        return b.shaped(R["codes"], "clientCodes.payCode[]", {"payType": "R", "calcMethod": "H", "workCompTaxable": "Y", "flag401k": True,
                                                              "productiveWork": True, "excludeACACalc": False, **values})
    return [
        code({"id": "REG", "payDescription": "Regular", "payClass": "E", "compensationType": "C", "rateClass": "S", "payReason": "H"}),
        code({"id": "OT", "payDescription": "Overtime", "payClass": "E", "compensationType": "C", "rateClass": "P", "payReason": "H"}),
        code({"id": "VAC", "payDescription": "Vacation", "payClass": "E", "compensationType": "C", "rateClass": "S", "payReason": "H"}),
        code({"id": "PIECE", "payDescription": "Piece rate", "payClass": "E", "compensationType": "C", "rateClass": "O", "payReason": "U"}),
        code({"id": "CONTR", "payDescription": "Contract fee", "payClass": "E", "compensationType": "C", "rateClass": "S", "payReason": "U", "flag401k": False}),
        code({"id": "TIPS", "payDescription": "Reported tips", "payClass": "RT", "compensationType": "N", "rateClass": "S", "payReason": "U"}),
        code({"id": "MILE", "payDescription": "Mileage", "payClass": "R", "compensationType": "C", "rateClass": "D", "payReason": "U",
              "obsoleteDate": "2024-12-31"}),
        code({"id": "FRINGE", "payDescription": "Group term life", "payClass": "F", "compensationType": "N", "rateClass": "", "payReason": "U",
              "w2FormBox": "12", "w2FormCode": "C", "flag401k": False}),
        code({"id": "MEMO", "payDescription": "Memo", "payClass": "M", "compensationType": "N", "rateClass": "S", "payReason": "U", "flag401k": False}),
    ]


def deduction_codes(b: Builder) -> list[dict]:
    """getClientCodes deductionCode[]: every code the setups and vouchers use (D-047)."""
    def code(values: dict) -> dict:
        return b.shaped(R["codes"], "clientCodes.deductionCode[]", {"mandatory": False, "printOnPaystub": "Y", **values})
    return [
        code({"id": "401K", "description": "401(k)", "type": "K", "calculationMethod": "K", "client401K": True, "formW2Box": "12", "formW2Code": "D",
              "maximum": "23500.00", "matchPercent": "50"}),
        code({"id": "401KC", "description": "401(k) catch-up", "type": "KC", "calculationMethod": "K", "client401K": True, "client401kCatchUp": True}),
        code({"id": "ROTH", "description": "Roth 401(k)", "type": "KR", "calculationMethod": "PG", "formW2Box": "12", "formW2Code": "AA"}),
        code({"id": "MED", "description": "Medical", "type": "C", "calculationMethod": "F", "clientSection125": True, "clientMedicalPlan": True}),
        code({"id": "DEN", "description": "Dental", "type": "C", "calculationMethod": "F", "clientSection125": True}),
        code({"id": "LTD", "description": "Long-term disability", "type": "P", "calculationMethod": "F", "toArrears": "Y"}),
        code({"id": "FSA", "description": "Health FSA", "type": "F", "calculationMethod": "F", "clientFSADependentCare": False}),
        code({"id": "GARN", "description": "Child support", "type": "G", "calculationMethod": "G"}),
        code({"id": "SPOUSE", "description": "Spousal support", "type": "G", "calculationMethod": "G"}),
        code({"id": "IRS", "description": "IRS Levy", "type": "VG", "calculationMethod": "G"}),
        code({"id": "LOAN", "description": "Payroll advance", "type": "L", "calculationMethod": "F"}),
        code({"id": "401KL", "description": "401(k) loan", "type": "KL", "calculationMethod": "F"}),
        code({"id": "CHAR", "description": "Charity", "type": "V", "calculationMethod": "PE"}),
        code({"id": "ADJ", "description": "Memo offset", "type": "V", "calculationMethod": "F"}),
        code({"id": "UNION", "description": "Union dues", "type": "V", "calculationMethod": "U", "unionRelated": "Y", "obsoleteDate": "2023-06-30"}),
    ]


def locations(b: Builder) -> list[dict]:
    """getClientCodes locationCode[]: the employees' location and an obsolete one."""
    def location(values: dict) -> dict:
        return b.shaped(R["codes"], "clientCodes.locationCode[]", values)
    return [
        location({"id": "SLC", "locationName": "Salt Lake City", "geoCode": "450351000", "addressLine1": "400 Quarry Ln",
                  "addressLine2": "Suite 210", "city": "Salt Lake City", "county": "Salt Lake", "state": "UT", "zipCode": "84111",
                  "zipSuffix": "3302", "workCompState": "UT", "locationObsolete": False,
                  "locationContacts": [{"contactName": "Dana Reyes", "contactDescription": "Site manager", "emailAddress": "dana.site@example.org",
                                        "telephone": "801-555-1440", "fax": ""}]}),
        location({"id": "OGD", "locationName": "Ogden (closed)", "geoCode": "450571000", "addressLine1": "9 Harbor Rd", "addressLine2": "",
                  "city": "Ogden", "county": "Weber", "state": "UT", "zipCode": "84401", "zipSuffix": "", "workCompState": "UT",
                  "obsoleteDate": "2022-12-31", "locationObsolete": True, "locationContacts": []}),
    ]
