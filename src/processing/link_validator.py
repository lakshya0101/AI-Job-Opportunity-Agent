from typing import Iterable, List
from urllib.parse import urlparse

from src.models.job import Job


def is_valid_url(url: str) -> bool:
    """Basic URL validation."""

    if not url:
        return False

    try:
        parsed = urlparse(url)

        return parsed.scheme in {
            "http",
            "https",
        } and bool(parsed.netloc)

    except Exception:
        return False


def validate_job_links(job: Job) -> Job:
    """Validate application and careers URLs."""

    if job.application_url and not is_valid_url(
        job.application_url
    ):
        job.application_url = None

    if job.careers_url and not is_valid_url(
        job.careers_url
    ):
        job.careers_url = None

    return job


def validate_links(
    jobs: Iterable[Job],
) -> List[Job]:
    """Validate links for multiple jobs."""

    return [
        validate_job_links(job)
        for job in jobs
    ]
