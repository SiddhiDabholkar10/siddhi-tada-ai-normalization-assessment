"""Helpers shared by the entity adapters, on top of ``employees.common``."""
from decimal import Decimal
from typing import Any

from ..canonical.base import SourceRef
from ..canonical.company import Company, DeductionCode, EarningCode
from ..canonical.diagnostics import DiagnosticCode, Severity
from ..canonical.values import MappingBasis
from ..employees.bundle import Response
from ..employees.common import NP, Ctx, Null

USD = "USD"  # not sent by PrismHR and isolved; assumed (CANONICAL_MODEL 1.5), as on employees


def prismhr_ok(response: Response | None) -> bool:
    """PrismHR success is HTTP 200 with errorCode 0 (D-021)."""
    return response is not None and response.ok and str((response.body or {}).get("errorCode", "0")) == "0"


def source(route: str, locator: str = "") -> SourceRef:
    return SourceRef(endpoint=f"GET {route}", locator=locator)


def route_code(value: str, raw_code: str, basis: MappingBasis = MappingBasis.DOCUMENTED) -> dict:
    """A coded value fixed by the route itself (no code sent): raw_code names the source
    (CANONICAL_MODEL 1.7), e.g. category garnishment from the isolved garnishments route."""
    return {"value": value, "raw_code": raw_code, "raw_label": None, "basis": basis.value}


def entry_extensions(provider: str, key: str, obj: Any, handled: set[str] = frozenset(), excluded: set[str] = frozenset()) -> dict:
    """The provider_extensions of a company-owned entry (D-063): the keys of ``obj`` not handled
    or excluded, keyed from the response root with list indices like record keys (D-080, D-088)."""
    ctx = Ctx(provider)
    ctx.rest(key, obj, handled, excluded=excluded)
    return ctx.extensions


# ---- payroll (D-089) ------------------------------------------------------------------


def code_index(companies: list[Company]) -> tuple[dict[str, EarningCode], dict[str, DeductionCode]]:
    """Earning and deduction codes of the given companies, by canonical id."""
    earning = {code.id: code for company in companies for code in company.earning_codes or []}
    deduction = {code.id: code for company in companies for code in company.deduction_codes or []}
    return earning, deduction


def copied(ctx: Ctx, code: Any, name: str, field: str) -> Any:
    """Classification ``name`` copied from the company code a line links to (lines inherit from the
    code, D-047, D-054, D-088). An inferred or unknown value gets its diagnostic on the record, at
    the line's field. No code, or a code without the value: not provided."""
    value = getattr(code, name, None) if code is not None else None
    if value is None:
        return NP
    if isinstance(value, bool):
        return value
    data = value.model_dump(mode="json")
    if data["basis"] == MappingBasis.INFERRED.value:
        ctx.diag(DiagnosticCode.INFERRED_MAPPING, Severity.INFO, "Copied from the linked company code, whose value is inferred.", field, "D-047")
    elif data["basis"] == MappingBasis.UNMAPPED.value:
        ctx.diag(DiagnosticCode.UNKNOWN_CODE, Severity.WARNING, "Copied from the linked company code, whose value is unknown.", field, "D-047")
    return data


def check_net_pay(ctx: Ctx, net_pay: Any, payments: list) -> None:
    """Net pay against the check and direct deposit lines (PrismHR netPay = checkAmt + deposits on
    192 of 192 live vouchers): reconciliation_incomplete when a payment amount is missing,
    reconciliation_mismatch when every amount is present and the sum differs (D-053)."""
    if isinstance(net_pay, Null):
        return
    amounts = [line.amount for line in payments]
    if any(amount is None for amount in amounts):
        ctx.diag(DiagnosticCode.RECONCILIATION_INCOMPLETE, Severity.WARNING,
                 "A payment line has no amount: net pay could not be compared with the payments.", "net_pay", "D-053")
    elif sum(amounts, Decimal(0)) != net_pay:
        ctx.diag(DiagnosticCode.RECONCILIATION_MISMATCH, Severity.WARNING,
                 f"Net pay {net_pay} differs from the check and deposit lines ({sum(amounts, Decimal(0))}).", "net_pay", "D-053")
