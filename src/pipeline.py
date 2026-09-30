from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from src.collectors.base import SourceHealth
from src.collectors.official_careers import OfficialCareersCollector
from src.collectors.runner import run_collectors_detailed
from src.collectors.unstop import UnstopCollector
from src.collectors.yc_jobs import YCJobsCollector
from src.matching.matcher import calculate_match
from src.models.job import Job
from src.processing.deduplicator import deduplicate_jobs
from src.processing.filter import filter_jobs
from src.processing.freshness import process_freshness
from src.processing.link_validator import validate_links
from src.processing.normalizer import normalize_jobs
from src.storage.change_detector import detect_changes
from src.storage.job_store import JobStore


@dataclass
class PipelineResult:
    """
    Structured outcome of the central job processing pipeline.
    """
    collected_count: int
    normalized_count: int
    deduplicated_count: int
    new_count: int
    updated_count: int
    matched_count: int
    filtered_count: int
    source_health: List[SourceHealth]
    reportable_jobs: List[Job]
    all_matched_jobs: List[Job] = field(default_factory=list)


def run_pipeline(
    preferences: Dict[str, Any],
    store: JobStore,
    collectors: Optional[Iterable[Any]] = None,
) -> PipelineResult:
    """
    Execute the central job opportunity pipeline in strict sequential order:
    1. Collect
    2. Normalize
    3. Deduplicate
    4. Detect Changes (Read-only from JobStore)
    5. Process Freshness (Flags & Urgency)
    6. Validate Links
    7. Match / Score
    8. Filter / Select Reportable Jobs
    """
    # 1. Collect
    if collectors is None:
        sources_cfg = preferences.get("sources", {})
        company_boards = sources_cfg.get("company_boards", [])
        preferred_sources = sources_cfg.get("preferred", [])

        active_collectors = [
            OfficialCareersCollector(company_boards),
            UnstopCollector(),
            YCJobsCollector(),
        ]
        raw_jobs, collector_results = run_collectors_detailed(
            active_collectors,
            all_configured_sources=preferred_sources,
        )
    else:
        raw_jobs, collector_results = run_collectors_detailed(collectors)

    source_health = [r.source_health for r in collector_results]
    collected_count = len(raw_jobs)

    # 2. Normalize
    jobs = normalize_jobs(raw_jobs)
    normalized_count = len(jobs)

    # 3. Deduplicate
    jobs = deduplicate_jobs(jobs)
    deduplicated_count = len(jobs)

    # 4. Change Detection (Read-only query against JobStore)
    jobs = detect_changes(jobs, store)
    new_count = sum(1 for j in jobs if j.is_new)
    updated_count = sum(1 for j in jobs if j.is_updated)

    # 5. Process Freshness
    jobs = process_freshness(jobs)

    # 6. Validate Links
    jobs = validate_links(jobs)

    # 7. Matching / Scoring
    matched_jobs = []
    for job in jobs:
        matched_jobs.append(calculate_match(job, preferences))
    matched_count = len(matched_jobs)

    # 8. Filtering
    matching_cfg = preferences.get("matching", {})
    min_score = float(matching_cfg.get("minimum_score_to_include", 55.0))

    filtered_jobs = filter_jobs(matched_jobs, minimum_score=min_score)
    filtered_count = len(filtered_jobs)

    return PipelineResult(
        collected_count=collected_count,
        normalized_count=normalized_count,
        deduplicated_count=deduplicated_count,
        new_count=new_count,
        updated_count=updated_count,
        matched_count=matched_count,
        filtered_count=filtered_count,
        source_health=source_health,
        reportable_jobs=filtered_jobs,
        all_matched_jobs=matched_jobs,
    )
