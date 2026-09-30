import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.collectors.base import CollectorStatus
from src.collectors.unstop import UnstopCollector, _parse_unstop_date, _format_compensation, _extract_locations
from src.collectors.yc_jobs import YCJobsCollector, _parse_yc_title
from src.collectors.runner import run_collectors_detailed
from src.models.job import Job
from src.processing.deduplicator import deduplicate_jobs
from src.processing.normalizer import normalize_jobs


def test_unstop_collector_success():
    """Unstop collector successfully parses jobs and internships."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": {
            "data": [
                {
                    "id": 1001,
                    "title": "Graduate AI Engineer",
                    "organisation": {"name": "Tech Corp"},
                    "seo_url": "https://unstop.com/jobs/graduate-ai-engineer-1001",
                    "approved_date": "2026-09-30 14:36:12 GMT+0530",
                    "end_date": "2026-10-30T00:00:00Z",
                    "details": "Developing GenAI and Python pipelines.",
                    "locations": [{"city": "Bangalore", "country": "India"}],
                    "jobDetail": {
                        "type": "in_office",
                        "min_salary": 800000,
                        "max_salary": 1200000,
                        "pay_in": "year",
                        "min_experience": 0,
                        "max_experience": 1,
                    },
                    "required_skills": [{"skill_name": "Python"}, {"skill_name": "Machine Learning"}],
                    "filters": [{"name": "Engineering Students"}],
                }
            ]
        }
    }

    with patch("requests.get", return_value=mock_resp):
        collector = UnstopCollector(max_pages=1)
        result = collector.collect()

        assert result.status == CollectorStatus.SUCCESS
        assert result.count == 2  # 1 from jobs + 1 from internships
        job = result.jobs[0]
        assert job["company"] == "Tech Corp"
        assert job["title"] == "Graduate AI Engineer"
        assert job["location"] == "Bangalore, India"
        assert job["work_mode"] == "Onsite"
        assert job["experience"] == "0-1 years"
        assert job["compensation"] == "₹800,000 - ₹1,200,000 / year"
        assert job["source"] == "Unstop"
        assert job["application_url"] == "https://unstop.com/jobs/graduate-ai-engineer-1001"
        assert "Python" in job["skills"]


def test_unstop_collector_network_failure():
    """Unstop network failure returns FAILED status gracefully."""
    with patch("requests.get", side_effect=Exception("Connection refused")):
        collector = UnstopCollector(max_pages=1)
        result = collector.collect()
        assert result.status == CollectorStatus.EMPTY or result.status == CollectorStatus.FAILED


def test_unstop_date_and_helpers():
    """Verify Unstop date parsing and compensation formatting."""
    iso_date = _parse_unstop_date("2026-09-30 14:36:12 GMT+0530")
    assert "2026-09-30" in iso_date

    assert _format_compensation({"min_salary": 500000, "max_salary": 500000, "pay_in": "year"}) == "₹500,000 / year"
    assert _format_compensation({}) is None

    loc = _extract_locations({"locations": [{"city": "Noida", "country": "India"}]})
    assert "Noida" in loc


def test_yc_jobs_collector_success():
    """YC Jobs collector successfully parses Hacker News job stories."""
    def mock_get(url, *args, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        if "jobstories.json" in url:
            resp.json.return_value = [101, 102]
        else:
            resp.json.return_value = {
                "id": 101,
                "title": "Anthropic (YC W21) Is Hiring AI Alignment Researchers",
                "url": "https://www.ycombinator.com/companies/anthropic/jobs/123",
                "time": 1790787620,
                "text": "Remote worldwide opportunity for Python & LLM engineers.",
            }
        return resp

    with patch("requests.get", side_effect=mock_get):
        collector = YCJobsCollector(max_items=2)
        result = collector.collect()

        assert result.status == CollectorStatus.SUCCESS
        assert result.count > 0
        job = result.jobs[0]
        assert job["company"] == "Anthropic"
        assert "AI Alignment Researchers" in job["title"]
        assert job["source"] == "YC Jobs"
        assert job["application_url"] == "https://www.ycombinator.com/companies/anthropic/jobs/123"


def test_yc_title_parsing():
    """Verify YC title regex parser handles various title patterns."""
    comp1, role1 = _parse_yc_title("Bild AI (YC W25) Is Hiring a Founding Product Engineer")
    assert comp1 == "Bild AI"
    assert role1 == "Founding Product Engineer"

    comp2, role2 = _parse_yc_title("Supabase (YC S20) Is Hiring for Backend Lead")
    assert comp2 == "Supabase"
    assert "Backend Lead" in role2


def test_deduplication_prioritizes_official_careers():
    """Aggregator duplicate is merged with preference for official career URL."""
    official_job = Job(
        company="Zeta",
        title="Software Engineer",
        location="Bangalore, India",
        source="official_company_careers",
        application_url="https://jobs.lever.co/zeta/123",
        careers_url="https://jobs.lever.co/zeta/123",
    )
    unstop_job = Job(
        company="Zeta",
        title="Software Engineer",
        location="Bangalore, India",
        source="Unstop",
        application_url="https://unstop.com/jobs/zeta-se-456",
        careers_url="https://unstop.com/jobs/zeta-se-456",
    )

    # When both are fed into deduplication, the official careers job is retained
    deduped = deduplicate_jobs([unstop_job, official_job])
    assert len(deduped) == 1
    assert deduped[0].source == "official_company_careers"
    assert deduped[0].application_url == "https://jobs.lever.co/zeta/123"


def test_multi_source_fault_isolation():
    """If one collector fails completely, other collectors still execute successfully."""
    mock_failing = MagicMock()
    mock_failing.source_name = "BrokenSource"
    mock_failing.collect.side_effect = Exception("Crash")

    mock_ok = MagicMock()
    mock_ok.source_name = "WorkingSource"
    mock_ok.collect.return_value = [{"company": "A", "title": "B", "location": "C"}]

    jobs, results = run_collectors_detailed([mock_failing, mock_ok])
    assert len(jobs) == 1
    assert len(results) == 2
    status_map = {r.source: r.status for r in results}
    assert status_map["BrokenSource"] == CollectorStatus.FAILED
    assert status_map["WorkingSource"] == CollectorStatus.SUCCESS
