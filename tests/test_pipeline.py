from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from unittest.mock import patch

from src.collectors.base import BaseCollector, CollectorResult, CollectorStatus
from src.models.job import Job
from src.pipeline import PipelineResult, run_pipeline
from src.processing.normalizer import normalize_job, normalize_jobs
from src.storage.job_store import JobStore


SAMPLE_PREFERENCES = {
    "candidate": {
        "education": {"degree": "B.Tech", "specialization": ["Computer Science", "Data Science"]},
        "experience": {"preferred": ["fresher", "graduate", "trainee", "0-1 years", "0-2 years"]},
    },
    "roles": {
        "ai_ml": ["AI Engineer", "ML Engineer", "Data Scientist", "Applied AI Engineer"],
        "genai": ["GenAI Engineer", "LLM Engineer", "RAG Engineer"],
        "backend": ["Python Backend Engineer", "FastAPI Developer"],
    },
    "locations": {
        "priority": {
            1: ["Noida", "Greater Noida"],
            2: ["New Delhi", "Delhi"],
            3: ["Gurugram", "Gurgaon"],
            4: ["Bangalore", "Bengaluru"],
            5: ["Jaipur"],
            6: ["Pune"],
            7: ["Mumbai"],
        },
        "remote": ["Remote India", "India Remote"],
    },
    "skills": {
        "programming": ["Python", "C++", "SQL"],
        "backend": ["FastAPI", "Flask", "REST APIs"],
        "ai_ml": ["Machine Learning", "Deep Learning", "Pandas", "NumPy", "PyTorch"],
        "genai": ["LLM", "Generative AI", "LangChain", "RAG"],
    },
    "matching": {
        "minimum_score_to_include": 55,
    },
    "sources": {
        "preferred": ["official_company_careers", "LinkedIn", "Wellfound"],
        "company_boards": [],
    },
}


class MockPipelineCollector(BaseCollector):
    def __init__(self, name: str, jobs: List[Dict[str, Any]], should_fail: bool = False):
        self._name = name
        self._jobs = jobs
        self._should_fail = should_fail

    @property
    def source_name(self) -> str:
        return self._name

    def collect(self) -> CollectorResult:
        if self._should_fail:
            raise RuntimeError("API timeout")
        return CollectorResult(
            source=self.source_name,
            jobs=self._jobs,
            status=CollectorStatus.SUCCESS if self._jobs else CollectorStatus.EMPTY,
            count=len(self._jobs),
        )


def test_batch_normalization():
    """Verify batch normalization handles valid and malformed dicts safely."""
    raw_list = [
        {"company": "Google", "title": "AI Engineer", "location": "Bangalore"},
        None,
        "not-a-dict",
        {"company": "Meta", "title": "ML Engineer", "location": "Remote India"},
    ]
    jobs = normalize_jobs(raw_list)
    assert len(jobs) == 2
    assert jobs[0].company == "Google"
    assert jobs[1].company == "Meta"


def test_pipeline_execution_and_counts(tmp_path):
    """End-to-end test of the central pipeline flow and counter tracking."""
    db_path = str(tmp_path / "test_pipe.db")
    store = JobStore(db_path)

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    future_deadline = (datetime.now(timezone.utc) + timedelta(days=5)).strftime("%Y-%m-%d")
    past_deadline = (datetime.now(timezone.utc) - timedelta(days=2)).strftime("%Y-%m-%d")

    raw_jobs_success = [
        # Job 1: Valid fresh job in Bangalore
        {
            "company": "OpenAI",
            "title": "AI Engineer",
            "location": "Bangalore",
            "skills": ["Python", "PyTorch", "LLM", "RAG"],
            "posting_date": today_str,
            "deadline": future_deadline,
            "application_url": "https://openai.com/jobs/1",
        },
        # Job 2: Duplicate of Job 1 (same company, title, location)
        {
            "company": "OpenAI",
            "title": "AI Engineer",
            "location": "Bangalore",
            "skills": ["Python", "PyTorch"],
            "application_url": "https://openai.com/jobs/1",
        },
        # Job 3: Expired deadline
        {
            "company": "DeepMind",
            "title": "ML Engineer",
            "location": "Noida",
            "skills": ["Python", "Machine Learning"],
            "posting_date": today_str,
            "deadline": past_deadline,
            "application_url": "https://deepmind.com/jobs/2",
        },
    ]

    success_collector = MockPipelineCollector("official_careers", raw_jobs_success)
    failing_collector = MockPipelineCollector("failing_source", [], should_fail=True)

    result = run_pipeline(
        preferences=SAMPLE_PREFERENCES,
        store=store,
        collectors=[success_collector, failing_collector],
    )

    assert isinstance(result, PipelineResult)
    # Collected count: 3
    assert result.collected_count == 3
    # Normalized count: 3
    assert result.normalized_count == 3
    # Deduplicated count: 2 (Job 2 merged into Job 1)
    assert result.deduplicated_count == 2
    # All are new in store: 2
    assert result.new_count == 2
    # Expired Job 3 filtered out, only Job 1 survives
    assert result.filtered_count == 1
    assert len(result.reportable_jobs) == 1
    assert result.reportable_jobs[0].company == "OpenAI"

    # Confirm change detection did NOT save jobs to DB
    assert store.count() == 0


def test_posting_date_does_not_overwrite_change_detection_is_new(tmp_path):
    """
    Architectural rule:
    job.is_new is set by change detection (is it newly seen in persistent storage?).
    Freshness classification (NEW_TODAY vs OLDER_ACTIVE) does NOT overwrite job.is_new.
    """
    db_path = str(tmp_path / "freshness_test.db")
    store = JobStore(db_path)

    # Job was posted 5 days ago (ACTIVE freshness), but system sees it for the first time
    five_days_ago = (datetime.now(timezone.utc) - timedelta(days=5)).strftime("%Y-%m-%d")
    raw_job = {
        "company": "Cohere",
        "title": "LLM Engineer",
        "location": "Noida",
        "skills": ["Python", "LLM", "LangChain"],
        "posting_date": five_days_ago,
        "application_url": "https://cohere.com/jobs/llm",
    }

    collector = MockPipelineCollector("test_source", [raw_job])
    result = run_pipeline(
        preferences=SAMPLE_PREFERENCES,
        store=store,
        collectors=[collector],
    )

    assert len(result.reportable_jobs) == 1
    job = result.reportable_jobs[0]
    # is_new remains True from change detection
    assert job.is_new is True
