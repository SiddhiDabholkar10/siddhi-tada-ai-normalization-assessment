"""Documented GET routes and their response fields, read from contracts/ (D-061).

A field path names a leaf of a response body: object keys joined by ".", "[]" for the items of
an array ("payrollVoucher[].earning[].payCode"), "{key}" for the values of a map, and "$" for a
response that is a single value. The live inventory tool (my_docs) uses the same format, so
documented and observed fields compare directly.
"""
import json
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
CONTRACTS = ROOT / "contracts"
PRISMHR_SPEC = "contracts/prismhr/openapi/prismhr-2025.09.openapi.json"
ISOLVED_SPEC = "contracts/isolved/openapi/isolved-v6.swagger.json"  # primary snapshot only (D-007)
UKG_SCHEMAS = "contracts/ukg-ready/reference-schemas.json"
UKG_PAGES = "contracts/ukg-ready/reference-docs/res"
PROVIDERS = ("prismhr", "isolved", "ukg-ready")

# "Definition get {{ getUriPrefix() }} /v2/companies/{cid}/..." on each UKG reference page.
_UKG_GET = re.compile(r'class="method get">get</[^>]+>\s*(?:<[^>]+>\s*)*\{\{ getUriPrefix\(\) \}\}\s*(?:<[^>]+>\s*)*([^<\s]+)')


@dataclass(frozen=True)
class RouteDoc:
    """A documented GET route. ``schema`` is its 200 JSON response schema, or None when the
    reference material has none (UKG pages whose schema was not extracted, non-JSON bodies).
    ``source`` is the file that documents it."""

    route: str
    source: str
    schema: dict | None
    definitions: dict  # where "#/..." references resolve


@cache
def _load(relative: str) -> Any:  # cached and shared: callers must not modify the result
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


@cache
def documented_routes(provider: str) -> dict[str, RouteDoc]:
    """Every documented GET route of a provider, by route template."""
    if provider == "prismhr":
        spec = _load(PRISMHR_SPEC)
        routes = {}
        for route, item in spec["paths"].items():
            if "get" in item:
                content = item["get"].get("responses", {}).get("200", {}).get("content", {})
                schema = content.get("application/json", {}).get("schema")
                routes[route] = RouteDoc(route, PRISMHR_SPEC, schema, spec)
        return routes
    if provider == "isolved":
        spec = _load(ISOLVED_SPEC)
        return {
            route: RouteDoc(route, ISOLVED_SPEC, item["get"].get("responses", {}).get("200", {}).get("schema"), spec)
            for route, item in spec["paths"].items()
            if "get" in item
        }
    if provider == "ukg-ready":
        extracted = {
            Path(entry["source_page"]).name: entry["schema"]
            for entry in _load(UKG_SCHEMAS)["schemas"]
            if entry["method"] == "GET" and "resp" in entry["source_container_id"]
        }
        routes = {}
        for page in sorted((ROOT / UKG_PAGES).glob("*.html")):
            match = _UKG_GET.search(page.read_text(encoding="utf-8", errors="replace"))
            if match:
                schema = extracted.get(page.name)
                routes[match.group(1)] = RouteDoc(match.group(1), f"{UKG_PAGES}/{page.name}", schema, schema or {})
        return routes
    raise ValueError(f"unknown provider {provider!r}")


def _resolve(node: dict, root: dict) -> tuple[dict, str | None]:
    ref = node.get("$ref")
    if ref is None:
        return node, None
    target: Any = root
    for part in ref.lstrip("#/").split("/"):
        target = target[part.replace("~1", "/").replace("~0", "~")]
    return target, ref


def _join(path: str, key: str) -> str:
    return f"{path}.{key}" if path else key


def _walk(node: Any, path: str, root: dict, refs: tuple[str, ...], out: set[str]) -> None:
    if not isinstance(node, dict):
        out.add(path or "$")
        return
    node, ref = _resolve(node, root)
    if ref in refs:  # recursive model: stop at the repeated reference
        out.add(path or "$")
        return
    refs = refs + (ref,) if ref else refs
    variants = [node] + [alt for key in ("allOf", "anyOf", "oneOf") for alt in node.get(key, [])]
    properties, items, mapped = {}, None, None
    for variant in variants:
        variant, _ = _resolve(variant, root)
        properties.update(variant.get("properties", {}))
        items = items or variant.get("items")
        extra = variant.get("additionalProperties")
        mapped = mapped or (extra if isinstance(extra, dict) and extra else None)
    if properties:
        for key, child in properties.items():
            _walk(child, _join(path, key), root, refs, out)
    elif items is not None:
        _walk(items, path + "[]", root, refs, out)
    elif mapped is not None:
        _walk(mapped, _join(path, "{key}"), root, refs, out)
    else:
        out.add(path or "$")


def _kind(node: Any, root: dict) -> str | None:
    """'object' or 'array' for a schema node, following references and allOf/anyOf/oneOf; None
    when the node does not say."""
    if not isinstance(node, dict):
        return None
    node, _ = _resolve(node, root)
    for variant in [node] + [alt for key in ("allOf", "anyOf", "oneOf") for alt in node.get(key, [])]:
        variant, _ = _resolve(variant, root)
        kind = variant.get("type")
        if kind in ("object", "array"):
            return kind
        if "properties" in variant:
            return "object"
        if "items" in variant:
            return "array"
    return None


def root_shape(doc: RouteDoc) -> tuple[str | None, str | None]:
    """The documented top-level JSON type of a 200 response ('object' or 'array') and, for an
    array, the type of its items; None where the schema does not say (D-089 shape guard)."""
    if doc.schema is None:
        return None, None
    kind = _kind(doc.schema, doc.definitions)
    if kind != "array":
        return kind, None
    node, _ = _resolve(doc.schema, doc.definitions)
    items = None
    for variant in [node] + [alt for key in ("allOf", "anyOf", "oneOf") for alt in node.get(key, [])]:
        items = items or _resolve(variant, doc.definitions)[0].get("items")
    return kind, _kind(items, doc.definitions)


def schema_fields(doc: RouteDoc) -> frozenset[str] | None:
    """Leaf field paths of a documented 200 response, or None without a schema."""
    if doc.schema is None:
        return None
    out: set[str] = set()
    _walk(doc.schema, "", doc.definitions, (), out)
    return frozenset(out)


@cache
def documented_fields(provider: str, route: str) -> frozenset[str] | None:
    return schema_fields(documented_routes(provider)[route])


def body_fields(body: Any) -> set[str]:
    """Leaf field paths of a response body (for live samples), in the same format."""
    out: set[str] = set()

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict) and node:
            for key, value in node.items():
                walk(value, _join(path, key))
        elif isinstance(node, list) and node:
            for item in node:
                walk(item, path + "[]")
        elif isinstance(node, list):
            out.add(path + "[]")
        else:
            out.add(path or "$")

    walk(body, "")
    return out


def resolve_pointer(reference: str) -> bool:
    """True if ``contracts/...json#/json/pointer`` names an existing node, or ``contracts/...``
    (no fragment) names an existing file."""
    file, _, pointer = reference.partition("#")
    path = ROOT / file
    if not file.startswith("contracts/") or not path.is_file():
        return False
    if not pointer:
        return True
    node: Any = _load(file)
    for part in pointer.lstrip("/").split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(node, list) and part.isdigit() and int(part) < len(node):
            node = node[int(part)]
        elif isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return False
    return True
