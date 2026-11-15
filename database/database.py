
import sqlite3
import numpy as np
import os
import json
from contextlib import contextmanager


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "smart_glasses.db")


@contextmanager
def database_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")

    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def register_user(name):
    with database_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
        INSERT INTO Users (name)
        VALUES (?)
        """, (name,))


def get_users():
    with database_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM Users")
        results = cursor.fetchall()

    return results


def get_user_by_name(name):
    with database_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
        SELECT * FROM Users
        WHERE name = ?
        """, (name,))

        result = cursor.fetchone()

    return result


def get_user_id(name):
    with database_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
        SELECT user_id
        FROM Users
        WHERE name = ?
        """, (name,))

        result = cursor.fetchone()

    if result is None:
        return None

    return result[0]


def get_user_embeddings(user_id):
    with database_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
        SELECT embedding_path
        FROM Face_Embeddings
        WHERE user_id = ?
        """, (user_id,))

        results = cursor.fetchall()

    return [row[0] for row in results]


def add_embedding(user_id, embedding_path):
    with database_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
        INSERT INTO Face_Embeddings (user_id, embedding_path)
        VALUES (?, ?)
        """, (user_id, embedding_path))


def get_all_known_embeddings():
    with database_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
        SELECT Users.name, Face_Embeddings.embedding_path
        FROM Users
        JOIN Face_Embeddings
        ON Users.user_id = Face_Embeddings.user_id
        """)

        results = cursor.fetchall()

    known_embeddings = []

    for name, path in results:
        full_path = os.path.join(BASE_DIR, path)

        if os.path.exists(full_path):
            embedding = np.load(full_path)
            known_embeddings.append((name, embedding))
        else:
            print("File not found:", full_path)

    return known_embeddings


def add_profile_columns():
    with database_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(Users)")
        columns = [row[1] for row in cursor.fetchall()]

        new_columns = {
            "age": "INTEGER",
            "gender": "TEXT",
            "introduction": "TEXT",
            "experience": "TEXT"
        }

        for column, data_type in new_columns.items():
            if column not in columns:
                cursor.execute(
                    f"ALTER TABLE Users ADD COLUMN {column} {data_type}"
                )

    print("Profile columns added successfully!")


def update_user_profile(name, age, gender, introduction, experience):
    with database_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
        UPDATE Users
        SET age = ?,
            gender = ?,
            introduction = ?,
            experience = ?
        WHERE name = ?
        """, (age, gender, introduction, experience, name))

        updated = cursor.rowcount > 0

    if updated:
        print("Profile updated:", name)
    else:
        print("User not found:", name)


def get_user_profile(name):
    with database_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
        SELECT name, age, gender, introduction, experience
        FROM Users
        WHERE name = ?
        """, (name,))

        result = cursor.fetchone()

    return result


def import_profiles_from_json():
    file_path = os.path.join(BASE_DIR, "profiles.json")

    with open(file_path, "r", encoding="utf-8") as file:
        profiles = json.load(file)

    for person in profiles:
        update_user_profile(
            person["name"],
            person.get("age"),
            person.get("gender"),
            person.get("introduction"),
            person.get("experience")
        )

    print("Profile import completed!")


def cleanup_old_data():
    with database_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
        SELECT face_id, user_id, embedding_path
        FROM Face_Embeddings
        """)

        records = cursor.fetchall()

        deleted_embeddings = 0

        for face_id, user_id, path in records:
            full_path = os.path.join(BASE_DIR, path)

            if not os.path.exists(full_path):
                cursor.execute("""
                DELETE FROM Face_Embeddings
                WHERE face_id = ?
                """, (face_id,))

                deleted_embeddings += 1

        cursor.execute("""
        DELETE FROM Users
        WHERE NOT EXISTS (
            SELECT 1
            FROM Face_Embeddings
            WHERE Face_Embeddings.user_id = Users.user_id
        )
        """)

        deleted_users = cursor.rowcount

    print("Cleanup completed!")
    print("Deleted embedding records:", deleted_embeddings)
    print("Deleted users:", deleted_users)


if __name__ == "__main__":
    cleanup_old_data()
