import hashlib
import sqlite3
from datetime import datetime
from typing import Optional

from src.models.job import Job


class JobStore:
    """SQLite-backed persistent job store."""

    def __init__(
        self,
        database_path: str = "jobs.db",
    ):
        self.database_path = database_path
        self._initialize()

    def _connect(self):
        return sqlite3.connect(
            self.database_path
        )

    def _initialize(self):
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
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

            connection.commit()

    @staticmethod
    def make_key(job: Job) -> str:
        """Create a stable identifier for a job."""

        raw = "|".join(
            [
                job.company or "",
                job.title or "",
                job.location or "",
                job.application_url or "",
            ]
        ).lower().strip()

        return hashlib.sha256(
            raw.encode("utf-8")
        ).hexdigest()

    @staticmethod
    def content_hash(job: Job) -> str:
        """Create a hash of meaningful job content."""

        raw = "|".join(
            [
                job.company or "",
                job.title or "",
                job.location or "",
                job.experience or "",
                job.description or "",
                job.compensation or "",
                "|".join(job.skills or []),
            ]
        )

        return hashlib.sha256(
            raw.encode("utf-8")
        ).hexdigest()

    def get(
        self,
        job_key: str,
    ) -> Optional[dict]:
        """Retrieve a stored job."""

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    job_key,
                    company,
                    title,
                    location,
                    application_url,
                    content_hash,
                    first_seen,
                    last_seen
                FROM jobs
                WHERE job_key = ?
                """,
                (job_key,),
            ).fetchone()

        if not row:
            return None

        return {
            "job_key": row[0],
            "company": row[1],
            "title": row[2],
            "location": row[3],
            "application_url": row[4],
            "content_hash": row[5],
            "first_seen": row[6],
            "last_seen": row[7],
        }

    def save(self, job: Job):
        """Insert or update a job."""

        job_key = self.make_key(job)
        current_hash = self.content_hash(job)

        now = datetime.utcnow().isoformat()

        existing = self.get(job_key)

        if existing:
            with self._connect() as connection:
                connection.execute(
                    """
                    UPDATE jobs
                    SET
                        content_hash = ?,
                        last_seen = ?
                    WHERE job_key = ?
                    """,
                    (
                        current_hash,
                        now,
                        job_key,
                    ),
                )

                connection.commit()

        else:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO jobs (
                        job_key,
                        company,
                        title,
                        location,
                        application_url,
                        content_hash,
                        first_seen,
                        last_seen
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job_key,
                        job.company,
                        job.title,
                        job.location,
                        job.application_url,
                        current_hash,
                        now,
                        now,
                    ),
                )

                connection.commit()

    def is_new(self, job: Job) -> bool:
        """Determine whether the job has never been seen."""

        return self.get(
            self.make_key(job)
        ) is None

    def is_updated(self, job: Job) -> bool:
        """Determine whether an existing job changed."""

        existing = self.get(
            self.make_key(job)
        )

        if not existing:
            return False

        return (
            existing["content_hash"]
            != self.content_hash(job)
        )
