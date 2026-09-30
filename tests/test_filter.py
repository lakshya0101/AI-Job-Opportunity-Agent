from datetime import datetime, timedelta, timezone

from src.models.job import Job
from src.processing.filter import filter_jobs, is_allowed_location, should_include


def test_low_score_job_is_rejected():
    job = Job(
        company="Test",
        title="Test Engineer",
        location="Noida",
        match_score=40,
        role_score=27,
        skill_score=10,
        experience_score=10,
        application_url="https://example.com",
    )
    assert should_include(job) is False


def test_expired_job_is_rejected():
    past = (datetime.now(timezone.utc) - timedelta(days=2)).strftime("%Y-%m-%d")
    job = Job(
        company="Test Co",
        title="AI Engineer",
        location="Noida",
        match_score=90,
        role_score=30,
        skill_score=30,
        experience_score=10,
        application_url="https://example.com",
        deadline=past,
    )
    assert should_include(job) is False


def test_missing_urls_rejected():
    job = Job(
        company="Test Co",
        title="AI Engineer",
        location="Noida",
        match_score=90,
        role_score=30,
        skill_score=30,
        experience_score=10,
        application_url=None,
        careers_url=None,
    )
    assert should_include(job) is False


def test_location_filtering():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Preferred location passes
    job_noida = Job(
        company="A", title="AI Engineer", location="Noida", match_score=60,
        role_score=27, skill_score=10, experience_score=10, application_url="https://a.com",
        posting_date=today,
    )
    assert should_include(job_noida) is True

    # Remote India passes
    job_remote = Job(
        company="A", title="AI Engineer", location="Remote India", match_score=60,
        role_score=27, skill_score=10, experience_score=10, application_url="https://a.com",
        posting_date=today,
    )
    assert should_include(job_remote) is True

    # Other Indian location (e.g. Hyderabad) passes only if match_score >= 80
    job_hyd_weak = Job(
        company="A", title="AI Engineer", location="Hyderabad", match_score=75,
        role_score=27, skill_score=10, experience_score=10, application_url="https://a.com",
        posting_date=today,
    )
    job_hyd_strong = Job(
        company="A", title="AI Engineer", location="Hyderabad", match_score=85,
        role_score=30, skill_score=25, experience_score=10, application_url="https://a.com",
        posting_date=today,
    )
    assert should_include(job_hyd_weak) is False
    assert should_include(job_hyd_strong) is True

    # Non-Indian location (e.g. London / New York) fails
    job_london = Job(
        company="A", title="AI Engineer", location="London, UK", match_score=95,
        role_score=30, skill_score=30, experience_score=10, application_url="https://a.com",
        posting_date=today,
    )
    assert should_include(job_london) is False



def test_role_and_experience_thresholds():
    # Low role score fails
    job_low_role = Job(
        company="A", title="Civil Engineer", location="Noida", match_score=80,
        role_score=10, skill_score=25, experience_score=10, application_url="https://a.com"
    )
    assert should_include(job_low_role) is False

    # Low experience score (senior/manager) fails
    job_senior = Job(
        company="A", title="Senior AI Architect", location="Noida", match_score=80,
        role_score=30, skill_score=30, experience_score=2, application_url="https://a.com"
    )
    assert should_include(job_senior) is False


def test_filter_jobs_batch():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    good_job = Job(
        company="A", title="AI Engineer", location="Noida", match_score=75,
        role_score=28, skill_score=15, experience_score=10, application_url="https://a.com",
        posting_date=now,
    )
    bad_job = Job(
        company="B", title="Sales Executive", location="London", match_score=30,
        role_score=0, skill_score=0, experience_score=0, application_url=None,
    )

    filtered = filter_jobs([good_job, bad_job])
    assert len(filtered) == 1
    assert filtered[0].company == "A"
