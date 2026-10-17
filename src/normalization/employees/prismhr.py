"""PrismHR employees: one Employee per (client, employee id) (D-039).

Follows ``mappings/data/prismhr/employee.json``; each ``row:`` comment (route, then fields) cites the
table row it applies (a test compares the cited rows with the table). Not read here: the getEmployee
``directDeposit`` block (DirectDeposit records, ``entities/prismhr/deposits.py``) and
``scheduledDeduction`` (excluded: getScheduledDeductions is the source, D-081). Arrears entries that
match no deduction setup are kept here (``entities.SENT_TO_EMPLOYEE``, D-088).
"""
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
from ..entities.prismhr.setups import employee_extras
from .bundle import Bundle, Response
from .common import NA, NP, Ctx, Null, build, is_blank, value_of

PROVIDER = "prismhr"
TABLE = "employee"  # the mapping table this module applies (pipeline.py)
ROUTES = {
    "getEmployeeList": "/employee/v1/getEmployeeList",
    "getEmployee": "/employee/v1/getEmployee",
    "getAddressInfo": "/employee/v1/getAddressInfo",
    "getHistory": "/employee/v1/getHistory",
    "getPayRateHistory": "/employee/v1/getPayRateHistory",
    "getStatusHistoryForAdjustment": "/employee/v1/getStatusHistoryForAdjustment",
    "getPositionRate": "/employee/v1/getPositionRate",
    "getPaidTimeOff": "/benefits/v1/getPaidTimeOff",
    "getDependents": "/benefits/v1/getDependents",
    "getEmployeeOverrideRates": "/payroll/v1/getEmployeeOverrideRates",
    "getClientCodes": "/clientMaster/v1/getClientCodes",
    "getPayrollSchedule": "/clientMaster/v1/getPayrollSchedule",
}
SSN_TYPE = {"value": "ssn", "raw_code": "ssn", "raw_label": None, "basis": "documented"}


def _id(tenant: str, entity: EntityType, *parts: str) -> str:
    return canonical_id(Provider.PRISMHR, tenant, entity, *parts)


def _ok(response: Response | None) -> bool:
    """PrismHR success is HTTP 200 with errorCode 0 (D-021)."""
    return response is not None and response.ok and str((response.body or {}).get("errorCode", "0")) == "0"


class ClientCodes:
    """Client code tables from getClientCodes (labels and classes, D-064) and the payroll
    schedule letters (D-041 amendment 2)."""

    def __init__(self, codes: dict, schedules: list[dict]) -> None:
        def by(name: str, key: str = "id") -> dict[str, dict]:
            return {str(item.get(key)): item for item in codes.get(name) or [] if not is_blank(item.get(key))}

        self.status = by("statusCode")  # row: getClientCodes clientCodes.statusCode[].id
        self.type = by("typeCode")  # row: getClientCodes clientCodes.typeCode[].id
        self.job = by("jobCode")  # row: getClientCodes clientCodes.jobCode[].id
        self.position = by("positionClass")  # row: getClientCodes clientCodes.positionClass[].id
        self.department = by("departmentCode")  # row: getClientCodes clientCodes.departmentCode[].id
        self.division = by("divisionCode")  # row: getClientCodes clientCodes.divisionCode[].id
        self.project = by("projectCode")  # row: getClientCodes clientCodes.projectCode[].id
        self.reason = by("reasonCode")  # row: getClientCodes clientCodes.reasonCode[].id
        self.ethnic = by("ethnicCode")  # row: getClientCodes clientCodes.ethnicCode[].id
        self.citizenship = by("citizenshipStatusCodes", "code")  # row: getClientCodes clientCodes.citizenshipStatusCodes[].code
        self.relation = by("relationCodes", "code")  # row: getClientCodes clientCodes.relationCodes[].code
        self.skill = by("skillCodes", "code")  # row: getClientCodes clientCodes.skillCodes[].code
        self.schedule = {str(s.get("groupId")): s for s in schedules if not is_blank(s.get("groupId"))}

    @staticmethod
    def field(table: dict, code: Any, name: str) -> Any:
        return (table.get(str(code)) or {}).get(name) if not is_blank(code) else None


def normalize_employees(bundle: Bundle) -> list[Employee]:
    records = []
    for listing in bundle.all(ROUTES["getEmployeeList"]):
        client = listing.params.get("clientId")
        if not client or not _ok(listing):
            continue
        codes_response = bundle.get(ROUTES["getClientCodes"], clientId=client)
        schedule_response = bundle.get(ROUTES["getPayrollSchedule"], clientId=client)
        schedule_body = (schedule_response.body or {}) if _ok(schedule_response) else {}
        codes = ClientCodes(
            (codes_response.body or {}).get("clientCodes") or {} if _ok(codes_response) else {},
            # The demo sends the singular key clientPayrollSchedule (live rename, D-062).
            schedule_body.get("clientPayrollSchedules") or schedule_body.get("clientPayrollSchedule") or [],
        )
        # row: getEmployeeList employeeList.employeeId[]
        for employee_id in (listing.body.get("employeeList") or {}).get("employeeId") or []:
            records.append(_employee(bundle, client, str(employee_id), codes, codes_response is not None and _ok(codes_response)))
    return records


def _employee(bundle: Bundle, client: str, employee_id: str, codes: ClientCodes, have_codes: bool) -> Employee:
    tenant = bundle.tenant_id
    ctx = Ctx(PROVIDER)
    params = {"clientId": client, "employeeId": employee_id}
    sources = [SourceRef(endpoint=f"GET {ROUTES['getEmployeeList']}", locator="/employeeList/employeeId")]
    if not have_codes:
        ctx.unavailable(None, "getClientCodes is not in the input: client code labels and classes are unknown.")

    def call(name: str) -> Any:
        response = bundle.get(ROUTES[name], **params)
        if not _ok(response):
            ctx.unavailable(None, f"{name} is not in the input or did not succeed.", "D-021")
            return None
        sources.append(SourceRef(endpoint=f"GET {ROUTES[name]}", locator=""))
        return response.body

    body = call("getEmployee") or {}
    items = [item for item in body.get("employee") or [] if str(item.get("id")) == employee_id]
    item = items[0] if items else {}
    index = (body.get("employee") or []).index(item) if items else 0
    if items:
        sources[-1] = SourceRef(endpoint=f"GET {ROUTES['getEmployee']}", locator=f"/employee/{index}")
    base = f"getEmployee:employee[{index}]"
    person = item.get("person") or {}
    contact = item.get("contactInformation") or {}
    work = item.get("client") or {}
    pay = item.get("compensation") or {}

    fields: dict[str, Any] = {
        # row: getEmployee employee[].id
        "id": _id(tenant, EntityType.EMPLOYEE, client, employee_id),
        "provider": Provider.PRISMHR,
        "tenant_id": tenant,
        "source_ids": params,
        "company_id": _id(tenant, EntityType.COMPANY, client),
        # The client has one tax entity, built from the client id (company table notes, D-042).
        "tax_entity_id": _id(tenant, EntityType.TAX_ENTITY, client),
        "person_ref": NA,  # PrismHR has no key grouping one person's records (D-039).
        "employee_number": ctx.text(work.get("clientEmployeeId")),  # row: getEmployee employee[].client.clientEmployeeId
        "currency": "USD",  # not sent; assumed (CANONICAL_MODEL 1.5)
    }
    if items:
        fields["name"] = build(
            PersonName,
            first=ctx.text(item.get("firstName")),  # row: getEmployee employee[].firstName
            last=ctx.text(item.get("lastName")),  # row: getEmployee employee[].lastName
            middle=ctx.text(item.get("middleInitial")),  # row: getEmployee employee[].middleInitial
            preferred_first=ctx.text(item.get("preferredName")),  # row: getEmployee employee[].preferredName
            prefix=NP,
            suffix=NP,
        )
        fields["demographics"] = _demographics(ctx, base, person, work, pay, codes)
        fields["national_ids"] = _national_ids(ctx, pay)
        fields["work_contact"] = build(
            WorkContact,
            email=ctx.text(work.get("workEmail")),  # row: getEmployee employee[].client.workEmail
            phone=ctx.text(work.get("workPhone")),  # row: getEmployee employee[].client.workPhone
            phone_extension=ctx.text(work.get("workPhoneExt")),  # row: getEmployee employee[].client.workPhoneExt
        )
        fields["employment"] = _employment(ctx, work, codes)
        fields["job"] = _job(ctx, tenant, client, work, codes)
        fields["compensation"] = _compensation(ctx, tenant, client, pay, codes, call("getEmployeeOverrideRates"))
        fields["tax_withholding"] = _tax(ctx, base, pay)
        fields["work_authorization"] = build(
            WorkAuthorization,
            i9_on_file=ctx.flag(pay.get("formI9Filed"), "work_authorization.i9_on_file"),  # row: getEmployee employee[].compensation.formI9Filed
            is_nonresident_alien=ctx.flag(pay.get("nonResAlien"), "work_authorization.is_nonresident_alien"),  # row: getEmployee employee[].compensation.nonResAlien
        )
        fields["qualifications"] = _qualifications(ctx, base, item.get("skillsAndEducation") or {}, codes)
        _employee_extensions(ctx, base, item, person, contact, work, pay)
    fields["personal_contact"] = _personal_contact(ctx, contact, call("getAddressInfo")) if items else NP
    history = call("getHistory")
    fields["employment_history"] = _employment_history(ctx, call("getStatusHistoryForAdjustment"), history, codes)
    fields["job_history"] = _job_history(ctx, tenant, client, history, codes)
    fields["compensation_history"] = _compensation_history(ctx, call("getPayRateHistory"))
    fields["pto_balances"] = _pto(ctx, call("getPaidTimeOff"))
    fields["related_people"] = _related_people(ctx, base, person, call("getDependents"), codes) if items else NP
    _position_rates(ctx, call("getPositionRate"))
    extras = employee_extras(bundle, client, employee_id)  # arrears matching no setup (D-088)
    if extras:
        sources.append(source("/deductions/v1/getDeductionArrears"))
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


def _yes_no_declined(ctx: Ctx, raw: Any, field: str, key: str) -> Any:
    """Y true, N false, blank not provided; D (declined to answer) not provided with the raw
    answer kept in the sensitive extension (D-076)."""
    if isinstance(raw, str) and raw.strip().upper() == "D":
        ctx.keep(key, raw, sensitive=True)
        return NP
    return ctx.flag(raw, field)


def _demographics(ctx: Ctx, base: str, person: dict, work: dict, pay: dict, codes: ClientCodes) -> Demographics:
    ethnic = person.get("ethnicCode")  # row: getEmployee employee[].person.ethnicCode
    if is_blank(ethnic):
        ethnicity = NP
    elif str(ethnic) in codes.ethnic:
        ethnicity = ctx.coded(
            "prismhr.eeo_ethnic_report_code",
            codes.field(codes.ethnic, ethnic, "reportCode"),  # row: getClientCodes clientCodes.ethnicCode[].reportCode
            "demographics.ethnicity",
            label=codes.field(codes.ethnic, ethnic, "description"),  # row: getClientCodes clientCodes.ethnicCode[].description
            raw_code=ethnic,
            sensitive=True,
        )
    else:
        ethnicity = ctx.unknown(ethnic, "demographics.ethnicity", sensitive=True, evidence="D-064")
    citizenship = pay.get("citizenshipStatus")
    veteran = person.get("veteran")
    deceased = ctx.flag(person.get("deceased"), "demographics.is_deceased")  # row: getEmployee employee[].person.deceased
    deceased_date = ctx.date(person.get("deceasedDate"), DateRole.EVENT, "demographics.deceased_date",  # row: getEmployee employee[].person.deceasedDate
                             blank=NA if deceased is False else NP)
    vet = f"{base}.person"
    return build(
        Demographics,
        birth_date=ctx.date(person.get("birthDate"), DateRole.EVENT, "demographics.birth_date"),  # row: getEmployee employee[].person.birthDate
        gender=ctx.coded("prismhr.gender", person.get("gender"), "demographics.gender", sensitive=True),  # row: getEmployee employee[].person.gender
        ethnicity=ethnicity,
        marital_status=ctx.coded("prismhr.marital_status", person.get("maritalStatus"), "demographics.marital_status", sensitive=True),  # row: getEmployee employee[].person.maritalStatus
        # row: getEmployee employee[].compensation.citizenshipStatus
        citizenship=ctx.coded("prismhr.citizenship_status", citizenship, "demographics.citizenship", sensitive=True,
                              label=codes.field(codes.citizenship, citizenship, "description")),  # row: getClientCodes clientCodes.citizenshipStatusCodes[].description
        preferred_pronouns=ctx.text(work.get("preferredPronoun")),  # row: getEmployee employee[].client.preferredPronoun
        veteran=build(
            VeteranStatus,
            is_veteran=_yes_no_declined(ctx, veteran, "demographics.veteran.is_veteran", f"{vet}.veteran"),  # row: getEmployee employee[].person.veteran
            is_disabled_veteran=_yes_no_declined(ctx, person.get("disabledVet"), "demographics.veteran.is_disabled_veteran", f"{vet}.disabledVet"),  # row: getEmployee employee[].person.disabledVet
            is_protected_veteran=_yes_no_declined(ctx, person.get("otherProtectedVet"), "demographics.veteran.is_protected_veteran", f"{vet}.otherProtectedVet"),  # row: getEmployee employee[].person.otherProtectedVet
            is_active_duty_wartime_or_campaign_badge_veteran=_yes_no_declined(  # row: getEmployee employee[].person.activeDutyBadgeVet
                ctx, person.get("activeDutyBadgeVet"), "demographics.veteran.is_active_duty_wartime_or_campaign_badge_veteran", f"{vet}.activeDutyBadgeVet"),
            is_recently_separated_veteran=_yes_no_declined(  # row: getEmployee employee[].person.recentlySeparatedVet
                ctx, person.get("recentlySeparatedVet"), "demographics.veteran.is_recently_separated_veteran", f"{vet}.recentlySeparatedVet"),
            is_armed_forces_service_medal_veteran=_yes_no_declined(  # row: getEmployee employee[].person.serviceMedalVet
                ctx, person.get("serviceMedalVet"), "demographics.veteran.is_armed_forces_service_medal_veteran", f"{vet}.serviceMedalVet"),
            # D (declined) sets not_disclosed; a Y or N answer was disclosed.
            not_disclosed=True if str(veteran or "").strip().upper() == "D" else (False if not is_blank(veteran) else NP),
        ),
        disability=build(
            Disability,
            has_disability=_yes_no_declined(ctx, person.get("handicapped"), "demographics.disability.has_disability", f"{vet}.handicapped"),  # row: getEmployee employee[].person.handicapped
            description=NP,
            effective_date=NP,
            requires_accommodation=NP,
        ),
        tobacco_user=ctx.flag(person.get("smoker"), "demographics.tobacco_user"),  # row: getEmployee employee[].person.smoker
        is_deceased=deceased,
        deceased_date=deceased_date,
    )


def _national_ids(ctx: Ctx, pay: dict) -> Any:
    # row: getEmployee employee[].compensation.ssn
    entry = ctx.national_id(NationalId, pay.get("ssn"), SSN_TYPE, "national_ids[0]", is_primary=NP)
    return NP if isinstance(entry, Null) else [entry]


def _address(ctx: Ctx, block: dict, kind: str, country: Any = NP) -> Any:
    """One personal address from a getAddressInfo block, or None when the block is empty."""
    lines = ("addressLine1", "addressLine2", "city", "county", "stateAbbr", "zipCode")
    if all(is_blank(block.get(key)) for key in lines):
        return None
    return build(
        PersonalAddress,
        type=kind,
        line1=ctx.text(block.get("addressLine1"), sensitive=True),
        line2=ctx.text(block.get("addressLine2"), sensitive=True),
        city=ctx.text(block.get("city")),
        county=ctx.text(block.get("county")),
        state=ctx.text(block.get("stateAbbr")),
        postal_code=ctx.text(block.get("zipCode"), sensitive=True),
        country=country,
    )


def _personal_contact(ctx: Ctx, contact: dict, address_body: Any) -> PersonalContact:
    addresses: Any = NP
    if address_body is not None:
        info = address_body.get("addressInfo") or {}
        alt = info.get("altAddress") or {}
        international = alt.get("internationalAddress") is True  # row: getAddressInfo addressInfo.altAddress.internationalAddress
        found = [
            # row: getAddressInfo addressInfo.homeAddress.addressLine1; addressInfo.homeAddress.addressLine2; addressInfo.homeAddress.city
            # row: getAddressInfo addressInfo.homeAddress.county; addressInfo.homeAddress.stateAbbr; addressInfo.homeAddress.zipCode
            _address(ctx, info.get("homeAddress") or {}, "home"),
            # row: getAddressInfo addressInfo.w2Address.addressLine1; addressInfo.w2Address.addressLine2; addressInfo.w2Address.city
            # row: getAddressInfo addressInfo.w2Address.county; addressInfo.w2Address.stateAbbr; addressInfo.w2Address.zipCode
            _address(ctx, info.get("w2Address") or {}, "tax_form"),
            # row: getAddressInfo addressInfo.altAddress.addressLine1; addressInfo.altAddress.addressLine2; addressInfo.altAddress.city
            # row: getAddressInfo addressInfo.altAddress.county; addressInfo.altAddress.stateAbbr; addressInfo.altAddress.zipCode
            # row: getAddressInfo addressInfo.altAddress.mailAddressCountry
            _address(ctx, alt, "mailing", ctx.text(alt.get("mailAddressCountry")) if international else NP),
        ]
        addresses = [address for address in found if address is not None]
        for name in ("homeAddress", "w2Address", "altAddress"):
            # row: getAddressInfo addressInfo.*.zipSuffix
            ctx.keep(f"getAddressInfo:addressInfo.{name}.zipSuffix", (info.get(name) or {}).get("zipSuffix"), sensitive=True)
        # row: getAddressInfo addressInfo.homeAddress.unincorporatedResidence
        ctx.keep("getAddressInfo:addressInfo.homeAddress.unincorporatedResidence", (info.get("homeAddress") or {}).get("unincorporatedResidence"))
        ctx.keep("getAddressInfo:addressInfo.altAddress.internationalAddress", alt.get("internationalAddress"))
        ctx.keep("getAddressInfo:addressInfo.homeGeoCode", info.get("homeGeoCode"))  # row: getAddressInfo addressInfo.homeGeoCode
    phones = []
    for key, kind in (("homePhone", "home"), ("mobilePhone", "mobile")):  # row: getEmployee employee[].contactInformation.homePhone; employee[].contactInformation.mobilePhone
        number = ctx.text(contact.get(key), sensitive=True)
        if number is not NP:
            phones.append(build(Phone, type=kind, number=number, extension=NP, is_preferred=NP))
    emails = []
    address = ctx.text(contact.get("emailAddress"), sensitive=True)  # row: getEmployee employee[].contactInformation.emailAddress
    if not isinstance(address, Null):
        emails.append(build(Email, type="personal", address=address, is_primary=NP))
    return build(PersonalContact, addresses=addresses, phones=phones, emails=emails)


# ---- employment and job ---------------------------------------------------------------


def _status(ctx: Ctx, codes: ClientCodes, code: Any, field: str, status_class: Any = None, label: Any = None) -> Any:
    """A client status code: raw_code the code, value from its status class (D-064)."""
    if is_blank(code):
        return NP
    if status_class is None:
        status_class = codes.field(codes.status, code, "statusClass")  # row: getClientCodes clientCodes.statusCode[].statusClass
    if label is None:
        label = codes.field(codes.status, code, "description")  # row: getClientCodes clientCodes.statusCode[].description
    if is_blank(status_class):
        return ctx.unknown(code, field, label, evidence="D-064")
    return ctx.coded("prismhr.employee_status_class", status_class, field, label=label, raw_code=code)


def _type(ctx: Ctx, codes: ClientCodes, code: Any, field: str, type_class: Any = None, label: Any = None) -> Any:
    """A client type code: raw_code the code, value from its type class (D-064, D-074)."""
    if is_blank(code):
        return NP
    if type_class is None:
        type_class = codes.field(codes.type, code, "typeClass")  # row: getClientCodes clientCodes.typeCode[].typeClass
    if label is None:
        label = codes.field(codes.type, code, "description")  # row: getClientCodes clientCodes.typeCode[].description
    if is_blank(type_class):
        return ctx.unknown(code, field, label, evidence="D-064")
    return ctx.coded("prismhr.type_class", type_class, field, label=label, raw_code=code)


def _employment(ctx: Ctx, work: dict, codes: ClientCodes) -> Employment:
    status_class = work.get("statusClass")  # row: getEmployee employee[].client.statusClass
    terminated = str(status_class or "").strip() == "T"
    reason = work.get("termReasonCode")  # row: getEmployee employee[].client.termReasonCode
    status_date = ctx.date(work.get("statusDate"), DateRole.EVENT, "employment.status_effective_date")  # row: getEmployee employee[].client.statusDate
    seasonal = codes.field(codes.type, work.get("employeeType"), "seasonal")  # row: getClientCodes clientCodes.typeCode[].seasonal
    if terminated and not is_blank(reason):
        termination_type = ctx.coded(
            "prismhr.termination_type",
            codes.field(codes.reason, reason, "terminationType"),  # row: getClientCodes clientCodes.reasonCode[].terminationType
            "employment.termination_type",
            label=codes.field(codes.reason, reason, "description"),  # row: getClientCodes clientCodes.reasonCode[].description
        )
    else:
        termination_type = NP if terminated else NA
    return build(
        Employment,
        # row: getEmployee employee[].client.employeeStatus
        status=_status(ctx, codes, work.get("employeeStatus"), "employment.status", status_class=status_class),
        status_effective_date=status_date,
        worker_type=ctx.coded("prismhr.employee_1099", work.get("employee1099"), "employment.worker_type"),  # row: getEmployee employee[].client.employee1099
        # row: getEmployee employee[].client.employeeType; employee[].client.typeClass
        employment_type=_type(ctx, codes, work.get("employeeType"), "employment.employment_type", type_class=work.get("typeClass")),
        is_seasonal=seasonal if isinstance(seasonal, bool) else NP,
        flsa_status=ctx.coded("prismhr.flsa_exempt", work.get("flsaExempt"), "employment.flsa_status"),  # row: getEmployee employee[].client.flsaExempt
        original_hire_date=ctx.date(work.get("firstHireDate"), DateRole.EVENT, "employment.original_hire_date"),  # row: getEmployee employee[].client.firstHireDate
        hire_date=ctx.date(work.get("lastHireDate"), DateRole.EVENT, "employment.hire_date"),  # row: getEmployee employee[].client.lastHireDate
        rehire_date=NP,  # PrismHR sends no rehire date (table notes).
        seniority_date=ctx.date(work.get("seniorityDate"), DateRole.EVENT, "employment.seniority_date"),  # row: getEmployee employee[].client.seniorityDate
        termination_date=value_of(status_date) or NP if terminated else NA,
        termination_type=termination_type,
        termination_reason=ctx.text(reason) if terminated else NA,
        eligible_for_rehire=ctx.flag(work.get("rehireOk"), "employment.eligible_for_rehire"),  # row: getEmployee employee[].client.rehireOk
    )


def _org_unit(ctx: Ctx, kind: str, source_field: str, code: Any, table: dict | None, name_key: str) -> Any:
    """An org unit whose type is documented by the source field (table notes); the field name is
    the type's raw_code. ``table`` labels the code; None when no label table exists."""
    if is_blank(code):
        return None
    return build(
        OrgUnit,
        type={"value": kind, "raw_code": source_field, "raw_label": None, "basis": "documented"},
        source_id=NP,
        code=str(code).strip(),
        name=ctx.text((table.get(str(code)) or {}).get(name_key)) if table is not None else NP,
    )


def _job_reference(ctx: Ctx, codes: ClientCodes, code: Any) -> Any:
    if is_blank(code):
        return NP
    return build(
        Reference,
        source_id=NP,
        code=str(code).strip(),
        name=ctx.text(codes.field(codes.job, code, "jobTitle")),  # row: getClientCodes clientCodes.jobCode[].jobTitle
    )


def _job(ctx: Ctx, tenant: str, client: str, work: dict, codes: ClientCodes) -> JobAssignment:
    job_code = work.get("jobCode")  # row: getEmployee employee[].client.jobCode
    position = codes.field(codes.job, job_code, "jobClass")  # row: getClientCodes clientCodes.jobCode[].jobClass
    eeo = codes.field(codes.position, position, "eeoJobClass")  # row: getClientCodes clientCodes.positionClass[].eeoJobClass
    units = [
        _org_unit(ctx, "department", "homeDepartment", work.get("homeDepartment"), codes.department, "deptName"),  # row: getEmployee employee[].client.homeDepartment
        _org_unit(ctx, "division", "homeDivision", work.get("homeDivision"), codes.division, "divisionName"),  # row: getEmployee employee[].client.homeDivision
        _org_unit(ctx, "project", "projCostCenter", work.get("projCostCenter"), codes.project, "description"),  # row: getEmployee employee[].client.projCostCenter
        _org_unit(ctx, "cost_center", "subCostCenter", work.get("subCostCenter"), None, ""),  # row: getEmployee employee[].client.subCostCenter
    ]
    # Org unit names come from these label columns.
    # row: getClientCodes clientCodes.departmentCode[].deptName; clientCodes.divisionCode[].divisionName
    # row: getClientCodes clientCodes.projectCode[].description
    location, manager = work.get("homeLocation"), work.get("manager")
    return build(
        JobAssignment,
        job=_job_reference(ctx, codes, job_code),
        effective_date=ctx.date(work.get("lastJobChangeDate"), DateRole.EVENT, "job.effective_date"),  # row: getEmployee employee[].client.lastJobChangeDate
        org_units=[unit for unit in units if unit is not None],
        work_location_id=NP if is_blank(location) else _id(tenant, EntityType.WORK_LOCATION, client, str(location).strip()),  # row: getEmployee employee[].client.homeLocation
        manager_employee_id=NP if is_blank(manager) else _id(tenant, EntityType.EMPLOYEE, client, str(manager).strip()),  # row: getEmployee employee[].client.manager
        supervisor_employee_id=NP,
        eeo_category=NP if is_blank(eeo) else ctx.unknown(eeo, "job.eeo_category", evidence="D-074"),
        union_code=ctx.text(work.get("unionCode")),  # row: getEmployee employee[].client.unionCode
        workers_comp_code=NP,
    )


def _employment_history(ctx: Ctx, status_body: Any, history_body: Any, codes: ClientCodes) -> Any:
    if status_body is None:
        return NP
    reasons: dict[tuple[str, str], str] = {}
    for record in _history_records(history_body):
        for block in ("statusChange", "leave", "termination"):
            change = record.get(block) or {}
            # row: getHistory historyRecords[].statusChange.reason; historyRecords[].leave.reason; historyRecords[].termination.reason
            if not is_blank(change.get("reason")):
                reasons[(str(record.get("effectiveDate")), str(change.get("employeeStatusCode")))] = change["reason"]
    periods = []
    for index, row in enumerate(status_body.get("statusTypeHistory") or []):
        where = f"employment_history[{index}]"
        status = row.get("status")  # row: getStatusHistoryForAdjustment statusTypeHistory[].status
        periods.append(build(
            EmploymentPeriod,
            employment_id=NP,
            status=_status(ctx, codes, status, f"{where}.status", label=row.get("statusDesc")),  # row: getStatusHistoryForAdjustment statusTypeHistory[].statusDesc
            # row: getStatusHistoryForAdjustment statusTypeHistory[].employeeType; statusTypeHistory[].typeDesc
            employment_type=_type(ctx, codes, row.get("employeeType"), f"{where}.employment_type", label=row.get("typeDesc")),
            effective_date=ctx.date(row.get("effectiveDate"), DateRole.EVENT, f"{where}.effective_date"),  # row: getStatusHistoryForAdjustment statusTypeHistory[].effectiveDate
            end_date=NP,
            reason=ctx.text(reasons.get((str(row.get("effectiveDate")), str(status)))),
        ))
        ctx.keep(f"getStatusHistoryForAdjustment:statusTypeHistory[{index}].dateUpdated", row.get("dateUpdated"))  # row: getStatusHistoryForAdjustment statusTypeHistory[].dateUpdated
    return periods


def _history_records(history_body: Any) -> list[dict]:
    # The demo sends the singular key historyRecord (live rename, D-062).
    if not history_body:
        return []
    return history_body.get("historyRecords") or history_body.get("historyRecord") or []


def _job_history(ctx: Ctx, tenant: str, client: str, history_body: Any, codes: ClientCodes) -> Any:
    if history_body is None:
        return NP
    key = "historyRecords" if "historyRecords" in history_body else "historyRecord"
    entries = []
    for index, record in enumerate(_history_records(history_body)):
        at = f"getHistory:{key}[{index}]"
        where = f"job_history[{len(entries)}]"
        position = record.get("newPositionCode")  # row: getHistory historyRecords[].newPositionCode
        department = (record.get("departmentChange") or {}).get("departmentCode")  # row: getHistory historyRecords[].departmentChange.departmentCode
        division = (record.get("divisionChange") or {}).get("divisionCode")  # row: getHistory historyRecords[].divisionChange.divisionCode
        location = (record.get("locationChange") or {}).get("locationCode")  # row: getHistory historyRecords[].locationChange.locationCode
        units = [
            _org_unit(ctx, "department", "departmentCode", department, codes.department, "deptName"),
            _org_unit(ctx, "division", "divisionCode", division, codes.division, "divisionName"),
        ]
        units = [unit for unit in units if unit is not None]
        if not is_blank(position) or units or not is_blank(location):
            entries.append(build(
                JobAssignment,
                job=_job_reference(ctx, codes, position),
                effective_date=ctx.date(record.get("effectiveDate"), DateRole.EVENT, f"{where}.effective_date"),  # row: getHistory historyRecords[].effectiveDate
                org_units=units or NP,
                work_location_id=NP if is_blank(location) else _id(tenant, EntityType.WORK_LOCATION, client, str(location).strip()),
                manager_employee_id=NP,
                supervisor_employee_id=NP,
                eeo_category=NP,
                union_code=NP,
                workers_comp_code=NP,
            ))
        ctx.keep(f"{at}.leave.expectedReturnDate", (record.get("leave") or {}).get("expectedReturnDate"))  # row: getHistory historyRecords[].leave.expectedReturnDate
        ctx.keep(f"{at}.termination.explanation", (record.get("termination") or {}).get("explanation"), sensitive=True)  # row: getHistory historyRecords[].termination.explanation
        ctx.keep(f"{at}.termination.rehireOK", (record.get("termination") or {}).get("rehireOK"))  # row: getHistory historyRecords[].termination.rehireOK
        ctx.keep(f"{at}.benefitGroupChange.benefitGroupCode", (record.get("benefitGroupChange") or {}).get("benefitGroupCode"))  # row: getHistory historyRecords[].benefitGroupChange.benefitGroupCode
        # row: getHistory historyRecords[].wellnessStatusChange.wellnessStatus
        ctx.keep(f"{at}.wellnessStatusChange.wellnessStatus", (record.get("wellnessStatusChange") or {}).get("wellnessStatus"), sensitive=True)
        for block in ("projectChange", "shiftChange", "workGroupChange"):  # row: getHistory historyRecords[].projectChange.**; historyRecords[].shiftChange.**; historyRecords[].workGroupChange.**
            ctx.keep(f"{at}.{block}", record.get(block))
    return entries


# ---- compensation and tax -------------------------------------------------------------


def _compensation(ctx: Ctx, tenant: str, client: str, pay: dict, codes: ClientCodes, override_body: Any) -> Compensation:
    group = pay.get("payGroup")  # row: getEmployee employee[].compensation.payGroup
    schedule = codes.schedule.get(str(group).strip()) if not is_blank(group) else None
    if schedule is not None:
        frequency = ctx.coded("prismhr.pay_period", schedule.get("payPeriod"), "compensation.pay_frequency", label=schedule.get("payPeriodDesc"))
    elif is_blank(group):
        frequency = NP
    else:
        frequency = ctx.unavailable("compensation.pay_frequency", f"Pay group {str(group).strip()!r} has no payroll schedule in the input.", "D-041")
    hours = ctx.number(pay.get("standardHours"), "compensation.standard_hours")  # row: getEmployee employee[].compensation.standardHours
    period_letter = pay.get("payPeriod")
    rates = []
    for number in (2, 3, 4):  # row: getEmployee employee[].compensation.payRate2; employee[].compensation.payRate3; employee[].compensation.payRate4
        amount = ctx.number(pay.get(f"payRate{number}"), f"compensation.additional_rates[{len(rates)}].amount")
        if not isinstance(amount, Null):
            rates.append(build(AdditionalRate, code=NP, name=f"alternate pay rate {number}", amount=amount, period=NP))
    if override_body is not None:
        for item in (override_body.get("overrideRate") or {}).get("payCodeRate") or []:
            rates.append(build(
                AdditionalRate,
                code=ctx.text(item.get("payCode")),  # row: getEmployeeOverrideRates overrideRate.payCodeRate[].payCode
                name=ctx.text(item.get("payCodeDesc")),  # row: getEmployeeOverrideRates overrideRate.payCodeRate[].payCodeDesc
                amount=ctx.number(item.get("payRate"), f"compensation.additional_rates[{len(rates)}].amount"),  # row: getEmployeeOverrideRates overrideRate.payCodeRate[].payRate
                period=NP,
            ))
    return build(
        Compensation,
        pay_type=ctx.coded("prismhr.pay_method", pay.get("payMethod"), "compensation.pay_type"),  # row: getEmployee employee[].compensation.payMethod
        pay_frequency=frequency,
        pay_group_id=NP if is_blank(group) else _id(tenant, EntityType.PAY_GROUP, client, str(group).strip()),
        base_rate=ctx.number(pay.get("hourlyPayRate"), "compensation.base_rate"),  # row: getEmployee employee[].compensation.hourlyPayRate
        base_rate_period=ctx.coded("prismhr.hourly_pay_period", pay.get("hourlyPayPeriod"), "compensation.base_rate_period"),  # row: getEmployee employee[].compensation.hourlyPayPeriod
        hourly_rate=ctx.number(pay.get("hourlyPay"), "compensation.hourly_rate"),  # row: getEmployee employee[].compensation.hourlyPay
        annual_salary=ctx.number(pay.get("annualPay"), "compensation.annual_salary"),  # row: getEmployee employee[].compensation.annualPay
        per_period_amount=ctx.number(pay.get("salary"), "compensation.per_period_amount"),  # row: getEmployee employee[].compensation.salary
        standard_hours=hours,
        standard_hours_period=NP if isinstance(hours, Null) or is_blank(period_letter) else {
            "value": "pay_period", "raw_code": str(period_letter).strip(), "raw_label": None, "basis": "documented"},
        effective_date=ctx.date(pay.get("effectiveDate"), DateRole.EVENT, "compensation.effective_date"),  # row: getEmployee employee[].compensation.effectiveDate
        additional_rates=rates,
    )


def _override(ctx: Ctx, kind: Any, amount: Any, field: str, type_key: str, amount_key: str) -> tuple[Any, Any]:
    """(is_blocked, additional_amount) from a PrismHR override type: B blocks; A adds the
    amount; F and P replace the calculation and have no typed home, so they are kept raw."""
    code = str(kind or "").strip().upper()
    if code == "B":
        return True, NA
    if code == "A":
        return False, ctx.number(amount, f"{field}.additional_amount")
    if code in ("F", "P"):
        ctx.keep(type_key, kind, sensitive=True)
        ctx.keep(amount_key, amount, sensitive=True)
        return False, NA
    if code == "":
        return False, NA
    ctx.diag(DiagnosticCode.UNKNOWN_CODE, Severity.WARNING, "Withholding override type is not documented.", f"{field}.is_blocked")
    ctx.keep(type_key, kind, sensitive=True)
    return NP, NP


def _tax(ctx: Ctx, base: str, pay: dict) -> TaxWithholding:
    at = f"{base}.compensation"
    # row: getEmployee employee[].compensation.fedOverrideType; employee[].compensation.fedOverrideAmt
    blocked, additional = _override(ctx, pay.get("fedOverrideType"), pay.get("fedOverrideAmt"), "tax_withholding.federal",
                                    f"{at}.fedOverrideType", f"{at}.fedOverrideAmt")
    federal = build(
        TaxWithholdingSetting,
        level="federal",
        jurisdiction="US",
        residency=NA,
        filing_status=ctx.coded("prismhr.fed_filing_status", pay.get("fedFilingStatus"), "tax_withholding.federal.filing_status", sensitive=True),  # row: getEmployee employee[].compensation.fedFilingStatus
        allowances=ctx.integer(pay.get("fedWithholdAllowance"), "tax_withholding.federal.allowances"),  # row: getEmployee employee[].compensation.fedWithholdAllowance
        additional_amount=additional,
        additional_percent=NP,
        is_exempt=NP,
        multiple_jobs=ctx.flag(pay.get("fedMultipleJobs"), "tax_withholding.federal.multiple_jobs"),  # row: getEmployee employee[].compensation.fedMultipleJobs
        dependents_amount=ctx.number(pay.get("fedDependents"), "tax_withholding.federal.dependents_amount"),  # row: getEmployee employee[].compensation.fedDependents
        other_income_amount=ctx.number(pay.get("fedOtherIncome"), "tax_withholding.federal.other_income_amount"),  # row: getEmployee employee[].compensation.fedOtherIncome
        deductions_amount=ctx.number(pay.get("fedDeductions"), "tax_withholding.federal.deductions_amount"),  # row: getEmployee employee[].compensation.fedDeductions
        is_blocked=blocked,
    )
    states = []
    for index, item in enumerate(pay.get("stateTax") or []):
        where, key = f"tax_withholding.states[{index}]", f"{at}.stateTax[{index}]"
        # row: getEmployee employee[].compensation.stateTax[].overrideType; employee[].compensation.stateTax[].overrideAmount
        blocked, additional = _override(ctx, item.get("overrideType"), item.get("overrideAmount"), where, f"{key}.overrideType", f"{key}.overrideAmount")
        states.append(build(
            TaxWithholdingSetting,
            level="state",
            jurisdiction=ctx.text(item.get("stateCode")),  # row: getEmployee employee[].compensation.stateTax[].stateCode
            residency=NP,
            filing_status=ctx.coded("prismhr.state_filing_status", item.get("filingStatus"), f"{where}.filing_status", sensitive=True),  # row: getEmployee employee[].compensation.stateTax[].filingStatus
            allowances=ctx.integer(item.get("primaryAllowance"), f"{where}.allowances"),  # row: getEmployee employee[].compensation.stateTax[].primaryAllowance
            additional_amount=additional,
            additional_percent=NP,
            is_exempt=NP,
            multiple_jobs=ctx.flag(item.get("multipleJobs"), f"{where}.multiple_jobs"),  # row: getEmployee employee[].compensation.stateTax[].multipleJobs
            dependents_amount=ctx.number(item.get("dependents"), f"{where}.dependents_amount"),  # row: getEmployee employee[].compensation.stateTax[].dependents
            other_income_amount=ctx.number(item.get("otherIncome"), f"{where}.other_income_amount"),  # row: getEmployee employee[].compensation.stateTax[].otherIncome
            deductions_amount=ctx.number(item.get("deductions"), f"{where}.deductions_amount"),  # row: getEmployee employee[].compensation.stateTax[].deductions
            is_blocked=blocked,
        ))
        handled = {"stateCode", "filingStatus", "primaryAllowance", "multipleJobs", "dependents", "otherIncome", "deductions", "overrideType", "overrideAmount"}
        # row: getEmployee employee[].compensation.stateTax[].*
        ctx.rest(key, item, handled, excluded={"reduceAddlWithholding", "fixedWithholding"}, all_sensitive=True)
    locals_ = []
    for index, item in enumerate(pay.get("localTax") or []):
        where = f"tax_withholding.locals[{index}]"
        locals_.append(build(
            TaxWithholdingSetting,
            level="local",
            jurisdiction=ctx.text(item.get("authId")),  # row: getEmployee employee[].compensation.localTax[].authId
            residency=NP,
            filing_status=ctx.coded("prismhr.local_filing_status", item.get("filingStatus"), f"{where}.filing_status", sensitive=True),  # row: getEmployee employee[].compensation.localTax[].filingStatus
            allowances=ctx.integer(item.get("primaryAllowance"), f"{where}.allowances"),  # row: getEmployee employee[].compensation.localTax[].primaryAllowance
            additional_amount=ctx.number(item.get("addlWithheld"), f"{where}.additional_amount"),  # row: getEmployee employee[].compensation.localTax[].addlWithheld
            additional_percent=NP,
            is_exempt=NP,
            multiple_jobs=NP,
            dependents_amount=NP,
            other_income_amount=NP,
            deductions_amount=NP,
            is_blocked=NP,
        ))
        ctx.keep(f"{at}.localTax[{index}].nonResCert", item.get("nonResCert"), sensitive=True)  # row: getEmployee employee[].compensation.localTax[].nonResCert
    return build(TaxWithholding, federal=federal, states=states, locals=locals_)


def _compensation_history(ctx: Ctx, body: Any) -> Any:
    if body is None:
        return NP
    changes = []
    for index, row in enumerate((body.get("payRateHistory") or {}).get("payRate") or []):
        where = f"compensation_history[{index}]"
        changes.append(build(
            CompensationChange,
            effective_date=ctx.date(row.get("effectiveDate"), DateRole.EVENT, f"{where}.effective_date"),  # row: getPayRateHistory payRateHistory.payRate[].effectiveDate
            pay_type=ctx.coded("prismhr.pay_method", row.get("payMethod"), f"{where}.pay_type"),  # row: getPayRateHistory payRateHistory.payRate[].payMethod
            amount=ctx.number(row.get("payRate"), f"{where}.amount"),  # row: getPayRateHistory payRateHistory.payRate[].payRate
            amount_period=ctx.coded("prismhr.rate_period", row.get("payPeriod"), f"{where}.amount_period"),  # row: getPayRateHistory payRateHistory.payRate[].payPeriod
            hourly_rate=ctx.number(row.get("hourlyRate"), f"{where}.hourly_rate"),  # row: getPayRateHistory payRateHistory.payRate[].hourlyRate
            annual_amount=ctx.number(row.get("annualPay"), f"{where}.annual_amount"),  # row: getPayRateHistory payRateHistory.payRate[].annualPay
            change_amount=ctx.number(row.get("changeAmount"), f"{where}.change_amount"),  # row: getPayRateHistory payRateHistory.payRate[].changeAmount
            change_percent=ctx.number(row.get("changePercent"), f"{where}.change_percent"),  # row: getPayRateHistory payRateHistory.payRate[].changePercent
            reason=ctx.text(row.get("reason")),  # row: getPayRateHistory payRateHistory.payRate[].reason
        ))
        key = f"getPayRateHistory:payRateHistory.payRate[{index}]"
        ctx.keep(f"{key}.standardHours", row.get("standardHours"))  # row: getPayRateHistory payRateHistory.payRate[].standardHours
        ctx.keep(f"{key}.percentMidpoint", row.get("percentMidpoint"))  # row: getPayRateHistory payRateHistory.payRate[].percentMidpoint
    return changes


# ---- time off, related people, qualifications -----------------------------------------


def _pto(ctx: Ctx, body: Any) -> Any:
    if body is None:
        return NP
    balances = []
    for index, item in enumerate(body.get("paidTimeOff") or []):
        where = f"pto_balances[{index}]"
        balances.append(build(
            PtoBalance,
            plan_source_id=ctx.text(item.get("ptoPlanId")),  # row: getPaidTimeOff paidTimeOff[].ptoPlanId
            plan_code=ctx.text(item.get("registerType")),  # row: getPaidTimeOff paidTimeOff[].registerType
            plan_name=ctx.text(item.get("registerTypeDescription")),  # row: getPaidTimeOff paidTimeOff[].registerTypeDescription
            balance=NP,  # PrismHR sends no balance; it is not derived (D-079).
            accrued_ytd=ctx.number(item.get("accruedHoursYTD"), f"{where}.accrued_ytd"),  # row: getPaidTimeOff paidTimeOff[].accruedHoursYTD
            used_ytd=ctx.number(item.get("usedHoursYTD"), f"{where}.used_ytd"),  # row: getPaidTimeOff paidTimeOff[].usedHoursYTD
            carryover=ctx.number(item.get("carryOverHours"), f"{where}.carryover"),  # row: getPaidTimeOff paidTimeOff[].carryOverHours
            as_of_date=ctx.date(item.get("accruedThru"), DateRole.EVENT, f"{where}.as_of_date"),  # row: getPaidTimeOff paidTimeOff[].accruedThru
            period_start=NP,
            period_end=ctx.date(item.get("yearEndDate"), DateRole.PERIOD_END, f"{where}.period_end"),  # row: getPaidTimeOff paidTimeOff[].yearEndDate
        ))
        # row: getPaidTimeOff paidTimeOff[].benefitStart; paidTimeOff[].lastCarryOver; paidTimeOff[].carryOverExpires
        # row: getPaidTimeOff paidTimeOff[].carryOverExpireFlag; paidTimeOff[].accruedFlag; paidTimeOff[].stopPTOAccruals; paidTimeOff[].priorYear[].*
        handled = {"ptoPlanId", "registerType", "registerTypeDescription", "accruedHoursYTD", "usedHoursYTD", "carryOverHours", "accruedThru", "yearEndDate"}
        ctx.rest(f"getPaidTimeOff:paidTimeOff[{index}]", item, handled, excluded={"journalId"})
    return balances


def _related_people(ctx: Ctx, base: str, person: dict, dependents_body: Any, codes: ClientCodes) -> Any:
    people = []
    for index, item in enumerate((dependents_body or {}).get("dependent") or []):
        people.append(_dependent(ctx, f"related_people[{len(people)}]", f"getDependents:dependent[{index}]", item, codes))
    for index, item in enumerate(person.get("emergencyContact") or []):
        people.append(_emergency_contact(ctx, f"related_people[{len(people)}]", f"{base}.person.emergencyContact[{index}]", item))
    if dependents_body is None and not people:
        return NP
    return people


def _dependent(ctx: Ctx, where: str, key: str, item: dict, codes: ClientCodes) -> RelatedPerson:
    relation, kind = item.get("relation"), item.get("relationshipCodeType")  # row: getDependents dependent[].relation; dependent[].relationshipCodeType
    label = codes.field(codes.relation, relation, "description")  # row: getClientCodes clientCodes.relationCodes[].description
    if is_blank(kind):
        relationship = ctx.unknown(relation, f"{where}.relationship", label, evidence="D-079") if not is_blank(relation) else NP
    else:
        relationship = ctx.coded("prismhr.relationship_code_type", kind, f"{where}.relationship", label=label,
                                 raw_code=relation if not is_blank(relation) else kind)
    relation_type = str(item.get("relationType") or "").strip().upper()  # row: getDependents dependent[].relationType
    beneficiary_type = str(item.get("beneficiaryType") or "").strip().upper()
    if relation_type == "D":
        is_dependent, is_beneficiary = True, (True if beneficiary_type in ("P", "C") else NP)
    elif relation_type == "B":
        is_dependent, is_beneficiary = False, True
    else:
        is_dependent, is_beneficiary = NP, NP
        if relation_type:
            ctx.diag(DiagnosticCode.UNKNOWN_CODE, Severity.WARNING, f"Dependent relation type {relation_type!r} is not documented.", f"{where}.is_dependent")
        ctx.keep(f"{key}.relationType", item.get("relationType"))
    status = str(item.get("status") or "").strip().upper()  # row: getDependents dependent[].status
    if status in ("A", "I"):
        is_active = status == "A"
    else:
        is_active = NP  # pending (P) never reads as inactive (D-079)
        ctx.keep(f"{key}.status", item.get("status"))
        if status not in ("", "P"):
            ctx.diag(DiagnosticCode.UNKNOWN_CODE, Severity.WARNING, f"Dependent status {status!r} is not documented.", f"{where}.is_active")
    phones = []
    for field, kind in (("homePhone", "home"), ("workPhone", "work")):  # row: getDependents dependent[].homePhone; dependent[].workPhone
        number = ctx.text(item.get(field), sensitive=True)
        if not isinstance(number, Null):
            phones.append(build(Phone, type=kind, number=number, extension=NP, is_preferred=NP))
    lines = ("address", "addressLine2", "city", "state", "zip", "country")
    address = NP if all(is_blank(item.get(k)) for k in lines) else build(
        PersonalAddress,
        type="unknown",
        line1=ctx.text(item.get("address"), sensitive=True),  # row: getDependents dependent[].address
        line2=ctx.text(item.get("addressLine2"), sensitive=True),  # row: getDependents dependent[].addressLine2
        city=ctx.text(item.get("city")),  # row: getDependents dependent[].city
        county=NP,
        state=ctx.text(item.get("state")),  # row: getDependents dependent[].state
        postal_code=ctx.text(item.get("zip"), sensitive=True),  # row: getDependents dependent[].zip
        country=ctx.text(item.get("country")),  # row: getDependents dependent[].country
    )
    # row: getDependents dependent[].* ; dependent[].ssnAppliedFor; dependent[].zipSuffix; dependent[].spouse; dependent[].statusDate
    handled = {"dependentId", "relation", "relationshipCodeType", "relationType", "status", "firstName", "middleInitial",
               "lastName", "email", "gender", "birthdate", "ssn", "address", "addressLine2", "city", "state", "zip",
               "country", "homePhone", "workPhone", "spouse", "statusDate"}
    ctx.rest(key, item, handled, excluded={"checksum"}, all_sensitive=True)
    ctx.keep(f"{key}.spouse", item.get("spouse"))
    ctx.keep(f"{key}.statusDate", item.get("statusDate"))
    return build(
        RelatedPerson,
        source_id=ctx.text(item.get("dependentId")),  # row: getDependents dependent[].dependentId
        relationship=relationship,
        name=build(
            PersonName,
            first=ctx.text(item.get("firstName")),  # row: getDependents dependent[].firstName
            middle=ctx.text(item.get("middleInitial")),  # row: getDependents dependent[].middleInitial
            last=ctx.text(item.get("lastName")),  # row: getDependents dependent[].lastName
            prefix=NP,
            suffix=NP,
            preferred_first=NP,
        ),
        full_name=NA,
        birth_date=ctx.date(item.get("birthdate"), DateRole.EVENT, f"{where}.birth_date"),  # row: getDependents dependent[].birthdate
        gender=ctx.coded("prismhr.dependent_gender", item.get("gender"), f"{where}.gender", sensitive=True),  # row: getDependents dependent[].gender
        national_id=ctx.national_id(NationalId, item.get("ssn"), SSN_TYPE, f"{where}.national_id", is_primary=NP),  # row: getDependents dependent[].ssn
        address=address,
        phones=phones,
        email=ctx.text(item.get("email"), sensitive=True),  # row: getDependents dependent[].email
        is_dependent=is_dependent,
        is_emergency_contact=NP,
        is_beneficiary=is_beneficiary,
        is_active=is_active,
    )


def _emergency_contact(ctx: Ctx, where: str, key: str, item: dict) -> RelatedPerson:
    kind = str(item.get("contactType") or "").strip().upper()  # row: getEmployee employee[].person.emergencyContact[].contactType
    info = item.get("contactInfo")  # row: getEmployee employee[].person.emergencyContact[].contactInfo
    phones: Any = NP
    email: Any = NP
    if kind in ("PHONE", "TEXT"):
        number = ctx.text(info, sensitive=True)
        phones = [] if isinstance(number, Null) else [build(Phone, type="unknown", number=number, extension=NP, is_preferred=NP)]
    elif kind == "EMAIL":
        email = ctx.text(info, sensitive=True)
    else:
        ctx.keep(f"{key}.contactType", item.get("contactType"), sensitive=True)
        ctx.keep(f"{key}.contactInfo", info, sensitive=True)
    relationship = item.get("contactRelationship")  # row: getEmployee employee[].person.emergencyContact[].contactRelationship
    ctx.keep(f"{key}.contactIfDetained", item.get("contactIfDetained"), sensitive=True)  # row: getEmployee employee[].person.emergencyContact[].contactIfDetained
    return build(
        RelatedPerson,
        source_id=NP,
        relationship=ctx.coded("prismhr.emergency_contact_relationship", relationship, f"{where}.relationship", sensitive=True),
        name=NP,
        full_name=ctx.text(item.get("contactName"), sensitive=True),  # row: getEmployee employee[].person.emergencyContact[].contactName
        birth_date=NP,
        gender=NP,
        national_id=NP,
        address=NP,
        phones=phones,
        email=email,
        is_dependent=NP,
        is_emergency_contact=True,
        is_beneficiary=NP,
        is_active=NP,
    )


def _qualifications(ctx: Ctx, base: str, block: dict, codes: ClientCodes) -> list[Qualification]:
    found = []
    for index, item in enumerate(block.get("skill") or []):
        where, key = f"qualifications[{len(found)}]", f"{base}.skillsAndEducation.skill[{index}]"
        code = item.get("skillCode")  # row: getEmployee employee[].skillsAndEducation.skill[].skillCode
        found.append(build(
            Qualification,
            type="skill",
            source_id=NP,
            code=ctx.text(code),
            name=ctx.text(codes.field(codes.skill, code, "description")),  # row: getClientCodes clientCodes.skillCodes[].description
            level=ctx.text(item.get("competencyLevel")),  # row: getEmployee employee[].skillsAndEducation.skill[].competencyLevel
            institution=NP,
            completed_date=ctx.date(item.get("certifyDate"), DateRole.EVENT, f"{where}.completed_date"),  # row: getEmployee employee[].skillsAndEducation.skill[].certifyDate
            expiration_date=NP,
            years_experience=NP,
        ))
        ctx.keep(f"{key}.renewDate", item.get("renewDate"))  # row: getEmployee employee[].skillsAndEducation.skill[].renewDate
        ctx.keep(f"{key}.skillComment", item.get("skillComment"), sensitive=True)  # row: getEmployee employee[].skillsAndEducation.skill[].skillComment
    for index, item in enumerate(block.get("school") or []):
        key = f"{base}.skillsAndEducation.school[{index}]"
        found.append(build(
            Qualification,
            type="education",
            source_id=NP,
            code=NP,
            name=ctx.text(item.get("degreeEarned")),  # row: getEmployee employee[].skillsAndEducation.school[].degreeEarned
            level=NP,
            institution=ctx.text(item.get("schoolName")),  # row: getEmployee employee[].skillsAndEducation.school[].schoolName
            completed_date=NP,
            expiration_date=NP,
            years_experience=NP,
        ))
        # row: getEmployee employee[].skillsAndEducation.school[].gradYear; employee[].skillsAndEducation.school[].graduated; employee[].skillsAndEducation.school[].schoolYear
        for name in ("gradYear", "graduated", "schoolYear"):
            ctx.keep(f"{key}.{name}", item.get(name))
        ctx.keep(f"{key}.schoolComment", item.get("schoolComment"), sensitive=True)  # row: getEmployee employee[].skillsAndEducation.school[].schoolComment
    ctx.keep(f"{base}.skillsAndEducation.osha10Certified", block.get("osha10Certified"))  # row: getEmployee employee[].skillsAndEducation.osha10Certified
    return found


def _position_rates(ctx: Ctx, body: Any) -> None:
    for index, item in enumerate((body or {}).get("positionRate") or []):
        ctx.rest(f"getPositionRate:positionRate[{index}]", item, excluded={"checksum"})  # row: getPositionRate positionRate[].**


# ---- extensions of the getEmployee blocks ---------------------------------------------

PERSON_MAPPED = {"birthDate", "gender", "ethnicCode", "maritalStatus", "smoker", "handicapped", "veteran", "disabledVet",
                 "otherProtectedVet", "activeDutyBadgeVet", "recentlySeparatedVet", "serviceMedalVet", "deceased",
                 "deceasedDate", "emergencyContact"}
PERSON_SENSITIVE = {"hispanic", "marriedDate", "blind", "vietnamVet", "hrpCitizenshipCountry", "cobraSSN", "legacyEmployeeId",
                    "driverLicenseId", "driverState", "driverLicenseExpireDate", "driverLicenseClass", "autoPolicies",
                    "autoPolicy", "vehicleDetails", "taxZipCode"}
PERSON_EXCLUDED = {"w2AddressLine1", "w2AddressLine2", "w2City", "w2State", "w2PostalCode", "unincorporatedResidence", "personChecksum"}
CLIENT_MAPPED = {"employeeStatus", "statusClass", "statusDate", "employeeType", "typeClass", "employee1099", "flsaExempt",
                 "firstHireDate", "lastHireDate", "seniorityDate", "rehireOk", "termReasonCode", "clientEmployeeId", "jobCode",
                 "lastJobChangeDate", "homeDepartment", "homeDivision", "projCostCenter", "subCostCenter", "homeLocation",
                 "manager", "unionCode", "workEmail", "workPhone", "workPhoneExt", "preferredPronoun"}
CLIENT_SENSITIVE = {"termExplanation", "genderDesignation", "selfIdDisabilityForm", "benefitEmail", "clockNum",
                    "courtOrderMedical", "childSpouseSupport", "childSpouseArrears", "hawaiiMedWaivers", "hawaiiMedWaiver"}
CLIENT_EXCLUDED = {"addressLine1", "addressLine2", "city", "state", "zip", "zipSuffix", "clientChecksum"}
PAY_MAPPED = {"ssn", "citizenshipStatus", "payGroup", "payMethod", "hourlyPayRate", "hourlyPayPeriod", "hourlyPay", "salary",
              "annualPay", "standardHours", "effectiveDate", "payRate2", "payRate3", "payRate4", "fedFilingStatus",
              "fedWithholdAllowance", "fedMultipleJobs", "fedDependents", "fedOtherIncome", "fedDeductions",
              "fedOverrideType", "fedOverrideAmt", "stateTax", "localTax", "formI9Filed", "nonResAlien"}
PAY_SENSITIVE = {"alternateId", "notes", "perfReviewLastRating", "fedTaxCalc", "eicFileStatus", "fedW4Filed", "fedW4Year",
                 "fedW5Filed", "fedW5Year", "w8Filed", "ficaExempt", "irsLockInDate", "lockIns", "taxCreditEmp",
                 "formI9RenewDate", "alienRegExpDate", "eeImage", "i9imageAudit"}
EMPLOYEE_HANDLED = {"id", "firstName", "lastName", "middleInitial", "preferredName", "person", "contactInformation", "client",
                    "compensation", "health", "skillsAndEducation", "employeeEvents", "newHireQuestions", "hsa"}
# directDeposit: DirectDeposit records (entities/prismhr/deposits.py); scheduledDeduction: excluded (D-081).
EMPLOYEE_EXCLUDED = {"absenceJournalId", "infoMessage", "updateMessage", "directDeposit", "scheduledDeduction"}


def _employee_extensions(ctx: Ctx, base: str, item: dict, person: dict, contact: dict, work: dict, pay: dict) -> None:
    # row: getEmployee employee[].person.hispanic; employee[].person.marriedDate; employee[].person.blind; employee[].person.vietnamVet
    # row: getEmployee employee[].person.hrpCitizenshipCountry; employee[].person.cobraSSN; employee[].person.legacyEmployeeId
    # row: getEmployee employee[].person.driverLicenseId; employee[].person.driverState; employee[].person.driverLicenseExpireDate
    # row: getEmployee employee[].person.driverLicenseClass; employee[].person.autoPolicies[].*; employee[].person.autoPolicy[]
    # row: getEmployee employee[].person.vehicleDetails[].*; employee[].person.taxZipCode; employee[].person.peoStartDate
    # row: getEmployee employee[].person.employerIds[]; employee[].person.employerId[]; employee[].person.nickname; employee[].person.*
    ctx.rest(f"{base}.person", person, PERSON_MAPPED, PERSON_SENSITIVE, PERSON_EXCLUDED)
    # row: getEmployee employee[].contactInformation.schoolDistrict
    ctx.rest(f"{base}.contactInformation", contact, {"homePhone", "mobilePhone", "emailAddress"},
             excluded={"addressLine1", "addressLine2", "city", "county", "state", "zipcode", "zipSuffix"})
    # row: getEmployee employee[].client.termExplanation; employee[].client.genderDesignation; employee[].client.selfIdDisabilityForm
    # row: getEmployee employee[].client.benefitEmail; employee[].client.clockNum; employee[].client.courtOrderMedical
    # row: getEmployee employee[].client.childSpouseSupport; employee[].client.childSpouseArrears; employee[].client.hawaiiMedWaivers[].*
    # row: getEmployee employee[].client.hawaiiMedWaiver[]; employee[].client.*; employee[].client.transferInfo[].*; employee[].client.property[].*
    # row: getEmployee employee[].client.typeDate; employee[].client.cafeteriaPlan[].*
    ctx.rest(f"{base}.client", work, CLIENT_MAPPED, CLIENT_SENSITIVE, CLIENT_EXCLUDED)
    # row: getEmployee employee[].compensation.alternateId; employee[].compensation.notes; employee[].compensation.perfReviewLastRating
    # row: getEmployee employee[].compensation.fedTaxCalc; employee[].compensation.eicFileStatus; employee[].compensation.fedW4Filed
    # row: getEmployee employee[].compensation.fedW4Year; employee[].compensation.fedW5Filed; employee[].compensation.fedW5Year
    # row: getEmployee employee[].compensation.w8Filed; employee[].compensation.ficaExempt; employee[].compensation.irsLockInDate
    # row: getEmployee employee[].compensation.lockIns[].*; employee[].compensation.taxCreditEmp; employee[].compensation.formI9RenewDate
    # row: getEmployee employee[].compensation.alienRegExpDate; employee[].compensation.eeImage[].*; employee[].compensation.i9imageAudit[].*
    # row: getEmployee employee[].compensation.overrideWorkGeocode; employee[].compensation.payPeriod; employee[].compensation.payPeriodsPerWeek
    # row: getEmployee employee[].compensation.lastChangePct; employee[].compensation.lastChangeAmt; employee[].compensation.payChangeLastDate
    # row: getEmployee employee[].compensation.compaRatio; employee[].compensation.quartile; employee[].compensation.benefitsBasePay
    # row: getEmployee employee[].compensation.benefitSalary; employee[].compensation.benefitsPerHour; employee[].compensation.perDiemPay
    # row: getEmployee employee[].compensation.defaultHours; employee[].compensation.autoAcceptTimeSheet; employee[].compensation.allocationTemplateId
    # row: getEmployee employee[].compensation.workShift; employee[].compensation.longPayTable; employee[].compensation.longBasisDate
    # row: getEmployee employee[].compensation.autoPayCode; employee[].compensation.deliverCheckHome; employee[].compensation.electronicPayStub
    # row: getEmployee employee[].compensation.pensionStatus; employee[].compensation.profitSharing; employee[].compensation.wagePlanCA
    # row: getEmployee employee[].compensation.familyMemberMI; employee[].compensation.probationCodeMO; employee[].compensation.healthInsVT
    # row: getEmployee employee[].compensation.perfReviewLastDate; employee[].compensation.perfReviewNextDate; employee[].compensation.perfReviewLastTitle
    # row: getEmployee employee[].compensation.compReviewNextDate; employee[].compensation.perfAgreement; employee[].compensation.firstPayPeriodHours
    # row: getEmployee employee[].compensation.lastPayDate; employee[].compensation.paidThruDate; employee[].compensation.lastWorkedDate
    # row: getEmployee employee[].compensation.providerNotifiedOn; employee[].compensation.altPayRate[]; employee[].compensation.payPeriodInfo[].*
    # row: getEmployee employee[].compensation.payAllocation[].*
    ctx.rest(f"{base}.compensation", pay, PAY_MAPPED, PAY_SENSITIVE, {"compensationChecksum"})
    ctx.keep(f"{base}.health", item.get("health"), sensitive=True)  # row: getEmployee employee[].health.**
    # HSA contribution transfer accounts: not net pay deposits (D-081).
    ctx.keep(f"{base}.hsa.hsaDepositSettings", (item.get("hsa") or {}).get("hsaDepositSettings"), sensitive=True)  # row: getEmployee employee[].hsa.hsaDepositSettings[].*
    ctx.keep(f"{base}.employeeEvents", item.get("employeeEvents"), sensitive=True)  # row: getEmployee employee[].employeeEvents.employeeEvent[].*
    ctx.keep(f"{base}.newHireQuestions", item.get("newHireQuestions"), sensitive=True)  # row: getEmployee employee[].newHireQuestions[].*
    # row: getEmployee employee[].enrollmentInProgress.*; employee[].benefitEnrollmentCompleted
    ctx.rest(base, item, EMPLOYEE_HANDLED, excluded=EMPLOYEE_EXCLUDED)


normalize = normalize_employees  # pipeline entry point (pipeline.py)
