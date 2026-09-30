import hashlib
import sqlite3
from datetime import datetime, timezone
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
        connection = sqlite3.connect(
            self.database_path
        )
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
                    application_url TEXT,
                    careers_url TEXT,
                    source TEXT,
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
    def _migrate_existing_database(connection):
        """
        Add newer columns when an older jobs.db already exists.
        """

        existing_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(jobs)"
            ).fetchall()
        }

        required_columns = {
            "careers_url": "TEXT",
            "source": "TEXT",
            "posting_date": "TEXT",
            "deadline": "TEXT",
        }

        for column, column_type in required_columns.items():
            if column not in existing_columns:
                connection.execute(
                    f"""
                    ALTER TABLE jobs
                    ADD COLUMN {column} {column_type}
                    """
                )

        connection.commit()

    @staticmethod
    def make_key(job: Job) -> str:
        """
        Create a stable identity for a job.

        Application URLs are intentionally excluded because
        a URL can change without the underlying job being new.
        """

        raw = "|".join(
            [
                (job.company or "").strip().lower(),
                (job.title or "").strip().lower(),
                (job.location or "").strip().lower(),
            ]
        )

        return hashlib.sha256(
            raw.encode("utf-8")
        ).hexdigest()

    @staticmethod
    def content_hash(job: Job) -> str:
        """
        Create a hash of meaningful job content.

        Changes to these fields will cause the job to be
        classified as updated.
        """

        raw = "|".join(
            [
                job.company or "",
                job.title or "",
                job.location or "",
                job.work_mode or "",
                job.experience or "",
                job.eligibility or "",
                job.compensation or "",
                job.posting_date or "",
                job.deadline or "",
                job.description or "",
                job.application_url or "",
                job.careers_url or "",
                job.source or "",
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
                    careers_url,
                    source,
                    posting_date,
                    deadline,
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

        return dict(row)

    def save(self, job: Job):
        """
        Insert or update a job.

        Existing jobs retain their original first_seen timestamp.
        """

        job_key = self.make_key(job)
        current_hash = self.content_hash(job)

        now = datetime.now(
            timezone.utc
        ).isoformat()

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
                        application_url = ?,
                        careers_url = ?,
                        source = ?,
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
                        job.application_url,
                        job.careers_url,
                        job.source,
                        job.posting_date,
                        job.deadline,
                        current_hash,
                        now,
                        job_key,
                    ),
                )

            else:
                connection.execute(
                    """
                    INSERT INTO jobs (
                        job_key,
                        company,
                        title,
                        location,
                        application_url,
                        careers_url,
                        source,
                        posting_date,
                        deadline,
                        content_hash,
                        first_seen,
                        last_seen
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job_key,
                        job.company,
                        job.title,
                        job.location,
                        job.application_url,
                        job.careers_url,
                        job.source,
                        job.posting_date,
                        job.deadline,
                        current_hash,
                        now,
                        now,
                    ),
                )

            connection.commit()

    def is_new(self, job: Job) -> bool:
        """Determine whether the job has never been seen."""

        return (
            self.get(
                self.make_key(job)
            )
            is None
        )

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
