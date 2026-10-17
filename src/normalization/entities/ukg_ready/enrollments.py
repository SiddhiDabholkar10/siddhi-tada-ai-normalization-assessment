"""UKG Ready benefit enrollments: one BenefitEnrollment per ``benefits[]`` item (D-049).

Follows ``mappings/data/ukg-ready/benefit_enrollment.json``. No amounts are sent, so plan_details
is not provided; benefit_type is not provided (lookup/benefit/types is not read, D-081). Coverage
level labels are company-defined: the code table sets coverage_level and, for 'Waived', status
(inferred); a status the table does not set stays not provided.
"""
from typing import Any

from ...canonical.benefits import BenefitEnrollment
from ...canonical.ids import EntityType, Provider, canonical_id
from ...canonical.parsing import DateRole
from ...canonical.parts import Reference
from ...canonical.values import MappingBasis
from ...employees.bundle import Bundle
from ...employees.common import NP, Ctx, build, code_entry, is_blank
from ..common import source

PROVIDER = "ukg-ready"
TABLE = "benefit_enrollment"
ROUTES = {"benefits": "/v2/companies/{cid}/employees/{aid}/benefits"}


def _id(tenant: str, entity: EntityType, *parts: Any) -> str:
    return canonical_id(Provider.UKG_READY, tenant, entity, *(str(p) for p in parts))


def normalize(bundle: Bundle) -> list[BenefitEnrollment]:
    records = []
    for response in bundle.all(ROUTES["benefits"]):
        if response.ok:
            for index, item in enumerate((response.body or {}).get("benefits") or []):
                records.append(_enrollment(bundle.tenant_id, response.params, index, item))
    return records


def _enrollment(tenant: str, params: dict, index: int, item: dict) -> BenefitEnrollment:
    ctx = Ctx(PROVIDER)
    cid = params.get("cid")
    item_id = str(item.get("id"))  # row: benefits benefits[].id
    account = (item.get("employee") or {}).get("account_id")  # row: benefits benefits[].employee.account_id
    plan = item.get("benefit_plan") or {}
    level = item.get("coverage_level")  # row: benefits benefits[].coverage_level
    entry = code_entry(PROVIDER, "ukg-ready.coverage_level", str(level).strip()) if not is_blank(level) else None
    status_known = entry is not None and entry["status"]["basis"] != MappingBasis.UNMAPPED.value
    return build(
        BenefitEnrollment,
        id=_id(tenant, EntityType.BENEFIT_ENROLLMENT, cid, item_id),
        provider=Provider.UKG_READY,
        tenant_id=tenant,
        source_ids={"companyId": cid, "accountId": str(account if not is_blank(account) else params.get("aid")), "id": item_id},
        sources=[source(ROUTES["benefits"], f"/benefits/{index}")],
        company_id=_id(tenant, EntityType.COMPANY, cid),
        employee_id=_id(tenant, EntityType.EMPLOYEE, cid, account if not is_blank(account) else params.get("aid")),
        plan=build(
            Reference,
            source_id=ctx.text(plan.get("id")),  # row: benefits benefits[].benefit_plan.id
            code=NP,
            name=ctx.text(item.get("name")),  # row: benefits benefits[].name
        ),
        benefit_type=NP,  # lookup/benefit/types is not read (table notes, D-081)
        status=ctx.coded("ukg-ready.coverage_level", level, "status", column="status") if status_known else NP,
        coverage_level=ctx.coded("ukg-ready.coverage_level", level, "coverage_level", column="coverage_level"),
        coverage_start=ctx.date(item.get("coverage_effective_from"), DateRole.PERIOD_START, "coverage_start"),  # row: benefits benefits[].coverage_effective_from
        coverage_end=ctx.date(item.get("coverage_effective_to"), DateRole.PERIOD_END, "coverage_end"),  # row: benefits benefits[].coverage_effective_to
        deduction_start=NP,
        deduction_end=NP,
        is_section_125=NP,
        waive_reason=NP,
        plan_details=NP,  # no amounts are sent (table notes)
        currency=ctx.text(plan.get("currency")),  # row: benefits benefits[].benefit_plan.currency
        diagnostics=ctx.diagnostics,
        provider_extensions=ctx.extensions,
        sensitive_provider_extensions=ctx.sensitive_extensions,
    )
