// Run with `npm test` (Node's built-in runner, no packages); tests/test_app.py runs it too.
import assert from "node:assert/strict";
import test from "node:test";
import { PENDING, requestKey, visible } from "./gate.js";

const path = "/datasets/4/records/employees/ukg-ready:1:employee:7:1";
const full = { item: { demographics: { birth_date: "1988-04-12" } }, sensitive_values: "shown" };

test("turning sensitive values off hides the full result at once", () => {
  const on = requestKey(path, {}, true);
  const off = requestKey(path, {}, false);
  const answered = { data: full, error: null, loading: false, key: on };
  assert.equal(visible(answered, on).data, full, "shown while the switch is on");
  assert.deepEqual(visible(answered, off), PENDING, "nothing shown while the masked request loads");
  const failed = { data: null, error: "HTTP 500", loading: false, key: off };
  assert.equal(visible(failed, off).data, null, "a failed masked request shows no data either");
});

test("a result answers only its own path and parameters", () => {
  const page = { data: { items: [] }, error: null, loading: false, key: requestKey(path, { offset: 0 }, false) };
  assert.deepEqual(visible(page, requestKey(path, { offset: 25 }, false)), PENDING);
  assert.deepEqual(visible(null, requestKey(path, {}, false)), PENDING);
});
