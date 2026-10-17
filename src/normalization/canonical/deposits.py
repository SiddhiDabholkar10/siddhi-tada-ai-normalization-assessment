"""Canonical direct deposit: one record per account allocation (D-046).

Ids: isolved and UKG deposit ids. PrismHR deposits have no id or sequence, so their id is the
position in the employee's list: deterministic for one response, not stable if PrismHR reorders
the list, and never read as a payment priority (each such record carries an unstable_id
diagnostic).
"""
from datetime import date
from typing import ClassVar

from pydantic import Field, model_validator

from .base import CanonicalRecord
from .enums import (
    AccountType,
    AllocationType,
    DepositFrequency,
    DepositStatus,
    PaycheckKind,
    PercentBasis,
    PrenoteStatus,
)
from .ids import EntityType
from .values import SENSITIVE, Amount, Coded, CurrencyCode, Last4, Percent


class DirectDeposit(CanonicalRecord):
    ENTITY: ClassVar[EntityType] = EntityType.DIRECT_DEPOSIT

    company_id: str
    employee_id: str
    sequence: int | None = Field(
        default=None,
        description="Provider's sequence number as sent (isolved 0 = net pay, UKG 1..n). Null for PrismHR, which has none.",
    )
    allocation_type: Coded[AllocationType] | None = None
    percent_basis: Coded[PercentBasis] | None = None
    amount: Amount | None = None
    percent: Percent | None = None
    skip_if_insufficient: bool | None = Field(
        default=None, description="Skip the deposit when the full fixed amount cannot be taken (PrismHR method FS)."
    )
    account_type: Coded[AccountType] | None = None
    bank_name: str | None = None
    routing_number: str | None = Field(default=None, json_schema_extra=SENSITIVE)
    routing_last4: Last4 | None = None
    account_number: str | None = Field(default=None, json_schema_extra=SENSITIVE)
    account_last4: Last4 | None = None
    status: Coded[DepositStatus] | None = None
    prenote_status: Coded[PrenoteStatus] | None = None
    frequency: Coded[DepositFrequency] | None = None
    applies_to_paycheck_kinds: list[Coded[PaycheckKind]] | None = Field(
        default=None, description="Paycheck kinds the deposit applies to (PrismHR voucherType, e.g. R, S, V)."
    )
    effective_from: date | None = None
    effective_to: date | None = None
    currency: CurrencyCode | None = None

    @model_validator(mode="after")
    def _checks(self) -> "DirectDeposit":
        if self.percent is not None and not 0 <= self.percent <= 100:
            raise ValueError(f"percent {self.percent} is outside 0 to 100")
        # A known allocation type fixes which value fields may be set. Unknown allows any.
        allocation = self.allocation_type.value if self.allocation_type else None
        forbidden = {
            AllocationType.FIXED_AMOUNT: ("percent", "percent_basis"),
            AllocationType.PERCENT: ("amount",),
            AllocationType.REMAINDER: ("amount", "percent", "percent_basis"),
        }.get(allocation, ())
        set_fields = [name for name in forbidden if getattr(self, name) is not None]
        if set_fields:
            raise ValueError(f"{allocation} allocation must not carry {', '.join(set_fields)}")
        self.require_references(
            [
                ("company_id", self.company_id, EntityType.COMPANY),
                ("employee_id", self.employee_id, EntityType.EMPLOYEE),
            ]
        )
        return self
