# Live browser view

The ground view can query a running Relate directory store without waiting
for a downlink export. It uses Relate's authenticated HTTP Query API, keeps
the browser's existing wiring and diagnosis views, and polls once a second
after each refresh finishes. The frozen WASM examples still work offline.

## Run on a laptop

Install the Python project and the [Relate CLI](https://relatedb.ai/docs/get-started/install/).
In the first terminal, start a virtual capture:

```bash
commoncause run --virtual-bench --interactive --run live-demo --db board/live-store --recording board/live-demo.jsonl
```

After the store exists, start its read-only follower in another terminal:

```bash
relate serve --database board/live-store --read-only=live --http 7474
```

Relate prints a generated credential in `user:token` form. Keep the default
loopback bind. The token is also stored beside the directory; it belongs
to this local server, not a cloud account.

Serve the ground view locally in a third terminal:

```bash
npm --prefix ground ci
npm --prefix ground run dev -- --host 127.0.0.1
```

Open the local URL Vite prints. Choose **Connect live**, use
`http://127.0.0.1:7474` as the server origin, and paste the credential.
The credential field clears after connecting; it is held only in this tab's
connection object, never in the URL or browser storage.

In the capture terminal, enter `F1 inject`, wait for the `REG_B` diagnosis,
then enter `F1 clear` and watch it resolve. `F9 inject` exercises two causes.
Enter `quit` when finished. All of these readings are simulated.

The page shows when it last checked the graph and the newest retained
telemetry timestamp. A connected server can be serving a stopped recorder;
the telemetry timestamp makes that distinction visible. If the server stops,
the last displayed diagnosis remains and the connection status reports the
interruption while polling retries. **Disconnect** returns to the fixture.

**Follow latest episode** starts enabled. Selecting a historical episode
turns it off. The selected part and channel survive background refreshes.
Reconnect after changing topology; wiring is loaded when the connection opens.
The view lists up to 200 episodes and 200 rows per query. The topology import
refuses more than 200 non-event nodes or relationships instead of silently
dropping wiring.

## API and checks

Each request starts a managed transaction with `accessMode: "READ"`, then
closes it with an empty commit. This matters because the auto-commit route
ignores `accessMode`. The server should also be started `--read-only=live`.
An interrupted request can leave a read transaction until Relate's default
60-second idle expiry. There is no public listener, proxy, or added server
dependency in Common Cause.

Relate's [HTTP reference](https://relatedb.ai/docs/reference/server/http/)
documents the request/response format and origin rules. Loopback browser
origins are accepted by default. Use the local ground view for this workflow;
the deployed HTTPS demo remains the portable recorded-session path.

`ground/test/http.test.js` checks the real transport and confirms mutations
are refused even against a disposable writable server. The browser test
keeps a Python writer and read-only HTTP follower running while checking a
healthy graph, F1, recovery, bad credentials, connection loss, and disconnect.
Set `RELATE_CLI` to the CLI path to run these integration checks.
