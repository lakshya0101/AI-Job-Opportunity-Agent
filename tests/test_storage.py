from src.models.job import Job
from src.storage.job_store import JobStore


def test_job_store(tmp_path):

    database = tmp_path / "jobs.db"

    store = JobStore(
        str(database)
    )

    job = Job(
        company="Test Company",
        title="AI Engineer",
        location="Noida",
        application_url="https://example.com",
    )

    assert store.is_new(job) is True

    store.save(job)

    assert store.is_new(job) is False
