"""Provider dispatch: each provider module's ``normalize`` runs the pipeline for that provider (D-087)."""
from ..mappings.tables import ENTITIES  # company, employee, direct_deposit, deduction_setup, benefit_enrollment, payroll
from . import isolved, prismhr, ukg_ready

ADAPTERS = {"prismhr": prismhr, "isolved": isolved, "ukg-ready": ukg_ready}

__all__ = ["ADAPTERS", "ENTITIES"]
