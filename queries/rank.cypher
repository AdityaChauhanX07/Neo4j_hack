MATCH (e:Event)-[:ON]->(:TelemetryChannel)-[:READS]->(d:Device)
WHERE e.run = $run AND e.ts >= $from AND e.ts <= $to
  AND coalesce(e.diagnostic, true)
  AND (e.confirmed_ts IS NULL OR e.confirmed_ts <= $to)
WITH d,
     min(CASE WHEN e.status IN $device_faults THEN e.ts END) AS first_fault,
     collect(DISTINCT e.status) AS statuses
WITH collect(CASE WHEN first_fault IS NOT NULL AND NOT d.id IN $exclude_devices
                  THEN {device: d, ts: first_fault, statuses: statuses} END) AS bad,
     collect(CASE WHEN first_fault IS NULL AND any(s IN statuses WHERE s IN ['OK', 'UNDERVOLTAGE'])
                  THEN d END) AS good
UNWIND bad AS observation
WITH observation.device AS b, observation.ts AS fault_ts, observation.statuses AS statuses,
     size(bad) AS total_bad, good
OPTIONAL MATCH (driver:Driver)-[:CONTROLS]->(b)
OPTIONAL MATCH (b)-[:ON_BUS]->(bus:Bus)
MATCH (b)-[:POWERED_BY|FED_BY|ON_BUS*0..4]->(upstream)
WITH b, fault_ts, statuses, total_bad, good, driver, bus, collect(DISTINCT upstream) AS parts
UNWIND CASE WHEN driver IS NOT NULL AND 'STALE' IN statuses THEN parts + [driver]
            ELSE parts END AS c
WITH c, total_bad, good, collect(DISTINCT b.id) AS covered_devices,
     min(fault_ts) AS first_fault,
     max(CASE WHEN c = driver AND 'STALE' IN statuses THEN 1
              WHEN c = bus AND 'HEARTBEAT_LOST' IN statuses THEN 1
              ELSE 0 END) AS link_evidence
OPTIONAL MATCH (d:Device)-[:POWERED_BY|FED_BY|ON_BUS*0..4]->(c)
OPTIONAL MATCH (c)-[:CONTROLS]->(controlled:Device)
WITH c, total_bad, covered_devices, first_fault, link_evidence,
     count(DISTINCT coalesce(d, controlled)) AS downstream,
     count(DISTINCT CASE WHEN coalesce(d, controlled) IN good
                         THEN coalesce(d, controlled) END) AS contradicted
OPTIONAL MATCH (c)<-[:MONITORS]-(:TelemetryChannel)<-[:ON]-(e:Event {status: 'UNDERVOLTAGE'})
WHERE e.run = $run AND e.ts >= $from AND e.ts <= $to
WITH c, total_bad, covered_devices, size(covered_devices) AS covered,
     contradicted, downstream, first_fault, link_evidence, count(e) AS voltage_reports
WITH c, total_bad, covered_devices, covered, contradicted, downstream, first_fault,
     voltage_reports > 0 OR link_evidence = 1 AS direct_evidence
RETURN c.id AS suspect, labels(c)[0] AS kind, covered, contradicted,
       (toFloat(covered) / total_bad) *
       (toFloat(covered) / (covered + contradicted)) AS score,
       covered_devices
ORDER BY score DESC, direct_evidence DESC, downstream ASC, first_fault ASC, suspect ASC
