# Reading and downlinking during capture

One process owns the writable directory store. Its sampler threads and
diagnosis engine share that connection. Readers must use a read-only
handle; opening the same directory as a second writer is unsupported.

To inspect new commits from another process, use the CLI's live freshness
mode against the directory:

```sh
relate --database board/virtual-live/store --read-only=live \
  'MATCH (e:Event) RETURN count(e) AS events'
```

A long-lived MCP reader can follow the same store:

```sh
relate serve --database board/virtual-live/store --mcp stdio --read-only=live
```

That command is for an MCP host to launch over stdio. The default
`.mcp.json` instead reads the committed, completed `.rl` fixture with
ordinary snapshot freshness. Live freshness applies to a directory, not
a `.rl` bundle.

While capture is active, a second terminal can create a downlink:

```sh
commoncause downlink --db board/virtual-live/store --out board/live-downlink
```

The resulting `.rl` and JSON describe one frozen snapshot. They keep that
content when later readings arrive at the writer. Repeat downlink when a
new snapshot is needed. A capture's Run is marked complete only when the
writer finishes it; a mid-capture snapshot can therefore have no completion
flag yet.

## Reproduce the concurrent check

With the Relate CLI installed:

```sh
python -m pytest -q tests/test_live_store.py
```

The check starts a five-second virtual recorder in one process and a
read-only live MCP follower in another. After observing committed events,
it clones and exports while the recorder remains active. More events must
then appear through the same follower, and the cloned graph must stay
unchanged after capture finishes. The `.rl` and JSON are also compared.

This passed locally with `relate-db==1.0.1` and Relate CLI 1.3.0 on x64
Linux. Ground-view CI runs it alongside the MCP protocol checks. It does
not turn the static browser dashboard into a live network reader.
