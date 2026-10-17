"""D-020: a provider-masked value maps to null with hidden_by_source and a
value_redacted_in_source diagnostic, never to a partial identifier; visible last characters go
to a separate last4 field."""
import unittest
from pathlib import Path

from normalization.canonical.diagnostics import DiagnosticCode
from normalization.canonical.employee import NationalId
from normalization.canonical.values import ValueStatus
from normalization.employees import adapter
from normalization.employees.bundle import load_bundle
from normalization.employees.common import HIDDEN, NP, Ctx, is_masked, visible_last4

ROOT = Path(__file__).resolve().parents[1]
SSN = {"value": "ssn", "raw_code": "ssn", "raw_label": None, "basis": "documented"}


def employee(provider: str, source_id: str):
    records = adapter(provider).normalize_employees(load_bundle(ROOT / "fixtures" / provider / "bundle.json"))
    return next(r for r in records if source_id in r.source_ids.values())


def redacted_fields(record) -> set[str]:
    return {d.field for d in record.diagnostics if d.code is DiagnosticCode.VALUE_REDACTED_IN_SOURCE}


class MaskHelpers(unittest.TestCase):
    def test_masks_are_recognized_and_only_visible_digits_kept(self):
        for raw, last4 in (("***-**-****", None), ("***-**-6789", "6789"), ("******1068", "1068"), ("REDACTED", None),
                           ("redacted", None), ("*", None)):
            with self.subTest(raw=raw):
                self.assertTrue(is_masked(raw))
                self.assertEqual(visible_last4(raw), last4)
        for raw in ("666-12-3456", "1988-04-12", "", None, 12):
            with self.subTest(raw=raw):
                self.assertFalse(is_masked(raw))

    def test_national_id_outcomes(self):
        """Masked: value hidden, visible digits in value_last4, a redaction diagnostic at the value.
        Null or blank: no id, no diagnostic. A full value is kept."""
        cases = (  # raw, result value, value status, last4, last4 status, diagnostics
            ("***-**-6789", None, ValueStatus.HIDDEN_BY_SOURCE, "6789", None, [DiagnosticCode.VALUE_REDACTED_IN_SOURCE]),
            ("***-**-****", None, ValueStatus.HIDDEN_BY_SOURCE, None, ValueStatus.NOT_PROVIDED, [DiagnosticCode.VALUE_REDACTED_IN_SOURCE]),
            ("666-45-1101", "666-45-1101", None, None, ValueStatus.NOT_APPLICABLE, []),
        )
        for raw, value, status, last4, last4_status, diagnostics in cases:
            ctx = Ctx("prismhr")
            entry = ctx.national_id(NationalId, raw, SSN, "national_ids[0]")
            with self.subTest(raw=raw):
                self.assertEqual((entry.value, entry.field_status.get("value")), (value, status))
                self.assertEqual((entry.value_last4, entry.field_status.get("value_last4")), (last4, last4_status))
                self.assertEqual([(d.code, d.field) for d in ctx.diagnostics], [(code, "national_ids[0].value") for code in diagnostics])
        for raw in (None, "", "   "):
            ctx = Ctx("prismhr")
            with self.subTest(raw=raw):
                self.assertIs(ctx.national_id(NationalId, raw, SSN, "national_ids[0]"), NP)
                self.assertEqual(ctx.diagnostics, [])

    def test_masked_text_and_dates_in_sensitive_fields(self):
        ctx = Ctx("prismhr")
        self.assertIs(ctx.text("***-***-1234", "personal_contact.phones[0].number", sensitive=True), HIDDEN)
        self.assertEqual(ctx.text("***", "note"), "***")  # not a sensitive field: kept as sent
        from normalization.canonical.parsing import DateRole
        self.assertIs(ctx.date("**/**/1988", DateRole.EVENT, "demographics.birth_date"), HIDDEN)
        self.assertEqual(len(ctx.diagnostics), 2)


class AdapterCases(unittest.TestCase):
    """The masked values in the fixtures, end to end."""

    def assert_hidden(self, part, last4):
        self.assertIsNone(part.value)
        self.assertEqual(part.field_status["value"], ValueStatus.HIDDEN_BY_SOURCE)
        self.assertEqual(part.value_last4, last4)

    def test_prismhr_ssn_masked_without_and_with_visible_digits(self):
        first, second = employee("prismhr", "P00001"), employee("prismhr", "P00002")
        self.assert_hidden(first.national_ids[0], None)
        self.assert_hidden(second.national_ids[0], "4321")
        self.assertIn("national_ids[0].value", redacted_fields(first))

    def test_prismhr_dependent_ssn_masked(self):
        record = employee("prismhr", "P00001")
        self.assert_hidden(record.related_people[0].national_id, "5555")
        self.assertIn("related_people[0].national_id.value", redacted_fields(record))

    def test_prismhr_blank_ssn_has_no_national_id(self):
        record = employee("prismhr", "P00003")
        self.assertIsNone(record.national_ids)
        self.assertEqual(record.field_status["national_ids"], ValueStatus.NOT_PROVIDED)

    def test_isolved_masked_twins_never_used_and_masked_unmasked_field_hidden(self):
        record = employee("isolved", "70001")
        spouse, child = record.related_people
        self.assertEqual(spouse.national_id.value, "666-22-6789")  # ssnUnmasked, not the masked twin ssn
        self.assertEqual(str(spouse.birth_date), "1988-07-20")  # birthDateUnmasked, not '**/**/1988'
        self.assert_hidden(child.national_id, "4444")  # ssnUnmasked itself still masked
        self.assertNotIn("*****", str(record.model_dump()))

    def test_isolved_masked_ssn_from_employees_with_ssn(self):
        record = employee("isolved", "70003")
        self.assert_hidden(record.national_ids[0], "9876")
        self.assertIn("national_ids[0].value", redacted_fields(record))


if __name__ == "__main__":
    unittest.main()
