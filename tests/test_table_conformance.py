"""Adapters against their mapping tables (D-061, D-080, D-085), for every entity table.

Each adapter module declares ``PROVIDER`` and ``TABLE`` and cites the rows it applies with
``# row: <route short name> <field>[; <field>...]`` comments. For every provider table:
- a table with an adapter in the pipeline: the cited rows equal the table's non-excluded rows,
  every extension entry of its records (and of company-owned entries, D-063) sits where its row
  says, and every extension leaf of the input is kept;
- a table without one (since Phase 5 step 3 only UKG deduction setups, which have no table): no
  module claims it (the run header lists its output lists as not normalized:
  test_pipeline.test_empty_lists_say_why).
Every adapter module found in the adapter packages must be registered in the pipeline. Items a
table note sends to the employee (``entities.SENT_TO_EMPLOYEE``, D-088) are looked for on the
employees and classified with the table that owns their rows.
"""
import json
import pkgutil
import re
import unittest
from functools import cache
from importlib import import_module
from pathlib import Path

from normalization.canonical.company import Company, CompanyEntry
from normalization.employees.bundle import load_bundle
from normalization.employees.common import json_leaf
from normalization.entities import SENT_TO_EMPLOYEE
from normalization.mappings.tables import DATA, ENTITIES, apply_live_renames, classify, load_routes, load_tables, row_routes
from normalization.pipeline import ADAPTERS, TABLE_LISTS, normalize_bundle

ROOT = Path(__file__).resolve().parents[1]
ADAPTER_PACKAGES = ("normalization.employees", "normalization.entities")
TARGETS = {"extension": "provider_extensions", "sensitive_extension": "sensitive_provider_extensions"}

# Mapped rows whose raw value is also kept in an extension in a stated case (table notes), per
# (provider, table, extension).
MAPPED_KEPT_RAW = {
    ("prismhr", "employee", "provider_extensions"): {
        "dependent[].status",  # P (pending) and undocumented statuses: is_active not provided, raw kept
        "dependent[].relationType",  # undocumented relation types
    },
    ("prismhr", "employee", "sensitive_provider_extensions"): {
        "employee[].person.veteran", "employee[].person.handicapped", "employee[].person.disabledVet",
        "employee[].person.otherProtectedVet", "employee[].person.activeDutyBadgeVet",
        "employee[].person.recentlySeparatedVet", "employee[].person.serviceMedalVet",  # D (declined), D-076
        "employee[].compensation.fedOverrideType", "employee[].compensation.fedOverrideAmt",
        "employee[].compensation.stateTax[].overrideType", "employee[].compensation.stateTax[].overrideAmount",  # F and P
        "employee[].person.emergencyContact[].contactType", "employee[].person.emergencyContact[].contactInfo",  # other contact types
    },
    ("isolved", "employee", "provider_extensions"): {
        "results[].workLocation",  # a code not among the legal's work locations
        # termination values still sent for an employee who is not terminated (D-080)
        "results[].terminationDate", "results[].terminationType", "results[].terminationReason",
        "[].manager.id", "[].supervisor.id",  # job history person not among the employees read
        "[].frequency.id", "[].frequency.description", "[].payGroup.id",  # salary entries not in effect
    },
    ("isolved", "employee", "sensitive_provider_extensions"): {"results[].i9Documents.i9CompletedDate"},  # full timestamp (1.6)
    ("prismhr", "direct_deposit", "provider_extensions"): {
        "employee[].directDeposit.achVoucher[].amount",  # an undocumented method: neither amount nor percent
    },
    ("prismhr", "deduction_setup", "provider_extensions"): {
        # loan dates valid as two different dates (D-083)
        "employeeLoanDetail[].loanDate", "employeeLoanDetail[].startDate", "employeeLoanDetail[].stopDate",
        "employeeDeductions.deduction[].loanOrGarnishId",  # a garnishment's id (no loan part)
        "employeeDeductions.deduction[].amount",  # usePercent not sent: neither amount nor percent
    },
    ("isolved", "company", "provider_extensions"): {"[].systemBenefitType"},  # on Earning and Memo Calc entries (row note)
    ("isolved", "payroll", "provider_extensions"): {"earnings[].isMemoEarning"},  # the flag of a memo-derived contribution (D-055)
    ("prismhr", "payroll", "provider_extensions"): {
        "payrollVouchers[].earning[].hoursUnits",  # the pay code's payReason is unknown: neither hours nor units (D-089)
    },
    ("isolved", "direct_deposit", "provider_extensions"): {"[].percent"},  # sent next to an amount
    ("isolved", "deduction_setup", "provider_extensions"): {
        "[].calcParams[].paramType", "[].calcParams[].paramValue",  # Percent, Amount2, Rate: unit_unverified
    },
    ("ukg-ready", "direct_deposit", "provider_extensions"): {
        "deposits[].amount", "deposits[].percentage",  # a value the calc method rules out
    },
    ("ukg-ready", "employee", "provider_extensions"): {
        "managers[].empl_ref.account_id",  # entries after the lowest index
        "dates.terminated",  # a date still sent for an account that is not terminated (D-080)
        "compensations[].time", "compensations[].time_period",  # entries other than the latest
    },
}


def adapter_modules() -> dict[tuple[str, str], object]:
    """Every module of the adapter packages that declares a table, by (provider, table)."""
    found = {}
    for package_name in ADAPTER_PACKAGES:
        try:
            package = import_module(package_name)
        except ModuleNotFoundError:
            continue  # normalization.entities arrives with Phase 5 step 2
        for info in pkgutil.walk_packages(package.__path__, package_name + "."):
            module = import_module(info.name)
            if hasattr(module, "TABLE"):
                key = (module.PROVIDER, module.TABLE)
                assert key not in found, f"two modules claim {key}"
                found[key] = module
    return found


def table(provider: str, name: str) -> dict | None:
    path = DATA / provider / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


@cache
def bundle(provider: str):
    return load_bundle(ROOT / "fixtures" / provider / "bundle.json")


@cache
def run(provider: str):
    return normalize_bundle(bundle(provider))


def records(provider: str, name: str) -> list:
    return [record for list_name in TABLE_LISTS[name] for record in run(provider).records[list_name]]


def built() -> list[tuple[str, str, object, dict]]:
    """(provider, table, module, table data) of every table the pipeline runs an adapter for."""
    modules = adapter_modules()
    return [(provider, name, modules[(provider, name)], table(provider, name))
            for name, by_provider in ADAPTERS.items() for provider in by_provider]


def cited(module) -> set[tuple[str, str]]:
    text = Path(module.__file__).read_text(encoding="utf-8")
    found = set()
    for short, fields in re.findall(r"#\s*row:\s*(\S+)\s+([^\n]+)", text):
        for field in fields.split(";"):
            if field.strip():
                found.add((module.ROUTES[short], field.strip()))
    return found


def renames(provider: str) -> dict[str, dict[str, str]]:
    return {entry["route"]: entry.get("live_renames", {}) for entry in load_routes(provider)["selected"]}


def entries(record) -> list[CompanyEntry]:
    """The company-owned entries of a record (D-063), each with its own provider_extensions."""
    if not isinstance(record, Company):
        return []
    return [entry for name in ("tax_entities", "work_locations", "pay_groups", "deduction_codes", "earning_codes")
            for entry in getattr(record, name) or []]


def sent(provider: str, table_name: str | None = None) -> dict[str, object]:
    """SENT_TO_EMPLOYEE entries of a provider (optionally of one owning table), by key prefix."""
    return {item.short: item for item in SENT_TO_EMPLOYEE
            if item.provider == provider and (table_name is None or item.table == table_name)}


def unpaged(short: str) -> str:
    """A key prefix without its page qualifier: ``legalPayItems(page=1)`` is ``legalPayItems``."""
    return re.sub(r"\(page=[^)]*\)$", "", short)


def classify_key(provider: str, data: dict, route: str, key_path: str) -> tuple[str, dict | None, str | None]:
    field = apply_live_renames(re.sub(r"\[\d+\]", "[]", key_path), renames(provider).get(route, {}))
    row, problem = classify([row for row in data["fields"] if route in row_routes(row)], field)
    return field, row, problem


class Registry(unittest.TestCase):
    def test_pipeline_tables_are_the_mapping_entities(self):
        self.assertEqual(tuple(TABLE_LISTS), ENTITIES)
        self.assertLessEqual(set(ADAPTERS), set(ENTITIES))

    def test_every_adapter_module_is_registered_and_every_registered_module_exists(self):
        modules = adapter_modules()
        registered = {(provider, name): path for name, by_provider in ADAPTERS.items() for provider, path in by_provider.items()}
        self.assertEqual(sorted(modules), sorted(registered))
        for key, path in registered.items():
            with self.subTest(key=key):
                self.assertEqual(modules[key].__name__, "normalization" + path)
                self.assertIsNotNone(table(*key), "an adapter needs its mapping table")


class TableConformance(unittest.TestCase):
    def test_cited_rows_equal_the_table_rows(self):
        for provider, name, module, data in built():
            expected = {(route, row["field"]) for row in data["fields"] if row["use"] != "excluded" for route in row_routes(row)}
            found = cited(module)
            with self.subTest(provider=provider, table=name):
                self.assertEqual(sorted(found - expected), [], "cited rows that are not table rows")
                self.assertEqual(sorted(expected - found), [], "table rows no adapter comment cites")

    def test_fixtures_use_every_live_rename_of_the_routes_read(self):
        """Each live wrapper rename (routes.json, D-062) on a route an adapter reads appears in the
        fixtures in its live form, so the adapters are tested on the shape the demo sends."""
        for provider, name, module, _ in built():
            read = set(module.ROUTES.values())
            for route, live_renames in renames(provider).items():
                if route not in read:
                    continue
                for documented, live in live_renames.items():
                    bodies = [r.body for r in bundle(provider).responses if r.route == route and r.status == 200]
                    with self.subTest(provider=provider, table=name, route=route):
                        self.assertTrue(bodies)
                        self.assertTrue(all(live in body and documented not in body for body in bodies))

    def test_extension_entries_follow_their_rows(self):
        """Record keys follow a row whose target is the record's extension, entry keys a row whose
        target is an entry's provider_extensions (D-063); keys sent to the employee follow a
        non-excluded row of the table that owns them (D-088)."""
        expected_use = {target: use for use, target in TARGETS.items()}
        for provider, name, module, data in built():
            to_employee = sent(provider) if name == "employee" else {}
            for record in records(provider, name):
                keys = [(target, key, False) for target in TARGETS.values() for key in getattr(record, target)]
                keys += [("provider_extensions", key, True) for entry in entries(record) for key in entry.provider_extensions]
                for target, key, in_entry in keys:
                    short, _, path = key.partition(":")
                    short = unpaged(short)
                    with self.subTest(provider=provider, table=name, key=key):
                        if short in to_employee:
                            item = to_employee[short]
                            _, row, problem = classify_key(provider, table(provider, item.table), item.route, path)
                            self.assertIsNotNone(row, problem)
                            self.assertNotEqual(row["use"], "excluded")
                            continue
                        field, row, problem = classify_key(provider, data, module.ROUTES[short], path)
                        self.assertIsNotNone(row, problem)
                        if row["use"] == "mapped":
                            self.assertIn(field, MAPPED_KEPT_RAW.get((provider, name, target), set()), f"mapped row kept raw in {target}")
                            continue
                        self.assertEqual(row["use"], expected_use[target])
                        self.assertEqual("[]." in row["target"], in_entry, f"row target {row['target']}")

    def test_every_extension_leaf_of_the_input_is_kept(self):
        """Nothing returned is dropped (CANONICAL_MODEL 1.12): each filled source leaf whose row
        says extension or sensitive extension is in the output with its value."""
        for provider, name, module, data in built():
            short_of = {template: short for short, template in module.ROUTES.items()}
            short_of.update({item.route: short for short, item in sent(provider, name).items()})
            route_renames = renames(provider)
            kept = {(target, key, json.dumps(value, sort_keys=True))
                    for record in records(provider, name) for target in TARGETS.values()
                    for key, value in getattr(record, target).items()}
            kept |= {("provider_extensions", key, json.dumps(value, sort_keys=True))
                     for record in records(provider, name) for entry in entries(record)
                     for key, value in entry.provider_extensions.items()}
            if sent(provider, name):  # items sent to the employee are looked for there (D-088)
                kept |= {("provider_extensions", key, json.dumps(value, sort_keys=True))
                         for record in records(provider, "employee") for key, value in record.provider_extensions.items()
                         if unpaged(key.partition(":")[0]) in sent(provider, name)}
            provider_rows = [row for other in load_tables(provider) for row in other["fields"]]
            for response in bundle(provider).responses:
                # A field has one row across the provider's tables (the checker's rule); this
                # table answers only for the leaves its own rows win (D-094: detail ein_name).
                route_rows = [row for row in provider_rows if response.route in row_routes(row)]
                if response.status != 200 or not any(row in data["fields"] for row in route_rows):
                    continue
                for path, value in leaf_values(response.body):
                    field = apply_live_renames(re.sub(r"\[\d+\]", "[]", path), route_renames.get(response.route, {}))
                    row, _ = classify(route_rows, field)
                    if row is None or row["use"] not in TARGETS or row not in data["fields"]:
                        continue
                    entry = (TARGETS[row["use"]], f"{short_of[response.route]}:{path}", json.dumps(json_leaf(value), sort_keys=True))
                    # Leaves sent to the employee from a paged route carry the page (D-090 review).
                    paged = (entry[0], f"{short_of[response.route]}(page={response.params.get('page')}):{path}", entry[2])
                    with self.subTest(provider=provider, table=name, entry=entry[1]):
                        self.assertTrue(entry in kept or paged in kept, entry)


def leaf_values(body, path: str = ""):
    """(path, value) of every filled leaf, with list indices (``a[0].b``)."""
    if isinstance(body, dict):
        for key, value in body.items():
            yield from leaf_values(value, f"{path}.{key}" if path else key)
    elif isinstance(body, list):
        for index, item in enumerate(body):
            yield from leaf_values(item, f"{path}[{index}]")
    elif not (body is None or (isinstance(body, str) and body.strip() == "")):
        yield path, body


if __name__ == "__main__":
    unittest.main()
