"""Check fixture responses against the documented response schemas in contracts/ (D-080).

Each response body is validated (JSON Schema draft 4, which the three references use or are
close to) against the 200 schema of its documented route, with three adjustments, each for
behavior the live services show and the mapping tables cover:

1. Null is accepted for any property: the live services send null for unset fields (isolved
   ``disabled``, UKG ``emergency_notif``), and the specs do not mark them nullable.
2. Live wrapper renames (``routes.json`` ``live_renames``, D-062) are mapped back to the
   documented key before validation, so the renamed block is checked against its schema.
3. A property the schema does not allow is accepted only when the provider's mapping table has
   a ``live_only`` row for it on that route (seen live, not documented).
4. ``DEVIATIONS`` lists documented constraints that live data breaks, each with its evidence;
   only those exact (route, field, keyword) errors are accepted. ``EMPTY_LIST_BODIES`` lists
   routes whose live "nothing found" body is ``[]`` against a documented object; only that exact
   body is accepted.
"""
import copy
import re
from functools import cache
from typing import Any

from jsonschema import Draft4Validator

from ..mappings.spec import body_fields, documented_fields, documented_routes
from ..mappings.tables import apply_live_renames, documented_below, load_routes, load_tables, row_routes

# (provider, route, field pattern, JSON Schema keyword): reason.
DEVIATIONS: dict[tuple[str, str, str, str], str] = {
    ("isolved", "/api/clients/{clientId}/legals/{legalId}/employees", r"results\[\d+\]\.maritalStatus", "maxLength"): (
        "Documented maxLength 1, but the live list sends labels ('Single', 'Married'); the code table maps the labels."
    ),
    ("isolved", "/api/clients/{clientId}/legals/{legalId}/employeesWithSSN", r"results\[\d+\]\.maritalStatus", "maxLength"): (
        "Same model as the list (see the list entry)."
    ),
    ("isolved", "/api/clients/{clientId}/legals/{legalId}/employees/{id}", r"maritalStatus", "maxLength"): (
        "Same model as the list (see the list entry)."
    ),
}
# (provider, route): reason. Only the exact body [] is accepted; any other list still fails.
EMPTY_LIST_BODIES: dict[tuple[str, str], str] = {
    ("isolved", "/api/clients/{clientId}/legals/{legalId}/employees/{employeeId}/checks/{id}"): (
        "Documented as one CheckModel object, but a call that finds no check returns an empty list (1 of 27 live detail "
        "responses); the payroll table excludes that body (row '[]')."
    ),
}


def _nullable(node: Any) -> Any:
    """A copy of a schema in which every typed node also accepts null."""
    if isinstance(node, dict):
        out = {key: _nullable(value) for key, value in node.items()}
        kind = out.get("type")
        if isinstance(kind, str) and kind != "null":
            out["type"] = [kind, "null"]
        elif isinstance(kind, list) and "null" not in kind:
            out["type"] = [*kind, "null"]
        if "enum" in out and None not in out["enum"]:
            out["enum"] = [*out["enum"], None]
        return out
    if isinstance(node, list):
        return [_nullable(item) for item in node]
    return node


@cache
def _nullable_definitions(provider: str, route: str) -> dict:
    """Shared definitions (OpenAPI components, Swagger definitions) of a spec, made nullable once
    per provider; UKG schemas are self-contained."""
    doc = documented_routes(provider)[route]
    return {key: _nullable(value) for key, value in doc.definitions.items() if key in ("components", "definitions")}


@cache
def _validator(provider: str, route: str) -> Draft4Validator | None:
    doc = documented_routes(provider)[route]
    if doc.schema is None:
        return None
    first_route = next(iter(documented_routes(provider))) if provider != "ukg-ready" else route
    return Draft4Validator({**_nullable(copy.deepcopy(doc.schema)), **_nullable_definitions(provider, first_route)})


def _documented_names(provider: str, route: str, body: Any) -> Any:
    """``body`` with live renamed top-level keys changed back to their documented names."""
    renames = {}
    for entry in load_routes(provider).get("selected", []):
        if entry["route"] == route:
            renames = entry.get("live_renames", {})
    if not renames or not isinstance(body, dict):
        return body
    out = dict(body)
    for documented, live in renames.items():
        if live in out and documented not in out:
            out[documented] = out.pop(live)
    return out


@cache
def _live_only(provider: str, route: str) -> frozenset[str]:
    """Field paths the tables mark live_only on ``route``."""
    return frozenset(row["field"] for data in load_tables(provider) for row in data.get("fields", [])
                     if row.get("live_only") and route in row_routes(row))


def _extra_is_live_only(provider: str, route: str, error: Any) -> bool:
    if error.validator != "additionalProperties" or not isinstance(error.instance, dict):
        return False
    allowed = set(error.schema.get("properties", {}))
    base = re.sub(r"\[\d+\]", "[]", _path(error))
    extras = [key for key in error.instance if key not in allowed]
    return bool(extras) and all((f"{base}.{key}" if base else key) in _live_only(provider, route) for key in extras)


def _path(error: Any) -> str:
    text = ""
    for part in error.absolute_path:
        text += f"[{part}]" if isinstance(part, int) else (f".{part}" if text else str(part))
    return text


def contract_problems(provider: str, route: str, body: Any) -> list[str]:
    """Why ``body`` does not match the documented 200 schema of ``route`` (empty when it does,
    or when the reference has no schema for the route)."""
    validator = _validator(provider, route)
    if validator is None or (body == [] and (provider, route) in EMPTY_LIST_BODIES):
        return []
    problems = []
    for error in validator.iter_errors(_documented_names(provider, route, body)):
        path = _path(error)
        allowed = any(
            p == provider and r == route and k == error.validator and re.fullmatch(pattern, path)
            for (p, r, pattern, k) in DEVIATIONS
        )
        if not allowed and not _extra_is_live_only(provider, route, error):
            problems.append(f"{route} {path or '$'}: {error.message[:200]}")
    return problems


def undocumented_fields(provider: str, route: str, body: Any) -> list[str]:
    """Field paths of ``body`` that the 200 schema of ``route`` does not document and no
    ``live_only`` row names (live renames applied first). The schema check alone does not catch
    a mistyped key: the PrismHR spec never sets additionalProperties and isolved rarely does."""
    documented = documented_fields(provider, route)
    if documented is None or (body == [] and (provider, route) in EMPTY_LIST_BODIES):
        return []
    renames = {}
    for entry in load_routes(provider).get("selected", []):
        if entry["route"] == route:
            renames = entry.get("live_renames", {})
    # body_fields reports [] and [{}] alike as "[]": a live_only "[]" row (an empty list body, see
    # EMPTY_LIST_BODIES) never admits a list of empty objects.
    live_only = _live_only(provider, route) - {"[]"}
    out = []
    for field in sorted(body_fields(body)):
        field = apply_live_renames(field, renames)
        if field == "$" and body == {}:  # an empty object body; its type is checked by contract_problems
            continue
        if field in documented or field in live_only or documented_below(field, documented):
            continue
        out.append(f"{route} {field}: not documented and no live_only row")
    return out


def skeleton(provider: str, route: str, path: str = "") -> Any:
    """A minimal value for the documented schema of ``route`` at ``path`` (``employee[]``,
    ``employee[].person``; "" is the body): every required property, filled with empty values
    ("" for strings, false, 0, [] and objects with their own required properties)."""
    doc = documented_routes(provider)[route]
    if doc.schema is None:
        return {}
    node = doc.schema
    for part in [p for p in re.split(r"\.|(?=\[\])", path) if p]:
        node = _resolve(node, doc.definitions)
        if part == "[]":
            node = node.get("items", {})
            continue
        properties = {}
        for variant in [node] + list(node.get("allOf", [])):
            properties.update(_resolve(variant, doc.definitions).get("properties", {}))
        node = properties[part]
    return _skeleton(node, doc.definitions, ())


def _resolve(node: dict, root: dict) -> dict:
    while isinstance(node, dict) and "$ref" in node:
        target: Any = root
        for part in node["$ref"].lstrip("#/").split("/"):
            target = target[part.replace("~1", "/").replace("~0", "~")]
        node = target
    return node


def _skeleton(node: Any, root: dict, seen: tuple) -> Any:
    ref = node.get("$ref") if isinstance(node, dict) else None
    if ref in seen:
        return {}
    node = _resolve(node, root)
    seen = seen + ((ref,) if ref else ())
    properties, required = {}, []
    for variant in [node] + list(node.get("allOf", [])):
        variant = _resolve(variant, root)
        properties.update(variant.get("properties", {}))
        required += variant.get("required", [])
    kind = node.get("type")
    if properties or kind == "object":
        return {name: _skeleton(properties.get(name, {}), root, seen) for name in required}
    if kind == "array":
        return []
    if kind == "boolean":
        return False
    if kind in ("integer", "number"):
        return 0
    if "enum" in node:
        return node["enum"][0]
    return ""
