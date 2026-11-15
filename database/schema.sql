BEGIN;

CREATE TABLE Users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    age INTEGER, gender TEXT, introduction TEXT, experience TEXT);

CREATE TABLE Face_Embeddings (
    face_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    embedding_path TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES Users(user_id)
);

CREATE TABLE Profile_Facts (
            fact_id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES Users(user_id),
            category TEXT NOT NULL, field TEXT NOT NULL, value TEXT NOT NULL,
            source_title TEXT NOT NULL, source_url TEXT NOT NULL, source_type TEXT NOT NULL,
            checked_on TEXT NOT NULL, note TEXT NOT NULL,
            UNIQUE(user_id,category,field,value,source_url));

COMMIT;
