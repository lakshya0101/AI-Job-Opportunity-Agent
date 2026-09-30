from typing import Iterable, List

from src.models.job import Job
from src.processing.freshness import is_expired, is_reportable

DEFAULT_MIN_MATCH_SCORE = 55.0
DEFAULT_MIN_SKILL_SCORE = 7.5
DEFAULT_MIN_ROLE_SCORE = 27.0
DEFAULT_MIN_EXPERIENCE_SCORE = 5.0


def is_allowed_location(job: Job) -> bool:
    """
    Allow preferred Indian locations and Remote India.

    Other Indian locations are allowed only when the job has a
    strong overall match (>=80.0).
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

    if any(preferred in location for preferred in preferred_locations):
        return True

    if any(remote in location for remote in remote_locations):
        return True

    # Other Indian locations can be considered only for strong matches
    india_indicators = [
        "india",
        "indian",
        "hyderabad",
        "chennai",
        "kolkata",
        "ahmedabad",
        "chandigarh",
        "indore",
        "kochi",
    ]

    if any(indicator in location for indicator in india_indicators):
        return job.match_score >= 80.0

    return False


def should_include(
    job: Job,
    minimum_score: float = DEFAULT_MIN_MATCH_SCORE,
    minimum_skill_score: float = DEFAULT_MIN_SKILL_SCORE,
    minimum_role_score: float = DEFAULT_MIN_ROLE_SCORE,
    minimum_experience_score: float = DEFAULT_MIN_EXPERIENCE_SCORE,
) -> bool:
    """
    Evaluate whether a job qualifies for the final report.
    """
    if job is None:
        return False

    # Check expiration via parsed deadline
    if is_expired(job):
        return False

    # Check location constraints
    if not is_allowed_location(job):
        return False

    # Require an actual target-role match
    if job.role_score < minimum_role_score:
        return False

    # Reject clearly experienced/senior roles
    if job.experience_score < minimum_experience_score:
        return False

    # Require meaningful technical overlap
    if job.skill_score < minimum_skill_score:
        return False

    # Overall match score threshold
    if job.match_score < minimum_score:
        return False

    # Must have a valid link (application or official careers URL)
    if not job.application_url and not job.careers_url:
        return False

    # Check freshness reportability (filters out stale/older low-fit jobs)
    if not is_reportable(job):
        return False

    return True


def filter_jobs(
    jobs: Iterable[Job],
    minimum_score: float = DEFAULT_MIN_MATCH_SCORE,
    minimum_skill_score: float = DEFAULT_MIN_SKILL_SCORE,
    minimum_role_score: float = DEFAULT_MIN_ROLE_SCORE,
    minimum_experience_score: float = DEFAULT_MIN_EXPERIENCE_SCORE,
) -> List[Job]:
    """Filter candidate jobs against all qualification criteria."""
    return [
        job
        for job in jobs
        if should_include(
            job,
            minimum_score=minimum_score,
            minimum_skill_score=minimum_skill_score,
            minimum_role_score=minimum_role_score,
            minimum_experience_score=minimum_experience_score,
        )
    ]
