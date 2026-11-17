import cytoscape from "cytoscape";

const tiers = ["PowerRail", "Regulator", "Bus", "Device", "Driver"];
const wireTypes = new Set(["FED_BY", "POWERED_BY", "ON_BUS", "CONTROLS"]);

export function partName(node) {
  return String(node.props.id ?? node.id);
}

export function createWiring(container, snapshot, onSelect) {
  const parts = snapshot.nodes.filter(node => tiers.includes(node.label));
  const partIds = new Set(parts.map(node => node.id));
  const wires = snapshot.rels.filter(rel => (
    wireTypes.has(rel.type) && partIds.has(rel.from) && partIds.has(rel.to)
  ));
  const choices = [...parts].sort((a, b) => partName(a).localeCompare(partName(b)));
  const buses = new Map(wires.filter(rel => rel.type === "ON_BUS").map(rel => [rel.from, rel.to]));
  const elements = [];
  let y = 0;

  for (const tier of tiers) {
    const nodes = parts.filter(node => node.label === tier).sort((a, b) => (
      (buses.get(a.id) ?? "").localeCompare(buses.get(b.id) ?? "") ||
      partName(a).localeCompare(partName(b))
    ));
    for (let offset = 0; offset < nodes.length; offset += 8) {
      const row = nodes.slice(offset, offset + 8);
      row.forEach((node, index) => elements.push({
        data: { id: node.id, name: partName(node), kind: node.label },
        position: { x: (index - (row.length - 1) / 2) * 105, y },
      }));
      y += 77;
    }
  }

  const wireIds = wires.map((wire, index) => {
    let id = `wire-${index}`;
    while (partIds.has(id)) id = `_${id}`;
    elements.push({
      data: { id, source: wire.from, target: wire.to },
      classes: wire.type === "ON_BUS" ? "bus-wire" : "",
    });
    return id;
  });
  const next = new Map();
  for (const [index, wire] of wires.entries()) {
    const backwards = wire.type === "CONTROLS";
    const from = backwards ? wire.to : wire.from;
    const to = backwards ? wire.from : wire.to;
    if (!next.has(from)) next.set(from, []);
    next.get(from).push({ to, id: wireIds[index] });
  }

  const cy = cytoscape({
    container,
    elements,
    layout: { name: "preset", fit: true, padding: 25 },
    autoungrabify: true,
    boxSelectionEnabled: false,
    minZoom: 0.2,
    maxZoom: 2.8,
    style: [
      { selector: "node", style: {
        shape: "round-rectangle", width: "label", padding: "9px", height: 15,
        label: "data(name)", "text-valign": "center", "text-halign": "center",
        "font-family": "monospace", "font-size": 13, "font-weight": 700,
        color: "#edf3f9", "background-color": "#243a51", "border-width": 1,
        "border-color": "#6e88a1",
      } },
      { selector: '[kind = "PowerRail"]', style: {
        "background-color": "#30465c", "border-color": "#99b1c9",
      } },
      { selector: '[kind = "Regulator"]', style: {
        "background-color": "#2e405c", "border-color": "#91a3ca",
      } },
      { selector: '[kind = "Bus"]', style: {
        "background-color": "#1d4148", "border-color": "#75bdba",
      } },
      { selector: "edge", style: {
        width: 1.3, "curve-style": "bezier", "line-color": "#7898b7",
        "target-arrow-color": "#7898b7", "target-arrow-shape": "triangle", "arrow-scale": 0.65,
      } },
      { selector: "edge.bus-wire", style: {
        "line-color": "#6faaa9", "target-arrow-color": "#6faaa9", "line-style": "dashed",
      } },
      { selector: "edge.fault-path", style: {
        width: 2.7, "line-style": "solid", "line-color": "#ff9d83",
        "target-arrow-color": "#ff9d83", "arrow-scale": 0.82,
      } },
      { selector: "node.fault-path", style: {
        "background-color": "#543a42", "border-width": 2, "border-color": "#ff9d83",
      } },
      { selector: "node.focused", style: { "overlay-color": "#d1e7f9", "overlay-opacity": 0.17, "overlay-padding": 5 } },
    ],
  });
  cy.on("tap", "node", event => onSelect(event.target.id()));

  function fit() {
    if (parts.length) cy.fit(cy.elements(), 23);
  }
  const resize = new ResizeObserver(() => {
    cy.resize();
    fit();
  });
  resize.observe(container);

  function highlight(root, affected) {
    cy.elements().removeClass("fault-path");
    if (!root) return;
    cy.getElementById(root).addClass("fault-path");
    for (const start of affected) {
      cy.getElementById(start).addClass("fault-path");
      const queue = [{ node: start, steps: [] }];
      const seen = new Set([start]);
      for (const visit of queue) {
        if (visit.node === root) {
          for (const hop of visit.steps) {
            cy.getElementById(hop.to).addClass("fault-path");
            cy.getElementById(hop.id).addClass("fault-path");
          }
          break;
        }
        for (const hop of next.get(visit.node) ?? []) {
          if (seen.has(hop.to)) continue;
          seen.add(hop.to);
          queue.push({ node: hop.to, steps: [...visit.steps, hop] });
        }
      }
    }
  }

  return {
    choices,
    fit,
    highlight,
    focus(id) {
      cy.nodes().removeClass("focused");
      cy.getElementById(id).addClass("focused");
    },
    dispose() {
      resize.disconnect();
      cy.destroy();
    },
  };
}
