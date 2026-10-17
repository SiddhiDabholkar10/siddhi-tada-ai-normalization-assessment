# UKG Ready mapping

Generated from `src/normalization/mappings/data/ukg-ready/` by `python -m normalization export-mappings`; do not edit by hand. Format and rules: `docs/mappings/README.md`.

Documented GET routes: 269. Selected: 31. Excluded individually: 27. Excluded by family: 211.

## Selected routes

| Route | Entities | Documented fields | Classified | Note |
| --- | --- | --- | --- | --- |
| `/v2/companies/{cid}/lookup/eins` | company | 5 | yes | Tax entities; returned only the Primary EIN, so payroll EIN references are added (D-029). |
| `/v2/companies/{cid}/lookup/deduction-codes` | company | 3 | yes | 43 codes without a type (D-031). |
| `/v2/companies/{cid}/lookup/earning-codes` | company | 4 | yes | 52 codes without a type (D-031). |
| `/v2/companies/{cid}/lookup/jobs` | employee | 5 | yes | Resolves pay-info default_job ids (51 jobs). |
| `/v2/companies/{cid}/lookup/employee-types` | employee | 2 | yes | Resolves pay-info employee_type ids (5 types). |
| `/v2/companies/{cid}/lookup/pay-types` | employee | 3 | yes | Resolves pay-info pay_type ids. |
| `/v2/companies/{cid}/lookup/pay-period-profiles` | company | 16 | yes | Company pay groups (D-065): one per pay period profile, frequency from the documented period_type (D-041). |
| `/v2/companies/{cid}/config/cost-centers` | employee | 7 | yes | Requires tree_index. location_code empty on 71 of 71 cost centers (tree 0: 54, tree 2: 17; tree 1: 400 code 19515 'Cost Center not used'); used to label employee cost center references (step 3); no work location source (D-065). |
| `/v2/companies/{cid}/employees` | employee | 20 | yes | 103 accounts; one account per EIN (D-039). |
| `/v2/companies/{cid}/employees/{aid}` | employee, company | 99 | yes | Detail with ein, dates, national ids (returned in full). |
| `/v2/companies/{cid}/employees/{aid}/demographics` | employee | 13 | yes |  |
| `/v2/companies/{cid}/employees/{aid}/pay-info` | employee | 27 | yes | Ids resolved through lookups; standard_work_day in milliseconds (D-028). |
| `/v2/companies/{cid}/employees/{aid}/profiles` | employee | 87 | yes | Pay period profile link (pay frequency, D-041); other profiles to extensions. |
| `/v2/companies/{cid}/employees/{aid}/compensation/history` | employee | 11 | yes |  |
| `/v2/companies/{cid}/employees/{aid}/compensation/total` | employee | 4 | yes |  |
| `/v2/companies/{cid}/employees/{aid}/compensation/additional` | employee | 10 | yes | Empty for 3 of 3 sampled. |
| `/v2/companies/{cid}/employees/{aid}/contacts` | employee | 38 | yes | Related people: 2 contacts for 1 of 3 sampled employees. |
| `/v2/companies/{cid}/employees/{aid}/tax-info` | employee | 7 | yes | W2, 1099 and DRAW flags; no structured withholding (COVERAGE section 1). |
| `/v2/companies/{cid}/employees/{aid}/skills` | employee | 4 | yes | 29 skills for 1 of 3 sampled employees; ids only (lookup/skills not called, D-077). |
| `/v2/companies/{cid}/employees/{aid}/training/certifications` | employee | 6 | yes | 4 training entries for 1 of 3 sampled employees. |
| `/v2/companies/{cid}/employees/{aid}/badges` | employee | 6 | yes |  |
| `/v2/companies/{cid}/employees/{aid}/hr-custom-fields` | employee | 2 | yes | Empty for 3 of 3 sampled. |
| `/v2/companies/{cid}/employees/{aid}/accrual/1/balances` | employee | 18 | yes | PTO balances; hour values documented as milliseconds (D-027 amendment 2). 403 for 3 of 3 sampled employees; classified from the documented schema. |
| `/v2/companies/{cid}/employees/{aid}/accrual/2/balances` | employee | 29 | yes | PTO balances; hour values documented as milliseconds (D-027 amendment 2). Empty list for 1 of 3 sampled; 400 code 17605 (no accruals profile) for 2. Classified from the documented schema. |
| `/v2/companies/{cid}/employees/{aid}/direct-deposits` | direct_deposit | 54 | yes | Deprecated, the only deposit list route (D-030). |
| `/v2/companies/{cid}/employees/{aid}/benefits` | benefit_enrollment | 8 | yes | Enrollments without amounts (D-049). |
| `/v2/companies/{cid}/payrolls` | payroll, company | 19 | yes | 67 payrolls, all OPEN (D-030). |
| `/v2/companies/{cid}/payrolls/{id}` | payroll | 13 | yes | Payroll detail with EIN reference (D-029). |
| `/v2/companies/{cid}/payrolls/{id}/batches` | payroll | 7 | yes |  |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements` | payroll | 9 | yes | Statement list per payroll (108 statements in 20 payrolls). |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | payroll | 72 | yes | Statement detail with lines (20 examined). |

## Routes excluded individually

| Route | Reason |
| --- | --- |
| `/v2/companies/{cid}/lookup/pay-grades` | Pay grade labels (38 grades); the model has no pay grade field, and pay-info sends the grade with its parent code and name, kept in provider_extensions (as PrismHR getPayGrades). |
| `/v2/companies/{cid}/lookup/pay-cal-profiles` | Pay calculation profiles, not pay groups: their ids match the employee profile link pay_calculations[].id (3 of 3 sampled), kept as an employee extension (section 3.4, D-065). |
| `/v2/companies/{cid}/lookup/payroll-types` | Payroll type labels; payrolls carry type id and display name inline (67 of 67). |
| `/v2/companies/{cid}/lookup/pay-statement-types` | Pay statement type labels; statements carry type id and display name inline (20 of 20 details). |
| `/v2/companies/{cid}/lookup/payroll-batch-types` | Batch type labels; batches carry type id and display name inline (4 of 4). |
| `/v2/companies/{cid}/accounts` | 403 for the demo account; login accounts, not employee data. |
| `/v2/companies/{cid}/ids` | Id translation helper; 400 without its required parameters in discovery. Not employee data. |
| `/v2/companies/{cid}/benefits` | Company-wide enrollment list; needs coverage dates (error 21079 without them in discovery). Enrollments are read per employee (D-081). |
| `/v2/companies/{cid}/direct-deposits/{id}` | One deposit by id (called once); the per-employee list returns the deposits. |
| `/v2/companies/{cid}/pay-periods` | Pay period calendar (56 periods for 2025); payrolls and statements carry their own period dates. |
| `/v2/companies/{cid}/lookup/pay-categories` | Timesheet pay category lookup: requires a timesheet date, owner and record type (TIME, EXTRA_PAY, ADJUSTMENT) and returns id, name, code and description (reference page; 400 without the parameters in discovery). It documents no earning classification, so UKG codes stay unclassified (D-031). |
| `/v2/companies/{cid}/employees/{aid}/deductions` | Scheduled deductions route labelled 'dev': 404 'Unresolvable URL' for 3 of 3 (D-030). |
| `/v2/companies/{cid}/employees/{aid}/managed-cost-centers` | 403 'Managed Cost Centers are not enabled' for 3 of 3; cost centers a manager manages, not the employee's own. |
| `/v2/companies/{cid}/compensation/history` | Company-wide form of the employee compensation history route; not called. Compensation history is read per employee (selected and classified in step 3a); the company-wide form could only batch those calls in a live run, which changes no mapping. |
| `/v2/companies/{cid}/compensation/total` | Company-wide form of the employee compensation total route; not called (see compensation/history). |
| `/v2/companies/{cid}/compensation/additional` | Company-wide form of the employee additional compensation route; not called (see compensation/history). |
| `/v2/companies/{cid}/employees/{aid}/currency` | Employee currency; not called. Compensation records carry a currency (D-036). |
| `/v2/companies/{cid}/external-pay-statements/{pst_id}` | Pay statements produced outside UKG and imported (schema: file name, pay date); not called. Payroll comes from UKG payrolls (D-081). |
| `/v2/companies/{cid}/lookup/tax-codes` | Tax codes with id, code, name, abbrev and external id; no tax type in the schema (checked for D-056). Not called: statement tax lines carry the same code and name inline, which the tax label table reads (D-081). |
| `/v2/companies/{cid}/lookup/profile-specific/eins` | EINs allowed by the API user's security profile (reference page), with the same fields as lookup/eins; not called. Tax entities come from lookup/eins plus the EINs payrolls reference, which covers every EIN in use (D-029). |
| `/v2/companies/{cid}/lookup/worker-types` | Worker types; not called. No selected employee route sends a worker type id to label (checked in step 3b-2): worker type comes from the tax-info flags (D-041). |
| `/v2/companies/{cid}/lookup/termination-reason` | Termination reasons; not called. No documented field of the selected employee routes holds a termination reason (checked in step 3b-2), so there is nothing to label and termination_reason is not_provided for UKG. |
| `/v2/companies/{cid}/lookup/benefit-plans` | Benefit plan list; not called. Enrollments carry plan id and name (D-081). |
| `/v2/companies/{cid}/benefits/benefit-plans` | Company benefit plan setup; not called. Enrollments carry plan id and name (D-081). |
| `/v2/companies/{cid}/employees/{aid}/deductions/{id}` | One scheduled deduction on the 'dev' route whose list returned 404 for 3 of 3 (D-030). |
| `/v2/companies/{cid}/employees/{aid}/managed-cost-centers/{mccid}` | One managed cost center; the list returned 403 (not enabled) for 3 of 3. |
| `/v2/companies/{cid}/lookup/benefit/types` | Benefit types; not called. Enrollment benefit_type stays not_provided without a call (scope rule, D-077, D-081). |

## Route families excluded

| Family | Patterns | Reason |
| --- | --- | --- |
| Authentication, accounts and security | `/v2/companies/{cid}/oauth2/**`<br>`/v2/companies/{cid}/oauth/**`<br>`/v2/companies/{cid}/session/**`<br>`/v2/companies/{cid}/employees/{aid}/password-policy`<br>`/v2/companies/{cid}/employees/{aid}/credentials`<br>`/v2/companies/{cid}/service-accounts**`<br>`/v2/companies/{cid}/access-profiles/{aid}`<br>`/v2/companies/{cid}/accounts/{aid}`<br>`/v2/companies/{cid}/config/security/**`<br>`/v2/companies/{cid}/ids/*/**`<br>`/v2/companies/{cid}/employees/{aid}/ids`<br>`/v2/companies/{cid}/lookup/credential-types`<br>`/v2/companies/{cid}/lookup/first-screens`<br>`/v2/companies/{cid}/lookup/groups`<br>`/v2/companies/{cid}/lookup/locales` | Sign-in, OAuth, sessions, service accounts, credentials, security groups and id translation: platform functions, not employee or payroll records. |
| Time, attendance and leave | `/v2/companies/{cid}/time-entries**`<br>`/v2/companies/{cid}/employees/{aid}/time-entries`<br>`/v2/companies/{cid}/employees/{aid}/timesheets`<br>`/v2/companies/{cid}/employees/{aid}/punches/**`<br>`/v2/companies/{cid}/attendance`<br>`/v2/companies/{cid}/employees/{aid}/attendance`<br>`/v2/companies/{cid}/overtime/**`<br>`/v2/companies/{cid}/employees/{aid}/overtime/**`<br>`/v2/companies/{cid}/employees/{aid}/holidays`<br>`/v2/companies/{cid}/employees/{aid}/timeoff-calendar-sync`<br>`/v2/companies/{cid}/schedules**`<br>`/v2/companies/{cid}/employee/**`<br>`/v2/companies/{cid}/loa/**`<br>`/v2/companies/{cid}/employees/{aid}/loa/**`<br>`/v2/companies/{cid}/counter-adjustments/**`<br>`/v2/companies/{cid}/employees/{aid}/counter-adjustments`<br>`/v2/companies/{cid}/pay-periods/*/**`<br>`/v2/companies/{cid}/lookup/loa/**`<br>`/v2/companies/{cid}/lookup/manual-counters`<br>`/v2/companies/{cid}/lookup/overtime/**`<br>`/v2/companies/{cid}/lookup/shift-premiums`<br>`/v2/companies/{cid}/lookup/reason-codes`<br>`/v2/companies/{cid}/lookup/timezones` | Time entries, timesheets, punches, schedules, overtime, leave, time-off requests and pay period exports: not one of the four data types. PTO balances come from the accrual balance routes (D-027). |
| Recruiting, learning, assets and expenses | `/v2/companies/{cid}/applicants**`<br>`/v2/companies/{cid}/job-applications**`<br>`/v2/companies/{cid}/recruitment/**`<br>`/v2/companies/{cid}/lookup/hiring-stages`<br>`/v2/companies/{cid}/lookup/interview-*`<br>`/v2/companies/{cid}/lookup/job-application-status`<br>`/v2/companies/{cid}/lookup/job-req/**`<br>`/v2/companies/{cid}/lookup/questionnaire`<br>`/v2/companies/{cid}/lookup/referrals`<br>`/v2/companies/{cid}/asset-assignments**`<br>`/v2/companies/{cid}/inventory-profiles**`<br>`/v2/companies/{cid}/lookup/asset*`<br>`/v2/companies/{cid}/vehicle/**`<br>`/v2/companies/{cid}/lookup/vehicles`<br>`/v2/companies/{cid}/lookup/vendors`<br>`/v2/companies/{cid}/expense-tracking/**`<br>`/v2/companies/{cid}/projects/**` | Applicants and recruiting, assets, vehicles, expenses and projects: not one of the four data types. |
| Notifications, announcements and dashboards | `/v2/companies/{cid}/config/announcements**`<br>`/v2/companies/{cid}/employees/{aid}/announcements`<br>`/v2/companies/{cid}/employees/{aid}/notifications/**`<br>`/v2/companies/{cid}/notifications/**`<br>`/v2/companies/{cid}/dashboard/**`<br>`/v2/companies/{cid}/hcm/**`<br>`/v2/companies/{cid}/navigation`<br>`/v2/companies/{cid}/notes`<br>`/v2/companies/{cid}/calendar/**`<br>`/v2/companies/{cid}/employees/{aid}/manager-replacements`<br>`/v2/companies/{cid}/employees/{aid}/vca-report-dialog-settings`<br>`/v2/companies/{cid}/lookup/notification*/**`<br>`/v2/companies/{cid}/lookup/notification-tags`<br>`/v2/companies/{cid}/hr-actions/**` | Announcements, notifications, dashboards, navigation, notes, calendars and HR action audit requests: platform and workflow, not employee or payroll records. |
| Data exports and integrations | `/v2/companies/{cid}/data-exports**`<br>`/v2/companies/{cid}/datadelivery/**`<br>`/v2/companies/{cid}/exports/**`<br>`/v2/companies/{cid}/system-jobs/**`<br>`/v2/companies/{cid}/integrations/**`<br>`/v2/companies/{cid}/lookup/data-export-types` | Export jobs, data delivery metadata and integration events: transport mechanisms, not records. |
| Forms and tax filings | `/v2/companies/{cid}/employees/{aid}/forms/**`<br>`/v2/companies/{cid}/forms/**`<br>`/v2/companies/{cid}/taxes/**`<br>`/v2/companies/{cid}/lookup/document-types` | Employee forms (pay forms are deprecated and employee-only) and company tax filing years and quarters: documents and filings, not structured employee or pay records. |
| Cost center, position and rate configuration | `/v2/companies/{cid}/config/cost-centers/*/**`<br>`/v2/companies/{cid}/config/cost-center-jobs**`<br>`/v2/companies/{cid}/position/**`<br>`/v2/companies/{cid}/primary-assignment`<br>`/v2/companies/{cid}/rates/**` | Cost center lists and single entries, cost-center jobs, position management and rate tables: configuration. The cost-center list itself is selected; employee job comes from pay-info (COVERAGE section 1). |
| Single-item, current-user and change-feed forms | `/v2/companies/{cid}/compensation/history/*/**`<br>`/v2/companies/{cid}/benefits/{id}`<br>`/v2/companies/{cid}/compensation/additional/{acid}`<br>`/v2/companies/{cid}/contacts/{id}`<br>`/v2/companies/{cid}/employees/changed`<br>`/v2/companies/{cid}/employees/info`<br>`/v2/companies/{cid}/employees/me`<br>`/v2/companies/{cid}/employees/me/currency` | One item by id, the signed-in user's own record, or a change feed over employees: the selected employee routes return these records. |
| Configuration profiles and other lookups | `/v2/companies/{cid}/lookup/profiles/**`<br>`/v2/companies/{cid}/lookup/additional-compensation-types`<br>`/v2/companies/{cid}/lookup/degrees`<br>`/v2/companies/{cid}/lookup/education-levels`<br>`/v2/companies/{cid}/lookup/eye-color`<br>`/v2/companies/{cid}/lookup/job-categories`<br>`/v2/companies/{cid}/lookup/job-change-reasons`<br>`/v2/companies/{cid}/lookup/object-lists/{type}`<br>`/v2/companies/{cid}/lookup/skills`<br>`/v2/companies/{cid}/lookup/unions`<br>`/v2/companies/{cid}/lookup/workers-comp-codes` | Configuration profiles (security, timesheet, holiday, scheduling and others; employee profile links go to extensions, section 3.4) and code lists not called in discovery. A step selects one of these when a code the employee routes send needs its label. |

## Company fields

- One company per sign-in company_id; there is no company resource (D-029), so legal_name, display_name, company_code, status, status_date, address, phone and parent are null with not_provided and the company carries a source_unavailable diagnostic.
- Tax entities come from lookup/eins plus the EINs referenced by payrolls and employees (D-029, D-094): one per EIN id. lookup/eins wins when it lists the id; an id it omits (live: the 2nd EIN, named by 24 payrolls and 13 employees, absent from lookup/eins and lookup/profile-specific/eins) is built from the payroll list's ein object, else the employee detail's ein_name, with a reference_only diagnostic. The ids themselves are the reference rows of the payroll and employee tables.
- Work locations: no source. config/cost-centers has a documented location_code, but it was empty on 71 of 71 cost centers (D-065); work_locations is null with not_provided.
- Deduction and earning codes carry no type (D-031): category, tax_treatment, calc_method, pay_class, rate_class and quantity_type are null with not_provided unless a tenant mapping is configured; is_cash, is_catch_up, w2 fields and is_active likewise.

| Route | Source field | Use | Canonical field | Transform | Evidence | Reason or note |
| --- | --- | --- | --- | --- | --- | --- |
| `/v2/companies/{cid}/lookup/eins` | `items[].id` | mapped | `Company.tax_entities[].id` | reference | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__lookup__eins.html`<br>D-042 | Canonical tax entity id from the UKG ein id, never from the EIN. |
| `/v2/companies/{cid}/lookup/eins` | `items[].ein_name` | mapped | `Company.tax_entities[].name` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__lookup__eins.html`<br>live: 'Primary EIN' (1 of 1) |  |
| `/v2/companies/{cid}/lookup/eins` | `items[].ein_tax_id` | mapped | `Company.tax_entities[].ein` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__lookup__eins.html`<br>D-029<br>D-044 | Returned in full (format-only check, D-029 correction); sensitive, masked in output by default. |
| `/v2/companies/{cid}/lookup/eins` | `items[].ein_country_id` | mapped | `Company.tax_entities[].country` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__lookup__eins.html`<br>live: 'USA' (1 of 1) |  |
| `/v2/companies/{cid}/payrolls` | `payrolls[].ein.ein_name` | mapped | `Company.tax_entities[].name` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls.html`<br>D-029<br>D-094 | Only for an EIN id lookup/eins does not list (reference_only); first payroll in list order. |
| `/v2/companies/{cid}/payrolls` | `payrolls[].ein.ein_tax_id` | mapped | `Company.tax_entities[].ein` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls.html`<br>D-029<br>D-044<br>D-094 | Only for an EIN id lookup/eins does not list; returned in full (D-029 correction), sensitive, masked by default. |
| `/v2/companies/{cid}/payrolls` | `payrolls[].ein.ein_country_id` | mapped (live only) | `Company.tax_entities[].country` | copy | live: not in the documented schema<br>D-094 | Only for an EIN id lookup/eins does not list. |
| `/v2/companies/{cid}/employees/{aid}` | `ein_name` | mapped (live only) | `Company.tax_entities[].name` | copy | live: sent beside ein.id (3 of 3 sampled details)<br>D-094 | Only for an EIN id that neither lookup/eins nor a payroll names; the detail sends no tax id or country, so those stay null. |
| `/v2/companies/{cid}/lookup/eins` | `items[].ein_currency_code` | extension | `Company.tax_entities[].provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__lookup__eins.html` | Currency setting of the EIN; tax entities hold no money (D-036). Absent in 1 of 1. |
| `/v2/companies/{cid}/lookup/deduction-codes` | `items[].id` | mapped (live only) | `Company.deduction_codes[].id` | reference | live: id on 43 of 43 codes; not in the documented schema | Canonical id from the UKG code id. Pay statement deduction lines refer to codes by this id (payroll table, live-only deduction.id). |
| `/v2/companies/{cid}/lookup/deduction-codes` | `items[].code` | mapped | `Company.deduction_codes[].code` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__lookup__deduction-codes.html` |  |
| `/v2/companies/{cid}/lookup/deduction-codes` | `items[].name` | mapped | `Company.deduction_codes[].name` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__lookup__deduction-codes.html` |  |
| `/v2/companies/{cid}/lookup/deduction-codes` | `items[].external_id` | extension | `Company.deduction_codes[].provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__lookup__deduction-codes.html` | Integration id of the code (10 of 43); no canonical meaning. |
| `/v2/companies/{cid}/lookup/earning-codes` | `items[].id` | mapped | `Company.earning_codes[].id` | reference | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__lookup__earning-codes.html` |  |
| `/v2/companies/{cid}/lookup/earning-codes` | `items[].code` | mapped | `Company.earning_codes[].code` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__lookup__earning-codes.html` |  |
| `/v2/companies/{cid}/lookup/earning-codes` | `items[].name` | mapped | `Company.earning_codes[].name` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__lookup__earning-codes.html` |  |
| `/v2/companies/{cid}/lookup/earning-codes` | `items[].external_id` | extension | `Company.earning_codes[].provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__lookup__earning-codes.html` | Integration id of the code (9 of 52); no canonical meaning. |
| `/v2/companies/{cid}/lookup/pay-period-profiles` | `items[].id` | mapped | `Company.pay_groups[].id` | reference | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__lookup__pay-period-profiles.html`<br>D-065 | One pay group per pay period profile. Employees link through profiles.pay_period[].id (step 3). |
| `/v2/companies/{cid}/lookup/pay-period-profiles` | `items[].name` | mapped | `Company.pay_groups[].name` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__lookup__pay-period-profiles.html` | Profiles have no code: pay_groups[].code is null with not_provided. |
| `/v2/companies/{cid}/lookup/pay-period-profiles` | `items[].active` | mapped | `Company.pay_groups[].is_active` | boolean | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__lookup__pay-period-profiles.html` |  |
| `/v2/companies/{cid}/lookup/pay-period-profiles` | `items[].period_type.type` | mapped | `Company.pay_groups[].pay_frequency` | code:ukg-ready.period_type | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__lookup__pay-period-profiles.html`<br>D-041 | Raw code is the type, except every_n_weeks and every_n_days, whose raw codes are 'every_n_weeks:<num_weeks>' and 'every_n_days:<num_days>'. |
| `/v2/companies/{cid}/lookup/pay-period-profiles` | `items[].period_type.params.num_weeks` | mapped | `Company.pay_groups[].pay_frequency` | derive | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__lookup__pay-period-profiles.html`<br>D-041 | Part of the raw code for every_n_weeks (see period_type.type). |
| `/v2/companies/{cid}/lookup/pay-period-profiles` | `items[].period_type.params.num_days` | mapped | `Company.pay_groups[].pay_frequency` | derive | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__lookup__pay-period-profiles.html` | Part of the raw code for every_n_days (see period_type.type). |
| `/v2/companies/{cid}/lookup/pay-period-profiles` | `items[].period_type.params.*` | extension | `Company.pay_groups[].provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__lookup__pay-period-profiles.html` | Schedule parameters (start dates, pay days, week day); the frequency is typed. |
| `/v2/companies/{cid}/lookup/pay-period-profiles` | `items[].description` | extension | `Company.pay_groups[].provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__lookup__pay-period-profiles.html` | Free-text description next to the name (7 of 12). |
| `/v2/companies/{cid}/lookup/pay-period-profiles` | `items[].effective_from` | extension | `Company.pay_groups[].provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__lookup__pay-period-profiles.html` | Validity window of the profile; PayGroup has no dates. |
| `/v2/companies/{cid}/lookup/pay-period-profiles` | `items[].effective_to` | extension | `Company.pay_groups[].provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__lookup__pay-period-profiles.html` | Validity window of the profile; PayGroup has no dates. |
| `/v2/companies/{cid}/lookup/pay-period-profiles` | `items[].is_user_profile` | extension | `Company.pay_groups[].provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__lookup__pay-period-profiles.html` | Profile setting; absent in 12 of 12. |

## Employee fields

- One Employee per UKG account (D-039). The employee list enumerates accounts; each is read with the detail route and its sub-resources. person_ref is primary_account_id; tax_entity_id comes from the detail's ein.id.
- Step 3a covers profile, employment, job and compensation; step 3b-2 contacts, skills, training certifications and the accrual balance routes (UKG sends no withholding or I-9 fields, step 3b-1).
- PTO (step 3b-2): accrual/1 items (time off) and accrual/2 items (accrual categories) each become a PtoBalance; they come from different id lists and are never merged. Hour values are milliseconds (documented, D-027 amendment 2) and convert with ms_to_hours. accrual/2 covers the current period, so only its balance and previous carry-over are typed. Skills keep only the skill id (lookup/skills is not called, D-077).
- Employee.compensation is the compensation history entry with the latest effective_from: base_rate amount, base_rate_period amount_period, hourly_rate hourly_pay, effective_date effective_from, standard hours from time and time_period (ms, documented, D-028). Taking the latest entry does not compare dates with the run date, so output does not depend on when it runs (D-036).
- Ids on pay-info are resolved through lookups (D-064): default_job through lookup/jobs, employee_type through lookup/employee-types, pay_type through lookup/pay-types.
- Cost center defaults (D-076): every default becomes an org unit of type cost_center with source_id set to its id and the type's raw_code set to its tree index, so the pair survives without the raw response. Code (payroll_code) and name come from config/cost-centers called with tree_index equal to the default's index. When that call is refused (tree 1 returned 400, code 19515, 'Cost Center not used', while 1 of 3 sampled employees has a default there) or the id is not in the tree, code and name are null with not_provided and the record gets a source_unavailable diagnostic naming the tree. The raw id is never written to code.
- Employee types are company-defined names ('PT Hourly', 'Temp', 'Consultant', 'FT Exempt', 'FT Non-Exempt'): employment_type keeps the id and name. A name that says full or part time at its start ('FT ...', 'PT ...', 'Full Time') gives full_time or part_time, inferred, with a diagnostic naming the name (D-099); any other name is unknown (unmapped, D-074).
- Pay frequency and pay group come from the pay period profile link: profiles pay_period, whose one entry (the contract allows at most one, maxItems 1) is joined to the company pay group (D-065) and its period_type frequency. Several entries break the contract: pay frequency and pay group are then not_provided with a conflicting_sources diagnostic. 1 of 3 sampled employees has the link; the others are not_provided.
- hire_date is re_hired when set, otherwise hired (the current employment); original_hire_date is hired.
- Termination date, type and reason describe the current employment: for an employee whose status is not terminated they are not_applicable, and a termination date still sent (the last termination of a rehired account) is kept in provider_extensions (CANONICAL_MODEL 3.2, D-080).
- Worker type comes from tax-info: _1099 true with W2 false is contractor, W2 true with _1099 false is employee, both inferred (D-041); any other combination (both true, both false, either absent) is unknown with an unknown_code diagnostic.

| Route | Source field | Use | Canonical field | Transform | Evidence | Reason or note |
| --- | --- | --- | --- | --- | --- | --- |
| `/v2/companies/{cid}/employees` | `employees[].id` | mapped | `Employee.source_ids` | source_id | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees.html`<br>D-039 | Enumerates accounts (103 in the demo); each is read with the detail route. |
| `/v2/companies/{cid}/employees` | `employees[]._links.*` | excluded |  |  |  | Navigation links. |
| `/v2/companies/{cid}/employees` | `employees[].*` | excluded |  |  |  | Name, ids, status and EIN name are read from the detail route; ein_name is not a key (D-039). |
| `/v2/companies/{cid}/employees` | `employees[].dates.*` | excluded |  |  |  | Dates are read from the detail route. |
| `/v2/companies/{cid}/employees/{aid}` | `id` | mapped | `Employee.source_ids` | source_id | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` |  |
| `/v2/companies/{cid}/employees/{aid}` | `employee_id` | mapped | `Employee.employee_number` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` |  |
| `/v2/companies/{cid}/employees/{aid}` | `external_id` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` | Integration id set by the customer; no canonical field. |
| `/v2/companies/{cid}/employees/{aid}` | `username` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` | Login name; needed to create a UKG employee (CANONICAL_MODEL 3.4, D-043, D-072). |
| `/v2/companies/{cid}/employees/{aid}` | `first_name` | mapped | `Employee.name.first` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` |  |
| `/v2/companies/{cid}/employees/{aid}` | `middle_name` | mapped | `Employee.name.middle` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` |  |
| `/v2/companies/{cid}/employees/{aid}` | `last_name` | mapped | `Employee.name.last` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` |  |
| `/v2/companies/{cid}/employees/{aid}` | `nickname` | mapped | `Employee.name.preferred_first` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` | UKG's only alternative first name. |
| `/v2/companies/{cid}/employees/{aid}` | `salutation` | mapped | `Employee.name.prefix` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` |  |
| `/v2/companies/{cid}/employees/{aid}` | `suffix` | mapped | `Employee.name.suffix` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` |  |
| `/v2/companies/{cid}/employees/{aid}` | `status` | mapped | `Employee.employment.status` | code:ukg-ready.employee_status | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html`<br>live: list Active 50, Terminated 53 of 103 |  |
| `/v2/companies/{cid}/employees/{aid}` | `photo_href` | excluded |  |  |  | Photo URL carrying a ticket token: a credential, never kept (D-072); the photo itself is binary personal content. |
| `/v2/companies/{cid}/employees/{aid}` | `isPhotoUploaded` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` | Photo flag (CANONICAL_MODEL 3.4). |
| `/v2/companies/{cid}/employees/{aid}` | `national_id_numbers[].type` | mapped | `Employee.national_ids[].type` | code:ukg-ready.national_id_type | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html`<br>live: SSN on 3 of 3 details |  |
| `/v2/companies/{cid}/employees/{aid}` | `national_id_numbers[].value` | mapped | `Employee.national_ids[].value` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html`<br>D-040 | Returned in full; sensitive, masked by default in output. |
| `/v2/companies/{cid}/employees/{aid}` | `national_id_numbers[].primary` | mapped | `Employee.national_ids[].is_primary` | boolean | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` |  |
| `/v2/companies/{cid}/employees/{aid}` | `social_security` | sensitive_extension | `Employee.sensitive_provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` | Single-value form of a national id next to national_id_numbers[], which is the typed source. Whether it repeats the SSN entry cannot be checked from saved samples (redacted, D-019). |
| `/v2/companies/{cid}/employees/{aid}` | `social_insurance` | sensitive_extension | `Employee.sensitive_provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` | Single-value national id form (see social_security). |
| `/v2/companies/{cid}/employees/{aid}` | `national_insurance` | sensitive_extension | `Employee.sensitive_provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` | Single-value national id form (see social_security). |
| `/v2/companies/{cid}/employees/{aid}` | `bsn` | sensitive_extension | `Employee.sensitive_provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` | Single-value national id form (Dutch BSN, see social_security). |
| `/v2/companies/{cid}/employees/{aid}` | `primary_account_id` | mapped | `Employee.person_ref` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html`<br>D-039 | 'Only returned for multi-EIN companies'; groups one person's accounts within the tenant. |
| `/v2/companies/{cid}/employees/{aid}` | `ein.id` | mapped | `Employee.tax_entity_id` | reference | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html`<br>D-039<br>D-042 |  |
| `/v2/companies/{cid}/employees/{aid}` | `address.address_line_1` | mapped | `Employee.personal_contact.addresses[].line1` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` | Address type home. |
| `/v2/companies/{cid}/employees/{aid}` | `address.address_line_2` | mapped | `Employee.personal_contact.addresses[].line2` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` |  |
| `/v2/companies/{cid}/employees/{aid}` | `address.city` | mapped | `Employee.personal_contact.addresses[].city` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` |  |
| `/v2/companies/{cid}/employees/{aid}` | `address.state_code` | mapped | `Employee.personal_contact.addresses[].state` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` |  |
| `/v2/companies/{cid}/employees/{aid}` | `address.zip` | mapped | `Employee.personal_contact.addresses[].postal_code` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` |  |
| `/v2/companies/{cid}/employees/{aid}` | `address.country` | mapped | `Employee.personal_contact.addresses[].country` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` | ISO 3166-1 alpha-3. |
| `/v2/companies/{cid}/employees/{aid}` | `mailing_address.address_line_1` | mapped | `Employee.personal_contact.addresses[].line1` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` | Address type mailing, added only when use_separate_mailing_address is true. |
| `/v2/companies/{cid}/employees/{aid}` | `mailing_address.address_line_2` | mapped | `Employee.personal_contact.addresses[].line2` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` |  |
| `/v2/companies/{cid}/employees/{aid}` | `mailing_address.city` | mapped | `Employee.personal_contact.addresses[].city` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` |  |
| `/v2/companies/{cid}/employees/{aid}` | `mailing_address.state_code` | mapped | `Employee.personal_contact.addresses[].state` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` |  |
| `/v2/companies/{cid}/employees/{aid}` | `mailing_address.zip` | mapped | `Employee.personal_contact.addresses[].postal_code` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` |  |
| `/v2/companies/{cid}/employees/{aid}` | `mailing_address.country` | mapped | `Employee.personal_contact.addresses[].country` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` |  |
| `/v2/companies/{cid}/employees/{aid}` | `*.address_line_3` | sensitive_extension | `Employee.sensitive_provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` | Third street line of a personal address: street lines are sensitive (D-040) and the model has two. |
| `/v2/companies/{cid}/employees/{aid}` | `*.number` | sensitive_extension | `Employee.sensitive_provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` | House number of a personal address (street part, sensitive). |
| `/v2/companies/{cid}/employees/{aid}` | `*.number_addition` | sensitive_extension | `Employee.sensitive_provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` | House number addition of a personal address (street part, sensitive). |
| `/v2/companies/{cid}/employees/{aid}` | `*.state` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` | State per UKG master data, next to state_code, which is mapped. |
| `/v2/companies/{cid}/employees/{aid}` | `use_separate_mailing_address` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` | Says whether the mailing address is used; the adapter adds the mailing address only when true. |
| `/v2/companies/{cid}/employees/{aid}` | `phones.cell_phone` | mapped | `Employee.personal_contact.phones[].number` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` | Phone type mobile. |
| `/v2/companies/{cid}/employees/{aid}` | `phones.home_phone` | mapped | `Employee.personal_contact.phones[].number` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` | Phone type home. |
| `/v2/companies/{cid}/employees/{aid}` | `phones.work_phone` | mapped | `Employee.work_contact.phone` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` |  |
| `/v2/companies/{cid}/employees/{aid}` | `phones.preferred_phone` | mapped | `Employee.personal_contact.phones[].is_preferred` | derive | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html`<br>live: HOME on 2 of 3 | Documented enum HOME, CELL, WORK, NONE: HOME or CELL marks that phone preferred and the other not; WORK and NONE mark both not preferred. |
| `/v2/companies/{cid}/employees/{aid}` | `phones.*_country_id` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` | ISO country of each phone number. |
| `/v2/companies/{cid}/employees/{aid}` | `phones.*_country_code` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` | Dialing code of each phone number. |
| `/v2/companies/{cid}/employees/{aid}` | `primary_email` | mapped | `Employee.personal_contact.emails[].address` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` | Email type unknown (not documented as work or personal); is_primary true. Empty on 3 of 3 sampled. |
| `/v2/companies/{cid}/employees/{aid}` | `secondary_email` | mapped | `Employee.personal_contact.emails[].address` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` | Email type unknown; is_primary false. |
| `/v2/companies/{cid}/employees/{aid}` | `managers[].empl_ref.account_id` | mapped | `Employee.job.manager_employee_id` | reference | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html`<br>D-045<br>live: 2 entries (index 0 and 1) on 1 of 3 | The entry with the lowest index; other entries stay in provider_extensions. |
| `/v2/companies/{cid}/employees/{aid}` | `managers[].index` | excluded |  |  |  | Position of the manager entry; used to pick the entry with the lowest index. |
| `/v2/companies/{cid}/employees/{aid}` | `cost_centers_info.defaults[].value.id` | mapped | `Employee.job.org_units[].source_id` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html`<br>D-076<br>live: 3 defaults (index 0, 1, 2) on 1 of 3 | Each default is an org unit of type cost_center with this id as source_id and its tree index as the type's raw_code; the id is never used as code. Code and name come from config/cost-centers with tree_index equal to that index (see notes). |
| `/v2/companies/{cid}/employees/{aid}` | `cost_centers_info.defaults[].index` | mapped | `Employee.job.org_units[].type` | derive | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html`<br>`contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__config__cost-centers.html`<br>D-076<br>live: index 0, 1 and 2 on 1 of 3 | The cost center tree, kept as the type's raw_code (value cost_center, documented by the route), so each org unit keeps its tree index next to its source_id. It is the tree_index the lookup requires. |
| `/v2/companies/{cid}/employees/{aid}` | `cost_centers_info.limits[].**` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` | Cost centers the employee may charge time to (limits per tree), not the home assignment. |
| `/v2/companies/{cid}/employees/{aid}` | `dates.hired` | mapped | `Employee.employment.original_hire_date` | date:event | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` | Also hire_date unless re_hired is set (see notes). |
| `/v2/companies/{cid}/employees/{aid}` | `dates.re_hired` | mapped | `Employee.employment.rehire_date` | date:event | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html`<br>live: list re_hired on 13 of 103 | Also hire_date when set. |
| `/v2/companies/{cid}/employees/{aid}` | `dates.terminated` | mapped | `Employee.employment.termination_date` | date:event | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` | not_applicable unless the status is terminated; a date sent for an active (rehired) account is kept in provider_extensions. |
| `/v2/companies/{cid}/employees/{aid}` | `dates.seniority` | mapped | `Employee.employment.seniority_date` | date:event | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` |  |
| `/v2/companies/{cid}/employees/{aid}` | `dates.birthday` | mapped | `Employee.demographics.birth_date` | date:event | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html`<br>D-040 |  |
| `/v2/companies/{cid}/employees/{aid}` | `dates.deceased` | mapped | `Employee.demographics.deceased_date` | date:event | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` | is_deceased is not sent: true when this date is set (derive), otherwise not_provided. |
| `/v2/companies/{cid}/employees/{aid}` | `dates.started` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` | Start date, undefined against hired (equal to hired for 3 of 3 sampled). |
| `/v2/companies/{cid}/employees/{aid}` | `dates.*` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` | PEO hire, review, benefits, frozen benefit and retirement dates: no canonical fields. |
| `/v2/companies/{cid}/employees/{aid}` | `dates.custom_dates[].*` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` | Company-defined dates. |
| `/v2/companies/{cid}/employees/{aid}` | `account_extra_fields[].**` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` | Company-defined dated account fields. |
| `/v2/companies/{cid}/employees/{aid}` | `time_entry_extra_fields[].*` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` | Company-defined time entry fields. |
| `/v2/companies/{cid}/employees/{aid}` | `hardware_settings.in_touch.pin` | excluded |  |  |  | Time clock PIN: an authentication secret, never kept (D-072). |
| `/v2/companies/{cid}/employees/{aid}` | `hardware_settings.in_touch.security_level` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` | Time clock role (EMPLOYEE or MANAGER). |
| `/v2/companies/{cid}/employees/{aid}` | `_links.*` | excluded |  |  |  | Navigation links. |
| `/v2/companies/{cid}/employees/{aid}` | `*` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` | Portal and login settings: forced password change, locked, new hire export, managed cost centers flag, time zone (CANONICAL_MODEL 3.4). |
| `/v2/companies/{cid}/employees/{aid}` | `*.id` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` | First screen and locale ids: portal settings. |
| `/v2/companies/{cid}/employees/{aid}` | `managed_cost_centers_settings.allow_save_others_cost_centers` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` | Manager portal setting. |
| `/v2/companies/{cid}/employees/{aid}/demographics` | `gender` | mapped | `Employee.demographics.gender` | code:ukg-ready.gender | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__demographics.html` |  |
| `/v2/companies/{cid}/employees/{aid}/demographics` | `ethnicity` | mapped | `Employee.demographics.ethnicity` | code:ukg-ready.ethnicity | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__demographics.html` |  |
| `/v2/companies/{cid}/employees/{aid}/demographics` | `citizenship` | mapped | `Employee.demographics.citizenship` | code:ukg-ready.citizenship | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__demographics.html` |  |
| `/v2/companies/{cid}/employees/{aid}/demographics` | `seasonal` | mapped | `Employee.employment.is_seasonal` | boolean | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__demographics.html` | Null on 3 of 3 sampled: not_provided. |
| `/v2/companies/{cid}/employees/{aid}/demographics` | `visa.type` | mapped | `Employee.work_authorization.visa_type` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__demographics.html` | Documented enum, kept as sent. Empty on 3 of 3 sampled. |
| `/v2/companies/{cid}/employees/{aid}/demographics` | `visa.expiration_date` | mapped | `Employee.work_authorization.document_expiration_date` | date:event | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__demographics.html` | Expiration of the visa, the only work authorization document UKG sends. |
| `/v2/companies/{cid}/employees/{aid}/demographics` | `visa.number` | sensitive_extension | `Employee.sensitive_provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__demographics.html` | Visa number: a document identifier, not seen live (0 of 3), so not typed (D-071). |
| `/v2/companies/{cid}/employees/{aid}/demographics` | `eye_color` | sensitive_extension | `Employee.sensitive_provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__demographics.html` | Physical characteristic with no canonical field. |
| `/v2/companies/{cid}/employees/{aid}/demographics` | `height` | sensitive_extension | `Employee.sensitive_provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__demographics.html` | Physical characteristic with no canonical field. |
| `/v2/companies/{cid}/employees/{aid}/demographics` | `full_time_student` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__demographics.html` | Student status; no canonical field. |
| `/v2/companies/{cid}/employees/{aid}/demographics` | `referral.id` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__demographics.html` | Recruiting referral reference. |
| `/v2/companies/{cid}/employees/{aid}/demographics` | `recruiter.*` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__demographics.html` | Recruiter account and display name (recruiting data). |
| `/v2/companies/{cid}/employees/{aid}/pay-info` | `default_job.id` | mapped | `Employee.job.job.source_id` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__pay-info.html`<br>live: 1 of 3 | Code and name from lookup/jobs. |
| `/v2/companies/{cid}/employees/{aid}/pay-info` | `job_last_changed` | mapped | `Employee.job.effective_date` | date:event | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__pay-info.html` |  |
| `/v2/companies/{cid}/employees/{aid}/pay-info` | `job_change_reason_code.display_name` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__pay-info.html` | Reason of the last job change; the model has no job reason field. |
| `/v2/companies/{cid}/employees/{aid}/pay-info` | `employee_type.id` | mapped | `Employee.employment.employment_type` | join | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__pay-info.html`<br>live: 3 of 3 | raw_code the id, raw_label the lookup name; value from the name only when it says full or part time (D-099, see notes). |
| `/v2/companies/{cid}/employees/{aid}/pay-info` | `pay_type.id` | mapped | `Employee.compensation.pay_type` | join | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__pay-info.html`<br>live: 3 of 3 | Value from the lookup/pay-types name through ukg-ready.pay_type. |
| `/v2/companies/{cid}/employees/{aid}/pay-info` | `eeo_classification` | mapped | `Employee.job.eeo_category` | code:ukg-ready.eeo_classification | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__pay-info.html`<br>live: 1 of 3 |  |
| `/v2/companies/{cid}/employees/{aid}/pay-info` | `workers_comp_code.external_id` | mapped | `Employee.job.workers_comp_code` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__pay-info.html` |  |
| `/v2/companies/{cid}/employees/{aid}/pay-info` | `union.id` | mapped | `Employee.job.union_code` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__pay-info.html` | The union's id (no code is sent). |
| `/v2/companies/{cid}/employees/{aid}/pay-info` | `standard_work_day` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__pay-info.html`<br>D-028 | Length of a standard work day in ms (documented; 28800000 on 1 of 3, 0 on 2). compensation.standard_hours comes from the compensation's time and time_period, the hours its pay is based on. |
| `/v2/companies/{cid}/employees/{aid}/pay-info` | `bank_account_number` | sensitive_extension | `Employee.sensitive_provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__pay-info.html` | Bank account number on pay-info (empty on 3 of 3). Not compared with the deposit accounts (empty on 3 of 3); deposits come from the direct-deposits route (D-081). |
| `/v2/companies/{cid}/employees/{aid}/pay-info` | `pay_grade.**` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__pay-info.html` | Pay grade and its parent; the model has no pay grade field. |
| `/v2/companies/{cid}/employees/{aid}/pay-info` | `*` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__pay-info.html` | Benefit eligibility flags, EEO-4 classification and function, payroll classification: no canonical fields. |
| `/v2/companies/{cid}/employees/{aid}/pay-info` | `shift_premium.id` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__pay-info.html` | Shift premium reference. |
| `/v2/companies/{cid}/employees/{aid}/pay-info` | `gl_codes[].*` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__pay-info.html` | General ledger codes. |
| `/v2/companies/{cid}/employees/{aid}/pay-info` | `ttoc[].*` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__pay-info.html` | Dated reference with no documented meaning (id, display name, effective date). |
| `/v2/companies/{cid}/employees/{aid}/profiles` | `pay_period[].id` | mapped | `Employee.compensation.pay_group_id` | reference | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__profiles.html`<br>D-065<br>live: 1 of 3 | The one entry the contract allows (maxItems 1); also the join to the pay group's frequency (pay_frequency). |
| `/v2/companies/{cid}/employees/{aid}/profiles` | `pay_period[].name` | excluded |  |  |  | Pay period profile name: the company pay group holds it. |
| `/v2/companies/{cid}/employees/{aid}/profiles` | `pay_period[].effective_from` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__profiles.html` | When the profile link took effect; no canonical field. |
| `/v2/companies/{cid}/employees/{aid}/profiles` | `**` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__profiles.html` | Links to non-pay profiles (security, timesheet, holiday, accruals, pay calculations, points, rate tables, work schedule and others) with effective dates: platform configuration (CANONICAL_MODEL 3.4, D-065). |
| `/v2/companies/{cid}/employees/{aid}/compensation/history` | `compensations[].effective_from` | mapped | `Employee.compensation_history[].effective_date` | date:event | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__compensation__history.html`<br>D-025 | 1900-12-31 (open start) is a placeholder on an event date: not_provided with sentinel_date; the entry is kept. |
| `/v2/companies/{cid}/employees/{aid}/compensation/history` | `compensations[].amount` | mapped | `Employee.compensation_history[].amount` | number | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__compensation__history.html` |  |
| `/v2/companies/{cid}/employees/{aid}/compensation/history` | `compensations[].amount_period` | mapped | `Employee.compensation_history[].amount_period` | code:ukg-ready.amount_period | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__compensation__history.html`<br>live: HOUR 5, YEAR 2 of 7 entries |  |
| `/v2/companies/{cid}/employees/{aid}/compensation/history` | `compensations[].hourly_pay` | mapped | `Employee.compensation_history[].hourly_rate` | number | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__compensation__history.html` |  |
| `/v2/companies/{cid}/employees/{aid}/compensation/history` | `compensations[].currency` | mapped | `Employee.currency` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__compensation__history.html`<br>live: USD on 7 of 7 entries | One currency per employee; entries that disagree raise conflicting_sources. |
| `/v2/companies/{cid}/employees/{aid}/compensation/history` | `compensations[].time` | mapped | `Employee.compensation.standard_hours` | ms_to_hours | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__compensation__history.html`<br>D-028 | 'Time is represented in milliseconds.' From the latest entry; history entries have no hours field, so earlier entries' times stay in provider_extensions. |
| `/v2/companies/{cid}/employees/{aid}/compensation/history` | `compensations[].time_period` | mapped | `Employee.compensation.standard_hours_period` | code:ukg-ready.time_period | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__compensation__history.html`<br>live: YEAR 6, PAY_PERIOD 1 of 7 entries | From the latest entry (see time). |
| `/v2/companies/{cid}/employees/{aid}/compensation/history` | `compensations[].num_pp_in_year` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__compensation__history.html` | Pay periods per year of the entry (26 seen); pay frequency comes from the pay period profile (D-041), not from this count. |
| `/v2/companies/{cid}/employees/{aid}/compensation/history` | `compensations[].id` | excluded |  |  |  | Row id. |
| `/v2/companies/{cid}/employees/{aid}/compensation/history` | `compensations[].employee.account_id` | excluded |  |  |  | The requested account, already the source id. |
| `/v2/companies/{cid}/employees/{aid}/compensation/history` | `compensations[]._links.*` | excluded |  |  |  | Navigation links. |
| `/v2/companies/{cid}/employees/{aid}/compensation/total` | `total_compensations[].account.id` | excluded |  |  |  | The requested account, already the source id. |
| `/v2/companies/{cid}/employees/{aid}/compensation/total` | `total_compensations[].*` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__compensation__total.html` | Dated total compensation amounts whose meaning is undocumented: they equal the annualized history amount for 2 of 8 entries (3 employees), so they are not read as annual salary. |
| `/v2/companies/{cid}/employees/{aid}/compensation/additional` | `additional_compensations[].account.id` | excluded |  |  |  | The requested account, already the source id. |
| `/v2/companies/{cid}/employees/{aid}/compensation/additional` | `additional_compensations[]._links.*` | excluded |  |  |  | Navigation links. |
| `/v2/companies/{cid}/employees/{aid}/compensation/additional` | `additional_compensations[].**` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__compensation__additional.html` | Additional compensation by type: the value is an amount or a percent of base depending on the type, and the type lookup is not selected, so it does not enter additional_rates (unit rule, D-036). Empty for 3 of 3 sampled. |
| `/v2/companies/{cid}/employees/{aid}/tax-info` | `employee-tax-type._1099` | mapped | `Employee.employment.worker_type` | derive | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__tax-info.html`<br>D-041<br>live: false on 3 of 3 | With W2 (see notes); inferred. |
| `/v2/companies/{cid}/employees/{aid}/tax-info` | `employee-tax-type.W2` | mapped | `Employee.employment.worker_type` | derive | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__tax-info.html`<br>D-041<br>live: true on 3 of 3 | With _1099 (see notes); inferred. |
| `/v2/companies/{cid}/employees/{aid}/tax-info` | `employee-tax-type.DRAW` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__tax-info.html` | Draw tax type flag (undocumented meaning). |
| `/v2/companies/{cid}/employees/{aid}/tax-info` | `fein` | sensitive_extension | `Employee.sensitive_provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__tax-info.html` | Employer EIN on the employee's tax info: EINs are sensitive (D-044); the tax entity link comes from ein.id. |
| `/v2/companies/{cid}/employees/{aid}/tax-info` | `*` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__tax-info.html` | Tax reporting settings: DBA company name, pension box type, third-party sick pay reporting. |
| `/v2/companies/{cid}/employees/{aid}/badges` | `badges[].pin` | excluded |  |  |  | Badge PIN: an authentication secret, never kept (D-072). |
| `/v2/companies/{cid}/employees/{aid}/badges` | `badges[].badge_number` | sensitive_extension | `Employee.sensitive_provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__badges.html` | Badge number: a person-level identifier (D-019). |
| `/v2/companies/{cid}/employees/{aid}/badges` | `badges[].short_id` | sensitive_extension | `Employee.sensitive_provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__badges.html` | Badge short id: a person-level identifier (D-019). |
| `/v2/companies/{cid}/employees/{aid}/badges` | `badges[].*` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__badges.html` | Badge type and validity dates (time clock setup). |
| `/v2/companies/{cid}/employees/{aid}/hr-custom-fields` | `hr_custom_fields[].*` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__hr-custom-fields.html` | Company-defined HR fields (empty for 3 of 3 sampled). |
| `/v2/companies/{cid}/employees/{aid}/contacts` | `contacts[].id` | mapped | `Employee.related_people[].source_id` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__contacts.html`<br>live: 2 contacts for 1 of 3 sampled employees | One RelatedPerson per contacts[] item; its flags say emergency contact, dependent or beneficiary. |
| `/v2/companies/{cid}/employees/{aid}/contacts` | `contacts[].salutation` | mapped | `Employee.related_people[].name.prefix` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__contacts.html` |  |
| `/v2/companies/{cid}/employees/{aid}/contacts` | `contacts[].first_name` | mapped | `Employee.related_people[].name.first` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__contacts.html` |  |
| `/v2/companies/{cid}/employees/{aid}/contacts` | `contacts[].middle_name` | mapped | `Employee.related_people[].name.middle` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__contacts.html` |  |
| `/v2/companies/{cid}/employees/{aid}/contacts` | `contacts[].last_name` | mapped | `Employee.related_people[].name.last` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__contacts.html` |  |
| `/v2/companies/{cid}/employees/{aid}/contacts` | `contacts[].name_suffix` | mapped | `Employee.related_people[].name.suffix` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__contacts.html` |  |
| `/v2/companies/{cid}/employees/{aid}/contacts` | `contacts[].relationship` | mapped | `Employee.related_people[].relationship` | code:ukg-ready.contact_relationship | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__contacts.html`<br>live: 'Spouse' and 'Child' on 2 of 2 | A label (no documented list); the label is the raw_code. Spouse and Child are inferred; any other label is unknown. |
| `/v2/companies/{cid}/employees/{aid}/contacts` | `contacts[].birthdate` | mapped | `Employee.related_people[].birth_date` | date:event | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__contacts.html` |  |
| `/v2/companies/{cid}/employees/{aid}/contacts` | `contacts[].emergency` | mapped | `Employee.related_people[].is_emergency_contact` | boolean | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__contacts.html` |  |
| `/v2/companies/{cid}/employees/{aid}/contacts` | `contacts[].dependent` | mapped | `Employee.related_people[].is_dependent` | boolean | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__contacts.html` |  |
| `/v2/companies/{cid}/employees/{aid}/contacts` | `contacts[].beneficiary` | mapped | `Employee.related_people[].is_beneficiary` | boolean | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__contacts.html` |  |
| `/v2/companies/{cid}/employees/{aid}/contacts` | `contacts[].active` | mapped (live only) | `Employee.related_people[].is_active` | boolean | live: filled on 2 of 2 contacts | Not in the documented schema; live it comes with a changeActiveStatus link, so it is read as the contact's active flag. |
| `/v2/companies/{cid}/employees/{aid}/contacts` | `contacts[].work_phone.number` | mapped | `Employee.related_people[].phones[].number` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__contacts.html` | phones[] entry of type work. |
| `/v2/companies/{cid}/employees/{aid}/contacts` | `contacts[].home_phone.number` | mapped | `Employee.related_people[].phones[].number` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__contacts.html` | phones[] entry of type home. |
| `/v2/companies/{cid}/employees/{aid}/contacts` | `contacts[].cell_phone.number` | mapped | `Employee.related_people[].phones[].number` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__contacts.html` | phones[] entry of type mobile. |
| `/v2/companies/{cid}/employees/{aid}/contacts` | `contacts[].*.primary` | mapped | `Employee.related_people[].phones[].is_preferred` | boolean | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__contacts.html` | The primary flag of each phone (work_phone, home_phone, cell_phone). |
| `/v2/companies/{cid}/employees/{aid}/contacts` | `contacts[].*.code` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__contacts.html` | Phone 'code' (integer, undocumented; perhaps a country code, not established); kept raw. |
| `/v2/companies/{cid}/employees/{aid}/contacts` | `contacts[].primary` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__contacts.html` | Primary contact flag; no typed home. |
| `/v2/companies/{cid}/employees/{aid}/contacts` | `contacts[].emergency_notif` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__contacts.html` | Emergency notification setting; no typed home. Empty on 2 of 2. |
| `/v2/companies/{cid}/employees/{aid}/contacts` | `contacts[].is_in_any_benefit_plan` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__contacts.html` | Whether the contact is in a benefit plan; plan coverage comes with benefit enrollments. |
| `/v2/companies/{cid}/employees/{aid}/contacts` | `contacts[].comments` | sensitive_extension | `Employee.sensitive_provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__contacts.html` | Free-text comments; may hold personal matters. |
| `/v2/companies/{cid}/employees/{aid}/contacts` | `contacts[].account_id` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__contacts.html` | Account id with no description, absent from the docs example and from the 2 live contacts; whose account it is (the contact's own, if also an employee) is not established. Kept raw. |
| `/v2/companies/{cid}/employees/{aid}/contacts` | `contacts[].employee.account_id` | excluded |  |  |  | The requested employee account id, already a source id. |
| `/v2/companies/{cid}/employees/{aid}/contacts` | `contacts[].has_*` | excluded |  |  |  | Permissions of the API user on this record (delete, activate, emergency notification): not data about the contact. |
| `/v2/companies/{cid}/employees/{aid}/contacts` | `contacts[]._links.*` | excluded |  |  |  | Navigation links (the live changeActiveStatus link included). |
| `/v2/companies/{cid}/employees/{aid}/contacts` | `_links.*` | excluded |  |  |  | Navigation links. |
| `/v2/companies/{cid}/employees/{aid}/contacts` | `_total_count` | excluded |  |  |  | Count of the list. |
| `/v2/companies/{cid}/employees/{aid}/contacts` | `_sub_count.*` | excluded |  |  |  | Counts of the list by kind. |
| `/v2/companies/{cid}/employees/{aid}/skills` | `employee_skills[].skill.id` | mapped | `Employee.qualifications[].source_id` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__skills.html`<br>live: 29 skills for 1 of 3 sampled employees, 29 distinct ids | One Qualification per item, type skill. The id is the only identity sent; name and code are not_provided (lookup/skills is not called, D-077). |
| `/v2/companies/{cid}/employees/{aid}/skills` | `employee_skills[].level` | mapped | `Employee.qualifications[].level` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__skills.html`<br>live: 1 on 29 of 29 |  |
| `/v2/companies/{cid}/employees/{aid}/skills` | `employee_skills[].years` | mapped | `Employee.qualifications[].years_experience` | number | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__skills.html`<br>live: 0 on 29 of 29 | A count of years, as the field name says (no description). |
| `/v2/companies/{cid}/employees/{aid}/skills` | `employee_skills[].primary` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__skills.html` | Primary flag of a schedulable skill (scheduling setting). |
| `/v2/companies/{cid}/employees/{aid}/training/certifications` | `employee_training_course_history[].course` | mapped | `Employee.qualifications[].name` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__training__certifications.html`<br>live: 4 entries for 1 of 3 sampled employees, 3 courses | One Qualification per course history entry, type training (the items are training courses). |
| `/v2/companies/{cid}/employees/{aid}/training/certifications` | `employee_training_course_history[].current_completed_date` | mapped | `Employee.qualifications[].completed_date` | date:event | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__training__certifications.html`<br>live: filled on 2 of 4 |  |
| `/v2/companies/{cid}/employees/{aid}/training/certifications` | `employee_training_course_history[].expires_on` | mapped | `Employee.qualifications[].expiration_date` | date:period_end | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__training__certifications.html` |  |
| `/v2/companies/{cid}/employees/{aid}/training/certifications` | `employee_training_course_history[].description` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__training__certifications.html` | Course description as HTML markup: kept raw, not typed as a name. |
| `/v2/companies/{cid}/employees/{aid}/training/certifications` | `employee_training_course_history[].is_expired` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__training__certifications.html` | Expired flag; follows from expires_on, kept raw. |
| `/v2/companies/{cid}/employees/{aid}/training/certifications` | `employee_training_course_history[].is_schedulable` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__training__certifications.html` | Scheduling setting of the course. |
| `/v2/companies/{cid}/employees/{aid}/accrual/1/balances` | `accrual_balances[].time_off.id` | mapped | `Employee.pto_balances[].plan_source_id` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__accrual__1__balances.html`<br>live: 403 for 3 of 3 sampled employees (D-027) | One PtoBalance per item (time off). Items of /1 (time off ids) and /2 (accrual category ids) are separate entries, never merged. The fields have no descriptions; the docs sample has remaining = carry_over + accrued - taken. |
| `/v2/companies/{cid}/employees/{aid}/accrual/1/balances` | `accrual_balances[].time_off.name` | mapped | `Employee.pto_balances[].plan_name` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__accrual__1__balances.html` |  |
| `/v2/companies/{cid}/employees/{aid}/accrual/1/balances` | `accrual_balances[].remaining` | mapped | `Employee.pto_balances[].balance` | ms_to_hours | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__accrual__1__balances.html`<br>D-027<br>D-028 | 'The hour(s) value is in milliseconds (ms)' (D-027 amendment 2). |
| `/v2/companies/{cid}/employees/{aid}/accrual/1/balances` | `accrual_balances[].accrued` | mapped | `Employee.pto_balances[].accrued_ytd` | ms_to_hours | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__accrual__1__balances.html`<br>D-027 | 'The hour(s) value is in milliseconds (ms)' (D-027 amendment 2). Accrued in the item's accrual year through accrued_to. |
| `/v2/companies/{cid}/employees/{aid}/accrual/1/balances` | `accrual_balances[].taken` | mapped | `Employee.pto_balances[].used_ytd` | ms_to_hours | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__accrual__1__balances.html`<br>D-027 | 'The hour(s) value is in milliseconds (ms)' (D-027 amendment 2). Taken in the item's accrual year. |
| `/v2/companies/{cid}/employees/{aid}/accrual/1/balances` | `accrual_balances[].carry_over` | mapped | `Employee.pto_balances[].carryover` | ms_to_hours | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__accrual__1__balances.html`<br>D-027 | 'The hour(s) value is in milliseconds (ms)' (D-027 amendment 2). |
| `/v2/companies/{cid}/employees/{aid}/accrual/1/balances` | `accrual_balances[].accrued_to` | mapped | `Employee.pto_balances[].as_of_date` | date:event | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__accrual__1__balances.html` |  |
| `/v2/companies/{cid}/employees/{aid}/accrual/1/balances` | `accrual_balances[].accrual_year.start_date` | mapped | `Employee.pto_balances[].period_start` | date:period_start | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__accrual__1__balances.html` |  |
| `/v2/companies/{cid}/employees/{aid}/accrual/1/balances` | `accrual_balances[].accrual_year.end_date` | mapped | `Employee.pto_balances[].period_end` | date:period_end | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__accrual__1__balances.html` |  |
| `/v2/companies/{cid}/employees/{aid}/accrual/1/balances` | `accrual_balances[].*` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__accrual__1__balances.html` | Estimated, external, pending, scheduled and carry-over-used amounts and the regular day time (milliseconds, kept raw): no typed home. |
| `/v2/companies/{cid}/employees/{aid}/accrual/2/balances` | `accrual_balances[].category.id` | mapped | `Employee.pto_balances[].plan_source_id` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__accrual__2__balances.html`<br>live: an empty list for 1 of 3 sampled employees, 400 code 17605 (no accruals profile) for 2 (D-027) | One PtoBalance per item (accrual category). The item covers the current period (period.start and end, a month in the docs sample), not the year: accrued_ytd and used_ytd are not_provided, and period_start and period_end, which bound the plan year, are not filled from it. |
| `/v2/companies/{cid}/employees/{aid}/accrual/2/balances` | `accrual_balances[].category.category_name` | mapped | `Employee.pto_balances[].plan_name` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__accrual__2__balances.html` |  |
| `/v2/companies/{cid}/employees/{aid}/accrual/2/balances` | `accrual_balances[].current_balance.hours` | mapped | `Employee.pto_balances[].balance` | ms_to_hours | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__accrual__2__balances.html`<br>D-027<br>D-028 | 'The hour(s) value is in milliseconds (ms)' (D-027 amendment 2). |
| `/v2/companies/{cid}/employees/{aid}/accrual/2/balances` | `accrual_balances[].previous_carry_over.hours` | mapped | `Employee.pto_balances[].carryover` | ms_to_hours | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__accrual__2__balances.html`<br>D-027 | 'The hour(s) value is in milliseconds (ms)' (D-027 amendment 2). |
| `/v2/companies/{cid}/employees/{aid}/accrual/2/balances` | `accrual_balances[].current_accrued.hours` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__accrual__2__balances.html` | Accrued in the current period, not year to date, so it does not fill accrued_ytd. Milliseconds, kept raw. |
| `/v2/companies/{cid}/employees/{aid}/accrual/2/balances` | `accrual_balances[].taken.hours` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__accrual__2__balances.html` | Taken in the current period, not year to date, so it does not fill used_ytd. Milliseconds, kept raw. |
| `/v2/companies/{cid}/employees/{aid}/accrual/2/balances` | `accrual_balances[].period.*` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__accrual__2__balances.html` | Start and end of the current period the item covers (not the plan year). |
| `/v2/companies/{cid}/employees/{aid}/accrual/2/balances` | `accrual_balances[].*.days` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__accrual__2__balances.html` | The same amounts in days (the category's unit when it is a days category): no typed home. |
| `/v2/companies/{cid}/employees/{aid}/accrual/2/balances` | `accrual_balances[].*.hours` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__accrual__2__balances.html` | Projected, scheduled, requested and expiring amounts (milliseconds, kept raw): no typed home. |
| `/v2/companies/{cid}/employees/{aid}/accrual/2/balances` | `accrual_balances[].category.type` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__accrual__2__balances.html` | Category type (docs sample ACCRUAL_CATEGORY). |
| `/v2/companies/{cid}/employees/{aid}/accrual/2/balances` | `accrual_balances[].category.color` | excluded |  |  |  | Display color. |
| `/v2/companies/{cid}/employees/{aid}/accrual/2/balances` | `accrual_balances[].expiring_date.date` | extension | `Employee.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__accrual__2__balances.html` | Date the expiring amount expires; no typed home. |
| `/v2/companies/{cid}/employees/{aid}/accrual/2/balances` | `accrual_balances[]._precision.*` | excluded |  |  |  | Display precision of days and hours. |
| `/v2/companies/{cid}/lookup/jobs` | `items[].id` | mapped | `Employee.job.job` | join | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__lookup__jobs.html`<br>D-064 | Key for pay-info default_job.id. |
| `/v2/companies/{cid}/lookup/jobs` | `items[].name` | mapped | `Employee.job.job.name` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__lookup__jobs.html` |  |
| `/v2/companies/{cid}/lookup/jobs` | `items[].payroll_code` | mapped | `Employee.job.job.code` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__lookup__jobs.html` |  |
| `/v2/companies/{cid}/lookup/jobs` | `items[].*` | excluded |  |  |  | External id and visibility flag: job configuration (D-064). |
| `/v2/companies/{cid}/lookup/employee-types` | `items[].id` | mapped | `Employee.employment.employment_type` | join | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__lookup__employee-types.html`<br>D-064 | Key for pay-info employee_type.id. |
| `/v2/companies/{cid}/lookup/employee-types` | `items[].name` | mapped | `Employee.employment.employment_type` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__lookup__employee-types.html`<br>live: 5 company-defined names | raw_label; read only when it says full or part time (D-099, see notes). |
| `/v2/companies/{cid}/lookup/pay-types` | `items[].id` | mapped | `Employee.compensation.pay_type` | join | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__lookup__pay-types.html`<br>D-064 | Key for pay-info pay_type.id (the raw_code). |
| `/v2/companies/{cid}/lookup/pay-types` | `items[].name` | mapped | `Employee.compensation.pay_type` | code:ukg-ready.pay_type | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__lookup__pay-types.html`<br>live: Hourly, Salaried | raw_label, and the key to the code table. |
| `/v2/companies/{cid}/lookup/pay-types` | `items[].external_id` | excluded |  |  |  | Integration id of the pay type (configuration). |
| `/v2/companies/{cid}/config/cost-centers` | `cost_centers[].id` | mapped | `Employee.job.org_units[].source_id` | join | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__config__cost-centers.html`<br>D-064<br>D-065<br>D-076 | Joined on (tree_index, id): the default's index selects the tree, its id the cost center. The defaults at tree 0 and tree 2 were found (1 of 1 each); tree 1 returned 400 (code 19515, 'Cost Center not used'). |
| `/v2/companies/{cid}/config/cost-centers` | `cost_centers[].payroll_code` | mapped | `Employee.job.org_units[].code` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__config__cost-centers.html`<br>live: filled on 3 of 54 cost centers in tree 0 and 0 of 17 in tree 2 | Usually empty: code is then null with not_provided. |
| `/v2/companies/{cid}/config/cost-centers` | `cost_centers[].name` | mapped | `Employee.job.org_units[].name` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__config__cost-centers.html` |  |
| `/v2/companies/{cid}/config/cost-centers` | `cost_centers[].location_code` | excluded |  |  |  | Empty on 71 of 71 cost centers; UKG has no work location source (D-065). |
| `/v2/companies/{cid}/config/cost-centers` | `cost_centers[].*` | excluded |  |  |  | Description, external id and parent: cost center configuration (D-064). |

## Direct deposit fields

- One DirectDeposit per deposits[] item (id from company and deposit id). The route is deprecated and the only deposit list (D-030): every record carries a deprecated_source diagnostic.
- allocation_type from calc_method.type; percent_basis from the same code: NET_PAY net_pay, GROSS_EARNING gross_pay, DIRECT_DEPOSIT_PER_OF_REMAINDER remainder_after_fixed (documented names), not_applicable for FULL and FLAT_AMOUNT.
- status from active (true active, false inactive); pre-note progress is prenote_status. Numbers are returned in full (some 1 to 4 characters in the demo data); routing_last4 and account_last4 are null with not_applicable next to a full value (CANONICAL_MODEL 1.4).

| Route | Source field | Use | Canonical field | Transform | Evidence | Reason or note |
| --- | --- | --- | --- | --- | --- | --- |
| `/v2/companies/{cid}/employees/{aid}/direct-deposits` | `deposits[].id` | mapped | `DirectDeposit.source_ids` | source_id | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__direct-deposits.html` |  |
| `/v2/companies/{cid}/employees/{aid}/direct-deposits` | `deposits[].sequence` | mapped | `DirectDeposit.sequence` | number | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__direct-deposits.html`<br>live: 1..n |  |
| `/v2/companies/{cid}/employees/{aid}/direct-deposits` | `deposits[].calc_method.type` | mapped | `DirectDeposit.allocation_type` | code:ukg-ready.deposit_calc_method | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__direct-deposits.html`<br>D-032<br>live: FULL 14, FLAT_AMOUNT 2, NET_PAY 2 (18 accounts) | Also sets percent_basis (notes). |
| `/v2/companies/{cid}/employees/{aid}/direct-deposits` | `deposits[].calc_method.display_name` | excluded |  |  |  | Label of calc_method.type. |
| `/v2/companies/{cid}/employees/{aid}/direct-deposits` | `deposits[].amount` | mapped | `DirectDeposit.amount` | number | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__direct-deposits.html`<br>live: 2 of 19 |  |
| `/v2/companies/{cid}/employees/{aid}/direct-deposits` | `deposits[].percentage` | mapped | `DirectDeposit.percent` | number | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__direct-deposits.html`<br>live: 15.0 in a 3-way split | 0 to 100 (live split). |
| `/v2/companies/{cid}/employees/{aid}/direct-deposits` | `deposits[].account_type` | mapped | `DirectDeposit.account_type` | code:ukg-ready.deposit_account_type | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__direct-deposits.html`<br>live: CHECKING 16, SAVINGS 2 |  |
| `/v2/companies/{cid}/employees/{aid}/direct-deposits` | `deposits[].routing_number` | mapped | `DirectDeposit.routing_number` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__direct-deposits.html` | Full value; sensitive, masked in output by default. |
| `/v2/companies/{cid}/employees/{aid}/direct-deposits` | `deposits[].account_number` | mapped | `DirectDeposit.account_number` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__direct-deposits.html` | Full value; sensitive, masked in output by default. |
| `/v2/companies/{cid}/employees/{aid}/direct-deposits` | `deposits[].active` | mapped | `DirectDeposit.status` | derive | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__direct-deposits.html`<br>live: true 16, false 2 | true active, false inactive. |
| `/v2/companies/{cid}/employees/{aid}/direct-deposits` | `deposits[].pre_note_status` | mapped | `DirectDeposit.prenote_status` | code:ukg-ready.prenote_status | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__direct-deposits.html`<br>live: READY_TO_SEND 9, CANCELED 5, COMPLETE_EXPIRED 4 |  |
| `/v2/companies/{cid}/employees/{aid}/direct-deposits` | `deposits[].payroll_frequency.type` | mapped | `DirectDeposit.frequency` | code:ukg-ready.deposit_frequency | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__direct-deposits.html`<br>live: EVERY_PAY 18 |  |
| `/v2/companies/{cid}/employees/{aid}/direct-deposits` | `deposits[].active_from` | mapped | `DirectDeposit.effective_from` | date:period_start | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__direct-deposits.html` |  |
| `/v2/companies/{cid}/employees/{aid}/direct-deposits` | `deposits[].active_to` | mapped | `DirectDeposit.effective_to` | date:period_end | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__direct-deposits.html`<br>D-025<br>live: 2099 sentinel on 16 of 18 | The 2099 sentinel means open-ended. |
| `/v2/companies/{cid}/employees/{aid}/direct-deposits` | `deposits[].currency` | mapped | `DirectDeposit.currency` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__direct-deposits.html` |  |
| `/v2/companies/{cid}/employees/{aid}/direct-deposits` | `deposits[].*` | extension | `DirectDeposit.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__direct-deposits.html` | Deposit settings with no canonical field: type (DIRECT_DEPOSIT or RESERVE_LIVE_CHECK; 18 of 18 DIRECT_DEPOSIT), free-text name ('test') and description, routing type, arrearage function, PayPal flag, pre-note dates and cancel flag, last payroll, use and visibility flags, month, quarter and year to date amounts. |
| `/v2/companies/{cid}/employees/{aid}/direct-deposits` | `deposits[].payroll_frequency.*` | extension | `DirectDeposit.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__direct-deposits.html` | Frequency parameters (month, payroll number, block last, holiday type). |
| `/v2/companies/{cid}/employees/{aid}/direct-deposits` | `deposits[].payroll_frequency.holiday_profile.*` | extension | `DirectDeposit.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__direct-deposits.html` | Holiday profile of the frequency. |
| `/v2/companies/{cid}/employees/{aid}/direct-deposits` | `deposits[]._links.*` | excluded |  |  |  | Hypermedia links and counters (API navigation), not data. |
| `/v2/companies/{cid}/employees/{aid}/direct-deposits` | `deposits[]._documents_count` | excluded |  |  |  | Hypermedia links and counters (API navigation), not data. |
| `/v2/companies/{cid}/employees/{aid}/direct-deposits` | `deposits[]._notes_count` | excluded |  |  |  | Hypermedia links and counters (API navigation), not data. |
| `/v2/companies/{cid}/employees/{aid}/direct-deposits` | `_links.*` | excluded |  |  |  | Hypermedia links and counters (API navigation), not data. |
| `/v2/companies/{cid}/employees/{aid}/direct-deposits` | `_total_count` | excluded |  |  |  | Hypermedia links and counters (API navigation), not data. |
| `/v2/companies/{cid}/employees/{aid}/direct-deposits` | `_routing_type` | excluded |  |  |  | Response-level routing type setting, repeated per deposit. |
| `/v2/companies/{cid}/employees/{aid}/direct-deposits` | `is_eligible_for_paypal` | excluded |  |  |  | Response-level PayPal eligibility; not deposit data. |

## Benefit enrollment fields

- One BenefitEnrollment per benefits[] item (company, enrollment id) (D-049). No amounts are sent: plan_details is null with not_provided. benefit_type is null with not_provided: lookup/benefit/types was not called (D-081).
- coverage_level labels are company-defined: 'Employee' reads as employee_only and 'Waived' as status waived (inferred); other labels are unknown. status is otherwise null with not_provided.

| Route | Source field | Use | Canonical field | Transform | Evidence | Reason or note |
| --- | --- | --- | --- | --- | --- | --- |
| `/v2/companies/{cid}/employees/{aid}/benefits` | `benefits[].id` | mapped | `BenefitEnrollment.source_ids` | source_id | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__benefits.html` |  |
| `/v2/companies/{cid}/employees/{aid}/benefits` | `benefits[].employee.account_id` | mapped | `BenefitEnrollment.employee_id` | reference | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__benefits.html` |  |
| `/v2/companies/{cid}/employees/{aid}/benefits` | `benefits[].benefit_plan.id` | mapped | `BenefitEnrollment.plan.source_id` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__benefits.html` |  |
| `/v2/companies/{cid}/employees/{aid}/benefits` | `benefits[].name` | mapped | `BenefitEnrollment.plan.name` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__benefits.html`<br>live: 11 enrollments of 1 of 3 employees |  |
| `/v2/companies/{cid}/employees/{aid}/benefits` | `benefits[].coverage_level` | mapped | `BenefitEnrollment.coverage_level` | code:ukg-ready.coverage_level | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__benefits.html`<br>live: Waived 5, Employee 4, 2 other labels | Also sets status (code table). |
| `/v2/companies/{cid}/employees/{aid}/benefits` | `benefits[].coverage_effective_from` | mapped | `BenefitEnrollment.coverage_start` | date:period_start | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__benefits.html` |  |
| `/v2/companies/{cid}/employees/{aid}/benefits` | `benefits[].coverage_effective_to` | mapped | `BenefitEnrollment.coverage_end` | date:period_end | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__benefits.html` |  |
| `/v2/companies/{cid}/employees/{aid}/benefits` | `benefits[].benefit_plan.currency` | mapped | `BenefitEnrollment.currency` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__benefits.html` |  |

## Payroll fields

- PayrollRun per payroll (company, payroll id), Paycheck per pay statement (company, statement id), linked by the route the statement is read under (CANONICAL_MODEL 8.1). All live payrolls and statements are OPEN: calculated, not finalized (D-030).
- The payrolls list is the run source; the payroll detail only adds date_finalized: its other fields equal the list entry (24 of 24 read both ways), so they are excluded (D-081). The statement list only enumerates statements; its fields equal the detail's (18 of 18), which is the record source.
- Pay periods: one pay_periods entry from start_date and end_date; pay_group_id is null with not_provided (payrolls name no pay period profile). Paycheck pay_group_id likewise.
- Tax lines: each taxes[] item gives one employee line (ee_ fields) and one employer line (er_ fields) that keep the same source_line_id; a side with wage figures but no amount keeps its wages with amount null (CANONICAL_MODEL 8.4). Tax type and level from the exact company_tax.name (ukg-ready.tax_label, inferred, D-056); partial names such as 'Wisconsin' are unknown. jurisdiction is null with not_provided.
- Deduction er_amount is an employer contribution line linked to the same deduction code (CANONICAL_MODEL 8.4). Payments: type_name Check and Direct Deposit are cash; Fringe is non_cash and not part of net pay. net_pay is derived from Check and Direct Deposit amounts only when each has an amount, else null with reconciliation_incomplete; gross_pay, gross_wages and total_earnings are null with not_provided (D-052, D-053).

| Route | Source field | Use | Canonical field | Transform | Evidence | Reason or note |
| --- | --- | --- | --- | --- | --- | --- |
| `/v2/companies/{cid}/payrolls` | `payrolls[].id` | mapped | `PayrollRun.source_ids` | source_id | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls.html` |  |
| `/v2/companies/{cid}/payrolls` | `payrolls[].name` | mapped | `PayrollRun.name` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls.html` |  |
| `/v2/companies/{cid}/payrolls` | `payrolls[].type.display_name` | mapped | `PayrollRun.run_type` | code:ukg-ready.payroll_type | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls.html`<br>live: Regular 67 |  |
| `/v2/companies/{cid}/payrolls` | `payrolls[].type.id` | extension | `PayrollRun.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls.html` | Payroll type id (the label is mapped). |
| `/v2/companies/{cid}/payrolls` | `payrolls[].status` | mapped | `PayrollRun.status` | code:ukg-ready.payroll_status | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls.html`<br>D-030<br>live: OPEN 67 |  |
| `/v2/companies/{cid}/payrolls` | `payrolls[].pay_date` | mapped | `PayrollRun.pay_date` | date:event | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls.html` |  |
| `/v2/companies/{cid}/payrolls` | `payrolls[].start_date` | mapped | `PayrollRun.pay_periods[].period_start` | date:period_start | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls.html` |  |
| `/v2/companies/{cid}/payrolls` | `payrolls[].end_date` | mapped | `PayrollRun.pay_periods[].period_end` | date:period_end | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls.html` |  |
| `/v2/companies/{cid}/payrolls` | `payrolls[].ein.id` | mapped | `PayrollRun.tax_entity_id` | reference | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls.html`<br>D-029 | Canonical tax entity id (company, ein id). |
| `/v2/companies/{cid}/payrolls` | `payrolls[].*` | extension | `PayrollRun.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls.html` | Payroll settings: direct deposit date, scheduled submit time, billable flag, invoice generator, default statement type and stub note, adjustment year-to-date source payroll. |
| `/v2/companies/{cid}/payrolls` | `payrolls[]._links.*` | excluded |  |  |  | Hypermedia links and counters (API navigation), not data. |
| `/v2/companies/{cid}/payrolls/{id}` | `id` | mapped | `PayrollRun.source_ids` | join | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id).html` | Joins the payroll from the list. |
| `/v2/companies/{cid}/payrolls/{id}` | `date_finalized` | mapped | `PayrollRun.finalized_date` | date:event | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id).html` | Absent on 24 of 24 live details (all OPEN). |
| `/v2/companies/{cid}/payrolls/{id}` | `*` | excluded |  |  |  | Equals the list entry (24 of 24); read from the list (D-081). |
| `/v2/companies/{cid}/payrolls/{id}` | `type.*` | excluded |  |  |  | Equals the list entry (24 of 24); read from the list (D-081). |
| `/v2/companies/{cid}/payrolls/{id}` | `ein.*` | excluded |  |  |  | Equals the list entry (24 of 24); read from the list (D-081). |
| `/v2/companies/{cid}/payrolls/{id}` | `ein.ein_country_id` | excluded (live only) |  |  | live: not in the documented schema | Equals the list entry; read from the list. |
| `/v2/companies/{cid}/payrolls/{id}/batches` | `batches[].**` | extension | `PayrollRun.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__batches.html` | Payroll batches (name, status, type, master flag): how input was grouped, not pay (live: 4 batches, Regular Earnings, CLOSED). |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements` | `pay_statements[].id` | mapped | `Paycheck.source_ids` | join | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements.html` | Enumerates statements; each is read from the detail route. |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements` | `pay_statements[].**` | excluded |  |  |  | Equal to the detail's fields (18 of 18); read from the detail (D-081). |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements` | `pay_statements[].employee.account_id` | excluded (live only) |  |  | live: not in the documented schema | Equal to the detail's; read from the detail. |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements` | `pay_statements[].calcUpto` | excluded (live only) |  |  | live: not in the documented schema | Equal to the detail's; read from the detail. |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements` | `pay_statements[].emptyEarning` | excluded (live only) |  |  | live: not in the documented schema | Equal to the detail's; read from the detail. |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `id` | mapped | `Paycheck.source_ids` | source_id | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html` |  |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `employee.account_id` | mapped | `Paycheck.employee_id` | reference | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html` |  |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `status` | mapped | `Paycheck.status` | code:ukg-ready.statement_status | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html`<br>D-030<br>live: OPEN 18 of 18 |  |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `type.display_name` | mapped | `Paycheck.kind` | code:ukg-ready.statement_type | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html`<br>live: Regular 18 of 18 |  |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `type.id` | extension | `Paycheck.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html` | Statement type id (the label is mapped). |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `pay_date` | mapped | `Paycheck.pay_date` | date:event | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html` |  |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `pay_period_start` | mapped | `Paycheck.period_start` | date:period_start | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html` |  |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `pay_period_end` | mapped | `Paycheck.period_end` | date:period_end | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html` |  |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `calcUpto` | extension (live only) | `Paycheck.provider_extensions` |  | live: not in the documented schema | Calculation state (undocumented). |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `emptyEarning` | extension (live only) | `Paycheck.provider_extensions` |  | live: not in the documented schema | Calculation flag (undocumented). |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `messages[].**` | extension | `Paycheck.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html` | Calculation messages: they explain why a statement is not final (CANONICAL_MODEL 8.6). |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `earnings[].id` | mapped | `Paycheck.earnings[].source_line_id` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html` |  |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `earnings[].earning.id` | mapped (live only) | `Paycheck.earnings[].earning_code_id` | reference | live: earning.id on every sampled line; not in the documented schema | Canonical id of the lookup/earning-codes entry with this id. |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `earnings[].earning.code` | mapped | `Paycheck.earnings[].earning_code.code` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html` |  |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `earnings[].earning.name` | mapped | `Paycheck.earnings[].earning_code.name` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html` |  |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `earnings[].type_name` | mapped | `Paycheck.earnings[].pay_class` | code:ukg-ready.earning_type_name | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html`<br>D-031 |  |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `earnings[].hours` | mapped | `Paycheck.earnings[].hours` | ms_to_hours | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html`<br>D-028 |  |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `earnings[].base_rate` | mapped | `Paycheck.earnings[].rate` | number | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html` |  |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `earnings[].ee_amount` | mapped | `Paycheck.earnings[].amount` | number | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html`<br>D-053 | Absent key: null with not_provided, never zero. |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `earnings[].quantity` | extension | `Paycheck.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html` | No documented unit (unit rule, CANONICAL_MODEL 8.3). |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `earnings[].earning.external_id` | extension | `Paycheck.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html` | Integration id of the code. |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `earnings[].**` | extension | `Paycheck.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html` | Line context: batch, cost centers, date range, shift, workers' comp code (CANONICAL_MODEL 8.6). |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `deductions[].id` | mapped | `Paycheck.deductions[].source_line_id` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html` |  |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `deductions[].deduction.id` | mapped (live only) | `Paycheck.deductions[].deduction_code_id` | reference | live: deduction.id on every sampled line; not in the documented schema | Canonical id of the lookup/deduction-codes entry with this id. |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `deductions[].deduction.code` | mapped | `Paycheck.deductions[].deduction_code.code` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html` |  |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `deductions[].deduction.name` | mapped | `Paycheck.deductions[].deduction_code.name` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html` |  |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `deductions[].ee_amount` | mapped | `Paycheck.deductions[].amount` | number | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html`<br>D-053 |  |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `deductions[].er_amount` | mapped | `Paycheck.employer_contributions[].amount` | number | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html`<br>live: 25 deduction lines | One contribution line linked to the same deduction code (deduction_code_id). |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `deductions[].type_name` | extension | `Paycheck.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html` | Line type label ('Deduction (Auto)' 41 of 41). |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `deductions[].quantity` | extension | `Paycheck.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html` | No documented unit. |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `deductions[].base_rate` | extension | `Paycheck.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html` | Rate of the deduction line; DeductionLine has no rate. |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `deductions[].deduction.external_id` | extension | `Paycheck.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html` | Integration id of the code. |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `deductions[].vendor.*` | extension | `Paycheck.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html` | Deduction vendor. |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `deductions[].ee_gross_subject_wage` | extension (live only) | `Paycheck.provider_extensions` |  | live: not in the documented schema | Wage figure on a deduction line; meaning undocumented (CANONICAL_MODEL 8.6). |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `deductions[].ee_gross_wage` | extension (live only) | `Paycheck.provider_extensions` |  | live: not in the documented schema | Wage figure on a deduction line; meaning undocumented (CANONICAL_MODEL 8.6). |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `deductions[].ee_subject_wage` | extension (live only) | `Paycheck.provider_extensions` |  | live: not in the documented schema | Wage figure on a deduction line; meaning undocumented (CANONICAL_MODEL 8.6). |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `deductions[].**` | extension | `Paycheck.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html` | Line context: batch, cost centers, date range, shift, workers' comp code (CANONICAL_MODEL 8.6). |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `taxes[].id` | mapped | `Paycheck.taxes[].source_line_id` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html` | Shared by the employee and employer lines. |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `taxes[].company_tax.id` | mapped (live only) | `Paycheck.taxes[].tax_code.source_id` | copy | live: company_tax.id on every sampled line; not in the documented schema |  |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `taxes[].company_tax.code` | mapped | `Paycheck.taxes[].tax_code.code` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html` |  |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `taxes[].company_tax.name` | mapped | `Paycheck.taxes[].tax_type` | code:ukg-ready.tax_label | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html`<br>D-056 | Also kept in tax_code.name; sets jurisdiction_level from the same table. |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `taxes[].company_tax.abbrev` | extension | `Paycheck.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html` | Abbreviation next to the code and name. |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `taxes[].company_tax.external_id` | extension (live only) | `Paycheck.provider_extensions` |  | live: not in the documented schema | Integration id of the tax. |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `taxes[].ee_amount` | mapped | `Paycheck.taxes[].amount` | number | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html`<br>D-053 | Employee line. |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `taxes[].er_amount` | mapped | `Paycheck.taxes[].amount` | number | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html`<br>D-053 | Employer line. |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `taxes[].ee_subject_wage` | mapped | `Paycheck.taxes[].taxable_wages` | number | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html` | Employee line; subject wage read as the wages subject to the tax. |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `taxes[].er_subject_wage` | mapped | `Paycheck.taxes[].taxable_wages` | number | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html` | Employer line. |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `taxes[].ee_gross_wage` | mapped | `Paycheck.taxes[].gross_wages` | number | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html` | Employee line. |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `taxes[].er_gross_wage` | mapped | `Paycheck.taxes[].gross_wages` | number | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html` | Employer line. |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `taxes[].ee_gross_subject_wage` | extension | `Paycheck.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html` | Gross subject wage: no matching TaxLine field. |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `taxes[].er_gross_subject_wage` | extension | `Paycheck.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html` | Gross subject wage: no matching TaxLine field. |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `taxes[].type_name` | extension | `Paycheck.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html` | Line type label ('Tax'). |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `taxes[].batch.*` | extension | `Paycheck.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html` | Line context: batch, cost centers, date range, shift, workers' comp code (CANONICAL_MODEL 8.6). |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `payments[].id` | mapped | `Paycheck.payments[].source_line_id` | copy | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html` |  |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `payments[].type_name` | mapped | `Paycheck.payments[].method` | code:ukg-ready.payment_type | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html`<br>live: Check 18, Fringe 8, Direct Deposit 5 (18 statements) |  |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `payments[].ee_amount` | mapped | `Paycheck.payments[].amount` | number | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html`<br>D-053<br>live: absent on 5 of 18 Check payments | Absent key: null with not_provided, never zero. |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `payments[].hours` | extension | `Paycheck.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html` | Hours on a payment line (meaning undocumented). |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `payments[].quantity` | extension | `Paycheck.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html` | No documented unit. |
| `/v2/companies/{cid}/payrolls/{id}/pay-statements/{id}` | `payments[].batch.*` | extension | `Paycheck.provider_extensions` |  | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html` | Line context: batch, cost centers, date range, shift, workers' comp code (CANONICAL_MODEL 8.6). |

### Code table `ukg-ready.period_type`

Source: /v2/companies/{cid}/lookup/pay-period-profiles items[].period_type.type (documented enum). value: `PayFrequency`

| Raw code | Label | value | Evidence | Note |
| --- | --- | --- | --- | --- |
| `weekly` |  | weekly (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__lookup__pay-period-profiles.html`<br>live: 1 of 12 profiles |  |
| `every_n_weeks:1` |  | weekly (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__lookup__pay-period-profiles.html`<br>D-041 |  |
| `every_n_weeks:2` |  | biweekly (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__lookup__pay-period-profiles.html`<br>D-041<br>live: 5 of 12 profiles |  |
| `semi_monthly` |  | semimonthly (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__lookup__pay-period-profiles.html`<br>live: 3 of 12 profiles |  |
| `monthly` |  | monthly (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__lookup__pay-period-profiles.html`<br>live: 1 of 12 profiles |  |
| `monthly_weekday` |  | monthly (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__lookup__pay-period-profiles.html` |  |
| `quarterly` |  | quarterly (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__lookup__pay-period-profiles.html` |  |
| `every_n_days:1` |  | daily (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__lookup__pay-period-profiles.html` | Other day counts are not in the table: unknown with an unknown_code diagnostic. |
| `user_defined` |  | unknown (unmapped) | D-041<br>live: 2 of 12 profiles |  |

### Code table `ukg-ready.employee_status`

Source: employee detail status (labels; no documented list). value: `EmploymentStatus`

| Raw code | Label | value | Evidence | Note |
| --- | --- | --- | --- | --- |
| `Active` | Active | active (inferred) | live: 50 of 103 accounts | Provider label; other labels are unknown with unknown_code. |
| `Terminated` | Terminated | terminated (inferred) | live: 53 of 103 accounts |  |

### Code table `ukg-ready.national_id_type`

Source: employee detail national_id_numbers[].type (documented enum). value: `NationalIdType`

| Raw code | Label | value | Evidence | Note |
| --- | --- | --- | --- | --- |
| `SSN` |  | ssn (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html`<br>live: 3 of 3 details |  |
| `SIN` |  | sin (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` |  |
| `NO_ID_NEEDED` |  | not_required (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` |  |
| `BSN` |  | unknown (unmapped) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` | Documented, but no canonical value (Dutch citizen service number). |
| `NIN` |  | unknown (unmapped) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` | Documented, but no canonical value. |
| `TFN` |  | unknown (unmapped) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` | Documented, but no canonical value. |
| `NSS` |  | unknown (unmapped) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` | Documented, but no canonical value. |
| `OTHER_1` |  | unknown (unmapped) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid).html` | OTHER_1 to OTHER_10 are documented placeholders; OTHER_2 to OTHER_10 are unknown the same way (not listed). |

### Code table `ukg-ready.gender`

Source: demographics gender (documented enum). value: `Gender`

| Raw code | Label | value | Evidence | Note |
| --- | --- | --- | --- | --- |
| `MALE` |  | male (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__demographics.html` |  |
| `FEMALE` |  | female (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__demographics.html` |  |
| `UNDEFINED` |  | unknown (unmapped) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__demographics.html` | Not stated whether this means not disclosed or not set. |

### Code table `ukg-ready.ethnicity`

Source: demographics ethnicity (documented enum). value: `Ethnicity`

| Raw code | Label | value | Evidence | Note |
| --- | --- | --- | --- | --- |
| `HISPANIC_OR_LATINO` |  | hispanic_or_latino (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__demographics.html` |  |
| `WHITE` |  | white (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__demographics.html` |  |
| `BLACK_OR_AFRICAN_AMERICAN` |  | black_or_african_american (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__demographics.html` |  |
| `NATIVE_HAWAIIAN_OR_OTHER_PACIFIC_ISLANDER` |  | native_hawaiian_or_pacific_islander (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__demographics.html` |  |
| `ASIAN` |  | asian (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__demographics.html` |  |
| `AMERICAN_INDIAN_OR_ALASKA_NATIVE` |  | american_indian_or_alaska_native (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__demographics.html` |  |
| `TWO_OR_MORE_RACES` |  | two_or_more_races (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__demographics.html` |  |

### Code table `ukg-ready.citizenship`

Source: demographics citizenship (documented enum). value: `CitizenshipStatus`

| Raw code | Label | value | Evidence | Note |
| --- | --- | --- | --- | --- |
| `US_CITIZEN` |  | citizen (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__demographics.html` |  |
| `NONCITIZEN_NATIONAL_OF_US` |  | noncitizen_national (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__demographics.html` |  |
| `PERMANENT_RESIDENT` |  | permanent_resident (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__demographics.html` |  |
| `ALIEN_WITH_WORK_PERMIT` |  | authorized_alien (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__demographics.html` |  |

### Code table `ukg-ready.eeo_classification`

Source: pay-info eeo_classification (documented enum, EEO-1 categories). value: `EeoJobCategory`

| Raw code | Label | value | Evidence | Note |
| --- | --- | --- | --- | --- |
| `EXECUTIVE_OR_SENIOR_LEVEL_OFFICIALS_AND_MANAGERS` |  | executives_senior_officials (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__pay-info.html` |  |
| `FIRST_OR_MID_LEVEL_OFFICIALS_AND_MANAGERS` |  | first_mid_level_managers (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__pay-info.html` |  |
| `PROFESSIONALS` |  | professionals (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__pay-info.html` |  |
| `TECHNICIANS` |  | technicians (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__pay-info.html` |  |
| `SALES_WORKERS` |  | sales_workers (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__pay-info.html` |  |
| `ADMINISTRATIVE_SUPPORT_WORKERS` |  | administrative_support (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__pay-info.html` |  |
| `CRAFT_WORKERS` |  | craft_workers (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__pay-info.html` |  |
| `OPERATIVES` |  | operatives (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__pay-info.html` |  |
| `LABORERS_AND_HELPERS` |  | laborers_helpers (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__pay-info.html` |  |
| `SERVICE_WORKERS` |  | service_workers (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__pay-info.html`<br>live: 1 of 3 |  |

### Code table `ukg-ready.amount_period`

Source: compensation history amount_period (documented enum). value: `RatePeriod`

| Raw code | Label | value | Evidence | Note |
| --- | --- | --- | --- | --- |
| `HOUR` |  | hour (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__compensation__history.html` |  |
| `WEEK` |  | week (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__compensation__history.html` |  |
| `PAY_PERIOD` |  | pay_period (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__compensation__history.html` |  |
| `MONTH` |  | month (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__compensation__history.html` |  |
| `YEAR` |  | year (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__compensation__history.html` |  |

### Code table `ukg-ready.time_period`

Source: compensation history time_period (documented enum). value: `RatePeriod`

| Raw code | Label | value | Evidence | Note |
| --- | --- | --- | --- | --- |
| `WEEK` |  | week (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__compensation__history.html` |  |
| `PAY_PERIOD` |  | pay_period (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__compensation__history.html`<br>D-028 |  |
| `MONTH` |  | month (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__compensation__history.html` |  |
| `YEAR` |  | year (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__compensation__history.html`<br>D-028 |  |

### Code table `ukg-ready.pay_type`

Source: lookup/pay-types name, joined through pay-info pay_type.id. value: `PayType`

| Raw code | Label | value | Evidence | Note |
| --- | --- | --- | --- | --- |
| `Hourly` | Hourly | hourly (inferred) | live: lookup/pay-types (2 entries) | Names in a company lookup; whether a company can define its own pay types is not documented, so the reading is inferred. |
| `Salaried` | Salaried | salary (inferred) | live: lookup/pay-types (2 entries) |  |

### Code table `ukg-ready.contact_relationship`

Source: contacts contacts[].relationship (a label; no documented list). value: `Relationship`

| Raw code | Label | value | Evidence | Note |
| --- | --- | --- | --- | --- |
| `Spouse` | Spouse | spouse (inferred) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__contacts.html`<br>live: 1 of 2 contacts | The docs example uses 'Spouse'; no list of labels is documented. |
| `Child` | Child | child (inferred) | live: 1 of 2 contacts |  |

### Code table `ukg-ready.deposit_calc_method`

Source: direct-deposits calc_method.type (documented enum). value: `AllocationType`

| Raw code | Label | value | Evidence | Note |
| --- | --- | --- | --- | --- |
| `FULL` |  | remainder (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__direct-deposits.html`<br>live: 14 |  |
| `FLAT_AMOUNT` |  | fixed_amount (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__direct-deposits.html`<br>live: 2 |  |
| `NET_PAY` |  | percent (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__direct-deposits.html`<br>live: 2 | percent_basis net_pay. |
| `GROSS_EARNING` |  | percent (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__direct-deposits.html` | percent_basis gross_pay. |
| `DIRECT_DEPOSIT_PER_OF_REMAINDER` |  | percent (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__direct-deposits.html` | percent_basis remainder_after_fixed. |

### Code table `ukg-ready.deposit_account_type`

Source: direct-deposits account_type (documented enum). value: `AccountType`

| Raw code | Label | value | Evidence | Note |
| --- | --- | --- | --- | --- |
| `CHECKING` |  | checking (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__direct-deposits.html`<br>live: 16 |  |
| `SAVINGS` |  | savings (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__direct-deposits.html`<br>live: 2 |  |

### Code table `ukg-ready.prenote_status`

Source: direct-deposits pre_note_status (documented enum). value: `PrenoteStatus`

| Raw code | Label | value | Evidence | Note |
| --- | --- | --- | --- | --- |
| `READY_TO_SEND` |  | pending (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__direct-deposits.html`<br>live: 9 |  |
| `SENT` |  | sent (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__direct-deposits.html` |  |
| `COMPLETE_OK` |  | verified (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__direct-deposits.html` |  |
| `COMPLETE_EXPIRED` |  | expired (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__direct-deposits.html`<br>live: 4 |  |
| `CANCELED` |  | canceled (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__direct-deposits.html`<br>live: 5 |  |
| `INVALID` |  | invalid (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__direct-deposits.html` |  |
| `NA` |  | unknown (unmapped) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__direct-deposits.html` | Not applicable: no pre-note state. |

### Code table `ukg-ready.deposit_frequency`

Source: direct-deposits payroll_frequency.type (documented enum). value: `DepositFrequency`

| Raw code | Label | value | Evidence | Note |
| --- | --- | --- | --- | --- |
| `EVERY_PAY` |  | every_pay (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__direct-deposits.html`<br>live: 18 |  |
| `EVERY_SCHEDULED_PAY` |  | every_scheduled_pay (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__direct-deposits.html` |  |
| `EVERY_OTHER_SCHEDULED_PAY` |  | every_other_scheduled_pay (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__direct-deposits.html` |  |
| `MONTHLY` |  | monthly (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__direct-deposits.html` |  |
| `QUARTERLY` |  | quarterly (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__direct-deposits.html` |  |
| `ANNUAL` |  | annual (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__direct-deposits.html` |  |
| `MANUAL` |  | manual (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__direct-deposits.html` |  |
| `EVERY_SCHEDULED_MONTH_ODD_PAY` |  | unknown (unmapped) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__direct-deposits.html` | No canonical value. |
| `EVERY_SCHEDULED_MONTH_EVEN_PAY` |  | unknown (unmapped) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__direct-deposits.html` | No canonical value. |
| `HOLIDAY_TABLE` |  | unknown (unmapped) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__direct-deposits.html` | No canonical value. |
| `BENEFIT_PLAN` |  | unknown (unmapped) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__employees__(aid)__direct-deposits.html` | No canonical value. |

### Code table `ukg-ready.coverage_level`

Source: benefits coverage_level (company-defined labels). coverage_level: `CoverageLevel`, status: `EnrollmentStatus`

| Raw code | Label | coverage_level | status | Evidence | Note |
| --- | --- | --- | --- | --- | --- |
| `Employee` |  | employee_only (inferred) | unknown (unmapped) | live: 4 |  |
| `Waived` |  | unknown (unmapped) | waived (inferred) | live: 5 |  |
| `Enter total annual contribution` |  | unknown (unmapped) | unknown (unmapped) | live: 1 |  |
| `75% Option` |  | unknown (unmapped) | unknown (unmapped) | live: 1 |  |

### Code table `ukg-ready.payroll_type`

Source: payrolls type.display_name (labels; lookup/payroll-types not called). value: `PayrollRunType`

| Raw code | Label | value | Evidence | Note |
| --- | --- | --- | --- | --- |
| `Regular` | Regular | regular (inferred) | live: 67 payrolls<br>D-050 | Provider label with no documented list: read from the label, so inferred (CANONICAL_MODEL 1.7, D-081); other labels are unknown with unknown_code. |

### Code table `ukg-ready.payroll_status`

Source: payrolls status (documented enum). value: `PayrollRunStatus`

| Raw code | Label | value | Evidence | Note |
| --- | --- | --- | --- | --- |
| `NEW` |  | new (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls.html` |  |
| `OPEN` |  | open (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls.html`<br>D-030<br>live: 67 |  |
| `CLOSED` |  | closed (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls.html` |  |
| `SUBMITTED` |  | submitted (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls.html` |  |
| `FINALIZED` |  | finalized (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls.html` |  |
| `OPEN_FAILED` |  | failed (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls.html` |  |
| `CLOSE_FAILED` |  | failed (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls.html` |  |
| `ROLLBACK_FAILED` |  | failed (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls.html` |  |
| `FINALIZE_FAILED` |  | failed (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls.html` |  |

### Code table `ukg-ready.statement_status`

Source: pay statement status (documented enum). value: `PaycheckStatus`

| Raw code | Label | value | Evidence | Note |
| --- | --- | --- | --- | --- |
| `INVALID` |  | invalid (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html` |  |
| `NEW` |  | new (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html` |  |
| `OPEN` |  | open (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html`<br>D-030<br>live: 18 of 18 |  |
| `CLOSED` |  | closed (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html` |  |
| `FINALIZED` |  | finalized (documented) | `contracts/ukg-ready/reference-docs/res/__v2__companies__(cid)__payrolls__(id)__pay-statements__(id).html` |  |

### Code table `ukg-ready.statement_type`

Source: pay statement type.display_name (labels). value: `PaycheckKind`

| Raw code | Label | value | Evidence | Note |
| --- | --- | --- | --- | --- |
| `Regular` | Regular | regular (inferred) | live: 18 of 18 | Provider label with no documented list: read from the label, so inferred (CANONICAL_MODEL 1.7, D-081); other labels are unknown with unknown_code. |

### Code table `ukg-ready.earning_type_name`

Source: pay statement earnings[].type_name (labels). value: `EarningClass`

| Raw code | Label | value | Evidence | Note |
| --- | --- | --- | --- | --- |
| `Earning (Fringe, Auto)` |  | non_cash_fringe (inferred) | live: 8 lines<br>D-031 | Provisional (D-031): offset by Fringe payment lines. |
| `Earning` |  | unknown (unmapped) | live: 19 lines | Does not say wages or another class. |
| `Earning (Auto)` |  | unknown (unmapped) | live: 7 lines |  |
| `Earning (Auto Reduce)` |  | unknown (unmapped) | live: 4 lines |  |

### Code table `ukg-ready.payment_type`

Source: pay statement payments[].type_name (labels). value: `PaymentMethod`

| Raw code | Label | value | Evidence | Note |
| --- | --- | --- | --- | --- |
| `Check` | Check | check (inferred) | live: 18 lines |  |
| `Direct Deposit` | Direct Deposit | direct_deposit (inferred) | live: 5 lines |  |
| `Fringe` | Fringe | non_cash (inferred) | live: 8 lines<br>D-052 | Offsets non-cash earnings; not part of net pay. |

### Code table `ukg-ready.tax_label`

Source: pay statement taxes[].company_tax.name: exact names only (D-056, D-081); other names are unknown with unknown_code. tax_type: `TaxType`, jurisdiction_level: `TaxJurisdictionLevel`

| Raw code | Label | tax_type | jurisdiction_level | Evidence | Note |
| --- | --- | --- | --- | --- | --- |
| `Federal Income Tax` |  | federal_income (inferred) | federal (inferred) | live: 18 lines<br>D-056 |  |
| `Social Security` |  | social_security (inferred) | federal (inferred) | live: 10 lines<br>D-056 |  |
| `OASDI` |  | social_security (inferred) | federal (inferred) | live: 8 lines<br>D-056 | Old-Age, Survivors and Disability Insurance: Social Security (code FICA). |
| `Medicare` |  | medicare (inferred) | federal (inferred) | live: 18 lines<br>D-056 |  |
| `Additional Medicare` |  | additional_medicare (inferred) | federal (inferred) | live: 18 lines<br>D-056 |  |
| `Federal Unemployment Tax` |  | federal_unemployment (inferred) | federal (inferred) | live: 8 lines<br>D-056 |  |
| `ER SUTA Wisconsin` |  | state_unemployment (inferred) | state (inferred) | live: 8 lines<br>D-056 |  |
