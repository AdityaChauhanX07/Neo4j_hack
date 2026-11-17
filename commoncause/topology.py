from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Optional

import yaml

from .schema import install_schema, merge_links, merge_nodes, read_asset, transaction

PARTS = {
    "rails": "PowerRail",
    "regulators": "Regulator",
    "buses": "Bus",
    "devices": "Device",
}
DEPENDENCIES = {"PowerRail", "Regulator", "Bus", "Device", "Driver"}


@dataclass(frozen=True)
class Channel:
    id: str
    device: str
    period_ms: int
    minimum: Optional[float]
    maximum: Optional[float]
    noisy: bool
    heartbeat: bool
    monitor: Optional[str]
    nominal: Optional[float]
    bus: Optional[str]
    driver: Optional[str]


def load_topology(db, path):
    raw = Path(path).read_bytes()
    digest = sha256(raw).hexdigest()
    topology = yaml.safe_load(raw)
    nodes, links = _wiring(topology)
    catalogue = yaml.safe_load(read_asset("catalog", "failure-modes.yaml"))

    install_schema(db)
    with transaction(db):
        existing = db.execute("MATCH (t:Topology) RETURN t.sha AS sha").fetchone()
        if existing:
            if existing["sha"] != digest:
                raise ValueError("Store already contains a different topology")
            return
        for label, rows in nodes.items():
            merge_nodes(db, label, rows)
        for (source, relationship, target), pairs in links.items():
            merge_links(db, source, relationship, target, pairs)
        _load_catalogue(db, catalogue, nodes)
        merge_nodes(db, "Topology", [{"id": topology["system"], "sha": digest}])


def _wiring(topology):
    if not isinstance(topology, dict) or not topology.get("system"):
        raise ValueError("Topology needs a system name")
    nodes = defaultdict(list)
    links = defaultdict(list)
    labels = {}

    def add(label, props):
        part = props.get("id")
        if not isinstance(part, str) or not part:
            raise ValueError(f"{label} needs a nonempty string id")
        if part in labels:
            raise ValueError(f"Duplicate topology id {part}")
        labels[part] = label
        nodes[label].append(props)

    def link(source, rel, target, allowed):
        label = labels.get(target)
        if label not in allowed:
            raise ValueError(f"{source} has invalid {rel} target {target}")
        links[(labels[source], rel, label)].append([source, target])

    wiring_keys = {"fed_by", "powered_by", "bus", "channels", "driver"}
    for group, label in PARTS.items():
        for item in topology.get(group, []):
            add(label, {key: value for key, value in item.items() if key not in wiring_keys})

    for regulator in topology.get("regulators", []):
        link(regulator["id"], "FED_BY", regulator.get("fed_by"), {"PowerRail"})

    for device in topology.get("devices", []):
        device_id = device["id"]
        if "powered_by" in device:
            link(device_id, "POWERED_BY", device["powered_by"], {"PowerRail", "Regulator"})
        if "bus" in device:
            link(device_id, "ON_BUS", device["bus"], {"Bus"})
        if "driver" in device:
            driver = device["driver"]
            add("Driver", driver)
            link(driver["id"], "CONTROLS", device_id, {"Device"})
        for channel in device.get("channels", []):
            channel_id = channel.get("id")
            _check_channel(channel)
            add("TelemetryChannel", {
                key: value for key, value in channel.items() if key != "monitors"
            })
            link(channel_id, "READS", device_id, {"Device"})
            if "monitors" in channel:
                link(channel_id, "MONITORS", channel["monitors"], {"Regulator"})
    return nodes, links


def _check_channel(channel):
    period = channel.get("period_ms")
    if type(period) is not int or period <= 0:
        raise ValueError(f"{channel.get('id')} needs a positive period_ms")
    low, high = channel.get("min"), channel.get("max")
    if low is not None and high is not None and low > high:
        raise ValueError(f"{channel.get('id')} has min above max")


def _load_catalogue(db, catalogue, nodes):
    merge_nodes(db, "Symptom", [
        {"code": code, "description": description}
        for code, description in catalogue["symptoms"].items()
    ])
    for entry in catalogue["failure_modes"]:
        mode = entry["id"]
        recovery = entry["recovery"]
        label = entry["applies_to"]
        merge_nodes(db, "FailureMode", [{
            "id": mode, "name": entry["name"], "applies_to": label,
        }])
        merge_nodes(db, "RecoveryProcedure", [recovery])
        merge_links(db, "FailureMode", "PRODUCES", "Symptom", [
            [mode, symptom] for symptom in entry["symptoms"]
        ])
        merge_links(db, "FailureMode", "RECOVERED_BY", "RecoveryProcedure", [
            [mode, recovery["id"]]
        ])
        merge_links(db, "FailureMode", "APPLIES_TO", label, [
            [mode, part["id"]] for part in nodes.get(label, [])
            if "bus_kind" not in entry or part.get("kind") == entry["bus_kind"]
        ])


def read_channels(db):
    rows = db.execute("""
        MATCH (ch:TelemetryChannel)-[:READS]->(d:Device)
        OPTIONAL MATCH (ch)-[:MONITORS]->(r:Regulator)
        OPTIONAL MATCH (d)-[:ON_BUS]->(b:Bus)
        OPTIONAL MATCH (driver:Driver)-[:CONTROLS]->(d)
        RETURN ch.id AS id, d.id AS device, ch.period_ms AS period_ms,
               ch.min AS minimum, ch.max AS maximum, coalesce(ch.noisy, false) AS noisy,
               coalesce(ch.heartbeat, false) AS heartbeat, r.id AS monitor,
               r.vout AS nominal, b.id AS bus, driver.id AS driver
    """).fetchall()
    return {row["id"]: Channel(**row) for row in rows}
