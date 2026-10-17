"""Output gate (D-036, D-080, D-085): every sensitive_fields() path of every record type is masked
by default, top-level and nested, and shown only with the explicit opt-in; every record is
validated before anything is written, and one invalid record fails the whole run."""
import contextlib
import io
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from pydantic import Field

from normalization.__main__ import main
from normalization.canonical import Employee, sensitive_fields
from normalization.canonical.base import CanonicalPart, CanonicalRecord
from normalization.canonical.deductions import GarnishmentDetails
from normalization.canonical.enums import DeductionCategory, GarnishmentType
from normalization.canonical.ids import Provider
from normalization.canonical.values import SENSITIVE, CanonicalEnum, MappingBasis, ValueStatus
from normalization.employees.bundle import load_bundle
from normalization.mappings.tables import DATA
from normalization.output import MASK, mask_record, record_json, render_run
from normalization.pipeline import ADAPTERS, RECORD_LISTS, TABLE_LISTS, RunResult, normalize_bundle
from test_canonical_company_employee import coded, company, explained
from test_canonical_deposits_deductions_benefits import deposit, enrollment, setup
from test_canonical_payroll import paycheck
from test_canonical_payroll import run as payroll_run

ROOT = Path(__file__).resolve().parents[1]
PROVIDERS = ("prismhr", "isolved", "ukg-ready")
EMPTY_LISTS = {name: [] for name in RECORD_LISTS}


class Secret(CanonicalPart):
    label: str | None = None
    code: str | None = Field(default=None, json_schema_extra=SENSITIVE)


class Holder(CanonicalRecord):
    note: str | None = None
    born: date | None = Field(default=None, json_schema_extra=SENSITIVE)
    inner: Secret | None = None
    items: list[Secret] | None = None
    whole: Secret | None = Field(default=None, json_schema_extra=SENSITIVE)


def holder() -> Holder:
    return Holder(
        id="prismhr:1:employee:9", provider=Provider.PRISMHR, tenant_id="1", source_ids={"id": "9"},
        sources=[{"endpoint": "GET /x", "locator": ""}],
        note="visible", born=date(1990, 1, 2), inner=Secret(label="a", code="S-1"),
        items=[Secret(label="b", code="S-2"), Secret(label="c", field_status={"code": "hidden_by_source"})],
        whole=Secret(label="whole", code="S-3"),
    )


# Sensitive extensions hold nested source values too (a list of objects).
EXTRAS = {"getSecret:holder.note": "EXT-SECRET-1", "getSecret:holder.items": [{"pin": "EXT-SECRET-2"}]}


def samples() -> dict[type, CanonicalRecord]:
    """One synthetic record per output record type other than Employee (whose sensitive paths
    the fixtures fill, test below), with every sensitive path of the type filled."""
    garnishment = explained(GarnishmentDetails, type=coded(GarnishmentType, GarnishmentType.CHILD_SUPPORT, "CS"),
                            case_number="CASE-SECRET-77", payee="PAYEE-SECRET acct 4455")
    built = [
        company(sensitive_provider_extensions=EXTRAS),
        deposit(routing_number="011000015", account_number="ACCT-SECRET-123456789", account_last4="6789",
                sensitive_provider_extensions=EXTRAS),
        setup(category=coded(DeductionCategory, DeductionCategory.GARNISHMENT, "CS"), garnishment=garnishment,
              sensitive_provider_extensions=EXTRAS),
        enrollment(sensitive_provider_extensions=EXTRAS),
        payroll_run(sensitive_provider_extensions=EXTRAS),
        paycheck(sensitive_provider_extensions=EXTRAS),
    ]
    return {type(record): record for record in built}


def run_records(provider: str) -> list[CanonicalRecord]:
    result = normalize_bundle(load_bundle(ROOT / "fixtures" / provider / "bundle.json"))
    return [record for records in result.records.values() for record in records]


def built_types() -> set[type]:
    """Record types an adapter in the pipeline produces for at least one provider."""
    return {RECORD_LISTS[name] for table in ADAPTERS for name in TABLE_LISTS[table]}


def fillable(model: type) -> set[str]:
    """Sensitive paths of ``model`` the mapping tables can fill: ``sensitive_provider_extensions``
    only when some table row sends a field to that record type's sensitive extension (no deposit
    table has one, D-088; the payroll table has them for Paycheck, not PayrollRun); every typed
    sensitive path."""
    tables = [table for table, lists in TABLE_LISTS.items() if any(RECORD_LISTS[name] is model for name in lists)]
    rows = [row for table in tables for path in DATA.glob(f"*/{table}.json")
            for row in json.loads(path.read_text(encoding="utf-8"))["fields"]]
    has_extension_row = any(row["use"] == "sensitive_extension" and row["target"].startswith(f"{model.__name__}.") for row in rows)
    return {path for path in sensitive_fields(model) if path != "sensitive_provider_extensions" or has_extension_row}


def value_at(data, path: str) -> list:
    """Every value at a sensitive_fields() path (``a[].b``) inside ``data``."""
    nodes = [data]
    for part in path.split("."):
        name, many = (part[:-2], True) if part.endswith("[]") else (part, False)
        found = []
        for node in nodes:
            value = node.get(name) if isinstance(node, dict) else None
            if value is None:
                continue
            found += value if many and isinstance(value, list) else [value]
        nodes = found
    return nodes


STATUSES = {status.value for status in ValueStatus}


def is_null_map(key: str, item) -> bool:
    """A canonical ``field_status`` map (statuses only). A source key of that name holding other
    values (raw extension JSON) is data and counts as leaves."""
    return key == "field_status" and isinstance(item, dict) and set(item.values()) <= STATUSES


def leaves(value) -> list:
    if isinstance(value, dict):
        return [leaf for key, item in value.items() if not is_null_map(key, item) for leaf in leaves(item)]
    if isinstance(value, list):
        return [leaf for item in value for leaf in leaves(item)]
    return [value]


def filled_paths(record: CanonicalRecord) -> set[str]:
    full = record_json(record, show_sensitive=True)
    return {path for path in sensitive_fields(type(record))
            if any(leaf is not None for value in value_at(full, path) for leaf in leaves(value))}


class MaskingTests(unittest.TestCase):
    def assert_masked_everywhere(self, record: CanonicalRecord, label: str) -> None:
        masked = record_json(record)
        for path in sensitive_fields(type(record)):
            for value in value_at(masked, path):
                for leaf in leaves(value):
                    with self.subTest(record=label, path=path):
                        self.assertTrue(leaf is None or str(leaf).startswith(MASK), leaf)

    def test_paths_include_top_level_nested_and_list(self):
        self.assertEqual(
            set(sensitive_fields(Holder)),
            {"sensitive_provider_extensions", "born", "inner.code", "items[].code", "whole", "whole.code"},
        )

    def test_masked_by_default_and_shown_only_with_opt_in(self):
        """Top-level, nested, list items and a sensitive part as a whole; a hidden_by_source item
        stays null with its status; a field that is not sensitive stays visible."""
        data = record_json(holder())
        self.assertEqual(data["born"], MASK)
        self.assertEqual(data["inner"]["code"], MASK)
        self.assertEqual(data["inner"]["label"], "a")
        self.assertEqual([item["code"] for item in data["items"]], [MASK, None])
        self.assertEqual(data["items"][1]["field_status"], {"code": "hidden_by_source"})
        self.assertEqual(data["whole"], {"field_status": {}, "label": MASK, "code": MASK})
        self.assertEqual(data["note"], "visible")
        data = record_json(holder(), show_sensitive=True)
        self.assertEqual(data["born"], "1990-01-02")
        self.assertEqual(data["inner"]["code"], "S-1")
        self.assertEqual(data["items"][0]["code"], "S-2")
        self.assertEqual(data["whole"]["code"], "S-3")

    def test_raw_extension_keys_named_field_status_are_masked(self):
        """Step 1 review blocker: a source key called field_status inside sensitive_provider_extensions
        is source data, not a canonical null map, so it is masked like every other leaf. The
        record's own null map stays visible."""
        record = company(sensitive_provider_extensions={
            "getX:bank": {"field_status": "ACCOUNT123"},
            "field_status": "ACCOUNT124",
            "getX:list": [{"field_status": {"acct": "ACCOUNT125"}}],
        })
        data = record_json(record)
        self.assertNotIn("ACCOUNT12", json.dumps(data))
        self.assertEqual(data["sensitive_provider_extensions"], {
            "getX:bank": {"field_status": MASK}, "field_status": MASK, "getX:list": [{"field_status": {"acct": MASK}}],
        })
        self.assertEqual(data["field_status"], record_json(record, show_sensitive=True)["field_status"])
        self.assertTrue(data["field_status"])

    def test_national_id_keeps_last_four(self):
        data = mask_record({"national_ids": [{"value": "666-12-3456"}], "x": {"national_id": {"value": "ab"}}},
                           ["national_ids[].value", "x.national_id.value"])
        self.assertEqual(data["national_ids"][0]["value"], "***3456")
        self.assertEqual(data["x"]["national_id"]["value"], MASK)  # fewer than 4 characters: nothing shown

    def test_every_record_type_masks_each_sensitive_path(self):
        """Per record type, top-level and nested: there is a sample for every type but Employee
        (the fixtures cover it), each sample fills every sensitive path (so the check is not
        vacuous), the masked view hides each leaf and the opt-in shows it."""
        self.assertEqual(set(samples()) | {Employee}, set(RECORD_LISTS.values()))
        for model, record in samples().items():
            with self.subTest(model=model.__name__):
                self.assertEqual(sorted(filled_paths(record)), sorted(sensitive_fields(model)))
            self.assert_masked_everywhere(record, model.__name__)

    def test_named_sensitive_values_per_record_type(self):
        by_type = samples()
        masked = {model.__name__: record_json(record) for model, record in by_type.items()}
        shown = {model.__name__: record_json(record, show_sensitive=True) for model, record in by_type.items()}
        self.assertEqual(masked["Company"]["tax_entities"][0]["ein"], MASK)
        self.assertEqual(shown["Company"]["tax_entities"][0]["ein"], "12-3456789")
        self.assertEqual((masked["DirectDeposit"]["account_number"], masked["DirectDeposit"]["routing_number"]), (MASK, MASK))
        self.assertEqual(shown["DirectDeposit"]["account_number"], "ACCT-SECRET-123456789")
        self.assertEqual(masked["DirectDeposit"]["account_last4"], "6789")  # not sensitive (D-020)
        self.assertEqual((masked["DeductionSetup"]["garnishment"]["case_number"], masked["DeductionSetup"]["garnishment"]["payee"]), (MASK, MASK))
        self.assertEqual(shown["DeductionSetup"]["garnishment"]["payee"], "PAYEE-SECRET acct 4455")
        for name in masked:
            with self.subTest(model=name):
                self.assertEqual(masked[name]["sensitive_provider_extensions"],
                                 {"getSecret:holder.note": MASK, "getSecret:holder.items": [{"pin": MASK}]})
                self.assertEqual(shown[name]["sensitive_provider_extensions"], json.loads(json.dumps(EXTRAS)))
                self.assertNotIn("SECRET", json.dumps(masked[name]))

    def test_every_sensitive_path_of_the_built_types_is_filled_somewhere_and_masked(self):
        """On the fixtures, through the pipeline: every record of every output list is masked, and
        for each record type an adapter produces, the fixtures fill every sensitive path."""
        filled: dict[type, set[str]] = {model: set() for model in built_types()}
        for provider in PROVIDERS:
            for record in run_records(provider):
                filled.setdefault(type(record), set()).update(filled_paths(record))
                self.assert_masked_everywhere(record, f"{provider} {record.id}")
        for model in built_types():
            with self.subTest(model=model.__name__):
                self.assertEqual(sorted(fillable(model) - filled[model]), [])

    def test_no_sensitive_value_appears_anywhere_in_masked_output(self):
        """No sensitive source value leaks through another field (a diagnostic message, an
        extension). Canonical vocabulary (enum values, mapping basis) is not a source value.
        Values of the raw sensitive extension are masked as a whole (test above), so only typed
        sensitive values are traced here. A typed sensitive value found anywhere else in the masked
        record is a leak, plain provider_extensions included (D-088 review: the PrismHR garnishment
        payee id also sent as cutbackPayeeCode)."""
        vocabulary = {member.value for enum in (*CanonicalEnum.__subclasses__(), MappingBasis, ValueStatus) for member in enum}
        for provider in PROVIDERS:
            for record in run_records(provider):
                full = record_json(record, show_sensitive=True)
                # A relative sharing the employee's (visible) name is not a leak.
                name = full.get("name")  # an employee's name part; a payroll run's name is text
                own_name = {v for v in name.values() if isinstance(v, str)} if isinstance(name, dict) else set()
                secrets = {str(leaf) for path in sensitive_fields(type(record)) if path != "sensitive_provider_extensions"
                           for value in value_at(full, path)
                           for leaf in leaves(value) if isinstance(leaf, str) and len(leaf) >= 5
                           and leaf not in vocabulary and leaf not in own_name}
                text = json.dumps(record_json(record))
                for secret in secrets:
                    with self.subTest(provider=provider, record=record.id):
                        self.assertNotIn(secret, text)

    def test_render_states_the_mode(self):
        result = RunResult("prismhr", "1", dict(EMPTY_LISTS), [], {})
        self.assertEqual(json.loads(render_run(result, "x.json"))["run"]["sensitive_values"], "masked")
        self.assertEqual(json.loads(render_run(result, "x.json", show_sensitive=True))["run"]["sensitive_values"], "shown")

    def test_cli_masks_by_default_and_shows_with_flag(self):
        source = ROOT / "fixtures" / "ukg-ready" / "bundle.json"
        with tempfile.TemporaryDirectory() as folder:
            masked, shown = Path(folder) / "masked.json", Path(folder) / "shown.json"
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["normalize", "--input", str(source), "--output", str(masked)]), 0)
                self.assertEqual(main(["normalize", "--input", str(source), "--output", str(shown), "--show-sensitive"]), 0)
                self.assertEqual(main(["normalize", "--input", str(source), "--output", str(masked)]), 1)  # no overwrite
            first_masked = json.loads(masked.read_text(encoding="utf-8"))["employees"][0]
            first_shown = json.loads(shown.read_text(encoding="utf-8"))["employees"][0]
            self.assertEqual(first_masked["national_ids"][0]["value"], "***1101")
            self.assertEqual(first_shown["national_ids"][0]["value"], "666-45-1101")
            self.assertEqual(first_masked["demographics"]["birth_date"], MASK)
            self.assertEqual(first_shown["demographics"]["birth_date"], "1992-12-01")


def with_broken_record(provider: str) -> RunResult:
    """The fixture run of ``provider`` with one employee that no longer validates. ``model_copy``
    skips validation, so only the output gate can catch it."""
    result = normalize_bundle(load_bundle(ROOT / "fixtures" / provider / "bundle.json"))
    employees = list(result.records["employees"])
    employees[-1] = employees[-1].model_copy(update={"sources": []})  # sources needs at least one entry
    return RunResult(result.provider, result.tenant_id, {**result.records, "employees": employees},
                     result.link_problems, result.not_normalized)


class ValidationGateTests(unittest.TestCase):
    def test_an_invalid_record_fails_the_render_and_names_its_id(self):
        result = with_broken_record("isolved")
        broken_id = result.records["employees"][-1].id
        for show_sensitive in (False, True):
            with self.subTest(show_sensitive=show_sensitive):
                with self.assertRaisesRegex(ValueError, f"^{broken_id}: record failed validation, nothing written"):
                    render_run(result, "bundle.json", show_sensitive=show_sensitive)

    def test_cli_writes_nothing_when_one_record_is_invalid(self):
        source = ROOT / "fixtures" / "isolved" / "bundle.json"
        result = with_broken_record("isolved")
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "out.json"
            errors, out = io.StringIO(), io.StringIO()
            with mock.patch("normalization.adapters.common.normalize_bundle", return_value=result), \
                    contextlib.redirect_stderr(errors), contextlib.redirect_stdout(out):
                self.assertEqual(main(["normalize", "--input", str(source), "--output", str(target)]), 1)
                self.assertEqual(main(["normalize", "--input", str(source)]), 1)
            self.assertFalse(target.exists())
            self.assertEqual(out.getvalue(), "")  # not even a partial document on standard output
            self.assertIn(result.records["employees"][-1].id, errors.getvalue())


if __name__ == "__main__":
    unittest.main()
