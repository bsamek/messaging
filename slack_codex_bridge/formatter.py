from __future__ import annotations

TRUNCATION_SUFFIX = "...[truncated]"


def truncate_output(text: str, max_chars: int) -> str:
    if max_chars < 1:
        return ""
    if len(text) <= max_chars:
        return text
    if max_chars <= len(TRUNCATION_SUFFIX):
        return TRUNCATION_SUFFIX[:max_chars]
    kept = max_chars - len(TRUNCATION_SUFFIX)
    return f"{text[:kept]}{TRUNCATION_SUFFIX}"


def format_success(
    *,
    job_id: str,
    duration_ms: int,
    output_text: str,
    max_output_chars: int,
) -> str:
    normalized_output = output_text.strip() or "(no output)"
    safe_output = truncate_output(normalized_output, max_output_chars)
    return f"Job `{job_id}` completed in {duration_ms}ms.\n{safe_output}"


def format_failure(
    *,
    job_id: str,
    error_type: str,
    error_detail: str | None,
) -> str:
    if error_detail:
        return f"Job `{job_id}` failed ({error_type}). {error_detail}"
    return f"Job `{job_id}` failed ({error_type})."
