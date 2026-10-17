"""Shared value conversions every adapter goes through (employees/common.Ctx, D-091): code lookup
(CANONICAL_MODEL 1.7, D-061) and UKG milliseconds to hours (D-028). The adapters' use of them on
the fixtures is in the golden, entity and payroll tests."""
import unittest
from decimal import Decimal

from normalization.canonical.diagnostics import DiagnosticCode
from normalization.employees.common import NP, Ctx


class CodeLookup(unittest.TestCase):
    def test_code_lookup_outcomes(self):
        """A documented code maps with no diagnostic; an inferred one says so; a code listed
        without a canonical value, or not in the table, is unknown and unmapped with the raw code
        kept; blank is not provided; booleans are looked up as true or false; raw_code overrides
        what is kept; a sensitive field's message never names the code."""
        cases = (  # table, raw, keyword arguments, value, basis, raw code kept, diagnostics
            ("prismhr.gender", "M", {}, "male", "documented", "M", []),
            ("prismhr.dependent_gender", "M", {}, "male", "inferred", "M", [DiagnosticCode.INFERRED_MAPPING]),
            ("prismhr.gender", "U", {}, "unknown", "unmapped", "U", [DiagnosticCode.UNKNOWN_CODE]),
            ("prismhr.gender", "ZZ", {}, "unknown", "unmapped", "ZZ", [DiagnosticCode.UNKNOWN_CODE]),
            ("prismhr.gender", " M ", {"raw_code": "Male"}, "male", "documented", "Male", []),
            ("prismhr.employee_1099", True, {}, None, "documented", "true", []),
        )
        for table, raw, extra, value, basis, kept, diagnostics in cases:
            ctx = Ctx("prismhr")
            coded = ctx.coded(table, raw, "demographics.gender", **extra)
            with self.subTest(table=table, raw=raw):
                if value is not None:
                    self.assertEqual(coded["value"], value)
                self.assertEqual((coded["basis"], coded["raw_code"]), (basis, kept))
                self.assertEqual([d.code for d in ctx.diagnostics], diagnostics)
                self.assertTrue(all(d.field == "demographics.gender" and d.evidence == table for d in ctx.diagnostics))
        for raw in (None, "", "  "):
            ctx = Ctx("prismhr")
            with self.subTest(raw=raw):
                self.assertIs(ctx.coded("prismhr.gender", raw, "demographics.gender"), NP)
                self.assertEqual(ctx.diagnostics, [])
        ctx = Ctx("prismhr")
        ctx.coded("prismhr.gender", "ZZ", "demographics.gender", sensitive=True)
        self.assertNotIn("ZZ", ctx.diagnostics[0].message)
        self.assertEqual(Ctx("prismhr").coded("prismhr.gender", "ZZ", "x", sensitive=True)["raw_code"], "ZZ")  # masked on output


class MillisecondsToHours(unittest.TestCase):
    def test_milliseconds_to_hours(self):
        """D-028, D-091: exact when the division ends; otherwise 7 decimal places, so the integer
        milliseconds of the contract are always recoverable. Zero is 0, never null; blank is not
        provided; text is unparseable."""
        cases = (
            (288_000_000, Decimal("80")),  # 80 h (live pay statement value, D-028)
            (5_400_000, Decimal("1.5")),
            (26_400_000, Decimal("7.3333333")),  # 7 h 20 min: the division does not end
            (60_000, Decimal("0.0166667")),  # one minute
            (1, Decimal("0.0000003")),
            (0, Decimal("0")),
        )
        for raw, hours in cases:
            ctx = Ctx("ukg-ready")
            value = ctx.ms_to_hours(raw, "pto_balances[0].balance")
            with self.subTest(raw=raw):
                self.assertEqual(value, hours)
                self.assertLessEqual(-value.as_tuple().exponent, 7)
                self.assertEqual((value * 3_600_000).to_integral_value(), raw)
                self.assertEqual(ctx.diagnostics, [])
        for raw in range(0, 3_600_000, 997):  # every ms value is recoverable, not only the listed ones
            self.assertEqual((Ctx("ukg-ready").ms_to_hours(raw, "x") * 3_600_000).to_integral_value(), raw)
        self.assertIs(Ctx("ukg-ready").ms_to_hours(None, "x"), NP)
        ctx = Ctx("ukg-ready")
        self.assertIs(ctx.ms_to_hours("eight hours", "x"), NP)
        self.assertEqual([d.code for d in ctx.diagnostics], [DiagnosticCode.UNPARSEABLE_VALUE])


if __name__ == "__main__":
    unittest.main()
