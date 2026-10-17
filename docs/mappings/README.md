# Mapping tables

How each provider's responses map to the canonical model (`docs/CANONICAL_MODEL.md`). The
tables are JSON data in `src/normalization/mappings/data/<provider>/`; the other files in this
folder are generated from them (`python -m normalization export-mappings`) and a test fails when
they differ. Decision ids (D-xxx) refer to the assumptions and decisions file.

The tables describe the mapping. The adapters are ordinary Python that follows them; nothing
interprets the tables at run time.

## What the tables prove

Checked offline by `tests/test_mappings.py`, against the reference material in `contracts/`:

1. **Routes.** Every documented GET route of a provider falls under exactly one entry: a
   selected route, a route excluded with its own reason, or an excluded family (a set of route
   patterns with one reason). Counts: PrismHR 253 (OpenAPI), isolved 302 (primary Swagger, D-007),
   UKG Ready 269 (reference pages; 260 have an extracted response schema).
2. **Fields.** For every selected route marked `classified`, every field of its documented
   response is classified by exactly one row: mapped to a canonical field, kept as an extension,
   kept as a sensitive extension, or excluded with a reason.
3. **Targets and evidence.** Every canonical field named exists in the models; every contract
   citation resolves; every code table value is a value of its canonical enum, and `unknown`
   occurs only with basis `unmapped`.

Fields seen in live demo responses but not documented are classified too (rows marked
`live_only`). The live samples are private and not in this repository, so that part is checked
with a local tool and recorded in the decisions file, not by the tests.

## Route list (`routes.json`)

| Key | Meaning |
| --- | --- |
| `selected[]` | `route` (template as documented), `entities`, `classified` (all fields classified), `note`. `schema`: `not_extracted` (UKG page without an extracted schema) or `not_documented` (spec without a 200 schema): fields then come from the page or live samples. `live_renames`: documented path prefix to the prefix the live API sends instead (PrismHR documents `payrollVouchers`, the demo sends `payrollVoucher`), so one set of rows covers both. |
| `excluded[]` | Either `route` with a `reason`, or `family` with `routes` (patterns) and one `reason`. |

Patterns: `*` matches within one path segment, `**` matches any number of segments
(`/timesheet/**` covers `/timesheet` and everything below it).

## Field rows (`<entity>.json`)

An entity file holds `notes` (rules that are not about one source field, such as how a record is
built when the provider has no route for it), `fields` (the rows below) and `code_tables`.

| Key | Meaning |
| --- | --- |
| `route` | Selected route (or a list of routes with the same response model). |
| `field` | Field path in the response: keys joined by `.`, `[]` for array items, `{key}` for map values. A pattern (`*`, `**`) classifies a group of fields with one reason, such as `**.links.**`. An exact row wins over a pattern row; among pattern rows, the one with the most fixed segments wins (`clientMaster.clientTax[].*` over `clientMaster.**`), and a tie is a mistake. |
| `use` | `mapped`, `extension`, `sensitive_extension` or `excluded`. |
| `target` | Canonical field (`Employee.name.first`), or the record's `provider_extensions` / `sensitive_provider_extensions`. |
| `transform` | A label naming the rule (below). |
| `evidence` | Contract citations (`contracts/...#/json/pointer` or a reference page), decision ids (`D-0xx`), or `live: ...` observations with sample sizes. |
| `reason`, `note` | Required for every use other than `mapped`. |
| `live_only` | Seen in live responses, not in the documented schema. |

Transform labels: `copy`, `number`, `boolean`, `yes_no_declined` (Y true, N false, blank not
provided; a declined answer `D` is not provided as a value and the raw answer is kept in
`sensitive_provider_extensions`, so declined and blank stay apart), `timestamp`, `date:<role>` (`event`,
`period_start`, `period_end`, CANONICAL_MODEL 1.6), `ms_to_hours`, `code:<table id>`, `masked`,
`last4`, `source_id`, `reference`, `join`, `derive` (the last two explained in the row's note).

## Code tables

Per provider code list: `id` (`<provider>.<name>`), `source`, `columns` (column name to canonical
enum), and `codes[]` with `raw`, `label`, one `{value, basis}` per column, and `evidence`. One
code can set several enums (a PrismHR deduction type sets category and tax treatment, D-047).
