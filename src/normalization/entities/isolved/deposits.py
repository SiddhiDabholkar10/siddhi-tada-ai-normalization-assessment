"""isolved direct deposits: one DirectDeposit per item of the per-employee directdeposits route (D-046).

Follows ``mappings/data/isolved/direct_deposit.json``. A 404 with an empty body means no deposits
(D-011). Allocation: an amount is fixed_amount, a percent is percent (basis unknown), an active
sequence 0 account ('0 = Net Pay') is the remainder (D-015, inferred), anything else unknown.
Numbers are sent in full, so the last-4 fields are not applicable.
"""
from typing import Any

from ...canonical.deposits import DirectDeposit
from ...canonical.diagnostics import DiagnosticCode, Severity
from ...canonical.ids import EntityType, Provider, canonical_id
from ...canonical.values import MappingBasis
from ...employees.bundle import Bundle
from ...employees.common import NA, NP, Ctx, Null, build
from ..common import USD, route_code, source

PROVIDER = "isolved"
TABLE = "direct_deposit"
ROUTES = {"directdeposits": "/api/clients/{clientId}/legals/{legalId}/employees/{employeeId}/directdeposits"}


def _id(tenant: str, entity: EntityType, *parts: Any) -> str:
    return canonical_id(Provider.ISOLVED, tenant, entity, *(str(p) for p in parts))


def normalize(bundle: Bundle) -> list[DirectDeposit]:
    records = []
    for response in bundle.all(ROUTES["directdeposits"]):
        if not response.ok:
            continue  # 404 with an empty body: no deposits (D-011); other statuses carry none
        params = response.params
        for index, item in enumerate(response.body or []):
            records.append(_deposit(bundle.tenant_id, params, index, item))
    return records


def _deposit(tenant: str, params: dict, index: int, item: dict) -> DirectDeposit:
    ctx = Ctx(PROVIDER)
    client, legal, employee = params.get("clientId"), params.get("legalId"), params.get("employeeId")
    deposit_id = str(item.get("id"))  # row: directdeposits [].id
    amount = ctx.number(item.get("amount"), "amount")  # row: directdeposits [].amount
    percent = ctx.number(item.get("percent"), "percent")  # row: directdeposits [].percent
    sequence = ctx.integer(item.get("sequenceNumber"), "sequence")  # row: directdeposits [].sequenceNumber
    status = ctx.coded("isolved.deposit_status", item.get("status"), "status")  # row: directdeposits [].status
    active = isinstance(status, dict) and status["value"] == "active"
    if not isinstance(amount, Null):
        allocation, basis = route_code("fixed_amount", "amount"), NA
        if not isinstance(percent, Null):  # both sent: the amount decides; the percent is kept raw
            ctx.keep(f"directdeposits:[{index}].percent", item.get("percent"))
            ctx.diag(DiagnosticCode.CONFLICTING_SOURCES, Severity.WARNING, "Both amount and percent are sent; read as a fixed amount.",
                     "percent", "D-015")
        percent = NA
    elif not isinstance(percent, Null):
        allocation, amount = route_code("percent", "percent"), NA
        basis = {"value": "unknown", "raw_code": "percent", "raw_label": None, "basis": MappingBasis.UNMAPPED.value}
        ctx.diag(DiagnosticCode.UNKNOWN_CODE, Severity.WARNING, "isolved states no basis for a percent deposit; value unknown.",
                 "percent_basis", "D-015")
    elif sequence == 0 and active:
        allocation, amount, percent, basis = route_code("remainder", "sequenceNumber", MappingBasis.INFERRED), NA, NA, NA
        ctx.diag(DiagnosticCode.INFERRED_MAPPING, Severity.INFO, "Active sequence 0 ('0 = Net Pay') read as the remainder account.",
                 "allocation_type", "D-015")
    else:
        allocation, basis = {"value": "unknown", "raw_code": "sequenceNumber", "raw_label": None, "basis": MappingBasis.UNMAPPED.value}, NP
        ctx.diag(DiagnosticCode.UNKNOWN_CODE, Severity.WARNING,
                 "No amount or percent, and not an active sequence 0 account: allocation unknown.", "allocation_type", "D-015")
    ctx.keep(f"directdeposits:[{index}].description", item.get("description"))  # row: directdeposits [].description
    routing = ctx.text(item.get("routingNumber"), "routing_number", sensitive=True)  # row: directdeposits [].routingNumber
    account = ctx.text(item.get("accountNumber"), "account_number", sensitive=True)  # row: directdeposits [].accountNumber
    return build(
        DirectDeposit,
        id=_id(tenant, EntityType.DIRECT_DEPOSIT, legal, deposit_id),
        provider=Provider.ISOLVED,
        tenant_id=tenant,
        source_ids={"clientId": client, "legalId": legal, "employeeId": employee, "id": deposit_id},
        sources=[source(ROUTES["directdeposits"], f"/{index}")],
        company_id=_id(tenant, EntityType.COMPANY, legal),
        employee_id=_id(tenant, EntityType.EMPLOYEE, legal, employee),
        sequence=sequence,
        allocation_type=allocation,
        percent_basis=basis,
        amount=amount,
        percent=percent,
        skip_if_insufficient=NP,
        account_type=ctx.coded("isolved.deposit_account_type", item.get("accountType"), "account_type"),  # row: directdeposits [].accountType
        bank_name=ctx.text(item.get("bankName")),  # row: directdeposits [].bankName
        routing_number=routing,
        routing_last4=NA if not isinstance(routing, Null) else NP,
        account_number=account,
        account_last4=NA if not isinstance(account, Null) else NP,
        status=status,
        prenote_status=NP,
        frequency=ctx.coded("isolved.deposit_frequency", item.get("frequency"), "frequency"),  # row: directdeposits [].frequency
        applies_to_paycheck_kinds=NP,
        effective_from=NP,  # no date field (table notes)
        effective_to=NP,
        currency=USD,
        diagnostics=ctx.diagnostics,
        provider_extensions=ctx.extensions,
        sensitive_provider_extensions=ctx.sensitive_extensions,
    )

