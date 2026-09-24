from typing import Iterable, List

from src.models.job import Job


DEFAULT_MIN_MATCH_SCORE = 55.0


def is_expired(job: Job) -> bool:
    """Return True when the job has been classified as expired."""

    return job.deadline == "EXPIRED"


def should_include(
    job: Job,
    minimum_score: float = DEFAULT_MIN_MATCH_SCORE,
) -> bool:
    """Determine whether a job should appear in the report."""

    if is_expired(job):
        return False

    if job.match_score < minimum_score:
        return False

    if not job.application_url and not job.careers_url:
        return False

    return True


def filter_jobs(
    jobs: Iterable[Job],
    minimum_score: float = DEFAULT_MIN_MATCH_SCORE,
) -> List[Job]:
    """Filter jobs using score, expiry, and application-link rules."""

    return [
        job
        for job in jobs
        if should_include(job, minimum_score)
    ]
