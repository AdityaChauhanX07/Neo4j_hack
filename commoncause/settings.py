import os
from dataclasses import dataclass
from hashlib import sha256
from math import isfinite
from pathlib import Path

import yaml

from .schema import read_asset


@dataclass(frozen=True)
class Detection:
    stuck_samples: int
    stale_periods: int
    heartbeat_timeout_ms: int
    undervoltage_ratio: float
    settle_ms: int
    recovery_samples: int
    ok_interval_ms: int


def parse_detection(text):
    try:
        rules = Detection(**yaml.safe_load(text))
    except (TypeError, yaml.YAMLError) as error:
        raise ValueError("Detection config needs the seven documented thresholds") from error
    for name in ("stuck_samples", "stale_periods", "heartbeat_timeout_ms",
                 "settle_ms", "recovery_samples", "ok_interval_ms"):
        value = getattr(rules, name)
        if type(value) is not int or value <= 0:
            raise ValueError(f"{name} must be a positive integer")
    ratio = rules.undervoltage_ratio
    if type(ratio) not in (int, float) or not isfinite(ratio) or not 0 < ratio <= 1:
        raise ValueError("undervoltage_ratio must be greater than zero and at most one")
    return rules


config_path = os.environ.get("COMMONCAUSE_DETECTION_CONFIG")
DETECTION_TEXT = Path(config_path).read_text(encoding="utf-8") if config_path else read_asset("config", "detection.yaml")
DETECTION = parse_detection(DETECTION_TEXT)
DETECTION_SHA = sha256(DETECTION_TEXT.encode("utf-8")).hexdigest()
