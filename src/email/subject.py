from typing import Optional


def build_subject(
    report_date: str,
    new_count: int = 0,
    apply_first_count: int = 0,
    prefix: str = "🚀 Daily Job Opportunities",
) -> str:
    """
    Build a structured, descriptive daily email subject line.
    
    Example output:
    '🚀 Daily Job Opportunities — 01 Oct 2026 | 5 New | 10 Apply First'
    """
    parts = [f"{prefix} — {report_date}"]

    if new_count > 0:
        parts.append(f"{new_count} New")
    if apply_first_count > 0:
        parts.append(f"{apply_first_count} Apply First")

    return " | ".join(parts)
