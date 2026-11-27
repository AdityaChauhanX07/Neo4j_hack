from collections import defaultdict


def reference_rank(topology, events, *, run, start, stop, excluded=()):
    """Set-based specification of ranking, independent of Relate and its loader."""
    kinds = {}
    dependencies = defaultdict(set)
    devices = {part["id"]: part for part in topology["devices"]}
    channels = {}
    monitors = {}
    drivers = {}
    for group, kind in (("rails", "PowerRail"), ("regulators", "Regulator"),
                        ("buses", "Bus"), ("devices", "Device")):
        for part in topology.get(group, []):
            name = part["id"]
            kinds[name] = kind
            dependencies[name].update(part[key] for key in ("fed_by", "powered_by", "bus")
                                      if key in part)
            for channel in part.get("channels", []):
                channels[channel["id"]] = name
                if "monitors" in channel:
                    monitors[channel["id"]] = channel["monitors"]
            if "driver" in part:
                driver = part["driver"]["id"]
                drivers[name] = driver
                kinds[driver] = "Driver"

    ancestors = {}
    for name in devices:
        reached, frontier = {name}, {name}
        for _ in range(4):
            frontier = set().union(*(dependencies[part] for part in frontier)) - reached
            reached.update(frontier)
        ancestors[name] = reached

    observations = defaultdict(list)
    voltage = set()
    for event in events:
        if event["run"] != run or not start <= event["ts"] <= stop:
            continue
        if event.get("diagnostic") is False or (event.get("confirmed_ts") or 0) > stop:
            continue
        observations[channels[event["channel"]]].append(event)
        if event["status"] == "UNDERVOLTAGE" and event["channel"] in monitors:
            voltage.add(monitors[event["channel"]])

    faults = {"NO_RESPONSE", "OUT_OF_RANGE", "STUCK", "STALE", "HEARTBEAT_LOST"}
    failed = {name for name, rows in observations.items()
              if any(row["status"] in faults for row in rows)}
    healthy = {name for name, rows in observations.items() if name not in failed
               and any(row["status"] in {"OK", "UNDERVOLTAGE"} for row in rows)}
    bad = failed - set(excluded)
    coverage = defaultdict(set)
    direct = set(voltage)
    first = {}
    for name in bad:
        rows = observations[name]
        first[name] = min(row["ts"] for row in rows if row["status"] in faults)
        candidates = set(ancestors[name])
        if name in drivers and any(row["status"] == "STALE" for row in rows):
            candidates.add(drivers[name])
            direct.add(drivers[name])
        if any(row["status"] == "HEARTBEAT_LOST" for row in rows) and "bus" in devices[name]:
            direct.add(devices[name]["bus"])
        for part in candidates:
            coverage[part].add(name)

    ranked = []
    for part, covered in coverage.items():
        downstream = {name for name in devices if part in ancestors[name] or drivers.get(name) == part}
        contradicted = len(downstream & healthy)
        score = len(covered) ** 2 / (len(bad) * (len(covered) + contradicted))
        order = (-score, part not in direct, len(downstream), min(first[name] for name in covered), part)
        ranked.append((order, {
            "suspect": part, "kind": kinds[part], "covered": len(covered),
            "contradicted": contradicted, "score": score, "covered_devices": sorted(covered),
        }))
    return [row for _, row in sorted(ranked, key=lambda entry: entry[0])]
