from datetime import datetime, timedelta, timezone

from src.models.job import Job
from src.processing.freshness import (
    classify_freshness,
    days_since,
    is_expired,
    is_reportable,
    mark_freshness,
    parse_date,
    process_freshness,
)


def test_parse_date_formats():
    """Verify various supported ISO and readable date formats."""
    assert parse_date("2026-10-01") is not None
    assert parse_date("2026-10-01T12:00:00Z") is not None
    assert parse_date("01-10-2026") is not None
    assert parse_date("01/10/2026") is not None
    assert parse_date("01 Oct 2026") is not None
    assert parse_date("invalid-date") is None
    assert parse_date(None) is None


def test_is_expired_past_deadline():
    """Jobs with past deadlines are expired."""
    past = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    future = (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%d")

    job_past = Job(company="A", title="B", location="C", deadline=past)
    job_future = Job(company="A", title="B", location="C", deadline=future)
    job_no_deadline = Job(company="A", title="B", location="C", deadline=None)

    assert is_expired(job_past) is True
    assert is_expired(job_future) is False
    assert is_expired(job_no_deadline) is False


def test_classify_freshness_categories():
    """Verify posting date classification thresholds."""
    now = datetime.now(timezone.utc)
    d0 = now.strftime("%Y-%m-%d")
    d2 = (now - timedelta(days=2)).strftime("%Y-%m-%d")
    d5 = (now - timedelta(days=5)).strftime("%Y-%m-%d")
    d10 = (now - timedelta(days=10)).strftime("%Y-%m-%d")
    d20 = (now - timedelta(days=20)).strftime("%Y-%m-%d")

    assert classify_freshness(Job(company="A", title="B", location="C", posting_date=d0)) == "NEW_TODAY"
    assert classify_freshness(Job(company="A", title="B", location="C", posting_date=d2)) == "FRESH"
    assert classify_freshness(Job(company="A", title="B", location="C", posting_date=d5)) == "ACTIVE"
    assert classify_freshness(Job(company="A", title="B", location="C", posting_date=d10)) == "OLDER_ACTIVE"
    assert classify_freshness(Job(company="A", title="B", location="C", posting_date=d20)) == "OLDER"
    assert classify_freshness(Job(company="A", title="B", location="C", posting_date=None)) == "UNKNOWN"


def test_is_reportable_matrix():
    """Test reportability rules across categories and match scores."""
    now = datetime.now(timezone.utc)
    d0 = now.strftime("%Y-%m-%d")
    d5 = (now - timedelta(days=5)).strftime("%Y-%m-%d")
    d10 = (now - timedelta(days=10)).strftime("%Y-%m-%d")
    d20 = (now - timedelta(days=20)).strftime("%Y-%m-%d")
    past_dl = (now - timedelta(days=1)).strftime("%Y-%m-%d")

    # NEW_TODAY and FRESH always reportable
    assert is_reportable(Job(company="A", title="B", location="C", posting_date=d0, match_score=55.0)) is True

    # ACTIVE (4-7d): requires match_score >= 70
    assert is_reportable(Job(company="A", title="B", location="C", posting_date=d5, match_score=75.0)) is True
    assert is_reportable(Job(company="A", title="B", location="C", posting_date=d5, match_score=65.0)) is False

    # OLDER_ACTIVE (8-14d): requires match_score >= 80
    assert is_reportable(Job(company="A", title="B", location="C", posting_date=d10, match_score=88.0)) is True
    assert is_reportable(Job(company="A", title="B", location="C", posting_date=d10, match_score=80.0)) is True
    assert is_reportable(Job(company="A", title="B", location="C", posting_date=d10, match_score=79.9)) is False

    # OLDER (>14d): requires match_score >= 90
    assert is_reportable(Job(company="A", title="B", location="C", posting_date=d20, match_score=95.0)) is True
    assert is_reportable(Job(company="A", title="B", location="C", posting_date=d20, match_score=90.0)) is True
    assert is_reportable(Job(company="A", title="B", location="C", posting_date=d20, match_score=89.9)) is False

    # EXPIRED: not reportable
    assert is_reportable(Job(company="A", title="B", location="C", posting_date=d0, deadline=past_dl, match_score=95.0)) is False

    # UNKNOWN posting date: reportable if is_new and score >= 70 or score >= 80
    assert is_reportable(Job(company="A", title="B", location="C", posting_date=None, is_new=True, match_score=72.0)) is True
    assert is_reportable(Job(company="A", title="B", location="C", posting_date=None, is_new=False, match_score=82.0)) is True
    assert is_reportable(Job(company="A", title="B", location="C", posting_date=None, is_new=False, match_score=60.0)) is False


def test_mark_freshness_urgency_and_preservation():
    """Urgency flag is set for <= 2 days deadline and does not overwrite is_new."""
    now = datetime.now(timezone.utc)
    urgent_deadline = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    far_deadline = (now + timedelta(days=10)).strftime("%Y-%m-%d")

    job_urgent = Job(company="A", title="B", location="C", deadline=urgent_deadline, is_new=False)
    job_far = Job(company="A", title="B", location="C", deadline=far_deadline, is_new=True)

    mark_freshness(job_urgent)
    mark_freshness(job_far)

    assert job_urgent.is_urgent is True
    assert job_urgent.is_new is False  # not overwritten

    assert job_far.is_urgent is False
    assert job_far.is_new is True  # not overwritten
