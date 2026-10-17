"""UKG Ready employee bundle: one company, three accounts (two of them one person under two
EINs, D-039).

Edge cases (employee tables, D-077): millisecond durations (standard hours, accrual balances,
D-028), the open-start sentinel 1900-12-31 on a compensation effective date (D-025), a cost
center tree whose lookup returns 400 'Cost Center not used' and a default whose id is not in
its tree (D-076), accrual/1 refused with 403, a rehired account, a terminated contractor with
NO_ID_NEEDED, company-defined employee types (unknown), contacts with an unlisted relationship
label and the live-only ``active`` flag, and a person grouped by primary_account_id.

The bundle also holds the company, setup and payroll inputs (ukg_company.py, ukg_setups.py,
ukg_payroll.py, D-082). The pay period profiles are shared with the company records.
"""
from . import ukg_company, ukg_payroll, ukg_setups
from .common import Builder
from .ukg_company import CID

C = "/v2/companies/{cid}"
R = {
    "list": f"{C}/employees",
    "detail": f"{C}/employees/{{aid}}",
    **{name: f"{C}/employees/{{aid}}/{name}" for name in (
        "demographics", "pay-info", "profiles", "compensation/history", "compensation/total", "compensation/additional",
        "contacts", "tax-info", "skills", "training/certifications", "badges", "hr-custom-fields",
        "accrual/1/balances", "accrual/2/balances")},
    "jobs": f"{C}/lookup/jobs",
    "employee-types": f"{C}/lookup/employee-types",
    "pay-types": f"{C}/lookup/pay-types",
    "pay-period-profiles": f"{C}/lookup/pay-period-profiles",
    "cost-centers": f"{C}/config/cost-centers",
}
HOUR_MS = 3_600_000


def build(seed: int) -> dict:
    b = Builder("ukg-ready", "900003", seed)
    _lookups(b)
    accounts = [_account_1(b), _account_2(b), _account_3(b)]
    b.add(R["list"], {"cid": CID}, {"employees": [_list_item(detail) for detail in accounts]})
    ukg_company.add(b)
    ukg_setups.add(b)
    ukg_payroll.add(b)
    return b.bundle()


def _list_item(detail: dict) -> dict:
    return {
        "id": detail["id"], "username": detail["username"], "employee_id": detail.get("employee_id"),
        "first_name": detail["first_name"], "last_name": detail["last_name"], "status": detail.get("status"),
        "primary_account_id": detail.get("primary_account_id"), "ein_name": detail.get("ein_name"),
        "dates": {"hired": detail["dates"]["hired"], "terminated": detail["dates"].get("terminated")},
        "_links": {"self": f"/employees/{detail['id']}"},
    }


def _lookups(b: Builder) -> None:
    b.add(R["jobs"], {"cid": CID}, {"items": [
        {"id": 501, "name": "Line Cook", "payroll_code": "COOK1", "external_id": "J-501", "visible": True},
        {"id": 502, "name": "Shift Manager", "payroll_code": "", "visible": True},
    ]})
    b.add(R["employee-types"], {"cid": CID}, {"items": [{"id": 61, "name": "FT Non-Exempt"}, {"id": 62, "name": "Consultant"}]})
    b.add(R["pay-types"], {"cid": CID}, {"items": [{"id": 71, "name": "Hourly", "external_id": "H"}, {"id": 72, "name": "Salaried"}, {"id": 73, "name": "Commission"}]})
    b.add(R["pay-period-profiles"], {"cid": CID}, {"items": ukg_company.profiles()})
    b.add(R["cost-centers"], {"cid": CID, "tree_index": 0}, {"cost_centers": [
        {"id": 8100, "name": "Kitchen", "payroll_code": "KIT", "description": "Back of house", "parent_id": 8000},
        {"id": 8101, "name": "Front of house", "payroll_code": ""},
    ]})
    b.add(R["cost-centers"], {"cid": CID, "tree_index": 1}, {"errors": [{"code": 19515, "message": "Cost Center not used"}]}, status=400)
    b.add(R["cost-centers"], {"cid": CID, "tree_index": 2}, {"cost_centers": [{"id": 8300, "name": "Region West"}]})


def _sub(b: Builder, name: str, aid: int, body, status: int = 200) -> None:
    b.add(R[name], {"cid": CID, "aid": aid}, body, status)


def _detail(b: Builder, values: dict) -> dict:
    return b.shaped(R["detail"], "", values)


def _compensation(aid: int, effective: str, amount: float, period: str, hourly: float, time_ms: int, time_period: str, entry: int) -> dict:
    return {"id": entry, "employee": {"account_id": aid}, "effective_from": effective, "amount": amount, "hourly_pay": hourly,
            "currency": "USD", "amount_period": period, "time": time_ms, "time_period": time_period, "num_pp_in_year": 26,
            "_links": {"self": f"/compensation/{entry}"}}


def _account_1(b: Builder) -> dict:
    """Active hourly cook under EIN 501; the person's primary account."""
    aid = 1101
    first, last = b.name()
    detail = _detail(b, {
        "id": aid, "username": f"{first.lower()}.{last.lower()}", "first_name": first, "middle_name": "Ray", "last_name": last,
        "nickname": "Ray", "salutation": "Mr.", "suffix": "", "employee_id": "U-1101", "external_id": "EXT-1101",
        "status": "Active", "photo_href": "https://example.invalid/photo?ticket=SECRET", "isPhotoUploaded": False,
        "primary_account_id": 1101, "ein": {"id": 501}, "ein_name": "Harbor Kitchens Inc",
        "national_id_numbers": [{"type": "SSN", "value": "666-45-1101", "primary": True}],
        "social_security": "666-45-1101",
        "address": {"country": "USA", "address_line_1": b.street(), "address_line_2": "Unit 5", "address_line_3": "Rear door", "city": "Denver",
                    "state": "CO", "state_code": "CO", "zip": "80202", "number": "12", "number_addition": "B"},
        "use_separate_mailing_address": True,
        "mailing_address": {"country": "USA", "address_line_1": "PO Box 300", "address_line_2": "Box B", "city": "Denver", "state_code": "CO", "zip": "80201"},
        "phones": {"cell_phone": b.phone("303"), "cell_phone_country_id": "US", "cell_phone_country_code": "1",
                   "home_phone": b.phone("303"), "work_phone": "303-555-0400", "preferred_phone": "CELL"},
        "primary_email": "ray.home@example.org", "secondary_email": "ray.alt@example.org",
        "managers": [{"index": 1, "empl_ref": {"account_id": 1999}}, {"index": 0, "empl_ref": {"account_id": 1103}}],
        "cost_centers_info": {"defaults": [{"index": 0, "value": {"id": 8100}}, {"index": 1, "value": {"id": 8200}}],
                              "limits": [{"index": 0, "values": [{"type": "LIST", "id": 8101, "effective_from": "2024-01-01"}]}]},
        "dates": {"hired": "2019-06-03", "started": "2019-06-03", "seniority": "2019-06-03", "birthday": "1992-12-01",
                  "review": "2025-06-03", "custom_dates": [{"index": 0, "date": "2025-01-01"}]},
        "account_extra_fields": [{"index": 0, "values": [{"value": "Blue", "effective_from": "2024-01-01"}]}],
        "hardware_settings": {"in_touch": {"pin": 4321, "security_level": "EMPLOYEE"}},
        "force_change_password": False, "locked": False, "timezone": "America/Denver", "locale": {"id": 1},
        "_links": {"self": "/employees/1101"},
    })
    _sub(b, "detail", aid, detail)
    _sub(b, "demographics", aid, {"gender": "MALE", "ethnicity": "HISPANIC_OR_LATINO", "citizenship": "PERMANENT_RESIDENT", "seasonal": False,
                                  "visa": {"type": "H-1B", "number": "V-77881", "expiration_date": "2027-08-31"},
                                  "eye_color": "Brown", "height": "180cm", "full_time_student": False,
                                  "referral": {"id": 3}, "recruiter": {"account_id": 1999, "display_name": "Recruiter One"}})
    _sub(b, "pay-info", aid, {"default_job": {"id": 501}, "job_last_changed": "2023-04-01",
                              "job_change_reason_code": {"display_name": "Promotion"}, "standard_work_day": 8 * HOUR_MS,
                              "employee_type": {"id": 61}, "pay_type": {"id": 71}, "eeo_classification": "SERVICE_WORKERS",
                              "workers_comp_code": {"external_id": "9079"}, "union": {"id": 44}, "payroll_classification": "REGULAR",
                              "medical_eligibility": "ELIGIBLE", "bank_account_number": "", "pay_grade": {"id": 5, "parent": {"id": 1, "code": 2, "name": "Kitchen"}},
                              "gl_codes": [{"index": 0, "value": "5100"}], "shift_premium": {"id": 9}})
    # The contract allows one pay_period entry (maxItems 1).
    _sub(b, "profiles", aid, {"pay_period": [{"id": 9001, "name": "Biweekly", "effective_from": "2023-01-01"}],
                              "security": [{"id": 3, "effective_from": "2019-06-03"}]})
    _sub(b, "compensation/history", aid, {"compensations": [
        _compensation(aid, "1900-12-31", 15.00, "HOUR", 15.00, 80 * HOUR_MS, "PAY_PERIOD", 1),
        _compensation(aid, "2023-04-01", 19.50, "HOUR", 19.50, 75 * HOUR_MS + 30 * 60_000, "PAY_PERIOD", 2),
    ]})
    _sub(b, "compensation/total", aid, {"total_compensations": [{"account": {"id": aid}, "amount": 40560.00, "effective_from": "2023-04-01", "currency": "USD"}]})
    _sub(b, "compensation/additional", aid, {"additional_compensations": []})
    _sub(b, "contacts", aid, {"contacts": [
        {"id": 31, "account_id": None, "employee": {"account_id": aid}, "primary": True, "emergency": True, "dependent": True, "beneficiary": False,
         "emergency_notif": None, "salutation": "Ms.", "first_name": "Lena", "middle_name": "", "last_name": last, "name_suffix": "",
         "relationship": "Spouse", "birthdate": "1993-03-03", "active": True, "comments": "Call after 6pm",
         "cell_phone": {"code": 1, "number": b.phone("303"), "primary": True}, "work_phone": {"code": 1, "number": "303-555-0450", "primary": False},
         "is_in_any_benefit_plan": True, "has_delete_permission": True, "_links": {"self": "/contacts/31"}},
        {"id": 32, "employee": {"account_id": aid}, "emergency": True, "dependent": False, "beneficiary": True, "first_name": "Omar",
         "middle_name": "Ann", "last_name": "Ruiz", "name_suffix": "II", "relationship": "Uncle", "active": False, "home_phone": {"code": 1, "number": b.phone("719"), "primary": True}},
    ], "_total_count": 2, "_sub_count": {"all": 2, "emergency": 2}})
    _sub(b, "tax-info", aid, {"employee-tax-type": {"W2": True, "_1099": False, "DRAW": False}, "fein": "12-3456789",
                              "pension-box-type": "SYSTEM_RULES", "dba-company-name": "Harbor Kitchens"})
    _sub(b, "skills", aid, {"employee_skills": [{"skill": {"id": 1201}, "level": 4, "years": 6, "primary": True}]})
    _sub(b, "training/certifications", aid, {"employee_training_course_history": [
        {"course": "Food Handler", "description": "<p>State certificate</p>", "is_schedulable": True,
         "current_completed_date": "2024-02-10", "expires_on": "2027-02-10", "is_expired": False}]})
    _sub(b, "badges", aid, {"badges": [{"badge_number": "B-1101", "badge_type": "SIMPLE_1", "pin": "9999", "short_id": "S11", "effective_from": "2019-06-03"}]})
    _sub(b, "hr-custom-fields", aid, {"hr_custom_fields": [{"index": 0, "value": "Night shift"}]})
    _sub(b, "accrual/1/balances", aid, {"accrual_balances": [
        {"time_off": {"id": 41, "name": "PTO"}, "accrual_year": {"start_date": "2026-01-01", "end_date": "2026-12-31"},
         "accrued": 48 * HOUR_MS, "accrued_to": "2026-09-30", "carry_over": 8 * HOUR_MS, "taken": 16 * HOUR_MS,
         "remaining": 40 * HOUR_MS, "regular_day_time": 8 * HOUR_MS, "scheduled": 0, "pending_approval": 4 * HOUR_MS}]})
    _sub(b, "accrual/2/balances", aid, {"accrual_balances": [
        {"category": {"id": 51, "category_name": "Sick", "type": "ACCRUAL_CATEGORY", "color": "#00ff00"},
         "current_balance": {"hours": 12 * HOUR_MS + 30 * 60_000, "days": 1.5625}, "previous_carry_over": {"hours": 4 * HOUR_MS, "days": 0.5},
         "current_accrued": {"hours": 2 * HOUR_MS}, "taken": {"hours": 0}, "projected_balance": {"hours": 14 * HOUR_MS},
         "period": {"start": "2026-09-01", "end": "2026-09-30"}, "expiring_date": {"date": "2026-12-31"},
         "_precision": {"day_precision": 2, "hour_precision": 2}}]})
    return detail


def _account_2(b: Builder) -> dict:
    """The same person under EIN 502: rehired salaried manager; accrual/1 refused (403)."""
    aid = 1102
    first = "Ray"
    detail = _detail(b, {
        "id": aid, "username": "ray.second", "first_name": first, "last_name": "Account", "suffix": "Sr.", "employee_id": "U-1102",
        "status": "Active", "primary_account_id": 1101, "ein": {"id": 502}, "ein_name": "Harbor Catering LLC",
        "national_id_numbers": [{"type": "SSN", "value": "666-45-1101", "primary": True}],
        "address": {"country": "USA", "address_line_1": b.street(), "city": "Denver", "state_code": "CO", "zip": "80202"},
        "use_separate_mailing_address": False,
        "mailing_address": {"country": "USA", "address_line_1": "Ignored when not separate", "city": "Denver"},
        "phones": {"home_phone": "", "cell_phone": b.phone("303"), "preferred_phone": "WORK"},
        "dates": {"hired": "2015-02-01", "re_hired": "2024-03-04", "terminated": "2020-10-31", "seniority": "2015-02-01"},
    })
    _sub(b, "detail", aid, detail)
    _sub(b, "demographics", aid, {"gender": "MALE", "seasonal": None})
    _sub(b, "pay-info", aid, {"default_job": {"id": 502}, "job_last_changed": "2024-03-04", "employee_type": {"id": 61},
                              "pay_type": {"id": 72}, "payroll_classification": "REGULAR", "standard_work_day": 0})
    _sub(b, "profiles", aid, {"pay_period": [{"id": 9001, "name": "Biweekly", "effective_from": "2024-03-04"}]})
    _sub(b, "compensation/history", aid, {"compensations": [
        _compensation(aid, "2024-03-04", 58000.00, "YEAR", 27.8846, 40 * HOUR_MS, "WEEK", 3)]})
    _sub(b, "compensation/total", aid, {"total_compensations": []})
    _sub(b, "compensation/additional", aid, {"additional_compensations": [
        {"id": 7, "type": {"id": 3}, "account": {"id": aid}, "effective_from": "2024-03-04", "period": "YEAR", "active": True, "value": 5.0}]})
    _sub(b, "contacts", aid, {"contacts": []})
    _sub(b, "tax-info", aid, {"employee-tax-type": {"W2": True, "_1099": False}})
    _sub(b, "skills", aid, {"employee_skills": []})
    _sub(b, "training/certifications", aid, {"employee_training_course_history": []})
    _sub(b, "badges", aid, {"badges": []})
    _sub(b, "hr-custom-fields", aid, {"hr_custom_fields": []})
    _sub(b, "accrual/1/balances", aid, {"errors": [{"code": 403, "message": "Forbidden"}]}, status=403)
    _sub(b, "accrual/2/balances", aid, {"accrual_balances": []})
    return detail


def _account_3(b: Builder) -> dict:
    """Terminated contractor: NO_ID_NEEDED, unknown employee type, unlisted gender, no pay
    period profile, a cost center default missing from its tree."""
    aid = 1103
    first, last = b.name()
    detail = _detail(b, {
        "id": aid, "username": f"{first.lower()}.c", "first_name": first, "last_name": last, "employee_id": "U-1103",
        "status": "Terminated", "ein": {"id": 501}, "ein_name": "Harbor Kitchens Inc",
        "national_id_numbers": [{"type": "NO_ID_NEEDED", "primary": True}],
        "address": {"country": "USA", "address_line_1": b.street(), "city": "Boulder", "state_code": "CO", "zip": "80301"},
        "phones": {"cell_phone": b.phone("720"), "home_phone": b.phone("720"), "preferred_phone": "HOME"},
        "cost_centers_info": {"defaults": [{"index": 2, "value": {"id": 8399}}]},
        "dates": {"hired": "2022-05-02", "terminated": "2025-08-15", "deceased": "2025-08-20", "birthday": "1980-01-31"},
    })
    _sub(b, "detail", aid, detail)
    _sub(b, "demographics", aid, {"gender": "UNDEFINED"})
    _sub(b, "pay-info", aid, {"default_job": {"id": 599}, "employee_type": {"id": 62}, "pay_type": {"id": 73}, "payroll_classification": "REGULAR"})
    _sub(b, "profiles", aid, {"pay_period": []})
    _sub(b, "compensation/history", aid, {"compensations": [
        _compensation(aid, "2022-05-02", 4000.00, "MONTH", 23.0769, 0, "MONTH", 4)]})
    _sub(b, "compensation/total", aid, {"total_compensations": []})
    _sub(b, "compensation/additional", aid, {"additional_compensations": []})
    _sub(b, "contacts", aid, {"contacts": []})
    _sub(b, "tax-info", aid, {"employee-tax-type": {"W2": False, "_1099": True, "DRAW": False}})
    _sub(b, "skills", aid, {"employee_skills": []})
    _sub(b, "training/certifications", aid, {"employee_training_course_history": []})
    _sub(b, "badges", aid, {"badges": []})
    _sub(b, "hr-custom-fields", aid, {"hr_custom_fields": []})
    _sub(b, "accrual/1/balances", aid, {"accrual_balances": []})
    _sub(b, "accrual/2/balances", aid, {"errors": [{"code": 17605, "message": "No accruals profile"}]}, status=400)
    return detail
