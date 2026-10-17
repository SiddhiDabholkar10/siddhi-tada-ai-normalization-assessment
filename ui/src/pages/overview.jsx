import { useState } from "react";
import { useApi, useApp } from "../api.js";
import { go } from "../App.jsx";
import {
  DiagnosticRow, Empty, ErrorBox, Group, KINDS, LISTS, Loading, PROVIDERS, Pager, SeverityIcon, StatusBadge, Val,
  coded, companyName, hasCompanyName, humanize, initials, money, personName, shortId,
} from "../ui.jsx";

export const CODE_HELP = {
  unknown_code: "Provider code with no canonical meaning; the value is unknown.",
  inferred_mapping: "Canonical value inferred from indirect evidence, not documented.",
  value_redacted_in_source: "The provider masked the value; it is not stored.",
  sentinel_date: "Placeholder date where a real date is required.",
  empty_via_404: "The route reports no records as HTTP 404.",
  source_unavailable: "The provider has no source for this data, or refused it.",
  unparseable_value: "The value could not be read as its canonical type.",
  reconciliation_mismatch: "Provider totals disagree with the line items.",
  reconciliation_incomplete: "Totals could not be checked against complete lines.",
  conflicting_sources: "Two provider sources disagree on one fact.",
  unit_unverified: "Unit or scale not established; value kept raw.",
  deprecated_source: "Data came from a route the provider marks deprecated.",
  unvalidated_source: "Source not validated for this meaning.",
  unstable_id: "Id rests on list order, not a provider id.",
  reference_only: "Built from records that name it; the provider's own list omits it.",
};

function OverviewHeader({ dataset, run }) {
  return (
    <div>
      <p className="eyebrow">{PROVIDERS[dataset.provider] || dataset.provider} / tenant {dataset.tenant_id}</p>
      <h1 className="title">{PROVIDERS[dataset.provider] || dataset.provider} tenant overview</h1>
      <p className="lede">
        {KINDS[dataset.kind]} from {run.input || "a bundle"}, stored {dataset.created_at.replace("T", " ").slice(0, 16)} UTC.
        Every record follows one canonical model across PrismHR, isolved and UKG Ready, with diagnostics where the
        provider data is unclear. {dataset.kept_values === "masked" ? "Values were masked before import." : "Sensitive values are masked unless you opt in."}
      </p>
    </div>
  );
}

function RunSummary({ dataset, run }) {
  const counts = run.counts || {};
  const warnings = (dataset.diagnostics || []).filter((d) => d.severity === "warning").reduce((n, d) => n + d.count, 0);
  const fetch = run.fetch;
  const problems = run.link_problems?.length || 0;
  const setAside = run.unusable_responses?.length || 0;
  return (
    <div className="panel accent">
      <div className="card" style={{ padding: "12px 16px", display: "flex", alignItems: "center", gap: 12, marginBottom: 10 }}>
        <span className="avatar dark" style={{ width: 34, height: 34, fontSize: 13 }}>{initials(PROVIDERS[dataset.provider])}</span>
        <span style={{ fontWeight: 500 }}>Run summary</span>
      </div>
      <div className="card feed rows">
        <div className="row"><span className="icon-dot info">$</span><div className="grow"><b>{counts.payroll_runs ?? 0}</b> <span className="muted">payroll runs and</span> <b>{(counts.paychecks ?? 0).toLocaleString()}</b> <span className="muted">paychecks normalized</span></div></div>
        <div className="row"><span className="icon-dot">+</span><div className="grow"><b>{counts.employees ?? 0}</b> <span className="muted">employees in</span> <b>{counts.companies ?? 0}</b> <span className="muted">companies</span></div></div>
        <div className="row"><span className={`icon-dot ${problems ? "warn" : "ok"}`}>{problems ? "!" : "✓"}</span><div className="grow"><b>{problems}</b> <span className="muted">link problems</span></div></div>
        <div className="row"><span className={`icon-dot ${setAside ? "warn" : "ok"}`}>{setAside ? "!" : "✓"}</span><div className="grow"><b>{setAside}</b> <span className="muted">responses set aside</span></div></div>
        <div className="row"><span className="icon-dot warn">!</span><div className="grow"><b>{warnings.toLocaleString()}</b> <span className="muted">warning diagnostics</span></div></div>
        {fetch && (
          <div className="row"><span className="icon-dot dark">&#8635;</span><div className="grow"><span className="muted">Fetched</span> <b>{fetch.calls?.toLocaleString()}</b> <span className="muted">calls in</span> <b>{fetch.seconds} s</b></div></div>
        )}
      </div>
    </div>
  );
}

export function Overview() {
  const { dataset: summary } = useApp();
  const detail = useApi(`/datasets/${summary.id}`);
  const companies = useApi(`/datasets/${summary.id}/records/companies`, { limit: 200 });
  if (detail.error) return <ErrorBox error={detail.error} />;
  if (!detail.data) return <Loading />;
  const dataset = detail.data;
  const run = dataset.run;
  const target = { companies: null, payroll_runs: "payroll", paychecks: "payroll" };
  return (
    <>
      <OverviewHeader dataset={dataset} run={run} />
      <h2 className="section" style={{ marginTop: 8 }}>Records</h2>
      <div className="grid-stats">
        {Object.entries(LISTS).map(([name, label]) => (
          <div key={name} className="card stat" onClick={() => target[name] !== null && go(target[name] || "employees")}>
            <div className="n">{(run.counts?.[name] ?? 0).toLocaleString()}</div>
            <div className="l">{label}{run.not_normalized?.[name] ? " (no source)" : ""}</div>
          </div>
        ))}
      </div>
      <div className="two-col">
        <div>
          <h2 className="section">Companies <span className="count">{companies.data?.total ?? ""}</span></h2>
          <div className="card rows">
            {companies.data?.items.map((c) => (
              <div key={c.id} className="row click" onClick={() => go("employees", null, { company: c.id })}>
                <span className="avatar">{initials(companyName(c))}</span>
                <div className="grow">
                  <div className="name">{companyName(c)}</div>
                  <div className="sub">
                    {hasCompanyName(c)
                      ? [c.legal_name !== companyName(c) && c.legal_name, c.company_code, shortId(c.id)].filter(Boolean).join(" / ")
                      : `No company name: ${PROVIDERS[c.provider] || "the provider"} does not send one`}
                  </div>
                </div>
                <div className="right">
                  {c.diagnostics?.some((d) => d.code === "reference_only" && !d.field) && <span className="badge soft">reference only</span>}
                  <StatusBadge value={c.status} />
                </div>
              </div>
            ))}
            {companies.data && !companies.data.items.length && <Empty>No companies</Empty>}
          </div>
        </div>
        <div>
          <h2 className="section">Run health</h2>
          <RunHealth run={run} />
        </div>
      </div>
    </>
  );
}

export function RunHealth({ run }) {
  const fetch = run.fetch;
  return (
    <>
      <Group title="Link problems" count={run.link_problems?.length || 0} icon={<SeverityIcon severity={run.link_problems?.length ? "warning" : "info"} />}>
        {run.link_problems?.length ? run.link_problems.map((p, i) => <div className="line" key={i}>{p}</div>) : <div className="line">Every link resolves to a record in this run.</div>}
      </Group>
      <Group title="Responses set aside" count={run.unusable_responses?.length || 0} icon={<SeverityIcon severity={run.unusable_responses?.length ? "warning" : "info"} />}>
        {run.unusable_responses?.length ? run.unusable_responses.map((p, i) => <div className="line" key={i}>{p}</div>) : <div className="line">Every response had the shape its contract documents.</div>}
      </Group>
      <Group title="Not normalized" count={Object.keys(run.not_normalized || {}).length} icon={<SeverityIcon severity="info" />}>
        {Object.entries(run.not_normalized || {}).map(([name, reason]) => <div className="line" key={name}><b>{LISTS[name] || name}</b>: {reason}</div>)}
        {!Object.keys(run.not_normalized || {}).length && <div className="line">Every list has an adapter for this provider.</div>}
      </Group>
      {fetch && (
        <Group title="Fetch report" count={fetch.calls?.toLocaleString()} icon={<span className="icon-dot dark">&#8635;</span>}>
          <div className="line">Tenant {fetch.tenant}, fetched {fetch.fetched_at}, today taken as {fetch.today}</div>
          <div className="line">{fetch.calls?.toLocaleString()} calls in {fetch.seconds} s; sign-ins {fetch.sign_ins}</div>
          <div className="line">Statuses: {Object.entries(fetch.statuses || {}).map(([s, n]) => `${s} x${n}`).join(", ")}</div>
          <div className="line">Unanswered after retries: {Object.keys(fetch.unanswered || {}).length || "none"}</div>
          <div className="line">Pay windows: {Object.values(fetch.pay_windows || {}).length} companies</div>
        </Group>
      )}
    </>
  );
}

function CompanyFilter({ value, onChange }) {
  const { companies } = useApp();
  const entries = Object.entries(companies);
  if (entries.length < 2) return null;
  return (
    <select className="select" value={value || ""} onChange={(e) => onChange(e.target.value || null)} aria-label="Company">
      <option value="">All companies</option>
      {entries.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
    </select>
  );
}
export { CompanyFilter };

export function Payroll() {
  const { dataset, route } = useApp();
  const [company, setCompany] = useState(route.query.get("company"));
  const [offset, setOffset] = useState(0);
  const [open, setOpen] = useState(null);
  const limit = 25;
  const runs = useApi(`/datasets/${dataset.id}/records/payroll_runs`, { offset, limit, company_id: company });
  return (
    <>
      <p className="eyebrow">Payroll</p>
      <h1 className="title">Payroll runs</h1>
      <p className="lede">Newest pay date first. Open a run to see its paychecks, then an employee for the full record.</p>
      <div className="toolbar"><CompanyFilter value={company} onChange={(v) => { setCompany(v); setOffset(0); }} /></div>
      {runs.error && <ErrorBox error={runs.error} />}
      <div className="card rows">
        {runs.data?.items.map((r) => (
          <div key={r.id}>
            <div className="row click" onClick={() => setOpen(open === r.id ? null : r.id)}>
              <span className="icon-dot info">$</span>
              <div className="grow">
                <div className="name">{r.name || `Payroll run ${shortId(r.id)}`}</div>
                <div className="sub">
                  {(r.pay_periods || []).map((p) => `${p.period_start} to ${p.period_end}`).slice(0, 2).join(", ") || shortId(r.id)}
                </div>
              </div>
              <div className="right">
                {coded(r.run_type) && <span className="badge">{humanize(coded(r.run_type))}</span>}
                <StatusBadge value={r.status} />
                <span style={{ minWidth: 96, textAlign: "right", fontWeight: 500 }}>{r.pay_date || "no pay date"}</span>
              </div>
            </div>
            {open === r.id && <RunPaychecks run={r} />}
          </div>
        ))}
        {runs.data && !runs.data.items.length && <Empty>No payroll runs in this dataset.</Empty>}
        {!runs.data && !runs.error && <Loading />}
      </div>
      {runs.data && <Pager offset={offset} limit={limit} total={runs.data.total} onChange={setOffset} />}
    </>
  );
}

function RunPaychecks({ run }) {
  const { dataset } = useApp();
  const [offset, setOffset] = useState(0);
  const limit = 50;
  const page = useApi(`/datasets/${dataset.id}/records/paychecks`, { payroll_run_id: run.id, offset, limit });
  const ids = [...new Set((page.data?.items || []).map((p) => p.employee_id).filter(Boolean))];
  const people = useApi(ids.length ? `/datasets/${dataset.id}/records/employees` : null, { ids: ids.join(","), limit: 200 });
  const names = Object.fromEntries((people.data?.items || []).map((e) => [e.id, personName(e)]));
  if (page.error) return <div className="card-pad"><ErrorBox error={page.error} /></div>;
  if (!page.data) return <Loading />;
  return (
    <div style={{ background: "var(--panel-2)", padding: "4px 18px 14px" }}>
      <div className="table-wrap">
        <table className="lines">
          <thead><tr><th>Employee</th><th>Check</th><th>Kind</th><th>Status</th><th className="num">Gross</th><th className="num">Net</th></tr></thead>
          <tbody>
            {page.data.items.map((p) => (
              <tr key={p.id} className="click" style={{ cursor: "pointer" }} onClick={() => p.employee_id && go("employees", p.employee_id, { tab: "paychecks" })}>
                <td>{names[p.employee_id] || <span className="mono">{shortId(p.employee_id)}</span>}</td>
                <td>{p.check_number || <span className="faint">none</span>}</td>
                <td><Val v={p.kind} /></td>
                <td><StatusBadge value={p.status} /></td>
                <td className="num">{money(p.gross_pay ?? p.total_earnings, p.currency)}</td>
                <td className="num">{money(p.net_pay, p.currency)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!page.data.items.length && <Empty>No paychecks for this run in the window.</Empty>}
      <Pager offset={offset} limit={limit} total={page.data.total} onChange={setOffset} />
    </div>
  );
}

export function Diagnostics() {
  const { dataset: summary } = useApp();
  const detail = useApi(`/datasets/${summary.id}`);
  const [pick, setPick] = useState(null);
  if (detail.error) return <ErrorBox error={detail.error} />;
  if (!detail.data) return <Loading />;
  const byCode = {};
  for (const d of detail.data.diagnostics) {
    const entry = (byCode[d.code] ||= { code: d.code, severity: d.severity, total: 0, lists: {} });
    entry.total += d.count;
    entry.lists[d.list] = (entry.lists[d.list] || 0) + d.count;
    if (d.severity === "warning") entry.severity = "warning";
  }
  const codes = Object.values(byCode).sort((a, b) => (a.severity === b.severity ? b.total - a.total : a.severity === "warning" ? -1 : 1));
  return (
    <>
      <div className="hero-split">
        <div>
          <p className="eyebrow">Diagnostics</p>
          <h1 className="title">Data quality</h1>
          <p className="lede">
            Where provider data is unclear, the record keeps the raw value and says why: unknown codes, inferred values,
            sources the provider does not expose. A warning count is a count of flags, not of records: one paycheck
            can carry several. Pick a count below to see the records behind it.
          </p>
        </div>
        <RunSummary dataset={detail.data} run={detail.data.run} />
      </div>
      <div className="two-col">
        <div>
          <h2 className="section">By code</h2>
          <div className="card rows">
            {codes.map((c) => (
              <div key={c.code} className="row" style={{ alignItems: "flex-start" }}>
                <SeverityIcon severity={c.severity} />
                <div className="grow">
                  <div className="name">{humanize(c.code)} <span className="count">{c.total.toLocaleString()}</span></div>
                  <div className="muted" style={{ fontSize: 13, margin: "2px 0 8px" }}>{CODE_HELP[c.code] || c.code}</div>
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {Object.entries(c.lists).map(([list, n]) => (
                      <button key={list} className={`btn btn-sm ${pick?.code === c.code && pick?.list === list ? "btn-dark" : ""}`}
                        onClick={() => setPick({ code: c.code, list })}>
                        {LISTS[list]} <span className="faint">{n.toLocaleString()}</span>
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            ))}
            {!codes.length && <Empty>No diagnostics in this dataset.</Empty>}
          </div>
        </div>
        <div>
          <h2 className="section">Run health</h2>
          <RunHealth run={detail.data.run} />
        </div>
      </div>
      {pick && <DiagnosticRecords key={`${pick.code}:${pick.list}`} {...pick} />}
    </>
  );
}

function DiagnosticRecords({ code, list }) {
  const { dataset } = useApp();
  const [offset, setOffset] = useState(0);
  const limit = 20;
  const page = useApi(`/datasets/${dataset.id}/records/${list}`, { diagnostic: code, offset, limit });
  return (
    <>
      <h2 className="section">{humanize(code)} in {LISTS[list].toLowerCase()} <span className="count">{page.data?.total?.toLocaleString() ?? ""}</span></h2>
      {page.error && <ErrorBox error={page.error} />}
      {!page.data && !page.error && <Loading />}
      {page.data?.items.map((r) => {
        const employeeId = list === "employees" ? r.id : r.employee_id;
        return (
          <div key={r.id} className="card" style={{ marginBottom: 10 }}>
            <div className={`row ${employeeId ? "click" : ""}`} onClick={() => employeeId && go("employees", employeeId)}>
              <span className="avatar">{initials(list === "employees" ? personName(r) : LISTS[list])}</span>
              <div className="grow">
                <div className="name">{list === "employees" ? personName(r) : list === "companies" ? companyName(r) : shortId(r.id)}</div>
                <div className="sub mono">{r.id}</div>
              </div>
            </div>
            <div className="rows" style={{ borderTop: "1px solid var(--border)" }}>
              {r.diagnostics.filter((d) => d.code === code).slice(0, 5).map((d, i) => <DiagnosticRow key={i} d={d} />)}
            </div>
          </div>
        );
      })}
      {page.data && <Pager offset={offset} limit={limit} total={page.data.total} onChange={setOffset} />}
    </>
  );
}
