"""Canonical company (D-034): the employer scope that owns employees and code tables.

PrismHR client, isolved legal entity (client kept as parent), UKG company. The company owns
lists that employees, setups and payroll refer to by canonical id: tax entities (EINs), work
locations, pay groups, deduction codes and earning codes.
"""
from datetime import date
from typing import ClassVar

from pydantic import Field, JsonValue, model_validator

from .base import CanonicalPart, CanonicalRecord
from .enums import (
    CompanyStatus,
    DeductionCalcMethod,
    DeductionCategory,
    EarningClass,
    PayFrequency,
    QuantityType,
    RateClass,
    TaxTreatment,
)
from .ids import EntityType
from .parts import PostalAddress, Reference
from .values import SENSITIVE, Coded


class CompanyEntry(CanonicalPart):
    """An entry of a company-owned list, referred to by canonical id. Provider settings of the
    entry with no canonical meaning (GL accounts, billing and arrears flags, external ids) stay
    with the entry in ``provider_extensions`` (D-063). None of the entries holds sensitive extras."""

    id: str
    provider_extensions: dict[str, JsonValue] = Field(
        default_factory=dict,
        description="Provider-specific settings of this entry, keyed by source field path within the entry (D-063).",
    )


class TaxEntity(CompanyEntry):
    """A legal employer identity (EIN). The id is built from the provider's own id for the
    entity (UKG ein id, isolved legal id, PrismHR client id), never from the EIN, which
    PrismHR masks. The EIN is sensitive (D-044): masked by default like personal identifiers."""

    name: str | None = None
    ein: str | None = Field(default=None, json_schema_extra=SENSITIVE)
    country: str | None = None


class WorkLocation(CompanyEntry):
    code: str | None = None
    name: str | None = None
    address: PostalAddress | None = None
    is_active: bool | None = None


class PayGroup(CompanyEntry):
    code: str | None = None
    name: str | None = None
    pay_frequency: Coded[PayFrequency] | None = None
    is_active: bool | None = None


class DeductionCode(CompanyEntry):
    """A deduction defined for the company (PrismHR client deduction code, UKG deduction code,
    isolved pay item catalog entry). Setups and paycheck lines refer to it, so a deduction is
    classified once (D-047). Category and tax treatment are separate dimensions; either is
    unknown when the provider does not establish it."""

    code: str | None = None
    name: str | None = None
    category: Coded[DeductionCategory] | None = None
    tax_treatment: Coded[TaxTreatment] | None = None
    is_catch_up: bool | None = None
    calc_method: Coded[DeductionCalcMethod] | None = None
    w2_box: str | None = None
    w2_code: str | None = None
    is_active: bool | None = None


class EarningCode(CompanyEntry):
    """An earning defined for the company (PrismHR client pay code, UKG earning code, isolved pay
    item catalog earning entry). Paycheck earning lines refer to it, so an earning is classified
    once (D-054). PrismHR documents payClass, compensationType, rateClass and payReason; UKG and
    isolved codes carry no type, so their classification is unknown unless configured."""

    code: str | None = None
    name: str | None = None
    pay_class: Coded[EarningClass] | None = None
    is_cash: bool | None = Field(default=None, description="Monetary compensation (PrismHR compensationType C) vs non-cash (N).")
    rate_class: Coded[RateClass] | None = None
    quantity_type: Coded[QuantityType] | None = None
    w2_box: str | None = None
    w2_code: str | None = None
    is_active: bool | None = None


class Company(CanonicalRecord):
    ENTITY: ClassVar[EntityType] = EntityType.COMPANY

    legal_name: str | None = None
    display_name: str | None = None
    company_code: str | None = None
    status: Coded[CompanyStatus] | None = None
    status_date: date | None = None
    address: PostalAddress | None = None
    phone: str | None = None
    parent: Reference | None = None
    tax_entities: list[TaxEntity] | None = None
    work_locations: list[WorkLocation] | None = None
    pay_groups: list[PayGroup] | None = None
    deduction_codes: list[DeductionCode] | None = None
    earning_codes: list[EarningCode] | None = None

    @model_validator(mode="after")
    def _owned_ids(self) -> "Company":
        problems = []
        for field, entity in (
            ("tax_entities", EntityType.TAX_ENTITY),
            ("work_locations", EntityType.WORK_LOCATION),
            ("pay_groups", EntityType.PAY_GROUP),
            ("deduction_codes", EntityType.DEDUCTION_CODE),
            ("earning_codes", EntityType.EARNING_CODE),
        ):
            items = getattr(self, field) or []
            for index, item in enumerate(items):
                problem = self.check_reference(f"{field}[{index}].id", item.id, entity)
                if problem:
                    problems.append(problem)
            ids = [item.id for item in items]
            if len(ids) != len(set(ids)):
                problems.append(f"{field} has duplicate ids")
        if problems:
            raise ValueError("; ".join(problems))
        return self
