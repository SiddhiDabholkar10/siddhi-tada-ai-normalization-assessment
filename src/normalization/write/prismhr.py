"""PrismHR: create is two calls, `importEmployees` (a `NewHire` with one `NewHireEmployee`) then
`commitEmployees` with the batch id the import returns; the client's own required fields come from
`getNewHireRequiredFields` first. Update is `updateEmployeeFields`, which requires `manager`.
`peoStartDate` is a different fact from the hire date and is never filled from it (D-043 rule 4)."""
from .plan import SESSION, Builder, Call, Plan, WriteRequest, last_segment, put, raw

REQUIRED_FIELDS = "/newHire/v1/getNewHireRequiredFields"
IMPORT = "/newHire/v1/importEmployees"
COMMIT = "/newHire/v1/commitEmployees"
UPDATE = "/employee/v1/updateEmployeeFields"


def _peo_start(b: Builder) -> str | None:
    if b.inputs.get("peo_start_date"):
        return b.inputs["peo_start_date"]
    if b.same_place:  # PrismHR to PrismHR: the record's own value, kept as an extension
        return next((value for key, value in (b.e.get("provider_extensions") or {}).items()
                     if key.endswith(".person.peoStartDate") and value), None)
    return None


def build(request: WriteRequest) -> Plan:
    b = Builder(request)
    client = b.required("company", b.company_id, "give input 'company' (the PrismHR client id)")
    middle = b.value("name", "middle")
    if request.operation == "create":
        hire: dict = {}
        sensitive: set[str] = set()
        put(hire, sensitive, "firstName", b.required("firstName", b.value("name", "first")))
        put(hire, sensitive, "lastName", b.required("lastName", b.value("name", "last")))
        put(hire, sensitive, "middleInitial", middle[:1] if middle else None)
        put(hire, sensitive, "ssn", b.required("ssn", b.ssn(), "the record holds no SSN (PrismHR sends it masked; D-020)"), sensitive=True)
        put(hire, sensitive, "birthDate", b.value("demographics", "birth_date"), sensitive=True)
        put(hire, sensitive, "employeeStatusCode", b.code("employeeStatusCode", "employment_status", raw(b.value("employment", "status"))))
        put(hire, sensitive, "employeeTypeCode",
            b.inputs.get("employment_type") or (raw(b.value("employment", "employment_type")) if b.same_place else None))
        put(hire, sensitive, "workLocationCode",
            b.code("workLocationCode", "work_location", b.company_code("work_locations", b.value("job", "work_location_id"))))
        put(hire, sensitive, "jobCode", b.code("jobCode", "job", b.value("job", "job", "code")))
        put(hire, sensitive, "payGroup", b.code("payGroup", "pay_group", b.company_code("pay_groups", b.value("compensation", "pay_group_id"))))
        put(hire, sensitive, "origHireDate", b.required("origHireDate", b.value("employment", "original_hire_date")))
        put(hire, sensitive, "lastHireDate", b.required("lastHireDate", b.value("employment", "hire_date")))
        put(hire, sensitive, "peoStartDate", b.required("peoStartDate", _peo_start(b),
                                                       "give input 'peo_start_date' (start with the PEO; never the hire date)"))
        put(hire, sensitive, "standardHours", b.required("standardHours", b.value("compensation", "standard_hours")))
        put(hire, sensitive, "employeeNumber", b.value("employee_number"))
        put(hire, sensitive, "emailAddress", b.value("work_contact", "email") or b.personal_email(),
            sensitive=b.value("work_contact", "email") is None)
        put(hire, sensitive, "homePhone", b.phone("home") or b.phone("mobile"), sensitive=True)
        put(hire, sensitive, "workPhone", b.value("work_contact", "phone"))
        home = b.home_address() or {}
        put(hire, sensitive, "addressLine1", home.get("line1"), sensitive=True)
        put(hire, sensitive, "addressLine2", home.get("line2"), sensitive=True)
        put(hire, sensitive, "city", home.get("city"))
        put(hire, sensitive, "stateCode", home.get("state"))
        put(hire, sensitive, "zipCode", home.get("postal_code"), sensitive=True)
        b.plan.calls.append(Call("GET", REQUIRED_FIELDS, REQUIRED_FIELDS, {"clientId": str(client)},
                                 note="The client's own required new hire fields, checked before the import; "
                                      "the dry run checks the 11 fields the schema requires."))
        body = {"sessionId": SESSION, "clientId": str(client), "translationTable": "", "newHireEmployee": [hire]}
        b.plan.calls.append(Call("POST", IMPORT, IMPORT, body=body, sensitive={f"newHireEmployee.0.{p}" for p in sensitive},
                                 note="Imports the new hire; each employee's validFlag says whether it passed. Returns importBatchId."))
        b.plan.calls.append(Call("POST", COMMIT, COMMIT, {"clientId": str(client), "importBatchId": "<importBatchId from importEmployees>"},
                                 note="Hires the imported employee. A batch that is not committed must be cancelled, "
                                      "or it stays pending."))
    else:
        employee = b.target()
        b.nothing_changed()
        body = {"sessionId": SESSION, "clientId": str(client), "employeeId": employee}
        sensitive = set()

        def send(path: str, form: str, value, secret: bool = False) -> None:
            if b.wanted(form):  # PrismHR ignores fields left out: only the edited ones go (app form)
                put(body, sensitive, path, value, sensitive=secret)

        manager = b.inputs.get("manager") or (last_segment(b.value("job", "manager_employee_id")) if b.same_place else None)
        put(body, sensitive, "manager", b.required("manager", manager, "give input 'manager' (required by updateEmployeeFields)"))
        send("firstName", "first_name", b.value("name", "first"))
        send("lastName", "last_name", b.value("name", "last"))
        send("middleInitial", "middle_name", middle)
        send("nickname", "preferred_name", b.value("name", "preferred_first"))
        send("workEmail", "work_email", b.value("work_contact", "email"))
        send("workPhone", "work_phone", b.value("work_contact", "phone"))
        send("emailAddress", "personal_email", b.personal_email(), True)
        send("homePhone", "home_phone", b.phone("home"), True)
        send("mobilePhone", "mobile_phone", b.phone("mobile"), True)
        send("birthDate", "birth_date", b.value("demographics", "birth_date"), True)
        b.plan.calls.append(Call("POST", UPDATE, UPDATE, body=body, sensitive=sensitive,
                                 note="Updates the fields given; PrismHR ignores fields left out or null."))
    b.plan.notes.append("Not sent: a real PrismHR write needs a real SSN and leaves a pending batch if the commit fails (D-100). Dry run only.")
    return b.plan
