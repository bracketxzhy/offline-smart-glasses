"""Start/stop only this project's processes. No autostart or global services."""
import argparse
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

import psutil

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "runtime/processes.json"
STOP = ROOT / "runtime/stop-requested"


def available(port):
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def wait_http(url, process, seconds=120):
    deadline = time.monotonic() + seconds
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Service exited ({process.returncode}); see logs")
        try:
            with opener.open(url, timeout=2) as r:
                if r.status == 200:
                    return
        except Exception:
            pass
        time.sleep(.5)
    raise RuntimeError(f"Timed out waiting for {url}; see logs")


def serve():
    if not available(8081) or not available(8765):
        raise RuntimeError("Ports 8081/8765 are in use; refusing to reuse an unknown service")
    STOP.unlink(missing_ok=True)
    (ROOT / "logs").mkdir(exist_ok=True)
    config = json.loads((ROOT / "config.app.json").read_text(encoding="utf-8"))
    name = "llama-server.exe" if sys.platform == "win32" else "llama-server"
    candidates = list((ROOT / "runtime/llama").rglob(name))
    if len(candidates) != 1:
        raise FileNotFoundError("Run model bootstrap; expected one llama-server executable")
    command = [str(candidates[0]), "-m", str(ROOT / "models/vlm/Qwen3.5-0.8B-Q4_K_M.gguf"), "--mmproj", str(ROOT / "models/vlm/mmproj-F16.gguf"), "--host", "127.0.0.1", "--port", "8081", "-c", "2048", "-np", "1", "-t", "4", "-tb", "4", "-ngl", "0", "--no-mmproj-offload", "--image-min-tokens", "64", "--image-max-tokens", "256", "--reasoning", "off", "--jinja", "--cors-origins", "http://127.0.0.1:8765,http://localhost:8765", "--no-webui"]
    processes = []
    app = None
    try:
        with (ROOT / "logs/vlm-server.log").open("w", encoding="utf-8") as vlm_log, (ROOT / "logs/app-server.log").open("w", encoding="utf-8") as app_log:
            kwargs = {"cwd": ROOT, "stdin": subprocess.DEVNULL}
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            vlm = subprocess.Popen(command, stdout=vlm_log, stderr=subprocess.STDOUT, **kwargs)
            processes.append(vlm)
            wait_http("http://127.0.0.1:8081/health", vlm)
            app = subprocess.Popen([sys.executable, "-m", "uvicorn", "glasses.web:app", "--host", "127.0.0.1", "--port", "8765", "--no-access-log"], stdout=app_log, stderr=subprocess.STDOUT, **kwargs)
            processes.append(app)
            wait_http("http://127.0.0.1:8765/api/status", app)
            controller = psutil.Process()
            STATE.write_text(json.dumps({"controller_pid": controller.pid, "created": controller.create_time(), "vlm_pid": vlm.pid, "app_pid": app.pid, "url": "http://127.0.0.1:8765"}, indent=2), encoding="utf-8")
            print("Ready: http://127.0.0.1:8765", flush=True)
            while not STOP.exists():
                if any(p.poll() is not None for p in processes):
                    raise RuntimeError("A model/application process stopped; inspect logs")
                time.sleep(.5)
    finally:
        if app is not None and app.poll() is None:
            try:
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                request = urllib.request.Request("http://127.0.0.1:8765/api/camera", data=b'{"enabled":false}', headers={"Content-Type": "application/json"})
                with opener.open(request, timeout=5):
                    pass
            except Exception:
                pass  # The app can be unavailable during a failed startup.
        for process in reversed(processes):
            if process.poll() is None:
                # Windows venv redirectors may own the actual Python worker.
                try:
                    children = psutil.Process(process.pid).children(recursive=True)
                except psutil.NoSuchProcess:
                    children = []
                for child in reversed(children):
                    try:
                        child.terminate()
                    except psutil.NoSuchProcess:
                        pass
                process.terminate()
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    process.kill()
        STATE.unlink(missing_ok=True)
        STOP.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["start", "serve", "stop", "status"])
    action = parser.parse_args().action
    if action == "serve":
        serve()
    elif action == "start":
        if not available(8765) or not available(8081):
            raise RuntimeError("A service already occupies the project ports; inspect status")
        (ROOT / "logs").mkdir(exist_ok=True)
        kwargs = {"cwd": ROOT, "stdin": subprocess.DEVNULL}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
        else:
            kwargs["start_new_session"] = True
        with (ROOT / "logs/launcher.log").open("w", encoding="utf-8") as out:
            child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "serve"], stdout=out, stderr=subprocess.STDOUT, **kwargs)
        print(f"Starting (controller PID {child.pid}); check logs/launcher.log or status")
    elif action == "status":
        print(STATE.read_text(encoding="utf-8") if STATE.exists() else "Not running or still starting; inspect logs/launcher.log")
    else:
        if not STATE.exists():
            raise RuntimeError("No active controller state; inspect logs before stopping anything")
        state = json.loads(STATE.read_text(encoding="utf-8"))
        process = psutil.Process(state["controller_pid"])
        if abs(process.create_time() - state["created"]) > .01 or str(Path(__file__).resolve()) not in process.cmdline() or "serve" not in process.cmdline():
            raise RuntimeError("Controller identity mismatch; refusing to signal an unrelated process")
        STOP.touch()
        print("Stop requested for this project's services")


if __name__ == "__main__":
    main()
