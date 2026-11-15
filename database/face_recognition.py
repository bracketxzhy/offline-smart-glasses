
import numpy as np


def compare_embeddings(embedding1, embedding2):
    distance = np.linalg.norm(embedding1 - embedding2)
    return distance


def recognize_face(new_embedding, known_embeddings, threshold=0.3):
    best_match = None
    min_distance = float("inf")

    for name, embedding in known_embeddings:
        distance = compare_embeddings(new_embedding, embedding)

        print(f"{name} Distance: {distance}")

        if distance < min_distance:
            min_distance = distance
            best_match = name

    if min_distance < threshold:
        print("Recognized:", best_match)
        return best_match

    else:
        print("Unknown")
        return "Unknown"
