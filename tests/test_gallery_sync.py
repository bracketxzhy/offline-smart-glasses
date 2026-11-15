from contextlib import closing
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
import time


@unittest.skipUnless(os.getenv("GLASSES_MODEL_TESTS") == "1", "Real face model integration")
class GallerySyncTests(unittest.TestCase):
    def setUp(self):
        import cv2
        from glasses.people import PeopleDatabase
        from glasses.vision import FaceRecognizer
        from glasses.gallery import GallerySync
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = Path(__file__).resolve().parents[1]
        self.images = self.root / "images"
        self.images.mkdir()
        self.db = self.root / "people.db"
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.executescript("CREATE TABLE Users(user_id INTEGER PRIMARY KEY,name TEXT,age INTEGER,gender TEXT,introduction TEXT,experience TEXT); INSERT INTO Users VALUES(1,'测试用户',20,NULL,NULL,NULL); CREATE TABLE Profile_Facts(fact_id INTEGER PRIMARY KEY,user_id INTEGER,category TEXT,field TEXT,value TEXT,source_title TEXT,source_url TEXT,source_type TEXT,checked_on TEXT,note TEXT);")
        self.faces = FaceRecognizer(self.project / "models/face", self.root / "cache.db")
        self.store = PeopleDatabase(self.db, {})
        self.sync = GallerySync(self.store, self.images, self.faces, interval=.1)
        self.original = cv2.imread(str(self.project / "data/fixtures/lena.jpg"))
        shutil.copyfile(self.project / "data/fixtures/lena.jpg", self.images / "测试用户.jpg")

    def tearDown(self):
        self.sync.stop()
        self.tmp.cleanup()

    @unittest.skipUnless(os.getenv("GLASSES_TEST_PORTRAIT"), "Second face-test image")
    def test_add_user_without_restart_and_existing_user_kept(self):
        import cv2
        import numpy as np
        self.sync.start()
        deadline = time.monotonic()+3
        while self.sync.status()["registered_people"] != 1 and time.monotonic()<deadline:
            time.sleep(.05)
        self.assertEqual(self.faces.identify(self.original)["person_id"], "1")
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute("INSERT INTO Users VALUES(2,'新增用户',NULL,NULL,NULL,NULL)")
        source = Path(os.environ["GLASSES_TEST_PORTRAIT"])
        shutil.copyfile(source, self.images / "新增用户.jpg")
        deadline = time.monotonic()+3
        while self.sync.status()["registered_people"] != 2 and time.monotonic()<deadline:
            time.sleep(.05)
        status = self.sync.status()
        image = cv2.imdecode(np.fromfile(source,dtype=np.uint8),cv2.IMREAD_COLOR)
        self.assertEqual(status["registered_people"], 2)
        self.assertEqual(self.faces.identify(image)["person_id"], "2")
        self.assertEqual(self.faces.identify(self.original)["person_id"], "1")

    def test_changed_or_removed_photo_never_uses_old_template(self):
        self.sync.sync_once()
        target = self.images / "测试用户.jpg"
        target.write_bytes(b"incomplete image")
        status = self.sync.sync_once()
        self.assertEqual(status["registered_people"], 0)
        self.assertEqual(len(status["errors"]), 1)
        self.assertEqual(self.faces.identify(self.original)["status"], "unknown")
        shutil.copyfile(self.project / "data/fixtures/lena.jpg", target)
        self.sync.sync_once()
        self.assertEqual(self.faces.identify(self.original)["person_id"], "1")
        target.unlink()
        self.sync.sync_once()
        self.assertEqual(self.faces.identify(self.original)["status"], "unknown")

    def test_removed_database_user_is_not_identified_from_leftover_photo(self):
        self.sync.sync_once()
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute("DELETE FROM Users WHERE user_id=1")
        self.sync.sync_once()
        self.assertEqual(self.faces.identify(self.original)["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
