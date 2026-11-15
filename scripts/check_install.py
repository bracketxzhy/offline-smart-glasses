"""Read-only model, source/schema and architecture checks; no device activation."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sqlite3
import struct
import sys
from contextlib import closing

ROOT = Path(__file__).resolve().parents[1]
MODEL_FILES = ["models/vlm/Qwen3.5-0.8B-Q4_K_M.gguf","models/vlm/mmproj-F16.gguf","models/detector/yolo11n.onnx","models/face/yunet.onnx","models/face/arcface_mbf.onnx","models/asr/encoder.int8.onnx","models/asr/decoder.onnx","models/asr/joiner.int8.onnx","models/asr/tokens.txt","models/tts/sherpa-onnx-vits-zh-ll/model.onnx","models/tts/sherpa-onnx-vits-zh-ll/tokens.txt","models/tts/sherpa-onnx-vits-zh-ll/lexicon.txt"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--all-files", action="store_true",help="Check the release snapshot, including editable database/config files")
    args = parser.parse_args()
    if sys.version_info < (3,12):
        raise RuntimeError("Python >=3.12 required")
    import cv2,numpy,onnxruntime,sherpa_onnx,sounddevice,soundfile,serial
    for path in MODEL_FILES:
        if not (ROOT / path).is_file():
            raise FileNotFoundError(path)
    release = ROOT / "release-manifest.json"
    checked = 0
    if release.is_file():
        records = json.loads(release.read_text(encoding="utf-8"))["files"]
        for item in records:
            if not args.all_files and not item["path"].startswith(("models/","runtime/llama/","wheelhouse/")):
                continue
            path = ROOT / item["path"]
            with path.open("rb") as f:
                digest = hashlib.file_digest(f,"sha256").hexdigest()
            if digest != item["sha256"]:
                raise RuntimeError("Release file changed: " + item["path"])
            checked += 1
    config = json.loads((ROOT / "config.app.json").read_text(encoding="utf-8"))
    database = ROOT / config["profile_database"]
    with closing(sqlite3.connect(database.as_uri()+"?mode=ro",uri=True)) as conn:
        if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise RuntimeError("SQLite quick_check failed")
        rows = conn.execute("SELECT count(*) FROM Users").fetchone()[0]
        conn.execute("SELECT category,field,value FROM Profile_Facts LIMIT 1")
    if platform.system()=="Linux":
        binaries = list((ROOT / "runtime/llama").rglob("llama-server"))
        if len(binaries)!=1:
            raise RuntimeError("Expected exactly one Linux llama-server")
        header=binaries[0].read_bytes()[:64]
        if header[:4]!=b'\x7fELF' or struct.unpack_from('<H',header,18)[0]!=183:
            raise RuntimeError("Bundled llama-server is not ARM64 ELF")
    print(json.dumps({"python":platform.python_version(),"platform":platform.platform(),"verified_release_files":checked,"models_present":len(MODEL_FILES),"database_rows":rows,"sensor_source":config["sensor_source"],"devices_activated":False},indent=2,ensure_ascii=False))


if __name__ == "__main__":
    main()
