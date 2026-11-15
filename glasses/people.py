"""Read-only adapter for the supplied Users / Profile_Facts SQLite schema."""
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
import sqlite3
import re
import time


def resolve_image_person(relative_path: str, users: list[dict], name_ids: dict) -> dict:
    path = PurePosixPath(relative_path.replace("\\", "/"))
    identity = path.parts[0] if len(path.parts) > 1 else path.stem
    by_id = {row["person_id"]: row for row in users}
    if identity in by_id:
        return by_id[identity]
    candidates = [row for row in users if row["display_name"] == identity]
    if identity in name_ids:
        selected = by_id.get(str(name_ids[identity]))
        if selected is None or selected["display_name"] != identity:
            raise ValueError(f"姓名绑定与数据库不一致：{identity}")
        return selected
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise ValueError(f"头像没有对应的 Users 记录：{identity}")
    raise ValueError(f"姓名对应多个 user_id，请改用编号文件名或显式绑定：{identity}")


class PeopleDatabase:
    def __init__(self, path: Path, name_ids: dict):
        self.path = Path(path).resolve()
        self.name_ids = {name: str(value) for name, value in name_ids.items()}

    @contextmanager
    def connection(self):
        if not self.path.is_file():
            raise FileNotFoundError(f"人员资料库不存在：{self.path}")
        conn = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=1)
        try:
            conn.execute("PRAGMA query_only=ON")
            conn.row_factory = sqlite3.Row
            deadline = time.monotonic() + .5
            conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
            conn.execute("BEGIN")
            yield conn
        finally:
            conn.close()

    def users(self) -> list[dict]:
        with self.connection() as conn:
            return [dict(row) for row in conn.execute("SELECT CAST(user_id AS TEXT) AS person_id,name AS display_name FROM Users ORDER BY user_id")]

    def get(self, person_id: str) -> dict | None:
        with self.connection() as conn:
            row = conn.execute("SELECT CAST(user_id AS TEXT) AS person_id,name AS display_name,age,gender,introduction,experience FROM Users WHERE user_id=?", (person_id,)).fetchone()
            if row is None:
                return None
            person = dict(row)
            person["facts"] = [dict(r) for r in conn.execute("SELECT category,field,value,source_title,source_url,source_type,checked_on,note FROM Profile_Facts WHERE user_id=? ORDER BY fact_id", (person_id,))]
            existing_fields = {f["field"] for f in person["facts"]}
            for column in ["introduction", "experience"]:
                for line in (person.get(column) or "").splitlines():
                    match = re.match(r"^\s*([^:：]+)[:：]\s*(.+)$", line)
                    if match is None:
                        continue
                    key, value = (item.strip() for item in match.groups())
                    if not key or not value or key in existing_fields or key == "资料核验":
                        continue
                    categories = [("research",["研究","擅长"]),("teaching",["课程","教学"]),("education",["博士","硕士","本科","学历","毕业","教育"]),("contact",["邮箱","电话","手机"]),("appointment",["职称","职务","职位","单位"]),("employment",["经历","既往","曾任"]),("identity",["英文名"]),("publication",["论文","著作"]),("honor",["奖","会士","荣誉"])]
                    category = next((category for category,words in categories if any(word in key for word in words)), "record")
                    person["facts"].append({"category":category,"field":key,"value":value,"source_title":"Users."+column,"source_url":"","source_type":"database_user_text","checked_on":None,"note":""})
            return person

    def person_in_question(self, question: str) -> dict | None:
        users = self.users()
        mentioned = {row["display_name"] for row in users if row["display_name"] and row["display_name"] in question}
        if len(mentioned) > 1:
            raise ValueError("问题中包含多位登记用户，请一次指定一人")
        if not mentioned:
            return None
        return resolve_image_person(next(iter(mentioned)) + ".jpg", users, self.name_ids)

    @staticmethod
    def _short(text: str, limit=240):
        if len(text) <= limit:
            return text
        # Explicitly mark truncation; full evidence remains in the response details.
        return text[:limit].rstrip("，、；。 ") + "……"

    @classmethod
    def render(cls, question: str, person: dict | None):
        if person is None:
            return "资料库中没有这位用户的信息。", []
        facts = person["facts"]
        name = person["display_name"]
        field_requests = [(["年龄", "几岁", "多大"], "age", "年龄"), (["性别"], "gender", "性别")]
        for words, key, label in field_requests:
            if any(word in question for word in words):
                value = person.get(key)
                return (f"资料库登记的{label}是{value}。" if value is not None and str(value).strip() else f"资料库中没有登记{label}。"), []
        if any(word in question for word in ["名字", "姓名", "叫什么"]) and "英文" not in question:
            return f"这是{name}。", []

        categories = None
        field_terms = None
        label = "这个问题对应的信息"
        if "英文" in question:
            categories, field_terms, label = {"identity"}, ["英文名"], "英文名"
        elif any(word in question for word in ["研究", "擅长", "领域"]):
            categories, label = {"research"}, "研究方向"
        elif any(word in question for word in ["教什么", "什么课", "哪些课", "课程", "教学", "教授什么"]):
            categories, label = {"teaching"}, "课程"
            field_terms = ["课程内容"] if "内容" in question else ["课程"]
        elif any(word in question for word in ["论文", "著作", "发表", "作品"]):
            categories, label = {"publication"}, "论文"
        elif any(word in question for word in ["荣誉", "奖项", "获奖", "会士"]):
            categories, label = {"honor"}, "荣誉"
        elif any(word in question for word in ["经历", "履历", "以前", "曾经", "工作过", "既往", "加入"]):
            categories, label = {"employment"}, "经历"
        elif any(word in question for word in ["博士", "硕士", "本科", "毕业", "学历", "教育背景", "读书", "上学"]):
            categories, label = {"education"}, "教育经历"
            field_terms = [x for x in ["博士", "硕士", "本科"] if x in question] or None
        elif any(word in question for word in ["邮箱", "邮件", "电话", "联系"]):
            categories, label = {"contact"}, "联系方式"
            field_terms = ["邮箱"] if any(x in question for x in ["邮箱", "邮件"]) else ["电话"] if "电话" in question else None
        elif any(word in question for word in ["职务", "职称", "职位", "职业", "工作", "单位", "任职", "做什么的"]):
            categories, label = {"appointment"}, "职务"
        elif any(word in question for word in ["专业", "爱好", "喜欢", "生日", "出生日期", "住址", "住在", "住哪", "来自", "哪里人", "籍贯", "身高", "体重"]):
            label = next(x for x in ["专业", "爱好", "喜欢", "生日", "出生日期", "住址", "住在", "住哪", "来自", "哪里人", "籍贯", "身高", "体重"] if x in question)
            label = {"喜欢":"爱好","住在":"住址","住哪":"住址","来自":"籍贯","哪里人":"籍贯"}.get(label,label)
            # A coordination role, course or broad research field is not a recorded major.
            field_terms = [label]
            categories = set()
        else:
            categories, label = {"appointment", "research"}, "简介"

        selected = []
        seen = set()
        for fact in facts:
            if categories and fact["category"] not in categories:
                continue
            if field_terms and not any((term == fact["field"] if term in {"课程", "专业"} else term in fact["field"]) for term in field_terms):
                continue
            key = (fact["field"], fact["value"])
            if key not in seen:
                selected.append(fact)
                seen.add(key)
        if selected:
            count = 4 if "详细" in question else 2
            chosen = selected[:count]
            pieces = [f"{f['field']}：{f['value']}" + (f"（{f['note']}）" if f["note"] else "") for f in chosen]
            return cls._short("资料库记录，" + "；".join(pieces), 400 if "详细" in question else 240) + "。", selected
        # Only explicit basic-schema text fields can supply missing facts.
        raw = person.get("experience") if label in {"经历", "教育经历"} else person.get("introduction") if label == "简介" else None
        if raw:
            lines = [line for line in raw.splitlines() if line.strip() and not line.startswith("资料核验")]
            return cls._short(f"这是{name}。" + "；".join(lines[:2])) + "。", []
        return f"资料库中没有登记{label}。", []

    def answer(self, question: str, person_id: str):
        return self.render(question, self.get(person_id))
