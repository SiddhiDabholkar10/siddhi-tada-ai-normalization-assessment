import { createContext, useContext, useEffect, useState } from "react";
import { PENDING, requestKey, visible } from "./gate.js";

// App-wide state: the chosen dataset, its companies, and the sensitive-values switch.
// The switch lives in memory only, so every page load starts masked (D-036).
export const AppContext = createContext(null);
export const useApp = () => useContext(AppContext);

export async function api(path, params = {}, sensitive = false, options = {}) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") query.set(key, value);
  }
  // Full values only on explicit opt-in; the API masks everything otherwise.
  if (sensitive) query.set("show_sensitive", "true");
  const text = query.toString();
  const response = await fetch(`/api${path}${text ? `?${text}` : ""}`, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || `HTTP ${response.status}`);
  return body;
}

/** Fetch on mount and whenever the request changes; `path` null skips the call. The result is
 *  returned only while it answers the current request (gate.js): switching sensitive values off
 *  never leaves full values on screen while the masked answer loads or after it fails. */
export function useApi(path, params = {}) {
  const { sensitive } = useApp();
  const key = requestKey(path, params, sensitive);
  const [state, setState] = useState(null);
  useEffect(() => {
    if (!path) return undefined;
    let live = true;
    api(path, params, sensitive)
      .then((data) => live && setState({ data, error: null, loading: false, key }))
      .catch((error) => live && setState({ data: null, error: error.message, loading: false, key }));
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return visible(state, key);
}
