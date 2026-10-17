"""Run a crawl plan against a signed-in session and build the provider bundle (D-092).

A plan (``plans/<provider>.py``) asks for calls stage by stage; the calls of one request run in
parallel and their responses are kept in request order, so the bundle does not depend on timing.
Each response is stored with its route template, its parameters exactly as sent (path values and
query, D-092 finding) and its status, the format the fixtures use (D-080). Window search calls
are probes: counted in the report, never stored, because an adapter reads every stored list.
"""
import json
import re
import threading
import time
import urllib.parse
from collections import Counter
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from importlib import import_module
from typing import Any

from ..canonical.ids import Provider
from ..employees.bundle import FORMAT, Bundle, Response
from .client import FetchError, Reply, Session

PLANS = {"prismhr": ".plans.prismhr", "isolved": ".plans.isolved", "ukg-ready": ".plans.ukg_ready"}
WINDOW_DAYS = 364  # a window is 365 days inclusive: "12 months", and under UKG's one-year limit
SEARCH_WINDOWS = 16  # backward search depth: back to about 2010, discovery's earliest range
PAGE_GUARD = 1000  # pages per list, against a server that never ends
PROGRESS_EVERY = 500  # calls between progress lines in a long stage
REPEATED = {"id": "payroll_id"}  # a template naming {id} twice keeps the first as payroll_id (D-082)
_PLACEHOLDER = re.compile(r"\{(\w+)\}")


@dataclass
class Call:
    route: str  # documented route template, as in routes.json and the bundle
    params: dict[str, str]  # path values and query parameters, exactly as sent
    headers: dict[str, str] = field(default_factory=dict)


def call(route: str, headers: dict[str, str] | None = None, **params: Any) -> Call:
    """A call with every value as the text sent (booleans as ``true``/``false``)."""
    text = {name: (str(value).lower() if isinstance(value, bool) else str(value)) for name, value in params.items()}
    return Call(route, text, dict(headers or {}))


def split_url(route: str, params: dict[str, str]) -> tuple[str, dict[str, str]]:
    """The path with its placeholders filled, and the remaining parameters as the query."""
    names = _PLACEHOLDER.findall(route)
    used: set[str] = set()
    path = route
    for index, name in enumerate(names):
        key = REPEATED.get(name, name) if name in names[index + 1:] else name
        if key not in params:
            raise ValueError(f"{route}: no value for {{{name}}}")
        used.add(key)
        path = path.replace("{" + name + "}", urllib.parse.quote(params[key], safe=""), 1)
    return path, {name: value for name, value in params.items() if name not in used}


def items(value: Any, *keys: str) -> list:
    """The list at ``keys`` inside a body (a single object counts as a one-item list; anything
    unexpected gives no items): the crawl never fails on an odd body, the adapters report it."""
    for key in keys:
        value = value.get(key) if isinstance(value, dict) else None
    if isinstance(value, list):
        return value
    return [] if value is None else [value]


def text_ids(values: Iterable[Any]) -> list[str]:
    """Non-blank ids as text, first occurrence order."""
    return list(dict.fromkeys(str(v).strip() for v in values if v is not None and str(v).strip()))


def day(value: Any) -> date | None:
    """The date part of a source date or timestamp, or None."""
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def http_problem(reply: Reply) -> str | None:
    """The default failed-probe rule: any status but 200."""
    return None if reply.status == 200 else f"HTTP {reply.status}"


def windows(start: date, end: date, days: int = WINDOW_DAYS) -> list[tuple[date, date]]:
    """``start`` to ``end`` cut into windows of at most ``days + 1`` days, oldest first."""
    out = []
    while start <= end:
        out.append((start, min(end, start + timedelta(days=days))))
        start += timedelta(days=days + 1)
    return out


class Crawl:
    """What a plan works with: the session, the scope and the growing bundle."""

    def __init__(
        self,
        session: Session,
        today: date,
        companies: Iterable[str] | None = None,
        pay_window: tuple[date, date] | None = None,
        workers: int = 4,
        page_sizes: dict[str, int] | None = None,
        progress: Callable[[str], None] = lambda line: None,
    ) -> None:
        self.session, self.today, self.workers, self.progress = session, today, max(1, workers), progress
        self.companies = set(companies) if companies else None
        self.pay_window = pay_window
        self.page_sizes = dict(page_sizes or {})
        self.responses: list[Response] = []
        self.statuses: Counter = Counter()
        self.unanswered: Counter = Counter()
        self.probes: Counter = Counter()
        self.windows: dict[str, Any] = {}
        self.chosen: list[str] = []
        self.prefix = ""  # the plan's path prefix (UKG: /rest before /v2)

    def wanted(self, ids: Iterable[str]) -> list[str]:
        """The company ids in scope, in the given order; ``--company`` values never found are an error."""
        ids = list(ids)
        if self.companies is None:
            self.chosen = ids
            return ids
        missing = sorted(self.companies - set(ids))
        if missing:
            # Counts only: the message reaches stderr and the app's job state, which carry no ids (D-092, D-098).
            raise FetchError(f"{len(missing)} of the requested companies not found in this tenant ({len(ids)} companies found)")
        self.chosen = [i for i in ids if i in self.companies]
        return self.chosen

    def _one(self, request: Call) -> Reply:
        path, query = split_url(request.route, request.params)
        return self.session.get(self.prefix + path, query, request.headers)

    def fetch(self, calls: list[Call], label: str, store: bool = True) -> list[Reply]:
        """Every call, in parallel; replies (and stored responses) in the order of ``calls``."""
        if not calls:
            return []
        self.progress(f"{label}: {len(calls)} call{'s' if len(calls) != 1 else ''}")
        done = [0]
        lock = threading.Lock()

        def one(request: Call) -> Reply:
            reply = self._one(request)
            with lock:
                done[0] += 1
                if done[0] % PROGRESS_EVERY == 0:
                    self.progress(f"  {done[0]} of {len(calls)}")
            return reply

        if self.workers == 1 or len(calls) == 1:
            replies = [one(c) for c in calls]
        else:
            with ThreadPoolExecutor(self.workers) as pool:
                replies = list(pool.map(one, calls))
        for request, reply in zip(calls, replies):
            self.statuses[str(reply.status)] += 1
            if reply.status == 0:
                self.unanswered[request.route] += 1
            if store:
                self.responses.append(Response(request.route, dict(request.params), reply.status, reply.body))
        return replies

    def pages(self, first: list[Call], label: str, following: Callable[[Call, Reply], Call | None]) -> list[list[Reply]]:
        """Paged lists: the first pages in parallel, then each list's next page (``following``
        gives it, or None at the end) wave by wave. Replies per list, in page order."""
        out: list[list[Reply]] = [[] for _ in first]
        pending = list(enumerate(first))
        for _ in range(PAGE_GUARD):
            if not pending:
                return out
            replies = self.fetch([c for _, c in pending], label)
            nxt = []
            for (index, request), reply in zip(pending, replies):
                out[index].append(reply)
                after = following(request, reply) if reply.status == 200 else None
                if after is not None:
                    nxt.append((index, after))
            pending = nxt
            label = f"{label} (next pages)" if "(next pages)" not in label else label
        raise FetchError(f"{first[0].route}: more than {PAGE_GUARD} pages; stopped")

    def page_size(self, route: str, default: int) -> int:
        return self.page_sizes.get(route, default)

    def windows_by_company(
        self,
        probes: dict[str, Callable[[date, date], Call]],
        latest: Callable[[Reply], date | None],
        problem: Callable[[Reply], str | None] = http_problem,
        finished: Callable[[Reply], str | None] = lambda reply: None,
    ) -> dict[str, list[tuple[date, date]]]:
        """The pay windows of each company for a dated run list (``probes``: company -> call for a
        range). With ``--pay-from``/``--pay-to`` that range (cut to the window size); otherwise a
        backward search: windows of ``WINDOW_DAYS`` back from today until one has a pay date on or
        before today, at most ``SEARCH_WINDOWS``; the window then ends on that date. Each round asks
        every company still searching at once. Probe calls are not stored.

        A failed probe stops that company's search and is reported in ``pay_windows``: ``problem``
        names the failure (by default any HTTP error; PrismHR also an errorCode sent with HTTP 200,
        and not its documented "no records" 404, D-021). An error is never read as "no payroll".
        ``finished`` names an answer that ends the search without a window and is not an error
        (PrismHR: the client has no batches at all, D-097)."""
        if self.pay_window is not None:
            return {company: self.window_ending(company, None, "given") for company in probes}
        found: dict[str, list[tuple[date, date]]] = {}
        pending, end = list(probes), self.today
        for round_number in range(SEARCH_WINDOWS):
            if not pending:
                break
            start = end - timedelta(days=WINDOW_DAYS)
            replies = self.fetch([probes[company](start, end) for company in pending],
                                 f"pay date search, year {round_number + 1} back", store=False)
            still = []
            for company, reply in zip(pending, replies):
                self.probes[company] += 1
                done = finished(reply)
                failure = None if done is not None else problem(reply)
                last = None if done is not None or failure is not None else latest(reply)
                if done is not None:
                    self.windows[company] = {"from": None, "to": None, "basis": done}
                    found[company] = []
                elif failure is not None:
                    self.windows[company] = {"from": None, "to": None, "basis": f"search stopped: {failure}"}
                    found[company] = []
                elif last is not None:
                    found[company] = self.window_ending(company, last, "latest pay date")
                else:
                    still.append(company)
            pending, end = still, start - timedelta(days=1)
        for company in pending:
            self.windows[company] = {"from": None, "to": None, "basis": f"no pay date in {SEARCH_WINDOWS} windows back from {self.today}"}
            found[company] = []
        return {company: found[company] for company in probes}

    def window_ending(self, company: str, last: date | None, basis: str) -> list[tuple[date, date]]:
        """The window of ``WINDOW_DAYS`` ending on ``last`` (the given range when set)."""
        if self.pay_window is not None:
            self.windows[company] = {"from": self.pay_window[0].isoformat(), "to": self.pay_window[1].isoformat(), "basis": "given"}
            return windows(*self.pay_window)
        if last is None:
            self.windows[company] = {"from": None, "to": None, "basis": f"no {basis} on or before {self.today}"}
            return []
        start = last - timedelta(days=WINDOW_DAYS)
        self.windows[company] = {"from": start.isoformat(), "to": last.isoformat(), "basis": basis}
        return [(start, last)]


@dataclass(frozen=True)
class Fetched:
    bundle: Bundle
    report: dict[str, Any]


def fetch_tenant(
    session: Session,
    today: date | None = None,
    companies: Iterable[str] | None = None,
    pay_window: tuple[date, date] | None = None,
    workers: int = 4,
    page_sizes: dict[str, int] | None = None,
    progress: Callable[[str], None] = lambda line: None,
) -> Fetched:
    """Crawl the signed-in tenant with its provider's plan; the bundle and the fetch report."""
    started = time.monotonic()
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    today = today or date.today()
    crawl = Crawl(session, today, companies, pay_window, workers, page_sizes, progress)
    plan = import_module(PLANS[session.provider], __package__)
    crawl.prefix = getattr(plan, "PATH_PREFIX", "")
    plan.crawl(crawl)
    if not session.tenant_id:
        raise FetchError("sign-in returned no tenant_id")
    bundle = Bundle(Provider(session.provider), session.tenant_id, tuple(crawl.responses))
    report = {
        "tenant": session.tenant,
        "fetched_at": fetched_at,
        "today": today.isoformat(),
        "companies": crawl.chosen,
        "pay_windows": crawl.windows,
        "window_search_calls": dict(crawl.probes),
        "calls": sum(crawl.statuses.values()),
        "statuses": dict(sorted(crawl.statuses.items())),
        "unanswered": dict(sorted(crawl.unanswered.items())),
        "sign_ins": session.sign_ins,
        "seconds": round(time.monotonic() - started, 1),
    }
    return Fetched(bundle, report)


# Credentials inside strings, URLs included: JWT-shaped tokens and token-like query parameters
# (UKG photo_href ".../fs?ticket=<JWT>", D-072). Applied to a saved bundle only.
_JWT = re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}(?:\.[A-Za-z0-9_-]*)?")
_TOKEN_PARAM = re.compile(r"([?&](?:ticket|token|access_token|id_token|sessionid|session_id|sig|signature|apikey|api_key|key)=)[^&#\s\"']+", re.I)


def scrub(text: str) -> str:
    return _TOKEN_PARAM.sub(r"\1REDACTED", _JWT.sub("REDACTED", text))


def _json(value: Any, indent: str = "") -> str:
    """JSON text with Decimals written exactly as numbers (the bundle is read back with
    parse_source_json) and every string scrubbed of credentials."""
    inner = indent + "  "
    if isinstance(value, dict):
        if not value:
            return "{}"
        parts = [f"{inner}{json.dumps(scrub(str(k)), ensure_ascii=False)}: {_json(v, inner)}" for k, v in value.items()]
        return "{\n" + ",\n".join(parts) + "\n" + indent + "}"
    if isinstance(value, (list, tuple)):
        if not value:
            return "[]"
        return "[\n" + ",\n".join(inner + _json(v, inner) for v in value) + "\n" + indent + "]"
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, str):
        return json.dumps(scrub(value), ensure_ascii=False)
    return json.dumps(value)


def bundle_text(bundle: Bundle, report: dict[str, Any]) -> str:
    """A fetched bundle in the fixture format (D-080), readable by ``normalize --input``."""
    data = {
        "format": FORMAT,
        "provider": bundle.provider.value,
        "tenant_id": bundle.tenant_id,
        "live": {"tenant": report["tenant"], "fetched_at": report["fetched_at"], "today": report["today"],
                 "note": "Live demo data: personal data, keep out of Git (D-009). Credential-like strings are scrubbed."},
        "responses": [{"route": r.route, "params": r.params, "status": r.status, "body": r.body} for r in bundle.responses],
    }
    return _json(data) + "\n"
