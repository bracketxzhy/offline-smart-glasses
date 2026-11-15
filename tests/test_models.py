"""Real model checks. Run with GLASSES_MODEL_TESTS=1 after bootstrap/startup."""
import os
from pathlib import Path
import tempfile
import unittest


@unittest.skipUnless(os.getenv("GLASSES_MODEL_TESTS") == "1", "Set GLASSES_MODEL_TESTS=1 for real model tests")
class ModelTests(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]

    def test_detector_finds_bus_in_known_fixture(self):
        import cv2
        from glasses.vision import ObjectDetector
        detector = ObjectDetector(self.ROOT / "models/detector/yolo11n.onnx")
        image = cv2.imread(str(self.ROOT / "data/fixtures/bus.jpg"))
        results = detector.detect(image)
        self.assertTrue(any(d["label"] == "公交车" and d["score"] > .45 for d in results))
        for detection in results:
            x1, y1, x2, y2 = detection["box"]
            self.assertTrue(0 <= x1 < x2 <= image.shape[1])
            self.assertTrue(0 <= y1 < y2 <= image.shape[0])

    def test_real_face_enrollment_is_not_implicit(self):
        import cv2
        from glasses.vision import FaceRecognizer
        image = cv2.imread(str(self.ROOT / "data/fixtures/lena.jpg"))
        with tempfile.TemporaryDirectory() as tmp:
            faces = FaceRecognizer(self.ROOT / "models/face", Path(tmp) / "faces.db")
            self.assertEqual(faces.identify(image)["status"], "unknown")
            faces.enroll("fixture_user", "测试图片", image)
            self.assertEqual(faces.identify(image)["person_id"], "fixture_user")
            small = cv2.resize(image, (448, 448))
            self.assertEqual(faces.identify(small)["person_id"], "fixture_user")

    def test_synthesized_chinese_wake_and_question_route_to_object(self):
        from glasses.core import route_query
        from glasses.speech import Speech, ChineseASR, WakeGate
        tts = Speech(self.ROOT)
        asr = ChineseASR(self.ROOT / "models/asr")
        audio, rate, _ = tts.synthesize("你好助手，前面是什么？")
        text = asr.transcribe(audio, rate)
        question = WakeGate("你好助手").accept(text)
        self.assertIsNotNone(question, text)
        self.assertEqual(route_query(question), "object", text)

    def test_chinese_vlm_identifies_known_vehicle(self):
        import cv2
        from glasses.vlm import VLM
        image = cv2.imread(str(self.ROOT / "data/fixtures/bus.jpg"))
        text, metrics = VLM("http://127.0.0.1:8081").ask(image, "画面中的主要交通工具是什么？用中文简短回答。")
        self.assertTrue(any(word in text for word in ["公交", "公共汽车", "巴士", "大巴", "客车"]), text)
        self.assertGreater(metrics["vlm_first_token_ms"], 0)


if __name__ == "__main__":
    unittest.main()
