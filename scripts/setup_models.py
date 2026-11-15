"""Explicit online bootstrap only. Runtime modules never download models."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import platform
import tarfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
REV = "6ab461498e2023f6e3c1baea90a8f0fe38ab64d0"
ASR_REV = "ad658fa0201659a09ea3c176129a191c77ecae8f"
ASR_BASE = f"https://huggingface.co/csukuangfj/sherpa-onnx-streaming-zipformer-zh-int8-2025-06-30/resolve/{ASR_REV}"
HF_BASE = f"https://huggingface.co/unsloth/Qwen3.5-0.8B-GGUF/resolve/{REV}"
ITEMS = [
    ("models/vlm/Qwen3.5-0.8B-Q4_K_M.gguf", HF_BASE + "/Qwen3.5-0.8B-Q4_K_M.gguf", "bd258782e35f7f458f8aced1adc053e6e92e89bc735ba3be89d38a06121dc517"),
    ("models/vlm/mmproj-F16.gguf", HF_BASE + "/mmproj-F16.gguf", "56e4c6cfe73b0c82e3e82bc518d7591997e61d81f723fc41a586f4fa69ea2453"),
    ("models/asr/encoder.int8.onnx", ASR_BASE + "/encoder.int8.onnx", "5ac51e27981bb4dab01bb9be4958453ba50c3b61c063ddda0eab23fd3671aa4f"),
    ("models/asr/decoder.onnx", ASR_BASE + "/decoder.onnx", "06522ad63cec0fdf6809f4e1db9bb4f7d710c34582e3b35db62ac60eccafac7e"),
    ("models/asr/joiner.int8.onnx", ASR_BASE + "/joiner.int8.onnx", "b34584dc6f561089e1d747fedebb3765f2caa72c927ef54d7ca55e5ae40a814b"),
    ("models/asr/tokens.txt", ASR_BASE + "/tokens.txt", None),
    ("models/asr/test_wavs/0.wav", "https://huggingface.co/csukuangfj/sherpa-onnx-streaming-zipformer-zh-14M-2023-02-23/resolve/204ad334e2e683fd295359930cc16fc0432a23ac/test_wavs/0.wav", None),
    ("models/face/yunet.onnx", "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx", None),
    ("models/face/sface.onnx", "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx", None),
    ("models/downloads/buffalo_sc.zip", "https://github.com/deepinsight/insightface/releases/download/model-zoo/buffalo_sc.zip", "57d31b56b6ffa911c8a73cfc1707c73cab76efe7f13b675a05223bf42de47c72"),
    ("models/detector/yolo11n.pt", "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt", None),
    ("models/downloads/tts.tar.bz2", "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/sherpa-onnx-vits-zh-ll.tar.bz2", None),
    ("data/fixtures/bus.jpg", "https://raw.githubusercontent.com/ultralytics/ultralytics/main/ultralytics/assets/bus.jpg", None),
    ("data/fixtures/lena.jpg", "https://raw.githubusercontent.com/opencv/opencv/master/samples/data/lena.jpg", None),
]


def sha256(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def download(item):
    name, url, expected = item
    path = ROOT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    # A non-LFS file can change between model revisions: force its new source
    # when the previous manifest says it came from a different URL.
    old_manifest = ROOT / "models/manifest.json"
    old_records = json.loads(old_manifest.read_text(encoding="utf-8")) if old_manifest.is_file() else []
    previous = next((r for r in old_records if r["path"] == name), None)
    source_unchanged = previous is None or previous["url"] == url
    pinned_hash = expected or (previous["sha256"] if previous and source_unchanged else None)
    if path.exists() and source_unchanged and pinned_hash and sha256(path) == pinned_hash:
        print(f"Verified existing: {name}", flush=True)
    else:
        print(f"Downloading: {name}", flush=True)
        request = urllib.request.Request(url, headers={"User-Agent": "SmartGlasses-local-setup"})
        partial = path.with_suffix(path.suffix + ".part")
        with urllib.request.urlopen(request, timeout=120) as response, partial.open("wb") as out:
            expected_size = response.headers.get("Content-Length")
            while block := response.read(1024 * 1024):
                out.write(block)
        if expected_size and partial.stat().st_size != int(expected_size):
            raise RuntimeError(f"Incomplete download: {name}")
        if pinned_hash and sha256(partial) != pinned_hash:
            raise RuntimeError(f"SHA-256 mismatch: {name}")
        partial.replace(path)
        print(f"Downloaded: {name} ({path.stat().st_size / 1024**2:.1f} MiB)", flush=True)
    return {"path": name, "url": url, "bytes": path.stat().st_size, "sha256": sha256(path), "upstream_sha256_verified": expected is not None}


def main():
    if (ROOT / "runtime/processes.json").exists():
        raise RuntimeError("Stop the project's services before replacing model/runtime files (Stop-Glasses.ps1 or scripts/run.py stop)")
    items = list(ITEMS)
    if platform.system() == "Windows":
        asset = "llama-b12110-bin-win-cpu-x64.zip"
    elif platform.system() == "Linux" and platform.machine() in {"aarch64", "arm64"}:
        asset = "llama-b12110-bin-ubuntu-arm64.tar.gz"
    else:
        raise RuntimeError("Supported deployment hosts: Windows x64 and Linux ARM64")
    items.append((f"runtime/{asset}", f"https://github.com/ggml-org/llama.cpp/releases/download/b12110/{asset}", None))
    with ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(download, items))
    with tarfile.open(ROOT / "models/downloads/tts.tar.bz2") as archive:
        archive.extractall(ROOT / "models/tts", filter="data")
    recognition = ROOT / "models/face/arcface_mbf.onnx"
    with zipfile.ZipFile(ROOT / "models/downloads/buffalo_sc.zip") as archive:
        members = [name for name in archive.namelist() if name.rsplit("/",1)[-1] == "w600k_mbf.onnx"]
        if len(members) != 1:
            raise RuntimeError("Expected one ArcFace MobileFaceNet recognition model")
        recognition.write_bytes(archive.read(members[0]))
    recognition_digest = "9cc6e4a75f0e2bf0b1aed94578f144d15175f357bdc05e815e5c4a02b319eb4f"
    if sha256(recognition) != recognition_digest:
        raise RuntimeError("Selected face recognition model checksum mismatch")
    (ROOT / "models/face/recognition.json").write_text(json.dumps({"model": "ArcFace MobileFaceNet WebFace600K", "dimension": 512, "sha256": recognition_digest, "archive_sha256": "57d31b56b6ffa911c8a73cfc1707c73cab76efe7f13b675a05223bf42de47c72", "license": "Non-commercial research, InsightFace model-zoo"}, indent=2), encoding="utf-8")
    target = (ROOT / "runtime/llama").resolve()
    target.mkdir(exist_ok=True)
    if asset.endswith(".zip"):
        with zipfile.ZipFile(ROOT / "runtime" / asset) as archive:
            for entry in archive.namelist():
                if not (target / entry).resolve().is_relative_to(target):
                    raise RuntimeError("Unsafe archive path")
            archive.extractall(target)
    else:
        with tarfile.open(ROOT / "runtime" / asset) as archive:
            archive.extractall(target, filter="data")
    (ROOT / "models/manifest.json").write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Model bootstrap complete. Export detector separately before running.", flush=True)


if __name__ == "__main__":
    main()
