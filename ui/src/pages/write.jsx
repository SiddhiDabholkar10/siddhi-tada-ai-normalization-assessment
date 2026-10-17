import { useEffect, useState } from "react";
import { api, useApi, useApp } from "../api.js";
import { go } from "../App.jsx";
import { requestKey, visible } from "../gate.js";
import { Empty, ErrorBox, Masonry, PROVIDERS, initials, isMasked, personName } from "../ui.jsx";

// Destination settings per provider (D-100): what a write may need that an employee record cannot supply.
const INPUTS = {
  "ukg-ready": [
    ["company", "UKG company id", "both"], ["username", "Username (unique in the destination)", "create"],
    ["start_date", "Start date (YYYY-MM-DD)", "create"],
    ["employee", "Account id to update", "update"],
  ],
  isolved: [
    ["company", "Client id", "both"], ["legal", "Legal code", "both"], ["id_type", "Id type", "both"],
    ["employment_status", "Employment status", "both"], ["employment_category", "Employment category", "both"],
    ["pay_type", "Pay type", "both"], ["pay_frequency", "Pay frequency (integer)", "both"], ["pay_group", "Pay group", "both"],
    ["work_location", "Work location", "both"], ["job", "Job code (optional)", "both"], ["employee", "Employee number to update", "update"],
  ],
  prismhr: [
    ["company", "Client id", "both"], ["peo_start_date", "PEO start date (YYYY-MM-DD)", "create"],
    ["employment_status", "Employee status code", "create"], ["employment_type", "Employee type code (optional)", "create"],
    ["work_location", "Work location code", "create"], ["job", "Job code", "create"], ["pay_group", "Pay group", "create"],
    ["employee", "Employee id to update", "update"], ["manager", "Manager employee id", "update"],
  ],
};

// The employee form: flat names the API maps onto the canonical record (write/plan.py FORM_FIELDS),
// laid out in the profile page's cards.
const LABELS = {
  first_name: "First", middle_name: "Middle", last_name: "Last", preferred_name: "Preferred first", prefix: "Prefix",
  suffix: "Suffix", employee_number: "Employee number", hire_date: "Hire date", original_hire_date: "Original hire date",
  ssn: "SSN", birth_date: "Birth date", work_email: "Email", work_phone: "Phone", personal_email: "Email",
  mobile_phone: "Mobile phone", home_phone: "Home phone", address_line1: "Line 1", address_line2: "Line 2", city: "City",
  state: "State", postal_code: "Postal code", country: "Country (3 letters)",
};
const CARDS = [
  ["Name and ids", ["first_name", "middle_name", "last_name", "preferred_name", "prefix", "suffix", "employee_number"]],
  ["Employment", ["hire_date", "original_hire_date"]],
  ["National id and birth date", ["ssn", "birth_date"]],
  ["Work contact", ["work_email", "work_phone"]],
  ["Personal contact", ["personal_email", "mobile_phone", "home_phone"]],
  ["Home address", ["address_line1", "address_line2", "city", "state", "postal_code", "country"]],
];
const ALL_CONTACT = ["work_email", "work_phone", "personal_email", "mobile_phone", "home_phone"];
const ADDRESS = ["address_line1", "address_line2", "city", "state", "postal_code"];
const NAMES = ["first_name", "middle_name", "last_name", "preferred_name", "prefix", "suffix"];
// The fields each destination's request accepts (the builders in src/normalization/write/), and the required ones.
const ACCEPTS = {
  "ukg-ready": {
    create: [...NAMES, "employee_number", "ssn", "birth_date", "hire_date", ...ALL_CONTACT, ...ADDRESS, "country"],
    update: [...NAMES, "employee_number", ...ALL_CONTACT, ...ADDRESS, "country"],
  },
  isolved: {
    create: [...NAMES, "ssn", "birth_date", "hire_date", "work_email", "personal_email", ...ADDRESS],
    update: [...NAMES, "ssn", "birth_date", "hire_date", "work_email", "personal_email", ...ADDRESS],
  },
  prismhr: {
    create: ["first_name", "middle_name", "last_name", "employee_number", "ssn", "birth_date", "hire_date", "original_hire_date",
      ...ALL_CONTACT, ...ADDRESS],
    update: ["first_name", "middle_name", "last_name", "preferred_name", "birth_date", ...ALL_CONTACT],
  },
};
const REQUIRED = {
  "ukg-ready": { create: ["first_name", "last_name", "birth_date"], update: [] },
  isolved: { create: ["first_name", "last_name", "ssn", "hire_date"], update: ["first_name", "last_name", "ssn", "hire_date"] },
  prismhr: { create: ["first_name", "last_name", "ssn", "hire_date", "original_hire_date"], update: [] },
};

const kindOf = (v) => (v && typeof v === "object" ? v.value : v);

/** The current value of a form field in a canonical employee. */
function readField(e, name) {
  if (!e) return null;
  const contact = e.personal_contact || {};
  const home = (contact.addresses || []).find((a) => (a.type || "home") === "home") || {};
  const phone = (kind) => (contact.phones || []).find((p) => kindOf(p.type) === kind)?.number;
  const direct = {
    first_name: e.name?.first, middle_name: e.name?.middle, last_name: e.name?.last, preferred_name: e.name?.preferred_first,
    prefix: e.name?.prefix, suffix: e.name?.suffix, employee_number: e.employee_number, birth_date: e.demographics?.birth_date,
    work_email: e.work_contact?.email, work_phone: e.work_contact?.phone, hire_date: e.employment?.hire_date,
    original_hire_date: e.employment?.original_hire_date,
    ssn: (e.national_ids || []).find((n) => kindOf(n.type) === "ssn")?.value,
    personal_email: (contact.emails || []).find((m) => kindOf(m.type) !== "work")?.address,
    mobile_phone: phone("mobile"), home_phone: phone("home"),
    address_line1: home.line1, address_line2: home.line2, city: home.city, state: home.state, postal_code: home.postal_code, country: home.country,
  };
  return direct[name] ?? null;
}

/** A request body as readable rows: "address / city" and its value. */
function rows(body, prefix = "") {
  if (body === null || body === undefined) return [];
  if (Array.isArray(body)) return body.flatMap((item, i) => rows(item, `${prefix}${prefix ? " / " : ""}${i + 1}`));
  if (typeof body === "object") return Object.entries(body).flatMap(([k, v]) => rows(v, `${prefix}${prefix ? " / " : ""}${k}`));
  return [[prefix, String(body)]];
}

function EmployeePicker() {
  const { dataset } = useApp();
  const [q, setQ] = useState("");
  const page = useApi(`/datasets/${dataset.id}/records/employees`, { q: q.trim(), limit: 8 });
  return (
    <div className="card card-pad">
      <div className="card-title">Start from an employee</div>
      <p className="muted" style={{ fontSize: 13, margin: "0 0 10px" }}>The form is filled from the employee, and you can change any field. Or start a new hire from a blank form.</p>
      <button className="btn btn-dark btn-sm" style={{ marginBottom: 12 }} onClick={() => go("write", "new")}>Start blank (new employee)</button>
      <input className="input" style={{ width: "100%", marginBottom: 8 }} placeholder="Search name, number or id" value={q} onChange={(e) => setQ(e.target.value)} />
      <div className="rows">
        {page.data?.items.map((e) => (
          <div key={e.id} className="row click" style={{ padding: "10px 4px" }} onClick={() => go("write", e.id)}>
            <span className="avatar" style={{ width: 30, height: 30, fontSize: 12 }}>{initials(personName(e))}</span>
            <div className="grow"><div className="name">{personName(e)}</div><div className="sub mono">{e.id}</div></div>
          </div>
        ))}
        {page.data && !page.data.items.length && <Empty>No employees match.</Empty>}
      </div>
    </div>
  );
}

export function WriteEmployee({ id }) {
  const { dataset, sensitive } = useApp();
  const blank = id === "new";
  const [destination, setDestination] = useState(dataset?.provider || "ukg-ready");
  const [operation, setOperation] = useState("create");
  const [inputs, setInputs] = useState({});
  const [changes, setChanges] = useState({});
  const [state, setState] = useState(null);
  const [confirming, setConfirming] = useState(false);
  const [result, setResult] = useState(null);
  const [sending, setSending] = useState(false);
  const record = useApi(id && !blank ? `/datasets/${dataset.id}/records/employees/${encodeURIComponent(id)}` : null);
  const item = record.data?.item;
  const body = { dataset_id: dataset?.id, employee_id: blank ? null : id, changes, destination, operation, inputs };
  const key = requestKey("/write/preview", body, sensitive);

  useEffect(() => {
    if (!id || !dataset) return undefined;
    let live = true;
    const timer = setTimeout(() => {
      api("/write/preview", {}, false, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...body, show_sensitive: sensitive }) })
        .then((data) => live && setState({ data, error: null, loading: false, key }))
        .catch((error) => live && setState({ data: null, error: error.message, loading: false, key }));
    }, 300);
    return () => { live = false; clearTimeout(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  useEffect(() => { setConfirming(false); setResult(null); }, [key]);
  useEffect(() => {
    const allowed = blank ? ["create"] : item && item.provider === destination ? ["update"] : ["create", "update"];
    if (!allowed.includes(operation)) setOperation(allowed[0]);
  }, [blank, item, destination, operation]);

  if (!dataset) return <Empty>No datasets yet.</Empty>;
  const preview = visible(state, key); // shown only while it answers the current form and switch (gate.js)
  const plan = preview.data;
  const same = item && item.provider === destination;
  // Blank form: a new hire, create only. The employee's own provider: they exist there, update only.
  const operations = blank ? ["create"] : same ? ["update"] : ["create", "update"];
  const settings = INPUTS[destination].filter(([, , when]) => when === "both" || when === operation);
  const ownCompany = same ? (item.source_ids || {})[destination === "ukg-ready" ? "companyId" : "clientId"] : null;
  const hint = (name) => {
    if (name === "company") return ownCompany ? `Leave empty to use ${ownCompany} (the employee's own company)` : "Required: the destination company";
    if (name === "username") return "Required: a new, unique username, e.g. tada.normalization.test1";
    if (name === "start_date") return item && item.provider === "ukg-ready" ? "Leave empty to use the employee's own UKG start date" : "Required by UKG: the first day of work (not the hire date)";
    if (name === "peo_start_date") return "Required: the start with the PEO (not the hire date)";
    if (name === "employee") return same ? "Leave empty to update this same employee" : "Required: the destination's id of the employee";
    return same ? "Leave empty to reuse the employee's own code" : "Required: the destination's code";
  };
  const changed = Object.keys(changes).length;
  const ready = Boolean(plan?.sendable) && !result?.ok;
  const buttonTitle = !plan ? "Building the dry run"
    : destination !== "ukg-ready" ? `Dry run only: ${PROVIDERS[destination]} is never sent`
      : result?.ok ? "Done" : plan.refusals.length ? `${plan.refusals.length} missing: see Review below` : "Ready to send";

  const setField = (name, value) => {
    const original = readField(item, name);
    const next = { ...changes };
    if (!isMasked(original) && (value === (original ?? "") )) delete next[name];
    else next[name] = value;
    setChanges(next);
  };

  const sendNow = async () => {
    setSending(true);
    try {
      setResult(await api("/write/send", {}, false, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...body, confirm: true }) }));
    } catch (e) {
      setResult({ ok: false, error: e.message, calls: [] });
    }
    setSending(false);
    setConfirming(false);
  };

  const accepted = new Set(ACCEPTS[destination][operation]);
  const required = new Set(REQUIRED[destination][operation]);
  const cards = CARDS.map(([title, names]) => [title, names.filter((n) => accepted.has(n))]).filter(([, names]) => names.length);

  return (
    <>
      <p className="eyebrow">Write employee</p>
      <h1 className="title">{blank ? "New employee" : operation === "update" ? "Edit employee" : "Copy employee"}</h1>
      <p className="lede">
        {blank ? "Fill in the fields" : "Change any field"} {PROVIDERS[destination]} accepts, then review what would be sent at the bottom.
        Only UKG Ready can be sent for real, after you confirm; isolved and PrismHR show their exact request as a dry run.
      </p>
      {!id && <div style={{ maxWidth: 620 }}><EmployeePicker /></div>}
      {id && (
        <>
          <div className="card card-pad" style={{ display: "flex", gap: 18, alignItems: "center", flexWrap: "wrap", marginBottom: 16 }}>
            <span className="avatar lg">{blank ? "+" : initials(personName(item))}</span>
            <div style={{ flex: 1, minWidth: 220 }}>
              <div style={{ fontSize: 24, fontWeight: 500 }}>{blank ? "New employee" : item ? personName(item) : "Loading"}</div>
              {!blank && <div className="mono faint" style={{ overflowWrap: "anywhere" }}>{id}</div>}
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
              <div className="segmented">
                {Object.keys(INPUTS).map((p) => (
                  <button key={p} className={destination === p ? "on" : ""} onClick={() => { setDestination(p); setInputs({}); }}>
                    {PROVIDERS[p]}{p !== "ukg-ready" && <span className="faint" style={{ fontSize: 12 }}> (dry run)</span>}
                  </button>
                ))}
              </div>
              {!blank && <button className="btn btn-sm" onClick={() => go("write")}>Pick another employee</button>}
            </div>
          </div>
          <div className="card card-pad action-card">
            <div className="action-settings">
              <div className="card-title">Settings for {PROVIDERS[destination]}</div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: 10 }}>
                {settings.map(([name, label]) => (
                  <label key={name} style={{ fontSize: 13 }}>
                    <span className="muted">{label}</span>
                    <input className="input" style={{ width: "100%", marginTop: 4 }} value={inputs[name] || ""} placeholder={hint(name)}
                      onChange={(e) => setInputs({ ...inputs, [name]: e.target.value })} />
                  </label>
                ))}
              </div>
            </div>
            <div className="action-panel">
              {operations.length > 1 && (
                <div className="segmented" style={{ alignSelf: "stretch" }}>
                  {operations.map((o) => (
                    <button key={o} style={{ flex: 1 }} className={operation === o ? "on" : ""} onClick={() => setOperation(o)}>
                      {o === "create" ? "Create" : "Update"}
                    </button>
                  ))}
                </div>
              )}
              <button className={`action-button ${ready ? "ready" : ""}`} disabled={!ready || sending} title={buttonTitle}
                onClick={() => setConfirming(true)}>
                {operation === "create" ? "Create Employee" : "Update Employee"}
              </button>
              {confirming && (
                <div className="action-confirm">
                  <div>Send to the UKG demo tenant? It cannot be undone.</div>
                  <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                    <button className="btn btn-dark btn-sm" disabled={sending} onClick={sendNow}>{sending ? "Sending" : "Confirm"}</button>
                    <button className="btn btn-sm" disabled={sending} onClick={() => setConfirming(false)}>Cancel</button>
                  </div>
                </div>
              )}
              {result && (
                <div className={`action-result ${result.ok ? "ok" : "bad"}`}>
                  {result.ok ? (operation === "create" ? "Created" : "Updated") : "Not accepted"}
                  {(result.calls || []).map((c, i) => (
                    <div key={i} style={{ fontWeight: 400, fontSize: 13, marginTop: 4 }}>
                      {c.outcome === "done" && c.id && `New account id ${c.id}`}
                      {c.outcome === "failed" && (c.messages?.join(" ") || "Refused without a message.")}
                      {c.status === 0 && "No answer: it may or may not have been applied (not retried)."}
                    </div>
                  ))}
                  {result.error && <div style={{ fontWeight: 400, fontSize: 13, marginTop: 4 }}>{result.error}</div>}
                </div>
              )}
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, margin: "0 0 12px", flexWrap: "wrap" }}>
            <span className="muted" style={{ fontSize: 14 }}>
              Fields {PROVIDERS[destination]} accepts for {operation === "create" ? "a create" : "an update"}; * is required.
            </span>
            {changed > 0 && <span className="badge soft">{changed} changed</span>}
            {changed > 0 && <button className="btn btn-sm" onClick={() => setChanges({})}>Undo changes</button>}
            <span className="spacer" />
            {plan && (plan.refusals.length ? <a className="badge warn" href="#review" onClick={(ev) => { ev.preventDefault(); document.getElementById("review")?.scrollIntoView({ behavior: "smooth" }); }}>{plan.refusals.length} missing: review</a>
              : <span className="badge ok">ready</span>)}
          </div>
          <Masonry minWidth={340}>
            {cards.map(([title, names]) => (
              <div className="card card-pad" key={title}>
                <div className="card-title">{title}</div>
                <div className="fields">
                  {names.map((name) => {
                    const original = readField(item, name);
                    const hidden = isMasked(original);
                    const value = name in changes ? changes[name] : hidden ? "" : original ?? "";
                    return (
                      <div key={name} style={{ display: "contents" }}>
                        <div className="k">{LABELS[name]}{required.has(name) && " *"}{name in changes && <span title="changed" style={{ color: "var(--accent)", marginLeft: 6 }}>&#9679;</span>}</div>
                        <div className="v">
                          <input className="input" style={{ width: "100%", borderRadius: 10, padding: "6px 10px" }} value={value}
                            placeholder={hidden ? "Hidden: unchanged unless you type" : blank ? "" : "empty"}
                            onChange={(e) => setField(name, e.target.value)} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </Masonry>
          <p className="muted" style={{ fontSize: 13, margin: "4px 0 0" }}>
            Only the fields you change are sent to the server; values hidden by the masking switch stay as stored.
          </p>

          <h2 className="section" id="review">Review and send</h2>
          {preview.error && <ErrorBox error={preview.error} />}
          {!plan && !preview.error && <div className="card"><Empty>Building the dry run</Empty></div>}
          {plan && (
            <div className="panel">
              <div className="card" style={{ padding: "12px 16px", display: "flex", alignItems: "center", gap: 10, marginBottom: 10, flexWrap: "wrap" }}>
                <span style={{ fontWeight: 500 }}>Dry run: {PROVIDERS[plan.destination]} {plan.operation}</span>
                <span className="spacer" />
                {plan.refusals.length ? <span className="badge warn">{plan.refusals.length} missing</span> : <span className="badge ok">ready</span>}
              </div>
              <p style={{ fontSize: 14, margin: "0 4px 10px" }}>
                {plan.destination !== "ukg-ready"
                  ? `Dry run only: ${PROVIDERS[plan.destination]} is never sent for real (it would need a real SSN in a shared demo tenant).`
                  : plan.sendable
                    ? `Ready. Check what will be sent below, then use ${operation === "create" ? "Create Employee" : "Update Employee"} above.`
                    : "Fill in what is missing (settings or fields above); the button above turns blue when nothing is."}
              </p>
              {plan.refusals.length > 0 && (
                <div className="card rows" style={{ marginBottom: 10 }}>
                  {plan.refusals.map((r, i) => (
                    <div key={i} className="row" style={{ padding: "10px 16px" }}>
                      <span className="icon-dot warn">!</span>
                      <div className="grow"><span className="badge">{r.field}</span> <span style={{ fontSize: 14 }}>{r.reason}</span></div>
                    </div>
                  ))}
                </div>
              )}
              {plan.calls.map((c, i) => (
                <div key={i} className="card card-pad" style={{ marginBottom: 10 }}>
                  <div className="card-title"><span className="badge dark">{c.method}</span> <span className="mono">{c.path}</span></div>
                  {c.note && <p className="muted" style={{ fontSize: 13, margin: "0 0 8px" }}>{c.note}</p>}
                  {rows(c.body).length > 0 && (
                    <table className="lines" style={{ marginBottom: 8 }}>
                      <tbody>
                        {rows(c.body).map(([path, value]) => (
                          <tr key={path}><td className="muted" style={{ width: "45%" }}>{path}</td><td>{isMasked(value) ? <span className="masked">{value}</span> : value}</td></tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                  {Object.keys(c.query || {}).length > 0 && <div className="mono muted" style={{ marginBottom: 6 }}>?{new URLSearchParams(c.query).toString()}</div>}
                  {c.body !== null && c.body !== undefined && (
                    <details>
                      <summary className="muted" style={{ fontSize: 13, cursor: "pointer" }}>Show the exact request (JSON)</summary>
                      <pre className="mono" style={{ background: "var(--panel)", borderRadius: 12, padding: 12, overflowX: "auto", margin: "8px 0 0", fontSize: 12.5 }}>
                        {JSON.stringify(c.body, null, 2)}
                      </pre>
                    </details>
                  )}
                </div>
              ))}
              {plan.notes.map((n, i) => <p key={i} className="muted" style={{ fontSize: 13, margin: "6px 4px" }}>{n}</p>)}
            </div>
          )}
        </>
      )}
    </>
  );
}
