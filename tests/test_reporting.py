from datetime import datetime, timedelta, timezone

from src.collectors.base import CollectorStatus, SourceHealth
from src.models.job import Job
from src.pipeline import PipelineResult
from src.reporting.report_builder import DailyReport, build_report
from src.reporting.templates import job_card, render_daily_report, render_source_health


def test_empty_report():
    """Verify empty report builds and renders without error."""
    report = build_report([])
    assert report.total_jobs == 0
    assert len(report.apply_first) == 0

    html = render_daily_report(report, "01 Oct 2026")
    assert "No matching opportunities were found" in html
    assert "Pipeline Summary" in html


def test_apply_first_ordering():
    """Apply First sorts top jobs by match_score descending, capped at 10."""
    jobs = [
        Job(company=f"Company {i}", title="AI Engineer", location="Noida", match_score=float(i * 5))
        for i in range(15)
    ]
    report = build_report(jobs)
    assert len(report.apply_first) == 10
    # Top score is 14 * 5 = 70.0
    assert report.apply_first[0].match_score == 70.0
    assert report.apply_first[1].match_score == 65.0


def test_newly_discovered_vs_new_today_distinction():
    """
    Verify distinction between:
    - job.is_new (discovered by system in this run)
    - NEW_TODAY (job posting date indicates posted today)
    """
    now = datetime.now(timezone.utc)
    today_str = now.strftime("%Y-%m-%d")
    two_days_ago = (now - timedelta(days=2)).strftime("%Y-%m-%d")

    # Job A: Posted today, already seen before
    job_a = Job(
        company="A", title="AI Engineer", location="Noida",
        posting_date=today_str, is_new=False, match_score=80.0
    )
    # Job B: Posted 2 days ago, discovered today by system
    job_b = Job(
        company="B", title="ML Engineer", location="Bangalore",
        posting_date=two_days_ago, is_new=True, match_score=85.0
    )

    report = build_report([job_a, job_b])
    assert job_a in report.new_today
    assert job_b not in report.new_today
    assert job_b in report.fresh_active


def test_updated_and_urgent_jobs():
    """Verify updated and urgent jobs are placed in their respective sections."""
    job_updated = Job(
        company="A", title="AI Engineer", location="Noida",
        is_updated=True, match_score=82.0
    )
    job_urgent = Job(
        company="B", title="Data Scientist", location="Gurugram",
        is_urgent=True, match_score=78.0
    )

    report = build_report([job_updated, job_urgent])
    assert job_updated in report.updated
    assert job_urgent in report.urgent


def test_remote_india_and_business_analyst():
    """Verify Remote India and Business Analyst classifications."""
    job_remote = Job(
        company="A", title="AI Engineer", location="Remote India",
        match_score=75.0
    )
    job_ba = Job(
        company="B", title="Senior Technical Business Analyst", location="Noida",
        match_score=80.0
    )

    report = build_report([job_remote, job_ba])
    assert job_remote in report.remote_india
    assert job_ba in report.business_analyst


def test_other_strong_matches_excludes_special_jobs():
    """Other strong matches (>=80) must exclude jobs already in primary categories."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # In new_today category
    job_new = Job(company="A", title="AI Engineer", location="Noida", posting_date=now, match_score=90.0)
    # In BA category
    job_ba = Job(company="B", title="Product Analyst", location="Noida", match_score=88.0)
    # Uncategorized strong match
    job_other = Job(company="C", title="Python Backend Engineer", location="Noida", match_score=85.0)

    report = build_report([job_new, job_ba, job_other])
    assert job_other in report.other_strong_matches
    assert job_new not in report.other_strong_matches
    assert job_ba not in report.other_strong_matches


def test_no_unhashable_job_set_error():
    """Regression test: report building with unhashable Job objects does not raise TypeError."""
    jobs = [
        Job(company="A", title="AI Engineer", location="Noida", skills=["Python", "FastAPI"], match_score=85.0),
        Job(company="B", title="ML Engineer", location="Gurugram", skills=["PyTorch", "NumPy"], match_score=90.0),
    ]
    # Dataclasses with mutable lists are unhashable if default set() is used.
    report = build_report(jobs)
    assert report.total_jobs == 2


def test_pipeline_summary_and_source_health_integration():
    """Verify source health and summary metrics are populated from PipelineResult."""
    source_health = [
        SourceHealth(source="official_careers", status=CollectorStatus.SUCCESS, job_count=10, duration_seconds=1.25),
        SourceHealth(source="LinkedIn", status=CollectorStatus.NOT_IMPLEMENTED, job_count=0),
    ]
    pipe_res = PipelineResult(
        collected_count=15,
        normalized_count=14,
        deduplicated_count=12,
        new_count=5,
        updated_count=2,
        matched_count=8,
        filtered_count=6,
        source_health=source_health,
        reportable_jobs=[],
    )

    report = build_report([], pipeline_result=pipe_res)
    assert report.summary.collected == 15
    assert report.summary.deduplicated == 12
    assert report.summary.new == 5
    assert len(report.source_health) == 2


def test_application_link_fallback_and_missing():
    """Verify direct application URL, careers URL fallback, and missing URL handling."""
    job_direct = Job(company="A", title="AI", location="Noida", application_url="https://direct.com/apply")
    job_careers = Job(company="B", title="AI", location="Noida", careers_url="https://company.com/careers")
    job_none = Job(company="C", title="AI", location="Noida")

    html_direct = job_card(job_direct)
    html_careers = job_card(job_careers)
    html_none = job_card(job_none)

    assert "https://direct.com/apply" in html_direct
    assert "Apply Directly" in html_direct

    assert "https://company.com/careers" in html_careers
    assert "Company Careers Page" in html_careers

    assert "Application link not available" in html_none
    assert "<a href" not in html_none


def test_html_rendering_complete():
    """Verify full HTML report generation includes expected sections and headers."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    job = Job(
        company="OpenAI & Partners",
        title="GenAI <Engineer>",
        location="Remote India",
        work_mode="Remote",
        experience="0-2 years",
        compensation="30 LPA",
        posting_date=now,
        match_score=92.5,
        role_score=30.0,
        skill_score=25.0,
        location_score=20.0,
        experience_score=10.0,
        freshness_score=10.0,
        skills=["Python", "LLM", "RAG"],
        match_reason="strong role match; preferred location",
        application_url="https://openai.com/careers/genai",
    )

    report = build_report([job])
    html = render_daily_report(report, "01 Oct 2026")

    # Check safe HTML escaping
    assert "OpenAI &amp; Partners" in html
    assert "GenAI &lt;Engineer&gt;" in html
    # Check section presence
    assert "Apply First" in html
    assert "New Today" in html
    assert "Remote India" in html
    assert "Source Health" in html
