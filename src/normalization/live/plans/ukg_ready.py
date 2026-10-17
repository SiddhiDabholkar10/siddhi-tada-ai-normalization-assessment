"""UKG Ready crawl plan (D-092): company lookups and employees, per employee the detail and 17
sub-routes, then payrolls in the pay window with their detail, batches and pay statements.

- The company id comes from sign-in (``context.companies[].company_id``, D-029); ``--company``
  narrows. Calls go to ``{base_url}/rest/v2/...`` (Foundations.html, confirmed in discovery).
- Cost center trees are asked for each documented ``tree_index`` (0 to 8); unused trees answer 400.
- The deprecated direct-deposits route is sent its ``X-End-of-Support-Timeline`` header (D-030).
- The payroll list takes a range shorter than one year: the window comes from a backward search
  over listed payrolls (all OPEN, D-030, so no status filter) with a pay date on or before today
  (D-092 review), then one stored list call. Throttling: 500 calls per rolling 60 s for small
  companies (Limits.html); the fetch caps itself at 450.
"""
from datetime import date

from ..fetch import Call, Crawl, call, day, items, text_ids

PROVIDER = "ukg-ready"
PATH_PREFIX = "/rest"
RATE_LIMIT = (450, 60.0)
C = "/v2/companies/{cid}"
E = C + "/employees/{aid}"
LOOKUPS = tuple(C + "/lookup/" + name for name in ("eins", "deduction-codes", "earning-codes", "jobs", "employee-types", "pay-types", "pay-period-profiles"))
COST_CENTERS = C + "/config/cost-centers"
EMPLOYEES = C + "/employees"
DETAIL = E
DEPOSITS = E + "/direct-deposits"
PER_EMPLOYEE = (DETAIL, *(E + "/" + name for name in (
    "demographics", "pay-info", "profiles", "compensation/history", "compensation/total", "compensation/additional", "contacts",
    "tax-info", "skills", "training/certifications", "badges", "hr-custom-fields", "accrual/1/balances", "accrual/2/balances",
    "direct-deposits", "benefits")))
PAYROLLS = C + "/payrolls"
PAYROLL = C + "/payrolls/{id}"
BATCHES = PAYROLL + "/batches"
STATEMENTS = PAYROLL + "/pay-statements"
STATEMENT = PAYROLL + "/pay-statements/{id}"
ROUTES = frozenset({*LOOKUPS, COST_CENTERS, EMPLOYEES, *PER_EMPLOYEE, PAYROLLS, PAYROLL, BATCHES, STATEMENTS, STATEMENT})
TREES = range(9)  # tree_index 0 to 8 (cost centers page)
HEADERS = {DEPOSITS: {"X-End-of-Support-Timeline": "2026-01-29"}}  # documented default date
QUERY: dict[str, dict[str, str]] = {}
PAGE_SIZES: dict[str, int] = {}


def payroll_list(cid: str, start: date, end: date) -> Call:
    return call(PAYROLLS, cid=cid, pay_date_from=start.isoformat(), pay_date_to=end.isoformat())


def latest_payroll(today: date):
    def latest(reply) -> date | None:
        dates = [day(p.get("pay_date")) for p in items(reply.body, "payrolls") if isinstance(p, dict)]
        return max((d for d in dates if d is not None and d <= today), default=None)
    return latest


def crawl(c: Crawl) -> None:
    cids = c.wanted(text_ids(company.get("company_id") for company in c.session.companies if isinstance(company, dict)))
    company_calls = [call(route, cid=cid) for cid in cids for route in LOOKUPS]
    company_calls += [call(COST_CENTERS, cid=cid, tree_index=tree) for cid in cids for tree in TREES]
    company_calls += [call(EMPLOYEES, cid=cid) for cid in cids]
    replies = c.fetch(company_calls, "company lookups and employee lists")
    employees = [(request.params["cid"], aid) for request, reply in zip(company_calls, replies)
                 if request.route == EMPLOYEES and reply.status == 200
                 for aid in text_ids(e.get("id") for e in items(reply.body, "employees") if isinstance(e, dict))]

    found = c.windows_by_company({cid: (lambda s, e, cid=cid: payroll_list(cid, s, e)) for cid in cids}, latest_payroll(c.today))
    lists = [payroll_list(cid, start, end) for cid in cids for start, end in found[cid]]
    payroll_lists = c.fetch(lists, "payroll lists")

    c.fetch([call(route, HEADERS.get(route), cid=cid, aid=aid) for cid, aid in employees for route in PER_EMPLOYEE],
            f"employee records ({len(employees)} employees)")

    payrolls = list(dict.fromkeys((request.params["cid"], pid) for request, reply in zip(lists, payroll_lists) if reply.status == 200
                                  for pid in text_ids(p.get("id") for p in items(reply.body, "payrolls") if isinstance(p, dict))))
    per_payroll = [call(route, cid=cid, id=pid) for cid, pid in payrolls for route in (PAYROLL, BATCHES, STATEMENTS)]
    payroll_replies = c.fetch(per_payroll, f"payrolls ({len(payrolls)})")
    statements = [call(STATEMENT, cid=request.params["cid"], payroll_id=request.params["id"], id=sid)
                  for request, reply in zip(per_payroll, payroll_replies) if request.route == STATEMENTS and reply.status == 200
                  for sid in text_ids(s.get("id") for s in items(reply.body, "pay_statements") if isinstance(s, dict))]
    c.fetch(statements, "pay statements")
