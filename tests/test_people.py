from contextlib import closing
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest

from glasses.people import PeopleDatabase, resolve_image_person


class PeopleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.path = self.root / "people.db"
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.executescript("""
            CREATE TABLE Users(user_id INTEGER PRIMARY KEY,name TEXT,age INTEGER,gender TEXT,introduction TEXT,experience TEXT);
            INSERT INTO Users VALUES(1,'测试甲',NULL,NULL,'登记的简介','登记的经历');
            INSERT INTO Users VALUES(2,'测试乙',22,NULL,'另一人简介',NULL);
            CREATE TABLE Profile_Facts(fact_id INTEGER PRIMARY KEY,user_id INTEGER,category TEXT,field TEXT,value TEXT,source_title TEXT,source_url TEXT,source_type TEXT,checked_on TEXT,note TEXT);
            INSERT INTO Profile_Facts VALUES(1,1,'research','研究方向','图像处理','测试来源','https://example.invalid/source','test','2026-11-07','仅测试记录');
            INSERT INTO Profile_Facts VALUES(2,1,'teaching','课程','数据库课程','测试课程来源','https://example.invalid/course','test','2026-11-07','2025课程大纲');
            """)
        self.store = PeopleDatabase(self.path, {})

    def tearDown(self):
        self.tmp.cleanup()

    def test_evidence_is_selected_without_inventing_other_fields(self):
        text, evidence = self.store.answer("他研究什么", "1")
        self.assertIn("图像处理", text)
        self.assertNotIn("数据库课程", text)
        self.assertEqual(evidence[0]["source_title"], "测试来源")
        self.assertIn("2025课程大纲", self.store.answer("他教什么课", "1")[0])
        self.assertIn("没有登记年龄", self.store.answer("他多大了", "1")[0])

    def test_database_changes_are_visible_and_reads_do_not_modify_file(self):
        before = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.assertIn("22", self.store.answer("年龄", "2")[0])
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(), before)
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("UPDATE Users SET age=23 WHERE user_id=2")
        self.assertIn("23", self.store.answer("年龄", "2")[0])

    def test_duplicate_names_require_explicit_mapping(self):
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("INSERT INTO Users VALUES(3,'测试甲',NULL,NULL,NULL,NULL)")
        users = self.store.users()
        with self.assertRaises(ValueError):
            resolve_image_person("测试甲.jpg", users, {})
        self.assertEqual(resolve_image_person("测试甲.jpg", users, {"测试甲": "1"})["person_id"], "1")
        self.assertEqual(resolve_image_person("3/正面.jpg", users, {})["person_id"], "3")

    def test_unknown_image_and_ambiguous_question_are_explicit(self):
        with self.assertRaises(ValueError):
            resolve_image_person("未登记.jpg", self.store.users(), {})
        self.assertEqual(self.store.person_in_question("测试乙多大了")["person_id"], "2")
        with self.assertRaises(ValueError):
            self.store.person_in_question("测试甲和测试乙分别是谁")

    def test_new_users_text_profile_fields_work_without_fact_import_script(self):
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("UPDATE Users SET introduction=? WHERE user_id=2", ("研究方向：机器人感知\n专业：ECE\n爱好：绘画",))
        answer, evidence = self.store.answer("他研究什么", "2")
        self.assertIn("机器人感知", answer)
        self.assertEqual(evidence[0]["source_title"], "Users.introduction")
        self.assertIn("ECE", self.store.answer("他的专业是什么", "2")[0])


if __name__ == "__main__":
    unittest.main()
