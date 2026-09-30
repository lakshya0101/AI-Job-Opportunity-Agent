from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from src.collectors.base import BaseCollector, CollectorResult, CollectorStatus
from src.main import ProductionRunResult, run_production
from src.models.job import Job
from src.storage.job_store import JobStore


class MockJobCollector(BaseCollector):
    def __init__(self, name: str, jobs: list, fail: bool = False):
        self._name = name
        self._jobs = jobs
        self._fail = fail

    @property
    def source_name(self) -> str:
        return self._name

    def collect(self) -> CollectorResult:
        if self._fail:
            raise ConnectionError(f"Failed connecting to {self._name}")
        return CollectorResult(
            source=self.source_name,
            jobs=self._jobs,
            status=CollectorStatus.SUCCESS if self._jobs else CollectorStatus.EMPTY,
            count=len(self._jobs),
        )


@pytest.fixture
def test_env(tmp_path):
    config_file = tmp_path / "preferences.yaml"
    config_file.write_text(
        """
candidate:
  education:
    degree: "B.Tech"
    specialization: ["Computer Science", "Data Science"]
  experience:
    preferred: ["fresher", "0-2 years"]
roles:
  ai_ml: ["AI Engineer", "ML Engineer", "Data Scientist"]
locations:
  priority:
    1: ["Noida"]
    4: ["Bangalore"]
  remote: ["Remote India"]
skills:
  programming: ["Python", "SQL"]
  genai: ["LLM", "RAG"]
matching:
  minimum_score_to_include: 55
sources:
  preferred: ["official_careers", "LinkedIn"]
  company_boards: []
email:
  recipient: "test@example.com"
  subject_prefix: "🚀 Daily Job Opportunities"
  attach_excel: true
""",
        encoding="utf-8",
    )

    db_file = tmp_path / "jobs.db"
    out_dir = tmp_path / "output"

    return {
        "config": config_file,
        "db": db_file,
        "output": out_dir,
    }


def test_successful_production_run(test_env, monkeypatch):
    """Verify full production cycle: pipeline -> HTML -> Excel -> email -> persistence."""
    monkeypatch.setenv("RESEND_API_KEY", "re_test_dummy_key")

    raw_job = {
        "company": "OpenAI",
        "title": "AI Engineer",
        "location": "Noida",
        "skills": ["Python", "LLM"],
        "posting_date": "2026-10-01",
        "application_url": "https://openai.com/apply/1",
    }
    collector = MockJobCollector("official_careers", [raw_job])

    with patch("src.main.send_daily_report") as mock_email:
        mock_email.return_value = {"id": "msg_success"}

        result = run_production(
            config_path=test_env["config"],
            db_path=test_env["db"],
            output_dir=test_env["output"],
            collectors=[collector],
        )

        assert result.success is True
        assert result.pipeline_status == "SUCCESS"
        assert result.html_status == "SUCCESS"
        assert result.excel_status == "SUCCESS"
        assert result.email_status == "SUCCESS"
        assert result.persistence_status == "SUCCESS"

        # Verify DB now has 1 record
        store = JobStore(str(test_env["db"]))
        assert store.count() == 1


def test_email_failure_prevents_persistence(test_env, monkeypatch):
    """When email dispatch fails, jobs must NOT be saved to the database."""
    monkeypatch.setenv("RESEND_API_KEY", "re_test_dummy_key")

    raw_job = {
        "company": "DeepMind",
        "title": "ML Engineer",
        "location": "Bangalore",
        "skills": ["Python", "SQL"],
        "posting_date": "2026-10-01",
        "application_url": "https://deepmind.com/jobs/1",
    }
    collector = MockJobCollector("official_careers", [raw_job])

    with patch("src.main.send_daily_report", side_effect=RuntimeError("Resend API rate limited")):
        result = run_production(
            config_path=test_env["config"],
            db_path=test_env["db"],
            output_dir=test_env["output"],
            collectors=[collector],
        )

        assert result.success is False
        assert result.email_status == "FAILED"
        assert "SKIPPED" in result.persistence_status

        # Database must still be empty
        store = JobStore(str(test_env["db"]))
        assert store.count() == 0


def test_all_collectors_failed_causes_failure(test_env, monkeypatch):
    """If all executed collectors fail, do NOT send misleading empty report."""
    monkeypatch.setenv("RESEND_API_KEY", "re_test_dummy_key")

    failing_1 = MockJobCollector("Source1", [], fail=True)
    failing_2 = MockJobCollector("Source2", [], fail=True)

    with patch("src.main.send_daily_report") as mock_email:
        result = run_production(
            config_path=test_env["config"],
            db_path=test_env["db"],
            output_dir=test_env["output"],
            collectors=[failing_1, failing_2],
        )

        assert result.success is False
        assert result.pipeline_status == "ALL_COLLECTORS_FAILED"
        assert not mock_email.called


def test_dry_run_does_not_send_email_or_persist(test_env, monkeypatch):
    """Dry run generates HTML and Excel but skips email sending and database saving."""
    raw_job = {
        "company": "Meta",
        "title": "AI Engineer",
        "location": "Noida",
        "skills": ["Python", "LLM"],
        "posting_date": "2026-10-01",
        "application_url": "https://meta.com/jobs/1",
    }
    collector = MockJobCollector("official_careers", [raw_job])

    with patch("src.main.send_daily_report") as mock_email:
        result = run_production(
            config_path=test_env["config"],
            db_path=test_env["db"],
            output_dir=test_env["output"],
            dry_run=True,
            collectors=[collector],
        )

        assert result.success is True
        assert "DRY RUN" in result.email_status
        assert "DRY RUN" in result.persistence_status
        assert not mock_email.called

        # DB remains empty
        store = JobStore(str(test_env["db"]))
        assert store.count() == 0

        # But Excel was generated
        assert result.excel_path is not None
        assert result.excel_path.exists()


def test_idempotency_second_run_not_new(test_env, monkeypatch):
    """Running the pipeline twice on the same job marks it as new on run 1, and not new on run 2."""
    monkeypatch.setenv("RESEND_API_KEY", "re_test_dummy_key")

    raw_job = {
        "company": "Anthropic",
        "title": "AI Engineer",
        "location": "Remote India",
        "skills": ["Python", "LLM", "RAG"],
        "posting_date": "2026-10-01",
        "application_url": "https://anthropic.com/jobs/1",
    }

    with patch("src.main.send_daily_report", return_value={"id": "msg_1"}):
        # Run 1
        res1 = run_production(
            config_path=test_env["config"],
            db_path=test_env["db"],
            output_dir=test_env["output"],
            collectors=[MockJobCollector("c1", [raw_job])],
        )
        assert res1.success is True
        assert res1.pipeline_result.new_count == 1

        # Run 2 (with same job)
        res2 = run_production(
            config_path=test_env["config"],
            db_path=test_env["db"],
            output_dir=test_env["output"],
            collectors=[MockJobCollector("c1", [raw_job])],
        )
        assert res2.success is True
        # On second run, new_count must be 0!
        assert res2.pipeline_result.new_count == 0
        assert res2.pipeline_result.updated_count == 0
