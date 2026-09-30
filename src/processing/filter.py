from typing import Any, Dict, Iterable, List, Optional

from src.models.job import Job
from src.processing.freshness import is_expired, is_reportable

DEFAULT_MIN_MATCH_SCORE = 55.0
DEFAULT_MIN_SKILL_SCORE = 7.5
DEFAULT_MIN_ROLE_SCORE = 27.0
DEFAULT_MIN_EXPERIENCE_SCORE = 5.0


def is_allowed_location(job: Job, preferences: Optional[Dict[str, Any]] = None) -> bool:
    """
    Allow preferred Indian locations and Remote India according to profile preferences.

    Other Indian locations are allowed only when the job has a
    strong overall match (>=80.0).
    """
    location = (job.location or "").lower()

    if preferences:
        # Resolve active profile if nested
        active_prefs = preferences
        if "locations" not in active_prefs and "profiles" in active_prefs:
            active_prefs = active_prefs["profiles"].get("lakshya", {})

        loc_cfg = active_prefs.get("locations", {})
        priority_map = loc_cfg.get("priority", {})
        
        preferred_locations = []
        for locs in priority_map.values():
            if isinstance(locs, list):
                preferred_locations.extend(l.lower() for l in locs if l)

        remote_list = loc_cfg.get("remote", [])
        remote_locations = [r.lower() for r in remote_list if r]
    else:
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

    # Explicit overseas locations without India should be rejected
    overseas_indicators = [
        "canada",
        "uk",
        "united kingdom",
        "us",
        "usa",
        "united states",
        "germany",
        "poland",
        "macedonia",
        "romania",
        "singapore",
        "australia",
        "ireland",
        "spain",
        "france",
        "netherlands",
        "brazil",
        "mexico",
        "japan",
    ]
    if any(os_ind in location for os_ind in overseas_indicators) and not any(ind in location for ind in ["india", "indian"]):
        return False

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
    preferences: Optional[Dict[str, Any]] = None,
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
    if not is_allowed_location(job, preferences=preferences):
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
    preferences: Optional[Dict[str, Any]] = None,
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
            preferences=preferences,
        )
    ]
