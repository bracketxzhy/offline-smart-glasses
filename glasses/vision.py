from pathlib import Path
from contextlib import closing
import json
import hashlib
import sqlite3
import threading
import time

import cv2
import numpy as np
import onnxruntime as ort

from .core import match_identity, require_fresh

LABELS = "人 自行车 汽车 摩托车 飞机 公交车 火车 卡车 船 红绿灯 消防栓 停车标志 停车计时器 长椅 鸟 猫 狗 马 羊 牛 大象 熊 斑马 长颈鹿 背包 雨伞 手提包 领带 行李箱 飞盘 滑雪板 单板滑雪板 球 风筝 棒球棒 棒球手套 滑板 冲浪板 网球拍 瓶子 红酒杯 杯子 叉子 刀 勺子 碗 香蕉 苹果 三明治 橙子 西兰花 胡萝卜 热狗 披萨 甜甜圈 蛋糕 椅子 沙发 盆栽 床 餐桌 马桶 电视 笔记本电脑 鼠标 遥控器 键盘 手机 微波炉 烤箱 烤面包机 水槽 冰箱 书 时钟 花瓶 剪刀 玩具熊 吹风机 牙刷".split()


class ObjectDetector:
    def __init__(self, model: Path, threads=2, size=320):
        if not model.is_file():
            raise FileNotFoundError(f"缺少物体模型：{model}")
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(model), sess_options=options, providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name
        self.size = size
        self.lock = threading.Lock()

    def detect(self, frame):
        h, w = frame.shape[:2]
        scale = self.size / max(h, w)
        resized = cv2.resize(frame, (round(w * scale), round(h * scale)))
        left = (self.size - resized.shape[1]) // 2
        top = (self.size - resized.shape[0]) // 2
        canvas = np.full((self.size, self.size, 3), 114, dtype=np.uint8)
        canvas[top:top+resized.shape[0], left:left+resized.shape[1]] = resized
        tensor = np.ascontiguousarray(canvas[:, :, ::-1].transpose(2, 0, 1)[None], dtype=np.float32) / 255.
        with self.lock:
            predictions = self.session.run(None, {self.input_name: tensor})[0][0].T
        ids = predictions[:, 4:].argmax(axis=1)
        scores = predictions[np.arange(len(ids)), ids + 4]
        mask = scores >= .45
        xywh, scores, ids = predictions[mask, :4], scores[mask], ids[mask]
        boxes = []
        for cx, cy, bw, bh in xywh:
            boxes.append([float((cx - bw/2 - left)/scale), float((cy - bh/2 - top)/scale), float(bw/scale), float(bh/scale)])
        # Class-aware NMS avoids suppressing an object overlapping a person.
        kept = []
        for class_id in set(ids.tolist()):
            indices = [i for i, x in enumerate(ids) if x == class_id]
            selected = cv2.dnn.NMSBoxes([boxes[i] for i in indices], [float(scores[i]) for i in indices], .45, .45)
            kept.extend(indices[int(i)] for i in np.array(selected).reshape(-1))
        results = []
        for i in kept:
            x, y, bw, bh = boxes[i]
            results.append({"class_id": int(ids[i]), "label": LABELS[int(ids[i])], "score": float(scores[i]), "box": [max(0., x), max(0., y), min(float(w), x+bw), min(float(h), y+bh)]})
        return sorted(results, key=lambda d: d["score"], reverse=True)


class FaceRecognizer:
    def __init__(self, model_dir: Path, gallery: Path):
        self.detector = cv2.FaceDetectorYN.create(str(model_dir / "yunet.onnx"), "", (320, 320), .85, .3, 1000)
        model = model_dir / "arcface_mbf.onnx"
        if not model.is_file():
            raise FileNotFoundError(f"缺少选定的 512 维人脸模型：{model}")
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        self.recognizer = ort.InferenceSession(str(model), sess_options=options, providers=["CPUExecutionProvider"])
        self.input_name = self.recognizer.get_inputs()[0].name
        with model.open("rb") as source:
            self.model_signature = "arcface-mbf-512-align-v1:" + hashlib.file_digest(source, "sha256").hexdigest()
        self.gallery = gallery
        gallery.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(gallery)) as conn, conn:
            conn.execute("CREATE TABLE IF NOT EXISTS face_templates(person_id TEXT PRIMARY KEY, display_name TEXT NOT NULL, embedding TEXT NOT NULL)")
            conn.execute("CREATE TABLE IF NOT EXISTS image_face_templates(source TEXT PRIMARY KEY,person_id TEXT NOT NULL,display_name TEXT NOT NULL,embedding TEXT NOT NULL,sha256 TEXT NOT NULL)")
            conn.execute("CREATE TABLE IF NOT EXISTS face_model(signature TEXT NOT NULL)")
            previous = conn.execute("SELECT signature FROM face_model").fetchone()
            if previous is None or previous[0] != self.model_signature:
                # These are derived caches only; source portraits and the teammate DB are untouched.
                conn.execute("DELETE FROM face_templates")
                conn.execute("DELETE FROM image_face_templates")
                conn.execute("DELETE FROM face_model")
                conn.execute("INSERT INTO face_model VALUES(?)", (self.model_signature,))
        self.lock = threading.Lock()

    @staticmethod
    def align(frame, face):
        source = np.asarray(face[4:14], dtype=np.float64).reshape(5, 2)
        target = np.array([[38.2946,51.6963],[73.5318,51.5014],[56.0252,71.7366],[41.5493,92.3655],[70.7299,92.2041]], dtype=np.float64)
        src_mean, dst_mean = source.mean(axis=0), target.mean(axis=0)
        src, dst = source-src_mean, target-dst_mean
        u, singular, vt = np.linalg.svd(dst.T @ src / 5)
        correction = np.array([1., np.sign(np.linalg.det(u @ vt))])
        rotation = u @ np.diag(correction) @ vt
        variance = np.sum(src*src)/5
        if variance <= 0:
            raise ValueError("人脸关键点无效")
        scale = np.sum(singular*correction)/variance
        translation = dst_mean - scale*rotation @ src_mean
        matrix = np.column_stack([scale*rotation, translation])
        return cv2.warpAffine(frame, matrix, (112,112), borderValue=0)

    def embed_aligned(self, aligned):
        tensor = cv2.dnn.blobFromImage(aligned, 1/127.5, (112,112), (127.5,)*3, swapRB=True)
        vector = self.recognizer.run(None, {self.input_name: tensor})[0].flatten().astype(float)
        norm = np.linalg.norm(vector)
        if len(vector) != 512 or not np.isfinite(vector).all() or norm <= 0:
            raise ValueError("人脸模型返回无效特征")
        return (vector / norm).tolist()

    def features(self, frame):
        # Small detection input, landmarks mapped back before SFace alignment.
        h, w = frame.shape[:2]
        scale = min(1., 480 / max(h, w))
        small = cv2.resize(frame, (round(w*scale), round(h*scale)))
        with self.lock:
            self.detector.setInputSize((small.shape[1], small.shape[0]))
            _, faces = self.detector.detect(small)
            output = []
            if faces is not None:
                for face in faces:
                    mapped = face.copy()
                    mapped[:14] /= scale
                    if min(mapped[2], mapped[3]) < 40:
                        continue
                    output.append(self.embed_aligned(self.align(frame, mapped)))
            return output

    def identify(self, frame):
        features = self.features(frame)
        if len(features) != 1:
            return {"status": "no_face" if not features else "multiple_faces", "count": len(features)}
        with closing(sqlite3.connect(self.gallery)) as conn:
            rows = conn.execute("SELECT person_id, display_name, embedding FROM face_templates UNION ALL SELECT person_id, display_name, embedding FROM image_face_templates").fetchall()
        person_id = match_identity(features[0], [(r[0], json.loads(r[2])) for r in rows])
        if person_id is None:
            return {"status": "unknown", "count": 1, "registered_count": len(rows)}
        name = next(r[1] for r in rows if r[0] == person_id)
        return {"status": "known", "person_id": person_id, "display_name": name, "count": 1}

    def image_gallery(self):
        with closing(sqlite3.connect(self.gallery)) as conn:
            conn.row_factory = sqlite3.Row
            return {r["source"]: {**dict(r), "embedding": json.loads(r["embedding"])} for r in conn.execute("SELECT * FROM image_face_templates")}

    def replace_image_gallery(self, records):
        with closing(sqlite3.connect(self.gallery)) as conn, conn:
            conn.execute("DELETE FROM image_face_templates")
            conn.executemany("INSERT INTO image_face_templates VALUES(?,?,?,?,?)", [(r["source"],r["person_id"],r["display_name"],json.dumps(r["embedding"]),r["sha256"]) for r in records])

    def enroll(self, person_id: str, display_name: str, frame):
        import re
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", person_id) or not display_name.strip() or len(display_name) > 80:
            raise ValueError("用户编号只能含字母、数字、下划线和短横线，姓名不能为空")
        features = self.features(frame)
        if len(features) != 1:
            raise ValueError("登记时画面必须恰好有一张清晰且足够大的人脸")
        with closing(sqlite3.connect(self.gallery)) as conn, conn:
            conn.execute("INSERT INTO face_templates VALUES(?,?,?) ON CONFLICT(person_id) DO UPDATE SET display_name=excluded.display_name,embedding=excluded.embedding", (person_id, display_name.strip(), json.dumps(features[0])))
        return {"person_id": person_id, "display_name": display_name.strip()}


class Camera:
    def __init__(self, source=0, fps=3):
        self.source, self.fps = source, fps
        self.frame, self.timestamp, self.error = None, 0., None
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = None

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.error = None
        self.thread = threading.Thread(target=self._run, daemon=True, name="camera")
        self.thread.start()

    def is_running(self):
        return bool(self.thread and self.thread.is_alive())

    def _run(self):
        cap = cv2.VideoCapture(self.source)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, self.fps)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        try:
            if not cap.isOpened():
                raise RuntimeError("摄像头无法打开，请检查编号和系统权限")
            while not self.stop_event.is_set():
                ok, frame = cap.read()
                if not ok:
                    raise RuntimeError("摄像头读取失败")
                with self.lock:
                    self.frame, self.timestamp = frame, time.monotonic()
                self.stop_event.wait(.01)
        except Exception as exc:
            self.error = str(exc)
        finally:
            cap.release()

    def snapshot(self):
        with self.lock:
            if self.frame is None:
                raise ValueError(self.error or "摄像头未就绪，请先启动摄像头")
            require_fresh(self.timestamp)
            return self.frame.copy(), self.timestamp

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=3)
