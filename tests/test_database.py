import tempfile
import unittest
from pathlib import Path

from server import Database


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


if __name__ == "__main__":
    unittest.main()
