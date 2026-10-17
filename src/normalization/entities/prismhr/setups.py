"""PrismHR deduction setups (D-048), following ``mappings/data/prismhr/deduction_setup.json``.

Per employee: one setup per getDeductions item (documented_assignment). Loans and garnishment
details join the setup they belong to, or make their own; scheduled deductions and retirement
loans make their own. Ids are (client, employee, deduction code); a code repeated in one
response adds the position, and records that are not plain setups carry a marker (D-088):
``scheduled`` + position, ``loan`` + loan id, ``retirement_loan`` + loan id, ``garnishment`` +
deduction code, ``garnishment_presence``. Setups whose source sends no type copy category, tax
treatment and catch-up from the client deduction code they link to (D-047, D-088).

Garnishments (D-088): details refused (403) leave each setup classified as garnishment with its
garnishment part null and source_unavailable; only an employee with no such setup and
checkForGarnishments enrolled gets a presence_only setup. Arrears entries join the setup with the
same code; an entry matching none goes to the employee (``employee_extras``, SENT_TO_EMPLOYEE).
Loan dates documented as YYYY-DD-MM are read both ways (D-083, ``loan_date``).
"""
import re
from collections import Counter
from datetime import date
from typing import Any

from ...canonical.deductions import DeductionSetup, EmployerMatch, GarnishmentDetails, LoanDetails
from ...canonical.diagnostics import DiagnosticCode, Severity
from ...canonical.ids import EntityType, Provider, canonical_id
from ...canonical.parsing import OPEN_END_SENTINELS, OPEN_START_SENTINELS, DateRole
from ...canonical.parts import Reference
from ...employees.bundle import Bundle
from ...employees.common import NA, NP, Ctx, Null, build, code_entry, is_blank
from ..common import USD, prismhr_ok, route_code, source

PROVIDER = "prismhr"
TABLE = "deduction_setup"
ROUTES = {
    "getDeductions": "/deductions/v1/getDeductions",
    "getScheduledDeductions": "/employee/v1/getScheduledDeductions",
    "getEmployeeLoans": "/deductions/v1/getEmployeeLoans",
    "getRetirementLoans": "/benefits/v1/getRetirementLoans",
    "getDeductionArrears": "/deductions/v1/getDeductionArrears",
    "getGarnishmentDetails": "/deductions/v1/getGarnishmentDetails",
    "checkForGarnishments": "/employee/v1/checkForGarnishments",
    "getClientCodes": "/clientMaster/v1/getClientCodes",  # classification of the linked code (not a table row)
}
PER_EMPLOYEE = ("getDeductions", "getScheduledDeductions", "getEmployeeLoans", "getDeductionArrears",
                "getGarnishmentDetails", "checkForGarnishments")
CATCH_UP_TYPES = {"KC", "KCR"}
GARNISHMENT = "garnishment"
DEDUCTION_HANDLED = {"deductionCode", "description", "deductionType", "deductionMethod", "amount", "usePercent", "period",
                     "loanOrGarnishId", "benefitPlanId", "limit", "maximum", "basis", "trackArrears", "startDate",
                     "stopDate", "matchMethod", "matchAmount", "matchDescription"}


def _id(tenant: str, entity: EntityType, *parts: str) -> str:
    return canonical_id(Provider.PRISMHR, tenant, entity, *parts)


# ---- D-083 loan dates -------------------------------------------------------------------

_YMD = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


def loan_date(ctx: Ctx, raw: Any, role: DateRole, field: str, key: str) -> Any:
    """A getEmployeeLoans date documented as YYYY-DD-MM (D-083). The sentinel check runs first on
    the raw value (D-025). Then: one valid reading, or both readings the same date, gives that
    date; two different valid dates give null with unparseable_value and the raw value kept in
    provider_extensions under ``key``; no valid reading gives null with unparseable_value."""
    if is_blank(raw):
        return NP
    text = str(raw).strip()
    if text in OPEN_START_SENTINELS or text in OPEN_END_SENTINELS:
        return ctx.date(text, role, field)
    match = _YMD.match(text)
    readings: set[date] = set()
    if match:
        year, first, second = (int(part) for part in match.groups())
        for month, day in ((first, second), (second, first)):
            try:
                readings.add(date(year, month, day))
            except ValueError:
                pass
    if len(readings) == 1:
        return readings.pop()
    if len(readings) == 2:
        ctx.keep(key, text)
        ctx.diag(DiagnosticCode.UNPARSEABLE_VALUE, Severity.ERROR,
                 f"Loan date {text!r} is documented as YYYY-DD-MM and reads as two different dates; not used (D-083).",
                 field, "D-083")
        return NP
    ctx.diag(DiagnosticCode.UNPARSEABLE_VALUE, Severity.ERROR,
             f"Loan date {text!r} is a valid date neither as YYYY-MM-DD nor as YYYY-DD-MM (D-083).", field, "D-083")
    return NP


# ---- records --------------------------------------------------------------------------


class Draft:
    """One setup being assembled from several routes."""

    def __init__(self, tenant: str, client: str, employee: str, parts: tuple[str, ...], ids: dict[str, str], basis: str,
                 origin: str) -> None:
        self.ctx = Ctx(PROVIDER)
        self.origin = origin  # the route the setup comes from
        self.code: str | None = None
        self.sources: list = []
        self.fields: dict[str, Any] = {
            "id": _id(tenant, EntityType.DEDUCTION_SETUP, client, employee, *parts),
            "provider": Provider.PRISMHR,
            "tenant_id": tenant,
            "source_ids": {"clientId": client, "employeeId": employee, **ids},
            "company_id": _id(tenant, EntityType.COMPANY, client),
            "employee_id": _id(tenant, EntityType.EMPLOYEE, client, employee),
            "source_basis": basis,
            "currency": USD,
        }

    def unstable(self) -> None:
        self.ctx.diag(DiagnosticCode.UNSTABLE_ID, Severity.WARNING,
                      "The id rests on the item's position in the response, not on a provider id.", None, "D-088")

    def finish(self) -> DeductionSetup:
        return build(DeductionSetup, **self.fields, sources=self.sources, diagnostics=self.ctx.diagnostics,
                     provider_extensions=self.ctx.extensions, sensitive_provider_extensions=self.ctx.sensitive_extensions)


class Employee:
    """The source responses of one employee and the setups made from them."""

    def __init__(self, bundle: Bundle, client: str, employee: str, code_types: dict[str, str], retirement: list) -> None:
        self.bundle, self.client, self.employee, self.tenant = bundle, client, employee, bundle.tenant_id
        self.code_types = code_types
        self.retirement = retirement  # (index in the client response, item) of this employee
        self.drafts: list[Draft] = []
        self.unmatched_arrears: dict[str, Any] = {}

    def response(self, name: str):
        return self.bundle.get(ROUTES[name], clientId=self.client, employeeId=self.employee)

    def body(self, name: str) -> Any:
        response = self.response(name)
        return response.body if prismhr_ok(response) else None

    def code_id(self, code: str) -> str:
        return _id(self.tenant, EntityType.DEDUCTION_CODE, self.client, code)

    def classify_from_code(self, draft: Draft, code: Any) -> None:
        """Category, tax treatment and catch-up copied from the linked client code (D-047, D-088)."""
        kind = self.code_types.get(str(code).strip()) if not is_blank(code) else None
        if kind is None:
            return
        _classify(draft, kind)

    # ---- getDeductions ----------------------------------------------------------------

    def deductions(self) -> None:
        items = (self.body("getDeductions") or {}).get("employeeDeductions") or {}
        items = items.get("deduction") or []
        counts = Counter(str(item.get("deductionCode") or "").strip() for item in items)
        for position, item in enumerate(items):
            code = str(item.get("deductionCode") or "").strip()  # row: getDeductions employeeDeductions.deduction[].deductionCode
            repeated = not code or counts[code] > 1
            parts = (code, str(position)) if code and repeated else ((str(position),) if not code else (code,))
            ids = {"deductionCode": code} if code else {}
            draft = Draft(self.tenant, self.client, self.employee, parts, {**ids, **({"position": str(position)} if repeated else {})},
                          "documented_assignment", "getDeductions")
            if repeated:
                draft.unstable()
            draft.code = code or None
            draft.sources.append(source(ROUTES["getDeductions"], f"/employeeDeductions/deduction/{position}"))
            _deduction(draft, self, item, position)
            self.drafts.append(draft)

    # ---- scheduled deductions ---------------------------------------------------------

    def scheduled(self) -> None:
        body = self.body("getScheduledDeductions") or {}
        # row: getScheduledDeductions clientId; employeeId
        for position, item in enumerate(body.get("scheduledDeduction") or []):
            draft = Draft(self.tenant, self.client, self.employee, ("scheduled", str(position)), {"position": str(position)},
                          "documented_assignment", "getScheduledDeductions")
            draft.unstable()
            draft.sources.append(source(ROUTES["getScheduledDeductions"], f"/scheduledDeduction/{position}"))
            ctx, fields = draft.ctx, draft.fields
            code = item.get("deductionCode")  # row: getScheduledDeductions scheduledDeduction[].deductionCode
            draft.code = str(code).strip() if not is_blank(code) else None
            fields["deduction_code_id"] = self.code_id(draft.code) if draft.code else NP
            fields["deduction_code"] = build(Reference, source_id=NP, code=draft.code or NP, name=NP) if draft.code else NP
            self.classify_from_code(draft, code)
            fields["amount"] = ctx.number(item.get("amount"), "amount")  # row: getScheduledDeductions scheduledDeduction[].amount
            fields["status"] = ctx.coded("prismhr.scheduled_deduction_status", item.get("status"), "status")  # row: getScheduledDeductions scheduledDeduction[].status
            fields["start_date"] = ctx.date(item.get("startDate"), DateRole.PERIOD_START, "start_date")  # row: getScheduledDeductions scheduledDeduction[].startDate
            fields["stop_date"] = ctx.date(item.get("stopDate"), DateRole.PERIOD_END, "stop_date")  # row: getScheduledDeductions scheduledDeduction[].stopDate
            key = f"getScheduledDeductions:scheduledDeduction[{position}]"
            ctx.keep(f"{key}.checkStubDescription", item.get("checkStubDescription"))  # row: getScheduledDeductions scheduledDeduction[].checkStubDescription
            ctx.keep(f"{key}.cutbackPayeeCode", item.get("cutbackPayeeCode"), sensitive=True)  # row: getScheduledDeductions scheduledDeduction[].cutbackPayeeCode
            self.drafts.append(draft)

    # ---- loans ------------------------------------------------------------------------

    def loans(self) -> None:
        by_ref = {d.fields["loan"].loan_ref: d for d in self.drafts
                  if isinstance(d.fields.get("loan"), LoanDetails) and d.fields["loan"].loan_ref}
        body = self.body("getEmployeeLoans") or {}
        # row: getEmployeeLoans clientId; employeeId
        for index, item in enumerate(body.get("employeeLoanDetail") or []):
            loan_id = str(item.get("loanId") or "").strip()  # row: getEmployeeLoans employeeLoanDetail[].loanId
            draft = by_ref.get(loan_id) if loan_id else None
            if draft is None:
                draft = Draft(self.tenant, self.client, self.employee, ("loan", loan_id or str(index)),
                              {"loanId": loan_id} if loan_id else {"position": str(index)}, "documented_assignment", "getEmployeeLoans")
                if not loan_id:
                    draft.unstable()
                code = item.get("deductionCode")  # row: getEmployeeLoans employeeLoanDetail[].deductionCode
                draft.code = str(code).strip() if not is_blank(code) else None
                draft.fields["deduction_code_id"] = self.code_id(draft.code) if draft.code else NP
                draft.fields["deduction_code"] = build(Reference, source_id=NP, code=draft.code or NP, name=NP) if draft.code else NP
                self.classify_from_code(draft, code)
                self.drafts.append(draft)
            draft.sources.append(source(ROUTES["getEmployeeLoans"], f"/employeeLoanDetail/{index}"))
            ctx, key = draft.ctx, f"getEmployeeLoans:employeeLoanDetail[{index}]"
            start = loan_date(ctx, item.get("startDate"), DateRole.PERIOD_START, "loan.deduction_start_date", f"{key}.startDate")  # row: getEmployeeLoans employeeLoanDetail[].startDate
            stop = loan_date(ctx, item.get("stopDate"), DateRole.PERIOD_END, "stop_date", f"{key}.stopDate")  # row: getEmployeeLoans employeeLoanDetail[].stopDate
            draft.fields["loan"] = build(
                LoanDetails,
                loan_ref=loan_id or NP,
                plan_code=NP,
                loan_date=loan_date(ctx, item.get("loanDate"), DateRole.EVENT, "loan.loan_date", f"{key}.loanDate"),  # row: getEmployeeLoans employeeLoanDetail[].loanDate
                loan_amount=ctx.number(item.get("loanAmount"), "loan.loan_amount"),  # row: getEmployeeLoans employeeLoanDetail[].loanAmount
                payment_amount=ctx.number(item.get("paymentAmount"), "loan.payment_amount"),  # row: getEmployeeLoans employeeLoanDetail[].paymentAmount
                payback_amount=ctx.number(item.get("paybackAmount"), "loan.payback_amount"),  # row: getEmployeeLoans employeeLoanDetail[].paybackAmount
                paid_to_date=ctx.number(item.get("paidAmount"), "loan.paid_to_date"),  # row: getEmployeeLoans employeeLoanDetail[].paidAmount
                deduction_start_date=start,
            )
            if draft.origin == "getEmployeeLoans":
                draft.fields["start_date"] = start
            _fill(draft, "stop_date", stop)
            # row: getEmployeeLoans employeeLoanDetail[].paymentFreq; employeeLoanDetail[].loanReason
            # row: getEmployeeLoans employeeLoanDetail[].glOverrideAccount; employeeLoanDetail[].paymentHistory[].*
            for name in ("paymentFreq", "loanReason", "glOverrideAccount", "paymentHistory"):
                ctx.keep(f"{key}.{name}", item.get(name))

    def retirement_loans(self) -> None:
        by_ref = {d.fields["loan"].loan_ref: d for d in self.drafts
                  if isinstance(d.fields.get("loan"), LoanDetails) and d.fields["loan"].loan_ref and d.origin == "getDeductions"}
        for index, item in self.retirement:
            loan_id = str(item.get("loanId") or "").strip()  # row: getRetirementLoans retirementLoan[].loanId
            draft = by_ref.get(loan_id) if loan_id else None
            own = draft is None
            if own:
                draft = Draft(self.tenant, self.client, self.employee, ("retirement_loan", loan_id or str(index)),
                              {"loanId": loan_id} if loan_id else {"position": str(index)}, "documented_assignment", "getRetirementLoans")
                if not loan_id:
                    draft.unstable()
                draft.fields["deduction_code_id"] = NP  # retirement loans send no code (table notes)
                draft.fields["category"] = route_code("retirement_loan", "retirementLoan")
                self.drafts.append(draft)
            draft.sources.append(source(ROUTES["getRetirementLoans"], f"/retirementLoan/{index}"))
            ctx = draft.ctx
            payment = ctx.number(item.get("paymentAmount"), "loan.payment_amount")  # row: getRetirementLoans retirementLoan[].paymentAmount
            start = ctx.date(item.get("deductionStarts"), DateRole.PERIOD_START, "loan.deduction_start_date")  # row: getRetirementLoans retirementLoan[].deductionStarts
            draft.fields["loan"] = build(
                LoanDetails,
                loan_ref=loan_id or NP,
                plan_code=ctx.text(item.get("planId401k")),  # row: getRetirementLoans retirementLoan[].planId401k
                loan_date=ctx.date(item.get("loanDate"), DateRole.EVENT, "loan.loan_date"),  # row: getRetirementLoans retirementLoan[].loanDate
                loan_amount=ctx.number(item.get("loanAmount"), "loan.loan_amount"),  # row: getRetirementLoans retirementLoan[].loanAmount
                payment_amount=payment,
                payback_amount=ctx.number(item.get("paybackAmount"), "loan.payback_amount"),  # row: getRetirementLoans retirementLoan[].paybackAmount
                paid_to_date=ctx.number(item.get("amtPaidBackToDate"), "loan.paid_to_date"),  # row: getRetirementLoans retirementLoan[].amtPaidBackToDate
                deduction_start_date=start,
            )
            if own:
                draft.fields["amount"] = payment
                draft.fields["start_date"] = start
            key = f"getRetirementLoans:retirementLoan[{index}]"
            # row: getRetirementLoans retirementLoan[].employeeId
            # row: getRetirementLoans retirementLoan[].interestRate; retirementLoan[].loanReason; retirementLoan[].tpaLoanId
            # row: getRetirementLoans retirementLoan[].overridePaymentAmt; retirementLoan[].overridePayFrom; retirementLoan[].overridePayTo
            # row: getRetirementLoans retirementLoan[].paidbackAdjust[].*
            for name in ("interestRate", "loanReason", "tpaLoanId", "overridePaymentAmt", "overridePayFrom", "overridePayTo", "paidbackAdjust"):
                ctx.keep(f"{key}.{name}", item.get(name))

    # ---- garnishments -----------------------------------------------------------------

    def garnishments(self) -> None:
        response = self.response("getGarnishmentDetails")
        garnishment_drafts = [d for d in self.drafts if _category(d) == GARNISHMENT]
        if prismhr_ok(response) or (response is not None and response.status == 404):
            details = (response.body or {}).get("garnishmentDetails") or [] if prismhr_ok(response) else []
            self._details(details)
            return
        # Details refused (403) or not in the input (D-088).
        for draft in garnishment_drafts:
            draft.fields["garnishment"] = draft.ctx.unavailable(
                "garnishment", "getGarnishmentDetails is refused or not in the input: the order details are unknown.", "D-048")
        flag = self.body("checkForGarnishments")
        if flag is None or garnishment_drafts or flag.get("enrolled") is not True:  # row: checkForGarnishments enrolled
            return
        draft = Draft(self.tenant, self.client, self.employee, ("garnishment_presence",), {}, "presence_only", "checkForGarnishments")
        draft.sources.append(source(ROUTES["checkForGarnishments"]))
        draft.ctx.unavailable(None, "checkForGarnishments says a garnishment exists; getGarnishmentDetails is refused, "
                                    "so nothing else is known (D-048).", "D-048")
        draft.fields["category"] = route_code(GARNISHMENT, "checkForGarnishments")
        active = flag.get("active")  # row: checkForGarnishments active
        draft.fields["status"] = route_code("active" if active else "inactive", str(active).lower()) if isinstance(active, bool) else NP
        self.drafts.append(draft)

    def _details(self, details: list[dict]) -> None:
        by_code: dict[str, Draft] = {}
        for draft in self.drafts:
            if draft.origin == "getDeductions" and draft.code and draft.code not in by_code:
                by_code[draft.code] = draft
        unmatched = Counter(str(d.get("deductionCode") or "").strip() for d in details
                            if str(d.get("deductionCode") or "").strip() not in by_code)
        for index, detail in enumerate(details):
            code = str(detail.get("deductionCode") or "").strip()  # row: getGarnishmentDetails garnishmentDetails[].deductionCode
            draft = by_code.get(code) if code else None
            if draft is None:
                repeated = not code or unmatched[code] > 1
                parts = ("garnishment", code, str(index)) if code and repeated else (("garnishment", str(index)) if not code else ("garnishment", code))
                ids = {"deductionCode": code} if code else {}
                draft = Draft(self.tenant, self.client, self.employee, parts, {**ids, **({"position": str(index)} if repeated else {})},
                              "documented_assignment", "getGarnishmentDetails")
                if repeated:
                    draft.unstable()
                draft.code = code or None
                draft.fields["deduction_code_id"] = self.code_id(code) if code else NP
                draft.fields["deduction_code"] = build(Reference, source_id=NP, code=code, name=NP) if code else NP
                if code in self.code_types:
                    self.classify_from_code(draft, code)
                else:
                    draft.fields["category"] = route_code(GARNISHMENT, "getGarnishmentDetails")
                self.drafts.append(draft)
            draft.sources.append(source(ROUTES["getGarnishmentDetails"], f"/garnishmentDetails/{index}"))
            _garnishment(draft, detail, index)

    # ---- arrears ----------------------------------------------------------------------

    def arrears(self) -> None:
        body = self.body("getDeductionArrears") or {}
        by_code: dict[str, Draft] = {}
        for draft in sorted(self.drafts, key=lambda d: d.origin != "getDeductions"):
            if draft.code and draft.code not in by_code:
                by_code[draft.code] = draft
        for index, entry in enumerate(body.get("deductionArrears") or []):
            key = f"getDeductionArrears:deductionArrears[{index}]"
            draft = by_code.get(str(entry.get("dedCode") or "").strip())
            if draft is None:
                holder = Ctx(PROVIDER)
                holder.rest(key, entry, excluded={"checksum"})
                self.unmatched_arrears.update(holder.extensions)
                continue
            draft.sources.append(source(ROUTES["getDeductionArrears"], f"/deductionArrears/{index}"))
            draft.ctx.rest(key, entry, excluded={"checksum"})  # row: getDeductionArrears deductionArrears[].*

    def build(self) -> None:
        self.deductions()
        self.scheduled()
        self.loans()
        self.retirement_loans()
        self.garnishments()
        self.arrears()


def _category(draft: Draft) -> str | None:
    category = draft.fields.get("category")
    return category["value"] if isinstance(category, dict) else None


def _classify(draft: Draft, kind: Any) -> None:
    """category, tax_treatment and is_catch_up from a PrismHR deduction type (D-047)."""
    ctx = draft.ctx
    draft.fields["category"] = ctx.coded("prismhr.deduction_type", kind, "category", column="category")
    draft.fields["tax_treatment"] = ctx.coded("prismhr.deduction_type", kind, "tax_treatment", column="tax_treatment")
    listed = not is_blank(kind) and code_entry(PROVIDER, "prismhr.deduction_type", str(kind).strip()) is not None
    draft.fields["is_catch_up"] = str(kind).strip() in CATCH_UP_TYPES if listed else NP


def _fill(draft: Draft, name: str, value: Any) -> None:
    """Set a field another route may already hold: the first known value stays; a different
    second value gives conflicting_sources."""
    current = draft.fields.get(name)
    if current is None or isinstance(current, Null):
        if not (isinstance(value, Null) and current is not None):
            draft.fields[name] = value
    elif not isinstance(value, Null) and value != current:
        draft.ctx.diag(DiagnosticCode.CONFLICTING_SOURCES, Severity.WARNING,
                       f"Another route gives a different {name}; the first is kept.", name)


def _deduction(draft: Draft, employee: Employee, item: dict, position: int) -> None:
    ctx, fields = draft.ctx, draft.fields
    key = f"getDeductions:employeeDeductions.deduction[{position}]"
    code = draft.code
    fields["deduction_code_id"] = employee.code_id(code) if code else NP
    fields["deduction_code"] = build(
        Reference, source_id=NP, code=code or NP,
        name=ctx.text(item.get("description")),  # row: getDeductions employeeDeductions.deduction[].description
    )
    _classify(draft, item.get("deductionType"))  # row: getDeductions employeeDeductions.deduction[].deductionType
    fields["calc_method"] = ctx.coded("prismhr.deduction_calc_method", item.get("deductionMethod"), "calc_method")  # row: getDeductions employeeDeductions.deduction[].deductionMethod
    use_percent = item.get("usePercent")  # row: getDeductions employeeDeductions.deduction[].usePercent
    value = ctx.number(item.get("amount"), "amount")  # row: getDeductions employeeDeductions.deduction[].amount
    if use_percent is True:
        fields["amount"], fields["percent"] = NA, value
    elif use_percent is False:
        fields["amount"], fields["percent"] = value, NA
    else:
        fields["amount"], fields["percent"] = NP, NP
        ctx.keep(f"{key}.amount", item.get("amount"))
    fields["period_numbers"] = _periods(ctx, item.get("period"))  # row: getDeductions employeeDeductions.deduction[].period
    ref = item.get("loanOrGarnishId")  # row: getDeductions employeeDeductions.deduction[].loanOrGarnishId
    if not is_blank(ref) and _category(draft) == GARNISHMENT:
        ctx.keep(f"{key}.loanOrGarnishId", ref)
    elif not is_blank(ref):
        fields["loan"] = build(LoanDetails, loan_ref=str(ref).strip(), plan_code=NP, loan_date=NP, loan_amount=NP,
                               payment_amount=NP, payback_amount=NP, paid_to_date=NP, deduction_start_date=NP)
    plan = item.get("benefitPlanId")  # row: getDeductions employeeDeductions.deduction[].benefitPlanId
    fields["benefit_enrollment_id"] = NP if is_blank(plan) else _id(
        employee.tenant, EntityType.BENEFIT_ENROLLMENT, employee.client, employee.employee, str(plan).strip())
    fields["per_period_limit"] = ctx.number(item.get("limit"), "per_period_limit")  # row: getDeductions employeeDeductions.deduction[].limit
    fields["maximum"] = ctx.number(item.get("maximum"), "maximum")  # row: getDeductions employeeDeductions.deduction[].maximum
    fields["maximum_period"] = ctx.coded("prismhr.limit_basis", item.get("basis"), "maximum_period")  # row: getDeductions employeeDeductions.deduction[].basis
    fields["track_arrears"] = ctx.flag(item.get("trackArrears"), "track_arrears")  # row: getDeductions employeeDeductions.deduction[].trackArrears
    fields["start_date"] = ctx.date(item.get("startDate"), DateRole.PERIOD_START, "start_date")  # row: getDeductions employeeDeductions.deduction[].startDate
    fields["stop_date"] = ctx.date(item.get("stopDate"), DateRole.PERIOD_END, "stop_date")  # row: getDeductions employeeDeductions.deduction[].stopDate
    fields["status"] = NP  # getDeductions sends no status (table notes)
    fields["employer_match"] = _match(ctx, item)
    # row: getDeductions employeeDeductions.deduction[].lastDedPerAdj; employeeDeductions.deduction[].glOverrideAcct
    # row: getDeductions employeeDeductions.deduction[].mandatory; employeeDeductions.deduction[].cutbackPayeeCode
    # row: getDeductions employeeDeductions.deduction[].rateTableId; employeeDeductions.deduction[].rateTier; employeeDeductions.deduction[].achOption
    ctx.rest(key, item, DEDUCTION_HANDLED, sensitive={"cutbackPayeeCode"}, excluded={"detailsChecksum"})


def _periods(ctx: Ctx, raw: Any) -> Any:
    """Each digit is a pay period of the month (1 to 5) in which the deduction is taken."""
    if is_blank(raw):
        return NP
    text = str(raw).strip()
    if not text.isdigit() or any(not 1 <= int(digit) <= 5 for digit in text):
        ctx.diag(DiagnosticCode.UNPARSEABLE_VALUE, Severity.ERROR, "Period is not a list of pay period digits 1 to 5.", "period_numbers")
        return NP
    return sorted({int(digit) for digit in text})


def _match(ctx: Ctx, item: dict) -> Any:
    method = item.get("matchMethod")  # row: getDeductions employeeDeductions.deduction[].matchMethod
    description = item.get("matchDescription")  # row: getDeductions employeeDeductions.deduction[].matchDescription
    if is_blank(method) and is_blank(description):
        return NP
    raw = item.get("matchAmount")  # row: getDeductions employeeDeductions.deduction[].matchAmount
    code = str(method or "").strip().upper()
    amount = ctx.number(raw, "employer_match.amount") if code == "F" else (NA if code == "P" else NP)
    percent = ctx.number(raw, "employer_match.percent") if code == "P" else (NA if code == "F" else NP)
    return build(EmployerMatch, method=ctx.coded("prismhr.match_method", method, "employer_match.method"),
                 amount=amount, percent=percent, description=ctx.text(description))


def _garnishment(draft: Draft, detail: dict, index: int) -> None:
    ctx = draft.ctx
    draft.fields["garnishment"] = build(
        GarnishmentDetails,
        type=ctx.coded("prismhr.garnishment_category", detail.get("category"), "garnishment.type"),  # row: getGarnishmentDetails garnishmentDetails[].category
        description=ctx.text(detail.get("issuingAuthority")),  # row: getGarnishmentDetails garnishmentDetails[].issuingAuthority
        case_number=ctx.text(detail.get("docketNumber")),  # row: getGarnishmentDetails garnishmentDetails[].docketNumber
        payee=ctx.text(detail.get("payee")),  # row: getGarnishmentDetails garnishmentDetails[].payee
        order_sequence=NP,
        issuing_state=NP,  # stateId is a state case number, not a state (table row)
        amount=ctx.number(detail.get("totalGarnishmentAmount"), "garnishment.amount"),  # row: getGarnishmentDetails garnishmentDetails[].totalGarnishmentAmount
        percent=ctx.number(detail.get("percentNet"), "garnishment.percent"),  # row: getGarnishmentDetails garnishmentDetails[].percentNet
        percent_basis=ctx.coded("prismhr.garnishment_percent_of", detail.get("percentOf"), "garnishment.percent_basis"),  # row: getGarnishmentDetails garnishmentDetails[].percentOf
        maximum_amount=NP,
        maximum_percent=ctx.number(detail.get("maxPercent"), "garnishment.maximum_percent"),  # row: getGarnishmentDetails garnishmentDetails[].maxPercent
        per_period_limit=ctx.number(detail.get("payPeriodLimit"), "garnishment.per_period_limit"),  # row: getGarnishmentDetails garnishmentDetails[].payPeriodLimit
        fee_amount=ctx.number(detail.get("garnishmentFee"), "garnishment.fee_amount"),  # row: getGarnishmentDetails garnishmentDetails[].garnishmentFee
        exemption_amount=ctx.number(detail.get("exemptAmt"), "garnishment.exemption_amount"),  # row: getGarnishmentDetails garnishmentDetails[].exemptAmt
        arrears_balance=NP,
        remaining_balance=NP,
        apply_arrears=NP,
        medical_support_required=NP,
        linked_deductions=NP,
    )
    _fill(draft, "start_date", ctx.date(detail.get("startDate"), DateRole.PERIOD_START, "start_date"))  # row: getGarnishmentDetails garnishmentDetails[].startDate
    _fill(draft, "stop_date", ctx.date(detail.get("stopDate"), DateRole.PERIOD_END, "stop_date"))  # row: getGarnishmentDetails garnishmentDetails[].stopDate
    key = f"getGarnishmentDetails:garnishmentDetails[{index}]"
    handled = {"category", "issuingAuthority", "docketNumber", "payee", "totalGarnishmentAmount", "percentNet", "percentOf",
               "maxPercent", "payPeriodLimit", "garnishmentFee", "exemptAmt", "startDate", "stopDate", "deductionCode"}
    # row: getGarnishmentDetails garnishmentDetails[].stateId; garnishmentDetails[].annotation1; garnishmentDetails[].annotation2
    # row: getGarnishmentDetails garnishmentDetails[].*
    ctx.rest(key, detail, handled, sensitive={"stateId", "annotation1", "annotation2"})


# ---- entry points ---------------------------------------------------------------------


def _retirement(bundle: Bundle) -> dict[tuple[str, str], list]:
    """getRetirementLoans items (per client) by (client, employee), with their index."""
    found: dict[tuple[str, str], list] = {}
    for response in bundle.all(ROUTES["getRetirementLoans"]):
        if not prismhr_ok(response):
            continue
        for index, item in enumerate(response.body.get("retirementLoan") or []):
            employee = str(item.get("employeeId") or "").strip()
            if employee:
                found.setdefault((response.params.get("clientId"), employee), []).append((index, item))
    return found


def _code_types(bundle: Bundle, client: str) -> dict[str, str]:
    """Deduction type of each client deduction code (getClientCodes), for classification (D-047)."""
    codes = bundle.get(ROUTES["getClientCodes"], clientId=client)
    items = ((codes.body or {}).get("clientCodes") or {}).get("deductionCode") or [] if prismhr_ok(codes) else []
    return {str(i.get("id")).strip(): i.get("type") for i in items if not is_blank(i.get("id")) and not is_blank(i.get("type"))}


def _employee(bundle: Bundle, client: str, employee: str, retirement: dict) -> Employee:
    built = Employee(bundle, client, employee, _code_types(bundle, client), retirement.get((client, employee), []))
    built.build()
    return built


def normalize(bundle: Bundle) -> list[DeductionSetup]:
    """Setups of every (client, employee) any setup route names."""
    retirement = _retirement(bundle)
    keys = {(r.params["clientId"], r.params["employeeId"]) for name in PER_EMPLOYEE
            for r in bundle.all(ROUTES[name]) if r.params.get("clientId") and r.params.get("employeeId")}
    employees = [_employee(bundle, client, employee, retirement) for client, employee in sorted(keys | set(retirement))]
    return [draft.finish() for employee in employees for draft in employee.drafts]


def employee_extras(bundle: Bundle, client: str, employee_id: str) -> dict[str, Any]:
    """Arrears entries of one employee that match no setup, as extension leaves for the Employee
    (deduction_setup notes; SENT_TO_EMPLOYEE)."""
    return _employee(bundle, client, employee_id, _retirement(bundle)).unmatched_arrears
