import copy
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

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
    Structured outcome of the job processing pipeline for a specific profile.
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


def get_profiles(preferences: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Retrieve configured candidate profiles from configuration dictionary.
    
    If 'profiles' mapping is present, returns it.
    Otherwise, returns a single default profile wrapping the flat preferences.
    """
    if "profiles" in preferences and isinstance(preferences["profiles"], dict):
        return preferences["profiles"]
    
    return {"lakshya": preferences}


def collect_and_process_base_jobs(
    preferences: Dict[str, Any],
    store: JobStore,
    collectors: Optional[Iterable[Any]] = None,
) -> Tuple[List[Job], List[SourceHealth], Dict[str, int]]:
    """
    Execute shared, candidate-independent upstream processing stages:
    1. Collect once from all configured sources
    2. Normalize raw schemas
    3. Deduplicate listings
    4. Detect changes against persistent JobStore (Read-only query)
    5. Process Freshness (flags & urgency)
    6. Validate URLs
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

    # 5. Process Freshness
    jobs = process_freshness(jobs)

    # 6. Validate Links
    jobs = validate_links(jobs)

    metrics = {
        "collected_count": collected_count,
        "normalized_count": normalized_count,
        "deduplicated_count": deduplicated_count,
    }

    return jobs, source_health, metrics


def evaluate_profile_jobs(
    base_jobs: List[Job],
    profile_config: Dict[str, Any],
    source_health: List[SourceHealth],
    metrics: Dict[str, int],
    global_preferences: Optional[Dict[str, Any]] = None,
) -> PipelineResult:
    """
    Evaluate candidate-independent base jobs against a specific candidate profile.
    
    Each job is shallow-copied so candidate scoring and match reasons remain isolated.
    """
    new_count = sum(1 for j in base_jobs if j.is_new)
    updated_count = sum(1 for j in base_jobs if j.is_updated)

    matched_jobs = []
    for job in base_jobs:
        job_copy = copy.copy(job)
        matched_jobs.append(calculate_match(job_copy, profile_config))

    matched_count = len(matched_jobs)

    # Determine minimum score threshold
    min_score = 55.0
    if global_preferences and "matching" in global_preferences:
        min_score = float(global_preferences["matching"].get("minimum_score_to_include", 55.0))
    elif "matching" in profile_config:
        min_score = float(profile_config["matching"].get("minimum_score_to_include", 55.0))

    filtered_jobs = filter_jobs(
        matched_jobs,
        minimum_score=min_score,
        preferences=profile_config,
    )
    filtered_count = len(filtered_jobs)

    return PipelineResult(
        collected_count=metrics.get("collected_count", len(base_jobs)),
        normalized_count=metrics.get("normalized_count", len(base_jobs)),
        deduplicated_count=metrics.get("deduplicated_count", len(base_jobs)),
        new_count=new_count,
        updated_count=updated_count,
        matched_count=matched_count,
        filtered_count=filtered_count,
        source_health=source_health,
        reportable_jobs=filtered_jobs,
        all_matched_jobs=matched_jobs,
    )


def run_pipeline(
    preferences: Dict[str, Any],
    store: JobStore,
    collectors: Optional[Iterable[Any]] = None,
    profile_key: Optional[str] = None,
) -> PipelineResult:
    """
    Execute central job opportunity pipeline for a single profile.
    Preserves backward compatibility for single-profile callers and tests.
    """
    base_jobs, source_health, metrics = collect_and_process_base_jobs(
        preferences,
        store,
        collectors=collectors,
    )

    profiles = get_profiles(preferences)
    if profile_key and profile_key in profiles:
        target_profile = profiles[profile_key]
    else:
        target_profile = profiles.get("lakshya") or next(iter(profiles.values()))

    return evaluate_profile_jobs(
        base_jobs=base_jobs,
        profile_config=target_profile,
        source_health=source_health,
        metrics=metrics,
        global_preferences=preferences,
    )
