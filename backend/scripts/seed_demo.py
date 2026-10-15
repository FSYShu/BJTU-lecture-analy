"""演示数据种子脚本（仅供本地预览 UI 效果，非生产数据）。

用法: uv run python scripts/seed_demo.py
"""
from pathlib import Path

from app.config import settings
from app.core.security import hash_password
from app.db.init_db import init_db
from app.db.models import Course, Keypoint, Mindmap, ParseTask, Summary, Transcript, User
from app.db.session import SessionLocal

DEMO_VIDEO = "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4"


def seed() -> None:
    Path(settings.storage_root, "db").mkdir(parents=True, exist_ok=True)
    init_db()

    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.username == "admin").first()
        if not admin:
            admin = User(username="admin", hashed_password=hash_password("admin123"), role="admin", display_name="管理员")
            db.add(admin)
            db.flush()
        student = db.query(User).filter(User.username == "student").first()
        if not student:
            student = User(username="student", hashed_password=hash_password("student123"), role="student", display_name="测试学生")
            db.add(student)
            db.flush()

        courses_data = [
            {"title": "高等数学 · 第3讲", "teacher_name": "张教授", "session_label": "傅里叶变换", "video_url": DEMO_VIDEO},
            {"title": "线性代数 · 第5讲", "teacher_name": "李教授", "session_label": "特征值与特征向量", "video_url": DEMO_VIDEO},
            {"title": "数据结构 · 第2讲", "teacher_name": "王教授", "session_label": "二叉树遍历", "video_url": DEMO_VIDEO},
        ]
        courses = []
        for cd in courses_data:
            c = Course(
                title=cd["title"], teacher_name=cd["teacher_name"],
                session_label=cd["session_label"], video_url=cd["video_url"], source="manual",
            )
            db.add(c)
            db.flush()
            courses.append(c)

        target = courses[0]
        if not db.query(ParseTask).filter(ParseTask.course_id == target.id).first():
            task = ParseTask(course_id=target.id, initiated_by=admin.id, status="succeeded", progress=100, current_step="persisting")
            db.add(task)
            db.flush()

            subs = [
                (0.5, 5.2, "同学们好，今天我们开始讲傅里叶变换。"),
                (5.5, 12.8, "首先回顾一下上节课的傅里叶级数。"),
                (13.0, 20.5, "傅里叶变换的定义是：一个函数可以分解成不同频率的正弦波叠加。"),
                (21.0, 28.3, "我们来看傅里叶系数公式，an 等于周期内 f(t) 乘 cos 的积分。"),
                (29.0, 36.7, "奇函数和偶函数的傅里叶系数可以简化，这是考试常考点。"),
                (37.2, 45.0, "典型例子：方波的傅里叶级数展开。"),
                (45.5, 53.8, "Parseval 定理说明了时域能量等于频域能量。"),
                (54.3, 62.0, "最后强调一下频谱的物理意义。"),
            ]
            for i, (s, e, txt) in enumerate(subs):
                db.add(Transcript(task_id=task.id, course_id=target.id, seq_index=i, text=txt,
                                  start_sec=s, end_sec=e, ai_generated=True, source_model="siliconflow-asr"))

            kps = [
                ("傅里叶变换的定义", "concept", 13.0, "将时域函数分解为频域成分的积分变换。"),
                ("傅里叶系数公式", "formula", 21.0, "an、bn 由函数与三角基的内积确定。"),
                ("求方波的傅里叶级数", "example", 37.2, "奇函数只有正弦项，系数按 1/n 衰减。"),
                ("奇偶函数系数简化", "exam_point", 29.0, "奇函数 an=0，偶函数 bn=0，可简化计算。"),
                ("Parseval 定理", "exam_point", 45.5, "能量守恒：时域平方积分等于频域系数平方和。"),
            ]
            for i, (title, cat, ts, summ) in enumerate(kps):
                db.add(Keypoint(task_id=task.id, course_id=target.id, seq_index=i, title=title,
                                category=cat, summary=summ, timestamp_sec=ts, ai_generated=True, source_model="deepseek-v3"))

            db.add(Summary(
                task_id=task.id, course_id=target.id,
                overview="本节课系统讲解傅里叶变换：从傅里叶级数推广到变换，重点推导系数公式，并通过方波例题演示展开过程，最后介绍 Parseval 定理与频谱的物理意义。",
                chapter_points='[{"chapter": "傅里叶级数回顾"},{"chapter": "傅里叶变换定义"},{"chapter": "傅里叶系数求解"},{"chapter": "奇偶函数简化"},{"chapter": "Parseval 定理"}]',
                key_details='["傅里叶系数 an、bn 的积分表达式", "奇函数只有正弦项，偶函数只有余弦项", "方波展开系数按 1/n 衰减", "Parseval 定理的能量守恒"]',
                review_hints='["重点掌握傅里叶系数求解", "理解频谱的物理意义", "熟练奇偶函数的简化技巧"]',
                ai_generated=True, source_model="deepseek-v3",
            ))

            db.add(Mindmap(
                task_id=task.id, course_id=target.id, root_topic="傅里叶变换",
                nodes='[{"module": "基本概念", "knowledge_points": [{"name": "傅里叶变换定义", "timestamp_sec": 13.0}, {"name": "频谱", "timestamp_sec": 54.3}]}, {"module": "系数求解", "knowledge_points": [{"name": "傅里叶系数公式", "timestamp_sec": 21.0}, {"name": "奇偶函数简化", "timestamp_sec": 29.0}]}, {"module": "应用", "knowledge_points": [{"name": "方波展开", "timestamp_sec": 37.2}, {"name": "Parseval 定理", "timestamp_sec": 45.5}]}]',
                ai_generated=True, source_model="deepseek-v3",
            ))

        db.commit()
        print("演示数据已就绪")
        print("  管理员：admin / admin123")
        print("  学生：  student / student123")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
