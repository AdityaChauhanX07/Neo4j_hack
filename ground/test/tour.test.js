import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import { tourFacts } from "../src/tour-data.js";

const graph = JSON.parse(await readFile(new URL("../public/simulations/cubesat.json", import.meta.url), "utf8"));

function facts(fault) {
  const run = `bench-fixture-${fault.toLowerCase()}`;
  const dx = graph.nodes.find(node => node.label === "Diagnosis" && node.props.run === run);
  const nodes = new Map(graph.nodes.map(node => [node.id, node]));
  const channels = new Map(graph.rels.filter(rel => rel.type === "READS").map(rel => [rel.from, nodes.get(rel.to).props.id]));
  const on = new Map(graph.rels.filter(rel => rel.type === "ON").map(rel => [rel.from, rel.to]));
  const observed = graph.rels.filter(rel => rel.type === "BASED_ON" && rel.from === dx.id).map(rel => ({
    ...nodes.get(rel.to).props, device: channels.get(on.get(rel.to)),
  }));
  const suspects = graph.rels.filter(rel => rel.type === "SUSPECTS" && rel.from === dx.id)
    .sort((a, b) => a.props.rank - b.props.rank)
    .map(rel => ({ suspect: nodes.get(rel.to).props.id, kind: nodes.get(rel.to).label }));
  const resolution = graph.rels.filter(rel => rel.type === "RESOLVED_AT" && rel.from === dx.id)
    .map(rel => ({ ts: nodes.get(rel.to).props.ts }));
  return tourFacts(graph, { id: dx.props.id, run, start: dx.props.window_from, end: dx.props.window_to,
    confidence: dx.props.confidence }, { suspects, observed, resolution, candidates: [], procedures: [] });
}

test("the F1 walkthrough uses real affected, healthy, bus, and recovery facts", () => {
  const view = facts("F1");
  assert.deepEqual(new Set(view.bad), new Set(["imu", "mag", "sun1"]));
  assert.equal(view.buses, 2);
  assert.equal(view.before.length, 8);
  assert.equal(view.good.length, 5);
  assert.deepEqual(view.roots, [{ id: "REG_B", kind: "Regulator", devices: view.bad }]);
  assert.equal(view.recovered, true);
  assert.ok(view.recoveryMs > view.decisionMs);
});

test("a bus fault changes both the explanation and its actual affected group", () => {
  const view = facts("F2");
  assert.equal(view.roots[0].id, "I2C-1");
  assert.deepEqual(new Set(view.bad), new Set(["imu", "mag", "epsmon", "thermal"]));
  assert.equal(view.buses, 1);
});

test("the two-cause walkthrough keeps the stored uncertainty and overlapping dependencies", () => {
  const view = facts("F9");
  assert.equal(view.confidence, "low");
  assert.deepEqual(view.roots.map(root => root.id), ["REG_B", "I2C-3"]);
  assert.ok(view.roots.every(root => root.devices.includes("sun1")));
  assert.equal(view.bad.length, 5);
});
