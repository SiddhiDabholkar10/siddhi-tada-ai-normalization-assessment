"""Helpers shared by the employee adapters.

``Ctx`` collects what one record gathers while it is built (diagnostics, extensions) and applies
the shared value rules: blank is not provided (D-020 amendment 2), dates by role with sentinels
(D-025), exact numbers (D-036), coded values from the provider's code tables (D-061), masked
values (D-020). ``build`` turns keyword values into a canonical part and writes the
``field_status`` entry of every null field.
"""
import re
from collections.abc import Iterable
from datetime import date
from decimal import Decimal, Inexact, localcontext
from functools import cache
from typing import Any

from ..canonical.base import CanonicalPart
from ..canonical.diagnostics import Diagnostic, DiagnosticCode, Severity
from ..canonical.parsing import DateRole, resolve_date, to_decimal
from ..canonical.values import UNKNOWN, MappingBasis, ValueStatus
from ..mappings.tables import code_tables, load_tables


HOUR_MS = Decimal(3_600_000)
HOURS_QUANTUM = Decimal("0.0000001")  # 7 decimal places of an hour (D-091)


class Null:
    """A null with its reason. Adapters return it where a value is missing."""

    __slots__ = ("status",)

    def __init__(self, status: ValueStatus) -> None:
        self.status = status

    def __repr__(self) -> str:
        return f"Null({self.status.value})"


NP = Null(ValueStatus.NOT_PROVIDED)
NA = Null(ValueStatus.NOT_APPLICABLE)
HIDDEN = Null(ValueStatus.HIDDEN_BY_SOURCE)


def build(model: type[CanonicalPart], **fields: Any) -> CanonicalPart:
    """Build ``model`` from ``fields``. A field given as None or NP is not_provided, NA
    not_applicable, HIDDEN hidden_by_source; a nullable field not given at all is not_provided.
    Fields with a non-null default (lists of diagnostics, extensions) keep their default."""
    values: dict[str, Any] = {}
    status: dict[str, ValueStatus] = {}
    for name, info in model.model_fields.items():
        if name == "field_status":
            continue
        if name not in fields:
            if info.is_required() or info.default is not None or info.default_factory is not None:
                continue
            status[name] = ValueStatus.NOT_PROVIDED
            continue
        value = fields.pop(name)
        if value is None:
            status[name] = ValueStatus.NOT_PROVIDED
        elif isinstance(value, Null):
            status[name] = value.status
        else:
            values[name] = value
    if fields:
        raise TypeError(f"{model.__name__} has no fields {sorted(fields)}")
    return model(**values, field_status=status)


def value_of(item: Any) -> Any:
    """The value of a helper result, or None for a Null."""
    return None if isinstance(item, Null) else item


def is_blank(raw: Any) -> bool:
    return raw is None or (isinstance(raw, str) and raw.strip() == "")


# A provider mask: runs of '*' or the word REDACTED (D-020). A real identifier, date or phone
# number never contains either.
_MASK = re.compile(r"\*|REDACTED", re.IGNORECASE)
# Client-defined employment type labels that say full or part time in so many words, at the start
# ('Full Time', 'FT Non-Exempt', 'PT Hourly'); 'FTE', 'Seasonal' or 'Consultant' say nothing (D-099).
_TYPE_LABELS = (
    (re.compile(r"(?:ft|full[\s-]?time)\b", re.IGNORECASE), "full_time"),
    (re.compile(r"(?:pt|part[\s-]?time)\b", re.IGNORECASE), "part_time"),
)


def is_masked(raw: Any) -> bool:
    return isinstance(raw, str) and bool(_MASK.search(raw))


def visible_last4(raw: str) -> str | None:
    """The characters a mask leaves visible at the end (``***-**-6789`` gives ``6789``),
    at most 4, or None when nothing is visible (``***-**-****``)."""
    tail = re.split(r"\*|REDACTED", raw, flags=re.IGNORECASE)[-1]
    visible = re.sub(r"[^0-9A-Za-z]", "", tail)
    return visible[-4:] or None


def json_leaf(value: Any) -> Any:
    """A source value as kept in an extension: Decimals become exact fixed-point strings,
    as canonical numbers do (D-036)."""
    if isinstance(value, Decimal):
        return format(value, "f")
    return value


@cache
def _tables(provider: str) -> dict[str, dict]:
    return code_tables(load_tables(provider))


def code_entry(provider: str, table_id: str, raw: str) -> dict | None:
    """The code table row for ``raw``, or None when the table does not list it."""
    for code in _tables(provider)[table_id]["codes"]:
        if code["raw"] == raw:
            return code
    return None


def join_key(key: str, name: str) -> str:
    """``key`` plus one object key: ``route:`` (a response root) takes no dot."""
    return f"{key}{name}" if key.endswith(":") else f"{key}.{name}"


class Ctx:
    """State of one record being built. ``provider`` selects the code tables."""

    def __init__(self, provider: str) -> None:
        self.provider = provider
        self.diagnostics: list[Diagnostic] = []
        self.extensions: dict[str, Any] = {}
        self.sensitive_extensions: dict[str, Any] = {}

    # ---- diagnostics -------------------------------------------------------------------

    def diag(
        self, code: DiagnosticCode, severity: Severity, message: str, field: str | None = None, evidence: str | None = None
    ) -> None:
        item = Diagnostic(code=code, severity=severity, message=message, field=field, evidence=evidence)
        if item not in self.diagnostics:
            self.diagnostics.append(item)

    def unavailable(self, field: str, message: str, evidence: str | None = None) -> Null:
        self.diag(DiagnosticCode.SOURCE_UNAVAILABLE, Severity.WARNING, message, field, evidence)
        return NP

    # ---- extensions --------------------------------------------------------------------

    def keep(self, key: str, value: Any, sensitive: bool = False) -> None:
        """Keep a source value in provider_extensions (or the sensitive extension), one entry per
        leaf, keyed ``<route>:<path from the response root>``. Null, blank and empty values carry
        nothing and are skipped; the input file still holds them (CANONICAL_MODEL 1.11)."""
        target = self.sensitive_extensions if sensitive else self.extensions
        if isinstance(value, dict):
            for name, item in value.items():
                self.keep(join_key(key, name), item, sensitive)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                self.keep(f"{key}[{index}]", item, sensitive)
        elif not is_blank(value):
            target[key] = json_leaf(value)

    def rest(
        self,
        key: str,
        obj: Any,
        handled: Iterable[str] = (),
        sensitive: Iterable[str] = (),
        excluded: Iterable[str] = (),
        all_sensitive: bool = False,
    ) -> None:
        """Keep the keys of ``obj`` not in ``handled`` or ``excluded``: those in ``sensitive`` (or
        all of them with ``all_sensitive``) in the sensitive extension, the others in
        provider_extensions."""
        if not isinstance(obj, dict):
            return
        skip, secret = set(handled) | set(excluded), set(sensitive)
        for name, value in obj.items():
            if name not in skip:
                self.keep(join_key(key, name), value, all_sensitive or name in secret)

    # ---- values ------------------------------------------------------------------------

    def text(self, raw: Any, field: str | None = None, sensitive: bool = False) -> Any:
        """A string as sent, trimmed; blank is not provided. A masked value in a sensitive field
        is hidden_by_source with value_redacted_in_source (D-020)."""
        if is_blank(raw):
            return NP
        if sensitive and is_masked(raw):
            return self.redacted(field)
        return raw.strip() if isinstance(raw, str) else str(raw)

    def redacted(self, field: str | None) -> Null:
        self.diag(
            DiagnosticCode.VALUE_REDACTED_IN_SOURCE,
            Severity.INFO,
            "The provider masked this value; it is not stored (D-020).",
            field,
            "D-020",
        )
        return HIDDEN

    def date(self, raw: Any, role: DateRole, field: str, blank: Null = NP) -> Any:
        """A date by role (CANONICAL_MODEL 1.6). ``blank`` is the status of a missing value."""
        if is_masked(raw):
            return self.redacted(field)
        resolved = resolve_date(raw, role)
        if resolved.value is not None:
            if resolved.dropped_time is not None:
                # Only the time is named: diagnostics are never masked, and a date may be sensitive.
                self.diag(DiagnosticCode.INFERRED_MAPPING, Severity.INFO,
                          f"Date part of a timestamp with no time zone; time of day {resolved.dropped_time} dropped.", field, "D-096")
            return resolved.value
        if resolved.diagnostic is DiagnosticCode.SENTINEL_DATE:
            self.diag(resolved.diagnostic, Severity.WARNING, f"Placeholder date {raw!r} where a real date is required.", field, "D-025")
        elif resolved.diagnostic is DiagnosticCode.UNPARSEABLE_VALUE:
            self.diag(resolved.diagnostic, Severity.ERROR, "Value is not a date-only value.", field)
        elif is_blank(raw):
            return blank
        return Null(resolved.status)

    def number(self, raw: Any, field: str) -> Any:
        try:
            value = to_decimal(raw)
        except ValueError:
            self.diag(DiagnosticCode.UNPARSEABLE_VALUE, Severity.ERROR, "Value is not a number.", field)
            return NP
        return NP if value is None else value

    def integer(self, raw: Any, field: str) -> Any:
        value = self.number(raw, field)
        if isinstance(value, Null):
            return value
        if value != value.to_integral_value():
            self.diag(DiagnosticCode.UNPARSEABLE_VALUE, Severity.ERROR, "Value is not a whole number.", field)
            return NP
        return int(value)

    def flag(self, raw: Any, field: str, true: str = "Y", false: str = "N") -> Any:
        """A boolean, or a provider flag letter (``Y``/``N``). Blank is not provided."""
        if isinstance(raw, bool):
            return raw
        if is_blank(raw):
            return NP
        if isinstance(raw, str) and raw.strip().upper() == true:
            return True
        if isinstance(raw, str) and raw.strip().upper() == false:
            return False
        self.diag(DiagnosticCode.UNPARSEABLE_VALUE, Severity.ERROR, "Value is not a recognized yes or no flag.", field)
        return NP

    def ms_to_hours(self, raw: Any, field: str) -> Any:
        """UKG milliseconds to decimal hours (D-028, D-091): divided by 3,600,000, exact when the
        division ends, else rounded to 7 decimal places (0.36 ms, finer than the contract's integer
        milliseconds, so hours x 3,600,000 rounded gives the source value back)."""
        value = self.number(raw, field)
        if isinstance(value, Null):
            return value
        if not value:
            return Decimal("0")
        with localcontext() as context:
            context.prec = 60
            context.traps[Inexact] = True
            try:
                return (value / HOUR_MS).normalize()
            except Inexact:
                context.traps[Inexact] = False
                return (value / HOUR_MS).quantize(HOURS_QUANTUM).normalize()

    def coded(
        self,
        table: str,
        raw: Any,
        field: str,
        label: Any = None,
        column: str = "value",
        sensitive: bool = False,
        raw_code: Any = None,
    ) -> Any:
        """A coded value from a code table (CANONICAL_MODEL 1.7). ``raw`` is looked up;
        ``raw_code`` (default ``raw``) is what the record keeps, for codes whose value comes from
        another field (PrismHR status code vs status class). A code the table does not list is
        unknown with an unknown_code diagnostic. Messages of sensitive fields do not name the code."""
        if isinstance(raw, bool):
            raw = "true" if raw else "false"
        if is_blank(raw):
            return NP
        raw = str(raw).strip()
        kept = raw if raw_code is None else str(raw_code)
        entry = code_entry(self.provider, table, raw)
        mapping = entry.get(column) if entry else None
        value, basis = (mapping["value"], mapping["basis"]) if mapping else (UNKNOWN, MappingBasis.UNMAPPED.value)
        label_text = value_of(self.text(label)) if label is not None else None
        named = "The provider code" if sensitive else f"Provider code {raw!r}"
        if basis == MappingBasis.UNMAPPED.value:
            listed = "listed without a canonical value" if entry else "not in the code table"
            self.diag(DiagnosticCode.UNKNOWN_CODE, Severity.WARNING, f"{named} is {listed}; value unknown.", field, table)
        elif basis == MappingBasis.INFERRED.value:
            self.diag(DiagnosticCode.INFERRED_MAPPING, Severity.INFO, f"{named} has an inferred canonical value.", field, table)
        return {"value": value, "raw_code": kept, "raw_label": label_text, "basis": basis}

    def client_type(self, raw: Any, field: str, label: Any = None, table: str | None = None) -> Any:
        """A client-defined employment type (D-074 amended by D-099). When the type's own label
        says full time or part time in so many words ('Full Time', 'FT Exempt', 'PT Hourly'), that
        is the value, inferred, with a diagnostic naming the label. Any other label says nothing:
        the code goes to ``table`` when given, else it is unknown (D-074)."""
        label_text = value_of(self.text(label)) if label is not None else None
        reading = next((value for pattern, value in _TYPE_LABELS if label_text and pattern.match(label_text)), None)
        if is_blank(raw) or reading is None:
            return self.coded(table, raw, field, label) if table else self.unknown(raw, field, label)
        raw = str(raw).strip()
        self.diag(DiagnosticCode.INFERRED_MAPPING, Severity.INFO,
                  f"Client-defined code {raw!r} is read from its label {label_text!r} as {reading}.", field, "D-099")
        return {"value": reading, "raw_code": raw, "raw_label": label_text, "basis": MappingBasis.INFERRED.value}

    def unknown(self, raw: Any, field: str, label: Any = None, sensitive: bool = False, evidence: str = "D-074") -> Any:
        """A client-defined code with no canonical reading: unknown with the raw code (D-074)."""
        if is_blank(raw):
            return NP
        named = "A client-defined code" if sensitive else f"Client-defined code {str(raw).strip()!r}"
        self.diag(DiagnosticCode.UNKNOWN_CODE, Severity.WARNING, f"{named} has no documented meaning; value unknown.", field, evidence)
        label_text = value_of(self.text(label)) if label is not None else None
        return {"value": UNKNOWN, "raw_code": str(raw).strip(), "raw_label": label_text, "basis": MappingBasis.UNMAPPED.value}

    def national_id(self, model: type[CanonicalPart], raw: Any, id_type: dict, field: str, **extra: Any) -> Any:
        """A national id: full value when sent, else hidden_by_source with the visible last
        characters in value_last4 (D-020). Blank: no id (not provided)."""
        if is_blank(raw):
            return NP
        if is_masked(raw):
            self.redacted(f"{field}.value")
            return build(model, type=id_type, value=HIDDEN, value_last4=visible_last4(raw) or NP, **extra)
        return build(model, type=id_type, value=str(raw).strip(), value_last4=NA, **extra)


def from_sources(items: list, sources: list) -> Any:
    """A list built from several routes. When a route was unavailable (None) and the others gave
    nothing, the list is not known to be empty: not provided, not []. The record already carries
    the source_unavailable diagnostic. Items found are kept even when another route failed."""
    if not items and any(source is None for source in sources):
        return NP
    return items


def latest(items: list[dict], key: str) -> dict | None:
    """The item with the greatest ``key`` (ISO dates compare as text); ties keep the first."""
    best = None
    for item in items:
        if not is_blank(item.get(key)) and (best is None or str(item[key]) > str(best[key])):
            best = item
    return best


def iso(value: Any) -> date | None:
    return value if isinstance(value, date) else None
