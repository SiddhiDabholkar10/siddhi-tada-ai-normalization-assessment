"""Source value parsing shared by all adapters (JSON, numbers and dates, D-025, D-036).

``parse_source_json`` is the only way provider JSON is read, so numbers keep their exact
digits. ``resolve_date`` applies the sentinel rule by field role: an open end on a deposit is
normal, but a sentinel where a real date is required is a placeholder.
"""
import json
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any

from .diagnostics import DiagnosticCode
from .values import ValueStatus


def _reject_constant(name: str) -> Any:
    raise ValueError(f"non-finite number {name} in source JSON")


def parse_source_json(text: str) -> Any:
    """Parse provider JSON with every decimal number as an exact Decimal.

    The standard parser turns 1.00 into the float 1.0 and cuts long decimals before any
    adapter sees them. Integers stay int. NaN and Infinity (accepted by Python's parser,
    not valid JSON) are rejected.
    """
    return json.loads(text, parse_float=Decimal, parse_constant=_reject_constant)

# Placeholder dates seen in provider data: PrismHR pay rate history (0000-01-01, 9999-12-31),
# UKG profiles, compensation and deposits (1900-12-31, 2099-12-31), UKG doc samples (9999-12-31).
OPEN_START_SENTINELS = frozenset({"0000-01-01", "1900-12-31"})
OPEN_END_SENTINELS = frozenset({"2099-12-31", "9999-12-31"})

# Date-only values, optionally with a midnight time and no offset (isolved "2018-07-15T00:00:00").
_DATE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:T00:00(?::00(?:\.0+)?)?)?$")
# A time of day with no offset (live isolved: 24 of 138 employees' hire and status dates, D-096):
# the calendar date is the date part, as no time zone conversion applies. With an offset, no.
# The time must be on the clock (hour 00 to 23, minute and second 00 to 59): "T99:99:99" is unparseable.
_LOCAL_TIMESTAMP = re.compile(r"^(\d{4}-\d{2}-\d{2})T((?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d(?:\.\d+)?)?)$")


class DateKind(StrEnum):
    DATE = "date"  # a real calendar date
    EMPTY = "empty"  # null or blank
    OPEN_START = "open_start"  # start sentinel: "no known start"
    OPEN_END = "open_end"  # end sentinel: "no end"


@dataclass(frozen=True)
class ParsedDate:
    value: date | None
    kind: DateKind
    dropped_time: str | None = None  # the time of day of a local timestamp read as its date (D-096)


def parse_source_date(raw: Any) -> ParsedDate:
    """Parse a provider date-only value. Raises ValueError for anything else.

    A timestamp with a time of day and no offset gives its date part, never silently: the dropped
    time is returned in ``dropped_time`` and reported by the caller (D-096). A timestamp with an
    offset or ``Z`` raises, because its calendar date depends on a time zone.
    """
    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        return ParsedDate(None, DateKind.EMPTY)
    if not isinstance(raw, str):
        raise ValueError(f"expected a date string, got {type(raw).__name__}")
    match = _DATE.match(raw.strip())
    timestamp = None if match else _LOCAL_TIMESTAMP.match(raw.strip())
    if not match and not timestamp:
        raise ValueError(f"not a date-only value: {raw!r}")
    text = (match or timestamp).group(1)
    if text in OPEN_START_SENTINELS:
        return ParsedDate(None, DateKind.OPEN_START)
    if text in OPEN_END_SENTINELS:
        return ParsedDate(None, DateKind.OPEN_END)
    return ParsedDate(date.fromisoformat(text), DateKind.DATE, timestamp.group(2) if timestamp else None)


class DateRole(StrEnum):
    """What a date field means, which decides how a sentinel is read. Set per field in the
    mapping tables."""

    EVENT = "event"  # when something happened or takes effect (hire, pay, rate change): must be real
    PERIOD_START = "period_start"  # start of a validity period that may be open (deposit active_from)
    PERIOD_END = "period_end"  # end of a validity period that may be open (deposit active_to)


@dataclass(frozen=True)
class ResolvedDate:
    """A canonical date, or why there is none. ``status`` is set exactly when ``value`` is null;
    ``diagnostic`` is set when the reason is more than "not sent", or when a value was read from
    a local timestamp (inferred_mapping, ``dropped_time`` names the time of day, D-096)."""

    value: date | None
    status: ValueStatus | None
    diagnostic: DiagnosticCode | None
    dropped_time: str | None = None


def resolve_date(raw: Any, role: DateRole) -> ResolvedDate:
    """Apply the D-025 / D-036 date rule for a field with the given role.

    - real date: the date. From a local timestamp: its date, with inferred_mapping (D-096).
    - null or blank: not_provided. (An adapter that knows the field cannot apply, e.g. the
      termination date of an active employee, uses not_applicable instead.)
    - open start sentinel in a period start, open end sentinel in a period end: an unbounded
      period, so not_applicable.
    - any other sentinel (in an event date, or the wrong bound): a placeholder, so not_provided
      with a sentinel_date diagnostic.
    - unparseable: not_provided with an unparseable_value diagnostic.
    """
    try:
        parsed = parse_source_date(raw)
    except ValueError:
        return ResolvedDate(None, ValueStatus.NOT_PROVIDED, DiagnosticCode.UNPARSEABLE_VALUE)
    if parsed.kind is DateKind.DATE:
        if parsed.dropped_time is not None:
            return ResolvedDate(parsed.value, None, DiagnosticCode.INFERRED_MAPPING, parsed.dropped_time)
        return ResolvedDate(parsed.value, None, None)
    if parsed.kind is DateKind.EMPTY:
        return ResolvedDate(None, ValueStatus.NOT_PROVIDED, None)
    open_bound = (parsed.kind is DateKind.OPEN_START and role is DateRole.PERIOD_START) or (
        parsed.kind is DateKind.OPEN_END and role is DateRole.PERIOD_END
    )
    if open_bound:
        return ResolvedDate(None, ValueStatus.NOT_APPLICABLE, None)
    return ResolvedDate(None, ValueStatus.NOT_PROVIDED, DiagnosticCode.SENTINEL_DATE)


def to_decimal(raw: Any) -> Decimal | None:
    """Exact Decimal from a JSON number or numeric string. Null or blank gives None.

    Floats go through their shortest repr, so 0.1 becomes Decimal("0.1"), not the binary
    approximation. Booleans, NaN and infinities raise ValueError.
    """
    if raw is None:
        return None
    if isinstance(raw, bool):
        raise ValueError("a boolean is not a number")
    if isinstance(raw, str):
        raw = raw.strip()
        if raw == "":
            return None
    try:
        value = Decimal(repr(raw)) if isinstance(raw, float) else Decimal(raw)
    except (InvalidOperation, TypeError) as exc:
        raise ValueError(f"not a number: {raw!r}") from exc
    if not value.is_finite():
        raise ValueError(f"not a finite number: {raw!r}")
    return value
