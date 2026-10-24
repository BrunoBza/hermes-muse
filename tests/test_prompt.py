import re
import unittest
from pathlib import Path

PROMPT = (Path(__file__).resolve().parents[1] / "prompts/system.md").read_text(encoding="utf-8")


class SystemPromptTest(unittest.TestCase):
    def test_fits_registered_section_limit(self):
        self.assertLessEqual(len(PROMPT), 4000)  # register_system_prompt_section(max_chars=4000)

    def test_delegation_guidance_is_generic(self):
        self.assertIn("one or two steps", PROMPT)
        self.assertIn("asynchronously", PROMPT)
        self.assertNotIn("short work", PROMPT)
        self.assertIn("Dispatch quietly", PROMPT)
        self.assertIsNone(re.search(r"delegate_task|paseo|claude|gpt|/Users/", PROMPT, re.I))


class ProactiveWatchPromptTest(unittest.TestCase):
    """Reported 2026-10-24: weak models skipped the field list, mis-shaped records and resent identical failing calls."""
    TEXT = (Path(__file__).resolve().parents[1] / "prompts/proactive-watch.md").read_text(encoding="utf-8")

    def test_no_longer_tells_the_model_to_skip_the_documentation(self):
        self.assertNotIn("Do not rediscover unchanged tool schemas", self.TEXT)
        self.assertIn("read the Muse field lists in the companion references before writing records", self.TEXT)

    def test_field_list_error_handling_and_envelope_rules_are_explicit(self):
        for needle in ("references/proactivity.md", "only `action` and `data`", "never beside `action`",
                       "`section` belongs to context/status", "`kind` and `id` to content_read/content_write",
                       "source_check needs no `started_at`", "never resend the same arguments", "`Fix:` text"):
            self.assertIn(needle, self.TEXT)

    def test_first_line_is_unchanged(self):
        self.assertTrue(self.TEXT.startswith("Use companion references/context.md: context/status are section directories."))


if __name__ == "__main__":
    unittest.main()
