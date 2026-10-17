"""Tests for the Phase 3 mapping tables and their checks (D-061).

The real tables are checked offline against contracts/. The check functions are also tested
with small synthetic route lists and tables, so each kind of mistake is shown to fail.
"""
import json
import re
import unittest
from pathlib import Path

from normalization.canonical import DirectDeposit, Employee, Paycheck, sensitive_fields
from normalization.mappings.render import render_mappings
from normalization.mappings.spec import PRISMHR_SPEC, PROVIDERS, RouteDoc, body_fields, documented_fields, documented_routes, resolve_pointer
from normalization.mappings.tables import (
    apply_live_renames,
    check_routes,
    check_tables,
    classify,
    code_tables,
    glob_regex,
    live_field_problem,
    load_routes,
    load_tables,
    pending_routes,
    route_problems,
    row_routes,
    table_problems,
)

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs" / "mappings"


class SpecInventoryTests(unittest.TestCase):
    def test_documented_route_counts(self):
        # GET operations: PrismHR OpenAPI, isolved primary Swagger (D-007), UKG reference pages.
        counts = {provider: len(documented_routes(provider)) for provider in PROVIDERS}
        self.assertEqual(counts, {"prismhr": 253, "isolved": 302, "ukg-ready": 269})

    def test_ukg_routes_without_an_extracted_schema(self):
        # 269 GET pages, 260 extracted response schemas: the other 9 are classified from the page.
        missing = [r for r, doc in documented_routes("ukg-ready").items() if doc.schema is None]
        self.assertEqual(len(missing), 9)

    def test_fields_follow_refs_arrays_and_nesting(self):
        employee = documented_fields("prismhr", "/employee/v1/getEmployee")
        self.assertIn("employee[].compensation.ssn", employee)
        deposits = documented_fields("isolved", "/api/clients/{clientId}/legals/{legalId}/employees/{employeeId}/directdeposits")
        self.assertIn("[].sequenceNumber", deposits)  # a top-level array
        balances = documented_fields("ukg-ready", "/v2/companies/{cid}/employees/{aid}/accrual/2/balances")
        self.assertIn("accrual_balances[].current_balance.hours", balances)

    def test_body_fields_use_the_same_format(self):
        body = {"items": [{"a": 1, "b": {"c": None}}, {"d": []}], "e": {}}
        self.assertEqual(body_fields(body), {"items[].a", "items[].b.c", "items[].d[]", "e"})
        self.assertEqual(body_fields([{"x": 1}]), {"[].x"})

    def test_pointer_resolution(self):
        good = "contracts/prismhr/openapi/prismhr-2025.09.openapi.json#/components/schemas/AchVoucher/properties/method"
        self.assertTrue(resolve_pointer(good))
        self.assertTrue(resolve_pointer("contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__config__cost-centers.html"))
        self.assertFalse(resolve_pointer(good + "X"))
        self.assertFalse(resolve_pointer("contracts/missing.json"))
        self.assertFalse(resolve_pointer("README.md"))


class PatternTests(unittest.TestCase):
    def test_route_patterns(self):
        family = glob_regex("/a/**", "/")
        self.assertTrue(all(family.match(r) for r in ("/a", "/a/b", "/a/b/c")))
        self.assertFalse(family.match("/ab"))
        below = glob_regex("/a/*/**", "/")
        self.assertFalse(below.match("/a"))
        self.assertTrue(below.match("/a/b") and below.match("/a/b/c"))
        self.assertTrue(glob_regex("/x/get*", "/").match("/x/getThing"))
        self.assertFalse(glob_regex("/x/get*", "/").match("/x/getThing/more"))

    def test_field_patterns(self):
        links = glob_regex("**._links.**", ".")
        self.assertTrue(all(links.match(f) for f in ("_links", "_links.self", "items[].a._links.href")))
        self.assertFalse(links.match("items[].my_links"))
        self.assertTrue(glob_regex("[].*", ".").match("[].links[]"))
        self.assertFalse(glob_regex("[].*", ".").match("[].links[].href"))


def doc(route, schema=True):
    return RouteDoc(route, "synthetic", {"type": "object"} if schema else None, {})


class RouteListCheckTests(unittest.TestCase):
    DOCUMENTED = {r: doc(r) for r in ("/emp/get", "/emp/list", "/time/a", "/time/b", "/forms/w2")}

    def routes(self, **changes):
        routes = {
            "selected": [{"route": "/emp/get", "entities": ["employee"], "classified": False}],
            "excluded": [
                {"route": "/emp/list", "reason": "filtered view"},
                {"family": "Time", "routes": ["/time/**"], "reason": "time and attendance"},
                {"family": "Forms", "routes": ["/forms/*"], "reason": "documents"},
            ],
        }
        routes.update(changes)
        return routes

    def test_real_route_lists_cover_every_documented_route_once(self):
        for provider in PROVIDERS:
            self.assertEqual(route_problems(provider), [], provider)

    def test_complete_list_passes(self):
        self.assertEqual(check_routes(self.routes(), self.DOCUMENTED), [])

    def test_uncovered_and_double_covered_routes_fail(self):
        routes = self.routes()
        routes["excluded"] = routes["excluded"][:2] + [{"family": "All", "routes": ["/**"], "reason": "too broad"}]
        problems = check_routes(routes, self.DOCUMENTED)
        self.assertTrue(any("/time/a: covered 2 times" in p for p in problems))
        routes = self.routes()
        routes["excluded"] = routes["excluded"][:2]
        self.assertIn("/forms/w2: covered 0 times (not covered)", check_routes(routes, self.DOCUMENTED))

    def test_entries_must_be_documented_and_reasoned(self):
        routes = self.routes()
        routes["selected"].append({"route": "/emp/typo", "entities": ["employee"], "classified": False})
        routes["excluded"].append({"route": "/forms/w2"})
        routes["excluded"].append({"family": "Nothing", "routes": ["/none/**"], "reason": "matches nothing"})
        problems = check_routes(routes, self.DOCUMENTED)
        self.assertIn("selected route is not documented: /emp/typo", problems)
        self.assertTrue(any(p.startswith("exclusion without a reason") for p in problems))
        self.assertTrue(any("pattern matches no documented route" in p for p in problems))

    def test_live_renames_must_name_a_documented_prefix(self):
        documented = {**self.DOCUMENTED, "/emp/get": RouteDoc("/emp/get", "synthetic", {"properties": {"payrollVouchers": {"items": {"properties": {"id": {}}}}}}, {})}
        good = self.routes(selected=[{"route": "/emp/get", "entities": ["payroll"], "classified": False, "live_renames": {"payrollVouchers": "payrollVoucher"}}])
        self.assertEqual(check_routes(good, documented), [])
        bad = self.routes(selected=[{"route": "/emp/get", "entities": ["payroll"], "classified": False, "live_renames": {"payrollVoucher": "x"}}])
        self.assertTrue(any("live_renames key is not a documented field prefix" in p for p in check_routes(bad, documented)))

    def test_apply_live_renames(self):
        renames = {"payrollVouchers": "payrollVoucher"}
        self.assertEqual(apply_live_renames("payrollVoucher[].netPay", renames), "payrollVouchers[].netPay")
        self.assertEqual(apply_live_renames("payrollVoucherCount", renames), "payrollVoucherCount")

    def test_missing_schema_must_be_flagged(self):
        documented = {**self.DOCUMENTED, "/emp/get": doc("/emp/get", schema=False)}
        self.assertTrue(any("must be set exactly when" in p for p in check_routes(self.routes(), documented)))
        flagged = self.routes(selected=[{"route": "/emp/get", "entities": ["employee"], "classified": False, "schema": "not_extracted"}])
        self.assertEqual(check_routes(flagged, documented), [])


ROUTE = "/emp/get"
FIELDS = frozenset({"id", "name.first", "ssn", "_links.self", "_links.edit", "items[]._links.href"})
BASE_ROWS = [
    {"route": ROUTE, "field": "id", "use": "mapped", "target": "Employee.source_ids", "transform": "source_id", "evidence": ["live: 3 of 3"]},
    {"route": ROUTE, "field": "name.first", "use": "mapped", "target": "Employee.name.first", "transform": "copy", "evidence": ["D-040"]},
    {"route": ROUTE, "field": "ssn", "use": "mapped", "target": "Employee.national_ids[].value", "transform": "code:prismhr.id_type", "evidence": ["live: masked"]},
    {"route": ROUTE, "field": "**._links.**", "use": "excluded", "reason": "navigation links"},
]
CODE_TABLE = {
    "id": "prismhr.id_type",
    "source": "synthetic",
    "columns": {"value": "NationalIdType"},
    "codes": [{"raw": "SSN", "value": {"value": "ssn", "basis": "documented"}}, {"raw": "X", "value": {"value": "unknown", "basis": "unmapped"}}],
}


class TableCheckTests(unittest.TestCase):
    def check(self, rows=None, code_tables=None, classified=True, fields=FIELDS):
        routes = {"selected": [{"route": ROUTE, "entities": ["employee"], "classified": classified}]}
        tables = [{"provider": "prismhr", "entity": "employee", "fields": BASE_ROWS if rows is None else rows, "code_tables": [CODE_TABLE] if code_tables is None else code_tables}]
        return check_tables("prismhr", routes, tables, lambda route: fields)

    def test_real_tables_pass_and_classify_every_selected_route(self):
        for provider in PROVIDERS:
            with self.subTest(provider=provider):
                self.assertEqual(table_problems(provider), [])
                self.assertEqual(pending_routes(provider), [])  # Phase 3 closed: none left to classify

    def test_complete_classification_passes(self):
        self.assertEqual(self.check(), [])

    def test_unclassified_field_fails_only_when_the_route_is_classified(self):
        rows = BASE_ROWS[:1] + BASE_ROWS[2:]
        self.assertIn(f"{ROUTE} name.first: not classified", self.check(rows))
        self.assertEqual(self.check(rows, classified=False), [])

    def test_exact_row_beats_group_and_the_most_specific_group_wins(self):
        exact = {"route": ROUTE, "field": "_links.self", "use": "excluded", "reason": "self link"}
        self.assertEqual(self.check(BASE_ROWS + [exact]), [])
        # "_links.*" has one fixed segment, "**._links.**" also one: a tie is a mistake.
        tie = {"route": ROUTE, "field": "_links.*", "use": "excluded", "reason": "again"}
        self.assertIn(f"{ROUTE} _links.edit: matched by 2 equally specific group rows", self.check(BASE_ROWS + [tie]))
        # "items[]._links.*" has two fixed segments, so it wins over "**._links.**" for its field.
        narrower = {"route": ROUTE, "field": "items[]._links.*", "use": "extension", "target": "Employee.provider_extensions", "reason": "item links"}
        self.assertEqual(self.check(BASE_ROWS + [narrower]), [])
        self.assertEqual(classify(BASE_ROWS + [narrower], "items[]._links.href")[0], narrower)
        self.assertIn(f"{ROUTE} id: classified by 2 exact rows", self.check(BASE_ROWS + [BASE_ROWS[0]]))
        row, problem = classify(BASE_ROWS + [exact], "_links.self")
        self.assertEqual((row, problem), (exact, None))

    def test_row_rules(self):
        cases = [
            ({"target": "Employee.name.nickname"}, "target is not a canonical field"),
            ({"transform": "uppercase"}, "unknown transform"),
            ({"transform": "code:prismhr.nothing"}, "unknown transform"),
            ({"transform": "date:someday"}, "unknown transform"),
            ({"evidence": []}, "evidence must be a non-empty list"),
            ({"evidence": ["contracts/prismhr/openapi/prismhr-2025.09.openapi.json#/nope"]}, "evidence does not resolve"),
            ({"evidence": ["my notes"]}, "evidence must start with"),
            ({"field": "name.last"}, "matches no documented field"),
            ({"route": "/emp/other"}, "route is not selected"),
            ({"use": "kept"}, "use must be one of"),
            ({"colour": "red"}, "unknown keys"),
        ]
        for change, expected in cases:
            rows = [dict(BASE_ROWS[1], **change)] + BASE_ROWS[2:] + BASE_ROWS[:1]
            problems = self.check(rows, classified=False)
            self.assertTrue(any(expected in p for p in problems), (change, problems))

    def test_live_empty_containers_follow_the_documented_fields_inside_them(self):
        # Regression (step 1 review): a live empty array, empty object or null is reported as its
        # own path. With every documented leaf classified it must not be reported unclassified.
        documented = frozenset({"arrear[].code", "arrear[].amount", "billing.rate", "name"})
        rows = [{"route": ROUTE, "field": f, "use": "excluded", "reason": "x"} for f in documented]
        for container in ("arrear[]", "billing"):
            self.assertIsNone(live_field_problem(rows, container, documented), container)
        partial = [r for r in rows if r["field"] != "arrear[].amount"]
        self.assertEqual(live_field_problem(partial, "arrear[]", documented), "1 documented fields inside it are not classified")
        # A live field with nothing documented inside it is still checked as a field of its own.
        self.assertEqual(live_field_problem(rows, "extra[]", documented), "not classified")
        self.assertIsNone(live_field_problem(rows, "name", documented))

    def test_live_only_rows_need_no_documented_field(self):
        row = {"route": ROUTE, "field": "nickname", "use": "excluded", "reason": "live only extra", "live_only": True}
        self.assertEqual(self.check(BASE_ROWS + [row]), [])

    def test_extension_rows_need_a_reason_and_an_extension_target(self):
        good = {"route": ROUTE, "field": "name.first", "use": "extension", "target": "Employee.provider_extensions", "reason": "portal setting"}
        rows = [good] + [r for r in BASE_ROWS if r["field"] != "name.first"]
        self.assertEqual(self.check(rows), [])
        for change, expected in (
            ({"target": "Employee.name.first"}, "target must be a record's provider_extensions"),
            ({"use": "sensitive_extension"}, "target must be a record's sensitive_provider_extensions"),
            ({"reason": None}, "a reason is required"),
        ):
            problems = self.check([dict(good, **change)] + rows[1:])
            self.assertTrue(any(expected in p for p in problems), (change, problems))

    def test_date_and_code_transforms(self):
        row = dict(BASE_ROWS[1], transform="date:event")
        self.assertEqual(self.check([row] + BASE_ROWS[2:] + BASE_ROWS[:1]), [])

    def test_code_table_rules(self):
        cases = [
            ({"columns": {"value": "NoSuchEnum"}}, "is not a canonical enum"),
            ({"id": "isolved.id_type"}, "id must start with 'prismhr.'"),
            ({"codes": [{"raw": "SSN", "value": {"value": "passport_x", "basis": "documented"}}]}, "needs a NationalIdType value"),
            ({"codes": [{"raw": "SSN", "value": {"value": "unknown", "basis": "documented"}}]}, "'unknown' and 'unmapped'"),
            ({"codes": [{"raw": "SSN", "value": {"value": "ssn", "basis": "unmapped"}}]}, "'unknown' and 'unmapped'"),
            ({"codes": [{"raw": "A", "value": {"value": "ssn", "basis": "documented"}}, {"raw": "A", "value": {"value": "ssn", "basis": "documented"}}]}, "unique string"),
        ]
        for change, expected in cases:
            table = dict(CODE_TABLE, **change)
            rows = [dict(r, transform=f"code:{table['id']}") if r["field"] == "ssn" else r for r in BASE_ROWS]
            problems = self.check(rows, code_tables=[table])
            self.assertTrue(any(expected in p for p in problems), (change, problems))


class CodeTableContentTests(unittest.TestCase):
    """Pins for code table decisions that a review corrected."""

    def test_documented_daily_pay_frequency_is_mapped(self):
        # D-068 review fix: PrismHR pay period D and UKG every_n_days with 1 day are daily.
        prismhr = code_tables(load_tables("prismhr"))["prismhr.pay_period"]["codes"]
        self.assertEqual(next(c for c in prismhr if c["raw"] == "D")["value"], {"value": "daily", "basis": "documented"})
        ukg = code_tables(load_tables("ukg-ready"))["ukg-ready.period_type"]["codes"]
        self.assertEqual(next(c for c in ukg if c["raw"] == "every_n_days:1")["value"], {"value": "daily", "basis": "documented"})


class RowContentTests(unittest.TestCase):
    """Pins for field row decisions that a review corrected."""

    def rows(self, provider, route):
        return [row for table in load_tables(provider) for row in table.get("fields", []) if route in row_routes(row)]

    def test_prismhr_declined_answers_stay_apart_from_blank(self):
        # D-076 review fix: PrismHR documents 'D' (declined to answer) apart from blank (not
        # specified). Every getEmployee field documenting it must keep the answer: mapped with
        # yes_no_declined, or kept whole in the sensitive extension.
        spec = json.loads((ROOT / PRISMHR_SPEC).read_text(encoding="utf-8"))["components"]["schemas"]
        blocks = {"person": "Person", "client": "Client", "compensation": "Compensation", "contactInformation": "ContactInformation"}
        route = "/employee/v1/getEmployee"
        rows = self.rows("prismhr", route)
        found = []
        for field in sorted(documented_fields("prismhr", route)):
            parts = field.split(".")
            if len(parts) != 3 or parts[1] not in blocks:
                continue
            description = spec[blocks[parts[1]]]["properties"].get(parts[2], {}).get("description", "")
            if re.search(r"'D'\s*\(declined to answer\)", description):
                row, problem = classify(rows, field)
                self.assertIsNone(problem, field)
                found.append(field)
                kept = row["use"] == "sensitive_extension" or (row["use"] == "mapped" and row.get("transform") == "yes_no_declined")
                self.assertTrue(kept, f"{field}: {row['use']} {row.get('transform')}")
        self.assertEqual(len(found), 8, found)  # handicapped, veteran and six veteran categories

    def test_ukg_cost_center_id_is_kept_as_source_id_never_as_code(self):
        # D-076 review fix: a default whose tree cannot be resolved (tree 1: 400 'Cost Center not
        # used') keeps its id as source_id; the id is never presented as a payroll code.
        # Round 2: the tree index the lookup needs is kept with the id on the same org unit.
        rows = self.rows("ukg-ready", "/v2/companies/{cid}/employees/{aid}")
        row, _ = classify(rows, "cost_centers_info.defaults[].value.id")
        self.assertEqual(row["target"], "Employee.job.org_units[].source_id")
        index, _ = classify(rows, "cost_centers_info.defaults[].index")
        self.assertEqual((index["use"], index["target"]), ("mapped", "Employee.job.org_units[].type"))
        lookup = self.rows("ukg-ready", "/v2/companies/{cid}/config/cost-centers")
        self.assertEqual(classify(lookup, "cost_centers[].payroll_code")[0]["target"], "Employee.job.org_units[].code")
        self.assertNotEqual(classify(lookup, "cost_centers[].id")[0]["target"], "Employee.job.org_units[].code")

    def assert_tax_and_i9_fields_stay_masked(self, provider, route, fields):
        """Each field is mapped into a sensitive canonical field (tax_withholding, work_authorization,
        demographics, D-040), kept in the sensitive extension, or excluded: never in the unmasked
        provider_extensions."""
        rows = self.rows(provider, route)
        sensitive = tuple("Employee." + path.replace("[]", "") for path in sensitive_fields(Employee))
        for field in fields:
            row, problem = classify(rows, field)
            self.assertIsNone(problem, field)
            ok = row["use"] in ("sensitive_extension", "excluded") or (
                row["use"] == "mapped" and row["target"].replace("[]", "").startswith(sensitive)
            )
            self.assertTrue(ok, f"{provider} {field}: {row['use']} {row.get('target')}")

    def test_prismhr_withholding_and_i9_fields_stay_masked(self):
        # Step 3b-1. The fields come from the contract: getEmployee compensation properties that
        # are withholding, lock-in or I-9 image blocks, or whose description names withholding,
        # a tax form, filing status, FICA, EIC, I-9 or alien status.
        spec = json.loads((ROOT / PRISMHR_SPEC).read_text(encoding="utf-8"))["components"]["schemas"]
        blocks = {"StateTax", "LocalTax", "LockIns", "EeImage", "I9ImageAudit"}
        words = re.compile(r"(?i)withh|filing status|form w-|w-8|i-9|fica|alien|\bEIC\b|federal")
        route = "/employee/v1/getEmployee"
        fields = []
        for field in sorted(documented_fields("prismhr", route)):
            parts = field.split(".")
            if len(parts) < 3 or parts[1] != "compensation":
                continue
            prop = spec["Compensation"]["properties"].get(parts[2].removesuffix("[]"), {})
            ref = (prop.get("items") or prop).get("$ref", "").rsplit("/", 1)[-1]
            if ref in blocks or words.search(prop.get("description", "")):
                fields.append(field)
        self.assertEqual(len(fields), 54, fields)  # 16 compensation fields (citizenshipStatus included), 38 in the five blocks
        self.assert_tax_and_i9_fields_stay_masked("prismhr", route, fields)

    def test_prismhr_i9_on_file_and_renewal_are_not_completion_or_expiration(self):
        # 3b-1 review fix: 'Form I-9 is on file' is not 'completed', and 'date on which Form I-9
        # must be renewed' is not a document expiration. Neither fills those canonical fields.
        # 3b-2 amendment: on file has its own typed field, i9_on_file.
        rows = self.rows("prismhr", "/employee/v1/getEmployee")
        filed, _ = classify(rows, "employee[].compensation.formI9Filed")
        self.assertEqual((filed["use"], filed["target"]), ("mapped", "Employee.work_authorization.i9_on_file"))
        renew, _ = classify(rows, "employee[].compensation.formI9RenewDate")
        self.assertEqual(renew["use"], "sensitive_extension")
        targets = {row.get("target") for table in load_tables("prismhr") for row in table.get("fields", [])}
        self.assertFalse({"Employee.work_authorization.i9_completed", "Employee.work_authorization.document_expiration_date"} & targets)

    def test_isolved_withholding_and_i9_fields_stay_masked(self):
        # Step 3b-1: every documented field of the list's taxes and i9Documents blocks and
        # reciprocityRule, and every field of i9/status.
        route = "/api/clients/{clientId}/legals/{legalId}/employees"
        fields = [f for f in documented_fields("isolved", route) if f.startswith(("results[].taxes.", "results[].i9Documents.", "results[].reciprocityRule"))]
        self.assertEqual(len(fields), 137, len(fields))  # 5 tax blocks of 19, 3 I-9 documents of 13, 3 others
        self.assert_tax_and_i9_fields_stay_masked("isolved", route, fields)
        status = "/api/clients/{clientId}/legals/{legalId}/employees/{employeeId}/i9/status"
        self.assert_tax_and_i9_fields_stay_masked("isolved", status, documented_fields("isolved", status))


    def test_related_people_personal_fields_never_in_plain_extensions(self):
        # Step 3b-2. Every documented field of a related-people source whose name says it holds
        # personal data is mapped (the model marks what is sensitive), kept in the sensitive
        # extension, or excluded: never in the unmasked provider_extensions. Masked twins are
        # excluded and their unmasked fields mapped (D-020, D-071).
        # A leading "use" is a setting (isolved useEmployeeAddress), not personal data.
        personal = re.compile(r"(?i)^(?!use)\w*(name|birth|ssn|phone|email|address|zip|city|state$|comment|salutation|suffix|prefix|gender|marital|contactinfo|deceased|disabled|tobacco|student|initial)")
        sources = [
            ("prismhr", "/benefits/v1/getDependents", "dependent[]."),
            ("prismhr", "/employee/v1/getEmployee", "employee[].person.emergencyContact[]."),
            ("isolved", "/api/clients/{clientId}/legals/{legalId}/employees/{employeeId}/contacts", "[]."),
            ("ukg-ready", "/v2/companies/{cid}/employees/{aid}/contacts", "contacts[]."),
        ]
        found = 0
        for provider, route, prefix in sources:
            rows = self.rows(provider, route)
            for field in sorted(documented_fields(provider, route)):
                nested_phone = re.search(r"phone\.number$", field)  # UKG work_phone.number and the like
                if not field.startswith(prefix) or not (personal.search(field.rsplit(".", 1)[-1]) or nested_phone):
                    continue
                row, problem = classify(rows, field)
                self.assertIsNone(problem, field)
                found += 1
                self.assertNotEqual(row["use"], "extension", f"{provider} {field}")
        self.assertEqual(found, 57)  # PrismHR dependents 21 and emergency contacts 2, isolved 24, UKG 10
        contacts = self.rows("isolved", sources[2][1])
        uses = {field: classify(contacts, field)[0]["use"] for field in ("[].ssn", "[].birthDate", "[].ssnUnmasked", "[].birthDateUnmasked")}
        self.assertEqual(uses, {"[].ssn": "excluded", "[].birthDate": "excluded", "[].ssnUnmasked": "mapped", "[].birthDateUnmasked": "mapped"})

    def test_pto_hours_fields_only_from_documented_units(self):
        # Step 3b-2 (CANONICAL_MODEL 1.5, D-027, D-077): an amount enters a PtoBalance hours field
        # only when its unit is documented. PrismHR: the field's description says hours, and no
        # balance is derived. isolved: amounts without a unit stay raw, so nothing is mapped. UKG:
        # milliseconds converted, and accrual/2 current-period amounts are not year to date.
        hours = {f"Employee.pto_balances[].{name}" for name in ("balance", "accrued_ytd", "used_ytd", "carryover")}
        spec = json.loads((ROOT / PRISMHR_SPEC).read_text(encoding="utf-8"))["components"]["schemas"]["PaidTimeOff"]["properties"]
        prismhr = [row for row in self.rows("prismhr", "/benefits/v1/getPaidTimeOff") if row.get("target") in hours]
        self.assertEqual(len(prismhr), 3)
        for row in prismhr:
            self.assertIn("hours", spec[row["field"].split(".")[-1]]["description"], row["field"])
        self.assertNotIn("Employee.pto_balances[].balance", {row["target"] for row in prismhr})
        isolved = self.rows("isolved", "/api/clients/{clientId}/legals/{legalId}/employees/{employeeId}/accruals")
        self.assertFalse([row["field"] for row in isolved if row.get("target") in hours])
        ukg = [row for n in (1, 2) for row in self.rows("ukg-ready", f"/v2/companies/{{cid}}/employees/{{aid}}/accrual/{n}/balances")]
        typed = [row for row in ukg if row.get("target") in hours]
        self.assertEqual(len(typed), 6)
        self.assertTrue(all(row["transform"] == "ms_to_hours" for row in typed))
        current = [row for row in ukg if row["field"] in ("accrual_balances[].current_accrued.hours", "accrual_balances[].taken.hours")]
        self.assertEqual([row["use"] for row in current], ["extension", "extension"])

    def test_bank_numbers_never_in_plain_extensions(self):
        # Contract-derived: every documented (or live-only) field of a selected route whose name is
        # a bank account or routing number is mapped to a sensitive field or a last-4 field, kept in
        # sensitive_provider_extensions, or excluded; never in plain provider_extensions (D-040, D-081).
        name = re.compile(r"(?i)(account.?num|transit.?num|routing.?num|bank.?account|checkaccountach|^account$|wireaccount)")
        sensitive = {f"{model.__name__}.{path}" for model in (DirectDeposit, Paycheck, Employee) for path in sensitive_fields(model)}
        checked = 0
        for provider in PROVIDERS:
            for route in (entry["route"] for entry in load_routes(provider)["selected"]):
                rows = self.rows(provider, route)
                fields = set(documented_fields(provider, route) or ()) | {r["field"] for r in rows if r.get("live_only") and "*" not in r["field"]}
                for field in sorted(f for f in fields if name.search(f.split(".")[-1].replace("[]", ""))):
                    row, problem = classify(rows, field)
                    with self.subTest(provider=provider, route=route, field=field):
                        self.assertIsNone(problem)
                        self.assertNotEqual(row["use"], "extension")
                        if row["use"] == "mapped":
                            self.assertTrue(row["target"] in sensitive or row["target"].endswith("_last4"), row["target"])
                    checked += 1
        self.assertGreaterEqual(checked, 25)

    def test_documented_codes_cite_the_contract(self):
        # CANONICAL_MODEL 1.7: documented means the spec, a lookup reference or the provider's code
        # table states the meaning. A label seen only live is inferred (D-081 review).
        for provider in PROVIDERS:
            for table_id, table in code_tables(load_tables(provider)).items():
                for code in table["codes"]:
                    if any(code[column]["basis"] == "documented" for column in table["columns"]):
                        with self.subTest(table=table_id, raw=code["raw"]):
                            self.assertTrue(any(e.startswith("contracts/") for e in code.get("evidence", [])))

    def test_label_tables_are_never_documented(self):
        # No provider documents a tax type or what a memo earning is for (D-055, D-056): readings
        # from exact labels are inferred, and nothing else is claimed.
        ids = ("prismhr.tax_label", "isolved.tax_label", "ukg-ready.tax_label", "isolved.memo_label")
        tables = {table_id: table for provider in PROVIDERS for table_id, table in code_tables(load_tables(provider)).items()}
        for table_id in ids:
            with self.subTest(table=table_id):
                self.assertTrue(tables[table_id]["codes"])
                bases = {cell["basis"] for code in tables[table_id]["codes"] for column in tables[table_id]["columns"]
                         for cell in [code[column]]}
                self.assertLessEqual(bases, {"inferred", "unmapped"})


class MappingDocumentTests(unittest.TestCase):
    def test_committed_documents_match_the_tables(self):
        # Drift test. Fix: python -m normalization export-mappings
        rendered = render_mappings()
        self.assertEqual(sorted(p.name for p in DOCS.glob("*.md") if p.name != "README.md"), sorted(rendered))
        for name, text in rendered.items():
            self.assertEqual((DOCS / name).read_bytes(), text.encode("utf-8"), f"{name} is out of date")


if __name__ == "__main__":
    unittest.main()
