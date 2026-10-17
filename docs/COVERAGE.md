# Coverage

Where each item the brief lists for the four data types lives in the canonical model, and what
each provider supplies for it. Model: `docs/CANONICAL_MODEL.md`. Decision ids (D-xxx) refer to
the assumptions and decisions file.

## What this document proves, and what it does not

- **It proves** that every item the brief lists (README "Data to normalize") has a named
  canonical home or a documented gap per provider, and that every field a provider requires to
  create an employee has a home or a documented rule (section 6).
- **It does not prove** source-field completeness. Whether every field returned by the selected
  routes is mapped, kept as an extension or excluded with a reason is the Phase 3 exit check
  (mapping tables). If Phase 3 finds a source field with no canonical home, the home is added
  as a recorded model amendment before Phase 3 closes (D-059).
- A test (`tests/test_canonical_schemas.py`) reads every "Canonical home" column below and
  checks that each named path exists in the models. It checks names, not mappings.

## Legend and evidence

| Mark | Meaning |
| --- | --- |
| L | Seen in live demo data; the sample size is given |
| S | Spec only: documented, not seen live; covered by the synthetic fixtures (`fixtures/<provider>/bundle.json`, D-082) |
| P | Partial: some of the item is available, or only from a weaker source |
| G | Gap: not available, with the reason |
| M | Masked by the provider: the field is null with `hidden_by_source` |
| U | Unknown: the route is documented, but the live result does not settle it |

Live evidence comes from the Phase 1 discovery (saved samples, Git-excluded) and format-only
checks. Sample sizes are what was examined, not tenant totals. Absence in a sample is not
treated as absence in the tenant.

## 1. Employee data

| Brief item | Canonical home | PrismHR | isolved | UKG Ready |
| --- | --- | --- | --- | --- |
| Name | `Employee.name` | L (6 employees sampled) | L (all 138) | L (all 103) |
| Demographics | `Employee.demographics` | L; birth date returned in full (D-024) | L; `gender` present in only some records; disability flags from the list (`disabilityStatus`, 404 for all 3 queried, excluded as the same facts, D-079) | L; citizenship, ethnicity, gender as enums; birth date in full (10 of 10) |
| National id | `Employee.national_ids[]` | M: SSN `***-**-****` (all 369 of client 102, D-024) | P: only `/employeesWithSSN` returns it; first pages held 70 records in total (50 of 118 for legal 5797, 20 of 20 for 5806), so a full fetch pages (D-013, D-057) | L: full value (8 of 10; 2 `NO_ID_NEEDED`) |
| Contact | `Employee.work_contact`, `Employee.personal_contact` | L (home, W-2 and alternate addresses) | L (`nameAddress`) | L (`address`) |
| Employment status and history | `Employee.employment.status`, `Employee.employment_history[]` | L: client status code and class, status history | L: Active 135, Terminated 2, Inactive 1; history keeps employment ids (D-039) | L: Active 50, Terminated 53 |
| Employment dates | `Employee.employment.hire_date`, `Employee.employment.original_hire_date`, `Employee.employment.rehire_date`, `Employee.employment.termination_date`, `Employee.employment.seniority_date` | L: last hire, original hire, seniority | L: hire; rehire on 3; termination | L: hired 103, terminated 53, re-hired 13 |
| Worker and employment type | `Employee.employment.worker_type`, `Employee.employment.employment_type` | L: type code and class; `employee1099` documented | L: FT/PT, read from 'Full Time'/'Part Time' (inferred, D-099); `payType` 1099 on 3 (inferred, D-041) | L: employee types lookup (5), read when the name says FT or PT (inferred, D-099); `tax-info` 1099 flag (inferred, D-041) |
| Job | `Employee.job.job`, `Employee.job_history[]` | L: job code; history from `getHistory` (2 position changes in 2 employees; department, division and location changes documented, not seen) | L: `jobs` (data for 4 of 6, 1 entry each) | L: `default_job` id resolved through `lookup/jobs` (51); G for history (only `job_last_changed`) |
| Organization and manager | `Employee.job.org_units[]`, `Employee.job.work_location_id`, `Employee.job.manager_employee_id`, `Employee.job.supervisor_employee_id` | L: division, department, location codes | L: organizations; 67 manager and supervisor links (D-045) | L: cost centers; no manager link observed |
| Current compensation | `Employee.compensation` | L | L: `payRates`, `salaries` | L: `pay-info`, `compensation/total` |
| Compensation history | `Employee.compensation_history[]` | L: 64 rows for one employee, 2 with sentinel dates (D-025) | L: salary history | L: `compensation/history` |
| Pay frequency | `Employee.compensation.pay_frequency` | L: pay group joined to the schedule's documented letter (6 of 6, D-041 amendment 2) | L, provider label, inferred (D-041, D-081) | L, documented enum (1 of 3 employees has a pay period profile) |
| Tax withholding | `Employee.tax_withholding` | L: compensation tax settings | L: federal, state and city settings | G: the documented `tax-info` schema has no structured withholding fields (only W2, 1099 and DRAW flags, FEIN, DBA name, pension box type, third-party sick). W-4 forms exist as documents, excluded as forms (discovery route inventory) |
| PTO balances | `Employee.pto_balances[]` | P: `getPaidTimeOff` (4 registers in 2 employees): carry-over, accrued and used hours, accrued-through and year-end dates; no balance is sent and none is derived | P: `accruals` (1 record in 3 employees, all zero): plan id and name typed; the amounts have no documented unit and stay raw with `unit_unverified` (D-077); `accruals/list` excluded (D-079) | U: `employees/{aid}/accrual/1/balances` and `/2/balances` are documented, and their pages state that hour values are milliseconds. Probed in Phase 3 (3 employees): `/1` returned 403 for 3 of 3; `/2` returned an empty list for 1, and for 2 the error "Employee does not have an Accruals profile configured" (D-027 amendment 2). Classified from the documented schemas: `/1` time off items give balance, accrued, taken and carry-over; `/2` accrual categories give balance and previous carry-over (current-period amounts stay in extensions) |
| Related people | `Employee.related_people[]` | L: `getDependents`, 2 dependents for 1 of the 2 queried employees; emergency contacts in `getEmployee`, 3 in 6 employees (one free-text name, kept whole in `full_name`) | U: `contacts` 404 for all 6 queried (D-011); classified from the documented schema | L: 2 contacts for 1 of 3 |
| Qualifications | `Employee.qualifications[]` | S: `skillsAndEducation` skill and school lists, empty for 6 of 6 sampled | S: skills, education, certifications and training return `[]` (3 employees each) | L: 29 skills (ids only; names not looked up, D-077) and 4 trainings for 1 of 3 |
| Work authorization | `Employee.work_authorization` | P: non-resident alien flag (`nonResAlien`) and I-9 on file (`formI9Filed`, filled on 6 of 6, D-079; on file is not completed); the renewal date is kept in `sensitive_provider_extensions` (not a document expiration) | L: `i9/status` (3 of 3) | P: citizenship enum only; no I-9 fields seen |
| Benefit enrollment (supports deduction setup) | `BenefitEnrollment` | L: 53 plans in 6 files | U: `benefits` is documented ("List Employee Benefits") but returned 404 for all 6 queried (D-011); classified from the spec model, benefit type and coverage level labels unknown (D-081) | L: 11 enrollments for 1 of 3, no amounts |
| All other employee fields | `Employee.provider_extensions`, `Employee.sensitive_provider_extensions` | Classified in `docs/mappings/prismhr.md`; HSA transfer accounts in the sensitive extension (D-081) | Classified in `docs/mappings/isolved.md` | Classified in `docs/mappings/ukg-ready.md` |

## 2. Direct deposits

| Brief item | Canonical home | PrismHR | isolved | UKG Ready |
| --- | --- | --- | --- | --- |
| Account type | `DirectDeposit.account_type` | L: `C` means "checking account or pay card", kept ambiguous (1 account among 6 employees). HSA transfer accounts and voluntary ACH deduction accounts are not deposits (D-081) | L: Checking 9, Savings 1; from the `directdeposits` route (the list's block was never sent, D-081) | L: CHECKING 16, SAVINGS 2 |
| Allocation | `DirectDeposit.allocation_type`, `DirectDeposit.percent_basis` | L: method B (remainder) seen once; F, P, FS, PN spec only | L: amount, percent, active sequence 0 (D-015) | L: FULL, FLAT_AMOUNT, NET_PAY; GROSS_EARNING and percent of remainder spec only |
| Amount or percentage | `DirectDeposit.amount`, `DirectDeposit.percent` | S: no live percentage deposit; 0 to 100 assumed, provisional (D-032) | L: 0 to 100 (spec maximum and live split) | L: 15.0 in a 3-way split |
| Priority | `DirectDeposit.sequence` | G: no id or sequence; the id is the list position, with `unstable_id` (D-046) | L: `sequenceNumber`; null on 2 inactive accounts | L: 1..n |
| Status | `DirectDeposit.status`, `DirectDeposit.prenote_status` | L: status D, `achStatus` A | L: Active 8, Inactive 2 | L: active flag and pre-note status |
| Effective dates | `DirectDeposit.effective_from`, `DirectDeposit.effective_to` | G: no date field in the `AchVoucher` spec | G: no date field in `EmployeeDirectDepositModel` | L: `active_from`, `active_to` (2099 sentinel on 16 of 18) |
| Bank numbers | `DirectDeposit.routing_number`, `DirectDeposit.account_number`, `DirectDeposit.account_last4` | M: account `****`; routing returned in full | L: full | L: full (some 1 to 4 characters, demo data) |
| Deposit frequency | `DirectDeposit.frequency` | G: no frequency field seen (the deposit applies per paycheck kind, next row) | L: "Every Pay" | L: EVERY_PAY (18) |
| Paycheck kinds the deposit applies to | `DirectDeposit.applies_to_paycheck_kinds` | L: `voucherType` RVS | G: no such field | G: no such field |

Volumes: PrismHR 1 of 6 sampled employees has a deposit; isolved 10 accounts for 8 employees
queried; UKG 18 accounts for all 103 employees (deprecated route, D-030 and section 5 of the
model).

## 3. Deductions

| Brief item | Canonical home | PrismHR | isolved | UKG Ready |
| --- | --- | --- | --- | --- |
| Employee setup | `DeductionSetup`, `DeductionSetup.source_basis` | L: documented route (`getDeductions`, 6 of 6 non-empty) | P: candidate source, 7 records (D-017); joined to the per-employee entries for type and parameters (D-081) | G: setup route 404 for 3 of 3 (D-030) |
| Codes and types | `Company.deduction_codes[]` | L: 43 codes (client 102); types documented, VG inferred (D-026) | L: client pay item catalog; category inferred from `systemBenefitType` labels (D-081) for 17 of 19 deduction items (D-066) | L: 43 codes without a type (D-031) |
| Amounts and percentages | `DeductionSetup.amount`, `DeductionSetup.percent` | L; stored amount is the per-pay deduction, billing amounts (period unknown) kept raw (D-084) | P: `Amount` typed; `Percent`, `Amount2`, `Rate` kept raw (unit rule) | G |
| Rules and dates | `DeductionSetup.period_numbers`, `DeductionSetup.per_period_limit`, `DeductionSetup.maximum`, `DeductionSetup.goal_amount`, `DeductionSetup.start_date`, `DeductionSetup.stop_date` | L: period, limit, basis | P: start and stop dates on some | G |
| Garnishments | `DeductionSetup.garnishment` | P: presence only; detail route 403 (2 of 2 flags negative) | L: 1 of 7 queried has one | P: only as a pay statement deduction line (1) |
| Loans | `DeductionSetup.loan` | L: 3 retirement loans | P: a "401K Loan" assignment | P: "401K Loan 1" pay statement lines only |
| Deductions recorded in payroll | `Paycheck.deductions[]` | L: 192 vouchers | L: 55 lines in 25 check details | L: 45 lines in 20 statement details |

## 4. Payroll data

| Brief item | Canonical home | PrismHR | isolved | UKG Ready |
| --- | --- | --- | --- | --- |
| Payroll runs | `PayrollRun`, `PayrollRun.run_type`, `PayrollRun.status` | L: 1,813 batches in 3 clients | P: 231 runs for pay group 7612, 36 completed, all 2018 data conversion; 2 pay groups 404 (D-014) | L: 67 payrolls, all OPEN (D-030) |
| Pay periods | `PayrollRun.pay_periods[]`, `Paycheck.period_start`, `Paycheck.period_end` | L: per pay group in each batch | L | L |
| Paychecks | `Paycheck` | L: 192 distinct vouchers | P: 430 listed checks, 25 details, conversion data only | L: 108 statements, 20 details, all OPEN |
| Earnings | `Paycheck.earnings[]`, `Company.earning_codes[]` | L: classes documented (D-023, D-054) | L: GTL and Mileage classes inferred (D-016) | L: classes provisional (D-031) |
| Hours | `Paycheck.earnings[].hours`, `Paycheck.earnings[].units` | L: hours only for H pay codes (D-051) | L: `checkHours` | L: milliseconds converted (D-028) |
| Gross pay | `Paycheck.gross_pay`, `Paycheck.gross_wages`, `Paycheck.total_earnings` | L: `earnAmount`, `totalEarnings` | L: `grossPay`, `grossWages` | G: not stated, not derived (D-052) |
| Net pay | `Paycheck.net_pay` | L | L | P: derived only when every cash payment amount is present (14 of 20, D-052) |
| Taxes | `Paycheck.taxes[]` | L; type from exact labels, inferred (D-056). Label table: federal, FICA, FUTA, CA and IL labels; other labels unknown (D-081) | L: 232 lines. Label table: federal, FICA, FUTA, CA and UT labels; others unknown (D-081) | L; employee and employer sides split. Label table: federal, FICA, FUTA, additional Medicare and the Wisconsin SUTA name; state names such as 'Wisconsin' unknown (D-081) |
| Deductions | `Paycheck.deductions[]` | L | L | L |
| Benefit contributions | `Paycheck.employer_contributions[]`, `Paycheck.benefit_lines[]`, `Paycheck.retirement` | L | P: from memo earnings, inferred (D-055) | L: `er_amount` on 25 deduction lines |
| Payments | `Paycheck.payments[]` | L: direct deposits on 24 of 104 regular vouchers | S: `directDepositAmount` 0 on all 430 checks | L: 5 direct deposit lines |
| Reversals and adjustments | `Paycheck.reverses_paycheck_id`, `Paycheck.kind` | L: 2 reversal and 2 adjustment vouchers | L: every check is type "Adjustment" | S |

## 5. Company and links

| Item | Canonical home | PrismHR | isolved | UKG Ready |
| --- | --- | --- | --- | --- |
| Company identity | `Company.legal_name`, `Company.address` | L: client master | L: legal entity | G: no company resource; name and address `not_provided` (D-029) |
| Tax entity (EIN) | `Company.tax_entities[]` | M (23 of 25 clients; 2 empty) | L | L |
| Work locations | `Company.work_locations[]` | L: client `locationCode` (41, client 102) | L: from the legal record (6 for legal 5797, 1 for 5806); the dedicated `/workLocations` route is 401 (D-012) | G: no work location source. The documented `config/cost-centers` route has a `location_code`, but it was empty on 71 of 71 cost centers (tree indexes 0 and 2; index 1 "not used"); recruitment location lookups do not describe employee work locations (D-065) |
| Pay groups | `Company.pay_groups[]` | L: client `payGroups` (2, client 102); frequency from the payroll schedule's documented letter (D-068) | L: from the legal record (2 and 1); frequency inferred (D-067) | L: the 12 pay period profiles (D-065); frequency from the documented `period_type` |
| Deduction codes | `Company.deduction_codes[]` | L: 43 (client 102) | L: client pay item catalog, 19 Deduction items (D-066) | L: `lookup/deduction-codes` (43) |
| Earning codes | `Company.earning_codes[]` | L: client `payCode` (14, client 102) | L: client pay item catalog, 19 Earning and 18 Memo Calc items (D-066) | L: `lookup/earning-codes` (52) |
| Links between records | `Employee.company_id`, `Employee.tax_entity_id`, `DirectDeposit.employee_id`, `DeductionSetup.employee_id`, `BenefitEnrollment.employee_id`, `Paycheck.employee_id`, `Paycheck.payroll_run_id` | Canonical ids, checked across records by `find_link_problems` (D-045) | same | same |

## 6. Write readiness (create employee)

Full table and rules: `docs/CANONICAL_MODEL.md` section 4 (D-043). Every required create field
has a typed home or is a destination input with a documented rule:

| Required field | Canonical home | Rule |
| --- | --- | --- |
| First and last name | `Employee.name.first`, `Employee.name.last` | typed |
| National id | `Employee.national_ids[].type`, `Employee.national_ids[].value` | never sent when hidden or not provided (D-020) |
| Hire dates | `Employee.employment.original_hire_date`, `Employee.employment.hire_date` | typed |
| Employment status and category | `Employee.employment.status`, `Employee.employment.employment_type` | destination code from a configured mapping |
| Job | `Employee.job.job.code` | destination code from a configured mapping |
| Work location | `Employee.job.work_location_id` | resolved to the destination's location code |
| Pay group | `Employee.compensation.pay_group_id` | resolved to the destination's code |
| Pay | `Employee.compensation.standard_hours`, `Employee.compensation.pay_type`, `Employee.compensation.pay_frequency` | isolved `payFrequency` integer through a configured table (D-018) |
| Legal employer | `Employee.company_id`, `Employee.tax_entity_id`, `Company.company_code` | typed |
| PrismHR `peoStartDate`, UKG `username` | `Employee.provider_extensions` | from the same-provider source, a configured rule or an explicit write input |
