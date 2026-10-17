"""Pipeline (D-085): records filed under their output lists, the set checked, the link check run on
the assembled records and its problems reported without failing the run."""
import contextlib
import io
import json
import re
import tempfile
import unittest
from pathlib import Path

from pydantic import BaseModel

from normalization.__main__ import main
from normalization.adapters import ADAPTERS
from normalization.canonical.parsing import parse_source_json
from normalization.canonical.values import ValueStatus
from normalization.employees.bundle import load_bundle
from normalization.pipeline import RECORD_LISTS, assemble, normalize_bundle, not_normalized
from test_canonical_company_employee import P, T, company, employee
from test_canonical_deposits_deductions_benefits import deposit

ROOT = Path(__file__).resolve().parents[1]
PROVIDERS = ("prismhr", "isolved", "ukg-ready")


def run(provider: str):
    return normalize_bundle(load_bundle(ROOT / "fixtures" / provider / "bundle.json"))


class AssembleTests(unittest.TestCase):
    def test_records_go_to_their_lists_in_id_order(self):
        lists = assemble([deposit(), employee(), company(), employee(id=employee().id.replace("1001", "0999"))], P.value, T)
        self.assertEqual(list(lists), list(RECORD_LISTS))
        self.assertEqual([len(items) for items in lists.values()], [1, 2, 1, 0, 0, 0, 0])
        self.assertEqual([e.id for e in lists["employees"]], sorted(e.id for e in lists["employees"]))

    def test_a_repeated_id_fails(self):
        with self.assertRaisesRegex(ValueError, "employees: ids given more than once"):
            assemble([employee(), employee()], P.value, T)

    def test_another_provider_or_tenant_fails(self):
        with self.assertRaisesRegex(ValueError, "not of bundle provider"):
            assemble([employee()], "prismhr", T)
        with self.assertRaisesRegex(ValueError, "not of bundle provider"):
            assemble([employee()], P.value, "1")

    def test_a_type_outside_the_output_lists_fails(self):
        with self.assertRaisesRegex(ValueError, "is not an output record type"):
            assemble([employee().name], P.value, T)


class RunTests(unittest.TestCase):
    def test_empty_lists_say_why(self):
        """A list is empty exactly when the run header names it with a reason: a table without an
        adapter, or a provider without a table (UKG deduction setups, D-030)."""
        self.assertEqual(not_normalized("ukg-ready")["deduction_setups"],
                         "no deduction_setup mapping table: the provider has no source")
        for provider in PROVIDERS:
            result = run(provider)
            for name, records in result.records.items():
                with self.subTest(provider=provider, records=name):
                    self.assertEqual(not records, name in result.not_normalized)

    def test_link_check_runs_on_the_assembled_records(self):
        """Phase 5 step 2: companies, deposits, setups and enrollments link with no problem. The one
        problem is deliberate: an isolved manager in legal 6002, which the bundle does not hold
        (test_employee_golden.test_managers_across_legals); a partial set reports it (D-045)."""
        expected = {
            "prismhr": [],
            "isolved": ["isolved:900002:employee:6001:70001: job.manager_employee_id 'isolved:900002:employee:6002:70009' is not in the set"],
            "ukg-ready": [],
        }
        for provider in PROVIDERS:
            with self.subTest(provider=provider):
                self.assertEqual(run(provider).link_problems, expected[provider])

    def test_diagnostics_point_at_fields_of_their_record(self):
        """Every diagnostic field on the fixtures names a path of its own record: each part a field
        of a filled part, each index inside its list (D-091). The last part may be null (the
        diagnostic explains it); a path that goes on below a null part is rejected."""
        def resolves(record, path: str) -> bool:
            node = record
            for part in path.split("."):
                match = re.fullmatch(r"([a-z_][a-z0-9_]*)(?:\[(\d+)\])?", part)
                if match is None or not isinstance(node, BaseModel) or match[1] not in type(node).model_fields:
                    return False  # also a part below a null: node is None there
                node = getattr(node, match[1])
                if match[2] is not None:
                    if not isinstance(node, list) or int(match[2]) >= len(node):
                        return False
                    node = node[int(match[2])]
            return True

        sample = employee(compensation=None, field_status={"compensation": ValueStatus.NOT_PROVIDED})
        self.assertTrue(resolves(sample, "compensation"))  # a null leaf
        self.assertTrue(resolves(sample, "national_ids[0].value"))
        for invalid in ("no_such_field", "compensation.pay_group_id", "national_ids[1].value", "national_ids[0].no_such_field", "name[0]"):
            with self.subTest(invalid=invalid):
                self.assertFalse(resolves(sample, invalid))
        for provider in PROVIDERS:
            checked = 0
            for records in run(provider).records.values():
                for record in records:
                    for diagnostic in record.diagnostics:
                        if diagnostic.field is not None:
                            checked += 1
                            with self.subTest(provider=provider, record=record.id, field=diagnostic.field):
                                self.assertTrue(resolves(record, diagnostic.field))
            self.assertGreater(checked, 50, provider)  # not vacuous

    def test_cli_reports_link_problems_on_stderr_and_in_the_run_without_failing(self):
        source = ROOT / "fixtures" / "isolved" / "bundle.json"
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "out.json"
            errors = io.StringIO()
            with contextlib.redirect_stderr(errors):
                self.assertEqual(main(["normalize", "--input", str(source), "--output", str(target)]), 0)
            document = json.loads(target.read_text(encoding="utf-8"))
        problems = document["run"]["link_problems"]
        self.assertTrue(problems)
        self.assertEqual(errors.getvalue().splitlines(), [f"link problem: {problem}" for problem in problems])
        self.assertEqual(list(document), ["run", *RECORD_LISTS])
        self.assertEqual(document["run"]["counts"], {name: len(document[name]) for name in RECORD_LISTS})
        self.assertEqual(document["run"]["input"], "bundle.json")  # the file name only, not the local path

    def test_the_starter_command_shape_works(self):
        """``normalize --provider --entity --input --output`` (the starter's arguments, D-087)."""
        source = ROOT / "fixtures" / "prismhr" / "bundle.json"
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "out.json"
            with contextlib.redirect_stderr(io.StringIO()):
                status = main(["normalize", "--provider", "prismhr", "--entity", "employee", "--input", str(source), "--output", str(target)])
            self.assertEqual(status, 0)
            document = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(list(document), ["run", "employees"])
        self.assertEqual(document["run"]["entity_filter"], ["employee"])
        self.assertEqual(len(document["employees"]), 3)

    def test_entity_filter_keeps_the_run_whole(self):
        """The filter only chooses lists to show: counts and link problems describe the whole run,
        and an invalid record outside the chosen lists still fails it (render_run validates all)."""
        source = ROOT / "fixtures" / "isolved" / "bundle.json"
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["normalize", "--input", str(source), "--entity", "payroll", "--entity", "company"]), 0)
        document = json.loads(out.getvalue())
        self.assertEqual(list(document), ["run", "companies", "payroll_runs", "paychecks"])
        self.assertEqual(document["run"]["entity_filter"], ["company", "payroll"])
        self.assertEqual(document["run"]["counts"]["employees"], 3)
        self.assertTrue(document["run"]["link_problems"])
        full = io.StringIO()
        with contextlib.redirect_stdout(full), contextlib.redirect_stderr(io.StringIO()):
            main(["normalize", "--input", str(source)])
        self.assertNotIn("entity_filter", json.loads(full.getvalue())["run"])

    def test_provider_must_match_the_bundle(self):
        source = ROOT / "fixtures" / "ukg-ready" / "bundle.json"
        with contextlib.redirect_stderr(io.StringIO()) as errors, contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(["normalize", "--provider", "prismhr", "--input", str(source)]), 1)
        self.assertIn("bundle provider is 'ukg-ready', not 'prismhr'", errors.getvalue())
        self.assertEqual(out.getvalue(), "")

    def test_adapters_check_the_bundle_and_mask_by_default(self):
        """The provider adapters (adapters/<provider>.py, D-087) take a Bundle or parsed bundle JSON,
        refuse another provider's bundle, and mask sensitive values unless asked."""
        source = ROOT / "fixtures" / "ukg-ready" / "bundle.json"
        with self.assertRaisesRegex(ValueError, "bundle provider is 'ukg-ready', not 'prismhr'"):
            ADAPTERS["prismhr"].normalize("employee", load_bundle(source), None)
        data = parse_source_json(source.read_text(encoding="utf-8"))
        masked = ADAPTERS["ukg-ready"].normalize("employee", data, None)
        shown = ADAPTERS["ukg-ready"].normalize("employee", data, None, show_sensitive=True)
        self.assertEqual(masked["employees"][0]["national_ids"][0]["value"], "***1101")
        self.assertEqual(shown["employees"][0]["national_ids"][0]["value"], "666-45-1101")
        self.assertEqual(ADAPTERS["ukg-ready"].normalize(None, data, None)["run"]["counts"], masked["run"]["counts"])

    def test_a_file_that_is_not_a_bundle_fails_cleanly(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "x.json"
            source.write_text('{"format": "other"}', encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()) as errors:
                self.assertEqual(main(["normalize", "--input", str(source)]), 1)
            self.assertIn("not a provider bundle", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
