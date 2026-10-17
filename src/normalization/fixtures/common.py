"""Building blocks shared by the fixture builders."""
import random
from datetime import date
from decimal import Decimal
from typing import Any

from ..live.plans import isolved as isolved_plan
from ..live.plans import prismhr as prismhr_plan
from ..live.plans import ukg_ready as ukg_plan
from .contracts import skeleton

FORMAT = "normalization-bundle/1"
FIRST_NAMES = ("Avery", "Jordan", "Riley", "Morgan", "Casey", "Quinn", "Rowan", "Emerson", "Harper", "Reese")
LAST_NAMES = ("Okafor", "Lindqvist", "Moreau", "Tanaka", "Castillo", "Novak", "Haddad", "Brennan", "Iyer", "Sato")
STREETS = ("Maple Ave", "Cedar St", "Harbor Rd", "Quarry Ln", "Juniper Way", "Orchard Dr")
# Fixtures record each call exactly as the live fetch sends it (D-092): the crawl plan's fixed query
# parameters, zero-based pages, and the pay window found from the fixture's own run lists on
# FETCH_DATE. Page sizes are small so the paged cases need few records.
PLANS = {"prismhr": prismhr_plan, "isolved": isolved_plan, "ukg-ready": ukg_plan}
FETCH_DATE = date(2026, 10, 16)
PAGE_SIZES = {
    "prismhr": {prismhr_plan.VOUCHERS: 2},
    "isolved": {isolved_plan.EMPLOYEES: 2, isolved_plan.CHECKS: 4},
    "ukg-ready": {},
}


def page_size(provider: str, route: str) -> int:
    """The page size the fixture of ``provider`` uses for ``route`` (the replay test fetches with it)."""
    return PAGE_SIZES[provider].get(route) or PLANS[provider].PAGE_SIZES[route]


def routing(body: str) -> str:
    """An invented ABA routing number: prefix 60 (reserved for future use, never assigned to a
    bank), the 6 digits of ``body`` and a valid check digit."""
    digits = [int(d) for d in "60" + body]
    total = 3 * (digits[0] + digits[3] + digits[6]) + 7 * (digits[1] + digits[4] + digits[7]) + digits[2] + digits[5]
    return "60" + body + str((10 - total % 10) % 10)


def num(value: str | Decimal) -> float:
    """A JSON number for a money or rate value given as a decimal string (the bundles are read
    back with parse_source_json, which keeps it exact)."""
    return float(Decimal(value))


def merge(base: Any, overlay: Any) -> Any:
    """``overlay`` written over ``base``: objects merge key by key, anything else replaces."""
    if isinstance(base, dict) and isinstance(overlay, dict):
        out = dict(base)
        for key, value in overlay.items():
            out[key] = merge(base.get(key), value) if key in base else value
        return out
    return overlay


class Builder:
    """Collects the responses of one bundle. ``rng`` is the only source of variation, so the
    same seed always gives the same bundle."""

    def __init__(self, provider: str, tenant_id: str, seed: int) -> None:
        self.provider = provider
        self.tenant_id = tenant_id
        self.seed = seed
        self.rng = random.Random(f"{provider}:{seed}")
        self.responses: list[dict] = []

    def part(self, name: str) -> None:
        """Switch to the random stream of one part of the bundle (company, setups, payroll), so
        adding to one part never shifts the values of another. Employees use the first stream."""
        self.rng = random.Random(f"{self.provider}:{self.seed}:{name}")

    def shaped(self, route: str, path: str, values: dict) -> dict:
        """``values`` over the documented required skeleton at ``path`` of ``route``."""
        return merge(skeleton(self.provider, route, path), values)

    def add(self, route: str, params: dict, body: Any, status: int = 200) -> None:
        """One response; the route's fixed query parameters (crawl plan ``QUERY``) are added."""
        params = {**params, **PLANS[self.provider].QUERY.get(route, {})}
        self.responses.append({"route": route, "params": {k: str(v) for k, v in params.items()}, "status": status, "body": body})

    def name(self) -> tuple[str, str]:
        return self.rng.choice(FIRST_NAMES), self.rng.choice(LAST_NAMES)

    def phone(self, area: str = "801") -> str:
        return f"{area}-555-{self.rng.randint(1000, 1999)}"  # never one of the fixed 01xx-04xx numbers

    def street(self) -> str:
        return f"{self.rng.randint(10, 9899)} {self.rng.choice(STREETS)}"

    def money(self, low: int, high: int) -> str:
        """A whole-cent amount as a string, e.g. '1234.50'."""
        return f"{self.rng.randint(low * 100, high * 100) / 100:.2f}"

    def bundle(self) -> dict:
        return {
            "format": FORMAT,
            "provider": self.provider,
            "tenant_id": self.tenant_id,
            "fixture": {
                "synthetic": True,
                "generator": "normalization.fixtures",
                "seed": self.seed,
                "note": "Synthetic data. Names, numbers and identifiers are invented; SSNs use area 666, which is never issued.",
            },
            "responses": self.responses,
        }
