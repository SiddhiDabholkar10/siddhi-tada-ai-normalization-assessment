import { useEffect, useState } from "react";
import { api, useApi, useApp } from "../api.js";
import { go } from "../App.jsx";
import { ErrorBox, PROVIDERS } from "../ui.jsx";

const TIMES = { prism: "about 12 minutes for all 25 clients", isol: "about 13 minutes", ukg: "about 4 minutes" };

export function Sync() {
  const { job, setJob, loadDatasets } = useApp();
  const tenants = useApi("/tenants");
  const [tenant, setTenant] = useState("ukg");
  const [companies, setCompanies] = useState("");
  const [error, setError] = useState(null);
  const running = job?.state === "running";

  useEffect(() => {
    if (!running) return undefined;
    const timer = setInterval(async () => {
      try {
        const next = await api(`/sync/${job.id}`);
        setJob(next);
        if (next.state === "done") loadDatasets(next.dataset_id);
      } catch (e) {
        setError(e.message);
      }
    }, 1000);
    return () => clearInterval(timer);
  }, [running, job?.id, setJob, loadDatasets]);

  const start = async () => {
    setError(null);
    const ids = companies.split(/[\s,]+/).map((s) => s.trim()).filter(Boolean);
    try {
      const started = await api("/sync", {}, false, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tenant, companies: ids.length ? ids : null }),
      });
      setJob(started);
    } catch (e) {
      setError(e.message);
    }
  };

  const keyMissing = tenants.data && !tenants.data[0]?.key_configured;
  return (
    <div className="hero-split">
      <div>
        <p className="eyebrow">Sync</p>
        <h1 className="title">Fetch a demo tenant</h1>
        <p className="lede">
          Signs in to the demo provider, fetches every company, employee and the 12 months of payroll ending at each
          company's latest pay date, then normalizes and stores the run. The raw responses are not kept.
        </p>
        <div className="card card-pad">
          <div className="card-title">Tenant</div>
          <div className="segmented" style={{ marginBottom: 16 }}>
            {(tenants.data || []).map((t) => (
              <button key={t.tenant} className={tenant === t.tenant ? "on" : ""} onClick={() => setTenant(t.tenant)} disabled={running}>
                {PROVIDERS[t.provider]}
              </button>
            ))}
          </div>
          <div className="card-title">Companies <span className="faint" style={{ fontWeight: 400, fontSize: 13 }}>optional</span></div>
          <input className="input" style={{ width: "100%", marginBottom: 6 }} value={companies} disabled={running}
            onChange={(e) => setCompanies(e.target.value)} placeholder="All companies; or ids, comma separated (e.g. PrismHR client 103)" />
          <p className="muted" style={{ fontSize: 13, margin: "4px 0 16px" }}>
            A full sync takes {TIMES[tenant]}. For a historical pay window use the command line (fetch --pay-from --pay-to).
          </p>
          {keyMissing && <div className="error-box" style={{ marginBottom: 12 }}>No sign-in key: set DEMO_SIGNIN_API_KEY in the environment or a .env file, then restart the app.</div>}
          {error && <div style={{ marginBottom: 12 }}><ErrorBox error={error} /></div>}
          <button className="btn btn-dark" onClick={start} disabled={running || keyMissing || !tenants.data}>
            {running ? "Sync running" : "Start sync"}
          </button>
        </div>
      </div>
      <div className="panel">
        <div className="card" style={{ padding: "12px 16px", display: "flex", alignItems: "center", gap: 12, marginBottom: 10 }}>
          <span className="avatar dark" style={{ width: 34, height: 34, fontSize: 15 }}>&#8635;</span>
          <span style={{ fontWeight: 500 }}>{job ? `Sync: ${PROVIDERS[{ prism: "prismhr", isol: "isolved", ukg: "ukg-ready" }[job.tenant]]}` : "No sync yet"}</span>
          <span className="spacer" />
          {job?.state === "done" && <button className="btn btn-dark btn-sm" onClick={() => go("overview")}>Open dataset</button>}
          {job?.state === "failed" && <span className="badge danger">failed</span>}
          {running && <span className="badge soft">running</span>}
        </div>
        <div className="card" style={{ padding: 16 }}>
          {running && <div className="progress indeterminate" style={{ marginBottom: 14 }}><div /></div>}
          {job?.state === "done" && <div className="progress" style={{ marginBottom: 14 }}><div style={{ width: "100%" }} /></div>}
          {!job && <p className="muted" style={{ margin: 0, fontSize: 14 }}>Progress appears here: call counts per stage, never ids or values.</p>}
          <div className="rows feed">
            {(job?.lines || []).slice(-14).map((line, i, shown) => {
              const last = i === shown.length - 1;
              return (
                <div className="row" key={`${i}:${line}`} style={{ padding: "8px 0" }}>
                  <span className={`icon-dot ${last && running ? "info" : "ok"}`}>{last && running ? "…" : "✓"}</span>
                  <div className="grow">{line}</div>
                </div>
              );
            })}
          </div>
          {job?.error && <ErrorBox error={job.error} />}
        </div>
      </div>
    </div>
  );
}
