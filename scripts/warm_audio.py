"""Pre-render common answers so the fast path only reads local WAV files."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from glasses.speech import Speech
from glasses.vision import LABELS

if __name__ == "__main__":
    speech = Speech(ROOT)
    phrases = [f"前面是{label}。" for label in LABELS]
    phrases += ["没有识别到常见物品。", "没有看到清晰的人脸。", "画面中有多个人，请让目标人物单独面对镜头。", "这位用户尚未识别为已登记人员。", "资料库中没有这位用户的信息。"]
    for i, phrase in enumerate(phrases):
        speech.synthesize(phrase)
        if (i+1) % 10 == 0 or i == len(phrases)-1:
            print(f"Cached {i+1}/{len(phrases)} answers", flush=True)
