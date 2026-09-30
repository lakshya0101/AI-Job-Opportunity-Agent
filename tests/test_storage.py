import sqlite3
import time
from datetime import datetime, timezone
import pytest

from src.models.job import Job
from src.storage.change_detector import detect_changes
from src.storage.job_store import JobStore


def test_new_job_detection(tmp_path):
    """A job never saved in the store is recognized as new."""
    db_path = str(tmp_path / "jobs.db")
    store = JobStore(db_path)

    job = Job(
        company="Anthropic",
        title="AI Research Engineer",
        location="Remote India",
        application_url="https://example.com/apply/1",
    )

    assert store.is_new(job) is True
    assert store.is_updated(job) is False


def test_unchanged_job_detection(tmp_path):
    """A saved job with identical attributes is recognized as unchanged."""
    db_path = str(tmp_path / "jobs.db")
    store = JobStore(db_path)

    job = Job(
        company="Google",
        title="ML Engineer",
        location="Bangalore",
        application_url="https://example.com/ml-eng",
        experience="0-2 years",
        skills=["Python", "PyTorch"],
    )

    store.save(job)

    assert store.is_new(job) is False
    assert store.is_updated(job) is False


def test_updated_job_detection(tmp_path):
    """A saved job whose description or compensation changes is recognized as updated."""
    db_path = str(tmp_path / "jobs.db")
    store = JobStore(db_path)

    job = Job(
        company="Microsoft",
        title="Data Scientist",
        location="Noida",
        compensation="20 LPA",
        description="Initial description",
    )
    store.save(job)

    # Modify meaningful content
    modified_job = Job(
        company="Microsoft",
        title="Data Scientist",
        location="Noida",
        compensation="25 LPA",
        description="Updated description with GenAI tasks",
    )

    assert store.is_new(modified_job) is False
    assert store.is_updated(modified_job) is True


def test_application_url_change_not_new_but_updated(tmp_path):
    """An application URL changing does NOT make it a new job, but DOES make it updated."""
    db_path = str(tmp_path / "jobs.db")
    store = JobStore(db_path)

    job_v1 = Job(
        company="DeepMind",
        title="GenAI Engineer",
        location="Gurugram",
        application_url="https://lever.co/deepmind/job1",
    )
    store.save(job_v1)

    job_v2 = Job(
        company="DeepMind",
        title="GenAI Engineer",
        location="Gurugram",
        application_url="https://greenhouse.io/deepmind/job1_new_url",
    )

    # Stable identity should be the same
    assert store.make_key(job_v1) == store.make_key(job_v2)
    # Not a new job
    assert store.is_new(job_v2) is False
    # But content hash differs, so it is updated
    assert store.is_updated(job_v2) is True


def test_first_seen_preserved_and_last_seen_updated(tmp_path):
    """Updating a job retains the original first_seen and updates last_seen."""
    db_path = str(tmp_path / "jobs.db")
    store = JobStore(db_path)

    initial_time = "2026-01-01T10:00:00+00:00"
    job = Job(
        company="Amazon",
        title="Backend Engineer",
        location="New Delhi",
        first_seen=initial_time,
        compensation="18 LPA",
    )
    store.save(job)

    record_before = store.get(store.make_key(job))
    assert record_before["first_seen"] == initial_time
    assert record_before["last_seen"] is not None

    time.sleep(0.01)

    # Save an update
    job.compensation = "22 LPA"
    store.save(job)

    record_after = store.get(store.make_key(job))
    assert record_after["first_seen"] == initial_time
    assert record_after["last_seen"] >= record_before["last_seen"]
    assert record_after["compensation"] == "22 LPA"


def test_stable_key_normalization(tmp_path):
    """make_key should ignore case and redundant whitespace differences."""
    db_path = str(tmp_path / "jobs.db")
    store = JobStore(db_path)

    job_a = Job(
        company="  Meta   Platforms ",
        title=" AI  Engineer\t",
        location=" Bangalore ",
    )
    job_b = Job(
        company="meta platforms",
        title="ai engineer",
        location="bangalore",
    )

    assert store.make_key(job_a) == store.make_key(job_b)


def test_persistence_of_all_metadata_fields(tmp_path):
    """Verify all job attributes are correctly persisted and retrieved."""
    db_path = str(tmp_path / "jobs.db")
    store = JobStore(db_path)

    job = Job(
        company="OpenAI",
        title="Applied AI Engineer",
        location="Remote India",
        work_mode="Remote",
        experience="0-1 years",
        eligibility="B.Tech CSE",
        compensation="30 LPA",
        posting_date="2026-09-30",
        deadline="2026-10-15",
        description="Exciting LLM agent engineering role.",
        source="official_company_careers",
        application_url="https://openai.com/careers/applied-ai",
        careers_url="https://openai.com/careers",
        recruiter_name="Jane Doe",
        recruiter_email="jane@openai.com",
        skills=["Python", "FastAPI", "LangChain", "RAG"],
    )

    store.save(job)
    data = store.get(store.make_key(job))

    assert data["company"] == "OpenAI"
    assert data["title"] == "Applied AI Engineer"
    assert data["location"] == "Remote India"
    assert data["work_mode"] == "Remote"
    assert data["experience"] == "0-1 years"
    assert data["eligibility"] == "B.Tech CSE"
    assert data["compensation"] == "30 LPA"
    assert data["posting_date"] == "2026-09-30"
    assert data["deadline"] == "2026-10-15"
    assert data["description"] == "Exciting LLM agent engineering role."
    assert data["source"] == "official_company_careers"
    assert data["application_url"] == "https://openai.com/careers/applied-ai"
    assert data["careers_url"] == "https://openai.com/careers"
    assert data["recruiter_name"] == "Jane Doe"
    assert data["recruiter_email"] == "jane@openai.com"
    assert "Python" in data["skills"]
    assert "FastAPI" in data["skills"]


def test_safe_schema_migration(tmp_path):
    """Existing older database schemas migrate without data loss."""
    db_path = str(tmp_path / "legacy_jobs.db")

    # Create a legacy table with minimal columns
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE jobs (
            job_key TEXT PRIMARY KEY,
            company TEXT,
            title TEXT,
            location TEXT,
            application_url TEXT,
            content_hash TEXT,
            first_seen TEXT,
            last_seen TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO jobs (job_key, company, title, location, application_url, content_hash, first_seen, last_seen)
        VALUES ('legacy_key_1', 'Legacy Corp', 'Software Dev', 'Noida', 'https://legacy.com', 'hash123', '2025-01-01', '2025-01-01')
        """
    )
    conn.commit()
    conn.close()

    # Initializing JobStore on the legacy db should run safe migration
    store = JobStore(db_path)

    # Legacy record should still exist intact
    legacy_row = store.get("legacy_key_1")
    assert legacy_row is not None
    assert legacy_row["company"] == "Legacy Corp"
    assert legacy_row["title"] == "Software Dev"
    assert legacy_row["location"] == "Noida"

    # New columns should be present and accessible
    assert "careers_url" in legacy_row
    assert "recruiter_name" in legacy_row
    assert "skills" in legacy_row


def test_detect_changes_does_not_modify_database(tmp_path):
    """detect_changes must classify jobs without persisting them to the database."""
    db_path = str(tmp_path / "jobs.db")
    store = JobStore(db_path)

    # Initial database has 1 existing job
    existing_job = Job(
        company="Existing Co",
        title="AI Engineer",
        location="Noida",
        compensation="15 LPA",
    )
    store.save(existing_job)
    assert store.count() == 1

    # Prepare 3 incoming jobs: 1 unchanged, 1 updated, 1 new
    job_unchanged = Job(
        company="Existing Co",
        title="AI Engineer",
        location="Noida",
        compensation="15 LPA",
    )
    job_updated = Job(
        company="Existing Co",
        title="AI Engineer",
        location="Noida",
        compensation="20 LPA",  # changed
    )
    job_new = Job(
        company="Brand New Co",
        title="Data Analyst",
        location="Jaipur",
    )

    # Run detect_changes
    classified = detect_changes([job_unchanged, job_updated, job_new], store)

    # Database count must still be 1 (detect_changes must NOT write to DB)
    assert store.count() == 1

    # Verify classification flags
    assert classified[0].is_new is False
    assert classified[0].is_updated is False

    assert classified[1].is_new is False
    assert classified[1].is_updated is True

    assert classified[2].is_new is True
    assert classified[2].is_updated is False
