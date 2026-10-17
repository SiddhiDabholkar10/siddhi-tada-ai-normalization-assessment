# Canonical JSON Schemas

Generated files: do not edit by hand. The Pydantic models in `src/normalization/canonical/` are
the source of truth (D-035); these files are exported from them (D-058):

```sh
python -m normalization export-schemas            # writes schemas/*.schema.json
```

A test (`tests/test_canonical_schemas.py`) fails when a committed file differs from what the
models generate, so the files cannot go stale silently.

| File | Record |
| --- | --- |
| `company.schema.json` | Company, with tax entities, work locations, pay groups, deduction and earning codes |
| `employee.schema.json` | Employee |
| `direct_deposit.schema.json` | Direct deposit allocation |
| `deduction_setup.schema.json` | Employee deduction setup |
| `benefit_enrollment.schema.json` | Benefit enrollment |
| `payroll_run.schema.json` | Payroll run |
| `paycheck.schema.json` | Paycheck with its lines |

## What the schemas describe

- **Output, not input.** Each schema is generated in serialization mode, so it describes the
  JSON that `to_json()` writes. Amounts, percentages, rates and hours are fixed-point strings
  (`"940.00"`, `"-1461.27"`) matching `^-?\d+(\.\d+)?$`, never JSON numbers.
- **Dialect:** JSON Schema 2020-12 (`$schema`); `$id` is the file name. Each file is
  self-contained: nested parts are in its own `$defs`.
- **Markers:**
  - `"x-sensitive": true` marks fields that output layers mask by default (D-036). The markers
    equal the model's `sensitive_fields()` list; a test checks this.
  - `"x-scale": "percent"` (0 to 100) or `"fraction"` (0.062 = 6.2%) on percentages and rates.

## What the schemas do not encode

Rules that span several fields or records are **not encoded** in these files. Some of them could
be expressed in JSON Schema (for example with `if`/`then`), but here they are enforced only by
the Python models and the link check. A document that validates against a schema can still
break them:

- **Null explanation:** every null field has a `field_status` entry, no entry names a field
  that has a value, and blank strings are not used for "no value" (`docs/CANONICAL_MODEL.md`
  1.3).
- **Ids:** a record's `id` matches its `provider`, `tenant_id` and entity type; references
  name the right entity type in the same provider and tenant (1.2).
- **Coded values:** `unknown` and basis `unmapped` occur together (1.7).
- **Record rules:**
  - direct deposit allocation values and the 0 to 100 percent bound (section 5);
  - deduction setup source basis rules (6.2);
  - paycheck `derived_totals` and reversal rules (section 8).
- **Cross-record links:** ownership of tax entities, pay groups, codes and runs; employee and
  deposit links (`find_link_problems`, D-045).

Use the Python models (`model_validate_json`) to check a document fully.
