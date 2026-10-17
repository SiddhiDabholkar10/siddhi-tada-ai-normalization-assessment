"""Write path (Phase 8, D-100): ``build`` maps a canonical employee to a provider's requests (a plan,
shown as a dry run); ``send`` sends a UKG Ready plan, the only provider written for real."""
from importlib import import_module

from .plan import DESTINATIONS, OPERATIONS, Plan, WriteRequest

BUILDERS = {"ukg-ready": ".ukg_ready", "isolved": ".isolved", "prismhr": ".prismhr"}


def build(request: WriteRequest) -> Plan:
    """The plan for ``request``: provider calls in order, refusals, notes. Nothing is sent."""
    return import_module(BUILDERS[request.destination], __package__).build(request)


__all__ = ["DESTINATIONS", "OPERATIONS", "Plan", "WriteRequest", "build"]
