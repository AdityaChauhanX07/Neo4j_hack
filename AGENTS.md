# Explain a Common Cause diagnosis

Use the read-only Relate graph for operator questions. Start with the latest
`Diagnosis`, or the diagnosis ID the operator supplies.

Follow `SUSPECTS` in rank order, `BASED_ON` for telemetry, and `RESOLVED_AT`
for recovery status. Use `MATCHES` and `RECOVERED_BY` for the recorded failure
mode and procedure.

Cite graph IDs for component, event, diagnosis, and procedure claims. Describe
coverage, contradictions, and confidence as recorded. If the graph lacks an
observation, say which channel or component would help resolve the question.
Give recovery steps only from the linked procedure.
