"""Canonical benefit enrollment: an employee's coverage in a benefit plan (D-049).

Separate from deduction setup (what is taken from pay) and from benefit lines on paychecks
(what was charged in one payroll). ``plan_details`` keeps every dated detail row: PrismHR
returns up to six per plan with distinct effective dates, so single premium fields would lose
history. Premium amounts keep their values; their period is not stated by PrismHR, so
``amount_period`` is null with not_provided rather than a guessed period.
"""
from datetime import date
from typing import ClassVar

from pydantic import model_validator

from .base import CanonicalPart, CanonicalRecord
from .enums import BenefitType, CoverageLevel, EnrollmentStatus, RatePeriod
from .ids import EntityType
from .parts import Reference
from .values import Amount, Coded, CurrencyCode


class BenefitPlanDetail(CanonicalPart):
    effective_date: date | None = None
    coverage_level: Coded[CoverageLevel] | None = None
    coverage_amount: Amount | None = None
    coverage_basis_amount: Amount | None = None
    employee_premium: Amount | None = None
    employee_contribution: Amount | None = None
    employee_premium_contribution: Amount | None = None
    provider_contribution: Amount | None = None
    dependent_premium: Amount | None = None
    amount_period: Coded[RatePeriod] | None = None


class BenefitEnrollment(CanonicalRecord):
    ENTITY: ClassVar[EntityType] = EntityType.BENEFIT_ENROLLMENT

    company_id: str
    employee_id: str
    plan: Reference | None = None
    benefit_type: Coded[BenefitType] | None = None
    status: Coded[EnrollmentStatus] | None = None
    coverage_level: Coded[CoverageLevel] | None = None
    coverage_start: date | None = None
    coverage_end: date | None = None
    deduction_start: date | None = None
    deduction_end: date | None = None
    is_section_125: bool | None = None
    waive_reason: str | None = None
    plan_details: list[BenefitPlanDetail] | None = None
    currency: CurrencyCode | None = None

    @model_validator(mode="after")
    def _checks(self) -> "BenefitEnrollment":
        self.require_references(
            [
                ("company_id", self.company_id, EntityType.COMPANY),
                ("employee_id", self.employee_id, EntityType.EMPLOYEE),
            ]
        )
        return self
