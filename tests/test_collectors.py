from typing import Any, Dict, List
from unittest.mock import patch

from src.collectors.base import BaseCollector, CollectorResult, CollectorStatus
from src.collectors.official_careers import OfficialCareersCollector
from src.collectors.runner import run_collectors, run_collectors_detailed


class MockSuccessCollector(BaseCollector):
    @property
    def source_name(self) -> str:
        return "mock_success"

    def collect(self) -> CollectorResult:
        return CollectorResult(
            source=self.source_name,
            jobs=[
                {
                    "company": "Company A",
                    "title": "AI Engineer",
                    "location": "Noida",
                },
                {
                    "company": "Company A",
                    "title": "ML Engineer",
                    "location": "Gurugram",
                },
            ],
            status=CollectorStatus.SUCCESS,
            count=2,
        )


class MockEmptyCollector(BaseCollector):
    @property
    def source_name(self) -> str:
        return "mock_empty"

    def collect(self) -> CollectorResult:
        return CollectorResult(
            source=self.source_name,
            jobs=[],
            status=CollectorStatus.EMPTY,
            count=0,
        )


class MockFailingCollector(BaseCollector):
    @property
    def source_name(self) -> str:
        return "mock_failing"

    def collect(self) -> CollectorResult:
        raise ConnectionError("Simulated network timeout or API rate limit")


def test_successful_collector_result():
    collector = MockSuccessCollector()
    result = collector.collect()

    assert result.source == "mock_success"
    assert result.status == CollectorStatus.SUCCESS
    assert result.count == 2
    assert len(result.jobs) == 2
    assert result.error is None


def test_empty_collector_result():
    collector = MockEmptyCollector()
    result = collector.collect()

    assert result.source == "mock_empty"
    assert result.status == CollectorStatus.EMPTY
    assert result.count == 0
    assert len(result.jobs) == 0
    assert result.error is None


def test_failed_collector_isolated_in_runner():
    failing = MockFailingCollector()
    jobs, results = run_collectors_detailed([failing])

    assert len(jobs) == 0
    assert len(results) == 1
    assert results[0].source == "mock_failing"
    assert results[0].status == CollectorStatus.FAILED
    assert "Simulated network timeout" in (results[0].error or "")
    assert results[0].count == 0


def test_runner_fault_isolation_multiple_collectors():
    """A failure in one collector does not stop other collectors from succeeding."""
    success_collector = MockSuccessCollector()
    failing_collector = MockFailingCollector()
    empty_collector = MockEmptyCollector()

    jobs, results = run_collectors_detailed([
        failing_collector,
        success_collector,
        empty_collector,
    ])

    # Aggregated jobs should contain jobs from the successful collector
    assert len(jobs) == 2
    assert jobs[0]["title"] == "AI Engineer"
    assert jobs[1]["title"] == "ML Engineer"

    # Check status per source
    status_map = {r.source: r.status for r in results}
    assert status_map["mock_failing"] == CollectorStatus.FAILED
    assert status_map["mock_success"] == CollectorStatus.SUCCESS
    assert status_map["mock_empty"] == CollectorStatus.EMPTY


def test_backward_compatible_run_collectors():
    """run_collectors returns the combined flat list of raw jobs."""
    success_collector = MockSuccessCollector()
    failing_collector = MockFailingCollector()

    jobs = run_collectors([success_collector, failing_collector])
    assert len(jobs) == 2
    assert jobs[0]["company"] == "Company A"


def test_callable_collector_support():
    """Functions returning lists or raising errors are supported transparently."""
    def simple_callable():
        return [{"company": "Company B", "title": "Data Analyst", "location": "Bangalore"}]

    def failing_callable():
        raise RuntimeError("Callable crash")

    jobs, results = run_collectors_detailed([simple_callable, failing_callable])
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Data Analyst"
    assert results[0].status == CollectorStatus.SUCCESS
    assert results[1].status == CollectorStatus.FAILED


def test_official_careers_collector_class():
    """OfficialCareersCollector behaves as a BaseCollector."""
    with patch("src.collectors.official_careers.collect") as mock_collect:
        mock_collect.return_value = [
            {"company": "Celonis", "title": "Data Scientist", "location": "Bangalore"}
        ]

        collector = OfficialCareersCollector([{"name": "Celonis", "platform": "greenhouse", "identifier": "celonis"}])
        assert collector.source_name == "official_company_careers"

        result = collector.collect()
        assert result.status == CollectorStatus.SUCCESS
        assert result.count == 1
        assert result.jobs[0]["company"] == "Celonis"
        assert result.duration_seconds >= 0.0


def test_source_health_and_not_implemented():
    """Verify NOT_IMPLEMENTED status for unconfigured sources and SourceHealth conversion."""
    success_collector = MockSuccessCollector()
    configured_sources = ["mock_success", "LinkedIn", "Naukri"]

    jobs, results = run_collectors_detailed([success_collector], all_configured_sources=configured_sources)

    assert len(jobs) == 2
    assert len(results) == 3

    health_list = [r.source_health for r in results]
    health_by_source = {h.source: h for h in health_list}

    assert health_by_source["mock_success"].status == CollectorStatus.SUCCESS
    assert health_by_source["mock_success"].job_count == 2

    assert health_by_source["LinkedIn"].status == CollectorStatus.NOT_IMPLEMENTED
    assert health_by_source["LinkedIn"].job_count == 0
    assert "not yet implemented" in (health_by_source["LinkedIn"].error or "").lower()

    assert health_by_source["Naukri"].status == CollectorStatus.NOT_IMPLEMENTED
    assert health_by_source["Naukri"].job_count == 0

