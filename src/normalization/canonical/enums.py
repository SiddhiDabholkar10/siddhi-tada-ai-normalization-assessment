"""Canonical enums for companies, employees, deposits, deductions, benefits and payroll.

Each enum has UNKNOWN (enforced by CanonicalEnum). Coded fields keep the provider's raw code
next to the value; mappings from provider codes are defined per provider in Phase 3 and
come from provider labels or documented code tables, never from code letters (D-026).
Enums used as plain fields (not Coded) describe where a value came from in the source
structure (e.g. which address block), not a provider code.
"""
from .values import CanonicalEnum

# --- Company -------------------------------------------------------------------------


class CompanyStatus(CanonicalEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    TERMINATED = "terminated"
    UNKNOWN = "unknown"


# --- Employment ----------------------------------------------------------------------


class EmploymentStatus(CanonicalEnum):
    ACTIVE = "active"
    LEAVE = "leave"
    INACTIVE = "inactive"  # provider says "inactive" without defining it (isolved)
    TERMINATED = "terminated"
    UNKNOWN = "unknown"


class WorkerType(CanonicalEnum):
    EMPLOYEE = "employee"  # W-2 employee
    CONTRACTOR = "contractor"  # 1099 contractor
    UNKNOWN = "unknown"


class EmploymentType(CanonicalEnum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    TEMPORARY = "temporary"
    UNKNOWN = "unknown"


class FlsaStatus(CanonicalEnum):
    EXEMPT = "exempt"
    NON_EXEMPT = "non_exempt"
    UNKNOWN = "unknown"


class TerminationType(CanonicalEnum):
    VOLUNTARY = "voluntary"
    INVOLUNTARY = "involuntary"
    UNKNOWN = "unknown"


# --- Pay -----------------------------------------------------------------------------


class PayType(CanonicalEnum):
    HOURLY = "hourly"
    SALARY = "salary"
    UNKNOWN = "unknown"


class PayFrequency(CanonicalEnum):
    DAILY = "daily"  # PrismHR pay period D (documented); UKG every_n_days with num_days 1
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    SEMIMONTHLY = "semimonthly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    SEMIANNUAL = "semiannual"
    ANNUAL = "annual"
    UNKNOWN = "unknown"


class RatePeriod(CanonicalEnum):
    """The period an amount or a number of hours refers to (per hour, per year, ...)."""

    HOUR = "hour"
    DAY = "day"
    WEEK = "week"
    PAY_PERIOD = "pay_period"
    MONTH = "month"
    YEAR = "year"
    UNKNOWN = "unknown"


# --- Organization --------------------------------------------------------------------


class OrgUnitType(CanonicalEnum):
    DEPARTMENT = "department"
    DIVISION = "division"
    LOCATION = "location"
    COST_CENTER = "cost_center"
    PROJECT = "project"
    UNKNOWN = "unknown"


class EeoJobCategory(CanonicalEnum):
    """EEO-1 job categories."""

    EXECUTIVES_SENIOR_OFFICIALS = "executives_senior_officials"
    FIRST_MID_LEVEL_MANAGERS = "first_mid_level_managers"
    PROFESSIONALS = "professionals"
    TECHNICIANS = "technicians"
    SALES_WORKERS = "sales_workers"
    ADMINISTRATIVE_SUPPORT = "administrative_support"
    CRAFT_WORKERS = "craft_workers"
    OPERATIVES = "operatives"
    LABORERS_HELPERS = "laborers_helpers"
    SERVICE_WORKERS = "service_workers"
    UNKNOWN = "unknown"


# --- Person and contact --------------------------------------------------------------


class AddressType(CanonicalEnum):
    HOME = "home"
    MAILING = "mailing"
    TAX_FORM = "tax_form"  # address for W-2 / tax forms (PrismHR w2Address)
    WORK = "work"
    UNKNOWN = "unknown"


class PhoneType(CanonicalEnum):
    HOME = "home"
    MOBILE = "mobile"
    WORK = "work"
    FAX = "fax"
    UNKNOWN = "unknown"


class EmailType(CanonicalEnum):
    WORK = "work"
    PERSONAL = "personal"
    UNKNOWN = "unknown"


class NationalIdType(CanonicalEnum):
    SSN = "ssn"
    ITIN = "itin"
    EIN = "ein"  # PrismHR accepts an EIN in the SSN field for contractors
    SIN = "sin"
    NOT_REQUIRED = "not_required"  # provider records that no id is needed (UKG NO_ID_NEEDED)
    UNKNOWN = "unknown"


class Gender(CanonicalEnum):
    FEMALE = "female"
    MALE = "male"
    NON_BINARY = "non_binary"
    NOT_DISCLOSED = "not_disclosed"
    UNKNOWN = "unknown"


class Ethnicity(CanonicalEnum):
    """EEO-1 race/ethnicity categories."""

    HISPANIC_OR_LATINO = "hispanic_or_latino"
    WHITE = "white"
    BLACK_OR_AFRICAN_AMERICAN = "black_or_african_american"
    ASIAN = "asian"
    NATIVE_HAWAIIAN_OR_PACIFIC_ISLANDER = "native_hawaiian_or_pacific_islander"
    AMERICAN_INDIAN_OR_ALASKA_NATIVE = "american_indian_or_alaska_native"
    TWO_OR_MORE_RACES = "two_or_more_races"
    NOT_DISCLOSED = "not_disclosed"
    UNKNOWN = "unknown"


class MaritalStatus(CanonicalEnum):
    SINGLE = "single"
    MARRIED = "married"
    DOMESTIC_PARTNER = "domestic_partner"
    SEPARATED = "separated"
    DIVORCED = "divorced"
    WIDOWED = "widowed"
    UNKNOWN = "unknown"


class CitizenshipStatus(CanonicalEnum):
    """Form I-9 attestation categories."""

    CITIZEN = "citizen"
    NONCITIZEN_NATIONAL = "noncitizen_national"
    PERMANENT_RESIDENT = "permanent_resident"
    AUTHORIZED_ALIEN = "authorized_alien"
    UNKNOWN = "unknown"


class Relationship(CanonicalEnum):
    SPOUSE = "spouse"
    DOMESTIC_PARTNER = "domestic_partner"
    CHILD = "child"
    DOMESTIC_PARTNER_CHILD = "domestic_partner_child"  # PrismHR DPC; not the employee's own child
    PARENT = "parent"
    SIBLING = "sibling"
    UNKNOWN = "unknown"


class QualificationType(CanonicalEnum):
    SKILL = "skill"
    EDUCATION = "education"
    CERTIFICATION = "certification"
    TRAINING = "training"
    LICENSE = "license"
    UNKNOWN = "unknown"


# --- Tax withholding -----------------------------------------------------------------


class TaxJurisdictionLevel(CanonicalEnum):
    FEDERAL = "federal"
    STATE = "state"
    LOCAL = "local"
    UNKNOWN = "unknown"


class TaxResidency(CanonicalEnum):
    RESIDENT = "resident"
    NON_RESIDENT = "non_resident"
    UNKNOWN = "unknown"


class FilingStatus(CanonicalEnum):
    SINGLE = "single"  # federal W-4 2020+: "single or married filing separately"
    MARRIED = "married"  # "Married" on pre-2020 federal W-4 and state forms; not married filing jointly
    MARRIED_FILING_JOINTLY = "married_filing_jointly"
    MARRIED_FILING_SEPARATELY = "married_filing_separately"
    HEAD_OF_HOUSEHOLD = "head_of_household"
    UNKNOWN = "unknown"  # includes state-specific statuses with no canonical equivalent


# --- Payroll -------------------------------------------------------------------------
#
# Run and paycheck vocabularies are kept apart (D-033, D-050): PrismHR batch type R means
# "Scheduled" while voucher type R means "Regular", and an R batch holds A and S vouchers.
# Values follow the provider labels; two labels are not merged into one value unless a source
# says they mean the same thing (e.g. PrismHR "Scheduled" and UKG "Regular" stay apart).


class PaycheckKind(CanonicalEnum):
    """Kind of paycheck (PrismHR voucher type, isolved check type). Reversal is not a kind: it is
    marked on the paycheck (D-033)."""

    REGULAR = "regular"
    SUPPLEMENTAL = "supplemental"
    VACATION = "vacation"
    ADJUSTMENT = "adjustment"
    ARREARS = "arrears"
    MANUAL = "manual"
    UNKNOWN = "unknown"


class PayrollRunType(CanonicalEnum):
    SCHEDULED = "scheduled"  # PrismHR batch R "Scheduled"
    REGULAR = "regular"  # UKG payroll type "Regular", isolved "Regular Payroll"
    SPECIAL = "special"  # PrismHR batch S "Special"
    SUPPLEMENTAL = "supplemental"  # UKG "Supplemental"
    ADJUSTMENT = "adjustment"
    REVERSAL = "reversal"  # PrismHR batch V "Reversal"
    VOID = "void"  # UKG "Void"
    MANUAL = "manual"
    CORRECTION = "correction"
    HISTORICAL = "historical"  # UKG "Historical": history loaded, not processed in the system
    CONVERSION = "conversion"  # isolved "Data Conversion" (all completed live runs, D-014)
    UNKNOWN = "unknown"


class PayrollRunStatus(CanonicalEnum):
    """Run status as the provider states it. Only completed and finalized describe processed
    pay; open means calculated but not finalized (UKG, D-030) and is never read as issued."""

    NOT_PROCESSED = "not_processed"  # isolved "Payroll Not Processed"
    NEW = "new"
    OPEN = "open"
    CLOSED = "closed"
    SUBMITTED = "submitted"
    COMPLETED = "completed"  # PrismHR COMP, isolved "Completed Payroll Run"
    FINALIZED = "finalized"  # UKG FINALIZED
    FAILED = "failed"  # UKG *_FAILED, PrismHR INITFAIL
    UNKNOWN = "unknown"


class PaycheckStatus(CanonicalEnum):
    PRINTED = "printed"  # PrismHR PRNT ("voucher status, such as printed")
    NEW = "new"
    OPEN = "open"  # UKG: calculated in an open payroll, not issued (D-030)
    CLOSED = "closed"
    FINALIZED = "finalized"
    INVALID = "invalid"
    UNKNOWN = "unknown"


class EarningClass(CanonicalEnum):
    """What an earning is (PrismHR payClass). Cash vs non-cash is a separate flag (is_cash),
    because class alone does not decide it (PrismHR TAXREF is memo and cash, D-023)."""

    WAGES = "wages"  # PrismHR E "Earnings"
    REIMBURSEMENT = "reimbursement"  # PrismHR R "Expense Reimbursement"
    NON_CASH_FRINGE = "non_cash_fringe"  # PrismHR F; isolved GTL and UKG "Fringe" lines (provisional)
    REPORTED_TIPS = "reported_tips"
    MEMO = "memo"  # PrismHR M, isolved isMemoEarning
    UNKNOWN = "unknown"


class RateClass(CanonicalEnum):
    """PrismHR pay code rateClass: S straight, P premium, D doubletime, O other."""

    STRAIGHT = "straight"
    PREMIUM = "premium"
    DOUBLETIME = "doubletime"
    OTHER = "other"
    UNKNOWN = "unknown"


class QuantityType(CanonicalEnum):
    """What an earning's quantity counts (PrismHR pay code payReason: H hours, U units). Decides
    whether a line's quantity may enter an hours field (unit rule, D-036)."""

    HOURS = "hours"
    UNITS = "units"
    UNKNOWN = "unknown"


class TaxType(CanonicalEnum):
    """Statutory tax on a paycheck line. No provider documents a tax type; mappings come from
    exact provider labels and are inferred (D-056). OTHER is a tax the label names clearly that
    has no category of its own here (e.g. a state workforce fund)."""

    FEDERAL_INCOME = "federal_income"
    SOCIAL_SECURITY = "social_security"
    MEDICARE = "medicare"
    ADDITIONAL_MEDICARE = "additional_medicare"
    FEDERAL_UNEMPLOYMENT = "federal_unemployment"
    STATE_INCOME = "state_income"
    STATE_UNEMPLOYMENT = "state_unemployment"
    STATE_DISABILITY = "state_disability"
    PAID_FAMILY_LEAVE = "paid_family_leave"
    LOCAL_INCOME = "local_income"
    OTHER = "other"
    UNKNOWN = "unknown"


class PaidBy(CanonicalEnum):
    """Who bears a tax line. Comes from the source structure (PrismHR employeeTax vs companyTax,
    isolved isEmployeeTax, UKG ee_amount vs er_amount), not from a code."""

    EMPLOYEE = "employee"
    EMPLOYER = "employer"
    UNKNOWN = "unknown"


class PaymentMethod(CanonicalEnum):
    CHECK = "check"
    DIRECT_DEPOSIT = "direct_deposit"
    # Offsets non-cash earnings; no money is paid (UKG "Fringe" payment lines). Not part of net pay.
    NON_CASH = "non_cash"
    UNKNOWN = "unknown"


# --- Direct deposit ------------------------------------------------------------------


class AllocationType(CanonicalEnum):
    FIXED_AMOUNT = "fixed_amount"
    PERCENT = "percent"
    REMAINDER = "remainder"  # receives what is left after the other allocations
    UNKNOWN = "unknown"


class PercentBasis(CanonicalEnum):
    NET_PAY = "net_pay"
    GROSS_PAY = "gross_pay"
    REMAINDER_AFTER_FIXED = "remainder_after_fixed"
    UNKNOWN = "unknown"


class AccountType(CanonicalEnum):
    CHECKING = "checking"
    SAVINGS = "savings"
    CHECKING_OR_PAY_CARD = "checking_or_pay_card"  # PrismHR 'C' does not say which
    PAY_CARD = "pay_card"
    INSTANT_PAY = "instant_pay"
    UNKNOWN = "unknown"


class DepositStatus(CanonicalEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PRENOTE = "prenote"  # account is being verified; deposits not yet live
    UNKNOWN = "unknown"


class PrenoteStatus(CanonicalEnum):
    PENDING = "pending"
    SENT = "sent"
    VERIFIED = "verified"
    EXPIRED = "expired"
    CANCELED = "canceled"
    INVALID = "invalid"
    UNKNOWN = "unknown"


class DepositFrequency(CanonicalEnum):
    EVERY_PAY = "every_pay"
    EVERY_SCHEDULED_PAY = "every_scheduled_pay"
    EVERY_OTHER_SCHEDULED_PAY = "every_other_scheduled_pay"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"
    MANUAL = "manual"
    UNKNOWN = "unknown"


# --- Deductions ----------------------------------------------------------------------


class DeductionCategory(CanonicalEnum):
    """Purpose of a deduction. Tax treatment is a separate dimension (TaxTreatment)."""

    BENEFIT = "benefit"
    RETIREMENT = "retirement"
    RETIREMENT_LOAN = "retirement_loan"
    LOAN = "loan"
    GARNISHMENT = "garnishment"
    FLEXIBLE_SPENDING = "flexible_spending"
    HEALTH_SAVINGS = "health_savings"
    VOLUNTARY = "voluntary"
    UNKNOWN = "unknown"


class TaxTreatment(CanonicalEnum):
    PRE_TAX = "pre_tax"
    POST_TAX = "post_tax"
    ROTH = "roth"
    UNKNOWN = "unknown"


class DeductionCalcMethod(CanonicalEnum):
    FIXED_AMOUNT = "fixed_amount"
    PERCENT_OF_GROSS_PAY = "percent_of_gross_pay"
    PERCENT_OF_GROSS_EARNINGS = "percent_of_gross_earnings"
    PERCENT_OF_STRAIGHT_PAY = "percent_of_straight_pay"
    PERCENT_OF_PAY_RATE = "percent_of_pay_rate"
    PERCENT_OF_NET_PAY = "percent_of_net_pay"
    RATE_TIMES_HOURS = "rate_times_hours"
    GARNISHMENT_RULE = "garnishment_rule"
    RETIREMENT_PLAN_RULE = "retirement_plan_rule"
    UNKNOWN = "unknown"


class LimitPeriod(CanonicalEnum):
    MONTH = "month"
    QUARTER = "quarter"
    YEAR = "year"
    LIFETIME = "lifetime"
    UNKNOWN = "unknown"


class SetupStatus(CanonicalEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    UNKNOWN = "unknown"


class SetupSourceBasis(CanonicalEnum):
    """How strongly the source establishes a deduction setup (D-048)."""

    DOCUMENTED_ASSIGNMENT = "documented_assignment"  # a provider route documented as employee deductions
    CANDIDATE_ASSIGNMENT = "candidate_assignment"  # best available source, not validated (isolved, D-017)
    PRESENCE_ONLY = "presence_only"  # provider says one exists; no setup details or code (PrismHR flags)
    UNKNOWN = "unknown"


class MatchMethod(CanonicalEnum):
    FLAT = "flat"
    PERCENT = "percent"
    UNKNOWN = "unknown"


class GarnishmentType(CanonicalEnum):
    CHILD_SUPPORT = "child_support"
    FEDERAL_TAX_LEVY = "federal_tax_levy"
    STATE_TAX_LEVY = "state_tax_levy"
    CREDITOR = "creditor"
    STUDENT_LOAN = "student_loan"
    BANKRUPTCY = "bankruptcy"
    UNKNOWN = "unknown"


class GarnishmentBasis(CanonicalEnum):
    GROSS_PAY = "gross_pay"
    GROSS_WAGES = "gross_wages"
    NET_PAY = "net_pay"
    DISPOSABLE_INCOME = "disposable_income"
    UNKNOWN = "unknown"


# --- Benefits ------------------------------------------------------------------------


class BenefitType(CanonicalEnum):
    MEDICAL = "medical"
    DENTAL = "dental"
    VISION = "vision"
    LIFE = "life"
    SHORT_TERM_DISABILITY = "short_term_disability"
    LONG_TERM_DISABILITY = "long_term_disability"
    UNKNOWN = "unknown"  # includes PrismHR insClass 'O', which is undocumented


class EnrollmentStatus(CanonicalEnum):
    ELIGIBLE_UNENROLLED = "eligible_unenrolled"
    ACTIVE = "active"
    TERMINATED = "terminated"
    COBRA = "cobra"
    WAIVED = "waived"
    UNKNOWN = "unknown"


class CoverageLevel(CanonicalEnum):
    EMPLOYEE_ONLY = "employee_only"
    EMPLOYEE_SPOUSE = "employee_spouse"
    EMPLOYEE_CHILDREN = "employee_children"
    FAMILY = "family"
    UNKNOWN = "unknown"
