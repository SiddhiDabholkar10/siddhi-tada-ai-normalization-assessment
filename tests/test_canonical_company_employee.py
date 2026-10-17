"""Tests for the canonical Company and Employee records (Phase 2, step 2). Synthetic values only."""
import json
import unittest
from datetime import date

from pydantic import ValidationError

from normalization.canonical import (
    Coded,
    Company,
    Employee,
    EntityType,
    MappingBasis,
    Provider,
    SourceRef,
    ValueStatus,
    canonical_id,
    sensitive_fields,
    to_json,
)
from normalization.canonical.benefits import BenefitEnrollment
from normalization.canonical.company import PayGroup, TaxEntity, WorkLocation
from normalization.canonical.deductions import DeductionSetup
from normalization.canonical.deposits import DirectDeposit
from normalization.canonical.employee import (
    Compensation,
    Employment,
    EmploymentPeriod,
    JobAssignment,
    NationalId,
    OrgUnit,
    PersonalContact,
    Phone,
    PtoBalance,
    Qualification,
    RelatedPerson,
    TaxWithholding,
    TaxWithholdingSetting,
    WorkAuthorization,
)
from normalization.canonical.enums import (
    AddressType,
    EmploymentStatus,
    FilingStatus,
    Gender,
    NationalIdType,
    OrgUnitType,
    PayFrequency,
    PhoneType,
    QualificationType,
    Relationship,
    TaxJurisdictionLevel,
    TaxResidency,
    WorkerType,
)
from normalization.canonical.links import find_link_problems
from normalization.canonical.parts import PersonalAddress, PersonName
from normalization.canonical.payroll import Paycheck, PayrollRun

P, T = Provider.UKG_READY, "833341"
COMPANY_ID = canonical_id(P, T, EntityType.COMPANY, "33704016")
EIN_ID = canonical_id(P, T, EntityType.TAX_ENTITY, "33704016", "35419520")
LOCATION_ID = canonical_id(P, T, EntityType.WORK_LOCATION, "33704016", "100")
PAY_GROUP_ID = canonical_id(P, T, EntityType.PAY_GROUP, "33704016", "36562688")
EMPLOYEE_ID = canonical_id(P, T, EntityType.EMPLOYEE, "33704016", "1001")
MANAGER_ID = canonical_id(P, T, EntityType.EMPLOYEE, "33704016", "1000")
SOURCE = SourceRef(endpoint="GET /v2/companies/{cid}/employees/{aid}", locator="")
NP = ValueStatus.NOT_PROVIDED


def explained(cls, **values):
    """Build ``cls`` with every optional field not given left null and explained as
    not_provided. A ``field_status`` passed in is merged on top."""
    given_status = values.pop("field_status", {})
    missing = {
        name: NP
        for name, info in cls.model_fields.items()
        if name not in values and not info.is_required() and info.default_factory is None
    }
    return cls(**values, field_status={**missing, **given_status})


def coded(enum, value, raw, basis=MappingBasis.DOCUMENTED):
    return Coded[enum](value=value, raw_code=raw, basis=basis)


def company(**overrides):
    values = {
        "id": COMPANY_ID,
        "provider": P,
        "tenant_id": T,
        "source_ids": {"cid": "33704016"},
        "sources": [SourceRef(endpoint="POST /signin", locator="/context/companies/0")],
        "tax_entities": [explained(TaxEntity, id=EIN_ID, name="Primary EIN", ein="12-3456789")],
        "work_locations": [explained(WorkLocation, id=LOCATION_ID, code="100", name="Main office")],
        "pay_groups": [
            explained(
                PayGroup,
                id=PAY_GROUP_ID,
                name="Primary-EIN Regular Bi-Weekly",
                pay_frequency=coded(PayFrequency, PayFrequency.BIWEEKLY, "every_n_weeks"),
            )
        ],
    }
    values.update(overrides)
    return explained(Company, **values)


def employee(**overrides):
    values = {
        "id": EMPLOYEE_ID,
        "provider": P,
        "tenant_id": T,
        "source_ids": {"cid": "33704016", "aid": "1001"},
        "sources": [SOURCE],
        "company_id": COMPANY_ID,
        "tax_entity_id": EIN_ID,
        "person_ref": "1001",
        "name": explained(PersonName, first="Alex", last="Example"),
        "national_ids": [
            explained(NationalId, type=coded(NationalIdType, NationalIdType.SSN, "SSN"), value="000-00-0000")
        ],
        "personal_contact": explained(
            PersonalContact,
            addresses=[explained(PersonalAddress, type=AddressType.HOME, line1="1 Main St", city="Springfield", state="IL")],
            phones=[explained(Phone, type=PhoneType.MOBILE, number="555-0100")],
        ),
        "employment": explained(
            Employment,
            status=coded(EmploymentStatus, EmploymentStatus.ACTIVE, "Active"),
            worker_type=coded(WorkerType, WorkerType.CONTRACTOR, "1099", MappingBasis.INFERRED),
            hire_date=date(2019, 8, 5),
        ),
        "employment_history": [
            explained(EmploymentPeriod, employment_id="2766849", status=coded(EmploymentStatus, EmploymentStatus.ACTIVE, "Active")),
            explained(EmploymentPeriod, employment_id="2766749", status=coded(EmploymentStatus, EmploymentStatus.TERMINATED, "Terminated")),
        ],
        "job": explained(JobAssignment, work_location_id=LOCATION_ID, manager_employee_id=MANAGER_ID),
        "compensation": explained(Compensation, pay_group_id=PAY_GROUP_ID, hourly_rate="23.50"),
        "currency": "USD",
    }
    values.update(overrides)
    return explained(Employee, **values)


class CompanyTests(unittest.TestCase):
    def test_minimal_records_need_only_identity_and_the_employees_company(self):
        record = explained(Company, id=COMPANY_ID, provider=P, tenant_id=T, source_ids={"cid": "33704016"}, sources=[SOURCE])
        self.assertEqual((record.tax_entities, record.field_status["legal_name"]), (None, NP))
        minimal = explained(Employee, id=EMPLOYEE_ID, provider=P, tenant_id=T, source_ids={"aid": "1001"}, sources=[SOURCE], company_id=COMPANY_ID)
        self.assertEqual(minimal.field_status["tax_entity_id"], NP)
        values = employee().model_dump()
        del values["company_id"]
        with self.assertRaises(ValidationError):
            Employee(**values)

    def test_owned_entries_have_ids_of_their_type_tenant_and_unique(self):
        from test_canonical_deposits_deductions_benefits import code_entry  # builders that import this module
        from test_canonical_payroll import earning_code
        cases = (  # owned list, its entity, an entry with an id of another type, a valid entry
            ("tax_entities", "tax_entity", explained(TaxEntity, id=LOCATION_ID), explained(TaxEntity, id=EIN_ID)),
            ("work_locations", "work_location", explained(WorkLocation, id=EIN_ID), explained(WorkLocation, id=LOCATION_ID)),
            ("deduction_codes", "deduction_code", code_entry(MANAGER_ID), code_entry()),
            ("earning_codes", "earning_code", earning_code(EIN_ID), earning_code()),
        )
        for name, entity, wrong, valid in cases:
            with self.subTest(owned=name):
                with self.assertRaisesRegex(ValidationError, rf"{name}\[0\].id .* is not a {entity} id"):
                    company(**{name: [wrong]})
                with self.assertRaisesRegex(ValidationError, f"{name} has duplicate ids"):
                    company(**{name: [valid, valid]})
        other_tenant = explained(TaxEntity, id=canonical_id(P, "999", EntityType.TAX_ENTITY, "1"))
        with self.assertRaisesRegex(ValidationError, "belongs to another provider or tenant"):
            company(tax_entities=[other_tenant])

    def test_owned_entries_keep_their_provider_settings(self):
        # D-063: settings with no canonical meaning stay with their entry, not on the company.
        location = explained(WorkLocation, id=LOCATION_ID, provider_extensions={"workCompState": "UT", "latitude": 40.76})
        output = json.loads(to_json(company(work_locations=[location])))
        self.assertEqual(output["work_locations"][0]["provider_extensions"], {"workCompState": "UT", "latitude": 40.76})
        self.assertEqual(explained(TaxEntity, id=EIN_ID).provider_extensions, {})
        with self.assertRaises(ValidationError):
            explained(PayGroup, id=PAY_GROUP_ID, provider_extensions={"bad": object()})


class EmployeeTests(unittest.TestCase):
    def test_full_employee_is_valid_and_round_trips(self):
        record = employee()
        self.assertEqual(Employee.model_validate_json(to_json(record)), record)

    def test_references_point_at_their_entity_within_provider_and_tenant(self):
        valid = explained(JobAssignment, work_location_id=LOCATION_ID)
        cases = [
            ({"company_id": EMPLOYEE_ID}, "company_id .* is not a company id"),
            ({"tax_entity_id": COMPANY_ID}, "tax_entity_id .* is not a tax_entity id"),
            ({"job": explained(JobAssignment, manager_employee_id=COMPANY_ID)}, "job.manager_employee_id"),
            ({"job": explained(JobAssignment, work_location_id=PAY_GROUP_ID)}, "job.work_location_id"),
            ({"compensation": explained(Compensation, pay_group_id=LOCATION_ID)}, "compensation.pay_group_id"),
            ({"job_history": [valid, explained(JobAssignment, manager_employee_id=COMPANY_ID)]}, r"job_history\[1\].manager_employee_id"),
            ({"job_history": [valid, explained(JobAssignment, supervisor_employee_id=LOCATION_ID)]}, r"job_history\[1\].supervisor_employee_id"),
            ({"job_history": [valid, explained(JobAssignment, work_location_id=PAY_GROUP_ID)]}, r"job_history\[1\].work_location_id"),
            ({"company_id": canonical_id(Provider.ISOLVED, "255938", EntityType.COMPANY, "5797")}, "belongs to another provider or tenant"),
        ]
        for override, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValidationError, message):
                    employee(**override)

    def test_job_history_entries_may_change_one_thing_only(self):
        # D-069: a PrismHR department change carries only the department; the rest is not provided.
        department = explained(OrgUnit, type=coded(OrgUnitType, OrgUnitType.DEPARTMENT, "department"), code="D10")
        change = explained(JobAssignment, effective_date=date(2024, 3, 1), org_units=[department])
        record = employee(job_history=[change])
        self.assertEqual(record.job_history[0].field_status["work_location_id"], NP)
        self.assertEqual(Employee.model_validate_json(to_json(record)), record)
        with self.assertRaisesRegex(ValidationError, "'job' is null without a field_status entry"):
            JobAssignment(effective_date=date(2024, 3, 1), field_status={})

    def test_org_unit_keeps_its_source_id_when_code_and_name_are_unavailable(self):
        # D-076: a UKG cost center default whose tree lookup was refused keeps its id and its tree
        # index (the type's raw_code) together; code and name are not provided, and the id is not
        # written to code.
        unit = explained(OrgUnit, type=coded(OrgUnitType, OrgUnitType.COST_CENTER, "1"), source_id="1234567890")
        self.assertEqual((unit.source_id, unit.code, unit.field_status["code"], unit.field_status["name"]), ("1234567890", None, NP, NP))
        record = employee(job=explained(JobAssignment, org_units=[unit]))
        output = json.loads(to_json(record))["job"]["org_units"][0]
        self.assertEqual((output["type"]["value"], output["type"]["raw_code"], output["source_id"]), ("cost_center", "1", "1234567890"))
        self.assertEqual(Employee.model_validate_json(to_json(record)), record)

    def test_last4_is_at_most_four_characters(self):
        ssn = coded(NationalIdType, NationalIdType.SSN, "SSN")
        hidden = {"value": ValueStatus.HIDDEN_BY_SOURCE}
        ok = explained(NationalId, type=ssn, value=None, value_last4="6789", field_status=hidden)
        self.assertEqual((ok.value, ok.value_last4), (None, "6789"))
        with self.assertRaises(ValidationError):
            explained(NationalId, type=ssn, value=None, value_last4="56789", field_status=hidden)

    def test_tax_withholding_keeps_w4_amounts_block_and_old_form_married(self):
        # Step 3b-1 (M1, M2): W-4 amounts and the provider block are typed; federal residency does
        # not apply; old-form "Married" is its own value, not married filing jointly.
        federal = explained(
            TaxWithholdingSetting,
            level=TaxJurisdictionLevel.FEDERAL,
            jurisdiction="US",
            residency=None,
            filing_status=coded(FilingStatus, FilingStatus.MARRIED, "FDM"),
            dependents_amount="2000.00",
            other_income_amount="0.00",
            deductions_amount="0.00",
            is_blocked=False,
            field_status={"residency": ValueStatus.NOT_APPLICABLE},
        )
        state = explained(
            TaxWithholdingSetting, level=TaxJurisdictionLevel.STATE, jurisdiction="UT", residency=TaxResidency.NON_RESIDENT, is_blocked=True
        )
        record = employee(tax_withholding=explained(TaxWithholding, federal=federal, states=[state], locals=[]))
        output = json.loads(to_json(record))["tax_withholding"]
        self.assertEqual(output["federal"]["filing_status"]["value"], "married")
        self.assertNotEqual(FilingStatus.MARRIED, FilingStatus.MARRIED_FILING_JOINTLY)
        self.assertEqual((output["federal"]["dependents_amount"], output["federal"]["field_status"]["residency"]), ("2000.00", "not_applicable"))
        self.assertEqual((output["states"][0]["residency"], output["states"][0]["is_blocked"]), ("non_resident", True))
        self.assertEqual(Employee.model_validate_json(to_json(record)), record)
        with self.assertRaisesRegex(ValidationError, "'residency' is null without a field_status entry"):
            TaxWithholdingSetting(level=TaxJurisdictionLevel.FEDERAL, field_status={})

    def test_related_people_qualifications_pto_and_i9_on_file(self):
        # Step 3b-2 (M3 to M6): a dependent keeps its provider id, gender, id, address and phones;
        # a domestic partner's child is its own relationship; a skill keeps its id and code; a PTO
        # balance keeps its plan id and plan year; I-9 on file is not I-9 completed.
        dependent = explained(
            RelatedPerson,
            source_id="D1",
            relationship=coded(Relationship, Relationship.DOMESTIC_PARTNER_CHILD, "C"),
            gender=coded(Gender, Gender.FEMALE, "F"),
            national_id=explained(NationalId, type=coded(NationalIdType, NationalIdType.SSN, "SSN"), value="000-00-0000"),
            address=explained(PersonalAddress, type=AddressType.HOME, city="Springfield"),
            phones=[explained(Phone, type=PhoneType.HOME, number="555-0101")],
            is_dependent=True,
        )
        skill = explained(Qualification, type=QualificationType.SKILL, source_id="29", code="EXCEL")
        balance = explained(PtoBalance, plan_source_id="7", accrued_ytd="12.5", period_end=date(2025, 12, 31))
        authorization = explained(WorkAuthorization, i9_on_file=True)
        record = employee(related_people=[dependent], qualifications=[skill], pto_balances=[balance], work_authorization=authorization)
        output = json.loads(to_json(record))
        person = output["related_people"][0]
        self.assertEqual((person["source_id"], person["relationship"]["value"], person["phones"][0]["number"]), ("D1", "domestic_partner_child", "555-0101"))
        self.assertNotEqual(Relationship.DOMESTIC_PARTNER_CHILD, Relationship.CHILD)
        self.assertEqual((output["qualifications"][0]["source_id"], output["pto_balances"][0]["period_end"]), ("29", "2025-12-31"))
        self.assertEqual((output["work_authorization"]["i9_on_file"], output["work_authorization"]["field_status"]["i9_completed"]), (True, "not_provided"))
        self.assertEqual(Employee.model_validate_json(to_json(record)), record)
        for cls, field in ((RelatedPerson, "source_id"), (Qualification, "code"), (PtoBalance, "period_start"), (WorkAuthorization, "i9_on_file")):
            values = {"type": QualificationType.SKILL} if cls is Qualification else {}
            with self.assertRaisesRegex(ValidationError, f"'{field}' is null without a field_status entry"):
                cls(**values, field_status={})


class SensitivityTests(unittest.TestCase):
    EXPECTED_EMPLOYEE = {
        "sensitive_provider_extensions",
        "demographics.birth_date",
        "demographics.gender",
        "demographics.ethnicity",
        "demographics.marital_status",
        "demographics.citizenship",
        "demographics.preferred_pronouns",
        "demographics.veteran",
        "demographics.disability",
        "demographics.tobacco_user",
        "demographics.is_deceased",
        "demographics.deceased_date",
        "national_ids[].value",
        "personal_contact.addresses[].line1",
        "personal_contact.addresses[].line2",
        "personal_contact.addresses[].postal_code",
        "personal_contact.phones[].number",
        "personal_contact.emails[].address",
        "tax_withholding",
        "related_people[].name",
        "related_people[].full_name",
        "related_people[].birth_date",
        "related_people[].gender",
        "related_people[].national_id.value",
        "related_people[].address.line1",
        "related_people[].address.line2",
        "related_people[].address.postal_code",
        "related_people[].phones[].number",
        "related_people[].email",
        "work_authorization.i9_on_file",
        "work_authorization.i9_completed",
        "work_authorization.i9_completed_date",
        "work_authorization.document_expiration_date",
        "work_authorization.is_nonresident_alien",
        "work_authorization.visa_type",
    }

    def test_sensitive_fields_are_the_agreed_set_per_record_type(self):
        """D-040, D-044, D-046, D-048: the sensitive paths of each record type. Names, city,
        state and work contact stay visible by design; payment lines hold only last 4."""
        expected = {
            Employee: self.EXPECTED_EMPLOYEE,
            Company: {"sensitive_provider_extensions", "tax_entities[].ein"},
            DirectDeposit: {"sensitive_provider_extensions", "routing_number", "account_number"},
            DeductionSetup: {"sensitive_provider_extensions", "garnishment.case_number", "garnishment.payee"},
            BenefitEnrollment: {"sensitive_provider_extensions"},
            PayrollRun: {"sensitive_provider_extensions"},
            Paycheck: {"sensitive_provider_extensions"},
        }
        for model, paths in expected.items():
            with self.subTest(model=model.__name__):
                self.assertEqual(set(sensitive_fields(model)), paths)


class LinkCheckTests(unittest.TestCase):
    OTHER_COMPANY_ID = canonical_id(P, T, EntityType.COMPANY, "999")
    OTHER_PAY_GROUP_ID = canonical_id(P, T, EntityType.PAY_GROUP, "999", "1")

    def records(self, **employee_overrides):
        other = company(
            id=self.OTHER_COMPANY_ID,
            source_ids={"cid": "999"},
            tax_entities=[],
            work_locations=[],
            pay_groups=[explained(PayGroup, id=self.OTHER_PAY_GROUP_ID)],
        )
        manager = employee(id=MANAGER_ID, source_ids={"aid": "1000"}, job=explained(JobAssignment, work_location_id=LOCATION_ID))
        return [company(), other], [employee(**employee_overrides), manager]

    def test_consistent_sets_have_no_problems(self):
        """Including a manager employed by another company of the tenant (isolved legals)."""
        self.assertEqual(find_link_problems(*self.records()), [])
        companies, employees = self.records()
        manager = employee(
            id=MANAGER_ID,
            source_ids={"aid": "1000"},
            company_id=self.OTHER_COMPANY_ID,
            tax_entity_id=None,
            job=None,
            compensation=explained(Compensation, pay_group_id=self.OTHER_PAY_GROUP_ID),
            field_status={"tax_entity_id": NP, "job": NP},
        )
        self.assertEqual(find_link_problems(companies, [employees[0], manager]), [])

    def test_broken_links_are_reported(self):
        """A company-owned id of another company (job history included, D-069), and a company or
        employee not in the set."""
        other_location = canonical_id(P, T, EntityType.WORK_LOCATION, "999", "7")
        missing_supervisor = canonical_id(P, T, EntityType.EMPLOYEE, "33704016", "1002")
        history = [
            explained(JobAssignment, work_location_id=LOCATION_ID, manager_employee_id=MANAGER_ID),
            explained(JobAssignment, work_location_id=other_location, supervisor_employee_id=missing_supervisor),
        ]
        companies, employees = self.records()
        cases = (  # name, link problems
            ("pay group of another company", find_link_problems(*self.records(compensation=explained(Compensation, pay_group_id=self.OTHER_PAY_GROUP_ID)))),
            ("job history", find_link_problems(*self.records(job_history=history))),
            ("manager missing", find_link_problems(companies, employees[:1])),
        )
        expected = {
            "pay group of another company": [f"{EMPLOYEE_ID}: compensation.pay_group_id {self.OTHER_PAY_GROUP_ID!r} is not owned by company {COMPANY_ID!r}"],
            "job history": [
                f"{EMPLOYEE_ID}: job_history[1].work_location_id {other_location!r} is not owned by company {COMPANY_ID!r}",
                f"{EMPLOYEE_ID}: job_history[1].supervisor_employee_id {missing_supervisor!r} is not in the set",
            ],
            "manager missing": [f"{EMPLOYEE_ID}: job.manager_employee_id {MANAGER_ID!r} is not in the set"],
        }
        for name, problems in cases:
            with self.subTest(case=name):
                self.assertEqual(problems, expected[name])
        self.assertIn("company_id", find_link_problems([], employees)[0])


if __name__ == "__main__":
    unittest.main()
