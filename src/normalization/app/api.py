"""HTTP API and web UI over the pipeline (Phase 7b).

Every record leaves through ``_view``: masked by ``output.mask_record`` unless the request opts in
with ``show_sensitive=true`` (D-036). A sync runs ``fetch_tenant`` and ``normalize_bundle``, the
same code as the ``fetch`` command, in a background thread, one at a time. Logs carry counts only:
no record values and no ids (the uvicorn access log is off in ``serve`` because URLs hold ids).
"""
import logging
import threading
import time
import uuid
from datetime import date, datetime, timezone
from importlib import import_module
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..canonical.base import sensitive_fields
from ..live import client as live_client
from ..live.fetch import PLANS, fetch_tenant
from ..output import mask_record
from ..pipeline import RECORD_LISTS, normalize_bundle
from ..write import WriteRequest, build
from ..write.plan import apply_changes, blank_employee
from ..write.send import send as send_plan
from .store import MAX_LIMIT, Store

STATIC = Path(__file__).resolve().parent / "static"
log = logging.getLogger("normalization.app")


class WriteBody(BaseModel):
    dataset_id: int
    employee_id: str | None = None  # None: a new employee from the form alone
    changes: dict[str, str] = {}  # form fields the viewer changed (write.plan.FORM_FIELDS)
    destination: str
    operation: str = "create"
    inputs: dict[str, str] = {}
    show_sensitive: bool = False
    confirm: bool = False  # send only: the caller confirmed this exact write


class SyncRequest(BaseModel):
    tenant: str
    companies: list[str] | None = None
    as_of: date | None = None  # the date treated as today, as ``fetch --as-of``


def _sensitivity(kept: str, show: bool) -> str:
    if not show:
        return "masked"
    return "shown" if kept == "full" else "masked at source"


def _view(name: str, data: dict, show: bool) -> dict:
    model = RECORD_LISTS[name]
    return data if show else mask_record(data, sensitive_fields(model), model)


class Syncs:
    """Background syncs, one at a time. A job keeps its progress lines (counts only)."""

    def __init__(self, store: Store, transport, key) -> None:
        self.store, self.transport, self.key = store, transport, key
        self.jobs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def running(self) -> bool:
        return any(job["state"] == "running" for job in self.jobs.values())

    def start(self, request: SyncRequest) -> dict:
        if request.tenant not in live_client.TENANTS:
            raise HTTPException(400, f"unknown tenant; choose from {', '.join(live_client.TENANTS)}")
        try:
            key = self.key()
        except live_client.FetchError as exc:
            raise HTTPException(400, str(exc)) from exc
        with self._lock:
            if self.running():
                raise HTTPException(409, "a sync is already running")
            job = {"id": uuid.uuid4().hex[:12], "tenant": request.tenant, "state": "running", "lines": [],
                   "dataset_id": None, "error": None, "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            self.jobs[job["id"]] = job
        threading.Thread(target=self._run, args=(job, request, key), daemon=True).start()
        return job

    def _run(self, job: dict, request: SyncRequest, key: str) -> None:
        def progress(line: str) -> None:
            job["lines"].append(line)
            log.info("sync %s: %s", job["tenant"], line)

        started = time.monotonic()
        log.info("sync %s: started", job["tenant"])
        try:
            provider = live_client.TENANTS[request.tenant]
            plan = import_module(PLANS[provider], "normalization.live")
            transport = self.transport or live_client.urllib_transport
            session = live_client.Session(request.tenant, key, transport=transport, rate_limit=getattr(plan, "RATE_LIMIT", None))
            progress(f"signed in to {request.tenant}")
            fetched = fetch_tenant(session, request.as_of, request.companies, None, progress=progress)
            progress("normalizing and storing")
            stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            job["dataset_id"] = self.store.add_run(normalize_bundle(fetched.bundle), "sync", f"Live sync: {provider}, {stamp}",
                                                   f"live:{request.tenant}", {"fetch": fetched.report})
            job["state"] = "done"
            progress(f"done in {time.monotonic() - started:.0f} s")
        except live_client.FetchError as exc:
            job["state"], job["error"] = "failed", str(exc)
        except Exception as exc:  # an adapter fault: the job fails, nothing is stored (D-089)
            # The exception text can name record ids, so only its type is kept (D-098 review).
            job["state"], job["error"] = "failed", f"normalization failed ({type(exc).__name__}); nothing stored"
        if job["error"]:
            log.warning("sync %s: failed, nothing stored", job["tenant"])


def create_app(store: Store, transport=None, key=live_client.api_key, samples: bool = True) -> FastAPI:
    """The app over ``store``. ``transport`` and ``key`` are for tests (the fake provider)."""
    if samples:
        store.ensure_samples()
    syncs = Syncs(store, transport, key)
    app = FastAPI(title="Tada AI normalization", docs_url="/api/docs", openapi_url="/api/openapi.json")

    def dataset_or_404(dataset: int) -> dict:
        found = store.dataset(dataset)
        if found is None:
            raise HTTPException(404, "no such dataset")
        return found

    def list_or_404(name: str) -> None:
        if name not in RECORD_LISTS:
            raise HTTPException(404, f"no such list; choose from {', '.join(RECORD_LISTS)}")

    @app.get("/api/tenants")
    def tenants():
        try:
            configured = bool(key())
        except live_client.FetchError:
            configured = False
        return [{"tenant": tenant, "provider": provider, "key_configured": configured}
                for tenant, provider in live_client.TENANTS.items()]

    @app.get("/api/datasets")
    def datasets():
        return store.datasets()

    @app.get("/api/datasets/{dataset}")
    def dataset(dataset: int):
        return dataset_or_404(dataset)

    @app.get("/api/datasets/{dataset}/records/{name}")
    def records(dataset: int, name: str, offset: int = 0, limit: int = 50, q: str | None = None,
                diagnostic: str | None = None, company_id: str | None = None, employee_id: str | None = None,
                payroll_run_id: str | None = None, ids: str | None = None, show_sensitive: bool = False):
        kept = dataset_or_404(dataset)["kept_values"]
        list_or_404(name)
        offset, limit = max(0, offset), max(1, min(limit, MAX_LIMIT))  # the page reports what it served
        wanted = [i for i in (ids or "").split(",") if i][:MAX_LIMIT]  # e.g. the employees named on a page
        items, total = store.page(dataset, name, offset, limit, q, diagnostic, wanted,
                                  company_id=company_id, employee_id=employee_id, payroll_run_id=payroll_run_id)
        return {"items": [_view(name, item, show_sensitive) for item in items], "total": total,
                "offset": offset, "limit": limit, "sensitive_values": _sensitivity(kept, show_sensitive)}

    @app.get("/api/datasets/{dataset}/records/{name}/{record_id}")
    def record(dataset: int, name: str, record_id: str, show_sensitive: bool = False):
        kept = dataset_or_404(dataset)["kept_values"]
        list_or_404(name)
        found = store.record(dataset, name, record_id)
        if found is None:
            raise HTTPException(404, "no such record")
        return {"item": _view(name, found, show_sensitive), "sensitive_values": _sensitivity(kept, show_sensitive)}

    @app.post("/api/sync", status_code=202)
    def sync(request: SyncRequest):
        return syncs.start(request)

    @app.get("/api/sync/{job}")
    def sync_job(job: str):
        if job not in syncs.jobs:
            raise HTTPException(404, "no such sync")
        found = syncs.jobs[job]
        return {**found, "lines": list(found["lines"])}  # a copy: the sync thread appends to it

    def write_plan(body: WriteBody):
        """The plan for a stored employee, built here from the store (a client's plan is never trusted)."""
        found = dataset_or_404(body.dataset_id)
        if body.employee_id is None:
            employee, company = blank_employee(), None
        else:
            if found["kept_values"] != "full":
                raise HTTPException(400, "this dataset was imported masked, so its values cannot be written; use one with full values")
            employee = store.record(body.dataset_id, "employees", body.employee_id)
            if employee is None:
                raise HTTPException(404, "no such employee")
            company = store.record(body.dataset_id, "companies", employee.get("company_id") or "")
        try:
            # Only changed fields arrive: untouched values (masked on the viewer's screen) stay the stored ones.
            employee = apply_changes(employee, body.changes)
            return build(WriteRequest(body.destination, body.operation, employee, company, body.inputs, set(body.changes)))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/write/preview")
    def write_preview(body: WriteBody):
        """Dry run: the provider requests a write would send, masked unless opted in (D-036)."""
        return write_plan(body).view(body.show_sensitive)

    @app.post("/api/write/send")
    def write_send(body: WriteBody):
        """Send a write: UKG Ready only, no refusals, and only with ``confirm`` (D-100)."""
        plan = write_plan(body)
        if not body.confirm:
            raise HTTPException(400, "not sent: confirm the write first")
        if not plan.sendable:
            raise HTTPException(400, "not sent: " + ("only UKG Ready is written for real" if plan.destination != "ukg-ready"
                                                    else "the plan has refusals"))
        try:
            plan_module = import_module(PLANS[plan.destination], "normalization.live")
            session = live_client.Session("ukg", key(), transport=transport or live_client.urllib_transport,
                                          rate_limit=getattr(plan_module, "RATE_LIMIT", None))
            result = send_plan(plan, session)
        except live_client.FetchError as exc:
            raise HTTPException(400, str(exc)) from exc
        log.info("write %s %s: %s", plan.destination, plan.operation,
                 ", ".join(f"HTTP {call['status']}" for call in result["calls"]))  # statuses only, no ids
        return result

    if (STATIC / "index.html").is_file():
        app.mount("/", StaticFiles(directory=STATIC, html=True), name="ui")
    return app
