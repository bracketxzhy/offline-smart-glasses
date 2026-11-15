"""Build a local private ARM64 bundle; never uploads or edits the source DB."""
from contextlib import closing
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tarfile
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
EXPORTS = ROOT / "exports"


def main():
    EXPORTS.mkdir(exist_ok=True)
    selected = {}
    def add(path, destination=None):
        selected[destination or path.relative_to(ROOT).as_posix()] = path
    for folder in ["glasses","scripts","tests","docs"]:
        for path in (ROOT/folder).rglob("*"):
            if path.is_file() and path.suffix in {".py",".html",".sh",".ps1",".md"} and "__pycache__" not in path.parts:
                add(path)
    for name in ["config.app.json","requirements-runtime.txt","README-AI.md","Start-Glasses.ps1","Stop-Glasses.ps1"]:
        add(ROOT/name)
    for name in ["models/vlm/Qwen3.5-0.8B-Q4_K_M.gguf","models/vlm/mmproj-F16.gguf","models/detector/yolo11n.onnx","models/detector/export.json","models/face/yunet.onnx","models/face/arcface_mbf.onnx","models/face/recognition.json","models/asr/encoder.int8.onnx","models/asr/decoder.onnx","models/asr/joiner.int8.onnx","models/asr/tokens.txt"]:
        add(ROOT/name)
    for folder in ["models/tts/sherpa-onnx-vits-zh-ll","database/images","data/audio-cache","data/fixtures"]:
        for path in (ROOT/folder).rglob("*"):
            if path.is_file() and not path.name.endswith(".part"):
                add(path)
    for path in (ROOT/"runtime/pi-wheelhouse").glob("*.whl"):
        add(path,"wheelhouse/linux-aarch64-cp313/"+path.name)
    for path in (ROOT/"runtime/pi-llama").rglob("*"):
        if path.is_file():
            add(path,"runtime/llama/"+path.relative_to(ROOT/"runtime/pi-llama").as_posix())
    firmware = ROOT / "hardware/xiao-esp32s3"
    for path in (firmware/"SmartGlassesCapture").glob("*"):
        if path.suffix in {".ino",".h"}:
            add(path)
    for path in (firmware/"build-stream").glob("*.bin"):
        if "merged" not in path.name:
            add(path,"hardware/xiao-esp32s3/firmware/"+path.name)
    with tempfile.TemporaryDirectory(prefix="pi-release-",dir=EXPORTS) as tmp:
        database = Path(tmp)/"smart_glasses.db"
        source = (ROOT/"database/smart_glasses.db").resolve()
        with closing(sqlite3.connect(source.as_uri()+"?mode=ro",uri=True)) as src, closing(sqlite3.connect(database)) as dst:
            src.backup(dst)
        add(database,"database/smart_glasses.db")
        manifest=[]
        for name,path in sorted(selected.items()):
            with path.open("rb") as f:
                digest=hashlib.file_digest(f,"sha256").hexdigest()
            manifest.append({"path":name,"bytes":path.stat().st_size,"sha256":digest})
        metadata={"built_at":time.time(),"target":"Raspberry Pi 5 8GB / Linux ARM64 / CPython3.13","contains_private_database_and_portraits":True,"source_database_modified":False,"files":manifest}
        archive=EXPORTS/"smart-glasses-pi5-offline-20261107.tar.gz"
        partial=archive.with_suffix(".gz.part")
        with tarfile.open(partial,"w:gz",compresslevel=1,format=tarfile.PAX_FORMAT) as tar:
            for index,item in enumerate(manifest):
                path=selected[item["path"]]
                info=tarfile.TarInfo("smart-glasses/"+item["path"])
                info.size=item["bytes"];info.mode=0o755 if item["path"].startswith("runtime/llama/") or path.suffix==".sh" else 0o644
                with path.open("rb") as source_file:
                    tar.addfile(info,source_file)
                if (index+1)%50==0:print(f"Bundled {index+1}/{len(manifest)} files",flush=True)
            raw=json.dumps(metadata,ensure_ascii=False,indent=2).encode()
            info=tarfile.TarInfo("smart-glasses/release-manifest.json");info.size=len(raw);info.mode=0o644
            tar.addfile(info,io.BytesIO(raw))
        partial.replace(archive)
        with archive.open("rb") as f:
            digest=hashlib.file_digest(f,"sha256").hexdigest()
        (EXPORTS/"release-build.json").write_text(json.dumps({"archive":archive.name,"bytes":archive.stat().st_size,"sha256":digest,"files":len(manifest),"target":metadata["target"],"contains_private_database_and_portraits":True},indent=2),encoding="utf-8")
        print(f"Built {archive.name}: {archive.stat().st_size/1024**2:.1f} MiB; SHA256 {digest}",flush=True)


if __name__ == "__main__":
    main()
