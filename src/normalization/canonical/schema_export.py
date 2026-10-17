"""JSON Schema export of the canonical records (D-058).

One self-contained file per record, generated in serialization mode, so each schema describes
what ``to_json`` writes (amounts as fixed-point strings). The Pydantic models stay the source
of truth: rules they enforce across fields (the null-explanation rule, id consistency, coded
value rules, allocation and derived total constraints, cross-record links) are not encoded in
the exported files.
"""
import json
from pathlib import Path

from pydantic import BaseModel

from .benefits import BenefitEnrollment
from .company import Company
from .deductions import DeductionSetup
from .deposits import DirectDeposit
from .employee import Employee
from .payroll import Paycheck, PayrollRun

JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"

# File name per record. Order is the order records link in: company first, payroll last.
SCHEMA_FILES: dict[str, type[BaseModel]] = {
    "company.schema.json": Company,
    "employee.schema.json": Employee,
    "direct_deposit.schema.json": DirectDeposit,
    "deduction_setup.schema.json": DeductionSetup,
    "benefit_enrollment.schema.json": BenefitEnrollment,
    "payroll_run.schema.json": PayrollRun,
    "paycheck.schema.json": Paycheck,
}


def record_schema(file_name: str) -> dict:
    """The exported schema for one record: Pydantic's serialization schema plus a header."""
    schema = SCHEMA_FILES[file_name].model_json_schema(mode="serialization")
    return {"$schema": JSON_SCHEMA_DIALECT, "$id": file_name, **schema}


def render_schemas() -> dict[str, str]:
    """Every schema file's exact text: sorted keys, 2-space indent, final newline (LF)."""
    return {name: json.dumps(record_schema(name), indent=2, sort_keys=True, ensure_ascii=False) + "\n" for name in SCHEMA_FILES}


def write_schemas(out_dir: Path) -> list[Path]:
    """Write every schema file into ``out_dir``, replacing existing ones. Returns the paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, text in render_schemas().items():
        path = out_dir / name
        path.write_bytes(text.encode("utf-8"))
        written.append(path)
    return written
