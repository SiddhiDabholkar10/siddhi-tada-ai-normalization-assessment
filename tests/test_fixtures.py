"""Fixture bundles (D-080, D-082): synthetic, seeded, one per provider tenant, valid against the
contracts. The employee tables' mapped rows are all filled (the employee slice). The edge cases the
other entities need are pinned by the adapter tests that read them by record id (test_entities,
test_payroll, D-091); two source facts no adapter checks stay here."""
import json
import re
import unittest
from decimal import Decimal
from pathlib import Path

from normalization.employees.bundle import Bundle, parse_bundle
from normalization.fixtures.common import routing
from normalization.fixtures.contracts import contract_problems, undocumented_fields
from normalization.fixtures.write import BUILDERS, DEFAULT_SEED, FILE_NAME, MANIFEST, fixture_text, manifest_text
from normalization.mappings.spec import documented_routes
from normalization.mappings.tables import DATA, apply_live_renames, is_pattern, load_routes, row_routes

ROOT = Path(__file__).resolve().parents[1]
PROVIDERS = tuple(BUILDERS)


def committed(provider: str) -> str:
    return (ROOT / "fixtures" / provider / FILE_NAME).read_text(encoding="utf-8")


def bundle(provider: str) -> Bundle:
    return parse_bundle(committed(provider))


def bodies(provider: str, route: str) -> list:
    return [r.body for r in bundle(provider).responses if r.route == route and r.ok]


def filled_leaves(body, path: str = "") -> set[str]:
    """Field paths (``a[].b``) of every non-null, non-blank leaf of a response body."""
    if isinstance(body, dict):
        return {leaf for key, value in body.items() for leaf in filled_leaves(value, f"{path}.{key}" if path else key)}
    if isinstance(body, list):
        return {leaf for item in body for leaf in filled_leaves(item, path + "[]")}
    if body is None or (isinstance(body, str) and body.strip() == ""):
        return set()
    return {path or "$"}


def values_of(body, keys: set[str]) -> list:
    """Every value stored under one of ``keys``, at any depth."""
    if isinstance(body, dict):
        return [v for k, v in body.items() if k in keys] + [x for v in body.values() for x in values_of(v, keys)]
    if isinstance(body, list):
        return [x for item in body for x in values_of(item, keys)]
    return []


def employee_table(provider: str) -> dict:
    return json.loads((DATA / provider / "employee.json").read_text(encoding="utf-8"))



class FixtureTests(unittest.TestCase):
    def test_committed_fixtures_and_manifest_match_the_generator(self):
        for provider in PROVIDERS:
            with self.subTest(provider=provider):
                self.assertEqual(committed(provider), fixture_text(provider, DEFAULT_SEED),
                                 "regenerate with: python -m normalization generate-fixtures")
        self.assertEqual((ROOT / "fixtures" / MANIFEST).read_text(encoding="utf-8"), manifest_text(DEFAULT_SEED))

    def test_same_seed_same_bytes_other_seed_other_bytes(self):
        for provider in PROVIDERS:
            with self.subTest(provider=provider):
                self.assertEqual(fixture_text(provider, 7), fixture_text(provider, 7))
                self.assertNotEqual(fixture_text(provider, 7), fixture_text(provider, 8))

    def test_every_response_matches_its_documented_schema(self):
        """Each 200 body has an extracted schema (contract_problems passes when none exists),
        validates against it, and sends no field the contract does not document unless a
        live_only row names it (the specs rarely forbid extra keys)."""
        for provider in PROVIDERS:
            for response in bundle(provider).responses:
                if not response.ok:
                    continue
                with self.subTest(provider=provider, route=response.route, params=response.params):
                    self.assertIsNotNone(documented_routes(provider)[response.route].schema, "no extracted schema")
                    self.assertEqual(contract_problems(provider, response.route, response.body), [])
                    self.assertEqual(undocumented_fields(provider, response.route, response.body), [])

    def test_the_contract_checks_reject_a_wrong_type_and_a_mistyped_key(self):
        route = "/api/clients/{clientId}/legals/{legalId}/employees/{employeeId}/salaries"
        self.assertTrue(contract_problems("isolved", route, [{"effectiveDate": "x", "frequency": {}, "payGroup": {}, "payType": {"id": 5}}]))
        voucher_route = "/payroll/v1/getPayrollVoucherForBatch"
        self.assertEqual(undocumented_fields("prismhr", voucher_route, {"payrollVoucher": [{"netPay": 1}]}), [])
        self.assertTrue(undocumented_fields("prismhr", voucher_route, {"payrollVoucher": [{"netPayy": 1}]}))

    def test_the_empty_list_exception_admits_only_the_empty_list(self):
        """The isolved check detail may be [] (EMPTY_LIST_BODIES); any non-empty list still fails."""
        route = "/api/clients/{clientId}/legals/{legalId}/employees/{employeeId}/checks/{id}"
        self.assertEqual((contract_problems("isolved", route, []), undocumented_fields("isolved", route, [])), ([], []))
        for body in ([{}], [{}, {}], [{"id": 1}]):
            with self.subTest(body=body):
                self.assertTrue(contract_problems("isolved", route, body))
                self.assertTrue(undocumented_fields("isolved", route, body))

    def test_every_selected_route_is_in_the_bundle_once_per_request(self):
        """A bundle holds every selected route of its provider, and no two responses share a route
        and parameters (Bundle.get refuses duplicates)."""
        for provider in PROVIDERS:
            responses = bundle(provider).responses
            with self.subTest(provider=provider):
                selected = {entry["route"] for entry in load_routes(provider)["selected"]}
                self.assertEqual(selected - {r.route for r in responses}, set())
                keys = [(r.route, tuple(sorted(r.params.items()))) for r in responses]
                self.assertEqual([k for k in set(keys) if keys.count(k) > 1], [])

    def test_every_mapped_employee_row_is_filled_in_some_fixture(self):
        """Every exact mapped row of the employee tables has a value in a fixture response, so the
        employee goldens exercise every mapping rule the employee adapters apply."""
        for provider in PROVIDERS:
            renames = {e["route"]: e.get("live_renames", {}) for e in load_routes(provider)["selected"]}
            filled: dict[str, set[str]] = {}
            for response in bundle(provider).responses:
                if response.ok:
                    leaves = {apply_live_renames(leaf, renames.get(response.route, {})) for leaf in filled_leaves(response.body)}
                    filled.setdefault(response.route, set()).update(leaves)
            missing = []
            for row in employee_table(provider)["fields"]:
                if row["use"] != "mapped" or is_pattern(row["field"]):
                    continue
                for route in row_routes(row):
                    if not any(leaf == row["field"] or leaf.startswith(row["field"] + ".") or leaf.startswith(row["field"] + "[]")
                               for leaf in filled.get(route, set())):
                        missing.append(f"{route} {row['field']}")
            with self.subTest(provider=provider):
                self.assertEqual(missing, [])

    def test_fixtures_never_read_live_samples(self):
        """D-009: fixtures are built from code only; nothing under fixtures/ reads my_docs or live samples."""
        for path in (ROOT / "src" / "normalization" / "fixtures").glob("*.py"):
            text = path.read_text(encoding="utf-8")
            with self.subTest(file=path.name):
                self.assertNotRegex(text, r"my_docs|live_samples|open\(|read_text\(")

    def test_fixture_ssns_use_an_area_never_issued(self):
        for provider in PROVIDERS:
            for ssn in re.findall(r'"\d{3}-\d{2}-\d{4}"', committed(provider)):
                with self.subTest(provider=provider, ssn=ssn):
                    self.assertTrue(ssn.startswith('"666-'), ssn)

    def test_fixture_routing_numbers_are_invented(self):
        """Every routing number uses prefix 60 (reserved, never a bank's) with a valid check digit."""
        keys = {"transitNum", "routingNumber", "routing_number"}
        for provider in PROVIDERS:
            numbers = [v for r in bundle(provider).responses for v in values_of(r.body, keys)]
            self.assertTrue(numbers)
            for number in numbers:
                with self.subTest(provider=provider, number=number):
                    self.assertRegex(number, r"^60\d{7}$")
                    self.assertEqual(routing(number[2:8]), number)


def amount(value) -> Decimal:
    return Decimal(str(value or 0))


class PrismHRCases(unittest.TestCase):
    def vouchers(self) -> list[dict]:
        return [v for b in bodies("prismhr", "/payroll/v1/getPayrollVoucherForBatch") for v in b["payrollVoucher"]]

    def test_voucher_arithmetic_holds(self):
        """netPay = checkAmt + deposits on every voucher; netPay = earnAmount - employee taxes -
        deductions on every voucher but the type J adjustment (D-023)."""
        for v in self.vouchers():
            with self.subTest(voucher=v["voucherId"]):
                self.assertEqual(amount(v["netPay"]), amount(v["checkAmt"]) + sum(amount(d["amount"]) for d in v["directDeposit"]))
                derived = amount(v["earnAmount"]) - sum(amount(t["empTaxAmount"]) for t in v["employeeTax"]) - sum(amount(d["deductAmount"]) for d in v["deduction"])
                if v["type"] == "J":
                    self.assertNotEqual(amount(v["netPay"]), derived)
                else:
                    self.assertEqual(amount(v["netPay"]), derived)

    def test_garnishment_details_given_refused_and_absent(self):
        responses = bundle("prismhr").all("/deductions/v1/getGarnishmentDetails")
        statuses = {r.params["employeeId"]: r.status for r in responses}
        checks = {r.params["employeeId"]: r.body for r in bundle("prismhr").all("/employee/v1/checkForGarnishments")}
        self.assertEqual(statuses["P00001"], 200)
        # Refused with enrolled true: P00002 already has a garnishment setup (IRS, type VG), so that
        # setup's garnishment part is null with source_unavailable and no presence_only setup is
        # made (D-088); test_entities covers the presence_only case on a modified bundle.
        self.assertEqual((statuses["P00002"], checks["P00002"]["enrolled"]), (403, True))
        self.assertEqual((statuses["P00003"], checks["P00003"]["enrolled"]), (403, False))


if __name__ == "__main__":
    unittest.main()
