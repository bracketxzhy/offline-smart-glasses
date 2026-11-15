
import argparse

from database import (
    get_all_known_embeddings,
    get_user_profile
)

from face_processing import extract_face_embedding
from face_recognition import recognize_face


def display_person_profile(name):
    profile = get_user_profile(name)

    if profile is None:
        print("No profile information found.")
        return

    name, age, gender, introduction, experience = profile

    print("\n========== Person Information ==========")
    print("Name:", name)
    print("Age:", age)
    print("Gender:", gender)
    print("Introduction:", introduction)
    print("Experience:", experience)
    print("=========================================")


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("image_path")
    args = parser.parse_args()

    known = get_all_known_embeddings()

    new_embedding = extract_face_embedding(args.image_path)

    result = recognize_face(new_embedding, known)

    if result != "Unknown":
        display_person_profile(result)
    else:
        print("Person not registered.")

    print("Recognition result:", result)
