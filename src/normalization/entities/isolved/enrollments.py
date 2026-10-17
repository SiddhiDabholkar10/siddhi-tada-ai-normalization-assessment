"""isolved benefit enrollments: one BenefitEnrollment per item of the per-employee benefits route (D-049).

Follows ``mappings/data/isolved/benefit_enrollment.json``, written from the spec model (the demo
route returned 404, COVERAGE U). Id from (legal, item id). Plan type and coverage name labels have
no documented list: unknown with unknown_code. isActive true is active; false is unknown, since an
inactive plan may be terminated or waived. A 404 with an empty body means none (D-011).
"""
from typing import Any

from ...canonical.benefits import BenefitEnrollment
from ...canonical.diagnostics import DiagnosticCode, Severity
from ...canonical.ids import EntityType, Provider, canonical_id
from ...canonical.parsing import DateRole
from ...canonical.parts import Reference
from ...canonical.values import MappingBasis
from ...employees.bundle import Bundle
from ...employees.common import NP, Ctx, build
from ..common import USD, route_code, source
from .company import without_links

PROVIDER = "isolved"
TABLE = "benefit_enrollment"
ROUTES = {"benefits": "/api/clients/{clientId}/legals/{legalId}/employees/{employeeId}/benefits"}
ITEM_HANDLED = {"id", "planName", "planType", "isActive", "coverageName", "employeeBenefitStartDate", "employeeBenefitStopDate",
                "benefitType", "calcParams", "deductionAmount", "employeeBenefitPlanDetail"}
DETAIL_HANDLED = {"planId", "waiveReason", "coverageLevel", "provider", "accountNumber", "routingNumber", "maskedAccountNumber",
                  "accountType", "participantId", "employeePCP", "beneficiaries", "dependents", "messagesLinksDocuments"}
DETAIL_SENSITIVE = ("accountNumber", "routingNumber", "accountType", "participantId", "employeePCP", "beneficiaries", "dependents")


def _id(tenant: str, entity: EntityType, *parts: Any) -> str:
    return canonical_id(Provider.ISOLVED, tenant, entity, *(str(p) for p in parts))


def normalize(bundle: Bundle) -> list[BenefitEnrollment]:
    records = []
    for response in bundle.all(ROUTES["benefits"]):
        if response.ok:
            for index, item in enumerate(response.body or []):
                records.append(_enrollment(bundle.tenant_id, response.params, index, item))
    return records


def _enrollment(tenant: str, params: dict, index: int, item: dict) -> BenefitEnrollment:
    ctx = Ctx(PROVIDER)
    client, legal, employee = params.get("clientId"), params.get("legalId"), params.get("employeeId")
    item_id = str(item.get("id"))  # row: benefits [].id
    key = f"benefits:[{index}]"
    detail = item.get("employeeBenefitPlanDetail") or {}
    at = f"{key}.employeeBenefitPlanDetail"
    active = item.get("isActive")  # row: benefits [].isActive
    if active is True:
        status = route_code("active", "true")
    elif active is False:
        status = {"value": "unknown", "raw_code": "false", "raw_label": None, "basis": MappingBasis.UNMAPPED.value}
        ctx.diag(DiagnosticCode.UNKNOWN_CODE, Severity.WARNING, "An inactive plan may be terminated or waived; status unknown.",
                 "status", "D-049")
    else:
        status = NP
    ctx.keep(f"{key}.benefitType", without_links(item.get("benefitType")))  # row: benefits [].benefitType.**
    ctx.keep(f"{key}.calcParams", item.get("calcParams"))  # row: benefits [].calcParams[].*
    ctx.keep(f"{key}.deductionAmount", item.get("deductionAmount"))  # row: benefits [].deductionAmount[]
    ctx.rest(key, item, ITEM_HANDLED)  # row: benefits [].*
    ctx.keep(f"{at}.coverageLevel", detail.get("coverageLevel"))  # row: benefits [].employeeBenefitPlanDetail.coverageLevel[]
    ctx.keep(f"{at}.provider", without_links(detail.get("provider")))  # row: benefits [].employeeBenefitPlanDetail.provider.*
    # row: benefits [].employeeBenefitPlanDetail.accountNumber; [].employeeBenefitPlanDetail.routingNumber
    # row: benefits [].employeeBenefitPlanDetail.accountType; [].employeeBenefitPlanDetail.participantId
    # row: benefits [].employeeBenefitPlanDetail.employeePCP; [].employeeBenefitPlanDetail.beneficiaries[]
    # row: benefits [].employeeBenefitPlanDetail.dependents[].*
    for name in DETAIL_SENSITIVE:
        ctx.keep(f"{at}.{name}", detail.get(name), sensitive=True)
    ctx.rest(at, detail, DETAIL_HANDLED)  # row: benefits [].employeeBenefitPlanDetail.*
    return build(
        BenefitEnrollment,
        id=_id(tenant, EntityType.BENEFIT_ENROLLMENT, legal, item_id),
        provider=Provider.ISOLVED,
        tenant_id=tenant,
        source_ids={"clientId": client, "legalId": legal, "employeeId": employee, "id": item_id},
        sources=[source(ROUTES["benefits"], f"/{index}")],
        company_id=_id(tenant, EntityType.COMPANY, legal),
        employee_id=_id(tenant, EntityType.EMPLOYEE, legal, employee),
        plan=build(
            Reference,
            source_id=ctx.text(detail.get("planId")),  # row: benefits [].employeeBenefitPlanDetail.planId
            code=NP,
            name=ctx.text(item.get("planName")),  # row: benefits [].planName
        ),
        benefit_type=ctx.coded("isolved.benefit_plan_type", item.get("planType"), "benefit_type"),  # row: benefits [].planType
        status=status,
        coverage_level=ctx.coded("isolved.coverage_name", item.get("coverageName"), "coverage_level"),  # row: benefits [].coverageName
        coverage_start=ctx.date(item.get("employeeBenefitStartDate"), DateRole.PERIOD_START, "coverage_start"),  # row: benefits [].employeeBenefitStartDate
        coverage_end=ctx.date(item.get("employeeBenefitStopDate"), DateRole.PERIOD_END, "coverage_end"),  # row: benefits [].employeeBenefitStopDate
        deduction_start=NP,
        deduction_end=NP,
        is_section_125=NP,
        waive_reason=ctx.text(detail.get("waiveReason")),  # row: benefits [].employeeBenefitPlanDetail.waiveReason
        plan_details=NP,
        currency=USD,
        diagnostics=ctx.diagnostics,
        provider_extensions=ctx.extensions,
        sensitive_provider_extensions=ctx.sensitive_extensions,
    )
