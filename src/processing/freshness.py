from datetime import datetime, timezone
from typing import Optional

from src.models.job import Job


def parse_date(value: Optional[str]) -> Optional[datetime]:
    """
    Convert common date formats into a timezone-aware datetime.
    """

    if not value:
        return None

    value = value.strip()

    formats = [
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%d %b %Y",
        "%d %B %Y",
    ]

    for fmt in formats:
        try:
            parsed = datetime.strptime(value, fmt)

            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)

            return parsed

        except ValueError:
            continue

    return None


def days_since(date_value: Optional[str]) -> Optional[int]:
    """
    Return the number of days since a given date.
    """

    parsed = parse_date(date_value)

    if parsed is None:
        return None

    now = datetime.now(timezone.utc)

    return max(0, (now - parsed).days)


def is_expired(job: Job) -> bool:
    """
    Determine whether a job's application deadline has passed.
    """

    if not job.deadline:
        return False

    deadline = parse_date(job.deadline)

    if deadline is None:
        return False

    return deadline < datetime.now(timezone.utc)


def classify_freshness(job: Job) -> str:
    """
    Classify a job according to its freshness.

    Categories:
        NEW_TODAY
        FRESH
        ACTIVE
        OLDER_ACTIVE
        EXPIRED
        UNKNOWN
    """

    if is_expired(job):
        return "EXPIRED"

    age = days_since(job.posting_date)

    if age is None:
        return "UNKNOWN"

    if age == 0:
        return "NEW_TODAY"

    if age <= 3:
        return "FRESH"

    if age <= 7:
        return "ACTIVE"

    if age <= 14:
        return "OLDER_ACTIVE"

    return "OLDER"


def is_reportable(job: Job) -> bool:
    """
    Decide whether a job should appear in the daily report.
    """

    category = classify_freshness(job)

    if category in {"NEW_TODAY", "FRESH"}:
        return True

    if category == "ACTIVE" and job.match_score >= 70:
        return True

    if category == "OLDER_ACTIVE" and job.match_score >= 85:
        return True

    return False

def mark_freshness(job: Job) -> Job:
    """
    Update job flags based on freshness.
    """

    category = classify_freshness(job)

    job.is_urgent = False

    if category == "NEW_TODAY":
        job.is_new = True

    elif category == "FRESH":
        job.is_new = True

    elif category in {"ACTIVE", "OLDER_ACTIVE"}:
        job.is_new = False

    elif category == "EXPIRED":
        job.is_new = False

    # Deadline within 2 days is considered urgent.
    if job.deadline:
        deadline = parse_date(job.deadline)

        if deadline:
            now = datetime.now(timezone.utc)
            days_remaining = (deadline - now).days

            if 0 <= days_remaining <= 2:
                job.is_urgent = True

    return job


def process_freshness(jobs):
    """
    Apply freshness classification and flags to all jobs.
    """

    return [mark_freshness(job) for job in jobs]
