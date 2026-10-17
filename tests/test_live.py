"""Live fetch (D-092), with no network: a fake provider serves each fixture bundle.

The fixtures record every call exactly as the live fetch sends it (route, path values, query), so
a crawl of the fake tenant must ask for every fixture response and its bundle must normalize to the
golden output. Calls the fixtures leave out on purpose are answered 404 by the fake, counted per
route against EXPECTED_UNSERVED, and dropped before normalizing.
"""
import io
import json
import re
import tempfile
import unittest
import urllib.parse
from collections import Counter
from contextlib import redirect_stderr
from datetime import date
from pathlib import Path
from unittest import mock

from normalization.__main__ import main, write_new
from normalization.employees.bundle import Bundle, load_bundle
from normalization.fixtures.common import FETCH_DATE, PAGE_SIZES
from normalization.live import client as live_client
from normalization.live.client import Session
from normalization.live.fetch import PLANS, fetch_tenant, split_url
from normalization.output import build_document
from normalization.pipeline import normalize_bundle
from importlib import import_module

ROOT = Path(__file__).resolve().parents[1]
TENANT = {"prismhr": "prism", "isolved": "isol", "ukg-ready": "ukg"}
SIGNIN = {  # what the sign-in service returns per tenant (organizer README), with a fake token
    "prismhr": ({"sessionId": "FAKE-SESSION-1234567890"}, {"header_name": "sessionId", "header_prefix": ""},
                [{"client_id": "1001"}]),
    "isolved": ({"access_token": "FAKE-ACCESS-1234567890", "refresh_token": "FAKE-REFRESH-0987654321", "expires_in": 299},
                {"header_name": "Authorization", "header_prefix": "bearer "}, [{"client_id": "5001", "legal_id": "6001"}]),
    "ukg-ready": ({"access_token": "FAKE-ACCESS-UKG-123456", "expires_in": 3600},
                  {"header_name": "Authorization", "header_prefix": "Bearer "}, [{"company_id": "7001"}]),
}
# Calls the crawl makes that the fixtures leave out on purpose, per route.
EXPECTED_UNSERVED = {
    "prismhr": {
        # The pending client 1002 has only its master in the fixture (source_unavailable case).
        "/clientMaster/v1/getClientCodes": 1, "/clientMaster/v1/getPayrollSchedule": 1, "/employee/v1/getEmployeeList": 1,
        "/benefits/v1/getRetirementLoans": 1, "/payroll/v1/getBatchListByDate": 1,
        "/payroll/v1/getBatchInfo": 1,  # batch 20250207-S1 has no getBatchInfo on purpose
        "/benefits/v1/getEmployeePremium": 6,  # recorded for 2 of the 8 enrolled plans (P00001 MED1, LTD1)
    },
    "isolved": {},
    "ukg-ready": {
        "/v2/companies/{cid}/config/cost-centers": 6,  # trees 3 to 8: the fixture has trees 0 to 2
        "/v2/companies/{cid}/payrolls/{id}": 1,  # payroll 3004 has no detail on purpose
        "/v2/companies/{cid}/payrolls/{id}/batches": 3,  # batches only for payroll 3001
    },
}
NOT_SERVED = {"replay": "not in the fixture"}
DATED_LISTS = {  # run lists the window search probes with any range: (route, id parameter, list key, date field, from, to)
    "prismhr": ("/payroll/v1/getBatchListByDate", "clientId", "batchList", "payDate", "startDate", "endDate"),
    "ukg-ready": ("/v2/companies/{cid}/payrolls", "cid", "payrolls", "pay_date", "pay_date_from", "pay_date_to"),
}


class FakeProvider:
    """A transport serving one fixture bundle: sign-in, then exact (path, query) matches."""

    def __init__(self, provider: str, clock=None) -> None:
        self.provider = provider
        self.data = json.loads((ROOT / "fixtures" / provider / "bundle.json").read_text(encoding="utf-8"))
        self.plan = import_module(PLANS[provider], "normalization.live")
        self.prefix = getattr(self.plan, "PATH_PREFIX", "")
        self.base = "https://replay.invalid/base"
        auth, usage, companies = SIGNIN[provider]
        self.token = auth.get("access_token") or auth["sessionId"]
        self.signin = {"tenant_id": self.data["tenant_id"], "base_url": self.base, "auth": auth, "usage": usage,
                       "context": {"companies": companies}}
        self.header = (usage["header_name"], usage["header_prefix"] + self.token)
        self.exact = {}
        for index, response in enumerate(self.data["responses"]):
            path, query = split_url(response["route"], response["params"])
            self.exact[(self.prefix + path, frozenset(query.items()))] = index
        self.served: set[int] = set()
        self.unserved: Counter = Counter()
        self.templates = [(route, re.compile("^" + re.escape(self.prefix) + re.sub(r"\\\{\w+\\\}", "[^/]+", re.escape(route)) + "$"))
                          for route in self.plan.ROUTES]

    def route_of(self, path: str) -> str:
        return next(route for route, regex in self.templates if regex.match(path))

    def __call__(self, method, url, headers, body, timeout):
        if url == live_client.SIGNIN_URL:
            return 200, json.dumps(self.signin).encode(), {}
        assert headers.get(self.header[0]) == self.header[1], "auth header from sign-in usage (D-005)"
        parts = urllib.parse.urlsplit(url)
        assert url.startswith(self.base), "base URL from sign-in (D-004)"
        path = parts.path[len(urllib.parse.urlsplit(self.base).path):]
        query = dict(urllib.parse.parse_qsl(parts.query, keep_blank_values=True))
        index = self.exact.get((path, frozenset(query.items())))
        if index is not None:
            self.served.add(index)
            response = self.data["responses"][index]
            return response["status"], json.dumps(response["body"]).encode(), {}
        route = self.route_of(path)
        dated = self.dated(route, query)
        if dated is not None:
            return 200, json.dumps(dated).encode(), {}
        self.unserved[route] += 1
        return 404, json.dumps(NOT_SERVED).encode(), {}

    def dated(self, route: str, query: dict):
        """A window search probe: the fixture's run list cut to the asked range."""
        spec = DATED_LISTS.get(self.provider)
        if spec is None or route != spec[0]:
            return None
        _, id_name, key, field, start, end = spec
        for response in self.data["responses"]:
            # PrismHR names the client in the query; UKG's company is in the path (one company).
            if response["route"] == route and response["params"].get(id_name) == query.get(id_name, response["params"].get(id_name)):
                body = dict(response["body"])
                body[key] = [item for item in body[key] if query[start] <= str(item[field])[:10] <= query[end]]
                return body
        return None


def crawl(provider: str, fake: FakeProvider):
    session = Session(TENANT[provider], "fake-key", transport=fake)
    lines: list[str] = []
    fetched = fetch_tenant(session, FETCH_DATE, workers=4, page_sizes=PAGE_SIZES[provider], progress=lines.append)
    return session, fetched, lines


class FixtureReplay(unittest.TestCase):
    def test_crawl_of_the_fixture_tenant_matches_the_golden(self):
        """Every fixture response is asked for, extra calls are only the pinned ones, and the
        crawled bundle normalizes to the golden document. No token leaves the session."""
        for provider in TENANT:
            with self.subTest(provider=provider):
                fake = FakeProvider(provider)
                session, fetched, lines = crawl(provider, fake)
                missing = [(r["route"], r["params"]) for i, r in enumerate(fake.data["responses"]) if i not in fake.served]
                self.assertEqual(missing, [], "fixture responses the crawl never asked for")
                self.assertEqual(dict(fake.unserved), EXPECTED_UNSERVED[provider])
                kept = tuple(r for r in fetched.bundle.responses if r.body != NOT_SERVED)
                self.assertEqual(len(kept), len(fake.data["responses"]), "stored once each; window search probes never stored")
                bundle = Bundle(fetched.bundle.provider, fetched.bundle.tenant_id, kept)
                golden = json.loads((ROOT / "tests" / "golden" / f"{provider}.json").read_text(encoding="utf-8"))
                document = build_document(normalize_bundle(bundle), golden["run"]["input"], show_sensitive=True)
                self.assertEqual(document, golden)
                self.assertTrue(fetched.report["pay_windows"], "a pay window was found")
                exposed = json.dumps([[r.params, str(r.body)] for r in fetched.bundle.responses]) + json.dumps(fetched.report) + "".join(lines) + repr(session)
                self.assertNotIn(fake.token, exposed)

    def test_fetch_command_writes_masked_output_and_a_bundle_that_normalizes_again(self):
        """The command end to end on the fake UKG tenant: masked by default, run.fetch present,
        no token anywhere, and the saved bundle gives the same records through normalize."""
        fake = FakeProvider("ukg-ready")
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(live_client, "urllib_transport", fake), \
                mock.patch.dict("os.environ", {live_client.KEY_NAME: "fake-key"}):
            out = Path(tmp) / "ukg.json"
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                code = main(["fetch", "--tenant", "ukg", "--as-of", FETCH_DATE.isoformat(), "--output", str(out), "--save-bundle"])
            self.assertEqual(code, 0, stderr.getvalue())
            document = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(document["run"]["sensitive_values"], "masked")
            self.assertEqual(document["run"]["input"], "live:ukg")
            self.assertEqual(document["run"]["fetch"]["pay_windows"]["7001"]["basis"], "latest pay date")
            saved = out.with_name("ukg.bundle.json")
            for text in (out.read_text(encoding="utf-8"), saved.read_text(encoding="utf-8"), stderr.getvalue()):
                self.assertNotIn(fake.token, text)
            # A credential inside a response body (the fixture's photo_href ticket) is scrubbed (D-072).
            self.assertIn("ticket=SECRET", json.dumps(fake.data))
            self.assertNotIn("ticket=SECRET", saved.read_text(encoding="utf-8"))
            self.assertIn("ticket=REDACTED", saved.read_text(encoding="utf-8"))
            # Progress gives counts only: neither the tenant id nor the company id.
            for identifier in (fake.data["tenant_id"], "7001"):
                self.assertNotRegex(stderr.getvalue(), rf"\b{identifier}\b")
            again = build_document(normalize_bundle(load_bundle(saved)), "live:ukg")
            self.assertEqual({k: v for k, v in again.items() if k != "run"}, {k: v for k, v in document.items() if k != "run"})
        with self.subTest("a failed write leaves no file behind"), tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "out.json"
            with self.assertRaises(FileExistsError):
                write_new([(first, "{}"), (first, "{}")])  # the second file cannot be created
            self.assertFalse(first.exists())


class ErrorProbes(FakeProvider):
    """PrismHR answering client 1001's window search probes with HTTP 200 and a nonzero errorCode."""

    def dated(self, route, query):
        if query.get("clientId") == "1001":
            return {"errorCode": "5", "errorMessage": "Session problem", "batchList": []}
        return super().dated(route, query)


class NoBatches(FakeProvider):
    """PrismHR answering client 1001's batch lists as live does for a client that never ran payroll."""

    def __call__(self, method, url, headers, body, timeout):
        if "getBatchListByDate" in url and "clientId=1001" in url:
            return 400, json.dumps({"errorCode": "400", "errorMessage": 'No batches exist for client "1001."'}).encode(), {}
        return super().__call__(method, url, headers, body, timeout)


class NoRecordWindows(FakeProvider):
    """PrismHR answering an empty window as live does: HTTP 404 with errorCode 404 (client 103)."""

    message = "No batches could be found for the date range specified."

    def __call__(self, method, url, headers, body, timeout):
        status, raw, response_headers = super().__call__(method, url, headers, body, timeout)
        reply = json.loads(raw)
        if "getBatchListByDate" in url and isinstance(reply, dict) and reply.get("batchList") == []:
            return 404, json.dumps({"errorCode": "404", "errorMessage": self.message}).encode(), {}
        return status, raw, response_headers


class ClientNotFound(NoRecordWindows):
    """The same 404 and errorCode with a message that does not say "no records"."""

    message = "Client not found."


class WindowSearch(unittest.TestCase):
    def test_window_search_stops_on_a_provider_error(self):
        """A failed probe stops the search and is reported; it is never read as "no payroll"
        (HTTP errors, and PrismHR errorCode with HTTP 200, D-021)."""
        fake = ErrorProbes("prismhr")
        _, fetched, _ = crawl("prismhr", fake)
        windows = fetched.report["pay_windows"]
        self.assertEqual(windows["1001"]["basis"], "search stopped: errorCode 5")
        self.assertEqual(windows["1002"]["basis"], "search stopped: HTTP 404")  # the pending client has no batch list
        self.assertEqual(fetched.report["window_search_calls"], {"1001": 1, "1002": 1})
        self.assertFalse([r for r in fetched.bundle.responses if r.route == "/payroll/v1/getBatchListByDate"])
        with self.subTest("PrismHR's 'no batches exist' 400 ends the search as no payroll, not an error"):
            _, fetched, _ = crawl("prismhr", NoBatches("prismhr"))
            self.assertEqual(fetched.report["pay_windows"]["1001"]["basis"], "no batches: the client has never run payroll")
            self.assertEqual(fetched.report["window_search_calls"]["1001"], 1)
        with self.subTest("PrismHR's no-records 404 is an empty window: the search steps back"):
            _, fetched, _ = crawl("prismhr", NoRecordWindows("prismhr"))
            self.assertEqual(fetched.report["pay_windows"]["1001"]["basis"], "latest pay date")
            self.assertEqual(fetched.report["window_search_calls"]["1001"], 2)
        with self.subTest("any other 404 stops the search (D-021: only a no-records message is empty)"):
            _, fetched, _ = crawl("prismhr", ClientNotFound("prismhr"))
            self.assertEqual(fetched.report["pay_windows"]["1001"]["basis"], "search stopped: HTTP 404")
            self.assertEqual(fetched.report["window_search_calls"]["1001"], 1)


class Script:
    """A transport answering from a script of (status, body, headers) or exceptions, after sign-in."""

    def __init__(self, *answers, expires_in=None):
        self.answers = list(answers)
        self.expires_in = expires_in
        self.sign_ins = 0
        self.seen: list[dict] = []

    def __call__(self, method, url, headers, body, timeout):
        if method == "POST":
            self.sign_ins += 1
            auth = {"access_token": f"FAKE-TOKEN-{self.sign_ins}", **({"expires_in": self.expires_in} if self.expires_in else {})}
            return 200, json.dumps({"tenant_id": "1", "base_url": "https://x.invalid", "auth": auth,
                                    "usage": {"header_name": "Authorization", "header_prefix": "Bearer "}}).encode(), {}
        self.seen.append(dict(headers))
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        status, body, response_headers = answer
        return status, (body if isinstance(body, str) else json.dumps(body)).encode(), response_headers


class Clock:
    def __init__(self):
        self.now, self.slept = 0.0, []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


class Client(unittest.TestCase):
    def test_client_rules(self):
        ok = (200, '{"value": 1.10}', {})
        with self.subTest("a new sign-in 30 s before expiry"):
            clock, script = Clock(), Script(ok, ok, expires_in=299)
            session = Session("isol", "k", transport=script, clock=clock, sleep=clock.sleep)
            session.get("/a")
            clock.now = 270
            reply = session.get("/a")
            self.assertEqual((script.sign_ins, script.seen[-1]["Authorization"]), (2, "Bearer FAKE-TOKEN-2"))
            self.assertEqual(str(reply.body["value"]), "1.10", "bodies read with parse_source_json (D-025)")
        with self.subTest("one new sign-in on a 401, then the 401 is the answer"):
            clock, script = Clock(), Script((401, None, {}), ok, (401, None, {}), (401, None, {}))
            session = Session("ukg", "k", transport=script, clock=clock, sleep=clock.sleep)
            self.assertEqual(session.get("/a").status, 200)
            self.assertEqual(session.get("/b").status, 401)
            self.assertEqual(script.sign_ins, 3)
        with self.subTest("503 waits the advertised time"):
            clock, script = Clock(), Script((503, None, {"X-CallLimit-TimeToWait": "7"}), (429, None, {"Retry-After": "120"}), ok)
            session = Session("ukg", "k", transport=script, clock=clock, sleep=clock.sleep)
            self.assertEqual(session.get("/a").status, 200)
            self.assertEqual(clock.slept, [7.0, 60.0])
        with self.subTest("network errors: 3 tries, then status 0"):
            clock, script = Clock(), Script(OSError("reset"), TimeoutError(), OSError("reset"))
            session = Session("prism", "k", transport=script, clock=clock, sleep=clock.sleep)
            self.assertEqual((session.get("/a").status, len(script.seen)), (0, 3))
        with self.subTest("the rate limit holds calls to the window"):
            clock, script = Clock(), Script(ok, ok, ok)
            session = Session("ukg", "k", transport=script, clock=clock, sleep=clock.sleep, rate_limit=(2, 60.0))
            for _ in range(3):
                session.get("/a")
            self.assertEqual(clock.slept, [60.0])
        with self.subTest("the token is never shown"):
            self.assertNotIn("FAKE-TOKEN", repr(session))


class Plans(unittest.TestCase):
    def test_plans_cover_the_selected_routes(self):
        """Each crawl plan calls exactly its provider's selected routes (routes.json)."""
        for provider, module in PLANS.items():
            with self.subTest(provider=provider):
                selected = json.loads((ROOT / "src" / "normalization" / "mappings" / "data" / provider / "routes.json").read_text(encoding="utf-8"))
                self.assertEqual(set(import_module(module, "normalization.live").ROUTES), {row["route"] for row in selected["selected"]})


if __name__ == "__main__":
    unittest.main()
