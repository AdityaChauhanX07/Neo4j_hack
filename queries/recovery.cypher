MATCH (dx:Diagnosis {id: $id})-[m:MATCHES]->(fm:FailureMode)-[:RECOVERED_BY]->(rp:RecoveryProcedure)
RETURN m.suspect AS suspect, fm.id AS mode_id, fm.name AS failure_mode,
       rp.id AS procedure_id, rp.title AS procedure, rp.steps AS steps, rp.risk AS risk
ORDER BY m.rank
