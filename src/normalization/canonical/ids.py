"""Deterministic canonical identifiers.

Format: ``{provider}:{tenant_id}:{entity}:{source part}[:{source part}...]``, for example
``prismhr:970592:employee:102:A00024``. Source parts are the provider's own identifiers,
percent-encoded so a ``:`` inside a source id cannot break the format.
"""
from enum import StrEnum
from typing import NamedTuple
from urllib.parse import quote, unquote

SEPARATOR = ":"


class Provider(StrEnum):
    PRISMHR = "prismhr"
    ISOLVED = "isolved"
    UKG_READY = "ukg-ready"


class EntityType(StrEnum):
    COMPANY = "company"
    # Lists owned by a company; given ids so employees and payroll can refer to them.
    TAX_ENTITY = "tax_entity"
    WORK_LOCATION = "work_location"
    PAY_GROUP = "pay_group"
    DEDUCTION_CODE = "deduction_code"
    EARNING_CODE = "earning_code"
    EMPLOYEE = "employee"
    DIRECT_DEPOSIT = "direct_deposit"
    DEDUCTION_SETUP = "deduction_setup"
    BENEFIT_ENROLLMENT = "benefit_enrollment"
    PAYROLL_RUN = "payroll_run"
    PAYCHECK = "paycheck"


class ParsedId(NamedTuple):
    provider: Provider
    tenant_id: str
    entity: EntityType
    source_parts: tuple[str, ...]


def _encode(part: str) -> str:
    if not isinstance(part, str) or part == "":
        raise ValueError(f"id parts must be non-empty strings, got {part!r}")
    return quote(part, safe="")


def canonical_id(provider: Provider, tenant_id: str, entity: EntityType, *source_parts: str) -> str:
    """Build a canonical id. The same inputs always give the same id."""
    if not source_parts:
        raise ValueError("a canonical id needs at least one source id part")
    parts = [Provider(provider).value, _encode(tenant_id), EntityType(entity).value]
    parts += [_encode(part) for part in source_parts]
    return SEPARATOR.join(parts)


def parse_canonical_id(value: str) -> ParsedId:
    """Split a canonical id back into its parts. Raises ValueError if malformed."""
    parts = value.split(SEPARATOR)
    if len(parts) < 4 or any(part == "" for part in parts):
        raise ValueError(f"malformed canonical id: {value!r}")
    provider, tenant, entity, *source = parts
    return ParsedId(Provider(provider), unquote(tenant), EntityType(entity), tuple(unquote(p) for p in source))
