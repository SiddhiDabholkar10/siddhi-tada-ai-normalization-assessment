"""isolved companies: one Company per legal, the client as parent (D-034).

Follows ``mappings/data/isolved/company.json``. Ids: company and tax entity from the legal id
(D-042), pay groups and work locations from (legal, id), as the employee adapter builds them
(D-080). Deduction and earning codes come from the client pay item catalog, given to every legal
of the client, with ids from (legal, catalog id) (D-066).
"""
from typing import Any

from ...canonical.company import Company, DeductionCode, EarningCode, PayGroup, TaxEntity, WorkLocation
from ...canonical.diagnostics import DiagnosticCode, Severity
from ...canonical.ids import EntityType, Provider, canonical_id
from ...canonical.parts import PostalAddress, Reference
from ...employees.bundle import Bundle
from ...employees.common import NP, Ctx, build, is_blank
from ..common import entry_extensions, source

PROVIDER = "isolved"
TABLE = "company"
API = "/api/clients/{clientId}/legals/{legalId}"
ROUTES = {
    "clients": "/api/clients",
    "legals": "/api/clients/{clientId}/legals",
    "miscellaneousFields": f"{API}/miscellaneousFields",
    "payItems": "/api/clients/{clientId}/payItems",
}
LEGAL_HANDLED = {"id", "legalName", "dbaName", "legalCode", "status", "federalEIN", "legalAddress", "client", "logoData",
                 "services", "compensationPlans", "workersComps", "links", "payGroups", "workLocations"}


def _id(tenant: str, entity: EntityType, *parts: Any) -> str:
    return canonical_id(Provider.ISOLVED, tenant, entity, *(str(p) for p in parts))


def without_links(value: Any) -> Any:
    """A copy without navigation links (excluded in every isolved table)."""
    if isinstance(value, dict):
        return {k: without_links(v) for k, v in value.items() if k != "links"}
    if isinstance(value, list):
        return [without_links(v) for v in value]
    return value


def normalize(bundle: Bundle) -> list[Company]:
    clients = []
    for page in bundle.all(ROUTES["clients"]):
        if page.ok:
            # row: clients results[].id
            clients += [str(item.get("id")) for item in (page.body or {}).get("results") or [] if not is_blank(item.get("id"))]
    records = []
    for client in dict.fromkeys(clients):
        response = bundle.get(ROUTES["legals"], clientId=client)
        if response is None or not response.ok:
            continue
        catalog = bundle.get(ROUTES["payItems"], clientId=client)
        for index, legal in enumerate(response.body or []):
            records.append(_company(bundle, client, index, legal, catalog))
    return records


def _company(bundle: Bundle, client: str, index: int, legal: dict, catalog: Any) -> Company:
    tenant, ctx = bundle.tenant_id, Ctx(PROVIDER)
    legal_id = str(legal.get("id"))  # row: legals [].id
    key = f"legals:[{index}]"
    sources = [source(ROUTES["legals"], f"/{index}")]
    address = legal.get("legalAddress") or {}
    parent = legal.get("client") or {}
    legal_name = ctx.text(legal.get("legalName"))  # row: legals [].legalName
    fields: dict[str, Any] = {
        "id": _id(tenant, EntityType.COMPANY, legal_id),
        "provider": Provider.ISOLVED,
        "tenant_id": tenant,
        "source_ids": {"clientId": client, "legalId": legal_id},
        "legal_name": legal_name,
        "display_name": ctx.text(legal.get("dbaName")),  # row: legals [].dbaName
        "company_code": ctx.text(legal.get("legalCode")),  # row: legals [].legalCode
        "status": ctx.coded("isolved.legal_status", legal.get("status"), "status"),  # row: legals [].status
        "status_date": NP,  # not sent (table row)
        "address": build(
            PostalAddress,
            type="mailing",
            line1=ctx.text(address.get("streetAddress1")),  # row: legals [].legalAddress.streetAddress1
            line2=ctx.text(address.get("streetAddress2")),  # row: legals [].legalAddress.streetAddress2
            city=ctx.text(address.get("city")),  # row: legals [].legalAddress.city
            county=NP,
            state=ctx.text(address.get("state")),  # row: legals [].legalAddress.state
            postal_code=ctx.text(address.get("zipCode")),  # row: legals [].legalAddress.zipCode
            country=NP,
        ) if address else NP,
        "phone": ctx.text(address.get("phoneNumber")),  # row: legals [].legalAddress.phoneNumber
        "parent": build(
            Reference,
            source_id=ctx.text(parent.get("id")),  # row: legals [].client.id
            code=ctx.text(parent.get("clientCode")),  # row: legals [].client.clientCode
            name=ctx.text(parent.get("clientName")),  # row: legals [].client.clientName
        ) if parent else NP,
        "tax_entities": [build(
            TaxEntity,
            id=_id(tenant, EntityType.TAX_ENTITY, legal_id),
            name=legal_name,
            ein=ctx.text(legal.get("federalEIN"), "tax_entities[0].ein", sensitive=True),  # row: legals [].federalEIN
            country=NP,
        )],
        "pay_groups": _pay_groups(ctx, tenant, legal_id, key, legal.get("payGroups") or []),
        "work_locations": _locations(ctx, tenant, legal_id, key, legal.get("workLocations") or []),
    }
    if catalog is None or not catalog.ok:
        message = "The client pay item catalog is not in the input or was refused: the company's codes are unknown."
        fields["deduction_codes"] = ctx.unavailable("deduction_codes", message, "D-066")
        fields["earning_codes"] = ctx.unavailable("earning_codes", message, "D-066")
    else:
        sources.append(source(ROUTES["payItems"]))
        fields["deduction_codes"], fields["earning_codes"] = _catalog(ctx, tenant, legal_id, catalog.body or [])
    ctx.keep(f"{key}.legalAddress.addressDescription", address.get("addressDescription"))  # row: legals [].legalAddress.addressDescription
    # row: legals [].services[].*; [].compensationPlans[].*; [].workersComps[].**
    for name in ("services", "compensationPlans", "workersComps"):
        ctx.keep(f"{key}.{name}", without_links(legal.get(name)))
    ctx.rest(key, legal, LEGAL_HANDLED)  # row: legals [].*
    misc = bundle.get(ROUTES["miscellaneousFields"], clientId=client, legalId=legal_id)
    if misc is not None and misc.ok:
        sources.append(source(ROUTES["miscellaneousFields"]))
        for row, item in enumerate(misc.body or []):
            ctx.rest(f"miscellaneousFields:[{row}]", item, excluded={"links"})  # row: miscellaneousFields [].*
    return build(
        Company,
        **fields,
        sources=sources,
        diagnostics=ctx.diagnostics,
        provider_extensions=ctx.extensions,
        sensitive_provider_extensions=ctx.sensitive_extensions,
    )


def _negated(ctx: Ctx, raw: Any, field: str) -> Any:
    flag = ctx.flag(raw, field)
    return (not flag) if isinstance(flag, bool) else flag


def _pay_groups(ctx: Ctx, tenant: str, legal: str, key: str, items: list[dict]) -> list[PayGroup]:
    groups = []
    for index, item in enumerate(items):
        where = f"pay_groups[{len(groups)}]"
        handled = {"id", "payGroupName", "payFrequency", "isInactive", "legal", "links"}
        groups.append(build(
            PayGroup,
            id=_id(tenant, EntityType.PAY_GROUP, legal, item.get("id")),  # row: legals [].payGroups[].id
            code=NP,  # pay groups have no code (table row)
            name=ctx.text(item.get("payGroupName")),  # row: legals [].payGroups[].payGroupName
            pay_frequency=ctx.coded("isolved.pay_group_frequency", item.get("payFrequency"), f"{where}.pay_frequency"),  # row: legals [].payGroups[].payFrequency
            is_active=_negated(ctx, item.get("isInactive"), f"{where}.is_active"),  # row: legals [].payGroups[].isInactive
            # row: legals [].payGroups[].**
            provider_extensions=entry_extensions(PROVIDER, f"{key}.payGroups[{index}]", without_links(item), handled),
        ))
    return groups


def _locations(ctx: Ctx, tenant: str, legal: str, key: str, items: list[dict]) -> list[WorkLocation]:
    locations = []
    for index, item in enumerate(items):
        where = f"work_locations[{len(locations)}]"
        handled = {"id", "workLocationCode", "workLocationDescription", "address1", "address2", "city", "state", "zipCode",
                   "isInactive", "links"}
        locations.append(build(
            WorkLocation,
            id=_id(tenant, EntityType.WORK_LOCATION, legal, item.get("id")),  # row: legals [].workLocations[].id
            code=ctx.text(item.get("workLocationCode")),  # row: legals [].workLocations[].workLocationCode
            name=ctx.text(item.get("workLocationDescription")),  # row: legals [].workLocations[].workLocationDescription
            address=build(
                PostalAddress,
                type="work",
                line1=ctx.text(item.get("address1")),  # row: legals [].workLocations[].address1
                line2=ctx.text(item.get("address2")),  # row: legals [].workLocations[].address2
                city=ctx.text(item.get("city")),  # row: legals [].workLocations[].city
                county=NP,
                state=ctx.text(item.get("state")),  # row: legals [].workLocations[].state
                postal_code=ctx.text(item.get("zipCode")),  # row: legals [].workLocations[].zipCode
                country=NP,
            ),
            is_active=_negated(ctx, item.get("isInactive"), f"{where}.is_active"),  # row: legals [].workLocations[].isInactive
            # row: legals [].workLocations[].**
            provider_extensions=entry_extensions(PROVIDER, f"{key}.workLocations[{index}]", without_links(item), handled),
        ))
    return locations


def _catalog(ctx: Ctx, tenant: str, legal: str, items: list[dict]) -> tuple[list[DeductionCode], list[EarningCode]]:
    """Deduction items become deduction codes; Earning and Memo Calc items earning codes (D-066)."""
    deductions: list[DeductionCode] = []
    earnings: list[EarningCode] = []
    for index, item in enumerate(items):
        kind = str(item.get("payItemType") or "").strip()  # row: payItems [].payItemType
        common = {
            "code": ctx.text(item.get("code")),  # row: payItems [].code
            "name": ctx.text(item.get("title")),  # row: payItems [].title
            "w2_box": NP,
            "w2_code": NP,
        }
        key = f"payItems:[{index}]"
        handled = {"id", "code", "title", "isInactive", "payItemType", "links"}
        if kind == "Deduction":
            where = f"deduction_codes[{len(deductions)}]"
            benefit = item.get("systemBenefitType")  # row: payItems [].systemBenefitType
            deductions.append(build(
                DeductionCode,
                id=_id(tenant, EntityType.DEDUCTION_CODE, legal, item.get("id")),  # row: payItems [].id
                **common,
                category=ctx.coded("isolved.system_benefit_type", benefit, f"{where}.category", column="category"),
                tax_treatment=ctx.coded("isolved.system_benefit_type", benefit, f"{where}.tax_treatment", column="tax_treatment"),
                is_catch_up=NP,
                calc_method=NP,
                is_active=_negated(ctx, item.get("isInactive"), f"{where}.is_active"),  # row: payItems [].isInactive
                # row: payItems [].systemPayItemType; [].**
                provider_extensions=entry_extensions(PROVIDER, key, without_links(item), handled | {"systemBenefitType"}),
            ))
        elif kind in ("Earning", "Memo Calc"):
            where = f"earning_codes[{len(earnings)}]"
            earnings.append(build(
                EarningCode,
                id=_id(tenant, EntityType.EARNING_CODE, legal, item.get("id")),
                **common,
                pay_class=ctx.coded("isolved.pay_item_type", kind, f"{where}.pay_class", column="pay_class"),
                is_cash=NP,
                rate_class=NP,
                quantity_type=NP,
                is_active=_negated(ctx, item.get("isInactive"), f"{where}.is_active"),
                provider_extensions=entry_extensions(PROVIDER, key, without_links(item), handled),
            ))
        else:
            ctx.diag(DiagnosticCode.UNKNOWN_CODE, Severity.WARNING,
                     f"Pay item type {kind!r} is neither Deduction nor Earning nor Memo Calc; the item is kept raw.", None, "D-066")
            ctx.keep(key, without_links(item))
    return deductions, earnings

