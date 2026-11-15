import unittest

from glasses.people import PeopleDatabase
from glasses.vlm import VLM


class ServiceContractTests(unittest.TestCase):
    def test_profile_answer_only_uses_requested_recorded_field(self):
        profile = {"person_id": "u1", "display_name": "测试用户", "age": 0, "introduction": "登记简介", "experience": None, "facts": [{"category": "contact", "field": "电话", "value": "123", "note": ""}]}
        self.assertEqual(PeopleDatabase.render("他的年龄是多少", profile)[0], "资料库登记的年龄是0。")
        self.assertEqual(PeopleDatabase.render("他喜欢什么", profile)[0], "资料库中没有登记爱好。")
        self.assertNotIn("123", PeopleDatabase.render("介绍一下他", profile)[0])

    def test_vlm_rejects_remote_endpoint_before_any_request(self):
        for url in ["https://example.com", "http://192.168.1.1", "file:///models"]:
            with self.assertRaises(ValueError):
                VLM(url)


if __name__ == "__main__":
    unittest.main()
