// Browser-side helpers for the diagnosis card and timeline. They have no Vite
// imports, so the Node tests can load them.

export const deviceFaults = ["NO_RESPONSE", "OUT_OF_RANGE", "STUCK", "STALE", "HEARTBEAT_LOST"];

// before.cypher lists changes strictly before $t0. The episode opens on its
// first anomaly, often the voltage sag itself, so cut off just after the first
// missed device reading to keep the sag and the dropout in the list.
export function precursorCutoff(observed, episode) {
  const missed = observed.filter(row => deviceFaults.includes(row.status)).map(row => row.ts);
  return (missed.length ? Math.min(...missed) : episode.start) + 1;
}

// Names the healthy devices behind each candidate's contradicted count. It uses
// the same healthy-device rule and dependency paths as queries/rank.cypher.
export const contradictions = `
MATCH (e:Event)-[:ON]->(:TelemetryChannel)-[:READS]->(d:Device)
WHERE e.run = $run AND e.ts >= $from AND e.ts <= $to
WITH d, collect(DISTINCT e.status) AS statuses
WHERE none(s IN statuses WHERE s IN $device_faults)
  AND any(s IN statuses WHERE s IN ['OK', 'UNDERVOLTAGE'])
WITH collect(d) AS good
UNWIND $suspects AS suspect
MATCH (c {id: suspect})
OPTIONAL MATCH (h:Device)-[:POWERED_BY|FED_BY|ON_BUS*0..4]->(c)
WHERE h IN good
OPTIONAL MATCH (c)-[:CONTROLS]->(controlled:Device)
WHERE controlled IN good
RETURN suspect, collect(DISTINCT h.id) + collect(DISTINCT controlled.id) AS against
`.trim();
