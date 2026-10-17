"""Local store of normalized runs for the app (Phase 7b): one SQLite file, one row per record.

A run is stored whole or not at all (one transaction). Records keep the values they arrived with:
full values for runs normalized here (samples and syncs), masked ones for an imported masked
document. Masking for people happens on the way out (``api.py``), never here. The file is
personal data: it lives in the Git-ignored ``live_data/`` (D-009, D-092).
"""
import json
import sqlite3
import threading
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..canonical.base import to_json
from ..employees.bundle import load_bundle
from ..output import run_header
from ..pipeline import RECORD_LISTS, RunResult, normalize_bundle

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"
SAMPLE_PROVIDERS = ("prismhr", "isolved", "ukg-ready")
LINKS = ("company_id", "employee_id", "payroll_run_id")
MAX_LIMIT = 200
SCHEMA_VERSION = 2  # raise when the tables change; an older file is refused with a clear message
NEWEST_FIRST = ("payroll_runs", "paychecks")  # paged by pay date, newest first; other lists by id

_SCHEMA = """
CREATE TABLE IF NOT EXISTS datasets (
    id INTEGER PRIMARY KEY, kind TEXT NOT NULL, label TEXT NOT NULL, provider TEXT NOT NULL,
    tenant_id TEXT NOT NULL, created_at TEXT NOT NULL, kept_values TEXT NOT NULL,
    run TEXT NOT NULL, diagnostics TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS records (
    dataset_id INTEGER NOT NULL REFERENCES datasets(id) ON DELETE CASCADE, list TEXT NOT NULL,
    id TEXT NOT NULL, company_id TEXT, employee_id TEXT, payroll_run_id TEXT, pay_date TEXT, search TEXT NOT NULL,
    data TEXT NOT NULL, PRIMARY KEY (dataset_id, list, id)
);
CREATE INDEX IF NOT EXISTS records_company ON records (dataset_id, list, company_id);
CREATE INDEX IF NOT EXISTS records_employee ON records (dataset_id, list, employee_id);
CREATE INDEX IF NOT EXISTS records_run ON records (dataset_id, list, payroll_run_id);
CREATE INDEX IF NOT EXISTS records_pay_date ON records (dataset_id, list, pay_date);
"""


def _search_text(data: dict) -> str:
    """What the ``q`` filter matches: the id, and for an employee the name and number."""
    name = data.get("name") if isinstance(data.get("name"), dict) else {}
    parts = [data.get("id"), data.get("employee_number"), name.get("first"), name.get("preferred_first"), name.get("last")]
    if isinstance(data.get("name"), str):
        parts.append(data["name"])
    return " ".join(str(part) for part in parts if part).lower()


class Store:
    def __init__(self, path: Path | str) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._db.execute("PRAGMA foreign_keys = ON")
            version = self._db.execute("PRAGMA user_version").fetchone()[0]
            if version != SCHEMA_VERSION and self._db.execute("SELECT 1 FROM sqlite_master WHERE name = 'records'").fetchone():
                self._db.close()
                raise ValueError(f"{path} was made by an older version of the app: delete it (samples load again on "
                                 "start; load outputs again with import-output)")
            self._db.executescript(_SCHEMA)
            self._db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # Writing

    def _add(self, kind: str, label: str, run: dict, kept: str, lists: dict[str, Any]) -> int:
        """Store one run: ``lists`` maps each list name to an iterable of record JSON texts."""
        diagnostics: Counter = Counter()
        with self._lock, self._db:  # one transaction: the whole run or nothing
            cursor = self._db.execute(
                "INSERT INTO datasets (kind, label, provider, tenant_id, created_at, kept_values, run, diagnostics)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, '[]')",
                (kind, label, run["provider"], run["tenant_id"], datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 kept, json.dumps(run)),
            )
            dataset = cursor.lastrowid
            for name, texts in lists.items():
                if name not in RECORD_LISTS:
                    continue
                rows = []
                for text in texts:
                    data = json.loads(text)
                    for item in data.get("diagnostics") or []:
                        diagnostics[(name, item.get("code"), item.get("severity"))] += 1
                    links = {link: data.get(link) for link in LINKS}
                    if name == "companies":
                        links["company_id"] = data["id"]
                    rows.append((dataset, name, data["id"], links["company_id"], links["employee_id"],
                                 links["payroll_run_id"], data.get("pay_date"), _search_text(data), text))
                self._db.executemany("INSERT INTO records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
            summary = [{"list": n, "code": c, "severity": s, "count": k} for (n, c, s), k in sorted(diagnostics.items())]
            self._db.execute("UPDATE datasets SET diagnostics = ? WHERE id = ?", (json.dumps(summary), dataset))
        return dataset

    def add_run(self, result: RunResult, kind: str, label: str, input_name: str, extra: dict | None = None) -> int:
        """A run normalized here: every record serialized (and validated) by ``to_json``, full values kept."""
        run = run_header(result, input_name)
        del run["sensitive_values"]  # a property of each response, not of the stored run
        run.update(extra or {})
        lists = {name: (to_json(record) for record in records) for name, records in result.records.items()}
        return self._add(kind, label, run, "full", lists)

    def add_document(self, document: dict, label: str) -> int:
        """An output document written earlier (``normalize`` or ``fetch``), as it was written.
        Raises ValueError when a list holds a different number of records than ``run.counts``
        says, as in a filtered output (``normalize --entity``): its counts describe the whole run,
        so the dataset would report records it does not have (D-098 review)."""
        run = dict(document["run"])
        short = [f"{name} ({len(document.get(name) or [])} of {count})" for name, count in run.get("counts", {}).items()
                 if len(document.get(name) or []) != count]
        if short or set(run.get("counts", {})) != set(RECORD_LISTS):
            raise ValueError(f"the document's lists do not match its run counts: {', '.join(short) or 'lists missing'}; "
                             "import a full output (normalize or fetch without --entity)")
        kept = "full" if run.pop("sensitive_values", "masked") == "shown" else "masked"
        lists = {name: (json.dumps(item) for item in document.get(name) or []) for name in RECORD_LISTS}
        return self._add("import", label, run, kept, lists)

    def ensure_samples(self, fixtures: Path = FIXTURES) -> None:
        """Normalize each fixture bundle into a ``sample`` dataset, once (no key needed)."""
        for provider in SAMPLE_PROVIDERS:
            path = fixtures / provider / "bundle.json"
            with self._lock:
                stored = self._db.execute("SELECT 1 FROM datasets WHERE kind = 'sample' AND provider = ?", (provider,)).fetchone()
            if not stored and path.is_file():
                self.add_run(normalize_bundle(load_bundle(path)), "sample", f"Sample data: {provider} (synthetic fixture)", path.name)

    # Reading

    @staticmethod
    def _dataset(row: sqlite3.Row, full: bool = False) -> dict:
        run = json.loads(row["run"])
        item = {
            "id": row["id"], "kind": row["kind"], "label": row["label"], "provider": row["provider"],
            "tenant_id": row["tenant_id"], "created_at": row["created_at"], "kept_values": row["kept_values"],
            "counts": run.get("counts", {}), "link_problems": len(run.get("link_problems", [])),
            "unusable_responses": len(run.get("unusable_responses", [])),
        }
        if full:
            item["run"] = run
            item["diagnostics"] = json.loads(row["diagnostics"])
        return item

    def datasets(self) -> list[dict]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM datasets ORDER BY id DESC").fetchall()
        return [self._dataset(row) for row in rows]

    def dataset(self, dataset: int) -> dict | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM datasets WHERE id = ?", (dataset,)).fetchone()
        return self._dataset(row, full=True) if row else None

    def page(self, dataset: int, name: str, offset: int = 0, limit: int = 50, q: str | None = None,
             diagnostic: str | None = None, ids: list[str] | None = None, **links: str | None) -> tuple[list[dict], int]:
        """One page of a list (payroll lists newest pay date first, others in id order) and the
        total that matches the filters. The caller
        bounds ``offset`` and ``limit`` (at most MAX_LIMIT) and reports the values it used."""
        where, args = ["dataset_id = ?", "list = ?"], [dataset, name]
        for link, value in links.items():
            if link in LINKS and value:
                where.append(f"{link} = ?")
                args.append(value)
        if ids:
            where.append(f"id IN ({', '.join('?' * len(ids))})")
            args.extend(ids)
        if q:
            where.append("search LIKE ?")
            args.append(f"%{q.lower()}%")
        if diagnostic:
            where.append("EXISTS (SELECT 1 FROM json_each(data, '$.diagnostics') WHERE json_extract(value, '$.code') = ?)")
            args.append(diagnostic)
        clause = " AND ".join(where)
        order = "pay_date DESC, id" if name in NEWEST_FIRST else "id"
        with self._lock:
            total = self._db.execute(f"SELECT COUNT(*) FROM records WHERE {clause}", args).fetchone()[0]
            rows = self._db.execute(f"SELECT data FROM records WHERE {clause} ORDER BY {order} LIMIT ? OFFSET ?",
                                    [*args, limit, offset]).fetchall()
        return [json.loads(row["data"]) for row in rows], total

    def record(self, dataset: int, name: str, record_id: str) -> dict | None:
        with self._lock:
            row = self._db.execute("SELECT data FROM records WHERE dataset_id = ? AND list = ? AND id = ?",
                                   (dataset, name, record_id)).fetchone()
        return json.loads(row["data"]) if row else None
