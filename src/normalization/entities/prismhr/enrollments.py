"""PrismHR benefit enrollments: one BenefitEnrollment per getBenefitPlans ``benefitPlan[]`` item (D-049).

Follows ``mappings/data/prismhr/benefit_enrollment.json``. Id from (client, employee, planId),
which deduction setups refer to by ``benefitPlanId``. Every planDetail row is kept in
plan_details; premium amounts state no period, so amount_period is not provided. The plan's
getEmployeePremium rates are kept raw in the enrollment's provider_extensions (D-084).
"""

from ...canonical.benefits import BenefitEnrollment, BenefitPlanDetail
from ...canonical.ids import EntityType, Provider, canonical_id
from ...canonical.parsing import DateRole
from ...canonical.parts import Reference
from ...employees.bundle import Bundle
from ...employees.common import NP, Ctx, build, is_blank
from ..common import USD, prismhr_ok, source

PROVIDER = "prismhr"
TABLE = "benefit_enrollment"
ROUTES = {
    "getBenefitPlans": "/benefits/v1/getBenefitPlans",
    "getEmployeePremium": "/benefits/v1/getEmployeePremium",
}
PLAN_HANDLED = {"planId", "description", "status", "insClass", "coverageStart", "coverageEnd", "deductionStart",
                "deductionEnd", "section125", "waiveReason", "planDetail"}
DETAIL_HANDLED = {"effectiveDate", "planType", "coverage", "coverageBasis", "employeePremium", "employeeContrib",
                  "eePremiumContrib", "peoPremium", "dependentPremium", "dependent", "beneficiary"}


def _id(tenant: str, entity: EntityType, *parts: str) -> str:
    return canonical_id(Provider.PRISMHR, tenant, entity, *parts)


def normalize(bundle: Bundle) -> list[BenefitEnrollment]:
    records = []
    for response in bundle.all(ROUTES["getBenefitPlans"]):
        if not prismhr_ok(response):
            continue
        client, employee = response.params.get("clientId"), response.params.get("employeeId")
        for index, plan in enumerate(response.body.get("benefitPlan") or []):
            if not is_blank(plan.get("planId")):
                records.append(_enrollment(bundle, client, employee, index, plan))
    return records


def _enrollment(bundle: Bundle, client: str, employee: str, index: int, plan: dict) -> BenefitEnrollment:
    tenant, ctx = bundle.tenant_id, Ctx(PROVIDER)
    plan_id = str(plan.get("planId")).strip()  # row: getBenefitPlans benefitPlan[].planId
    key = f"getBenefitPlans:benefitPlan[{index}]"
    sources = [source(ROUTES["getBenefitPlans"], f"/benefitPlan/{index}")]
    details = []
    for row, detail in enumerate(plan.get("planDetail") or []):
        where, at = f"plan_details[{row}]", f"{key}.planDetail[{row}]"
        details.append(build(
            BenefitPlanDetail,
            effective_date=ctx.date(detail.get("effectiveDate"), DateRole.EVENT, f"{where}.effective_date"),  # row: getBenefitPlans benefitPlan[].planDetail[].effectiveDate
            coverage_level=ctx.coded("prismhr.plan_type", detail.get("planType"), f"{where}.coverage_level"),  # row: getBenefitPlans benefitPlan[].planDetail[].planType
            coverage_amount=ctx.number(detail.get("coverage"), f"{where}.coverage_amount"),  # row: getBenefitPlans benefitPlan[].planDetail[].coverage
            coverage_basis_amount=ctx.number(detail.get("coverageBasis"), f"{where}.coverage_basis_amount"),  # row: getBenefitPlans benefitPlan[].planDetail[].coverageBasis
            employee_premium=ctx.number(detail.get("employeePremium"), f"{where}.employee_premium"),  # row: getBenefitPlans benefitPlan[].planDetail[].employeePremium
            employee_contribution=ctx.number(detail.get("employeeContrib"), f"{where}.employee_contribution"),  # row: getBenefitPlans benefitPlan[].planDetail[].employeeContrib
            employee_premium_contribution=ctx.number(detail.get("eePremiumContrib"), f"{where}.employee_premium_contribution"),  # row: getBenefitPlans benefitPlan[].planDetail[].eePremiumContrib
            provider_contribution=ctx.number(detail.get("peoPremium"), f"{where}.provider_contribution"),  # row: getBenefitPlans benefitPlan[].planDetail[].peoPremium
            dependent_premium=ctx.number(detail.get("dependentPremium"), f"{where}.dependent_premium"),  # row: getBenefitPlans benefitPlan[].planDetail[].dependentPremium
            amount_period=NP,  # no period is stated (table notes, D-084)
        ))
        # row: getBenefitPlans benefitPlan[].planDetail[].dependent[].*; benefitPlan[].planDetail[].beneficiary[].*
        ctx.keep(f"{at}.dependent", detail.get("dependent"), sensitive=True)
        ctx.keep(f"{at}.beneficiary", detail.get("beneficiary"), sensitive=True)
        ctx.rest(at, detail, DETAIL_HANDLED)  # row: getBenefitPlans benefitPlan[].planDetail[].*
    # row: getBenefitPlans benefitPlan[].carrierEmployeeId; benefitPlan[].doctorId; benefitPlan[].seenByDoctor
    # row: getBenefitPlans benefitPlan[].groupTermLife[].*; benefitPlan[].rateGuaranty[].*; benefitPlan[].gtlVoucherNumber[]
    # row: getBenefitPlans benefitPlan[].*
    ctx.rest(key, plan, PLAN_HANDLED, sensitive={"carrierEmployeeId", "doctorId", "seenByDoctor"})
    for response in bundle.all(ROUTES["getEmployeePremium"], clientId=client, employeeId=employee, planId=plan_id):
        if prismhr_ok(response):
            sources.append(source(ROUTES["getEmployeePremium"]))
            # row: getEmployeePremium billingRates.*; premiumRates.*; contributionRates.*
            for name in ("billingRates", "premiumRates", "contributionRates"):
                ctx.keep(f"getEmployeePremium:{name}", response.body.get(name))
    return build(
        BenefitEnrollment,
        id=_id(tenant, EntityType.BENEFIT_ENROLLMENT, client, employee, plan_id),
        provider=Provider.PRISMHR,
        tenant_id=tenant,
        source_ids={"clientId": client, "employeeId": employee, "planId": plan_id},
        sources=sources,
        company_id=_id(tenant, EntityType.COMPANY, client),
        employee_id=_id(tenant, EntityType.EMPLOYEE, client, employee),
        plan=build(Reference, source_id=NP, code=plan_id,
                   name=ctx.text(plan.get("description"))),  # row: getBenefitPlans benefitPlan[].description
        benefit_type=ctx.coded("prismhr.ins_class", plan.get("insClass"), "benefit_type"),  # row: getBenefitPlans benefitPlan[].insClass
        status=ctx.coded("prismhr.benefit_status", plan.get("status"), "status"),  # row: getBenefitPlans benefitPlan[].status
        coverage_level=NP,  # only detail rows carry planType (table notes)
        coverage_start=ctx.date(plan.get("coverageStart"), DateRole.PERIOD_START, "coverage_start"),  # row: getBenefitPlans benefitPlan[].coverageStart
        coverage_end=ctx.date(plan.get("coverageEnd"), DateRole.PERIOD_END, "coverage_end"),  # row: getBenefitPlans benefitPlan[].coverageEnd
        deduction_start=ctx.date(plan.get("deductionStart"), DateRole.PERIOD_START, "deduction_start"),  # row: getBenefitPlans benefitPlan[].deductionStart
        deduction_end=ctx.date(plan.get("deductionEnd"), DateRole.PERIOD_END, "deduction_end"),  # row: getBenefitPlans benefitPlan[].deductionEnd
        is_section_125=ctx.flag(plan.get("section125"), "is_section_125"),  # row: getBenefitPlans benefitPlan[].section125
        waive_reason=ctx.text(plan.get("waiveReason")),  # row: getBenefitPlans benefitPlan[].waiveReason
        plan_details=details,
        currency=USD,
        diagnostics=ctx.diagnostics,
        provider_extensions=ctx.extensions,
        sensitive_provider_extensions=ctx.sensitive_extensions,
    )

