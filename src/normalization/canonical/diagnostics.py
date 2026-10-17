"""Diagnostics attached to canonical records.

A diagnostic records anything the adapter had to assume, could not map, or found
inconsistent. Messages and evidence never contain sensitive values (SSN, account numbers).
"""
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class Severity(StrEnum):
    INFO = "info"  # expected provider behavior worth knowing (e.g. empty list sent as 404)
    WARNING = "warning"  # meaning is uncertain or partially lost; the record is still usable
    ERROR = "error"  # a value could not be used; the affected field is null


class DiagnosticCode(StrEnum):
    UNKNOWN_CODE = "unknown_code"  # source code has no canonical mapping; value is unknown
    INFERRED_MAPPING = "inferred_mapping"  # canonical value inferred from indirect evidence
    VALUE_REDACTED_IN_SOURCE = "value_redacted_in_source"  # provider masked the value (D-020)
    SENTINEL_DATE = "sentinel_date"  # placeholder date where a real date is required (D-025)
    EMPTY_VIA_404 = "empty_via_404"  # route reports "no records" as HTTP 404 (D-011)
    SOURCE_UNAVAILABLE = "source_unavailable"  # route refused (401/403), not exposed, or an error withholds the data (UKG 400 "Cost Center not used")
    UNPARSEABLE_VALUE = "unparseable_value"  # value could not be parsed to the canonical type
    RECONCILIATION_MISMATCH = "reconciliation_mismatch"  # provider totals disagree with line items
    # A missing input prevents a specific total or comparison; that total stays null (not_provided)
    # and no mismatch is claimed (D-053).
    RECONCILIATION_INCOMPLETE = "reconciliation_incomplete"
    CONFLICTING_SOURCES = "conflicting_sources"  # two provider sources disagree on one fact
    UNIT_UNVERIFIED = "unit_unverified"  # unit or scale not established; value kept raw
    DEPRECATED_SOURCE = "deprecated_source"  # data came from a route the provider marks deprecated
    UNVALIDATED_SOURCE = "unvalidated_source"  # record comes from a source not validated for this meaning (D-017)
    UNSTABLE_ID = "unstable_id"  # id rests on the source's list order, not a provider id (D-046)
    REFERENCE_ONLY = "reference_only"  # entry built from the records that name it; the provider's own list omits it (D-094)


class Diagnostic(BaseModel):
    """One finding about a record.

    ``field`` is a path within the record (``deductions[2].category``); null means the finding
    is about the whole record. ``evidence`` cites a decision id or spec pointer; null means
    none applies. These nulls are part of the type's meaning, so Diagnostic is a value type
    and is not subject to the field_status rule.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: DiagnosticCode
    severity: Severity
    message: str
    field: str | None = None
    evidence: str | None = None
