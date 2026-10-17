"""UKG Ready direct deposits: one DirectDeposit per ``deposits[]`` item (D-046).

Follows ``mappings/data/ukg-ready/direct_deposit.json``. The route is deprecated and the only
deposit list (D-030): every record carries a deprecated_source diagnostic. Allocation and percent
basis come from calc_method.type; numbers are sent in full, so the last-4 fields are not applicable.
"""
from typing import Any

from ...canonical.deposits import DirectDeposit
from ...canonical.diagnostics import DiagnosticCode, Severity
from ...canonical.ids import EntityType, Provider, canonical_id
from ...canonical.parsing import DateRole
from ...employees.bundle import Bundle
from ...employees.common import NA, NP, Ctx, Null, build, is_blank
from ..common import route_code, source

PROVIDER = "ukg-ready"
TABLE = "direct_deposit"
ROUTES = {"direct-deposits": "/v2/companies/{cid}/employees/{aid}/direct-deposits"}
# percent_basis from the calc method (table notes); FULL and FLAT_AMOUNT carry none.
PERCENT_BASIS = {"NET_PAY": "net_pay", "GROSS_EARNING": "gross_pay", "DIRECT_DEPOSIT_PER_OF_REMAINDER": "remainder_after_fixed"}
HANDLED = {"id", "sequence", "calc_method", "amount", "percentage", "account_type", "routing_number", "account_number", "active",
           "pre_note_status", "payroll_frequency", "active_from", "active_to", "currency", "_links", "_documents_count", "_notes_count"}


def _id(tenant: str, entity: EntityType, *parts: Any) -> str:
    return canonical_id(Provider.UKG_READY, tenant, entity, *(str(p) for p in parts))


def normalize(bundle: Bundle) -> list[DirectDeposit]:
    records = []
    for response in bundle.all(ROUTES["direct-deposits"]):
        if response.ok:
            for index, item in enumerate((response.body or {}).get("deposits") or []):
                records.append(_deposit(bundle.tenant_id, response.params, index, item))
    return records


def _deposit(tenant: str, params: dict, index: int, item: dict) -> DirectDeposit:
    ctx = Ctx(PROVIDER)
    cid, aid = params.get("cid"), params.get("aid")
    deposit_id = str(item.get("id"))  # row: direct-deposits deposits[].id
    key = f"direct-deposits:deposits[{index}]"
    ctx.diag(DiagnosticCode.DEPRECATED_SOURCE, Severity.WARNING,
             "UKG marks the employee direct-deposits route deprecated; it is the only deposit list (D-030).", None, "D-030")
    method = str((item.get("calc_method") or {}).get("type") or "").strip()  # row: direct-deposits deposits[].calc_method.type
    allocation = ctx.coded("ukg-ready.deposit_calc_method", method, "allocation_type")
    kind = allocation["value"] if isinstance(allocation, dict) else None
    amount = ctx.number(item.get("amount"), "amount")  # row: direct-deposits deposits[].amount
    percent = ctx.number(item.get("percentage"), "percent")  # row: direct-deposits deposits[].percentage
    if kind in ("fixed_amount", "remainder"):
        percent = _not_applicable(ctx, key, "percentage", item, percent)
    if kind in ("percent", "remainder"):
        amount = _not_applicable(ctx, key, "amount", item, amount)
    active = item.get("active")  # row: direct-deposits deposits[].active
    frequency = item.get("payroll_frequency") or {}
    # row: direct-deposits deposits[].payroll_frequency.*; deposits[].payroll_frequency.holiday_profile.*
    ctx.rest(f"{key}.payroll_frequency", frequency, {"type"})
    ctx.rest(key, item, HANDLED)  # row: direct-deposits deposits[].*
    routing = ctx.text(item.get("routing_number"), "routing_number", sensitive=True)  # row: direct-deposits deposits[].routing_number
    account = ctx.text(item.get("account_number"), "account_number", sensitive=True)  # row: direct-deposits deposits[].account_number
    return build(
        DirectDeposit,
        id=_id(tenant, EntityType.DIRECT_DEPOSIT, cid, deposit_id),
        provider=Provider.UKG_READY,
        tenant_id=tenant,
        source_ids={"companyId": cid, "accountId": aid, "id": deposit_id},
        sources=[source(ROUTES["direct-deposits"], f"/deposits/{index}")],
        company_id=_id(tenant, EntityType.COMPANY, cid),
        employee_id=_id(tenant, EntityType.EMPLOYEE, cid, aid),
        sequence=ctx.integer(item.get("sequence"), "sequence"),  # row: direct-deposits deposits[].sequence
        allocation_type=allocation,
        percent_basis=route_code(PERCENT_BASIS[method], method) if method in PERCENT_BASIS else (NA if kind else NP),
        amount=amount,
        percent=percent,
        skip_if_insufficient=NP,
        account_type=ctx.coded("ukg-ready.deposit_account_type", item.get("account_type"), "account_type"),  # row: direct-deposits deposits[].account_type
        bank_name=NP,
        routing_number=routing,
        routing_last4=NA if not isinstance(routing, Null) else NP,
        account_number=account,
        account_last4=NA if not isinstance(account, Null) else NP,
        status=route_code("active" if active else "inactive", str(active).lower()) if isinstance(active, bool) else NP,
        prenote_status=ctx.coded("ukg-ready.prenote_status", item.get("pre_note_status"), "prenote_status"),  # row: direct-deposits deposits[].pre_note_status
        frequency=ctx.coded("ukg-ready.deposit_frequency", frequency.get("type"), "frequency"),  # row: direct-deposits deposits[].payroll_frequency.type
        applies_to_paycheck_kinds=NP,
        effective_from=ctx.date(item.get("active_from"), DateRole.PERIOD_START, "effective_from"),  # row: direct-deposits deposits[].active_from
        effective_to=ctx.date(item.get("active_to"), DateRole.PERIOD_END, "effective_to"),  # row: direct-deposits deposits[].active_to
        currency=ctx.text(item.get("currency")),  # row: direct-deposits deposits[].currency
        diagnostics=ctx.diagnostics,
        provider_extensions=ctx.extensions,
        sensitive_provider_extensions=ctx.sensitive_extensions,
    )


def _not_applicable(ctx: Ctx, key: str, name: str, item: dict, value: Any) -> Any:
    """A value field the allocation type rules out: not applicable; one still sent is kept raw."""
    if not isinstance(value, Null) and not is_blank(item.get(name)):
        ctx.keep(f"{key}.{name}", item.get(name))
    return NA
