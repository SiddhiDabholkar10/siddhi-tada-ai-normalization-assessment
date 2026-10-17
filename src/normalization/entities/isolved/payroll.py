"""isolved payroll: one PayrollRun per run history entry (legal, entry id), one Paycheck per check (legal, check id).

Follows ``mappings/data/isolved/payroll.json`` (D-050 to D-056, D-089).

- Runs come from each pay group's full run history, never a year-filtered one (D-050). A 404 on
  that route has no confirmed "no records" meaning (D-011): the pay group's runs are unknown.
- Checks carry no run id. A check links to the run of its legal with the same pay date and run
  number when exactly one such run is completed. A match with only a run not processed, or with
  several completed runs, is not linked (conflicting_sources); no match is not provided, or
  source_unavailable when a run history of the legal could not be read.
- The legal check list enumerates checks; the detail is the record source (D-016). A listed check
  whose detail is missing or empty (``[]``, D-082) becomes a Paycheck with its ids only and
  source_unavailable, so it does not disappear (D-089).
- Memo earnings whose label is in isolved.memo_label are employer contribution lines (D-055,
  inferred); others stay earning lines with class memo. Lines copy the catalog code's
  classification (D-047, D-066); garnishment lines are category garnishment from the route.
- Net pay is compared with the check and deposit lines (D-089).
"""
from datetime import date
from typing import Any

from ...canonical.diagnostics import DiagnosticCode, Severity
from ...canonical.ids import EntityType, Provider, canonical_id
from ...canonical.parsing import DateRole
from ...canonical.parts import Reference
from ...canonical.payroll import BenefitLine, DeductionLine, EarningLine, EmployerContributionLine, Paycheck, PaymentLine, PayPeriod, PayrollRun, TaxLine
from ...employees.bundle import Bundle
from ...employees.common import NP, Ctx, build, code_entry, is_blank
from ..common import USD, check_net_pay, code_index, copied, route_code, source
from . import company
from .company import without_links

PROVIDER = "isolved"
TABLE = "payroll"
API = "/api/clients/{clientId}/legals/{legalId}"
ROUTES = {
    "runHistory": f"{API}/paygroupId/{{paygroupId}}/payrollRunHistory",
    "checks": f"{API}/checks",
    "check": f"{API}/employees/{{employeeId}}/checks/{{id}}",
}
RUN_HANDLED = {"id", "runNumber", "payrollRunType", "status", "payDate", "scheduledPayDate", "runDate", "periodBeginDate",
               "periodEndDate", "payPeriod"}
CHECK_HANDLED = {"id", "employeeId", "checkNumber", "checkDate", "periodBeginDate", "periodEndDate", "checkTypeDescription",
                 "payrollRunNumber", "grossPay", "grossWages", "netPay", "checkAmount", "directDeposits", "earnings", "deductions",
                 "garnishments", "taxes", "benefits"}
SNAPSHOT = {"employeeName", "employeeNumber", "employeeSSN", "employeeAddress1", "employeeAddress2", "employeeCity", "employeeState",
            "employeeZipCode", "employeeFederalFilingStatus", "employeeFederalExemptions", "employeeFederalAddlAmountOrPercent",
            "employeeStateFilingStatus", "employeeStateExemptions", "employeeStateAddlAmountOrPercent", "taxCategories",
            "vertexResidentGeoCode", "vertexWorkGeoCode", "vertexSchoolDistrictCode"}
LINE_HANDLED = {"id", "itemCode", "itemDescription", "checkDollars", "sequence"}


def _id(tenant: str, entity: EntityType, *parts: Any) -> str:
    return canonical_id(Provider.ISOLVED, tenant, entity, *(str(p) for p in parts))


class Runs:
    """Run history entries of the bundle, indexed for the check join (D-050)."""

    def __init__(self, bundle: Bundle) -> None:
        self.records: list[PayrollRun] = []
        self.by_key: dict[tuple[str, date, int], list[tuple[str, str]]] = {}
        self.unread_legals: set[str] = set()
        for response in bundle.all(ROUTES["runHistory"]):
            legal = response.params.get("legalId")
            if not response.ok:
                self.unread_legals.add(legal)
                continue
            for index, entry in enumerate(response.body or []):
                run = _run(bundle.tenant_id, response.params, index, entry)
                self.records.append(run)
                if run.pay_date is not None and run.run_number is not None:
                    status = run.status.value.value if run.status is not None else "unknown"
                    self.by_key.setdefault((legal, run.pay_date, run.run_number), []).append((run.id, status))

    def join(self, ctx: Ctx, legal: str, pay_date: Any, run_number: Any) -> Any:
        if not isinstance(pay_date, date) or not isinstance(run_number, int):
            return NP
        matches = self.by_key.get((legal, pay_date, run_number), [])
        completed = [run_id for run_id, status in matches if status == "completed"]
        if len(completed) == 1:
            return completed[0]
        if len(completed) > 1:
            ctx.diag(DiagnosticCode.CONFLICTING_SOURCES, Severity.WARNING,
                     f"{len(completed)} completed runs share this pay date and run number; the check is not linked.", "payroll_run_id", "D-050")
        elif matches:
            ctx.diag(DiagnosticCode.CONFLICTING_SOURCES, Severity.WARNING,
                     "The check's pay date and run number match only a run that is not completed; the check is not linked.",
                     "payroll_run_id", "D-050")
        elif legal in self.unread_legals:
            return ctx.unavailable("payroll_run_id", "A run history of this legal could not be read: the check's run may be there.", "D-011")
        return NP


def normalize(bundle: Bundle) -> list:
    earning_codes, deduction_codes = code_index(company.normalize(bundle))
    runs = Runs(bundle)
    records: list = list(runs.records)
    for page in bundle.all(ROUTES["checks"]):
        if not page.ok:
            continue
        for index, listed in enumerate((page.body or {}).get("results") or []):
            records.append(_paycheck(bundle, page.params, index, listed, runs, earning_codes, deduction_codes))
    return records


def _run(tenant: str, params: dict, index: int, entry: dict) -> PayrollRun:
    ctx = Ctx(PROVIDER)
    legal, group = params.get("legalId"), params.get("paygroupId")
    entry_id = str(entry.get("id"))  # row: runHistory [].id
    ctx.rest(f"runHistory:[{index}]", entry, RUN_HANDLED)  # row: runHistory [].*
    return build(
        PayrollRun,
        id=_id(tenant, EntityType.PAYROLL_RUN, legal, entry_id),
        provider=Provider.ISOLVED,
        tenant_id=tenant,
        source_ids={"clientId": params.get("clientId"), "legalId": legal, "paygroupId": group, "runId": entry_id},
        sources=[source(ROUTES["runHistory"], f"/{index}")],
        company_id=_id(tenant, EntityType.COMPANY, legal),
        tax_entity_id=_id(tenant, EntityType.TAX_ENTITY, legal),
        name=NP,
        run_type=ctx.coded("isolved.run_type", entry.get("payrollRunType"), "run_type"),  # row: runHistory [].payrollRunType
        status=ctx.coded("isolved.run_status", entry.get("status"), "status"),  # row: runHistory [].status
        pay_date=ctx.date(entry.get("payDate"), DateRole.EVENT, "pay_date"),  # row: runHistory [].payDate
        scheduled_pay_date=ctx.date(entry.get("scheduledPayDate"), DateRole.EVENT, "scheduled_pay_date"),  # row: runHistory [].scheduledPayDate
        run_number=ctx.integer(entry.get("runNumber"), "run_number"),  # row: runHistory [].runNumber
        run_date=ctx.date(entry.get("runDate"), DateRole.EVENT, "run_date"),  # row: runHistory [].runDate
        finalized_date=NP,  # not sent (table notes)
        pay_periods=[build(
            PayPeriod,
            pay_group_id=_id(tenant, EntityType.PAY_GROUP, legal, group),  # the route's paygroupId (table notes)
            period_start=ctx.date(entry.get("periodBeginDate"), DateRole.PERIOD_START, "pay_periods[0].period_start"),  # row: runHistory [].periodBeginDate
            period_end=ctx.date(entry.get("periodEndDate"), DateRole.PERIOD_END, "pay_periods[0].period_end"),  # row: runHistory [].periodEndDate
            period_number=ctx.integer(entry.get("payPeriod"), "pay_periods[0].period_number"),  # row: runHistory [].payPeriod
        )],
        diagnostics=ctx.diagnostics,
        provider_extensions=ctx.extensions,
        sensitive_provider_extensions=ctx.sensitive_extensions,
    )


def _paycheck(bundle: Bundle, params: dict, index: int, listed: dict, runs: Runs, earning_codes: dict, deduction_codes: dict) -> Paycheck:
    tenant, ctx = bundle.tenant_id, Ctx(PROVIDER)
    client, legal = params.get("clientId"), params.get("legalId")
    check_id = str(listed.get("id"))  # row: checks results[].id
    employee = str(listed.get("employeeId"))  # row: checks results[].employeeId
    sources = [source(ROUTES["checks"], f"/results/{index}")]
    common: dict[str, Any] = {
        "id": _id(tenant, EntityType.PAYCHECK, legal, check_id),
        "provider": Provider.ISOLVED,
        "tenant_id": tenant,
        "source_ids": {"clientId": client, "legalId": legal, "employeeId": employee, "checkId": check_id},
        "company_id": _id(tenant, EntityType.COMPANY, legal),
        "tax_entity_id": _id(tenant, EntityType.TAX_ENTITY, legal),
        "pay_group_id": NP,  # the check sends none (D-089)
        "currency": USD,
    }
    response = bundle.get(ROUTES["check"], clientId=client, legalId=legal, employeeId=employee, id=check_id)
    body = response.body if response is not None and response.ok else None
    if not isinstance(body, dict):
        found = "is not in the input" if response is None else f"returned {'an empty list' if body == [] else f'HTTP {response.status}'}"
        ctx.unavailable(None, f"The check detail {found}: only the check's ids are known (D-089).", "D-016")
        return build(Paycheck, **common, employee_id=_id(tenant, EntityType.EMPLOYEE, legal, employee), sources=sources,
                     diagnostics=ctx.diagnostics)
    body = without_links(body)  # navigation links are excluded (table rows)
    sources = [source(ROUTES["check"])] + sources
    pay_date = ctx.date(body.get("checkDate"), DateRole.EVENT, "pay_date")  # row: check checkDate
    run_number = ctx.integer(body.get("payrollRunNumber"), "payroll_run_id")  # row: check payrollRunNumber
    earnings, contributions = _earnings(ctx, tenant, legal, body, earning_codes)
    payments = _payments(ctx, body)
    net_pay = ctx.number(body.get("netPay"), "net_pay")  # row: check netPay
    check_net_pay(ctx, net_pay, payments)
    # row: check employeeName; employeeNumber; employeeSSN; employeeAddress1; employeeAddress2; employeeCity; employeeState
    # row: check employeeZipCode; employeeFederalFilingStatus; employeeFederalExemptions; employeeFederalAddlAmountOrPercent
    # row: check employeeStateFilingStatus; employeeStateExemptions; employeeStateAddlAmountOrPercent; taxCategories[].**
    # row: check vertexResidentGeoCode; vertexWorkGeoCode; vertexSchoolDistrictCode
    # row: check *; directDepositAmount; payrollRunType; employeeOrganizations[].*; accruals[].*
    ctx.rest("check:", body, CHECK_HANDLED, sensitive=SNAPSHOT, excluded={"legalCompanyName"})
    return build(
        Paycheck,
        **common,
        employee_id=_id(tenant, EntityType.EMPLOYEE, legal, body.get("employeeId")),  # row: check employeeId
        sources=sources,
        # row: check id
        payroll_run_id=runs.join(ctx, legal, pay_date, run_number),
        check_number=ctx.text(body.get("checkNumber")),  # row: check checkNumber
        kind=ctx.coded("isolved.check_type", body.get("checkTypeDescription"), "kind"),  # row: check checkTypeDescription
        status=NP,  # checks have no status (table notes)
        is_manual_check=NP,
        pay_date=pay_date,
        period_start=ctx.date(body.get("periodBeginDate"), DateRole.PERIOD_START, "period_start"),  # row: check periodBeginDate
        period_end=ctx.date(body.get("periodEndDate"), DateRole.PERIOD_END, "period_end"),  # row: check periodEndDate
        processed_date=NP,
        reverses_paycheck_id=NP,
        void_date=NP,
        earnings=earnings,
        deductions=_deductions(ctx, tenant, legal, body, deduction_codes),
        taxes=_taxes(ctx, body),
        employer_contributions=contributions,
        benefit_lines=[_benefit(ctx, n, item) for n, item in enumerate(body.get("benefits") or [])],
        retirement=NP,  # no retirement block (PrismHR only)
        payments=payments,
        gross_pay=ctx.number(body.get("grossPay"), "gross_pay"),  # row: check grossPay
        gross_wages=ctx.number(body.get("grossWages"), "gross_wages"),  # row: check grossWages
        total_earnings=NP,  # a PrismHR total (D-052)
        net_pay=net_pay,
        diagnostics=ctx.diagnostics,
        provider_extensions=ctx.extensions,
        sensitive_provider_extensions=ctx.sensitive_extensions,
    )


def _earnings(ctx: Ctx, tenant: str, legal: str, body: dict, codes: dict) -> tuple[list, list]:
    """Earning lines, and the employer contribution lines read from memo earnings (D-055)."""
    lines, contributions = [], []
    for index, item in enumerate(body.get("earnings") or []):
        key = f"check:earnings[{index}]"
        item_id = item.get("id")  # row: check earnings[].id
        code_id = NP if is_blank(item_id) else _id(tenant, EntityType.EARNING_CODE, legal, item_id)
        code = codes.get(code_id) if isinstance(code_id, str) else None
        label = item.get("itemDescription")  # row: check earnings[].itemDescription
        memo = item.get("isMemoEarning") is True  # row: check earnings[].isMemoEarning
        # row: check earnings[].*; earnings[].labors[].**
        ctx.rest(key, item, LINE_HANDLED | {"isMemoEarning", "checkHours", "checkUnits"})
        entry = code_entry(PROVIDER, "isolved.memo_label", str(label).strip()) if memo and not is_blank(label) else None
        if entry is not None:
            where = f"employer_contributions[{len(contributions)}]"
            ctx.keep(f"{key}.isMemoEarning", True)  # the flag of a memo-derived line (D-055)
            ctx.diag(DiagnosticCode.INFERRED_MAPPING, Severity.INFO,
                     f"Memo earning {str(label).strip()!r} read as an employer contribution "
                     f"({entry['category']['value']}, inferred from the label and arithmetic).", where, "isolved.memo_label")
            contributions.append(build(
                EmployerContributionLine,
                source_line_id=ctx.text(item.get("sequence")),
                plan=build(Reference, source_id=NP, code=ctx.text(item.get("itemCode")), name=ctx.text(label)),
                deduction_code_id=NP,
                earning_code_id=code_id,
                amount=ctx.number(item.get("checkDollars"), f"{where}.amount"),
            ))
            continue
        where = f"earnings[{len(lines)}]"
        lines.append(build(
            EarningLine,
            source_line_id=ctx.text(item.get("sequence")),  # row: check earnings[].sequence
            earning_code_id=code_id,
            earning_code=build(Reference, source_id=NP, code=ctx.text(item.get("itemCode")), name=ctx.text(label)),  # row: check earnings[].itemCode
            pay_class=route_code("memo", "isMemoEarning") if memo else copied(ctx, code, "pay_class", f"{where}.pay_class"),
            is_cash=copied(ctx, code, "is_cash", f"{where}.is_cash"),
            rate_class=copied(ctx, code, "rate_class", f"{where}.rate_class"),
            hours=ctx.number(item.get("checkHours"), f"{where}.hours"),  # row: check earnings[].checkHours
            hours_worked=NP,
            units=ctx.number(item.get("checkUnits"), f"{where}.units"),  # row: check earnings[].checkUnits
            rate=NP,
            amount=ctx.number(item.get("checkDollars"), f"{where}.amount"),  # row: check earnings[].checkDollars
        ))
    return lines, contributions


def _deductions(ctx: Ctx, tenant: str, legal: str, body: dict, codes: dict) -> list[DeductionLine]:
    lines = []
    for block in ("deductions", "garnishments"):
        for index, item in enumerate(body.get(block) or []):
            where = f"deductions[{len(lines)}]"
            # row: check deductions[].*; garnishments[].*
            ctx.rest(f"check:{block}[{index}]", item, LINE_HANDLED)
            item_id = item.get("id")  # row: check deductions[].id
            if block == "garnishments":
                # The employee's garnishment id, not a pay item (D-095): kept raw, no code reference.
                ctx.keep(f"check:garnishments[{index}].id", item_id)  # row: check garnishments[].id
                item_id = None
            code_id = NP if is_blank(item_id) else _id(tenant, EntityType.DEDUCTION_CODE, legal, item_id)
            code = codes.get(code_id) if isinstance(code_id, str) else None
            lines.append(build(
                DeductionLine,
                source_line_id=ctx.text(item.get("sequence")),  # row: check deductions[].sequence; garnishments[].sequence
                deduction_code_id=code_id,
                # row: check deductions[].itemCode; deductions[].itemDescription; garnishments[].itemCode; garnishments[].itemDescription
                deduction_code=build(Reference, source_id=NP, code=ctx.text(item.get("itemCode")), name=ctx.text(item.get("itemDescription"))),
                category=route_code("garnishment", "garnishments") if block == "garnishments" else copied(ctx, code, "category", f"{where}.category"),
                tax_treatment=copied(ctx, code, "tax_treatment", f"{where}.tax_treatment"),
                is_catch_up=copied(ctx, code, "is_catch_up", f"{where}.is_catch_up"),
                plan=NP,
                amount=ctx.number(item.get("checkDollars"), f"{where}.amount"),  # row: check deductions[].checkDollars; garnishments[].checkDollars
            ))
    return lines


def _taxes(ctx: Ctx, body: dict) -> list[TaxLine]:
    lines = []
    for index, item in enumerate(body.get("taxes") or []):
        where = f"taxes[{len(lines)}]"
        label = item.get("itemDescription")  # row: check taxes[].itemDescription
        employee = item.get("isEmployeeTax")  # row: check taxes[].isEmployeeTax
        if isinstance(employee, bool):
            paid_by = "employee" if employee else "employer"
        else:
            paid_by = "unknown"
            ctx.diag(DiagnosticCode.UNPARSEABLE_VALUE, Severity.WARNING, "isEmployeeTax is not true or false; payer unknown.", f"{where}.paid_by")
        ctx.rest(f"check:taxes[{index}]", item, LINE_HANDLED | {"isEmployeeTax", "checkTaxableWages"})  # row: check taxes[].*
        lines.append(build(
            TaxLine,
            source_line_id=ctx.text(item.get("sequence")),  # row: check taxes[].sequence
            # row: check taxes[].id; taxes[].itemCode
            tax_code=build(Reference, source_id=ctx.text(item.get("id")), code=ctx.text(item.get("itemCode")), name=ctx.text(label)),
            tax_type=ctx.coded("isolved.tax_label", label, f"{where}.tax_type", column="tax_type"),
            jurisdiction_level=ctx.coded("isolved.tax_label", label, f"{where}.jurisdiction_level", column="jurisdiction_level"),
            jurisdiction=NP,  # no field states it (table notes)
            paid_by=paid_by,
            amount=ctx.number(item.get("checkDollars"), f"{where}.amount"),  # row: check taxes[].checkDollars
            taxable_wages=ctx.number(item.get("checkTaxableWages"), f"{where}.taxable_wages"),  # row: check taxes[].checkTaxableWages
            gross_wages=NP,
            exempt_wages=NP,
            over_limit_wages=NP,
            rate=NP,
        ))
    return lines


def _benefit(ctx: Ctx, n: int, item: dict) -> BenefitLine:
    where = f"benefit_lines[{n}]"
    handled = {"benefitTitle", "checkEligibleWages", "checkEmployeeCatchUp", "checkEmployeeDeduction", "checkEmployerContribution",
               "checkMatchEligibleWages"}
    ctx.rest(f"check:benefits[{n}]", item, handled)  # row: check benefits[].*
    return build(
        BenefitLine,
        plan=build(Reference, source_id=NP, code=NP, name=ctx.text(item.get("benefitTitle"))),  # row: check benefits[].benefitTitle
        coverage_period=NP,
        premium_amount=NP,
        premium_cost=NP,
        employee_contribution=NP,
        employee_deduction=ctx.number(item.get("checkEmployeeDeduction"), f"{where}.employee_deduction"),  # row: check benefits[].checkEmployeeDeduction
        employer_contribution=ctx.number(item.get("checkEmployerContribution"), f"{where}.employer_contribution"),  # row: check benefits[].checkEmployerContribution
        catch_up_amount=ctx.number(item.get("checkEmployeeCatchUp"), f"{where}.catch_up_amount"),  # row: check benefits[].checkEmployeeCatchUp
        eligible_wages=ctx.number(item.get("checkEligibleWages"), f"{where}.eligible_wages"),  # row: check benefits[].checkEligibleWages
        match_eligible_wages=ctx.number(item.get("checkMatchEligibleWages"), f"{where}.match_eligible_wages"),  # row: check benefits[].checkMatchEligibleWages
        adjustment_ref=NP,
    )


def _payments(ctx: Ctx, body: dict) -> list[PaymentLine]:
    """checkAmount as one check line (raw_code 'checkAmount', always, even 0), each deposit one line.
    The deposit account is kept whole in the sensitive extension; its form is undocumented, so no
    last 4 is taken (table row)."""
    lines = [build(
        PaymentLine,
        source_line_id=NP,
        method=route_code("check", "checkAmount"),
        amount=ctx.number(body.get("checkAmount"), "payments[0].amount"),  # row: check checkAmount
        direct_deposit_id=NP,
        routing_last4=NP,
        account_last4=NP,
    )]
    for index, item in enumerate(body.get("directDeposits") or []):
        key = f"check:directDeposits[{index}]"
        ctx.keep(f"{key}.account", item.get("account"), sensitive=True)  # row: check directDeposits[].account
        ctx.keep(f"{key}.itemDescription", item.get("itemDescription"))  # row: check directDeposits[].itemDescription
        lines.append(build(
            PaymentLine,
            source_line_id=ctx.text(item.get("id")),  # row: check directDeposits[].id
            method=route_code("direct_deposit", "directDeposits"),
            amount=ctx.number(item.get("depositAmount"), f"payments[{len(lines)}].amount"),  # row: check directDeposits[].depositAmount
            direct_deposit_id=NP,  # the line id is not shown to be a deposit id (table notes)
            routing_last4=NP,
            account_last4=NP,
        ))
    return lines
