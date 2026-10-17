"""UKG Ready payroll: one PayrollRun per payroll (cid, payroll id), one Paycheck per pay statement (cid, statement id).

Follows ``mappings/data/ukg-ready/payroll.json`` (D-050 to D-056, D-089). The payrolls list is the
run source; the detail adds date_finalized (D-081). Statements are enumerated by the statement list
and read from the detail; a statement links to the payroll it is read under and to that payroll's
EIN. An EIN the payroll names that ``lookup/eins`` lacks is still a company tax entity, built from
the references with ``reference_only`` (D-094; D-088 had made it a link problem). Statuses travel
with every record: OPEN is calculated, not finalized (D-030).

- Each tax item gives an employee line when it sends an ``ee_`` field and an employer line when it
  sends an ``er_`` field, sharing source_line_id (D-051); a side without an amount keeps its wages.
- A deduction that sends ``er_amount`` also gives an employer contribution line on the same code.
- A missing amount is null, never zero (D-053). net_pay is derived from the Check and Direct
  Deposit lines only when there is one and every one has an amount, else null with
  reconciliation_incomplete; the other totals are not provided (D-052).
- A listed statement without a detail response gives no record: the list's other fields are not a
  source (table rows), and a Paycheck needs its employee.
"""
from decimal import Decimal
from typing import Any

from ...canonical.diagnostics import DiagnosticCode, Severity
from ...canonical.ids import EntityType, Provider, canonical_id
from ...canonical.parsing import DateRole
from ...canonical.parts import Reference
from ...canonical.payroll import DeductionLine, EarningLine, EmployerContributionLine, Paycheck, PaymentLine, PayPeriod, PayrollRun, TaxLine
from ...employees.bundle import Bundle
from ...employees.common import NP, Ctx, build, is_blank
from ..common import code_index, copied, source
from . import company

PROVIDER = "ukg-ready"
TABLE = "payroll"
C = "/v2/companies/{cid}"
ROUTES = {
    "payrolls": f"{C}/payrolls",
    "payroll": f"{C}/payrolls/{{id}}",
    "batches": f"{C}/payrolls/{{id}}/batches",
    "statements": f"{C}/payrolls/{{id}}/pay-statements",
    "statement": f"{C}/payrolls/{{id}}/pay-statements/{{id}}",
    "lookup/eins": f"{C}/lookup/eins",  # the EIN currency (not a payroll table row)
}
PAYROLL_HANDLED = {"id", "name", "type", "status", "pay_date", "start_date", "end_date", "ein", "_links"}
STATEMENT_HANDLED = {"id", "employee", "status", "type", "pay_date", "pay_period_start", "pay_period_end", "earnings", "deductions",
                     "taxes", "payments"}
CASH = {"check", "direct_deposit"}
SIDES = {"employee": "ee_", "employer": "er_"}


def _id(tenant: str, entity: EntityType, *parts: Any) -> str:
    return canonical_id(Provider.UKG_READY, tenant, entity, *(str(p) for p in parts))


def _ref_id(tenant: str, entity: EntityType, cid: str, raw: Any) -> Any:
    return NP if is_blank(raw) else _id(tenant, entity, cid, raw)


def normalize(bundle: Bundle) -> list:
    earning_codes, deduction_codes = code_index(company.normalize(bundle))
    records: list = []
    for listing in bundle.all(ROUTES["payrolls"]):
        if not listing.ok:
            continue
        cid = listing.params.get("cid")
        currencies = _currencies(bundle, cid)
        for index, item in enumerate((listing.body or {}).get("payrolls") or []):
            payroll = item.get("id")  # row: payrolls payrolls[].id
            if is_blank(payroll):
                continue
            payroll = str(payroll)
            run = _run(bundle, cid, payroll, index, item)
            records.append(run)
            statements = bundle.get(ROUTES["statements"], cid=cid, id=payroll)
            listed = (statements.body or {}).get("pay_statements") or [] if statements is not None and statements.ok else []
            for entry in listed:
                statement = entry.get("id")  # row: statements pay_statements[].id
                detail = bundle.get(ROUTES["statement"], cid=cid, payroll_id=payroll, id=str(statement))
                if detail is not None and detail.ok and isinstance(detail.body, dict):
                    currency = currencies.get(str((item.get("ein") or {}).get("id")))
                    records.append(_paycheck(bundle.tenant_id, cid, payroll, str(statement), run, detail.body, currency, earning_codes, deduction_codes))
    return records


def _currencies(bundle: Bundle, cid: str) -> dict[str, str]:
    response = bundle.get(ROUTES["lookup/eins"], cid=cid)
    items = (response.body or {}).get("items") or [] if response is not None and response.ok else []
    return {str(i.get("id")): str(i["ein_currency_code"]).strip() for i in items if not is_blank(i.get("ein_currency_code"))}


def _run(bundle: Bundle, cid: str, payroll: str, index: int, item: dict) -> PayrollRun:
    tenant, ctx = bundle.tenant_id, Ctx(PROVIDER)
    key = f"payrolls:payrolls[{index}]"
    sources = [source(ROUTES["payrolls"], f"/payrolls/{index}")]
    kind = item.get("type") or {}
    ctx.keep(f"{key}.type.id", kind.get("id"))  # row: payrolls payrolls[].type.id
    ctx.rest(key, item, PAYROLL_HANDLED)  # row: payrolls payrolls[].*
    detail = bundle.get(ROUTES["payroll"], cid=cid, id=payroll)
    if detail is not None and detail.ok and isinstance(detail.body, dict):
        sources.append(source(ROUTES["payroll"]))
        # row: payroll id
        finalized = ctx.date(detail.body.get("date_finalized"), DateRole.EVENT, "finalized_date")  # row: payroll date_finalized
    else:
        finalized = ctx.unavailable("finalized_date", "The payroll detail is not in the input or did not succeed: the finalized date is unknown.")
    batches = bundle.get(ROUTES["batches"], cid=cid, id=payroll)
    if batches is not None and batches.ok:
        ctx.keep("batches:batches", (batches.body or {}).get("batches"))  # row: batches batches[].**
    ein = (item.get("ein") or {}).get("id")  # row: payrolls payrolls[].ein.id
    return build(
        PayrollRun,
        id=_id(tenant, EntityType.PAYROLL_RUN, cid, payroll),
        provider=Provider.UKG_READY,
        tenant_id=tenant,
        source_ids={"companyId": cid, "payrollId": payroll},
        sources=sources,
        company_id=_id(tenant, EntityType.COMPANY, cid),
        tax_entity_id=_ref_id(tenant, EntityType.TAX_ENTITY, cid, ein),
        name=ctx.text(item.get("name")),  # row: payrolls payrolls[].name
        run_type=ctx.coded("ukg-ready.payroll_type", kind.get("display_name"), "run_type"),  # row: payrolls payrolls[].type.display_name
        status=ctx.coded("ukg-ready.payroll_status", item.get("status"), "status"),  # row: payrolls payrolls[].status
        pay_date=ctx.date(item.get("pay_date"), DateRole.EVENT, "pay_date"),  # row: payrolls payrolls[].pay_date
        scheduled_pay_date=NP,
        run_number=NP,
        run_date=NP,
        finalized_date=finalized,
        pay_periods=[build(
            PayPeriod,
            pay_group_id=NP,  # payrolls name no pay period profile (table notes)
            period_start=ctx.date(item.get("start_date"), DateRole.PERIOD_START, "pay_periods[0].period_start"),  # row: payrolls payrolls[].start_date
            period_end=ctx.date(item.get("end_date"), DateRole.PERIOD_END, "pay_periods[0].period_end"),  # row: payrolls payrolls[].end_date
            period_number=NP,
        )],
        diagnostics=ctx.diagnostics,
        provider_extensions=ctx.extensions,
        sensitive_provider_extensions=ctx.sensitive_extensions,
    )


def _paycheck(tenant: str, cid: str, payroll: str, listed: str, run: PayrollRun, body: dict, currency: str | None,
              earning_codes: dict, deduction_codes: dict) -> Paycheck:
    ctx = Ctx(PROVIDER)
    # The listed id when the detail sends none, so two such statements never share an id.
    statement = listed if is_blank(body.get("id")) else str(body.get("id"))  # row: statement id
    kind = body.get("type") or {}
    ctx.keep("statement:type.id", kind.get("id"))  # row: statement type.id
    ctx.rest("statement:", body, STATEMENT_HANDLED)  # row: statement calcUpto; emptyEarning; messages[].**
    deductions, contributions = _deductions(ctx, tenant, cid, body, deduction_codes)
    payments = _payments(ctx, body)
    net_pay, derived = _net_pay(ctx, payments)
    return build(
        Paycheck,
        id=_id(tenant, EntityType.PAYCHECK, cid, statement),
        provider=Provider.UKG_READY,
        tenant_id=tenant,
        source_ids={"companyId": cid, "payrollId": payroll, "payStatementId": statement},
        sources=[source(ROUTES["statement"])],
        company_id=_id(tenant, EntityType.COMPANY, cid),
        employee_id=_id(tenant, EntityType.EMPLOYEE, cid, (body.get("employee") or {}).get("account_id")),  # row: statement employee.account_id
        payroll_run_id=run.id,  # the payroll the statement is read under (table notes)
        tax_entity_id=run.tax_entity_id or NP,
        pay_group_id=NP,
        check_number=NP,
        kind=ctx.coded("ukg-ready.statement_type", kind.get("display_name"), "kind"),  # row: statement type.display_name
        status=ctx.coded("ukg-ready.statement_status", body.get("status"), "status"),  # row: statement status
        is_manual_check=NP,
        pay_date=ctx.date(body.get("pay_date"), DateRole.EVENT, "pay_date"),  # row: statement pay_date
        period_start=ctx.date(body.get("pay_period_start"), DateRole.PERIOD_START, "period_start"),  # row: statement pay_period_start
        period_end=ctx.date(body.get("pay_period_end"), DateRole.PERIOD_END, "period_end"),  # row: statement pay_period_end
        processed_date=NP,
        reverses_paycheck_id=NP,
        void_date=NP,
        earnings=_earnings(ctx, tenant, cid, body, earning_codes),
        deductions=deductions,
        taxes=_taxes(ctx, body),
        employer_contributions=contributions,
        benefit_lines=NP,
        retirement=NP,
        payments=payments,
        gross_pay=NP,  # UKG states no totals; cash classification is provisional (D-052)
        gross_wages=NP,
        total_earnings=NP,
        net_pay=net_pay,
        derived_totals=derived,
        currency=currency or NP,
        diagnostics=ctx.diagnostics,
        provider_extensions=ctx.extensions,
        sensitive_provider_extensions=ctx.sensitive_extensions,
    )


def _earnings(ctx: Ctx, tenant: str, cid: str, body: dict, codes: dict) -> list[EarningLine]:
    lines = []
    for index, item in enumerate(body.get("earnings") or []):
        where, key = f"earnings[{index}]", f"statement:earnings[{index}]"
        code = item.get("earning") or {}
        code_id = _ref_id(tenant, EntityType.EARNING_CODE, cid, code.get("id"))  # row: statement earnings[].earning.id
        linked = codes.get(code_id) if isinstance(code_id, str) else None
        ctx.keep(f"{key}.earning.external_id", code.get("external_id"))  # row: statement earnings[].earning.external_id
        # row: statement earnings[].quantity; earnings[].**
        ctx.rest(key, item, {"id", "earning", "type_name", "hours", "base_rate", "ee_amount"})
        lines.append(build(
            EarningLine,
            source_line_id=ctx.text(item.get("id")),  # row: statement earnings[].id
            earning_code_id=code_id,
            # row: statement earnings[].earning.code; earnings[].earning.name
            earning_code=build(Reference, source_id=NP, code=ctx.text(code.get("code")), name=ctx.text(code.get("name"))),
            pay_class=ctx.coded("ukg-ready.earning_type_name", item.get("type_name"), f"{where}.pay_class"),  # row: statement earnings[].type_name
            is_cash=copied(ctx, linked, "is_cash", f"{where}.is_cash"),
            rate_class=copied(ctx, linked, "rate_class", f"{where}.rate_class"),
            hours=ctx.ms_to_hours(item.get("hours"), f"{where}.hours"),  # row: statement earnings[].hours
            hours_worked=NP,
            units=NP,  # quantity has no documented unit (kept raw)
            rate=ctx.number(item.get("base_rate"), f"{where}.rate"),  # row: statement earnings[].base_rate
            amount=ctx.number(item.get("ee_amount"), f"{where}.amount"),  # row: statement earnings[].ee_amount
        ))
    return lines


def _deductions(ctx: Ctx, tenant: str, cid: str, body: dict, codes: dict) -> tuple[list, list]:
    lines, contributions = [], []
    for index, item in enumerate(body.get("deductions") or []):
        where, key = f"deductions[{index}]", f"statement:deductions[{index}]"
        code = item.get("deduction") or {}
        code_id = _ref_id(tenant, EntityType.DEDUCTION_CODE, cid, code.get("id"))  # row: statement deductions[].deduction.id
        linked = codes.get(code_id) if isinstance(code_id, str) else None
        reference = build(Reference, source_id=NP, code=ctx.text(code.get("code")), name=ctx.text(code.get("name")))  # row: statement deductions[].deduction.code; deductions[].deduction.name
        ctx.keep(f"{key}.deduction.external_id", code.get("external_id"))  # row: statement deductions[].deduction.external_id
        # row: statement deductions[].type_name; deductions[].quantity; deductions[].base_rate; deductions[].vendor.*
        # row: statement deductions[].ee_gross_subject_wage; deductions[].ee_gross_wage; deductions[].ee_subject_wage; deductions[].**
        ctx.rest(key, item, {"id", "deduction", "ee_amount", "er_amount"})
        line_id = ctx.text(item.get("id"))  # row: statement deductions[].id
        lines.append(build(
            DeductionLine,
            source_line_id=line_id,
            deduction_code_id=code_id,
            deduction_code=reference,
            category=copied(ctx, linked, "category", f"{where}.category"),
            tax_treatment=copied(ctx, linked, "tax_treatment", f"{where}.tax_treatment"),
            is_catch_up=copied(ctx, linked, "is_catch_up", f"{where}.is_catch_up"),
            plan=NP,
            amount=ctx.number(item.get("ee_amount"), f"{where}.amount"),  # row: statement deductions[].ee_amount
        ))
        if "er_amount" in item:
            contributions.append(build(
                EmployerContributionLine,
                source_line_id=line_id,
                plan=reference,
                deduction_code_id=code_id,
                earning_code_id=NP,
                amount=ctx.number(item.get("er_amount"), f"employer_contributions[{len(contributions)}].amount"),  # row: statement deductions[].er_amount
            ))
    return lines, contributions


def _taxes(ctx: Ctx, body: dict) -> list[TaxLine]:
    lines = []
    for index, item in enumerate(body.get("taxes") or []):
        key = f"statement:taxes[{index}]"
        tax = item.get("company_tax") or {}
        label = tax.get("name")  # row: statement taxes[].company_tax.name
        # row: statement taxes[].company_tax.abbrev; taxes[].company_tax.external_id
        for field in ("abbrev", "external_id"):
            ctx.keep(f"{key}.company_tax.{field}", tax.get(field))
        # row: statement taxes[].ee_gross_subject_wage; taxes[].er_gross_subject_wage; taxes[].type_name; taxes[].batch.*
        ctx.rest(key, item, {"id", "company_tax", "ee_amount", "er_amount", "ee_subject_wage", "er_subject_wage", "ee_gross_wage", "er_gross_wage"})
        for paid_by, prefix in SIDES.items():
            if not any(name.startswith(prefix) for name in item):
                continue
            where = f"taxes[{len(lines)}]"
            lines.append(build(
                TaxLine,
                source_line_id=ctx.text(item.get("id")),  # row: statement taxes[].id
                # row: statement taxes[].company_tax.id; taxes[].company_tax.code
                tax_code=build(Reference, source_id=ctx.text(tax.get("id")), code=ctx.text(tax.get("code")), name=ctx.text(label)),
                tax_type=ctx.coded("ukg-ready.tax_label", label, f"{where}.tax_type", column="tax_type"),
                jurisdiction_level=ctx.coded("ukg-ready.tax_label", label, f"{where}.jurisdiction_level", column="jurisdiction_level"),
                jurisdiction=NP,  # no field states it (table notes)
                paid_by=paid_by,
                # row: statement taxes[].ee_amount; taxes[].er_amount
                amount=ctx.number(item.get(f"{prefix}amount"), f"{where}.amount"),
                # row: statement taxes[].ee_subject_wage; taxes[].er_subject_wage
                taxable_wages=ctx.number(item.get(f"{prefix}subject_wage"), f"{where}.taxable_wages"),
                # row: statement taxes[].ee_gross_wage; taxes[].er_gross_wage
                gross_wages=ctx.number(item.get(f"{prefix}gross_wage"), f"{where}.gross_wages"),
                exempt_wages=NP,
                over_limit_wages=NP,
                rate=NP,
            ))
    return lines


def _payments(ctx: Ctx, body: dict) -> list[PaymentLine]:
    lines = []
    for index, item in enumerate(body.get("payments") or []):
        ctx.rest(f"statement:payments[{index}]", item, {"id", "type_name", "ee_amount"})  # row: statement payments[].hours; payments[].quantity; payments[].batch.*
        lines.append(build(
            PaymentLine,
            source_line_id=ctx.text(item.get("id")),  # row: statement payments[].id
            method=ctx.coded("ukg-ready.payment_type", item.get("type_name"), f"payments[{index}].method"),  # row: statement payments[].type_name
            amount=ctx.number(item.get("ee_amount"), f"payments[{index}].amount"),  # row: statement payments[].ee_amount
            direct_deposit_id=NP,
            routing_last4=NP,
            account_last4=NP,
        ))
    return lines


def _net_pay(ctx: Ctx, payments: list[PaymentLine]) -> tuple[Any, list[str]]:
    """Check plus Direct Deposit amounts, derived only when there is such a line and every one has
    an amount; a payment of unknown type blocks it too (D-052, D-053)."""
    methods = [line.method.value.value for line in payments]
    cash = [line for line, method in zip(payments, methods) if method in CASH]
    if "unknown" in methods:
        problem = "a payment line has an unknown type"
    elif not cash:
        problem = "the statement has no Check or Direct Deposit line"
    elif any(line.amount is None for line in cash):
        problem = "a Check or Direct Deposit line has no amount"
    else:
        return sum((line.amount for line in cash), Decimal(0)), ["net_pay"]
    ctx.diag(DiagnosticCode.RECONCILIATION_INCOMPLETE, Severity.WARNING, f"Net pay not derived: {problem}.", "net_pay", "D-052")
    return NP, []
