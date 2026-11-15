"""Setup-time conversion only; deployment inference does not import PyTorch."""
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["YOLO_CONFIG_DIR"] = str(ROOT / "runtime/ultralytics")
os.environ["YOLO_AUTOINSTALL"] = "false"
os.environ["YOLO_OFFLINE"] = "true"

from ultralytics import YOLO

if __name__ == "__main__":
    source = ROOT / "models/detector/yolo11n.pt"
    if not source.is_file():
        raise FileNotFoundError(source)
    output = Path(YOLO(source).export(format="onnx", imgsz=320, opset=17, simplify=False, dynamic=False, device="cpu"))
    record = {"path": str(output.relative_to(ROOT)), "sha256": hashlib.file_digest(output.open("rb"), "sha256").hexdigest(), "input_size": 320, "format": "ONNX", "source": "ultralytics/assets v8.3.0 yolo11n.pt", "license": "AGPL-3.0 (Ultralytics)"}
    (ROOT / "models/detector/export.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
