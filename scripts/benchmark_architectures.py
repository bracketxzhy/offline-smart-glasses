"""Controlled local fixtures for A/B/C modes, with explicit unsupported tasks."""
import argparse
import json
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import cv2
import numpy as np
from glasses.service import Assistant
from glasses.speech import speech_chunks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--output", type=Path, default=ROOT / "logs/architecture-benchmark.json")
    parser.add_argument("--cases", type=Path, default=ROOT / "data/fixtures/architecture-cases.json")
    args = parser.parse_args()
    if not args.cases.is_file():
        parser.error("Prepare a local case list using scripts/architecture-cases.example.json.")
    if args.runs < 1:
        parser.error("--runs must be positive")
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    assistant = Assistant(ROOT)
    records = []
    try:
        # Wait only for our own finite prewarm queue; do not classify warmup as inference.
        deadline = time.monotonic() + 120
        while assistant.prewarmer.pending.unfinished_tasks:
            if time.monotonic() > deadline:
                raise RuntimeError("Profile audio prewarm did not finish")
            time.sleep(.1)
        for mode in ["vlm_only", "modular", "adaptive"]:
            for kind, case_id, image_path, question, expected in cases:
                image = cv2.imdecode(np.fromfile(ROOT / image_path, dtype=np.uint8), cv2.IMREAD_COLOR)
                if image is None:
                    raise FileNotFoundError(image_path)
                for repetition in range(args.runs):
                    entry = {"mode": mode, "query_type": kind, "case": case_id, "repetition": repetition}
                    if (mode == "vlm_only" and kind in {"face","profile"}) or (mode == "modular" and kind == "complex"):
                        entry.update({"status": "unsupported", "correct": None})
                    else:
                        started = time.perf_counter()
                        result = assistant.ask(question, frame=image, mode=mode, speak=False)
                        chunk = speech_chunks(result["answer"])[0]
                        _, _, audio = assistant.speech.synthesize(chunk)
                        if kind == "face":
                            identity = result["details"]["identity"]
                            correct = identity["status"] == "unknown" if expected is None else identity.get("person_id") == expected
                        elif kind == "profile":
                            correct = expected in result["answer"] and bool(result["details"].get("evidence"))
                        else:
                            correct = any(word in result["answer"] for word in ["公交", "公共汽车", "巴士", "大巴", "客车"])
                        t = result["timings"]
                        entry.update({"status":"ok", "correct":correct, "answer":result["answer"], "latency_ms":(time.perf_counter()-started)*1000, "stages_ms":{"routing":t["routing_ms"],"capture":t["capture_ms"],"vision_and_lookup":t["vision_and_answer_ms"],"first_audio_prepare":audio["tts_prepare_ms"]}})
                    records.append(entry)
                print(f"{mode}: {case_id} ({args.runs} trials)", flush=True)
        paths, summaries = {}, {}
        for mode in ["vlm_only", "modular", "adaptive"]:
            paths[mode], summaries[mode] = {}, {}
            for kind in ["object", "face", "profile", "complex"]:
                group = [r for r in records if r["mode"] == mode and r["query_type"] == kind]
                valid = [r for r in group if r["status"] == "ok"]
                summary = {"trials":len(group),"supported":len(valid),"correct":sum(r["correct"] for r in valid)}
                if valid:
                    ordered = sorted(r["latency_ms"] for r in valid)
                    summary.update({"median_ms":statistics.median(ordered),"p95_ms":ordered[max(0,int(len(ordered)*.95+.999)-1)],"max_ms":max(ordered),"over_1s":sum(v>1000 for v in ordered)})
                    paths[mode][kind] = {"stages_ms":{stage:statistics.median(r["stages_ms"][stage] for r in valid) for stage in valid[0]["stages_ms"]},"energy_j":None}
                else:
                    paths[mode][kind] = None
                summaries[mode][kind] = summary
        report = {"scope":"Windows/local CPU, predecoded registered/public images, warm models and repeated identical prompts (prefix/image caches may be reused), first TTS chunk prepared; no live ASR, audio device onset, Pi timing, power, or independent face accuracy. Ground truth only for these fixtures.","runs":args.runs,"summaries":summaries,"measured_paths":paths,"records":records}
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
        print(json.dumps(summaries,indent=2,ensure_ascii=False),flush=True)
    finally:
        assistant.close()


if __name__ == "__main__":
    main()
