from datetime import date
import unittest

from scan_schedule import is_due
from scanner_config import load_config
from pathlib import Path


class ScheduleTests(unittest.TestCase):
    def test_three_days_cross_month_boundary(self):
        schedule = {"enabled": True, "interval_days": 3, "start_date": "2026-01-30"}
        for day, expected in [(date(2026, 1, 29), False), (date(2026, 1, 30), True),
                              (date(2026, 1, 31), False), (date(2026, 2, 1), False),
                              (date(2026, 2, 2), True), (date(2026, 2, 5), True)]:
            with self.subTest(day=day):
                self.assertEqual(is_due(schedule, day), expected)

    def test_intervals_and_disabled(self):
        for interval in (1, 2, 3, 7, 14):
            schedule = {"enabled": True, "interval_days": interval, "start_date": "2026-11-01"}
            self.assertTrue(is_due(schedule, date(2026, 11, 1 + interval)))
            schedule["enabled"] = False
            self.assertFalse(is_due(schedule, date(2026, 11, 1 + interval)))

    def test_invalid_interval_rejected(self):
        for interval in (0, True, "3", 4):
            with self.assertRaises(ValueError):
                is_due({"enabled": True, "interval_days": interval, "start_date": "2026-11-24"}, date(2026, 11, 24))

    def test_profile_has_sufficient_lookback(self):
        config = load_config(Path(__file__).resolve().parents[1] / "profiles/jan-snel.json")
        self.assertGreaterEqual(config["scan"]["days"], config["schedule"]["interval_days"] + 1)
