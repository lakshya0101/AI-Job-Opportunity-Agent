import os
from pathlib import Path
import sqlite3
import time
from unittest.mock import MagicMock, patch
import pytest
import yaml

from src.collectors.base import BaseCollector, CollectorResult, CollectorStatus
from src.main import ProductionRunResult, run_production
from src.models.job import Job
from src.storage.change_detector import detect_changes
from src.storage.job_store import JobStore


class MockCollector(BaseCollector):
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
def phase12_env(tmp_path):
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
  ai_ml: ["AI Engineer", "Data Scientist"]
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
  preferred: ["official_careers"]
  company_boards: []
email:
  recipient: "test@example.com"
  subject_prefix: "🚀 Daily Job Opportunities"
  attach_excel: true
""",
        encoding="utf-8",
    )

    db_file = tmp_path / "data" / "jobs.db"
    out_dir = tmp_path / "output"

    return {
        "config": config_file,
        "db": db_file,
        "output": out_dir,
    }


def test_idempotent_multi_run_lifecycle_and_fresh_process_simulation(phase12_env, monkeypatch):
    """
    Simulates Run A -> Run B -> Run C -> Run D across separate process invocations (fresh JobStore).
    Run A: Unseen job => is_new=True
    Run B: Identical job => is_new=False, is_updated=False
    Run C: Content changed => is_new=False, is_updated=True
    Run D: Fresh process restores state correctly
    """
    monkeypatch.setenv("RESEND_API_KEY", "re_dummy_key_123")
    db_path = phase12_env["db"]

    base_job = {
        "company": "Scale AI",
        "title": "AI Engineer",
        "location": "Noida",
        "skills": ["Python", "LLM"],
        "posting_date": "2026-10-01",
        "application_url": "https://scale.com/apply/1",
        "description": "Initial job description v1",
        "compensation": "20 LPA",
    }

    # RUN A: First time discovering the job
    with patch("src.main.send_daily_report", return_value={"id": "msg_run_a"}):
        res_a = run_production(
            config_path=phase12_env["config"],
            db_path=db_path,
            output_dir=phase12_env["output"],
            collectors=[MockCollector("c1", [base_job])],
        )
        assert res_a.success is True
        assert res_a.pipeline_result.new_count == 1
        assert res_a.pipeline_result.updated_count == 0

    # RUN B: Running the next day with the exact same job (Simulating a new VM/process opening the persisted DB)
    fresh_store_b = JobStore(str(db_path))
    assert fresh_store_b.count() == 1

    with patch("src.main.send_daily_report", return_value={"id": "msg_run_b"}):
        res_b = run_production(
            config_path=phase12_env["config"],
            db_path=db_path,
            output_dir=phase12_env["output"],
            collectors=[MockCollector("c1", [base_job])],
        )
        assert res_b.success is True
        assert res_b.pipeline_result.new_count == 0
        assert res_b.pipeline_result.updated_count == 0

    # RUN C: Running with updated compensation and description
    updated_job = dict(base_job)
    updated_job["compensation"] = "25 LPA"
    updated_job["description"] = "Updated description with RAG systems"

    with patch("src.main.send_daily_report", return_value={"id": "msg_run_c"}):
        res_c = run_production(
            config_path=phase12_env["config"],
            db_path=db_path,
            output_dir=phase12_env["output"],
            collectors=[MockCollector("c1", [updated_job])],
        )
        assert res_c.success is True
        assert res_c.pipeline_result.new_count == 0
        assert res_c.pipeline_result.updated_count == 1

    # RUN D: Verify fresh process reflects the updated data and preserves original first_seen
    fresh_store_d = JobStore(str(db_path))
    key = fresh_store_d.make_key(Job(company="Scale AI", title="AI Engineer", location="Noida"))
    rec = fresh_store_d.get(key)
    assert rec is not None
    assert rec["compensation"] == "25 LPA"
    assert rec["first_seen"] is not None
    assert rec["last_seen"] is not None


def test_app_url_change_is_updated_not_new(tmp_path):
    """Changing application URL is an update, not a new job opening."""
    store = JobStore(str(tmp_path / "data" / "jobs.db"))

    j1 = Job(company="Brillio", title="AI Engineer", location="Noida", application_url="https://lever.co/b1")
    store.save(j1)

    j2 = Job(company="Brillio", title="AI Engineer", location="Noida", application_url="https://greenhouse.io/b1_new")
    assert store.is_new(j2) is False
    assert store.is_updated(j2) is True


def test_failed_email_leaves_database_unmodified(phase12_env, monkeypatch):
    """If email dispatch throws an exception, the SQLite database remains empty."""
    monkeypatch.setenv("RESEND_API_KEY", "re_dummy_key_123")
    db_path = phase12_env["db"]

    raw_job = {
        "company": "Anthropic",
        "title": "AI Engineer",
        "location": "Noida",
        "skills": ["Python", "LLM"],
        "posting_date": "2026-10-01",
        "application_url": "https://anthropic.com/jobs/1",
    }

    with patch("src.main.send_daily_report", side_effect=RuntimeError("Resend API 500 Internal Error")):
        res = run_production(
            config_path=phase12_env["config"],
            db_path=db_path,
            output_dir=phase12_env["output"],
            collectors=[MockCollector("c1", [raw_job])],
        )
        assert res.success is False
        assert res.email_status == "FAILED"
        assert "SKIPPED" in res.persistence_status

        # Database must still have 0 records
        store = JobStore(str(db_path))
        assert store.count() == 0


def test_workflow_yaml_structure_and_cron():
    """Verify that daily-jobs.yml has valid syntax, the 04:30 UTC schedule, and required steps."""
    workflow_path = Path(".github") / "workflows" / "daily-jobs.yml"
    assert workflow_path.exists()

    with open(workflow_path, "r", encoding="utf-8") as f:
        doc = yaml.safe_load(f)

    assert doc["name"] == "Daily Job Opportunity Report"
    
    # Check trigger schedule
    triggers = doc.get("on") or doc.get(True)
    assert triggers is not None
    assert "schedule" in triggers
    cron_exprs = [item["cron"] for item in triggers["schedule"]]
    assert "30 4 * * *" in cron_exprs
    assert "workflow_dispatch" in triggers

    # Check concurrency and permissions
    assert doc.get("concurrency", {}).get("group") == "daily-job-agent-production"
    assert doc["jobs"]["job-agent"]["permissions"]["contents"] == "write"

    # Check steps
    steps = doc["jobs"]["job-agent"]["steps"]
    step_names = [s.get("name") for s in steps]
    assert "Checkout repository" in step_names
    assert "Setup Python" in step_names
    assert "Install dependencies" in step_names
    assert "Run test suite" in step_names
    assert "Run job opportunity agent" in step_names
    assert "Persist updated database state" in step_names
