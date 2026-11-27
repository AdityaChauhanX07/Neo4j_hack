import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import test from "node:test";
import { initSync, RelateDb } from "@relate/relate-wasm";
import { contradictions, deviceFaults, precursorCutoff, sourceLabel } from "../src/evidence.js";
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

test("WASM ranking waits for missing-reading confirmation at the requested time", async () => {
  const snapshot = structuredClone(fixture);
  const end = Math.max(...snapshot.nodes.filter(node => node.label === "Event").map(node => node.props.ts));
  const faults = snapshot.nodes.filter(node => node.label === "Event" && deviceFaults.includes(node.props.status));
  const db = new RelateDb();
  try {
    for (const event of faults) {
      event.props.diagnostic = false;
      event.props.confirmed_ts = end + 1000;
    }
    loadSnapshot(db, snapshot);
    const rank = await shared("rank");
    const run = snapshot.nodes.find(node => node.label === "Run").props.id;
    const scope = { run, from: 0, to: end, device_faults: deviceFaults, exclude_devices: [] };
    assert.deepEqual(querySnapshot(db, rank, scope).rows, []);
    db.execute("MATCH (e:Event) WHERE e.diagnostic = false SET e.diagnostic = true");
    assert.deepEqual(querySnapshot(db, rank, scope).rows, []);
    assert.equal(querySnapshot(db, rank, { ...scope, to: end + 1000 }).rows[0].suspect, "REG_B");
  } finally {
    db.free();
  }
});

test("simulation provenance survives a downlink import into Relate WASM", () => {
  const snapshot = structuredClone(fixture);
  const run = snapshot.nodes.find(node => node.label === "Run");
  run.props.simulated = true;
  const db = new RelateDb();
  try {
    loadSnapshot(db, snapshot);
    const stored = querySnapshot(db, "MATCH (r:Run) RETURN properties(r) AS props").rows[0].props;
    assert.equal(stored.simulated, true);
    assert.equal(sourceLabel(false, stored), "Simulated bench");
    assert.equal(sourceLabel(false, {}), "Imported downlink");
    assert.equal(sourceLabel(true, stored), "Synthetic fixture");
  } finally {
    db.free();
  }
});

async function shared(name) {
  return readFile(new URL(`../../queries/${name}.cypher`, import.meta.url), "utf8");
}

function firstEpisode(db) {
  const [episode] = querySnapshot(db, `
    MATCH (dx:Diagnosis) RETURN dx.id AS id, dx.run AS run, dx.window_from AS start, dx.window_to AS end
    ORDER BY dx.ts DESC LIMIT 1`).rows;
  const observed = querySnapshot(db, `
    MATCH (:Diagnosis {id: $id})-[:BASED_ON]->(e:Event) RETURN e.ts AS ts, e.status AS status`,
  { id: episode.id }).rows;
  return { episode, observed };
}

test("diagnosis card names the healthy devices that contradict each candidate", async () => {
  const db = new RelateDb();
  try {
    loadSnapshot(db, fixture);
    const { episode } = firstEpisode(db);
    const scope = {
      run: episode.run, from: episode.start, to: episode.end,
      device_faults: deviceFaults, exclude_devices: [],
    };
    const ranked = querySnapshot(db, await shared("rank"), scope).rows;
    const against = new Map(querySnapshot(db, contradictions, {
      ...scope, suspects: ranked.map(row => row.suspect),
    }).rows.map(row => [row.suspect, row.against]));

    for (const row of ranked) assert.equal(against.get(row.suspect).length, row.contradicted, row.suspect);
    assert.deepEqual(against.get("REG_B"), []);
    assert.deepEqual([...against.get("I2C-1")].sort(), ["epsmon", "thermal"]);
    assert.deepEqual(against.get("RAIL_5V"), ["radio"]);
  } finally {
    db.free();
  }
});

test("change list keeps the voltage sag that opens the episode", async () => {
  const db = new RelateDb();
  try {
    loadSnapshot(db, fixture);
    const { episode, observed } = firstEpisode(db);
    const before = await shared("before");
    assert.deepEqual(querySnapshot(db, before, { run: episode.run, t0: episode.start }).rows, []);
    const rows = querySnapshot(db, before, { run: episode.run, t0: precursorCutoff(observed, episode) }).rows;
    const sag = rows.find(row => row.channel === "eps.regb.voltage");
    assert.equal(sag.before, 3.28);
    assert.equal(sag.after, 0.16);
    assert.ok(rows.some(row => row.channel === "imu.gyro" && row.after === null));
  } finally {
    db.free();
  }
});

test("named contradictions match rank.cypher in every simulated case", async t => {
  const index = new URL("../public/simulations/index.json", import.meta.url);
  let suites;
  try {
    ({ suites } = JSON.parse(await readFile(index)));
  } catch {
    t.skip("Run `python -m sim.demo` to build the simulations.");
    return;
  }
  const rank = await shared("rank");
  let checked = 0;
  for (const suite of suites) {
    const db = new RelateDb();
    try {
      loadSnapshot(db, JSON.parse(await readFile(new URL(`../public/simulations/${suite.graph}`, import.meta.url))));
      const episodes = querySnapshot(db, `
        MATCH (dx:Diagnosis) RETURN dx.id AS id, dx.run AS run, dx.window_from AS start, dx.window_to AS end`).rows;
      for (const episode of episodes) {
        const scope = {
          run: episode.run, from: episode.start, to: episode.end,
          device_faults: deviceFaults, exclude_devices: [],
        };
        const ranked = querySnapshot(db, rank, scope).rows;
        const against = new Map(querySnapshot(db, contradictions, {
          ...scope, suspects: ranked.map(row => row.suspect),
        }).rows.map(row => [row.suspect, row.against]));
        for (const row of ranked) {
          assert.equal(against.get(row.suspect).length, row.contradicted, `${episode.id} ${row.suspect}`);
          checked += 1;
        }
      }
    } finally {
      db.free();
    }
  }
  assert.ok(checked > 0);
});
