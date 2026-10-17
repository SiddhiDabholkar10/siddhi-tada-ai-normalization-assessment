"""Tests for the exported JSON Schemas and the coverage document (Phase 2, step 5, D-058).

Synthetic values only. Builders come from the step 2 to 4 tests.
"""
import json
import re
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from jsonschema import Draft202012Validator
from pydantic import BaseModel, ValidationError

from normalization.canonical import sensitive_fields, to_json
from normalization.canonical.enums import DeductionCategory, PaidBy, PaycheckKind, PaymentMethod, PayrollRunStatus, PayrollRunType
from normalization.canonical.paths import path_exists
from normalization.canonical.payroll import DeductionLine, EmployerContributionLine, PaymentLine, PayPeriod
from normalization.canonical.schema_export import JSON_SCHEMA_DIALECT, SCHEMA_FILES, record_schema, render_schemas
from normalization.canonical.values import DECIMAL_STRING_PATTERN, Amount, Percent
from test_canonical_company_employee import EIN_ID, NP, PAY_GROUP_ID, coded, company, employee, explained
from test_canonical_deposits_deductions_benefits import CODE_ID, code_entry, deposit, enrollment, setup
from test_canonical_payroll import RUN_ID, earning_code, paycheck, regular_earning, run, tax

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas"
COVERAGE = ROOT / "docs" / "COVERAGE.md"


def sample_records():
    """One representative record per exported schema, with nested parts and coded values."""
    return {
        "company.schema.json": company(deduction_codes=[code_entry()], earning_codes=[earning_code()]),
        "employee.schema.json": employee(),
        "direct_deposit.schema.json": deposit(amount="100.00", percent="15.5"),
        "deduction_setup.schema.json": setup(deduction_code_id=CODE_ID, amount="10.00"),
        "benefit_enrollment.schema.json": enrollment(coverage_start=date(2025, 1, 1)),
        "payroll_run.schema.json": run(
            run_type=coded(PayrollRunType, PayrollRunType.SCHEDULED, "R"),
            status=coded(PayrollRunStatus, PayrollRunStatus.COMPLETED, "COMP"),
            tax_entity_id=EIN_ID,
            pay_periods=[explained(PayPeriod, pay_group_id=PAY_GROUP_ID, period_start=date(2025, 7, 27))],
        ),
        "paycheck.schema.json": paycheck(
            payroll_run_id=RUN_ID,
            kind=coded(PaycheckKind, PaycheckKind.REGULAR, "R"),
            earnings=[regular_earning()],
            deductions=[explained(DeductionLine, deduction_code_id=CODE_ID, category=coded(DeductionCategory, DeductionCategory.RETIREMENT, "K"), amount="28.20")],
            taxes=[tax(PaidBy.EMPLOYEE, "58.28", rate="0.062"), tax(PaidBy.EMPLOYER, None, field_status={"amount": NP})],
            employer_contributions=[explained(EmployerContributionLine, amount="9.40")],
            payments=[explained(PaymentLine, method=coded(PaymentMethod, PaymentMethod.CHECK, "Check"), amount="-1461.27")],
            net_pay="-1461.27",
            derived_totals=["net_pay"],
        ),
    }


def schema_sensitive_paths(schema: dict) -> list[str]:
    """Paths marked x-sensitive in an exported schema, in the format of sensitive_fields()."""
    defs = schema.get("$defs", {})

    def resolve(node):
        while "$ref" in node:
            node = defs[node["$ref"].rsplit("/", 1)[-1]]
        return node

    def marked(node):
        return node.get("x-sensitive") or any(resolve(alt).get("x-sensitive") for alt in node.get("anyOf", []))

    def walk(node, prefix):
        paths = []
        for name, prop in resolve(node).get("properties", {}).items():
            if marked(prop):
                paths.append(prefix + name)
            for alt in [prop, *prop.get("anyOf", [])]:
                alt = resolve(alt)
                if alt.get("type") == "object" and "properties" in alt:
                    paths += walk(alt, f"{prefix}{name}.")
                elif alt.get("type") == "array" and "items" in alt:
                    item = resolve(alt["items"])
                    if "properties" in item:
                        paths += walk(item, f"{prefix}{name}[].")
        return paths

    return walk(schema, "")


def coverage_homes() -> list[tuple[int, str]]:
    """(line number, token) for every backticked token in a "Canonical home" table column."""
    found, column = [], None
    for number, line in enumerate(COVERAGE.read_text(encoding="utf-8").splitlines(), 1):
        if not line.startswith("|"):
            column = None
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if "Canonical home" in cells:
            column = cells.index("Canonical home")
        elif column is not None and not set(cells[0]) <= set("-: "):
            tokens = re.findall(r"`([^`]+)`", cells[column])
            found += [(number, token) for token in tokens] or [(number, "")]
    return found


class SchemaFileTests(unittest.TestCase):
    def test_committed_schemas_match_the_models(self):
        # Drift test: regenerate in memory and compare byte for byte. Fix: python -m normalization export-schemas
        rendered = render_schemas()
        self.assertEqual(sorted(p.name for p in SCHEMA_DIR.glob("*.schema.json")), sorted(rendered))
        for name, text in rendered.items():
            self.assertEqual((SCHEMA_DIR / name).read_bytes(), text.encode("utf-8"), f"{name} is out of date")

    def test_header_and_format(self):
        for name, text in render_schemas().items():
            schema = json.loads(text)
            self.assertEqual((schema["$schema"], schema["$id"]), (JSON_SCHEMA_DIALECT, name))
            self.assertTrue(text.endswith("}\n") and "\r" not in text)
            Draft202012Validator.check_schema(schema)

    def test_sensitive_markers_match_sensitive_fields(self):
        for name, model in SCHEMA_FILES.items():
            self.assertEqual(sorted(schema_sensitive_paths(record_schema(name))), sorted(sensitive_fields(model)), name)

    def test_record_output_validates_against_its_schema(self):
        for name, record in sample_records().items():
            errors = list(Draft202012Validator(record_schema(name)).iter_errors(json.loads(to_json(record))))
            self.assertEqual(errors, [], f"{name}: {[e.message for e in errors][:3]}")

    def test_schema_rejects_amounts_as_json_numbers(self):
        output = json.loads(to_json(sample_records()["paycheck.schema.json"]))
        output["net_pay"] = -1461.27
        self.assertFalse(Draft202012Validator(record_schema("paycheck.schema.json")).is_valid(output))


class DecimalPatternTests(unittest.TestCase):
    class Holder(BaseModel):
        amount: Amount
        percent: Percent | None = None

    def test_pattern_is_in_the_serialization_schema_only(self):
        serialization = self.Holder.model_json_schema(mode="serialization")["properties"]
        validation = self.Holder.model_json_schema(mode="validation")["properties"]
        self.assertEqual(serialization["amount"]["pattern"], DECIMAL_STRING_PATTERN)
        percent = serialization["percent"]["anyOf"][0]
        # The hook keeps the field's own metadata (x-scale, description) next to the pattern.
        self.assertEqual((percent["pattern"], percent["x-scale"]), (DECIMAL_STRING_PATTERN, "percent"))
        self.assertNotIn("pattern", json.dumps(validation))

    def test_runtime_validation_is_unchanged(self):
        for value in (Decimal("940.00"), "940.00", 1, Decimal("-1461.27"), Decimal("1E-7")):
            text = json.loads(self.Holder(amount=value).model_dump_json())["amount"]
            self.assertRegex(text, DECIMAL_STRING_PATTERN)
        self.assertEqual(json.loads(self.Holder(amount=Decimal("1E-7")).model_dump_json())["amount"], "0.0000001")
        with self.assertRaises(ValidationError):
            self.Holder(amount=True)


class CoverageDocumentTests(unittest.TestCase):
    def test_every_named_canonical_home_exists(self):
        # Proves the named homes exist in the models; it does not prove source-field completeness.
        homes = coverage_homes()
        self.assertGreater(len(homes), 100)
        missing = [(line, token) for line, token in homes if not path_exists(token)]
        self.assertEqual(missing, [])

    def test_path_check_rejects_malformed_paths(self):
        valid = ("Paycheck.earnings[].hours", "Employee.name.first", "Company.deduction_codes[]", "DirectDeposit.applies_to_paycheck_kinds", "BenefitEnrollment")
        for token in valid:
            self.assertTrue(path_exists(token), token)
        invalid = (
            "Paycheck.no_such_field",
            "Employee.job.no_such_field",
            "Nothing.name",
            "Employee.name.first.last",  # reviewer case: a plain value field followed by more segments
            "Employee.name[]",  # reviewer case: [] on a field that is not a list
            "Paycheck.earnings.hours",  # list items reached without []
            "Employee.employment.status.value",  # Coded is a value type, not a canonical part
        )
        for token in invalid:
            self.assertFalse(path_exists(token), token)


if __name__ == "__main__":
    unittest.main()
