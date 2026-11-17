import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import test from "node:test";
import { initSync, RelateDb } from "@relate/relate-wasm";
import { loadSnapshot, querySnapshot } from "../src/graph-data.js";

const require = createRequire(import.meta.url);
const wasm = await readFile(require.resolve("@relate/relate-wasm/relate_bg.wasm"));
initSync({ module: wasm });
const fixture = JSON.parse(await readFile(new URL("../../downlink/common-cause.json", import.meta.url)));

test("WASM runs the shared rank query over the downlink", async () => {
  const db = new RelateDb();
  try {
    loadSnapshot(db, fixture);
    const rank = await readFile(new URL("../../queries/rank.cypher", import.meta.url), "utf8");
    const { rows } = querySnapshot(db, rank, {
      run: "f1-fixture", from: 1794873601000, to: 1794873602000, exclude_devices: [],
      device_faults: ["NO_RESPONSE", "OUT_OF_RANGE", "STUCK", "STALE", "HEARTBEAT_LOST"],
    });
    assert.equal(rows[0].suspect, "REG_B");
    assert.equal(rows[0].score, 1);
    assert.equal(rows[0].covered, 3);
    assert.equal(rows[0].contradicted, 0);
    const stored = querySnapshot(db, "MATCH (d:Device {id: 'imu'}) RETURN properties(d) AS props").rows[0];
    assert.equal(Object.hasOwn(stored.props, "__downlink_id"), false);
  } finally {
    db.free();
  }
});

test("console refuses writes even when they start with MATCH", () => {
  const db = new RelateDb();
  try {
    loadSnapshot(db, fixture);
    for (const statement of [
      "MATCH (n) DETACH DELETE n",
      "MATCH (n) CREATE (:Device {id: 'injected'}) RETURN n",
      "MATCH (n:Device) SET n.id = 'changed' RETURN n",
      "RETURN 1; CREATE (:Device {id: 'injected'})",
    ]) {
      assert.throws(() => querySnapshot(db, statement));
    }
    assert.equal(querySnapshot(db, "MATCH (n:Device) RETURN count(n) AS devices").rows[0].devices, 8);
  } finally {
    db.free();
  }
});
