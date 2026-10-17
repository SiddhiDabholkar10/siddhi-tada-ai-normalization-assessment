"""Starter plumbing checks, updated when the adapters were implemented (D-087).

The delivered version asserted that all nine provider and entity transformations raise
NotImplementedError; its tests README said to replace those placeholder assertions once
implemented. The same call, ``adapter.normalize(entity, response, reference)``, now returns a
result for every provider and entity (the ``normalize`` command dispatches to it). The entity
list follows the brief's four data types (direct deposits and deductions added). These do not
assess transformation correctness: goldens, edge cases and table conformance do (tests/).
"""
import contextlib
import io
import json
import unittest
from pathlib import Path

from normalization.__main__ import main
from normalization.adapters import ADAPTERS, ENTITIES
from normalization.employees.bundle import load_bundle
from normalization.pipeline import TABLE_LISTS
from normalization.references import all_readiness_issues, load_reference

ROOT = Path(__file__).resolve().parents[1]


def fixture(provider: str):
    return load_bundle(ROOT / "fixtures" / provider / "bundle.json")


class StarterChecks(unittest.TestCase):
    def test_expected_providers_and_entities_are_exposed(self):
        self.assertEqual(set(ADAPTERS), {"prismhr", "isolved", "ukg-ready"})
        self.assertLessEqual({"company", "employee", "payroll"}, set(ENTITIES))  # the starter's three
        self.assertEqual(set(ENTITIES), {"company", "employee", "direct_deposit", "deduction_setup", "benefit_enrollment", "payroll"})

    def test_reference_readiness_matches_distributed_materials(self):
        issues = all_readiness_issues()
        self.assertEqual(load_reference("prismhr")["lookup_status"], "verified")
        self.assertEqual(issues["prismhr"], [])
        for provider in ("isolved", "ukg-ready"):
            with self.subTest(provider=provider):
                ref = load_reference(provider)
                self.assertEqual(ref["lookup_status"], "verified")
                self.assertTrue(ref["lookups"])
                self.assertEqual(ref["distribution"]["status"], "user_approved_private_upload")
                self.assertFalse(ref["distribution"]["provider_redistribution_permission_verified"])
                self.assertTrue(issues[provider])

    def test_every_provider_and_entity_is_normalized(self):
        """Phase 5 exit check (D-090): every provider and mapping table normalizes its fixture with
        no crash; each list returned has records or is named in run.not_normalized with its
        reason; no response is set aside. The normalize command calls this same function."""
        for provider, adapter in ADAPTERS.items():
            response = fixture(provider)
            for entity in ENTITIES:
                with self.subTest(provider=provider, entity=entity):
                    result = adapter.normalize(entity, response, load_reference(provider))
                    self.assertEqual(result["run"]["provider"], provider)
                    self.assertEqual(list(result), ["run", *TABLE_LISTS[entity]])
                    self.assertEqual(result["run"]["unusable_responses"], [])
                    for name in TABLE_LISTS[entity]:
                        self.assertTrue(result[name] or name in result["run"]["not_normalized"], name)
                    json.dumps(result)  # JSON-serializable, as the starter asked

    def test_readiness_command_exits_nonzero_for_missing_pack(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["check-inputs"]), 2)


if __name__ == "__main__":
    unittest.main()
