MATCH (prev:Event)-[:NEXT]->(e:Event)-[:ON]->(ch:TelemetryChannel)
WHERE e.run = $run AND e.ts >= $t0 - 2000 AND e.ts < $t0
  AND (e.status <> prev.status
       OR CASE WHEN ch.scalar = true AND ch.change_threshold IS NOT NULL
               THEN abs(e.value - prev.value) > ch.change_threshold ELSE false END)
RETURN ch.id AS channel, prev.value AS before, e.value AS after, e.ts AS at
ORDER BY at, channel
