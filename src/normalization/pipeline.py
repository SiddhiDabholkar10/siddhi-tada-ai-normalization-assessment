"""Normalization pipeline: one provider bundle in, every canonical record of the tenant out (D-085).

Each adapter module applies one mapping table (``mappings/data/<provider>/<table>.json``) and
exposes ``PROVIDER``, ``TABLE`` and ``normalize(bundle) -> list[CanonicalRecord]``. The pipeline
runs the modules ``ADAPTERS`` registers for the bundle's provider, files every record under its
output list, checks the set (record type, provider, tenant, unique ids) and runs
``find_link_problems`` on the assembled records. Writing and masking are the output layer's job
(``output.render_run``).

The ``normalize`` command runs this pipeline; it replaced the starter's stub adapters (D-087).
"""
from dataclasses import dataclass, field
from importlib import import_module
from types import ModuleType
from typing import Any

from .canonical.base import CanonicalRecord
from .canonical.benefits import BenefitEnrollment
from .canonical.company import Company
from .canonical.deductions import DeductionSetup
from .canonical.deposits import DirectDeposit
from .canonical.employee import Employee
from .canonical.links import find_link_problems
from .canonical.payroll import Paycheck, PayrollRun
from .employees.bundle import Bundle
from .fixtures.contracts import EMPTY_LIST_BODIES
from .mappings.spec import documented_routes, root_shape
from .mappings.tables import DATA

# Output lists, in document order, and the record type each holds.
RECORD_LISTS: dict[str, type[CanonicalRecord]] = {
    "companies": Company,
    "employees": Employee,
    "direct_deposits": DirectDeposit,
    "deduction_setups": DeductionSetup,
    "benefit_enrollments": BenefitEnrollment,
    "payroll_runs": PayrollRun,
    "paychecks": Paycheck,
}
# Mapping table -> the output lists its records go to.
TABLE_LISTS: dict[str, tuple[str, ...]] = {
    "company": ("companies",),
    "employee": ("employees",),
    "direct_deposit": ("direct_deposits",),
    "deduction_setup": ("deduction_setups",),
    "benefit_enrollment": ("benefit_enrollments",),
    "payroll": ("payroll_runs", "paychecks"),
}
# Mapping table -> provider -> adapter module, in run order (D-085, D-088, D-089); a table missing
# here is reported in the run header, never silently empty.
ADAPTERS: dict[str, dict[str, str]] = {
    "company": {
        "prismhr": ".entities.prismhr.company",
        "isolved": ".entities.isolved.company",
        "ukg-ready": ".entities.ukg_ready.company",
    },
    "employee": {
        "prismhr": ".employees.prismhr",
        "isolved": ".employees.isolved",
        "ukg-ready": ".employees.ukg_ready",
    },
    "direct_deposit": {
        "prismhr": ".entities.prismhr.deposits",
        "isolved": ".entities.isolved.deposits",
        "ukg-ready": ".entities.ukg_ready.deposits",
    },
    "deduction_setup": {  # UKG has no setup source (D-030)
        "prismhr": ".entities.prismhr.setups",
        "isolved": ".entities.isolved.setups",
    },
    "benefit_enrollment": {
        "prismhr": ".entities.prismhr.enrollments",
        "isolved": ".entities.isolved.enrollments",
        "ukg-ready": ".entities.ukg_ready.enrollments",
    },
    "payroll": {
        "prismhr": ".entities.prismhr.payroll",
        "isolved": ".entities.isolved.payroll",
        "ukg-ready": ".entities.ukg_ready.payroll",
    },
}


def adapter_modules(provider: str) -> list[ModuleType]:
    """The adapter modules registered for ``provider``, in run order."""
    return [import_module(by_provider[provider], __package__) for by_provider in ADAPTERS.values() if provider in by_provider]


def not_normalized(provider: str) -> dict[str, str]:
    """Output lists this run leaves empty because nothing fills them, with the reason: the
    provider has no mapping table for them, or the table has no adapter yet."""
    reasons = {}
    for table, lists in TABLE_LISTS.items():
        if provider in ADAPTERS.get(table, {}):
            continue
        has_table = (DATA / provider / f"{table}.json").exists()
        reason = "adapter not built yet" if has_table else f"no {table} mapping table: the provider has no source"
        reasons.update({name: reason for name in lists})
    return reasons


@dataclass(frozen=True)
class RunResult:
    provider: str
    tenant_id: str
    records: dict[str, list[CanonicalRecord]]  # every RECORD_LISTS name, records in id order
    link_problems: list[str]
    not_normalized: dict[str, str]
    unusable_responses: list[str] = field(default_factory=list)  # set aside before the adapters ran (D-089)


def _shape_problem(provider: str, route: str, body: Any) -> str | None:
    """Why a 200 body cannot be read as its route documents it: its top-level JSON type, or the
    type of a top-level array's items, differs from the contract. Only the shape is checked, so
    live deviations inside a body still reach the adapters; the isolved check detail's ``[]``
    (EMPTY_LIST_BODIES, D-082) is a documented exception."""
    doc = documented_routes(provider).get(route)
    kind, items = root_shape(doc) if doc is not None else (None, None)
    if kind is None or (body == [] and (provider, route) in EMPTY_LIST_BODIES):
        return None
    sent = {dict: "object", list: "array"}.get(type(body), "null" if body is None else type(body).__name__)
    if sent != kind:
        return f"the body is {sent} where the contract documents {kind}"
    if kind == "array" and items == "object" and not all(isinstance(item, dict) for item in body):
        return "an item of the body is not an object, as the contract documents"
    return None


def usable(bundle: Bundle) -> tuple[Bundle, list[str]]:
    """The bundle without the 200 responses whose shape differs from the contract, and why each
    was set aside. Adapters then treat them as absent ("not in the input"), never crash on them."""
    kept, problems = [], []
    for response in bundle.responses:
        problem = _shape_problem(bundle.provider.value, response.route, response.body) if response.ok else None
        if problem is None:
            kept.append(response)
        else:
            params = ", ".join(f"{key}={value}" for key, value in sorted(response.params.items()))
            problems.append(f"{response.route} ({params}): {problem}")
    return Bundle(bundle.provider, bundle.tenant_id, tuple(kept)), problems


def assemble(records: list[CanonicalRecord], provider: str, tenant_id: str) -> dict[str, list[CanonicalRecord]]:
    """``records`` filed under their output lists in id order. Raises ValueError for a record of
    an unknown type, of another provider or tenant, or an id given twice in one list."""
    lists: dict[str, list[CanonicalRecord]] = {name: [] for name in RECORD_LISTS}
    list_of = {model: name for name, model in RECORD_LISTS.items()}
    for record in records:
        name = list_of.get(type(record))
        if name is None:
            raise ValueError(f"{getattr(record, 'id', record)!r}: {type(record).__name__} is not an output record type")
        if record.provider.value != provider or record.tenant_id != tenant_id:
            raise ValueError(f"{record.id}: not of bundle provider {provider!r} and tenant {tenant_id!r}")
        lists[name].append(record)
    for name, items in lists.items():
        items.sort(key=lambda record: record.id)
        repeated = sorted({a.id for a, b in zip(items, items[1:]) if a.id == b.id})
        if repeated:
            raise ValueError(f"{name}: ids given more than once: {', '.join(repeated)}")
    return lists


def normalize_bundle(bundle: Bundle) -> RunResult:
    """Run every registered adapter of the bundle's provider and check the assembled set.
    Responses whose shape differs from the contract are set aside first (``usable``)."""
    provider = bundle.provider.value
    bundle, unusable = usable(bundle)
    modules = adapter_modules(provider)
    records = [record for module in modules for record in module.normalize(bundle)]
    lists = assemble(records, provider, bundle.tenant_id)
    problems = find_link_problems(
        lists["companies"], lists["employees"], lists["direct_deposits"], lists["deduction_setups"],
        lists["benefit_enrollments"], lists["payroll_runs"], lists["paychecks"],
    )
    return RunResult(provider, bundle.tenant_id, lists, problems, not_normalized(provider), unusable)
