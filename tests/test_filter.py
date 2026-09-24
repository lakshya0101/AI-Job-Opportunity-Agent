from src.models.job import Job
from src.processing.filter import should_include


def test_low_score_job_is_rejected():

    job = Job(
        company="Test",
        title="Test Engineer",
        location="Noida",
        match_score=40,
        application_url="https://example.com",
    )

    assert should_include(job) is False
