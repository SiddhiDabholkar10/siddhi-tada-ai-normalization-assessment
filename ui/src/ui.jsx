import { Children, useLayoutEffect, useRef, useState } from "react";

// Formatting and small building blocks shared by the pages.

export const PROVIDERS = { prismhr: "PrismHR", isolved: "isolved", "ukg-ready": "UKG Ready" };
export const KINDS = { sample: "Synthetic sample", sync: "Live sync", import: "Imported run" };
export const LISTS = {
  companies: "Companies", employees: "Employees", direct_deposits: "Direct deposits", deduction_setups: "Deductions",
  benefit_enrollments: "Benefits", payroll_runs: "Payroll runs", paychecks: "Paychecks",
};
const HIDDEN_KEYS = new Set(["field_status", "provider_extensions", "sensitive_provider_extensions", "sources", "diagnostics"]);
const REASONS = {
  not_provided: "not provided", not_applicable: "not applicable", hidden_by_source: "hidden by the provider",
  not_in_input: "not in the input",
};

export const humanize = (text) => {
  const words = String(text).replace(/[_-]+/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
};
export const isCoded = (v) => v && typeof v === "object" && !Array.isArray(v) && "value" in v && "raw_code" in v;
export const isMasked = (v) => typeof v === "string" && v.startsWith("***");
export const coded = (v) => (isCoded(v) ? v.value : v);
export const shortId = (id) => (id ? String(id).split(":").slice(3).join(" / ") : "");
export const initials = (text) =>
  String(text || "?").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("") || "?";

export function personName(employee) {
  const name = employee?.name || {};
  const first = name.preferred_first || name.first;
  return [first, name.last].filter(Boolean).join(" ") || employee?.employee_number || shortId(employee?.id);
}

export function companyName(company) {
  return company?.display_name || company?.legal_name || shortId(company?.id);
}

export function money(value, currency = "USD") {
  if (value === null || value === undefined) return null;
  if (isMasked(value)) return <Masked value={value} />;
  const n = Number(value);
  if (Number.isNaN(n)) return String(value);
  return n.toLocaleString("en-US", { style: "currency", currency: currency || "USD" });
}

export const Masked = ({ value }) => (
  <span className="masked" title="Masked. Turn on Show sensitive values to see it.">
    <LockIcon /> {value}
  </span>
);

export const LockIcon = () => (
  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
    <rect x="4" y="11" width="16" height="10" rx="2" /><path d="M8 11V7a4 4 0 0 1 8 0v4" />
  </svg>
);

export const Chevron = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="m9 6 6 6-6 6" /></svg>
);

/** A canonical value: masked, coded (value plus the provider's raw code), boolean, or plain. */
export function Val({ v, reason }) {
  if (v === null || v === undefined || (Array.isArray(v) && v.length === 0)) {
    return <span className="reason">{REASONS[reason] || reason || "none"}</span>;
  }
  if (isMasked(v)) return <Masked value={v} />;
  if (isCoded(v)) {
    return (
      <span style={{ display: "inline-flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
        <span>{isMasked(v.value) ? <Masked value={v.value} /> : humanize(v.value ?? "unknown")}</span>
        {v.raw_code !== null && v.raw_code !== undefined && (
          <span className="badge" title={v.raw_label || "provider code"}>{isMasked(v.raw_code) ? "***" : String(v.raw_code)}</span>
        )}
        {v.basis && v.basis !== "documented" && <span className={`badge ${v.basis === "unmapped" ? "warn" : "soft"}`}>{v.basis}</span>}
      </span>
    );
  }
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (typeof v === "string" && /^[a-z-]+:\d+:[a-z_]+:/.test(v)) return <span className="mono">{v}</span>;
  return String(v);
}

/** Every field of a canonical object, nested parts in sub-cards; nulls show their field_status reason. */
export function Fields({ obj, skip = [], depth = 0 }) {
  if (!obj || typeof obj !== "object") return <Val v={obj} />;
  const status = obj.field_status || {};
  const entries = Object.entries(obj).filter(([k]) => !HIDDEN_KEYS.has(k) && !skip.includes(k));
  return (
    <div className="fields">
      {entries.map(([key, value]) => (
        <FieldRow key={key} name={key} value={value} reason={status[key]} depth={depth} />
      ))}
    </div>
  );
}

function FieldRow({ name, value, reason, depth }) {
  let body;
  if (Array.isArray(value) && value.length && typeof value[0] === "object" && !isCoded(value[0])) {
    const shown = value.slice(0, 12);
    body = (
      <div className="nested">
        {shown.map((item, i) => (
          <div className="sub-card" key={i}><Fields obj={item} depth={depth + 1} /></div>
        ))}
        {value.length > shown.length && <div className="faint">and {value.length - shown.length} more</div>}
      </div>
    );
  } else if (Array.isArray(value) && value.length) {
    body = (
      <span style={{ display: "inline-flex", gap: 6, flexWrap: "wrap" }}>
        {value.map((item, i) => <Val key={i} v={item} />)}
      </span>
    );
  } else if (value && typeof value === "object" && !isCoded(value) && !Array.isArray(value)) {
    body = <div className="sub-card"><Fields obj={value} depth={depth + 1} /></div>;
  } else {
    body = <Val v={value} reason={reason} />;
  }
  return (
    <>
      <div className="k">{humanize(name)}</div>
      <div className="v">{body}</div>
    </>
  );
}

export function SeverityIcon({ severity }) {
  const kind = severity === "warning" ? "warn" : severity === "error" ? "error" : "info";
  return <span className={`icon-dot ${kind}`}>{kind === "info" ? "i" : "!"}</span>;
}

export function DiagnosticRow({ d }) {
  return (
    <div className="row">
      <SeverityIcon severity={d.severity} />
      <div className="grow">
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <span className="badge">{d.code}</span>
          {d.field && <span className="mono muted">{d.field}</span>}
        </div>
        <div style={{ marginTop: 4, fontSize: 14 }}>{d.message}</div>
      </div>
      {d.evidence && <span className="faint mono">{d.evidence}</span>}
    </div>
  );
}

export function StatusBadge({ value }) {
  const v = coded(value);
  if (!v) return null;
  if (isMasked(v)) return <Masked value={v} />;
  const style = {
    active: "dark", completed: "dark", paid: "dark", printed: "dark", processed: "dark",
    terminated: "", inactive: "", voided: "danger", leave: "soft", on_leave: "soft", pending: "soft", unknown: "warn",
  }[v] ?? "";
  return <span className={`badge ${style}`}>{humanize(v)}</span>;
}

export function Group({ title, count, children, initiallyOpen = false, icon }) {
  const [open, setOpen] = useState(initiallyOpen);
  return (
    <div className={`group ${open ? "open" : ""}`}>
      <div className="group-head" onClick={() => setOpen(!open)}>
        {icon}
        <span>{title}</span>
        <span className="count">{count}</span>
        <span className="chev"><Chevron /></span>
      </div>
      {open && <div className="group-body">{children}</div>}
    </div>
  );
}

export function Pager({ offset, limit, total, onChange }) {
  if (!total) return null;
  const end = Math.min(offset + limit, total);
  return (
    <div className="pager">
      <span>{offset + 1} to {end} of {total.toLocaleString()}</span>
      <button className="btn btn-sm" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>Previous</button>
      <button className="btn btn-sm" disabled={end >= total} onClick={() => onChange(offset + limit)}>Next</button>
    </div>
  );
}

export const Loading = () => <div className="empty">Loading</div>;
export const ErrorBox = ({ error }) => <div className="error-box">{error}</div>;
export const Empty = ({ children }) => <div className="empty">{children}</div>;

/** About how many rows ``Fields`` draws for a value: the height estimate Masonry balances on. */
export function rowCount(value) {
  if (value === null || value === undefined || typeof value !== "object" || isCoded(value)) return 1;
  if (Array.isArray(value)) {
    if (!value.length || typeof value[0] !== "object" || isCoded(value[0])) return 1;
    return value.slice(0, 12).reduce((n, item) => n + rowCount(item) + 1, 0);
  }
  return Object.entries(value).filter(([k]) => !HIDDEN_KEYS.has(k)).reduce((n, [, v]) => n + rowCount(v), 0) || 1;
}

/** Cards in as many columns as fit, each only as tall as its content. Cards are placed in order,
 *  each in the shortest column so far (by ``weights``, an estimate of each card's height), so
 *  the first cards stay near the top and the columns end at about the same point. */
export function Masonry({ children, weights, minWidth = 380, gap = 16, style }) {
  const ref = useRef(null);
  const [count, setCount] = useState(1);
  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return undefined;
    const measure = () => setCount(Math.max(1, Math.floor((element.clientWidth + gap) / (minWidth + gap))));
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [minWidth, gap]);
  const columns = Array.from({ length: count }, () => []);
  const heights = Array(count).fill(0);
  Children.toArray(children).filter(Boolean).forEach((item, i) => {
    const shortest = heights.indexOf(Math.min(...heights)); // ties go to the leftmost column
    columns[shortest].push(item);
    heights[shortest] += (weights?.[i] ?? 1) + 3; // + card padding and title
  });
  return (
    <div ref={ref} className="masonry" style={{ gap, ...style }}>
      {columns.map((items, i) => <div key={i} className="masonry-col" style={{ gap }}>{items}</div>)}
    </div>
  );
}
