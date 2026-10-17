"""Entity adapters of Phase 5 step 2 (D-088): company, direct deposits, deduction setups and benefit
enrollments on the fixtures. The fixture's edge cases for these tables are pinned here, by record
id (D-091); the D-083 loan date rule is tested outcome by outcome."""
import json
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from normalization.canonical.diagnostics import DiagnosticCode
from normalization.canonical.parsing import DateRole
from normalization.canonical.values import ValueStatus
from normalization.employees.bundle import Bundle, Response, load_bundle
from normalization.employees.common import Ctx
from normalization.entities.prismhr.setups import loan_date
from normalization.pipeline import normalize_bundle

ROOT = Path(__file__).resolve().parents[1]
NS, NAS, HIDDEN = ValueStatus.NOT_PROVIDED, ValueStatus.NOT_APPLICABLE, ValueStatus.HIDDEN_BY_SOURCE


def run(provider: str, bundle: Bundle | None = None):
    return normalize_bundle(bundle or load_bundle(ROOT / "fixtures" / provider / "bundle.json"))


def by_id(provider: str, name: str, suffix: str):
    return next(r for r in run(provider).records[name] if r.id.endswith(suffix))


def codes(record) -> list[DiagnosticCode]:
    return [d.code for d in record.diagnostics]


def fields_with(record, code: DiagnosticCode) -> set:
    return {d.field for d in record.diagnostics if d.code is code}


class LoanDateRule(unittest.TestCase):
    """D-083: getEmployeeLoans dates documented YYYY-DD-MM, read both ways after the sentinel check."""

    def test_each_reading(self):
        """Valid one way only, or the same date both ways: that date. Two different dates: null,
        unparseable, the raw value kept. Valid neither way: null, unparseable. Sentinels first
        (0000-01-01 is valid neither way; D-025 decides by role). Blank: not provided."""
        key = "getEmployeeLoans:employeeLoanDetail[0].loanDate"
        UNPARSEABLE, SENTINEL = [DiagnosticCode.UNPARSEABLE_VALUE], [DiagnosticCode.SENTINEL_DATE]
        cases = (  # raw, role, value (a date, or a null's status), diagnostic codes, extensions
            ("2024-31-01", DateRole.EVENT, date(2024, 1, 31), [], {}),
            ("2024-10-15", DateRole.EVENT, date(2024, 10, 15), [], {}),
            ("2025-12-12", DateRole.EVENT, date(2025, 12, 12), [], {}),
            ("2024-11-01", DateRole.EVENT, NS, UNPARSEABLE, {key: "2024-11-01"}),
            ("2024-13-45", DateRole.EVENT, NS, UNPARSEABLE, {}),
            ("15/10/2024", DateRole.EVENT, NS, UNPARSEABLE, {}),
            ("0000-01-01", DateRole.EVENT, NS, SENTINEL, {}),
            ("9999-12-31", DateRole.PERIOD_END, NAS, [], {}),
            ("", DateRole.EVENT, NS, [], {}),
        )
        for raw, role, expected, diagnostics, extensions in cases:
            ctx = Ctx("prismhr")
            value = loan_date(ctx, raw, role, "loan.loan_date", key)
            with self.subTest(raw=raw):
                self.assertEqual(value if isinstance(value, date) else value.status, expected)
                self.assertEqual(([d.code for d in ctx.diagnostics], ctx.extensions), (diagnostics, extensions))
                if extensions:
                    self.assertIn(raw, ctx.diagnostics[0].message)


class Companies(unittest.TestCase):
    """Company ids agree with the employee adapters (D-080): test_pipeline pins the exact link
    problems per provider (only the deliberate isolved manager)."""

    def test_prismhr_client_without_code_tables(self):
        company = by_id("prismhr", "companies", ":company:1002")
        for name in ("pay_groups", "work_locations", "deduction_codes", "earning_codes"):
            self.assertEqual(company.field_status[name], NS)
            self.assertIn(name, fields_with(company, DiagnosticCode.SOURCE_UNAVAILABLE))

    def test_prismhr_masked_ein_and_unscheduled_pay_group(self):
        company = by_id("prismhr", "companies", ":company:1001")
        self.assertEqual(company.tax_entities[0].field_status["ein"], HIDDEN)
        monthly = next(group for group in company.pay_groups if group.code == "MO")
        self.assertEqual(monthly.field_status["pay_frequency"], NS)
        self.assertEqual(company.pay_groups[0].pay_frequency.value.value, "biweekly")

    def test_entry_extensions_keep_the_response_path(self):
        company = by_id("prismhr", "companies", ":company:1001")
        self.assertIn("getPayrollSchedule:clientPayrollSchedule[0].groupDesc", company.pay_groups[0].provider_extensions)

    def test_ukg_tax_entities_from_the_ein_lookup_only(self):
        company = by_id("ukg-ready", "companies", ":company:7001")
        self.assertEqual([t.id for t in company.tax_entities], ["ukg-ready:900003:tax_entity:7001:501", "ukg-ready:900003:tax_entity:7001:502"])
        self.assertEqual(company.field_status["work_locations"], NS)
        self.assertIn(DiagnosticCode.SOURCE_UNAVAILABLE, codes(company))


class Deposits(unittest.TestCase):
    def test_prismhr_methods_masks_and_position_ids(self):
        """test_fixtures.test_deposit_methods_and_masks: F, FS, P, PN, B and both mask forms."""
        deposits = run("prismhr").records["direct_deposits"]
        by_method = {d.allocation_type.raw_code: d for d in deposits}
        self.assertEqual(set(by_method), {"F", "FS", "P", "PN", "B"})
        self.assertEqual((by_method["F"].skip_if_insufficient, by_method["FS"].skip_if_insufficient), (False, True))
        self.assertEqual((by_method["P"].percent_basis.value.value, by_method["P"].percent_basis.raw_code), ("unknown", "P"))
        self.assertEqual(by_method["PN"].percent_basis.value.value, "remainder_after_fixed")
        self.assertEqual((by_method["B"].field_status["amount"], by_method["B"].field_status["percent"]), (NAS, NAS))
        hidden = by_method["F"]  # accountNum '****'
        self.assertEqual((hidden.field_status["account_number"], hidden.field_status["account_last4"]), (HIDDEN, HIDDEN))
        self.assertEqual(by_method["PN"].account_last4, "6789")
        for deposit in deposits:
            self.assertIn(DiagnosticCode.UNSTABLE_ID, codes(deposit))
            self.assertEqual(deposit.field_status["sequence"], NS)
        self.assertEqual([k.value.value for k in by_method["PN"].applies_to_paycheck_kinds], ["regular", "vacation", "supplemental"])
        self.assertEqual([k.value.value for k in by_method["F"].applies_to_paycheck_kinds], ["regular"])  # override

    def test_isolved_sequences(self):
        """test_fixtures.test_deposit_sequences: active 0 is the remainder, inactive 0 unknown, null kept null."""
        deposits = {d.source_ids["id"]: d for d in run("isolved").records["direct_deposits"]}
        self.assertEqual((deposits["42"].allocation_type.value.value, deposits["42"].allocation_type.basis.value), ("remainder", "inferred"))
        self.assertEqual(deposits["44"].allocation_type.value.value, "unknown")
        self.assertEqual((deposits["45"].field_status["sequence"], deposits["45"].amount), (NS, Decimal("50.0")))
        self.assertEqual(deposits["41"].field_status["amount"], NAS)  # a missing amount is never zero (D-053)
        self.assertFalse([d for d in deposits.values() if d.employee_id.endswith(":70003")])  # 404: none

    def test_ukg_methods_sentinels_and_deprecated_source(self):
        """test_fixtures.test_deposit_methods_and_sentinels."""
        deposits = run("ukg-ready").records["direct_deposits"]
        basis = {d.allocation_type.raw_code: (d.allocation_type.value.value, d.percent_basis.value.value if d.percent_basis else None)
                 for d in deposits}
        self.assertEqual(basis, {
            "FULL": ("remainder", None), "FLAT_AMOUNT": ("fixed_amount", None), "NET_PAY": ("percent", "net_pay"),
            "GROSS_EARNING": ("percent", "gross_pay"), "DIRECT_DEPOSIT_PER_OF_REMAINDER": ("percent", "remainder_after_fixed"),
        })
        self.assertTrue(all(DiagnosticCode.DEPRECATED_SOURCE in codes(d) for d in deposits))
        self.assertIn(NAS, {d.field_status.get("effective_to") for d in deposits})  # 2099-12-31
        self.assertIn(NAS, {d.field_status.get("effective_from") for d in deposits})  # 1900-12-31


class PrismhrSetups(unittest.TestCase):
    def setups(self, bundle: Bundle | None = None) -> dict:
        return {r.id.split(":", 3)[3]: r for r in run("prismhr", bundle).records["deduction_setups"]}

    def test_loan_dates_each_reading(self):
        """test_fixtures.test_loan_dates_cover_each_reading through the adapter (D-083)."""
        setups = self.setups()
        joined, own = setups["1001:P00001:LOAN"].loan, setups["1001:P00001:loan:LN-2"]
        self.assertEqual(joined.loan_date, date(2024, 10, 15))
        self.assertEqual(joined.field_status["deduction_start_date"], NS)  # 2024-11-01: ambiguous
        self.assertEqual(setups["1001:P00001:LOAN"].provider_extensions["getEmployeeLoans:employeeLoanDetail[0].startDate"], "2024-11-01")
        self.assertEqual((own.loan.loan_date, own.stop_date), (date(2024, 1, 31), date(2025, 12, 12)))

    def test_garnishment_given_refused_and_absent(self):
        """test_fixtures.test_garnishment_details_given_refused_and_absent (D-088)."""
        setups = self.setups()
        given = setups["1001:P00001:GARN"].garnishment
        self.assertEqual((given.type.value.value, given.amount, given.case_number), ("child_support", Decimal("100.00"), "UT-CS-2024-0912"))
        self.assertEqual(setups["1001:P00001:garnishment:SPOUSE"].source_basis.value, "documented_assignment")
        levy = setups["1001:P00002:IRS"]
        self.assertEqual(levy.field_status["garnishment"], NS)
        self.assertIn("garnishment", fields_with(levy, DiagnosticCode.SOURCE_UNAVAILABLE))
        self.assertFalse([key for key in setups if "garnishment_presence" in key])
        self.assertFalse([key for key in setups if ":P00003:" in key])

    def test_presence_only_when_no_garnishment_setup(self):
        """Details refused, enrolled true and no setup classified as garnishment: one presence_only
        setup (D-048, D-088). The fixture's P00002 has the IRS setup, so it is removed here."""
        bundle = load_bundle(ROOT / "fixtures" / "prismhr" / "bundle.json")
        responses = []
        for response in bundle.responses:
            if response.route == "/deductions/v1/getDeductions" and response.params.get("employeeId") == "P00002":
                body = json.loads(json.dumps(response.body, default=str))
                body["employeeDeductions"]["deduction"] = [d for d in body["employeeDeductions"]["deduction"] if d["deductionCode"] != "IRS"]
                response = Response(response.route, response.params, response.status, body)
            responses.append(response)
        setups = self.setups(Bundle(bundle.provider, bundle.tenant_id, tuple(responses)))
        flag = setups["1001:P00002:garnishment_presence"]
        self.assertEqual((flag.source_basis.value, flag.category.value.value, flag.status.value.value), ("presence_only", "garnishment", "active"))
        self.assertIn(DiagnosticCode.SOURCE_UNAVAILABLE, codes(flag))

    def test_repeated_code_and_markers(self):
        setups = self.setups()
        for key in ("1001:P00002:CHAR:0", "1001:P00002:CHAR:1", "1001:P00001:scheduled:0"):
            self.assertIn(DiagnosticCode.UNSTABLE_ID, codes(setups[key]))
        loan = setups["1001:P00001:retirement_loan:RL-7"]
        self.assertEqual((loan.category.value.value, loan.amount, loan.field_status["deduction_code_id"]), ("retirement_loan", Decimal("104.17"), NS))
        self.assertEqual(setups["1001:P00001:scheduled:0"].category.value.value, "voluntary")  # copied from code ADJ (D-088)

    def test_arrears_on_the_setup_or_the_employee(self):
        setups = self.setups()
        self.assertEqual(setups["1001:P00001:LTD"].provider_extensions["getDeductionArrears:deductionArrears[0].dedCode"], "LTD")
        employee = by_id("prismhr", "employees", ":P00001")
        self.assertEqual(employee.provider_extensions["getDeductionArrears:deductionArrears[1].dedCode"], "VIS")
        self.assertFalse([k for s in setups.values() for k in s.provider_extensions if k.startswith("getDeductionArrears:deductionArrears[1]")])

    def test_setup_links_its_enrollment(self):
        medical = self.setups()["1001:P00001:MED"]
        enrollments = {e.id for e in run("prismhr").records["benefit_enrollments"]}
        self.assertIn(medical.benefit_enrollment_id, enrollments)
        self.assertEqual(medical.employer_match.amount, Decimal("334.6"))


class IsolvedSetups(unittest.TestCase):
    def test_setup_join(self):
        """test_fixtures.test_setup_join: Deduction entries are candidate setups; the Earning entry
        goes to the employee; the negative-id placeholder makes nothing; no code stays unlinked."""
        setups = {s.source_ids.get("id") or s.source_ids["garnishmentId"]: s for s in run("isolved").records["deduction_setups"]}
        self.assertEqual(sorted(k for k, s in setups.items() if s.source_basis.value == "candidate_assignment"), ["9501", "9502", "9503", "9504"])
        for key in ("9501", "9502", "9503", "9504"):
            self.assertIn(DiagnosticCode.UNVALIDATED_SOURCE, codes(setups[key]))
        self.assertEqual(setups["9503"].field_status["deduction_code_id"], NS)
        self.assertEqual(setups["9501"].field_status["amount"], NS)  # Percent parameter: unit unverified, kept raw
        self.assertIn(DiagnosticCode.UNIT_UNVERIFIED, codes(setups["9501"]))
        self.assertEqual(setups["9502"].amount, Decimal("60.0"))
        employee = by_id("isolved", "employees", ":70001")
        self.assertEqual(employee.provider_extensions["employeePayItems:[2].payItemType"], "Earning")
        self.assertEqual(setups["77"].id, "isolved:900002:deduction_setup:6001:garnishment:77")

    def test_items_sent_to_the_employee_from_two_pages_are_both_kept(self):
        """D-090 review: an employee's Earning entries at results[0] of two legal pay item pages are
        both kept on the Employee; the page in the key keeps the second from overwriting the first."""
        bundle = load_bundle(ROOT / "fixtures" / "isolved" / "bundle.json")
        legal_route = "/api/clients/{clientId}/legals/{legalId}/payItems"
        responses = []
        for response in bundle.responses:
            body = json.loads(json.dumps(response.body, default=str))
            if response.route == legal_route:
                regular = next(e for e in body["results"] if e["payItemCode"] == "REG")
                overtime = dict(regular, id=9506, auditId=909506, payItemCode="OT", payItemName="Overtime", payItemId=502)
                responses.append(Response(response.route, response.params, 200, dict(body, results=[regular], totalPages=2)))
                responses.append(Response(response.route, dict(response.params, page="1"), 200,
                                          dict(body, results=[overtime], totalPages=2)))
                continue
            if response.route.endswith("{employeeId}/payItems") and response.params.get("employeeId") == "70001":
                regular = next(e for e in body if e["id"] == 9505)
                body.append(dict(regular, id=9506, auditId=909506, payItemCode="OT", payItemName="Overtime", payItemId=502))
                response = Response(response.route, response.params, response.status, body)
            responses.append(response)
        result = run("isolved", Bundle(bundle.provider, bundle.tenant_id, tuple(responses)))
        employee = next(e for e in result.records["employees"] if e.id.endswith(":70001"))
        codes_kept = {k: v for k, v in employee.provider_extensions.items() if k.startswith("legalPayItems") and k.endswith(".payItemCode")}
        self.assertEqual(codes_kept, {"legalPayItems(page=0):results[0].payItemCode": "REG",
                                      "legalPayItems(page=1):results[0].payItemCode": "OT"})


class ReferencedPayGroups(unittest.TestCase):
    def test_pay_group_missing_from_the_code_list_is_built_once_from_its_references(self):
        """A pay group that batches and employees name but getClientCodes omits (live: client 134,
        "Main") becomes one pay group with reference_only; its links resolve (D-097, as D-094)."""
        bundle = load_bundle(ROOT / "fixtures" / "prismhr" / "bundle.json")
        responses = []
        for response in bundle.responses:
            if response.route.endswith("getClientCodes"):
                body = json.loads(json.dumps(response.body, default=str))
                body["clientCodes"]["payGroups"] = [g for g in body["clientCodes"]["payGroups"] if g["payGroupCode"] != "MO"]
                response = Response(response.route, response.params, response.status, body)
            responses.append(response)
        result = run("prismhr", Bundle(bundle.provider, bundle.tenant_id, tuple(responses)))
        company = next(c for c in result.records["companies"] if c.id.endswith(":1001"))
        mo = [g for g in company.pay_groups if g.id.endswith(":MO")]
        self.assertEqual(len(mo), 1)
        self.assertEqual((mo[0].code, mo[0].name, mo[0].field_status["name"]), ("MO", None, ValueStatus.NOT_PROVIDED))
        marked = [d for d in company.diagnostics if d.code == DiagnosticCode.REFERENCE_ONLY]
        self.assertEqual([d.field for d in marked], [f"pay_groups[{company.pay_groups.index(mo[0])}]"])
        self.assertIn("batch lists", marked[0].message)
        self.assertIn("employees", marked[0].message)
        self.assertFalse([p for p in result.link_problems if "pay_group" in p])


if __name__ == "__main__":
    unittest.main()
