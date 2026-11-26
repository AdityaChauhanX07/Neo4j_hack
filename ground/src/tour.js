import { element } from "./render.js";
import { friendlyName } from "./tour-data.js";

const joins = ids => new Intl.ListFormat("en", { style: "long", type: "conjunction" }).format(ids.map(friendlyName));
const duration = ms => `${(ms / 1000).toFixed(1)} seconds`;

export function createTour({ selectCase, inspect }) {
  const ids = ["tour", "tour-loading", "tour-system", "tour-map-state", "tour-map", "tour-map-note",
    "tour-kicker", "tour-title", "tour-description", "tour-proof", "tour-next", "tour-reset", "start-demo"];
  const ui = Object.fromEntries(ids.map(id => [id, document.getElementById(id)]));
  const steps = [...document.querySelectorAll("[data-stage]")];
  const cases = [...document.querySelectorAll("[data-case]")];
  let stage = 0;
  let key;
  let facts;
  let system;
  let busy = true;
  let choosing = false;

  function setBusy(value) {
    busy = value;
    [...cases, ...steps, ui["tour-next"], ui["tour-reset"]].forEach(button => { button.disabled = value; });
    ui.tour.setAttribute("aria-busy", String(value));
  }

  function proof(label, detail) {
    const row = element("div", null, "proof-row");
    row.append(element("span", label), element("p", detail));
    ui["tour-proof"].append(row);
  }

  function drawConnections() {
    const map = ui["tour-map"];
    const svg = map.querySelector("svg");
    if (!svg || !map.clientWidth) return;
    const bounds = map.getBoundingClientRect();
    svg.setAttribute("viewBox", `0 0 ${bounds.width} ${bounds.height}`);
    svg.replaceChildren();
    for (const [index, root] of facts.roots.entries()) {
      const source = map.querySelector(`[data-root="${index}"]`).getBoundingClientRect();
      for (const device of root.devices) {
        const target = [...map.querySelectorAll("[data-device]")].find(node => node.dataset.device === device)?.getBoundingClientRect();
        if (!target) continue;
        const x1 = source.left + source.width / 2 - bounds.left;
        const y1 = source.bottom - bounds.top;
        const x2 = target.left + target.width / 2 - bounds.left;
        const y2 = target.top - bounds.top;
        const mid = (y1 + y2) / 2;
        const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
        path.setAttribute("d", `M ${x1} ${y1} C ${x1} ${mid}, ${x2} ${mid}, ${x2} ${y2}`);
        svg.append(path);
      }
    }
  }

  function renderMap() {
    const map = ui["tour-map"];
    map.dataset.stage = stage;
    map.replaceChildren();
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("aria-hidden", "true");
    map.append(svg);
    const roots = element("div", null, "map-roots");
    facts.roots.forEach((root, index) => {
      const box = element("div", null, "map-root");
      box.dataset.root = index;
      box.append(element("span", stage === 1 ? "A shared dependency?" : root.kind === "Bus" ? "Communication" : "Shared dependency", "map-node-kind"),
        element("strong", stage === 1 ? "Trace the connection" : friendlyName(root.id)),
        element("small", stage === 0 ? (root.kind === "Bus" ? "Connecting this group" : "Supporting this group") : stage === 1 ? "The clues are in the wiring" : stage === 3 && facts.recovered ? "Responding again" : "Suspected cause"));
      roots.append(box);
    });
    map.append(roots);
    const devices = element("div", null, "map-devices");
    for (const device of facts.bad) {
      const node = element("div", null, "map-device");
      node.dataset.device = device;
      const healthy = stage === 0 ? facts.before.includes(device) : stage === 3 && facts.recovered;
      node.append(element("span", healthy ? "Healthy" : stage === 0 ? "Unknown" : "Needs attention", "device-status"),
        element("strong", friendlyName(device)), element("small", friendlyName(facts.busByDevice.get(device) ?? "Local sampler")));
      devices.append(node);
    }
    map.append(devices);
    requestAnimationFrame(drawConnections);
  }

  function render() {
    if (!facts) return;
    ui.tour.hidden = false;
    ui["tour-loading"].hidden = true;
    ui["start-demo"].disabled = false;
    steps.forEach(button => {
      const selected = Number(button.dataset.stage) === stage;
      if (selected) button.setAttribute("aria-current", "step");
      else button.removeAttribute("aria-current");
      button.classList.toggle("complete", Number(button.dataset.stage) < stage);
    });
    cases.forEach(button => button.setAttribute("aria-pressed", String(button.dataset.case === key)));
    ui["tour-system"].textContent = system === "quadcopter" ? "Quadcopter · dependency view" : "CubeSat · dependency view";
    ui["tour-proof"].replaceChildren();
    ui["tour-reset"].hidden = stage === 0;
    const labels = ["Before the fault", "Something stopped responding", "Follow the common connection", "Check what came back"];
    ui["tour-kicker"].textContent = `Step ${stage + 1} / 4 · ${labels[stage]}`;
    if (stage === 0) {
      ui["tour-title"].textContent = "Start with a healthy system.";
      ui["tour-description"].textContent = `The recording begins with normal readings from ${facts.before.length} devices. Watch what happens when a shared connection fails.`;
      proof("Your task", "Find the cause behind the sensor alarms, using the parts they depend on.");
      proof("This view", `The ${facts.bad.length} devices shown are the group affected later in this recording.`);
      ui["tour-next"].textContent = "Introduce the fault";
      ui["tour-map-state"].textContent = "Healthy readings";
      ui["tour-map-note"].textContent = "Connections describe dependencies. The sensors haven't failed yet.";
    } else if (stage === 1) {
      ui["tour-title"].textContent = `${facts.bad.length} ${facts.bad.length === 1 ? "device needs" : "devices need"} attention.`;
      ui["tour-description"].textContent = `${joins(facts.bad)} ${facts.bad.length === 1 ? "has" : "have"} missing or abnormal readings. That tells us the symptoms. What explains them together?`;
      proof("A useful clue", facts.buses > 1 ? `The affected devices use ${facts.buses} different data buses. Look beyond a single bus.` : "Look at both the data connection and the supply feeding these devices.");
      proof("Still responding", facts.good.length ? joins(facts.good) : "There are no healthy-device observations in this window.");
      ui["tour-next"].textContent = "See the diagnosis";
      ui["tour-map-state"].textContent = `${facts.bad.length} affected`;
      ui["tour-map-note"].textContent = "Several alarms can be symptoms of a shared failure.";
    } else if (stage === 2) {
      ui["tour-title"].textContent = joins(facts.roots.map(root => root.id));
      ui["tour-description"].textContent = facts.roots.length > 1
        ? "One part doesn't explain this whole pattern. The stored diagnosis names multiple causes for different groups of affected devices."
        : `The graph connects the failing devices to ${friendlyName(facts.roots[0].id)}. It also checks whether that explanation would wrongly blame devices that still work.`;
      const confidence = { high: "Strong evidence", medium: "Some uncertainty", low: "More inspection needed" }[facts.confidence] ?? "Confidence not recorded";
      proof(confidence, facts.roots.length > 1 ? "Multiple causes are recorded; treat the confidence level as a reason to inspect the evidence." : `Explains ${facts.bad.length} affected ${facts.bad.length === 1 ? "device" : "devices"} in this episode.`);
      if (facts.ruledOut) proof(`Why not ${friendlyName(facts.ruledOut.suspect)}?`, `${joins(facts.ruledOut.against)} ${facts.ruledOut.against.length === 1 ? "is" : "are"} still responding. That weakens this alternative.`);
      else if (facts.voltage) proof("Direct evidence", `The monitor recorded ${facts.voltage.value} V on ${facts.voltage.channel}.`);
      if (facts.decisionMs != null) proof("Recorded timing", `First verdict ${duration(facts.decisionMs)} after the first abnormal reading. This is recording time, not browser speed.`);
      ui["tour-next"].textContent = "Check the recovery";
      ui["tour-map-state"].textContent = facts.roots.length > 1 ? "Multiple causes" : "Shared cause identified";
      ui["tour-map-note"].textContent = "The highlighted connections link the symptoms to the recorded suspect parts.";
    } else {
      ui["tour-title"].textContent = facts.recovered ? "The readings return." : "The fault is still open.";
      ui["tour-description"].textContent = facts.recovered
        ? "The later telemetry shows the affected channels responding normally again. The diagnosis closes with a link to the recovery evidence."
        : "The recording contains no confirmed resolution. A suggested procedure alone doesn't establish that a fault recovered.";
      proof("Recorded outcome", facts.recovered ? `Resolved ${duration(facts.recoveryMs)} after the first abnormal reading.` : "No resolution event is present.");
      if (facts.procedures[0]) proof("Linked guidance", facts.procedures[0].procedure);
      proof("Try another explanation", "Switch to a blocked data bus or two simultaneous faults. The same graph reasoning follows their dependencies.");
      ui["tour-next"].textContent = "Replay this walkthrough";
      ui["tour-map-state"].textContent = facts.recovered ? "Recovery recorded" : "Unresolved";
      ui["tour-map-note"].textContent = facts.recovered ? "Healthy readings confirm recovery in this simulated recording." : "Keep observing the affected devices before declaring recovery.";
    }
    renderMap();
  }

  async function choose(caseKey) {
    if (busy) return;
    choosing = true;
    setBusy(true);
    ui["tour-loading"].textContent = "Loading this scenario…";
    ui["tour-loading"].hidden = false;
    try { await selectCase(caseKey); }
    finally { choosing = false; setBusy(false); }
  }
  cases.forEach(button => button.addEventListener("click", () => choose(button.dataset.case)));
  steps.forEach(button => button.addEventListener("click", () => { stage = Number(button.dataset.stage); render(); }));
  ui["tour-next"].addEventListener("click", () => { stage = (stage + 1) % 4; render(); });
  ui["tour-reset"].addEventListener("click", () => { stage = 0; render(); });
  ui["start-demo"].addEventListener("click", async () => {
    if (!facts || !key) await choose("cubesat:F1");
    stage = 0;
    render();
    document.getElementById("demo").scrollIntoView({ behavior: "smooth", block: "start" });
    document.getElementById("demo-heading").focus({ preventScroll: true });
  });
  document.querySelectorAll("[data-open-workspace]").forEach(button => button.addEventListener("click", inspect));
  const observer = new ResizeObserver(drawConnections);
  observer.observe(ui["tour-map"]);
  setBusy(true);
  return {
    set(fresh, context) {
      if (!context.guided) {
        ui.tour.hidden = true;
        ui["tour-loading"].hidden = false;
        ui["tour-loading"].textContent = "Your selected recording is open in the evidence workspace. Use ‘Try a fault’ to return to the walkthrough.";
        facts = null;
        key = null;
        if (!choosing) setBusy(false);
        return;
      }
      if (key !== context.key) stage = 0;
      facts = fresh;
      key = context.key;
      system = context.system;
      if (!choosing) setBusy(false);
      render();
    },
    fail(message) {
      ui["tour-loading"].hidden = false;
      ui["tour-loading"].textContent = message;
      setBusy(false);
    },
  };
}
