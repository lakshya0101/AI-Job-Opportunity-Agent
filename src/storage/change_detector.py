from typing import Iterable, List

from src.models.job import Job
from src.storage.job_store import JobStore


def detect_changes(
    jobs: Iterable[Job],
    store: JobStore,
) -> List[Job]:
    """Mark jobs as new or updated."""

    changed_jobs = []

    for job in jobs:

        if store.is_new(job):
            job.is_new = True
            job.is_updated = False

        elif store.is_updated(job):
            job.is_new = False
            job.is_updated = True

        else:
            job.is_new = False
            job.is_updated = False

        changed_jobs.append(job)

    return changed_jobs
