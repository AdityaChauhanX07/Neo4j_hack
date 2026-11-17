MERGE (dx:Diagnosis {id: $id})
SET dx.run = $run, dx.ts = $now, dx.window_from = $from, dx.window_to = $now,
    dx.confidence = $confidence, dx.state = 'open'
WITH dx
UNWIND $ranked AS s
MATCH (c {id: s.suspect})
WHERE s.kind IN labels(c)
CREATE (dx)-[:SUSPECTS {rank: s.rank, score: s.score, covered: s.covered,
                        contradicted: s.contradicted}]->(c)
