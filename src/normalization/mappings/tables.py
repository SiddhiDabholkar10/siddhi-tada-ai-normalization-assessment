"""Mapping tables: route lists, field rows and code tables per provider (D-061).

Data lives in ``data/<provider>/routes.json`` and ``data/<provider>/<entity>.json``. The tables
describe the mapping for reviewers and for the Phase 5 adapters, which are ordinary Python that
follows them. A ``transform`` is a label naming the rule, not an instruction for an engine.

Route and field patterns: ``*`` matches within one segment, ``**`` matches any number of
segments (route segments are separated by "/", field segments by ".").
"""
import json
import re
from collections.abc import Callable
from functools import cache
from pathlib import Path
from typing import Any

from ..canonical import enums
from ..canonical.parsing import DateRole
from ..canonical.paths import path_exists
from ..canonical.values import UNKNOWN, CanonicalEnum, MappingBasis
from .spec import RouteDoc, documented_fields, documented_routes, resolve_pointer, schema_fields

DATA = Path(__file__).parent / "data"
ENTITIES = ("company", "employee", "direct_deposit", "deduction_setup", "benefit_enrollment", "payroll")
USES = ("mapped", "extension", "sensitive_extension", "excluded")
EXTENSION_FIELD = {"extension": "provider_extensions", "sensitive_extension": "sensitive_provider_extensions"}
# Transform labels. "date:<role>" names a DateRole; "code:<table id>" names a code table.
TRANSFORMS = {
    "copy": "value used as sent (strings trimmed; blank is not provided)",
    "number": "exact decimal (parse_source_json, to_decimal)",
    "boolean": "provider flag to true or false",
    "yes_no_declined": "Y true, N false, blank not_provided; D (declined to answer) not_provided with the raw answer kept in sensitive_provider_extensions",
    "timestamp": "date and time kept as sent, never truncated",
    "ms_to_hours": "UKG milliseconds divided by 3,600,000: exact when the division ends, else rounded to 7 decimal places, which keeps the integer milliseconds recoverable (D-028, D-091)",
    "masked": "provider-masked value: null, hidden_by_source, value_redacted_in_source (D-020)",
    "last4": "visible last characters of a masked value (D-020)",
    "source_id": "kept in source_ids and used in the canonical id (D-036)",
    "reference": "canonical id of another record or company-owned entry",
    "join": "value found by joining to another route or table (see note)",
    "derive": "computed from other fields (see note)",
}
DATE_ROLES = {role.value for role in DateRole}
EVIDENCE_PREFIXES = ("contracts/", "live:", "D-")
ROW_KEYS = {"route", "field", "use", "target", "transform", "evidence", "reason", "note", "live_only"}


def glob_regex(pattern: str, sep: str) -> re.Pattern:
    """Regex for a route or field pattern (see module docstring)."""
    out, s = [], re.escape(sep)
    for token in re.split(rf"(\*\*{s}|{s}\*\*|\*\*|\*)", pattern):
        if token == f"**{sep}":
            out.append(f"(?:.*{s})?")
        elif token == f"{sep}**":
            out.append(f"(?:{s}.*)?")
        elif token == "**":
            out.append(".*")
        elif token == "*":
            out.append(f"[^{s}]*")
        else:
            out.append(re.escape(token))
    return re.compile("".join(out) + r"\Z")


def is_pattern(text: str) -> bool:
    return "*" in text


def documented_fields_of(doc: RouteDoc) -> frozenset[str]:
    return schema_fields(doc) or frozenset()


def apply_live_renames(field: str, renames: dict[str, str]) -> str:
    """A live field path in documented terms. ``renames`` maps a documented path prefix to the
    prefix the live API sends instead (PrismHR spec ``payrollVouchers``, live ``payrollVoucher``)."""
    for documented, live in renames.items():
        if field == live or field.startswith((live + ".", live + "[]")):
            return documented + field[len(live):]
    return field


def row_routes(row: dict) -> list[str]:
    routes = row.get("route")
    return routes if isinstance(routes, list) else [routes]


@cache
def load_routes(provider: str) -> dict:
    return json.loads((DATA / provider / "routes.json").read_text(encoding="utf-8"))


@cache
def load_tables(provider: str) -> tuple[dict, ...]:
    """The entity files of a provider that exist, in ENTITIES order."""
    files = [DATA / provider / f"{entity}.json" for entity in ENTITIES]
    return tuple(json.loads(f.read_text(encoding="utf-8")) for f in files if f.is_file())


def code_tables(tables: tuple[dict, ...] | list[dict]) -> dict[str, dict]:
    return {table["id"]: table for data in tables for table in data.get("code_tables", [])}


# ---- route list ---------------------------------------------------------------------------


def check_routes(routes: dict, documented: dict[str, RouteDoc]) -> list[str]:
    """Problems with a provider's route list. Every documented GET route must fall under exactly
    one selected route, one individually excluded route, or one excluded family."""
    problems = []
    exact: dict[str, int] = {}
    for entry in routes.get("selected", []):
        route = entry.get("route")
        exact[route] = exact.get(route, 0) + 1
        if route not in documented:
            problems.append(f"selected route is not documented: {route}")
            continue
        entities = entry.get("entities") or []
        if not entities or not set(entities) <= set(ENTITIES):
            problems.append(f"{route}: entities must be a non-empty subset of {ENTITIES}")
        if not isinstance(entry.get("classified"), bool):
            problems.append(f"{route}: 'classified' must be true or false")
        flagged = entry.get("schema") in ("not_extracted", "not_documented")
        if flagged != (documented[route].schema is None):
            problems.append(f"{route}: 'schema' (not_extracted or not_documented) must be set exactly when no response schema is documented")
        renames = entry.get("live_renames", {})
        fields = documented_fields_of(documented[route]) if renames else frozenset()
        for prefix in renames:
            if not any(f == prefix or f.startswith((prefix + ".", prefix + "[]")) for f in fields):
                problems.append(f"{route}: live_renames key is not a documented field prefix: {prefix}")
    families = []
    for entry in routes.get("excluded", []):
        if not entry.get("reason"):
            problems.append(f"exclusion without a reason: {entry}")
        if "route" in entry:
            route = entry["route"]
            exact[route] = exact.get(route, 0) + 1
            if route not in documented:
                problems.append(f"excluded route is not documented: {route}")
        elif entry.get("family") and entry.get("routes"):
            families.append(entry)
            for pattern in entry["routes"]:
                if not any(glob_regex(pattern, "/").match(route) for route in documented):
                    problems.append(f"family '{entry['family']}': pattern matches no documented route: {pattern}")
        else:
            problems.append(f"exclusion needs 'route', or 'family' and 'routes': {entry}")
    problems += [f"route listed {count} times: {route}" for route, count in exact.items() if count > 1]
    for route in documented:
        hits = [f"family '{f['family']}'" for f in families if any(glob_regex(p, "/").match(route) for p in f["routes"])]
        hits += ["listed"] * exact.get(route, 0)
        if len(hits) != 1:
            problems.append(f"{route}: covered {len(hits)} times ({', '.join(hits) or 'not covered'})")
    return problems


# ---- field rows and code tables -------------------------------------------------------------


def _evidence_problems(where: str, evidence: Any, required: bool) -> list[str]:
    if not isinstance(evidence, list) or (required and not evidence):
        return [f"{where}: evidence must be a {'non-empty ' if required else ''}list"]
    problems = []
    for item in evidence:
        if not isinstance(item, str) or not item.startswith(EVIDENCE_PREFIXES):
            problems.append(f"{where}: evidence must start with {EVIDENCE_PREFIXES}: {item!r}")
        elif item.startswith("contracts/") and not resolve_pointer(item):
            problems.append(f"{where}: evidence does not resolve: {item}")
    return problems


def _transform_problem(transform: Any, tables: dict[str, dict]) -> str | None:
    if not isinstance(transform, str):
        return "transform is required for a mapped field"
    kind, _, arg = transform.partition(":")
    if kind == "date" and arg in DATE_ROLES:
        return None
    if kind == "code" and arg in tables:
        return None
    if transform in TRANSFORMS:
        return None
    return f"unknown transform {transform!r}"


def check_code_tables(provider: str, tables: dict[str, dict]) -> list[str]:
    problems = []
    for table_id, table in tables.items():
        where = f"code table {table_id}"
        if not table_id.startswith(f"{provider}."):
            problems.append(f"{where}: id must start with '{provider}.'")
        columns = table.get("columns") or {}
        enum_types = {}
        for column, enum_name in columns.items():
            enum_type = getattr(enums, enum_name, None)
            if not isinstance(enum_type, type) or not issubclass(enum_type, CanonicalEnum):
                problems.append(f"{where}: {enum_name} is not a canonical enum")
            else:
                enum_types[column] = enum_type
        if not columns or not table.get("source"):
            problems.append(f"{where}: needs 'source' and 'columns'")
        seen = set()
        for code in table.get("codes", []):
            raw = code.get("raw")
            if not isinstance(raw, str) or raw in seen:
                problems.append(f"{where}: raw code must be a unique string: {raw!r}")
            seen.add(raw)
            extra = set(code) - {"raw", "label", "note", "evidence"} - set(columns)
            if extra:
                problems.append(f"{where} code {raw!r}: unknown keys {sorted(extra)}")
            problems += _evidence_problems(f"{where} code {raw!r}", code.get("evidence", []), False)
            for column, enum_type in enum_types.items():
                cell = code.get(column) or {}
                value, basis = cell.get("value"), cell.get("basis")
                if value not in {member.value for member in enum_type} or basis not in {b.value for b in MappingBasis}:
                    problems.append(f"{where} code {raw!r}: {column} needs a {enum_type.__name__} value and a basis")
                elif (value == UNKNOWN) != (basis == MappingBasis.UNMAPPED):
                    problems.append(f"{where} code {raw!r}: {column} 'unknown' and 'unmapped' must be used together")
    return problems


def specificity(pattern: str) -> int:
    """Number of fixed segments in a field pattern (segments without a wildcard)."""
    return sum(1 for segment in pattern.split(".") if "*" not in segment)


def classify(rows: list[dict], field: str) -> tuple[dict | None, str | None]:
    """The row that classifies a field: an exact row, else the matching pattern row with the
    most fixed segments (``clientMaster.clientTax[].*`` beats ``clientMaster.**``). Two exact
    rows, or two pattern rows tied for most specific, are a mistake."""
    exact = [row for row in rows if not is_pattern(row["field"]) and row["field"] == field]
    if len(exact) == 1:
        return exact[0], None
    if len(exact) > 1:
        return None, f"classified by {len(exact)} exact rows"
    groups = [row for row in rows if is_pattern(row["field"]) and glob_regex(row["field"], ".").match(field)]
    if not groups:
        return None, "not classified"
    best = max(specificity(row["field"]) for row in groups)
    winners = [row for row in groups if specificity(row["field"]) == best]
    if len(winners) == 1:
        return winners[0], None
    return None, f"matched by {len(winners)} equally specific group rows"


def documented_below(field: str, documented: frozenset[str]) -> list[str]:
    """Documented fields inside ``field`` (its object keys or array items)."""
    return [d for d in documented if d.startswith((field + ".", field + "[]"))]


def live_field_problem(rows: list[dict], field: str, documented: frozenset[str]) -> str | None:
    """Why a field seen live is not classified, or None.

    A live response reports an empty array, empty object or null as a path of its own
    (``body_fields``). When the documented schema has fields inside that path, it is a container,
    not a leaf: it counts as classified when every documented field inside it is."""
    below = documented_below(field, documented) if field not in documented else []
    if below:
        missing = sum(1 for d in below if classify(rows, d)[1])
        return f"{missing} documented fields inside it are not classified" if missing else None
    return classify(rows, field)[1]


def check_tables(
    provider: str,
    routes: dict,
    tables: tuple[dict, ...] | list[dict],
    fields_of: Callable[[str], frozenset[str] | None],
) -> list[str]:
    """Problems with a provider's field rows and code tables, and completeness of every route
    marked ``classified``. ``fields_of(route)`` gives the documented fields of a route."""
    problems = []
    selected = {entry["route"]: entry for entry in routes.get("selected", [])}
    codes = code_tables(tables)
    problems += check_code_tables(provider, codes)
    rows_by_route: dict[str, list[dict]] = {}
    for data in tables:
        if data.get("provider") != provider or data.get("entity") not in ENTITIES:
            problems.append(f"table file must name provider {provider!r} and an entity: {data.get('entity')!r}")
        if set(data) - {"provider", "entity", "notes", "fields", "code_tables"}:
            problems.append(f"{data.get('entity')}: unknown file keys {sorted(set(data) - {'provider', 'entity', 'notes', 'fields', 'code_tables'})}")
        for index, row in enumerate(data.get("fields", [])):
            where = f"{data.get('entity')} row {index} ({row.get('field')})"
            if set(row) - ROW_KEYS or not isinstance(row.get("field"), str):
                problems.append(f"{where}: needs 'field'; unknown keys {sorted(set(row) - ROW_KEYS)}")
                continue
            use = row.get("use")
            if use not in USES:
                problems.append(f"{where}: use must be one of {USES}")
            if use == "mapped":
                if not isinstance(row.get("target"), str) or not path_exists(row["target"]):
                    problems.append(f"{where}: target is not a canonical field: {row.get('target')!r}")
                problem = _transform_problem(row.get("transform"), codes)
                if problem:
                    problems.append(f"{where}: {problem}")
            if use in EXTENSION_FIELD:
                target = row.get("target")
                if not isinstance(target, str) or not path_exists(target) or not target.endswith("." + EXTENSION_FIELD[use]):
                    problems.append(f"{where}: target must be a record's {EXTENSION_FIELD[use]}: {target!r}")
            if use != "mapped" and not row.get("reason"):
                problems.append(f"{where}: a reason is required for {use}")
            problems += _evidence_problems(where, row.get("evidence", []), use == "mapped")
            for route in row_routes(row):
                if route not in selected:
                    problems.append(f"{where}: route is not selected: {route}")
                    continue
                rows_by_route.setdefault(route, []).append(row)
                documented = fields_of(route)
                if documented is not None and not row.get("live_only"):
                    pattern = glob_regex(row["field"], ".")
                    if not any(pattern.match(field) for field in documented):
                        problems.append(f"{where}: matches no documented field of {route} (mark live_only if seen only live)")
    for route, entry in selected.items():
        documented = fields_of(route)
        if entry.get("classified") and documented is not None:
            for field in sorted(documented):
                _, problem = classify(rows_by_route.get(route, []), field)
                if problem:
                    problems.append(f"{route} {field}: {problem}")
    return problems


def route_problems(provider: str) -> list[str]:
    return check_routes(load_routes(provider), documented_routes(provider))


def table_problems(provider: str) -> list[str]:
    return check_tables(provider, load_routes(provider), load_tables(provider), lambda route: documented_fields(provider, route))


def pending_routes(provider: str) -> list[str]:
    """Selected routes whose fields are not classified yet (Phase 3 steps 2 to 5)."""
    return [entry["route"] for entry in load_routes(provider)["selected"] if not entry["classified"]]
