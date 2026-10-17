"""PrismHR crawl plan (D-092): clients, then per client its codes, schedule, employees, retirement
loans and payroll batches in the pay window, then per employee the employee, deduction and
benefit routes.

- Clients come from ``getClientList`` (the company source, D-034); ``--company`` narrows them.
- Success is HTTP 200 with errorCode 0 (D-021); other answers are stored and the adapters apply it.
- The batch list needs a date range: the pay window comes from a backward search over completed
  (``COMP``) batches (D-092 review), then one stored list call. Every listed batch gets its info
  and its voucher pages (``count`` per page, ``startpage`` a page index from 0, until ``total``,
  D-022; discovery: client 136 batch 202537, total 66, page 1 held the last 16).
- ``getEmployeePremium`` is asked per enrolled plan with the fetch date as ``effectiveDate``.
"""
from datetime import date

from ..fetch import Call, Crawl, call, day, items, text_ids

PROVIDER = "prismhr"
CLIENTS = "/clientMaster/v1/getClientList"
MASTER = "/clientMaster/v1/getClientMaster"
CODES = "/clientMaster/v1/getClientCodes"
SCHEDULE = "/clientMaster/v1/getPayrollSchedule"
EMPLOYEES = "/employee/v1/getEmployeeList"
EMPLOYEE = "/employee/v1/getEmployee"
RETIREMENT_LOANS = "/benefits/v1/getRetirementLoans"
PLANS = "/benefits/v1/getBenefitPlans"
PREMIUM = "/benefits/v1/getEmployeePremium"
BATCHES = "/payroll/v1/getBatchListByDate"
BATCH_INFO = "/payroll/v1/getBatchInfo"
VOUCHERS = "/payroll/v1/getPayrollVoucherForBatch"
# The per-employee routes called with clientId and employeeId (plus QUERY), in this order.
PER_EMPLOYEE = (
    EMPLOYEE, "/employee/v1/getAddressInfo", "/employee/v1/getHistory", "/employee/v1/getPayRateHistory",
    "/employee/v1/getStatusHistoryForAdjustment", "/employee/v1/getPositionRate", "/benefits/v1/getPaidTimeOff",
    "/benefits/v1/getDependents", "/payroll/v1/getEmployeeOverrideRates", "/deductions/v1/getDeductions",
    "/employee/v1/getScheduledDeductions", "/deductions/v1/getEmployeeLoans", "/deductions/v1/getDeductionArrears",
    "/deductions/v1/getGarnishmentDetails", "/employee/v1/checkForGarnishments", PLANS,
)
ROUTES = frozenset({CLIENTS, MASTER, CODES, SCHEDULE, EMPLOYEES, RETIREMENT_LOANS, PREMIUM, BATCHES, BATCH_INFO, VOUCHERS, *PER_EMPLOYEE})

# Fixed query parameters (discovery call log): all 14 getEmployee options, the client code tables
# the adapters label from, the voucher blocks for employer and retirement amounts; getDeductions and
# getDeductionArrears document "send empty String" for options.
QUERY: dict[str, dict[str, str]] = {
    EMPLOYEE: {"options": "Person,Client,Compensation,DirectDeposit,EmployeeEvents,Health,Skills,AbsenceJournal,"
                          "BenefitEnrollStatus,ScheduledDeductions,NewHireQuestions,EnrollmentInprogress,ContactInformation,HSA"},
    CODES: {"options": "Deduction,Pay,Status,Type,PGroups,Department,Division,Location,Job,Reason,Union,Workgroup,"
                       "BenefitGroup,RetirementPlan,Ethnic,Relation,PositionClass,Shift"},
    "/deductions/v1/getDeductions": {"options": ""},
    "/deductions/v1/getDeductionArrears": {"options": ""},
    BATCHES: {"dateType": "PAY"},
    VOUCHERS: {"options": "EmployerContribution,Retirement"},
}
PAGE_SIZES = {VOUCHERS: 50}


def q(route: str, **params) -> Call:
    return call(route, **params, **QUERY.get(route, {}))


def _ok(body) -> bool:
    return isinstance(body, dict) and str(body.get("errorCode", "0")) == "0"


def batch_call(client: str, start: date, end: date) -> Call:
    return q(BATCHES, clientId=client, startDate=start.isoformat(), endDate=end.isoformat())


def error_code(reply) -> str | None:
    """Why a batch list probe failed, or None (D-021). A 404 with errorCode 404 whose message says
    no batches were found is PrismHR's "no records" answer, an empty window (live, client 103: "No
    batches could be found for the date range specified"), so the search steps back. Any other
    404 (such as "Client not found"), any other status, or an errorCode sent with HTTP 200 stops it."""
    body = reply.body if isinstance(reply.body, dict) else {}
    code = str(body.get("errorCode")) if body else "missing"
    message = str(body.get("errorMessage") or "")
    if reply.status == 404 and code == "404" and message.startswith("No batches could be found"):
        return None
    if reply.status != 200:
        return f"HTTP {reply.status}"
    return None if code == "0" else f"errorCode {code}"


def no_batches(reply) -> str | None:
    """PrismHR's answer for a client that has never run payroll: HTTP 400, errorCode 400,
    'No batches exist for client "145."' (live: 12 clients, 11 without employees and client 127
    with 5). Not an error and not worth searching further back (D-097)."""
    body = reply.body if isinstance(reply.body, dict) else {}
    if reply.status == 400 and str(body.get("errorCode")) == "400" and str(body.get("errorMessage") or "").startswith("No batches exist for client"):
        return "no batches: the client has never run payroll"
    return None


def latest_completed(today: date):
    """The latest pay date of a completed (COMP) batch on or before ``today`` in a batch list reply."""
    def latest(reply) -> date | None:
        if not _ok(reply.body):
            return None
        dates = [day(b.get("payDate")) for b in items(reply.body, "batchList") if isinstance(b, dict) and b.get("batchStatus") == "COMP"]
        dates = [d for d in dates if d is not None and d <= today]
        return max(dates, default=None)
    return latest


def voucher_call(client: str, batch: str, size: int, page: int) -> Call:
    return q(VOUCHERS, clientId=client, batchId=batch, count=size, startpage=page)


def crawl(c: Crawl) -> None:
    listing = c.fetch([q(CLIENTS)], "client list")[0]
    found = text_ids(item.get("clientId") for item in items(listing.body, "clientListResult", "clientList") if isinstance(item, dict))
    clients = c.wanted(found)
    per_client = [q(route, clientId=client) for client in clients for route in (MASTER, CODES, SCHEDULE, EMPLOYEES, RETIREMENT_LOANS)]
    replies = dict(zip([(r.route, r.params["clientId"]) for r in per_client], c.fetch(per_client, "client records")))

    probes = {client: (lambda s, e, client=client: batch_call(client, s, e)) for client in clients}
    found = c.windows_by_company(probes, latest_completed(c.today), error_code, no_batches)
    lists = [batch_call(client, start, end) for client in clients for start, end in found[client]]
    batch_lists = c.fetch(lists, "batch lists")

    employees = [(client, employee) for client in clients
                 for employee in text_ids(items(replies[(EMPLOYEES, client)].body, "employeeList", "employeeId"))]
    calls = [q(route, clientId=client, employeeId=employee) for client, employee in employees for route in PER_EMPLOYEE]
    employee_replies = c.fetch(calls, f"employee records ({len(employees)} employees)")
    premiums = []
    for request, reply in zip(calls, employee_replies):
        if request.route == PLANS and _ok(reply.body):
            for plan in text_ids(p.get("planId") for p in items(reply.body, "benefitPlan") if isinstance(p, dict)):
                premiums.append(q(PREMIUM, clientId=request.params["clientId"], employeeId=request.params["employeeId"],
                                  effectiveDate=c.today.isoformat(), planId=plan))
    c.fetch(premiums, "plan premiums")

    batches = []
    for request, reply in zip(lists, batch_lists):
        if _ok(reply.body):
            client = request.params["clientId"]
            batches += [(client, b) for b in text_ids(i.get("batchId") for i in items(reply.body, "batchList") if isinstance(i, dict))]
    batches = list(dict.fromkeys(batches))  # windows given by --pay-from/--pay-to may overlap at a boundary
    c.fetch([q(BATCH_INFO, clientId=client, batchId=batch) for client, batch in batches], "batch details")
    size = c.page_size(VOUCHERS, PAGE_SIZES[VOUCHERS])

    def following(request: Call, reply) -> Call | None:
        page = int(request.params["startpage"])
        try:
            total = int(float(str(reply.body.get("total") or 0))) if _ok(reply.body) else 0
        except ValueError:
            return None
        return voucher_call(request.params["clientId"], request.params["batchId"], size, page + 1) if (page + 1) * size < total else None

    c.pages([voucher_call(client, batch, size, 0) for client, batch in batches], "voucher pages", following)
