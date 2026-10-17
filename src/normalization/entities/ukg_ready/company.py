"""UKG Ready companies: one Company per company id (cid); there is no company resource (D-029).

Follows ``mappings/data/ukg-ready/company.json``. The company's own fields are not provided and
carry source_unavailable. Owned entries: tax entities, one per EIN id, from ``lookup/eins`` plus
the EIN ids that payrolls and employees name (D-029, D-094: live, the 2nd EIN is named by 24
payrolls and 13 employees but listed by neither EIN lookup); an id the lookup omits is built from
the fields those records send and carries ``reference_only``. Deduction and earning codes, pay
groups (pay period profiles, D-065); ids from (cid, lookup id), as the employee adapter builds
them (D-080). Work locations have no source (D-065). Codes carry no type (D-031).
"""
from typing import Any

from ...canonical.company import Company, DeductionCode, EarningCode, PayGroup, TaxEntity
from ...canonical.diagnostics import DiagnosticCode, Severity
from ...canonical.ids import EntityType, Provider, canonical_id
from ...employees.bundle import Bundle
from ...employees.common import NP, Ctx, build, is_blank
from ..common import entry_extensions, source

PROVIDER = "ukg-ready"
TABLE = "company"
C = "/v2/companies/{cid}"
ROUTES = {name: f"{C}/{name}" for name in ("lookup/eins", "lookup/deduction-codes", "lookup/earning-codes", "lookup/pay-period-profiles")}
ROUTES |= {"payrolls": f"{C}/payrolls", "detail": f"{C}/employees/{{aid}}"}  # EIN ids named by records (D-094)
LIST_OF = {"tax_entities": "lookup/eins", "deduction_codes": "lookup/deduction-codes", "earning_codes": "lookup/earning-codes",
           "pay_groups": "lookup/pay-period-profiles"}


def _id(tenant: str, entity: EntityType, *parts: Any) -> str:
    return canonical_id(Provider.UKG_READY, tenant, entity, *(str(p) for p in parts))


def normalize(bundle: Bundle) -> list[Company]:
    cids = sorted({r.params["cid"] for route in ROUTES.values() for r in bundle.all(route) if r.params.get("cid")})
    return [_company(bundle, cid) for cid in cids]


def _company(bundle: Bundle, cid: str) -> Company:
    tenant, ctx = bundle.tenant_id, Ctx(PROVIDER)
    sources = []
    ctx.unavailable(None, "UKG Ready has no company resource: name, code, status, address and parent are not provided.", "D-029")
    lists: dict[str, Any] = {}
    for field, name in LIST_OF.items():
        response = bundle.get(ROUTES[name], cid=cid)
        if response is None or not response.ok:
            status = "is not in the input" if response is None else f"returned HTTP {response.status}"
            lists[field] = ctx.unavailable(field, f"{name} {status}; the list is unknown.")
            continue
        sources.append(source(ROUTES[name]))
        items = list(enumerate((response.body or {}).get("items") or []))
        lists[field] = BUILDERS[field](ctx, tenant, cid, items)
    lists["tax_entities"] = _with_referenced(ctx, tenant, cid, lists["tax_entities"], _referenced(bundle, cid))
    return build(
        Company,
        id=_id(tenant, EntityType.COMPANY, cid),
        provider=Provider.UKG_READY,
        tenant_id=tenant,
        source_ids={"companyId": cid},
        sources=sources or [source(ROUTES["lookup/eins"])],
        legal_name=NP,
        display_name=NP,
        company_code=NP,
        status=NP,
        status_date=NP,
        address=NP,
        phone=NP,
        parent=NP,
        work_locations=NP,  # no source: cost center location_code empty on 71 of 71 (D-065)
        **lists,
        diagnostics=ctx.diagnostics,
        provider_extensions=ctx.extensions,
        sensitive_provider_extensions=ctx.sensitive_extensions,
    )


def _tax_entities(ctx: Ctx, tenant: str, cid: str, items: list) -> list[TaxEntity]:
    return [build(
        TaxEntity,
        id=_id(tenant, EntityType.TAX_ENTITY, cid, item.get("id")),  # row: lookup/eins items[].id
        name=ctx.text(item.get("ein_name")),  # row: lookup/eins items[].ein_name
        ein=ctx.text(item.get("ein_tax_id"), f"tax_entities[{n}].ein", sensitive=True),  # row: lookup/eins items[].ein_tax_id
        country=ctx.text(item.get("ein_country_id")),  # row: lookup/eins items[].ein_country_id
        # row: lookup/eins items[].ein_currency_code
        provider_extensions=entry_extensions(PROVIDER, f"lookup/eins:items[{index}]", item, {"id", "ein_name", "ein_tax_id", "ein_country_id"}),
    ) for n, (index, item) in enumerate(items) if not is_blank(item.get("id"))]


def _referenced(bundle: Bundle, cid: str) -> dict[str, dict[str, Any]]:
    """The EIN ids that payrolls and employee details name, in input order, with the EIN fields
    they send: the payroll list's ``ein`` object first, then the detail's ``ein_name`` (the
    detail sends no tax id or country)."""
    found: dict[str, dict[str, Any]] = {}

    def entry(raw: Any, where: str) -> dict[str, Any] | None:
        if is_blank(raw):
            return None
        item = found.setdefault(str(raw).strip(), {"name": None, "ein": None, "country": None, "named_by": []})
        if where not in item["named_by"]:
            item["named_by"].append(where)
        return item

    for listing in bundle.all(ROUTES["payrolls"], cid=cid):
        payrolls = (listing.body or {}).get("payrolls") if listing.ok and isinstance(listing.body, dict) else None
        for payroll in payrolls if isinstance(payrolls, list) else []:
            ein = payroll.get("ein") if isinstance(payroll, dict) else None
            item = entry(ein.get("id"), "payrolls") if isinstance(ein, dict) else None  # id: payroll table reference row
            if item is None:
                continue
            # row: payrolls payrolls[].ein.ein_name; payrolls[].ein.ein_tax_id; payrolls[].ein.ein_country_id
            for key, name in (("name", "ein_name"), ("ein", "ein_tax_id"), ("country", "ein_country_id")):
                if is_blank(item[key]) and not is_blank(ein.get(name)):
                    item[key] = ein.get(name)
    for detail in bundle.all(ROUTES["detail"], cid=cid):
        body = detail.body if detail.ok and isinstance(detail.body, dict) else {}
        ein = body.get("ein")
        item = entry(ein.get("id"), "employee details") if isinstance(ein, dict) else None  # id: employee table reference row
        if item is not None and is_blank(item["name"]):
            item["name"] = body.get("ein_name")  # row: detail ein_name
    return found


def _with_referenced(ctx: Ctx, tenant: str, cid: str, listed: Any, referenced: dict[str, dict[str, Any]]) -> Any:
    """The lookup's tax entities plus one per EIN id they lack that a record names (D-094).
    Lookup data wins for an id it lists; a referenced entry takes the fields actually sent, others
    stay null, and a reference_only diagnostic names its sources."""
    entities = list(listed) if isinstance(listed, list) else []
    known = {entity.id for entity in entities}
    for ein_id, values in referenced.items():
        entity_id = _id(tenant, EntityType.TAX_ENTITY, cid, ein_id)
        if entity_id in known:
            continue
        where = f"tax_entities[{len(entities)}]"
        ctx.diag(DiagnosticCode.REFERENCE_ONLY, Severity.INFO,
                 f"lookup/eins does not list EIN id {ein_id}; built from the {' and '.join(values['named_by'])} that name it.",
                 where, "D-094")
        entities.append(build(
            TaxEntity,
            id=entity_id,
            name=ctx.text(values["name"]),
            ein=ctx.text(values["ein"], f"{where}.ein", sensitive=True),
            country=ctx.text(values["country"]),
            provider_extensions={},
        ))
    return entities if entities or isinstance(listed, list) else listed


def _deduction_codes(ctx: Ctx, tenant: str, cid: str, items: list) -> list[DeductionCode]:
    return [build(
        DeductionCode,
        id=_id(tenant, EntityType.DEDUCTION_CODE, cid, item.get("id")),  # row: lookup/deduction-codes items[].id
        code=ctx.text(item.get("code")),  # row: lookup/deduction-codes items[].code
        name=ctx.text(item.get("name")),  # row: lookup/deduction-codes items[].name
        category=NP, tax_treatment=NP, is_catch_up=NP, calc_method=NP, w2_box=NP, w2_code=NP, is_active=NP,  # no type (D-031)
        # row: lookup/deduction-codes items[].external_id
        provider_extensions=entry_extensions(PROVIDER, f"lookup/deduction-codes:items[{index}]", item, {"id", "code", "name"}),
    ) for index, item in items if not is_blank(item.get("id"))]


def _earning_codes(ctx: Ctx, tenant: str, cid: str, items: list) -> list[EarningCode]:
    return [build(
        EarningCode,
        id=_id(tenant, EntityType.EARNING_CODE, cid, item.get("id")),  # row: lookup/earning-codes items[].id
        code=ctx.text(item.get("code")),  # row: lookup/earning-codes items[].code
        name=ctx.text(item.get("name")),  # row: lookup/earning-codes items[].name
        pay_class=NP, is_cash=NP, rate_class=NP, quantity_type=NP, w2_box=NP, w2_code=NP, is_active=NP,  # no type (D-031)
        # row: lookup/earning-codes items[].external_id
        provider_extensions=entry_extensions(PROVIDER, f"lookup/earning-codes:items[{index}]", item, {"id", "code", "name"}),
    ) for index, item in items if not is_blank(item.get("id"))]


def _pay_groups(ctx: Ctx, tenant: str, cid: str, items: list) -> list[PayGroup]:
    groups = []
    for index, item in items:
        if is_blank(item.get("id")):
            continue
        where = f"pay_groups[{len(groups)}]"
        period = item.get("period_type") or {}
        params = period.get("params") or {}
        kind = period.get("type")  # row: lookup/pay-period-profiles items[].period_type.type
        if kind == "every_n_weeks":  # row: lookup/pay-period-profiles items[].period_type.params.num_weeks
            raw = f"every_n_weeks:{params.get('num_weeks')}"
        elif kind == "every_n_days":  # row: lookup/pay-period-profiles items[].period_type.params.num_days
            raw = f"every_n_days:{params.get('num_days')}"
        else:
            raw = kind
        key = f"lookup/pay-period-profiles:items[{index}]"
        extensions = entry_extensions(PROVIDER, key, item, {"id", "name", "active", "period_type"})
        # row: lookup/pay-period-profiles items[].description; items[].effective_from; items[].effective_to; items[].is_user_profile
        # row: lookup/pay-period-profiles items[].period_type.params.*
        extensions.update(entry_extensions(PROVIDER, f"{key}.period_type.params", params, {"num_weeks", "num_days"}))
        groups.append(build(
            PayGroup,
            id=_id(tenant, EntityType.PAY_GROUP, cid, item.get("id")),  # row: lookup/pay-period-profiles items[].id
            code=NP,  # profiles have no code (table row)
            name=ctx.text(item.get("name")),  # row: lookup/pay-period-profiles items[].name
            pay_frequency=ctx.coded("ukg-ready.period_type", raw, f"{where}.pay_frequency"),
            is_active=ctx.flag(item.get("active"), f"{where}.is_active"),  # row: lookup/pay-period-profiles items[].active
            provider_extensions=extensions,
        ))
    return groups


BUILDERS = {"tax_entities": _tax_entities, "deduction_codes": _deduction_codes, "earning_codes": _earning_codes,
            "pay_groups": _pay_groups}
