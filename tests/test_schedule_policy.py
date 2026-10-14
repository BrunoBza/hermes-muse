import sys
import types
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from hermes_muse.scheduling import validate_watch


class SchedulePolicyTests(unittest.TestCase):
    def check(self, parsed):
        jobs = types.ModuleType("cron.jobs")
        jobs.parse_schedule = lambda _: parsed
        clock = types.ModuleType("hermes_time")
        clock.now = lambda: datetime.now(timezone.utc)
        with patch.dict(sys.modules, {"cron.jobs": jobs, "hermes_time": clock}):
            return validate_watch("fixture")

    def test_all_minute_hour_slots_and_midnight_not_just_next_two(self):
        for expr in [
            "*/31 * * * *",
            "0,5 1,13 * * *",
            "10,50 0,23 * * MON",
            "* * * * *",
            "0 0 * * * *",
        ]:
            with self.subTest(expr=expr), self.assertRaises(ValueError):
                self.check({"kind": "cron", "expr": expr})
        for expr in ["0,30 * * * *", "0 0 * * *", "0 */2 * * MON-FRI"]:
            self.assertEqual(self.check({"kind": "cron", "expr": expr})["expr"], expr)

    def test_once_exempt_interval_floor(self):
        self.assertEqual(self.check({"kind": "once"})["kind"], "once")
        with self.assertRaises(ValueError):
            self.check({"kind": "interval", "minutes": 29.99})
        self.assertEqual(self.check({"kind": "interval", "minutes": 30})["minutes"], 30)
