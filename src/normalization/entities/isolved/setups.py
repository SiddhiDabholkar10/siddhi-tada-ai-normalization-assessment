"""isolved deduction setups (D-048), following ``mappings/data/isolved/deduction_setup.json``.

Candidate setups (D-017): one per legal-level pay item entry whose joined per-employee entry
(same legal, employee and id) is a Deduction, source_basis candidate_assignment with an
unvalidated_source diagnostic, id from (legal, entry id). payItemType and calcParams come from
the per-employee entry, the rest from the legal list (D-081). The code joins the client catalog
by code (D-066), and the setup copies the catalog code's classification (D-047, D-088). A legal
entry whose per-employee entry is Earning or Memo Calc makes no setup: it goes to the employee
(``employee_extras``, SENT_TO_EMPLOYEE). Garnishments: one documented setup per garnishments
item, id from (legal, ``garnishment``, garnishment id) (D-088).
"""
from typing import Any

from ...canonical.deductions import DeductionSetup, GarnishmentDetails
from ...canonical.diagnostics import DiagnosticCode, Severity
from ...canonical.ids import EntityType, Provider, canonical_id
from ...canonical.parsing import DateRole
from ...canonical.parts import Reference
from ...employees.bundle import Bundle, Response
from ...employees.common import NP, Ctx, build, is_blank
from ..common import USD, route_code, source
from .company import without_links

PROVIDER = "isolved"
TABLE = "deduction_setup"
API = "/api/clients/{clientId}/legals/{legalId}"
ROUTES = {
    "legalPayItems": f"{API}/payItems",
    "employeePayItems": f"{API}/employees/{{employeeId}}/payItems",
    "garnishments": f"{API}/employees/{{employeeId}}/garnishments",
    "payItems": "/api/clients/{clientId}/payItems",  # catalog: code join and classification (not a table row)
}
LEGAL_KEPT = ("payItemId", "referenceNumber", "scheduleOverride", "balance")
# Leaves of a non-deduction entry that are classified (not excluded) and so go to the employee.
LEGAL_TO_EMPLOYEE = ("id", "employeeId", "payItemCode", "payItemName", "startDate", "stopDate", *LEGAL_KEPT)
GARNISHMENT_HANDLED = {"id", "garnishmentType", "garnishmentDescription", "caseNumber", "garnishmentPayee", "thirdPartyPayee",
                       "garnishmentSequence", "state", "amount", "percent", "percentageOf", "maximumAmount", "maximumPercent",
                       "feeAmount", "arrearsBalance", "remainingBalance", "applyArrears", "isMedicalSupportRequired",
                       "selectedDeductions", "startDate", "stopDate", "status", "links"}


def _id(tenant: str, entity: EntityType, *parts: Any) -> str:
    return canonical_id(Provider.ISOLVED, tenant, entity, *(str(p) for p in parts))


def _catalog(bundle: Bundle, client: str) -> dict[str, dict]:
    response = bundle.get(ROUTES["payItems"], clientId=client)
    items = response.body or [] if response is not None and response.ok else []
    return {str(item["code"]).strip(): item for item in items if not is_blank(item.get("code"))}


def _per_employee(bundle: Bundle, client: str, legal: str, employee: str) -> tuple[Response | None, dict[str, tuple[int, dict]]]:
    response = bundle.get(ROUTES["employeePayItems"], clientId=client, legalId=legal, employeeId=employee)
    entries = {}
    if response is not None and response.ok:
        for index, entry in enumerate(response.body or []):
            entries.setdefault(str(entry.get("id")), (index, entry))  # row: employeePayItems [].id
    return response, entries


def _legal_entries(bundle: Bundle) -> list[tuple[Response, int, dict]]:
    found = []
    for page in bundle.all(ROUTES["legalPayItems"]):
        if page.ok:
            found += [(page, index, entry) for index, entry in enumerate((page.body or {}).get("results") or [])]
    return found


def _is_deduction(joined: tuple[int, dict] | None) -> bool | None:
    """True for a Deduction per-employee entry, False for another type, None when not joined."""
    if joined is None:
        return None
    return str(joined[1].get("payItemType") or "").strip() == "Deduction"  # row: employeePayItems [].payItemType


def normalize(bundle: Bundle) -> list[DeductionSetup]:
    records = []
    catalogs: dict[str, dict] = {}
    for page, index, entry in _legal_entries(bundle):
        client, legal = page.params.get("clientId"), page.params.get("legalId")
        employee = str(entry.get("employeeId"))  # row: legalPayItems results[].employeeId
        _, entries = _per_employee(bundle, client, legal, employee)
        joined = entries.get(str(entry.get("id")))
        if _is_deduction(joined) is False:
            continue  # Earning or Memo Calc: kept on the employee (employee_extras)
        if client not in catalogs:
            catalogs[client] = _catalog(bundle, client)
        records.append(_candidate(bundle.tenant_id, client, legal, employee, index, entry, joined, catalogs[client]))
    for response in bundle.all(ROUTES["garnishments"]):
        if response.ok:  # a 404 with an empty body means none (D-011)
            for index, item in enumerate(response.body or []):
                records.append(_garnishment(bundle.tenant_id, response.params, index, item))
    return records


def _candidate(tenant: str, client: str, legal: str, employee: str, index: int, entry: dict, joined: tuple[int, dict] | None,
               catalog: dict[str, dict]) -> DeductionSetup:
    ctx = Ctx(PROVIDER)
    entry_id = str(entry.get("id"))  # row: legalPayItems results[].id
    key = f"legalPayItems:results[{index}]"
    ctx.diag(DiagnosticCode.UNVALIDATED_SOURCE, Severity.WARNING,
             "Legal-level pay item assignment: the best available setup source, not validated as the employee's deductions.",
             None, "D-017")
    sources = [source(ROUTES["legalPayItems"], f"/results/{index}")]
    code = entry.get("payItemCode")  # row: legalPayItems results[].payItemCode
    item = catalog.get(str(code).strip()) if not is_blank(code) else None
    fields: dict[str, Any] = {"amount": NP}
    if item is not None and str(item.get("payItemType") or "").strip() == "Deduction":
        fields["deduction_code_id"] = _id(tenant, EntityType.DEDUCTION_CODE, legal, item.get("id"))
        benefit = item.get("systemBenefitType")
        fields["category"] = ctx.coded("isolved.system_benefit_type", benefit, "category", column="category")
        fields["tax_treatment"] = ctx.coded("isolved.system_benefit_type", benefit, "tax_treatment", column="tax_treatment")
    else:
        fields["deduction_code_id"] = NP
        if not is_blank(code):
            ctx.diag(DiagnosticCode.UNKNOWN_CODE, Severity.WARNING,
                     f"Pay item code {str(code).strip()!r} is not a Deduction item of the client catalog; not linked.",
                     "deduction_code_id", "D-066")
    if joined is None:
        ctx.diag(DiagnosticCode.SOURCE_UNAVAILABLE, Severity.WARNING,
                 "No per-employee pay item with this id: the entry's type and calculation parameters are unknown.", None, "D-081")
    else:
        position, detail = joined
        sources.append(source(ROUTES["employeePayItems"], f"/{position}"))
        for number, param in enumerate(detail.get("calcParams") or []):
            kind = str(param.get("paramType") or "").strip()  # row: employeePayItems [].calcParams[].paramType
            if kind == "Amount":
                fields["amount"] = ctx.number(param.get("paramValue"), "amount")  # row: employeePayItems [].calcParams[].paramValue
            else:
                ctx.keep(f"employeePayItems:[{position}].calcParams[{number}]", param)
                ctx.diag(DiagnosticCode.UNIT_UNVERIFIED, Severity.INFO,
                         f"Calculation parameter {kind!r}: scale and meaning undocumented; kept raw.", None, "CANONICAL_MODEL 6.2")
    # row: legalPayItems results[].payItemId; results[].referenceNumber; results[].scheduleOverride; results[].balance
    for name in LEGAL_KEPT:
        ctx.keep(f"{key}.{name}", entry.get(name))
    return build(
        DeductionSetup,
        id=_id(tenant, EntityType.DEDUCTION_SETUP, legal, entry_id),
        provider=Provider.ISOLVED,
        tenant_id=tenant,
        source_ids={"clientId": client, "legalId": legal, "id": entry_id},
        sources=sources,
        company_id=_id(tenant, EntityType.COMPANY, legal),
        employee_id=_id(tenant, EntityType.EMPLOYEE, legal, employee),
        source_basis="candidate_assignment",
        deduction_code=build(Reference, source_id=NP, code=ctx.text(code),
                             name=ctx.text(entry.get("payItemName"))),  # row: legalPayItems results[].payItemName
        start_date=ctx.date(entry.get("startDate"), DateRole.PERIOD_START, "start_date"),  # row: legalPayItems results[].startDate
        stop_date=ctx.date(entry.get("stopDate"), DateRole.PERIOD_END, "stop_date"),  # row: legalPayItems results[].stopDate
        currency=USD,
        **fields,
        diagnostics=ctx.diagnostics,
        provider_extensions=ctx.extensions,
        sensitive_provider_extensions=ctx.sensitive_extensions,
    )


def _garnishment(tenant: str, params: dict, index: int, item: dict) -> DeductionSetup:
    ctx = Ctx(PROVIDER)
    client, legal, employee = params.get("clientId"), params.get("legalId"), params.get("employeeId")
    garnishment_id = str(item.get("id"))  # row: garnishments [].id
    key = f"garnishments:[{index}]"
    payee = item.get("garnishmentPayee") or {}
    state = item.get("state") or {}
    linked = [build(
        Reference,
        source_id=ctx.text(entry.get("id")),  # row: garnishments [].selectedDeductions[].id
        code=NP,
        name=ctx.text(entry.get("payItemTitle")),  # row: garnishments [].selectedDeductions[].payItemTitle
    ) for entry in item.get("selectedDeductions") or []]
    ctx.keep(f"{key}.garnishmentPayee.id", payee.get("id"))  # row: garnishments [].garnishmentPayee.id
    ctx.keep(f"{key}.state.id", state.get("id"))  # row: garnishments [].state.id
    ctx.keep(f"{key}.thirdPartyPayee", without_links(item.get("thirdPartyPayee")), sensitive=True)  # row: garnishments [].thirdPartyPayee.*
    ctx.rest(key, item, GARNISHMENT_HANDLED)  # row: garnishments [].*
    return build(
        DeductionSetup,
        id=_id(tenant, EntityType.DEDUCTION_SETUP, legal, "garnishment", garnishment_id),
        provider=Provider.ISOLVED,
        tenant_id=tenant,
        source_ids={"clientId": client, "legalId": legal, "employeeId": employee, "garnishmentId": garnishment_id},
        sources=[source(ROUTES["garnishments"], f"/{index}")],
        company_id=_id(tenant, EntityType.COMPANY, legal),
        employee_id=_id(tenant, EntityType.EMPLOYEE, legal, employee),
        source_basis="documented_assignment",
        deduction_code_id=NP,
        deduction_code=NP,
        category=route_code("garnishment", "garnishments"),
        status=ctx.coded("isolved.garnishment_status", item.get("status"), "status"),  # row: garnishments [].status
        start_date=ctx.date(item.get("startDate"), DateRole.PERIOD_START, "start_date"),  # row: garnishments [].startDate
        stop_date=ctx.date(item.get("stopDate"), DateRole.PERIOD_END, "stop_date"),  # row: garnishments [].stopDate
        garnishment=build(
            GarnishmentDetails,
            type=ctx.coded("isolved.garnishment_type", (item.get("garnishmentType") or {}).get("id"), "garnishment.type"),  # row: garnishments [].garnishmentType.id
            description=ctx.text(item.get("garnishmentDescription")),  # row: garnishments [].garnishmentDescription
            case_number=ctx.text(item.get("caseNumber")),  # row: garnishments [].caseNumber
            payee=ctx.text(payee.get("payeeName")),  # row: garnishments [].garnishmentPayee.payeeName
            order_sequence=ctx.integer(item.get("garnishmentSequence"), "garnishment.order_sequence"),  # row: garnishments [].garnishmentSequence
            issuing_state=ctx.text(state.get("stateName")),  # row: garnishments [].state.stateName
            amount=ctx.number(item.get("amount"), "garnishment.amount"),  # row: garnishments [].amount
            percent=ctx.number(item.get("percent"), "garnishment.percent"),  # row: garnishments [].percent
            percent_basis=ctx.coded("isolved.garnishment_basis", item.get("percentageOf"), "garnishment.percent_basis"),  # row: garnishments [].percentageOf
            maximum_amount=ctx.number(item.get("maximumAmount"), "garnishment.maximum_amount"),  # row: garnishments [].maximumAmount
            maximum_percent=ctx.number(item.get("maximumPercent"), "garnishment.maximum_percent"),  # row: garnishments [].maximumPercent
            per_period_limit=NP,
            fee_amount=ctx.number(item.get("feeAmount"), "garnishment.fee_amount"),  # row: garnishments [].feeAmount
            exemption_amount=NP,
            arrears_balance=ctx.number(item.get("arrearsBalance"), "garnishment.arrears_balance"),  # row: garnishments [].arrearsBalance
            remaining_balance=ctx.number(item.get("remainingBalance"), "garnishment.remaining_balance"),  # row: garnishments [].remainingBalance
            apply_arrears=ctx.flag(item.get("applyArrears"), "garnishment.apply_arrears"),  # row: garnishments [].applyArrears
            medical_support_required=ctx.flag(item.get("isMedicalSupportRequired"), "garnishment.medical_support_required"),  # row: garnishments [].isMedicalSupportRequired
            linked_deductions=linked,
        ),
        currency=USD,
        diagnostics=ctx.diagnostics,
        provider_extensions=ctx.extensions,
        sensitive_provider_extensions=ctx.sensitive_extensions,
    )


def paged_short(short: str, page: Response) -> str:
    """The key prefix of leaves taken from one page of a paged route into a record that gathers
    several pages: the page keeps two pages' ``results[0]`` apart (D-090 review). The page is the
    zero-based ``page`` parameter as sent (D-092)."""
    number = page.params.get("page")
    return short if number is None else f"{short}(page={number})"


def employee_extras(bundle: Bundle, client: str, legal: str, employee_id: str) -> dict[str, Any]:
    """Legal pay item entries of one employee whose per-employee entry is not a Deduction (Earning,
    Memo Calc), with that entry's payItemType and calcParams, as extension leaves for the Employee
    (deduction_setup notes; SENT_TO_EMPLOYEE). The entries come from every page of the legal list,
    so their keys carry the page (``legalPayItems(page=0):results[2].payItemCode``)."""
    holder = Ctx(PROVIDER)
    response, entries = _per_employee(bundle, client, legal, employee_id)
    for page, index, entry in _legal_entries(bundle):
        if (page.params.get("clientId"), page.params.get("legalId"), str(entry.get("employeeId"))) != (client, legal, employee_id):
            continue
        joined = entries.get(str(entry.get("id")))
        if _is_deduction(joined) is not False:
            continue
        for name in LEGAL_TO_EMPLOYEE:
            holder.keep(f"{paged_short('legalPayItems', page)}:results[{index}].{name}", entry.get(name))
        position, detail = joined
        holder.keep(f"employeePayItems:[{position}].payItemType", detail.get("payItemType"))
        holder.keep(f"employeePayItems:[{position}].calcParams", detail.get("calcParams"))
    return holder.extensions
