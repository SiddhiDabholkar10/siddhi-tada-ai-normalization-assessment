"""PrismHR payroll: one PayrollRun per batch (client, batchId), one Paycheck per voucher (client, voucherId).

Follows ``mappings/data/prismhr/payroll.json`` (D-050 to D-056, D-089). The batch list is the run
source; batch info adds the description and the period number of each pay group (D-081). Voucher
pages are read for every batch. Both records link to the client's single tax entity.

- Run type and paycheck kind are separate lists: batch R is Scheduled, voucher R Regular (D-033).
- A reversal voucher points to the voucher it reverses (voidVoucherId); arrears vouchers are full
  records with their benefit and contribution lines (D-033).
- Hours vs units by the pay code's payReason (unit rule, CANONICAL_MODEL 8.3); a line whose code is
  unknown keeps hoursUnits raw. Lines without their own classification copy the code's (D-047).
- A missing amount is null, never zero (D-053); net pay is compared with the check and deposit
  lines (D-089).
"""
from typing import Any

from ...canonical.diagnostics import DiagnosticCode, Severity
from ...canonical.ids import EntityType, Provider, canonical_id
from ...canonical.parsing import DateRole
from ...canonical.parts import Reference
from ...canonical.payroll import (
    BenefitLine,
    DeductionLine,
    EarningLine,
    EmployerContributionLine,
    Paycheck,
    PaymentLine,
    PayPeriod,
    PayrollRun,
    RetirementBreakdown,
    TaxLine,
)
from ...employees.bundle import Bundle
from ...employees.common import NA, NP, Ctx, build, code_entry, is_blank, is_masked, visible_last4
from ..common import USD, check_net_pay, code_index, copied, prismhr_ok, route_code, source
from . import company
from .company import CATCH_UP_TYPES

PROVIDER = "prismhr"
TABLE = "payroll"
ROUTES = {
    "getBatchListByDate": "/payroll/v1/getBatchListByDate",
    "getBatchInfo": "/payroll/v1/getBatchInfo",
    "getPayrollVoucherForBatch": "/payroll/v1/getPayrollVoucherForBatch",
}
# The demo sends the voucher list as payrollVoucher; the spec documents payrollVouchers (D-062).
VOUCHER_KEYS = ("payrollVoucher", "payrollVouchers")
VOUCHER_HANDLED = {
    "voucherId", "batchId", "employeeId", "payGroup", "checkNumber", "checkNum", "type", "status", "isManualCheck", "payDate",
    "payPeriodStart", "payPeriodEnd", "dateProcessed", "voidDate", "voidVoucherId", "earnAmount", "totalEarnings", "netPay",
    "checkAmt", "earning", "otherEarningsDetail", "deduction", "otherDeduction", "employeeTax", "companyTax", "benefit",
    "employerContributions", "retirement", "directDeposit",
}
SENSITIVE = {"bankAccount", "checkAccountACH", "taxFilingStatus"}
RETIREMENT_TYPED = {"planId", "planYearPeriod", "baseEarnings", "employerMatchingContributions", "employerNonElectiveContributions",
                    "employerSafeHarborMatchType1", "employerSafeHarborMatchType2", "peoMatchingContribution"}


def _id(tenant: str, entity: EntityType, *parts: str) -> str:
    return canonical_id(Provider.PRISMHR, tenant, entity, *parts)


def _code_id(tenant: str, entity: EntityType, client: str, raw: Any) -> Any:
    return NP if is_blank(raw) else _id(tenant, entity, client, str(raw).strip())


def normalize(bundle: Bundle) -> list:
    earning_codes, deduction_codes = code_index(company.normalize(bundle))
    records: list = []
    seen: set[tuple[str, str]] = set()
    for listing in bundle.all(ROUTES["getBatchListByDate"]):
        if not prismhr_ok(listing):
            continue
        client = listing.params.get("clientId")
        for index, item in enumerate(listing.body.get("batchList") or []):
            batch = item.get("batchId")  # row: getBatchListByDate batchList[].batchId
            if is_blank(batch) or (client, str(batch).strip()) in seen:
                continue  # a batch listed again (overlapping date windows) is read once
            batch = str(batch).strip()
            seen.add((client, batch))
            records.append(_run(bundle, client, batch, index, item))
            for page in sorted(bundle.all(ROUTES["getPayrollVoucherForBatch"]), key=lambda r: int(r.params.get("startpage") or 0)):
                if page.params.get("clientId") != client or page.params.get("batchId") != batch or not prismhr_ok(page):
                    continue
                wrapper = next((key for key in VOUCHER_KEYS if key in page.body), VOUCHER_KEYS[0])
                for position, voucher in enumerate(page.body.get(wrapper) or []):
                    records.append(_paycheck(bundle.tenant_id, client, wrapper, position, voucher, earning_codes, deduction_codes))
    return records


# ---- runs -----------------------------------------------------------------------------


def _run(bundle: Bundle, client: str, batch: str, index: int, item: dict) -> PayrollRun:
    tenant, ctx = bundle.tenant_id, Ctx(PROVIDER)
    sources = [source(ROUTES["getBatchListByDate"], f"/batchList/{index}")]
    key = f"getBatchListByDate:batchList[{index}]"
    info_response = bundle.get(ROUTES["getBatchInfo"], clientId=client, batchId=batch)
    info = (info_response.body or {}).get("batchControl") or {} if prismhr_ok(info_response) else None
    numbers: dict[str, Any] = {}
    if info is None:
        name = ctx.unavailable("name", "getBatchInfo is not in the input or did not succeed: the description and period numbers are unknown.", "D-021")
    else:
        sources.append(source(ROUTES["getBatchInfo"], "/batchControl"))
        # row: getBatchInfo batchControl.batchId
        name = ctx.text(info.get("batchDescription"))  # row: getBatchInfo batchControl.batchDescription
        for voucher in info.get("voucher") or []:
            group = voucher.get("payGroupId")
            if not is_blank(group):
                numbers[str(group).strip()] = voucher.get("payPeriod")  # row: getBatchInfo batchControl.voucher[].payPeriod
        # row: getBatchInfo batchControl.processor; batchControl.deliveryDate; batchControl.deliveryMethod
        # row: getBatchInfo batchControl.actualShipMethod; batchControl.actualShipDate
        for field in ("processor", "deliveryDate", "deliveryMethod", "actualShipMethod", "actualShipDate"):
            ctx.keep(f"getBatchInfo:batchControl.{field}", info.get(field))
    periods = []
    for number, group in enumerate(item.get("payGroup") or []):
        code = group.get("payGroupId")  # row: getBatchListByDate batchList[].payGroup[].payGroupId
        where = f"pay_periods[{number}]"
        code = None if is_blank(code) else str(code).strip()
        period_number = numbers.get(code) if code else None
        periods.append(build(
            PayPeriod,
            pay_group_id=_code_id(tenant, EntityType.PAY_GROUP, client, code),
            period_start=ctx.date(group.get("payPeriodStartDate"), DateRole.PERIOD_START, f"{where}.period_start"),  # row: getBatchListByDate batchList[].payGroup[].payPeriodStartDate
            period_end=ctx.date(group.get("payPeriodEndDate"), DateRole.PERIOD_END, f"{where}.period_end"),  # row: getBatchListByDate batchList[].payGroup[].payPeriodEndDate
            period_number=_period_number(ctx, info, period_number, f"{where}.period_number"),
        ))
        # row: getBatchListByDate batchList[].payGroup[].weeksWorked; batchList[].payGroup[].deductPeriod
        for field in ("weeksWorked", "deductPeriod"):
            ctx.keep(f"{key}.payGroup[{number}].{field}", group.get(field))
    return build(
        PayrollRun,
        id=_id(tenant, EntityType.PAYROLL_RUN, client, batch),
        provider=Provider.PRISMHR,
        tenant_id=tenant,
        source_ids={"clientId": client, "batchId": batch},
        sources=sources,
        company_id=_id(tenant, EntityType.COMPANY, client),
        tax_entity_id=_id(tenant, EntityType.TAX_ENTITY, client),
        name=name,
        run_type=ctx.coded("prismhr.batch_type", item.get("batchType"), "run_type"),  # row: getBatchListByDate batchList[].batchType
        status=ctx.coded("prismhr.batch_status", item.get("batchStatus"), "status"),  # row: getBatchListByDate batchList[].batchStatus
        pay_date=ctx.date(item.get("payDate"), DateRole.EVENT, "pay_date"),  # row: getBatchListByDate batchList[].payDate
        scheduled_pay_date=NP,  # not sent (table notes)
        run_number=NP,
        run_date=NP,
        finalized_date=NP,
        pay_periods=periods,
        diagnostics=ctx.diagnostics,
        provider_extensions=ctx.extensions,
        sensitive_provider_extensions=ctx.sensitive_extensions,
    )


def _period_number(ctx: Ctx, info: dict | None, raw: Any, field: str) -> Any:
    """The pay group's period number from batch info; without batch info it is unknown."""
    if info is None:
        return ctx.unavailable(field, "getBatchInfo is not in the input or did not succeed: the period number is unknown.", "D-021")
    return NP if raw is None else ctx.integer(raw, field)


# ---- paychecks ------------------------------------------------------------------------


def _paycheck(tenant: str, client: str, wrapper: str, position: int, voucher: dict, earning_codes: dict, deduction_codes: dict) -> Paycheck:
    ctx = Ctx(PROVIDER)
    voucher_id = str(voucher.get("voucherId")).strip()  # row: getPayrollVoucherForBatch payrollVouchers[].voucherId
    key = f"getPayrollVoucherForBatch:{wrapper}[{position}]"
    reversed_id = voucher.get("voidVoucherId")  # row: getPayrollVoucherForBatch payrollVouchers[].voidVoucherId
    earnings = _earnings(ctx, tenant, client, key, voucher, earning_codes)
    payments = _payments(ctx, key, voucher)
    net_pay = ctx.number(voucher.get("netPay"), "net_pay")  # row: getPayrollVoucherForBatch payrollVouchers[].netPay
    check_net_pay(ctx, net_pay, payments)
    retirement = voucher.get("retirement")
    # row: getPayrollVoucherForBatch payrollVouchers[].retirement.*
    ctx.rest(f"{key}.retirement", retirement, RETIREMENT_TYPED)
    # row: getPayrollVoucherForBatch payrollVouchers[].bankAccount; payrollVouchers[].checkAccountACH; payrollVouchers[].taxFilingStatus[].*
    # row: getPayrollVoucherForBatch payrollVouchers[].otherEarnAmount; payrollVouchers[].fitTaxableAmount; payrollVouchers[].payPeriod
    # row: getPayrollVoucherForBatch payrollVouchers[].payStubType; payrollVouchers[].importBatchNo; payrollVouchers[].hsaPeoMatch
    # row: getPayrollVoucherForBatch payrollVouchers[].fsaMatch[].*; payrollVouchers[].fromArrears[].*; payrollVouchers[].toArrears[].*
    # row: getPayrollVoucherForBatch payrollVouchers[].workerComp[].*; payrollVouchers[].wcHomeClass; payrollVouchers[].wcState
    # row: getPayrollVoucherForBatch payrollVouchers[].wcInformation.**; payrollVouchers[].glAcctDistribution.**
    # row: getPayrollVoucherForBatch payrollVouchers[].asoClientGLAcctDistribution.**
    ctx.rest(key, voucher, VOUCHER_HANDLED, sensitive=SENSITIVE)
    return build(
        Paycheck,
        id=_id(tenant, EntityType.PAYCHECK, client, voucher_id),
        provider=Provider.PRISMHR,
        tenant_id=tenant,
        source_ids={"clientId": client, "voucherId": voucher_id},
        sources=[source(ROUTES["getPayrollVoucherForBatch"], f"/{wrapper}/{position}")],
        company_id=_id(tenant, EntityType.COMPANY, client),
        employee_id=_id(tenant, EntityType.EMPLOYEE, client, str(voucher.get("employeeId")).strip()),  # row: getPayrollVoucherForBatch payrollVouchers[].employeeId
        payroll_run_id=_code_id(tenant, EntityType.PAYROLL_RUN, client, voucher.get("batchId")),  # row: getPayrollVoucherForBatch payrollVouchers[].batchId
        tax_entity_id=_id(tenant, EntityType.TAX_ENTITY, client),
        pay_group_id=_code_id(tenant, EntityType.PAY_GROUP, client, voucher.get("payGroup")),  # row: getPayrollVoucherForBatch payrollVouchers[].payGroup
        check_number=ctx.text(voucher.get("checkNumber")),  # row: getPayrollVoucherForBatch payrollVouchers[].checkNumber
        kind=ctx.coded("prismhr.voucher_type", voucher.get("type"), "kind"),  # row: getPayrollVoucherForBatch payrollVouchers[].type
        status=ctx.coded("prismhr.voucher_status", voucher.get("status"), "status"),  # row: getPayrollVoucherForBatch payrollVouchers[].status
        is_manual_check=ctx.flag(voucher.get("isManualCheck"), "is_manual_check", true="TRUE", false="FALSE"),  # row: getPayrollVoucherForBatch payrollVouchers[].isManualCheck
        pay_date=ctx.date(voucher.get("payDate"), DateRole.EVENT, "pay_date"),  # row: getPayrollVoucherForBatch payrollVouchers[].payDate
        period_start=ctx.date(voucher.get("payPeriodStart"), DateRole.PERIOD_START, "period_start"),  # row: getPayrollVoucherForBatch payrollVouchers[].payPeriodStart
        period_end=ctx.date(voucher.get("payPeriodEnd"), DateRole.PERIOD_END, "period_end"),  # row: getPayrollVoucherForBatch payrollVouchers[].payPeriodEnd
        processed_date=ctx.date(voucher.get("dateProcessed"), DateRole.EVENT, "processed_date"),  # row: getPayrollVoucherForBatch payrollVouchers[].dateProcessed
        # A voucher that voids nothing: both reversal fields not applicable.
        reverses_paycheck_id=NA if is_blank(reversed_id) else _id(tenant, EntityType.PAYCHECK, client, str(reversed_id).strip()),
        void_date=ctx.date(voucher.get("voidDate"), DateRole.EVENT, "void_date", blank=NA),  # row: getPayrollVoucherForBatch payrollVouchers[].voidDate
        earnings=earnings,
        deductions=_deductions(ctx, tenant, client, key, voucher, deduction_codes),
        taxes=_taxes(ctx, key, voucher),
        employer_contributions=[build(
            EmployerContributionLine,
            source_line_id=NP,
            plan=build(Reference, source_id=NP, code=ctx.text(item.get("code")), name=ctx.text(item.get("description"))),  # row: getPayrollVoucherForBatch payrollVouchers[].employerContributions[].code; payrollVouchers[].employerContributions[].description
            deduction_code_id=NP,
            earning_code_id=NP,
            amount=ctx.number(item.get("amount"), f"employer_contributions[{n}].amount"),  # row: getPayrollVoucherForBatch payrollVouchers[].employerContributions[].amount
        ) for n, item in enumerate(voucher.get("employerContributions") or [])],
        benefit_lines=[_benefit(ctx, n, item) for n, item in enumerate(voucher.get("benefit") or [])],
        retirement=NP if not isinstance(retirement, dict) else _retirement(ctx, retirement),
        payments=payments,
        gross_pay=ctx.number(voucher.get("earnAmount"), "gross_pay"),  # row: getPayrollVoucherForBatch payrollVouchers[].earnAmount
        gross_wages=NP,  # an isolved total; PrismHR sends none with that definition (D-052)
        total_earnings=ctx.number(voucher.get("totalEarnings"), "total_earnings"),  # row: getPayrollVoucherForBatch payrollVouchers[].totalEarnings
        net_pay=net_pay,
        currency=USD,
        diagnostics=ctx.diagnostics,
        provider_extensions=ctx.extensions,
        sensitive_provider_extensions=ctx.sensitive_extensions,
    )


def _earnings(ctx: Ctx, tenant: str, client: str, key: str, voucher: dict, codes: dict) -> list[EarningLine]:
    lines = []
    for index, item in enumerate(voucher.get("earning") or []):
        where = f"earnings[{len(lines)}]"
        raw_code = item.get("payCode")  # row: getPayrollVoucherForBatch payrollVouchers[].earning[].payCode
        code_id = _code_id(tenant, EntityType.EARNING_CODE, client, raw_code)
        code = codes.get(code_id) if isinstance(code_id, str) else None
        quantity = code.quantity_type.value.value if code is not None and code.quantity_type is not None else None
        raw_quantity = item.get("hoursUnits")  # row: getPayrollVoucherForBatch payrollVouchers[].earning[].hoursUnits
        if quantity == "hours":
            hours, units = ctx.number(raw_quantity, f"{where}.hours"), NA
        elif quantity == "units":
            hours, units = NA, ctx.number(raw_quantity, f"{where}.units")
        else:
            hours, units = NP, NP
            if not is_blank(raw_quantity):
                ctx.keep(f"{key}.earning[{index}].hoursUnits", raw_quantity)
                ctx.diag(DiagnosticCode.UNIT_UNVERIFIED, Severity.WARNING,
                         "The pay code's payReason is not known: hoursUnits is not placed in hours or units; kept raw.", where, "D-051")
        pay_class_raw = item.get("payClass")  # row: getPayrollVoucherForBatch payrollVouchers[].earning[].payClass
        # A line without its own class takes the linked code's (D-047, D-089).
        pay_class = (copied(ctx, code, "pay_class", f"{where}.pay_class") if is_blank(pay_class_raw)
                     else ctx.coded("prismhr.pay_class", pay_class_raw, f"{where}.pay_class"))
        # row: getPayrollVoucherForBatch payrollVouchers[].earning[].*
        ctx.rest(f"{key}.earning[{index}]", item, {"payCode", "payClass", "hoursUnits", "hoursWorked", "unitRate", "payAmount"},
                 excluded={"payClassDescription"})
        lines.append(build(
            EarningLine,
            source_line_id=NP,
            earning_code_id=code_id,
            earning_code=build(Reference, source_id=NP, code=ctx.text(raw_code), name=NP),
            pay_class=pay_class,
            is_cash=copied(ctx, code, "is_cash", f"{where}.is_cash"),
            rate_class=copied(ctx, code, "rate_class", f"{where}.rate_class"),
            hours=hours,
            hours_worked=ctx.number(item.get("hoursWorked"), f"{where}.hours_worked"),  # row: getPayrollVoucherForBatch payrollVouchers[].earning[].hoursWorked
            units=units,
            rate=ctx.number(item.get("unitRate"), f"{where}.rate"),  # row: getPayrollVoucherForBatch payrollVouchers[].earning[].unitRate
            amount=ctx.number(item.get("payAmount"), f"{where}.amount"),  # row: getPayrollVoucherForBatch payrollVouchers[].earning[].payAmount
        ))
    for item in voucher.get("otherEarningsDetail") or []:
        where = f"earnings[{len(lines)}]"
        raw_code = item.get("otherEarnCode")  # row: getPayrollVoucherForBatch payrollVouchers[].otherEarningsDetail[].otherEarnCode
        code_id = _code_id(tenant, EntityType.EARNING_CODE, client, raw_code)
        code = codes.get(code_id) if isinstance(code_id, str) else None
        lines.append(build(
            EarningLine,
            source_line_id=NP,
            earning_code_id=code_id,
            earning_code=build(Reference, source_id=NP, code=ctx.text(raw_code), name=ctx.text(item.get("otherEarnsDesc"))),  # row: getPayrollVoucherForBatch payrollVouchers[].otherEarningsDetail[].otherEarnsDesc
            pay_class=copied(ctx, code, "pay_class", f"{where}.pay_class"),
            is_cash=copied(ctx, code, "is_cash", f"{where}.is_cash"),
            rate_class=copied(ctx, code, "rate_class", f"{where}.rate_class"),
            hours=NP,
            hours_worked=NP,
            units=NP,
            rate=NP,
            amount=ctx.number(item.get("otherEarnAmount"), f"{where}.amount"),  # row: getPayrollVoucherForBatch payrollVouchers[].otherEarningsDetail[].otherEarnAmount
        ))
    return lines


def _deductions(ctx: Ctx, tenant: str, client: str, key: str, voucher: dict, codes: dict) -> list[DeductionLine]:
    lines = []
    for index, item in enumerate(voucher.get("deduction") or []):
        where = f"deductions[{len(lines)}]"
        raw_code = item.get("deductCode")  # row: getPayrollVoucherForBatch payrollVouchers[].deduction[].deductCode
        kind = item.get("deductType")  # row: getPayrollVoucherForBatch payrollVouchers[].deduction[].deductType
        code_id = _code_id(tenant, EntityType.DEDUCTION_CODE, client, raw_code)
        code = codes.get(code_id) if isinstance(code_id, str) else None
        plan = item.get("planId")  # row: getPayrollVoucherForBatch payrollVouchers[].deduction[].planId
        ctx.keep(f"{key}.deduction[{index}].deductUnionId", item.get("deductUnionId"))  # row: getPayrollVoucherForBatch payrollVouchers[].deduction[].deductUnionId
        if is_blank(kind):  # the line sends no type: the linked code's classification (D-047, D-089)
            category = copied(ctx, code, "category", f"{where}.category")
            tax_treatment = copied(ctx, code, "tax_treatment", f"{where}.tax_treatment")
            catch_up = copied(ctx, code, "is_catch_up", f"{where}.is_catch_up")
        else:
            listed = code_entry(PROVIDER, "prismhr.deduction_type", str(kind).strip()) is not None
            category = ctx.coded("prismhr.deduction_type", kind, f"{where}.category", column="category")
            tax_treatment = ctx.coded("prismhr.deduction_type", kind, f"{where}.tax_treatment", column="tax_treatment")
            catch_up = str(kind).strip() in CATCH_UP_TYPES if listed else NP
        lines.append(build(
            DeductionLine,
            source_line_id=NP,
            deduction_code_id=code_id,
            deduction_code=build(Reference, source_id=NP, code=ctx.text(raw_code), name=ctx.text(item.get("deductDescription"))),  # row: getPayrollVoucherForBatch payrollVouchers[].deduction[].deductDescription
            category=category,
            tax_treatment=tax_treatment,
            is_catch_up=catch_up,
            plan=NP if is_blank(plan) else build(Reference, source_id=NP, code=str(plan).strip(), name=NP),
            amount=ctx.number(item.get("deductAmount"), f"{where}.amount"),  # row: getPayrollVoucherForBatch payrollVouchers[].deduction[].deductAmount
        ))
    for index, item in enumerate(voucher.get("otherDeduction") or []):
        where = f"deductions[{len(lines)}]"
        raw_code = item.get("otherDeductCode")  # row: getPayrollVoucherForBatch payrollVouchers[].otherDeduction[].otherDeductCode
        code_id = _code_id(tenant, EntityType.DEDUCTION_CODE, client, raw_code)
        code = codes.get(code_id) if isinstance(code_id, str) else None
        ctx.keep(f"{key}.otherDeduction[{index}].otherDeductOneTimeSwitch", item.get("otherDeductOneTimeSwitch"))  # row: getPayrollVoucherForBatch payrollVouchers[].otherDeduction[].otherDeductOneTimeSwitch
        lines.append(build(
            DeductionLine,
            source_line_id=NP,
            deduction_code_id=code_id,
            deduction_code=build(Reference, source_id=NP, code=ctx.text(raw_code), name=ctx.text(item.get("otherDeductDescription"))),  # row: getPayrollVoucherForBatch payrollVouchers[].otherDeduction[].otherDeductDescription
            category=copied(ctx, code, "category", f"{where}.category"),
            tax_treatment=copied(ctx, code, "tax_treatment", f"{where}.tax_treatment"),
            is_catch_up=copied(ctx, code, "is_catch_up", f"{where}.is_catch_up"),
            plan=NP,
            amount=ctx.number(item.get("otherDeductAmount"), f"{where}.amount"),  # row: getPayrollVoucherForBatch payrollVouchers[].otherDeduction[].otherDeductAmount
        ))
    return lines


def _taxes(ctx: Ctx, key: str, voucher: dict) -> list[TaxLine]:
    lines = []
    for item in voucher.get("employeeTax") or []:
        where = f"taxes[{len(lines)}]"
        label = item.get("empTaxDeductCodeDesc")  # row: getPayrollVoucherForBatch payrollVouchers[].employeeTax[].empTaxDeductCodeDesc
        lines.append(build(
            TaxLine,
            source_line_id=NP,
            tax_code=build(Reference, source_id=NP, code=ctx.text(item.get("empTaxDeductCode")), name=ctx.text(label)),  # row: getPayrollVoucherForBatch payrollVouchers[].employeeTax[].empTaxDeductCode
            tax_type=ctx.coded("prismhr.tax_label", label, f"{where}.tax_type", column="tax_type"),
            jurisdiction_level=ctx.coded("prismhr.tax_label", label, f"{where}.jurisdiction_level", column="jurisdiction_level"),
            jurisdiction=NP,  # no field states it (table notes)
            paid_by="employee",  # employeeTax[] (structure)
            amount=ctx.number(item.get("empTaxAmount"), f"{where}.amount"),  # row: getPayrollVoucherForBatch payrollVouchers[].employeeTax[].empTaxAmount
            taxable_wages=ctx.number(item.get("empTaxableAmount"), f"{where}.taxable_wages"),  # row: getPayrollVoucherForBatch payrollVouchers[].employeeTax[].empTaxableAmount
            gross_wages=NP,
            exempt_wages=NP,
            over_limit_wages=ctx.number(item.get("empOverLimitAmount"), f"{where}.over_limit_wages"),  # row: getPayrollVoucherForBatch payrollVouchers[].employeeTax[].empOverLimitAmount
            rate=NP,
        ))
    for index, item in enumerate(voucher.get("companyTax") or []):
        where = f"taxes[{len(lines)}]"
        label = item.get("comTaxDeductCodeDesc")  # row: getPayrollVoucherForBatch payrollVouchers[].companyTax[].comTaxDeductCodeDesc
        # row: getPayrollVoucherForBatch payrollVouchers[].companyTax[].comShelteredAmount; payrollVouchers[].companyTax[].comTaxType
        # row: getPayrollVoucherForBatch payrollVouchers[].companyTax[].comTaxEntity; payrollVouchers[].companyTax[].comClientSutaRpt
        for field in ("comShelteredAmount", "comTaxType", "comTaxEntity", "comClientSutaRpt"):
            ctx.keep(f"{key}.companyTax[{index}].{field}", item.get(field))
        lines.append(build(
            TaxLine,
            source_line_id=NP,
            tax_code=build(Reference, source_id=NP, code=ctx.text(item.get("comTaxDeductCode")), name=ctx.text(label)),  # row: getPayrollVoucherForBatch payrollVouchers[].companyTax[].comTaxDeductCode
            tax_type=ctx.coded("prismhr.tax_label", label, f"{where}.tax_type", column="tax_type"),
            jurisdiction_level=ctx.coded("prismhr.tax_label", label, f"{where}.jurisdiction_level", column="jurisdiction_level"),
            jurisdiction=NP,
            paid_by="employer",  # companyTax[] (structure)
            amount=ctx.number(item.get("comTaxAmount"), f"{where}.amount"),  # row: getPayrollVoucherForBatch payrollVouchers[].companyTax[].comTaxAmount
            taxable_wages=ctx.number(item.get("comTaxableAmount"), f"{where}.taxable_wages"),  # row: getPayrollVoucherForBatch payrollVouchers[].companyTax[].comTaxableAmount
            gross_wages=NP,
            exempt_wages=ctx.number(item.get("comExemptAmount"), f"{where}.exempt_wages"),  # row: getPayrollVoucherForBatch payrollVouchers[].companyTax[].comExemptAmount
            over_limit_wages=ctx.number(item.get("comOvrLimit"), f"{where}.over_limit_wages"),  # row: getPayrollVoucherForBatch payrollVouchers[].companyTax[].comOvrLimit
            rate=ctx.number(item.get("comTaxRate"), f"{where}.rate"),  # row: getPayrollVoucherForBatch payrollVouchers[].companyTax[].comTaxRate
        ))
    return lines


def _benefit(ctx: Ctx, n: int, item: dict) -> BenefitLine:
    where = f"benefit_lines[{n}]"
    plan = item.get("planId")  # row: getPayrollVoucherForBatch payrollVouchers[].benefit[].planId
    return build(
        BenefitLine,
        plan=NP if is_blank(plan) else build(Reference, source_id=NP, code=str(plan).strip(), name=NP),
        coverage_period=ctx.text(item.get("coveragePeriod")),  # row: getPayrollVoucherForBatch payrollVouchers[].benefit[].coveragePeriod
        premium_amount=ctx.number(item.get("premiumAmt"), f"{where}.premium_amount"),  # row: getPayrollVoucherForBatch payrollVouchers[].benefit[].premiumAmt
        premium_cost=ctx.number(item.get("premiumCost"), f"{where}.premium_cost"),  # row: getPayrollVoucherForBatch payrollVouchers[].benefit[].premiumCost
        employee_contribution=ctx.number(item.get("empContrib"), f"{where}.employee_contribution"),  # row: getPayrollVoucherForBatch payrollVouchers[].benefit[].empContrib
        employee_deduction=ctx.number(item.get("empDeduct"), f"{where}.employee_deduction"),  # row: getPayrollVoucherForBatch payrollVouchers[].benefit[].empDeduct
        employer_contribution=NP,
        catch_up_amount=NP,
        eligible_wages=NP,
        match_eligible_wages=NP,
        adjustment_ref=ctx.text(item.get("adjRef")),  # row: getPayrollVoucherForBatch payrollVouchers[].benefit[].adjRef
    )


def _retirement(ctx: Ctx, block: dict) -> RetirementBreakdown:
    """Employer side only, not additive (D-051); on arrears vouchers every amount is null and stays null."""
    plan = block.get("planId")  # row: getPayrollVoucherForBatch payrollVouchers[].retirement.planId
    return build(
        RetirementBreakdown,
        plan=NP if is_blank(plan) else build(Reference, source_id=NP, code=str(plan).strip(), name=NP),
        plan_year_period=ctx.text(block.get("planYearPeriod")),  # row: getPayrollVoucherForBatch payrollVouchers[].retirement.planYearPeriod
        base_earnings=ctx.number(block.get("baseEarnings"), "retirement.base_earnings"),  # row: getPayrollVoucherForBatch payrollVouchers[].retirement.baseEarnings
        employer_matching=ctx.number(block.get("employerMatchingContributions"), "retirement.employer_matching"),  # row: getPayrollVoucherForBatch payrollVouchers[].retirement.employerMatchingContributions
        employer_non_elective=ctx.number(block.get("employerNonElectiveContributions"), "retirement.employer_non_elective"),  # row: getPayrollVoucherForBatch payrollVouchers[].retirement.employerNonElectiveContributions
        employer_safe_harbor_1=ctx.number(block.get("employerSafeHarborMatchType1"), "retirement.employer_safe_harbor_1"),  # row: getPayrollVoucherForBatch payrollVouchers[].retirement.employerSafeHarborMatchType1
        employer_safe_harbor_2=ctx.number(block.get("employerSafeHarborMatchType2"), "retirement.employer_safe_harbor_2"),  # row: getPayrollVoucherForBatch payrollVouchers[].retirement.employerSafeHarborMatchType2
        peo_matching=ctx.number(block.get("peoMatchingContribution"), "retirement.peo_matching"),  # row: getPayrollVoucherForBatch payrollVouchers[].retirement.peoMatchingContribution
    )


def _payments(ctx: Ctx, key: str, voucher: dict) -> list[PaymentLine]:
    """checkAmt as one check line (raw_code 'checkAmt', always, even 0), each deposit one line.
    Payment lines hold no full numbers: last 4 of the full routing number, and of the masked
    account number only when the mask shows them (table notes)."""
    lines = [build(
        PaymentLine,
        source_line_id=NP,
        method=route_code("check", "checkAmt"),
        amount=ctx.number(voucher.get("checkAmt"), "payments[0].amount"),  # row: getPayrollVoucherForBatch payrollVouchers[].checkAmt
        direct_deposit_id=NA,
        routing_last4=NA,
        account_last4=NA,
    )]
    for index, item in enumerate(voucher.get("directDeposit") or []):
        routing = item.get("transitNum")  # row: getPayrollVoucherForBatch payrollVouchers[].directDeposit[].transitNum
        account = item.get("accountNum")  # row: getPayrollVoucherForBatch payrollVouchers[].directDeposit[].accountNum
        if is_blank(account):
            account_last4 = NP
        elif is_masked(account):
            account_last4 = visible_last4(account) or ctx.redacted(f"payments[{len(lines)}].account_last4")
        else:
            account_last4 = str(account).strip()[-4:]
        ctx.keep(f"{key}.directDeposit[{index}].status", item.get("status"))  # row: getPayrollVoucherForBatch payrollVouchers[].directDeposit[].status
        lines.append(build(
            PaymentLine,
            source_line_id=NP,
            method=route_code("direct_deposit", "directDeposit"),
            amount=ctx.number(item.get("amount"), f"payments[{len(lines)}].amount"),  # row: getPayrollVoucherForBatch payrollVouchers[].directDeposit[].amount
            direct_deposit_id=NP,  # voucher deposits carry no deposit id (table notes)
            routing_last4=NP if is_blank(routing) else str(routing).strip()[-4:],
            account_last4=account_last4,
        ))
    return lines
