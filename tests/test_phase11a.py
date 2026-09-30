import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

from src.models.job import Job
from src.collectors.official_careers import OfficialCareersCollector, collect, collect_company
from src.collectors.base import CollectorStatus
from src.processing.freshness import is_reportable, is_expired, classify_freshness
from src.processing.deduplicator import deduplicate_jobs
from src.main import load_preferences, DEFAULT_CONFIG_PATH


def test_expanded_board_configuration():
    """Verify that preferences.yaml contains 20+ verified company boards."""
    prefs = load_preferences(DEFAULT_CONFIG_PATH)
    boards = prefs.get("sources", {}).get("company_boards", [])
    assert len(boards) >= 20, f"Expected at least 20 company boards, found {len(boards)}"
    
    # Verify structure of each board entry
    for board in boards:
        assert "name" in board and board["name"]
        assert "platform" in board and board["platform"] in ("greenhouse", "lever")
        assert "identifier" in board and board["identifier"]


def test_failing_board_does_not_stop_other_boards():
    """One failing board returns empty/fails gracefully without aborting other boards."""
    companies = [
        {"name": "Valid Lever", "platform": "lever", "identifier": "valid_lever"},
        {"name": "Broken Lever", "platform": "lever", "identifier": "invalid_slug_xyz123"},
        {"name": "Valid Greenhouse", "platform": "greenhouse", "identifier": "valid_gh"},
    ]

    def mock_requests_get(url, *args, **kwargs):
        resp = MagicMock()
        if "invalid_slug_xyz123" in url:
            resp.raise_for_status.side_effect = Exception("404 Not Found")
            return resp
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        if "greenhouse" in url:
            resp.json.return_value = {
                "jobs": [
                    {
                        "title": "Data Analyst",
                        "location": {"name": "Bangalore"},
                        "first_published": "2026-10-01T00:00:00Z",
                    }
                ]
            }
        else:
            resp.json.return_value = [
                {
                    "text": "AI Engineer",
                    "categories": {"location": "Noida"},
                    "createdAt": 1759276800000,
                }
            ]
        return resp

    with patch("requests.get", side_effect=mock_requests_get):
        collector = OfficialCareersCollector(companies)
        result = collector.collect()

        assert result.status == CollectorStatus.SUCCESS
        assert result.count == 2
        assert len(result.jobs) == 2
        titles = [j["title"] for j in result.jobs]
        assert "AI Engineer" in titles
        assert "Data Analyst" in titles


def test_duplicate_jobs_across_boards_deduplicated():
    """Duplicate jobs across sources or boards are eliminated cleanly."""
    job1 = Job(company="Acme Corp", title="Data Scientist", location="Bangalore, India", source="board_a")
    job2 = Job(company="Acme Corp", title="Data Scientist", location="Bangalore, India", source="board_b")
    job3 = Job(company="Acme Corp", title="AI Engineer", location="Bangalore, India", source="board_a")

    deduped = deduplicate_jobs([job1, job2, job3])
    assert len(deduped) == 2


def test_older_active_freshness_boundary_79_9_vs_80_0():
    """OLDER_ACTIVE (8-14 days) boundary: score 79.9 is rejected, 80.0 is reportable."""
    now = datetime.now(timezone.utc)
    posting_date = (now - timedelta(days=10)).strftime("%Y-%m-%d")

    job_below = Job(company="A", title="T", location="L", posting_date=posting_date, match_score=79.9)
    job_at = Job(company="A", title="T", location="L", posting_date=posting_date, match_score=80.0)

    assert classify_freshness(job_below) == "OLDER_ACTIVE"
    assert classify_freshness(job_at) == "OLDER_ACTIVE"

    assert is_reportable(job_below) is False
    assert is_reportable(job_at) is True


def test_older_freshness_boundary_89_9_vs_90_0():
    """OLDER (>14 days) boundary: score 89.9 is rejected, 90.0 is reportable."""
    now = datetime.now(timezone.utc)
    posting_date = (now - timedelta(days=25)).strftime("%Y-%m-%d")

    job_below = Job(company="A", title="T", location="L", posting_date=posting_date, match_score=89.9)
    job_at = Job(company="A", title="T", location="L", posting_date=posting_date, match_score=90.0)

    assert classify_freshness(job_below) == "OLDER"
    assert classify_freshness(job_at) == "OLDER"

    assert is_reportable(job_below) is False
    assert is_reportable(job_at) is True


def test_expiration_behavior_remains_unchanged():
    """Expired jobs past deadline are never reportable regardless of score or freshness."""
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    past_deadline = (now - timedelta(days=2)).strftime("%Y-%m-%d")
    future_deadline = (now + timedelta(days=5)).strftime("%Y-%m-%d")

    job_expired = Job(
        company="A", title="AI Engineer", location="Bangalore",
        posting_date=today, deadline=past_deadline, match_score=99.0
    )
    job_valid = Job(
        company="A", title="AI Engineer", location="Bangalore",
        posting_date=today, deadline=future_deadline, match_score=99.0
    )

    assert is_expired(job_expired) is True
    assert is_reportable(job_expired) is False

    assert is_expired(job_valid) is False
    assert is_reportable(job_valid) is True
