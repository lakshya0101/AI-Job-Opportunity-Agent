import hashlib
import json
from pathlib import Path
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from src.models.job import Job


def _normalize_str(value: Optional[str]) -> str:
    """Normalize whitespace and lowercase for stable comparison."""
    if not value:
        return ""
    return " ".join(value.strip().split()).lower()


class JobStore:
    """
    SQLite-backed persistent job store.
    
    Provides stable identity tracking, content hash comparison for change detection,
    and safe schema migration for existing databases.
    """

    def __init__(
        self,
        database_path: str = "data/jobs.db",
    ):
        self.database_path = database_path
        self._memory_conn: Optional[sqlite3.Connection] = None
        if self.database_path == ":memory:":
            self._memory_conn = sqlite3.connect(":memory:")
            self._memory_conn.row_factory = sqlite3.Row
        else:
            Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        if self._memory_conn is not None:
            return self._memory_conn
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection


    def _initialize(self):
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_key TEXT PRIMARY KEY,
                    company TEXT,
                    title TEXT,
                    location TEXT,
                    work_mode TEXT,
                    experience TEXT,
                    eligibility TEXT,
                    compensation TEXT,
                    description TEXT,
                    application_url TEXT,
                    careers_url TEXT,
                    source TEXT,
                    recruiter_name TEXT,
                    recruiter_email TEXT,
                    skills TEXT,
                    posting_date TEXT,
                    deadline TEXT,
                    content_hash TEXT,
                    first_seen TEXT,
                    last_seen TEXT
                )
                """
            )
            connection.commit()
            self._migrate_existing_database(connection)

    @staticmethod
    def _migrate_existing_database(connection: sqlite3.Connection):
        """
        Safely add any missing columns when an older jobs.db schema exists.
        Preserves existing records without dropping tables.
        """
        existing_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(jobs)").fetchall()
        }

        required_columns = {
            "company": "TEXT",
            "title": "TEXT",
            "location": "TEXT",
            "work_mode": "TEXT",
            "experience": "TEXT",
            "eligibility": "TEXT",
            "compensation": "TEXT",
            "description": "TEXT",
            "application_url": "TEXT",
            "careers_url": "TEXT",
            "source": "TEXT",
            "recruiter_name": "TEXT",
            "recruiter_email": "TEXT",
            "skills": "TEXT",
            "posting_date": "TEXT",
            "deadline": "TEXT",
            "content_hash": "TEXT",
            "first_seen": "TEXT",
            "last_seen": "TEXT",
        }

        for column, column_type in required_columns.items():
            if column not in existing_columns:
                connection.execute(
                    f"ALTER TABLE jobs ADD COLUMN {column} {column_type}"
                )

        connection.commit()

    @staticmethod
    def make_key(job: Job) -> str:
        """
        Generate a stable identity key for a job.

        Architectural Decision:
        Identity is strictly based on normalized (company, title, location).
        Application URLs, careers URLs, posting dates, and external IDs can vary,
        expire, redirect, or change across scrapes without representing a distinct job opportunity.
        """
        company = _normalize_str(job.company)
        title = _normalize_str(job.title)
        location = _normalize_str(job.location)

        raw = f"{company}|{title}|{location}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def content_hash(job: Job) -> str:
        """
        Create a hash of meaningful job content to detect updates.

        Included:
            company, title, location, work_mode, experience, eligibility,
            compensation, posting_date, deadline, description, application_url,
            careers_url, source, recruiter_name, recruiter_email, skills.

        Explicitly Excluded (transient / runtime fields):
            first_seen, last_seen, match_score, match_reason, role_score,
            skill_score, location_score, experience_score, freshness_score,
            is_new, is_updated, is_urgent.
        """
        cleaned_skills = sorted(
            [s.strip().lower() for s in (job.skills or []) if s and s.strip()]
        )

        parts = [
            (job.company or "").strip(),
            (job.title or "").strip(),
            (job.location or "").strip(),
            (job.work_mode or "").strip(),
            (job.experience or "").strip(),
            (job.eligibility or "").strip(),
            (job.compensation or "").strip(),
            (job.posting_date or "").strip(),
            (job.deadline or "").strip(),
            (job.description or "").strip(),
            (job.application_url or "").strip(),
            (job.careers_url or "").strip(),
            (job.source or "").strip(),
            (job.recruiter_name or "").strip(),
            (job.recruiter_email or "").strip(),
            ",".join(cleaned_skills),
        ]

        raw = "|".join(parts)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, job_key: str) -> Optional[Dict[str, Any]]:
        """Retrieve a stored job dictionary by its stable key."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM jobs WHERE job_key = ?",
                (job_key,),
            ).fetchone()

        if not row:
            return None

        return dict(row)

    def is_new(self, job: Job) -> bool:
        """Return True if the job has never been recorded in persistent storage."""
        return self.get(self.make_key(job)) is None

    def is_updated(self, job: Job) -> bool:
        """Return True if an existing job has changed its meaningful content."""
        existing = self.get(self.make_key(job))
        if not existing:
            return False

        return existing.get("content_hash") != self.content_hash(job)

    def save(self, job: Job):
        """
        Persist a job.
        
        Inserts new jobs with first_seen and last_seen set to current UTC time.
        Updates existing jobs while preserving their original first_seen timestamp.
        """
        job_key = self.make_key(job)
        current_hash = self.content_hash(job)
        now = datetime.now(timezone.utc).isoformat()

        skills_serialized = json.dumps(job.skills or [])
        existing = self.get(job_key)

        with self._connect() as connection:
            if existing:
                connection.execute(
                    """
                    UPDATE jobs
                    SET
                        company = ?,
                        title = ?,
                        location = ?,
                        work_mode = ?,
                        experience = ?,
                        eligibility = ?,
                        compensation = ?,
                        description = ?,
                        application_url = ?,
                        careers_url = ?,
                        source = ?,
                        recruiter_name = ?,
                        recruiter_email = ?,
                        skills = ?,
                        posting_date = ?,
                        deadline = ?,
                        content_hash = ?,
                        last_seen = ?
                    WHERE job_key = ?
                    """,
                    (
                        job.company,
                        job.title,
                        job.location,
                        job.work_mode,
                        job.experience,
                        job.eligibility,
                        job.compensation,
                        job.description,
                        job.application_url,
                        job.careers_url,
                        job.source,
                        job.recruiter_name,
                        job.recruiter_email,
                        skills_serialized,
                        job.posting_date,
                        job.deadline,
                        current_hash,
                        now,
                        job_key,
                    ),
                )
            else:
                first_seen = job.first_seen or now
                connection.execute(
                    """
                    INSERT INTO jobs (
                        job_key,
                        company,
                        title,
                        location,
                        work_mode,
                        experience,
                        eligibility,
                        compensation,
                        description,
                        application_url,
                        careers_url,
                        source,
                        recruiter_name,
                        recruiter_email,
                        skills,
                        posting_date,
                        deadline,
                        content_hash,
                        first_seen,
                        last_seen
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job_key,
                        job.company,
                        job.title,
                        job.location,
                        job.work_mode,
                        job.experience,
                        job.eligibility,
                        job.compensation,
                        job.description,
                        job.application_url,
                        job.careers_url,
                        job.source,
                        job.recruiter_name,
                        job.recruiter_email,
                        skills_serialized,
                        job.posting_date,
                        job.deadline,
                        current_hash,
                        first_seen,
                        now,
                    ),
                )
            connection.commit()

    def save_all(self, jobs: Iterable[Job]):
        """Persist multiple jobs in a single transaction."""
        for job in jobs:
            self.save(job)

    def count(self) -> int:
        """Return total number of jobs stored in the database."""
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS total FROM jobs").fetchone()
            return row["total"] if row else 0

