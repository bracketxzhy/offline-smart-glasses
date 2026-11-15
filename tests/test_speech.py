import unittest
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch
import tempfile
from pathlib import Path
import hashlib

from glasses.speech import WakeGate, speech_chunks, pronounce_text


class WakeTests(unittest.TestCase):
    def test_long_answers_can_start_before_all_audio_is_generated(self):
        text = "这是测试。" + "完整保留文字"*30 + "；最后一句。"
        pieces = speech_chunks(text)
        self.assertEqual("".join(pieces), text)
        self.assertTrue(all(len(p) <= 60 for p in pieces))

    def test_email_and_latin_text_are_not_silently_dropped_by_chinese_tts(self):
        spoken = pronounce_text("邮箱：A_b@x.cn")
        self.assertEqual(spoken, "邮箱，诶下划线比艾特艾克斯点西恩")
        self.assertEqual(pronounce_text("前面是杯子。"), "前面是杯子。")

    def test_cached_answer_does_not_wait_for_background_tts_generation(self):
        import numpy as np
        import soundfile as sf
        from glasses.speech import Speech
        with tempfile.TemporaryDirectory() as tmp:
            speech = Speech.__new__(Speech)
            speech.cache_dir, speech.lock = Path(tmp), threading.Lock()
            text = "前面是杯子。"
            target = speech.cache_dir / (hashlib.sha256(text.encode()).hexdigest()+".wav")
            sf.write(target,np.zeros(1600,dtype=np.float32),16000,subtype="PCM_16")
            held, release = threading.Event(), threading.Event()
            def slow_generation():
                with speech.lock:
                    held.set();release.wait(1)
            worker = threading.Thread(target=slow_generation)
            worker.start();held.wait(1)
            try:
                started = time.perf_counter()
                samples,rate,metrics = speech.synthesize(text)
                self.assertLess(time.perf_counter()-started,.2)
                self.assertEqual((len(samples),rate),(1600,16000))
                self.assertTrue(metrics["tts_cached"])
            finally:
                release.set();worker.join(2)

    def test_disconnected_audio_source_stops_voice_loop(self):
        from glasses.speech import VoiceLoop
        class DisconnectedInput:
            active = False
            def start(self): pass
            def abort(self): pass
            def close(self): pass
        asr = SimpleNamespace(recognizer=SimpleNamespace(create_stream=lambda: None))
        loop = VoiceLoop(asr,SimpleNamespace(speaking=threading.Event()),{"wake_phrase":"你好助手","wake_required":True,"audio_input_device":None},lambda *args:None,input_factory=lambda callback:DisconnectedInput())
        loop.start();loop.thread.join(5)
        try:
            self.assertEqual(loop.phase,"stopped")
            self.assertIn("中断",loop.error or "")
        finally:loop.stop()

    def test_no_query_without_wake_and_question_can_follow_wake(self):
        gate = WakeGate("你好眼镜", required=True)
        self.assertIsNone(gate.accept("前面是什么", now=1))
        self.assertEqual(gate.accept("你好，眼镜，前面是什么？", now=2), "前面是什么")

    def test_wake_only_opens_bounded_question_window(self):
        gate = WakeGate("你好眼镜", required=True)
        self.assertIsNone(gate.accept("你好眼镜", now=1))
        self.assertEqual(gate.accept("这是谁", now=3), "这是谁")
        self.assertIsNone(gate.accept("前面是什么", now=4))
        gate.accept("你好眼镜", now=5)
        self.assertIsNone(gate.accept("这是谁", now=20))

    def test_explicit_direct_mode_accepts_question(self):
        self.assertEqual(WakeGate("你好眼镜", required=False).accept("前面是什么", now=1), "前面是什么")

    def test_stopping_releases_microphone_during_slow_answer(self):
        import numpy as np
        from glasses.speech import VoiceLoop
        entered, release, closed = threading.Event(), threading.Event(), threading.Event()

        class Recognizer:
            def create_stream(self):
                return SimpleNamespace(accept_waveform=lambda *args: None)
            def is_ready(self, stream):
                return False
            def get_result(self, stream):
                return "你好助手这是谁"
            def is_endpoint(self, stream):
                return True
            def reset(self, stream):
                pass

        class InputDevice:
            def __init__(self, **kwargs):
                self.callback = kwargs["callback"]
            def start(self):
                self.callback(np.ones((1600, 1), dtype=np.float32), 1600, None, None)
            def abort(self):
                pass
            def close(self):
                closed.set()

        def answer(query, ended, cancel_event):
            entered.set()
            release.wait(3)

        loop = VoiceLoop(SimpleNamespace(recognizer=Recognizer()), SimpleNamespace(speaking=threading.Event()), {"wake_phrase": "你好助手", "wake_required": True, "audio_input_device": None}, answer)
        with patch("sounddevice.InputStream", InputDevice):
            try:
                loop.start()
                self.assertTrue(entered.wait(1))
                start = time.perf_counter()
                loop.stop()
                self.assertTrue(closed.is_set(), "Microphone remained open during the slow answer")
                self.assertLess(time.perf_counter()-start, 1)
                with self.assertRaises(ValueError):
                    loop.start()
            finally:
                release.set()
                loop.thread.join(2)


if __name__ == "__main__":
    unittest.main()
