import "@fontsource-variable/geist";
import "./style.css";
import fixture from "../../downlink/common-cause.json";
import { openEngine } from "./engine.js";
import { validateSnapshot } from "./graph-data.js";
import { createWiring, partName } from "./wiring.js";
import {
  contradictions, deviceFaults, episodes, events, evidence, precursorCutoff, presetQueries, resolved,
} from "./queries.js";
import { element, options, show, showDiagnosis, table } from "./render.js";

const ids = [
  "browse", "changes", "channel", "component", "diagnosis", "diagnosis-state", "episode",
  "execute", "file", "fit", "graph-size", "metadata", "notice", "parameters", "part",
  "precursors", "preset", "query", "query-result", "query-status", "restore", "source",
  "timeline", "timeline-caption", "wiring", "wiring-context", "simulation",
  "simulation-controls", "simulation-results", "simulation-score",
  "simulation-case", "simulation-recording",
];
const ui = Object.fromEntries(ids.map(id => [id, document.getElementById(id)]));
const eventColumns = [
  { key: "ts", label: "Time from fault" }, { key: "channel", label: "Channel" },
  { key: "status", label: "Status" }, { key: "value", label: "Reading" },
  { key: "id", label: "Event ID" },
];

let current;
let loadId = 0;
let episodeId = 0;
let partId = 0;
let restoreView;
const committed = "downlink";
const examples = new Map();
const graphs = new Map();
const simulationRoot = new URL("simulations/", location.href);

function notice(message, error = false) {
  ui.notice.hidden = !message;
  ui.notice.textContent = message;
  ui.notice.classList.toggle("error", error);
}

async function load(input, name, { bundled = false, example } = {}) {
  const attempt = ++loadId;
  let engine;
  ui.browse.disabled = true;
  ui.restore.disabled = true;
  ui.simulation.disabled = true;
  notice("Opening downlink…");
  try {
    const snapshot = await input;
    validateSnapshot(snapshot);
    engine = openEngine(snapshot);
    await engine.ready;
    const { rows } = await engine.query(episodes);
    if (attempt !== loadId) {
      engine.close();
      return false;
    }

    const episode = example ? rows.find(row => row.run === example.run) : rows[0];
    if (example && !episode) throw new Error("The selected simulation has no diagnosis.");

    current?.engine.close();
    current?.graph.dispose();
    current = {
      engine, graph: createWiring(ui.wiring, snapshot, inspectPart), rows, example,
      committed: bundled && !example,
    };
    ui.restore.hidden = bundled;
    ui.source.textContent = bundled ? "Synthetic fixture" : "Imported downlink";
    ui.source.title = name;
    ui["graph-size"].textContent = `${snapshot.nodes.length} nodes · ${snapshot.rels.length} relationships`;
    const system = snapshot.nodes.find(node => node.label === "Topology")?.props.id;
    current.system = system ?? name;
    const run = snapshot.nodes.find(node => node.label === "Run")?.props.id;
    ui.metadata.textContent = run ? `${current.system} / ${run}` : current.system;
    options(ui.part, current.graph.choices.map(part => ({ id: part.id, label: partName(part) })));
    ui.part.disabled = !current.graph.choices.length;
    options(ui.episode, rows.map(row => ({ id: row.id, label: row.id })));
    ui.episode.hidden = Boolean(example) || rows.length < 2;
    showSimulation(example, bundled);
    notice("");
    await loadEpisode(episode);
    return true;
  } catch (error) {
    if (engine !== current?.engine) engine?.close();
    if (attempt === loadId) {
      if (!current) ui.restore.hidden = false;
      notice(error.message, true);
    }
    return false;
  } finally {
    if (attempt === loadId) {
      ui.browse.disabled = false;
      ui.restore.disabled = false;
      ui.simulation.disabled = false;
    }
  }
}

async function loadEpisode(episode) {
  const attempt = ++episodeId;
  const inspected = partId;
  const session = current;
  session.episode = episode;
  session.events = [];
  session.first = null;
  ui["diagnosis-state"].hidden = true;
  ui.precursors.hidden = true;
  ui["query-result"].replaceChildren();
  ui["query-status"].textContent = "";
  options(ui.channel, [{ id: "", label: "All channels" }]);

  if (!episode) {
    showDiagnosis(ui.diagnosis, [], [], {});
    current.graph.highlight(null, []);
    ui["timeline-caption"].textContent = "";
    ui["wiring-context"].textContent = "Power and data dependencies";
    renderTimeline();
    await inspectPart(session.graph.choices[0]?.id);
    setPreset();
    return;
  }

  ui.metadata.textContent = `${session.system} / ${episode.run}`;
  const ids = { id: episode.id };
  const scope = {
    run: episode.run, from: episode.start, to: episode.end,
    device_faults: deviceFaults, exclude_devices: [],
  };
  try {
    const results = await Promise.all([
      session.engine.query(presetQueries.verdict, ids),
      session.engine.query(presetQueries.recovery, ids),
      session.engine.query(evidence, ids),
      session.engine.query(resolved, ids),
      session.engine.query(presetQueries.rank, scope),
    ]);
    if (session !== current || attempt !== episodeId) return;
    const [suspects, procedures, observed, resolution, ranked] = results.map(result => result.rows);
    const finish = resolution[0]?.ts ?? episode.end;
    const [timeline, before, contradicted] = await Promise.all([
      session.engine.query(events, { run: episode.run, start: episode.start - 1000, end: finish }),
      session.engine.query(presetQueries.before, { run: episode.run, t0: precursorCutoff(observed, episode) }),
      session.engine.query(contradictions, { ...scope, suspects: ranked.map(row => row.suspect) }),
    ]);
    const changes = before.rows;
    const against = contradicted.rows;
    if (session !== current || attempt !== episodeId) return;
    session.events = timeline.rows;
    session.first = observed[0];

    const top = suspects[0];
    ui["diagnosis-state"].hidden = false;
    ui["diagnosis-state"].textContent = episode.state === "resolved" ? "Resolved" : "Open";
    ui["diagnosis-state"].classList.toggle("resolved", episode.state === "resolved");
    const names = new Map(against.map(row => [row.suspect, row.against]));
    const candidates = ranked.map(row => ({ ...row, against: names.get(row.suspect) ?? [] }));
    showDiagnosis(ui.diagnosis, suspects, procedures, episode, candidates);

    const byName = new Map(session.graph.choices.map(part => [partName(part), part.id]));
    const root = byName.get(top?.suspect);
    const failing = [...new Set(observed.filter(row => deviceFaults.includes(row.status))
      .map(row => byName.get(row.device)).filter(Boolean))];
    session.graph.highlight(root, failing);
    ui["wiring-context"].textContent = root ? `Suspect paths to ${top.suspect}` : "Power and data dependencies";

    const channels = [...new Set(session.events.map(event => event.channel))].sort();
    options(ui.channel, [{ id: "", label: "All channels" }, ...channels.map(id => ({ id, label: id }))]);
    ui["timeline-caption"].textContent = `${episode.id} · ${timeline.count} readings${timeline.count > timeline.rows.length ? " · first 200 shown" : ""}`;
    renderTimeline();
    ui.precursors.hidden = !changes.length;
    table(ui.changes, [
      { key: "at", label: "Time from fault" }, { key: "channel", label: "Channel" },
      { key: "before", label: "Before" }, { key: "after", label: "After" },
    ], changes, (cell, key, row) => {
      cell.textContent = key === "at" ? offset(row.at, episode.start) : show(row[key]);
    });
    // Keep a part the operator picked while the episode was loading.
    if (partId === inspected) await inspectPart(root ?? session.graph.choices[0]?.id);
    setPreset();
  } catch (error) {
    if (session === current && attempt === episodeId) notice(error.message, true);
  }
}

function offset(timestamp, start) {
  const ms = timestamp - start;
  return `${ms > 0 ? "+" : ""}${ms} ms`;
}

function renderTimeline() {
  const { episode, events: rows, first } = current;
  const selected = rows.filter(row => !ui.channel.value || row.channel === ui.channel.value);
  table(ui.timeline, eventColumns, selected, (cell, key, row) => {
    cell.textContent = key === "ts" ? offset(row.ts, episode.start) : show(row[key]);
    if (key === "ts" || key === "id") cell.className = "code";
    if (key === "status") {
      cell.className = row.status === "OK" ? "event-status" : "event-status warning";
      if (row.id === first?.id) cell.append(element("span", "First fault", "event-marker"));
    }
    if (key === "value" && row.error) cell.textContent = row.error;
  }, "No readings in this episode.", row => row.id === first?.id ? "first-event" : "");
}

async function inspectPart(id) {
  const session = current;
  const part = session.graph.choices.find(node => node.id === id);
  if (!part) {
    ui.component.hidden = true;
    return;
  }
  const attempt = ++partId;
  const name = partName(part);
  ui.part.value = id;
  session.selected = part;
  session.graph.focus(id);
  ui.component.hidden = false;
  ui.component.replaceChildren(element("h3", `Impact of ${name}`), element("p", "Reading paths…"));
  if (ui.preset.value === "impact") setPreset();
  try {
    const { rows } = await session.engine.query(presetQueries.impact, { part: name });
    if (session !== current || attempt !== partId) return;
    const impact = rows.map(row => row.device);
    ui.component.lastElementChild.textContent = impact.length
      ? `Dependent devices · ${impact.join(", ")}`
      : "No downstream devices in this downlink.";
  } catch (error) {
    if (session === current && attempt === partId) ui.component.lastElementChild.textContent = error.message;
  }
}

function setPreset() {
  const preset = ui.preset.value;
  if (preset === "custom") return;
  const episode = current?.episode;
  const parameters = {
    verdict: { id: episode?.id ?? "" },
    rank: {
      run: episode?.run ?? "", from: episode?.start ?? 0, to: episode?.end ?? 0,
      device_faults: deviceFaults, exclude_devices: [],
    },
    impact: { part: current?.selected ? partName(current.selected) : "" },
    before: { run: episode?.run ?? "", t0: episode?.start ?? 0 },
    recovery: { id: episode?.id ?? "" },
  };
  ui.query.value = presetQueries[preset];
  ui.parameters.value = JSON.stringify(parameters[preset], null, 2);
}

async function executeConsole() {
  const session = current;
  if (!session) return;
  ui.execute.disabled = true;
  ui["query-status"].classList.remove("error");
  ui["query-status"].textContent = "Running query…";
  try {
    const parameters = JSON.parse(ui.parameters.value || "{}");
    const { columns, rows, count } = await session.engine.query(ui.query.value, parameters);
    if (session !== current) return;
    ui["query-status"].textContent = `${count} ${count === 1 ? "row" : "rows"}${count > rows.length ? " · first 200 shown" : ""}`;
    table(ui["query-result"], columns.map(key => ({ key, label: key })), rows);
  } catch (error) {
    if (session !== current) return;
    ui["query-result"].replaceChildren();
    ui["query-status"].textContent = error.message;
    ui["query-status"].classList.add("error");
  } finally {
    ui.execute.disabled = false;
  }
}

function showSimulation(example, bundled) {
  const key = example?.key ?? (bundled ? committed : "");
  ui.simulation.value = key;
  ui["simulation-results"].hidden = !example;
  const url = new URL(location.href);
  if (example) {
    restoreView = () => selectSimulation(example);
    url.searchParams.set("case", example.key);
    const { suite, expected, baseline } = example;
    const { count, top_one, baseline: baselineCount } = suite.score;
    ui["simulation-score"].textContent =
      `${suite.label} simulation · Correct first pick ${top_one}/${count} · First failed device ${baselineCount}/${count}`;
    ui["simulation-case"].textContent = `Expected ${expected.join(", ")} · First failed device ${baseline ?? "-"}`;
    ui["simulation-recording"].href = new URL(suite.recording, simulationRoot).href;
  } else if (bundled) {
    restoreView = openCommitted;
    url.searchParams.set("case", committed);
  } else {
    url.searchParams.delete("case");
  }
  history.replaceState(null, "", url);
}

async function readSimulation(filename) {
  const response = await fetch(new URL(filename, simulationRoot));
  if (!response.ok) throw new Error("The simulation could not be loaded.");
  return response.json();
}

async function simulationGraph(suite) {
  if (!graphs.has(suite.id)) graphs.set(suite.id, await readSimulation(suite.graph));
  return graphs.get(suite.id);
}

async function selectSimulation(example) {
  if (current?.example?.suite.id === example.suite.id) {
    const episode = current.rows.find(row => row.run === example.run);
    if (episode) {
      current.example = example;
      showSimulation(example);
      notice("");
      await loadEpisode(episode);
      return true;
    }
  }
  const opened = await load(simulationGraph(example.suite), example.label, { bundled: true, example });
  if (!opened && current) ui.simulation.value = current.example?.key ?? "";
  return opened;
}

function openCommitted() {
  return load(fixture, "common-cause.json", { bundled: true });
}

async function start() {
  try {
    const { suites } = await readSimulation("index.json");
    for (const suite of suites) {
      for (const scenario of suite.cases) {
        const key = `${suite.id}:${scenario.id}`;
        examples.set(key, { ...scenario, key, suite });
      }
    }
    if (examples.size) {
      options(ui.simulation, [
        { id: "", label: "Choose a case" },
        { id: committed, label: "Committed downlink · downlink/common-cause.json" },
        ...[...examples.values()].map(example => ({
          id: example.key,
          label: `${example.suite.label}${example.suite.id === "cubesat" ? " " + example.id : ""} · ${example.label}`,
        })),
      ]);
      ui["simulation-controls"].hidden = false;
      const requested = new URLSearchParams(location.search).get("case");
      if (requested === committed && await openCommitted()) return;
      if (await selectSimulation(examples.get(requested) ?? examples.values().next().value)) return;
    }
  } catch {
    // The bundled F1 fixture also works when the optional simulations have not been built.
  }
  await openCommitted();
}

ui.browse.addEventListener("click", () => ui.file.click());
ui.file.addEventListener("change", async () => {
  const file = ui.file.files[0];
  ui.file.value = "";
  if (!file) return;
  try {
    await load(JSON.parse(await file.text()), file.name);
  } catch {
    notice("This file could not be parsed as JSON.", true);
  }
});
ui.restore.addEventListener("click", () => (restoreView ?? openCommitted)());
ui.simulation.addEventListener("change", () => {
  const example = examples.get(ui.simulation.value);
  if (example) selectSimulation(example);
  else if (ui.simulation.value === committed) openCommitted();
  else ui.simulation.value = current?.example?.key ?? (current?.committed ? committed : "");
});
ui.fit.addEventListener("click", () => current?.graph.fit());
ui.part.addEventListener("change", () => inspectPart(ui.part.value));
ui.episode.addEventListener("change", () => loadEpisode(current.rows.find(row => row.id === ui.episode.value)));
ui.channel.addEventListener("change", renderTimeline);
ui.preset.addEventListener("change", setPreset);
for (const field of [ui.query, ui.parameters]) {
  field.addEventListener("input", () => { ui.preset.value = "custom"; });
}
ui.execute.addEventListener("click", executeConsole);

setPreset();
start();
