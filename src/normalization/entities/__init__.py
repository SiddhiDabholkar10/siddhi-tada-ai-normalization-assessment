"""Entity adapters other than employees (D-085, D-088): ``entities/<provider>/<module>.py``, one per
mapping table, each with ``PROVIDER``, ``TABLE``, ``ROUTES`` and ``normalize(bundle)``, registered
in ``pipeline.ADAPTERS``. ``# row:`` comments cite the table rows applied (test_table_conformance).

``SENT_TO_EMPLOYEE`` lists the source items a table's rows classify but its adapter turns into no
record, because a table note sends them to the employee instead. The employee adapter keeps every
classified leaf of such an item in ``Employee.provider_extensions`` under ``<short>:<path from
the response root>`` (D-080 key form), so nothing returned is dropped (CANONICAL_MODEL 1.12). Items
gathered from several pages of a paged route add the page to the prefix,
``<short>(page=<n>):<path>`` (D-090 review; ``page`` as sent, zero-based, D-092), so two pages' ``results[0]`` never overwrite each
other. The conformance test looks for those leaves on the employees and classifies the keys with
``table``.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class SentToEmployee:
    provider: str
    table: str  # the mapping table whose rows classify the leaves
    short: str  # key prefix of the kept leaves
    route: str
    condition: str  # which items go to the employee


SENT_TO_EMPLOYEE = (
    SentToEmployee("prismhr", "deduction_setup", "getDeductionArrears", "/deductions/v1/getDeductionArrears",
                   "arrears entries whose dedCode matches no setup of the employee (deduction_setup notes)"),
    SentToEmployee("isolved", "deduction_setup", "legalPayItems", "/api/clients/{clientId}/legals/{legalId}/payItems",
                   "legal pay item entries whose per-employee payItemType is not Deduction (Earning, Memo Calc)"),
    SentToEmployee("isolved", "deduction_setup", "employeePayItems",
                   "/api/clients/{clientId}/legals/{legalId}/employees/{employeeId}/payItems",
                   "payItemType and calcParams of the per-employee entries joined to those legal entries"),
)
