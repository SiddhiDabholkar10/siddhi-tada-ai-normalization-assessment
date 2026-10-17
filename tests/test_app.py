"""The app (Phase 7b), offline: the API over the sample datasets, and a sync against the fake
provider from test_live. Masking gate (D-036): every API surface is masked unless the request opts
in, and logs carry no full sensitive value, no token and no ids.
"""
import io
import json
import logging
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from normalization.__main__ import main
from normalization.app.api import create_app
from normalization.app.store import MAX_LIMIT, Store
from normalization.canonical.base import sensitive_fields
from normalization.fixtures.common import FETCH_DATE
from normalization.live.client import FetchError
from normalization.output import mask_record
from normalization.pipeline import RECORD_LISTS
from test_live import FakeProvider

ROOT = Path(__file__).resolve().parents[1]


def full_leaves(full, masked):
    """The values ``full`` holds where ``masked`` differs: what masking hid."""
    if isinstance(full, dict) and isinstance(masked, dict):
        return [leaf for key in full for leaf in full_leaves(full[key], masked.get(key))]
    if isinstance(full, list) and isinstance(masked, list):
        return [leaf for a, b in zip(full, masked) for leaf in full_leaves(a, b)]
    return [] if full == masked else [full]


def every_record(client, dataset, show):
    return {name: client.get(f"/api/datasets/{dataset}/records/{name}",
                             params={"limit": MAX_LIMIT, "show_sensitive": show}).json() for name in RECORD_LISTS}


def run_sync(client, body):
    """Start a sync and wait for it to end; its final job state."""
    job = client.post("/api/sync", json=body)
    assert job.status_code == 202, job.text
    deadline = time.monotonic() + 60
    while (state := client.get(f"/api/sync/{job.json()['id']}").json())["state"] == "running":
        assert time.monotonic() < deadline, "sync did not finish"
        time.sleep(0.05)
    return state


class Api(unittest.TestCase):
    def test_every_list_is_masked_by_default_and_full_on_opt_in(self):
        """Each sample dataset holds the golden records; each list and single record is masked
        exactly as the CLI masks it, unless show_sensitive=true. Paging and filters work."""
        client = TestClient(create_app(Store(":memory:")))
        datasets = {item["provider"]: item for item in client.get("/api/datasets").json()}
        self.assertEqual(sorted(datasets), ["isolved", "prismhr", "ukg-ready"], "samples stored on start, no key needed")
        hidden = 0
        for provider, dataset in datasets.items():
            golden = json.loads((ROOT / "tests" / "golden" / f"{provider}.json").read_text(encoding="utf-8"))
            masked, shown = every_record(client, dataset["id"], False), every_record(client, dataset["id"], True)
            for name, model in RECORD_LISTS.items():
                with self.subTest(provider=provider, list=name):
                    expected = [mask_record(item, sensitive_fields(model), model) for item in golden[name]]
                    by_id = lambda items: sorted(items, key=lambda item: item["id"])  # payroll lists are newest first
                    self.assertEqual((by_id(masked[name]["items"]), masked[name]["sensitive_values"]), (expected, "masked"))
                    self.assertEqual((by_id(shown[name]["items"]), shown[name]["sensitive_values"]), (golden[name], "shown"))
                    dates = [item.get("pay_date") or "" for item in shown[name]["items"]]
                    if name in ("payroll_runs", "paychecks"):
                        self.assertEqual(dates, sorted(dates, reverse=True), "newest pay date first")
                    hidden += len(full_leaves(golden[name], expected))
                    if golden[name]:
                        first = golden[name][0]["id"]
                        one = client.get(f"/api/datasets/{dataset['id']}/records/{name}/{first}").json()
                        self.assertEqual(one, {"item": expected[0], "sensitive_values": "masked"})
        self.assertGreater(hidden, 0, "the samples hold sensitive values, so masking was exercised")
        prism = datasets["prismhr"]["id"]
        employee = client.get(f"/api/datasets/{prism}/records/employees", params={"limit": 1}).json()
        self.assertEqual((len(employee["items"]), employee["total"]), (1, 3))
        linked = client.get(f"/api/datasets/{prism}/records/paychecks", params={"employee_id": employee["items"][0]["id"]}).json()
        self.assertTrue(linked["items"] and all(p["employee_id"] == employee["items"][0]["id"] for p in linked["items"]))
        self.assertEqual(client.get(f"/api/datasets/{prism}/records/employees", params={"q": "OKAFOR"}).json()["total"], 1)
        self.assertEqual(client.get(f"/api/datasets/{prism}/records/nothing").status_code, 404)
        named = [e["id"] for e in client.get(f"/api/datasets/{prism}/records/employees").json()["items"]][:2]
        picked = client.get(f"/api/datasets/{prism}/records/employees", params={"ids": ",".join(named)}).json()
        self.assertEqual(sorted(e["id"] for e in picked["items"]), sorted(named), "lookup by a list of ids")
        bounded = client.get(f"/api/datasets/{prism}/records/employees", params={"limit": 500, "offset": -5}).json()
        self.assertEqual((bounded["limit"], bounded["offset"], len(bounded["items"])), (MAX_LIMIT, 0, 3), "a page reports what it served")
        with self.subTest("the built UI is served at / with its assets (no Node needed)"):
            page = client.get("/")
            self.assertEqual(page.status_code, 200)
            assets = re.findall(r'(?:src|href)="\./(assets/[^"]+)"', page.text)
            self.assertTrue(assets and all(client.get(f"/{path}").status_code == 200 for path in assets), assets)
        with self.subTest("an output whose lists do not match its counts is refused"):
            store = Store(":memory:")
            golden = json.loads((ROOT / "tests" / "golden" / "prismhr.json").read_text(encoding="utf-8"))
            filtered = {key: value for key, value in golden.items() if key not in ("payroll_runs", "paychecks")}  # as --entity leaves it
            with self.assertRaisesRegex(ValueError, r"payroll_runs \(0 of 6\), paychecks \(0 of 9\)"):
                store.add_document(filtered, "filtered")
            self.assertEqual(store.datasets(), [], "nothing stored")

    def test_sync_stores_the_run_and_logs_counts_only(self):
        """A sync of the fake UKG tenant runs in the background and stores a dataset whose API
        view is masked. Failed syncs store nothing. No log line or job state holds a hidden value,
        the token, the tenant id or a company id."""
        fake = FakeProvider("ukg-ready")
        root = logging.getLogger()
        captured: list[str] = []
        handler = logging.Handler(logging.DEBUG)
        handler.emit = lambda record: captured.append(record.getMessage())
        root.addHandler(handler)
        level, root.level = root.level, logging.DEBUG
        try:
            client = TestClient(create_app(Store(":memory:"), transport=fake, key=lambda: "fake-key", samples=False))
            state = run_sync(client, {"tenant": "ukg", "as_of": FETCH_DATE.isoformat()})
            self.assertEqual(state["state"], "done", state["error"])
            # Failed syncs: an unknown company (the fetch error) and an adapter fault whose text names a record.
            unknown = run_sync(client, {"tenant": "ukg", "companies": ["SECRET-COMPANY-42"], "as_of": FETCH_DATE.isoformat()})
            fault = ValueError("ukg-ready:900003:employee:7001:1101: record failed validation")
            with mock.patch("normalization.app.api.normalize_bundle", side_effect=fault):
                faulted = run_sync(client, {"tenant": "ukg", "as_of": FETCH_DATE.isoformat()})
            self.assertEqual([unknown["state"], unknown["dataset_id"], faulted["state"], faulted["dataset_id"]], ["failed", None, "failed", None])
            self.assertEqual(unknown["error"], "1 of the requested companies not found in this tenant (1 companies found)")
            self.assertEqual(faulted["error"], "normalization failed (ValueError); nothing stored")
            self.assertEqual(len(client.get("/api/datasets").json()), 1, "a failed sync stores nothing")
            dataset = client.get(f"/api/datasets/{state['dataset_id']}").json()
            golden = json.loads((ROOT / "tests" / "golden" / "ukg-ready.json").read_text(encoding="utf-8"))
            self.assertEqual(dataset["run"]["counts"], golden["run"]["counts"])
            self.assertEqual(dataset["run"]["fetch"]["pay_windows"]["7001"]["basis"], "latest pay date")
            masked, shown = every_record(client, dataset["id"], False), every_record(client, dataset["id"], True)
            hidden = [str(leaf) for name in RECORD_LISTS for leaf in full_leaves(shown[name]["items"], masked[name]["items"])]
            self.assertTrue(hidden, "the synced records hold sensitive values")
            logs = "\n".join(captured) + json.dumps([state, unknown, faulted])
            self.assertIn("sync ukg: started", logs)
            for secret in [fake.token, *(value for value in hidden if len(value) >= 4)]:
                self.assertNotIn(secret, logs)
            for identifier in (fake.data["tenant_id"], "7001", "SECRET-COMPANY-42"):
                self.assertNotRegex(logs, rf"\b{identifier}\b")
        finally:
            root.removeHandler(handler)
            root.level = level
        with self.subTest("a sync without a key is refused before it starts"):
            def no_key():
                raise FetchError("no sign-in key")
            refused = TestClient(create_app(Store(":memory:"), key=no_key, samples=False)).post("/api/sync", json={"tenant": "ukg"})
            self.assertEqual((refused.status_code, refused.json()["detail"]), (400, "no sign-in key"))

    def test_import_bundle_keeps_full_values_and_an_older_store_is_refused(self):
        """import-bundle stores a saved bundle normalized with full values (the API masks them);
        a store file from an older schema is refused with a clear message, not used."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "app.db"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["import-bundle", str(ROOT / "fixtures" / "ukg-ready" / "bundle.json"), "--db", str(db)]), 0)
            store = Store(db)
            (dataset,) = store.datasets()
            golden = json.loads((ROOT / "tests" / "golden" / "ukg-ready.json").read_text(encoding="utf-8"))
            self.assertEqual((dataset["kept_values"], dataset["counts"]), ("full", golden["run"]["counts"]))
            stored, _ = store.page(dataset["id"], "employees", 0, MAX_LIMIT)
            store.close()
            self.assertEqual(stored, golden["employees"], "full values, exactly the golden records")
            with self.subTest("an older store file is refused"):
                old = Path(tmp) / "old.db"
                with sqlite3.connect(old) as connection:  # schema version 0, as before the guard
                    connection.execute("CREATE TABLE records (dataset_id INTEGER, list TEXT, id TEXT)")
                connection.close()
                with self.assertRaisesRegex(ValueError, "older version of the app"):
                    Store(old)

    def test_ui_hides_full_values_when_the_switch_goes_off(self):
        """The UI gate (ui/src/gate.js), run with Node's built-in test runner: a full-value answer
        is not shown once the switch is off, while the masked answer loads or after it fails."""
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node is not installed; the UI gate test needs it (npm test in ui/)")
        result = subprocess.run([node, "--test", "src/"], cwd=ROOT / "ui", capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("# fail 0", result.stdout)


if __name__ == "__main__":
    unittest.main()
