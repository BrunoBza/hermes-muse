import json
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

from hermes_muse.host import HermesHost
from hermes_muse.service import Companion, DEFAULT_PREFERENCES
from hermes_muse.store import Store


class TestDeliveryResolution(unittest.TestCase):
    def setUp(self):
        self.base = Path("/tmp/muse-test-delivery")
        shutil.rmtree(self.base, ignore_errors=True)
        self.base.mkdir(parents=True, exist_ok=True)
        self.store = Store(self.base)
        self.host = HermesHost(self.store, plugin_root=Path(__file__).parents[1])
        template = (Path(__file__).parents[1] / "templates/PROACTIVE_PREFERENCES.md").read_text(encoding="utf-8")
        self.store.write_text("PROACTIVE_PREFERENCES.md", template)
        self.service = Companion(self.store, self.host)

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def test_default_deliver_fallback_to_bot_chat(self):
        with patch("cron.scheduler_delivery._iter_home_target_platforms", return_value=[]):
            self.assertEqual(self.host.default_deliver(), "bot-chat")

    def test_default_deliver_auto_resolves_all_when_home_channel_present(self):
        with patch("cron.scheduler_delivery._iter_home_target_platforms", return_value=["telegram"]):
            with patch("cron.scheduler_delivery._get_home_target_chat_id", return_value="123"):
                self.assertEqual(self.host.default_deliver(), "all")

    def test_explicit_preference_overrides_home_detection(self):
        self.service.preference_update({"deliver": "telegram"})
        with patch("cron.scheduler_delivery._iter_home_target_platforms", return_value=["signal"]):
            with patch("cron.scheduler_delivery._get_home_target_chat_id", return_value="+551199999999"):
                self.assertEqual(self.host.default_deliver(), "telegram")

    def test_invalid_deliver_preference_raises(self):
        with self.assertRaises(ValueError):
            self.service.preference_update({"deliver": 123})
        with self.assertRaises(ValueError):
            self.service.preference_update({"deliver": "   "})
