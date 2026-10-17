"""Write path (Phase 8, D-038, D-043, D-100): a canonical employee mapped to one provider's create
or update requests, as a plan that is shown (dry run) and, for UKG Ready only, sent.

A plan lists the provider calls in order and every refusal. Rules (CANONICAL_MODEL section 4):
values the record does not hold are never sent and a required one is a refusal; raw provider codes
are reused only when the destination is the record's own provider and company, otherwise each
required code comes from an input given with the write; credentials never appear in a plan.
"""
import copy
import re
from dataclasses import dataclass, field
from typing import Any

MASK = "***"
SESSION = "<session>"  # stands for a credential the provider wants in the body (PrismHR sessionId)
DESTINATIONS = ("ukg-ready", "isolved", "prismhr")
OPERATIONS = ("create", "update")
COMPANY_KEY = {"ukg-ready": "companyId", "isolved": "clientId", "prismhr": "clientId"}
EMPLOYEE_KEY = {"ukg-ready": "accountId", "isolved": "employeeId", "prismhr": "employeeId"}


@dataclass
class WriteRequest:
    destination: str  # provider written to
    operation: str  # create or update
    employee: dict  # canonical employee as JSON, full values
    company: dict | None = None  # the employee's canonical company (codes of its pay groups, locations)
    inputs: dict[str, str] = field(default_factory=dict)  # destination inputs given with this write
    changed: set[str] | None = None  # form fields edited (app): an update then sends only these; None sends all held

    def __post_init__(self) -> None:
        if self.destination not in DESTINATIONS:
            raise ValueError(f"unknown destination {self.destination!r}; choose from {', '.join(DESTINATIONS)}")
        if self.operation not in OPERATIONS:
            raise ValueError(f"unknown operation {self.operation!r}; choose create or update")
        self.inputs = {key: str(value).strip() for key, value in (self.inputs or {}).items() if str(value or "").strip()}


@dataclass
class Call:
    method: str
    route: str  # documented route template
    path: str  # the route with its path values filled
    query: dict[str, str] = field(default_factory=dict)
    body: Any = None
    note: str = ""
    sensitive: set[str] = field(default_factory=set)  # dot paths in body from sensitive canonical fields
    content_type: str = "application/json"  # UKG's JSON Patch must say application/json-patch+json (live 415)


@dataclass
class Plan:
    destination: str
    operation: str
    calls: list[Call] = field(default_factory=list)
    refusals: list[dict[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def sendable(self) -> bool:
        """Only a UKG Ready plan without refusals is ever sent (D-100)."""
        return self.destination == "ukg-ready" and not self.refusals and bool(self.calls)

    def view(self, show_sensitive: bool = False) -> dict:
        """The plan as JSON data: sensitive body values masked unless the caller opts in (D-036)."""
        calls = []
        for call in self.calls:
            body = copy.deepcopy(call.body)
            if not show_sensitive:
                for path in sorted(call.sensitive):
                    _mask(body, path.split("."))
            calls.append({"method": call.method, "route": call.route, "path": call.path, "query": call.query,
                          "content_type": call.content_type, "body": body, "note": call.note})
        return {"destination": self.destination, "operation": self.operation, "sendable": self.sendable,
                "sensitive_values": "shown" if show_sensitive else "masked", "calls": calls,
                "refusals": self.refusals, "notes": self.notes}


def _mask(node: Any, parts: list[str]) -> None:
    """Mask the value at ``parts`` (dict keys; a list index as digits) in place. SSNs keep their
    last 4 characters, as the output layer does (D-080)."""
    for part in parts[:-1]:
        node = node[int(part)] if isinstance(node, list) else (node or {}).get(part)
        if node is None:
            return
    last = parts[-1]
    holder_ok = isinstance(node, dict) and last in node or isinstance(node, list) and last.isdigit()
    if not holder_ok:
        return
    key = int(last) if isinstance(node, list) else last
    value = node[key]
    if value is None:
        return
    if last in ("ssn", "social_security") and isinstance(value, str):
        visible = re.sub(r"[^0-9A-Za-z]", "", value)[-4:]
        node[key] = MASK + visible if len(visible) == 4 else MASK
    else:
        node[key] = MASK


def coded(value: Any) -> Any:
    """The canonical value of a coded field (its ``value``), else the value itself."""
    return value.get("value") if isinstance(value, dict) and "raw_code" in value else value


def raw(value: Any) -> Any:
    """The provider's raw code of a coded field."""
    return value.get("raw_code") if isinstance(value, dict) and "raw_code" in value else None


def last_segment(canonical_id: Any) -> str | None:
    """The provider key at the end of a canonical id (``...:pay_group:1001:BW`` gives ``BW``)."""
    return str(canonical_id).rsplit(":", 1)[-1] if canonical_id else None


class Builder:
    """Shared rules for one write: what the record holds, the destination codes, refusals."""

    def __init__(self, request: WriteRequest) -> None:
        self.request, self.e, self.inputs = request, request.employee, request.inputs
        self.source = self.e.get("provider")
        self.source_ids = self.e.get("source_ids") or {}
        own_company = self.source_ids.get(COMPANY_KEY.get(self.source, ""))
        same_provider = self.source == request.destination
        # Destination company: an input, else the record's own when the provider matches.
        self.company_id = self.inputs.get("company") or (own_company if same_provider else None)
        # Raw codes travel only within the record's own provider and company (D-043 rule 2).
        self.same_place = same_provider and self.company_id == own_company
        self.plan = Plan(request.destination, request.operation)
        if request.operation == "create" and self.same_place:
            self.refuse("operation", "this employee already exists in this company: use update (a create would duplicate it)")

    def wanted(self, form_field: str) -> bool:
        """Whether an update sends this field: every held field, or only the edited ones (app form)."""
        return self.request.changed is None or form_field in self.request.changed

    def nothing_changed(self) -> bool:
        """An update from the form with no field edited: refused, there is nothing to send."""
        if self.request.changed is not None and not self.request.changed:
            self.refuse("changes", "change at least one field: an update sends only the fields you change")
            return True
        return False

    def refuse(self, name: str, reason: str) -> None:
        self.plan.refusals.append({"field": name, "reason": reason})

    def value(self, *path: str) -> Any:
        """The value at ``path`` in the employee (None when absent, null or empty)."""
        node: Any = self.e
        for part in path:
            node = node.get(part) if isinstance(node, dict) else None
        return None if node in ("", [], {}) else node

    def required(self, name: str, value: Any, why: str = "the record holds no value") -> Any:
        if value is None:
            self.refuse(name, why)
        return value

    def code(self, name: str, input_key: str, own: Any) -> Any:
        """A destination code: ``own`` (the record's raw code) only when writing back to the record's
        own provider and company, else the input ``input_key``; a refusal when neither applies."""
        given = self.inputs.get(input_key)
        if given is not None:
            return given
        if self.same_place and own not in (None, ""):
            return own
        where = "the record holds no code for it" if self.same_place else "codes are reused only within the record's own provider and company"
        self.refuse(name, f"give input '{input_key}' ({where})")
        return None

    def company_code(self, kind: str, canonical_id: Any) -> Any:
        """The code of the employee's pay group or work location, from its company record."""
        for entry in (self.request.company or {}).get(kind) or []:
            if entry.get("id") == canonical_id:
                return entry.get("code") or entry.get("name")
        return None

    def ssn(self) -> Any:
        for item in self.value("national_ids") or []:
            if coded(item.get("type")) in ("ssn", "itin") and item.get("value"):
                return item["value"]
        return None

    def target(self) -> str | None:
        """The employee to update: an input, else the record itself when writing back to its place."""
        given = self.inputs.get("employee")
        if given:
            return given
        if self.same_place:
            return self.source_ids.get(EMPLOYEE_KEY[self.request.destination])
        self.refuse("employee", "give input 'employee' (the destination's id of the employee to update)")
        return None

    def phone(self, kind: str) -> str | None:
        return next((p.get("number") for p in self.value("personal_contact", "phones") or []
                     if coded(p.get("type")) == kind and p.get("number")), None)

    def personal_email(self) -> str | None:
        return next((m.get("address") for m in self.value("personal_contact", "emails") or []
                     if coded(m.get("type")) != "work" and m.get("address")), None)

    def home_address(self) -> dict | None:
        for address in self.value("personal_contact", "addresses") or []:
            if address.get("type") in ("home", None):
                return address
        return None


def put(body: dict, call_sensitive: set[str], path: str, value: Any, sensitive: bool = False) -> None:
    """Set ``path`` (dots) in ``body`` when ``value`` is held; record it as sensitive if it is."""
    if value is None or value == "":
        return
    node = body
    parts = path.split(".")
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value
    if sensitive:
        call_sensitive.add(path)


# Form fields (the app's write form and the CLI's --change): a flat name per canonical value. Only
# changed fields are sent, so a value the viewer saw masked is never written back (D-100).
FORM_FIELDS = {
    "first_name": ("name", "first"), "middle_name": ("name", "middle"), "last_name": ("name", "last"),
    "preferred_name": ("name", "preferred_first"), "prefix": ("name", "prefix"), "suffix": ("name", "suffix"),
    "employee_number": ("employee_number",), "birth_date": ("demographics", "birth_date"),
    "work_email": ("work_contact", "email"), "work_phone": ("work_contact", "phone"),
    "hire_date": ("employment", "hire_date"), "original_hire_date": ("employment", "original_hire_date"),
    "ssn": ("national_ids", "ssn"), "personal_email": ("emails", "personal"),
    "mobile_phone": ("phones", "mobile"), "home_phone": ("phones", "home"),
    "address_line1": ("address", "line1"), "address_line2": ("address", "line2"), "city": ("address", "city"),
    "state": ("address", "state"), "postal_code": ("address", "postal_code"), "country": ("address", "country"),
}


def blank_employee() -> dict:
    """A new employee with nothing in it yet, for a write that starts from the form alone."""
    return {"provider": None, "tenant_id": None, "source_ids": {}, "name": {}, "national_ids": [], "employment": {},
            "work_contact": {}, "personal_contact": {"addresses": [], "phones": [], "emails": []}, "demographics": {},
            "job": None, "compensation": None, "provider_extensions": {}}


def _entry(items: list, kind: str, key: str, default: dict) -> dict:
    """The entry of ``kind`` in a canonical list (by its ``key``), added when missing."""
    for item in items:
        if coded(item.get(key)) == kind:
            return item
    entry = dict(default)
    items.append(entry)
    return entry


def apply_changes(employee: dict, changes: dict[str, str]) -> dict:
    """A copy of ``employee`` with the form ``changes`` applied. An empty value clears the field.
    Raises ValueError for an unknown field or a masked value (``***``), which is never written."""
    result = copy.deepcopy(employee)
    for name, given in (changes or {}).items():
        if name not in FORM_FIELDS:
            raise ValueError(f"unknown form field {name!r}; choose from {', '.join(FORM_FIELDS)}")
        value = str(given).strip() if given is not None else ""
        if value.startswith(MASK):
            raise ValueError(f"{name}: a masked value cannot be written; type the real value or leave the field unchanged")
        value = value or None
        group, part = FORM_FIELDS[name] if len(FORM_FIELDS[name]) == 2 else (FORM_FIELDS[name][0], None)
        if part is None:
            result[group] = value
        elif group == "national_ids":
            ids = result.setdefault("national_ids", []) or []
            result["national_ids"] = ids
            entry = _entry(ids, "ssn", "type", {"type": {"value": "ssn", "raw_code": "SSN", "raw_label": None, "basis": "documented"}})
            entry["value"] = value
        elif group in ("emails", "phones", "address"):
            contact = result.get("personal_contact") or {}
            result["personal_contact"] = contact
            if group == "address":
                entry = _entry(contact.setdefault("addresses", []), "home", "type", {"type": "home"})
                entry[part] = value
            elif group == "emails":
                _entry(contact.setdefault("emails", []), part, "type", {"type": part})["address"] = value
            else:
                _entry(contact.setdefault("phones", []), part, "type", {"type": part})["number"] = value
        else:
            node = result.get(group) or {}
            result[group] = node
            node[part] = value
    return result
