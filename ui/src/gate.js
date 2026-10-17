// A fetched result is shown only while it belongs to the request wanted now: same path, same
// parameters, same sensitive-values setting. Turning the switch off therefore hides full values
// at once, even while the masked request is still loading or after it fails (D-036).

export const PENDING = Object.freeze({ data: null, error: null, loading: true });

export const requestKey = (path, params, sensitive) => JSON.stringify([path, params ?? {}, Boolean(sensitive)]);

/** `state` (a finished request and its key) if it answers `key`, else nothing to show yet. */
export function visible(state, key) {
  return state && state.key === key ? state : PENDING;
}
