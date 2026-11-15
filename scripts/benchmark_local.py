"""Repeat real local inference; explicitly excludes live ASR/acoustic onset."""
import argparse
import json
from pathlib import Path
import platform
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cv2
import psutil
from glasses.service import Assistant


def summary(values):
    ordered = sorted(values)
    return {"median_ms": statistics.median(values), "p95_ms": ordered[max(0, int(len(ordered)*.95+.999)-1)], "max_ms": max(values), "n": len(values)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--vlm-runs", type=int, default=3)
    args = parser.parse_args()
    if args.runs < 1 or args.vlm_runs < 1:
        parser.error("runs must be positive")
    a = Assistant(ROOT)
    image = cv2.imread(str(ROOT / "data/fixtures/bus.jpg"))
    if image is None:
        raise FileNotFoundError("Bootstrap image fixture")
    results = {"platform": platform.platform(), "processor": platform.processor(), "scope": "Local CPU; repeated identical image query -> text and TTS preparation. Warm prompt/image caches may be reused. Excludes microphone/ASR endpoint and acoustic onset; not cold-start performance or a controlled architecture comparison.", "object": [], "vlm": []}
    try:
        for mode, count in [("adaptive", args.runs), ("vlm_only", args.vlm_runs)]:
            for i in range(count):
                start = time.perf_counter()
                result = a.ask("前面是什么", frame=image, mode=mode, speak=False)
                _, _, tts_metrics = a.speech.synthesize(result["answer"])
                record = {"answer": result["answer"], "timings": result["timings"], "tts": tts_metrics, "query_to_prepared_audio_ms": (time.perf_counter()-start)*1000}
                results["object" if mode == "adaptive" else "vlm"].append(record)
                print(f"{mode} {i+1}/{count}: {record['query_to_prepared_audio_ms']:.1f} ms", flush=True)
        results["object_summary"] = summary([x["query_to_prepared_audio_ms"] for x in results["object"]])
        results["vlm_summary"] = summary([x["query_to_prepared_audio_ms"] for x in results["vlm"]])
        results["python_rss_mib"] = psutil.Process().memory_info().rss/1024**2
        state = ROOT / "runtime/processes.json"
        if state.exists():
            process = psutil.Process(json.loads(state.read_text())["vlm_pid"])
            results["vlm_server_rss_mib"] = process.memory_info().rss/1024**2
        target = ROOT / "logs/benchmark-local.json"
        target.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({k:v for k,v in results.items() if k.endswith("summary") or k.endswith("rss_mib")},indent=2), flush=True)
    finally:
        a.close()


if __name__ == "__main__":
    main()
