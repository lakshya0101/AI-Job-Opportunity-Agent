import re
from typing import Iterable

from src.models.job import Job


def normalize_key(value: str) -> str:
    """
    Normalize text so small formatting differences
    don't create duplicate jobs.
    """

    value = value.lower().strip()

    # Remove punctuation
    value = re.sub(r"[^a-z0-9\s]", " ", value)

    # Collapse multiple spaces
    value = re.sub(r"\s+", " ", value)

    return value


def job_key(job: Job) -> str:
    """
    Generate a stable identity key for a job.

    Company + title + location are used because the
    same opening can appear on multiple platforms.
    """

    company = normalize_key(job.company)
    title = normalize_key(job.title)
    location = normalize_key(job.location)

    return f"{company}|{title}|{location}"


def deduplicate_jobs(jobs: Iterable[Job]) -> list[Job]:
    """
    Remove duplicate job listings.

    When duplicates exist, prefer the listing with:
    1. An application URL
    2. An official careers URL
    3. More complete information
    """

    unique_jobs: dict[str, Job] = {}

    for job in jobs:
        key = job_key(job)

        if key not in unique_jobs:
            unique_jobs[key] = job
            continue

        existing = unique_jobs[key]

        # Prefer the job with a direct application URL.
        if not existing.application_url and job.application_url:
            unique_jobs[key] = job
            continue

        # Otherwise prefer the job with an official careers URL.
        if not existing.careers_url and job.careers_url:
            unique_jobs[key] = job
            continue

        # If both have similar links, prefer the one
        # containing more useful information.
        existing_info = _information_score(existing)
        new_info = _information_score(job)

        if new_info > existing_info:
            unique_jobs[key] = job

    return list(unique_jobs.values())


def _information_score(job: Job) -> int:
    """
    Calculate how complete a job record is.
    Used only to decide which duplicate to retain.
    """

    score = 0

    fields = [
        job.experience,
        job.eligibility,
        job.compensation,
        job.posting_date,
        job.deadline,
        job.description,
        job.source,
        job.application_url,
        job.careers_url,
        job.recruiter_name,
        job.recruiter_email,
        job.match_reason,
    ]

    for field in fields:
        if field:
            score += 1

    score += len(job.skills)

    return score
