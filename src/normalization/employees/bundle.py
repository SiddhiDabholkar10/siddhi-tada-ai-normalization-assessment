"""Provider bundle: the raw responses of one provider tenant, as one JSON file (D-080).

A bundle holds every response a normalization run reads, each with its documented route
template, the parameters it was called with and its HTTP status. Fixtures are bundles; a live
fetch (Phase 7) can write the same format. Bundles are read only through ``parse_source_json``
(exact decimals, D-025). Parameters are keyed by name; when a route template repeats a name
(UKG ``/payrolls/{id}/pay-statements/{id}``), the first is stored under a distinct key
(``payroll_id``) and the template is kept as documented (D-082).

    {"format": "normalization-bundle/1", "provider": "prismhr", "tenant_id": "900001",
     "fixture": {...},                      # optional: generator, seed, synthetic
     "responses": [{"route": "/employee/v1/getEmployee",
                    "params": {"clientId": "1001", "employeeId": "P00001"},
                    "status": 200, "body": {...}}]}
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..canonical.ids import Provider
from ..canonical.parsing import parse_source_json

FORMAT = "normalization-bundle/1"


@dataclass(frozen=True)
class Response:
    route: str
    params: dict[str, str]
    status: int
    body: Any

    @property
    def ok(self) -> bool:
        return self.status == 200


@dataclass(frozen=True)
class Bundle:
    provider: Provider
    tenant_id: str
    responses: tuple[Response, ...]

    def all(self, route: str, **params: str) -> list[Response]:
        """Responses of ``route`` whose parameters include ``params``, in file order."""
        return [
            r for r in self.responses if r.route == route and all(r.params.get(k) == str(v) for k, v in params.items())
        ]

    def get(self, route: str, **params: str) -> Response | None:
        """The one response of ``route`` with these parameters, or None if the input has none."""
        found = self.all(route, **params)
        if len(found) > 1:
            raise ValueError(f"bundle has {len(found)} responses for {route} {params}")
        return found[0] if found else None


def parse_bundle(text: str) -> Bundle:
    return bundle_from_data(parse_source_json(text))


def bundle_from_data(data: Any) -> Bundle:
    """A bundle from JSON already parsed with ``parse_source_json`` (exact decimals, D-025)."""
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise ValueError(
            f"not a provider bundle (expected format {FORMAT!r}): the input holds every API response of one "
            "tenant, e.g. fixtures/prismhr/bundle.json; a single API response cannot build complete records"
        )
    tenant = data.get("tenant_id")
    if not isinstance(tenant, str) or not tenant:
        raise ValueError("bundle tenant_id must be a non-empty string")
    responses = []
    for index, item in enumerate(data.get("responses") or []):
        if not isinstance(item, dict) or not isinstance(item.get("route"), str) or not isinstance(item.get("status"), int):
            raise ValueError(f"bundle response {index} needs a route and an integer status")
        params = {str(k): str(v) for k, v in (item.get("params") or {}).items()}
        responses.append(Response(item["route"], params, item["status"], item.get("body")))
    return Bundle(Provider(data.get("provider")), tenant, tuple(responses))


def load_bundle(path: Path) -> Bundle:
    return parse_bundle(Path(path).read_text(encoding="utf-8"))
