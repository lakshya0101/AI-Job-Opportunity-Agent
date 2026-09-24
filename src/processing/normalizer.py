from datetime import datetime, timezone
from typing import Any, Dict

from src.models.job import Job


def clean_text(value: Any) -> str:
    """Convert a value to clean text."""
    if value is None:
        return ""

    return " ".join(str(value).split())


def normalize_list(value: Any) -> list[str]:
    """Normalize a value into a list of clean strings."""
    if value is None:
        return []

    if isinstance(value, str):
        return [clean_text(value)] if clean_text(value) else []

    if isinstance(value, (list, tuple, set)):
        return [
            clean_text(item)
            for item in value
            if clean_text(item)
        ]

    return [clean_text(value)]


def normalize_job(raw: Dict[str, Any]) -> Job:
    """
    Convert raw job data from any source into the standard Job model.
    """

    now = datetime.now(timezone.utc).isoformat()

    return Job(
        company=clean_text(raw.get("company")),
        title=clean_text(raw.get("title")),

        location=clean_text(raw.get("location")) or "Not specified",
        work_mode=clean_text(raw.get("work_mode")) or None,

        experience=clean_text(raw.get("experience")) or None,
        eligibility=clean_text(raw.get("eligibility")) or None,
        compensation=clean_text(raw.get("compensation")) or None,

        posting_date=clean_text(raw.get("posting_date")) or None,
        deadline=clean_text(raw.get("deadline")) or None,

        description=clean_text(raw.get("description")) or None,

        source=clean_text(raw.get("source")) or None,
        application_url=clean_text(raw.get("application_url")) or None,
        careers_url=clean_text(raw.get("careers_url")) or None,

        recruiter_name=clean_text(raw.get("recruiter_name")) or None,
        recruiter_email=clean_text(raw.get("recruiter_email")) or None,

        skills=normalize_list(raw.get("skills")),

        first_seen=raw.get("first_seen") or now,
        last_seen=now,

        match_score=float(raw.get("match_score", 0.0)),
        match_reason=clean_text(raw.get("match_reason")) or None,

        is_new=bool(raw.get("is_new", True)),
        is_updated=bool(raw.get("is_updated", False)),
        is_urgent=bool(raw.get("is_urgent", False)),
    )
