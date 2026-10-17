"""isolved: create (`POST /api/clients/{clientId}/newEmployee`) and update (`.../updateEmployee`),
both with `EmployeeModel`. Ten fields are required plus first and last name; eight are client
codes, reused only within the record's own client (D-043 rule 2). `payFrequency` is an integer
whose meaning is undocumented (D-018): it is never derived from the canonical frequency."""
from .plan import Builder, Call, Plan, WriteRequest, coded, put, raw

ROUTES = {"create": "/api/clients/{clientId}/newEmployee", "update": "/api/clients/{clientId}/updateEmployee"}


def build(request: WriteRequest) -> Plan:
    b = Builder(request)
    client = b.required("company", b.company_id, "give input 'company' (the isolved client id)")
    body: dict = {}
    sensitive: set[str] = set()
    put(body, sensitive, "nameAddress.firstName", b.required("nameAddress.firstName", b.value("name", "first")))
    put(body, sensitive, "nameAddress.lastName", b.required("nameAddress.lastName", b.value("name", "last")))
    put(body, sensitive, "nameAddress.middleName", b.value("name", "middle"))
    put(body, sensitive, "nameAddress.preferredName", b.value("name", "preferred_first"))
    put(body, sensitive, "nameAddress.prefix", b.value("name", "prefix"))
    put(body, sensitive, "nameAddress.suffix", b.value("name", "suffix"))
    home = b.home_address() or {}
    put(body, sensitive, "nameAddress.address1", home.get("line1"), sensitive=True)
    put(body, sensitive, "nameAddress.address2", home.get("line2"), sensitive=True)
    put(body, sensitive, "nameAddress.city", home.get("city"))
    put(body, sensitive, "nameAddress.state", home.get("state"))
    put(body, sensitive, "nameAddress.zipCode", home.get("postal_code"), sensitive=True)
    put(body, sensitive, "ssn", b.required("ssn", b.ssn(), "the record holds no SSN (hidden by the source or not sent)"), sensitive=True)
    id_type = next((raw(item.get("type")) for item in b.value("national_ids") or [] if coded(item.get("type")) == "ssn"), None)
    put(body, sensitive, "idType", b.code("idType", "id_type", id_type))
    put(body, sensitive, "hireDate", b.required("hireDate", b.value("employment", "hire_date")))
    put(body, sensitive, "employmentStatus", b.code("employmentStatus", "employment_status", raw(b.value("employment", "status"))))
    put(body, sensitive, "employmentCategoryCode",
        b.code("employmentCategoryCode", "employment_category", raw(b.value("employment", "employment_type"))))
    put(body, sensitive, "payType", b.code("payType", "pay_type", raw(b.value("compensation", "pay_type"))))
    frequency = b.code("payFrequency", "pay_frequency", raw(b.value("compensation", "pay_frequency")))
    if frequency is not None and not str(frequency).isdigit():
        b.refuse("payFrequency", f"isolved wants an integer; {frequency!r} is not one")
    put(body, sensitive, "payFrequency", int(frequency) if str(frequency).isdigit() else None)
    put(body, sensitive, "payGroup", b.code("payGroup", "pay_group", b.company_code("pay_groups", b.value("compensation", "pay_group_id"))))
    put(body, sensitive, "workLocation",
        b.code("workLocation", "work_location", b.company_code("work_locations", b.value("job", "work_location_id"))))
    put(body, sensitive, "legalCode", b.code("legalCode", "legal", (request.company or {}).get("company_code")))
    put(body, sensitive, "jobCode", b.inputs.get("job") or (b.value("job", "job", "code") if b.same_place else None))
    put(body, sensitive, "emailAddress", b.value("work_contact", "email") or b.personal_email(),
        sensitive=b.value("work_contact", "email") is None)
    put(body, sensitive, "birthDate", b.value("demographics", "birth_date"), sensitive=True)
    if request.operation == "update":
        number = b.inputs.get("employee") or (b.value("employee_number") if b.same_place else None)
        put(body, sensitive, "employeeNumber", b.required(
            "employeeNumber", number, "give input 'employee' (the employee number in the destination; required to update)"))
    route = ROUTES[request.operation]
    note = ("Creates the employee." if request.operation == "create" else
            "Updates the employee named by employeeNumber; the same model and required fields as a create.")
    b.plan.calls.append(Call("POST", route, route.replace("{clientId}", str(client)), body=body, sensitive=sensitive, note=note))
    b.plan.notes.append("Not sent: a real isolved write needs a real SSN in a shared demo tenant (D-100). Dry run only.")
    return b.plan
