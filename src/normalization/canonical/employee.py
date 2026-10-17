"""Canonical employee: one record per provider employee record (D-039).

PrismHR (client, employee), isolved employee (several employments kept in
employment_history), UKG account (one per EIN; a person's accounts share person_ref).
Sensitive fields are marked at field level (D-040) and masked by default in output (D-036).
"""
from datetime import date
from typing import ClassVar

from pydantic import Field, model_validator

from .base import CanonicalPart, CanonicalRecord
from .enums import (
    CitizenshipStatus,
    EeoJobCategory,
    EmailType,
    EmploymentStatus,
    EmploymentType,
    Ethnicity,
    FilingStatus,
    FlsaStatus,
    Gender,
    MaritalStatus,
    NationalIdType,
    OrgUnitType,
    PayFrequency,
    PayType,
    PhoneType,
    QualificationType,
    RatePeriod,
    Relationship,
    TaxJurisdictionLevel,
    TaxResidency,
    TerminationType,
    WorkerType,
)
from .ids import EntityType
from .parts import PersonalAddress, PersonName, Reference
from .values import SENSITIVE, Amount, Coded, CurrencyCode, Hours, Last4, Number, Percent

# --- Person --------------------------------------------------------------------------


class VeteranStatus(CanonicalPart):
    """VEVRAA categories as flags; a provider may set several."""

    is_veteran: bool | None = None
    is_protected_veteran: bool | None = None
    is_disabled_veteran: bool | None = None
    is_recently_separated_veteran: bool | None = None
    is_active_duty_wartime_or_campaign_badge_veteran: bool | None = None
    is_armed_forces_service_medal_veteran: bool | None = None
    not_disclosed: bool | None = None


class Disability(CanonicalPart):
    has_disability: bool | None = None
    description: str | None = None
    effective_date: date | None = None
    requires_accommodation: bool | None = None


class Demographics(CanonicalPart):
    """Protected personal characteristics. Every field is sensitive."""

    birth_date: date | None = Field(default=None, json_schema_extra=SENSITIVE)
    gender: Coded[Gender] | None = Field(default=None, json_schema_extra=SENSITIVE)
    ethnicity: Coded[Ethnicity] | None = Field(default=None, json_schema_extra=SENSITIVE)
    marital_status: Coded[MaritalStatus] | None = Field(default=None, json_schema_extra=SENSITIVE)
    citizenship: Coded[CitizenshipStatus] | None = Field(default=None, json_schema_extra=SENSITIVE)
    preferred_pronouns: str | None = Field(default=None, json_schema_extra=SENSITIVE)
    veteran: VeteranStatus | None = Field(default=None, json_schema_extra=SENSITIVE)
    disability: Disability | None = Field(default=None, json_schema_extra=SENSITIVE)
    tobacco_user: bool | None = Field(default=None, json_schema_extra=SENSITIVE)
    is_deceased: bool | None = Field(default=None, json_schema_extra=SENSITIVE)
    deceased_date: date | None = Field(default=None, json_schema_extra=SENSITIVE)


class NationalId(CanonicalPart):
    type: Coded[NationalIdType]
    value: str | None = Field(default=None, json_schema_extra=SENSITIVE)
    value_last4: Last4 | None = None
    is_primary: bool | None = None


class WorkContact(CanonicalPart):
    email: str | None = None
    phone: str | None = None
    phone_extension: str | None = None


class Phone(CanonicalPart):
    type: PhoneType
    number: str | None = Field(default=None, json_schema_extra=SENSITIVE)
    extension: str | None = None
    is_preferred: bool | None = None


class Email(CanonicalPart):
    type: EmailType
    address: str | None = Field(default=None, json_schema_extra=SENSITIVE)
    is_primary: bool | None = None


class PersonalContact(CanonicalPart):
    """Home and personal contact details. Street, postal code, numbers and addresses are
    sensitive (marked on the nested parts)."""

    addresses: list[PersonalAddress] | None = None
    phones: list[Phone] | None = None
    emails: list[Email] | None = None


class RelatedPerson(CanonicalPart):
    """A dependent, emergency contact or beneficiary: one entry per source item, never merged by
    name. ``source_id`` is the provider's id for the person (PrismHR dependentId, isolved
    contactId), used to join benefit dependents and beneficiaries (step 4). Identifying fields
    are sensitive (street lines, postal code, phone numbers and the id value on the nested parts)."""

    source_id: str | None = None
    relationship: Coded[Relationship] | None = None
    name: PersonName | None = Field(default=None, json_schema_extra=SENSITIVE)
    full_name: str | None = Field(
        default=None,
        json_schema_extra=SENSITIVE,
        description="The name as sent when the provider sends it as one string (PrismHR emergency contacts); never split.",
    )
    birth_date: date | None = Field(default=None, json_schema_extra=SENSITIVE)
    gender: Coded[Gender] | None = Field(default=None, json_schema_extra=SENSITIVE)
    national_id: NationalId | None = None
    address: PersonalAddress | None = None
    phones: list[Phone] | None = None
    email: str | None = Field(default=None, json_schema_extra=SENSITIVE)
    is_dependent: bool | None = None
    is_emergency_contact: bool | None = None
    is_beneficiary: bool | None = None
    is_active: bool | None = None


class WorkAuthorization(CanonicalPart):
    """Form I-9 and immigration-related facts. Every field is sensitive. ``i9_on_file`` (a form is
    on file) and ``i9_completed`` are different facts; one never fills the other."""

    i9_on_file: bool | None = Field(default=None, json_schema_extra=SENSITIVE)
    i9_completed: bool | None = Field(default=None, json_schema_extra=SENSITIVE)
    i9_completed_date: date | None = Field(default=None, json_schema_extra=SENSITIVE)
    document_expiration_date: date | None = Field(default=None, json_schema_extra=SENSITIVE)
    is_nonresident_alien: bool | None = Field(default=None, json_schema_extra=SENSITIVE)
    visa_type: str | None = Field(default=None, json_schema_extra=SENSITIVE)


class Qualification(CanonicalPart):
    """A skill, education, certification, training or license. ``source_id`` is the provider's id
    for the entry or the item it names (UKG skill id, the only identity it sends); ``code`` is the
    provider's code for it (PrismHR skillCode)."""

    type: QualificationType
    source_id: str | None = None
    code: str | None = None
    name: str | None = None
    level: str | None = None
    institution: str | None = None
    completed_date: date | None = None
    expiration_date: date | None = None
    years_experience: Number | None = None


# --- Employment and job --------------------------------------------------------------


class Employment(CanonicalPart):
    status: Coded[EmploymentStatus] | None = None
    status_effective_date: date | None = None
    worker_type: Coded[WorkerType] | None = None
    employment_type: Coded[EmploymentType] | None = None
    is_seasonal: bool | None = None
    flsa_status: Coded[FlsaStatus] | None = None
    original_hire_date: date | None = None
    hire_date: date | None = Field(default=None, description="Start of the current (latest) employment.")
    rehire_date: date | None = None
    seniority_date: date | None = None
    termination_date: date | None = None
    termination_type: Coded[TerminationType] | None = None
    termination_reason: str | None = Field(default=None, description="Provider's reason text or code, as sent.")
    eligible_for_rehire: bool | None = None


class EmploymentPeriod(CanonicalPart):
    """One entry of status history. ``employment_id`` keeps the provider's employment id
    (isolved holds several per employee); a second id does not mean the first is past."""

    employment_id: str | None = None
    status: Coded[EmploymentStatus] | None = None
    employment_type: Coded[EmploymentType] | None = None
    effective_date: date | None = None
    end_date: date | None = None
    reason: str | None = None


class OrgUnit(CanonicalPart):
    """An organization unit the employee belongs to. ``source_id`` is the provider's own id for
    the unit when it sends one (UKG cost center id); it is never used as ``code`` (D-076)."""

    type: Coded[OrgUnitType]
    source_id: str | None = None
    code: str | None = None
    name: str | None = None


class JobAssignment(CanonicalPart):
    """The current job (``Employee.job``) or one dated entry of job history
    (``Employee.job_history``). A history entry may change one thing only (a PrismHR department
    change carries only the department); its other fields are null with not_provided."""

    job: Reference | None = None
    effective_date: date | None = None
    org_units: list[OrgUnit] | None = None
    work_location_id: str | None = None
    manager_employee_id: str | None = None
    supervisor_employee_id: str | None = None
    eeo_category: Coded[EeoJobCategory] | None = None
    union_code: str | None = None
    workers_comp_code: str | None = None


# --- Compensation, tax, time off -----------------------------------------------------


class AdditionalRate(CanonicalPart):
    code: str | None = None
    name: str | None = None
    amount: Amount | None = None
    period: Coded[RatePeriod] | None = None


class Compensation(CanonicalPart):
    """Current pay. Amounts are in the employee's ``currency``. Pay frequency comes only from
    labeled or documented sources (D-018, D-041)."""

    pay_type: Coded[PayType] | None = None
    pay_frequency: Coded[PayFrequency] | None = None
    pay_group_id: str | None = None
    base_rate: Amount | None = None
    base_rate_period: Coded[RatePeriod] | None = None
    hourly_rate: Amount | None = None
    annual_salary: Amount | None = None
    per_period_amount: Amount | None = None
    standard_hours: Hours | None = None
    standard_hours_period: Coded[RatePeriod] | None = None
    effective_date: date | None = None
    additional_rates: list[AdditionalRate] | None = None


class CompensationChange(CanonicalPart):
    effective_date: date | None = None
    pay_type: Coded[PayType] | None = None
    amount: Amount | None = None
    amount_period: Coded[RatePeriod] | None = None
    hourly_rate: Amount | None = None
    annual_amount: Amount | None = None
    change_amount: Amount | None = None
    change_percent: Percent | None = None
    reason: str | None = None


class TaxWithholdingSetting(CanonicalPart):
    """One withholding setting. W-4 amounts (dependents, other income, deductions) are the
    employee's claims; ``is_blocked`` is a provider override that withholds nothing, which is not
    the same fact as an exempt claim (``is_exempt``)."""

    level: TaxJurisdictionLevel
    jurisdiction: str | None = Field(default=None, description="'US', a state code, or a locality code, as sent.")
    residency: TaxResidency | None = Field(
        default=None, description="Resident or non-resident of the jurisdiction; not_applicable for federal settings."
    )
    filing_status: Coded[FilingStatus] | None = None
    allowances: int | None = None
    additional_amount: Amount | None = None
    additional_percent: Percent | None = None
    is_exempt: bool | None = None
    multiple_jobs: bool | None = None
    dependents_amount: Amount | None = Field(default=None, description="Credit amount claimed for dependents (Form W-4 step 3).")
    other_income_amount: Amount | None = Field(default=None, description="Other income not from jobs (Form W-4 step 4a).")
    deductions_amount: Amount | None = Field(default=None, description="Deductions beyond the standard deduction (Form W-4 step 4b).")
    is_blocked: bool | None = Field(default=None, description="The provider blocks withholding for this tax (nothing is withheld).")


class TaxWithholding(CanonicalPart):
    federal: TaxWithholdingSetting | None = None
    states: list[TaxWithholdingSetting] | None = None
    locals: list[TaxWithholdingSetting] | None = None


class PtoBalance(CanonicalPart):
    """One time-off plan's balance (D-027). Hours fields hold only values whose unit is documented
    or verified (CANONICAL_MODEL 1.5). ``period_start`` and ``period_end`` bound the plan year the
    year-to-date amounts cover, when the provider sends them."""

    plan_source_id: str | None = None
    plan_code: str | None = None
    plan_name: str | None = None
    balance: Hours | None = None
    accrued_ytd: Hours | None = None
    used_ytd: Hours | None = None
    carryover: Hours | None = None
    as_of_date: date | None = None
    period_start: date | None = None
    period_end: date | None = None


# --- Employee ------------------------------------------------------------------------


class Employee(CanonicalRecord):
    ENTITY: ClassVar[EntityType] = EntityType.EMPLOYEE

    company_id: str
    tax_entity_id: str | None = None
    person_ref: str | None = Field(
        default=None,
        description=(
            "Provider's own key grouping several employee records of one person within this "
            "tenant (UKG primary_account_id). Not a cross-provider identity match."
        ),
    )
    employee_number: str | None = None
    currency: CurrencyCode | None = None
    name: PersonName | None = None
    demographics: Demographics | None = None
    national_ids: list[NationalId] | None = None
    work_contact: WorkContact | None = None
    personal_contact: PersonalContact | None = None
    employment: Employment | None = None
    employment_history: list[EmploymentPeriod] | None = None
    job: JobAssignment | None = None
    job_history: list[JobAssignment] | None = Field(
        default=None, description="Dated job, organization and location changes, each with its effective_date (D-069)."
    )
    compensation: Compensation | None = None
    compensation_history: list[CompensationChange] | None = None
    tax_withholding: TaxWithholding | None = Field(default=None, json_schema_extra=SENSITIVE)
    pto_balances: list[PtoBalance] | None = None
    related_people: list[RelatedPerson] | None = None
    qualifications: list[Qualification] | None = None
    work_authorization: WorkAuthorization | None = None

    @model_validator(mode="after")
    def _references(self) -> "Employee":
        checks = [
            ("company_id", self.company_id, EntityType.COMPANY),
            ("tax_entity_id", self.tax_entity_id, EntityType.TAX_ENTITY),
        ]
        jobs = [("job", self.job)] if self.job is not None else []
        jobs += [(f"job_history[{index}]", entry) for index, entry in enumerate(self.job_history or [])]
        for where, job in jobs:
            checks += [
                (f"{where}.work_location_id", job.work_location_id, EntityType.WORK_LOCATION),
                (f"{where}.manager_employee_id", job.manager_employee_id, EntityType.EMPLOYEE),
                (f"{where}.supervisor_employee_id", job.supervisor_employee_id, EntityType.EMPLOYEE),
            ]
        if self.compensation is not None:
            checks.append(("compensation.pay_group_id", self.compensation.pay_group_id, EntityType.PAY_GROUP))
        self.require_references(checks)
        return self
