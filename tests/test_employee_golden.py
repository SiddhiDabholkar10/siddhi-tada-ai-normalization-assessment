"""Employee slice (D-077, D-080): golden outputs per provider and the employee edge cases pinned
one by one. The goldens are the whole ``normalize`` document (D-085), so they grow as the
Phase 5 adapters land. The table conformance checks are in ``test_table_conformance``.

Regenerate the golden files after an intended change:
    UPDATE_GOLDEN=1 python -m unittest tests.test_employee_golden
"""
import json
import os
import unittest
from decimal import Decimal
from pathlib import Path

from normalization.canonical.diagnostics import DiagnosticCode
from normalization.canonical.values import ValueStatus
from normalization.employees import adapter
from normalization.employees.bundle import load_bundle
from normalization.output import render_run
from normalization.pipeline import normalize_bundle

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests" / "golden"
PROVIDERS = ("prismhr", "isolved", "ukg-ready")
NS, NA, HIDDEN = ValueStatus.NOT_PROVIDED, ValueStatus.NOT_APPLICABLE, ValueStatus.HIDDEN_BY_SOURCE


def records(provider: str):
    return adapter(provider).normalize_employees(load_bundle(ROOT / "fixtures" / provider / "bundle.json"))


def output(provider: str) -> str:
    """The normalize document of the provider's fixture, sensitive values shown."""
    return render_run(normalize_bundle(load_bundle(ROOT / "fixtures" / provider / "bundle.json")), "bundle.json", show_sensitive=True)


def by_source(provider: str, value: str):
    return next(r for r in records(provider) if value in r.source_ids.values())


def codes(record, code: DiagnosticCode) -> set[str]:
    return {d.field for d in record.diagnostics if d.code is code}


class GoldenTests(unittest.TestCase):
    def test_golden_outputs(self):
        """Per provider and output part (the run header and each entity list), then the exact text.
        Each test run is a new process (new hash seed), so the compare also proves the output is
        deterministic."""
        for provider in PROVIDERS:
            path = GOLDEN / f"{provider}.json"
            text = output(provider)
            if os.environ.get("UPDATE_GOLDEN"):
                path.parent.mkdir(exist_ok=True)
                path.write_text(text, encoding="utf-8", newline="\n")
            golden_text = path.read_text(encoding="utf-8")
            document, golden = json.loads(text), json.loads(golden_text)
            for part in sorted(set(document) | set(golden)):
                with self.subTest(provider=provider, part=part):
                    self.assertEqual(document.get(part), golden.get(part), "run UPDATE_GOLDEN=1 after an intended change")
            with self.subTest(provider=provider, part="text"):
                self.assertEqual(text, golden_text, "run UPDATE_GOLDEN=1 after an intended change")

    def test_unread_blocks_leave_no_trace(self):
        """The fixtures carry the blocks the employee adapters do not read (PrismHR directDeposit and
        scheduledDeduction, isolved list directDeposits[]); nothing from them reaches the records."""
        for provider in PROVIDERS:
            body = json.loads(output(provider))["employees"]
            with self.subTest(provider=provider):
                self.assertNotRegex(json.dumps(body), r"directDeposit|scheduledDeduction")

    def test_hsa_settings_stay_on_the_employee_as_sensitive(self):
        """PrismHR HSA transfer accounts are kept in the sensitive extension, not as deposits (D-081)."""
        record = records("prismhr")[0]
        self.assertTrue([key for key in record.sensitive_provider_extensions if ".hsa.hsaDepositSettings" in key])
        self.assertFalse([key for key in record.provider_extensions if ".hsa." in key])


class PrismhrCases(unittest.TestCase):
    def test_declined_answers_stay_apart_from_blank(self):
        jo = by_source("prismhr", "P00001")
        self.assertEqual(jo.demographics.veteran.field_status["is_veteran"], NS)
        self.assertIs(jo.demographics.veteran.not_disclosed, True)
        self.assertEqual(jo.sensitive_provider_extensions["getEmployee:employee[0].person.veteran"], "D")
        rehired = by_source("prismhr", "P00002")
        self.assertEqual(rehired.demographics.disability.field_status["has_disability"], NS)
        self.assertEqual(rehired.sensitive_provider_extensions["getEmployee:employee[0].person.handicapped"], "D")
        self.assertEqual(rehired.demographics.veteran.field_status["is_disabled_veteran"], NS)  # blank
        self.assertNotIn("getEmployee:employee[0].person.disabledVet", rehired.sensitive_provider_extensions)

    def test_undocumented_live_codes_are_unknown_with_raw_code(self):
        jo, rehired = by_source("prismhr", "P00001"), by_source("prismhr", "P00002")
        filing = jo.tax_withholding.federal.filing_status
        self.assertEqual((filing.value.value, filing.raw_code, filing.basis.value), ("unknown", "M", "unmapped"))
        period = rehired.compensation.base_rate_period
        self.assertEqual((period.value.value, period.raw_code), ("unknown", "A"))
        self.assertIn("compensation.base_rate_period", codes(rehired, DiagnosticCode.UNKNOWN_CODE))

    def test_sentinel_effective_dates_keep_the_row(self):
        rehired = by_source("prismhr", "P00002")
        self.assertEqual(len(rehired.compensation_history), 4)
        for index in (1, 2):
            entry = rehired.compensation_history[index]
            self.assertIsNone(entry.effective_date)
            self.assertEqual(entry.field_status["effective_date"], NS)
            self.assertIn(f"compensation_history[{index}].effective_date", codes(rehired, DiagnosticCode.SENTINEL_DATE))
        self.assertEqual(rehired.compensation_history[1].amount, Decimal("17.25"))

    def test_rehired_history_and_reason_join(self):
        rehired = by_source("prismhr", "P00002")
        statuses = [(p.status.value.value, str(p.effective_date), p.reason) for p in rehired.employment_history]
        self.assertEqual(statuses, [("active", "2012-05-14", None), ("terminated", "2018-08-31", "Moved away"), ("active", "2020-02-03", "Rehire")])
        self.assertEqual(str(rehired.employment.hire_date), "2020-02-03")
        self.assertEqual(str(rehired.employment.original_hire_date), "2012-05-14")
        self.assertEqual(rehired.employment.field_status["rehire_date"], NS)

    def test_terminated_contractor(self):
        gone = by_source("prismhr", "P00003")
        self.assertEqual(gone.employment.status.value.value, "terminated")
        self.assertEqual(str(gone.employment.termination_date), "2025-06-30")
        self.assertEqual(gone.employment.termination_reason, "DEC")
        self.assertEqual((gone.employment.termination_type.raw_code, gone.employment.termination_type.value.value), ("N", "unknown"))
        self.assertEqual(gone.employment.worker_type.value.value, "contractor")
        self.assertEqual(gone.demographics.field_status["birth_date"], NS)  # blank
        active = by_source("prismhr", "P00001")
        self.assertEqual(active.employment.field_status["termination_date"], NA)

    def test_pay_group_without_schedule(self):
        gone = by_source("prismhr", "P00003")
        self.assertEqual(gone.compensation.field_status["pay_frequency"], NS)
        self.assertIn("compensation.pay_frequency", codes(gone, DiagnosticCode.SOURCE_UNAVAILABLE))
        self.assertEqual(by_source("prismhr", "P00001").compensation.pay_frequency.value.value, "biweekly")

    def test_withholding_overrides(self):
        jo, rehired, gone = (by_source("prismhr", e) for e in ("P00001", "P00002", "P00003"))
        self.assertEqual(jo.tax_withholding.federal.additional_amount, Decimal("25.00"))  # A
        self.assertIs(rehired.tax_withholding.states[0].is_blocked, True)  # B
        self.assertEqual(jo.tax_withholding.states[0].field_status["additional_amount"], NA)  # F
        self.assertEqual(jo.sensitive_provider_extensions["getEmployee:employee[0].compensation.stateTax[0].overrideType"], "F")
        self.assertEqual(gone.sensitive_provider_extensions["getEmployee:employee[0].compensation.fedOverrideType"], "P")

    def test_related_people_pending_and_contact_types(self):
        people = by_source("prismhr", "P00001").related_people
        spouse, child, friend, phone, email, address = people
        self.assertEqual((spouse.is_active, spouse.is_dependent, spouse.is_beneficiary), (True, True, True))
        self.assertEqual(child.field_status["is_active"], NS)  # pending never reads as inactive
        self.assertEqual((friend.is_dependent, friend.is_beneficiary, friend.is_active), (False, True, False))
        self.assertEqual(friend.relationship.value.value, "unknown")
        self.assertEqual(phone.phones[0].type.value, "unknown")
        self.assertEqual(email.email, "alex.contact@example.org")
        self.assertEqual(address.field_status["phones"], NS)
        self.assertEqual(address.field_status["email"], NS)
        self.assertIs(phone.is_emergency_contact, True)
        self.assertEqual(phone.field_status["is_dependent"], NS)

    def test_live_schedule_key_is_read_and_documented_key_too(self):
        """The demo sends clientPayrollSchedule (routes.json live_renames, D-062); the fixture uses it,
        and the documented clientPayrollSchedules is read the same way."""
        from normalization.employees.bundle import parse_bundle
        text = (ROOT / "fixtures" / "prismhr" / "bundle.json").read_text(encoding="utf-8")
        self.assertIn('"clientPayrollSchedule":', text)
        live = [r.compensation.pay_frequency for r in records("prismhr")]
        documented = adapter("prismhr").normalize_employees(parse_bundle(text.replace('"clientPayrollSchedule":', '"clientPayrollSchedules":')))
        for frequencies in (live, [r.compensation.pay_frequency for r in documented]):
            self.assertEqual([f.value.value if f else None for f in frequencies], ["biweekly", "biweekly", None])

    def test_live_history_key_is_read(self):
        jo = by_source("prismhr", "P00001")
        self.assertEqual([str(j.effective_date) for j in jo.job_history], ["2021-07-01", "2021-07-01", "2019-01-01", "2016-03-01"])
        self.assertEqual(jo.employment_history[1].reason, "Family leave")


class IsolvedCases(unittest.TestCase):
    def test_rehired_two_employments(self):
        rehired = by_source("isolved", "70002")
        ids = [p.employment_id for p in rehired.employment_history]
        self.assertEqual(ids, ["811", "811", "812", "811", "812"])
        self.assertEqual(str(rehired.employment.rehire_date), "2022-01-10")
        # Active again: termination fields are not applicable; the last termination stays raw (D-080).
        for field in ("termination_date", "termination_type", "termination_reason"):
            self.assertEqual(rehired.employment.field_status[field], NA)
        self.assertEqual(rehired.provider_extensions["employees:results[1].terminationDate"], "2021-06-30T00:00:00")
        self.assertEqual(rehired.provider_extensions["employees:results[1].terminationType"], "Voluntary Termination")
        self.assertEqual(rehired.employment_history[2].field_status["end_date"], NA)  # open entry

    def test_404_rules(self):
        rehired = by_source("isolved", "70002")
        self.assertEqual(rehired.job_history, [])  # jobs: no records (D-011)
        self.assertIn("job_history", codes(rehired, DiagnosticCode.EMPTY_VIA_404))
        self.assertIsNone(rehired.related_people)  # contacts: meaning unknown
        self.assertEqual(rehired.field_status["related_people"], NS)
        self.assertIn("related_people", codes(rehired, DiagnosticCode.SOURCE_UNAVAILABLE))

    def test_key_absent_null_and_blank(self):
        contractor, rehired = by_source("isolved", "70003"), by_source("isolved", "70002")
        self.assertEqual(contractor.demographics.field_status["gender"], NS)  # key absent
        self.assertEqual(contractor.demographics.disability.field_status["has_disability"], NS)  # null
        self.assertEqual(rehired.demographics.field_status["tobacco_user"], NS)  # null
        self.assertEqual(contractor.employment.status.raw_code, "Leave of Absence")
        self.assertEqual(contractor.employment.status.value.value, "unknown")

    def test_filing_status_and_block(self):
        contractor = by_source("isolved", "70003")
        federal = contractor.tax_withholding.federal
        self.assertEqual((federal.filing_status.raw_code, federal.filing_status.value.value), ("FDM2", "unknown"))
        self.assertIs(federal.is_blocked, True)
        local = contractor.tax_withholding.locals[0]
        self.assertEqual((local.residency.value, local.field_status["jurisdiction"]), ("non_resident", NS))

    def test_i9_timestamp_split(self):
        first = by_source("isolved", "70001")
        self.assertEqual(str(first.work_authorization.i9_completed_date), "2019-04-03")
        self.assertEqual(first.sensitive_provider_extensions["employees:results[0].i9Documents.i9CompletedDate"], "2019-04-03T13:45:00")

    def test_pay_from_salary_in_effect_and_none_in_effect(self):
        first, contractor = by_source("isolved", "70001"), by_source("isolved", "70003")
        self.assertEqual(first.compensation.pay_frequency.raw_code, "26")
        self.assertEqual(first.compensation.pay_group_id, "isolved:900002:pay_group:6001:7625")
        self.assertEqual(first.provider_extensions["salaries:[0].frequency.id"], 24)  # entry not in effect
        self.assertEqual(contractor.compensation.field_status["pay_frequency"], NS)
        # A time of day with no time zone: the date part, reported with the dropped time (D-096).
        self.assertEqual(str(contractor.compensation.effective_date), "2024-09-16")
        self.assertIn("compensation.effective_date", codes(contractor, DiagnosticCode.INFERRED_MAPPING))

    def test_managers_across_legals(self):
        first = by_source("isolved", "70001")
        self.assertEqual(first.job.manager_employee_id, "isolved:900002:employee:6002:70009")
        self.assertEqual(first.job_history[0].manager_employee_id, "isolved:900002:employee:6001:70002")
        self.assertEqual(first.job_history[0].field_status["supervisor_employee_id"], NS)

    def test_accrual_amounts_stay_raw(self):
        first = by_source("isolved", "70001")
        balance = first.pto_balances[0]
        self.assertEqual({balance.field_status[f] for f in ("balance", "accrued_ytd", "used_ytd", "carryover")}, {NS})
        self.assertIn("pto_balances[0]", codes(first, DiagnosticCode.UNIT_UNVERIFIED))
        self.assertEqual(first.provider_extensions["accruals:[0].currentBalance"], "40.0")


class UkgCases(unittest.TestCase):
    def test_milliseconds_to_hours(self):
        first = by_source("ukg-ready", "1101")
        self.assertEqual(first.compensation.standard_hours, Decimal("75.5"))
        self.assertEqual([b.balance for b in first.pto_balances], [Decimal("40"), Decimal("12.5")])
        self.assertEqual(first.pto_balances[0].accrued_ytd, Decimal("48"))
        self.assertEqual(first.provider_extensions["accrual/1/balances:accrual_balances[0].pending_approval"], 14400000)

    def test_sentinel_and_latest_entry(self):
        first = by_source("ukg-ready", "1101")
        self.assertEqual(first.compensation_history[0].field_status["effective_date"], NS)
        self.assertIn("compensation_history[0].effective_date", codes(first, DiagnosticCode.SENTINEL_DATE))
        self.assertEqual(str(first.compensation.effective_date), "2023-04-01")
        self.assertEqual(first.compensation.pay_frequency.raw_code, "every_n_weeks:2")

    def test_cost_center_trees(self):
        first, contractor = by_source("ukg-ready", "1101"), by_source("ukg-ready", "1103")
        found, refused = first.job.org_units
        self.assertEqual((found.type.raw_code, found.source_id, found.code, found.name), ("0", "8100", "KIT", "Kitchen"))
        self.assertEqual((refused.type.raw_code, refused.source_id, refused.field_status["code"]), ("1", "8200", NS))
        self.assertIn("job.org_units[1]", codes(first, DiagnosticCode.SOURCE_UNAVAILABLE))
        missing = contractor.job.org_units[0]
        self.assertEqual((missing.source_id, missing.field_status["name"]), ("8399", NS))

    def test_person_grouping_and_rehire(self):
        first, second = by_source("ukg-ready", "1101"), by_source("ukg-ready", "1102")
        self.assertEqual(first.person_ref, second.person_ref)
        self.assertNotEqual(first.tax_entity_id, second.tax_entity_id)
        self.assertEqual(str(second.employment.hire_date), "2024-03-04")
        self.assertEqual(str(second.employment.original_hire_date), "2015-02-01")
        self.assertEqual(second.employment.field_status["termination_date"], NA)  # active again (D-080)
        self.assertEqual(second.provider_extensions["detail:dates.terminated"], "2020-10-31")
        self.assertIn("pto_balances", codes(second, DiagnosticCode.SOURCE_UNAVAILABLE))  # accrual/1 403
        # accrual/1 refused and accrual/2 empty: not known to be empty, so not [] (no "no PTO" claim).
        self.assertIsNone(second.pto_balances)
        self.assertEqual(second.field_status["pto_balances"], NS)
        contractor = by_source("ukg-ready", "1103")  # accrual/1 empty, accrual/2 refused (400)
        self.assertEqual(contractor.field_status["pto_balances"], NS)
        self.assertEqual(by_source("ukg-ready", "1101").pto_balances[0].plan_name, "PTO")  # both available
        self.assertEqual(len(second.personal_contact.addresses), 1)  # mailing address not separate

    def test_terminated_contractor_no_id_needed(self):
        contractor = by_source("ukg-ready", "1103")
        self.assertEqual(contractor.national_ids[0].type.value.value, "not_required")
        self.assertEqual(contractor.national_ids[0].field_status["value"], NA)
        self.assertEqual(contractor.employment.worker_type.value.value, "contractor")
        self.assertEqual(contractor.employment.employment_type.raw_label, "Consultant")
        self.assertEqual(contractor.employment.employment_type.value.value, "unknown")
        self.assertIs(contractor.demographics.is_deceased, True)
        self.assertEqual(contractor.field_status["person_ref"], NS)

    def test_worker_type_needs_one_flag_and_not_the_other(self):
        from normalization.employees.common import Ctx
        from normalization.employees.ukg_ready import _worker_type
        cases = {(True, False): "employee", (False, True): "contractor", (True, True): "unknown",
                 (False, False): "unknown", (None, True): "unknown", (True, None): "unknown"}
        for (w2, contractor), expected in cases.items():
            ctx = Ctx("ukg-ready")
            flags = {k: v for k, v in (("W2", w2), ("_1099", contractor)) if v is not None}
            result = _worker_type(ctx, {"employee-tax-type": flags})
            with self.subTest(w2=w2, contractor=contractor):
                self.assertEqual(result["value"], expected)
                code = DiagnosticCode.UNKNOWN_CODE if expected == "unknown" else DiagnosticCode.INFERRED_MAPPING
                self.assertEqual([d.code for d in ctx.diagnostics], [code])

    def test_client_type_reads_only_a_label_that_says_full_or_part_time(self):
        """D-099: a client-defined type is read from its label only when the label says full or
        part time at its start; otherwise it stays unknown (D-074), or goes to the code table."""
        from normalization.employees.common import Ctx
        cases = {"Full Time": "full_time", "FT Non-Exempt": "full_time", "full-time": "full_time", "PT Hourly": "part_time",
                 "Part Time": "part_time", "FTE": "unknown", "Seasonal": "unknown", "Consultant": "unknown",
                 "Not FT": "unknown", None: "unknown"}
        for label, expected in cases.items():
            ctx = Ctx("ukg-ready")
            result = ctx.client_type("61", "employment.employment_type", label)
            with self.subTest(label=label):
                self.assertEqual((result["value"], result["raw_code"], result["raw_label"]), (expected, "61", label))
                self.assertEqual(result["basis"], "unmapped" if expected == "unknown" else "inferred")
                code = DiagnosticCode.UNKNOWN_CODE if expected == "unknown" else DiagnosticCode.INFERRED_MAPPING
                self.assertEqual([d.code for d in ctx.diagnostics], [code])

    def test_pay_period_link_is_the_sole_entry(self):
        """The contract allows one pay_period entry (maxItems 1); several are refused, not resolved."""
        from normalization.employees.bundle import Bundle
        from normalization.employees.common import Ctx
        from normalization.employees.ukg_ready import Lookups, _pay_frequency
        lookups = Lookups(load_bundle(ROOT / "fixtures" / "ukg-ready" / "bundle.json"), "7001")
        one = {"pay_period": [{"id": 9001, "effective_from": "2023-01-01"}]}
        ctx = Ctx("ukg-ready")
        frequency, group = _pay_frequency(ctx, "900003", "7001", one, lookups)
        self.assertEqual((frequency["value"], group), ("biweekly", "ukg-ready:900003:pay_group:7001:9001"))
        two = {"pay_period": [{"id": 9002, "effective_from": "2019-06-03"}, {"id": 9001, "effective_from": "2023-01-01"}]}
        ctx = Ctx("ukg-ready")
        frequency, group = _pay_frequency(ctx, "900003", "7001", two, lookups)
        self.assertEqual((frequency.status, group.status), (NS, NS))
        self.assertEqual([d.code for d in ctx.diagnostics], [DiagnosticCode.CONFLICTING_SOURCES])

    def test_contacts(self):
        spouse, uncle = by_source("ukg-ready", "1101").related_people
        self.assertEqual(spouse.relationship.value.value, "spouse")
        self.assertEqual(uncle.relationship.value.value, "unknown")
        self.assertIs(uncle.is_active, False)


if __name__ == "__main__":
    unittest.main()
