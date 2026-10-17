"""Markdown rendering of the mapping tables to docs/mappings/ (D-061). Generated; a test fails
when the committed files differ."""
from pathlib import Path

from .spec import PROVIDERS, documented_fields, documented_routes
from .tables import code_tables, glob_regex, load_routes, load_tables

TITLES = {"prismhr": "PrismHR", "isolved": "isolved", "ukg-ready": "UKG Ready"}


def _cell(value) -> str:
    if value is None or value == [] or value == "":
        return ""
    if isinstance(value, list):
        return "<br>".join(f"`{item}`" if str(item).startswith("contracts/") else str(item) for item in value)
    return str(value).replace("|", "\\|").replace("\n", " ")


def _table(header: list[str], rows: list[list]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
    lines += ["| " + " | ".join(_cell(value) for value in row) + " |" for row in rows]
    return lines + [""]


def render_provider(provider: str) -> str:
    routes, tables, documented = load_routes(provider), load_tables(provider), documented_routes(provider)
    families = [entry for entry in routes["excluded"] if "family" in entry]
    singles = [entry for entry in routes["excluded"] if "route" in entry]
    out = [
        f"# {TITLES[provider]} mapping",
        "",
        f"Generated from `src/normalization/mappings/data/{provider}/` by `python -m normalization "
        "export-mappings`; do not edit by hand. Format and rules: `docs/mappings/README.md`.",
        "",
        f"Documented GET routes: {len(documented)}. Selected: {len(routes['selected'])}. "
        f"Excluded individually: {len(singles)}. Excluded by family: "
        f"{sum(1 for r in documented if any(glob_regex(p, '/').match(r) for f in families for p in f['routes']))}.",
        "",
        "## Selected routes",
        "",
    ]
    rows = []
    for entry in routes["selected"]:
        fields = documented_fields(provider, entry["route"])
        count = "not extracted" if fields is None else len(fields)
        rows.append([f"`{entry['route']}`", ", ".join(entry["entities"]), count, "yes" if entry["classified"] else "pending", entry.get("note")])
    out += _table(["Route", "Entities", "Documented fields", "Classified", "Note"], rows)
    out += ["## Routes excluded individually", ""]
    out += _table(["Route", "Reason"], [[f"`{e['route']}`", e["reason"]] for e in singles])
    out += ["## Route families excluded", ""]
    out += _table(["Family", "Patterns", "Reason"], [[f["family"], "<br>".join(f"`{p}`" for p in f["routes"]), f["reason"]] for f in families])
    for data in tables:
        out += [f"## {data['entity'].replace('_', ' ').capitalize()} fields", ""]
        out += [f"- {_cell(note)}" for note in data.get("notes", [])] + ([""] if data.get("notes") else [])
        rows = [
            [
                "<br>".join(f"`{r}`" for r in (row["route"] if isinstance(row["route"], list) else [row["route"]])),
                f"`{row['field']}`",
                row["use"] + (" (live only)" if row.get("live_only") else ""),
                f"`{row['target']}`" if row.get("target") else "",
                row.get("transform"),
                row.get("evidence"),
                row.get("reason") or row.get("note"),
            ]
            for row in data.get("fields", [])
        ]
        out += _table(["Route", "Source field", "Use", "Canonical field", "Transform", "Evidence", "Reason or note"], rows)
    for table_id, table in code_tables(tables).items():
        columns = list(table["columns"])
        out += [f"### Code table `{table_id}`", "", f"Source: {table['source']}. " + ", ".join(f"{c}: `{e}`" for c, e in table["columns"].items()), ""]
        rows = [[f"`{code['raw']}`", code.get("label"), *[f"{code[c]['value']} ({code[c]['basis']})" for c in columns], code.get("evidence"), code.get("note")] for code in table["codes"]]
        out += _table(["Raw code", "Label", *columns, "Evidence", "Note"], rows)
    return "\n".join(out).rstrip("\n") + "\n"


def render_mappings() -> dict[str, str]:
    return {f"{provider}.md": render_provider(provider) for provider in PROVIDERS}


def write_mappings(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, text in render_mappings().items():
        path = out_dir / name
        path.write_bytes(text.encode("utf-8"))
        written.append(path)
    return written
