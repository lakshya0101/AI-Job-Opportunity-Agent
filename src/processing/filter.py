from typing import Iterable, List

from src.models.job import Job


DEFAULT_MIN_MATCH_SCORE = 55.0
DEFAULT_MIN_SKILL_SCORE = 8.0
DEFAULT_MIN_ROLE_SCORE = 27.0
DEFAULT_MIN_EXPERIENCE_SCORE = 5.0


def is_expired(job: Job) -> bool:
    return job.deadline == "EXPIRED"


def is_allowed_location(job: Job) -> bool:
    """
    Allow preferred Indian locations and Remote India.

    Other locations are allowed only when the job has a
    very strong overall match.
    """

    location = (job.location or "").lower()

    preferred_locations = [
        "noida",
        "greater noida",
        "new delhi",
        "delhi",
        "gurugram",
        "gurgaon",
        "bangalore",
        "bengaluru",
        "jaipur",
        "pune",
        "mumbai",
        "navi mumbai",
    ]

    remote_locations = [
        "remote india",
        "india remote",
    ]

    if any(
        preferred in location
        for preferred in preferred_locations
    ):
        return True

    if any(
        remote in location
        for remote in remote_locations
    ):
        return True

    # Other Indian locations can be considered only
    # for exceptionally strong matches.
    india_indicators = [
        "india",
        "indian",
    ]

    if any(
        indicator in location
        for indicator in india_indicators
    ):
        return job.match_score >= 80.0

    return False

def should_include(
    job: Job,
    minimum_score: float = DEFAULT_MIN_MATCH_SCORE,
    minimum_skill_score: float = DEFAULT_MIN_SKILL_SCORE,
    minimum_role_score: float = DEFAULT_MIN_ROLE_SCORE,
    minimum_experience_score: float = DEFAULT_MIN_EXPERIENCE_SCORE,
) -> bool:
    if job is None:
        return False

    if not is_allowed_location(job):
        return False

    if is_expired(job):
        return False

    # Require an actual target-role match.
    if job.role_score < minimum_role_score:
        return False

    # Reject clearly experienced/senior roles.
    if job.experience_score < minimum_experience_score:
        return False

    # Require meaningful technical overlap.
    if job.skill_score < minimum_skill_score:
        return False

    if job.match_score < minimum_score:
        return False

    if not job.application_url and not job.careers_url:
        return False

    return True


def filter_jobs(
    jobs: Iterable[Job],
    minimum_score: float = DEFAULT_MIN_MATCH_SCORE,
    minimum_skill_score: float = DEFAULT_MIN_SKILL_SCORE,
    minimum_role_score: float = DEFAULT_MIN_ROLE_SCORE,
    minimum_experience_score: float = DEFAULT_MIN_EXPERIENCE_SCORE,
) -> List[Job]:
    return [
        job
        for job in jobs
        if should_include(
            job,
            minimum_score,
            minimum_skill_score,
            minimum_role_score,
            minimum_experience_score,
        )
    ]
