"""Phase 5 exit check (D-085, D-089, D-090): a few focused failure cases through the ``normalize``
command end in a valid document or a clean exit 1, never a traceback. Every provider and mapping
table on the fixtures: test_starter.test_every_provider_and_entity_is_normalized (D-091). The broad
sweep (each route given six wrong-shaped bodies) was run once by hand: 0 crash sites after the
shape guard; it is not repeated here (review, scope)."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from normalization.__main__ import main
from normalization.employees.bundle import FORMAT, load_bundle
from normalization.pipeline import _shape_problem

ROOT = Path(__file__).resolve().parents[1]
PROVIDERS = ("prismhr", "isolved", "ukg-ready")
ISOLVED_DETAIL = "/api/clients/{clientId}/legals/{legalId}/employees/{employeeId}/checks/{id}"


def command(*args: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        status = main(["normalize", *args])
    return status, out.getvalue(), err.getvalue()


def write_bundle(folder: str, provider: str, change) -> Path:
    """The fixture bundle with ``change(response) -> (status, body)`` applied, as a bundle file."""
    bundle = load_bundle(ROOT / "fixtures" / provider / "bundle.json")
    responses = []
    for response in bundle.responses:
        status, body = change(response)
        responses.append({"route": response.route, "params": response.params, "status": status, "body": body})
    path = Path(folder) / f"{provider}.json"
    data = {"format": FORMAT, "provider": provider, "tenant_id": bundle.tenant_id, "responses": responses}
    path.write_text(json.dumps(data, default=str), encoding="utf-8")
    return path


class ExitCheck(unittest.TestCase):
    def test_failed_routes_degrade_to_a_valid_document(self):
        """Every response HTTP 500: no crash, a valid document, the run still reported."""
        with tempfile.TemporaryDirectory() as folder:
            for provider in PROVIDERS:
                with self.subTest(provider=provider):
                    path = write_bundle(folder, provider, lambda r: (500, None))
                    status, out, _ = command("--input", str(path))
                    self.assertEqual(status, 0)
                    self.assertEqual(json.loads(out)["run"]["provider"], provider)

    def test_wrong_shaped_bodies_are_set_aside_and_reported(self):
        """A 200 body whose top-level shape differs from the contract is set aside before the
        adapters run (they then see the response as absent), named in the run header and on stderr."""
        cases = {"prismhr": ("/clientMaster/v1/getClientList", None),
                 "isolved": ("/api/clients/{clientId}/legals/{legalId}/checks", "not json"),
                 "ukg-ready": ("/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}", [None])}
        with tempfile.TemporaryDirectory() as folder:
            for provider, (route, bad) in cases.items():
                with self.subTest(provider=provider):
                    path = write_bundle(folder, provider, lambda r: (r.status, bad if r.route == route else r.body))
                    status, out, err = command("--input", str(path))
                    self.assertEqual(status, 0, err)
                    unusable = json.loads(out)["run"]["unusable_responses"]
                    self.assertTrue(unusable and all(item.startswith(route + " (") for item in unusable))
                    self.assertIn("response set aside: " + route, err)

    def test_an_adapter_fault_fails_cleanly_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "out.json"
            with mock.patch("normalization.entities.prismhr.payroll.normalize", side_effect=RuntimeError("boom")):
                status, out, err = command("--input", str(ROOT / "fixtures" / "prismhr" / "bundle.json"), "--output", str(target))
            self.assertEqual((status, out), (1, ""))
            self.assertIn("normalization failed (RuntimeError: boom); nothing written", err)
            self.assertFalse(target.exists())

    def test_shape_rules(self):
        self.assertIsNone(_shape_problem("isolved", ISOLVED_DETAIL, []))  # the documented exception (D-082)
        self.assertIsNotNone(_shape_problem("isolved", ISOLVED_DETAIL, [{}]))
        self.assertIsNotNone(_shape_problem("isolved", "/api/clients/{clientId}/legals", [None]))
        self.assertIsNone(_shape_problem("isolved", "/api/clients/{clientId}/legals", []))
        self.assertIsNotNone(_shape_problem("ukg-ready", "/v2/companies/{cid}/payrolls", []))
        self.assertIsNone(_shape_problem("prismhr", "/not/a/documented/route", "anything"))


if __name__ == "__main__":
    unittest.main()
