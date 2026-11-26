import { deviceFaults } from "./evidence.js";

const names = {
  imu: "Motion sensor", mag: "Compass", sun1: "Sun sensor 1", sun2: "Sun sensor 2",
  epsmon: "Power monitor", thermal: "Temperature sensor", payload: "Payload sensor", radio: "Radio",
  REG_B: "Regulator B", REG_A: "Platform supply", RAIL_5V: "Main 5 V supply", RAIL_PI: "Computer supply",
  "I2C-1": "Data bus 1", "I2C-3": "Data bus 3", UART0: "Radio link", "drv.imu": "Motion sensor driver",
  BEC_5V: "5 V regulator", fc: "Flight controller", compass: "Compass", barometer: "Barometer",
  gyro: "Gyroscope", gps: "GPS receiver", telemetry: "Telemetry radio", "power-monitor": "Power monitor",
  PDB: "Power distribution", BATTERY: "Battery", "I2C-FC": "Compass data bus", "SPI-FC": "Motion data bus",
};

export function friendlyName(id) {
  if (names[id]) return names[id];
  if (/^esc\.\d$/.test(id)) return `Motor controller ${id.at(-1)}`;
  if (/^motor\.\d$/.test(id)) return `Motor ${id.at(-1)}`;
  return String(id).replaceAll("_", " ");
}

export function tourFacts(snapshot, episode, { suspects, observed, resolution, candidates, procedures }) {
  const nodes = new Map(snapshot.nodes.map(node => [node.id, node]));
  const devices = snapshot.nodes.filter(node => node.label === "Device").map(node => node.props.id);
  const channels = new Map(snapshot.rels.filter(rel => rel.type === "READS")
    .map(rel => [rel.from, nodes.get(rel.to)?.props.id]));
  const eventChannels = new Map(snapshot.rels.filter(rel => rel.type === "ON").map(rel => [rel.from, rel.to]));
  const events = snapshot.nodes.filter(node => node.label === "Event" && node.props.run === episode.run)
    .map(node => ({ ...node.props, device: channels.get(eventChannels.get(node.id)) }));
  const bad = [...new Set(observed.filter(row => deviceFaults.includes(row.status)).map(row => row.device))];
  const window = events.filter(row => row.ts >= episode.start && row.ts <= episode.end);
  const good = devices.filter(device => window.some(row => row.device === device && ["OK", "UNDERVOLTAGE"].includes(row.status))
    && !window.some(row => row.device === device && deviceFaults.includes(row.status)));
  const before = devices.filter(device => events.some(row => row.device === device && row.ts < episode.start && row.status === "OK"));
  const busByDevice = new Map(snapshot.rels.filter(rel => rel.type === "ON_BUS")
    .map(rel => [nodes.get(rel.from)?.props.id, nodes.get(rel.to)?.props.id]));
  const next = new Map();
  for (const rel of snapshot.rels) {
    if (!["POWERED_BY", "FED_BY", "ON_BUS", "CONTROLS"].includes(rel.type)) continue;
    const from = nodes.get(rel.type === "CONTROLS" ? rel.to : rel.from)?.props.id;
    const to = nodes.get(rel.type === "CONTROLS" ? rel.from : rel.to)?.props.id;
    if (!next.has(from)) next.set(from, []);
    next.get(from).push(to);
  }
  function depends(device, root) {
    const queue = [device];
    const seen = new Set();
    for (const part of queue) {
      if (part === root) return true;
      if (seen.has(part)) continue;
      seen.add(part);
      queue.push(...(next.get(part) ?? []));
    }
    return false;
  }
  const roots = suspects.map(row => ({ id: row.suspect, kind: row.kind,
    devices: bad.filter(device => depends(device, row.suspect)) }));
  const ruledOut = candidates.find(row => !roots.some(root => root.id === row.suspect)
    && row.kind === "Bus" && row.against.length) ?? candidates.find(row => row.against.length);
  const voltage = observed.find(row => row.status === "UNDERVOLTAGE" && typeof row.value === "number");
  const diagnosis = snapshot.nodes.find(node => node.label === "Diagnosis" && node.props.id === episode.id)?.props;
  return {
    bad, good, before, roots, busByDevice, ruledOut, voltage, procedures,
    total: devices.length, buses: new Set(bad.map(id => busByDevice.get(id)).filter(Boolean)).size,
    confidence: episode.confidence, recovered: resolution.length > 0,
    decisionMs: diagnosis?.first_verdict_ts == null ? null : diagnosis.first_verdict_ts - episode.start,
    recoveryMs: resolution[0] ? resolution[0].ts - episode.start : null,
  };
}
