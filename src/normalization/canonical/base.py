"""Base classes for canonical records and the null-explanation rule (D-020 amendment).

Rule: every field whose value is null must have an entry in the same object's
``field_status`` map saying why (hidden_by_source, not_provided, not_applicable). A field
that holds a value must not have an entry. Nested parts (an address, a pay line) carry their
own map. Plain string fields never hold a blank string: blank means "no value", so it is
null with a status. Validation rejects any object that breaks these rules.

The rules are checked at construction and on attribute assignment. Changing a mutable value
in place (e.g. ``record.field_status["x"] = ...``) is not seen, so output goes through
``to_json``, which validates again.
"""
import types
from typing import Annotated, Any, ClassVar, Union, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_serializer, model_validator

from .diagnostics import Diagnostic
from .ids import EntityType, Provider, parse_canonical_id
from .values import SENSITIVE, ValueStatus

_STATUS_FIELD = "field_status"


class CanonicalPart(BaseModel):
    """Any canonical object that holds provider data. Enforces the null-explanation rule."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    field_status: dict[str, ValueStatus] = Field(
        default_factory=dict,
        description="Why each null field in this object is null. Lists null fields only.",
    )

    @field_serializer(_STATUS_FIELD)
    def _sorted_status(self, value: dict[str, ValueStatus]) -> dict[str, ValueStatus]:
        return dict(sorted(value.items()))

    @model_validator(mode="after")
    def _explain_nulls(self) -> "CanonicalPart":
        fields = type(self).model_fields
        problems = []
        for name, status in self.field_status.items():
            if name not in fields or name == _STATUS_FIELD:
                problems.append(f"field_status names unknown field {name!r}")
            elif getattr(self, name) is not None:
                problems.append(f"{name!r} has a value but field_status says {status.value!r}")
        for name in fields:
            value = getattr(self, name)
            if value is None and name not in self.field_status:
                problems.append(f"{name!r} is null without a field_status entry")
            elif isinstance(value, str) and value.strip() == "":
                problems.append(f"{name!r} is a blank string; use null with a field_status entry")
        if problems:
            raise ValueError("; ".join(problems))
        return self


class SourceRef(BaseModel):
    """Where a record's data came from.

    ``endpoint`` is the method and route template as documented by the provider, e.g.
    ``GET /api/clients/{clientId}/legals/{legalId}/employees/{employeeId}``. ``locator`` is a
    JSON Pointer to the record inside that response body ("" means the whole body). Together
    with the run's input (the source file, or a retained response) it locates the raw value;
    on its own it does not hold the value.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    endpoint: str = Field(min_length=1)
    locator: str


class CanonicalRecord(CanonicalPart):
    """A top-level canonical entity (company, employee, paycheck, ...)."""

    ENTITY: ClassVar[EntityType | None] = None

    id: str = Field(description="Canonical id: provider:tenant:entity:source ids (see ids.py).")
    provider: Provider
    tenant_id: str = Field(min_length=1)
    source_ids: dict[str, Annotated[str, Field(min_length=1)]] = Field(
        min_length=1,
        description="The provider's own identifiers needed to address this record, by provider field name.",
    )
    sources: list[SourceRef] = Field(min_length=1)
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    provider_extensions: dict[str, JsonValue] = Field(
        default_factory=dict,
        description=(
            "Provider-specific fields with no canonical meaning, keyed by source field path. "
            "Never used for anything the brief lists for the four data types (D-037)."
        ),
    )
    sensitive_provider_extensions: dict[str, JsonValue] = Field(
        default_factory=dict,
        json_schema_extra=SENSITIVE,
        description=(
            "Like provider_extensions, for provider-specific data that is sensitive (e.g. PrismHR "
            "health screening results). Masked as a whole by default in output (D-036)."
        ),
    )

    @model_validator(mode="after")
    def _id_matches_record(self) -> "CanonicalRecord":
        parsed = parse_canonical_id(self.id)
        if parsed.provider != self.provider or parsed.tenant_id != self.tenant_id:
            raise ValueError(f"id {self.id!r} does not match provider/tenant_id of the record")
        if self.ENTITY is not None and parsed.entity != self.ENTITY:
            raise ValueError(f"id {self.id!r} is not a {self.ENTITY.value} id")
        return self

    def check_reference(self, field: str, value: str | None, entity: EntityType) -> str | None:
        """Problem with a canonical id held in ``field``, or None if it is valid.

        A reference must be a well-formed id of the expected entity type from the same
        provider and tenant as this record.
        """
        if value is None:
            return None
        try:
            parsed = parse_canonical_id(value)
        except ValueError:
            return f"{field} {value!r} is not a canonical id"
        if parsed.entity != entity:
            return f"{field} {value!r} is not a {entity.value} id"
        if parsed.provider != self.provider or parsed.tenant_id != self.tenant_id:
            return f"{field} {value!r} belongs to another provider or tenant"
        return None

    def require_references(self, checks: list[tuple[str, str | None, EntityType]]) -> None:
        """Raise ValueError listing every invalid reference among (field, value, entity) checks."""
        problems = [p for p in (self.check_reference(*check) for check in checks) if p]
        if problems:
            raise ValueError("; ".join(problems))


def to_json(part: CanonicalPart) -> str:
    """Validate ``part`` again, then serialize it. Use this for all output."""
    revalidated = type(part).model_validate(part.model_dump())
    return revalidated.model_dump_json()


def _nested_parts(annotation: Any) -> list[tuple[str, type[CanonicalPart]]]:
    """CanonicalPart types inside an annotation, with "[]" when reached through a list."""
    if isinstance(annotation, type) and issubclass(annotation, CanonicalPart):
        return [("", annotation)]
    origin = get_origin(annotation)
    found = []
    for arg in get_args(annotation):
        for suffix, part in _nested_parts(arg):
            in_list = origin in (list, tuple, set, frozenset)
            found.append((("[]" if in_list else "") + suffix, part))
    if origin not in (Union, types.UnionType, Annotated, list, tuple, set, frozenset, None):
        return []  # dicts and other containers are not walked
    return found


def sensitive_fields(model: type[BaseModel], _prefix: str = "") -> list[str]:
    """Paths of fields marked SENSITIVE in ``model`` and its nested parts.

    Nested paths use dots, and "[]" for list items: ``deposits[].account_number``.
    """
    paths = []
    for name, info in model.model_fields.items():
        extra = info.json_schema_extra
        if isinstance(extra, dict) and extra.get("x-sensitive"):
            paths.append(_prefix + name)
        for suffix, part in _nested_parts(info.annotation):
            paths += sensitive_fields(part, f"{_prefix}{name}{suffix}.")
    return paths
