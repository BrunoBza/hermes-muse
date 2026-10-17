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
            "0/5 * * * *",
            "5/10 * * * *",
            "0/1 * * * *",
            "* 0/1 * * *",
            "0,15 0/2 * * *",
            "10-20/5 * * * *",
        ]:
            with self.subTest(expr=expr), self.assertRaises(ValueError):
                self.check({"kind": "cron", "expr": expr})
        # N/step expands like croniter: 0 0/1 = hourly (60 min apart) and 0/30 = :00 and :30.
        for expr in ["0,30 * * * *", "0 0 * * *", "0 */2 * * MON-FRI", "0 0/1 * * *", "0/30 * * * *", "15 3/6 * * *"]:
            self.assertEqual(self.check({"kind": "cron", "expr": expr})["expr"], expr)

    def test_once_exempt_interval_floor(self):
        self.assertEqual(self.check({"kind": "once"})["kind"], "once")
        with self.assertRaises(ValueError):
            self.check({"kind": "interval", "minutes": 29.99})
        self.assertEqual(self.check({"kind": "interval", "minutes": 30})["minutes"], 30)


class CroniterAgreementTests(unittest.TestCase):
    """The proof must agree with core's actual cron engine wherever croniter is installed."""

    @unittest.skipUnless(__import__("importlib.util").util.find_spec("croniter"), "croniter not installed")
    def test_acceptance_matches_actual_fire_spacing(self):
        from croniter import croniter
        start = datetime(2026, 10, 17, tzinfo=timezone.utc)
        for expr in ["0/5 * * * *", "5/10 * * * *", "0 0/1 * * *", "0/30 * * * *", "*/31 * * * *",
                     "10-20/5 * * * *", "0,15 0/2 * * *", "15 3/6 * * *", "0,30 * * * *", "45 23 * * *",
                     "0/45 * * * *", "50 0/1 * * *", "0 0,23 * * *", "29/30 * * * *"]:
            it = croniter(expr, start)
            fires = [it.get_next(datetime) for _ in range(200)]
            spacing = min((b - a).total_seconds() / 60 for a, b in zip(fires, fires[1:]))
            with self.subTest(expr=expr, spacing=spacing):
                try:
                    SchedulePolicyTests.check(self, {"kind": "cron", "expr": expr})
                    accepted = True
                except ValueError:
                    accepted = False
                self.assertEqual(accepted, spacing >= 30)
