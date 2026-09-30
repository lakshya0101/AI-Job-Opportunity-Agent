import copy
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
import yaml

from src.collectors.base import BaseCollector, CollectorResult, CollectorStatus
from src.main import ProductionRunResult, load_preferences, run_production
from src.matching.matcher import calculate_match, score_location_match
from src.models.job import Job
from src.pipeline import (
    collect_and_process_base_jobs,
    evaluate_profile_jobs,
    get_profiles,
    run_pipeline,
)
from src.processing.filter import filter_jobs, is_allowed_location, should_include
from src.reporting.excel_report import (
    generate_excel_report,
    get_profile_excel_filename,
)
from src.reporting.report_builder import build_report
from src.reporting.templates import render_daily_report
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
def config_preferences():
    config_path = Path("config") / "preferences.yaml"
    return load_preferences(config_path)


# 1. Both profiles load successfully
def test_1_both_profiles_load_successfully(config_preferences):
    profiles = get_profiles(config_preferences)
    assert "lakshya" in profiles
    assert "smriti" in profiles
    assert profiles["lakshya"]["name"] == "Lakshya Dogra"
    assert profiles["smriti"]["name"] == "Smriti Verma"


# 2. Lakshya profile remains unchanged
def test_2_lakshya_profile_remains_unchanged(config_preferences):
    lakshya = config_preferences["profiles"]["lakshya"]
    assert lakshya["email"] == "lakshyadogra05@gmail.com"
    assert "Business Analyst" in lakshya["roles"]["business_analysis"]
    assert "Python Backend Engineer" in lakshya["roles"]["backend"]
    assert "AI/ML Engineer" in lakshya["roles"]["ai_ml"]
    # Locations
    priority = lakshya["locations"]["priority"]
    assert "Noida" in priority[1]
    assert "Jaipur" in priority[5]


# 3. Smriti profile contains the correct roles
def test_3_smriti_profile_contains_correct_roles(config_preferences):
    smriti = config_preferences["profiles"]["smriti"]
    assert smriti["email"] == "smritiverma.6725@gmail.com"
    roles = smriti["roles"]
    
    # SDE
    assert any("sde" in r.lower() or "software development engineer" in r.lower() for r in roles.get("sde", []))
    # AIML
    assert any("aiml" in r.lower() or "ai/ml" in r.lower() for r in roles.get("ai_ml", []))
    # GenAI
    assert any("genai" in r.lower() or "generative ai" in r.lower() for r in roles.get("genai", []))
    # FDE / Fullstack
    assert any("fde" in r.lower() or "full-stack" in r.lower() for r in roles.get("fullstack", []))
    # Backend
    assert any("backend engineer" in r.lower() for r in roles.get("backend", []))


# 4. Smriti location priority is correct (1. Noida, 2. Delhi, 3. Gurgaon, 4. Bangalore, 5. Hyderabad, 6. Pune, 7. Mumbai)
def test_4_smriti_location_priority_is_correct(config_preferences):
    smriti = config_preferences["profiles"]["smriti"]
    priority = smriti["locations"]["priority"]
    
    assert any("noida" in loc.lower() for loc in priority[1])
    assert any("delhi" in loc.lower() for loc in priority[2])
    assert any("gurgaon" in loc.lower() or "gurugram" in loc.lower() for loc in priority[3])
    assert any("bangalore" in loc.lower() or "bengaluru" in loc.lower() for loc in priority[4])
    assert any("hyderabad" in loc.lower() for loc in priority[5])
    assert any("pune" in loc.lower() for loc in priority[6])
    assert any("mumbai" in loc.lower() for loc in priority[7])


# 5. Smriti is fresher/0–2 compatible
def test_5_smriti_experience_compatible(config_preferences):
    smriti = config_preferences["profiles"]["smriti"]
    pref_exp = smriti["candidate"]["experience"]["preferred"]
    assert any("fresher" in e.lower() for e in pref_exp)
    assert any("0-2 years" in e.lower() for e in pref_exp)


# 6. An SDE job matches Smriti
def test_6_sde_job_matches_smriti(config_preferences):
    smriti = config_preferences["profiles"]["smriti"]
    job = Job(
        company="Amazon",
        title="Software Development Engineer I (SDE 1)",
        location="Noida",
        experience="0-1 years / Fresher",
        skills=["Java", "Python", "Data Structures"],
        application_url="https://amazon.jobs/1",
    )
    evaluated = calculate_match(job, smriti)
    assert evaluated.role_score >= 27.0
    assert should_include(evaluated, preferences=smriti) is True


# 7. An AIML job matches Smriti
def test_7_aiml_job_matches_smriti(config_preferences):
    smriti = config_preferences["profiles"]["smriti"]
    job = Job(
        company="Microsoft",
        title="AI/ML Engineer - Entry Level",
        location="Gurgaon",
        experience="Fresher",
        skills=["Python", "PyTorch", "Machine Learning"],
        application_url="https://careers.microsoft.com/1",
    )
    evaluated = calculate_match(job, smriti)
    assert evaluated.role_score >= 27.0
    assert should_include(evaluated, preferences=smriti) is True


# 8. A GenAI job matches Smriti
def test_8_genai_job_matches_smriti(config_preferences):
    smriti = config_preferences["profiles"]["smriti"]
    job = Job(
        company="Cohere",
        title="Generative AI Engineer",
        location="Bangalore",
        experience="0-2 years",
        skills=["Python", "LLM", "LangChain", "RAG"],
        application_url="https://cohere.com/jobs/1",
    )
    evaluated = calculate_match(job, smriti)
    assert evaluated.role_score >= 27.0
    assert should_include(evaluated, preferences=smriti) is True


# 9. An FDE/full-stack job matches Smriti
def test_9_fde_fullstack_job_matches_smriti(config_preferences):
    smriti = config_preferences["profiles"]["smriti"]
    job = Job(
        company="Postman",
        title="Full-Stack Engineer (FDE)",
        location="Noida",
        experience="Graduate Trainee",
        skills=["React", "Node.js", "TypeScript", "Python"],
        application_url="https://postman.com/jobs/1",
    )
    evaluated = calculate_match(job, smriti)
    assert evaluated.role_score >= 27.0
    assert should_include(evaluated, preferences=smriti) is True


# 10. An unrelated marketing job does not match Smriti
def test_10_unrelated_marketing_job_rejected_smriti(config_preferences):
    smriti = config_preferences["profiles"]["smriti"]
    job = Job(
        company="HubSpot",
        title="Digital Marketing Specialist & SEO Analyst",
        location="Noida",
        experience="Fresher",
        skills=["SEO", "Content Marketing", "Analytics"],
        application_url="https://hubspot.com/jobs/1",
    )
    evaluated = calculate_match(job, smriti)
    assert evaluated.role_score == 0.0
    assert should_include(evaluated, preferences=smriti) is False


# 11. A senior SDE role is rejected when experience is incompatible
def test_11_senior_sde_role_rejected(config_preferences):
    smriti = config_preferences["profiles"]["smriti"]
    job = Job(
        company="Google",
        title="Senior Software Development Engineer (SDE III)",
        location="Bangalore",
        experience="8+ years of experience required",
        skills=["Java", "Python", "Distributed Systems"],
        application_url="https://google.com/jobs/1",
    )
    evaluated = calculate_match(job, smriti)
    assert evaluated.experience_score < 5.0
    assert should_include(evaluated, preferences=smriti) is False


# 12. A Noida role receives the appropriate location preference (Priority 1 = 20)
def test_12_noida_location_preference(config_preferences):
    smriti = config_preferences["profiles"]["smriti"]
    job = Job(company="X", title="SDE", location="Noida, Sector 62")
    evaluated = calculate_match(job, smriti)
    assert evaluated.location_score == 20.0


# 13. A Bangalore role receives the appropriate location preference (Priority 4 = 16)
def test_13_bangalore_location_preference(config_preferences):
    smriti = config_preferences["profiles"]["smriti"]
    job = Job(company="X", title="SDE", location="Bengaluru, Karnataka")
    evaluated = calculate_match(job, smriti)
    assert evaluated.location_score == 16.0


# 14. A Hyderabad role is recognized for Smriti (Priority 5 = 15)
def test_14_hyderabad_recognized_for_smriti(config_preferences):
    smriti = config_preferences["profiles"]["smriti"]
    job = Job(
        company="Microsoft",
        title="Software Engineer",
        location="Hyderabad, Telangana",
        experience="0-1 years",
        skills=["Python", "C++", "SQL"],
        application_url="https://microsoft.com/jobs/2",
    )
    evaluated = calculate_match(job, smriti)
    assert evaluated.location_score == 15.0
    assert is_allowed_location(evaluated, preferences=smriti) is True
    assert should_include(evaluated, preferences=smriti) is True


# 15. Lakshya and Smriti can receive different match scores for the same job
def test_15_differential_scoring_between_profiles(config_preferences):
    lakshya = config_preferences["profiles"]["lakshya"]
    smriti = config_preferences["profiles"]["smriti"]

    # Job: Business Analyst in Jaipur
    job_ba = Job(
        company="McKinsey",
        title="Business Analyst",
        location="Jaipur",
        experience="Fresher",
        skills=["SQL", "Python", "Tableau", "Data Analysis"],
        application_url="https://mckinsey.com/jobs/1",
    )
    eval_lakshya = calculate_match(copy.copy(job_ba), lakshya)
    eval_smriti = calculate_match(copy.copy(job_ba), smriti)

    # Lakshya matches Business Analyst; Smriti rejects non-engineering BA
    assert eval_lakshya.role_score >= 27.0
    assert eval_smriti.role_score == 0.0
    assert eval_lakshya.match_score > eval_smriti.match_score


# 16. The same job can appear in both reports if appropriate
def test_16_shared_opportunity_matches_both(config_preferences):
    lakshya = config_preferences["profiles"]["lakshya"]
    smriti = config_preferences["profiles"]["smriti"]

    job_ai = Job(
        company="OpenAI",
        title="AI Engineer",
        location="Noida",
        experience="0-2 years",
        skills=["Python", "LLM", "PyTorch", "RAG"],
        application_url="https://openai.com/jobs/1",
    )
    eval_lakshya = calculate_match(copy.copy(job_ai), lakshya)
    eval_smriti = calculate_match(copy.copy(job_ai), smriti)

    assert should_include(eval_lakshya, preferences=lakshya) is True
    assert should_include(eval_smriti, preferences=smriti) is True


# 17, 18, 19. Email recipient, personalized HTML, and XLSX attachment per candidate
def test_17_18_19_personalized_reports_and_emails(tmp_path, config_preferences):
    db_path = tmp_path / "jobs.db"
    out_dir = tmp_path / "output"

    job_1 = {
        "company": "DeepMind",
        "title": "AI Engineer",
        "location": "Noida",
        "experience": "Fresher",
        "skills": ["Python", "PyTorch", "LLM"],
        "posting_date": "2026-10-01",
        "application_url": "https://deepmind.com/jobs/1",
    }
    collector = MockJobCollector("c1", [job_1])

    sent_emails = []

    def mock_send(recipient, subject, html, attachment_path=None):
        sent_emails.append({
            "recipient": recipient,
            "subject": subject,
            "html": html,
            "attachment": attachment_path,
        })
        return {"id": f"msg_{len(sent_emails)}"}

    with patch("src.main.send_daily_report", side_effect=mock_send):
        res = run_production(
            config_path=Path("config") / "preferences.yaml",
            db_path=db_path,
            output_dir=out_dir,
            collectors=[collector],
        )

        assert res.success is True
        assert len(sent_emails) == 2

        # Email 1: Lakshya
        assert sent_emails[0]["recipient"] == "lakshyadogra05@gmail.com"
        assert "Lakshya" in sent_emails[0]["html"] or "AI Job Opportunity Report" in sent_emails[0]["html"]
        assert "lakshya" in str(sent_emails[0]["attachment"]).lower()

        # Email 2: Smriti
        assert sent_emails[1]["recipient"] == "smritiverma.6725@gmail.com"
        assert "Smriti" in sent_emails[1]["subject"]
        assert "Smriti Verma" in sent_emails[1]["html"]
        assert "smriti" in str(sent_emails[1]["attachment"]).lower()


# 20. If Lakshya email succeeds but Smriti email fails, jobs.db is NOT persisted
def test_20_transactional_email_failure_prevents_persistence(tmp_path):
    db_path = tmp_path / "jobs.db"
    out_dir = tmp_path / "output"

    job_1 = {
        "company": "Anthropic",
        "title": "AI Engineer",
        "location": "Noida",
        "experience": "Fresher",
        "skills": ["Python", "LLM"],
        "posting_date": "2026-10-01",
        "application_url": "https://anthropic.com/jobs/1",
    }
    collector = MockJobCollector("c1", [job_1])

    call_count = 0

    def mock_send_partial(recipient, subject, html, attachment_path=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {"id": "msg_lakshya_success"}
        raise RuntimeError("Smriti email delivery timed out")

    with patch("src.main.send_daily_report", side_effect=mock_send_partial):
        res = run_production(
            config_path=Path("config") / "preferences.yaml",
            db_path=db_path,
            output_dir=out_dir,
            collectors=[collector],
        )

        assert res.success is False
        assert res.email_status == "FAILED"
        assert "SKIPPED" in res.persistence_status

        # Database must still have 0 records!
        store = JobStore(str(db_path))
        assert store.count() == 0


# 21. If both emails succeed, jobs.db persistence occurs
def test_21_successful_all_emails_triggers_persistence(tmp_path):
    db_path = tmp_path / "jobs.db"
    out_dir = tmp_path / "output"

    job_1 = {
        "company": "Anthropic",
        "title": "AI Engineer",
        "location": "Noida",
        "experience": "Fresher",
        "skills": ["Python", "LLM"],
        "posting_date": "2026-10-01",
        "application_url": "https://anthropic.com/jobs/1",
    }
    collector = MockJobCollector("c1", [job_1])

    with patch("src.main.send_daily_report", return_value={"id": "msg_ok"}):
        res = run_production(
            config_path=Path("config") / "preferences.yaml",
            db_path=db_path,
            output_dir=out_dir,
            collectors=[collector],
        )

        assert res.success is True
        assert res.email_status == "SUCCESS"
        assert res.persistence_status == "SUCCESS"

        store = JobStore(str(db_path))
        assert store.count() == 1


# 22. Existing single-profile tests continue passing (verified by entire test suite)
def test_22_single_profile_backward_compatibility(tmp_path):
    store = JobStore(str(tmp_path / "jobs.db"))
    flat_config = {
        "candidate": {"experience": {"preferred": ["fresher"]}},
        "roles": {"ai_ml": ["AI Engineer"]},
        "locations": {"priority": {1: ["Noida"]}, "remote": ["Remote India"]},
        "skills": {"programming": ["Python"]},
        "matching": {"minimum_score_to_include": 55},
        "sources": {"preferred": ["c1"], "company_boards": []},
    }
    raw_job = {
        "company": "Scale AI",
        "title": "AI Engineer",
        "location": "Noida",
        "skills": ["Python"],
        "posting_date": "2026-10-01",
        "application_url": "https://scale.com/1",
    }
    res = run_pipeline(flat_config, store, collectors=[MockJobCollector("c1", [raw_job])])
    assert res.collected_count == 1
    assert res.filtered_count == 1
