# Read-only ground agent

The repository's `.mcp.json` starts the Relate CLI against the committed F1
snapshot. Install the [Relate CLI](https://relatedb.ai/docs/get-started/install/),
check `relate --version`, and open this repository in an MCP-capable client.
The client needs to support project MCP configuration; configuration
discovery and activation depend on that client.

The server uses stdio and opens `data/common-cause.rl` read-only. It lists
`get_schema` and `read_cypher`; `write_cypher` is absent. To inspect a new
downlink, change only the database path to its `.rl` snapshot. JSON exports
are for the browser, not the MCP server.

## Ask about the graph

Use the operator instructions in `AGENTS.md`. A useful first request is:

> Explain the latest diagnosis. Cite the diagnosis, suspected component,
> telemetry evidence, failure mode, and recovery procedure by graph ID.
> Report its recorded confidence and distinguish observations from causes.

For the bundled F1 snapshot, the answer should name `REG_B` from
`dx:f1-fixture:1`, report high confidence and resolved state, explain the
three affected devices and zero healthy-device contradictions, and cite
the linked voltage and missing-reply events. Recovery instructions must
come from the linked procedure. For an ambiguous or intermittent episode,
the answer should preserve its stored confidence.

The same evidence is available without an agent:

```sh
commoncause explain dx:f1-fixture:1
```

## Reproduce the protocol checks

From the repository root with Python and Relate installed:

```sh
python -m pip install '.[test]'
python -m pytest -q tests/test_mcp.py
```

Set `RELATE_CLI` to the binary's full path if it is not on `PATH`. The
checks start the actual command from `.mcp.json`, perform the MCP
initialization handshake, list tools, read the schema, and traverse the
diagnosis, evidence, and recovery relationships. All returned citation IDs
are checked against graph nodes. A separate intermittent recording checks
that medium confidence is preserved.

Mutation probes run against disposable copies. Calls to the missing write
tool and writes submitted through `read_cypher`, including schema changes,
must fail. The snapshot's SHA-256 must remain unchanged, and a later read
must still work. Ground-view CI installs the CLI and runs these checks;
Python-only jobs skip them when the CLI is absent.

These checks verify the server and a real protocol client. They do not
measure an LLM's answer quality or certify every host application's MCP
configuration behavior. No hosted model or API key is needed for them.
