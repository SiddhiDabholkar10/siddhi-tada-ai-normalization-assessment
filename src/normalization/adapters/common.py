"""What the three provider adapters share (D-087): run the pipeline on a bundle of one provider
and return the output document as JSON data."""
from collections.abc import Iterable
from typing import Any

from ..employees.bundle import Bundle, bundle_from_data
from ..output import build_document
from ..pipeline import normalize_bundle


def normalize_provider(
    provider: str,
    entity: str | Iterable[str] | None,
    response: Any,
    show_sensitive: bool = False,
    input_name: str | None = None,
) -> dict[str, Any]:
    """``response`` is a provider bundle: a ``Bundle``, or the bundle JSON parsed with
    ``parse_source_json`` (exact decimals, D-025). ``entity`` is a mapping table name
    (``company``, ``employee``, ``direct_deposit``, ``deduction_setup``, ``benefit_enrollment``,
    ``payroll``), several, or None for all. The whole bundle is normalized, validated and link
    checked either way; ``entity`` only chooses the lists returned. Sensitive values are masked
    unless ``show_sensitive``."""
    bundle = response if isinstance(response, Bundle) else bundle_from_data(response)
    if bundle.provider.value != provider:
        raise ValueError(f"bundle provider is {bundle.provider.value!r}, not {provider!r}")
    entities = [entity] if isinstance(entity, str) else (list(entity) if entity else None)
    return build_document(normalize_bundle(bundle), input_name, show_sensitive, entities)
