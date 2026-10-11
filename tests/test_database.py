import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from server import AppError, Database, generate_routine_questions


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_dir.name) / "test.sqlite3")
        self.today = "2026-10-10"

    def tearDown(self):
        self.temp_dir.cleanup()

    def add_entry(self, title, estimate=60, **extra):
        return self.database.create_entry(
            {
                "date": self.today,
                "title": title,
                "estimate_minutes": estimate,
                **extra,
            }
        )

    def test_entries_persist_in_sqlite_file(self):
        created = self.add_entry("整理访谈提纲", project_name="用户研究")

        reopened = Database(self.database.path)
        day = reopened.get_day(self.today)

        self.assertTrue(self.database.path.is_file())
        self.assertEqual(day["entries"][0]["id"], created["id"])
        self.assertEqual(day["entries"][0]["title"], "整理访谈提纲")
        self.assertEqual(day["entries"][0]["project_name"], "用户研究")

    def test_only_one_timer_can_run(self):
        first = self.add_entry("任务一")
        second = self.add_entry("任务二")

        self.database.start_timer(first["id"])
        result = self.database.start_timer(second["id"])
        day = self.database.get_day(self.today)

        self.assertEqual(result["stopped_entry_id"], first["id"])
        self.assertFalse(day["entries"][0]["is_running"])
        self.assertTrue(day["entries"][1]["is_running"])
        stopped = self.database.stop_timer(second["id"])
        self.assertTrue(stopped["stopped"])

    def test_subtask_turns_parent_into_non_counting_container(self):
        parent = self.add_entry("完成市场调研", estimate=180)
        self.add_entry(
            "整理竞品清单",
            estimate=60,
            parent_entry_id=parent["id"],
        )
        self.add_entry(
            "提炼卖点",
            estimate=90,
            parent_entry_id=parent["id"],
        )

        day = self.database.get_day(self.today)
        week = self.database.get_week(self.today)
        parent_after = next(item for item in day["entries"] if item["id"] == parent["id"])

        self.assertEqual(parent_after["estimate_minutes"], 0)
        self.assertTrue(parent_after["has_children"])
        self.assertEqual(week["days"][5]["estimate_minutes"], 150)
        self.assertEqual(week["days"][5]["total_count"], 2)

    def test_close_day_carries_task_and_records_reason(self):
        entry = self.add_entry("写方案", estimate=120)

        result = self.database.close_day(
            {
                "date": self.today,
                "reflection": "需求拆得还不够细。",
                "mood": 3,
                "decisions": [
                    {
                        "entry_id": entry["id"],
                        "action": "carry",
                        "reason": "underestimated",
                        "note": "还差验证部分",
                        "target_date": "2026-10-11",
                        "next_estimate_minutes": 45,
                    }
                ],
            }
        )
        tomorrow = self.database.get_day("2026-10-11")
        week = self.database.get_week(self.today)

        self.assertEqual(result["entries"][0]["outcome"], "carried")
        self.assertEqual(result["day"]["reflection"], "需求拆得还不够细。")
        self.assertIsNotNone(result["day"]["closed_at"])
        self.assertEqual(tomorrow["entries"][0]["title"], "写方案")
        self.assertEqual(tomorrow["entries"][0]["estimate_minutes"], 45)
        self.assertEqual(week["reasons"][0]["label"], "估时偏短")

    def test_parent_is_resolved_from_child_decisions(self):
        parent = self.add_entry("制作页面", estimate=120)
        child = self.add_entry(
            "完成首屏",
            estimate=60,
            parent_entry_id=parent["id"],
        )

        closed = self.database.close_day(
            {
                "date": self.today,
                "decisions": [
                    {
                        "entry_id": child["id"],
                        "action": "carry",
                        "reason": "partial",
                        "target_date": "2026-10-11",
                        "next_estimate_minutes": 30,
                    }
                ],
            }
        )
        tomorrow = self.database.get_day("2026-10-11")

        parent_today = next(
            item for item in closed["entries"] if item["id"] == parent["id"]
        )
        self.assertEqual(parent_today["outcome"], "carried")
        self.assertEqual(len(tomorrow["entries"]), 2)
        self.assertTrue(any(item["has_children"] for item in tomorrow["entries"]))

    def test_focus_timer_expires_at_target_and_is_counted(self):
        entry = self.add_entry("完成深度工作", estimate=30)
        self.database.start_timer(entry["id"], mode="focus", focus_minutes=5)
        connection = self.database.connect()
        try:
            with connection:
                connection.execute(
                    "UPDATE time_segments SET start_at = '2000-01-01T00:00:00Z' "
                    "WHERE end_at IS NULL"
                )
        finally:
            connection.close()

        day = self.database.get_day(self.today)
        report = self.database.get_report(self.today, "week")

        self.assertIsNone(day["active_timer"])
        self.assertEqual(day["segments"][0]["duration_seconds"], 300)
        self.assertEqual(day["segments"][0]["focus_completed"], 1)
        self.assertEqual(report["focus"]["completed_count"], 1)

    def test_worklog_duration_can_be_corrected(self):
        entry = self.add_entry("测试计时修正")
        self.database.start_timer(entry["id"])
        stopped = self.database.stop_timer(entry["id"])
        day = self.database.get_day(self.today)
        segment_id = day["segments"][0]["id"]

        updated = self.database.update_segment(
            segment_id, {"duration_minutes": 35}
        )

        self.assertTrue(stopped["stopped"])
        self.assertEqual(updated["duration_seconds"], 2100)
        self.assertEqual(
            self.database.get_day(self.today)["entries"][0]["actual_seconds"],
            2100,
        )

    def test_memos_are_searchable_and_daily_reflections_join_results(self):
        memo = self.database.create_memo(
            {
                "date": self.today,
                "content": "估时要参考历史倍率",
                "tags": "估时,复盘",
            }
        )
        self.database.save_day(
            {
                "date": self.today,
                "reflection": "今天发现拆任务能降低启动阻力",
            }
        )

        estimate_results = self.database.list_memos("估时")
        reflection_results = self.database.list_memos("启动阻力")

        self.assertEqual(estimate_results[0]["id"], memo["id"])
        self.assertEqual(reflection_results[0]["kind"], "daily")

    def test_month_and_quarter_reports_share_the_same_source_data(self):
        entry = self.add_entry("完成报告", estimate=60)
        self.database.start_timer(entry["id"])
        self.database.stop_timer(entry["id"])

        month = self.database.get_report(self.today, "month")
        quarter = self.database.get_report(self.today, "quarter")

        self.assertEqual(month["start"], "2026-10-01")
        self.assertEqual(month["end"], "2026-10-31")
        self.assertEqual(quarter["start"], "2026-10-01")
        self.assertEqual(quarter["end"], "2026-12-31")
        self.assertTrue(month["insights"])
        self.assertEqual(len(quarter["days"]), 92)

    def test_daily_routines_lock_changes_behind_four_operation_challenge(self):
        questions = generate_routine_questions()
        self.assertEqual(len(questions), 3)
        for question in questions:
            for symbol in ("+", "−", "×", "÷"):
                self.assertIn(symbol, question["prompt"])
            self.assertIsInstance(question["answer"], int)

        today = date.today().isoformat()
        created = self.database.create_routine(
            {
                "title": "锻炼",
                "note": "5 分钟",
                "estimate_minutes": 5,
            }
        )
        second = self.database.create_routine(
            {"title": "阅读生财有术", "note": "5 篇", "estimate_minutes": 15}
        )
        with self.assertRaises(AppError):
            self.database.update_routine(
                created["id"], {"title": "改为散步", "estimate_minutes": 1}
            )

        challenge = self.database.create_routine_challenge()
        connection = self.database.connect()
        try:
            stored = json.loads(
                connection.execute(
                    "SELECT questions_json FROM routine_challenges WHERE id = ?",
                    (challenge["id"],),
                ).fetchone()["questions_json"]
            )
        finally:
            connection.close()
        with self.assertRaises(AppError):
            self.database.verify_routine_challenge(
                {"id": challenge["id"], "answers": [0, 0, 0]}
            )
        passed = self.database.verify_routine_challenge(
            {
                "id": challenge["id"],
                "answers": [item["answer"] for item in stored],
            }
        )
        updated = self.database.update_routine(
            created["id"],
            {
                "title": "每天锻炼",
                "note": "5 分钟",
                "estimate_minutes": 5,
                "unlock_token": passed["unlock_token"],
            },
        )
        self.database.set_routine_check(
            {"routine_id": created["id"], "date": today, "completed": True}
        )
        with self.assertRaises(AppError):
            self.database.set_routine_check(
                {
                    "routine_id": created["id"],
                    "date": "2099-01-01",
                    "completed": True,
                }
            )

        day = self.database.get_day(today)
        report = self.database.get_report(today, "week")
        routine = next(item for item in report["routines"] if item["id"] == created["id"])

        self.assertEqual(updated["title"], "每天锻炼")
        self.assertEqual(second["title"], "阅读生财有术")
        self.assertTrue(day["routines"][0]["locked"])
        self.assertTrue(day["routines"][0]["completed"])
        self.assertEqual(routine["completed_count"], 1)
        self.assertTrue(
            any(item["date"] == today and item["status"] == "done" for item in routine["days"])
        )
        self.assertTrue(self.database.get_report(today, "month")["routines"])
        self.assertTrue(self.database.get_report(today, "quarter")["routines"])

        saved = self.database.save_settings(
            {
                "profile": {
                    "display_name": "勇攀",
                    "avatar_data": "",
                    "focus_minutes": 50,
                    "break_minutes": 10,
                }
            }
        )
        reopened = Database(self.database.path)
        self.assertEqual(saved["display_name"], "勇攀")
        self.assertEqual(reopened.get_settings()["profile"]["focus_minutes"], 50)
        self.assertEqual(len(reopened.get_settings()["routines"]), 2)

    def test_note_images_round_trip_and_recent_tags(self):
        tiny_png = (
            "data:image/png;base64,"
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        )
        with self.assertRaises(AppError):
            self.database.create_memo({"date": self.today, "content": "   "})

        memo = self.database.create_memo(
            {"date": self.today, "content": "", "has_images": True, "tags": ""}
        )
        saved = self.database.create_note_image(
            {
                "owner_type": "memo",
                "owner_key": str(memo["id"]),
                "original": tiny_png,
                "thumbnail": tiny_png,
                "width": 1,
                "height": 1,
            }
        )
        original, content_type = self.database.read_note_image(saved["id"])
        thumbnail, thumbnail_type = self.database.read_note_image(
            saved["id"], thumbnail=True
        )
        self.assertEqual(content_type, "image/png")
        self.assertEqual(thumbnail_type, "image/jpeg")
        self.assertTrue(original.startswith(b"\x89PNG"))
        self.assertEqual(thumbnail, original)
        self.assertTrue((self.database.image_dir / str(saved["id"])).is_file())

        listed = next(
            item for item in self.database.list_memos("") if item["id"] == memo["id"]
        )
        self.assertEqual(listed["images"][0]["id"], saved["id"])
        cleared = self.database.update_memo(memo["id"], {"content": ""})
        self.assertEqual(cleared["content"], "")
        self.assertEqual(cleared["images"][0]["id"], saved["id"])

        day_image = self.database.create_note_image(
            {
                "owner_type": "day",
                "owner_key": self.today,
                "original": tiny_png,
                "thumbnail": tiny_png,
                "width": 1,
                "height": 1,
            }
        )
        self.assertEqual(
            self.database.get_day(self.today)["day"]["images"][0]["id"],
            day_image["id"],
        )
        self.database.save_day(
            {"date": self.today, "reflection": "今天把发现画了下来"}
        )
        daily = next(
            item
            for item in self.database.list_memos("画了下来")
            if item["kind"] == "daily"
        )
        self.assertEqual(daily["images"][0]["id"], day_image["id"])
        listed_daily = next(
            item
            for item in self.database.list_memos("")
            if item["kind"] == "daily" and item["memo_date"] == self.today
        )
        self.assertEqual(listed_daily["images"][0]["id"], day_image["id"])

        self.database.delete_note_image(saved["id"])
        self.assertFalse((self.database.image_dir / str(saved["id"])).exists())
        self.assertFalse((self.database.image_dir / f"{saved['id']}.thumb").exists())
        with self.assertRaises(AppError):
            self.database.read_note_image(saved["id"])

        doomed = self.database.create_memo(
            {"date": self.today, "content": "待删除", "has_images": True}
        )
        doomed_image = self.database.create_note_image(
            {
                "owner_type": "memo",
                "owner_key": doomed["id"],
                "original": tiny_png,
                "thumbnail": tiny_png,
                "width": 1,
                "height": 1,
            }
        )
        self.database.delete_memo(doomed["id"])
        self.assertFalse((self.database.image_dir / str(doomed_image["id"])).exists())

        with self.assertRaises(AppError):
            self.database.create_note_image(
                {
                    "owner_type": "day",
                    "owner_key": self.today,
                    "original": "not-an-image",
                    "thumbnail": tiny_png,
                }
            )
        for _ in range(8):
            self.database.create_note_image(
                {
                    "owner_type": "day",
                    "owner_key": self.today,
                    "original": tiny_png,
                    "thumbnail": tiny_png,
                    "width": 1,
                    "height": 1,
                }
            )
        with self.assertRaises(AppError):
            self.database.create_note_image(
                {
                    "owner_type": "day",
                    "owner_key": self.today,
                    "original": tiny_png,
                    "thumbnail": tiny_png,
                    "width": 1,
                    "height": 1,
                }
            )

        specs = [
            ("旧主题", "2026-10-01T00:00:00Z"),
            ("估时", "2026-10-02T00:00:00Z"),
            ("估时", "2026-10-08T00:00:00Z"),
            ("产品", "2026-10-09T00:00:00Z"),
            ("复盘", "2026-10-10T00:00:00Z"),
            ("估时", "2026-10-11T00:00:00Z"),
        ]
        created_ids = [
            self.database.create_memo(
                {"date": self.today, "content": tag, "tags": tag}
            )["id"]
            for tag, _created_at in specs
        ]
        connection = self.database.connect()
        try:
            for memo_id, (_tag, created_at) in zip(created_ids, specs):
                connection.execute(
                    "UPDATE memos SET created_at = ? WHERE id = ?",
                    (created_at, memo_id),
                )
            connection.commit()
        finally:
            connection.close()

        self.assertEqual(self.database.suggested_tags(), ["估时", "复盘", "产品"])

    def test_daily_reflection_merges_into_one_memo(self):
        tiny_png = (
            "data:image/png;base64,"
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        )
        self.database.save_day(
            {"date": self.today, "reflection": "原先写在今日感悟里"}
        )
        image = self.database.create_note_image(
            {
                "owner_type": "day",
                "owner_key": self.today,
                "original": tiny_png,
                "thumbnail": tiny_png,
                "width": 1,
                "height": 1,
            }
        )
        connection = self.database.connect()
        try:
            connection.execute(
                "DELETE FROM app_settings WHERE key = 'daily_notes_merged'"
            )
            self.database._merge_daily_notes(connection)
            connection.commit()
        finally:
            connection.close()

        day = self.database.get_day(self.today)
        merged = [
            item
            for item in self.database.list_memos("")
            if item.get("kind") == "memo" and item["content"] == "原先写在今日感悟里"
        ]
        self.assertEqual(day["day"]["reflection"], "")
        self.assertEqual(day["day"]["images"], [])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["images"][0]["id"], image["id"])

        connection = self.database.connect()
        try:
            connection.execute(
                "DELETE FROM app_settings WHERE key = 'daily_notes_merged'"
            )
            self.database._merge_daily_notes(connection)
            connection.commit()
        finally:
            connection.close()
        again = [
            item
            for item in self.database.list_memos("")
            if item.get("kind") == "memo" and item["content"] == "原先写在今日感悟里"
        ]
        self.assertEqual(len(again), 1)

if __name__ == "__main__":
    unittest.main()
