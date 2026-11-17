import "@fontsource-variable/geist";
import "./style.css";
import fixture from "../../downlink/common-cause.json";
import { openEngine } from "./engine.js";
import { validateSnapshot } from "./graph-data.js";
import { createWiring, partName } from "./wiring.js";
import { deviceFaults, episodes, events, evidence, presetQueries, resolved } from "./queries.js";
import { element, options, show, showDiagnosis, table } from "./render.js";

const ids = [
  "browse", "changes", "channel", "component", "diagnosis", "diagnosis-state", "episode",
  "execute", "file", "fit", "graph-size", "metadata", "notice", "parameters", "part",
  "precursors", "preset", "query", "query-result", "query-status", "restore", "source",
  "timeline", "timeline-caption", "wiring", "wiring-context",
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

function notice(message, error = false) {
  ui.notice.hidden = !message;
  ui.notice.textContent = message;
  ui.notice.classList.toggle("error", error);
}

async function load(snapshot, name, bundled = false) {
  const attempt = ++loadId;
  let engine;
  ui.browse.disabled = true;
  ui.restore.disabled = true;
  notice("Opening downlink…");
  try {
    validateSnapshot(snapshot);
    engine = openEngine(snapshot);
    await engine.ready;
    const { rows } = await engine.query(episodes);
    if (attempt !== loadId) {
      engine.close();
      return;
    }

    current?.engine.close();
    current?.graph.dispose();
    current = { engine, graph: createWiring(ui.wiring, snapshot, inspectPart), rows };
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
    ui.episode.hidden = rows.length < 2;
    notice("");
    await loadEpisode(rows[0]);
  } catch (error) {
    if (engine !== current?.engine) engine?.close();
    if (attempt === loadId) {
      if (!current) ui.restore.hidden = false;
      notice(error.message, true);
    }
  } finally {
    if (attempt === loadId) {
      ui.browse.disabled = false;
      ui.restore.disabled = false;
    }
  }
}

async function loadEpisode(episode) {
  const attempt = ++episodeId;
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
  const run = { run: episode.run, t0: episode.start };
  try {
    const results = await Promise.all([
      session.engine.query(presetQueries.verdict, ids),
      session.engine.query(presetQueries.recovery, ids),
      session.engine.query(evidence, ids),
      session.engine.query(resolved, ids),
      session.engine.query(presetQueries.before, run),
    ]);
    if (session !== current || attempt !== episodeId) return;
    const [suspects, procedures, observed, resolution, changes] = results.map(result => result.rows);
    const finish = resolution[0]?.ts ?? episode.end;
    const timeline = await session.engine.query(events, {
      run: episode.run, start: episode.start - 1000, end: finish,
    });
    if (session !== current || attempt !== episodeId) return;
    session.events = timeline.rows;
    session.first = observed[0];

    const top = suspects[0];
    ui["diagnosis-state"].hidden = false;
    ui["diagnosis-state"].textContent = episode.state === "resolved" ? "Resolved" : "Open";
    ui["diagnosis-state"].classList.toggle("resolved", episode.state === "resolved");
    showDiagnosis(ui.diagnosis, suspects, procedures, episode);

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
    await inspectPart(root ?? session.graph.choices[0]?.id);
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
ui.restore.addEventListener("click", () => load(fixture, "common-cause.json", true));
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
load(fixture, "common-cause.json", true);
