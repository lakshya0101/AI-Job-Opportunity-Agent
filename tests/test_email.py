import base64
import os
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from src.email.resend_client import _prepare_attachment, send_daily_report, send_email
from src.email.subject import build_subject
from src.models.job import Job
from src.pipeline import PipelineResult
from src.reporting.excel_report import generate_excel_report
from src.reporting.report_builder import build_report
from src.reporting.templates import render_daily_report


def test_subject_generation():
    """Verify subject formatting with prefix, date, and metrics."""
    s1 = build_subject("01 Oct 2026", new_count=3, apply_first_count=5)
    assert s1 == "🚀 Daily Job Opportunities — 01 Oct 2026 | 3 New | 5 Apply First"

    s2 = build_subject("01 Oct 2026", new_count=0, apply_first_count=0, prefix="💼 Jobs")
    assert s2 == "💼 Jobs — 01 Oct 2026"


def test_missing_api_key_raises_error(monkeypatch):
    """Attempting to send an email without RESEND_API_KEY raises a clear RuntimeError."""
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="RESEND_API_KEY environment variable is not set"):
        send_email(
            recipient="lakshyadogra05@gmail.com",
            subject="Test",
            html="<p>Test</p>",
        )


def test_mocked_successful_send(monkeypatch):
    """Verify payload structure and Authorization header in successful API call."""
    monkeypatch.setenv("RESEND_API_KEY", "re_test_dummy_key_123")
    monkeypatch.setenv("EMAIL_SENDER", "test_sender@resend.dev")

    with patch("requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "msg_12345"}
        mock_post.return_value = mock_response

        res = send_email(
            recipient="lakshyadogra05@gmail.com",
            subject="🚀 Daily Jobs",
            html="<h1>Report</h1>",
        )

        assert res["id"] == "msg_12345"
        assert mock_post.called

        args, kwargs = mock_post.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer re_test_dummy_key_123"
        payload = kwargs["json"]
        assert payload["to"] == ["lakshyadogra05@gmail.com"]
        assert payload["from"] == "test_sender@resend.dev"
        assert payload["subject"] == "🚀 Daily Jobs"
        assert payload["html"] == "<h1>Report</h1>"
        assert "attachments" not in payload


def test_excel_attachment_encoding_and_inclusion(tmp_path, monkeypatch):
    """Verify Excel file is base64-encoded and included in payload."""
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")

    dummy_excel = tmp_path / "test_report.xlsx"
    dummy_excel.write_bytes(b"dummy binary content for excel")

    with patch("requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "msg_with_att"}
        mock_post.return_value = mock_response

        res = send_daily_report(
            recipient="lakshyadogra05@gmail.com",
            subject="Jobs + Attachment",
            html="<p>See attached</p>",
            attachment_path=dummy_excel,
        )

        assert res["id"] == "msg_with_att"
        payload = mock_post.call_args[1]["json"]
        assert "attachments" in payload
        assert len(payload["attachments"]) == 1

        att = payload["attachments"][0]
        assert att["filename"] == "test_report.xlsx"
        decoded = base64.b64decode(att["content"])
        assert decoded == b"dummy binary content for excel"


def test_attachment_validation_errors(tmp_path):
    """Verify missing file, empty file, and invalid extension checks."""
    missing = tmp_path / "nonexistent.xlsx"
    with pytest.raises(FileNotFoundError):
        _prepare_attachment(missing)

    empty_file = tmp_path / "empty.xlsx"
    empty_file.write_bytes(b"")
    with pytest.raises(ValueError, match="Attachment file is empty"):
        _prepare_attachment(empty_file)

    bad_ext = tmp_path / "script.exe"
    bad_ext.write_bytes(b"some content")
    with pytest.raises(ValueError, match="Unsupported attachment file type"):
        _prepare_attachment(bad_ext)


def test_mocked_end_to_end_email_construction(tmp_path, monkeypatch):
    """
    End-to-end integration test:
    PipelineResult -> DailyReport -> HTML -> Excel -> send_daily_report (mocked)
    """
    monkeypatch.setenv("RESEND_API_KEY", "re_mock_test_key")

    job = Job(
        company="OpenAI",
        title="AI Engineer",
        location="Remote India",
        match_score=92.0,
        application_url="https://openai.com/careers/ai",
        is_new=True,
    )

    pipe_res = PipelineResult(
        collected_count=1,
        normalized_count=1,
        deduplicated_count=1,
        new_count=1,
        updated_count=0,
        matched_count=1,
        filtered_count=1,
        source_health=[],
        reportable_jobs=[job],
    )

    report = build_report([job], pipeline_result=pipe_res)
    html_content = render_daily_report(report, "01 Oct 2026")

    excel_path = tmp_path / "ai_jobs_01_Oct_2026.xlsx"
    generate_excel_report(report, excel_path, "01 Oct 2026")

    subject = build_subject("01 Oct 2026", new_count=report.summary.new, apply_first_count=len(report.apply_first))

    with patch("requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "msg_pipeline_e2e"}
        mock_post.return_value = mock_response

        result = send_daily_report(
            recipient="lakshyadogra05@gmail.com",
            subject=subject,
            html=html_content,
            attachment_path=excel_path,
        )

        assert result["id"] == "msg_pipeline_e2e"
        payload = mock_post.call_args[1]["json"]

        assert payload["to"] == ["lakshyadogra05@gmail.com"]
        assert "01 Oct 2026" in payload["subject"]
        assert "OpenAI" in payload["html"]
        assert payload["attachments"][0]["filename"] == "ai_jobs_01_Oct_2026.xlsx"
