"""PrismHR companies: one Company per client (D-034).

Follows ``mappings/data/prismhr/company.json``; each ``row:`` comment cites the table row it
applies. The client id is the company id and the id of its single tax entity (D-042); owned
entries take the client id plus the provider code, as the employee adapter builds them (D-080).
"""
from typing import Any

from ...canonical.company import Company, DeductionCode, EarningCode, PayGroup, TaxEntity, WorkLocation
from ...canonical.diagnostics import DiagnosticCode, Severity
from ...canonical.ids import EntityType, Provider, canonical_id
from ...canonical.parsing import DateRole
from ...canonical.parts import PostalAddress
from ...employees.bundle import Bundle
from ...employees.common import NA, NP, Ctx, build, code_entry, is_blank
from ..common import entry_extensions, prismhr_ok, source

PROVIDER = "prismhr"
TABLE = "company"
ROUTES = {
    "getClientList": "/clientMaster/v1/getClientList",
    "getClientMaster": "/clientMaster/v1/getClientMaster",
    "getClientCodes": "/clientMaster/v1/getClientCodes",
    "getPayrollSchedule": "/clientMaster/v1/getPayrollSchedule",
}
# Pay group ids named by records (D-097): the ids are the reference rows of the payroll and employee tables.
NAMING = {
    "getBatchListByDate": "/payroll/v1/getBatchListByDate",
    "getPayrollVoucherForBatch": "/payroll/v1/getPayrollVoucherForBatch",
    "getEmployee": "/employee/v1/getEmployee",
}
MASTER_HANDLED = {"id", "legalName", "clientName", "statusClass", "statusDate", "addressLine1", "addressLine2", "city",
                  "stateCode", "zipCode", "mainPhone", "federalIdNumber", "clientTax", "payCardAccount",
                  "instantPayAccount", "reverseWireAccount", "altEmployer"}
CATCH_UP_TYPES = {"KC", "KCR"}


def _id(tenant: str, entity: EntityType, *parts: str) -> str:
    return canonical_id(Provider.PRISMHR, tenant, entity, *parts)


def normalize(bundle: Bundle) -> list[Company]:
    records = []
    for listing in bundle.all(ROUTES["getClientList"]):
        if not prismhr_ok(listing):
            continue
        clients = (listing.body.get("clientListResult") or {}).get("clientList") or []
        for index, item in enumerate(clients):
            client = item.get("clientId")  # row: getClientList clientListResult.clientList[].clientId
            if not is_blank(client):
                records.append(_company(bundle, str(client).strip(), index))
    return records


def _company(bundle: Bundle, client: str, list_index: int) -> Company:
    tenant = bundle.tenant_id
    ctx = Ctx(PROVIDER)
    sources = [source(ROUTES["getClientList"], f"/clientListResult/clientList/{list_index}")]

    def call(name: str) -> Any:
        response = bundle.get(ROUTES[name], clientId=client)
        if not prismhr_ok(response):
            return None
        sources.append(source(ROUTES[name], "/clientMaster" if name == "getClientMaster" else ""))
        return response.body

    master_body = call("getClientMaster")
    if master_body is None:
        ctx.unavailable(None, "getClientMaster is not in the input or did not succeed: client details are unknown.", "D-021")
    master = (master_body or {}).get("clientMaster") or {}
    codes_body = call("getClientCodes")
    schedule_body = call("getPayrollSchedule")
    legal_name = ctx.text(master.get("legalName"))  # row: getClientMaster clientMaster.legalName
    fields: dict[str, Any] = {
        "id": _id(tenant, EntityType.COMPANY, client),
        "provider": Provider.PRISMHR,
        "tenant_id": tenant,
        "source_ids": {"clientId": client},  # row: getClientMaster clientMaster.id
        "legal_name": legal_name,
        "display_name": ctx.text(master.get("clientName")),  # row: getClientMaster clientMaster.clientName
        "company_code": NP,  # not sent (table note)
        "status": ctx.coded("prismhr.client_status_class", master.get("statusClass"), "status"),  # row: getClientMaster clientMaster.statusClass
        "status_date": ctx.date(master.get("statusDate"), DateRole.EVENT, "status_date"),  # row: getClientMaster clientMaster.statusDate
        "address": _address(ctx, master),
        "phone": ctx.text(master.get("mainPhone")),  # row: getClientMaster clientMaster.mainPhone
        "parent": NA,  # a PrismHR client is the top company scope (D-034)
        "tax_entities": [build(
            TaxEntity,
            id=_id(tenant, EntityType.TAX_ENTITY, client),
            name=legal_name,
            ein=ctx.text(master.get("federalIdNumber"), "tax_entities[0].ein", sensitive=True),  # row: getClientMaster clientMaster.federalIdNumber
            country=NP,  # not sent (table note)
        )] if master else NP,
    }
    if codes_body is None:
        message = "getClientCodes is not in the input or did not succeed: the client's code tables are unknown."
        for name in ("work_locations", "pay_groups", "deduction_codes", "earning_codes"):
            fields[name] = ctx.unavailable(name, message, "D-021")
    else:
        codes = codes_body.get("clientCodes") or {}
        fields["work_locations"] = _locations(ctx, tenant, client, codes.get("locationCode") or [])
        fields["pay_groups"] = _pay_groups(ctx, tenant, client, codes.get("payGroups") or [], schedule_body)
        fields["deduction_codes"] = _deduction_codes(ctx, tenant, client, codes.get("deductionCode") or [])
        fields["earning_codes"] = _earning_codes(ctx, tenant, client, codes.get("payCode") or [])
    fields["pay_groups"] = _with_referenced_groups(ctx, tenant, client, fields["pay_groups"], _referenced_groups(bundle, client))
    _master_extensions(ctx, master)
    return build(
        Company,
        **fields,
        sources=sources,
        diagnostics=ctx.diagnostics,
        provider_extensions=ctx.extensions,
        sensitive_provider_extensions=ctx.sensitive_extensions,
    )


def _address(ctx: Ctx, master: dict) -> Any:
    lines = ("addressLine1", "addressLine2", "city", "stateCode", "zipCode")
    if all(is_blank(master.get(key)) for key in lines):
        return NP
    return build(
        PostalAddress,
        type="mailing",  # the delivery/mailing address (table notes)
        line1=ctx.text(master.get("addressLine1")),  # row: getClientMaster clientMaster.addressLine1
        line2=ctx.text(master.get("addressLine2")),  # row: getClientMaster clientMaster.addressLine2
        city=ctx.text(master.get("city")),  # row: getClientMaster clientMaster.city
        county=NP,
        state=ctx.text(master.get("stateCode")),  # row: getClientMaster clientMaster.stateCode
        postal_code=ctx.text(master.get("zipCode")),  # row: getClientMaster clientMaster.zipCode
        country=NP,
    )


def _master_extensions(ctx: Ctx, master: dict) -> None:
    base = "getClientMaster:clientMaster"
    # row: getClientMaster clientMaster.clientTax[].*; clientMaster.payCardAccount; clientMaster.instantPayAccount
    # row: getClientMaster clientMaster.reverseWireAccount
    for name in ("clientTax", "payCardAccount", "instantPayAccount", "reverseWireAccount"):
        ctx.keep(f"{base}.{name}", master.get(name), sensitive=True)
    for index, alt in enumerate(master.get("altEmployer") or []):
        # row: getClientMaster clientMaster.altEmployer[].altAchAcct; clientMaster.altEmployer[].altCheckingAcct
        ctx.rest(f"{base}.altEmployer[{index}]", alt, sensitive={"altAchAcct", "altCheckingAcct"})
    ctx.rest(base, master, MASTER_HANDLED)  # row: getClientMaster clientMaster.**


def _locations(ctx: Ctx, tenant: str, client: str, items: list[dict]) -> list[WorkLocation]:
    locations = []
    for index, item in enumerate(items):
        code = item.get("id")  # row: getClientCodes clientCodes.locationCode[].id
        if is_blank(code):
            continue
        key = f"getClientCodes:clientCodes.locationCode[{index}]"
        obsolete = ctx.flag(item.get("locationObsolete"), f"work_locations[{len(locations)}].is_active")  # row: getClientCodes clientCodes.locationCode[].locationObsolete
        # row: getClientCodes clientCodes.locationCode[].locationContacts[].*
        ctx.keep(f"{key}.locationContacts", item.get("locationContacts"), sensitive=True)
        handled = {"id", "locationName", "addressLine1", "addressLine2", "city", "county", "state", "zipCode",
                   "locationObsolete", "locationContacts"}
        locations.append(build(
            WorkLocation,
            id=_id(tenant, EntityType.WORK_LOCATION, client, str(code).strip()),
            code=str(code).strip(),
            name=ctx.text(item.get("locationName")),  # row: getClientCodes clientCodes.locationCode[].locationName
            address=build(
                PostalAddress,
                type="work",
                line1=ctx.text(item.get("addressLine1")),  # row: getClientCodes clientCodes.locationCode[].addressLine1
                line2=ctx.text(item.get("addressLine2")),  # row: getClientCodes clientCodes.locationCode[].addressLine2
                city=ctx.text(item.get("city")),  # row: getClientCodes clientCodes.locationCode[].city
                county=ctx.text(item.get("county")),  # row: getClientCodes clientCodes.locationCode[].county
                state=ctx.text(item.get("state")),  # row: getClientCodes clientCodes.locationCode[].state
                postal_code=ctx.text(item.get("zipCode")),  # row: getClientCodes clientCodes.locationCode[].zipCode
                country=NP,
            ),
            is_active=(not obsolete) if isinstance(obsolete, bool) else obsolete,
            provider_extensions=entry_extensions(PROVIDER, key, item, handled),  # row: getClientCodes clientCodes.locationCode[].*
        ))
    return locations


def _pay_groups(ctx: Ctx, tenant: str, client: str, items: list[dict], schedule_body: Any) -> list[PayGroup]:
    # The demo sends the singular key clientPayrollSchedule (live rename, D-062).
    schedule_key = "clientPayrollSchedule" if schedule_body and "clientPayrollSchedule" in schedule_body else "clientPayrollSchedules"
    schedules = {}
    for index, schedule in enumerate((schedule_body or {}).get(schedule_key) or []):
        group = schedule.get("groupId")  # row: getPayrollSchedule clientPayrollSchedules[].groupId
        if not is_blank(group):
            schedules[str(group).strip()] = (index, schedule)
    codes = [str(item.get("payGroupCode")).strip() for item in items if not is_blank(item.get("payGroupCode"))]  # row: getClientCodes clientCodes.payGroups[].payGroupCode
    names = {str(item.get("payGroupCode")).strip(): item.get("description") for item in items}  # row: getClientCodes clientCodes.payGroups[].description
    # A schedule whose group is not in the code list still names a pay group: it keeps its entry.
    codes += [code for code in schedules if code not in codes]
    groups = []
    for code in codes:
        where = f"pay_groups[{len(groups)}].pay_frequency"
        extensions: dict = {}
        if code in schedules:
            index, schedule = schedules[code]
            frequency = ctx.coded(
                "prismhr.pay_period",
                schedule.get("payPeriod"),  # row: getPayrollSchedule clientPayrollSchedules[].payPeriod
                where,
                label=schedule.get("payPeriodDesc"),  # row: getPayrollSchedule clientPayrollSchedules[].payPeriodDesc
            )
            # row: getPayrollSchedule clientPayrollSchedules[].*
            extensions = entry_extensions(PROVIDER, f"getPayrollSchedule:{schedule_key}[{index}]", schedule,
                                          {"groupId", "payPeriod", "payPeriodDesc"})
        elif schedule_body is None:
            frequency = ctx.unavailable(where, "getPayrollSchedule is not in the input or did not succeed.", "D-068")
        else:
            frequency = ctx.unavailable(where, f"Pay group {code!r} has no payroll schedule in the input.", "D-068")
        groups.append(build(
            PayGroup,
            id=_id(tenant, EntityType.PAY_GROUP, client, code),
            code=code,
            name=ctx.text(names.get(code)),
            pay_frequency=frequency,
            is_active=NP,  # pay groups send no active flag (table notes)
            provider_extensions=extensions,
        ))
    return groups


def _referenced_groups(bundle: Bundle, client: str) -> dict[str, list[str]]:
    """Pay group ids that batch lists, vouchers and employees of ``client`` name, in input order,
    with the kinds of record naming each (D-097)."""
    found: dict[str, list[str]] = {}

    def add(raw: Any, named_by: str) -> None:
        if not is_blank(raw) and isinstance(raw, (str, int)):
            kinds = found.setdefault(str(raw).strip(), [])
            if named_by not in kinds:
                kinds.append(named_by)

    def dicts(value: Any) -> list[dict]:
        return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []

    for response in bundle.all(NAMING["getBatchListByDate"], clientId=client):
        for batch in dicts(response.body.get("batchList")) if prismhr_ok(response) else []:
            for group in dicts(batch.get("payGroup")):
                add(group.get("payGroupId"), "batch lists")
    for response in bundle.all(NAMING["getPayrollVoucherForBatch"], clientId=client):
        body = response.body if prismhr_ok(response) else {}
        for voucher in dicts(body.get("payrollVoucher") or body.get("payrollVouchers")):  # live key singular (D-062)
            add(voucher.get("payGroup"), "vouchers")
    for response in bundle.all(NAMING["getEmployee"], clientId=client):
        for employee in dicts(response.body.get("employee")) if prismhr_ok(response) else []:
            compensation = employee.get("compensation")
            add(compensation.get("payGroup") if isinstance(compensation, dict) else None, "employees")
    return found


def _with_referenced_groups(ctx: Ctx, tenant: str, client: str, listed: Any, referenced: dict[str, list[str]]) -> Any:
    """The code list's pay groups (and schedule-only ones) plus one per id a record names that they
    lack, as D-094 does for UKG EINs (live: client 134 lists no pay groups while 37 batches name
    "Main"). Only the id is sent, so name and frequency stay null; reference_only names the sources."""
    groups = list(listed) if isinstance(listed, list) else []
    known = {group.id for group in groups}
    for code, named_by in referenced.items():
        group_id = _id(tenant, EntityType.PAY_GROUP, client, code)
        if group_id in known:
            continue
        where = f"pay_groups[{len(groups)}]"
        ctx.diag(DiagnosticCode.REFERENCE_ONLY, Severity.INFO,
                 f"getClientCodes does not list pay group {code!r}; built from the {' and '.join(named_by)} that name it.", where, "D-097")
        groups.append(build(PayGroup, id=group_id, code=code, name=NP, pay_frequency=NP, is_active=NP, provider_extensions={}))
    return groups if groups or isinstance(listed, list) else listed


def _deduction_codes(ctx: Ctx, tenant: str, client: str, items: list[dict]) -> list[DeductionCode]:
    entries = []
    for index, item in enumerate(items):
        code = item.get("id")  # row: getClientCodes clientCodes.deductionCode[].id
        if is_blank(code):
            continue
        where = f"deduction_codes[{len(entries)}]"
        kind = item.get("type")  # row: getClientCodes clientCodes.deductionCode[].type
        listed = not is_blank(kind) and code_entry(PROVIDER, "prismhr.deduction_type", str(kind).strip()) is not None
        handled = {"id", "description", "type", "calculationMethod", "formW2Box", "formW2Code"}
        entries.append(build(
            DeductionCode,
            id=_id(tenant, EntityType.DEDUCTION_CODE, client, str(code).strip()),
            code=str(code).strip(),
            name=ctx.text(item.get("description")),  # row: getClientCodes clientCodes.deductionCode[].description
            category=ctx.coded("prismhr.deduction_type", kind, f"{where}.category", column="category"),
            tax_treatment=ctx.coded("prismhr.deduction_type", kind, f"{where}.tax_treatment", column="tax_treatment"),
            is_catch_up=str(kind).strip() in CATCH_UP_TYPES if listed else NP,
            calc_method=ctx.coded("prismhr.deduction_calc_method", item.get("calculationMethod"), f"{where}.calc_method"),  # row: getClientCodes clientCodes.deductionCode[].calculationMethod
            w2_box=ctx.text(item.get("formW2Box")),  # row: getClientCodes clientCodes.deductionCode[].formW2Box
            w2_code=ctx.text(item.get("formW2Code")),  # row: getClientCodes clientCodes.deductionCode[].formW2Code
            is_active=NP,  # only an obsolete date is sent (table notes, D-036)
            # row: getClientCodes clientCodes.deductionCode[].client401kCatchUp; clientCodes.deductionCode[].*
            provider_extensions=entry_extensions(PROVIDER, f"getClientCodes:clientCodes.deductionCode[{index}]", item, handled),
        ))
    return entries


def _earning_codes(ctx: Ctx, tenant: str, client: str, items: list[dict]) -> list[EarningCode]:
    entries = []
    for index, item in enumerate(items):
        code = item.get("id")  # row: getClientCodes clientCodes.payCode[].id
        if is_blank(code):
            continue
        where = f"earning_codes[{len(entries)}]"
        handled = {"id", "payDescription", "payClass", "compensationType", "rateClass", "payReason", "w2FormBox", "w2FormCode"}
        entries.append(build(
            EarningCode,
            id=_id(tenant, EntityType.EARNING_CODE, client, str(code).strip()),
            code=str(code).strip(),
            name=ctx.text(item.get("payDescription")),  # row: getClientCodes clientCodes.payCode[].payDescription
            pay_class=ctx.coded("prismhr.pay_class", item.get("payClass"), f"{where}.pay_class"),  # row: getClientCodes clientCodes.payCode[].payClass
            is_cash=_is_cash(ctx, item.get("compensationType"), f"{where}.is_cash"),  # row: getClientCodes clientCodes.payCode[].compensationType
            rate_class=ctx.coded("prismhr.rate_class", item.get("rateClass"), f"{where}.rate_class"),  # row: getClientCodes clientCodes.payCode[].rateClass
            quantity_type=ctx.coded("prismhr.pay_reason", item.get("payReason"), f"{where}.quantity_type"),  # row: getClientCodes clientCodes.payCode[].payReason
            w2_box=ctx.text(item.get("w2FormBox")),  # row: getClientCodes clientCodes.payCode[].w2FormBox
            w2_code=ctx.text(item.get("w2FormCode")),  # row: getClientCodes clientCodes.payCode[].w2FormCode
            is_active=NP,  # only an obsolete date is sent (table notes, D-036)
            # row: getClientCodes clientCodes.payCode[].*
            provider_extensions=entry_extensions(PROVIDER, f"getClientCodes:clientCodes.payCode[{index}]", item, handled),
        ))
    return entries


def _is_cash(ctx: Ctx, raw: Any, field: str) -> Any:
    """compensationType C (cash) true, N (non-cash) false; anything else unknown (table row)."""
    if is_blank(raw):
        return NP
    value = str(raw).strip().upper()
    if value in ("C", "N"):
        return value == "C"
    ctx.diag(DiagnosticCode.UNKNOWN_CODE, Severity.WARNING, f"Compensation type {value!r} is not documented.", field)
    return NP

