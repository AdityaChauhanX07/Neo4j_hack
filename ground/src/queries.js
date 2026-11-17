import before from "../../queries/before.cypher?raw";
import impact from "../../queries/impact.cypher?raw";
import rank from "../../queries/rank.cypher?raw";
import recovery from "../../queries/recovery.cypher?raw";

export const episodes = `
MATCH (dx:Diagnosis)
RETURN dx.id AS id, dx.run AS run, dx.state AS state, dx.confidence AS confidence,
       dx.window_from AS start, dx.window_to AS end
ORDER BY dx.ts DESC, dx.id DESC
`.trim();

export const verdict = `
MATCH (dx:Diagnosis {id: $id})-[s:SUSPECTS]->(part)
RETURN s.rank AS rank, part.id AS suspect, labels(part)[0] AS kind,
       s.covered AS covered, s.contradicted AS contradicted, s.score AS score
ORDER BY rank
`.trim();

export const events = `
MATCH (e:Event {run: $run})-[:ON]->(ch:TelemetryChannel)-[:READS]->(device:Device)
WHERE e.ts >= $start AND e.ts <= $end
RETURN e.id AS id, e.ts AS ts, e.status AS status, ch.id AS channel,
       device.id AS device, e.value AS value, e.error AS error
ORDER BY e.ts, e.seq, e.id
`.trim();

export const evidence = `
MATCH (dx:Diagnosis {id: $id})-[:BASED_ON]->(e:Event)-[:ON]->(ch:TelemetryChannel)-[:READS]->(device:Device)
RETURN e.id AS id, e.ts AS ts, e.status AS status, ch.id AS channel,
       device.id AS device, e.value AS value, e.error AS error
ORDER BY e.ts, e.seq, e.id
`.trim();

export const resolved = `
MATCH (dx:Diagnosis {id: $id})-[:RESOLVED_AT]->(e:Event)
RETURN e.ts AS ts
`.trim();

export const presetQueries = { verdict, before, impact, rank, recovery };

export const deviceFaults = ["NO_RESPONSE", "OUT_OF_RANGE", "STUCK", "STALE", "HEARTBEAT_LOST"];
