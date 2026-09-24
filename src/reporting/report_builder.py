from dataclasses import dataclass
from typing import List

from src.models.job import Job


@dataclass
class DailyReport:
    """Structured daily job report."""

    apply_first: List[Job]
    new_today: List[Job]
    urgent: List[Job]
    fresh_active: List[Job]
    total_jobs: int


def build_report(jobs: List[Job]) -> DailyReport:
    """Build the daily report sections."""

    apply_first = sorted(
        jobs,
        key=lambda job: job.match_score,
        reverse=True,
    )[:10]

    new_today = [
        job
        for job in jobs
        if job.is_new
    ]

    urgent = [
        job
        for job in jobs
        if job.is_urgent
    ]

    fresh_active = [
        job
        for job in jobs
        if job not in new_today
        and job not in urgent
    ]

    fresh_active.sort(
        key=lambda job: job.match_score,
        reverse=True,
    )

    return DailyReport(
        apply_first=apply_first,
        new_today=new_today,
        urgent=urgent,
        fresh_active=fresh_active,
        total_jobs=len(jobs),
    )
