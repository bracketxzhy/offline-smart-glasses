"""Simulate workloads using an architecture benchmark's measured path medians."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from glasses.simulation import simulate

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("measurements", type=Path)
    parser.add_argument("--object", type=float, default=.4)
    parser.add_argument("--face", type=float, default=.25)
    parser.add_argument("--profile", type=float, default=.25)
    parser.add_argument("--complex", type=float, default=.1)
    parser.add_argument("--output", type=Path, default=ROOT / "logs/pipeline-simulation.json")
    args = parser.parse_args()
    report = json.loads(args.measurements.read_text(encoding="utf-8"))
    workload = {key: getattr(args,key) for key in ["object","face","profile","complex"]}
    results = {name: simulate(workload, paths) for name, paths in report["measured_paths"].items()}
    output = {"scope": report["scope"], "workload": workload, "architectures": results, "energy_note": "No energy is inferred from CPU/TDP; requires an external power measurement"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output,indent=2,ensure_ascii=False),encoding="utf-8")
    print(json.dumps(output,indent=2,ensure_ascii=False))
