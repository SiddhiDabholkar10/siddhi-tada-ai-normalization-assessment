"""Payroll adapters of Phase 5 step 3 (D-089): PayrollRun and Paycheck for the three providers on the
fixtures. The fixture's payroll edge cases are pinned here, by record id (D-091), with the rules the
step decided: missing amounts never zero (D-053), the isolved run join (D-050), UKG net pay
(D-052), the net pay comparison, ids-only checks and unknown values in the link check."""
import json
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from normalization.canonical.diagnostics import DiagnosticCode
from normalization.canonical.links import _classification_conflicts
from normalization.canonical.payroll import DeductionLine, PaymentLine
from normalization.canonical.values import ValueStatus
from normalization.employees.bundle import Bundle, Response, load_bundle
from normalization.employees.common import NP, Ctx, build
from normalization.entities.common import check_net_pay, route_code
from normalization.pipeline import normalize_bundle

ROOT = Path(__file__).resolve().parents[1]
NS, NAS = ValueStatus.NOT_PROVIDED, ValueStatus.NOT_APPLICABLE
DROP = object()


def fixture(provider: str) -> Bundle:
    return load_bundle(ROOT / "fixtures" / provider / "bundle.json")


def edited(provider: str, route_end: str, edit, **params) -> Bundle:
    """The fixture bundle with ``edit(body)`` applied to every response whose route ends with
    ``route_end`` and whose params include ``params``; ``edit`` returning DROP removes it."""
    bundle, responses = fixture(provider), []
    for response in bundle.responses:
        if response.route.endswith(route_end) and all(response.params.get(k) == v for k, v in params.items()):
            body = edit(json.loads(json.dumps(response.body, default=str)))
            if body is DROP:
                continue
            response = Response(response.route, response.params, response.status, body)
        responses.append(response)
    return Bundle(bundle.provider, bundle.tenant_id, tuple(responses))


def run(provider: str, bundle: Bundle | None = None):
    return normalize_bundle(bundle or fixture(provider))


def record(result, suffix: str):
    return next(r for name in ("payroll_runs", "paychecks") for r in result.records[name] if r.id.endswith(suffix))


def codes_at(item, field: str) -> set:
    return {d.code for d in item.diagnostics if d.field == field}


class PrismHR(unittest.TestCase):
    result = None

    @classmethod
    def setUpClass(cls):
        cls.result = run("prismhr")

    def paycheck(self, voucher: str):
        return record(self.result, f":paycheck:1001:{voucher}")

    def test_hours_and_units_follow_the_pay_code(self):
        """REG and OT (payReason H) are hours, PIECE (U) units (unit rule, D-051)."""
        lines = {line.earning_code.code: line for line in self.paycheck("000102").earnings}
        self.assertEqual((lines["REG"].hours, lines["REG"].field_status["units"]), (Decimal("80"), NAS))
        self.assertEqual((lines["PIECE"].units, lines["PIECE"].field_status["hours"]), (Decimal("120"), NAS))
        self.assertEqual((lines["REG"].is_cash, lines["REG"].rate_class.value.value), (True, "straight"))  # copied from the code

    def test_unknown_pay_code_keeps_hours_units_raw(self):
        def rename(body):
            body["payrollVoucher"][1]["earning"][2]["payCode"] = "NOCODE"
            return body
        result = run("prismhr", edited("prismhr", "getPayrollVoucherForBatch", rename, batchId="20250110-01", startpage="0"))
        paycheck = record(result, ":paycheck:1001:000102")
        line = paycheck.earnings[2]
        self.assertEqual((line.hours, line.units), (None, None))
        self.assertEqual((line.field_status["hours"], line.field_status["units"]), (NS, NS))
        self.assertIn(DiagnosticCode.UNIT_UNVERIFIED, codes_at(paycheck, "earnings[2]"))
        self.assertEqual(paycheck.provider_extensions["getPayrollVoucherForBatch:payrollVoucher[1].earning[2].hoursUnits"], 120)

    def test_blank_line_class_and_type_copy_the_code(self):
        """A line that sends no payClass or deductType takes its linked code's classification
        (D-047, D-089 review): REG is E (wages) and 401K is K (retirement, pre-tax) on the code."""
        def blank(body):
            voucher = body["payrollVoucher"][0]
            voucher["earning"][0]["payClass"] = ""
            voucher["deduction"][0]["deductType"] = ""
            return body
        bundle = edited("prismhr", "getPayrollVoucherForBatch", blank, batchId="20250110-01", startpage="0")
        paycheck = record(run("prismhr", bundle), ":paycheck:1001:000101")
        expected = record(self.result, ":paycheck:1001:000101")
        self.assertEqual(paycheck.earnings[0].pay_class.value.value, "wages")
        self.assertEqual(paycheck.earnings[0].pay_class, expected.earnings[0].pay_class)
        line, sent = paycheck.deductions[0], expected.deductions[0]
        self.assertEqual((line.category, line.tax_treatment, line.is_catch_up), (sent.category, sent.tax_treatment, sent.is_catch_up))
        self.assertEqual(line.category.value.value, "retirement")

    def test_arrears_voucher_is_a_full_zero_pay_record(self):
        """D-033: zero pay, benefit and employer contribution lines kept, retirement amounts null."""
        arrears = self.paycheck("000105")
        self.assertEqual((arrears.kind.value.value, arrears.net_pay), ("arrears", Decimal("0")))
        self.assertTrue(arrears.benefit_lines and arrears.employer_contributions)
        self.assertIsNone(arrears.retirement.employer_matching)
        self.assertEqual(arrears.retirement.field_status["employer_matching"], NS)

    def test_reversal_adjustment_and_vacation_vouchers(self):
        reversal = self.paycheck("000107")
        self.assertEqual(reversal.reverses_paycheck_id, self.paycheck("000102").id)
        self.assertEqual((reversal.void_date, reversal.kind.value.value), (date(2025, 1, 28), "regular"))
        self.assertEqual(record(self.result, ":payroll_run:1001:20250128-V1").run_type.value.value, "reversal")
        self.assertEqual(self.paycheck("000102").field_status["reverses_paycheck_id"], NAS)
        self.assertEqual(self.paycheck("000108").kind.value.value, "adjustment")
        self.assertEqual(self.paycheck("000109").kind.value.value, "vacation")
        self.assertEqual(record(self.result, ":payroll_run:1001:20250110-01").run_type.value.value, "scheduled")  # batch R (D-050)

    def test_batch_without_info_and_multi_group_periods(self):
        failed = record(self.result, ":payroll_run:1001:20250207-S1")
        self.assertEqual((failed.name, failed.status.value.value), (None, "failed"))
        self.assertIn(DiagnosticCode.SOURCE_UNAVAILABLE, codes_at(failed, "name"))
        self.assertEqual(failed.pay_periods[0].field_status["period_number"], NS)
        self.assertIn(DiagnosticCode.SOURCE_UNAVAILABLE, codes_at(failed, "pay_periods[0].period_number"))
        periods = record(self.result, ":payroll_run:1001:20250110-01").pay_periods
        self.assertEqual([p.pay_group_id.rsplit(":", 1)[1] for p in periods], ["BW", "MO"])

    def test_payments_hold_last4_only(self):
        payments = self.paycheck("000101").payments
        self.assertEqual(payments[0].method.raw_code, "checkAmt")
        self.assertEqual(payments[0].amount, Decimal("0"))  # a check line even at 0 (table notes)
        self.assertEqual([p.routing_last4 for p in payments[1:]], ["0010", "0023", "0036"])
        self.assertEqual([p.account_last4 for p in payments[1:]], [None, "6789", "1234"])
        self.assertEqual(payments[1].field_status["account_last4"], ValueStatus.HIDDEN_BY_SOURCE)

    def test_net_pay_is_compared_with_the_payments(self):
        for paycheck in self.result.records["paychecks"]:
            with self.subTest(paycheck=paycheck.id):
                self.assertFalse({d.code for d in paycheck.diagnostics} & {DiagnosticCode.RECONCILIATION_MISMATCH,
                                                                          DiagnosticCode.RECONCILIATION_INCOMPLETE})

        def change(body):
            body["payrollVoucher"][1]["netPay"] = "1.00"
            return body
        result = run("prismhr", edited("prismhr", "getPayrollVoucherForBatch", change, batchId="20250110-01", startpage="0"))
        self.assertIn(DiagnosticCode.RECONCILIATION_MISMATCH, codes_at(record(result, ":paycheck:1001:000102"), "net_pay"))


class Isolved(unittest.TestCase):
    result = None

    @classmethod
    def setUpClass(cls):
        cls.result = run("isolved")

    def paycheck(self, check: str, result=None):
        return record(result or self.result, f":paycheck:6001:{check}")

    def test_run_join_outcomes(self):
        """D-050: a check links only to exactly one completed run with its date and run number (101
        is also on 2024-01-12: the date decides). Only a run not processed, or two completed runs:
        conflicting_sources. No match: source_unavailable while a pay group history is a 404
        (D-011), not_provided once every history was read."""
        def same_date(body):
            for entry in body:
                if entry["id"] == 9099:
                    entry["payDate"] = "2025-01-10T00:00:00"
            return body
        every_history_read = run("isolved", edited("isolved", "payrollRunHistory", lambda body: DROP, paygroupId="7626"))
        two_completed = run("isolved", edited("isolved", "payrollRunHistory", same_date, paygroupId="7625"))
        cases = (  # check, result, linked run, status, diagnostic
            ("880001", self.result, "9101", None, None),
            ("880004", self.result, "9001", None, None),
            ("880003", self.result, None, NS, DiagnosticCode.CONFLICTING_SOURCES),
            ("880005", self.result, None, NS, DiagnosticCode.SOURCE_UNAVAILABLE),
            ("880005", every_history_read, None, NS, None),
            ("880001", two_completed, None, NS, DiagnosticCode.CONFLICTING_SOURCES),
        )
        for check_id, result, linked, status, code in cases:
            check = self.paycheck(check_id, result)
            with self.subTest(check=check_id, result="fixture" if result is self.result else "edited"):
                if linked:
                    self.assertTrue(check.payroll_run_id.endswith(f":payroll_run:6001:{linked}"))
                else:
                    self.assertEqual((check.payroll_run_id, check.field_status["payroll_run_id"]), (None, status))
                    self.assertEqual(codes_at(check, "payroll_run_id"), {code} if code else set())

    def test_listed_check_with_empty_detail_keeps_its_ids(self):
        """Choice 1 (D-089): the check is kept with its ids; everything else is not provided."""
        check = self.paycheck("880006")
        self.assertTrue(check.employee_id.endswith(":employee:6001:70002"))
        self.assertEqual((check.net_pay, check.field_status["net_pay"], check.field_status["earnings"]), (None, NS, NS))
        self.assertIn(DiagnosticCode.SOURCE_UNAVAILABLE, {d.code for d in check.diagnostics})

    def test_memo_earnings(self):
        """D-055: labels in the memo table become employer contributions (inferred, flag kept);
        'ER Life' stays an earning line with class memo."""
        check = self.paycheck("880001")
        self.assertEqual([(c.plan.name, c.amount) for c in check.employer_contributions],
                         [("401k Match", Decimal("57.0")), ("ER Medical", Decimal("310.0"))])
        self.assertTrue(check.employer_contributions[0].earning_code_id.endswith(":earning_code:6001:520"))
        self.assertIn(DiagnosticCode.INFERRED_MAPPING, codes_at(check, "employer_contributions[0]"))
        self.assertEqual({k: v for k, v in check.provider_extensions.items() if k.endswith("isMemoEarning")},
                         {"check:earnings[2].isMemoEarning": True, "check:earnings[3].isMemoEarning": True})
        life = next(line for line in check.earnings if line.earning_code.name == "ER Life")
        self.assertEqual((life.pay_class.value.value, life.pay_class.raw_code), ("memo", "isMemoEarning"))

    def test_null_memo_amount_stays_null(self):
        def blank(body):
            body["earnings"][2]["checkDollars"] = None
            return body
        check = self.paycheck("880001", run("isolved", edited("isolved", "checks/{id}", blank, id="880001")))
        contribution = check.employer_contributions[0]
        self.assertEqual((contribution.amount, contribution.field_status["amount"]), (None, NS))

    def test_garnishment_line_keeps_the_garnishment_id_not_a_code_reference(self):
        """Category garnishment from the route. The line id is the employee's garnishment id, not a
        pay item (live: 80 of 80, D-095): no deduction code reference, the id kept raw, no link problem."""
        check = self.paycheck("880001")
        line = check.deductions[2]
        self.assertEqual((line.deduction_code.name, line.category.value.value), ("Federal Tax Levy", "garnishment"))
        self.assertEqual((line.deduction_code_id, line.field_status["deduction_code_id"]), (None, ValueStatus.NOT_PROVIDED))
        self.assertEqual(check.provider_extensions["check:garnishments[0].id"], 77)
        self.assertFalse([p for p in self.result.link_problems if ":paycheck:" in p])

    def test_net_pay_matches_payments(self):
        check = self.paycheck("880001")
        self.assertEqual([p.amount for p in check.payments], [Decimal("0.0"), Decimal("347.44"), Decimal("1042.31")])
        self.assertEqual(check.sensitive_provider_extensions["check:directDeposits[0].account"], "*****0045")
        self.assertFalse(codes_at(check, "net_pay"))


class UKG(unittest.TestCase):
    result = None

    @classmethod
    def setUpClass(cls):
        cls.result = run("ukg-ready")

    def statement(self, sid: str, result=None):
        return record(result or self.result, f":paycheck:7001:{sid}")

    def test_tax_items_split_by_payer(self):
        lines = [(t.tax_code.name, t.paid_by.value, t.amount, t.taxable_wages, t.source_line_id) for t in self.statement("5001").taxes]
        social = [line for line in lines if line[0] == "Social Security"]
        self.assertEqual([line[1] for line in social], ["employee", "employer"])
        self.assertEqual(len({line[4] for line in social}), 1)
        additional = [line for line in lines if line[0] == "Additional Medicare"]
        self.assertEqual([(line[1], line[2]) for line in additional], [("employee", None)])
        self.assertIsNotNone(additional[0][3])  # wages kept, amount null (D-051)
        self.assertEqual([line[1] for line in lines if line[0] == "Federal Unemployment Tax"], ["employer"])

    def test_missing_amounts_are_null_never_zero(self):
        """D-053: every absent ee_amount of the fixture statements is null with not_provided."""
        bodies = {str(r.body["id"]): r.body for r in fixture("ukg-ready").responses if r.route.endswith("pay-statements/{id}")}
        found = set()
        for sid, body in bodies.items():
            paycheck = self.statement(sid)
            for block in ("earnings", "deductions", "payments"):
                for item, line in zip(body[block], getattr(paycheck, block)):
                    if "ee_amount" not in item:
                        found.add(block)
                        with self.subTest(statement=sid, block=block, line=item["id"]):
                            self.assertEqual((line.amount, line.field_status["amount"]), (None, NS))
        self.assertLessEqual({"earnings", "payments"}, found)  # the fixtures hold both cases

    def test_net_pay_derived_only_from_complete_cash_payments(self):
        """D-052: 100.0 + 982.76 (Fringe excluded); a Check without an amount blocks it."""
        full = self.statement("5001")
        self.assertEqual((full.net_pay, full.derived_totals), (Decimal("1082.76"), ["net_pay"]))
        self.assertEqual(full.payments[2].method.value.value, "non_cash")
        self.assertEqual((full.gross_pay, full.field_status["gross_pay"]), (None, NS))
        missing = self.statement("5002")
        self.assertEqual((missing.net_pay, missing.derived_totals, missing.field_status["net_pay"]), (None, [], NS))
        self.assertIn(DiagnosticCode.RECONCILIATION_INCOMPLETE, codes_at(missing, "net_pay"))

    def test_hours_from_milliseconds_and_contributions_from_er_amount(self):
        statement = self.statement("5001")
        self.assertEqual([line.hours for line in statement.earnings[:2]], [Decimal("80"), Decimal("2")])
        self.assertEqual([(c.deduction_code_id.rsplit(":", 1)[1], c.amount) for c in statement.employer_contributions],
                         [("801", Decimal("48.56")), ("802", Decimal("150.0"))])

    def test_status_and_links_travel_with_the_records(self):
        """D-030: statuses as sent; a statement links to the payroll it is read under and its EIN."""
        run_open = record(self.result, ":payroll_run:7001:3001")
        self.assertEqual(run_open.status.value.value, "open")
        self.assertEqual(self.statement("5001").payroll_run_id, run_open.id)
        self.assertEqual(self.statement("5001").tax_entity_id, run_open.tax_entity_id)
        finalized = record(self.result, ":payroll_run:7001:3002")
        self.assertEqual((finalized.status.value.value, finalized.finalized_date), ("finalized", date(2024, 12, 26)))
        self.assertIn(DiagnosticCode.SOURCE_UNAVAILABLE, codes_at(record(self.result, ":payroll_run:7001:3004"), "finalized_date"))

    def test_statement_detail_without_an_id_keeps_the_listed_id(self):
        """Two details of payroll 3001 that send no id still give two paychecks (the listed ids)."""
        result = run("ukg-ready", edited("ukg-ready", "pay-statements/{id}", lambda body: {}, payroll_id="3001"))
        ids = sorted(p.id.rsplit(":", 1)[1] for p in result.records["paychecks"])
        self.assertEqual(ids, ["5001", "5002", "5003", "5004"])

    def test_ein_missing_from_lookup_is_built_once_from_its_references(self):
        """An EIN id that lookup/eins omits but records name (live: the 2nd EIN) becomes one tax
        entity, from the fields those records send, marked reference_only; its links resolve (D-094)."""
        def only_501(body):
            body["items"] = [item for item in body["items"] if str(item["id"]) == "501"]
            return body

        def other_ein(body):
            body["ein"] = {"id": 598}  # named by this employee only: the detail sends a name, no tax id
            return body

        bundle = edited("ukg-ready", "lookup/eins", only_501)
        bundle = Bundle(bundle.provider, bundle.tenant_id, tuple(
            Response(r.route, r.params, r.status, other_ein(json.loads(json.dumps(r.body))))
            if r.route.endswith("employees/{aid}") and r.params.get("aid") == "1103" else r for r in bundle.responses))
        result = run("ukg-ready", bundle)
        company = result.records["companies"][0]
        by_id = {entity.id.rsplit(":", 1)[1]: entity for entity in company.tax_entities}
        self.assertEqual(sorted(by_id), ["501", "502", "598"])  # 502 named by payrolls 3003, 3004 and employee 1102: once
        self.assertEqual((by_id["502"].name, by_id["502"].ein, by_id["502"].country), ("Harbor Catering LLC", "84-2210458", "USA"))
        self.assertEqual((by_id["598"].name, by_id["598"].ein, by_id["598"].field_status["ein"]),
                         ("Harbor Kitchens Inc", None, ValueStatus.NOT_PROVIDED))
        marked = {d.field: d.message for d in company.diagnostics if d.code == DiagnosticCode.REFERENCE_ONLY}
        self.assertEqual(sorted(marked), ["tax_entities[1]", "tax_entities[2]"])
        self.assertIn("payrolls and employee details", marked["tax_entities[1]"])
        self.assertIn("employee details", marked["tax_entities[2]"])
        self.assertEqual(result.link_problems, [])
        linked = {r.tax_entity_id for r in result.records["payroll_runs"] + result.records["paychecks"] + result.records["employees"]}
        self.assertTrue({by_id["502"].id, by_id["598"].id} <= linked)


class Shared(unittest.TestCase):
    def test_tax_labels_in_and_out_of_the_tables(self):
        """D-056: a label in the table is inferred with a diagnostic at the line; others unknown."""
        for provider, inside, outside in (("prismhr", "Federal Income Tax", "UT Income Tax"),
                                          ("isolved", "FEDERAL WH", "OREGON TRANSIT EE"),
                                          ("ukg-ready", "Federal Income Tax", "Wisconsin")):
            seen = set()
            for paycheck in run(provider).records["paychecks"]:
                for index, line in enumerate(paycheck.taxes or []):
                    if line.tax_code.name not in (inside, outside):
                        continue
                    seen.add(line.tax_code.name)
                    with self.subTest(provider=provider, paycheck=paycheck.id, label=line.tax_code.name):
                        expected = DiagnosticCode.INFERRED_MAPPING if line.tax_code.name == inside else DiagnosticCode.UNKNOWN_CODE
                        self.assertIn(expected, codes_at(paycheck, f"taxes[{index}].tax_type"))
                        self.assertEqual(line.tax_type.value.value == "unknown", line.tax_code.name == outside)
                        self.assertEqual(line.field_status["jurisdiction"], NS)
            self.assertEqual(seen, {inside, outside}, provider)  # the fixtures hold both paths

    def test_net_pay_check_rules(self):
        def lines(*amounts):
            return [build(PaymentLine, method=route_code("check", "checkAmt"), amount=NP if a is None else Decimal(a)) for a in amounts]
        for amounts, net, expected in ((("10", "5"), "15", set()), (("10", "5"), "16", {DiagnosticCode.RECONCILIATION_MISMATCH}),
                                       (("10", None), "15", {DiagnosticCode.RECONCILIATION_INCOMPLETE})):
            ctx = Ctx("prismhr")
            check_net_pay(ctx, Decimal(net), lines(*amounts))
            with self.subTest(amounts=amounts, net=net):
                self.assertEqual({d.code for d in ctx.diagnostics}, expected)
        ctx = Ctx("prismhr")
        check_net_pay(ctx, NP, lines("10"))
        self.assertEqual(ctx.diagnostics, [])  # no net pay: nothing to compare

    def test_unknown_classification_is_not_a_conflict(self):
        """Choice 3: unknown on either side makes no claim; two known values that differ still conflict."""
        def line(category):
            return build(DeductionLine, category={"value": category, "raw_code": "x", "raw_label": None,
                                                   "basis": "unmapped" if category == "unknown" else "inferred"})
        self.assertEqual(_classification_conflicts("p", line("garnishment"), line("unknown"), ("category",)), [])
        self.assertEqual(_classification_conflicts("p", line("unknown"), line("benefit"), ("category",)), [])
        self.assertTrue(_classification_conflicts("p", line("garnishment"), line("benefit"), ("category",)))


if __name__ == "__main__":
    unittest.main()
