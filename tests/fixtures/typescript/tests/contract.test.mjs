import assert from "node:assert/strict";
import test from "node:test";
import { respond } from "../src/.build/index.js";

test("versioned message round-trip", () => {
  assert.deepEqual(respond({ version: 1, value: 41 }), {
    version: 1,
    result: 42,
  });
});

test("runtime input is validated", () => {
  for (const invalid of [
    null,
    {},
    { version: 1, value: "41" },
    { version: 2, value: 41 },
    { version: 1, value: 1.5 },
    { version: 1, value: NaN },
    { version: 1, value: Infinity },
    { version: 1, value: Number.MAX_SAFE_INTEGER },
  ]) {
    assert.throws(() => respond(invalid), /Invalid versioned request/);
  }
});
