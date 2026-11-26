import assert from "node:assert/strict";
import { spawn, execFileSync } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
import { openHttpEngine } from "../src/http-engine.js";

test("live connections keep credentials out of the address and use READ transactions", async () => {
  const requests = [];
  const engine = openHttpEngine("http://127.0.0.1:7474", "relate:test-only", {
    fetcher: async (url, options) => {
      requests.push({ url: String(url), ...options, body: JSON.parse(options.body) });
      return Response.json(requests.length === 1 ? {
        transaction: { id: "tx-4" }, data: { fields: ["suspect"], values: [["REG_B"]] },
      } : {});
    },
  });
  assert.deepEqual(await engine.query("RETURN $part AS suspect", { part: "REG_B" }), {
    columns: ["suspect"], count: 1, rows: [{ suspect: "REG_B" }],
  });
  assert.deepEqual(requests[0].body, {
    statement: "RETURN $part AS suspect", parameters: { part: "REG_B" }, accessMode: "READ",
  });
  assert.equal(requests[0].redirect, "error");
  assert.equal(requests[0].credentials, "omit");
  assert.equal(requests[0].headers.Authorization, "Basic cmVsYXRlOnRlc3Qtb25seQ==");
  assert.equal(requests[1].url, "http://127.0.0.1:7474/db/neo4j/query/v2/tx/tx-4/commit");
  assert.deepEqual(requests[1].body, {});
  engine.close();
  await assert.rejects(engine.query("RETURN 1"), /closed/);
  assert.throws(() => openHttpEngine("https://relate:token@example.com", "relate:token"), /server origin/);
  assert.throws(() => openHttpEngine("http://127.0.0.1:7474/db/neo4j", "relate:token"), /server origin/);
});

test("disconnect cancels an outstanding HTTP read", async () => {
  const engine = openHttpEngine("http://127.0.0.1:7474", "relate:test-only", {
    fetcher: (url, { signal }) => new Promise((resolve, reject) => {
      signal.addEventListener("abort", () => reject(new Error("cancelled")), { once: true });
    }),
  });
  const pending = engine.query("RETURN 1");
  engine.close();
  await assert.rejects(pending, /cancelled/);
});

test("the real HTTP engine reads shared Cypher and cannot mutate even a writable test server", {
  skip: !process.env.RELATE_CLI,
}, async () => {
  const root = fileURLToPath(new URL("../../", import.meta.url));
  const scratch = await mkdtemp(join(tmpdir(), "cc-http-"));
  const socket = createServer();
  await new Promise(resolve => socket.listen(0, "127.0.0.1", resolve));
  const port = socket.address().port;
  await new Promise(resolve => socket.close(resolve));
  const store = join(scratch, "store");
  execFileSync(process.env.RELATE_CLI, ["clone", join(root, "data/common-cause.rl"), store]);
  const server = spawn(process.env.RELATE_CLI, ["serve", "--database", store, "--http", String(port)], {
    env: { ...process.env, RELATE_AUTH: "relate:http-test-only" }, stdio: ["ignore", "ignore", "pipe"],
  });
  let logs = "";
  server.stderr.on("data", chunk => { logs += chunk; });
  const address = `http://127.0.0.1:${port}`;
  const engine = openHttpEngine(address, "relate:http-test-only");
  try {
    const deadline = Date.now() + 10000;
    while (true) {
      try { if ((await fetch(address)).ok) break; } catch {}
      assert.equal(server.exitCode, null, logs);
      assert.ok(Date.now() < deadline, logs);
      await new Promise(resolve => setTimeout(resolve, 30));
    }
    const snapshot = await engine.snapshot();
    assert.ok(snapshot.nodes.some(node => node.id === "Regulator:REG_B"));
    assert.ok(snapshot.rels.some(rel => rel.type === "POWERED_BY"));
    const verdict = await engine.query(`MATCH (dx:Diagnosis {id: $id})-[s:SUSPECTS]->(c)
      RETURN c.id AS suspect ORDER BY s.rank`, { id: "dx:f1-fixture:1" });
    assert.deepEqual(verdict.rows, [{ suspect: "REG_B" }]);
    const before = await engine.query("MATCH (n) RETURN count(n) AS total");
    for (const statement of [
      "CREATE (:Device {id: 'http-test'})",
      "MATCH (n:Diagnosis) SET n.confidence = 'changed'",
      "MATCH (n) DETACH DELETE n",
      "CREATE INDEX http_test FOR (n:Diagnosis) ON (n.confidence)",
    ]) await assert.rejects(engine.query(statement), /READ transaction|read.only/i);
    assert.deepEqual(await engine.query("MATCH (n) RETURN count(n) AS total"), before);
  } finally {
    engine.close();
    server.kill();
    await new Promise(resolve => server.once("close", resolve));
    await rm(scratch, { recursive: true, force: true });
  }
});
