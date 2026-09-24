from typing import Iterable, List

from src.models.job import Job


DEFAULT_MIN_MATCH_SCORE = 55.0
DEFAULT_MIN_SKILL_SCORE = 8.0

def is_expired(job: Job) -> bool:
    """Return True when the job has been classified as expired."""

    return job.deadline == "EXPIRED"


def should_include(
    job: Job,
    minimum_score: float = DEFAULT_MIN_MATCH_SCORE,
    minimum_skill_score: float = DEFAULT_MIN_SKILL_SCORE,
) -> bool:
    if is_expired(job):
        return False

    if job.match_score < minimum_score:
        return False

    if job.skill_score < minimum_skill_score:
        return False

    if not job.application_url and not job.careers_url:
        return False

    return True


def filter_jobs(
    jobs: Iterable[Job],
    minimum_score: float = DEFAULT_MIN_MATCH_SCORE,
    minimum_skill_score: float = DEFAULT_MIN_SKILL_SCORE,
) -> List[Job]:
    return [
        job
        for job in jobs
        if should_include(
            job,
            minimum_score,
            minimum_skill_score,
        )
    ]
