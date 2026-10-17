"""Tests for direct deposits, deduction codes and setups, benefit enrollments (Phase 2, step 3).

Synthetic values only. Builders come from the step 2 tests.
"""
import json
import unittest
from datetime import date

from pydantic import ValidationError

from normalization.canonical import (
    BenefitEnrollment,
    DeductionSetup,
    Diagnostic,
    DiagnosticCode,
    DirectDeposit,
    EntityType,
    MappingBasis,
    Severity,
    ValueStatus,
    canonical_id,
    to_json,
)
from normalization.canonical.benefits import BenefitPlanDetail
from normalization.canonical.company import DeductionCode
from normalization.canonical.deductions import GarnishmentDetails
from normalization.canonical.enums import (
    AccountType,
    AllocationType,
    BenefitType,
    DeductionCategory,
    DepositStatus,
    EnrollmentStatus,
    SetupSourceBasis,
    TaxTreatment,
)
from normalization.canonical.links import find_link_problems
from normalization.canonical.parts import Reference
from test_canonical_company_employee import (
    COMPANY_ID,
    EMPLOYEE_ID,
    MANAGER_ID,
    NP,
    P,
    SOURCE,
    T,
    coded,
    company,
    employee,
    explained,
)

CODE_ID = canonical_id(P, T, EntityType.DEDUCTION_CODE, "33704016", "401K")
DEPOSIT_ID = canonical_id(P, T, EntityType.DIRECT_DEPOSIT, "33704016", "47480384")
SETUP_ID = canonical_id(P, T, EntityType.DEDUCTION_SETUP, "33704016", "1001", "401K")
ENROLLMENT_ID = canonical_id(P, T, EntityType.BENEFIT_ENROLLMENT, "33704016", "17217889822")
HIDDEN = ValueStatus.HIDDEN_BY_SOURCE


def base(record_id, **values):
    return {
        "id": record_id,
        "provider": P,
        "tenant_id": T,
        "source_ids": {"id": record_id.rsplit(":", 1)[-1]},
        "sources": [SOURCE],
        "company_id": COMPANY_ID,
        "employee_id": EMPLOYEE_ID,
        **values,
    }


def deposit(**values):
    return explained(DirectDeposit, **base(DEPOSIT_ID, **values))


def setup(**values):
    values.setdefault("source_basis", SetupSourceBasis.DOCUMENTED_ASSIGNMENT)
    return explained(DeductionSetup, **base(SETUP_ID, **values))


def enrollment(**values):
    return explained(BenefitEnrollment, **base(ENROLLMENT_ID, **values))


def code_entry(code_id=CODE_ID):
    return explained(
        DeductionCode,
        id=code_id,
        code="K",
        category=coded(DeductionCategory, DeductionCategory.RETIREMENT, "K"),
        tax_treatment=coded(TaxTreatment, TaxTreatment.PRE_TAX, "K"),
    )


class DirectDepositTests(unittest.TestCase):
    def test_remainder_account_with_masked_number(self):
        record = deposit(
            sequence=0,
            allocation_type=coded(AllocationType, AllocationType.REMAINDER, "0"),
            account_type=coded(AccountType, AccountType.CHECKING, "Checking"),
            account_number=None,
            account_last4="1068",
            routing_number="000000000",
            status=coded(DepositStatus, DepositStatus.ACTIVE, "Active"),
            field_status={"account_number": HIDDEN},
        )
        self.assertEqual((record.account_number, record.account_last4), (None, "1068"))
        self.assertEqual(DirectDeposit.model_validate_json(to_json(record)), record)

    def test_percent_must_be_between_0_and_100(self):
        deposit(percent="15.0")
        for bad in ("100.01", "-1"):
            with self.assertRaisesRegex(ValidationError, "outside 0 to 100"):
                deposit(percent=bad)

    def test_references(self):
        with self.assertRaisesRegex(ValidationError, "employee_id .* is not a employee id"):
            deposit(employee_id=COMPANY_ID)

    def test_allocation_type_fixes_which_values_may_be_set(self):
        allocation = lambda kind, raw: coded(AllocationType, kind, raw)  # noqa: E731
        deposit(allocation_type=allocation(AllocationType.FIXED_AMOUNT, "F"), amount="10.00")
        deposit(allocation_type=allocation(AllocationType.PERCENT, "NET_PAY"), percent="15.0")
        deposit(allocation_type=allocation(AllocationType.REMAINDER, "FULL"))
        cases = [
            (AllocationType.REMAINDER, "FULL", {"amount": "10.00", "percent": "5"}, "remainder allocation must not carry amount, percent"),
            (AllocationType.FIXED_AMOUNT, "F", {"amount": "10.00", "percent": "5"}, "fixed_amount allocation must not carry percent"),
            (AllocationType.PERCENT, "P", {"amount": "10.00", "percent": "5"}, "percent allocation must not carry amount"),
        ]
        for kind, raw, values, message in cases:
            with self.assertRaisesRegex(ValidationError, message):
                deposit(allocation_type=allocation(kind, raw), **values)
        # Unknown allocation type: no constraint, the raw values are kept as sent.
        unknown = coded(AllocationType, AllocationType.UNKNOWN, "X", MappingBasis.UNMAPPED)
        deposit(allocation_type=unknown, amount="10.00", percent="5")


class DeductionTests(unittest.TestCase):
    UNAVAILABLE = [Diagnostic(code=DiagnosticCode.SOURCE_UNAVAILABLE, severity=Severity.WARNING, message="detail route 403")]

    def test_candidate_setup_needs_the_unvalidated_source_diagnostic(self):
        """D-017, D-048: an isolved candidate setup says so; it may have no code link."""
        with self.assertRaisesRegex(ValidationError, "candidate_assignment setup needs the unvalidated_source diagnostic"):
            setup(source_basis=SetupSourceBasis.CANDIDATE_ASSIGNMENT)
        diagnostic = Diagnostic(code=DiagnosticCode.UNVALIDATED_SOURCE, severity=Severity.WARNING, message="isolved legal pay item", evidence="D-017")
        record = setup(
            source_basis=SetupSourceBasis.CANDIDATE_ASSIGNMENT,
            deduction_code=explained(Reference, source_id="5372205", name="Medical Calcula"),
            diagnostics=[diagnostic],
        )
        self.assertEqual(record.field_status["deduction_code_id"], NP)

    def test_presence_only_garnishment_has_no_invented_details(self):
        """D-048: a presence_only setup carries no code, amount or garnishment details, and needs
        the source_unavailable diagnostic (another diagnostic is not enough)."""
        record = setup(
            source_basis=SetupSourceBasis.PRESENCE_ONLY,
            category=coded(DeductionCategory, DeductionCategory.GARNISHMENT, "enrolled"),
            garnishment=None,
            field_status={"garnishment": NP},
            diagnostics=self.UNAVAILABLE,
        )
        self.assertEqual((record.amount, record.field_status["garnishment"]), (None, NP))
        for values, field in (
            ({"deduction_code_id": CODE_ID}, "deduction_code_id"),
            ({"amount": "50.00"}, "amount"),
            ({"garnishment": explained(GarnishmentDetails)}, "garnishment"),
        ):
            with self.subTest(detail=field):
                with self.assertRaisesRegex(ValidationError, f"presence_only setup must not carry setup details: {field}"):
                    setup(source_basis=SetupSourceBasis.PRESENCE_ONLY, diagnostics=self.UNAVAILABLE, **values)
        other = [Diagnostic(code=DiagnosticCode.UNKNOWN_CODE, severity=Severity.WARNING, message="not the right reason")]
        for diagnostics in ([], other):
            with self.subTest(diagnostics=len(diagnostics)):
                with self.assertRaisesRegex(ValidationError, "presence_only setup needs the source_unavailable diagnostic"):
                    setup(source_basis=SetupSourceBasis.PRESENCE_ONLY, diagnostics=diagnostics)

    def test_period_numbers_are_1_to_5(self):
        self.assertEqual(setup(period_numbers=[1, 2, 3, 4, 5]).period_numbers, [1, 2, 3, 4, 5])
        with self.assertRaisesRegex(ValidationError, "between 1 and 5"):
            setup(period_numbers=[0, 6])


class BenefitEnrollmentTests(unittest.TestCase):
    def test_plan_detail_history_is_kept(self):
        rows = [
            explained(BenefitPlanDetail, effective_date=date(2017, 6, 1), employee_premium="16.06"),
            explained(BenefitPlanDetail, effective_date=date(2019, 3, 22), employee_premium="17.75"),
            explained(BenefitPlanDetail, effective_date=date(2025, 1, 1), employee_premium="450.76"),
        ]
        record = enrollment(
            plan=explained(Reference, code="BCBSPPO1000", name="BCBS PPO 1000"),
            benefit_type=coded(BenefitType, BenefitType.MEDICAL, "M"),
            status=coded(EnrollmentStatus, EnrollmentStatus.ACTIVE, "A"),
            plan_details=rows,
        )
        self.assertEqual([row.effective_date.year for row in record.plan_details], [2017, 2019, 2025])
        self.assertEqual(record.plan_details[0].field_status["amount_period"], NP)
        self.assertEqual(json.loads(to_json(record))["plan_details"][2]["employee_premium"], "450.76")


class LinkTests(unittest.TestCase):
    def records(self):
        companies = [company(deduction_codes=[code_entry()])]
        manager = employee(id=MANAGER_ID, source_ids={"aid": "1000"})
        return companies, [employee(), manager]

    def test_consistent_sets_have_no_problems(self):
        """A setup may repeat its code's classification or leave it null (a null is no claim)."""
        companies, employees = self.records()
        matching = setup(
            deduction_code_id=CODE_ID,
            category=coded(DeductionCategory, DeductionCategory.RETIREMENT, "K"),
            tax_treatment=coded(TaxTreatment, TaxTreatment.PRE_TAX, "K"),
        )
        for name, setups in (("linked", [setup(deduction_code_id=CODE_ID, benefit_enrollment_id=ENROLLMENT_ID)]),
                             ("same classification", [matching]),
                             ("null classification", [setup(deduction_code_id=CODE_ID)])):
            with self.subTest(case=name):
                problems = find_link_problems(companies, employees, deposits=[deposit()], setups=setups, enrollments=[enrollment()])
                self.assertEqual(problems, [])

    def test_broken_links_are_reported(self):
        """A code of another company, another employee's enrollment, a setup that reclassifies its
        code, a record whose company differs from its employee's, a missing employee."""
        companies, employees = self.records()
        foreign_code = canonical_id(P, T, EntityType.DEDUCTION_CODE, "999", "X")
        other_company = canonical_id(P, T, EntityType.COMPANY, "999")
        other_enrollment = explained(BenefitEnrollment, **base(ENROLLMENT_ID, employee_id=MANAGER_ID))
        roth = coded(TaxTreatment, TaxTreatment.ROTH, "KR")
        cases = (  # name, problems, each problem in order (in full, or a field it names)
            ("foreign code and enrollment",
             find_link_problems(companies, employees, setups=[setup(deduction_code_id=foreign_code, benefit_enrollment_id=ENROLLMENT_ID)],
                                enrollments=[other_enrollment]),
             ["deduction_code_id", "benefit_enrollment_id"]),
            ("reclassified code", find_link_problems(companies, employees, setups=[setup(deduction_code_id=CODE_ID, tax_treatment=roth)]),
             [f"{SETUP_ID}: tax_treatment 'roth' conflicts with its code's 'pre_tax'"]),
            ("company differs", find_link_problems(companies, employees, deposits=[deposit(company_id=other_company)]),
             [f"{DEPOSIT_ID}: company_id {other_company!r} differs from its employee's company"]),
            ("missing employee", find_link_problems(companies, [], deposits=[deposit()])[:1], ["is not in the set"]),
        )
        for name, problems, expected in cases:
            with self.subTest(case=name):
                self.assertEqual(len(problems), len(expected))
                for problem, text in zip(problems, expected):
                    if text.startswith((SETUP_ID, DEPOSIT_ID)):
                        self.assertEqual(problem, text)
                    else:
                        self.assertIn(text, problem)


if __name__ == "__main__":
    unittest.main()
