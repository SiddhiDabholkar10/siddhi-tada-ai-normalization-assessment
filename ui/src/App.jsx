import { useCallback, useEffect, useMemo, useState } from "react";
import { AppContext, api } from "./api.js";
import { KINDS, PROVIDERS, companyName } from "./ui.jsx";
import { Diagnostics, Overview, Payroll } from "./pages/overview.jsx";
import { EmployeeDetail, Employees } from "./pages/employees.jsx";
import { Sync } from "./pages/sync.jsx";
import { WriteEmployee } from "./pages/write.jsx";

const NAV = [
  ["overview", "Overview"], ["employees", "Employees"], ["payroll", "Payroll"], ["diagnostics", "Diagnostics"],
  ["sync", "Sync"], ["write", "Write employee"],
];
const STORED_DATASET = "normalization.dataset"; // a per-viewer convenience only

function readHash() {
  const [path, query = ""] = window.location.hash.replace(/^#\/?/, "").split("?");
  const [page = "overview", ...rest] = path.split("/");
  return { page: page || "overview", arg: rest.length ? decodeURIComponent(rest.join("/")) : null, query: new URLSearchParams(query) };
}

let currentDataset = null; // the dataset shown, so a detail link can name it

/** Go to a page. A detail page (with `arg`) carries its dataset (`ds`), so the link still opens
 *  the same record later, whichever dataset is selected then. */
export const go = (page, arg, query) => {
  const params = { ...(query || {}) };
  if (arg && currentDataset) params.ds = currentDataset;
  const q = Object.keys(params).length ? `?${new URLSearchParams(params)}` : "";
  window.location.hash = `#/${page}${arg ? `/${encodeURIComponent(arg)}` : ""}${q}`;
};

function remember(id) {
  try { window.localStorage.setItem(STORED_DATASET, String(id)); } catch { /* storage unavailable */ }
}

function recall() {
  try { return Number(window.localStorage.getItem(STORED_DATASET)); } catch { return null; }
}

export default function App() {
  const [route, setRoute] = useState(readHash());
  const [datasets, setDatasets] = useState(null);
  const [datasetId, setDatasetId] = useState(null);
  const [companies, setCompanies] = useState({});
  const [sensitive, setSensitive] = useState(false); // off on every load (D-036)
  const [error, setError] = useState(null);
  const [job, setJob] = useState(null); // the running or last sync, kept across pages

  useEffect(() => {
    const onHash = () => setRoute(readHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const loadDatasets = useCallback(async (select) => {
    try {
      const list = await api("/datasets");
      setDatasets(list);
      const wanted = select ?? (Number(readHash().query.get("ds")) || recall());
      const chosen = list.find((d) => d.id === wanted) || list.find((d) => d.kind !== "sample") || list[0];
      setDatasetId(chosen ? chosen.id : null);
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => { loadDatasets(); }, [loadDatasets]);

  // A link naming its dataset selects it (opened later, or from another dataset).
  const linked = Number(route.query.get("ds")) || null;
  const linkedKnown = linked && datasets?.some((d) => d.id === linked);
  useEffect(() => {
    if (linkedKnown) setDatasetId(linked); // only when the link changes, so the dropdown still wins
  }, [linked, linkedKnown]);

  useEffect(() => {
    currentDataset = datasetId;
    if (!datasetId) return;
    remember(datasetId);
    api(`/datasets/${datasetId}/records/companies`, { limit: 200 })
      .then((page) => setCompanies(Object.fromEntries(page.items.map((c) => [c.id, companyName(c)]))))
      .catch(() => setCompanies({}));
  }, [datasetId]);

  const dataset = datasets?.find((d) => d.id === datasetId) || null;
  const context = useMemo(
    () => ({ dataset, datasets, companies, sensitive, job, setJob, loadDatasets, route }),
    [dataset, datasets, companies, sensitive, job, loadDatasets, route],
  );

  const chooseDataset = (id) => {
    setDatasetId(id);
    if (route.arg) go(route.page); // a detail page belongs to the old dataset
  };

  let page;
  if (error) page = <div className="error-box">The API did not answer: {error}</div>;
  else if (!datasets || (route.arg && linkedKnown && linked !== datasetId)) page = <div className="empty">Loading</div>;
  else if (linked && !linkedKnown) page = <div className="error-box">This link names a dataset that is not stored here (it may have been deleted).</div>;
  else if (route.page === "sync") page = <Sync />;
  else if (!dataset) page = <div className="empty">No datasets yet. Run a sync to fetch one.</div>;
  else if (route.page === "write") page = <WriteEmployee key={`${dataset.id}:${route.arg || ""}`} id={route.arg} />;
  else if (route.page === "employees" && route.arg) page = <EmployeeDetail key={`${dataset.id}:${route.arg}`} id={route.arg} />;
  else if (route.page === "employees") page = <Employees key={dataset.id} />;
  else if (route.page === "payroll") page = <Payroll key={dataset.id} />;
  else if (route.page === "diagnostics") page = <Diagnostics key={dataset.id} />;
  else page = <Overview key={dataset.id} />;

  return (
    <AppContext.Provider value={context}>
      <header className="topbar">
        <div className="topbar-inner">
          <a className="brand" href="#/overview">
            {/* The TADA AI mark, drawn inline at the user's request (D-098): two stacked pills. */}
            <svg className="brand-logo" width="20" height="20" viewBox="0 0 20 20" aria-hidden="true">
              <rect x="1" y="2" width="18" height="7.5" rx="3.75" fill="currentColor" />
              <rect x="1" y="10.5" width="18" height="7.5" rx="3.75" fill="currentColor" />
              <rect x="5" y="7" width="10" height="6" fill="currentColor" />
            </svg>
            <span>TADA AI</span>
            <span className="brand-sub">Normalization Console</span>
          </a>
          <nav className="nav">
            {NAV.map(([key, label]) => (
              <a key={key} href={`#/${key}`} className={route.page === key ? "active" : ""}>
                {label}
              </a>
            ))}
          </nav>
          <a className="btn btn-dark" href="#/sync">Sync data</a>
        </div>
      </header>
      {datasets && datasets.length > 0 && (
        <div className="contextbar">
          <select className="select" value={datasetId ?? ""} onChange={(e) => chooseDataset(Number(e.target.value))} aria-label="Dataset">
            {datasets.map((d) => (
              <option key={d.id} value={d.id}>
                {PROVIDERS[d.provider] || d.provider}: {KINDS[d.kind]}, {d.kept_values === "full" ? "full values" : "masked"} ({d.counts.employees ?? 0} employees, {d.created_at.slice(0, 10)})
              </option>
            ))}
          </select>
          {dataset && <span className={`badge ${dataset.kind === "sample" ? "soft" : "dark"}`}>{KINDS[dataset.kind]}</span>}
          {dataset?.kept_values === "masked" && <span className="badge">masked at source</span>}
          <span className="spacer" />
          <label className={`switch ${sensitive ? "on" : ""}`}>
            <input type="checkbox" checked={sensitive} onChange={(e) => setSensitive(e.target.checked)} hidden />
            <span className="track" />
            Show sensitive values
          </label>
        </div>
      )}
      {sensitive && (
        <div className="banner">
          <div>
            Sensitive values are shown in full (birth dates, national ids, account numbers, addresses). Turn the switch off when you are done.
            {dataset?.kept_values === "masked" && " This dataset was imported masked, so its values stay masked."}
          </div>
        </div>
      )}
      <main className="page">{page}</main>
    </AppContext.Provider>
  );
}
