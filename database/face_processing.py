
import cv2
import numpy as np
import os
from insightface.app import FaceAnalysis
from database import (
    register_user,
    get_user_id,
    add_embedding
)


app = FaceAnalysis(
    name="buffalo_l",
    providers=["CPUExecutionProvider"]
)

app.prepare(ctx_id=-1, det_size=(640, 640))

print("Face recognition model loaded successfully!")


def extract_face_embedding(image_path):
    image = cv2.imread(image_path)

    if image is None:
        raise FileNotFoundError("Cannot read image: " + image_path)

    faces = app.get(image)

    if len(faces) == 0:
        raise ValueError("No face detected!")

    if len(faces) > 1:
        raise ValueError("More than one face detected!")

    embedding = faces[0].normed_embedding

    return embedding.astype(np.float32)


def save_face_embedding(embedding, filename):
    folder = os.path.join(os.path.dirname(__file__), "embeddings")
    os.makedirs(folder, exist_ok=True)

    file_path = os.path.join(folder, filename)
    np.save(file_path, embedding)

    return os.path.join("embeddings", filename)


def register_face(name, image_path, filename):
    embedding = extract_face_embedding(image_path)

    embedding_path = save_face_embedding(embedding, filename)

    register_user(name)

    user_id = get_user_id(name)

    add_embedding(user_id, embedding_path)

    print("User registered:", name)
    print("Embedding saved:", embedding_path)


def register_all_faces():
    image_folder = os.path.join(
        os.path.dirname(__file__),
        "images"
    )

    extensions = (".jpg", ".jpeg", ".png", ".bmp", ".webp")

    success_count = 0
    failed_count = 0

    for filename in sorted(os.listdir(image_folder)):

        if not filename.lower().endswith(extensions):
            continue

        image_path = os.path.join(image_folder, filename)

        name = os.path.splitext(filename)[0]

        try:
            register_face(
                name,
                image_path,
                name + ".npy"
            )

            success_count += 1

        except Exception as e:
            print("Failed:", filename, "-", e)
            failed_count += 1

    print("\nRegistration completed!")
    print("Successful:", success_count)
    print("Failed:", failed_count)


if __name__ == "__main__":
    register_all_faces()
