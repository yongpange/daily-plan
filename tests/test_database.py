import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from app.core.database import Database
from app.core.errors import AppError
from app.services.routine_questions import generate_routine_questions


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

    def test_unfinished_task_is_cut_onto_a_later_day(self):
        target = date.fromordinal(
            max(date.today().toordinal(), date(2026, 10, 11).toordinal()) + 1
        ).isoformat()
        entry = self.add_entry("还没做完的方案", estimate=45)

        moved = self.database.move_entry(entry["id"], {"date": target})
        source = self.database.get_day(self.today)
        destination = self.database.get_day(target)

        self.assertEqual(moved["moved_to"], target)
        self.assertEqual(source["entries"], [])
        self.assertEqual(destination["entries"][0]["title"], "还没做完的方案")
        self.assertEqual(destination["entries"][0]["outcome"], "planned")
        self.assertEqual(destination["entries"][0]["estimate_minutes"], 45)
        with self.assertRaises(AppError):
            self.database.move_entry(destination["entries"][0]["id"], {"date": self.today})

    def test_logged_time_stays_on_the_original_day_when_task_moves(self):
        target = date.fromordinal(
            max(date.today().toordinal(), date(2026, 10, 11).toordinal()) + 1
        ).isoformat()
        entry = self.add_entry("做了一半", estimate=30)
        self.database.start_timer(entry["id"])
        with self.assertRaises(AppError):
            self.database.move_entry(entry["id"], {"date": target})
        self.database.stop_timer(entry["id"])

        self.database.move_entry(entry["id"], {"date": target})
        source = self.database.get_day(self.today)
        destination = self.database.get_day(target)

        self.assertEqual(source["entries"][0]["outcome"], "rescheduled")
        self.assertEqual(source["entries"][0]["estimate_minutes"], 0)
        self.assertEqual(source["segments"][0]["title"], "做了一半")
        self.assertEqual(destination["entries"][0]["title"], "做了一半")
        self.assertEqual(destination["entries"][0]["outcome"], "planned")
        self.assertEqual(destination["entries"][0]["estimate_minutes"], 30)

    def test_moving_the_last_child_takes_its_parent_along(self):
        target = date.fromordinal(
            max(date.today().toordinal(), date(2026, 10, 11).toordinal()) + 1
        ).isoformat()
        parent = self.add_entry("整组还没做完")
        child = self.add_entry("其中一步", parent_entry_id=parent["id"])
        sibling = self.add_entry("另一步", parent_entry_id=parent["id"])

        self.database.move_entry(child["id"], {"date": target})
        source = self.database.get_day(self.today)
        destination = self.database.get_day(target)
        source_titles = {item["title"] for item in source["entries"]}
        destination_titles = {item["title"] for item in destination["entries"]}

        self.assertIn("另一步", source_titles)
        self.assertIn("整组还没做完", source_titles)
        self.assertNotIn("其中一步", source_titles)
        self.assertEqual(destination_titles, {"整组还没做完", "其中一步"})

        self.database.move_entry(sibling["id"], {"date": target})
        source_after = self.database.get_day(self.today)
        destination_after = self.database.get_day(target)

        self.assertFalse(
            any(item["outcome"] == "planned" for item in source_after["entries"])
        )
        self.assertEqual(
            {item["title"] for item in destination_after["entries"]},
            {"整组还没做完", "其中一步", "另一步"},
        )

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
        self.assertEqual(estimate_results[0]["read_count"], 0)
        self.assertEqual(reflection_results[0]["kind"], "daily")

    def test_memo_read_count_persists_and_clears_with_the_memo(self):
        memo = self.database.create_memo(
            {"date": self.today, "content": "估时要回头看倍率"}
        )

        first = self.database.mark_memo_read({"kind": "memo", "id": memo["id"]})
        second = self.database.mark_memo_read({"kind": "memo", "id": str(memo["id"])})
        listed = next(
            item
            for item in self.database.list_memos("倍率")
            if item["kind"] == "memo"
        )
        reopened = Database(self.database.path)
        kept = next(
            item for item in reopened.list_memos("倍率") if item["kind"] == "memo"
        )

        self.assertEqual(first["read_count"], 1)
        self.assertTrue(first["counted"])
        self.assertTrue(first["read_today"])
        self.assertEqual(second["read_count"], 1)
        self.assertFalse(second["counted"])
        self.assertEqual(listed["read_count"], 1)
        self.assertTrue(listed["read_today"])
        self.assertEqual(kept["read_count"], 1)
        self.assertEqual(kept["last_read_at"], first["last_read_at"])

        self.database.delete_memo(memo["id"])
        with self.assertRaises(AppError):
            self.database.mark_memo_read({"kind": "memo", "id": memo["id"]})
        connection = self.database.connect()
        try:
            leftover = connection.execute(
                "SELECT COUNT(*) FROM memo_reads WHERE owner_kind = 'memo' AND owner_key = ?",
                (str(memo["id"]),),
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(leftover, 0)

    def test_memo_read_counts_again_on_a_later_day(self):
        memo = self.database.create_memo(
            {"date": self.today, "content": "估时要回头看倍率"}
        )
        self.database.mark_memo_read({"kind": "memo", "id": memo["id"]})
        yesterday = datetime.now().astimezone().replace(
            hour=15, minute=0, second=0, microsecond=0
        ) - timedelta(days=1)
        stamped = (
            yesterday.astimezone(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )
        connection = self.database.connect()
        try:
            connection.execute(
                """
                UPDATE memo_reads
                SET last_read_at = ?
                WHERE owner_kind = 'memo' AND owner_key = ?
                """,
                (stamped, str(memo["id"])),
            )
            connection.commit()
        finally:
            connection.close()

        again = self.database.mark_memo_read({"kind": "memo", "id": memo["id"]})
        listed = next(
            item
            for item in self.database.list_memos("倍率")
            if item["kind"] == "memo"
        )

        self.assertTrue(again["counted"])
        self.assertEqual(again["read_count"], 2)
        self.assertTrue(listed["read_today"])
        self.assertEqual(listed["read_count"], 2)

    def test_daily_reflection_read_count_is_stored_separately(self):
        self.database.save_day(
            {"date": self.today, "reflection": "拆任务能降低启动阻力"}
        )

        marked = self.database.mark_memo_read({"kind": "daily", "id": self.today})
        again = self.database.mark_memo_read({"kind": "daily", "id": self.today})
        listed = self.database.list_memos("启动阻力")

        self.assertEqual(marked["read_count"], 1)
        self.assertEqual(again["read_count"], 1)
        self.assertFalse(again["counted"])
        self.assertEqual(listed[0]["kind"], "daily")
        self.assertEqual(listed[0]["read_count"], 1)
        self.assertTrue(listed[0]["read_today"])
        with self.assertRaises(AppError):
            self.database.mark_memo_read({"kind": "note", "id": self.today})

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

    def test_reminders_can_be_created_updated_and_removed(self):
        created = self.database.create_reminder(
            {"message": "  回信  ", "remind_at": "2099-10-15T09:30"}
        )
        self.assertEqual(created["message"], "回信")
        self.assertEqual(created["remind_at"], "2099-10-15T09:30")
        self.assertEqual(created["status"], "pending")

        with self.assertRaises(AppError):
            self.database.create_reminder(
                {"message": "太早了", "remind_at": "2000-01-01T09:30"}
            )
        with self.assertRaises(AppError):
            self.database.create_reminder({"message": "   ", "remind_at": "2099-10-15T09:30"})

        updated = self.database.update_reminder(
            created["id"],
            {"message": "改到下午", "remind_at": "2099-10-15T15:00"},
        )
        self.assertEqual(updated["message"], "改到下午")
        self.assertEqual(updated["remind_at"], "2099-10-15T15:00")
        done = self.database.update_reminder(created["id"], {"status": "done"})
        self.assertEqual(done["status"], "done")
        self.assertTrue(
            any(item["id"] == created["id"] for item in self.database.list_reminders())
        )

        self.database.delete_reminder(created["id"])
        self.assertFalse(
            any(item["id"] == created["id"] for item in self.database.list_reminders())
        )
        with self.assertRaises(AppError):
            self.database.delete_reminder(created["id"])

    def test_completed_task_remains_on_that_day(self):
        entry = self.add_entry("写完复盘明细", estimate=40)
        updated = self.database.update_entry(entry["id"], {"outcome": "completed"})
        day = self.database.get_day(self.today)
        self.assertEqual(updated["outcome"], "completed")
        self.assertEqual(day["entries"][0]["title"], "写完复盘明细")
        self.assertEqual(day["entries"][0]["outcome"], "completed")

    def test_segments_in_a_week_keep_their_task_and_time(self):
        entry = self.add_entry("对照时间轴")
        self.database.start_timer(entry["id"])
        self.database.stop_timer(entry["id"])

        rows = self.database.list_segments_between("2026-10-05", "2026-10-11")

        self.assertEqual(rows[0]["title"], "对照时间轴")
        self.assertEqual(rows[0]["plan_date"], self.today)
        self.assertEqual(rows[0]["entry_id"], entry["id"])
        self.assertIn("estimate_minutes", rows[0])
        self.assertTrue(rows[0]["start_at"])
        self.assertTrue(rows[0]["end_at"])
        with self.assertRaises(AppError):
            self.database.list_segments_between("2026-10-11", "2026-10-05")

    def test_thread_carries_a_new_sentence_into_the_next_day(self):
        opened = self.database.create_thread(
            {
                "date": self.today,
                "title": "选品结论",
                "done_when": "能讲清这个细分做不做",
                "step": "拆 10 个竞品",
                "project_name": "选品",
            }
        )
        entry = next(item for item in opened["entries"] if item["thread_id"])
        self.database.close_day(
            {
                "date": self.today,
                "decisions": [
                    {
                        "entry_id": entry["id"],
                        "action": "completed",
                        "next_step": "把缺口写成三句话",
                    }
                ],
            }
        )

        tomorrow = self.database.get_day("2026-10-11")
        step = next(item for item in tomorrow["entries"] if item["thread_id"])
        thread = tomorrow["threads"][0]

        self.assertEqual(opened["threads"][0]["featured"], True)
        self.assertEqual(opened["threads"][0]["project_name"], "选品")
        self.assertEqual(step["title"], "把缺口写成三句话")
        self.assertNotEqual(step["task_id"], entry["task_id"])
        self.assertEqual(thread["recent"][1]["title"], "拆 10 个竞品")
        self.assertEqual(thread["recent"][1]["outcome"], "completed")
        self.assertEqual(thread["recent"][0]["title"], "")

    def test_unfinished_thread_step_starts_tomorrow_from_the_stuck_point(self):
        opened = self.database.create_thread(
            {
                "date": self.today,
                "title": "选品结论",
                "done_when": "能讲清这个细分做不做",
                "step": "拆 10 个竞品",
            }
        )
        entry = next(item for item in opened["entries"] if item["thread_id"])
        self.database.close_day(
            {
                "date": self.today,
                "decisions": [
                    {
                        "entry_id": entry["id"],
                        "action": "carry",
                        "reason": "underestimated",
                        "target_date": "2026-10-11",
                        "next_estimate_minutes": 40,
                        "next_step": "先看完差评再写缺口",
                    }
                ],
            }
        )

        tomorrow = self.database.get_day("2026-10-11")
        titles = [item["title"] for item in tomorrow["entries"]]

        self.assertEqual(titles, ["先看完差评再写缺口"])
        self.assertEqual(tomorrow["entries"][0]["estimate_minutes"], 40)
        self.assertEqual(tomorrow["entries"][0]["thread_id"], entry["thread_id"])

    def test_checked_thread_step_still_asks_for_the_next_sentence(self):
        opened = self.database.create_thread(
            {
                "date": self.today,
                "title": "选品结论",
                "done_when": "能讲清这个细分做不做",
                "step": "拆 10 个竞品",
            }
        )
        entry = next(item for item in opened["entries"] if item["thread_id"])
        self.database.update_entry(entry["id"], {"outcome": "completed"})
        with self.assertRaises(AppError):
            self.database.close_day({"date": self.today, "decisions": []})

        self.database.close_day(
            {
                "date": self.today,
                "decisions": [
                    {"entry_id": entry["id"], "next_step": "把缺口写成三句话"}
                ],
            }
        )
        tomorrow = self.database.get_day("2026-10-11")
        self.assertEqual(tomorrow["entries"][0]["title"], "把缺口写成三句话")

    def test_only_two_threads_can_stay_active(self):
        first = self.database.create_thread(
            {
                "date": self.today,
                "title": "选品结论",
                "done_when": "能讲清做不做",
                "step": "拆竞品",
            }
        )
        self.database.create_thread(
            {
                "date": self.today,
                "title": "每日计划",
                "done_when": "主线能跨过明天",
                "step": "把收工写上下一句",
            }
        )
        with self.assertRaises(AppError):
            self.database.create_thread(
                {
                    "date": self.today,
                    "title": "第三条",
                    "done_when": "不该同时开着",
                    "step": "先停一条",
                }
            )

        thread_id = first["threads"][0]["id"]
        paused = self.database.update_thread(
            thread_id, {"status": "paused", "date": self.today}
        )
        self.assertEqual(
            [item["status"] for item in paused["threads"] if item["id"] == thread_id],
            ["paused"],
        )
        self.assertEqual(
            sum(1 for item in paused["threads"] if item["featured"]),
            1,
        )
        resumed = self.database.create_thread(
            {
                "date": self.today,
                "title": "学 SQL",
                "done_when": "能自己写出那天的查询",
                "step": "把连接表写一遍",
            }
        )
        self.assertEqual(
            sum(1 for item in resumed["threads"] if item["status"] == "active"),
            2,
        )

    def test_routine_and_thread_notes_can_be_listed_by_source(self):
        routine = self.database.create_routine(
            {"title": "看生财有术文章", "note": "5 篇", "estimate_minutes": 15}
        )
        opened = self.database.create_thread(
            {
                "date": self.today,
                "title": "小红书虚拟产品",
                "done_when": "能讲清怎么卖",
                "step": "拆三篇笔记",
            }
        )
        thread = opened["threads"][0]
        entry = next(item for item in opened["entries"] if item["thread_id"])
        feedback_day = date.today().isoformat()
        self.database.create_memo(
            {
                "date": feedback_day,
                "content": "达人账号往往就是店铺号",
                "routine_id": routine["id"],
            }
        )
        self.database.create_memo(
            {
                "content": "拆笔记时先看收藏数",
                "entry_id": entry["id"],
            }
        )
        self.database.create_memo(
            {"date": self.today, "content": "和这条主线无关的一句"}
        )

        routine_notes = self.database.list_memos(
            source_kind="routine", source_id=routine["id"]
        )
        thread_notes = self.database.list_memos(
            source_kind="thread", source_id=thread["id"]
        )
        sources = self.database.list_memo_sources()
        day = self.database.get_day(feedback_day)
        thread_day = self.database.get_day(self.today)

        self.assertEqual([item["content"] for item in routine_notes], ["达人账号往往就是店铺号"])
        self.assertEqual(routine_notes[0]["source_title"], "看生财有术文章")
        self.assertEqual([item["content"] for item in thread_notes], ["拆笔记时先看收藏数"])
        self.assertEqual(thread_notes[0]["source_thread_title"], "小红书虚拟产品")
        self.assertEqual(
            next(item for item in sources if item["kind"] == "routine")["count"],
            1,
        )
        self.assertEqual(day["routines"][0]["feedback_count"], 1)
        self.assertEqual(thread_day["threads"][0]["note_count"], 1)

    def test_routine_timer_is_saved_and_yields_to_a_task_timer(self):
        today = date.today().isoformat()
        routine = self.database.create_routine(
            {"title": "锻炼", "note": "5 分钟", "estimate_minutes": 5}
        )
        entry = self.database.create_entry(
            {"date": today, "title": "写方案", "estimate_minutes": 30}
        )
        self.database.start_routine_timer(
            {"routine_id": routine["id"], "date": today}
        )
        running = self.database.get_day(today)
        routine_row = next(
            item for item in running["routines"] if item["id"] == routine["id"]
        )
        self.assertTrue(routine_row["is_running"])
        self.assertEqual(running["active_timer"]["routine_id"], routine["id"])

        switched = self.database.start_timer(entry["id"])
        after = self.database.get_day(today)
        routine_after = next(
            item for item in after["routines"] if item["id"] == routine["id"]
        )

        self.assertEqual(switched["stopped_routine_id"], routine["id"])
        self.assertFalse(routine_after["is_running"])
        self.assertGreaterEqual(routine_after["actual_seconds"], 0)
        self.assertTrue(after["entries"][0]["is_running"])
        self.assertTrue(any(item.get("kind") == "routine" for item in after["segments"]))

    def test_task_notes_keep_title_link_and_share_the_task(self):
        entry = self.add_entry("整理访谈提纲")
        first = self.database.create_memo(
            {
                "content": "先把问题列出来",
                "entry_id": entry["id"],
                "note_title": "问题清单",
                "note_link": "scys.com/article/1",
            }
        )
        second = self.database.create_memo(
            {
                "content": "补充了一个例子",
                "entry_id": entry["id"],
                "note_title": "例子",
                "note_link": "https://example.com/note",
            }
        )
        notes = self.database.list_memos(task_id=entry["task_id"])

        self.assertEqual(first["source_task_id"], entry["task_id"])
        self.assertEqual(first["note_link"], "https://scys.com/article/1")
        self.assertEqual(second["source_task_id"], entry["task_id"])
        self.assertEqual(
            {item["note_title"] for item in notes},
            {"例子", "问题清单"},
        )
        with self.assertRaises(AppError):
            self.database.create_memo(
                {
                    "content": "坏链接",
                    "entry_id": entry["id"],
                    "note_link": "javascript:alert(1)",
                }
            )


class TaskNoteTests(unittest.TestCase):
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

    def test_task_note_keeps_title_estimate_and_actual_time(self):
        parent = self.add_entry("主任务留下感悟", estimate=180)
        child = self.add_entry(
            "子步骤",
            estimate=60,
            parent_entry_id=parent["id"],
        )
        self.add_entry("另一个子步骤", estimate=90, parent_entry_id=parent["id"])
        self.database.start_timer(child["id"])
        self.database.stop_timer(child["id"])
        child_after = next(
            item
            for item in self.database.get_day(self.today)["entries"]
            if item["id"] == child["id"]
        )

        memo = self.database.create_memo(
            {
                "entry_id": parent["id"],
                "content_format": "rich",
                "content": "<p>做成了<strong>关键一步</strong></p>",
                "tags": "复盘",
            }
        )

        self.assertEqual(memo["source_title"], "主任务留下感悟")
        self.assertEqual(memo["source_entry_id"], parent["id"])
        self.assertEqual(memo["source_estimate_minutes"], 150)
        self.assertEqual(memo["source_actual_seconds"], child_after["actual_seconds"])
        self.assertEqual(memo["source_plan_date"], self.today)
        self.assertEqual(memo["memo_date"], self.today)
        self.assertIn("关键一步", memo["content"])
        self.assertEqual(self.database.list_memos("主任务留下感悟")[0]["id"], memo["id"])
        with self.assertRaises(AppError):
            self.database.create_memo(
                {"entry_id": child["id"], "content": "子任务不单独记"}
            )

    def test_rich_memo_drops_unsafe_markup(self):
        memo = self.database.create_memo(
            {
                "date": self.today,
                "content_format": "rich",
                "content": '<p class="note-lg" onclick="alert(1)">重点<script>bad()</script></p>',
            }
        )

        self.assertIn("重点", memo["content"])
        self.assertIn("note-lg", memo["content"])
        self.assertNotIn("script", memo["content"].lower())
        self.assertNotIn("onclick", memo["content"])

    def test_memo_templates_can_be_saved_and_removed(self):
        created = self.database.create_memo_template(
            {"name": "做完一个任务", "content": "<p>做成了【结果】</p>"}
        )

        self.assertEqual(created["name"], "做完一个任务")
        self.assertIn("【结果】", created["content"])
        self.assertEqual(self.database.list_memo_templates()[0]["id"], created["id"])
        renamed = self.database.update_memo_template(created["id"], {"name": "任务复盘"})
        self.assertEqual(renamed["name"], "任务复盘")
        self.database.delete_memo_template(created["id"])
        self.assertEqual(self.database.list_memo_templates(), [])


if __name__ == "__main__":
    unittest.main()
