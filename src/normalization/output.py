"""Output layer: canonical records to JSON, sensitive values masked by default (D-036, D-080, D-085).

Every record goes through ``to_json`` (validated again before it is written), then every path
``sensitive_fields`` lists for its model is masked unless the caller opts in. Masking keeps the
structure: object keys, nulls and the ``field_status`` maps of canonical parts stay, so a reader can
still tell a masked value from one that was hidden by the provider or not sent. Raw source JSON
(``sensitive_provider_extensions``) has no such map: every leaf in it is masked, whatever its key.
National id values keep their last 4 characters (``***6789``); every other sensitive value
becomes ``***``.

Masked output is a view for people, not a canonical record: ``***`` is not a date, so it is not
expected to validate against the exported schemas. The records themselves keep full values.
"""
import json
import re
from collections.abc import Iterable
from typing import Any

from pydantic.fields import FieldInfo

from .canonical.base import CanonicalPart, CanonicalRecord, _nested_parts, sensitive_fields, to_json
from .pipeline import TABLE_LISTS, RunResult

MASK = "***"
_STATUS_KEY = "field_status"


def is_id_path(path: str) -> bool:
    """National id values, which are masked to their last 4 characters."""
    return path.endswith(("national_ids[].value", "national_id.value"))


def _part_of(info: FieldInfo | None) -> type[CanonicalPart] | None:
    """The canonical part type a field holds (alone or in a list), or None for raw JSON, scalars
    and fields that could hold several part types."""
    parts = {part for _, part in _nested_parts(info.annotation)} if info is not None else set()
    return parts.pop() if len(parts) == 1 else None


def _mask_value(value: Any, last4: bool, part: type[CanonicalPart] | None = None) -> Any:
    """``value`` with every leaf masked. Only when ``part`` says the value is a canonical part does
    its ``field_status`` map stay; in raw JSON a key of that name is source data like any other."""
    if value is None:
        return None
    if isinstance(value, dict):
        fields = part.model_fields if part is not None else {}
        return {
            key: item if part is not None and key == _STATUS_KEY else _mask_value(item, False, _part_of(fields.get(key)))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_mask_value(item, last4, part) for item in value]
    if last4 and isinstance(value, str):
        visible = re.sub(r"[^0-9A-Za-z]", "", value)[-4:]
        return MASK + visible if len(visible) == 4 else MASK
    return MASK


def _mask_path(node: Any, parts: list[str], last4: bool, model: type[CanonicalPart] | None) -> None:
    """Mask the value at ``parts`` (``name`` or ``name[]`` segments) inside ``node``, in place.
    ``model`` is the canonical type of ``node`` (None: treat everything below as raw JSON)."""
    if not parts or not isinstance(node, dict):
        return
    head, rest = parts[0], parts[1:]
    in_list = head.endswith("[]")
    name = head[:-2] if in_list else head
    if name not in node or node[name] is None:
        return
    targets = node[name] if in_list else [node[name]]
    if in_list and not isinstance(targets, list):
        return
    part = _part_of(model.model_fields.get(name)) if model is not None else None
    if not rest:
        node[name] = _mask_value(node[name], last4, part)
        return
    for item in targets:
        _mask_path(item, rest, last4, part)


def mask_record(data: dict, paths: Iterable[str], model: type[CanonicalPart] | None = None) -> dict:
    """``data`` (a record of type ``model`` as JSON) with every value at ``paths`` masked. Paths
    use dots, and ``[]`` for list items, as ``sensitive_fields`` writes them. Without ``model``
    every masked value is treated as raw JSON (no ``field_status`` map kept)."""
    masked = json.loads(json.dumps(data))
    # Longest paths first is not needed: a masked parent leaves only "***" leaves below it.
    for path in paths:
        _mask_path(masked, path.split("."), is_id_path(path), model)
    return masked


def record_json(record: CanonicalRecord, show_sensitive: bool = False) -> dict:
    """One record as JSON data: validated by ``to_json``, masked unless ``show_sensitive``."""
    data = json.loads(to_json(record))
    return data if show_sensitive else mask_record(data, sensitive_fields(type(record)), type(record))


def run_header(result: RunResult, input_name: str | None, show_sensitive: bool = False) -> dict[str, Any]:
    """The ``run`` block of a document: what was normalized, counts and problems, no records."""
    return {
        "provider": result.provider,
        "tenant_id": result.tenant_id,
        "input": input_name,
        "sensitive_values": "shown" if show_sensitive else "masked",
        "counts": {name: len(items) for name, items in result.records.items()},
        "not_normalized": result.not_normalized,
        "unusable_responses": result.unusable_responses,
        "link_problems": result.link_problems,
    }


def build_document(
    result: RunResult, input_name: str | None, show_sensitive: bool = False, entities: Iterable[str] | None = None
) -> dict[str, Any]:
    """The output document of one run as JSON data (D-085): ``run``, then one list per record
    type (``companies``, ``employees``, ... ``paychecks``) in id order.

    Every record is validated by ``to_json`` and the whole document is built before anything is
    returned, so a caller that writes the result never writes part of a run. A record that fails
    raises ValueError naming its id. No time is written: the same input gives the same bytes.

    ``entities`` (mapping table names, e.g. ``employee``, ``payroll``) keeps only their lists in
    the document (D-087); ``run.entity_filter`` then names them. Counts and link problems still
    describe the whole run, and every record is still validated."""
    lists: dict[str, list[dict]] = {}
    for name, records in result.records.items():
        lists[name] = []
        for record in records:
            try:
                lists[name].append(record_json(record, show_sensitive))
            except ValueError as exc:  # pydantic ValidationError included
                raise ValueError(f"{record.id}: record failed validation, nothing written\n{exc}") from exc
    run = run_header(result, input_name, show_sensitive)
    if entities:
        chosen = list(dict.fromkeys(entities))
        unknown = [name for name in chosen if name not in TABLE_LISTS]
        if unknown:
            raise ValueError(f"unknown entity {', '.join(unknown)}; choose from {', '.join(TABLE_LISTS)}")
        run["entity_filter"] = [name for name in TABLE_LISTS if name in chosen]
        shown = {list_name for name in chosen for list_name in TABLE_LISTS[name]}
        lists = {name: items for name, items in lists.items() if name in shown}
    return {"run": run, **lists}


def document_text(document: dict[str, Any]) -> str:
    """The document as the text the CLI writes."""
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def render_run(result: RunResult, input_name: str | None, show_sensitive: bool = False, entities: Iterable[str] | None = None) -> str:
    """``build_document`` as text."""
    return document_text(build_document(result, input_name, show_sensitive, entities))
