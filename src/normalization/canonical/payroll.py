"""Canonical payroll: payroll runs and paychecks with their line items (D-050 to D-056).

A run is a PrismHR batch, an isolved payroll run (run history) or a UKG payroll. A paycheck is
a PrismHR voucher, an isolved check or a UKG pay statement.

Rules that shape these models:
- Run type and paycheck kind are separate vocabularies (D-033, D-050).
- A zero-pay paycheck is a full record: arrears vouchers keep their benefit and employer
  contribution lines (D-033). Nothing here rejects a paycheck for having no pay.
- Totals are filled only from a provider field with the same definition, or derived from lines
  and then named in ``derived_totals`` (D-052).
- A missing amount is null with not_provided, never zero (D-053).
- Benefit lines and the retirement breakdown are informational and not additive: they repeat
  or break down amounts held elsewhere (D-051).
"""
from datetime import date
from typing import ClassVar

from pydantic import Field, model_validator

from .base import CanonicalPart, CanonicalRecord
from .enums import (
    DeductionCategory,
    EarningClass,
    PaidBy,
    PaycheckKind,
    PaycheckStatus,
    PaymentMethod,
    PayrollRunStatus,
    PayrollRunType,
    RateClass,
    TaxJurisdictionLevel,
    TaxTreatment,
    TaxType,
)
from .ids import EntityType
from .parts import Reference
from .values import Amount, Coded, CurrencyCode, Hours, Last4, Number, Rate

LINE_ID_DESCRIPTION = (
    "The provider's id for the line, as sent (isolved, UKG). A UKG tax line split into employee and "
    "employer sides keeps the same id on both."
)

# --- Payroll run ---------------------------------------------------------------------


class PayPeriod(CanonicalPart):
    """The period a run pays for one pay group. A PrismHR batch can cover several pay groups,
    each with its own period (15 of 1,813 sampled batches)."""

    pay_group_id: str | None = None
    period_start: date | None = None
    period_end: date | None = None
    period_number: int | None = Field(default=None, description="Pay period sequence number as sent (isolved payPeriod).")


class PayrollRun(CanonicalRecord):
    ENTITY: ClassVar[EntityType] = EntityType.PAYROLL_RUN

    company_id: str
    tax_entity_id: str | None = None
    name: str | None = Field(default=None, description="Provider's description of the run, as sent.")
    run_type: Coded[PayrollRunType] | None = None
    status: Coded[PayrollRunStatus] | None = None
    pay_date: date | None = None
    scheduled_pay_date: date | None = None
    run_number: int | None = Field(default=None, description="Run sequence number (isolved runNumber); joins checks to runs.")
    run_date: date | None = None
    finalized_date: date | None = None
    pay_periods: list[PayPeriod] | None = None

    @model_validator(mode="after")
    def _references(self) -> "PayrollRun":
        checks = [
            ("company_id", self.company_id, EntityType.COMPANY),
            ("tax_entity_id", self.tax_entity_id, EntityType.TAX_ENTITY),
        ]
        for index, period in enumerate(self.pay_periods or []):
            checks.append((f"pay_periods[{index}].pay_group_id", period.pay_group_id, EntityType.PAY_GROUP))
        self.require_references(checks)
        return self


# --- Paycheck lines ------------------------------------------------------------------


class EarningLine(CanonicalPart):
    """One earning. ``hours`` holds a quantity only when it is documented or verified as hours
    (PrismHR pay codes with payReason H, UKG milliseconds per D-028); a unit count goes in
    ``units``. ``amount`` is the line total (PrismHR payAmount, despite its spec description,
    D-051)."""

    source_line_id: str | None = Field(default=None, description=LINE_ID_DESCRIPTION)
    earning_code_id: str | None = None
    earning_code: Reference | None = Field(default=None, description="The provider's code, id and name as sent.")
    pay_class: Coded[EarningClass] | None = None
    is_cash: bool | None = None
    rate_class: Coded[RateClass] | None = None
    hours: Hours | None = Field(default=None, description="Hours paid.")
    hours_worked: Hours | None = None
    units: Number | None = Field(default=None, description="Units paid, for unit-based pay codes.")
    rate: Amount | None = Field(default=None, description="Rate per hour or unit.")
    amount: Amount | None = None


class DeductionLine(CanonicalPart):
    """An employee deduction taken in this payroll. Classification is inherited from the
    company deduction code (D-047). Garnishments are deduction lines with category garnishment."""

    source_line_id: str | None = Field(default=None, description=LINE_ID_DESCRIPTION)
    deduction_code_id: str | None = None
    deduction_code: Reference | None = Field(default=None, description="The provider's code, id and name as sent.")
    category: Coded[DeductionCategory] | None = None
    tax_treatment: Coded[TaxTreatment] | None = None
    is_catch_up: bool | None = None
    plan: Reference | None = Field(default=None, description="Benefit plan the deduction is for (PrismHR planId).")
    amount: Amount | None = None


class TaxLine(CanonicalPart):
    """One tax for one payer. Each line has a single ``paid_by``: UKG lines that hold employee
    and employer amounts together are split in two (D-051). A side with wage figures but no
    amount keeps the wages, with amount null."""

    source_line_id: str | None = Field(default=None, description=LINE_ID_DESCRIPTION)
    tax_code: Reference | None = Field(default=None, description="The provider's tax code and label as sent.")
    tax_type: Coded[TaxType] | None = None
    jurisdiction_level: Coded[TaxJurisdictionLevel] | None = None
    jurisdiction: str | None = Field(default=None, description="Jurisdiction the provider names: 'US', a state code or a locality name.")
    paid_by: PaidBy
    amount: Amount | None = None
    taxable_wages: Amount | None = None
    gross_wages: Amount | None = None
    exempt_wages: Amount | None = None
    over_limit_wages: Amount | None = None
    rate: Rate | None = Field(default=None, description="Tax rate as a fraction (PrismHR comTaxRate 0.0145).")


class EmployerContributionLine(CanonicalPart):
    """An amount the employer pays toward a plan. Sources: PrismHR employerContributions, UKG
    deduction er_amount (linked to that deduction code), isolved memo earnings whose label is
    in the mapping table (inferred, D-055). Retirement employer amounts are not repeated here:
    they stay in the non-additive retirement breakdown."""

    source_line_id: str | None = Field(default=None, description=LINE_ID_DESCRIPTION)
    plan: Reference | None = Field(default=None, description="Plan or code the contribution is for, as sent.")
    deduction_code_id: str | None = None
    earning_code_id: str | None = Field(default=None, description="isolved: the memo earning code it came from.")
    amount: Amount | None = None


class BenefitLine(CanonicalPart):
    """A benefit plan row as the provider reports it for this paycheck (PrismHR benefit[],
    isolved benefits[]). Informational and not additive: its amounts repeat deduction and
    employer contribution lines, and isolved also lists non-contribution rows here (D-051)."""

    plan: Reference | None = None
    coverage_period: str | None = Field(default=None, description="Coverage period as sent (PrismHR '202508').")
    premium_amount: Amount | None = None
    premium_cost: Amount | None = None
    employee_contribution: Amount | None = None
    employee_deduction: Amount | None = None
    employer_contribution: Amount | None = None
    catch_up_amount: Amount | None = None
    eligible_wages: Amount | None = None
    match_eligible_wages: Amount | None = None
    adjustment_ref: str | None = None


class RetirementBreakdown(CanonicalPart):
    """PrismHR voucher retirement block, employer side. Not additive: on 16 of 85 sampled
    vouchers the non-elective and both safe harbor fields are non-zero and equal, and how they
    relate is undocumented (D-051). Employee-side fields match the deduction lines of their
    type (repetition evidenced only for pre-tax elective and Roth; the other four are zero
    throughout the sample) and stay in provider_extensions as source evidence."""

    plan: Reference | None = None
    plan_year_period: str | None = None
    base_earnings: Amount | None = None
    employer_matching: Amount | None = None
    employer_non_elective: Amount | None = None
    employer_safe_harbor_1: Amount | None = None
    employer_safe_harbor_2: Amount | None = None
    peo_matching: Amount | None = None


class PaymentLine(CanonicalPart):
    """How net pay was delivered. ``method`` keeps the provider's label (UKG type_name) or, where
    the method comes from the source structure, the source field name. Non-cash lines (UKG
    "Fringe") are kept as information and are not part of net pay."""

    source_line_id: str | None = Field(default=None, description=LINE_ID_DESCRIPTION)
    method: Coded[PaymentMethod]
    amount: Amount | None = None
    direct_deposit_id: str | None = Field(default=None, description="The direct deposit record, when the source identifies it.")
    routing_last4: Last4 | None = None
    account_last4: Last4 | None = None


# --- Paycheck ------------------------------------------------------------------------


class Paycheck(CanonicalRecord):
    ENTITY: ClassVar[EntityType] = EntityType.PAYCHECK

    # Totals; each comes from a provider field with the same definition or is derived (D-052).
    TOTAL_FIELDS: ClassVar[tuple[str, ...]] = ("gross_pay", "gross_wages", "total_earnings", "net_pay")

    company_id: str
    employee_id: str
    payroll_run_id: str | None = Field(
        default=None, description="Null when the source does not identify the run (isolved checks are joined, D-050)."
    )
    tax_entity_id: str | None = None
    pay_group_id: str | None = None
    check_number: str | None = None
    kind: Coded[PaycheckKind] | None = None
    status: Coded[PaycheckStatus] | None = None
    is_manual_check: bool | None = None
    pay_date: date | None = None
    period_start: date | None = None
    period_end: date | None = None
    processed_date: date | None = None
    reverses_paycheck_id: str | None = Field(
        default=None, description="The paycheck this one reverses (PrismHR voidVoucherId). It may be outside the synced set."
    )
    void_date: date | None = None
    earnings: list[EarningLine] | None = None
    deductions: list[DeductionLine] | None = None
    taxes: list[TaxLine] | None = None
    employer_contributions: list[EmployerContributionLine] | None = None
    benefit_lines: list[BenefitLine] | None = None
    retirement: RetirementBreakdown | None = None
    payments: list[PaymentLine] | None = None
    gross_pay: Amount | None = Field(
        default=None, description="Cash earnings before taxes and deductions (PrismHR earnAmount, isolved grossPay)."
    )
    gross_wages: Amount | None = Field(
        default=None, description="isolved grossWages: gross pay plus imputed income (GTL). Not the same total as total_earnings."
    )
    total_earnings: Amount | None = Field(
        default=None, description="PrismHR totalEarnings: earnAmount plus other earnings (fringe, memo, other codes)."
    )
    net_pay: Amount | None = Field(default=None, description="Amount paid to the employee by check and direct deposit.")
    derived_totals: list[str] = Field(
        default_factory=list, description="Totals the adapter computed from lines instead of reading from the provider."
    )
    currency: CurrencyCode | None = None

    @model_validator(mode="after")
    def _checks(self) -> "Paycheck":
        problems = []
        for name in self.derived_totals:
            if name not in self.TOTAL_FIELDS:
                problems.append(f"derived_totals names {name!r}, which is not a total")
            elif getattr(self, name) is None:
                problems.append(f"derived_totals names {name!r}, which is null")
        if len(set(self.derived_totals)) != len(self.derived_totals):
            problems.append("derived_totals has duplicates")
        if self.reverses_paycheck_id is not None and self.reverses_paycheck_id == self.id:
            problems.append("a paycheck cannot reverse itself")
        if problems:
            raise ValueError("; ".join(problems))
        checks = [
            ("company_id", self.company_id, EntityType.COMPANY),
            ("employee_id", self.employee_id, EntityType.EMPLOYEE),
            ("payroll_run_id", self.payroll_run_id, EntityType.PAYROLL_RUN),
            ("tax_entity_id", self.tax_entity_id, EntityType.TAX_ENTITY),
            ("pay_group_id", self.pay_group_id, EntityType.PAY_GROUP),
            ("reverses_paycheck_id", self.reverses_paycheck_id, EntityType.PAYCHECK),
        ]
        for index, line in enumerate(self.earnings or []):
            checks.append((f"earnings[{index}].earning_code_id", line.earning_code_id, EntityType.EARNING_CODE))
        for index, line in enumerate(self.deductions or []):
            checks.append((f"deductions[{index}].deduction_code_id", line.deduction_code_id, EntityType.DEDUCTION_CODE))
        for index, line in enumerate(self.employer_contributions or []):
            checks.append((f"employer_contributions[{index}].deduction_code_id", line.deduction_code_id, EntityType.DEDUCTION_CODE))
            checks.append((f"employer_contributions[{index}].earning_code_id", line.earning_code_id, EntityType.EARNING_CODE))
        for index, line in enumerate(self.payments or []):
            checks.append((f"payments[{index}].direct_deposit_id", line.direct_deposit_id, EntityType.DIRECT_DEPOSIT))
        self.require_references(checks)
        return self
