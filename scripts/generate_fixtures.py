"""Seeded fixture generation from the contracts: writes the synthetic provider bundles and their
manifest to fixtures/.

The generator lives in ``normalization.fixtures`` (also run as ``python -m normalization
generate-fixtures``). It builds one bundle per provider from a fixed seed, validates every
response against its contract schema, and writes byte-identical files for the same seed.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from normalization.fixtures.write import DEFAULT_SEED, write_fixtures  # noqa: E402


def generate(seed: int = DEFAULT_SEED) -> list[Path]:
    return write_fixtures(ROOT / "fixtures", seed)


if __name__ == "__main__":
    for path in generate():
        print(path.relative_to(ROOT))
