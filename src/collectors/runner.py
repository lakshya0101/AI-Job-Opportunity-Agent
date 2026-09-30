import logging
import time
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, Union

from src.collectors.base import BaseCollector, CollectorResult, CollectorStatus, NotImplementedCollector, SourceHealth

logger = logging.getLogger(__name__)

CollectorType = Union[BaseCollector, Callable[[], Union[CollectorResult, Iterable[Dict[str, Any]]]]]


def _execute_single_collector(collector: CollectorType) -> CollectorResult:
    """Safely execute a single collector with timing and fault isolation."""
    # Determine source name
    if isinstance(collector, BaseCollector):
        source_name = collector.source_name
        collect_fn = collector.collect
    elif hasattr(collector, "source_name"):
        source_name = getattr(collector, "source_name")
        collect_fn = getattr(collector, "collect", collector)
    elif hasattr(collector, "__name__"):
        source_name = collector.__name__
        collect_fn = collector
    else:
        source_name = str(collector)
        collect_fn = collector

    start_time = time.monotonic()
    try:
        raw_result = collect_fn()
        elapsed = round(time.monotonic() - start_time, 4)

        if isinstance(raw_result, CollectorResult):
            if raw_result.duration_seconds == 0.0 and elapsed > 0:
                raw_result.duration_seconds = elapsed
            return raw_result

        # Convert raw list/iterable of jobs to CollectorResult
        jobs = list(raw_result) if raw_result is not None else []
        status = CollectorStatus.SUCCESS if len(jobs) > 0 else CollectorStatus.EMPTY

        return CollectorResult(
            source=source_name,
            jobs=jobs,
            status=status,
            error=None,
            count=len(jobs),
            duration_seconds=elapsed,
        )

    except Exception as exc:
        elapsed = round(time.monotonic() - start_time, 4)
        logger.error(f"Collector '{source_name}' failed with error: {exc}", exc_info=True)
        return CollectorResult(
            source=source_name,
            jobs=[],
            status=CollectorStatus.FAILED,
            error=str(exc),
            count=0,
            duration_seconds=elapsed,
        )


def run_collectors_detailed(
    collectors: Iterable[CollectorType],
    all_configured_sources: Optional[Iterable[str]] = None,
) -> Tuple[List[Dict[str, Any]], List[CollectorResult]]:
    """
    Run all collectors independently, isolating failures.
    
    If all_configured_sources is provided, any source without an active
    collector will be marked as NOT_IMPLEMENTED in the results list.
    
    Returns:
        Tuple of (aggregated_successful_jobs, list_of_individual_collector_results)
    """
    aggregated_jobs: List[Dict[str, Any]] = []
    results: List[CollectorResult] = []
    executed_sources = set()

    from concurrent.futures import ThreadPoolExecutor, as_completed

    collector_list = list(collectors)
    if not collector_list:
        return [], []

    with ThreadPoolExecutor(max_workers=min(len(collector_list), 10)) as executor:
        future_to_collector = {
            executor.submit(_execute_single_collector, collector): collector
            for collector in collector_list
        }
        for future in as_completed(future_to_collector):
            try:
                result = future.result()
                results.append(result)
                executed_sources.add(result.source)
                if result.status == CollectorStatus.SUCCESS and result.jobs:
                    aggregated_jobs.extend(result.jobs)
            except Exception as exc:
                logger.error(f"Unexpected error retrieving collector result: {exc}", exc_info=True)

    if all_configured_sources:
        for source_name in all_configured_sources:
            if source_name not in executed_sources:
                results.append(
                    NotImplementedCollector(source_name).collect()
                )

    return aggregated_jobs, results


def run_collectors(
    collectors: Iterable[CollectorType],
) -> List[Dict[str, Any]]:
    """
    Execute all collectors and return the combined list of raw jobs.
    Preserves backward compatibility while guaranteeing fault isolation.
    """
    jobs, _ = run_collectors_detailed(collectors)
    return jobs
