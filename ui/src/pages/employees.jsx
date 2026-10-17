import { useEffect, useState } from "react";
import { useApi, useApp } from "../api.js";
import { go } from "../App.jsx";
import { CompanyFilter } from "./overview.jsx";
import {
  Chevron, DiagnosticRow, Empty, ErrorBox, Fields, Loading, Masonry, Pager, rowCount, StatusBadge, Val, coded, humanize, initials, money,
  personName, shortId,
} from "../ui.jsx";

const warningCount = (record) => (record.diagnostics || []).filter((d) => d.severity === "warning").length;

export function Employees() {
  const { dataset, companies, route } = useApp();
  const [company, setCompany] = useState(route.query.get("company"));
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const limit = 25;
  useEffect(() => {
    const timer = setTimeout(() => { setSearch(q.trim()); setOffset(0); }, 250);
    return () => clearTimeout(timer);
  }, [q]);
  const page = useApi(`/datasets/${dataset.id}/records/employees`, { offset, limit, q: search, company_id: company });
  return (
    <>
      <p className="eyebrow">Employees</p>
      <h1 className="title">People</h1>
      <p className="lede">Every employee with their deposits, deductions, benefits and paychecks linked by canonical id.</p>
      <div className="toolbar">
        <input className="input" style={{ width: 280 }} placeholder="Search name, number or id" value={q} onChange={(e) => setQ(e.target.value)} />
        <CompanyFilter value={company} onChange={(v) => { setCompany(v); setOffset(0); }} />
        <span className="spacer" />
        {page.data && <span className="muted" style={{ fontSize: 14 }}>{page.data.total.toLocaleString()} employees</span>}
      </div>
      {page.error && <ErrorBox error={page.error} />}
      <div className="card rows">
        {page.data?.items.map((e) => {
          const warnings = warningCount(e);
          return (
            <div key={e.id} className="row click" onClick={() => go("employees", e.id)}>
              <span className="avatar">{initials(personName(e))}</span>
              <div className="grow">
                <div className="name">{personName(e)}</div>
                <div className="sub">
                  {[e.job?.job?.name || e.job?.title, companies[e.company_id], e.employee_number && `#${e.employee_number}`].filter(Boolean).join(" / ")}
                </div>
              </div>
              <div className="right">
                {warnings > 0 && <span className="badge warn" title="warning diagnostics">{warnings} flagged</span>}
                <StatusBadge value={e.employment?.status} />
                <span className="muted" style={{ fontSize: 13, minWidth: 90, textAlign: "right" }}>
                  {e.employment?.hire_date ? `hired ${e.employment.hire_date}` : ""}
                </span>
              </div>
            </div>
          );
        })}
        {page.data && !page.data.items.length && <Empty>No employees match.</Empty>}
        {!page.data && !page.error && <Loading />}
      </div>
      {page.data && <Pager offset={offset} limit={limit} total={page.data.total} onChange={setOffset} />}
    </>
  );
}

/** Employment type for the header. An unknown value shows the provider's own label (or code),
 *  marked unmapped: the client-defined code has no documented meaning (D-074), so the canonical
 *  value stays unknown and only the display says what the provider called it. */
function TypeBadge({ value }) {
  if (!value || !value.value) return null;
  if (value.value !== "unknown") return <span className="badge">{humanize(value.value)}</span>;
  const shown = value.raw_label || value.raw_code;
  if (!shown) return <span className="badge warn">Unknown type</span>;
  return (
    <span className="badge warn" title={`Client-defined code ${value.raw_code} has no documented meaning, so the canonical employment type is unknown. "${shown}" is the provider's own label.`}>
      {shown} (unmapped)
    </span>
  );
}

const TABS = [
  ["profile", "Profile"], ["direct_deposits", "Direct deposits"], ["deduction_setups", "Deductions"],
  ["benefit_enrollments", "Benefits"], ["paychecks", "Paychecks"], ["diagnostics", "Diagnostics"],
];

export function EmployeeDetail({ id }) {
  const { dataset, companies, route } = useApp();
  const [tab, setTab] = useState(route.query.get("tab") || "profile");
  const record = useApi(`/datasets/${dataset.id}/records/employees/${encodeURIComponent(id)}`);
  const counts = {};
  for (const name of ["direct_deposits", "deduction_setups", "benefit_enrollments", "paychecks"]) {
    // eslint-disable-next-line react-hooks/rules-of-hooks
    counts[name] = useApi(`/datasets/${dataset.id}/records/${name}`, { employee_id: id, limit: 1 }).data?.total;
  }
  if (record.error) return <><a className="back" href="#/employees">&#8592; Employees</a><ErrorBox error={record.error} /></>;
  if (!record.data) return <Loading />;
  const e = record.data.item;
  const employment = e.employment || {};
  counts.diagnostics = e.diagnostics?.length || 0;
  return (
    <>
      <a className="back" href="#/employees">&#8592; Employees</a>
      <div className="card card-pad" style={{ display: "flex", gap: 18, alignItems: "center", flexWrap: "wrap", marginBottom: 18 }}>
        <span className="avatar lg">{initials(personName(e))}</span>
        <div style={{ flex: 1, minWidth: 220 }}>
          <div style={{ fontSize: 26, fontWeight: 500, letterSpacing: "-0.01em" }}>{personName(e)}</div>
          <div className="muted" style={{ marginTop: 4 }}>
            {[e.job?.job?.name, companies[e.company_id], e.employee_number && `#${e.employee_number}`].filter(Boolean).join(" / ")}
          </div>
          <div className="mono faint" style={{ marginTop: 4 }}>{e.id}</div>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <StatusBadge value={employment.status} />
          <TypeBadge value={employment.employment_type} />
          {employment.hire_date && <span className="badge">hired {employment.hire_date}</span>}
          {employment.termination_date && <span className="badge danger">terminated {employment.termination_date}</span>}
          <button className="btn btn-sm" onClick={() => go("write", e.id)}>Write to a provider</button>
        </div>
      </div>
      <div className="segmented" style={{ marginBottom: 18 }}>
        {TABS.map(([key, label]) => (
          <button key={key} className={tab === key ? "on" : ""} onClick={() => setTab(key)}>
            {label}
            {key !== "profile" && counts[key] !== undefined && <span className="count">{counts[key]}</span>}
          </button>
        ))}
      </div>
      {tab === "profile" && <Profile e={e} />}
      {tab === "diagnostics" && (
        <div className="card rows">
          {e.diagnostics?.length ? e.diagnostics.map((d, i) => <DiagnosticRow key={i} d={d} />) : <Empty>No diagnostics on this record.</Empty>}
        </div>
      )}
      {["direct_deposits", "deduction_setups", "benefit_enrollments", "paychecks"].includes(tab) && (
        <Linked key={tab} list={tab} employeeId={id} />
      )}
    </>
  );
}

// Ordered by weight for payroll and HR work: who and whether employed, how they are paid and
// taxed, then contact, compliance and balances, then history, then peripheral details.
const PROFILE_SECTIONS = [
  ["employment", "Employment"], ["compensation", "Compensation"], ["job", "Job"],
  ["tax_withholding", "Tax withholding"], ["national_ids", "National ids"], ["work_contact", "Work contact"],
  ["personal_contact", "Personal contact"], ["pto_balances", "PTO balances"], ["work_authorization", "Work authorization"],
  ["demographics", "Demographics"], ["compensation_history", "Compensation history"],
  ["employment_history", "Employment history"], ["job_history", "Job history"], ["related_people", "Related people"],
  ["qualifications", "Qualifications"],
];

function Profile({ e }) {
  const status = e.field_status || {};
  const ids = { ...e.name, employee_number: e.employee_number, currency: e.currency, company_id: e.company_id, tax_entity_id: e.tax_entity_id };
  const weights = [rowCount(ids), ...PROFILE_SECTIONS.map(([key]) => rowCount(e[key]))];
  return (
    <Masonry weights={weights}>
      <div className="card card-pad">
        <div className="card-title">Name and ids</div>
        <Fields obj={ids} />
      </div>
      {PROFILE_SECTIONS.map(([key, title]) => {
        const value = e[key];
        const empty = value === null || value === undefined || (Array.isArray(value) && !value.length);
        return (
          <div className="card card-pad" key={key}>
            <div className="card-title">{title} {Array.isArray(value) && value.length > 0 && <span className="count">{value.length}</span>}</div>
            {empty ? <Val v={null} reason={status[key]} /> : Array.isArray(value)
              ? value.slice(0, 12).map((item, i) => <div className="sub-card" key={i}><Fields obj={item} /></div>)
              : <Fields obj={value} />}
          </div>
        );
      })}
    </Masonry>
  );
}

function Linked({ list, employeeId }) {
  const { dataset } = useApp();
  const [offset, setOffset] = useState(0);
  const [open, setOpen] = useState(null);
  const limit = 20;
  const page = useApi(`/datasets/${dataset.id}/records/${list}`, { employee_id: employeeId, offset, limit });
  if (page.error) return <ErrorBox error={page.error} />;
  if (!page.data) return <Loading />;
  if (!page.data.items.length) {
    const reason = dataset.counts?.[list] === 0 ? " The provider has no source for this list." : "";
    return <div className="card"><Empty>None for this employee.{reason}</Empty></div>;
  }
  return (
    <>
      <div className="card rows">
        {page.data.items.map((r) => (
          <div key={r.id}>
            <div className="row click" onClick={() => setOpen(open === r.id ? null : r.id)}>
              <Summary list={list} r={r} />
              <span className="faint" style={{ transform: open === r.id ? "rotate(90deg)" : "none", transition: "transform .15s" }}><Chevron /></span>
            </div>
            {open === r.id && (
              <div style={{ background: "var(--panel-2)", padding: "6px 18px 16px" }}>
                {list === "paychecks" && <PaycheckLines p={r} />}
                <Fields obj={r} skip={list === "paychecks" ? ["earnings", "deductions", "taxes", "employer_contributions", "payments"] : []} />
                {r.diagnostics?.length > 0 && (
                  <div className="card rows" style={{ marginTop: 12 }}>{r.diagnostics.map((d, i) => <DiagnosticRow key={i} d={d} />)}</div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
      <Pager offset={offset} limit={limit} total={page.data.total} onChange={setOffset} />
    </>
  );
}

function Summary({ list, r }) {
  const warnings = warningCount(r);
  const flag = warnings > 0 && <span className="badge warn">{warnings} flagged</span>;
  if (list === "direct_deposits") {
    const allocation = coded(r.allocation_type);
    const amount = r.percent !== null && r.percent !== undefined ? `${r.percent}%` : money(r.amount, r.currency);
    return (
      <>
        <span className="icon-dot info">$</span>
        <div className="grow">
          <div className="name">{r.bank_name || "Bank account"} <span className="muted" style={{ fontWeight: 400 }}>{humanize(coded(r.account_type) || "account")}</span></div>
          <div className="sub" style={{ display: "flex", gap: 8, alignItems: "center" }}>
            Account <Val v={r.account_number ?? (r.account_last4 ? `...${r.account_last4}` : null)} reason={r.field_status?.account_number} />
          </div>
        </div>
        <div className="right">{flag}<span className="badge">{allocation ? humanize(allocation) : "allocation"}</span><b>{amount}</b><StatusBadge value={r.status} /></div>
      </>
    );
  }
  if (list === "deduction_setups") {
    const amount = r.percent !== null && r.percent !== undefined ? `${r.percent}%` : money(r.amount, r.currency);
    return (
      <>
        <span className="icon-dot">&#8722;</span>
        <div className="grow">
          <div className="name">{r.deduction_code?.name || r.deduction_code?.code || shortId(r.id)}</div>
          <div className="sub">{[humanize(coded(r.category) || "deduction"), coded(r.tax_treatment) && humanize(coded(r.tax_treatment)), r.start_date && `from ${r.start_date}`].filter(Boolean).join(" / ")}</div>
        </div>
        <div className="right">{flag}{r.garnishment && <span className="badge danger">garnishment</span>}<b>{amount || ""}</b><StatusBadge value={r.status} /></div>
      </>
    );
  }
  if (list === "benefit_enrollments") {
    return (
      <>
        <span className="icon-dot info">+</span>
        <div className="grow">
          <div className="name">{r.plan?.name || r.plan?.code || shortId(r.id)}</div>
          <div className="sub">{[coded(r.benefit_type) && humanize(coded(r.benefit_type)), coded(r.coverage_level) && humanize(coded(r.coverage_level)), r.coverage_start && `from ${r.coverage_start}`].filter(Boolean).join(" / ")}</div>
        </div>
        <div className="right">{flag}<StatusBadge value={r.status} /></div>
      </>
    );
  }
  return (
    <>
      <span className="icon-dot dark">$</span>
      <div className="grow">
        <div className="name">{r.pay_date || "No pay date"} <span className="muted" style={{ fontWeight: 400 }}>{r.check_number ? `check ${r.check_number}` : ""}</span></div>
        <div className="sub">{[r.period_start && `${r.period_start} to ${r.period_end}`, coded(r.kind) && humanize(coded(r.kind))].filter(Boolean).join(" / ")}</div>
      </div>
      <div className="right">
        {flag}<StatusBadge value={r.status} />
        <span className="muted" style={{ fontSize: 13 }}>gross</span><b>{money(r.gross_pay ?? r.total_earnings, r.currency) || "none"}</b>
        <span className="muted" style={{ fontSize: 13 }}>net</span><b>{money(r.net_pay, r.currency) || "none"}</b>
      </div>
    </>
  );
}

function lineName(line) {
  const ref = line.earning_code || line.deduction_code || line.tax_code || line.plan || {};
  return ref.name || ref.code || coded(line.tax_type) || coded(line.method) || "line";
}

function PaycheckLines({ p }) {
  const groups = [["earnings", "Earnings"], ["deductions", "Deductions"], ["taxes", "Taxes"], ["employer_contributions", "Employer contributions"], ["payments", "Payments"]];
  return (
    <Masonry minWidth={340} weights={groups.filter(([key]) => p[key]?.length).map(([key]) => p[key].length)} style={{ margin: "8px 0 14px" }}>
      {groups.filter(([key]) => p[key]?.length).map(([key, title]) => (
        <div className="card card-pad" key={key}>
          <div className="card-title">{title} <span className="count">{p[key].length}</span></div>
          <div className="table-wrap">
            <table className="lines">
              <thead><tr><th>Item</th>{key === "earnings" && <th className="num">Hours</th>}<th className="num">Amount</th></tr></thead>
              <tbody>
                {p[key].map((line, i) => (
                  <tr key={i}>
                    <td>{lineName(line)} {line.paid_by && <span className="faint">({humanize(coded(line.paid_by))})</span>}</td>
                    {key === "earnings" && <td className="num">{line.hours ?? ""}</td>}
                    <td className="num">{money(line.amount, p.currency)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </Masonry>
  );
}
