import unittest

from slack_codex_bridge.formatter import TRUNCATION_SUFFIX, format_success


class FormatterTests(unittest.TestCase):
    def test_output_truncation_behavior(self) -> None:
        message = format_success(
            job_id="abc123",
            duration_ms=42,
            output_text="x" * 100,
            max_output_chars=30,
        )
        body = message.split("\n", 1)[1]
        self.assertEqual(len(body), 30)
        self.assertTrue(body.endswith(TRUNCATION_SUFFIX))


if __name__ == "__main__":
    unittest.main()
