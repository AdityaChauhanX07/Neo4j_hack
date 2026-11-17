import subprocess
import sys
from pathlib import Path

from commoncause.matrix import matrix

ROOT = Path(__file__).resolve().parents[1]


def test_second_topology_uses_the_same_diagnosis(tmp_path):
    recording = tmp_path / "quad.jsonl"
    with recording.open("w") as feed:
        subprocess.run([sys.executable, ROOT / "sim" / "quad.py"], stdout=feed, check=True)

    scored = matrix(recording, ROOT / "topologies" / "quadcopter.yaml")
    assert [row["ranked"] for row in scored] == [["BEC_5V"], ["I2C-FC"], ["esc.3"]]
