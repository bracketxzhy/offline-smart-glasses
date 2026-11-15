"""Capture real JPEG frames from the board and verify complete image decoding."""
import io
import json
import sys
import time
from pathlib import Path

import serial
from PIL import Image, ImageStat


def verify(port, folder):
    folder.mkdir(parents=True, exist_ok=True)
    with serial.Serial(port, 115200, timeout=8) as connection:
        time.sleep(0.5)
        connection.reset_input_buffer()
        connection.write(b"status\n")
        deadline = time.monotonic() + 30
        status = None
        while time.monotonic() < deadline:
            line = connection.readline().decode(errors="replace").strip()
            if line.startswith('{"device":'):
                status = json.loads(line)
                break
        assert status is not None, "No board status received"
        assert status.get("camera_initialized"), f"Camera is not initialized: {status}"
        assert status.get("camera_error") == 0, f"Camera reports a driver error: {status}"
        if status.get("camera_model") == "OV5640":
            assert status.get("camera_autofocus_ready"), f"OV5640 autofocus is not initialized: {status}"
            assert status.get("camera_autofocus_error") == 0, f"Autofocus reports an error: {status}"
            assert status.get("camera_focus_status") != 255, "Autofocus status register could not be read"
        frames = []
        for index in range(3):
            connection.write(b"capture\n")
            deadline = time.monotonic() + 15
            length = None
            while time.monotonic() < deadline:
                line = connection.readline().decode(errors="replace").strip()
                if line.startswith("ERROR"):
                    raise AssertionError(line)
                if line.startswith("JPEG "):
                    length = int(line.split()[1])
                    break
            assert length is not None, "No JPEG frame header received"
            assert 100 < length < 2_000_000, f"Unexpected frame length: {length}"
            data = connection.read(length)
            assert len(data) == length, f"Truncated transfer: {len(data)}/{length} bytes"
            assert connection.readline().strip() == b"", "Unexpected JPEG terminator"
            assert connection.readline().strip() == b"JPEG_END", "JPEG_END marker missing"
            path = folder / f"camera-{index + 1}.jpg"
            path.write_bytes(data)
            with Image.open(io.BytesIO(data)) as image:
                assert image.format == "JPEG", "Captured data is not JPEG"
                image.load()
                assert image.size == (640, 480), f"Unexpected dimensions: {image.size}"
                stats = ImageStat.Stat(image.convert("RGB"))
                frames.append({"file": str(path.resolve()), "bytes": length,
                               "width": image.width, "height": image.height,
                               "mean_rgb": stats.mean, "stddev_rgb": stats.stddev,
                               "decoded": True})
            time.sleep(0.5)
    return {"passed": True, "status": status, "frames": frames}


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "logs" / "camera"
    try:
        report = verify("COM3", target)
    except Exception as exc:
        report = {"passed": False, "error": f"{type(exc).__name__}: {exc}"}
    target.mkdir(parents=True, exist_ok=True)
    output = json.dumps(report, ensure_ascii=False, indent=2)
    (target / "verification.json").write_text(output + "\n", encoding="utf-8")
    print(output)
    sys.exit(0 if report["passed"] else 1)
