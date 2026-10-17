"""Canonical deduction setup: one record per employee deduction assignment (D-048).

``source_basis`` says how strongly the source establishes the setup: a documented assignment
(PrismHR deductions), a candidate (isolved legal-level pay items, D-017, with an
unvalidated_source diagnostic), or presence only (a provider flag saying one exists, with no
details or code). Garnishments and loans are setups with an extra nested part. Deductions
taken in payroll are paycheck lines (step 4), not setups.
"""
from datetime import date
from typing import ClassVar

from pydantic import Field, model_validator

from .base import CanonicalPart, CanonicalRecord
from .diagnostics import DiagnosticCode
from .enums import (
    DeductionCalcMethod,
    DeductionCategory,
    GarnishmentBasis,
    GarnishmentType,
    LimitPeriod,
    MatchMethod,
    SetupSourceBasis,
    SetupStatus,
    TaxTreatment,
)
from .ids import EntityType
from .parts import Reference
from .values import SENSITIVE, Amount, Coded, CurrencyCode, Percent


class EmployerMatch(CanonicalPart):
    method: Coded[MatchMethod] | None = None
    amount: Amount | None = None
    percent: Percent | None = None
    description: str | None = None


class GarnishmentDetails(CanonicalPart):
    """Court or agency order details. ``linked_deductions`` keeps the provider's own
    references as sent; they are not required to join to a setup or code (isolved ids do not
    match the employee's pay item ids)."""

    type: Coded[GarnishmentType] | None = None
    description: str | None = None
    case_number: str | None = Field(default=None, json_schema_extra=SENSITIVE)
    payee: str | None = Field(default=None, json_schema_extra=SENSITIVE, description="Payee as sent; may embed account digits.")
    order_sequence: int | None = None
    issuing_state: str | None = None
    amount: Amount | None = None
    percent: Percent | None = None
    percent_basis: Coded[GarnishmentBasis] | None = None
    maximum_amount: Amount | None = None
    maximum_percent: Percent | None = None
    per_period_limit: Amount | None = None
    fee_amount: Amount | None = None
    exemption_amount: Amount | None = None
    arrears_balance: Amount | None = None
    remaining_balance: Amount | None = None
    apply_arrears: bool | None = None
    medical_support_required: bool | None = None
    linked_deductions: list[Reference] | None = None


class LoanDetails(CanonicalPart):
    loan_ref: str | None = Field(default=None, description="Provider's loan id as sent.")
    plan_code: str | None = None
    loan_date: date | None = None
    loan_amount: Amount | None = None
    payment_amount: Amount | None = None
    payback_amount: Amount | None = None
    paid_to_date: Amount | None = None
    deduction_start_date: date | None = None


class DeductionSetup(CanonicalRecord):
    ENTITY: ClassVar[EntityType] = EntityType.DEDUCTION_SETUP

    company_id: str
    employee_id: str
    source_basis: SetupSourceBasis
    deduction_code_id: str | None = Field(
        default=None, description="Company deduction code, when the source gives a key that links to one."
    )
    deduction_code: Reference | None = Field(default=None, description="The provider's code, id and name as sent.")
    category: Coded[DeductionCategory] | None = None
    tax_treatment: Coded[TaxTreatment] | None = None
    is_catch_up: bool | None = None
    calc_method: Coded[DeductionCalcMethod] | None = None
    amount: Amount | None = None
    percent: Percent | None = None
    period_numbers: list[int] | None = Field(
        default=None, description="Pay periods within a month (1 to 5) in which the deduction is taken (PrismHR period)."
    )
    per_period_limit: Amount | None = None
    maximum: Amount | None = None
    maximum_period: Coded[LimitPeriod] | None = None
    goal_amount: Amount | None = None
    balance: Amount | None = None
    track_arrears: bool | None = None
    start_date: date | None = None
    stop_date: date | None = None
    status: Coded[SetupStatus] | None = None
    employer_match: EmployerMatch | None = None
    benefit_enrollment_id: str | None = None
    garnishment: GarnishmentDetails | None = None
    loan: LoanDetails | None = None
    currency: CurrencyCode | None = None

    # A presence-only setup records that a deduction exists and, at most, what kind it is.
    PRESENCE_ONLY_ALLOWED: ClassVar[frozenset[str]] = frozenset(
        {"category", "tax_treatment", "is_catch_up", "status", "currency"}
    )

    @model_validator(mode="after")
    def _checks(self) -> "DeductionSetup":
        if self.period_numbers is not None and any(not 1 <= n <= 5 for n in self.period_numbers):
            raise ValueError(f"period_numbers {self.period_numbers} must be between 1 and 5")
        if self.source_basis is SetupSourceBasis.PRESENCE_ONLY:
            setup_fields = set(type(self).model_fields) - set(CanonicalRecord.model_fields)
            filled = sorted(
                name
                for name in setup_fields - self.PRESENCE_ONLY_ALLOWED - {"company_id", "employee_id", "source_basis"}
                if getattr(self, name) is not None
            )
            if filled:
                raise ValueError(f"presence_only setup must not carry setup details: {', '.join(filled)}")
        # Each weaker basis must say why on the record itself.
        required = {
            SetupSourceBasis.PRESENCE_ONLY: DiagnosticCode.SOURCE_UNAVAILABLE,
            SetupSourceBasis.CANDIDATE_ASSIGNMENT: DiagnosticCode.UNVALIDATED_SOURCE,
        }.get(self.source_basis)
        if required is not None and not any(d.code is required for d in self.diagnostics):
            raise ValueError(f"{self.source_basis.value} setup needs the {required.value} diagnostic")
        self.require_references(
            [
                ("company_id", self.company_id, EntityType.COMPANY),
                ("employee_id", self.employee_id, EntityType.EMPLOYEE),
                ("deduction_code_id", self.deduction_code_id, EntityType.DEDUCTION_CODE),
                ("benefit_enrollment_id", self.benefit_enrollment_id, EntityType.BENEFIT_ENROLLMENT),
            ]
        )
        return self
