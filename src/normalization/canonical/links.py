"""Cross-record link checks, run when a set of records is assembled (D-045).

Model validation (``CanonicalRecord.check_reference``) proves a reference has the right
entity type, provider and tenant. It cannot prove ownership: a pay group id of another company
in the same tenant is well formed. These checks need the other records, so they run on the
assembled set and return problems for the caller to report.
"""
from collections.abc import Iterable

from typing import Any

from .benefits import BenefitEnrollment
from .company import Company
from .deductions import DeductionSetup
from .deposits import DirectDeposit
from .employee import Employee
from .enums import QuantityType
from .payroll import Paycheck, PayrollRun
from .values import UNKNOWN

DEDUCTION_CLASSIFICATION = ("category", "tax_treatment", "is_catch_up")
EARNING_CLASSIFICATION = ("pay_class", "is_cash", "rate_class")


def _classification_conflicts(where: str, item: Any, code: Any, fields: tuple[str, ...]) -> list[str]:
    """An item linked to a code must not classify it differently (D-047, D-054: classified
    once). Only values both sides carry are compared; a null or an unknown value on either side
    is not a conflict, since unknown makes no claim (D-089: an isolved garnishment line is category
    garnishment from its route while its catalog code is unknown)."""
    problems = []
    for field in fields:
        mine, theirs = getattr(item, field), getattr(code, field)
        if mine is None or theirs is None:
            continue
        if not isinstance(mine, bool) and UNKNOWN in (mine.value.value, theirs.value.value):
            continue
        if isinstance(mine, bool):
            if mine != theirs:
                problems.append(f"{where}: {field} conflicts with its code")
        elif mine.value != theirs.value:
            problems.append(f"{where}: {field} {mine.value.value!r} conflicts with its code's {theirs.value.value!r}")
    return problems


def _owned_code(where: str, field: str, code_id: str | None, codes: dict, company_id: str) -> tuple[Any, list[str]]:
    """The company code ``code_id`` names, or a problem if the company does not own it."""
    if code_id is None:
        return None, []
    code = codes.get(code_id)
    if code is None:
        return None, [f"{where}: {field} {code_id!r} is not owned by company {company_id!r}"]
    return code, []


def find_link_problems(
    companies: Iterable[Company],
    employees: Iterable[Employee],
    deposits: Iterable[DirectDeposit] = (),
    setups: Iterable[DeductionSetup] = (),
    enrollments: Iterable[BenefitEnrollment] = (),
    runs: Iterable[PayrollRun] = (),
    paychecks: Iterable[Paycheck] = (),
) -> list[str]:
    """Problems with links between the given records, in a stable order.

    Employees:
    - ``company_id`` must name a company in the set.
    - ``tax_entity_id``, ``compensation.pay_group_id`` and the ``work_location_id`` of ``job``
      and of every ``job_history`` entry must be owned by the employee's own company.
    - ``manager_employee_id`` and ``supervisor_employee_id`` of ``job`` and of every
      ``job_history`` entry must name an employee in the set. They may be in another company of
      the tenant: isolved manager references carry their own legal id.

    Deposits, deduction setups, benefit enrollments:
    - ``employee_id`` must name an employee in the set whose company is the record's company.
    - A setup's ``deduction_code_id`` must be owned by that company, the setup must not
      classify the deduction differently from that code, and its ``benefit_enrollment_id``
      must name an enrollment of the same employee.

    Payroll runs:
    - ``company_id`` must name a company in the set; ``tax_entity_id`` and each pay period's
      ``pay_group_id`` must be owned by it.

    Paychecks (in addition to the employee rule above):
    - ``tax_entity_id`` and ``pay_group_id`` must be owned by the paycheck's company.
    - ``payroll_run_id`` must name a run in the set of the same company.
    - Earning, deduction and employer contribution lines must link only to codes the company
      owns, and earning and deduction lines must not reclassify their code.
    - An earning line linked to an hours code must not carry ``units``, and one linked to a
      units code must not carry ``hours``.
    - A payment's ``direct_deposit_id`` must name a deposit in the set of the same employee.
    - ``reverses_paycheck_id`` is not checked: the reversed paycheck may predate the synced
      window (PrismHR reversals point to vouchers from earlier batches).

    A set that does not hold every linked record (e.g. one company synced alone) reports the
    missing ones; the caller decides whether that is an error or a diagnostic.
    """
    by_company = {company.id: company for company in companies}
    employees = list(employees)
    by_employee = {employee.id: employee for employee in employees}
    enrollments = list(enrollments)
    enrollment_owner = {enrollment.id: enrollment.employee_id for enrollment in enrollments}
    runs = list(runs)
    by_run = {run.id: run for run in runs}
    deposits = list(deposits)
    by_deposit = {deposit.id: deposit for deposit in deposits}
    problems = []

    for employee in sorted(employees, key=lambda e: e.id):
        company = by_company.get(employee.company_id)
        if company is None:
            problems.append(f"{employee.id}: company_id {employee.company_id!r} is not in the set")
            continue
        pay = employee.compensation
        problems += _not_owned(employee.id, "tax_entity_id", employee.tax_entity_id, company.tax_entities, company.id)
        problems += _not_owned(employee.id, "compensation.pay_group_id", pay.pay_group_id if pay else None, company.pay_groups, company.id)
        jobs = [("job", employee.job)] if employee.job is not None else []
        jobs += [(f"job_history[{index}]", entry) for index, entry in enumerate(employee.job_history or [])]
        for where, job in jobs:
            problems += _not_owned(employee.id, f"{where}.work_location_id", job.work_location_id, company.work_locations, company.id)
            for field in ("manager_employee_id", "supervisor_employee_id"):
                value = getattr(job, field)
                if value is not None and value not in by_employee:
                    problems.append(f"{employee.id}: {where}.{field} {value!r} is not in the set")

    for run in sorted(runs, key=lambda r: r.id):
        company = by_company.get(run.company_id)
        if company is None:
            problems.append(f"{run.id}: company_id {run.company_id!r} is not in the set")
            continue
        problems += _not_owned(run.id, "tax_entity_id", run.tax_entity_id, company.tax_entities, company.id)
        for index, period in enumerate(run.pay_periods or []):
            problems += _not_owned(run.id, f"pay_periods[{index}].pay_group_id", period.pay_group_id, company.pay_groups, company.id)

    for record in sorted([*deposits, *setups, *enrollments, *paychecks], key=lambda r: r.id):
        employee = by_employee.get(record.employee_id)
        if employee is None:
            problems.append(f"{record.id}: employee_id {record.employee_id!r} is not in the set")
        elif employee.company_id != record.company_id:
            problems.append(f"{record.id}: company_id {record.company_id!r} differs from its employee's company")
        company = by_company.get(record.company_id)
        deduction_codes = {item.id: item for item in (company.deduction_codes or [])} if company else {}
        earning_codes = {item.id: item for item in (company.earning_codes or [])} if company else {}
        if isinstance(record, DeductionSetup):
            code, found = _owned_code(record.id, "deduction_code_id", record.deduction_code_id, deduction_codes, record.company_id)
            problems += found
            if code is not None:
                problems += _classification_conflicts(record.id, record, code, DEDUCTION_CLASSIFICATION)
            enrollment_id = record.benefit_enrollment_id
            if enrollment_id is not None and enrollment_owner.get(enrollment_id) != record.employee_id:
                problems.append(f"{record.id}: benefit_enrollment_id {enrollment_id!r} is not an enrollment of the same employee in the set")
        if isinstance(record, Paycheck):
            problems += _paycheck_problems(record, company, by_run, by_deposit, deduction_codes, earning_codes)
    return problems


def _not_owned(where: str, field: str, value: str | None, items: list | None, company_id: str) -> list[str]:
    if value is None or value in {item.id for item in items or []}:
        return []
    return [f"{where}: {field} {value!r} is not owned by company {company_id!r}"]


def _quantity_conflicts(where: str, line: Any, code: Any) -> list[str]:
    """An earning line must hold its quantity where its code says it belongs (unit rule, D-051):
    an hours code puts it in ``hours``, a units code in ``units``. ``hours_worked`` is not
    constrained: PrismHR documents it as hours worked from the time sheet for every pay code."""
    kind = code.quantity_type.value if code.quantity_type is not None else None
    if kind is QuantityType.HOURS and line.units is not None:
        return [f"{where}: units is set but its code counts hours"]
    if kind is QuantityType.UNITS and line.hours is not None:
        return [f"{where}: hours is set but its code counts units"]
    return []


def _paycheck_problems(
    paycheck: Paycheck,
    company: Company | None,
    by_run: dict,
    by_deposit: dict,
    deduction_codes: dict,
    earning_codes: dict,
) -> list[str]:
    where, problems = paycheck.id, []
    if company is not None:
        problems += _not_owned(where, "tax_entity_id", paycheck.tax_entity_id, company.tax_entities, company.id)
        problems += _not_owned(where, "pay_group_id", paycheck.pay_group_id, company.pay_groups, company.id)
    if paycheck.payroll_run_id is not None:
        run = by_run.get(paycheck.payroll_run_id)
        if run is None:
            problems.append(f"{where}: payroll_run_id {paycheck.payroll_run_id!r} is not in the set")
        elif run.company_id != paycheck.company_id:
            problems.append(f"{where}: payroll_run_id {paycheck.payroll_run_id!r} belongs to another company")
    for index, line in enumerate(paycheck.earnings or []):
        field = f"earnings[{index}].earning_code_id"
        code, found = _owned_code(where, field, line.earning_code_id, earning_codes, paycheck.company_id)
        problems += found
        if code is not None:
            problems += _classification_conflicts(f"{where} earnings[{index}]", line, code, EARNING_CLASSIFICATION)
            problems += _quantity_conflicts(f"{where} earnings[{index}]", line, code)
    for index, line in enumerate(paycheck.deductions or []):
        field = f"deductions[{index}].deduction_code_id"
        code, found = _owned_code(where, field, line.deduction_code_id, deduction_codes, paycheck.company_id)
        problems += found
        if code is not None:
            problems += _classification_conflicts(f"{where} deductions[{index}]", line, code, DEDUCTION_CLASSIFICATION)
    for index, line in enumerate(paycheck.employer_contributions or []):
        prefix = f"employer_contributions[{index}]"
        problems += _owned_code(where, f"{prefix}.deduction_code_id", line.deduction_code_id, deduction_codes, paycheck.company_id)[1]
        problems += _owned_code(where, f"{prefix}.earning_code_id", line.earning_code_id, earning_codes, paycheck.company_id)[1]
    for index, line in enumerate(paycheck.payments or []):
        if line.direct_deposit_id is None:
            continue
        deposit = by_deposit.get(line.direct_deposit_id)
        field = f"payments[{index}].direct_deposit_id {line.direct_deposit_id!r}"
        if deposit is None:
            problems.append(f"{where}: {field} is not in the set")
        elif deposit.employee_id != paycheck.employee_id:
            problems.append(f"{where}: {field} belongs to another employee")
    return problems
