import unittest

from slack_codex_bridge.formatter import (
    TRUNCATION_SUFFIX,
    format_failure,
    format_success,
    truncate_output,
)


class TruncateOutputTests(unittest.TestCase):
    def test_returns_empty_string_when_max_chars_less_than_1(self) -> None:
        result = truncate_output("hello", 0)
        self.assertEqual(result, "")

    def test_returns_empty_string_when_max_chars_negative(self) -> None:
        result = truncate_output("hello", -5)
        self.assertEqual(result, "")

    def test_returns_full_text_when_within_limit(self) -> None:
        result = truncate_output("hello", 10)
        self.assertEqual(result, "hello")

    def test_returns_full_text_when_exactly_at_limit(self) -> None:
        result = truncate_output("hello", 5)
        self.assertEqual(result, "hello")

    def test_truncates_when_over_limit(self) -> None:
        # max_chars=20, text=30 chars, suffix=14 chars, kept=6
        long_text = "a" * 30
        result = truncate_output(long_text, 20)
        self.assertTrue(result.endswith(TRUNCATION_SUFFIX))
        self.assertEqual(len(result), 20)

    def test_returns_partial_suffix_when_max_chars_less_than_suffix_length(self) -> None:
        result = truncate_output("hello world", 5)
        self.assertEqual(result, TRUNCATION_SUFFIX[:5])

    def test_returns_partial_suffix_when_max_chars_equals_suffix_length(self) -> None:
        # When text is longer than max_chars and max_chars <= len(TRUNCATION_SUFFIX),
        # it returns truncated suffix
        long_text = "a" * 20
        result = truncate_output(long_text, len(TRUNCATION_SUFFIX))
        self.assertEqual(result, TRUNCATION_SUFFIX)


class FormatSuccessTests(unittest.TestCase):
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

    def test_formats_success_message(self) -> None:
        message = format_success(
            job_id="job123",
            duration_ms=150,
            output_text="Hello, world!",
            max_output_chars=100,
        )
        self.assertIn("Job `job123` completed in 150ms.", message)
        self.assertIn("Hello, world!", message)

    def test_replaces_empty_output_with_placeholder(self) -> None:
        message = format_success(
            job_id="job123",
            duration_ms=100,
            output_text="",
            max_output_chars=100,
        )
        self.assertIn("(no output)", message)

    def test_replaces_whitespace_only_output_with_placeholder(self) -> None:
        message = format_success(
            job_id="job123",
            duration_ms=100,
            output_text="   \n\t  ",
            max_output_chars=100,
        )
        self.assertIn("(no output)", message)


class FormatFailureTests(unittest.TestCase):
    def test_formats_failure_with_detail(self) -> None:
        message = format_failure(
            job_id="job123",
            error_type="timeout",
            error_detail="exceeded 300s timeout",
        )
        self.assertEqual(
            message,
            "Job `job123` failed (timeout). exceeded 300s timeout",
        )

    def test_formats_failure_without_detail(self) -> None:
        message = format_failure(
            job_id="job123",
            error_type="internal_error",
            error_detail=None,
        )
        self.assertEqual(message, "Job `job123` failed (internal_error).")

    def test_formats_failure_with_empty_detail(self) -> None:
        message = format_failure(
            job_id="job123",
            error_type="non_zero_exit",
            error_detail="",
        )
        self.assertEqual(message, "Job `job123` failed (non_zero_exit).")


if __name__ == "__main__":
    unittest.main()
