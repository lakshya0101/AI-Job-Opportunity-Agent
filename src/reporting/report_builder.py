from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from src.collectors.base import SourceHealth
from src.models.job import Job
from src.pipeline import PipelineResult
from src.processing.freshness import classify_freshness


@dataclass
class PipelineSummary:
    """Summary metrics of the pipeline execution."""
    collected: int = 0
    normalized: int = 0
    deduplicated: int = 0
    new: int = 0
    updated: int = 0
    matched: int = 0
    total_reportable: int = 0


@dataclass
class DailyReport:
    """Structured daily job report data model."""
    apply_first: List[Job]
    new_today: List[Job]
    updated: List[Job]
    urgent: List[Job]
    fresh_active: List[Job]
    remote_india: List[Job]
    business_analyst: List[Job]
    other_strong_matches: List[Job]
    total_jobs: int
    source_health: List[SourceHealth] = field(default_factory=list)
    summary: PipelineSummary = field(default_factory=PipelineSummary)


def _job_identity(job: Job) -> str:
    """Create a string identifier for deduplication within report sections."""
    company = (job.company or "").strip().lower()
    title = (job.title or "").strip().lower()
    location = (job.location or "").strip().lower()
    return f"{company}|{title}|{location}"


def is_remote_india(job: Job) -> bool:
    """Check whether a job explicitly indicates remote work in India."""
    location = (job.location or "").lower()
    work_mode = (job.work_mode or "").lower()
    return (
        "remote india" in location
        or "india remote" in location
        or ("remote" in work_mode and "india" in location)
    )


def is_business_analyst(job: Job) -> bool:
    """Check whether a job is a business analysis or business intelligence role."""
    title = (job.title or "").lower()
    ba_keywords = [
        "business analyst",
        "business data analyst",
        "technical business analyst",
        "business intelligence analyst",
        "product analyst",
        "analytics analyst",
        "bi analyst",
    ]
    return any(keyword in title for keyword in ba_keywords)


def build_report(
    jobs: List[Job],
    pipeline_result: Optional[PipelineResult] = None,
    source_health: Optional[List[SourceHealth]] = None,
) -> DailyReport:
    """
    Construct the structured daily report with prioritized sections.
    
    Order of sections:
    1. Apply First (top objective matches)
    2. New Today (posting date indicates posted today)
    3. Updated (content changed since last stored version)
    4. Urgent (deadline approaching within 2 days)
    5. Fresh & Active (1-7 days old)
    6. Remote India
    7. Business Analyst
    8. Other Strong Matches (score >= 80, not in above primary categories)
    """
    reportable_jobs = [job for job in jobs if job is not None]

    # 1. Apply First: Top 10 by match_score descending, with freshness tie-breaker
    apply_first = sorted(
        reportable_jobs,
        key=lambda j: (j.match_score, j.freshness_score, 1 if j.is_urgent else 0),
        reverse=True,
    )[:10]

    # 2. New Today: Posted today according to source date
    new_today = [
        job for job in reportable_jobs
        if classify_freshness(job) == "NEW_TODAY"
    ]
    new_today.sort(key=lambda j: j.match_score, reverse=True)

    # 3. Updated: Content changed from previous DB record
    updated = [
        job for job in reportable_jobs
        if getattr(job, "is_updated", False)
    ]
    updated.sort(key=lambda j: j.match_score, reverse=True)

    # 4. Urgent: Deadline <= 2 days away
    urgent = [
        job for job in reportable_jobs
        if getattr(job, "is_urgent", False)
    ]
    urgent.sort(key=lambda j: (j.match_score), reverse=True)

    # 5. Fresh & Active: Posted within 1-7 days, not already in new_today or updated
    fresh_active = [
        job for job in reportable_jobs
        if classify_freshness(job) in {"FRESH", "ACTIVE"}
        and job not in new_today
        and job not in updated
    ]
    fresh_active.sort(key=lambda j: j.match_score, reverse=True)

    # 6. Remote India
    remote_india = [
        job for job in reportable_jobs
        if is_remote_india(job)
    ]
    remote_india.sort(key=lambda j: j.match_score, reverse=True)

    # 7. Business Analyst
    business_analyst = [
        job for job in reportable_jobs
        if is_business_analyst(job)
    ]
    business_analyst.sort(key=lambda j: j.match_score, reverse=True)

    # 8. Other Strong Matches: Safe identity tracking to avoid unhashable Job set error
    special_identities = {
        _job_identity(j)
        for j in (new_today + updated + urgent + fresh_active + remote_india + business_analyst)
    }

    other_strong_matches = [
        job for job in reportable_jobs
        if _job_identity(job) not in special_identities
        and job.match_score >= 80.0
    ]
    other_strong_matches.sort(key=lambda j: j.match_score, reverse=True)

    # Summary and Source Health derivation
    if pipeline_result:
        health_list = pipeline_result.source_health
        summary = PipelineSummary(
            collected=pipeline_result.collected_count,
            normalized=pipeline_result.normalized_count,
            deduplicated=pipeline_result.deduplicated_count,
            new=pipeline_result.new_count,
            updated=pipeline_result.updated_count,
            matched=pipeline_result.matched_count,
            total_reportable=pipeline_result.filtered_count,
        )
    else:
        health_list = source_health or []
        summary = PipelineSummary(
            collected=len(reportable_jobs),
            normalized=len(reportable_jobs),
            deduplicated=len(reportable_jobs),
            new=sum(1 for j in reportable_jobs if j.is_new),
            updated=sum(1 for j in reportable_jobs if j.is_updated),
            matched=len(reportable_jobs),
            total_reportable=len(reportable_jobs),
        )

    return DailyReport(
        apply_first=apply_first,
        new_today=new_today,
        updated=updated,
        urgent=urgent,
        fresh_active=fresh_active,
        remote_india=remote_india,
        business_analyst=business_analyst,
        other_strong_matches=other_strong_matches,
        total_jobs=len(reportable_jobs),
        source_health=health_list,
        summary=summary,
    )
