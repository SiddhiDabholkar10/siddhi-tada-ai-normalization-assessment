# Payroll data normalization: PrismHR, isolved and UKG Ready

This project reads company, employee, direct deposit, deduction, benefit and payroll data from
three payroll providers (PrismHR, isolved and UKG Ready) and turns it into one canonical model.
Records keep their links (company, employee, payroll run, paycheck), every null value says why it
is null, every inferred meaning is marked as inferred, and sensitive values are masked by default.

It can be used in four ways:

- **Offline, on synthetic fixtures** (no key, no network): `normalize` reads a provider bundle
  and writes one output document. This is what the tests use.
- **Live, on the organizer's demo tenants**: `fetch` signs in, crawls the provider APIs and
  normalizes the result with the same pipeline.
- **In a web app**: `serve` starts an API and a browser UI over the same pipeline, to browse
  companies, employees, deposits, deductions, benefits, payroll and diagnostics, and to sync a
  demo tenant.
- **Writing an employee back to a provider**: the optional write path turns a canonical employee
  into a provider's create or update requests. Every provider gets a dry run; UKG Ready is also
  written for real.

Assumptions, decisions and limitations, with the reasons for each, are in
[ASSUMPTIONS_DECISIONS_LIMITATIONS.md](ASSUMPTIONS_DECISIONS_LIMITATIONS.md).

## Quick start

### Requirements

- Python 3.13
- Dependencies are pinned in `requirements.txt`: pydantic and jsonschema for the model, FastAPI
  and uvicorn for the web app, with their requirements.
- Node is not needed: the web UI is committed already built. Node 20.18 or later is needed only to
  change the UI.
- On Windows, clone into a short folder path (for example `C:\src\tada`). Some contract file
  names are long, and a deep folder can push them past the 260 character path limit, so they are
  not checked out.

### Set up and run the tests

Windows (PowerShell):

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:PYTHONPATH = "src"; $env:PYTHONUTF8 = "1"
python -m unittest discover -s tests
```

macOS / Linux:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export PYTHONPATH=src
python -m unittest discover -s tests
```

Set the two environment variables in each new terminal:

- `PYTHONPATH=src` makes the `normalization` package importable.
- `PYTHONUTF8=1` (Windows only): two of the organizer's reference tests read UTF-8 files without
  naming the encoding, which fails under the Windows default `cp1252`.

The suite runs 245 tests in about 10 seconds, fully offline: no key, network or live data. One
test, the UI's own check, is skipped when Node is not installed.

### Normalize the synthetic fixtures

No key or network needed. Each provider has a synthetic bundle in `fixtures/<provider>/bundle.json`.

```sh
# The output document as JSON on standard output, sensitive values masked
python -m normalization normalize --input fixtures/prismhr/bundle.json
python -m normalization normalize --input fixtures/isolved/bundle.json
python -m normalization normalize --input fixtures/ukg-ready/bundle.json

# Written to a file (an existing file is never overwritten)
python -m normalization normalize --input fixtures/ukg-ready/bundle.json --output ukg.json

# Only some record lists (the whole bundle is still normalized and checked)
python -m normalization normalize --input fixtures/prismhr/bundle.json --entity employee --entity payroll

# Sensitive values in full: an explicit opt-in, with a warning
python -m normalization normalize --input fixtures/ukg-ready/bundle.json --show-sensitive
```

### Fetch live data from a demo tenant

Put the organizer's key in `DEMO_SIGNIN_API_KEY`, either as an environment variable or in a
`.env` file at the repository root (`DEMO_SIGNIN_API_KEY=...`). Both are Git-ignored, and the key
is never printed or written.

```sh
python -m normalization fetch --tenant ukg      # about 4 minutes
python -m normalization fetch --tenant isol     # about 13 minutes
python -m normalization fetch --tenant prism    # about 12 minutes, all 25 clients

# A quicker run: one PrismHR client, keeping the raw responses as a bundle
python -m normalization fetch --tenant prism --company 103 --save-bundle

# A saved bundle normalizes again offline, with no network
python -m normalization normalize --input live_data/<file>.bundle.json
```

Output goes to `live_data/` (Git-ignored), masked by default. A saved bundle holds unmasked
personal data, so keep it local. The tests never call the live APIs.

### Start the web app

```sh
python -m normalization serve      # then open http://127.0.0.1:8000
```

On the first start the app creates its store, one SQLite file at `live_data/app.db`
(Git-ignored), and loads the three synthetic fixture bundles into it, so data shows at once with
no key. SQLite comes with Python; nothing else needs installing or configuring.

- **Pages:** Overview (record counts, companies), Employees (search and company filter; each
  employee's profile, direct deposits, deductions, benefits, paychecks with their lines, and
  diagnostics), Payroll (runs newest first, with their paychecks), Diagnostics (counts by code and
  the records behind each count), Sync, and Write employee.
- **Sync** runs the same fetch as `fetch --tenant` in the background and stores the result. It
  needs `DEMO_SIGNIN_API_KEY`, as `fetch` does.
- **Masked by default:** every API response is masked unless the request asks for full values.
  In the UI, the "Show sensitive values" switch starts off on every page load and shows a warning
  banner while it is on.
- **API:** interactive documentation at `http://127.0.0.1:8000/api/docs`.
- Existing results can be loaded into the app: `import-output <file>` for an output document,
  `import-bundle <file>` for a raw bundle saved with `fetch --save-bundle` (normalized again, with
  full values).

The UI was built late and under time pressure, so it can be a little finicky in places (layout
on narrow windows, some edge cases in the write form). The API and the command line underneath it
are the tested, reliable path.

### Write an employee to a provider

The write path takes one canonical employee and builds the requests that create or update it in
a destination provider: the calls in order, and every field that is refused with the reason.

```sh
# Dry run from a fixture bundle: prints the plan (exit 2 when something is refused)
python -m normalization write --input fixtures/isolved/bundle.json --employee isolved:900002:employee:6001:70001 --to isolved --operation update

# A refused plan: a create into UKG needs the UKG company, a username and a start date
python -m normalization write --input fixtures/isolved/bundle.json --employee isolved:900002:employee:6001:70001 --to ukg-ready

# Across providers, the destination's own codes are given as inputs
python -m normalization write --input fixtures/ukg-ready/bundle.json --employee ukg-ready:900003:employee:7001:1101 --to prismhr --set company=103 --set employment_status=A --set work_location=GA --set job=8603N5 --set pay_group=BW --set peo_start_date=2024-01-02
```

In the app, open an employee and choose **Write to a provider**, or open **Write employee** and
choose **Start blank** for a new hire. The form shows only the fields the chosen provider accepts,
and **Review and send** shows the exact request. A UKG Ready plan with nothing missing can be sent
for real (with the key), after a confirmation; isolved and PrismHR always stay dry runs.

### Command options

`normalize`:

| Option | Meaning |
| --- | --- |
| `--input <file>` | The provider bundle to normalize (required) |
| `--provider <name>` | Optional; must match the provider the bundle names (`prismhr`, `isolved`, `ukg-ready`) |
| `--entity <table>` | Keep only these record lists in the output (repeatable): `company`, `employee`, `direct_deposit`, `deduction_setup`, `benefit_enrollment`, `payroll` (runs and paychecks) |
| `--output <file>` | File to create; refuses to overwrite. Default: standard output |
| `--show-sensitive` | Show sensitive values in full (prints a warning) |

`fetch`:

| Option | Meaning |
| --- | --- |
| `--tenant prism\|isol\|ukg` | The demo tenant (required) |
| `--company <id>` | Only this company (PrismHR client id, isolved legal id, UKG company id); repeatable. Default: all |
| `--pay-from`, `--pay-to` | The payroll window, both or neither (`YYYY-MM-DD`). Default: for each company, the 12 months ending on its latest pay date on or before today |
| `--as-of <date>` | The date treated as today. Default: today |
| `--output <file>` | File to create; refuses to overwrite. Default: `live_data/<provider>-<UTC time>.json` |
| `--save-bundle` | Also write the raw responses as `<output>.bundle.json` (tokens in URLs scrubbed) |
| `--show-sensitive` | Show sensitive values in full (prints a warning) |
| `--workers <n>` | Calls in parallel (default 4) |

`write` (dry run):

| Option | Meaning |
| --- | --- |
| `--input <file>` | The provider bundle the employee comes from (required) |
| `--employee <id>` | The canonical employee id (required) |
| `--to ukg-ready\|isolved\|prismhr` | The destination provider (required) |
| `--operation create\|update` | Default: create |
| `--set NAME=VALUE` | An input the destination needs (repeatable), such as a code, `username` or `start_date` |
| `--show-sensitive` | Show sensitive values in the plan in full |

`serve`: `--host` (default `127.0.0.1`), `--port` (default 8000), `--db` (default
`live_data/app.db`). `import-output <file>` and `import-bundle <file>` take the same `--db`.

`normalize` and `fetch` exit with status 1 and write nothing when a record fails validation or
normalization fails; a partial file is never left behind. Other commands:
`generate-fixtures` (rebuild the synthetic bundles, same seed, same bytes), `export-schemas` and
`export-mappings` (regenerate `schemas/` and `docs/mappings/`), and the organizer's
`list-providers` and `check-inputs`.

## Approach

The brief asks for transformations that preserve the meaning of the source data. Most of the
work therefore went into finding out what each provider field actually means, and into making
the output say plainly when that is not known. Six principles guided every mapping.

### 1. Evidence before mapping

Every mapping rests on a source: the provider's contract (PrismHR OpenAPI, isolved Swagger, UKG
Ready reference pages and lookup files) or a live observation, recorded with counts. The
contracts are old snapshots, so the demo tenants were used to check them, and they often
disagreed: different base URLs, different wrapper keys, different paging, fields documented as
one thing and sent as another. Where the two disagree, the mapping follows the data and the
difference is written down.

### 2. Never guess a code

A provider code whose meaning no source states maps to `unknown`, with the raw code and label
kept. A meaning that is read from a label or confirmed by arithmetic, but not stated by the
provider, is marked `inferred`, and the record carries an `inferred_mapping` diagnostic. Code
letters are never read as words: PrismHR's undocumented deduction type `VG` was classified as a
garnishment only after the data showed it is used for an IRS levy with the same calculation
method as the documented garnishment types, and it is still marked inferred.

### 3. Every null has a reason

A null field is listed in its object's `field_status` with one of three reasons:

- `not_provided`: no usable value was received (missing, blank, a placeholder date, an
  unparseable value, or a route the account could not read);
- `hidden_by_source`: the value exists, but the provider masked it;
- `not_applicable`: the field does not apply (for example the termination date of an active
  employee).

Validation rejects a null without a reason. A missing amount is never read as zero, and when a
missing amount prevents a check (net pay against payments, for example), the record says
`reconciliation_incomplete` instead of claiming a match.

### 4. Nothing returned is dropped

Everything the brief lists has a typed field, even when only one provider supplies it (the
others say `not_provided`). Every other field a selected route returns is kept in
`provider_extensions`, or in `sensitive_provider_extensions` when it is sensitive, unless it is
excluded with a written reason (credentials such as PINs and token URLs are always excluded).
At the route level, every documented GET route of each provider is either selected or excluded
with a reason, and tests enforce both rules.

### 5. Links are checked

All records of a tenant are built together, then a link check confirms that every reference
resolves: an employee's company, tax entity, pay group, work location and manager; a deposit's
or setup's employee; a paycheck's run, employee and codes. A broken link is reported in the
output, never hidden and never "fixed" by guessing.

### 6. Private by default

Sensitive values (SSNs and other national ids, bank account and routing numbers, EINs, birth
dates, tax withholding, and more) are kept in full inside the program, but every output shows
them masked (`***`). To see the real values, you have to ask for them explicitly with the
`--show-sensitive` flag (the command then prints a warning), or turn on the app's "Show
sensitive values" switch (a warning banner stays on while it is). A masked provider value is
never treated as a real one. Test fixtures are synthetic. Live data, keys and tokens never enter
Git.

### Matching providers, and keeping differences visible

Values from the three providers are mapped onto one shared set wherever a source shows they mean
the same thing: pay frequencies, employment statuses, deposit allocation types, deduction
categories, tax types and payment methods all use one canonical list, and PrismHR `earnAmount`
and isolved `grossPay` both fill `gross_pay`. Where the evidence does not show the same meaning,
the model keeps the difference instead of forcing a match. Two examples:

- **Run types:** PrismHR calls a batch "Scheduled" and UKG calls a payroll "Regular". They map
  to different values, because no source says the two mean the same thing.
- **Gross pay:** isolved sends `grossPay` and `grossWages` (which differ by imputed income) and
  PrismHR sends `earnAmount` and `totalEarnings` (which differ by "other earnings", mostly
  non-cash fringe). The paycheck has separately defined totals (`gross_pay`, `gross_wages`, `total_earnings`,
  `net_pay`), each filled only from a provider field with the same meaning, rather than one
  "gross" field holding three different figures.

## How it was built

### In phases

The work ran in phases, each building on the one before. Every phase started with a short
written design and ended with a review.

| Phase | What it produced |
| --- | --- |
| 0. Setup | Python, keeping the provided scaffold; the setup steps for Windows and macOS/Linux |
| 1. Discovery | Read-only calls to all three demo tenants: how each provider signs in, pages, reports errors and empty results, and where its data differs from its contract |
| 2. Canonical model | Pydantic v2 models for the seven record types, shared conventions (ids, numbers, dates, codes, null reasons, diagnostics, masking), exported JSON Schemas, and the fields needed to create an employee in each provider |
| 3. Mapping tables | For each provider, one table per record type classifying every field of every selected route as mapped, extension or excluded, with evidence; routes selected or excluded with reasons (PrismHR 26 of 253 documented GET routes selected, isolved 29 of 302, UKG Ready 31 of 269); readable docs generated from the tables |
| 4. Fixtures | A seeded generator producing one synthetic bundle per provider, every response validated against its contract schema, covering the edge cases the adapters must handle |
| 5. Adapters and pipeline | Adapters for every provider and record type, the output document, the validation gate, masking, the link check and the guard against wrongly shaped responses |
| 6. Tests | A lean suite: one test per rule, cases as subtests, a golden output per provider |
| 7. Live pipeline | The `fetch` command and full runs against all three demo tenants; every issue the real data revealed was fixed and tested |
| 7b. Application | A FastAPI app and a React UI over the pipeline, with a SQLite store, sample data on start, background sync and masking by default |
| 8. Write path | Create and update employee for all three providers as dry runs, and real writes to the UKG Ready demo tenant, checked by reading the employee back |

### How correctness was checked

- **Mapping tables are data, and tests hold the code to them.** Each adapter cites the table
  row it applies; a test compares those citations with the tables, and another checks that
  every field a route can return is classified. The Markdown in `docs/mappings/` is generated
  from the tables, so the docs cannot drift from the code.
- **Fixtures follow the contracts.** Every synthetic response is validated against the
  provider's documented schema, and a field the schema does not document is rejected unless it
  was seen live. Fixture values are invented (SSNs in the 666 area, routing numbers in a
  reserved range), generated from a fixed seed, and identical byte for byte on every run.
- **Rules are tested by breaking them.** When a rule was added, the code was broken on purpose
  once to confirm a test fails for the right reason.
- **Every step was reviewed** in a separate review pass, looking for blocking problems before
  the step was closed, and every choice was recorded with its reason
  ([ASSUMPTIONS_DECISIONS_LIMITATIONS.md](ASSUMPTIONS_DECISIONS_LIMITATIONS.md)).

### Live data during development

The optional demo access was used for discovery and for the final end-to-end runs. Raw samples
were kept in a private, Git-excluded folder with account numbers and SSNs redacted at save
time. They were never used as test input, and nothing from them is in this repository.

## Architecture

### From provider data to one output document

```text
   fixtures/<provider>/bundle.json              demo tenant (live API)
                 |                                       |
                 |                       live/client.py   sign-in, token refresh,
                 |                                        throttling, network retries
                 |                       live/plans/      what to call, per provider
                 |                       live/fetch.py    paging, pay window search
                 |                                       |
                 +---------------- a bundle ------------+
                                     |
                          pipeline.normalize_bundle
                                     |
          1. shape guard: set aside responses whose shape breaks the contract
          2. adapters: one per provider and record type
          3. assemble: one list per record type, in id order, ids unique
          4. link check across every record of the tenant
                                     |
                          output.build_document
                                     |
          5. validation gate: every record validated, else nothing is written
          6. masking: sensitive values shown as ***, unless --show-sensitive
                                     |
               one output document: run header + seven record lists
                                     |
          the web app (app/): stores the records in SQLite, serves them
          masked through the API and the UI; Sync runs the live fetch
                                     |
          the write path (write/): a stored or bundled employee becomes
          a provider's create or update requests (dry run, or a UKG send)
```

### Why the input is a bundle

A **bundle** is every raw response of one tenant in one JSON file: for each response, the route
template, the parameters sent, the HTTP status and the body. The pipeline takes a bundle rather
than a single API response for two reasons:

- One canonical record is built from many responses. A PrismHR employee, for example, comes
  from about 12 routes (profile, addresses, pay rates, history, dependents, and more).
- Links can only be checked when all records of a tenant are built together.

A live fetch fills a bundle in memory and hands it to the same pipeline, so live data and
fixtures go through exactly the same code. With `--save-bundle`, a live bundle is also written
to disk and can be normalized again later, offline.

### Packages

| Package | Role |
| --- | --- |
| `src/normalization/canonical/` | The canonical model (Pydantic v2): records, parts, enums, ids, the null rule, date and number parsing, diagnostics, the link check, JSON Schema export |
| `src/normalization/mappings/` | The mapping tables as JSON data (`data/<provider>/`), their loaders and checks, and the generator of `docs/mappings/` |
| `src/normalization/employees/`, `src/normalization/entities/` | The adapters: ordinary Python that follows the mapping tables, one module per provider and record type |
| `src/normalization/pipeline.py`, `src/normalization/output.py` | The adapter registry, shape guard, assembly and link check; the validation gate, masking and the output document |
| `src/normalization/adapters/` | The organizer's adapter entry points, now implemented: each runs the pipeline for its provider |
| `src/normalization/live/` | Live access: the client, one crawl plan per provider, the fetch runner (standard library only) |
| `src/normalization/fixtures/` | The synthetic fixture generator |
| `src/normalization/app/` | The web app: the FastAPI API, the SQLite store and the built UI (`static/`) |
| `src/normalization/write/` | The write path: one request planner per provider, the refusal rules, and the UKG send |
| `ui/` | The React source of the UI (Vite); only needed to change it |

### The output document

One JSON document per run:

- `run`: provider, tenant, input, whether sensitive values are masked, the record count per list,
  the lists left empty and why, any responses set aside, and the link problems found. A live run
  adds a fetch report: the date used as today, the companies, each company's pay window and how
  it was found, the calls per HTTP status, and the time taken.
- `companies`, `employees`, `direct_deposits`, `deduction_setups`, `benefit_enrollments`,
  `payroll_runs`, `paychecks`: the canonical records, each list in id order.

Every record carries `sources` (the routes and JSON locations it was built from), `field_status`
(the reason for each null), `diagnostics` (unknown codes, inferred mappings, masked or
placeholder values, unavailable sources), and the provider's extra fields in
`provider_extensions` and `sensitive_provider_extensions`.

## The canonical model in brief

The full model, field by field, is in [docs/CANONICAL_MODEL.md](docs/CANONICAL_MODEL.md); a JSON
Schema per record type is in [schemas/](schemas/).

### Seven record types

| Record | One record per | Holds |
| --- | --- | --- |
| Company | Employer scope: a PrismHR client, an isolved legal entity, a UKG company | Name, address, status, and the lists the company owns: tax entities (EINs), work locations, pay groups, earning codes, deduction codes |
| Employee | Provider employee record | Name, demographics, national ids, work and personal contacts, employment and its history, job and its history, compensation and its history, tax withholding, PTO balances, related people (dependents, emergency contacts), qualifications, work authorization |
| DirectDeposit | Account allocation | Allocation type (fixed amount, percent with its basis, or remainder), amount or percent, priority, account type, bank, routing and account numbers, status, effective dates |
| DeductionSetup | Deduction assignment | Link to the company's deduction code, category and tax treatment, amount or percent, limits and goal, dates, status, garnishment or loan details, and how strong its source is |
| BenefitEnrollment | Plan enrollment | Plan and benefit type, status, coverage level, coverage and deduction dates, every dated plan detail row |
| PayrollRun | Payroll run or batch | Run type, status, pay date, run number, run and finalized dates, the pay period of each pay group |
| Paycheck | Paycheck or voucher | Earnings (hours, units, rate, amount), deductions, taxes (one payer per line), employer contributions, benefit lines, payments (check, direct deposit), and the four defined totals |

Records link by canonical id: an employee names its company, tax entity, pay group and work
location; deposits, setups and enrollments name their employee; a paycheck names its employee,
run, tax entity and the company codes of its lines.

### Shared conventions

- **Ids** are readable and deterministic: `provider:tenant:entity:source ids`, for example
  `ukg-ready:900003:employee:7001:1101`. The provider's own ids are also kept in `source_ids`.
- **Numbers** are exact decimals, written as strings, never floats. Percentages are on a 0 to
  100 scale; rates (such as a tax rate of 0.062) are fractions in separately named fields; hours
  are decimal hours. Every money-holding record states its currency.
- **Dates** are ISO dates. Placeholder dates such as `9999-12-31` are never read as real dates:
  on a period bound they mean "open" (`not_applicable`), elsewhere "no usable value".
- **Coded values** are `{value, raw_code, raw_label, basis}`: the canonical value, what the
  provider sent, and what the value rests on (`documented`, `inferred`, `unmapped` and others).
  Every canonical list has `unknown`.
- **Null reasons** in a sparse `field_status` map on every object, enforced by validation.
- **Diagnostics** from a closed list of codes, each with a severity and the field it concerns,
  and never containing a sensitive value.
- **Sensitive fields** are marked in the model (and in the exported schemas), so masking covers
  them wherever they appear, including nested parts and lists.

## Results

### On the synthetic fixtures

All three providers normalize with every record valid. The link check finds no problem except
one planted on purpose: an isolved manager who works in a legal entity the bundle does not hold,
which the check must report. The fixtures also plant the edge cases the adapters must handle,
each pinned by a test: PrismHR arrears, reversal, adjustment and vacation vouchers; UKG lines
with missing amounts; an isolved check listed without a detail; provider-masked values; and
placeholder dates.

### On the live demo tenants

Full runs on 2026-10-16, with 4 calls in parallel:

| Tenant | Calls | Time | Records | Link problems |
| --- | --- | --- | --- | --- |
| UKG Ready | 2,030 | about 4 min | 103 employees, 18 direct deposits, 214 benefit enrollments, 51 payroll runs, 107 paychecks | 0 |
| isolved | 3,073 | about 13 min | 138 employees, 87 direct deposits, 10 deduction setups, 231 payroll runs, 430 paychecks | 0 |
| PrismHR (25 clients) | 19,045 | about 12 min | 668 employees, 392 direct deposits, 1,710 deduction setups, 6,836 benefit enrollments, 601 payroll runs, 14,583 paychecks | 2 |

Every call was answered and no response was set aside. Pay windows found by the runs: UKG Ready,
the 12 months ending on its latest pay date (2026-10-09); isolved, 2017-08-16 to 2018-08-15, as
its only completed payroll is from 2018; PrismHR, 13 clients from their latest completed batch,
while the other 12 have never run payroll.

The two PrismHR link problems are genuine data gaps. Two employees name a manager who is not in
their client's employee list. The same id exists in another client, but the field carries no
client, so no cross-client link is assumed, and the gap is reported rather than hidden.

### Writing to the UKG Ready demo tenant

A synthetic test employee (reserved `example.com` addresses and 555-01xx phone numbers, no SSN)
was created in the UKG demo company (HTTP 201) and then updated (HTTP 204). Reading it back
matched every field sent: 23 of 23 after the create, and after the update the 9 changed fields
changed while the others stayed as they were. The first attempts showed what the UKG reference
does not say: a create also requires a start date and a national id, and an update must be sent
as a JSON Patch.

### What the live runs uncovered

The live runs found issues that neither the contracts nor the discovery samples had shown. Each
was fixed in code and covered by a test:

- **Entries named but not listed.** UKG payrolls and employees name a second EIN that the
  provider's EIN lookup does not list, and PrismHR batches and employees name pay groups their
  client's code list leaves out. Such entries are now built from the fields the records send and
  marked `reference_only`, instead of being reported as broken links.
- **isolved garnishment lines.** The id on a paycheck's garnishment line is the employee's
  garnishment id, not a pay item code. It is kept as sent instead of being linked to a code.
- **isolved dates with a time of day.** 24 of 138 employees send hire and status dates as
  timestamps with a time of day and no time zone. The date part is now used, and the dropped
  time is noted on the record.
- **PrismHR's pay window search.** PrismHR answers an empty date range with "no records" (HTTP
  404) and a client that never ran payroll with "no batches" (HTTP 400). Both are now read for
  what they say, while any other error still stops the search instead of being read as "no
  payroll".

## Where things are

| Path | What |
| --- | --- |
| [ASSUMPTIONS_DECISIONS_LIMITATIONS.md](ASSUMPTIONS_DECISIONS_LIMITATIONS.md) | Assumptions, decisions with their reasons, data issues found, gaps by provider, limitations |
| [docs/CANONICAL_MODEL.md](docs/CANONICAL_MODEL.md) | The canonical model field by field: conventions, every record and part, write readiness |
| [docs/COVERAGE.md](docs/COVERAGE.md) | Each item the brief lists, per provider: mapped, partial, a gap, masked or unknown |
| [docs/mappings/](docs/mappings/) | Per provider: selected and excluded routes with reasons, every field row with its evidence, code tables (generated from `src/normalization/mappings/data/`) |
| [schemas/](schemas/) | A JSON Schema per record type, exported from the models |
| `fixtures/` | The synthetic bundles per provider, and `manifest.json` (seed, responses per route) |
| `src/normalization/` | The code (packages above) |
| `tests/` | The test suite; `tests/golden/` holds the expected output per provider |
| `ui/` | The UI source |
| `Provider_README.md`, `contracts/`, `docs/REFERENCE_AUDIT.md` | The organizer's brief (its original `README.md`, renamed) and reference material, unchanged |

## Known limitations

The main limits are below. The full list, with the reason and evidence for each, is in
[ASSUMPTIONS_DECISIONS_LIMITATIONS.md](ASSUMPTIONS_DECISIONS_LIMITATIONS.md).

- **UKG Ready has no deduction setup source** for the demo account (the documented route
  answers 404). UKG deductions therefore appear only as paycheck lines and as the company's
  deduction codes.
- **isolved deduction setups come from a candidate source.** The documented employee deduction
  routes are refused for the demo account, so setups come from the legal entity's pay item
  assignments, which are not documented as enrollments. Each such setup is marked
  `unvalidated_source`.
- **UKG payroll in the demo tenant is all OPEN** (calculated, not finalized). The status
  travels with every run and paycheck, which are never presented as issued pay.
- **isolved live payroll is 2018 conversion data only.** Regular current-year payroll and
  direct-deposited pay are covered by the synthetic fixtures, not by live data.
- **Many classifications are inferred** from exact provider labels, because no source documents
  them: tax types, isolved employer contributions and several status and type labels. Each is
  marked `inferred` and flagged on its record; labels outside the tables stay `unknown`.
- **Writes reach only UKG Ready.** isolved and PrismHR creates need a real SSN and client codes in
  a shared demo tenant, so their writes are dry runs: the full request is built and shown, never
  sent. Only employees are written.
- **The UI can be finicky.** It was built under time pressure; the API and the command line are
  the tested path.
- **Some values are masked by the provider.** PrismHR masks SSNs, bank account numbers and
  client EINs for the demo API user, so those fields are `hidden_by_source` and cannot be shown
  even with `--show-sensitive`.
