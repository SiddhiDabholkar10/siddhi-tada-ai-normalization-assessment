"""Tests for the shared canonical conventions (Phase 2, step 1)."""
import json
import unittest
from datetime import date
from decimal import Decimal
from typing import ClassVar

from pydantic import Field, ValidationError

from normalization.canonical import (
    SENSITIVE,
    Amount,
    CanonicalEnum,
    CanonicalPart,
    CanonicalRecord,
    Coded,
    DiagnosticCode,
    EntityType,
    MappingBasis,
    Percent,
    Provider,
    Rate,
    SourceRef,
    ValueStatus,
    canonical_id,
    parse_canonical_id,
    sensitive_fields,
    to_json,
)
from normalization.canonical.parsing import (
    DateKind,
    DateRole,
    parse_source_date,
    parse_source_json,
    resolve_date,
    to_decimal,
)


class _Status(CanonicalEnum):
    ACTIVE = "active"
    UNKNOWN = "unknown"


class _Address(CanonicalPart):
    line1: str | None = None
    city: str | None = None


class _Account(CanonicalPart):
    account_number: str | None = Field(default=None, json_schema_extra=SENSITIVE)


class _Person(CanonicalRecord):
    ENTITY: ClassVar[EntityType] = EntityType.EMPLOYEE

    name: str | None = None
    ssn: str | None = Field(default=None, json_schema_extra=SENSITIVE)
    status: Coded[_Status] | None = None
    pay: Amount | None = None
    share: Percent | None = None
    tax_rate: Rate | None = None
    address: _Address | None = None
    accounts: list[_Account] = Field(default_factory=list)


ID = canonical_id(Provider.PRISMHR, "970592", EntityType.EMPLOYEE, "102", "A00024")
SOURCE = SourceRef(endpoint="GET /employee/v1/getEmployee", locator="/employee/0")


def person(**overrides):
    values = {
        "id": ID,
        "provider": Provider.PRISMHR,
        "tenant_id": "970592",
        "source_ids": {"clientId": "102", "employeeId": "A00024"},
        "sources": [SOURCE],
        "name": "Sam",
        "ssn": "123-45-6789",
        "status": Coded[_Status](value=_Status.ACTIVE, raw_code="A", raw_label="Active", basis=MappingBasis.DOCUMENTED),
        "pay": "10.00",
        "share": "1.5",
        "tax_rate": "0.062",
        "address": _Address(line1="1 Main St", city="Springfield"),
    }
    values.update(overrides)
    return _Person(**values)


def omitted(name: str) -> _Person:
    values = person().model_dump()
    del values[name]
    return _Person(**values)


class NullExplanationRuleTests(unittest.TestCase):
    def test_every_null_is_explained_exactly_where_it_is(self):
        """A null needs a field_status entry in its own part (an omitted field counts as null; a
        parent's status does not explain a nested null); a status needs a null, and a field."""
        def nested_null():
            return _Address(line1="x", city=None)
        rejected = (  # build, error
            (lambda: person(ssn=None), "'ssn' is null without a field_status entry"),
            (lambda: omitted("name"), "'name' is null"),
            (lambda: person(field_status={"ssn": ValueStatus.HIDDEN_BY_SOURCE}), "'ssn' has a value but field_status says 'hidden_by_source'"),
            (lambda: person(field_status={"not_a_field": ValueStatus.NOT_PROVIDED}), "unknown field 'not_a_field'"),
            (lambda: person(field_status={"field_status": ValueStatus.NOT_PROVIDED}), "unknown field 'field_status'"),
            (lambda: person(address=nested_null()), "'city' is null without a field_status entry"),
            (lambda: person(field_status={"address": ValueStatus.NOT_PROVIDED}, address=nested_null()), "'city' is null without a field_status entry"),
        )
        for build, error in rejected:
            with self.subTest(error=error):
                with self.assertRaisesRegex(ValidationError, error):
                    build()
        self.assertEqual(person().field_status, {})
        for status in ValueStatus:
            with self.subTest(status=status):
                self.assertEqual(person(ssn=None, field_status={"ssn": status}).field_status, {"ssn": status})
        nested = _Address(line1="1 Main St", city=None, field_status={"city": ValueStatus.NOT_PROVIDED})
        self.assertEqual(person(address=nested).address.field_status, {"city": ValueStatus.NOT_PROVIDED})

    def test_extra_fields_are_rejected(self):
        with self.assertRaises(ValidationError):
            person(nickname="S")

    def test_field_status_serializes_sorted(self):
        record = person(
            ssn=None, name=None, field_status={"ssn": ValueStatus.HIDDEN_BY_SOURCE, "name": ValueStatus.NOT_PROVIDED}
        )
        self.assertEqual(list(record.model_dump(mode="json")["field_status"]), ["name", "ssn"])

    def test_json_round_trip(self):
        record = person(ssn=None, field_status={"ssn": ValueStatus.HIDDEN_BY_SOURCE})
        self.assertEqual(_Person.model_validate_json(record.model_dump_json()), record)

    def test_blank_strings_are_rejected_except_raw_codes(self):
        for build, error in ((lambda: person(name=""), "'name' is a blank string"),
                             (lambda: person(name="   "), "'name' is a blank string"),
                             (lambda: _Address(line1="1 Main St", city=""), "'city' is a blank string"),
                             (lambda: person(source_ids={"clientId": ""}), "")):
            with self.subTest(error=error or "source id"):
                with self.assertRaisesRegex(ValidationError, error):
                    build()
        coded = Coded[_Status](value=_Status.ACTIVE, raw_code="", basis=MappingBasis.DOCUMENTED)
        self.assertEqual(person(status=coded).status.raw_code, "")  # a source may send a blank code

    def test_changes_after_construction_are_validated(self):
        """Assignment is validated at once; an in-place change to a map is caught by to_json."""
        record = person()
        with self.assertRaisesRegex(ValidationError, "'name' is null without a field_status entry"):
            record.name = None
        record = person()
        record.field_status["name"] = ValueStatus.NOT_PROVIDED  # in-place change: not seen at once
        with self.assertRaisesRegex(ValidationError, "'name' has a value but field_status says"):
            to_json(record)
        self.assertEqual(json.loads(to_json(person()))["name"], "Sam")


class RecordIdentityTests(unittest.TestCase):
    def test_id_must_match_provider_tenant_and_entity(self):
        with self.assertRaisesRegex(ValidationError, "does not match provider/tenant_id"):
            person(tenant_id="000000")
        with self.assertRaisesRegex(ValidationError, "does not match provider/tenant_id"):
            person(provider=Provider.ISOLVED)
        wrong_entity = canonical_id(Provider.PRISMHR, "970592", EntityType.PAYCHECK, "102", "1")
        with self.assertRaisesRegex(ValidationError, "is not a employee id"):
            person(id=wrong_entity)

    def test_record_needs_a_source_and_source_ids(self):
        with self.assertRaises(ValidationError):
            person(sources=[])
        with self.assertRaises(ValidationError):
            person(source_ids={})

    def test_sensitive_fields_are_discoverable_including_nested_parts(self):
        # Every record also carries sensitive_provider_extensions (D-040).
        self.assertEqual(sensitive_fields(_Person), ["sensitive_provider_extensions", "ssn", "accounts[].account_number"])
        self.assertEqual(sensitive_fields(_Account), ["account_number"])


class CanonicalIdTests(unittest.TestCase):
    def test_id_is_readable_and_deterministic(self):
        self.assertEqual(ID, "prismhr:970592:employee:102:A00024")
        self.assertEqual(ID, canonical_id(Provider.PRISMHR, "970592", EntityType.EMPLOYEE, "102", "A00024"))

    def test_separator_inside_a_source_id_is_escaped_and_round_trips(self):
        value = canonical_id(Provider.UKG_READY, "833341", EntityType.PAYCHECK, "a:b", "50%")
        self.assertEqual(value, "ukg-ready:833341:paycheck:a%3Ab:50%25")
        parsed = parse_canonical_id(value)
        self.assertEqual(parsed.source_parts, ("a:b", "50%"))
        self.assertIs(parsed.provider, Provider.UKG_READY)

    def test_invalid_ids_are_rejected(self):
        with self.assertRaises(ValueError):
            canonical_id(Provider.ISOLVED, "255938", EntityType.COMPANY)
        with self.assertRaises(ValueError):
            canonical_id(Provider.ISOLVED, "255938", EntityType.COMPANY, "")
        for bad in ("isolved:255938:company", "nope:1:company:2", "isolved:255938:widget:2", "isolved::company:2"):
            with self.assertRaises(ValueError):
                parse_canonical_id(bad)


class CodedValueTests(unittest.TestCase):
    def test_unknown_requires_unmapped_and_vice_versa(self):
        Coded[_Status](value=_Status.UNKNOWN, raw_code="VG", basis=MappingBasis.UNMAPPED)
        with self.assertRaises(ValidationError):
            Coded[_Status](value=_Status.UNKNOWN, raw_code="VG", basis=MappingBasis.INFERRED)
        with self.assertRaises(ValidationError):
            Coded[_Status](value=_Status.ACTIVE, raw_code="A", basis=MappingBasis.UNMAPPED)

    def test_canonical_enums_must_define_unknown(self):
        with self.assertRaisesRegex(TypeError, "must define UNKNOWN"):

            class _NoUnknown(CanonicalEnum):
                ACTIVE = "active"

        with self.assertRaisesRegex(TypeError, "must define UNKNOWN"):

            class _WrongValue(CanonicalEnum):
                UNKNOWN = "other"


class NumberTests(unittest.TestCase):
    def test_amounts_are_exact_and_serialize_as_fixed_point_strings(self):
        """Exact decimals, written as fixed-point strings (never JSON floats); booleans, NaN,
        infinities and text are rejected."""
        cases = [(0.1, "0.1"), (940.0, "940.0"), ("25.0000", "25.0000"), (10, "10"), (1e-7, "0.0000001")]
        for raw, text in cases:
            with self.subTest(raw=raw):
                record = person(pay=raw)
                self.assertEqual(record.model_dump(mode="json")["pay"], text)
                self.assertEqual(json.loads(record.model_dump_json())["pay"], text)
                self.assertEqual(record.pay, Decimal(text))
        for raw in (True, float("nan"), float("inf"), "NaN", "abc"):
            with self.subTest(raw=raw):
                with self.assertRaises(ValidationError):
                    person(pay=raw)

    def test_source_json_keeps_exact_digits_and_rejects_non_finite_constants(self):
        long = "0.12345678901234567890123"
        source = parse_source_json('{"pay": 1.00, "rate": %s, "count": 3}' % long)
        self.assertEqual(str(source["pay"]), "1.00")
        self.assertEqual(str(source["rate"]), long)
        self.assertIs(type(source["count"]), int)
        dumped = person(pay=source["pay"], tax_rate=source["rate"]).model_dump(mode="json")
        self.assertEqual((dumped["pay"], dumped["tax_rate"]), ("1.00", long))
        # The standard parser loses both, which is why sources never go through it.
        self.assertEqual(str(json.loads("1.00")), "1.0")
        self.assertNotEqual(repr(json.loads(long)), long)
        for text in ('{"a": NaN}', '{"a": Infinity}', '{"a": -Infinity}'):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    parse_source_json(text)

    def test_percent_and_rate_scales_are_recorded_in_the_schema(self):
        props = _Person.model_json_schema(mode="serialization")["properties"]
        scales = {name: [s.get("x-scale") for s in props[name]["anyOf"]] for name in ("share", "tax_rate")}
        self.assertEqual(scales, {"share": ["percent", None], "tax_rate": ["fraction", None]})


class ParsingTests(unittest.TestCase):
    def test_source_dates(self):
        """Dates and midnight timestamps read as dates; a local timestamp gives its date and the
        dropped time (D-096); sentinels mark open bounds; blank is empty; an offset, another format,
        an impossible date or a time off the clock raises."""
        cases = [
            ("2025-08-08", DateKind.DATE, date(2025, 8, 8)),
            ("2018-07-15T00:00:00", DateKind.DATE, date(2018, 7, 15)),
            ("2018-07-15T00:00:00.000", DateKind.DATE, date(2018, 7, 15)),
            ("0000-01-01", DateKind.OPEN_START, None),
            ("1900-12-31", DateKind.OPEN_START, None),
            ("2099-12-31", DateKind.OPEN_END, None),
            ("9999-12-31", DateKind.OPEN_END, None),
            ("9999-12-31T00:00:00", DateKind.OPEN_END, None),
            (None, DateKind.EMPTY, None),
            ("", DateKind.EMPTY, None),
            ("  ", DateKind.EMPTY, None),
            ("2018-07-15T13:45:00", DateKind.DATE, date(2018, 7, 15)),
            ("2019-04-01T09:05:12.123", DateKind.DATE, date(2019, 4, 1)),
        ]
        for raw, kind, value in cases:
            with self.subTest(raw=raw):
                parsed = parse_source_date(raw)
                self.assertEqual(parsed.kind, kind)
                if value is not None or kind is DateKind.EMPTY:
                    self.assertEqual(parsed.value, value)
        self.assertEqual(parse_source_date("2019-04-01T09:05:12.123").dropped_time, "09:05:12.123")
        self.assertIsNone(parse_source_date("2018-07-15T00:00:00").dropped_time)
        for raw in ("2018-07-15T13:45:00Z", "2018-07-15T13:45:00+02:00", "07/15/2018", "2018-02-30", 20180715,
                    "2019-04-01T99:99:99", "2019-04-01T24:00:00", "2019-04-01T12:60", "2019-04-01T12:00:60"):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    parse_source_date(raw)

    def test_resolve_date_by_field_role(self):
        nd, na = ValueStatus.NOT_PROVIDED, ValueStatus.NOT_APPLICABLE
        sentinel, unparseable = DiagnosticCode.SENTINEL_DATE, DiagnosticCode.UNPARSEABLE_VALUE
        cases = [
            # (raw, role, expected value, status, diagnostic)
            ("2025-08-08", DateRole.EVENT, date(2025, 8, 8), None, None),
            ("2099-12-31", DateRole.PERIOD_END, None, na, None),  # open-ended deposit
            ("1900-12-31", DateRole.PERIOD_START, None, na, None),  # open start of a profile
            ("9999-12-31", DateRole.EVENT, None, nd, sentinel),  # PrismHR rate effectiveDate
            ("0000-01-01", DateRole.EVENT, None, nd, sentinel),
            ("9999-12-31", DateRole.PERIOD_START, None, nd, sentinel),  # wrong bound
            ("0000-01-01", DateRole.PERIOD_END, None, nd, sentinel),
            (None, DateRole.PERIOD_END, None, nd, None),
            ("", DateRole.EVENT, None, nd, None),
            ("07/15/2018", DateRole.EVENT, None, nd, unparseable),
            ("2018-07-15T13:45:00Z", DateRole.EVENT, None, nd, unparseable),
            ("2018-07-15T13:45:00", DateRole.EVENT, date(2018, 7, 15), None, DiagnosticCode.INFERRED_MAPPING),
            ("2019-04-01T99:99:99", DateRole.EVENT, None, nd, unparseable),  # not a time of day
        ]
        for raw, role, value, status, diagnostic in cases:
            resolved = resolve_date(raw, role)
            self.assertEqual((resolved.value, resolved.status, resolved.diagnostic), (value, status, diagnostic), (raw, role))

    def test_to_decimal(self):
        self.assertEqual(to_decimal(0.1), Decimal("0.1"))
        self.assertEqual(to_decimal(" 51999.00 "), Decimal("51999.00"))
        self.assertEqual(to_decimal(7), Decimal(7))
        self.assertEqual(str(to_decimal(Decimal("1.00"))), "1.00")
        self.assertIsNone(to_decimal(None))
        self.assertIsNone(to_decimal(""))
        for raw in (True, "NaN", "Infinity", float("inf"), "1,000", [1]):
            with self.assertRaises(ValueError, msg=repr(raw)):
                to_decimal(raw)


if __name__ == "__main__":
    unittest.main()
