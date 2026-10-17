"""Canonical field paths such as ``Paycheck.earnings[].hours`` (used by docs/COVERAGE.md and the
mapping tables, D-059, D-061)."""
import types
from typing import Annotated, Union, get_args, get_origin

from .base import CanonicalPart
from .schema_export import SCHEMA_FILES

RECORDS = {model.__name__: model for model in SCHEMA_FILES.values()}


def field_shape(annotation) -> tuple[bool, type[CanonicalPart] | None]:
    """(is a list, nested part model or None) for a field annotation, looking through Optional.
    Value types (Coded, Diagnostic, SourceRef) are not parts: their subfields are not homes."""
    if isinstance(annotation, type) and issubclass(annotation, CanonicalPart):
        return False, annotation
    origin = get_origin(annotation)
    if origin is list:
        return True, field_shape(get_args(annotation)[0])[1]
    if origin in (Union, types.UnionType, Annotated):
        for arg in get_args(annotation):
            if arg is not type(None):
                shape = field_shape(arg)
                if shape != (False, None):
                    return shape
    return False, None


def path_exists(token: str) -> bool:
    """True if ``Record.field.sub[]...`` names a field of a canonical record.

    ``[]`` is allowed only on a list field, a list's items are reached only through ``[]``, and
    a field holding a plain value (not a part) must be the last segment.
    """
    record, _, path = token.partition(".")
    model = RECORDS.get(record)
    if model is None:
        return False
    parts = path.split(".") if path else []
    for index, part in enumerate(parts):
        name, brackets = (part[:-2], True) if part.endswith("[]") else (part, False)
        if model is None or name not in model.model_fields:
            return False
        is_list, nested = field_shape(model.model_fields[name].annotation)
        last = index == len(parts) - 1
        if brackets and not is_list:
            return False
        if not last and (nested is None or (is_list and not brackets)):
            return False
        model = nested
    return True
