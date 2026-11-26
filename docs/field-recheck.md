# Field recheck

Reviewed 2026-11-26. This is a bounded review of public projects, not a
novelty or market-leadership claim.

## Finding

Graph-based explanations, deterministic decisions, persistent Relate
stores, read-only MCP, and browser WebAssembly are already used by other
projects. Common Cause should lead with its concrete diagnostic question:
**several sensors fail across different buses; which shared power component
explains the failures, and which healthy neighbors rule out the alternatives?**

The useful distinction is the combined workflow: crossed power and data
dependencies, explicit healthy-device contradictions, multiple simultaneous
causes, timed telemetry history, and recorded recovery evidence. This
review did not identify the same CubeSat workflow in the selected sources.
That observation does not establish that no equivalent project exists.

## Closest inspected projects

These descriptions come from the projects' own READMEs. Their code was not
executed for this review; their performance and validation claims remain
self-reported.

| Project and inspected source | What overlaps | Where Common Cause's question differs |
| --- | --- | --- |
| [Interlock Tracer](https://github.com/ali8765-sketch/interlock-tracer/blob/1963a9842c67840f35943828e4187e1588946cb8/README.md) | Offline deterministic explanation of blocked PLC outputs; a Relate logic graph, three-valued evaluation, synthetic snapshots, explicit incompleteness, and optional read-only MCP. | Common Cause infers a shared failed dependency from changing sensor observations across power and buses. Its input is a telemetry stream rather than a Structured Text logic program and input snapshot. |
| [Relate Bug Finder](https://github.com/IoakeimKyrgiafinis/RelateBugFinder/blob/06ab62a33de4979cf97b2267665434de4c64e10b/README.md) | Explainable suspect rankings from a code graph and recorded executions; related passing tests provide negative evidence; read-only Cypher and MCP. | Common Cause's candidates are devices, supplies, buses, and drivers. Healthy-device contradiction is the corresponding domain-specific evidence, so negative evidence itself should not be presented as unprecedented. |
| [Blind Flange](https://github.com/loksai-codes/blind-flange/blob/2cc6a4a4c4a5b0063980965004bd6817b1a3fed4/README.md) | A physical dependency graph, deterministic decisions, explicit unknown states, recorded evidence, a simple baseline, and an independent traversal oracle. | It evaluates conflicts between work permits through observed piping barriers. Common Cause diagnoses changing failures and records fault episodes and recovery. Neither prototype establishes certified equipment safety. |
| [Yokoten Graph](https://github.com/Onlyaguest/yokoten-graph/blob/b0c314a2b64144b5b62f111293f899ac95fa938a/README.md) | Manufacturing failure modes, root-cause mechanisms, proven actions, persistent evidence, MCP, and a no-install Relate WASM demo. | It retrieves prior quality cases and missed deployment of fixes. Common Cause computes a current suspect set from sampled faults and healthy components. |
| [Chokepoint Lab](https://github.com/GGGODLIN/relate-chokepoint-lab/blob/139c1968ac4e7f34fee0193938e77026f56c1ce3/README.md) | Interactive disruption scenarios, multi-hop impact, browser WASM, a native inspectable store, MCP, and native/browser parity checks. | Its graph models route reachability after maritime closures. Common Cause's graph explains observed component failures; a browser graph and an MCP surface alone are supporting implementation choices. |
| [RootCause](https://github.com/rootcause-1/rootcause/blob/2a3bac1e20b895eaa9a4080632f957cf2876ae34/README.md) | Graph-based incident diagnosis, evidence paths, MCP tools, action history, and recovery verification. | This adjacent project uses FalkorDB and OpenTelemetry software-service incidents and identifies a different hackathon. Common Cause uses embedded Relate and simulated embedded-system telemetry. Recovery verification is valuable, but is not a new category by itself. |

The [graph-on-a-microcontroller idea](https://github.com/jexp/relate-ideas/blob/280c2cb7974db163511a75778353e13beed9b55b/Project/graph-on-a-microcontroller.md)
is a proposal for a port and measured device footprint. It should not be
counted as an inspected implementation or as evidence that Common Cause
runs on a microcontroller.

## Positioning and first-time experience

- Start with the observable problem: three silent sensors are three symptoms,
  and they can share one failed supply. Use the wiring and healthy neighbors
  to explain why the bus is a weaker candidate.
- Give a visitor one guided fault story before exposing identifiers,
  evidence tables, Cypher, or live-server configuration. Keep those available
  for inspection after the result makes sense.
- Show that the same reasoning handles two causes and a second topology.
  These are concrete extensions of the first example, rather than a list of
  database capabilities.
- Label the measurements precisely. The [36-injection bundle](virtual-matrix.md)
  is four repetitions of nine modeled virtual faults. It demonstrates that
  workflow, not accuracy on arbitrary spacecraft or electrical failures.
- Describe the [recovery controller](virtual-recovery.md) as simulated policy,
  action, and fresh-telemetry verification. Physical bus recovery and flight
  validation remain outside scope.

## Search coverage and limits

GitHub's public repository search for
[`topic:relate-neo4j-hackathon`](https://github.com/search?q=topic%3Arelate-neo4j-hackathon&type=repositories)
returned 100 entries on the first page and 22 on the second at review time.
This is topic membership, not a verified count of eligible submissions.
The broader [`relate` topic](https://github.com/topics/relate), searches for
`fault`, `telemetry`, and `satellite` in repository names, descriptions, and
READMEs, and public web searches were used to select nearby examples.

The comparison above focuses on inspected primary READMEs. Private work,
unpublished entries, missing topic tags, search-index lag, and unreviewed
repositories limit recall. Some GitHub pages were unavailable through web
search; their READMEs and source revisions were read through the GitHub
connector instead. No competing application was installed or benchmarked,
and test counts or accuracy figures across different workloads are not
treated as a head-to-head comparison. No new feature is required solely
to match this list.
