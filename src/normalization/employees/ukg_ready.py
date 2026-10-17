"""UKG Ready employees: one Employee per account (one account per EIN, D-039).

Follows ``mappings/data/ukg-ready/employee.json``; each ``row:`` comment (route, then fields) cites
the table row it applies (a test compares the cited rows with the table). The employee list
enumerates accounts; each is read with the detail route and its sub-resources. Durations are
milliseconds (D-028). Every employee route of this provider is classified; nothing is left for
step 4 on these routes.
"""
from typing import Any

from ..canonical.base import SourceRef
from ..canonical.diagnostics import DiagnosticCode, Severity
from ..canonical.employee import (
    Compensation,
    CompensationChange,
    Demographics,
    Email,
    Employee,
    Employment,
    JobAssignment,
    NationalId,
    OrgUnit,
    PersonalContact,
    Phone,
    PtoBalance,
    Qualification,
    RelatedPerson,
    WorkAuthorization,
    WorkContact,
)
from ..canonical.ids import EntityType, Provider, canonical_id
from ..canonical.parsing import DateRole
from ..canonical.parts import PersonalAddress, PersonName, Reference
from .bundle import Bundle
from .common import NA, NP, Ctx, Null, build, from_sources, is_blank, latest, value_of

PROVIDER = "ukg-ready"
TABLE = "employee"  # the mapping table this module applies (pipeline.py)
C = "/v2/companies/{cid}"
ROUTES = {
    "employees": f"{C}/employees",
    "detail": f"{C}/employees/{{aid}}",
    **{name: f"{C}/employees/{{aid}}/{name}" for name in (
        "demographics", "pay-info", "profiles", "compensation/history", "compensation/total", "compensation/additional",
        "contacts", "tax-info", "skills", "training/certifications", "badges", "hr-custom-fields",
        "accrual/1/balances", "accrual/2/balances")},
    "lookup/jobs": f"{C}/lookup/jobs",
    "lookup/employee-types": f"{C}/lookup/employee-types",
    "lookup/pay-types": f"{C}/lookup/pay-types",
    "lookup/pay-period-profiles": f"{C}/lookup/pay-period-profiles",
    "config/cost-centers": f"{C}/config/cost-centers",
}


def _id(tenant: str, entity: EntityType, *parts: Any) -> str:
    return canonical_id(Provider.UKG_READY, tenant, entity, *(str(p) for p in parts))


class Lookups:
    """Company lookups the employee rows join to (D-064, D-065, D-076)."""

    def __init__(self, bundle: Bundle, cid: str) -> None:
        def items(name: str, key: str = "items") -> dict[str, dict] | None:
            response = bundle.get(ROUTES[name], cid=cid)
            if response is None or not response.ok:
                return None
            return {str(item.get("id")): item for item in (response.body or {}).get(key) or []}

        self.jobs = items("lookup/jobs")  # row: lookup/jobs items[].id
        self.employee_types = items("lookup/employee-types")  # row: lookup/employee-types items[].id
        self.pay_types = items("lookup/pay-types")  # row: lookup/pay-types items[].id
        self.pay_period_profiles = items("lookup/pay-period-profiles")
        self.cost_centers: dict[str, Any] = {}
        for response in bundle.all(ROUTES["config/cost-centers"], cid=cid):
            tree = response.params.get("tree_index")
            # row: config/cost-centers cost_centers[].id
            self.cost_centers[tree] = ({str(c.get("id")): c for c in (response.body or {}).get("cost_centers") or []}
                                       if response.ok else response.status)


def normalize_employees(bundle: Bundle) -> list[Employee]:
    records = []
    for listing in bundle.all(ROUTES["employees"]):
        cid = listing.params.get("cid")
        if not cid or not listing.ok:
            continue
        lookups = Lookups(bundle, cid)
        for index, item in enumerate((listing.body or {}).get("employees") or []):
            records.append(_employee(bundle, cid, index, item, lookups))  # row: employees employees[].id
    return records


def _employee(bundle: Bundle, cid: str, list_index: int, list_item: dict, lookups: Lookups) -> Employee:
    tenant = bundle.tenant_id
    ctx = Ctx(PROVIDER)
    aid = str(list_item.get("id"))
    sources = [SourceRef(endpoint=f"GET {ROUTES['employees']}", locator=f"/employees/{list_index}")]

    calls: dict[str, Any] = {}

    def call(name: str, field: str | None) -> Any:
        """The body of an account sub-route, read once; None (with a diagnostic) when missing or refused."""
        if name not in calls:
            calls[name] = fetch(name, field)
        return calls[name]

    def fetch(name: str, field: str | None) -> Any:
        response = bundle.get(ROUTES[name], cid=cid, aid=aid)
        if response is None:
            ctx.unavailable(field, f"{name} is not in the input.")
            return None
        if not response.ok:
            ctx.unavailable(field, f"{name} returned HTTP {response.status}; the data is not available.")
            return None
        sources.append(SourceRef(endpoint=f"GET {ROUTES[name]}", locator=""))
        return response.body if response.body is not None else {}

    detail = call("detail", None) or {}
    dates = detail.get("dates") or {}
    status = ctx.coded("ukg-ready.employee_status", detail.get("status"), "employment.status")  # row: detail status
    history = call("compensation/history", "compensation_history")
    entries = (history or {}).get("compensations") or []
    current = latest(entries, "effective_from")
    pay_info = call("pay-info", "compensation") or {}
    demographics = call("demographics", "demographics")
    ein = (detail.get("ein") or {}).get("id")  # row: detail ein.id
    primary = detail.get("primary_account_id")  # row: detail primary_account_id
    fields: dict[str, Any] = {
        "id": _id(tenant, EntityType.EMPLOYEE, cid, aid),  # row: detail id
        "provider": Provider.UKG_READY,
        "tenant_id": tenant,
        "source_ids": {"companyId": cid, "accountId": aid},
        "company_id": _id(tenant, EntityType.COMPANY, cid),
        "tax_entity_id": NP if is_blank(ein) else _id(tenant, EntityType.TAX_ENTITY, cid, ein),
        "person_ref": NP if is_blank(primary) else str(primary),
        "employee_number": ctx.text(detail.get("employee_id")),  # row: detail employee_id
        "currency": _currency(ctx, entries),
        "name": build(
            PersonName,
            first=ctx.text(detail.get("first_name")),  # row: detail first_name
            middle=ctx.text(detail.get("middle_name")),  # row: detail middle_name
            last=ctx.text(detail.get("last_name")),  # row: detail last_name
            preferred_first=ctx.text(detail.get("nickname")),  # row: detail nickname
            prefix=ctx.text(detail.get("salutation")),  # row: detail salutation
            suffix=ctx.text(detail.get("suffix")),  # row: detail suffix
        ),
        "demographics": _demographics(ctx, dates, demographics) if detail else NP,
        "national_ids": _national_ids(ctx, detail.get("national_id_numbers")) if detail else NP,
        "work_contact": build(WorkContact, email=NP, phone=ctx.text((detail.get("phones") or {}).get("work_phone")),  # row: detail phones.work_phone
                              phone_extension=NP),
        "personal_contact": _personal_contact(ctx, detail) if detail else NP,
        "employment": _employment(ctx, status, dates, pay_info, demographics, lookups, call("tax-info", "employment.worker_type")),
        "employment_history": NP,
        "job": _job(ctx, tenant, cid, detail, pay_info, lookups),
        "job_history": NP,
        "compensation": _compensation(ctx, tenant, cid, current, pay_info, lookups, call("profiles", "compensation.pay_frequency")),
        "compensation_history": NP if history is None else _compensation_history(ctx, entries, current),
        "tax_withholding": NP,  # UKG sends no withholding settings (COVERAGE section 1)
        "work_authorization": _work_authorization(ctx, demographics),
        "pto_balances": _pto(ctx, call("accrual/1/balances", "pto_balances"), call("accrual/2/balances", "pto_balances")),
        "related_people": _related_people(ctx, call("contacts", "related_people")),
        "qualifications": _qualifications(ctx, call("skills", "qualifications"), call("training/certifications", "qualifications")),
    }
    _extensions(ctx, detail, pay_info, demographics, call)
    return build(
        Employee,
        **fields,
        sources=sources,
        diagnostics=ctx.diagnostics,
        provider_extensions=ctx.extensions,
        sensitive_provider_extensions=ctx.sensitive_extensions,
    )


# ---- person ---------------------------------------------------------------------------


def _currency(ctx: Ctx, entries: list[dict]) -> Any:
    # row: compensation/history compensations[].currency
    found = sorted({str(e["currency"]).strip() for e in entries if not is_blank(e.get("currency"))})
    if len(found) > 1:
        ctx.diag(DiagnosticCode.CONFLICTING_SOURCES, Severity.WARNING, f"Compensation entries state different currencies {found}.", "currency")
        return NP
    return found[0] if found else NP


def _demographics(ctx: Ctx, dates: dict, body: Any) -> Demographics:
    body = body or {}
    deceased = ctx.date(dates.get("deceased"), DateRole.EVENT, "demographics.deceased_date")  # row: detail dates.deceased
    return build(
        Demographics,
        birth_date=ctx.date(dates.get("birthday"), DateRole.EVENT, "demographics.birth_date"),  # row: detail dates.birthday
        gender=ctx.coded("ukg-ready.gender", body.get("gender"), "demographics.gender", sensitive=True),  # row: demographics gender
        ethnicity=ctx.coded("ukg-ready.ethnicity", body.get("ethnicity"), "demographics.ethnicity", sensitive=True),  # row: demographics ethnicity
        marital_status=NP,
        citizenship=ctx.coded("ukg-ready.citizenship", body.get("citizenship"), "demographics.citizenship", sensitive=True),  # row: demographics citizenship
        preferred_pronouns=NP,
        veteran=NP,
        disability=NP,
        tobacco_user=NP,
        # is_deceased is not sent: true when the date is set, otherwise not provided.
        is_deceased=True if value_of(deceased) is not None else NP,
        deceased_date=deceased,
    )


def _national_ids(ctx: Ctx, items: Any) -> Any:
    if not items:
        return NP
    found = []
    for index, item in enumerate(items):
        where = f"national_ids[{index}]"
        id_type = ctx.coded("ukg-ready.national_id_type", item.get("type"), f"{where}.type")  # row: detail national_id_numbers[].type
        primary = ctx.flag(item.get("primary"), f"{where}.is_primary")  # row: detail national_id_numbers[].primary
        if str(item.get("type")) == "NO_ID_NEEDED" and is_blank(item.get("value")):
            found.append(build(NationalId, type=id_type, value=NA, value_last4=NA, is_primary=primary))
            continue
        # row: detail national_id_numbers[].value
        entry = ctx.national_id(NationalId, item.get("value"), id_type, where, is_primary=primary)
        if not isinstance(entry, Null):
            found.append(entry)
    return found


def _address(ctx: Ctx, block: dict, kind: str) -> Any:
    return build(
        PersonalAddress,
        type=kind,
        line1=ctx.text(block.get("address_line_1"), sensitive=True),
        line2=ctx.text(block.get("address_line_2"), sensitive=True),
        city=ctx.text(block.get("city")),
        county=NP,
        state=ctx.text(block.get("state_code")),
        postal_code=ctx.text(block.get("zip"), sensitive=True),
        country=ctx.text(block.get("country")),
    )


def _personal_contact(ctx: Ctx, detail: dict) -> PersonalContact:
    # row: detail address.address_line_1; address.address_line_2; address.city; address.state_code; address.zip; address.country
    addresses = [_address(ctx, detail.get("address") or {}, "home")] if detail.get("address") else []
    if detail.get("use_separate_mailing_address") is True and detail.get("mailing_address"):
        # row: detail mailing_address.address_line_1; mailing_address.address_line_2; mailing_address.city
        # row: detail mailing_address.state_code; mailing_address.zip; mailing_address.country
        addresses.append(_address(ctx, detail["mailing_address"], "mailing"))
    phones_block = detail.get("phones") or {}
    preferred = str(phones_block.get("preferred_phone") or "").strip().upper()  # row: detail phones.preferred_phone
    phones = []
    # row: detail phones.cell_phone; phones.home_phone
    for key, kind, marker in (("cell_phone", "mobile", "CELL"), ("home_phone", "home", "HOME")):
        number = ctx.text(phones_block.get(key), sensitive=True)
        if number is not NP:
            is_preferred = NP if not preferred else preferred == marker
            phones.append(build(Phone, type=kind, number=number, extension=NP, is_preferred=is_preferred))
    emails = []
    # row: detail primary_email; secondary_email
    for key, primary in (("primary_email", True), ("secondary_email", False)):
        address = ctx.text(detail.get(key), sensitive=True)
        if address is not NP:
            emails.append(build(Email, type="unknown", address=address, is_primary=primary))
    return build(PersonalContact, addresses=addresses, phones=phones, emails=emails)


# ---- employment and job ---------------------------------------------------------------


def _worker_type(ctx: Ctx, tax: Any) -> Any:
    """Worker type from the tax-info flags: _1099 true with W2 false is contractor, W2 true with
    _1099 false is employee, both inferred (D-041); any other combination (both true, both false,
    either absent) is unknown."""
    if tax is None:
        return NP
    flags = tax.get("employee-tax-type") or {}
    w2, contractor = flags.get("W2"), flags.get("_1099")  # row: tax-info employee-tax-type.W2; employee-tax-type._1099
    raw = f"W2={str(w2).lower()};_1099={str(contractor).lower()}"
    if contractor is True and w2 is False:
        value = "contractor"
    elif w2 is True and contractor is False:
        value = "employee"
    else:
        ctx.diag(DiagnosticCode.UNKNOWN_CODE, Severity.WARNING, f"Tax type flags {raw} give no worker type.", "employment.worker_type", "D-041")
        return {"value": "unknown", "raw_code": raw, "raw_label": None, "basis": "unmapped"}
    ctx.diag(DiagnosticCode.INFERRED_MAPPING, Severity.INFO, f"Worker type {value} is inferred from tax type flags {raw}.", "employment.worker_type", "D-041")
    return {"value": value, "raw_code": raw, "raw_label": None, "basis": "inferred"}


def _employment(ctx: Ctx, status: Any, dates: dict, pay_info: dict, demographics: Any, lookups: Lookups, tax: Any) -> Employment:
    hired = ctx.date(dates.get("hired"), DateRole.EVENT, "employment.original_hire_date")  # row: detail dates.hired
    rehired = ctx.date(dates.get("re_hired"), DateRole.EVENT, "employment.rehire_date")  # row: detail dates.re_hired
    type_id = (pay_info.get("employee_type") or {}).get("id")  # row: pay-info employee_type.id
    type_name = (lookups.employee_types or {}).get(str(type_id), {}).get("name")  # row: lookup/employee-types items[].name
    seasonal = (demographics or {}).get("seasonal")  # row: demographics seasonal
    # Termination fields describe the current employment (table notes, D-080): not_applicable when
    # the status is known and not terminated, with a date still sent (the last termination of a
    # rehired account) kept raw. An unknown status cannot rule them out.
    current = status["value"] if isinstance(status, dict) else None
    if current not in (None, "unknown", "terminated"):
        ctx.keep("detail:dates.terminated", dates.get("terminated"))
        termination_date, other = NA, NA
    else:
        termination_date = ctx.date(dates.get("terminated"), DateRole.EVENT, "employment.termination_date")  # row: detail dates.terminated
        other = NP
    return build(
        Employment,
        status=status,
        status_effective_date=NP,
        worker_type=_worker_type(ctx, tax),
        # Company-defined names: only a label that says full or part time is read (D-074, D-099).
        employment_type=ctx.client_type(type_id, "employment.employment_type", type_name),
        is_seasonal=seasonal if isinstance(seasonal, bool) else NP,
        flsa_status=NP,
        original_hire_date=hired,
        hire_date=rehired if value_of(rehired) is not None else hired,
        rehire_date=rehired,
        seniority_date=ctx.date(dates.get("seniority"), DateRole.EVENT, "employment.seniority_date"),  # row: detail dates.seniority
        termination_date=termination_date,
        termination_type=other,
        termination_reason=other,
        eligible_for_rehire=NP,
    )


def _cost_centers(ctx: Ctx, detail: dict, lookups: Lookups) -> list[OrgUnit]:
    units = []
    for item in (detail.get("cost_centers_info") or {}).get("defaults") or []:
        where = f"job.org_units[{len(units)}]"
        tree = str(item.get("index"))  # row: detail cost_centers_info.defaults[].index
        source_id = (item.get("value") or {}).get("id")  # row: detail cost_centers_info.defaults[].value.id
        found = lookups.cost_centers.get(tree)
        center = found.get(str(source_id)) if isinstance(found, dict) else None
        if center is None:
            reason = (f"returned HTTP {found}" if isinstance(found, int) else
                      "is not in the input" if found is None else "does not list this id")
            ctx.unavailable(where, f"The cost center lookup for tree {tree} {reason}; code and name are unknown.", "D-076")
        units.append(build(
            OrgUnit,
            # The tree index is the type's raw_code, so the id keeps its tree (D-076).
            type={"value": "cost_center", "raw_code": tree, "raw_label": None, "basis": "documented"},
            source_id=NP if is_blank(source_id) else str(source_id),
            code=NP if center is None else ctx.text(center.get("payroll_code")),  # row: config/cost-centers cost_centers[].payroll_code
            name=NP if center is None else ctx.text(center.get("name")),  # row: config/cost-centers cost_centers[].name
        ))
    return units


def _job(ctx: Ctx, tenant: str, cid: str, detail: dict, pay_info: dict, lookups: Lookups) -> JobAssignment:
    job_id = (pay_info.get("default_job") or {}).get("id")  # row: pay-info default_job.id
    job = (lookups.jobs or {}).get(str(job_id))
    if not is_blank(job_id) and job is None:
        ctx.unavailable("job.job", f"Job {job_id} is not in lookup/jobs in the input; code and name are unknown.")
    managers = sorted((detail.get("managers") or []), key=lambda m: m.get("index", 99))
    manager = (managers[0].get("empl_ref") or {}).get("account_id") if managers else None  # row: detail managers[].empl_ref.account_id
    for other in managers[1:]:
        ctx.keep(f"detail:managers[{(detail.get('managers') or []).index(other)}].empl_ref.account_id", (other.get("empl_ref") or {}).get("account_id"))
    return build(
        JobAssignment,
        job=NP if is_blank(job_id) else build(
            Reference,
            source_id=str(job_id),
            code=NP if job is None else ctx.text(job.get("payroll_code")),  # row: lookup/jobs items[].payroll_code
            name=NP if job is None else ctx.text(job.get("name")),  # row: lookup/jobs items[].name
        ),
        effective_date=ctx.date(pay_info.get("job_last_changed"), DateRole.EVENT, "job.effective_date"),  # row: pay-info job_last_changed
        org_units=_cost_centers(ctx, detail, lookups),
        work_location_id=NP,  # UKG has no work location source (D-065)
        manager_employee_id=NP if is_blank(manager) else _id(tenant, EntityType.EMPLOYEE, cid, manager),
        supervisor_employee_id=NP,
        eeo_category=ctx.coded("ukg-ready.eeo_classification", pay_info.get("eeo_classification"), "job.eeo_category"),  # row: pay-info eeo_classification
        union_code=ctx.text((pay_info.get("union") or {}).get("id")),  # row: pay-info union.id
        workers_comp_code=ctx.text((pay_info.get("workers_comp_code") or {}).get("external_id")),  # row: pay-info workers_comp_code.external_id
    )


# ---- compensation ---------------------------------------------------------------------


def _pay_frequency(ctx: Ctx, tenant: str, cid: str, profiles: Any, lookups: Lookups) -> tuple[Any, Any]:
    """(pay_frequency, pay_group_id) from the pay period profile link, joined to the company pay
    group's period type (D-041, D-065). The contract allows one link (maxItems 1); several
    break it, so neither value is taken."""
    if profiles is None:
        return NP, NP
    links = profiles.get("pay_period") or []
    if len(links) > 1:
        ctx.diag(DiagnosticCode.CONFLICTING_SOURCES, Severity.WARNING,
                 f"{len(links)} pay period links were sent; the contract allows one.", "compensation.pay_frequency")
        return NP, NP
    link = links[0] if links else None
    if link is None or is_blank(link.get("id")):
        return NP, NP
    group = _id(tenant, EntityType.PAY_GROUP, cid, link["id"])  # row: profiles pay_period[].id
    profile = (lookups.pay_period_profiles or {}).get(str(link["id"]))
    if profile is None:
        return ctx.unavailable("compensation.pay_frequency", f"Pay period profile {link['id']} is not in the input."), group
    period = profile.get("period_type") or {}
    kind, params = period.get("type"), period.get("params") or {}
    raw = f"{kind}:{params.get('num_weeks')}" if kind == "every_n_weeks" else f"{kind}:{params.get('num_days')}" if kind == "every_n_days" else kind
    return ctx.coded("ukg-ready.period_type", raw, "compensation.pay_frequency", label=profile.get("name")), group


def _compensation(ctx: Ctx, tenant: str, cid: str, current: dict | None, pay_info: dict, lookups: Lookups, profiles: Any) -> Compensation:
    frequency, group = _pay_frequency(ctx, tenant, cid, profiles, lookups)
    pay_type_id = (pay_info.get("pay_type") or {}).get("id")  # row: pay-info pay_type.id
    pay_type_name = (lookups.pay_types or {}).get(str(pay_type_id), {}).get("name")  # row: lookup/pay-types items[].name
    if is_blank(pay_type_id):
        pay_type = NP
    elif is_blank(pay_type_name):
        pay_type = ctx.unknown(pay_type_id, "compensation.pay_type", evidence="D-064")
    else:
        pay_type = ctx.coded("ukg-ready.pay_type", pay_type_name, "compensation.pay_type", label=pay_type_name, raw_code=pay_type_id)
    current = current or {}
    hours = ctx.ms_to_hours(current.get("time"), "compensation.standard_hours") if current else NP  # row: compensation/history compensations[].time
    return build(
        Compensation,
        pay_type=pay_type,
        pay_frequency=frequency,
        pay_group_id=group,
        base_rate=ctx.number(current.get("amount"), "compensation.base_rate"),
        base_rate_period=ctx.coded("ukg-ready.amount_period", current.get("amount_period"), "compensation.base_rate_period"),
        hourly_rate=ctx.number(current.get("hourly_pay"), "compensation.hourly_rate"),
        annual_salary=NP,
        per_period_amount=NP,
        standard_hours=hours,
        # row: compensation/history compensations[].time_period
        standard_hours_period=ctx.coded("ukg-ready.time_period", current.get("time_period"), "compensation.standard_hours_period"),
        effective_date=ctx.date(current.get("effective_from"), DateRole.EVENT, "compensation.effective_date"),
        additional_rates=NP,  # compensation/additional stays raw (unit rule, D-036)
    )


def _compensation_history(ctx: Ctx, entries: list[dict], current: dict | None) -> list[CompensationChange]:
    changes = []
    for index, entry in enumerate(entries):
        where, key = f"compensation_history[{index}]", f"compensation/history:compensations[{index}]"
        changes.append(build(
            CompensationChange,
            effective_date=ctx.date(entry.get("effective_from"), DateRole.EVENT, f"{where}.effective_date"),  # row: compensation/history compensations[].effective_from
            pay_type=NP,
            amount=ctx.number(entry.get("amount"), f"{where}.amount"),  # row: compensation/history compensations[].amount
            amount_period=ctx.coded("ukg-ready.amount_period", entry.get("amount_period"), f"{where}.amount_period"),  # row: compensation/history compensations[].amount_period
            hourly_rate=ctx.number(entry.get("hourly_pay"), f"{where}.hourly_rate"),  # row: compensation/history compensations[].hourly_pay
            annual_amount=NP,
            change_amount=NP,
            change_percent=NP,
            reason=NP,
        ))
        if entry is not current:  # history entries have no hours field (table row)
            ctx.keep(f"{key}.time", entry.get("time"))
            ctx.keep(f"{key}.time_period", entry.get("time_period"))
        ctx.keep(f"{key}.num_pp_in_year", entry.get("num_pp_in_year"))  # row: compensation/history compensations[].num_pp_in_year
    return changes


def _work_authorization(ctx: Ctx, demographics: Any) -> Any:
    if demographics is None:
        return NP
    visa = demographics.get("visa") or {}
    return build(
        WorkAuthorization,
        i9_on_file=NP,
        i9_completed=NP,
        i9_completed_date=NP,
        document_expiration_date=ctx.date(visa.get("expiration_date"), DateRole.EVENT, "work_authorization.document_expiration_date"),  # row: demographics visa.expiration_date
        is_nonresident_alien=NP,
        visa_type=ctx.text(visa.get("type"), sensitive=True),  # row: demographics visa.type
    )


# ---- time off, related people, qualifications -----------------------------------------


def _pto(ctx: Ctx, time_off: Any, categories: Any) -> Any:
    if time_off is None and categories is None:
        return NP
    balances = []
    for index, item in enumerate((time_off or {}).get("accrual_balances") or []):
        where, year = f"pto_balances[{len(balances)}]", item.get("accrual_year") or {}
        balances.append(build(
            PtoBalance,
            plan_source_id=ctx.text((item.get("time_off") or {}).get("id")),  # row: accrual/1/balances accrual_balances[].time_off.id
            plan_code=NP,
            plan_name=ctx.text((item.get("time_off") or {}).get("name")),  # row: accrual/1/balances accrual_balances[].time_off.name
            balance=ctx.ms_to_hours(item.get("remaining"), f"{where}.balance"),  # row: accrual/1/balances accrual_balances[].remaining
            accrued_ytd=ctx.ms_to_hours(item.get("accrued"), f"{where}.accrued_ytd"),  # row: accrual/1/balances accrual_balances[].accrued
            used_ytd=ctx.ms_to_hours(item.get("taken"), f"{where}.used_ytd"),  # row: accrual/1/balances accrual_balances[].taken
            carryover=ctx.ms_to_hours(item.get("carry_over"), f"{where}.carryover"),  # row: accrual/1/balances accrual_balances[].carry_over
            as_of_date=ctx.date(item.get("accrued_to"), DateRole.EVENT, f"{where}.as_of_date"),  # row: accrual/1/balances accrual_balances[].accrued_to
            period_start=ctx.date(year.get("start_date"), DateRole.PERIOD_START, f"{where}.period_start"),  # row: accrual/1/balances accrual_balances[].accrual_year.start_date
            period_end=ctx.date(year.get("end_date"), DateRole.PERIOD_END, f"{where}.period_end"),  # row: accrual/1/balances accrual_balances[].accrual_year.end_date
        ))
        handled = {"time_off", "remaining", "accrued", "taken", "carry_over", "accrued_to", "accrual_year"}
        ctx.rest(f"accrual/1/balances:accrual_balances[{index}]", item, handled)  # row: accrual/1/balances accrual_balances[].*
    for index, item in enumerate((categories or {}).get("accrual_balances") or []):
        where, key = f"pto_balances[{len(balances)}]", f"accrual/2/balances:accrual_balances[{index}]"
        category = item.get("category") or {}
        balances.append(build(
            PtoBalance,
            plan_source_id=ctx.text(category.get("id")),  # row: accrual/2/balances accrual_balances[].category.id
            plan_code=NP,
            plan_name=ctx.text(category.get("category_name")),  # row: accrual/2/balances accrual_balances[].category.category_name
            balance=ctx.ms_to_hours((item.get("current_balance") or {}).get("hours"), f"{where}.balance"),  # row: accrual/2/balances accrual_balances[].current_balance.hours
            accrued_ytd=NP,
            used_ytd=NP,
            carryover=ctx.ms_to_hours((item.get("previous_carry_over") or {}).get("hours"), f"{where}.carryover"),  # row: accrual/2/balances accrual_balances[].previous_carry_over.hours
            as_of_date=NP,
            period_start=NP,
            period_end=NP,
        ))
        # row: accrual/2/balances accrual_balances[].current_accrued.hours; accrual_balances[].taken.hours; accrual_balances[].period.*
        # row: accrual/2/balances accrual_balances[].*.days; accrual_balances[].*.hours; accrual_balances[].category.type
        # row: accrual/2/balances accrual_balances[].expiring_date.date
        for name, value in item.items():
            if name == "category":
                ctx.keep(f"{key}.category.type", category.get("type"))
            elif name in ("current_balance", "previous_carry_over") and isinstance(value, dict):
                ctx.rest(f"{key}.{name}", value, {"hours"})
            elif name != "_precision":
                ctx.keep(f"{key}.{name}", value)
    return from_sources(balances, [time_off, categories])


def _related_people(ctx: Ctx, body: Any) -> Any:
    if body is None:
        return NP
    people = []
    for index, item in enumerate(body.get("contacts") or []):
        where, key = f"related_people[{index}]", f"contacts:contacts[{index}]"
        phones = []
        # row: contacts contacts[].work_phone.number; contacts[].home_phone.number; contacts[].cell_phone.number; contacts[].*.primary
        for block, kind in (("work_phone", "work"), ("home_phone", "home"), ("cell_phone", "mobile")):
            phone = item.get(block) or {}
            number = ctx.text(phone.get("number"), sensitive=True)
            if number is not NP:
                phones.append(build(Phone, type=kind, number=number, extension=NP,
                                    is_preferred=ctx.flag(phone.get("primary"), f"{where}.phones[{len(phones)}].is_preferred")))
            ctx.keep(f"{key}.{block}.code", phone.get("code"))  # row: contacts contacts[].*.code
        people.append(build(
            RelatedPerson,
            source_id=ctx.text(item.get("id")),  # row: contacts contacts[].id
            relationship=ctx.coded("ukg-ready.contact_relationship", item.get("relationship"), f"{where}.relationship"),  # row: contacts contacts[].relationship
            name=build(
                PersonName,
                prefix=ctx.text(item.get("salutation")),  # row: contacts contacts[].salutation
                first=ctx.text(item.get("first_name")),  # row: contacts contacts[].first_name
                middle=ctx.text(item.get("middle_name")),  # row: contacts contacts[].middle_name
                last=ctx.text(item.get("last_name")),  # row: contacts contacts[].last_name
                suffix=ctx.text(item.get("name_suffix")),  # row: contacts contacts[].name_suffix
                preferred_first=NP,
            ),
            full_name=NA,
            birth_date=ctx.date(item.get("birthdate"), DateRole.EVENT, f"{where}.birth_date"),  # row: contacts contacts[].birthdate
            gender=NP,
            national_id=NP,
            address=NP,
            phones=phones,
            email=NP,
            is_dependent=ctx.flag(item.get("dependent"), f"{where}.is_dependent"),  # row: contacts contacts[].dependent
            is_emergency_contact=ctx.flag(item.get("emergency"), f"{where}.is_emergency_contact"),  # row: contacts contacts[].emergency
            is_beneficiary=ctx.flag(item.get("beneficiary"), f"{where}.is_beneficiary"),  # row: contacts contacts[].beneficiary
            is_active=ctx.flag(item.get("active"), f"{where}.is_active"),  # row: contacts contacts[].active
        ))
        # row: contacts contacts[].primary; contacts[].emergency_notif; contacts[].is_in_any_benefit_plan; contacts[].account_id
        for name in ("primary", "emergency_notif", "is_in_any_benefit_plan", "account_id"):
            ctx.keep(f"{key}.{name}", item.get(name))
        ctx.keep(f"{key}.comments", item.get("comments"), sensitive=True)  # row: contacts contacts[].comments
    return people


def _qualifications(ctx: Ctx, skills: Any, training: Any) -> Any:
    if skills is None and training is None:
        return NP
    found = []
    for index, item in enumerate((skills or {}).get("employee_skills") or []):
        where = f"qualifications[{len(found)}]"
        found.append(build(
            Qualification, type="skill",
            source_id=ctx.text((item.get("skill") or {}).get("id")),  # row: skills employee_skills[].skill.id
            code=NP, name=NP,
            level=ctx.text(item.get("level")),  # row: skills employee_skills[].level
            institution=NP, completed_date=NP, expiration_date=NP,
            years_experience=ctx.number(item.get("years"), f"{where}.years_experience"),  # row: skills employee_skills[].years
        ))
        ctx.keep(f"skills:employee_skills[{index}].primary", item.get("primary"))  # row: skills employee_skills[].primary
    for index, item in enumerate((training or {}).get("employee_training_course_history") or []):
        where, key = f"qualifications[{len(found)}]", f"training/certifications:employee_training_course_history[{index}]"
        found.append(build(
            Qualification, type="training",
            source_id=NP, code=NP,
            name=ctx.text(item.get("course")),  # row: training/certifications employee_training_course_history[].course
            level=NP, institution=NP,
            completed_date=ctx.date(item.get("current_completed_date"), DateRole.EVENT, f"{where}.completed_date"),  # row: training/certifications employee_training_course_history[].current_completed_date
            expiration_date=ctx.date(item.get("expires_on"), DateRole.PERIOD_END, f"{where}.expiration_date"),  # row: training/certifications employee_training_course_history[].expires_on
            years_experience=NP,
        ))
        # row: training/certifications employee_training_course_history[].description; employee_training_course_history[].is_expired
        # row: training/certifications employee_training_course_history[].is_schedulable
        for name in ("description", "is_expired", "is_schedulable"):
            ctx.keep(f"{key}.{name}", item.get(name))
    return from_sources(found, [skills, training])


# ---- extensions ------------------------------------------------------------------------

DETAIL_MAPPED = {"id", "employee_id", "first_name", "middle_name", "last_name", "nickname", "salutation", "suffix", "status",
                 "national_id_numbers", "primary_account_id", "ein", "address", "mailing_address", "phones", "primary_email",
                 "secondary_email", "managers", "cost_centers_info", "dates", "hardware_settings", "account_extra_fields",
                 "time_entry_extra_fields", "first_screen", "locale", "managed_cost_centers_settings"}
DETAIL_SENSITIVE = {"social_security", "social_insurance", "national_insurance", "bsn"}
DETAIL_EXCLUDED = {"photo_href", "ein_name", "_links"}
ADDRESS_MAPPED = {"address_line_1", "address_line_2", "city", "state_code", "zip", "country"}


def _extensions(ctx: Ctx, detail: dict, pay_info: dict, demographics: Any, call) -> None:
    # row: detail external_id; username; isPhotoUploaded; use_separate_mailing_address; *
    # row: detail social_security; social_insurance; national_insurance; bsn
    ctx.rest("detail:", detail, DETAIL_MAPPED, DETAIL_SENSITIVE, DETAIL_EXCLUDED)
    for block in ("address", "mailing_address"):
        # row: detail *.address_line_3; *.number; *.number_addition; *.state
        ctx.rest(f"detail:{block}", detail.get(block), ADDRESS_MAPPED, {"address_line_3", "number", "number_addition"})
    # row: detail phones.*_country_id; phones.*_country_code
    ctx.rest("detail:phones", detail.get("phones"), {"cell_phone", "home_phone", "work_phone", "preferred_phone"})
    dates = detail.get("dates") or {}
    # row: detail dates.started; dates.*; dates.custom_dates[].*
    ctx.rest("detail:dates", dates, {"hired", "re_hired", "terminated", "seniority", "birthday", "deceased"})
    for name in ("account_extra_fields", "time_entry_extra_fields"):  # row: detail account_extra_fields[].**; time_entry_extra_fields[].*
        ctx.keep(f"detail:{name}", detail.get(name))
    ctx.keep("detail:hardware_settings.in_touch.security_level", ((detail.get("hardware_settings") or {}).get("in_touch") or {}).get("security_level"))  # row: detail hardware_settings.in_touch.security_level
    for name in ("first_screen", "locale"):  # row: detail *.id
        ctx.keep(f"detail:{name}.id", (detail.get(name) or {}).get("id"))
    ctx.keep("detail:managed_cost_centers_settings", detail.get("managed_cost_centers_settings"))  # row: detail managed_cost_centers_settings.allow_save_others_cost_centers
    ctx.keep("detail:cost_centers_info.limits", (detail.get("cost_centers_info") or {}).get("limits"))  # row: detail cost_centers_info.limits[].**
    if demographics:
        visa = demographics.get("visa") or {}
        ctx.keep("demographics:visa.number", visa.get("number"), sensitive=True)  # row: demographics visa.number
        # row: demographics eye_color; height; full_time_student; referral.id; recruiter.*
        ctx.rest("demographics:", demographics, {"gender", "ethnicity", "citizenship", "seasonal", "visa"}, {"eye_color", "height"})
    # row: pay-info job_change_reason_code.display_name; standard_work_day; bank_account_number; pay_grade.**; *; shift_premium.id
    # row: pay-info gl_codes[].*; ttoc[].*
    pay_handled = {"default_job", "job_last_changed", "employee_type", "pay_type", "eeo_classification", "workers_comp_code", "union"}
    ctx.rest("pay-info:", pay_info, pay_handled, {"bank_account_number"})
    profiles = call("profiles", None) or {}
    # row: profiles pay_period[].effective_from; **
    for index, link in enumerate(profiles.get("pay_period") or []):
        ctx.keep(f"profiles:pay_period[{index}].effective_from", link.get("effective_from"))
    ctx.rest("profiles:", profiles, {"pay_period"})
    total = call("compensation/total", None) or {}
    for index, item in enumerate(total.get("total_compensations") or []):  # row: compensation/total total_compensations[].*
        ctx.rest(f"compensation/total:total_compensations[{index}]", item, excluded={"account"})
    additional = call("compensation/additional", None) or {}
    for index, item in enumerate(additional.get("additional_compensations") or []):  # row: compensation/additional additional_compensations[].**
        ctx.rest(f"compensation/additional:additional_compensations[{index}]", item, excluded={"account", "_links"})
    tax = call("tax-info", None) or {}
    ctx.keep("tax-info:employee-tax-type.DRAW", (tax.get("employee-tax-type") or {}).get("DRAW"))  # row: tax-info employee-tax-type.DRAW
    ctx.keep("tax-info:fein", tax.get("fein"), sensitive=True)  # row: tax-info fein
    ctx.rest("tax-info:", tax, {"employee-tax-type", "fein"})  # row: tax-info *
    for index, badge in enumerate((call("badges", None) or {}).get("badges") or []):
        # row: badges badges[].badge_number; badges[].short_id; badges[].*
        ctx.rest(f"badges:badges[{index}]", badge, sensitive={"badge_number", "short_id"}, excluded={"pin"})
    custom = call("hr-custom-fields", None) or {}
    ctx.keep("hr-custom-fields:hr_custom_fields", custom.get("hr_custom_fields"))  # row: hr-custom-fields hr_custom_fields[].*


normalize = normalize_employees  # pipeline entry point (pipeline.py)
