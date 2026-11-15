from pathlib import Path
import json
import threading
import time
from concurrent.futures import CancelledError

import numpy as np
import psutil

from .core import route_query, select_object
from .people import PeopleDatabase
from .gallery import GallerySync
from .speech import ChineseASR, Speech, VoiceLoop, AudioPrewarmer
from .vision import Camera, FaceRecognizer, ObjectDetector
from .vlm import VLM
from .usb_transport import USBTransport
from .wifi_transport import WiFiTransport
from .sensor_input import SensorCamera, SensorInputStream


class Assistant:
    def __init__(self, root: Path):
        self.root = root
        self.config = json.loads((root / "config.app.json").read_text(encoding="utf-8"))
        self.detector = ObjectDetector(root / "models/detector/yolo11n.onnx", self.config["threads"])
        self.faces = FaceRecognizer(root / "models/face", root / "data/identity-cache.sqlite3")
        self.speech = Speech(root, self.config["threads"], self.config["audio_output_device"])
        self.asr = ChineseASR(root / "models/asr", self.config["threads"])
        self.vlm = VLM(self.config["vlm_url"])
        self.transport = None
        if self.config["sensor_source"] == "local":
            self.camera = Camera(self.config["camera_source"], self.config["camera_fps"])
        elif self.config["sensor_source"] == "xiao_usb":
            self.transport = USBTransport(self.config["xiao_usb"])
            self.camera = SensorCamera(self.transport)
        elif self.config["sensor_source"] == "xiao_wifi":
            self.transport = WiFiTransport(self.config["xiao_wifi"])
            self.camera = SensorCamera(self.transport)
        else:
            raise ValueError("sensor_source 必须显式选择 local、xiao_usb 或 xiao_wifi")
        self.people = PeopleDatabase(root / self.config["profile_database"], self.config["identity_name_ids"])
        self.query_lock = threading.Lock()
        self.prewarmer = AudioPrewarmer(self.speech, lambda: not self.query_lock.locked())
        self.gallery = GallerySync(self.people, root / self.config["portraits_directory"], self.faces, interval=self.config["portrait_sync_seconds"], on_people_changed=self._warm_people)
        self.gallery.sync_once()
        self.gallery.start()
        self.last_result = None
        input_factory = (lambda callback: SensorInputStream(self.transport, callback)) if self.transport else None
        self.voice = VoiceLoop(self.asr, self.speech, self.config, self._voice_query, input_factory=input_factory)
        self.log_dir = root / "logs"
        self.log_dir.mkdir(exist_ok=True)
        self.detector.detect(np.zeros((320, 320, 3), dtype=np.uint8))

    def _warm_people(self, users):
        for user in users:
            self.prewarmer.enqueue(f"这是{user['display_name']}。")
            person = self.people.get(user["person_id"])
            for question in ["年龄", "性别", "介绍一下他", "他研究什么", "他教什么课", "他的职务是什么", "他的学历是什么", "他的邮箱是什么"]:
                self.prewarmer.enqueue(self.people.render(question, person)[0])

    def _voice_query(self, text, ended, cancel_event):
        try:
            self.ask(text, speak=True, speech_ended=ended, cancel_event=cancel_event)
        except CancelledError:
            self.last_result = {"answer": "语音请求已取消", "route": "cancelled", "timings": {}}
        except Exception as exc:
            self.last_result = {"error": str(exc)}

    def ask(self, question: str, *, speak=False, mode="adaptive", frame=None, speech_ended=None, cancel_event=None):
        if not self.query_lock.acquire(blocking=False):
            raise ValueError("正在处理上一条问题，请稍候")
        started = time.perf_counter()
        timings = {}
        try:
            named = self.people.person_in_question(question)
            route = route_query(question, known_person=named is not None)
            if mode not in {"adaptive", "modular", "vlm_only"}:
                raise ValueError("未知实验模式")
            if mode == "vlm_only":
                if route in {"face", "profile"}:
                    raise ValueError("VLM-only 不能识别私人登记身份；人脸与资料查询请使用混合或模块模式")
                route = "vlm"
            if mode == "modular" and route == "vlm":
                raise ValueError("模块模式不支持通用视觉问题，请显式选择混合或 VLM-only 模式")
            timings["routing_ms"] = (time.perf_counter()-started)*1000
            stage = time.perf_counter()
            needs_image = not (named and route in {"face", "profile"})
            if frame is None and needs_image:
                frame, timestamp = self.camera.snapshot()
                timings["frame_age_ms"] = (time.monotonic()-timestamp)*1000
            timings["capture_ms"] = (time.perf_counter()-stage)*1000
            details = {}
            stage = time.perf_counter()
            if route == "object":
                detections = self.detector.detect(frame)
                item = select_object(detections, frame.shape[1], frame.shape[0])
                answer = f"前面是{item['label']}。" if item else "没有识别到常见物品。"
                details = {"detections": detections, "selected": item}
            elif route in {"face", "profile"}:
                if named:
                    identity = {"status": "known", **named, "source": "explicit_name"}
                else:
                    sync_status = self.gallery.status()
                    if sync_status["error"]:
                        raise ValueError("人员库同步失败：" + sync_status["error"])
                    identity = self.faces.identify(frame)
                    identity["source"] = "camera_face"
                details = {"identity": identity}
                status = identity["status"]
                if status == "no_face":
                    answer = "没有看到清晰的人脸。"
                elif status == "multiple_faces":
                    answer = "画面中有多个人，请让目标人物单独面对镜头。"
                elif status == "unknown":
                    answer = "这位用户尚未识别为已登记人员。"
                else:
                    db_start = time.perf_counter()
                    person = self.people.get(identity["person_id"])
                    timings["database_ms"] = (time.perf_counter()-db_start)*1000
                    if person is None:
                        identity = {"status": "unknown", "source": identity["source"]}
                        details["identity"] = identity
                        answer = "这位用户的资料已移除，不能作为已登记人员识别。"
                    elif route == "face":
                        identity["display_name"] = person["display_name"]
                        answer = f"这是{person['display_name']}。"
                    else:
                        answer, evidence = self.people.render(question, person)
                        details["evidence"] = evidence
            else:
                answer, vlm_timings = self.vlm.ask(frame, question, cancel_event=cancel_event)
                timings.update(vlm_timings)
            if cancel_event is not None and cancel_event.is_set():
                raise CancelledError("语音请求已取消")
            timings["vision_and_answer_ms"] = (time.perf_counter()-stage)*1000
            timings["text_ready_ms"] = (time.perf_counter()-started)*1000
            result = {"question": question, "answer": answer, "route": route, "mode": mode, "timings": timings, "details": details}
            self.last_result = result
            if speak:
                def on_start(audio_metrics):
                    timings.update(audio_metrics)
                    timings["request_to_audio_submit_ms"] = (time.perf_counter()-started)*1000
                    if speech_ended is not None:
                        timings["estimated_speech_end_to_audio_submit_ms"] = (time.perf_counter()-speech_ended)*1000
                    timings["estimated_audio_onset_ms"] = timings["request_to_audio_submit_ms"] + audio_metrics["audio_device_latency_ms"]
                timings.update(self.speech.say(answer, on_start=on_start, cancel_event=cancel_event))
            timings["request_total_ms"] = (time.perf_counter()-started)*1000
            timings["python_rss_mib"] = psutil.Process().memory_info().rss / 1024**2
            record = {"timestamp": time.time(), "route": route, "mode": mode, "timings": timings}
            # Do not persist questions, answers, camera frames or private profiles by default.
            with (self.log_dir / "queries.jsonl").open("a", encoding="utf-8") as out:
                out.write(json.dumps(record, ensure_ascii=False)+"\n")
            return result
        finally:
            self.query_lock.release()

    def close(self):
        self.voice.stop()
        self.camera.stop()
        self.gallery.stop()
        self.prewarmer.stop()
