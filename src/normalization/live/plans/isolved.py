"""isolved crawl plan (D-092): clients, their legals (the companies, D-034) and pay item catalog;
per legal the employee lists, pay items, run history and checks in the pay window; per employee
the detail and 18 sub-routes; per check its detail.

- Lists are paged with a zero-based ``page`` (checks: ``filter.page``) and read until
  ``totalPages`` (D-013, D-057); the first page is sent as page 0 so every page is named.
- 401s on some routes are permission limits (D-012); a 404 is stored and read per D-011.
- The run history route takes no dates: the pay window ends on the latest pay date of a completed
  run ("Completed Payroll Run") on or before today. Live, 195 of 231 runs are "Payroll Not
  Processed", dated up to 2026, and the 36 completed runs are all 2018 (D-014).
"""
from datetime import date

from ..fetch import Call, Crawl, call, day, items, text_ids

PROVIDER = "isolved"
API = "/api/clients/{clientId}/legals/{legalId}"
EMP = API + "/employees/{employeeId}"
CLIENTS = "/api/clients"
LEGALS = "/api/clients/{clientId}/legals"
CATALOG = "/api/clients/{clientId}/payItems"
MISC = API + "/miscellaneousFields"
EMPLOYEES = API + "/employees"
SSN = API + "/employeesWithSSN"
LEGAL_ITEMS = API + "/payItems"
RUNS = API + "/paygroupId/{paygroupId}/payrollRunHistory"
CHECKS = API + "/checks"
CHECK = EMP + "/checks/{id}"
DETAIL = API + "/employees/{id}"
PER_EMPLOYEE = tuple(EMP + "/" + name for name in (
    "statuses", "categories", "jobs", "payRates", "salaries", "veteranStatus", "contacts", "accruals", "skills", "education",
    "certifications", "training", "priorEmployment", "i9/status", "directdeposits", "payItems", "garnishments", "benefits"))
ROUTES = frozenset({CLIENTS, LEGALS, CATALOG, MISC, EMPLOYEES, SSN, LEGAL_ITEMS, RUNS, CHECKS, CHECK, DETAIL, *PER_EMPLOYEE})

# Fixed query parameters (routes.json notes and the discovery call log).
QUERY: dict[str, dict[str, str]] = {
    LEGALS: {"includeDetails": "true"},
    EMPLOYEES: {"includeMiscFields": "true", "includeLabors": "true", "includeOrganizations": "true",
                "includeAlternateRates": "true", "includeTaxes": "true"},
    DETAIL: {"includeI9Details": "true", "includeMiscDataSets": "true"},
    EMP + "/benefits": {"includeDetails": "true"},
    CHECKS: {"includeDetails": "true"},
    CHECK: {"includeLaborDetails": "true"},
}
PAGE_SIZES = {CLIENTS: 100, EMPLOYEES: 100, SSN: 100, CHECKS: 100}
COMPLETED = "Completed Payroll Run"


def q(route: str, **params) -> Call:
    return call(route, **params, **QUERY.get(route, {}))


def first_page(c: Crawl, route: str, **params) -> Call:
    """Page 0 of a paged list (the legal pay item list documents ``page`` but no size)."""
    if route == CHECKS:
        return q(route, **params, **{"filter.page": 0, "filter.pageSize": c.page_size(route, PAGE_SIZES[route])})
    size = {"pageSize": c.page_size(route, PAGE_SIZES[route])} if route in PAGE_SIZES else {}
    return q(route, **params, page=0, **size)


def following(request: Call, reply) -> Call | None:
    """The next page while ``page + 1 < totalPages``."""
    key = "filter.page" if request.route == CHECKS else "page"
    page = int(request.params[key])
    try:
        pages = int(float(str(reply.body.get("totalPages") or 0)))
    except (AttributeError, ValueError):
        return None
    return Call(request.route, {**request.params, key: str(page + 1)}, dict(request.headers)) if page + 1 < pages else None


def results(page_replies) -> list[dict]:
    return [item for reply in page_replies if reply.status == 200 for item in items(reply.body, "results") if isinstance(item, dict)]


def latest_completed(replies, today: date) -> date | None:
    dates = [day(run.get("payDate")) for reply in replies if reply.status == 200
             for run in (reply.body if isinstance(reply.body, list) else []) if isinstance(run, dict) and run.get("status") == COMPLETED]
    return max((d for d in dates if d is not None and d <= today), default=None)


def crawl(c: Crawl) -> None:
    clients = text_ids(item.get("id") for item in results(c.pages([first_page(c, CLIENTS)], "client list", following)[0]))
    per_client = [q(route, clientId=client) for client in clients for route in (LEGALS, CATALOG)]
    client_replies = c.fetch(per_client, "legals and pay item catalogs")
    legals_found = {}
    for request, reply in zip(per_client, client_replies):
        if request.route == LEGALS and reply.status == 200 and isinstance(reply.body, list):
            for legal in reply.body:
                if isinstance(legal, dict) and legal.get("id") is not None:
                    legals_found[str(legal["id"])] = (request.params["clientId"], legal)
    legals = [(legals_found[lid][0], lid, legals_found[lid][1]) for lid in c.wanted(list(legals_found))]

    c.fetch([q(MISC, clientId=client, legalId=legal) for client, legal, _ in legals], "legal fields")
    paged = [first_page(c, route, clientId=client, legalId=legal) for client, legal, _ in legals for route in (EMPLOYEES, SSN, LEGAL_ITEMS)]
    pages = c.pages(paged, "employee and pay item lists", following)
    employees = [(request.params["clientId"], request.params["legalId"], str(item["id"]))
                 for request, replies in zip(paged, pages) if request.route == EMPLOYEES
                 for item in results(replies) if item.get("id") is not None]
    employees = list(dict.fromkeys(employees))

    run_calls = {legal: [q(RUNS, clientId=client, legalId=legal, paygroupId=group)
                         for group in text_ids(g.get("id") for g in items(record, "payGroups") if isinstance(g, dict))]
                 for client, legal, record in legals}
    run_replies = c.fetch([r for calls in run_calls.values() for r in calls], "run histories")
    by_legal, at = {}, 0
    for legal, calls in run_calls.items():
        by_legal[legal], at = run_replies[at:at + len(calls)], at + len(calls)
    check_lists = []
    for client, legal, _ in legals:
        for start, end in c.window_ending(legal, latest_completed(by_legal[legal], c.today), "latest completed run"):
            check_lists.append(first_page(c, CHECKS, clientId=client, legalId=legal,
                                          **{"filter.fromDate": start.isoformat(), "filter.toDate": end.isoformat()}))

    calls = []
    for client, legal, employee in employees:
        calls.append(q(DETAIL, clientId=client, legalId=legal, id=employee))
        calls += [q(route, clientId=client, legalId=legal, employeeId=employee) for route in PER_EMPLOYEE]
    c.fetch(calls, f"employee records ({len(employees)} employees)")

    check_pages = c.pages(check_lists, "check lists", following)
    checks = [(request.params["clientId"], request.params["legalId"], str(item["employeeId"]), str(item["id"]))
              for request, replies in zip(check_lists, check_pages)
              for item in results(replies) if item.get("id") is not None and item.get("employeeId") is not None]
    checks = list(dict.fromkeys(checks))
    c.fetch([q(CHECK, clientId=client, legalId=legal, employeeId=employee, id=check) for client, legal, employee, check in checks],
            "check details")
