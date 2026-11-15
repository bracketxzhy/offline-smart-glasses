"""Local candidate evaluation; synthetic perturbations are not an accuracy dataset."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ASSETS = [
    ("buffalo_l", "80ffe37d8a5940d59a7384c201a2a38d4741f2f3c51eef46ebb28218a7b0ca2f", "w600k_r50.onnx"),
    ("buffalo_sc", "57d31b56b6ffa911c8a73cfc1707c73cab76efe7f13b675a05223bf42de47c72", "w600k_mbf.onnx"),
]


def prepare(asset):
    name, digest, wanted = asset
    archive = ROOT / "models/downloads" / (name + ".zip")
    url = f"https://github.com/deepinsight/insightface/releases/download/model-zoo/{name}.zip"
    def checksum(path):
        with path.open("rb") as f:
            return hashlib.file_digest(f, "sha256").hexdigest()
    if not archive.is_file() or checksum(archive) != digest:
        print("Downloading official candidate: " + name, flush=True)
        partial = archive.with_suffix(".zip.part")
        with urllib.request.urlopen(url, timeout=120) as response, partial.open("wb") as out:
            while block := response.read(1024*1024):
                out.write(block)
        if checksum(partial) != digest:
            raise RuntimeError("Candidate archive checksum mismatch: " + name)
        partial.replace(archive)
    target = ROOT / "models/face-candidates" / name / wanted
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        entries = [n for n in z.namelist() if Path(n).name == wanted]
        if len(entries) != 1:
            raise RuntimeError("Expected one recognition model in archive")
        with z.open(entries[0]) as source, target.open("wb") as output:
            while block := source.read(1024*1024):
                output.write(block)
    return name, target, {"archive_url": url, "archive_sha256": digest, "model_sha256": checksum(target)}


def main():
    import cv2
    import numpy as np
    import onnxruntime as ort
    import tempfile
    with ThreadPoolExecutor(max_workers=2) as pool:
        prepared = list(pool.map(prepare, ASSETS))
    records = {}
    with tempfile.TemporaryDirectory() as tmp:
        detector = cv2.FaceDetectorYN.create(str(ROOT / "models/face/yunet.onnx"), "", (320,320), .85, .3, 1000)
        sface = cv2.FaceRecognizerSF.create(str(ROOT / "models/face/sface.onnx"), "")
        def align(image):
            h,w=image.shape[:2]
            detector.setInputSize((w,h))
            _, found=detector.detect(image)
            if found is None or len(found)!=1:
                raise ValueError("Comparison requires one face")
            return sface.alignCrop(image,found[0])
        portraits = {}
        for p in sorted((ROOT / "database/images").glob("*.jpg")):
            image=cv2.imdecode(np.fromfile(p,dtype=np.uint8),cv2.IMREAD_COLOR)
            variants={"original": image, "darker":cv2.convertScaleAbs(image,alpha=.7), "blur":cv2.GaussianBlur(image,(5,5),1.1), "low_resolution":cv2.resize(cv2.resize(image,(96,96)),(image.shape[1],image.shape[0]))}
            portraits[p.stem]={k:align(v) for k,v in variants.items()}
        unknown=align(cv2.imread(str(ROOT / "data/fixtures/lena.jpg")))
        configs=[("sface_128",None,{})]+prepared
        for name, path, source in configs:
            session=None
            if path:
                opts=ort.SessionOptions();opts.intra_op_num_threads=2;opts.inter_op_num_threads=1
                session=ort.InferenceSession(str(path),sess_options=opts,providers=["CPUExecutionProvider"])
            def embed(image):
                if session:
                    blob=cv2.dnn.blobFromImage(image,1/127.5,(112,112),(127.5,)*3,swapRB=True)
                    feature=session.run(None,{session.get_inputs()[0].name:blob})[0].ravel()
                else:
                    feature=sface.feature(image).ravel()
                return feature/np.linalg.norm(feature)
            vectors={key:{v:embed(image) for v,image in images.items()} for key,images in portraits.items()}
            originals=[x["original"] for x in vectors.values()]
            positive=[float(v["original"]@a) for v in vectors.values() for label,a in v.items() if label!="original"]
            unknown_vector=embed(unknown)
            negatives=[float(unknown_vector@x) for x in originals]
            negatives += [float(originals[i]@originals[j]) for i in range(len(originals)) for j in range(i)]
            sample=next(iter(portraits.values()))["original"]
            for _ in range(3):embed(sample)
            elapsed=[]
            for _ in range(20):
                start=time.perf_counter();embed(sample);elapsed.append((time.perf_counter()-start)*1000)
            records[name]={"dimension":len(originals[0]),"model_mib":path.stat().st_size/1024**2 if path else (ROOT/'models/face/sface.onnx').stat().st_size/1024**2,"embedding_median_ms":statistics.median(elapsed),"embedding_max_ms":max(elapsed),"synthetic_positive_min_cosine":min(positive),"negative_max_cosine":max(negatives),"source":source}
            print(json.dumps({name:records[name]},ensure_ascii=False),flush=True)
    report={"scope":"Two registration portraits, synthetic perturbations, one public unknown fixture. Not independent identity/pose accuracy or Pi latency.","models":records}
    (ROOT / "logs/face-model-comparison.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")


if __name__ == "__main__":
    main()
