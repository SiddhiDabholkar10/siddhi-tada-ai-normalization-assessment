"""Write path (Phase 8, D-100), offline: plans per provider contract, masked previews, and the
UKG-only send through a fake transport (one attempt, new id reported, refused plans never sent).
"""
import json
import logging
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from normalization.app.api import create_app
from normalization.app.store import Store
from normalization.live import client as live_client
from normalization.write import WriteRequest, build
from normalization.write.send import send

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = {p: json.loads((ROOT / "tests" / "golden" / f"{p}.json").read_text(encoding="utf-8")) for p in ("ukg-ready", "isolved", "prismhr")}


def employee(provider, index=0):
    e = GOLDEN[provider]["employees"][index]
    return e, next(c for c in GOLDEN[provider]["companies"] if c["id"] == e["company_id"])


def refused(plan):
    return [r["field"] for r in plan.refusals]


class FakeUKG:
    """Sign-in plus one scripted answer per write; records what was sent."""

    def __init__(self, *answers):
        self.answers, self.sent = list(answers), []

    def __call__(self, method, url, headers, body, timeout):
        if url == live_client.SIGNIN_URL:
            signin = {"tenant_id": "900003", "base_url": "https://ukg.invalid", "auth": {"access_token": "FAKE-TOKEN-123456", "expires_in": 3600},
                      "usage": {"header_name": "Authorization", "header_prefix": "Bearer "}, "context": {"companies": []}}
            return 200, json.dumps(signin).encode(), {}
        self.sent.append((method, url, json.loads(body) if body else None))
        self.types = getattr(self, "types", []) + [headers.get("Content-Type")]
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


class Plans(unittest.TestCase):
    def test_each_provider_request_follows_its_contract_and_rules(self):
        with self.subTest("same provider and company: the record's own codes are reused (update; a create is refused)"):
            e, c = employee("isolved")
            self.assertEqual(refused(build(WriteRequest("isolved", "create", e, c))), ["operation"], "a create would duplicate")
            plan = build(WriteRequest("isolved", "update", e, c))
            self.assertEqual(refused(plan), [])
            raw = next(r["body"]["results"][0] for r in json.loads((ROOT / "fixtures" / "isolved" / "bundle.json").read_text(encoding="utf-8"))["responses"]
                       if r["route"].endswith("/employees") and isinstance(r["body"], dict))
            body = plan.calls[0].body
            for name in ("employmentStatus", "employmentCategoryCode", "payType", "payFrequency", "payGroup", "workLocation", "legalCode"):
                self.assertEqual(body[name], raw[name], name)  # exactly what isolved itself sent
            self.assertEqual((plan.calls[0].path, body["employeeNumber"]), ("/api/clients/5001/updateEmployee", raw["employeeNumber"]))
        with self.subTest("PrismHR: required fields first, import, then commit; a masked SSN is never sent"):
            e, c = employee("prismhr")
            plan = build(WriteRequest("prismhr", "create", e, c, {"company": "1002"}))  # another client of the same provider
            self.assertEqual([(call.method, call.route) for call in plan.calls], [
                ("GET", "/newHire/v1/getNewHireRequiredFields"), ("POST", "/newHire/v1/importEmployees"), ("POST", "/newHire/v1/commitEmployees")])
            self.assertEqual(refused(plan)[0], "ssn", "PrismHR sends SSNs masked (D-020)")
            self.assertIn("peoStartDate", refused(plan), "another client: the record's own PEO start date does not travel")
            self.assertEqual(plan.calls[1].body["sessionId"], "<session>")
            self.assertEqual(plan.calls[2].query["importBatchId"], "<importBatchId from importEmployees>")
        with self.subTest("another provider: each destination code and input is refused until given"):
            e, c = employee("ukg-ready")
            plan = build(WriteRequest("prismhr", "create", e, c))
            self.assertEqual(refused(plan), ["company", "employeeStatusCode", "workLocationCode", "jobCode", "payGroup", "peoStartDate"])
            inputs = {"company": "103", "employment_status": "A", "work_location": "GA", "job": "8603N5", "pay_group": "BW", "peo_start_date": "2024-01-02"}
            given = build(WriteRequest("prismhr", "create", e, c, inputs))
            self.assertEqual(refused(given), [])
            self.assertEqual(given.calls[1].body["newHireEmployee"][0]["peoStartDate"], "2024-01-02", "never the hire date")
            self.assertFalse(given.sendable, "PrismHR is a dry run only")
        with self.subTest("UKG: the username is always an explicit input; update is a JSON Patch on the account"):
            e, c = employee("ukg-ready")
            self.assertEqual(refused(build(WriteRequest("ukg-ready", "create", e, c, {"company": "33704016"}))), ["username"])
            create = build(WriteRequest("ukg-ready", "create", e, c, {"company": "33704016", "username": "new.user"}))
            self.assertTrue(create.sendable)
            self.assertEqual({k: create.calls[0].body[k] for k in ("username", "first_name", "last_name")}, {"username": "new.user", "first_name": "Quinn", "last_name": "Moreau"})
            update = build(WriteRequest("ukg-ready", "update", e, c))
            self.assertEqual((update.calls[0].method, update.calls[0].path), ("PATCH", "/v2/companies/7001/employees/1101"))
            self.assertTrue(all(op["op"] == "add" for op in update.calls[0].body), "add sets a member that may be missing (live 400 on replace)")
        with self.subTest("updates name their target; PrismHR's needs a manager"):
            e, c = employee("prismhr")
            update = build(WriteRequest("prismhr", "update", e, c))
            self.assertEqual(refused(update), [])
            self.assertEqual((update.calls[0].body["employeeId"], update.calls[0].body["manager"] is not None), ("P00001", True))
            e, c = employee("ukg-ready")
            self.assertEqual(refused(build(WriteRequest("isolved", "update", e, c, {"company": "5001"})))[-1], "employeeNumber")

    def test_previews_are_masked_unless_opted_in(self):
        for provider in ("ukg-ready", "isolved"):
            e, c = employee(provider)
            plan = build(WriteRequest(provider, "create", e, c, {"company": "33704016", "username": "new.user"}))
            ssn = next(n["value"] for n in e["national_ids"] if n["value"])
            birth = e["demographics"]["birth_date"]
            masked, shown = json.dumps(plan.view()), json.dumps(plan.view(show_sensitive=True))
            with self.subTest(provider=provider):
                self.assertNotIn(ssn, masked)
                self.assertNotIn(birth, masked)
                self.assertIn("***" + ssn.replace("-", "")[-4:], masked, "SSN keeps its last 4, as the output does")
                self.assertIn(ssn, shown)
                self.assertEqual(plan.view()["sensitive_values"], "masked")


class Sending(unittest.TestCase):
    def test_only_a_ukg_plan_without_refusals_is_sent_once(self):
        e, c = employee("ukg-ready")
        plan = build(WriteRequest("ukg-ready", "create", e, c, {"company": "33704016", "username": "new.user"}))
        fake = FakeUKG((201, b"", {"Location": "https://ukg.invalid/rest/v2/companies/7001/employees/555"}))
        result = send(plan, live_client.Session("ukg", "fake-key", transport=fake))
        self.assertEqual((result["ok"], result["calls"][0]["id"]), (True, "555"))
        self.assertEqual(fake.sent[0][:2], ("POST", "https://ukg.invalid/rest/v2/companies/33704016/employees"))
        self.assertEqual(fake.sent[0][2]["username"], "new.user")
        with self.subTest("an update is sent as JSON Patch (UKG answers 415 to application/json)"):
            patch = build(WriteRequest("ukg-ready", "update", e, c, changed={"middle_name"}))
            fake = FakeUKG((200, b"", {}))
            self.assertTrue(send(patch, live_client.Session("ukg", "fake-key", transport=fake))["ok"])
            self.assertEqual((fake.sent[0][0], fake.types[0]), ("PATCH", "application/json-patch+json"))
        with self.subTest("no answer: reported as unknown, never retried"):
            fake = FakeUKG(OSError("connection reset"))
            result = send(plan, live_client.Session("ukg", "fake-key", transport=fake, sleep=lambda s: None))
            self.assertEqual((result["ok"], result["calls"][0]["status"], len(fake.sent)), (False, 0, 1))
            self.assertIn("unknown", result["calls"][0]["outcome"])
        with self.subTest("a provider error is reported with its message"):
            fake = FakeUKG((400, json.dumps({"errors": [{"code": 1, "message": "Username already exists"}]}).encode(), {}))
            result = send(plan, live_client.Session("ukg", "fake-key", transport=fake))
            self.assertEqual(result["calls"][0]["messages"], ["Username already exists"])
        for other in (build(WriteRequest("ukg-ready", "create", e, c, {"company": "33704016"})), build(WriteRequest("isolved", "create", *employee("isolved")))):
            with self.subTest(destination=other.destination, refusals=refused(other)), self.assertRaises(ValueError):
                send(other, live_client.Session("ukg", "fake-key", transport=FakeUKG()))

    def test_api_preview_and_confirmed_send(self):
        fake = FakeUKG((201, json.dumps({"id": 777}).encode(), {}))
        client = TestClient(create_app(Store(":memory:"), transport=fake, key=lambda: "fake-key"))
        dataset = next(d["id"] for d in client.get("/api/datasets").json() if d["provider"] == "ukg-ready")
        e, _ = employee("ukg-ready")
        body = {"dataset_id": dataset, "employee_id": e["id"], "destination": "ukg-ready", "inputs": {"company": "33704016", "username": "new.user"}}
        preview = client.post("/api/write/preview", json=body).json()
        self.assertEqual((preview["sendable"], preview["sensitive_values"]), (True, "masked"))
        self.assertNotIn(e["demographics"]["birth_date"], json.dumps(preview))
        with self.subTest("an update from the form patches only the changed fields"):
            update = dict(body, operation="update", inputs={})
            self.assertEqual([r["field"] for r in client.post("/api/write/preview", json=update).json()["refusals"]], ["changes"])
            patch = client.post("/api/write/preview", json=dict(update, changes={"middle_name": "J", "suffix": ""})).json()
            self.assertEqual(patch["calls"][0]["body"], [{"op": "add", "path": "/middle_name", "value": "J"}, {"op": "remove", "path": "/suffix"}])
        with self.subTest("the form: changed fields only; a masked value is refused; a blank form is a new hire"):
            edited = client.post("/api/write/preview", json=dict(body, changes={"first_name": "Robin", "mobile_phone": "555-0100"})).json()
            sent = edited["calls"][0]["body"]
            self.assertEqual((sent["first_name"], sent["phones"]["cell_phone"], sent["last_name"]), ("Robin", "***", "Moreau"))
            self.assertEqual(client.post("/api/write/preview", json=dict(body, changes={"ssn": "***1101"})).status_code, 400)
            names = client.post("/api/write/preview", json=dict(body, changes={"state": "Illinois", "country": "United States"})).json()
            self.assertEqual([r["field"] for r in names["refusals"]], ["state", "country"], "UKG takes codes (IL, USA), refused before sending")
            new = dict(body, employee_id=None, changes={"first_name": "New", "last_name": "Hire", "hire_date": "2026-10-01"})
            missing = client.post("/api/write/preview", json=new).json()
            self.assertEqual([r["field"] for r in missing["refusals"]], ["start_date", "birth_date"], "both required by UKG (live 400s)")
            new["changes"] = dict(new["changes"], birth_date="1990-01-15")
            given = dict(new["inputs"], start_date="2026-10-05")
            started = client.post("/api/write/preview", json=dict(new, inputs=given)).json()
            self.assertEqual((started["sendable"], started["calls"][0]["body"]["dates"]), (True, {"hired": "2026-10-01", "started": "2026-10-05", "birthday": "***"}),
                             "the start date is never the hire date")
            self.assertEqual(started["calls"][0]["body"]["national_id_numbers"], [{"type": "NO_ID_NEEDED", "primary": True}],
                             "no SSN given: UKG's own no-id type, never an invented number")
        self.assertEqual(client.post("/api/write/send", json=body).status_code, 400, "not sent without confirm")
        self.assertEqual(fake.sent, [])
        refused_body = dict(body, destination="isolved", confirm=True)
        self.assertEqual(client.post("/api/write/send", json=refused_body).status_code, 400, "isolved is never sent")
        records: list[str] = []
        handler = logging.Handler()
        handler.emit = lambda record: records.append(record.getMessage())
        logger = logging.getLogger("normalization.app")
        logger.addHandler(handler)
        level, logger.level = logger.level, logging.INFO
        try:
            result = client.post("/api/write/send", json=dict(body, confirm=True)).json()
        finally:
            logger.removeHandler(handler)
            logger.level = level
        self.assertEqual((result["ok"], result["calls"][0]["id"], len(fake.sent)), (True, "777", 1))
        self.assertEqual(records, ["write ukg-ready create: HTTP 201"], "statuses only: no ids or values")


if __name__ == "__main__":
    unittest.main()
