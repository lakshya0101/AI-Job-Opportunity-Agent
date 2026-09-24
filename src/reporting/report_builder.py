from dataclasses import dataclass
from typing import List

from src.models.job import Job
from src.processing.freshness import classify_freshness


@dataclass
class DailyReport:
    """Structured daily job report."""

    apply_first: List[Job]
    new_today: List[Job]
    urgent: List[Job]
    fresh_active: List[Job]
    remote_india: List[Job]
    business_analyst: List[Job]
    other_strong_matches: List[Job]
    total_jobs: int


def is_remote_india(job: Job) -> bool:
    """Check whether a job is explicitly remote in India."""

    location = (job.location or "").lower()

    return (
        "remote india" in location
        or "india remote" in location
    )


def is_business_analyst(job: Job) -> bool:
    """Check whether a job is a business-analysis role."""

    title = (job.title or "").lower()

    return (
        "business analyst" in title
        or "business data analyst" in title
        or "technical business analyst" in title
        or "business intelligence analyst" in title
        or "product analyst" in title
        or "analytics analyst" in title
    )


def build_report(jobs: List[Job]) -> DailyReport:
    """Build the daily job report sections."""

    reportable_jobs = [
        job
        for job in jobs
        if job is not None
    ]

    apply_first = sorted(
        reportable_jobs,
        key=lambda job: job.match_score,
        reverse=True,
    )[:10]

    new_today = [
        job
        for job in reportable_jobs
        if classify_freshness(job) == "NEW_TODAY"
    ]

    urgent = [
        job
        for job in reportable_jobs
        if job.is_urgent
    ]

    fresh_active = [
        job
        for job in reportable_jobs
        if classify_freshness(job) in {
            "FRESH",
            "ACTIVE",
        }
        and job not in new_today
    ]

    fresh_active.sort(
        key=lambda job: job.match_score,
        reverse=True,
    )

    remote_india = [
        job
        for job in reportable_jobs
        if is_remote_india(job)
    ]

    remote_india.sort(
        key=lambda job: job.match_score,
        reverse=True,
    )

    business_analyst = [
        job
        for job in reportable_jobs
        if is_business_analyst(job)
    ]

    business_analyst.sort(
        key=lambda job: job.match_score,
        reverse=True,
    )

    special_jobs = set(
        new_today
        + urgent
        + fresh_active
        + remote_india
        + business_analyst
    )

    other_strong_matches = [
        job
        for job in reportable_jobs
        if job not in special_jobs
        and job.match_score >= 80
    ]

    other_strong_matches.sort(
        key=lambda job: job.match_score,
        reverse=True,
    )

    return DailyReport(
        apply_first=apply_first,
        new_today=new_today,
        urgent=urgent,
        fresh_active=fresh_active,
        remote_india=remote_india,
        business_analyst=business_analyst,
        other_strong_matches=other_strong_matches,
        total_jobs=len(reportable_jobs),
    )
