# SQLite 与头像自动登记

实际数据源：`database/smart_glasses.db`。

- `Users(user_id,name,age,gender,introduction,experience,created_at)`
- `Profile_Facts(fact_id,user_id,category,field,value,source_title,source_url,source_type,checked_on,note)`
- 旧 `Face_Embeddings` 保留不修改，不把其中其他模型向量用于新识别流程。

运行时以mode=ro、query_only、参数绑定和查询预算读取；只在自有 `data/identity-cache.sqlite3` 写派生模板。年龄/性别等为空时不推测。

## 对应与同步

头像文件名为唯一姓名或user_id；多头像放 `images/<user_id>/`。重名需编号或显式配置 `identity_name_ids`。

启动和后台约2秒扫描；以内容SHA-256检测替换，单脸提取成功后用事务更新派生图库。删除、损坏或无法对应的图片不继续保留旧模板；界面显示错误。每次资料查询重新读SQLite，资料修改无须重启。

## 资料问答

研究→research；课程→teaching；学历→education；既往工作→employment；登记职务→appointment；论文→publication；荣誉→honor；联系方式→contact。原字段、值、日期与备注保留在回答详情；历史任职不会自动改称今天的事实。

新用户没有Profile_Facts时，Users.introduction/experience可使用明确的逐行字段：

```text
研究方向：机器人感知
专业：ECE
邮箱：example@example.com
```

这些字段标记来源为Users.introduction/Users.experience，不伪造网址或核验日期。一般介绍可引用简介原文；未登记的信息明确返回没有登记，不把专业协调职务当成学位专业。

明确姓名可直接查库；“他/她”依赖当前画面中单个已识别人脸。多人、未知人脸和已删除人员不会拿其他人的资料回答。

## 新增流程

在Users创建资料，再放有效头像即可。不要反复运行旧脚本重提新模型特征：旧register_user每次会插入一行，database.py主入口还会清理无旧Face_Embeddings的人员。本流程从原图自动建立统一512维缓存，原SQLite、头像和旧向量文件不做清理。
