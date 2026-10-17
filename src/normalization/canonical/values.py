"""Value types shared by every canonical record: numbers, value status and coded values."""
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any, Generic, TypeVar

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, GetJsonSchemaHandler, PlainSerializer, model_validator

UNKNOWN = "unknown"


def _reject_bool(value: Any) -> Any:
    # bool is an int subclass; True must never become Decimal("1").
    if isinstance(value, bool):
        raise ValueError("a boolean is not a number")
    return value


def _fixed_point(value: Decimal) -> str:
    # Decimal's own str() switches to scientific notation for small values ("1E-7").
    return format(value, "f")


# What _fixed_point writes: optional minus sign, digits, optional fraction. Never an exponent.
DECIMAL_STRING_PATTERN = r"^-?\d+(\.\d+)?$"


class _DecimalStringPattern:
    """Adds DECIMAL_STRING_PATTERN to the serialization JSON Schema only (D-058).

    A runtime ``Field(pattern=...)`` cannot be applied to a Decimal, and replacing the schema
    (``WithJsonSchema``) would drop field descriptions and ``x-scale`` on optional fields. This
    hook keeps the generated schema and adds the pattern; validation is unchanged.
    """

    def __get_pydantic_json_schema__(self, core_schema: Any, handler: GetJsonSchemaHandler) -> dict[str, Any]:
        schema = handler(core_schema)
        if handler.mode == "serialization":
            schema = {**handler.resolve_ref_schema(schema), "pattern": DECIMAL_STRING_PATTERN}
        return schema


# Exact decimal number. Parsed from JSON numbers or numeric strings without binary float
# error, rejected if NaN or infinite, written to JSON as a fixed-point string ("940.00").
# Source precision is kept as given; values are compared numerically, never as text.
Number = Annotated[
    Decimal,
    BeforeValidator(_reject_bool),
    Field(allow_inf_nan=False),
    PlainSerializer(_fixed_point, return_type=str, when_used="json"),
    _DecimalStringPattern(),
]
Amount = Annotated[Number, Field(description="Money amount in the record's `currency`.")]
# Percent and Rate are both decimals at runtime; the scale is fixed by the field's type and
# name (`*_percent` vs `*_rate`) and recorded in the schema, so 0.062 is never read as 0.062%.
Percent = Annotated[
    Number,
    Field(description="Percentage on a 0 to 100 scale: 1.5 means 1.5%.", json_schema_extra={"x-scale": "percent"}),
]
Rate = Annotated[
    Number,
    Field(description="Ratio as a fraction: 0.062 means 6.2%.", json_schema_extra={"x-scale": "fraction"}),
]
Hours = Annotated[Number, Field(description="Duration in decimal hours.")]
CurrencyCode = Annotated[str, Field(pattern=r"^[A-Z]{3}$", description="ISO 4217 currency code.")]
# Last characters a provider shows of a value it otherwise masks (D-020). Never the full value.
Last4 = Annotated[str, Field(pattern=r"^.{1,4}$", description="Visible last characters of a masked value (D-020).")]

# Marker for fields that hold sensitive personal or banking data (SSN, account numbers,
# birth date). Read by output layers to mask values by default (D-036).
SENSITIVE: dict[str, Any] = {"x-sensitive": True}


class ValueStatus(StrEnum):
    """Why a field is null. A field holding a value is "present" and is not listed."""

    HIDDEN_BY_SOURCE = "hidden_by_source"  # exists, but the provider masked it
    # No usable value was received: missing key, null, blank, a placeholder such as a sentinel
    # date, an unparseable value, or an unavailable route. Unless the field was simply absent,
    # a diagnostic on the record says which.
    NOT_PROVIDED = "not_provided"
    NOT_APPLICABLE = "not_applicable"  # does not apply (e.g. termination date of an active employee)


class MappingBasis(StrEnum):
    """What a canonical code value rests on."""

    DOCUMENTED = "documented"  # provider spec, lookup reference, or provider code table states the meaning
    EVIDENCED = "evidenced"  # established from provider data (e.g. amounts that reconcile), not stated
    INFERRED = "inferred"  # reasoned from indirect evidence; the record carries an inferred_mapping diagnostic
    CONFIGURED = "configured"  # from a tenant mapping supplied to the pipeline
    UNMAPPED = "unmapped"  # no evidence; the canonical value is unknown


class CanonicalEnum(StrEnum):
    """Base for canonical domain enums. Every subclass must define UNKNOWN = "unknown"."""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        unknown = cls.__members__.get("UNKNOWN")
        if unknown is None or unknown.value != UNKNOWN:
            raise TypeError(f"{cls.__name__} must define UNKNOWN = {UNKNOWN!r}")


E = TypeVar("E", bound=CanonicalEnum)


class Coded(BaseModel, Generic[E]):
    """A provider code translated to a canonical value, with the original code kept.

    ``raw_code`` is the code exactly as sent (an empty string is a real code for some
    providers). ``raw_label`` is the provider's description when it sends one; null means it
    sent only the code. That null is part of this type's meaning, so Coded is a value type
    and is not subject to the field_status rule.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    value: E
    raw_code: str
    raw_label: str | None = None
    basis: MappingBasis

    @model_validator(mode="after")
    def _unknown_iff_unmapped(self) -> "Coded[E]":
        is_unknown = self.value.value == UNKNOWN
        if is_unknown != (self.basis is MappingBasis.UNMAPPED):
            raise ValueError("value 'unknown' and basis 'unmapped' must be used together")
        return self
