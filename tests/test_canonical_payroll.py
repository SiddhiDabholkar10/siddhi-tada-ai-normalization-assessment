"""Tests for payroll runs, paychecks and earning codes (Phase 2, step 4).

Synthetic values only. Builders come from the step 2 and step 3 tests.
"""
import json
import unittest
from datetime import date

from pydantic import ValidationError

from normalization.canonical import (
    EntityType,
    MappingBasis,
    Paycheck,
    PayrollRun,
    canonical_id,
    to_json,
)
from normalization.canonical.company import EarningCode
from normalization.canonical.enums import (
    DeductionCategory,
    EarningClass,
    PaidBy,
    PaycheckKind,
    PaycheckStatus,
    PaymentMethod,
    PayrollRunStatus,
    PayrollRunType,
    QuantityType,
    RateClass,
    TaxTreatment,
    TaxType,
)
from normalization.canonical.links import find_link_problems
from normalization.canonical.parts import Reference
from normalization.canonical.payroll import (
    DeductionLine,
    EarningLine,
    EmployerContributionLine,
    PaymentLine,
    PayPeriod,
    TaxLine,
)
from test_canonical_company_employee import (
    COMPANY_ID,
    EIN_ID,
    EMPLOYEE_ID,
    MANAGER_ID,
    NP,
    P,
    PAY_GROUP_ID,
    SOURCE,
    T,
    coded,
    company,
    employee,
    explained,
)
from test_canonical_deposits_deductions_benefits import CODE_ID, DEPOSIT_ID, base, code_entry, deposit

from normalization.canonical import DirectDeposit

RUN_ID = canonical_id(P, T, EntityType.PAYROLL_RUN, "33704016", "4332471439")
PAYCHECK_ID = canonical_id(P, T, EntityType.PAYCHECK, "33704016", "85949527786")
ORIGINAL_ID = canonical_id(P, T, EntityType.PAYCHECK, "33704016", "85949500000")
EARNING_CODE_ID = canonical_id(P, T, EntityType.EARNING_CODE, "33704016", "REG")
INFERRED = MappingBasis.INFERRED


def run(**values):
    return explained(
        PayrollRun,
        **{
            "id": RUN_ID,
            "provider": P,
            "tenant_id": T,
            "source_ids": {"cid": "33704016", "id": "4332471439"},
            "sources": [SOURCE],
            "company_id": COMPANY_ID,
            **values,
        },
    )


def paycheck(**values):
    return explained(
        Paycheck,
        **{
            "id": PAYCHECK_ID,
            "provider": P,
            "tenant_id": T,
            "source_ids": {"cid": "33704016", "payroll": "4332471439", "id": "85949527786"},
            "sources": [SOURCE],
            "company_id": COMPANY_ID,
            "employee_id": EMPLOYEE_ID,
            **values,
        },
    )


def earning_code(code_id=EARNING_CODE_ID, **values):
    defaults = {
        "code": "REG",
        "pay_class": coded(EarningClass, EarningClass.WAGES, "E"),
        "is_cash": True,
        "rate_class": coded(RateClass, RateClass.STRAIGHT, "S"),
        "quantity_type": coded(QuantityType, QuantityType.HOURS, "H"),
    }
    return explained(EarningCode, id=code_id, **{**defaults, **values})


def regular_earning(**values):
    defaults = {
        "earning_code_id": EARNING_CODE_ID,
        "pay_class": coded(EarningClass, EarningClass.WAGES, "E"),
        "is_cash": True,
        "hours": "40.0",
        "rate": "23.50",
        "amount": "940.00",
    }
    return explained(EarningLine, **{**defaults, **values})


def tax(paid_by, amount, **values):
    return explained(
        TaxLine,
        source_line_id="1108665272006",
        tax_code=explained(Reference, code="Social Security", name="Social Security"),
        tax_type=coded(TaxType, TaxType.SOCIAL_SECURITY, "Social Security", INFERRED),
        paid_by=paid_by,
        amount=amount,
        **values,
    )


class PayrollRunTests(unittest.TestCase):
    def test_batch_with_several_pay_groups(self):
        periods = [
            explained(PayPeriod, pay_group_id=PAY_GROUP_ID, period_start=date(2025, 7, 27), period_end=date(2025, 8, 2)),
            explained(PayPeriod, period_start=date(2025, 7, 20), period_end=date(2025, 8, 2)),
        ]
        record = run(
            run_type=coded(PayrollRunType, PayrollRunType.SCHEDULED, "R"),
            status=coded(PayrollRunStatus, PayrollRunStatus.COMPLETED, "COMP"),
            pay_date=date(2025, 8, 8),
            tax_entity_id=EIN_ID,
            pay_periods=periods,
        )
        self.assertEqual(record.run_type.value, "scheduled")
        self.assertEqual(record.pay_periods[1].field_status["pay_group_id"], NP)
        self.assertEqual(PayrollRun.model_validate_json(to_json(record)), record)

class PaycheckTests(unittest.TestCase):
    def test_full_paycheck_round_trips(self):
        record = paycheck(
            payroll_run_id=RUN_ID,
            tax_entity_id=EIN_ID,
            kind=coded(PaycheckKind, PaycheckKind.REGULAR, "Regular"),
            status=coded(PaycheckStatus, PaycheckStatus.OPEN, "OPEN"),
            pay_date=date(2025, 12, 5),
            earnings=[regular_earning()],
            deductions=[
                explained(
                    DeductionLine,
                    deduction_code_id=CODE_ID,
                    category=coded(DeductionCategory, DeductionCategory.RETIREMENT, "K"),
                    amount="28.20",
                )
            ],
            taxes=[tax(PaidBy.EMPLOYEE, "58.28", rate="0.062"), tax(PaidBy.EMPLOYER, "58.28")],
            employer_contributions=[explained(EmployerContributionLine, deduction_code_id=CODE_ID, amount="9.40")],
            payments=[explained(PaymentLine, method=coded(PaymentMethod, PaymentMethod.CHECK, "Check"), amount="646.88")],
            net_pay="646.88",
            derived_totals=["net_pay"],
            currency="USD",
        )
        # UKG states no totals: net pay is derived from cash payments, gross pay stays null (D-052).
        self.assertEqual(record.field_status["gross_pay"], NP)
        dumped = json.loads(to_json(record))
        self.assertEqual(dumped["taxes"][0]["rate"], "0.062")
        self.assertEqual(dumped["earnings"][0]["hours"], "40.0")
        self.assertEqual(Paycheck.model_validate_json(to_json(record)), record)

    def test_derived_totals_must_name_filled_totals(self):
        paycheck(net_pay="646.88", derived_totals=["net_pay"])
        cases = [
            ({"derived_totals": ["check_number"], "check_number": "1"}, "'check_number', which is not a total"),
            ({"derived_totals": ["net_pay"]}, "'net_pay', which is null"),
            ({"derived_totals": ["net_pay", "net_pay"], "net_pay": "1.00"}, "derived_totals has duplicates"),
        ]
        for values, message in cases:
            with self.assertRaisesRegex(ValidationError, message):
                paycheck(**values)

    def test_references_point_at_their_entity(self):
        """Run and paycheck references, line references, and a reversal (never of itself)."""
        self.assertEqual(paycheck(reverses_paycheck_id=ORIGINAL_ID, void_date=date(2019, 8, 9)).reverses_paycheck_id, ORIGINAL_ID)
        cases = [
            (lambda: run(pay_periods=[explained(PayPeriod, pay_group_id=EIN_ID)]), r"pay_periods\[0\].pay_group_id .* is not a pay_group id"),
            (lambda: run(tax_entity_id=COMPANY_ID), "tax_entity_id .* is not a tax_entity id"),
            (lambda: paycheck(earnings=[regular_earning(earning_code_id=CODE_ID)]), r"earnings\[0\].earning_code_id .* is not a earning_code id"),
            (lambda: paycheck(payroll_run_id=PAYCHECK_ID), "payroll_run_id .* is not a payroll_run id"),
            (lambda: paycheck(reverses_paycheck_id=RUN_ID), "reverses_paycheck_id .* is not a paycheck id"),
            (lambda: paycheck(reverses_paycheck_id=PAYCHECK_ID), "a paycheck cannot reverse itself"),
        ]
        for build, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValidationError, message):
                    build()


class PayrollLinkTests(unittest.TestCase):
    find = staticmethod(find_link_problems)

    def records(self):
        manager = employee(id=MANAGER_ID, source_ids={"aid": "1000"})
        return [company(deduction_codes=[code_entry()], earning_codes=[earning_code()])], [employee(), manager]

    def deposit_line(self):
        return explained(
            PaymentLine,
            method=coded(PaymentMethod, PaymentMethod.DIRECT_DEPOSIT, "Direct Deposit"),
            amount="100.00",
            direct_deposit_id=DEPOSIT_ID,
        )

    def test_consistent_set(self):
        """A reversal of a paycheck outside the set is not checked; a payment names the
        employee's own deposit."""
        companies, employees = self.records()
        check = paycheck(
            payroll_run_id=RUN_ID,
            tax_entity_id=EIN_ID,
            pay_group_id=PAY_GROUP_ID,
            reverses_paycheck_id=ORIGINAL_ID,  # outside the set: not checked
            earnings=[regular_earning()],
            deductions=[explained(DeductionLine, deduction_code_id=CODE_ID)],
            payments=[self.deposit_line()],
        )
        periods = [explained(PayPeriod, pay_group_id=PAY_GROUP_ID)]
        problems = self.find(companies, employees, deposits=[deposit()], runs=[run(tax_entity_id=EIN_ID, pay_periods=periods)], paychecks=[check])
        self.assertEqual(problems, [])

    def test_broken_links_are_reported(self):
        companies, employees = self.records()
        foreign_earning = canonical_id(P, T, EntityType.EARNING_CODE, "999", "REG")
        foreign_pay_group = canonical_id(P, T, EntityType.PAY_GROUP, "999", "1")
        other_company = canonical_id(P, T, EntityType.COMPANY, "999")
        foreign_codes = paycheck(
            payroll_run_id=RUN_ID,
            pay_group_id=foreign_pay_group,
            earnings=[regular_earning(earning_code_id=foreign_earning)],
            employer_contributions=[explained(EmployerContributionLine, earning_code_id=foreign_earning)],
        )
        memo = regular_earning(pay_class=coded(EarningClass, EarningClass.MEMO, "M"), is_cash=False)
        roth = explained(DeductionLine, deduction_code_id=CODE_ID, tax_treatment=coded(TaxTreatment, TaxTreatment.ROTH, "KR"))
        # Reviewer case: a units-only line linked to an hours code passed the check. hours_worked is
        # not constrained (PrismHR U lines carry hoursWorked 0).
        units_code_id = canonical_id(P, T, EntityType.EARNING_CODE, "33704016", "BON")
        units_companies = [company(earning_codes=[earning_code(), earning_code(units_code_id, quantity_type=coded(QuantityType, QuantityType.UNITS, "U"))])]
        quantities = [
            regular_earning(hours=None, units="1.0", field_status={"hours": NP}),
            regular_earning(earning_code_id=units_code_id),
            regular_earning(earning_code_id=units_code_id, hours=None, units="1.0", hours_worked="0", field_status={"hours": NP}),
        ]
        managers_deposit = explained(DirectDeposit, **base(DEPOSIT_ID, employee_id=MANAGER_ID))
        with_deposit = paycheck(payments=[self.deposit_line()])
        cases = (  # name, problems, each problem in order (in full, or a field it names)
            ("missing run and foreign codes", self.find(companies, employees, paychecks=[foreign_codes]),
             ["pay_group_id", "payroll_run_id", "earnings[0].earning_code_id", "employer_contributions[0].earning_code_id"]),
            ("run of another company", self.find(companies, employees, runs=[run(company_id=other_company)], paychecks=[paycheck(payroll_run_id=RUN_ID)]),
             [f"{RUN_ID}: company_id {other_company!r} is not in the set", f"{PAYCHECK_ID}: payroll_run_id {RUN_ID!r} belongs to another company"]),
            ("lines reclassify their code", self.find(companies, employees, paychecks=[paycheck(earnings=[memo], deductions=[roth])]),
             [f"{PAYCHECK_ID} earnings[0]: pay_class 'memo' conflicts with its code's 'wages'",
              f"{PAYCHECK_ID} earnings[0]: is_cash conflicts with its code",
              f"{PAYCHECK_ID} deductions[0]: tax_treatment 'roth' conflicts with its code's 'pre_tax'"]),
            ("quantity differs from its code", self.find(units_companies, employees, paychecks=[paycheck(earnings=quantities)]),
             [f"{PAYCHECK_ID} earnings[0]: units is set but its code counts hours", f"{PAYCHECK_ID} earnings[1]: hours is set but its code counts units"]),
            ("another employee's deposit", self.find(companies, employees, deposits=[managers_deposit], paychecks=[with_deposit]),
             [f"{PAYCHECK_ID}: payments[0].direct_deposit_id {DEPOSIT_ID!r} belongs to another employee"]),
            ("deposit not in the set", self.find(companies, employees, paychecks=[with_deposit]),
             [f"{PAYCHECK_ID}: payments[0].direct_deposit_id {DEPOSIT_ID!r} is not in the set"]),
            ("run pay group of another company", self.find(companies, employees, runs=[run(pay_periods=[explained(PayPeriod, pay_group_id=foreign_pay_group)])]),
             [f"{RUN_ID}: pay_periods[0].pay_group_id {foreign_pay_group!r} is not owned by company {COMPANY_ID!r}"]),
        )
        for name, problems, expected in cases:
            with self.subTest(case=name):
                self.assertEqual(len(problems), len(expected))
                for problem, text in zip(problems, expected):
                    if text.startswith((PAYCHECK_ID, RUN_ID)):
                        self.assertEqual(problem, text)
                    else:
                        self.assertIn(text, problem)


if __name__ == "__main__":
    unittest.main()
