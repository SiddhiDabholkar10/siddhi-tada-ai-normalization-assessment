"""Employee adapters for the vertical slice (D-077, D-080): provider bundle in, canonical Employee
records out. Each adapter is ordinary Python that follows its provider's mapping table
(``mappings/data/<provider>/employee.json``); ``# row:`` comments cite the rows it applies."""
from importlib import import_module
from types import ModuleType

MODULES = {"prismhr": "prismhr", "isolved": "isolved", "ukg-ready": "ukg_ready"}


def adapter(provider: str) -> ModuleType:
    """The employee adapter module of ``provider`` (``normalize_employees(bundle)``)."""
    return import_module(f".{MODULES[provider]}", __name__)
