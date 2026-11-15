import base64
import json
import re
import time
from concurrent.futures import CancelledError
from urllib.parse import urlsplit

import cv2
import requests


class VLM:
    def __init__(self, url: str):
        parsed = urlsplit(url)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("VLM 必须为本机 HTTP 服务，禁止将画面发送到外部服务器")
        self.url = url.rstrip("/")
        self.session = requests.Session()
        self.session.trust_env = False

    def ready(self):
        return self.session.get(self.url + "/health", timeout=2).status_code == 200

    def ask(self, frame, question, cancel_event=None):
        if cancel_event is not None and cancel_event.is_set():
            raise CancelledError("语音请求已取消")
        h, w = frame.shape[:2]
        scale = min(1., 448 / max(h, w))
        image = cv2.resize(frame, (round(w*scale), round(h*scale)))
        ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ok:
            raise ValueError("图片编码失败")
        payload = {
            "messages": [
                {"role": "system", "content": "你是离线智能眼镜助手。用简体中文直接回答，最多两句。仅根据图像描述可见内容；看不清就说看不清，不猜测人物身份和私人资料。"},
                {"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(encoded).decode()}},
                    {"type": "text", "text": question},
                ]},
            ],
            "max_tokens": 96, "temperature": .2, "stream": True,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        start = time.perf_counter()
        first = None
        parts = []
        with self.session.post(self.url + "/v1/chat/completions", json=payload, stream=True, timeout=(5, 180)) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if cancel_event is not None and cancel_event.is_set():
                    raise CancelledError("语音请求已取消")
                if not line.startswith(b"data: ") or line == b"data: [DONE]":
                    continue
                item = json.loads(line[6:])
                content = item.get("choices", [{}])[0].get("delta", {}).get("content", "")
                if content:
                    if first is None:
                        first = (time.perf_counter() - start) * 1000
                    parts.append(content)
        text = re.sub(r"<think>.*?</think>", "", "".join(parts), flags=re.DOTALL).strip()
        if not text:
            raise ValueError("视觉模型未产生有效回答")
        return text, {"vlm_first_token_ms": first, "vlm_total_ms": (time.perf_counter()-start)*1000}
