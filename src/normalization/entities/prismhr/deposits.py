"""PrismHR direct deposits: one DirectDeposit per getEmployee ``directDeposit.achVoucher[]`` item (D-046).

Follows ``mappings/data/prismhr/direct_deposit.json``. PrismHR sends no deposit id or sequence:
the id is the item's position in the employee's list, sequence is not provided, and every record
carries an unstable_id diagnostic. The position is never read as a payment priority.
"""
from typing import Any

from ...canonical.deposits import DirectDeposit
from ...canonical.diagnostics import DiagnosticCode, Severity
from ...canonical.ids import EntityType, Provider, canonical_id
from ...employees.bundle import Bundle
from ...employees.common import HIDDEN, NA, NP, Ctx, Null, build, is_blank, is_masked, visible_last4
from ..common import USD, prismhr_ok, route_code, source

PROVIDER = "prismhr"
TABLE = "direct_deposit"
ROUTES = {"getEmployee": "/employee/v1/getEmployee"}
FIXED, PERCENT = {"F", "FS"}, {"P", "PN"}


def _id(tenant: str, entity: EntityType, *parts: str) -> str:
    return canonical_id(Provider.PRISMHR, tenant, entity, *parts)


def normalize(bundle: Bundle) -> list[DirectDeposit]:
    records = []
    for response in bundle.all(ROUTES["getEmployee"]):
        if not prismhr_ok(response):
            continue
        client = response.params.get("clientId")
        for index, item in enumerate(response.body.get("employee") or []):
            block = item.get("directDeposit") or {}
            employee_id = str(item.get("id"))
            for position, voucher in enumerate(block.get("achVoucher") or []):
                records.append(_deposit(bundle.tenant_id, client, employee_id, index, block, position, voucher))
    return records


def _deposit(tenant: str, client: str, employee_id: str, index: int, block: dict, position: int, voucher: dict) -> DirectDeposit:
    ctx = Ctx(PROVIDER)
    base = f"getEmployee:employee[{index}].directDeposit"
    ctx.diag(DiagnosticCode.UNSTABLE_ID, Severity.WARNING,
             "PrismHR sends no deposit id: the id is the position in the employee's list, not stable if the list is reordered.",
             None, "D-046")
    method = str(voucher.get("method") or "").strip().upper()  # row: getEmployee employee[].directDeposit.achVoucher[].method
    raw_amount = voucher.get("amount")  # row: getEmployee employee[].directDeposit.achVoucher[].amount
    if method in FIXED:
        amount, percent = ctx.number(raw_amount, "amount"), NA
    elif method in PERCENT:
        amount, percent = NA, ctx.number(raw_amount, "percent")
    elif method == "B":
        amount, percent = NA, NA  # 'must not be specified' for B
    else:
        amount, percent = NP, NP
        ctx.keep(f"{base}.achVoucher[{position}].amount", raw_amount)
    if method == "PN":
        percent_basis = route_code("remainder_after_fixed", "PN")  # documented 'percentage of net after fixed'
    elif method == "P":
        percent_basis = {"value": "unknown", "raw_code": "P", "raw_label": None, "basis": "unmapped"}
        ctx.diag(DiagnosticCode.UNKNOWN_CODE, Severity.WARNING, "Method P states no percent basis; value unknown.", "percent_basis", "D-032")
    else:
        percent_basis = NA if method in FIXED or method == "B" else NP
    override = voucher.get("voucherTypeOverride")  # row: getEmployee employee[].directDeposit.achVoucher[].voucherTypeOverride
    letters = override if not is_blank(override) else block.get("voucherType")  # row: getEmployee employee[].directDeposit.voucherType
    kinds = [ctx.coded("prismhr.deposit_voucher_type", letter, f"applies_to_paycheck_kinds[{n}]")
             for n, letter in enumerate(str(letters or "").strip())]
    routing = ctx.text(voucher.get("transitNum"), "routing_number", sensitive=True)  # row: getEmployee employee[].directDeposit.achVoucher[].transitNum
    account_raw = voucher.get("accountNum")  # row: getEmployee employee[].directDeposit.achVoucher[].accountNum
    account = ctx.text(account_raw, "account_number", sensitive=True)
    # row: getEmployee employee[].directDeposit.achVoucher[].limit; employee[].directDeposit.achStatus; employee[].directDeposit.suppressAccountPrint
    ctx.keep(f"{base}.achVoucher[{position}].limit", voucher.get("limit"))
    ctx.keep(f"{base}.achStatus", block.get("achStatus"))
    ctx.keep(f"{base}.suppressAccountPrint", block.get("suppressAccountPrint"))
    return build(
        DirectDeposit,
        id=_id(tenant, EntityType.DIRECT_DEPOSIT, client, employee_id, str(position)),
        provider=Provider.PRISMHR,
        tenant_id=tenant,
        source_ids={"clientId": client, "employeeId": employee_id, "position": str(position)},
        sources=[source(ROUTES["getEmployee"], f"/employee/{index}/directDeposit/achVoucher/{position}")],
        company_id=_id(tenant, EntityType.COMPANY, client),
        employee_id=_id(tenant, EntityType.EMPLOYEE, client, employee_id),
        sequence=NP,  # PrismHR sends none
        allocation_type=ctx.coded("prismhr.deposit_method", voucher.get("method"), "allocation_type"),
        percent_basis=percent_basis,
        amount=amount,
        percent=percent,
        skip_if_insufficient=(method == "FS") if method in FIXED else NA,
        account_type=ctx.coded("prismhr.deposit_account_type", voucher.get("accountType"), "account_type"),  # row: getEmployee employee[].directDeposit.achVoucher[].accountType
        bank_name=ctx.text(voucher.get("bankName")),  # row: getEmployee employee[].directDeposit.achVoucher[].bankName
        routing_number=routing,
        routing_last4=_last4(voucher.get("transitNum"), routing),
        account_number=account,
        account_last4=_last4(account_raw, account),
        status=ctx.coded("prismhr.deposit_status", voucher.get("status"), "status"),  # row: getEmployee employee[].directDeposit.achVoucher[].status
        prenote_status=NP,  # only the P status is sent (table row)
        frequency=NP,
        applies_to_paycheck_kinds=kinds or NP,
        effective_from=NP,
        effective_to=NP,
        currency=USD,
        diagnostics=ctx.diagnostics,
        provider_extensions=ctx.extensions,
        sensitive_provider_extensions=ctx.sensitive_extensions,
    )


def _last4(raw: Any, value: Any) -> Any:
    """Last 4 from a mask that shows them (CANONICAL_MODEL 1.4): next to a full value not
    applicable, next to a mask that shows nothing hidden_by_source."""
    if isinstance(value, Null) and value is HIDDEN:
        return visible_last4(raw) or HIDDEN
    if isinstance(value, Null):
        return NP
    return NA if not is_masked(raw) else HIDDEN
