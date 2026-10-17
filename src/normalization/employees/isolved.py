"""isolved employees: one Employee per employee id of a legal (D-039).

Follows ``mappings/data/isolved/employee.json``; each ``row:`` comment (route, then fields) cites the
table row it applies (a test compares the cited rows with the table). The legal employee list is
the main source (paged, D-013); the detail route is read only for what the list does not return,
employeesWithSSN only for the SSN (D-057, D-070). The list's ``directDeposits[]`` is excluded (the
directdeposits route is the deposit source, D-081); nothing is read from it. Legal pay item entries
that are not deductions (Earning, Memo Calc) are kept here (``entities.SENT_TO_EMPLOYEE``, D-088).
"""
import re
from typing import Any

from ..canonical.base import SourceRef
from ..canonical.diagnostics import DiagnosticCode, Severity
from ..canonical.employee import (
    AdditionalRate,
    Compensation,
    CompensationChange,
    Demographics,
    Disability,
    Email,
    Employee,
    Employment,
    EmploymentPeriod,
    JobAssignment,
    NationalId,
    OrgUnit,
    PersonalContact,
    Phone,
    PtoBalance,
    Qualification,
    RelatedPerson,
    TaxWithholding,
    TaxWithholdingSetting,
    VeteranStatus,
    WorkAuthorization,
    WorkContact,
)
from ..canonical.ids import EntityType, Provider, canonical_id
from ..canonical.parsing import DateRole
from ..canonical.parts import PersonalAddress, PersonName, Reference
from ..entities.common import source
from ..entities.isolved.setups import ROUTES as SETUP_ROUTES
from ..entities.isolved.setups import employee_extras
from .bundle import Bundle, Response
from .common import NA, NP, Ctx, Null, build, from_sources, is_blank, latest

PROVIDER = "isolved"
TABLE = "employee"  # the mapping table this module applies (pipeline.py)
API = "/api/clients/{clientId}/legals/{legalId}"
ROUTES = {
    "legals": "/api/clients/{clientId}/legals",
    "employees": f"{API}/employees",
    "employeesWithSSN": f"{API}/employeesWithSSN",
    "detail": f"{API}/employees/{{id}}",
    **{name: f"{API}/employees/{{employeeId}}/{name}" for name in (
        "statuses", "categories", "jobs", "payRates", "salaries", "veteranStatus", "contacts", "accruals", "skills",
        "education", "certifications", "training", "priorEmployment")},
    "i9/status": f"{API}/employees/{{employeeId}}/i9/status",
}
# Routes where a 404 with an empty body means "no records" (D-011); a 404 elsewhere is unknown.
EMPTY_VIA_404 = {"jobs"}
TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")
MIDNIGHT = re.compile(r"^\d{4}-\d{2}-\d{2}T00:00(:00(\.0+)?)?$")


def _id(tenant: str, entity: EntityType, *parts: Any) -> str:
    return canonical_id(Provider.ISOLVED, tenant, entity, *(str(p) for p in parts))


def normalize_employees(bundle: Bundle) -> list[Employee]:
    records = []
    legals: dict[tuple[str, str], dict] = {}
    for response in bundle.all(ROUTES["legals"]):
        for legal in response.body or [] if response.ok else []:
            legals[(response.params.get("clientId"), str(legal.get("id")))] = legal
    pages = [r for r in bundle.all(ROUTES["employees"]) if r.ok]
    # Every employee id of the tenant, by id, for job history managers that carry no legal id.
    tenant_employees = {str(item.get("id")): str(page.params.get("legalId"))
                        for page in pages for item in (page.body or {}).get("results") or []}
    ssn_rows: dict[tuple[str, str], tuple[Response, int, dict]] = {}
    for page in bundle.all(ROUTES["employeesWithSSN"]):
        for index, item in enumerate((page.body or {}).get("results") or [] if page.ok else []):
            ssn_rows[(page.params.get("legalId"), str(item.get("id")))] = (page, index, item)  # row: employeesWithSSN results[].id
    for page in pages:
        client, legal = page.params.get("clientId"), page.params.get("legalId")
        for index, item in enumerate((page.body or {}).get("results") or []):
            records.append(_employee(bundle, client, legal, page, index, item, legals.get((client, legal), {}),
                                     ssn_rows, tenant_employees))
    return records


class Calls:
    """Per-employee sub-route responses, with the 404 rule (D-011) and source lineage."""

    def __init__(self, bundle: Bundle, ctx: Ctx, params: dict, sources: list[SourceRef]) -> None:
        self.bundle, self.ctx, self.params, self.sources = bundle, ctx, params, sources

    def get(self, name: str, field: str) -> Any:
        """The body of sub-route ``name``, [] for "no records", or None (with a diagnostic on
        ``field``) when it is missing or its meaning is unknown."""
        response = self.bundle.get(ROUTES[name], **self.params)
        if response is None:
            self.ctx.unavailable(field, f"{name} is not in the input.")
            return None
        if response.status == 404 and name in EMPTY_VIA_404:
            self.ctx.diag(DiagnosticCode.EMPTY_VIA_404, Severity.INFO, f"{name} reported no records as HTTP 404.", field, "D-011")
            return []
        if not response.ok:
            self.ctx.unavailable(field, f"{name} returned HTTP {response.status}; whether records exist is unknown.", "D-011")
            return None
        self.sources.append(SourceRef(endpoint=f"GET {ROUTES[name]}", locator=""))
        return response.body


def _employee(bundle: Bundle, client: str, legal: str, page: Response, index: int, item: dict, legal_body: dict,
              ssn_rows: dict, tenant_employees: dict) -> Employee:
    tenant = bundle.tenant_id
    ctx = Ctx(PROVIDER)
    employee_id = str(item.get("id"))  # row: employees results[].id
    sources = [SourceRef(endpoint=f"GET {ROUTES['employees']}", locator=f"/results/{index}")]
    calls = Calls(bundle, ctx, {"clientId": client, "legalId": legal, "employeeId": employee_id}, sources)
    base = f"employees:results[{index}]"
    names = item.get("nameAddress") or {}
    personal = item.get("personal") or {}
    status = ctx.coded("isolved.employment_status", item.get("employmentStatus"), "employment.status")  # row: employees results[].employmentStatus
    salaries = calls.get("salaries", "compensation_history")
    in_effect = latest([s for s in salaries or [] if s.get("isInactive") is not True], "effectiveDate")
    detail = bundle.get(ROUTES["detail"], clientId=client, legalId=legal, id=employee_id)
    fields: dict[str, Any] = {
        "id": _id(tenant, EntityType.EMPLOYEE, legal, employee_id),
        "provider": Provider.ISOLVED,
        "tenant_id": tenant,
        "source_ids": {"clientId": client, "legalId": legal, "employeeId": employee_id},
        "company_id": _id(tenant, EntityType.COMPANY, legal),
        # Each legal has one tax entity, built from the legal id (company table notes, D-042).
        "tax_entity_id": _id(tenant, EntityType.TAX_ENTITY, legal),
        "person_ref": NA,  # isolved has no key grouping one person's records (D-039).
        "employee_number": ctx.text(item.get("employeeNumber")),  # row: employees results[].employeeNumber
        "currency": "USD",  # not sent; assumed (CANONICAL_MODEL 1.5)
        "name": build(
            PersonName,
            first=ctx.text(names.get("firstName")),  # row: employees results[].nameAddress.firstName
            middle=ctx.text(names.get("middleName")),  # row: employees results[].nameAddress.middleName
            last=ctx.text(names.get("lastName")),  # row: employees results[].nameAddress.lastName
            prefix=ctx.text(names.get("prefix")),  # row: employees results[].nameAddress.prefix
            suffix=ctx.text(names.get("suffix")),  # row: employees results[].nameAddress.suffix
            preferred_first=ctx.text(names.get("preferredName")),  # row: employees results[].nameAddress.preferredName
        ),
        "demographics": _demographics(ctx, item, names, calls.get("veteranStatus", "demographics.veteran")),
        "national_ids": _national_ids(ctx, legal, employee_id, ssn_rows, sources),
        "work_contact": build(WorkContact, email=NP, phone=ctx.text(personal.get("officePhone")), phone_extension=NP),  # row: employees results[].personal.officePhone
        "personal_contact": _personal_contact(ctx, item, names, personal),
        "employment": _employment(ctx, base, item, status, calls.get("categories", "employment_history")),
        "job": _job(ctx, tenant, legal, base, item, legal_body),
        "compensation": _compensation(ctx, tenant, legal, item, in_effect, calls.get("payRates", "compensation.additional_rates")),
        "tax_withholding": _tax(ctx, base, item.get("taxes") or {}),
        "work_authorization": _work_authorization(ctx, base, item.get("i9Documents") or {}),
    }
    fields["employment_history"] = _employment_history(ctx, calls)
    fields["job_history"] = _job_history(ctx, tenant, calls.get("jobs", "job_history"), tenant_employees)
    fields["compensation_history"] = _compensation_history(ctx, tenant, legal, salaries, in_effect)
    fields["pto_balances"] = _pto(ctx, calls.get("accruals", "pto_balances"))
    fields["related_people"] = _related_people(ctx, calls.get("contacts", "related_people"))
    fields["qualifications"] = _qualifications(ctx, calls)
    _i9_status(ctx, calls.get("i9/status", "work_authorization"))
    # row: priorEmployment [].*
    for row_index, row in enumerate(calls.get("priorEmployment", None) or []):
        ctx.rest(f"priorEmployment:[{row_index}]", row, excluded={"links"}, all_sensitive=True)
    if detail is not None and detail.ok:
        sources.append(SourceRef(endpoint=f"GET {ROUTES['detail']}", locator=""))
        _detail(ctx, detail.body or {})
    _list_extensions(ctx, base, item, names, personal)
    extras = employee_extras(bundle, client, legal, employee_id)  # pay items that are not deductions (D-088)
    if extras:
        sources.append(source(SETUP_ROUTES["legalPayItems"]))
        ctx.extensions.update(extras)
    return build(
        Employee,
        **fields,
        sources=sources,
        diagnostics=ctx.diagnostics,
        provider_extensions=ctx.extensions,
        sensitive_provider_extensions=ctx.sensitive_extensions,
    )


# ---- person ---------------------------------------------------------------------------


def _demographics(ctx: Ctx, item: dict, names: dict, veteran: Any) -> Demographics:
    veteran = veteran or {}
    # The label has no documented values, so it is kept raw, not read as is_veteran.
    ctx.keep("veteranStatus:veteranStatus", veteran.get("veteranStatus"), sensitive=True)  # row: veteranStatus veteranStatus
    return build(
        Demographics,
        birth_date=ctx.date(item.get("birthDate"), DateRole.EVENT, "demographics.birth_date"),  # row: employees results[].birthDate
        gender=ctx.coded("isolved.gender", item.get("gender"), "demographics.gender", sensitive=True),  # row: employees results[].gender
        ethnicity=ctx.coded("isolved.ethnic_origin", item.get("ethnicOrigin"), "demographics.ethnicity", sensitive=True),  # row: employees results[].ethnicOrigin
        marital_status=ctx.coded("isolved.marital_status", item.get("maritalStatus"), "demographics.marital_status", sensitive=True),  # row: employees results[].maritalStatus
        citizenship=ctx.coded("isolved.citizenship", item.get("citizenship"), "demographics.citizenship", sensitive=True),  # row: employees results[].citizenship
        preferred_pronouns=ctx.text(names.get("preferredPronouns")),  # row: employees results[].nameAddress.preferredPronouns
        veteran=build(
            VeteranStatus,
            is_veteran=NP,
            is_protected_veteran=ctx.flag(item.get("protectedVeteran"), "demographics.veteran.is_protected_veteran"),  # row: employees results[].protectedVeteran
            is_recently_separated_veteran=ctx.flag(item.get("isRecentlySeparatedVeteran"), "demographics.veteran.is_recently_separated_veteran"),  # row: employees results[].isRecentlySeparatedVeteran
            is_disabled_veteran=ctx.flag(veteran.get("disabledVeteran"), "demographics.veteran.is_disabled_veteran"),  # row: veteranStatus disabledVeteran
            is_armed_forces_service_medal_veteran=ctx.flag(veteran.get("serviceMedalVeteran"), "demographics.veteran.is_armed_forces_service_medal_veteran"),  # row: veteranStatus serviceMedalVeteran
            # row: veteranStatus activeWartimeOrCampaignBadgeVeteran
            is_active_duty_wartime_or_campaign_badge_veteran=ctx.flag(veteran.get("activeWartimeOrCampaignBadgeVeteran"), "demographics.veteran.is_active_duty_wartime_or_campaign_badge_veteran"),
            not_disclosed=NP,
        ),
        disability=build(
            Disability,
            has_disability=ctx.flag(item.get("disabled"), "demographics.disability.has_disability"),  # row: employees results[].disabled
            description=ctx.text(item.get("disabilityDescription"), sensitive=True),  # row: employees results[].disabilityDescription
            effective_date=ctx.date(item.get("disabledEffectiveDate"), DateRole.EVENT, "demographics.disability.effective_date"),  # row: employees results[].disabledEffectiveDate
            requires_accommodation=ctx.flag(item.get("disabledRequiresAccomodation"), "demographics.disability.requires_accommodation"),  # row: employees results[].disabledRequiresAccomodation
        ),
        tobacco_user=ctx.flag(item.get("tobaccoUse"), "demographics.tobacco_user"),  # row: employees results[].tobaccoUse
        is_deceased=NP,
        deceased_date=NP,
    )


def _national_ids(ctx: Ctx, legal: str, employee_id: str, ssn_rows: dict, sources: list[SourceRef]) -> Any:
    found = ssn_rows.get((legal, employee_id))
    if found is None:
        return ctx.unavailable("national_ids", "The employee is not in employeesWithSSN in the input (D-057).")
    page, index, row = found
    sources.append(SourceRef(endpoint=f"GET {ROUTES['employeesWithSSN']}", locator=f"/results/{index}"))
    raw_type = row.get("idType")  # row: employeesWithSSN results[].idType
    if is_blank(raw_type):
        ctx.diag(DiagnosticCode.INFERRED_MAPPING, Severity.INFO, "No id type is sent; the SSN field holds an SSN (inferred).", "national_ids[0].type")
        id_type = {"value": "ssn", "raw_code": "ssn", "raw_label": None, "basis": "inferred"}  # raw_code: the source field (CANONICAL_MODEL 1.7)
    else:
        id_type = ctx.coded("isolved.id_type", raw_type, "national_ids[0].type")
    entry = ctx.national_id(NationalId, row.get("ssn"), id_type, "national_ids[0]", is_primary=NP)  # row: employeesWithSSN results[].ssn
    return NP if isinstance(entry, Null) else [entry]


def _address(ctx: Ctx, block: dict, kind: str, country: Any) -> Any:
    lines = ("address1", "address2", "city", "state", "zipCode")
    if all(is_blank(block.get(key)) for key in lines):
        return None
    return build(
        PersonalAddress,
        type=kind,
        line1=ctx.text(block.get("address1"), sensitive=True),
        line2=ctx.text(block.get("address2"), sensitive=True),
        city=ctx.text(block.get("city")),
        county=NP,
        state=ctx.text(block.get("state")),
        postal_code=ctx.text(block.get("zipCode"), sensitive=True),
        country=country,
    )


def _personal_contact(ctx: Ctx, item: dict, names: dict, personal: dict) -> PersonalContact:
    override = item.get("overrideAddress") or {}
    found = [
        # row: employees results[].nameAddress.address1; results[].nameAddress.address2; results[].nameAddress.city
        # row: employees results[].nameAddress.state; results[].nameAddress.zipCode
        _address(ctx, names, "home", NP),
        # row: employees results[].overrideAddress.address1; results[].overrideAddress.address2; results[].overrideAddress.city
        # row: employees results[].overrideAddress.state; results[].overrideAddress.zipCode; results[].overrideAddress.country
        _address(ctx, override, "tax_form", ctx.text(override.get("country"))),
    ]
    phones = []
    # row: employees results[].personal.homePhone; results[].personal.mobilePhone; results[].personal.faxNumber
    for key, kind in (("homePhone", "home"), ("mobilePhone", "mobile"), ("faxNumber", "fax")):
        number = ctx.text(personal.get(key), sensitive=True)
        if number is not NP:
            phones.append(build(Phone, type=kind, number=number, extension=NP, is_preferred=NP))
    emails = []
    # row: employees results[].personal.personalEmailAddress; results[].emailAddress
    for raw, kind in ((personal.get("personalEmailAddress"), "personal"), (item.get("emailAddress"), "unknown")):
        address = ctx.text(raw, sensitive=True)
        if address is not NP:
            emails.append(build(Email, type=kind, address=address, is_primary=NP))
    return build(PersonalContact, addresses=[a for a in found if a is not None], phones=phones, emails=emails)


# ---- employment and job ---------------------------------------------------------------


def _employment(ctx: Ctx, base: str, item: dict, status: Any, categories: Any) -> Employment:
    code = item.get("employmentCategoryCode")  # row: employees results[].employmentCategoryCode
    label = None
    for entry in categories or []:  # raw_label from the categories route (same code)
        category = entry.get("employmentCategory") or {}
        if not is_blank(code) and category.get("code") == code:
            label = category.get("description")
    # Termination fields describe the current employment (table notes, D-080): for an employee whose
    # status is known and not terminated they are not_applicable, and values still sent (the last
    # termination of a rehired employee) stay raw. An unknown status cannot rule them out.
    current = status["value"] if isinstance(status, dict) else None
    if current not in (None, "unknown", "terminated"):
        for name in ("terminationDate", "terminationType", "terminationReason"):
            ctx.keep(f"{base}.{name}", item.get(name))
        termination = {"termination_date": NA, "termination_type": NA, "termination_reason": NA}
    else:
        termination = {
            "termination_date": ctx.date(item.get("terminationDate"), DateRole.EVENT, "employment.termination_date"),  # row: employees results[].terminationDate
            "termination_type": ctx.coded("isolved.termination_type", item.get("terminationType"), "employment.termination_type"),  # row: employees results[].terminationType
            "termination_reason": ctx.text(item.get("terminationReason")),  # row: employees results[].terminationReason
        }
    return build(
        Employment,
        status=status,
        status_effective_date=ctx.date(item.get("statusDate"), DateRole.EVENT, "employment.status_effective_date"),  # row: employees results[].statusDate
        worker_type=ctx.coded("isolved.pay_type", item.get("payType"), "employment.worker_type", column="worker_type"),
        employment_type=ctx.client_type(code, "employment.employment_type", label, table="isolved.employment_category"),
        is_seasonal=ctx.flag(item.get("jobIsSeasonal"), "employment.is_seasonal"),  # row: employees results[].jobIsSeasonal
        flsa_status=ctx.coded("isolved.flsa_exempt", item.get("jobFLSAExempt"), "employment.flsa_status"),  # row: employees results[].jobFLSAExempt
        original_hire_date=ctx.date(item.get("originalHireDate"), DateRole.EVENT, "employment.original_hire_date"),  # row: employees results[].originalHireDate
        hire_date=ctx.date(item.get("hireDate"), DateRole.EVENT, "employment.hire_date"),  # row: employees results[].hireDate
        rehire_date=ctx.date(item.get("rehireDate"), DateRole.EVENT, "employment.rehire_date"),  # row: employees results[].rehireDate
        seniority_date=ctx.date(item.get("adjustedServiceDate"), DateRole.EVENT, "employment.seniority_date"),  # row: employees results[].adjustedServiceDate
        **termination,
        eligible_for_rehire=ctx.flag(item.get("eligibleForRehire"), "employment.eligible_for_rehire"),  # row: employees results[].eligibleForRehire
    )


def _org_units(ctx: Ctx, where: str, units: list[tuple[Any, Any, Any]]) -> list[OrgUnit]:
    """Org units from (client-defined title, value, name): the title is the type's raw_code,
    value unknown (table notes, D-074)."""
    out = []
    for title, value, name in units:
        if is_blank(value):
            continue
        out.append(build(
            OrgUnit,
            type=ctx.unknown(title, f"{where}.org_units[{len(out)}].type") if not is_blank(title) else {
                "value": "unknown", "raw_code": "", "raw_label": None, "basis": "unmapped"},
            source_id=NP,
            code=str(value).strip(),
            name=ctx.text(name),
        ))
    return out


def _person_ref(tenant: str, block: Any) -> Any:
    block = block or {}
    if is_blank(block.get("id")):
        return NP
    if is_blank(block.get("legalId")):
        return NP
    return _id(tenant, EntityType.EMPLOYEE, block["legalId"], block["id"])


def _job(ctx: Ctx, tenant: str, legal: str, base: str, item: dict, legal_body: dict) -> JobAssignment:
    location = item.get("workLocation")  # row: employees results[].workLocation
    location_id: Any = NP
    if not is_blank(location):
        matches = [w for w in legal_body.get("workLocations") or [] if w.get("workLocationCode") == location]
        if matches:
            location_id = _id(tenant, EntityType.WORK_LOCATION, legal, matches[0].get("id"))
        else:
            location_id = ctx.unavailable("job.work_location_id", f"Work location code {location!r} is not among the legal's work locations in the input.")
            ctx.keep(f"{base}.workLocation", location)
    job = NP if all(is_blank(item.get(k)) for k in ("jobId", "jobCode", "jobTitle")) else build(
        Reference,
        source_id=ctx.text(item.get("jobId")),  # row: employees results[].jobId
        code=ctx.text(item.get("jobCode")),  # row: employees results[].jobCode
        name=ctx.text(item.get("jobTitle")),  # row: employees results[].jobTitle
    )
    # row: employees results[].organizations[].title; results[].organizations[].value; results[].organizations[].valueDescription
    units = [(o.get("title"), o.get("value"), o.get("valueDescription")) for o in item.get("organizations") or []]
    return build(
        JobAssignment,
        job=job,
        effective_date=ctx.date(item.get("jobEffectiveDate"), DateRole.EVENT, "job.effective_date"),  # row: employees results[].jobEffectiveDate
        org_units=_org_units(ctx, "job", units),
        work_location_id=location_id,
        # row: employees results[].assignedManager.id; results[].assignedManager.legalId
        manager_employee_id=_person_ref(tenant, item.get("assignedManager")),
        # row: employees results[].assignedSupervisor.id; results[].assignedSupervisor.legalId
        supervisor_employee_id=_person_ref(tenant, item.get("assignedSupervisor")),
        eeo_category=ctx.coded("isolved.eeo_category", item.get("jobEeoCategory"), "job.eeo_category"),  # row: employees results[].jobEeoCategory
        union_code=NP,
        workers_comp_code=ctx.text(item.get("workersCompCode")),  # row: employees results[].workersCompCode
    )


def _employment_history(ctx: Ctx, calls: Calls) -> Any:
    statuses = calls.get("statuses", "employment_history")
    categories = calls.bundle.get(ROUTES["categories"], **calls.params)
    categories = categories.body if categories is not None and categories.ok else None
    if statuses is None and categories is None:
        return NP
    periods = []
    for index, row in enumerate(statuses or []):
        where = f"employment_history[{len(periods)}]"
        periods.append(build(
            EmploymentPeriod,
            employment_id=ctx.text(row.get("employeeEmploymentId")),  # row: statuses [].employeeEmploymentId
            status=ctx.coded("isolved.employment_status", row.get("clientEmploymentStatusDescription"), f"{where}.status"),  # row: statuses [].clientEmploymentStatusDescription
            employment_type=NP,
            effective_date=ctx.date(row.get("effectiveDate"), DateRole.EVENT, f"{where}.effective_date"),  # row: statuses [].effectiveDate
            end_date=ctx.date(row.get("endDate"), DateRole.PERIOD_END, f"{where}.end_date", blank=NA),  # row: statuses [].endDate
            reason=ctx.text(row.get("changeReason")),  # row: statuses [].changeReason
        ))
        ctx.keep(f"statuses:[{index}].statusBeginNotes", row.get("statusBeginNotes"), sensitive=True)  # row: statuses [].statusBeginNotes
        ctx.keep(f"statuses:[{index}].isImpliedStatus", row.get("isImpliedStatus"))  # row: statuses [].isImpliedStatus
    for index, row in enumerate(categories or []):
        where = f"employment_history[{len(periods)}]"
        category = row.get("employmentCategory") or {}
        periods.append(build(
            EmploymentPeriod,
            employment_id=ctx.text(row.get("employmentId")),  # row: categories [].employmentId
            status=NP,
            # row: categories [].employmentCategory.code; [].employmentCategory.description
            employment_type=ctx.client_type(category.get("code"), f"{where}.employment_type", category.get("description"), table="isolved.employment_category"),
            effective_date=ctx.date(row.get("effectiveDate"), DateRole.EVENT, f"{where}.effective_date"),  # row: categories [].effectiveDate
            end_date=NP,
            reason=ctx.text((row.get("changeReason") or {}).get("description")),  # row: categories [].changeReason.description
        ))
        # row: categories [].*
        ctx.rest(f"categories:[{index}]", row, {"employmentId", "employmentCategory", "effectiveDate", "changeReason"}, excluded={"id", "links"})
    return periods


def _job_history(ctx: Ctx, tenant: str, jobs: Any, tenant_employees: dict) -> Any:
    if jobs is None:
        return NP
    entries = []
    for index, row in enumerate(jobs):
        where, key = f"job_history[{index}]", f"jobs:[{index}]"
        job = row.get("clientJob") or {}

        def person(block_name: str) -> Any:
            # No legal id is sent: the person is looked up among the tenant's employees by id (D-045).
            raw = (row.get(block_name) or {}).get("id")
            if is_blank(raw):
                return NP
            legal = tenant_employees.get(str(raw))
            if legal is None:
                ctx.keep(f"{key}.{block_name}.id", raw)
                return ctx.unavailable(f"{where}.{block_name}_employee_id", f"Job {block_name} {raw} is not among the employees in the input, so its legal is unknown.", "D-045")
            return _id(tenant, EntityType.EMPLOYEE, legal, raw)

        units = []
        for org in row.get("organizations") or []:
            field = org.get("clientOrganizationField") or {}
            value = org.get("organizationValue")  # row: jobs [].organizations[].organizationValue
            # row: jobs [].organizations[].clientOrganizationField.lookups[].description
            name = next((lookup.get("description") for lookup in field.get("lookups") or [] if lookup.get("code") == value), None)
            units.append((field.get("title"), value, name))  # row: jobs [].organizations[].clientOrganizationField.title
        entries.append(build(
            JobAssignment,
            job=build(
                Reference,
                source_id=ctx.text(job.get("id")),  # row: jobs [].clientJob.id
                code=ctx.text(job.get("jobCode")),  # row: jobs [].clientJob.jobCode
                name=ctx.text(job.get("jobTitle")),  # row: jobs [].clientJob.jobTitle
            ) if job else NP,
            effective_date=ctx.date(row.get("effectiveDate"), DateRole.EVENT, f"{where}.effective_date"),  # row: jobs [].effectiveDate
            org_units=_org_units(ctx, where, units),
            work_location_id=NP,
            manager_employee_id=person("manager"),  # row: jobs [].manager.id
            supervisor_employee_id=person("supervisor"),  # row: jobs [].supervisor.id
            eeo_category=ctx.coded("isolved.eeo_category", job.get("eeoCategory"), f"{where}.eeo_category"),  # row: jobs [].clientJob.eeoCategory
            union_code=NP,
            workers_comp_code=ctx.text((row.get("workersComp") or {}).get("code")),  # row: jobs [].workersComp.code
        ))
        ctx.keep(f"{key}.comments", row.get("comments"), sensitive=True)  # row: jobs [].comments
        ctx.keep(f"{key}.changeReason", _without_links(row.get("changeReason")))  # row: jobs [].changeReason.*; [].changeReason.changeReasonType.*
        handled = {"effectiveDate", "clientJob", "manager", "supervisor", "organizations", "workersComp", "comments", "changeReason"}
        ctx.rest(key, _without_links(row), handled, excluded={"id"})  # row: jobs [].**
    return entries


def _without_links(value: Any) -> Any:
    """A copy without navigation links (excluded in every table)."""
    if isinstance(value, dict):
        return {k: _without_links(v) for k, v in value.items() if k != "links"}
    if isinstance(value, list):
        return [_without_links(v) for v in value]
    return value


# ---- compensation and tax -------------------------------------------------------------


def _compensation(ctx: Ctx, tenant: str, legal: str, item: dict, in_effect: dict | None, pay_rates: Any) -> Compensation:
    hours = ctx.number(item.get("normalHours"), "compensation.standard_hours")  # row: employees results[].normalHours
    if in_effect is not None:
        frequency = in_effect.get("frequency") or {}
        pay_frequency = ctx.coded("isolved.salary_frequency", frequency.get("id"), "compensation.pay_frequency",  # row: salaries [].frequency.id
                                  label=frequency.get("description"))  # row: salaries [].frequency.description
        group = (in_effect.get("payGroup") or {}).get("id")  # row: salaries [].payGroup.id
        pay_group = NP if is_blank(group) else _id(tenant, EntityType.PAY_GROUP, legal, group)
    else:
        pay_frequency = pay_group = NP
    rates: Any = NP
    if pay_rates is not None:
        rates = []
        for index, row in enumerate(pay_rates):
            rates.append(build(
                AdditionalRate,
                code=ctx.text(row.get("payRateId")),  # row: payRates [].payRateId
                name=ctx.text(row.get("rateDescription")),  # row: payRates [].rateDescription
                amount=ctx.number(row.get("rateValue"), f"compensation.additional_rates[{index}].amount"),  # row: payRates [].rateValue
                period=NP,
            ))
            ctx.keep(f"payRates:[{index}].laborRates", row.get("laborRates"))  # row: payRates [].laborRates[].*
    return build(
        Compensation,
        pay_type=ctx.coded("isolved.pay_type", item.get("payType"), "compensation.pay_type", column="pay_type"),  # row: employees results[].payType
        pay_frequency=pay_frequency,
        pay_group_id=pay_group,
        base_rate=NP,
        base_rate_period=NP,
        hourly_rate=ctx.number(item.get("hourlyRate"), "compensation.hourly_rate"),  # row: employees results[].hourlyRate
        annual_salary=ctx.number(item.get("annualSalary"), "compensation.annual_salary"),  # row: employees results[].annualSalary
        per_period_amount=ctx.number(item.get("perPaySalary"), "compensation.per_period_amount"),  # row: employees results[].perPaySalary
        standard_hours=hours,
        standard_hours_period=NP if isinstance(hours, Null) else {"value": "pay_period", "raw_code": "normalHours", "raw_label": None, "basis": "documented"},
        effective_date=ctx.date(item.get("salaryEffectiveDate"), DateRole.EVENT, "compensation.effective_date"),  # row: employees results[].salaryEffectiveDate
        additional_rates=rates,
    )


def _compensation_history(ctx: Ctx, tenant: str, legal: str, salaries: Any, in_effect: dict | None) -> Any:
    if salaries is None:
        return NP
    changes = []
    for index, row in enumerate(salaries):
        where, key = f"compensation_history[{index}]", f"salaries:[{index}]"
        pay_type = row.get("payType") or {}
        amount = ctx.number(row.get("perPaySalary"), f"{where}.amount")  # row: salaries [].perPaySalary
        changes.append(build(
            CompensationChange,
            effective_date=ctx.date(row.get("effectiveDate"), DateRole.EVENT, f"{where}.effective_date"),  # row: salaries [].effectiveDate
            # row: salaries [].payType.id; [].payType.description
            pay_type=ctx.coded("isolved.salary_pay_type", pay_type.get("id"), f"{where}.pay_type", label=pay_type.get("description")),
            amount=amount,
            amount_period=NP if isinstance(amount, Null) else {"value": "pay_period", "raw_code": "perPaySalary", "raw_label": None, "basis": "documented"},
            hourly_rate=ctx.number(row.get("hourlyRate"), f"{where}.hourly_rate"),  # row: salaries [].hourlyRate
            annual_amount=NP,
            change_amount=NP,
            change_percent=NP,
            reason=ctx.text((row.get("changeReason") or {}).get("description")),  # row: salaries [].changeReason.description
        ))
        ctx.keep(f"{key}.comments", row.get("comments"), sensitive=True)  # row: salaries [].comments
        # row: salaries [].**
        handled = {"effectiveDate", "payType", "perPaySalary", "hourlyRate", "changeReason", "comments", "frequency", "payGroup"}
        ctx.rest(key, _without_links(row), handled, excluded={"id"})
        if row is not in_effect:  # the pay group and frequency of entries not in effect stay raw
            ctx.keep(f"{key}.frequency", (row.get("frequency") or {}))
            ctx.keep(f"{key}.payGroup.id", (row.get("payGroup") or {}).get("id"))
    return changes


TAX_MAPPED = {"additionalAmount", "additionalPercent", "additionalIncomeAmount", "deductionExemptionAmount",
              "dependantExemptionAmount", "filingStatus", "isBlocked", "multipleJobsOrSpouseWorks", "primaryExemptions"}


def _setting(ctx: Ctx, block: dict, where: str, level: str, residency: Any, jurisdiction: Any) -> TaxWithholdingSetting:
    # row: employees results[].taxes.federal.additionalAmount; results[].taxes.*State.additionalAmount; results[].taxes.*City.additionalAmount
    # row: employees results[].taxes.federal.additionalPercent; results[].taxes.*State.additionalPercent; results[].taxes.*City.additionalPercent
    # row: employees results[].taxes.federal.additionalIncomeAmount; results[].taxes.*State.additionalIncomeAmount; results[].taxes.*City.additionalIncomeAmount
    # row: employees results[].taxes.federal.deductionExemptionAmount; results[].taxes.*State.deductionExemptionAmount; results[].taxes.*City.deductionExemptionAmount
    # row: employees results[].taxes.federal.dependantExemptionAmount; results[].taxes.*State.dependantExemptionAmount; results[].taxes.*City.dependantExemptionAmount
    # row: employees results[].taxes.federal.filingStatus; results[].taxes.*State.filingStatus; results[].taxes.*City.filingStatus
    # row: employees results[].taxes.federal.isBlocked; results[].taxes.*State.isBlocked; results[].taxes.*City.isBlocked
    # row: employees results[].taxes.federal.multipleJobsOrSpouseWorks; results[].taxes.*State.multipleJobsOrSpouseWorks; results[].taxes.*City.multipleJobsOrSpouseWorks
    # row: employees results[].taxes.federal.primaryExemptions; results[].taxes.*State.primaryExemptions; results[].taxes.*City.primaryExemptions
    return build(
        TaxWithholdingSetting,
        level=level,
        jurisdiction=jurisdiction,
        residency=residency,
        filing_status=ctx.coded("isolved.filing_status", block.get("filingStatus"), f"{where}.filing_status", sensitive=True),
        allowances=ctx.integer(block.get("primaryExemptions"), f"{where}.allowances"),
        additional_amount=ctx.number(block.get("additionalAmount"), f"{where}.additional_amount"),
        additional_percent=ctx.number(block.get("additionalPercent"), f"{where}.additional_percent"),
        is_exempt=NP,  # isolved sends no exempt claim (table notes)
        multiple_jobs=ctx.flag(block.get("multipleJobsOrSpouseWorks"), f"{where}.multiple_jobs"),
        dependents_amount=ctx.number(block.get("dependantExemptionAmount"), f"{where}.dependents_amount"),
        other_income_amount=ctx.number(block.get("additionalIncomeAmount"), f"{where}.other_income_amount"),
        deductions_amount=ctx.number(block.get("deductionExemptionAmount"), f"{where}.deductions_amount"),
        is_blocked=ctx.flag(block.get("isBlocked"), f"{where}.is_blocked"),
    )


def _tax(ctx: Ctx, base: str, taxes: dict) -> TaxWithholding:
    federal = taxes.get("federal")
    states, locals_ = [], []
    for name, residency in (("residentState", "resident"), ("nonResidentState", "non_resident")):
        if isinstance(taxes.get(name), dict):
            # row: employees results[].taxes.*State.taxState
            states.append(_setting(ctx, taxes[name], f"tax_withholding.states[{len(states)}]", "state", residency, ctx.text(taxes[name].get("taxState"))))
    for name, residency in (("residentCity", "resident"), ("nonResidentCity", "non_resident")):
        if isinstance(taxes.get(name), dict):
            # The city's locality is not sent; taxState is the state of the city tax (kept raw).
            locals_.append(_setting(ctx, taxes[name], f"tax_withholding.locals[{len(locals_)}]", "local", residency, NP))
            ctx.keep(f"{base}.taxes.{name}.taxState", taxes[name].get("taxState"), sensitive=True)  # row: employees results[].taxes.*City.taxState
    for name, block in taxes.items():
        if isinstance(block, dict):
            handled = TAX_MAPPED | ({"taxState"} if name != "federal" else set())
            ctx.rest(f"{base}.taxes.{name}", _without_links(block), handled, all_sensitive=True)  # row: employees results[].taxes.**
    return build(
        TaxWithholding,
        federal=_setting(ctx, federal, "tax_withholding.federal", "federal", NA, "US") if isinstance(federal, dict) else NP,
        states=states,
        locals=locals_,
    )


def _work_authorization(ctx: Ctx, base: str, i9: dict) -> WorkAuthorization:
    raw = i9.get("i9CompletedDate")  # row: employees results[].i9Documents.i9CompletedDate
    field = "work_authorization.i9_completed_date"
    if isinstance(raw, str) and TIMESTAMP.match(raw.strip()) and not MIDNIGHT.match(raw.strip()):
        # A timestamp in a field documented as a date: its date part fills the field and the full
        # timestamp is kept (CANONICAL_MODEL 1.6).
        completed_date = ctx.date(raw.strip()[:10], DateRole.EVENT, field)
        ctx.keep(f"{base}.i9Documents.i9CompletedDate", raw, sensitive=True)
    else:
        completed_date = ctx.date(raw, DateRole.EVENT, field)
    return build(
        WorkAuthorization,
        i9_on_file=NP,
        i9_completed=ctx.flag(i9.get("i9Completed"), "work_authorization.i9_completed"),  # row: employees results[].i9Documents.i9Completed
        i9_completed_date=completed_date,
        document_expiration_date=NP,
        is_nonresident_alien=NP,
        visa_type=NP,
    )


def _i9_status(ctx: Ctx, body: Any) -> None:
    if body is None:
        return
    ctx.keep("i9/status:hasSignedI9Form", body.get("hasSignedI9Form"), sensitive=True)  # row: i9/status hasSignedI9Form
    ctx.keep("i9/status:uploadedDocuments", _without_links(body.get("uploadedDocuments")), sensitive=True)  # row: i9/status uploadedDocuments[].*
    ctx.keep("i9/status:isDocumentUploadComplete", body.get("isDocumentUploadComplete"), sensitive=True)  # row: i9/status isDocumentUploadComplete


def _detail(ctx: Ctx, body: dict) -> None:
    """The detail route: only what the list does not return (D-070)."""
    ctx.keep("detail:taxExemptStatus", body.get("taxExemptStatus"), sensitive=True)  # row: detail taxExemptStatus
    for name in ("documentA", "documentB", "documentC"):  # row: detail i9Documents.documentA.*; i9Documents.documentB.*; i9Documents.documentC.*
        document = _without_links((body.get("i9Documents") or {}).get(name))
        if isinstance(document, dict):
            ctx.rest(f"detail:i9Documents.{name}", document, excluded={"documentContent"}, all_sensitive=True)
    ctx.keep("detail:miscDataSets", body.get("miscDataSets"))  # row: detail miscDataSets[].**


# ---- time off, related people, qualifications -----------------------------------------


UNVERIFIED_AMOUNTS = ("currentBalance", "availableBalance", "carryoverBalance", "ytdAccrued", "ytdTaken")


def _pto(ctx: Ctx, accruals: Any) -> Any:
    if accruals is None:
        return NP
    balances = []
    for index, row in enumerate(accruals):
        where = f"pto_balances[{index}]"
        balances.append(build(
            PtoBalance,
            plan_source_id=ctx.text(row.get("planId")),  # row: accruals [].planId
            plan_code=NP,
            plan_name=ctx.text(row.get("planDescription")),  # row: accruals [].planDescription
            balance=NP,
            accrued_ytd=NP,
            used_ytd=NP,
            carryover=NP,
            as_of_date=NP,
            period_start=NP,
            period_end=NP,
        ))
        # row: accruals [].currentBalance; [].availableBalance; [].carryoverBalance; [].ytdAccrued; [].ytdTaken
        if any(not is_blank(row.get(name)) for name in UNVERIFIED_AMOUNTS):
            ctx.diag(DiagnosticCode.UNIT_UNVERIFIED, Severity.WARNING,
                     "Accrual amounts have no documented unit; kept raw in provider_extensions, hours fields not filled.", where, "D-077")
        # row: accruals [].accrualName; [].id; [].currentAccrued; [].currentTaken; [].*
        ctx.rest(f"accruals:[{index}]", _without_links(row), {"planId", "planDescription"})
    return balances


def _related_people(ctx: Ctx, contacts: Any) -> Any:
    if contacts is None:
        return NP
    people = []
    for index, row in enumerate(contacts):
        where, key = f"related_people[{index}]", f"contacts:[{index}]"
        phones = []
        # row: contacts [].homePhone; [].mobilePhone; [].workPhone
        for field, kind in (("homePhone", "home"), ("mobilePhone", "mobile"), ("workPhone", "work")):
            number = ctx.text(row.get(field), sensitive=True)
            if number is not NP:
                phones.append(build(Phone, type=kind, number=number, extension=NP, is_preferred=NP))
        lines = ("address1", "address2", "city", "state", "zipCode")
        address = NP if all(is_blank(row.get(k)) for k in lines) else build(
            PersonalAddress,
            type="mailing",
            line1=ctx.text(row.get("address1"), sensitive=True),  # row: contacts [].address1
            line2=ctx.text(row.get("address2"), sensitive=True),  # row: contacts [].address2
            city=ctx.text(row.get("city")),  # row: contacts [].city
            county=NP,
            state=ctx.text(row.get("state")),  # row: contacts [].state
            postal_code=ctx.text(row.get("zipCode"), sensitive=True),  # row: contacts [].zipCode
            country=NP,
        )
        ssn_type = {"value": "ssn", "raw_code": "ssnUnmasked", "raw_label": None, "basis": "documented"}  # the source field (1.7)
        people.append(build(
            RelatedPerson,
            source_id=ctx.text(row.get("id")),  # row: contacts [].id
            relationship=ctx.coded("isolved.contact_relationship", row.get("relationshipCode"), f"{where}.relationship"),  # row: contacts [].relationshipCode
            name=build(
                PersonName,
                first=ctx.text(row.get("firstName")),  # row: contacts [].firstName
                middle=ctx.text(row.get("middleName")),  # row: contacts [].middleName
                last=ctx.text(row.get("lastName")),  # row: contacts [].lastName
                prefix=ctx.text(row.get("prefix")),  # row: contacts [].prefix
                suffix=ctx.text(row.get("suffix")),  # row: contacts [].suffix
                preferred_first=NP,
            ),
            full_name=NA,
            birth_date=ctx.date(row.get("birthDateUnmasked"), DateRole.EVENT, f"{where}.birth_date"),  # row: contacts [].birthDateUnmasked
            gender=ctx.coded("isolved.contact_gender", row.get("genderCode"), f"{where}.gender", sensitive=True),  # row: contacts [].genderCode
            national_id=ctx.national_id(NationalId, row.get("ssnUnmasked"), ssn_type, f"{where}.national_id", is_primary=NP),  # row: contacts [].ssnUnmasked
            address=address,
            phones=phones,
            email=ctx.text(row.get("emailAddress"), sensitive=True),  # row: contacts [].emailAddress
            is_dependent=ctx.flag(row.get("isDependent"), f"{where}.is_dependent"),  # row: contacts [].isDependent
            is_emergency_contact=ctx.flag(row.get("isEmergencyContact"), f"{where}.is_emergency_contact"),  # row: contacts [].isEmergencyContact
            is_beneficiary=ctx.flag(row.get("isBeneficiary"), f"{where}.is_beneficiary"),  # row: contacts [].isBeneficiary
            is_active=NP,
        ))
        # row: contacts [].ssnAppliedFor; [].maritalStatusCode; [].isDeceased; [].isDisabled; [].isStudent; [].notifyIfArrestedDetained
        for name in ("ssnAppliedFor", "maritalStatusCode", "isDeceased", "isDisabled", "isStudent", "notifyIfArrestedDetained"):
            ctx.keep(f"{key}.{name}", row.get(name), sensitive=True)
        for name in ("useEmployeeAddress", "emergencyCallOrder", "hideForSelfService"):  # row: contacts [].useEmployeeAddress; [].emergencyCallOrder; [].hideForSelfService
            ctx.keep(f"{key}.{name}", row.get(name))
    return people


def _qualifications(ctx: Ctx, calls: Calls) -> Any:
    found: list[Qualification] = []
    bodies = {name: calls.get(name, "qualifications") for name in ("skills", "education", "certifications", "training")}
    if all(body is None for body in bodies.values()):
        return NP
    for index, row in enumerate(bodies["skills"] or []):
        where, key = f"qualifications[{len(found)}]", f"skills:[{index}]"
        found.append(build(
            Qualification, type="skill",
            source_id=ctx.text(row.get("id")),  # row: skills [].id
            code=NP,
            name=ctx.text(row.get("skill")),  # row: skills [].skill
            level=ctx.text(row.get("proficiency")),  # row: skills [].proficiency
            institution=NP,
            completed_date=ctx.date(row.get("dateAttained"), DateRole.EVENT, f"{where}.completed_date"),  # row: skills [].dateAttained
            expiration_date=NP, years_experience=NP,
        ))
        ctx.keep(f"{key}.experience", row.get("experience"))  # row: skills [].experience
        ctx.keep(f"{key}.lastUsed", row.get("lastUsed"))  # row: skills [].lastUsed
        ctx.keep(f"{key}.comments", row.get("comments"), sensitive=True)  # row: skills [].comments
        ctx.keep(f"{key}.miscellaneous", row.get("miscellaneous"), sensitive=True)  # row: skills [].miscellaneous
    for index, row in enumerate(bodies["education"] or []):
        where, key = f"qualifications[{len(found)}]", f"education:[{index}]"
        found.append(build(
            Qualification, type="education",
            source_id=ctx.text(row.get("id")),  # row: education [].id
            code=NP,
            name=ctx.text(row.get("degree")),  # row: education [].degree
            level=NP,
            institution=ctx.text(row.get("school")),  # row: education [].school
            completed_date=ctx.date(row.get("completionDate"), DateRole.EVENT, f"{where}.completed_date"),  # row: education [].completionDate
            expiration_date=NP, years_experience=NP,
        ))
        for name in ("educationType", "major", "minor", "honors", "graduated"):  # row: education [].educationType; [].major; [].minor; [].honors; [].graduated
            ctx.keep(f"{key}.{name}", row.get(name))
        for name in ("gpa", "comments"):  # row: education [].gpa; [].comments
            ctx.keep(f"{key}.{name}", row.get(name), sensitive=True)
    for index, row in enumerate(bodies["certifications"] or []):
        where, key = f"qualifications[{len(found)}]", f"certifications:[{index}]"
        found.append(build(
            Qualification, type="certification",
            source_id=ctx.text(row.get("id")),  # row: certifications [].id
            code=NP,
            name=ctx.text(row.get("certification")),  # row: certifications [].certification
            level=NP,
            institution=ctx.text(row.get("authority")),  # row: certifications [].authority
            completed_date=NP,
            expiration_date=ctx.date(row.get("expirationDate"), DateRole.PERIOD_END, f"{where}.expiration_date"),  # row: certifications [].expirationDate
            years_experience=NP,
        ))
        # row: certifications [].effectiveDate; [].cost; [].reimbursementAmount; [].reimbursementApprovalDate; [].reimbursementDate
        for name in ("effectiveDate", "cost", "reimbursementAmount", "reimbursementApprovalDate", "reimbursementDate"):
            ctx.keep(f"{key}.{name}", row.get(name))
        for name in ("licenseNumber", "comments", "miscellaneous"):  # row: certifications [].licenseNumber; [].comments; [].miscellaneous
            ctx.keep(f"{key}.{name}", row.get(name), sensitive=True)
    for index, row in enumerate(bodies["training"] or []):
        where, key = f"qualifications[{len(found)}]", f"training:[{index}]"
        found.append(build(
            Qualification, type="training",
            source_id=ctx.text(row.get("id")),  # row: training [].id
            code=NP,
            name=ctx.text(row.get("title")),  # row: training [].title
            level=NP, institution=NP, completed_date=NP,
            expiration_date=ctx.date(row.get("expirationDate"), DateRole.PERIOD_END, f"{where}.expiration_date"),  # row: training [].expirationDate
            years_experience=NP,
        ))
        ctx.keep(f"{key}.comments", row.get("comments"), sensitive=True)  # row: training [].comments
        # row: training [].endDate; [].*
        ctx.rest(key, _without_links(row), {"id", "title", "expirationDate", "comments"})
    return from_sources(found, list(bodies.values()))


# ---- extensions of the list item ------------------------------------------------------

LIST_MAPPED = {"id", "employeeNumber", "nameAddress", "personal", "overrideAddress", "emailAddress", "birthDate", "gender",
               "ethnicOrigin", "maritalStatus", "citizenship", "protectedVeteran", "isRecentlySeparatedVeteran", "disabled",
               "disabledEffectiveDate", "disabledRequiresAccomodation", "disabilityDescription", "tobaccoUse",
               "employmentStatus", "statusDate", "employmentCategoryCode", "hireDate", "originalHireDate", "rehireDate",
               "adjustedServiceDate", "terminationDate", "terminationReason", "terminationType", "eligibleForRehire",
               "jobId", "jobCode", "jobTitle", "jobEffectiveDate", "jobEeoCategory", "jobFLSAExempt", "jobIsSeasonal",
               "workersCompCode", "workLocation", "organizations", "assignedManager", "assignedSupervisor", "payType",
               "hourlyRate", "annualSalary", "perPaySalary", "normalHours", "salaryEffectiveDate", "taxes", "i9Documents"}
LIST_SENSITIVE = {"eeoGenderOverride", "militaryStatus", "veteranStatusNotSpecified", "activeDutySeparationDate",
                  "disabilityNotes", "tobaccoUseEffectiveDate", "uniqueId", "timeclockId", "reciprocityRule"}
LIST_EXCLUDED = {"legalCode", "ssn", "idType", "updatedHireDate", "updatedStatusDate", "updatedJobEffectiveDate",
                 "updatedSalaryEffectiveDate", "updatedDisabledEffectiveDate", "workLocationDashDescription", "team",
                 "attachments", "messages", "previousPunchLabors", "profilePicture", "taxExemptStatus", "payGroup",
                 "payRates", "links", "directDeposits"}


def _list_extensions(ctx: Ctx, base: str, item: dict, names: dict, personal: dict) -> None:
    # row: employees results[].nameAddress.residentGeoCode; results[].nameAddress.schoolDistrictCode
    for name in ("residentGeoCode", "schoolDistrictCode"):
        ctx.keep(f"{base}.nameAddress.{name}", names.get(name))
    override = item.get("overrideAddress") or {}
    ctx.keep(f"{base}.overrideAddress.foreignPostalCode", override.get("foreignPostalCode"), sensitive=True)  # row: employees results[].overrideAddress.foreignPostalCode
    # row: employees results[].overrideAddress.foreignStateProvince; results[].overrideAddress.militaryCity; results[].overrideAddress.militaryState
    # row: employees results[].overrideAddress.useForPaychecks; results[].overrideAddress.useForTaxForms
    for name in ("foreignStateProvince", "militaryCity", "militaryState", "useForPaychecks", "useForTaxForms"):
        ctx.keep(f"{base}.overrideAddress.{name}", override.get(name))
    # row: employees results[].eeoGenderOverride; results[].militaryStatus; results[].veteranStatusNotSpecified
    # row: employees results[].activeDutySeparationDate; results[].disabilityNotes; results[].tobaccoUseEffectiveDate
    # row: employees results[].uniqueId; results[].timeclockId; results[].reciprocityRule
    # row: employees results[].employmentCategoryEffectiveDate; results[].employmentCategoryFullTimeEquivalent; results[].acaEmploymentStatus
    # row: employees results[].isPending; results[].enableSelfService; results[].isManager; results[].isSupervisor
    # row: employees results[].isRemoteWorker; results[].timecardPunchStatusDate; results[].timecardPunchStatusIsIn
    # row: employees results[].jobIsUnion; results[].jobGroup; results[].socCode; results[].payFrequency
    # row: employees results[].labors[].*; results[].miscFields[].*; results[].miscDataSets[].**; results[].wotc.*
    ctx.rest(base, _without_links(item), LIST_MAPPED, LIST_SENSITIVE, LIST_EXCLUDED)


normalize = normalize_employees  # pipeline entry point (pipeline.py)
