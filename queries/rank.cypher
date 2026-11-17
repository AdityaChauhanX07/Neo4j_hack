MATCH (e:Event)-[:ON]->(:TelemetryChannel)-[:READS]->(d:Device)
WHERE e.ts >= $from AND e.ts <= $to
WITH d,
     min(CASE WHEN e.status IN $device_faults THEN e.ts END) AS first_fault,
     max(CASE WHEN e.status IN ['OK', 'UNDERVOLTAGE'] THEN 1 ELSE 0 END) AS answered
WITH collect(CASE WHEN first_fault IS NOT NULL
                  THEN {device: d, ts: first_fault} END) AS bad,
     collect(CASE WHEN first_fault IS NULL AND answered = 1 THEN d END) AS good
UNWIND bad AS observation
WITH observation.device AS b, observation.ts AS fault_ts, size(bad) AS total_bad, good
MATCH (b)-[:POWERED_BY|FED_BY|ON_BUS*0..4]->(c)
WITH c, total_bad, good, count(DISTINCT b) AS covered, min(fault_ts) AS first_fault
MATCH (d:Device)-[:POWERED_BY|FED_BY|ON_BUS*0..4]->(c)
WITH c, total_bad, covered, first_fault, count(DISTINCT d) AS downstream,
     count(DISTINCT CASE WHEN d IN good THEN d END) AS contradicted
OPTIONAL MATCH (c)<-[:MONITORS]-(:TelemetryChannel)<-[:ON]-(e:Event {status: 'UNDERVOLTAGE'})
WHERE e.ts >= $from AND e.ts <= $to
WITH c, total_bad, covered, contradicted, downstream, first_fault,
     count(e) > 0 AS direct_evidence
RETURN c.id AS suspect, labels(c)[0] AS kind, covered, contradicted,
       (toFloat(covered) / total_bad) *
       (toFloat(covered) / (covered + contradicted)) AS score
ORDER BY score DESC, direct_evidence DESC, downstream ASC, first_fault ASC, suspect ASC
