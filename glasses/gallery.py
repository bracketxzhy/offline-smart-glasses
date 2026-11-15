"""Incremental, local-only portrait import. Source database is never written."""
import hashlib
import json
from pathlib import Path
import threading
import time

import cv2
import numpy as np

from .people import resolve_image_person


class GallerySync:
    EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

    def __init__(self, people, images: Path, faces, *, interval=2., on_people_changed=None):
        self.people, self.images, self.faces = people, Path(images).resolve(), faces
        self.interval, self.on_people_changed = interval, on_people_changed
        self.stop_event = threading.Event()
        self.scan_lock = threading.Lock()
        self.state_lock = threading.Lock()
        self.thread = None
        self._fingerprint = None
        self._db_revision = None
        self._state = {"registered_people": 0, "valid_images": 0, "errors": [], "error": None, "last_sync": None, "users": [], "syncing": False}

    def status(self):
        with self.state_lock:
            return json.loads(json.dumps(self._state, ensure_ascii=False))

    def sync_once(self):
        if not self.scan_lock.acquire(blocking=False):
            return {**self.status(), "syncing": True}
        started = time.perf_counter()
        try:
            with self.state_lock:
                self._state["syncing"] = True
            if not self.images.is_dir():
                raise FileNotFoundError(f"头像目录不存在：{self.images}")
            users = self.people.users()
            previous = self.faces.image_gallery()
            records, errors = [], []
            for path in sorted(self.images.rglob("*")):
                if path.suffix.lower() not in self.EXTENSIONS or not path.is_file():
                    continue
                relative = path.relative_to(self.images).as_posix()
                try:
                    if not path.resolve().is_relative_to(self.images):
                        raise ValueError("不允许读取头像目录外的链接文件")
                    person = resolve_image_person(relative, users, self.people.name_ids)
                    raw = path.read_bytes()
                    digest = hashlib.sha256(raw).hexdigest()
                    old = previous.get(relative)
                    if old and old["sha256"] == digest:
                        vector = old["embedding"]
                    else:
                        image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
                        if image is None:
                            raise ValueError("图片尚未写完、已损坏或格式不支持")
                        vectors = self.faces.features(image)
                        if len(vectors) != 1:
                            raise ValueError("头像必须恰好包含一张清晰且足够大的人脸")
                        vector = vectors[0]
                    records.append({"source": relative, **person, "embedding": vector, "sha256": digest})
                except Exception as exc:
                    errors.append({"source": relative, "reason": str(exc)})
            fingerprint = tuple((r["source"], r["person_id"], r["display_name"], r["sha256"]) for r in records)
            changed = fingerprint != self._fingerprint
            if changed:
                self.faces.replace_image_gallery(records)
                self._fingerprint = fingerprint
            revision = tuple((p.stat().st_mtime_ns, p.stat().st_size) if p.exists() else None for p in [self.people.path, Path(str(self.people.path)+"-wal")])
            active = {r["person_id"]: {"person_id": r["person_id"], "display_name": r["display_name"]} for r in records}
            with self.state_lock:
                self._state = {"registered_people": len(active), "valid_images": len(records), "errors": errors, "error": None, "last_sync": time.time(), "sync_ms": (time.perf_counter()-started)*1000, "users": list(active.values()), "syncing": False}
            if (changed or revision != self._db_revision) and self.on_people_changed:
                self.on_people_changed(list(active.values()))
            self._db_revision = revision
        except Exception as exc:
            # A missing/replaced/unreadable source cannot authorize stale identities.
            self.faces.replace_image_gallery([])
            self._fingerprint = None
            with self.state_lock:
                self._state.update({"registered_people": 0, "valid_images": 0, "users": [], "error": str(exc), "syncing": False})
        finally:
            self.scan_lock.release()
        return self.status()

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, daemon=True, name="portrait-sync")
        self.thread.start()

    def _run(self):
        while not self.stop_event.is_set():
            self.sync_once()
            self.stop_event.wait(self.interval)

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)
