"""Protect routing, current-frame use, identity rejection and DB boundaries."""
import sqlite3
from contextlib import closing
import tempfile
from pathlib import Path
import unittest

from glasses.core import route_query, require_fresh, select_object, match_identity, ProfileStore


class RoutingTests(unittest.TestCase):
    def test_action_and_attribute_questions_reach_vlm(self):
        for text in ["这个人拿着什么", "谁拿着杯子", "这是什么颜色", "这是什么型号", "描述一下眼前的场景", "这部电话是什么颜色", "这台机器怎么工作", "他的手机是什么颜色"]:
            self.assertEqual(route_query(text), "vlm", text)

    def test_common_object_face_and_profile_questions_have_fast_paths(self):
        for text, route in [("面前的是什么物品", "object"), ("这是什么", "object"), ("前面有什么", "object"), ("这是谁", "face"), ("他叫什么名字", "profile"), ("这个人的专业是什么", "profile")]:
            self.assertEqual(route_query(text), route)

    def test_blank_question_rejected(self):
        with self.assertRaises(ValueError):
            route_query(" \n")

    def test_private_questions_do_not_reach_visual_model(self):
        for text in ["他叫什么", "他喜欢什么", "她多大了", "他的职业是什么", "他在哪上学", "详细介绍一下他的专业", "他在做什么工作", "他研究什么", "他教什么课", "他的博士在哪里读的", "他的代表论文有哪些", "他是做什么的", "他的简介是什么", "他来自哪里", "他住在哪里"]:
            self.assertEqual(route_query(text), "profile", text)
        self.assertEqual(route_query("仔细说说这是谁"), "face")
        self.assertEqual(route_query("你认识这个人吗"), "face")

    def test_old_frames_rejected(self):
        require_fresh(9.6, now=10.0, max_age=0.75)
        with self.assertRaises(ValueError):
            require_fresh(8.0, now=10.0, max_age=0.75)

    def test_object_near_center_selected_not_largest_person(self):
        detections = [{"class_id": 0, "box": [0, 0, 120, 480], "score": .95}, {"class_id": 41, "box": [280, 200, 360, 300], "score": .8}]
        self.assertEqual(select_object(detections, 640, 480)["class_id"], 41)
        self.assertIsNone(select_object([], 640, 480))

    def test_unknown_and_ambiguous_faces_are_rejected(self):
        self.assertIsNone(match_identity([1., 0.], [("a", [0., 1.])]))
        self.assertEqual(match_identity([1., 0.], [("a", [1., 0.])]), "a")
        self.assertIsNone(match_identity([1., 0.], [("a", [1., 0.]), ("b", [.99, .01])]))

    def test_multiple_photos_of_same_person_are_not_competing_identities(self):
        self.assertEqual(match_identity([1., 0.], [("a", [1., 0.]), ("a", [.99, .01])]), "a")


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "people.sqlite3"
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("CREATE TABLE people(person_id TEXT, display_name TEXT, major TEXT)")
            conn.execute("INSERT INTO people VALUES('u1', '测试用户', 'ECE')")
        self.sql = "SELECT person_id, display_name, major FROM people WHERE person_id=:person_id LIMIT 1"

    def tearDown(self):
        self.tmp.cleanup()

    def test_read_only_parameterized_lookup(self):
        store = ProfileStore(self.path, self.sql)
        self.assertEqual(store.get("u1")["major"], "ECE")
        self.assertIsNone(store.get("u1' OR 1=1 --"))
        self.assertIsNone(store.get("unknown"))

    def test_never_create_missing_database(self):
        missing = Path(self.tmp.name) / "missing.db"
        with self.assertRaises(FileNotFoundError):
            ProfileStore(missing, self.sql).get("u1")
        self.assertFalse(missing.exists())

    def test_write_query_and_unbounded_query_rejected(self):
        for sql in ["DELETE FROM people WHERE person_id=:person_id", "SELECT * FROM people"]:
            with self.assertRaises(ValueError):
                ProfileStore(self.path, sql)
        with closing(sqlite3.connect(self.path)) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM people").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
