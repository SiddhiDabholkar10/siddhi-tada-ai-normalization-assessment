"""Write the fixture bundles and their manifest (``python -m normalization generate-fixtures``).

One bundle per provider tenant (D-082): every response the adapters read, for every entity, so
a response that feeds several entities (PrismHR getEmployee: employees and deposits) exists once.
"""
import json
from collections import Counter
from pathlib import Path

from ..mappings.spec import documented_routes
from . import isolved, prismhr, ukg_ready
from .common import FORMAT

DEFAULT_SEED = 20261016
BUILDERS = {"prismhr": prismhr.build, "isolved": isolved.build, "ukg-ready": ukg_ready.build}
FILE_NAME = "bundle.json"
MANIFEST = "manifest.json"


def _text(data: dict) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def fixture_text(provider: str, seed: int = DEFAULT_SEED) -> str:
    """The bundle of ``provider`` as written to disk: the same seed gives the same bytes."""
    return _text(BUILDERS[provider](seed))


def manifest_text(seed: int = DEFAULT_SEED) -> str:
    """Seed, file and per-route response counts of every bundle, with the contract file that
    documents each route's schema."""
    providers = {}
    for provider, build in BUILDERS.items():
        bundle = build(seed)
        routes: dict[str, Counter] = {}
        for response in bundle["responses"]:
            routes.setdefault(response["route"], Counter())[str(response["status"])] += 1
        providers[provider] = {
            "file": f"{provider}/{FILE_NAME}",
            "tenant_id": bundle["tenant_id"],
            "responses": len(bundle["responses"]),
            "routes": {route: {"statuses": dict(sorted(counts.items())), "schema_source": documented_routes(provider)[route].source}
                       for route, counts in sorted(routes.items())},
        }
    return _text({"format": FORMAT, "generator": "normalization.fixtures", "seed": seed, "synthetic": True, "providers": providers})


def write_fixtures(out: Path, seed: int = DEFAULT_SEED) -> list[Path]:
    paths = []
    for provider in BUILDERS:
        path = Path(out) / provider / FILE_NAME
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(fixture_text(provider, seed), encoding="utf-8", newline="\n")
        paths.append(path)
    path = Path(out) / MANIFEST
    path.write_text(manifest_text(seed), encoding="utf-8", newline="\n")
    paths.append(path)
    return paths
