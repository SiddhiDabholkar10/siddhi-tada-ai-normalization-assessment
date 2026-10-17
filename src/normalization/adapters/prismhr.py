"""PrismHR adapter: runs the normalization pipeline for PrismHR (D-087).

The source mappings live in the mapping tables (``mappings/data/prismhr/``) and the modules that
apply them (``normalization/employees/prismhr.py`` and, as Phase 5 adds them,
``normalization/entities/prismhr/``); ``normalization.pipeline`` runs them together so links
between records can be checked.
"""
from typing import Any, Dict

from .common import normalize_provider


def normalize(entity: str, response: Any, reference: Dict[str, Any], *, show_sensitive: bool = False, input_name: str | None = None) -> Any:
    """Return the candidate-designed JSON-serializable canonical result.

    ``response`` is a PrismHR provider bundle (every API response of one tenant; a ``Bundle`` or
    the bundle JSON parsed with ``parse_source_json``). ``entity`` is a mapping table name, a list
    of them, or None for all. ``reference`` is the lookup reference from ``contracts/``; it is
    accepted for the starter signature and not read at run time, because the mapping tables
    already carry the documented code meanings with their citations. Returns the output document
    (``run`` plus the record lists), sensitive values masked unless ``show_sensitive``.
    """
    return normalize_provider("prismhr", entity, response, show_sensitive, input_name)
