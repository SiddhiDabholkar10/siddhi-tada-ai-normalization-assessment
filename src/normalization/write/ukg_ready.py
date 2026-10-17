"""UKG Ready: create (`POST /v2/companies/{cid}/employees`) and update (`PATCH .../employees/{aid}`,
JSON Patch). Three fields are required to create: username, first and last name. The username
must be unique in the destination, so it is always an explicit input (D-043 rule 5)."""
from .plan import Builder, Call, Plan, WriteRequest, put

CREATE = "/v2/companies/{cid}/employees"
UPDATE = "/v2/companies/{cid}/employees/{aid}"
# JSON Pointer in the UKG employee, how to read the value, form field, sensitive. An update from the form
# sends only the edited fields; without the form, every held one.
PATCHED = (
    ("/first_name", lambda b: b.value("name", "first"), "first_name", False),
    ("/last_name", lambda b: b.value("name", "last"), "last_name", False),
    ("/middle_name", lambda b: b.value("name", "middle"), "middle_name", False),
    ("/nickname", lambda b: b.value("name", "preferred_first"), "preferred_name", False),
    ("/salutation", lambda b: b.value("name", "prefix"), "prefix", False),
    ("/suffix", lambda b: b.value("name", "suffix"), "suffix", False),
    ("/employee_id", lambda b: b.value("employee_number"), "employee_number", False),
    ("/primary_email", lambda b: b.value("work_contact", "email"), "work_email", False),
    ("/secondary_email", lambda b: b.personal_email(), "personal_email", True),
    ("/phones/work_phone", lambda b: b.value("work_contact", "phone"), "work_phone", False),
    ("/phones/cell_phone", lambda b: b.phone("mobile"), "mobile_phone", True),
    ("/phones/home_phone", lambda b: b.phone("home"), "home_phone", True),
    ("/address/address_line_1", lambda b: (b.home_address() or {}).get("line1"), "address_line1", True),
    ("/address/address_line_2", lambda b: (b.home_address() or {}).get("line2"), "address_line2", True),
    ("/address/city", lambda b: (b.home_address() or {}).get("city"), "city", False),
    ("/address/state", lambda b: (b.home_address() or {}).get("state"), "state", False),
    ("/address/zip", lambda b: (b.home_address() or {}).get("postal_code"), "postal_code", True),
    ("/address/country", lambda b: (b.home_address() or {}).get("country"), "country", False),
)


def _started(b: Builder) -> str | None:
    """UKG's start date: an input, else the source's own UKG value (kept as an extension). Never
    the hire date: the two differ for 34 of 103 live employees (live write, D-100)."""
    if b.inputs.get("start_date"):
        return b.inputs["start_date"]
    if b.source == "ukg-ready":
        return next((value for key, value in (b.e.get("provider_extensions") or {}).items()
                     if key.endswith("dates.started") and value), None)
    return None


def build(request: WriteRequest) -> Plan:
    b = Builder(request)
    cid = b.required("company", b.company_id, "give input 'company' (the UKG company id)")
    if request.operation == "create":
        first = b.required("first_name", b.value("name", "first"))
        last = b.required("last_name", b.value("name", "last"))
        username = b.required("username", b.inputs.get("username"),
                              "give input 'username': it must be unique in the destination, so it is never guessed")
        body: dict = {}
        sensitive: set[str] = set()
        put(body, sensitive, "username", username)
        put(body, sensitive, "first_name", first)
        put(body, sensitive, "last_name", last)
        put(body, sensitive, "middle_name", b.value("name", "middle"))
        put(body, sensitive, "nickname", b.value("name", "preferred_first"))
        put(body, sensitive, "employee_id", b.value("employee_number"))
        put(body, sensitive, "primary_email", b.value("work_contact", "email"))
        put(body, sensitive, "secondary_email", b.personal_email(), sensitive=True)
        put(body, sensitive, "salutation", b.value("name", "prefix"))
        put(body, sensitive, "suffix", b.value("name", "suffix"))
        home = b.home_address() or {}
        put(body, sensitive, "address.address_line_1", home.get("line1"), sensitive=True)
        put(body, sensitive, "address.address_line_2", home.get("line2"), sensitive=True)
        put(body, sensitive, "address.city", home.get("city"))
        put(body, sensitive, "address.state", home.get("state"))
        put(body, sensitive, "address.zip", home.get("postal_code"), sensitive=True)
        put(body, sensitive, "address.country", home.get("country") if len(str(home.get("country") or "")) == 3 else None)
        put(body, sensitive, "phones.cell_phone", b.phone("mobile"), sensitive=True)
        put(body, sensitive, "phones.home_phone", b.phone("home"), sensitive=True)
        put(body, sensitive, "phones.work_phone", b.value("work_contact", "phone"))
        # The demo company requires a social security number (live 400). Without one, UKG's own NO_ID_NEEDED
        # type is sent (read back as "not_required"); an SSN is never invented.
        ssn = b.ssn()
        if ssn:
            put(body, sensitive, "social_security", ssn, sensitive=True)
        else:
            body["national_id_numbers"] = [{"type": "NO_ID_NEEDED", "primary": True}]
            b.plan.notes.append("No SSN given: sent as UKG's 'no id needed' national id type (UKG requires one or the other).")
        put(body, sensitive, "dates.hired", b.value("employment", "hire_date"))
        # Required by the demo company although the reference lists only three required fields (live 400).
        put(body, sensitive, "dates.started", b.required("start_date", _started(b),
                                                         "give input 'start_date': UKG requires a start date, and it is not the hire date"))
        put(body, sensitive, "dates.re_hired", b.value("employment", "rehire_date"))
        put(body, sensitive, "dates.seniority", b.value("employment", "seniority_date"))
        # Also required by the demo company though not marked in the reference (live 400 "'Birthday' is required").
        put(body, sensitive, "dates.birthday", b.required("birth_date", b.value("demographics", "birth_date"),
                                                          "UKG requires a birth date"), sensitive=True)
        b.plan.calls.append(Call("POST", CREATE, CREATE.replace("{cid}", str(cid)), body=body, sensitive=sensitive,
                                 note="Creates the employee; the response carries the new account id."))
    else:
        aid = b.target()
        b.nothing_changed()
        # A held value is "add": it sets the member whether or not it exists ("replace" fails on a missing one, live
        # 400 'Missing field'). An emptied field is removed. Without the form, every held field is set.
        ops, sensitive = [], set()
        for pointer, read, form, secret in PATCHED:
            value = read(b)
            if not b.wanted(form) or (request.changed is None and value is None):
                continue
            if secret and value is not None:
                sensitive.add(f"{len(ops)}.value")
            ops.append({"op": "add", "path": pointer, "value": value} if value is not None else {"op": "remove", "path": pointer})
        b.plan.calls.append(Call("PATCH", UPDATE, UPDATE.replace("{cid}", str(cid)).replace("{aid}", str(aid)), body=ops,
                                 content_type="application/json-patch+json", sensitive=sensitive,
                                 note="JSON Patch on the account: the fields changed (or, without the form, every name, id, "
                                      "email, phone and home address field the record holds)."))
        b.plan.notes.append("Other UKG sections (pay-info, demographics, profiles, tax-info) have their own PUT routes; not written (D-038).")
    return b.plan
