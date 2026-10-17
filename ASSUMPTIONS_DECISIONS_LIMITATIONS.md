# Assumptions, decisions and limitations

This file records what was assumed where the sources were silent, the main architecture and
data decisions with the reason for each, the issues found in the provider data, and the known
limitations. The approach, setup and results are in [README.md](README.md).

Code comments cite internal decision numbers (D-xxx) from the project's working log; this file
summarizes the ones that matter to a reviewer.

**Evidence words used below.** *Documented*: the provider's contract or lookup file states it.
*Live*: seen in the organizer's demo tenants, with counts. *Inferred*: read from a label or
from arithmetic, not stated by the provider; inferred values are marked `inferred` in the
output and carry an `inferred_mapping` diagnostic.

## Contents

1. [Assumptions](#1-assumptions)
2. [Decisions](#2-decisions)
3. [Data issues found, and what was decided](#3-data-issues-found-and-what-was-decided)
4. [Gaps by provider](#4-gaps-by-provider)
5. [Known limitations](#5-known-limitations)

## 1. Assumptions

Each assumption is either flagged on the records it affects or stated in the mapping tables.

| Assumption | Why it was needed | How it is handled |
| --- | --- | --- |
| All amounts are in US dollars. | No provider sends a currency on payroll data; all three are US payroll systems. | Every money-holding record states `currency: USD`. A currency the source does state (UKG EIN currency) is used as given. |
| The tenant id returned by sign-in is stable. | Canonical ids include it. | Ids are deterministic for the same tenant; a changed tenant id would give new ids. |
| isolved legal entity ids and UKG pay statement ids are unique on their own within a tenant. | Their ids are used without their parent id. | Consistent with all demo data (for example 108 UKG statements, 108 ids); the parent ids are kept in `source_ids`. |
| PrismHR deposit percentages are on a 0 to 100 scale. | The spec names percent methods without a scale, and no live PrismHR percentage deposit exists. isolved and UKG both use 0 to 100. | Mapped on that scale with a `unit_unverified` diagnostic on each such deposit. |
| Today's code tables apply to older paychecks. | Earning and deduction lines are classified by joining their code to the company's current code table. | Stated in the model; a code redefined over time would be classified by its current meaning. |
| Placeholder dates are `0000-01-01` and `1900-12-31` (open start) and `2099-12-31` and `9999-12-31` (open end). | Providers use them instead of null (PrismHR pay rate history, UKG profiles and deposits). | On a period bound they mean "open" (`not_applicable`); on any other date they are not a real date (`not_provided` with a `sentinel_date` diagnostic). |
| An active isolved deposit with sequence 0 receives the remainder of net pay. | The spec labels sequence 0 "Net Pay" but does not describe its behavior. | Mapped to `remainder`, marked inferred. |
| A UKG pay period profile is a pay group. | UKG has no pay group resource; employees link to a profile, and payroll names contain the profile name. | Mapped that way and recorded as an inference. |
| An isolved check belongs to the completed run of its legal entity with the same check date and run number. | isolved checks carry no run id. | Linked only when exactly one completed run matches; otherwise null with the reason (live: 430 of 430 checks matched). |
| A record that names an id (an EIN, a pay group) refers to a real entry, even when the provider's own list omits it. | UKG and PrismHR records name entries their lookups leave out. | The entry is built from the fields the records send and marked `reference_only`. |
| A timestamp with a time of day and no time zone, in a date field, means its calendar date. | isolved sends some hire and status dates that way. | The date part is used; the dropped time is named in an `inferred_mapping` diagnostic. With a time zone, the value stays unparseable. |
| PrismHR `earnAmount` is cash gross pay. | It reconciles with net pay, taxes and deductions on 116 of 117 live vouchers. | Mapped to `gross_pay`. Whether it includes reimbursements is unknown (none seen). |

## 2. Decisions

### 2.1 Architecture

- **Python, keeping the provided scaffold.** The organizer's CLI, adapter registry and
  tests were extended rather than replaced, so a reviewer runs it the way the starter expects.
- **The core pipeline first, then an application over it.** The normalization is what
  must be correct; the API and UI only call it, so they were built last to avoid rework while
  the model was still changing.
- **Pydantic v2 models are the single source of the schema.** One definition
  gives types, validation (including rules JSON Schema cannot express, such as the null rule)
  and the exported JSON Schemas. A test validates real output against the exported files, so
  the two cannot drift.
- **Mapping tables are data, and the docs are generated from them.** At about 4,100
  distinct source fields, hand-written Markdown could not be checked. One JSON table per
  provider and record type classifies every field; adapters cite the rows they apply, and tests
  compare the citations with the tables. Adapters are ordinary Python, not a generic engine
  driven by the tables, so the mapping logic stays readable.
- **The input is a bundle, and one run gives one output document.** One record
  is built from many responses, and links can only be checked across all records of a tenant.
  Every record is validated before anything is written; if one fails, nothing is written.
- **The organizer's adapter files run the pipeline.** The starter's
  `normalize(entity, response, reference)` functions and `normalize` command are implemented
  rather than left as placeholders; the starter test's placeholder assertion was replaced, as
  the organizer's original test notes asked once the code was implemented.
- **A shape guard instead of crashes.** A response whose top-level shape breaks its
  contract is set aside before the adapters run and reported; any other failure exits cleanly
  with nothing written.
- **The live fetch fills a bundle.** The same pipeline normalizes live data and fixtures,
  so every guarantee (validation, masking, link check) applies to live runs without new code. A
  live bundle can be saved and normalized again offline.
- **The app stores records in SQLite and masks them on the way out.** The full PrismHR
  output is about 424 MB, so the API cannot page through a document file. One row per record,
  indexed by list, company, employee and run; full values are stored locally (Git-ignored) so the
  explicit opt-in can work, and every response is masked by default.

### 2.2 Reading the provider APIs

- **The optional live demo data was used.** The contracts are old snapshots, and the
  isolved and UKG lookup files leave many code meanings empty. Live responses show which fields
  and codes actually occur and where the contracts are wrong. Tests and fixtures stay offline.
- **Only isolved's primary Swagger snapshot is used.** As the brief instructs, schemas
  are never mixed between the two snapshots; the alternate one served only for comparison.
- **Base URLs and the auth header come from the sign-in response.** The contract
  servers differ from the demo (PrismHR's spec points at production; the demo is a UAT host),
  and the header name and prefix differ per provider.
- **Tokens are refreshed before they expire.** isolved tokens last 5 minutes and a full
  crawl takes longer; a new sign-in happens 30 seconds before expiry and once after a 401.
- **Every list is read to its last page.** Reading only the first page silently drops
  employees (an isolved legal entity had 118 employees on 2 pages).
- **PrismHR success means HTTP 200 and `errorCode` 0.** PrismHR can report an error in
  the body with HTTP 200. A 404 whose message says no records exist is an empty result; a 403
  is a permission limit; anything else is an error.
- **isolved 404 means "no records" only where that is shown.** isolved returns 404 with
  an empty body both for "nothing here" and on routes that never returned data. A 404 is read as
  empty only on the five routes where both data and 404 were seen; elsewhere it stays "unknown".
- **Routes the demo account cannot read are documented gaps, with working alternatives where
  they exist.** For example, isolved payroll comes from run history and per-check
  details, because the dedicated payroll and deduction routes return 401.
- **isolved taxes come from the per-check detail.** The check list returns `taxes: []`
  for every check; only the detail route has them.
- **PrismHR payroll is read batch by batch.** The batch list is complete and its
  vouchers page reliably; the date-range voucher route reports an ambiguous total.
- **The payroll window is the 12 months ending on each company's latest pay date.** A
  window ending today would show no isolved payroll at all (its only completed payroll is from
  2018). PrismHR and UKG list payrolls only by date range, so the latest pay date is found by a
  bounded search one year at a time; those search calls are not kept.
- **All PrismHR clients by default.** One command covers the whole tenant; `--company`
  narrows it. Sampling employees was rejected because their paychecks would become broken links.
- **The isolved SSN is fetched from its one source and masked.** Only
  `/employeesWithSSN` returns it. The brief asks for complete employee data, and the output
  masks it by default.

### 2.3 Canonical model conventions

- **Company is the employer scope that owns employees and code tables.** That is a
  PrismHR client, an isolved legal entity and a UKG company. Each company holds a list of tax
  entities (EINs). Splitting UKG's one company by EIN was rejected: its code tables, deposits and
  API scope are company-level.
- **One Employee per provider employee record.** Records are never merged into
  people. UKG's own "same person" key is kept in `person_ref`, which means "same person within
  this tenant" only.
- **Companies own their lists, with canonical ids.** Tax entities, work
  locations, pay groups, earning codes and deduction codes are entries of the company, so an
  employee's location or a paycheck line's code points at something real. Each entry keeps its
  own provider settings.
- **Every null has a reason.** A sparse `field_status` map lists each null field as
  `not_provided`, `hidden_by_source` or `not_applicable`; validation rejects an unexplained
  null. A masked provider value is never stored as a value: a partial account number looks valid
  and is worse than none.
- **Shared conventions.** Deterministic readable ids; exact decimals (never floats);
  percentages 0 to 100 and rates as fractions in separate fields; hours in decimal hours; ISO
  dates; coded values with their basis; a closed list of diagnostic codes; sensitive fields
  marked in the model.
- **Typed fields for everything the brief lists.** Even when only one provider
  supplies an item, it gets a typed field (the others say `not_provided`). New typed fields were
  otherwise added only when live data showed them filled; everything else goes to
  `provider_extensions`, so nothing returned is dropped.
- **Sensitive data, field by field.** Demographics, national ids, personal
  contact details, tax withholding, related people's details, work authorization, bank numbers,
  garnishment details and company EINs are sensitive. Sensitive provider extras have their own
  field (`sensitive_provider_extensions`), so they cannot bypass masking.
- **Masked by default everywhere.** Full values in the model; the CLI, API, UI and logs
  show them masked unless the user explicitly asks.
- **Links are checked across records.** After assembly, every reference is checked:
  ownership of tax entities, locations, pay groups and codes, managers, and every record's
  employee and run. Problems are reported in the output, never fixed by guessing.
- **Job history is its own list.** isolved and PrismHR send dated job changes, so the
  employee holds `job_history[]` next to the current job, with each entry's location and manager
  link-checked like the current one.
- **"Declined to answer" is kept apart from blank.** PrismHR documents Y, N, D (declined)
  and blank for disability and veteran flags. Reading D as blank would lose the answer, so D is
  kept as the raw answer while the flag itself stays unset.
- **Related people are never merged.** Each dependent or contact from the source is one
  entry; entries are never combined by name, and a name sent as one string is kept whole, never
  split into first and last.
- **Credentials are excluded, not kept.** PINs and URLs carrying tokens are not employee
  data and are stored nowhere, not even in the sensitive extension.

### 2.4 Mapping codes and values

- **An undocumented code is `unknown` unless provider data supports a reading.** Code letters are never read as words. PrismHR deduction type `VG` became a
  garnishment (inferred) only because the data shows it used for an IRS levy with the same
  calculation method as the documented garnishment types. Client-defined codes stay `unknown`
  with their raw code and label.
- **An employment type label that says full or part time is read.** Client-defined
  employment types such as 'Full Time', 'FT Exempt' or 'PT Hourly' map to full or part time,
  inferred; any other label stays `unknown`. Without this, the value was `unknown` for all 241
  UKG and isolved employees although every label stated it.
- **One source per fact.** Several routes repeat the same fact. The copies were compared
  offline; one source was chosen, and the others are excluded with the comparison as the reason,
  so two values can never disagree.
- **Pay frequency only from labeled or documented sources.** The
  isolved employee `payFrequency` integer is undocumented and contradicts its pay group, so it
  stays raw. PrismHR pay groups use the payroll schedule's documented letter; UKG uses its
  documented period type; isolved pay groups use the labels isolved itself gives the same
  integers (inferred).
- **Company codes come from each provider's own catalog.** isolved's client pay item
  catalog is its earning and deduction code list (paycheck lines carry its ids); UKG and PrismHR
  use their code lookups and client code tables.
- **UKG pay groups are pay period profiles, and UKG has no work location source.** UKG has
  no pay group resource; employees link to a pay period profile, which has a documented period
  type. Cost centers carry no location code (empty on all 71), so work locations are a gap.
- **PTO balances are in scope; the PTO transaction ledger is not.** Balances are
  part of an employee snapshot; the accrual and usage history is closer to time and attendance.
  Hours fields are filled only where the unit is documented (UKG milliseconds); isolved amounts
  without a unit stay raw, and no balance is derived where none is sent (PrismHR).
- **UKG durations are milliseconds and are converted to hours.** Documented and
  confirmed live (28,800,000 ms is an 8-hour day). Hours are exact when the division ends,
  otherwise rounded to 7 decimal places, so the source value can always be recovered.
- **Dates by field role.** A placeholder date on a period bound means "open"; on
  an event date it is not a date. Local timestamps give their date part; an impossible time of
  day (`T99:99:99`) or a time zone makes the value unparseable.
- **PrismHR loan dates are documented as YYYY-DD-MM.** Every other PrismHR date is
  YYYY-MM-DD, and no live loan exists to settle it. Each value is read both ways; when both
  readings are valid and differ, the field is null with the raw value kept.
- **UKG earning and deduction categories stay `unknown`.** UKG code lookups carry no
  type. The pay statement's raw `type_name` is kept, but is not treated as a category.
- **Tax types from exact labels only.** No provider documents a tax type. Only labels
  that name one statutory tax unambiguously ("Federal Income Tax", "OASDI") are mapped,
  inferred; partial labels ("Wisconsin") stay `unknown`. PrismHR's tax code pattern is never
  parsed.

### 2.5 Direct deposits

- **One record per account allocation, with shared allocation types.** All
  three providers express the same ideas: a fixed amount, a percentage (of net, gross or the
  remainder), or the remainder. Percentages are validated to 0 to 100.
- **isolved percentages are 0 to 100, and sequence 0 is the net pay account.** The spec
  sets a maximum of 100 and labels sequence 0 "Net Pay"; only an active account with sequence 0
  is read as the remainder, because inactive leftovers can look the same.
- **PrismHR deposits have no id or priority.** Their id is the position in the list,
  flagged `unstable_id`, and never read as a payment priority. PrismHR account type `C` means
  "checking account or pay card" and stays that ambiguous.
- **HSA transfers and voluntary ACH deductions are not direct deposits.** They move
  deductions, not net pay; they stay on the employee as sensitive extensions.

### 2.6 Deductions and benefits

- **Two separate classifications per deduction code.** Category (retirement, medical,
  garnishment, ...) and tax treatment (pre-tax, post-tax, Roth, ...) are independent fields, held
  once on the company's code and inherited by setups and paycheck lines.
- **Every deduction setup states how strong its source is.** `documented_assignment`
  (PrismHR's employee deduction route), `candidate_assignment` (isolved, below) or
  `presence_only` (a garnishment is known to exist but its details are refused). Validation
  enforces what each may carry.
- **isolved deduction setups come from a candidate source.** The documented employee
  deduction routes return 401 for the demo account. The legal entity's pay item assignments are
  the only list of employee-specific deductions; each joins to exactly one per-employee entry,
  and each setup is marked `unvalidated_source`.
- **UKG has no deduction setups.** The documented setup route returns 404; UKG
  deductions appear only as paycheck lines and company codes.
- **Benefit enrollments are their own record.** Coverage and money taken from pay do
  not always match (waived plans, employer-paid plans), and PrismHR sends dated plan history
  that single fields would lose.
- **PrismHR's stored deduction amount is the per-pay deduction.** It matched the
  paycheck lines; the plan's billing amounts have no stated period and stay raw.

### 2.7 Payroll

- **Batch types and voucher types are different code lists.** PrismHR uses the same
  letters for both with different meanings (`A` is "All types" on a batch but "Arrears" on a
  voucher). Zero-pay vouchers are full records, because they carry benefit and employer
  contribution amounts that exist nowhere else.
- **Run types and statuses follow the provider's words.** PrismHR "Scheduled" and UKG
  "Regular" stay different values. UKG's OPEN payroll is `open`; only `completed` and
  `finalized` describe processed pay.
- **Paycheck lines keep unit, payer and additivity straight.** A quantity is hours only
  when documented or verified as hours (bonus "units" are not hours). Each tax line has one
  payer (UKG's combined lines are split). Benefit and retirement breakdown lines are marked
  informational and are never summed.
- **Four totals with fixed meanings.** `gross_pay` (cash earnings), `gross_wages`,
  `total_earnings` and `net_pay` (check plus direct deposit), each filled only from a provider
  field with the same definition, or derived from lines and then named as derived.
- **A missing amount is never zero.** It stays null; when it blocks a check, the record
  says `reconciliation_incomplete` rather than claiming a match.
- **PrismHR earnings are classified through the client's pay code table.** Each
  line's code is joined to the documented pay class and cash or non-cash type of that client.
- **isolved employer contributions come from memo earnings.** They are the only source
  that includes the 401(k) match. Only the listed labels are mapped, inferred.
- **isolved garnishment line ids are garnishment ids.** Seen live: they equal the
  employee's garnishment records, not pay item codes, so they are kept as sent rather than
  linked to a code.

### 2.8 Writing employees to a provider

- **Create and update employee only.** The brief's optional extension is about employee
  data; deposits, deductions and payroll are not written, so no financial record is written to
  a demo tenant.
- **A write is a plan, built on the server from the stored record.** The plan lists the
  provider calls in order, every refusal with its field and reason, and notes. A plan with a
  refusal is never sent, and a plan sent by a client is never trusted.
- **Dry run for all three providers; a real send for UKG Ready only.** A UKG create needs
  no client codes and accepts an employee without an SSN. isolved and PrismHR creates need an SSN
  and several client codes,
  and PrismHR's create is a two-step import and commit that can leave a pending batch. Inventing
  SSNs in shared demo tenants is not acceptable, so their send stays off and their plans are
  shown as dry runs.
- **Nothing the record does not hold is ever sent.** A value that is masked by the
  provider or not provided is never sent; if the destination requires it, the write is refused
  with the reason (a PrismHR create from PrismHR data is refused for the SSN, which PrismHR masks).
- **Codes and provider-specific facts are never guessed.** A provider's raw codes are
  reused only when writing back to the same provider and company; otherwise each code is an input
  of the write. The UKG username is always an input. PrismHR's PEO start date and UKG's start
  date are never taken from the hire date: they are different facts (UKG's differ for 34 of 103
  live employees).
- **An SSN is never invented.** A UKG create sends the SSN when the record holds one; when the
  field is left empty, it sends UKG's own "no id needed" national id type instead. Any other
  missing national id is refused before sending.
- **A write is sent once.** A write retried after a lost answer could be applied twice,
  so no answer means "outcome unknown", not a retry. A 401 (sign in again) or a 429 or 503 (wait)
  is resent, because nothing was processed.
- **Only changed fields travel.** UKG and PrismHR updates send only the edited fields;
  isolved's update sends the whole employee model, as its contract requires. An update with
  nothing changed is refused.
- **Masked previews.** Sensitive values in a preview are masked unless the user opts in;
  credentials never appear; a send result keeps the status, outcome, new id and messages, never
  the response body.
- **Checked by reading back.** The live writes were verified by reading the employee back from
  UKG: after the create, 23 of 23 fields were stored as sent; after the update, the 9 changed
  fields had changed and the untouched ones had not.

### 2.9 Testing, fixtures and data handling

- **Fixtures are synthetic and generated from code.** One bundle per provider,
  from a fixed seed, byte-identical on every run, every response validated against its contract
  schema. Values are invented (SSNs in the 666 area, routing numbers in a reserved range); no
  live data is ever copied into them.
- **A lean suite: one test per rule, cases as subtests.** Goldens per provider pin the
  whole output; edge cases are pinned by record id.
- **No live calls in the suite.** The live fetch is tested against a fake provider that serves
  the fixture bundles.
- **Keys and live data never enter Git.** The key lives in the environment or a
  Git-ignored `.env`; live output, saved bundles and the app store live in the Git-ignored
  `live_data/`. Saved bundles have token-like strings scrubbed.
- **The organizer's files stay unchanged.** `contracts/` (checked by hash) and the
  organizer's README are never edited.

## 3. Data issues found, and what was decided

The contracts are snapshots "not verified against the latest live APIs". These are the
differences and surprises that changed a mapping.

| Provider | Issue | Evidence | Decision |
| --- | --- | --- | --- |
| All | Base URLs differ from the contracts | PrismHR spec: production host; demo: a UAT host with an extra path segment | Use the sign-in response's base URL |
| PrismHR | Wrapper keys are singular live, plural in the spec | Vouchers, history, payroll schedule (for example `payrollVoucher` vs `payrollVouchers`) | Tables use the documented paths; adapters read the live key |
| PrismHR | `payAmount` is the line total, not "pay per hour" as documented | Sum of `payAmount` equals `earnAmount` on 177 of 177 vouchers | Mapped as the line amount |
| PrismHR | Undocumented codes in use | Deduction type `VG`; federal filing status `M` and `S`; `hourlyPayPeriod` `A` | `VG` inferred from evidence; the others `unknown` with the raw code |
| PrismHR | Birth date sent in full although the spec says it is masked by default | Live employees | Mapped; the adapter also handles a masked value |
| PrismHR | SSN, bank account numbers and client EINs masked for this API user | `***-**-****`, `****`, EINs only `*` on 23 of 25 clients | `hidden_by_source` |
| PrismHR | Pay groups named by batches and employees but missing from the client's code list | One client lists none while its batches name one | Built from the id, `reference_only` |
| PrismHR | An empty date range answers HTTP 404, and a client that never ran payroll answers HTTP 400 | Window search on the demo tenant | Read as "empty" and "no payroll"; any other error stops the search |
| PrismHR | Loan dates documented as YYYY-DD-MM | Four loan date fields; no live value | Read both ways; ambiguous values null with the raw value kept |
| isolved | Paging is zero-based `page`, not the documented `pageNumber` | Live calls | Fetch and fixtures use the live form |
| isolved | The check list sends no taxes | `taxes: []` on all 430 checks | Taxes from the per-check detail |
| isolved | The check detail answers `[]` when it finds no check, where an object is documented | 1 of 27 live detail responses | Accepted for that exact body; the check is kept with its ids only |
| isolved | Employee `payFrequency` contradicts the pay group | Biweekly groups with 23, 24, 26 and 52 | Kept raw |
| isolved | Hire and status dates with a time of day | 24 of 138 employees | Date part used, dropped time noted |
| isolved | Garnishment line ids are not pay item ids | 80 of 80 lines equal the employee's garnishment ids | Kept raw, not linked to a code |
| isolved | Payroll is 2018 conversion data only | 36 of 231 runs completed, all "Data Conversion" in 2018 | Live evidence for structure; regular payroll covered by fixtures |
| UKG | No company resource | `GET /v2/companies/{cid}` answers 404 | Company built from the sign-in id; name `not_provided` |
| UKG | A second EIN used by payrolls is missing from the EIN lookup | 24 payrolls and 13 employees name it | Built from the records, `reference_only` |
| UKG | Amount keys omitted on some lines | 6 check payments, 19 employee tax sides | Null, never zero; net pay derived only when every payment amount is present |
| UKG | Every payroll is OPEN | 67 of 67 payrolls | Status kept on every run and paycheck |
| UKG | A create requires a start date, although the reference marks only username, first and last name as required | The first live create answered HTTP 400 "'Date started' is required"; nothing was created | The create sends the start date, from an input or the source's own start date, never the hire date |
| UKG | A create also requires a national id, also not marked required | The second create answered HTTP 400 "'Social security' is required" | The SSN when held, else UKG's own "no id needed" type; an SSN is never invented. The third create succeeded (HTTP 201) |
| UKG | An update must be a JSON Patch, and `replace` fails on a field the employee does not have yet | HTTP 415 for `application/json`; then HTTP 400 'Missing field "suffix"', with nothing applied | Updates are sent as `application/json-patch+json` with `add` and `remove` operations; the next update succeeded (HTTP 204) |

## 4. Gaps by provider

What a provider does not expose to the demo account, or does not have at all. Each gap shows in
the output as a null with its reason, not as a missing key.

**PrismHR**

- SSN, bank account numbers and client EINs: masked by the provider (`hidden_by_source`).
- Garnishment details: the route answers 403; garnishments are known from the deduction codes
  and a presence flag only.
- Direct deposits: no id, no priority and no effective dates in the source.
- PTO: carry-over, accrued and used hours are sent, but no balance (none is derived).

**isolved**

- Employee deduction setups: the documented routes answer 401 (candidate source used instead).
- Employee payroll, payroll deduction, legal tax and work location routes: 401 (alternatives
  used where they exist).
- Benefits, contacts and several other employee routes answered 404 for every employee sampled;
  their live meaning is unknown, and they are classified from the documented schema.
- Direct deposits: no effective dates; payroll payments show no direct deposit amounts (2018
  conversion data).
- PTO amounts have no documented unit and stay raw (`unit_unverified`).

**UKG Ready**

- No company resource: company name and address are `not_provided`.
- No deduction setup source (the documented route answers 404).
- No structured tax withholding fields in the documented schema.
- No work location source (cost centers carry no location code).
- Gross pay is not stated, so `gross_pay` stays null; net pay is derived only when every
  payment amount is present.
- PTO balance route 1 answers 403; route 2 returned no balances for the employees sampled.

The full item-by-item table per provider is in [docs/COVERAGE.md](docs/COVERAGE.md).

## 5. Known limitations

- **Inferred classifications.** Tax types, isolved employer contributions and several status
  and type labels are read from exact provider labels; labels outside the tables stay
  `unknown`. isolved and UKG employment types use a prefix rule instead: any label that
  starts with "Full Time", "FT", "Part Time" or "PT" is read, including a new one no table lists,
  so a client label that uses those letters for something else would be misread. Every inferred
  value is flagged on its record with the code and label it came from.
- **Live coverage is limited by the demo data.** isolved payroll is 2018 conversion data only;
  UKG payroll is all OPEN; some documented routes returned nothing for the employees sampled.
  The synthetic fixtures cover the documented shapes the live data does not show.
- **Unstable PrismHR deposit ids.** They rest on list order; if PrismHR reorders the list, the
  ids change. Each is flagged `unstable_id`.
- **Cross-client managers.** PrismHR's manager field carries no client, so a manager listed in
  another client is reported as a link problem rather than linked (2 employees in the demo
  tenant).
- **A deduction line does not link to its deduction setup.** Paycheck deduction lines link to
  the company's deduction code; there is no link to the employee's setup (isolved garnishment
  lines, for example, name the garnishment but cannot reference it).
- **Codes are classified by today's code tables.** Older paychecks use the current meaning of
  their codes.
- **Raw values are not kept in the output.** Records point to the route and location each
  value came from; the raw value itself is only in the input. For live runs, the raw responses
  are kept only with `--save-bundle`.
- **Writes reach only UKG Ready.** isolved and PrismHR writes are dry runs (the full request is
  built and shown, never sent), and only employees are written.
- **The UI can be finicky.** It was built late and under time pressure: some layouts on narrow
  windows and some edge cases in the write form are rough. The API and the command line under it
  are the tested path, and every rule the UI shows (masking, refusals, what a send does) is
  enforced on the server, not in the browser.
- **The app is local and single-user.** It has no login. Full values are stored in the local,
  Git-ignored store so the explicit opt-in can show them; responses are masked by default.
- **The test employee stays in the UKG demo tenant.** The write path has no delete (only create
  and update are in scope), so the synthetic employee created to check it remains there.
