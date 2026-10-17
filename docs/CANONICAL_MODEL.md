# Canonical Model

This document describes the provider-neutral model that PrismHR, isolved and UKG Ready data
is normalized into. The Python models in `src/normalization/canonical/` are the source of
truth; JSON Schema files are exported from them to `schemas/` (`python -m normalization
export-schemas`, see `schemas/README.md`). Decision ids (D-xxx) refer to the assumptions and
decisions file.

Status: sections 1 to 8 (conventions, company, employee, write readiness, direct deposits,
deductions, benefit enrollment, payroll) are complete. Where each item of the brief lives, and
what each provider supplies or lacks for it, is in `docs/COVERAGE.md`.

## 1. Conventions

These rules apply to every canonical record, whatever the provider.

### 1.1 Records and parts

- A **record** is a top-level entity: company, employee, direct deposit, deduction setup,
  payroll run, paycheck (`CanonicalRecord`).
- A **part** is a structured object nested inside a record, such as an address or a paycheck
  earning line (`CanonicalPart`).
- Unknown fields are rejected (`extra="forbid"`), so a typo in an adapter fails loudly.

Every record carries:

| Field | Meaning |
| --- | --- |
| `id` | Canonical id (1.2). |
| `provider` | `prismhr`, `isolved` or `ukg-ready`. |
| `tenant_id` | The provider tenant the data came from. |
| `source_ids` | The provider's own identifiers for the record, by provider field name (e.g. `{"clientId": "102", "employeeId": "A00024"}`). Kept so the record can be traced and written back. |
| `sources` | Where the data came from: endpoint (method plus documented route template) and a JSON Pointer to the record within that response. A record built from several calls lists each one. See 1.11 for what this can and cannot recover. |
| `field_status` | Why each null field is null (1.3). |
| `diagnostics` | Findings about the record (1.7). |
| `provider_extensions` | Provider-specific extras with no canonical meaning (1.8). |

Fetch time is not stored on records, so normalizing the same input always produces the same
output byte for byte. Run-level facts (time, tenant, endpoints called) belong to the run
manifest.

Validation runs when an object is built and when a field is assigned. A mutable value changed
in place (for example `record.field_status["x"] = ...`) is not seen at that moment, so all
output goes through `to_json()`, which validates the record again before serializing it.
Plain string fields never hold a blank string; blank means "no value" and is null with a
status (raw codes inside coded values are exempt, see 1.7).

### 1.2 Identifiers

Format: `{provider}:{tenant_id}:{entity}:{source id}[:{source id}...]`.

| Example | Built from |
| --- | --- |
| `prismhr:970592:employee:102:A00024` | client id, employee id |
| `isolved:255938:company:5797` | legal id |
| `ukg-ready:833341:paycheck:33704016:85949527786` | company id, pay statement id |

- Deterministic and readable: the same source record always gets the same id, and a person can
  read where it came from.
- Source ids are percent-encoded, so a `:` inside a provider id cannot break the format.
- The id holds the source ids needed for **uniqueness within the tenant**, no more. PrismHR
  employee ids are unique per client, so the client id is included. isolved legal ids and UKG
  pay statement ids are treated as unique on their own, so the isolved client id and the UKG
  payroll id are left out. That is an assumption consistent with the demo data (108 UKG pay
  statements, 108 distinct ids), not a documented guarantee.
- The full set of ids needed to **address** the record through the provider's routes (e.g.
  isolved client and legal, UKG company, payroll and pay statement) is kept in `source_ids`.
- Records link to each other by canonical id (`company_id`, `employee_id`, `payroll_run_id`).
- Validation checks that the id's provider, tenant and entity type match the record.
- Assumption: the tenant id returned by the sign-in service is stable for a demo account.

### 1.3 Null values and `field_status`

A null alone is ambiguous: it could mean the provider hid the value, never sent it, or that
it does not apply. So **every null field must be explained**, in the `field_status` map of
the object that holds it:

| Status | Meaning | Example |
| --- | --- | --- |
| `hidden_by_source` | The value exists, but the provider masked it. | PrismHR SSN `***-**-****` |
| `not_provided` | **No usable value was received**: the key was missing, null or blank; the provider sent a placeholder (sentinel date) or an unparseable value; or the route was unavailable to this account. | isolved `gender` absent for some employees; PrismHR rate `effectiveDate` `9999-12-31` |
| `not_applicable` | The field does not apply to this record. | Termination date of an active employee; the end date of an open-ended deposit |

- Fields that hold a value are not listed; the map is sparse.
- Validation rejects a null without an entry, an entry for a field that has a value, and an
  entry naming a field that does not exist.
- Nested parts carry their own `field_status`. A record's map never explains a part's nulls.
- `not_provided` alone means the field was simply absent. For every other reason the record
  also gets a diagnostic naming it: `sentinel_date` (placeholder), `unparseable_value`, or
  `source_unavailable` (HTTP 401 or 403, or an error that withholds the data, such as UKG's 400
  "Cost Center not used"). So "not sent", "sent but unusable" and "could not be
  fetched" stay distinguishable without more statuses.
- The rule is enforced by the Python models; JSON Schema cannot express it, so exported
  schemas describe the shapes only.
- Exemption: small value types whose optional parts have a fixed meaning by definition
  (`Coded.raw_label`: the provider sent only a code; `Diagnostic.field` and
  `Diagnostic.evidence`: the finding concerns the whole record, or no citation applies) are
  not subject to the rule.

### 1.4 Sensitive values

- Sensitive fields (SSN and other national ids, bank account and routing numbers, birth date)
  are marked in the schema (`"x-sensitive": true`).
- A masked provider value is never stored as if it were the value. The field is null with
  `hidden_by_source` and a `value_redacted_in_source` diagnostic.
- Where a provider shows the last characters (e.g. `******1068`), they are kept in a separate
  `*_last4` field, never in the full-value field.
- Full values are held in the canonical model. Output layers (CLI, API, UI, logs) mask marked
  fields by default and show them only with an explicit opt-in (decided, D-036). Implemented
  for the CLI (D-080): `normalization/output.py` serializes each record through `to_json()`
  (which re-validates) and then masks every `sensitive_fields()` path, keeping the structure,
  nulls and `field_status`; national id values keep their last 4 characters (`***6789`), every
  other sensitive value becomes `***`. `--show-sensitive` is the opt-in. `to_json()` itself
  does not mask, so the canonical records keep full values.
  `sensitive_fields()` lists every marked field, including those inside nested parts
  (`deposits[].account_number`), so output layers mask nested values too.

### 1.5 Numbers, money, percentages and hours

- All numbers are exact decimals and are written to JSON as **fixed-point strings**
  (`"940.00"`), so no consumer turns them into floats. NaN, infinities and booleans are
  rejected.
- **Source JSON is read with exact decimals** (`parse_source_json`, used by the CLI and by every
  future reader of provider responses). The standard parser would turn `1.00` into the float
  `1.0` and cut long decimals before an adapter sees them. With exact reading, source precision
  is kept as sent: JSON `1.00` stays `1.00`, string `"25.0000"` stays `"25.0000"`. Compare values
  numerically, never as text.
- Values that reach the model as Python floats anyway (not from provider JSON) are converted
  through their shortest representation (`0.1` stays `0.1`); their original digits are not
  recoverable, which is why provider JSON never goes through the float parser.
- **Currency** is held once per record that contains money (`currency`, ISO 4217). None of the
  three providers states a currency on payroll data; all three are US payroll systems, so
  `USD` is assumed. A currency the source does state (UKG compensation) is used as given.
- **Percentages** (`Percent`, fields named `*_percent`) are on a 0 to 100 scale: `1.5` means
  1.5%. **Rates** (`Rate`, fields named `*_rate`) are fractions: `0.062` means 6.2% (e.g.
  PrismHR company tax `comTaxRate`). The two never share a field, and the exported schema
  records the scale (`"x-scale": "percent"` or `"fraction"`). Percent fields are not bounded in
  general (a pay change can be -100 or +2000); fields that must lie in 0 to 100, such as deposit
  allocations, add that bound on the entity.
- **Hours** are decimal hours. Source units are converted only where documented or verified,
  e.g. UKG milliseconds (D-028). The conversion for each field is recorded in the mapping
  tables (see 1.11 for tracing the original value).
- **Unverified units: one rule, one explicit exception.**
  - **Rule:** a value enters a typed unit-bearing field (hours, percent, rate) only when its
    unit or scale is documented or verified. Otherwise it stays raw in `provider_extensions`
    with a `unit_unverified` diagnostic, even when the kind of quantity is known. Example: a UKG
    field known to be a duration but with no documented or verified unit could be
    milliseconds, seconds, minutes or hours, so it never enters an hours field.
  - **Exception (provisional, D-032): PrismHR deposit method `P`.** "Percentage" is documented,
    but the scale (0 to 100 or fraction) is not, and no live percentage deposit was seen. The
    value still enters the deposit percent field, assumed to be 0 to 100, with a
    `unit_unverified` diagnostic. Reasons this case is treated differently from durations:
    1. Deposit percentages are a field the brief lists, so leaving them out of the typed model
       would drop a required fact for every PrismHR percentage deposit (D-037).
    2. There are only two candidate scales, and some values settle the question: a value above
       1 can only be on the 0 to 100 scale. Values at or below 1 stay ambiguous (0.5 could mean
       0.5% or 50%; 1 could mean 1% or 100%), and both readings pass the 0 to 100 bound, so for
       them the assumption is only made visible by the `unit_unverified` diagnostic, not
       checked. A duration has several candidate units that
       differ by factors of 60 to 3,600,000, and a wrong guess produces plausible-looking
       hours with no way to notice.
    3. The other two providers use 0 to 100 (isolved spec maximum 100 and live split; UKG live
       split), which supports, but does not prove, the same reading for PrismHR.

    The spec's "precision 2 (##.##)" is not scale evidence, because it also describes dollar
    amounts. The exception is revisited if live data shows a PrismHR percentage deposit
    (synthetic fixtures cannot settle it, since we choose their scale).

### 1.6 Dates

- Date-only values are ISO dates (`2025-08-08`). isolved's midnight timestamps
  (`2018-07-15T00:00:00`) are date-only values and are read as dates.
- A value with a real time of day is a timestamp, never silently truncated to a date. With no
  time zone (live isolved: hire, status, category and salary dates of 24 of 138 employees), its
  date part fills the date field with an `inferred_mapping` diagnostic naming the dropped time of
  day (date plus time give the raw value back; the date itself is not repeated, because
  diagnostics are not masked), D-096. With an offset or `Z` it is `unparseable_value`: its
  calendar date depends on a time zone. The isolved I-9 completion date also keeps the full
  timestamp in `sensitive_provider_extensions` (step 3b-1).
- **Sentinel dates** are placeholders, not dates, and always map to null:
  - open start: `0000-01-01`, `1900-12-31`
  - open end: `2099-12-31`, `9999-12-31`
- **The status depends on the field's role**, set per field in the mapping tables
  (`DateRole`, applied by `resolve_date`):

  | Role | Examples | Sentinel handling |
  | --- | --- | --- |
  | `period_start` | deposit `active_from`, profile `effective_from` | open-start sentinel: unbounded start, `not_applicable` |
  | `period_end` | deposit `active_to`, coverage end | open-end sentinel: unbounded end, `not_applicable` |
  | `event` | hire date, pay date, pay rate `effectiveDate` | any sentinel: a placeholder where a real date is required, `not_provided` plus `sentinel_date` |

  A sentinel of the wrong kind for a period bound (an open-end value in a start field) is also
  a placeholder. Example: PrismHR pay rate history (client 102, one employee, 64 rows) has one
  row with `effectiveDate` `9999-12-31` and one with `0000-01-01`, both otherwise ordinary
  changes ("Promo", with rates). The effective date of a change is an event, so both become
  `not_provided` with a `sentinel_date` diagnostic, and the rows are kept.
- Null or blank gives `not_provided`. An adapter that knows the field cannot apply (the
  termination date of an active employee) uses `not_applicable` instead.
- Any other value that is not a date is `not_provided` with an `unparseable_value` diagnostic.
- Blank strings, in date fields and all others, are treated as not provided, except where the
  provider documents the empty string as a code (PrismHR `hrsType ""`). Coded values keep it as
  their raw code.

### 1.7 Coded values

Every provider code that maps to a canonical enum is stored as a coded value:

```json
{"value": "garnishment", "raw_code": "VG", "raw_label": "IRS Levy", "basis": "inferred"}
```

- `value`: the canonical enum value. Every canonical enum has `unknown`.
- `raw_code`, `raw_label`: exactly what the provider sent, so no meaning is lost and the
  original can be written back. Two cases send no code at all, and their `raw_code` is
  defined instead (D-080):
  - **The source field itself sets the value** (the field's documentation states it): `raw_code`
    is the source field name. Examples: PrismHR org unit types (`homeDepartment`), the national
    id type of an SSN field (`ssn`, isolved contacts `ssnUnmasked`), isolved period fields
    documented as per pay period (`normalHours`, `perPaySalary`).
  - **Several flags together set the value**: `raw_code` lists them as sent, e.g. UKG worker
    type `W2=true;_1099=false`; UKG pay period types with a parameter, e.g. `every_n_weeks:2`.

  A `raw_code` that names a source field is never a provider code, so the write path must not
  send it back as one.
- `basis`: what the mapping rests on:

| Basis | Meaning |
| --- | --- |
| `documented` | The provider spec, lookup reference, or the provider's own code table states it. |
| `evidenced` | Established from provider data (e.g. amounts that reconcile), not stated. |
| `inferred` | Reasoned from indirect evidence; the record carries an `inferred_mapping` diagnostic. |
| `configured` | From a tenant mapping supplied to the pipeline. |
| `unmapped` | No evidence. Always paired with `unknown`, and with an `unknown_code` diagnostic. |

Validation enforces that `unknown` and `unmapped` occur together. Codes are never mapped from
the letters or words of a code alone.

### 1.8 Typed fields vs provider extensions

- Everything the brief lists for the four data types lands in **typed canonical fields**,
  even when only one provider supplies it (the others then carry `not_provided`).
- `provider_extensions` holds only genuinely provider-specific extras, keyed by source field
  path, as raw JSON.
- The mapping tables account for every source field: mapped, kept as an extension, or
  excluded with a reason.

### 1.9 Diagnostics

Each diagnostic has a `code`, a `severity` (`info`, `warning`, `error`), a `message`, the
`field` path it concerns (e.g. `deductions[2].category`), and optional `evidence` (a decision
id or spec pointer). Messages never contain sensitive values.

| Code | Raised when |
| --- | --- |
| `unknown_code` | A source code has no canonical mapping. |
| `inferred_mapping` | A canonical value is inferred, not documented. |
| `value_redacted_in_source` | The provider masked a value. |
| `sentinel_date` | A placeholder date appears where a real date is required. |
| `empty_via_404` | A route reported "no records" as HTTP 404 (isolved, D-011). |
| `source_unavailable` | A route was refused (401 or 403), is not exposed, or returned an error that withholds the data (e.g. UKG cost center lookup 400 "Cost Center not used", D-076). |
| `unparseable_value` | A value could not be parsed to its canonical type. |
| `reconciliation_mismatch` | Provider totals disagree with the line items. |
| `reconciliation_incomplete` | A missing input prevents a specific total or comparison. That total stays null with `not_provided`, and no mismatch is claimed (section 8.5). |
| `conflicting_sources` | Two provider sources disagree on one fact. |
| `unit_unverified` | A unit or scale is not established; the value is kept unconverted. |
| `deprecated_source` | Data came from a route the provider marks deprecated (UKG direct deposits). |
| `unvalidated_source` | The record comes from a source not validated for this meaning (isolved candidate deduction setups, D-017). |
| `unstable_id` | The id rests on the source's list order, not a provider id (PrismHR deposits, D-046). |
| `reference_only` | A company entry built from the records that name it, because the provider's own list omits it (UKG EIN missing from `lookup/eins`, D-094). |

### 1.10 Company scope

The canonical **company** is the employer scope that owns employees and code tables:

| Provider | Company | Parent | Tax entities (EINs) |
| --- | --- | --- | --- |
| PrismHR | Client | none (the PEO tenant) | client master `federalIdNumber` (whether the provider masks it is checked in section 2) |
| isolved | Legal entity | Client (kept as parent) | the legal's own EIN |
| UKG Ready | Company | none | a list: `lookup/eins` plus EINs referenced by payrolls |

Payroll runs and paychecks reference a tax entity whenever the source identifies one. See
section 2 (to be written) for the full company entity.

EIN availability (format-only live check, 2026-10-15): isolved `federalEIN` and UKG
`ein_tax_id` are returned in full; PrismHR `federalIdNumber` is masked by the provider (23
clients) or empty (2), so it is `hidden_by_source` or `not_provided` there.

### 1.11 Traceability

- `sources` names the endpoint and the JSON Pointer of each record in that response. It does
  not hold the value, so it recovers the original only together with the run's input.
- **File input** (the CLI, tests, fixtures): the input file is the raw provider response, so
  every value can be traced exactly.
- **Live runs** (Phase 7): raw responses contain personal data, so they are not kept by
  default. Whether to offer an opt-in that keeps them in a local, Git-ignored folder is decided
  in Phase 7. Without it, a live run's canonical output records where each value came from but
  not the raw value.
- Coded values always keep their raw code and label, and records keep their provider ids and
  `provider_extensions`, so the most important raw values travel with the record regardless.

### 1.12 Sensitive provider extras

Every record has two extension fields. `provider_extensions` holds provider-specific extras
that are not sensitive. `sensitive_provider_extensions` holds provider-specific extras that
are (for example PrismHR health screening results: drug tests, blood type, conditions); the
field is marked sensitive as a whole, so default output masking (1.4) covers everything in
it. Nothing returned by a provider is dropped for being outside the brief: it is typed, or
kept in one of these two fields.

## 2. Company

Model: `src/normalization/canonical/company.py`. One company per employer scope (D-034).

| Provider | Company | Id built from | Parent |
| --- | --- | --- | --- |
| PrismHR | client | client id | none |
| isolved | legal entity | legal id | client (`parent`, a reference) |
| UKG Ready | company | company id | none |

| Field | Meaning |
| --- | --- |
| `legal_name`, `display_name`, `company_code` | Registered name, trading or display name, provider's short code (isolved `legalCode`) |
| `status`, `status_date` | Coded company status (active, inactive, terminated) |
| `address`, `phone` | Business address and main phone (not sensitive) |
| `parent` | Provider reference to a parent organization (isolved client) |
| `tax_entities[]` | Legal employer identities: `id`, `name`, `ein`, `country` |
| `work_locations[]` | `id`, `code`, `name`, `address`, `is_active` |
| `pay_groups[]` | `id`, `code`, `name`, `pay_frequency`, `is_active` |
| `deduction_codes[]` | `id`, `code`, `name`, `category`, `tax_treatment`, `is_catch_up`, `calc_method`, `w2_box`, `w2_code`, `is_active` (section 6) |
| `earning_codes[]` | `id`, `code`, `name`, `pay_class`, `is_cash`, `rate_class`, `quantity_type`, `w2_box`, `w2_code`, `is_active` (section 8.3) |

- Tax entities, work locations and pay groups have **canonical ids** (`tax_entity`,
  `work_location`, `pay_group` entity types) so employees and payroll can refer to them.
  Their ids come from the provider's own id for the entry, never from the EIN, which PrismHR
  masks. Validation checks each id's type, provider and tenant, and that ids are unique.
- EIN availability: isolved and UKG return it in full; PrismHR masks it (`hidden_by_source`).
  `tax_entities[].ein` is **sensitive** (D-044): masked by default in output like personal
  identifiers, shown with the opt-in. The tax entity's name stays visible.
- UKG has no company resource (D-029): name and address are `not_provided` with a
  `source_unavailable` diagnostic; tax entities come from `lookup/eins` plus EINs referenced
  by payrolls and employees, one per EIN id. An id the lookup omits (live: the 2nd EIN) is built
  from the fields those records send and carries a `reference_only` diagnostic (D-094).
- PrismHR client-master settings for billing, commissions, invoicing and processing describe
  the PEO relationship, not employees or payroll, and are kept in `provider_extensions`.
  PrismHR state tax and unemployment insurance employer ids, the pay card account and the other
  account fields of unknown form are kept in `sensitive_provider_extensions`, like the EIN
  (D-044); references to the PEO's check and ACH account records (1 to 3 digit values, four of
  them documented as account ids) stay in `provider_extensions`.
- **Each owned entry has its own `provider_extensions`** (D-063): provider settings of a code,
  location, pay group or tax entity with no canonical meaning (GL and billing codes, Vertex geo
  codes, external ids) stay with that entry, not on the company.
- **Pay groups per provider:** PrismHR client pay groups, with the frequency from the payroll
  schedule's documented pay period letter (D-068); isolved legal pay groups, with the frequency
  from an undocumented integer read through isolved's own salary history labels, `inferred`
  (D-067); UKG pay period profiles, which define pay schedules and are what employees link to
  (D-065). UKG pay calculation profiles are not pay groups.
- **Work locations:** PrismHR client location codes, isolved legal work locations; UKG has no
  source (cost-center `location_code` empty on 71 of 71, D-065).
- Mapping tables: `docs/mappings/` (D-061).

## 3. Employee

Model: `src/normalization/canonical/employee.py`.

### 3.1 Granularity and links (D-039)

One canonical employee per **provider employee record**:

| Provider | Record | Notes |
| --- | --- | --- |
| PrismHR | (client, employee id) | The same person at two clients cannot be linked (SSN is masked). |
| isolved | employee id | Several employments under one id stay in `employment_history`, each entry with its `employment_id`. |
| UKG Ready | account id | One account per EIN. A person with accounts under both EINs is two records sharing `person_ref` (`primary_account_id`). |

- `company_id` (required) and `tax_entity_id` link the employee to its company and legal
  employer. For UKG the EIN id comes from the employee detail (`ein.id`); the employee list
  has only `ein_name`, which is not used as a key, so without the detail call
  `tax_entity_id` is null with `not_provided`.
- `person_ref` groups records of one person **within one provider tenant**. It is never a
  cross-provider identity match.
- References to other records (`company_id`, `tax_entity_id`, `job.work_location_id`,
  `job.manager_employee_id`, `job.supervisor_employee_id`, the same three fields on every
  `job_history[]` entry, `compensation.pay_group_id`) are validated: right entity type, same
  provider and tenant. A reference the source does not identify is null with a status.
- That validation cannot prove **ownership** (a pay group id of another company in the same
  tenant is well formed). `canonical/links.py` (`find_link_problems`, D-045) checks a set of
  assembled records: the employee's company is in the set; its tax entity, work location and
  pay group (and the work location of each job history entry) belong to that company; its
  manager and supervisor, current and in job history, are employees in the set
  (possibly in another company of the tenant, since isolved manager references carry their own
  legal id). The caller decides whether a missing record is an error or a diagnostic.

### 3.2 Parts

| Part | Contents |
| --- | --- |
| `name` | first, middle, last, prefix, suffix, preferred first name |
| `demographics` | birth date, gender, ethnicity, marital status, citizenship, preferred pronouns, veteran flags (VEVRAA categories), disability, tobacco use, deceased |
| `national_ids[]` | type (coded), value, `value_last4`, primary flag |
| `work_contact` | work email, work phone and extension |
| `personal_contact` | addresses (home, mailing, tax form), phones, emails |
| `employment` | status, status date, worker type, employment type, seasonal flag, FLSA status, original hire, hire, rehire, seniority, termination date, type and reason, rehire eligibility. Termination date, type and reason describe the current employment: `not_applicable` when the status is known and not terminated; a value still sent (a rehired employee's last termination) stays in `provider_extensions` (D-080) |
| `employment_history[]` | employment id, status, employment type, effective and end date, reason |
| `job` | job reference, effective date, org units (department, division, location, cost center, project; each with type, the provider's id for the unit when sent, code and name; for a UKG cost center the type's raw code is its cost center tree index, D-076), work location id, manager and supervisor ids, EEO-1 category, union code, workers' comp code |
| `job_history[]` | dated job, organization and location changes, same fields as `job` (D-069). An entry may change one thing only (a PrismHR department change); its other fields are null with `not_provided` |
| `compensation` | pay type, pay frequency, pay group id, base rate and its period, hourly rate, annual salary, per-period amount, standard hours and their period, effective date, additional rates |
| `compensation_history[]` | effective date, pay type, amount and period, hourly and annual equivalents, change amount and percent, reason |
| `tax_withholding` | federal, state and local settings: jurisdiction, residency (not applicable for federal), filing status (old-form "Married" is its own value, not married filing jointly), allowances, additional amount or percent, exempt, multiple jobs, Form W-4 dependents, other income and deductions amounts, and a provider block (`is_blocked`: nothing withheld, not the same as an exempt claim) |
| `pto_balances[]` | plan (the provider's plan id, code and name), balance, accrued and used year to date, carryover, as-of date, and the start and end of the plan year the year-to-date amounts cover when sent (D-027). Hours fields hold only amounts whose unit is documented (1.5): isolved balances stay raw with `unit_unverified`; UKG milliseconds are converted |
| `related_people[]` | dependents, emergency contacts, beneficiaries, one entry per source item (never merged by name): the provider's id for the person (joins benefit dependents and beneficiaries, which stay in the enrollment's sensitive extension), relationship (a domestic partner's child is its own value), name, or `full_name` when the provider sends the name as one string (PrismHR emergency contacts; never split), birth date, gender, national id, address, phones, email, and the flags dependent, emergency contact, beneficiary and active. A flag the source does not state is `not_provided`, not false |
| `qualifications[]` | skills, education, certifications, training, licenses: the provider's id for the entry or the item it names (`source_id`, the only identity UKG sends for a skill) and its code, name, level, institution, completed and expiration dates, years of experience. A renewal deadline is not an expiration date |
| `work_authorization` | I-9 on file (a form is on file, PrismHR `formI9Filed`; not the same fact as completed), I-9 completion and date, document expiration, non-resident alien, visa type |

Other employee-level fields: `employee_number` (the number people use), `currency`.

- **Pay frequency** comes only from labeled or documented sources (D-018, D-041):
  - UKG: pay-period profile `period_type`, a documented enum (e.g. `every_n_weeks` with
    `num_weeks` 2 = biweekly): `documented`.
  - isolved: salary history `frequency.description` ("Bi-Weekly", "Semi-Monthly", "Monthly"),
    a provider label with no documented list: `inferred` (D-081). The raw `payFrequency` integer stays in
    `provider_extensions`.
  - PrismHR: the employee's pay group (`compensation.payGroup`) joined to the payroll
    schedule's documented pay period letter (`documented`, D-041 amendment 2, D-068). Checked
    on 6 of 6 sampled employees, whose own `payPeriod` equals the joined letter. Without a
    matching schedule the frequency is null with `not_provided` and a diagnostic; the raw
    `payPeriod` stays in `provider_extensions`. (`hourlyPayPeriod`, a rate basis documented as
    H, W, B, S, M, Y, was seen with `A`, which is not in that list.)
- **Worker type:** PrismHR `employee1099` is documented as "a 1099 contractor"
  (`documented`); isolved `payType` "1099" and UKG `employee-tax-type._1099` have no documented
  meaning, so mapping them to contractor is `inferred`, with a diagnostic.
- **Benefit enrollments** are not part of the employee record: they get a typed home with
  deduction setup (section 5, to be written), separate from benefit contributions on paychecks.

### 3.3 Sensitive fields (D-040)

Marked at field level and masked by default in output (1.4). The test suite pins the exact
list.

| Area | Sensitive | Visible |
| --- | --- | --- |
| Person | every `demographics` field | `name` |
| Identifiers | `national_ids[].value` | `value_last4`, type |
| Personal contact | address street lines and postal code, personal phone numbers, personal email addresses | city, state, county, country |
| Work contact | none | work email and phone |
| Tax | the whole `tax_withholding` part | |
| Related people | name, full name, birth date, gender, national id value, address street lines and postal code, phone numbers, email | relationship, flags, provider id, address city and state |
| Work authorization | every field | |
| Extras | `sensitive_provider_extensions` | `provider_extensions` |

### 3.4 Kept in extensions, with reasons

| Data | Field | Reason |
| --- | --- | --- |
| PrismHR health screenings (drug, audio, physical tests, blood type, conditions, allergies) | `sensitive_provider_extensions` | One provider only, medical data. Preserved and masked. Only the blood donor flag is filled (6 of 6 sampled employees). |
| Related people extras (tobacco use, disability, student status, marital status, deceased flag, beneficiary percent and precedence, notify-if-detained flags) | `sensitive_provider_extensions` | Personal or health data of a related person with no typed home (D-071). |
| isolved prior employment (employer, job, dates, ending pay, reference) | `sensitive_provider_extensions` | Personal history with no typed home (D-071); empty for 3 of 3 sampled. |
| PTO amounts without a documented unit (isolved balances), current-period and projected amounts (UKG), prior register years (PrismHR) | `provider_extensions` | Not the typed year-to-date or current balance facts, or unit not documented (1.5, D-077). |
| isolved raw `payFrequency` integer | `provider_extensions` | Meaning undocumented (D-018); needed to write back to isolved. |
| UKG `username` | `provider_extensions` | Login name for one provider; needed to create a UKG employee (section 4). |
| Portal and login settings (self-service enabled, locked, force password change, photo flags) | `provider_extensions` | System settings, not facts about the employee. |
| UKG non-pay profiles (security, timesheet, holiday, points, pay calculation ids) | `provider_extensions` | Platform configuration references with no canonical meaning. The pay-period profile is typed (pay frequency). |
| PrismHR PEO fields (`peoStartDate`, benefit group, onboarding flags) | `provider_extensions` | Describe the PEO relationship. `peoStartDate` is needed to write to PrismHR (section 4). |

## 4. Write readiness (create and update employee, D-038)

Fields each provider requires to **create** an employee, and where they come from. Source:
request schemas in the reference material; no live write has been attempted. Most required
fields have a typed canonical home. Some are **destination inputs**: they exist in the
canonical record only when the source is the same provider, and otherwise must come from a
configured mapping or rule for the destination, or the write is refused (rules 2, 4, 5 below).

| Provider field (required) | PrismHR `POST /newHire/v1/importEmployees` (`NewHireEmployee`), then `commitEmployees` | isolved `POST /api/clients/{clientId}/newEmployee` (`EmployeeModel`) | UKG `POST /v2/companies/{cid}/employees` | Canonical home |
| --- | --- | --- | --- | --- |
| First and last name | `firstName`, `lastName` | `nameAddress.firstName`, `lastName` | `first_name`, `last_name` | `name` |
| National id | `ssn` | `ssn` + `idType` | (optional `national_id_numbers`) | `national_ids[]` (type and value) |
| Hire dates | `origHireDate`, `lastHireDate` | `hireDate` | (optional `dates`) | `employment.original_hire_date`, `hire_date` |
| Employment status | `employeeStatusCode` (client code) | `employmentStatus` | (optional `status`) | `employment.status` (raw code) |
| Employment category | | `employmentCategoryCode` | | `employment.employment_type` (raw code) |
| Job | `jobCode` (client code) | | | `job.job.code` |
| Work location | `workLocationCode` (client code) | `workLocation` | | `job.work_location_id` resolved to the destination's location code |
| Pay group | `payGroup` (client code) | `payGroup` | | `compensation.pay_group_id` resolved to the destination's code |
| Pay | `standardHours` | `payType`, `payFrequency` (integer) | | `compensation.standard_hours`, `pay_type`; isolved `payFrequency` from extensions |
| Legal employer | | `legalCode` | (optional `ein`) | `company_id`, `tax_entity_id` |
| Provider-specific | `peoStartDate` | | `username` | see below |

**Update** routes: PrismHR has targeted routes (`employee/v1/updateEmployeeFields`,
`updateAddressInfo`, `updateJobCode`, `updatePayRate`, `updatePayGroup`, `updatePayMethod`,
`updateEmployeeStatusType`, `updateW4`, `updateEmergencyContact`, `terminateEmployee`,
`rehireEmployee`); isolved has `POST /api/clients/{clientId}/updateEmployee` (same model,
`employeeNumber` required) plus section routes (`PUT nameAddress`, `PUT personal`, `POST
statuses`, `jobs`, `salaries`, `terminate`, `rehire`); UKG has `PUT` and `PATCH
/employees/{aid}` plus `PUT` on `pay-info`, `demographics`, `profiles` and `tax-info`.

**Gaps and rules for the write path:**

1. **PrismHR requirements are per client.** The 11 schema-required fields are a minimum;
   `GET /newHire/v1/getNewHireRequiredFields` returns each client's own list and is checked
   before a write.
2. **Destination codes need a configured mapping.** Every coded value a destination requires
   must be translated into that destination's own code, from a configured mapping for the
   destination (`configured` basis); without one, the write is refused. This covers:
   - PrismHR: `employeeStatusCode`, `jobCode`, `workLocationCode`, `payGroup` (client codes).
   - isolved: `employmentStatus`, `employmentCategoryCode`, `payType`, `idType`,
     `workLocation`, `payGroup`, `legalCode`, and `payFrequency`. The integer `payFrequency`
     is in the canonical record only when the source is isolved (`provider_extensions`); from
     any other source it must be mapped from the typed `compensation.pay_frequency`, and since
     the integer's meaning is undocumented (D-018) that mapping is configured, never derived.
   - The raw code is reused only when source and destination are the same provider tenant.
3. **National id.** PrismHR masks SSNs and isolved returns them only through
   `employeesWithSSN`; a value with status `hidden_by_source` or `not_provided` is never sent
   (D-020), so a create that needs it is refused unless the source supplied it.
4. **PrismHR `peoStartDate`** is "the date the employee started with the service provider", a
   different fact from the hire date. It is never filled from the hire date: it comes from the
   source record (PrismHR to PrismHR), a configured rule, or an explicit input supplied with
   the write request; otherwise the write is refused.
5. **UKG `username`** must be unique in the destination. When the source is not UKG it comes
   from a configured naming rule with a collision check, or an explicit input with the write
   request, never from an unchecked guess.
6. **Demo write permission** cannot be confirmed from the documentation (several read routes
   are refused for the isolved demo account; PrismHR permissions are per method). Every
   provider gets a dry run first; a real write to a demo tenant happens only with the user's
   explicit approval.

## 5. Direct deposits

Model: `src/normalization/canonical/deposits.py`. One `DirectDeposit` record per account
allocation (D-046), linked by `employee_id` and `company_id`.

| Field | Meaning |
| --- | --- |
| `sequence` | Provider's sequence number as sent: isolved (0 = "Net Pay"), UKG (1..n). PrismHR has none: null, `not_provided`. |
| `allocation_type`, `percent_basis` | Fixed amount, percent (of net pay, gross pay, or the remainder after fixed amounts), or remainder (D-032) |
| `amount`, `percent` | Allocation value. `percent` is 0 to 100 and validated to that range. |
| `skip_if_insufficient` | Skip when the full fixed amount cannot be taken (PrismHR `FS`) |
| `account_type` | Checking, savings, checking or pay card, pay card, instant pay |
| `bank_name`, `routing_number`, `routing_last4`, `account_number`, `account_last4` | Bank details; full numbers sensitive, masked values never stored as numbers (D-020) |
| `status`, `prenote_status` | Active, inactive or pre-note; pre-note progress (UKG) |
| `frequency` | Every pay, monthly, ... (isolved label, UKG enum) |
| `applies_to_paycheck_kinds` | Paycheck kinds the deposit applies to (PrismHR `voucherType` R, S, V) |
| `effective_from`, `effective_to` | Active window (UKG; period roles, so sentinels mean open-ended) |

Provider notes:

- **Ids.** isolved and UKG deposits have ids. **PrismHR deposits have no id or sequence**: the
  id is the position in the employee's list, deterministic for one response but not stable if
  PrismHR reorders the list. It is **never read as a payment priority**, and each such record
  carries an `unstable_id` diagnostic.
- **Allocation.** PrismHR methods are documented (`F` fixed, `FS` fixed and skip, `P` percent,
  `PN` percent of net after fixed, `B` remaining balance); `P` gives no basis, so
  `percent_basis` is unknown. UKG `calc_method` is a documented enum (`FULL` remainder,
  `FLAT_AMOUNT`, `NET_PAY`, `GROSS_EARNING`, `DIRECT_DEPOSIT_PER_OF_REMAINDER`). isolved: amount
  means fixed, percent means percent with no stated basis, and only an **active** account with
  sequence 0 is the remainder account (D-015; the remainder behavior is inferred from the
  "Net Pay" label).
- **Allocation values are validated against the type:** a fixed amount carries no percent or
  percent basis, a percent carries no amount, a remainder carries neither. An unknown type
  allows any combination, so raw values are still kept.
- **Percent scale.** Verified 0 to 100 for isolved (spec maximum 100 and live split) and UKG
  (live split). PrismHR is the provisional exception of 1.5 (D-032).
- **Account type.** PrismHR `C` means "checking account or pay card"; the ambiguity is kept
  (`checking_or_pay_card`), never resolved to one.
- **PrismHR `limit`** ("precision 2, permissible only when method is P") does not say what it
  limits, so it stays raw in `provider_extensions`.
- **UKG** deposits come from a deprecated route (`deprecated_source` diagnostic).
- **Not deposits (D-081).** PrismHR HSA deposit settings (`getEmployee` `hsa`, employee and
  company HSA contributions sent to checking or savings) and voluntary ACH deduction accounts
  (`getACHDeductions`, DED1 to DED3) move deductions, not net pay: the HSA settings stay in the
  employee's `sensitive_provider_extensions`, and the ACH deduction route is not read. The
  deductions themselves are setups and paycheck lines.
- **isolved source.** Deposits come from the per-employee `directdeposits` route; the employee
  list documents a `directDeposits[]` block but never sent it (138 of 138, D-081).
- **Volume in the demo data:** PrismHR 1 of 6 sampled employees; isolved 10 accounts
  (8 employees queried); UKG 18 accounts (all 103 employees).

## 6. Deductions

Models: `DeductionCode` in `company.py`, `DeductionSetup` in `deductions.py`. Deductions taken
in a payroll are paycheck lines (payroll section), not setups.

### 6.1 Deduction codes (company-owned, D-047)

Each provider defines deduction codes per company: PrismHR client deduction codes (43 in client
102), UKG `lookup/deduction-codes` (43), the isolved client pay item catalog
(`/api/clients/{clientId}/payItems`, 19 deduction items of 56, D-066). Setups and paycheck lines
refer to a code, so each deduction is classified once.

Classification uses two independent dimensions, each unknown unless the provider establishes
it: **category** (benefit, retirement, retirement loan, loan, garnishment, flexible spending,
health savings, voluntary) and **tax treatment** (pre-tax, post-tax, Roth), plus `is_catch_up`.
PrismHR deduction types are documented (lookup `deduction_type`):

| Type | PrismHR meaning | Category | Tax treatment |
| --- | --- | --- | --- |
| `V` | Voluntary | voluntary | unknown |
| `C` | Section 125 | benefit | pre-tax (inferred: salary reductions for qualified Section 125 benefits are usually pre-tax; PrismHR does not state it) |
| `P` | Post Tax Benefit | benefit | post-tax |
| `F` | Flexible Spending Account | flexible spending | unknown |
| `G` | Wage Garnishment | garnishment | unknown |
| `L` | Employee Loan Payment | loan | unknown |
| `K` | Pre-Tax Retirement Contribution | retirement | pre-tax |
| `KC` | Catch-Up Retirement Contribution | retirement, catch-up | unknown |
| `KE` | Post-Tax Retirement Contribution | retirement | post-tax |
| `KL` | Retirement Plan Loan Payment | retirement loan | unknown |
| `KR` | Roth 401(k) Contribution | retirement | Roth |
| `KCR` | Roth 401(k) Catch-Up Contribution | retirement, catch-up | Roth |
| `VG` | (undocumented; "IRS Levy" in all 3 clients) | garnishment (inferred, D-026) | unknown |

UKG codes carry no type (D-031): category and tax treatment are unknown unless a tenant mapping
is configured. isolved catalog items carry a `systemBenefitType` label (D-066): "Medical, Dental,
Vision Pre-Tax 125" give benefit and pre-tax; "401(k)" retirement; "FSA Medical" and "FSA
Dependent Care" flexible spending; "Health Savings Account" health savings, each `inferred` from
the provider's label (no documented list, D-081), with tax treatment unknown where the label does
not state it. "None" (2
deduction items) stays unknown.

### 6.2 Deduction setups (D-048)

One `DeductionSetup` per employee assignment. Main fields: `deduction_code_id` (nullable) and
the raw `deduction_code` reference, `category`, `tax_treatment`, `calc_method`, `amount`,
`percent`, `period_numbers` (pay periods within a month, 1 to 5), `per_period_limit`, `maximum`
and `maximum_period` (month, quarter, year, lifetime), `goal_amount`, `balance`,
`track_arrears`, start and stop dates, `status`, `employer_match`, `benefit_enrollment_id`, and
nested `garnishment` and `loan` parts.

**`source_basis`** states how strongly the source establishes the setup:

| Basis | Used for | Diagnostic |
| --- | --- | --- |
| `documented_assignment` | PrismHR `getDeductions`; isolved garnishments; PrismHR retirement loans | none |
| `candidate_assignment` | isolved legal-level pay items (D-017: the best available source, not validated as enrollment) | `unvalidated_source` |
| `presence_only` | PrismHR `checkForGarnishments` returning enrolled: a garnishment exists, but no setup or code is known (detail route 403). Details are null with `not_provided`. | `source_unavailable` |

Validation enforces the bases: a `presence_only` setup may carry only `category`,
`tax_treatment`, `is_catch_up`, `status` and `currency` (no code, amounts, limits, dates or
nested details) and must carry a `source_unavailable` diagnostic, and a `candidate_assignment`
must carry an `unvalidated_source` diagnostic.
The link check (D-045) also rejects a setup whose category, tax treatment or catch-up flag
differs from its linked code (D-047: a deduction is classified once); a null or an `unknown`
value on either side is not a conflict, since unknown makes no claim (D-089). The same rule
applies to paycheck lines (8.3, 8.4).

Provider notes:

- **PrismHR:** amounts, `usePercent`, `period`, `basis`, `limit` ("maximum the system can
  deduct in a payroll period") and match method are documented. No positive garnishment flag
  was seen (2 of 2 responses `enrolled: false`).
- **isolved:** setups come from the legal-level pay items list joined to the per-employee list
  on (legal, employee, id) (D-017). **`deduction_code_id` is nullable:** 2 of the 7 saved
  assignments have no `payItemCode`, so they cannot be linked to a catalog code. Parameters:
  `Amount` maps to `amount`. The pay item type and the parameters are read from the
  per-employee entry: the legal list sends no type (7 of 7) and fewer parameters on 2 of 7; the
  other fields agree (D-081). **`Percent` is not typed:** its scale is undocumented and every
  sampled value is 0, so under the unit rule (1.5) it stays raw in `provider_extensions` with
  `unit_unverified`. `Amount2` and `Rate` have no documented meaning and stay raw too.
- **isolved garnishments** are their own records (type, percent of disposable income, payee,
  balances). Their `selectedDeductions` keep their provider ids in `linked_deductions`; they are
  **not required to join** to a pay item assignment: the 2 saved ids match none of that
  employee's pay item ids (their names match catalog items).
- **UKG:** no employee deduction setup route (D-030); deduction amounts exist only on pay
  statements.
- **isolved catalog:** the client pay item catalog route gives the company codes (D-066):
  Deduction items become `deduction_codes`; Earning and Memo Calc items become `earning_codes`
  (section 8.3, D-054). Check detail lines carry the catalog id (205 of 205 earning and
  deduction lines). Per-employee pay items and legal-level assignments use other ids (0 matches)
  but carry the catalog code (19 of 19 and 5 of 5 that have one); the negative-id per-employee
  entries (mostly zero values) are not employee setups.
- Sensitive: garnishment `case_number` and `payee` (the payee text can embed account digits).

## 7. Benefit enrollment (D-049)

Model: `src/normalization/canonical/benefits.py`. One `BenefitEnrollment` per employee plan
enrollment: an employee's coverage, separate from deduction setups (money taken from pay) and
from benefit lines on paychecks (what one payroll charged). A PrismHR deduction that names a
benefit plan links to its enrollment through `benefit_enrollment_id`.

| Field | Meaning |
| --- | --- |
| `plan` | Provider plan reference (id, code, name) |
| `benefit_type` | Medical, dental, vision, life, short- or long-term disability |
| `status` | Eligible but unenrolled, active, terminated, COBRA, waived |
| `coverage_level` | Employee only, employee and spouse, employee and children, family |
| `coverage_start`, `coverage_end`, `deduction_start`, `deduction_end` | Coverage and payroll deduction windows |
| `is_section_125`, `waive_reason` | Cafeteria plan election; reason for waiving |
| `plan_details[]` | Dated detail rows: effective date, coverage level, coverage amount and basis, employee premium, employee contribution, employee premium contribution, provider contribution, dependent premium, `amount_period` |

Provider notes:

- **PrismHR** (`getBenefitPlans`, 6 files, 53 plans): `status` (E, A, T, C, W) and `insClass`
  (M, N, V, L, D, S) are documented; **`insClass` `O` appears on 7 of 53 plans and is
  undocumented**, so it is unknown with the raw code kept. **11 of the 53 plans have several
  detail rows** (up to 6, each with its own effective date); all are kept in `plan_details`.
  Premium amounts are kept, but PrismHR does not state their period, so `amount_period` is null
  with `not_provided`. Detail `planType` (ES, EE, E1) is described only as "benefit plan type",
  so coverage level is unknown with the raw code kept. Group term life accrual lists stay in
  `provider_extensions`; covered dependents and beneficiaries (empty in all samples) go to
  `sensitive_provider_extensions`.
- **UKG** (`employees/{aid}/benefits`, 11 enrollments for 1 of 3 employees): plan, coverage
  window and `coverage_level` labels ("Employee", "Waived", "75% Option", ...); no amounts.
- **isolved:** the primary spec documents `GET .../employees/{employeeId}/benefits` ("List
  Employee Benefits"), but every call returned 404 (6 employees, no positive comparison,
  D-011). The live result is unknown: the 404s do not show that isolved has no enrollment data.
  The mapping is written from the spec model (Phase 3, D-081): plan, status from `isActive`,
  coverage dates and waive reason are typed; benefit type and coverage level labels have no
  documented list and are `unknown`; account numbers, dependents and beneficiaries go to the
  sensitive extension. Fixtures exercise it (Phase 4).

## 8. Payroll (D-050 to D-056)

Model: `src/normalization/canonical/payroll.py`. Evidence base: PrismHR 192 distinct vouchers
(3 clients) and 1,813 batches; isolved 25 check details, 430 listed checks and 231 run history
entries (legal 5797, pay group 7612); UKG 67 payrolls and 20 pay statement details (of 108).

### 8.1 Records and links

| Provider | Payroll run | Paycheck | Paycheck to run |
| --- | --- | --- | --- |
| PrismHR | batch (client, batch id) | voucher (client, voucher id) | voucher `batchId` |
| isolved | payroll run history entry (`id`) | check (`id`) | joined on (legal, check date, run number), see below |
| UKG | payroll (`id`) | pay statement (`id`) | the route: statements are read per payroll |

- Both records link to `company_id` and, when the source identifies it, `tax_entity_id` (UKG
  payroll `ein`; isolved legal; PrismHR client). A paycheck also links to `employee_id`,
  `payroll_run_id` and `pay_group_id`.
- **List and detail routes (D-081).** One route is the source for each fact. PrismHR: the batch
  list gives type, status, pay date and pay group periods; batch info adds the description and
  period numbers (its repeats agree on 17 of 17 batches, but its type is blank on V batches).
  isolved: the legal check list only enumerates checks, the detail is the paycheck source. UKG:
  the payroll list is the run source and the detail adds only `date_finalized` (24 of 24 equal);
  the statement list only enumerates statements (18 of 18 equal to the detail).
- **isolved checks carry no run id.** Joining on (check date, `payrollRunNumber`) to completed
  runs matched 430 of 430 checks against the **full** run history (20 of 36 completed runs have
  checks in legal 5797). The 2018 date-filtered history (45 runs, 34 completed) matches only
  409, for a reason not established. The join is evidenced, not documented, so
  `payroll_run_id` is nullable and the adapter reads the full run history, never a year-filtered
  one. A check links only when exactly one completed run of its legal has its pay date and run
  number; a match with only a run not processed, or with several completed runs, is not linked
  (`conflicting_sources`); no match is `not_provided`, or `source_unavailable` when a run history
  of the legal could not be read (a 404 there is not "no runs", D-011) (D-089). The check sends no
  pay group, so the paycheck's `pay_group_id` is `not_provided`.
- **isolved listed check without a detail:** a check the legal check list names whose detail is
  missing or the empty list `[]` is kept as a Paycheck with its ids, company and employee only,
  every other field `not_provided` and a `source_unavailable` diagnostic (D-089).
- **Reversals:** a PrismHR reversal voucher (in a V batch, voucher type still R) points to the
  voucher it reverses through `voidVoucherId`. `reverses_paycheck_id` holds that canonical id
  and `void_date` the provider's void date. The original may predate the synced window, so the
  link check does not require it to be in the set.

### 8.2 Run type, status and paycheck kind (D-050)

Run and paycheck vocabularies are separate enums, and values follow the provider labels:

- **Run type** (`PayrollRunType`): PrismHR batch R is "Scheduled", not "Regular", so it maps to
  `scheduled`; UKG "Regular" and isolved "Regular Payroll" map to `regular`. The model does not
  claim the two are the same. isolved "Data Conversion" (every completed live run, D-014) is
  `conversion`.
- **Paycheck kind** (`PaycheckKind`): PrismHR voucher type (R Regular, V Vacation, S
  Supplemental, A Arrears, J Adjustment, D-033), isolved check type. Run type and paycheck kind
  are independent: sampled R batches hold A and S vouchers, an M batch holds an S voucher.
- **Run status** (`PayrollRunStatus`): only `completed` (PrismHR COMP, isolved "Completed
  Payroll Run") and `finalized` (UKG FINALIZED) describe processed pay. UKG OPEN maps to
  `open` (calculated, not finalized, D-030), never to `completed`.
- **Paycheck status** (`PaycheckStatus`): PrismHR PRNT is `printed`; UKG statement statuses map
  one to one; isolved checks have no status (`not_provided`).
- **Pay periods:** a run holds `pay_periods[]` (pay group, start, end, period number), because a
  PrismHR batch can cover several pay groups with their own periods (15 of 1,813 batches).

### 8.3 Earnings and earning codes (D-054)

The company owns `earning_codes[]` like `deduction_codes` (D-047), so an earning is classified
once: `pay_class` (wages, reimbursement, non-cash fringe, reported tips, memo), `is_cash`,
`rate_class` (straight, premium, doubletime, other) and `quantity_type` (hours or units).

- **PrismHR** documents all four on the client pay code table (`payClass`, `compensationType`,
  `rateClass`, `payReason`). All 189 sampled earning lines and 80 other-earning lines join to
  their client's table. Applying today's table to older vouchers assumes the codes have not
  been redefined.
- **UKG** codes and **isolved** catalog earning items carry no earning class; their
  classification is unknown unless configured, except isolved catalog items of type "Memo Calc"
  (class memo, inferred from the label, D-066, D-081) and line-level evidence: isolved `isMemoEarning` (documented flag) and UKG
  `type_name` "Fringe" (provisional, D-031).
- Each `EarningLine` has the code link and raw reference, its classification (validated against
  the code by the link check), `hours`, `hours_worked`, `units`, `rate` and `amount`.
- **Hours vs units (unit rule, 1.5):** PrismHR `hoursUnits` is hours only for pay codes with
  `payReason` H; for U codes it goes to `units` (sampled U lines: BON, BONUSup, COMM, 7 lines;
  FRINGE and MEMO are U codes too). The link check rejects `units` on a line whose code counts
  hours and `hours` on a line whose code counts units. `hours_worked` is not constrained: it is
  documented as hours worked from the time sheet for every pay code (0 on all 7 U lines). UKG
  earning `hours` are milliseconds converted to hours (D-028). UKG `quantity` has no documented
  unit and stays in `provider_extensions`.
- **PrismHR `payAmount` is the line total**, although the spec describes it as "pay per hour or
  unit": `earnAmount` equals the sum of `payAmount` on 177 of 177 sampled vouchers that have
  earning lines (175 R, 2 S; the other 15, types A and J, have none), and REG
  40 hours x `unitRate` 59.375 = 2375.00 `payAmount`. The data is followed; `unitRate`
  (undescribed) is the rate.

### 8.4 Deductions, taxes, contributions, benefits, payments (D-051, D-055, D-056)

| Lines | Contents and sources |
| --- | --- |
| `deductions[]` | Employee deductions taken: code link and raw reference, classification inherited from the code (D-047), plan reference (PrismHR `planId`), amount. Garnishments (isolved `garnishments[]`, PrismHR type G) are deduction lines with category garnishment. |
| `taxes[]` | One tax for one payer: raw code and label, `tax_type`, `jurisdiction_level`, `jurisdiction`, `paid_by`, amount, taxable, gross, exempt and over-limit wages, `rate` (a fraction, `Rate`). |
| `employer_contributions[]` | PrismHR `employerContributions[]`; UKG deduction `er_amount` (linked to that deduction code); isolved memo earnings whose label is in the mapping table. |
| `benefit_lines[]` | Plan rows as reported for the paycheck (PrismHR `benefit[]`, isolved `benefits[]`): premium amount and cost, employee contribution and deduction, employer contribution, catch-up, eligible wages, coverage period. **Informational, not additive.** |
| `retirement` | PrismHR voucher `retirement` block, employer side only. **Not additive.** |
| `payments[]` | Check, direct deposit and non-cash lines: method, amount, routing and account last 4. |

- **Tax lines have one payer each.** UKG holds employee and employer amounts on one line; it is
  split into two canonical lines that keep the same `source_line_id`. PrismHR (`employeeTax[]`
  vs `companyTax[]`) and isolved (`isEmployeeTax`) already separate them. A side with wage
  figures but no amount (19 UKG employee sides) keeps its wages, with amount null.
- **Tax type (D-056):** no provider documents a tax type field or code table that was
  retrieved. Labels that name one statutory tax exactly and unambiguously ("Federal Income Tax",
  "FEDERAL WH", "Social Security") map as `inferred`, with an `inferred_mapping` diagnostic on
  the paycheck whose `field` points to the line (`taxes[3].tax_type`); partial labels such as
  UKG "Wisconsin" stay `unknown`. The PrismHR code pattern (`05-20`, `15089-30`) is undocumented
  and never parsed. The label tables (`<provider>.tax_label`, D-081) list the federal, FICA and
  FUTA labels and a few state income and unemployment labels per provider; any other label is
  `unknown` with `unknown_code`. They also set `jurisdiction_level`; `jurisdiction` is null with
  `not_provided` (no field states it).
- **Benefit lines repeat other lines.** isolved `benefits[]` employee amounts equal deduction
  lines (50 of 50), and isolved also lists non-contribution rows there ("Leave Accrual" equals a
  Holiday earning, "GTL" the GTL earning). Summing benefit lines with deductions or
  contributions double counts.
- **isolved employer contributions come from memo earnings (D-055).** For dental, medical and
  HSA, the memo earning equals the `benefits[]` employer amount in 28 of 28 nonzero pairs; for
  all 16 "401k Match" memo earnings, `benefits[]` shows 0. Two further memo earnings have a
  null amount against a benefit employer amount of 0.0: they are not matches, and the
  contribution amount stays null. Reading memo earnings as contributions rests on their labels
  and the arithmetic, so the paycheck carries one `inferred_mapping` diagnostic per such line,
  with `field` pointing to it (`employer_contributions[2]`; lines have no diagnostics of their
  own); a memo
  earning whose label is not in the table stays an earning line with class memo.
- **PrismHR retirement block.** Employee fields match the deduction lines of their type (K, KC,
  KR, KCR, KE, KL) on all 85 vouchers with retirement amounts, but that is evidence of repetition
  only for pre-tax elective (nonzero on 56 vouchers) and Roth (2). Catch-up, Roth catch-up,
  post-tax and loan payments are zero on both sides throughout the sample, so they match
  trivially and their relationship is not established. The employee fields stay in
  `provider_extensions` as source evidence. Employer fields (match, non-elective, safe harbor 1
  and 2, PEO match) appear nowhere else, so they are typed in `retirement`. They are **not**
  turned into contribution lines or summed: on 16 vouchers the non-elective and both safe harbor
  fields are nonzero and equal, and how they relate is undocumented. On arrears vouchers every
  retirement amount is null in the source and stays null.
- **Payments.** PrismHR `checkAmt` and `directDeposit[]` (account numbers provider-masked, so
  only last 4 where visible); isolved `checkAmount` and `directDeposits[]`; UKG Check, Direct
  Deposit and Fringe lines. UKG "Fringe" lines (8) offset non-cash earnings and are kept as
  `non_cash` payments for information; they are not part of net pay. PrismHR voucher deposit
  statuses (`D*C`, `D*S`) are undocumented and stay raw. When the source identifies the deposit
  record, `direct_deposit_id` links to it; the link check requires that deposit to be in the set
  and to belong to the paycheck's employee.
- **Zero-pay paychecks are full records (D-033).** Nothing rejects a paycheck without earnings or
  pay; PrismHR arrears vouchers keep their benefit and employer contribution lines.

### 8.5 Totals and missing amounts (D-052, D-053)

| Total | Meaning | Filled from |
| --- | --- | --- |
| `gross_pay` | Cash earnings before taxes and deductions | PrismHR `earnAmount`, isolved `grossPay` |
| `gross_wages` | Gross pay plus imputed income | isolved `grossWages` (differs from `grossPay` on 25 of 25 details by the GTL amount) |
| `total_earnings` | Cash plus other earnings | PrismHR `totalEarnings` |
| `net_pay` | Paid to the employee by check and direct deposit | PrismHR `netPay`, isolved `netPay`, UKG derived |

- A total is filled only from a provider field with the same definition. `gross_wages` and
  `total_earnings` are different totals: besides FRINGE, PrismHR other earnings hold MEMO
  (adjustment voucher 001167) and REG and Sick (adjustment voucher 035664), so `totalEarnings` is
  not "gross plus imputed income".
- `gross_pay` for isolved excludes reimbursements (Mileage is added after it). PrismHR
  `earnAmount` was not seen with a reimbursement line, so its treatment of one is unknown.
- **Derived totals** are named in `derived_totals`; validation requires each named total to be
  a total and to hold a value. UKG states no totals: `net_pay` is derived from Check and Direct
  Deposit payments **only when every one of them has an amount** (14 of 20 statement details);
  `gross_pay` stays null (`not_provided`), since UKG cash classification is provisional.
- **A missing amount is null with `not_provided`, never zero (D-053).** UKG omits amount keys on
  some lines (6 Check payments have no `ee_amount`). The UKG cash equation holds on 20 of 20
  statements only when missing amounts are read as zero.
- **Reconciliation:** when a missing input prevents a specific total or comparison, the adapter
  raises `reconciliation_incomplete` (warning), leaves that derived total null with
  `not_provided`, and does not also claim a mismatch. A missing value that the calculation does
  not use does not block it. `reconciliation_mismatch` is raised only when all inputs are present
  and disagree.
- **Net pay vs payments (D-089):** for PrismHR and isolved, `net_pay` is compared with the sum of
  the check and direct deposit payment lines (PrismHR netPay = checkAmt + deposits on 192 of 192
  live vouchers). The check payment line is always written, even at 0. A difference gives
  `reconciliation_mismatch`, a payment without an amount `reconciliation_incomplete`. UKG net pay
  is derived from the same lines, so it is not compared again; it is derived only when there is at
  least one Check or Direct Deposit line, every one has an amount and no payment type is unknown.

### 8.6 Kept in extensions, with reasons

| Data | Field | Reason |
| --- | --- | --- |
| isolved check employee snapshot (name, address, SSN as sent, filing statuses, exemptions, `taxCategories`, Vertex geo codes) | `sensitive_provider_extensions` | A historical copy of employee data at check time; the employee record holds the current values. Personal data, so masked. |
| isolved to-date accumulators (`ptd`, `mtd`, `qtd`, `ytd`, `ftd` amounts, hours, wages) on every line | `provider_extensions` | Not listed in the brief (D-037); one provider only per line. |
| PrismHR retirement employee fields | `provider_extensions` | Repeat deduction lines; kept as source evidence. |
| Line context: PrismHR department, job, location, workers' comp, charge date; UKG cost centers, batch, date range | `provider_extensions` | Costing detail, not pay. |
| PrismHR workers' comp, GL distributions, arrears lists, `fsaMatch`, `hsaPeoMatch`; isolved reissue check; UKG calculation `messages` | `provider_extensions` | Provider processing detail. UKG messages explain why a statement is not final. |
| UKG earning `quantity`, UKG wage figures on deduction lines | `provider_extensions` | Unit or meaning not documented (unit rule, 1.5). |

`Paycheck` and `PayrollRun` have no sensitive typed fields: payment lines hold only last 4.
