MATCH (d:Device)-[:POWERED_BY|FED_BY|ON_BUS*0..4]->(c {id: $part})
WITH DISTINCT d
OPTIONAL MATCH (ch:TelemetryChannel)-[:READS]->(d)
RETURN d.id AS device, collect(ch.id) AS channels_lost
ORDER BY device
UNION
MATCH (c:Driver {id: $part})-[:CONTROLS]->(d:Device)
OPTIONAL MATCH (ch:TelemetryChannel)-[:READS]->(d)
RETURN d.id AS device, collect(ch.id) AS channels_lost
ORDER BY device
