import math
from contextlib import closing
from pathlib import Path
import re
import sqlite3
import time


def route_query(text: str, *, known_person=False) -> str:
    text = re.sub(r"[\s，。？！?!、]", "", text)
    if not text:
        raise ValueError("问题不能为空")
    # Distinguish private fields from homonymous object/action questions.
    # "详细介绍他的专业" stays grounded; "电话是什么颜色" is visual.
    if any(x in text for x in ["颜色", "型号", "形状", "材质", "外观", "品牌"]):
        return "vlm"
    person_context = known_person or any(x in text for x in ["他", "她", "这个人", "那个人", "这位", "那位", "用户", "同学", "老师", "前面的人", "眼前的人", "面前的人"])
    distinct_private_field = any(x in text for x in ["专业", "年龄", "爱好", "职业", "学校", "资料", "简介", "生日", "出生日期", "性别", "住址", "籍贯", "身高", "体重", "邮箱", "研究方向", "研究领域", "论文", "学历", "博士", "硕士", "本科", "教育背景", "职称", "职务", "履历", "获奖", "荣誉", "会士", "英文名"])
    contextual_private_field = person_context and any(x in text for x in ["名字", "姓名", "叫什么", "几岁", "多大", "喜欢", "工作", "做什么的", "上学", "读书", "电话", "介绍", "研究", "教什么", "课程", "哪些课", "什么课", "经历", "毕业", "奖项", "任职", "单位", "擅长", "来自", "哪里人", "住在", "住哪", "加入", "哪一年"])
    if distinct_private_field or contextual_private_field:
        return "profile"
    if any(x in text for x in ["是谁", "谁是", "认识他", "认识她", "认得他", "认得她"]) or (person_context and any(x in text for x in ["认识", "认得"])):
        return "face"
    if any(x in text for x in ["拿着", "拿了", "手里", "正在", "在做", "颜色", "型号", "为什么", "怎么", "描述", "仔细", "详细", "几个人", "多少人"]):
        return "vlm"
    if any(x in text for x in ["是什么", "是啥", "有什么", "有啥", "哪些东西", "什么物品", "什么东西"]):
        return "object"
    return "vlm"


def require_fresh(timestamp: float, *, now: float | None = None, max_age: float = .75):
    age = (time.monotonic() if now is None else now) - timestamp
    if age > max_age or age < -.1:
        raise ValueError("摄像头画面已过期，请检查摄像头连接")


def select_object(detections: list[dict], width: int, height: int):
    if not detections:
        return None
    def rank(d):
        x1, y1, x2, y2 = d["box"]
        distance = (((x1 + x2) / 2 - width / 2) / width) ** 2 + (((y1 + y2) / 2 - height / 2) / height) ** 2
        return distance - d["score"] * .03
    return min(detections, key=rank)


def match_identity(vector, gallery, threshold: float = .50, margin: float = .08):
    def cosine(a, b):
        if len(a) != len(b):
            raise ValueError("人脸特征维度不一致")
        denominator = math.sqrt(sum(x*x for x in a) * sum(x*x for x in b))
        return sum(x*y for x, y in zip(a, b)) / denominator if denominator else -1.
    best_by_person = {}
    for person_id, feature in gallery:
        score = cosine(vector, feature)
        best_by_person[person_id] = max(score, best_by_person.get(person_id, -1.))
    scores = sorted([(score, person_id) for person_id, score in best_by_person.items()], reverse=True)
    if not scores or scores[0][0] < threshold:
        return None
    if len(scores) > 1 and scores[0][0] - scores[1][0] < margin:
        return None
    return scores[0][1]


class ProfileStore:
    """Teammate-owned DB: explicit SELECT returning person_id and display_name."""
    def __init__(self, path: str | Path, query: str):
        if not re.match(r"^\s*SELECT\b", query, re.IGNORECASE) or ":person_id" not in query:
            raise ValueError("资料查询必须为带 :person_id 参数的单条 SELECT")
        self.path = Path(path).resolve()
        self.query = query

    def get(self, person_id: str) -> dict | None:
        if not self.path.is_file():
            raise FileNotFoundError(f"资料数据库不存在：{self.path}")
        with closing(sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=1)) as conn:
            conn.execute("PRAGMA query_only=ON")
            conn.enable_load_extension(False)
            conn.row_factory = sqlite3.Row
            deadline = time.monotonic() + .25
            conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
            row = conn.execute(self.query, {"person_id": person_id}).fetchone()
            if row is None:
                return None
            result = dict(row)
            if "person_id" not in result or "display_name" not in result:
                raise ValueError("查询结果必须含 person_id 和 display_name，可用 SQL AS 映射")
            if str(result["person_id"]) != person_id:
                raise ValueError("资料查询返回了不匹配的用户编号")
            return result
