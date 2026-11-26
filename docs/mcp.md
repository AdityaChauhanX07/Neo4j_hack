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

## Checked explanation example

The following facts were read through the MCP stdio connection against
the committed synthetic F1 graph on November 26, 2026:

Diagnosis `dx:f1-fixture:1` ranks `REG_B` with high confidence and resolved
state. Its stored suspect relationship covers three failed devices with
zero healthy-device contradictions (`dx:f1-fixture:1`, `REG_B`). The IMU,
magnetometer, and first sun sensor have missing-reply evidence
(`imu`, `mag`, `sun1`; events `reading:f1-fixture:23`,
`reading:f1-fixture:25`, and `reading:f1-fixture:29`). The monitor's voltage
reading is 0.16 V and classified `UNDERVOLTAGE`
(`eps.regb.voltage`, `reading:f1-fixture:26`).

The linked failure mode is regulator dropout (`regulator-dropout`). Its
procedure says to inspect the input supply and regulator wiring, then
reinitialize the affected drivers once output is stable
(`power-cycle-regulator`). The procedure's recorded risk is interruption
of the attached devices. Recovery is linked to an OK event
(`reading:f1-fixture:83`).

This example retains the graph's cause, confidence, evidence, procedure,
and IDs. The MCP tests independently check the links and that every
returned citation identifies a node in the graph.
