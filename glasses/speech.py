import hashlib
from pathlib import Path
import queue
import re
import threading
import time
import uuid


def pronounce_text(text: str):
    # The selected Mandarin voice has no general English lexicon. Spell letters
    # explicitly instead of dropping out-of-vocabulary personal details.
    names = ["诶","比","西","迪","伊","艾弗","吉","艾尺","艾","杰","开","艾勒","艾姆","恩","欧","披","丘","阿尔","艾丝","提","优","维","达布留","艾克斯","歪","贼德"]
    text = re.sub(r"[A-Za-z]", lambda m: names[ord(m[0].lower())-ord('a')], text)
    text = text.replace("@", "艾特").replace("_", "下划线")
    text = re.sub(r"(?<=[\w\u4e00-\u9fff])\.(?=[\w\u4e00-\u9fff])", "点", text)
    return text.translate(str.maketrans({"：":"，", ":":"，", "（":"，", "）":"，", "(":"，", ")":"，", "；":"。", ";":"。", "…":"，", "/":"斜杠", "-":"横线"}))


def speech_chunks(text: str):
    chunks = []
    for sentence in re.findall(r"[^。！？；;]*[。！？；;]|[^。！？；;]+$", text):
        while len(sentence) > 60:
            comma = max(sentence.rfind("，", 20, 60), sentence.rfind("、", 20, 60))
            cut = comma+1 if comma >= 20 else 60
            chunks.append(sentence[:cut])
            sentence = sentence[cut:]
        if sentence:
            chunks.append(sentence)
    return chunks


class WakeGate:
    def __init__(self, phrase: str, required=True):
        self.phrase, self.required = phrase, required
        self.until = 0.

    def accept(self, text: str, now: float | None = None):
        now = time.monotonic() if now is None else now
        clean = re.sub(r"[\s，。？！?!、]", "", text)
        if not clean:
            return None
        if not self.required:
            return clean
        if self.phrase in clean:
            question = clean.split(self.phrase, 1)[1]
            self.until = now + 8
            if question:
                self.until = 0.
                return question
            return None
        if now < self.until:
            self.until = 0.
            return clean
        return None


class Speech:
    def __init__(self, root: Path, threads=2, output_device=None):
        import sherpa_onnx
        self.root, self.output_device = root, output_device
        model_dir = root / "models/tts/sherpa-onnx-vits-zh-ll"
        model = model_dir / "model.onnx"
        if not model.is_file():
            raise FileNotFoundError(f"缺少中文语音合成模型：{model}")
        config = sherpa_onnx.OfflineTtsConfig(
            model=sherpa_onnx.OfflineTtsModelConfig(
                vits=sherpa_onnx.OfflineTtsVitsModelConfig(model=str(model), tokens=str(model_dir / "tokens.txt"), lexicon=str(model_dir / "lexicon.txt")),
                num_threads=threads, provider="cpu", debug=False,
            ),
            rule_fsts=",".join(str(model_dir / (name + ".fst")) for name in ["phone", "date", "number"]),
            max_num_sentences=1,
        )
        if not config.validate():
            raise ValueError("中文语音合成配置无效")
        self.tts = sherpa_onnx.OfflineTts(config)
        self.cache_dir = root / "data/audio-cache" / f"zh-ll-speaker2-v1-{model.stat().st_size}"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.speaking = threading.Event()

    def synthesize(self, text: str):
        import numpy as np
        import soundfile as sf
        if not text.strip() or len(text) > 1000:
            raise ValueError("播报文字不能为空且最多 1000 字")
        text = pronounce_text(text)
        path = self.cache_dir / (hashlib.sha256(text.encode()).hexdigest() + ".wav")
        started = time.perf_counter()
        # Published WAV files are immutable and atomically replaced. Reading a
        # cached fast answer must not wait for unrelated background synthesis.
        if path.is_file():
            samples, rate = sf.read(path, dtype="float32")
            return samples, rate, {"tts_prepare_ms":(time.perf_counter()-started)*1000,"tts_cached":True}
        with self.lock:
            cached = path.is_file()
            if cached:
                samples, rate = sf.read(path, dtype="float32")
            else:
                import sherpa_onnx
                config = sherpa_onnx.GenerationConfig()
                config.sid, config.speed = 2, 1.15
                audio = self.tts.generate(text, config)
                samples, rate = np.asarray(audio.samples, dtype=np.float32), audio.sample_rate
                if not samples.size:
                    raise ValueError("语音合成返回空音频")
                partial = path.with_name(path.stem + "." + uuid.uuid4().hex + ".wav.part")
                sf.write(partial, samples, rate, subtype="PCM_16", format="WAV")
                partial.replace(path)
        return samples, rate, {"tts_prepare_ms": (time.perf_counter()-started)*1000, "tts_cached": cached}

    def say(self, text: str, on_start=None, cancel_event=None):
        import sounddevice as sd
        started = time.perf_counter()
        self.speaking.set()
        try:
            chunks = speech_chunks(text)
            if not chunks:
                raise ValueError("播报内容不能为空")
            samples, rate, metrics = self.synthesize(chunks[0])
            if cancel_event is not None and cancel_event.is_set():
                return {**metrics, "cancelled": True}
            # Stream startup is included. Timestamp is submission, not measured acoustic onset.
            with sd.OutputStream(samplerate=rate, channels=1, dtype="float32", device=self.output_device, latency="low") as out:
                metrics["audio_submit_ms"] = (time.perf_counter()-started)*1000
                metrics["audio_device_latency_ms"] = float(out.latency)*1000
                if on_start:
                    on_start(metrics)
                for index, chunk in enumerate(chunks):
                    if index:
                        samples, chunk_rate, _ = self.synthesize(chunk)
                        if chunk_rate != rate:
                            raise ValueError("播报采样率发生变化")
                    block = max(1, int(rate*.05))
                    for offset in range(0, len(samples), block):
                        if cancel_event is not None and cancel_event.is_set():
                            out.abort()
                            return {**metrics, "cancelled": True}
                        out.write(samples[offset:offset+block].reshape(-1, 1))
                metrics["speech_chunks"] = len(chunks)
            return metrics
        finally:
            self.speaking.clear()


class AudioPrewarmer:
    def __init__(self, speech, is_idle):
        self.speech, self.is_idle = speech, is_idle
        self.pending = queue.Queue()
        self.stop_event = threading.Event()
        self.error = None
        self.thread = threading.Thread(target=self._run, daemon=True, name="profile-audio-cache")
        self.thread.start()

    def enqueue(self, text):
        chunks = speech_chunks(text)
        if chunks:
            self.pending.put(chunks[0])

    def _run(self):
        while not self.stop_event.is_set():
            try:
                phrase = self.pending.get(timeout=.2)
            except queue.Empty:
                continue
            try:
                while not self.is_idle() and not self.stop_event.wait(.1):
                    pass
                if not self.stop_event.is_set():
                    self.speech.synthesize(phrase)
            except Exception as exc:
                self.error = str(exc)
            finally:
                self.pending.task_done()

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=5)


class ChineseASR:
    def __init__(self, model_dir: Path, threads=2):
        import sherpa_onnx
        self.recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
            tokens=str(model_dir / "tokens.txt"),
            encoder=str(model_dir / "encoder.int8.onnx"),
            decoder=str(model_dir / "decoder.onnx"),
            joiner=str(model_dir / "joiner.int8.onnx"),
            num_threads=threads, sample_rate=16000, feature_dim=80,
            decoding_method="greedy_search", provider="cpu",
            enable_endpoint_detection=True,
            rule1_min_trailing_silence=1.2,
            rule2_min_trailing_silence=.32,
            rule3_min_utterance_length=15,
        )

    def transcribe(self, samples, rate):
        import numpy as np
        stream = self.recognizer.create_stream()
        stream.accept_waveform(rate, samples)
        stream.accept_waveform(rate, np.zeros(int(rate*.6), dtype=np.float32))
        stream.input_finished()
        while self.recognizer.is_ready(stream):
            self.recognizer.decode_stream(stream)
        return self.recognizer.get_result(stream)


class VoiceLoop:
    """Explicit start/stop. No recording retained. Ignore speaker output to avoid feedback."""
    def __init__(self, asr: ChineseASR, speech: Speech, config: dict, handler, input_factory=None):
        self.asr, self.speech, self.config, self.handler = asr, speech, config, handler
        self.stop_event = threading.Event()
        self.thread = None
        self.error = None
        self.last_transcript = ""
        self.phase = "stopped"
        self.input_stream = None
        self.lifecycle_lock = threading.Lock()
        self.input_factory = input_factory

    def start(self):
        if self.thread and self.thread.is_alive():
            if self.stop_event.is_set():
                raise ValueError("上一条语音请求正在取消，麦克风已关闭，请稍后重新开启")
            return
        self.stop_event.clear()
        self.error = None
        self.thread = threading.Thread(target=self._run, daemon=True, name="voice")
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.phase = "stopping" if self.thread and self.thread.is_alive() else "stopped"
        # Release hardware independently of a potentially slow VLM/TTS handler.
        with self.lifecycle_lock:
            if self.input_stream is not None:
                self.input_stream.abort()
                self.input_stream.close()
                self.input_stream = None
        if self.thread:
            self.thread.join(timeout=.5)

    def _run(self):
        import numpy as np
        import sounddevice as sd
        pending = queue.Queue(maxsize=100)
        gate = WakeGate(self.config["wake_phrase"], self.config["wake_required"])
        recognizer = self.asr.recognizer
        stream = recognizer.create_stream()
        voiced_until = None

        def callback(data, frames, timing, status):
            if status:
                self.error = str(status)
            if self.speech.speaking.is_set() or self.phase != "listening":
                return
            try:
                pending.put_nowait((data[:, 0].copy(), time.perf_counter()))
            except queue.Full:
                self.error = "语音处理跟不上实时输入，请停止后检查 CPU 负载"
                self.stop_event.set()

        try:
            with self.lifecycle_lock:
                if self.stop_event.is_set():
                    return
                self.input_stream = self.input_factory(callback) if self.input_factory else sd.InputStream(samplerate=16000, channels=1, dtype="float32", blocksize=1600, device=self.config["audio_input_device"], callback=callback)
                self.phase = "listening"
                self.input_stream.start()
            while not self.stop_event.is_set():
                try:
                    samples, captured_at = pending.get(timeout=.2)
                except queue.Empty:
                    device = self.input_stream
                    if device is not None and not self.stop_event.is_set() and not device.active:
                        raise RuntimeError("音频输入已中断，请检查采集设备后重新开启语音")
                    continue
                if time.perf_counter() - captured_at > .75:
                    raise RuntimeError("语音输入积压，无法满足实时响应")
                if np.sqrt(np.mean(samples*samples)) > .008:
                    voiced_until = captured_at
                stream.accept_waveform(16000, samples)
                while recognizer.is_ready(stream):
                    recognizer.decode_stream(stream)
                text = recognizer.get_result(stream)
                self.last_transcript = text
                if recognizer.is_endpoint(stream):
                    query = gate.accept(text)
                    recognizer.reset(stream)
                    if query:
                        self.phase = "answering"
                        self.handler(query, voiced_until, self.stop_event)
                        self.phase = "stopping" if self.stop_event.is_set() else "listening"
                        # Discard audio captured while responding; reset partial decoder state.
                        while not pending.empty():
                            try:
                                pending.get_nowait()
                            except queue.Empty:
                                break
                        recognizer.reset(stream)
                    voiced_until = None
        except Exception as exc:
            self.error = str(exc)
        finally:
            with self.lifecycle_lock:
                if self.input_stream is not None:
                    self.input_stream.abort()
                    self.input_stream.close()
                    self.input_stream = None
            self.phase = "stopped"
