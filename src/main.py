import os
from datetime import datetime
from pathlib import Path

import yaml

from src.collectors.runner import run_collectors
from src.email.resend_client import send_daily_report
from src.email.subject import build_subject
from src.matching.matcher import calculate_match
from src.processing.deduplicator import deduplicate_jobs
from src.processing.filter import filter_jobs
from src.processing.freshness import process_freshness
from src.processing.link_validator import validate_links
from src.processing.normalizer import normalize_jobs
from src.reporting.report_builder import build_report
from src.reporting.templates import render_daily_report
from src.storage.change_detector import detect_changes
from src.storage.job_store import JobStore


BASE_DIR = Path(__file__).resolve().parent.parent

PREFERENCES_FILE = (
    BASE_DIR
    / "config"
    / "preferences.yaml"
)

DATABASE_FILE = (
    BASE_DIR
    / "jobs.db"
)

RECIPIENT = os.getenv(
    "JOB_REPORT_EMAIL",
    "lakshyadogra05@gmail.com",
)


def load_preferences() -> dict:
    """Load user preferences."""

    with open(
        PREFERENCES_FILE,
        "r",
        encoding="utf-8",
    ) as file:
        return yaml.safe_load(file) or {}


def main():
    """Run the complete job opportunity pipeline."""

    print("=" * 60)
    print("AI JOB OPPORTUNITY AGENT")
    print("=" * 60)

    preferences = load_preferences()

    print("[1/10] Running collectors...")

    # Collectors will be added here progressively.
    collectors = []

    raw_jobs = run_collectors(
        collectors
    )

    print(
        f"Collected {len(raw_jobs)} raw jobs."
    )

    print("[2/10] Normalizing...")

    jobs = normalize_jobs(
        raw_jobs
    )

    print(
        f"Normalized {len(jobs)} jobs."
    )

    print("[3/10] Deduplicating...")

    jobs = deduplicate_jobs(
        jobs
    )

    print(
        f"After deduplication: {len(jobs)}"
    )

    print("[4/10] Processing freshness...")

    jobs = process_freshness(
        jobs
    )

    print("[5/10] Validating links...")

    jobs = validate_links(
        jobs
    )

    print("[6/10] Checking job history...")

    store = JobStore(
        str(DATABASE_FILE)
    )

    jobs = detect_changes(
        jobs,
        store,
    )

    print("[7/10] Matching jobs...")

    matched_jobs = []

    for job in jobs:
        job = calculate_match(
            job,
            preferences,
        )

        matched_jobs.append(job)

    print("[8/10] Filtering...")

    filtered_jobs = filter_jobs(
        matched_jobs
    )

    print(
        f"Jobs in report: "
        f"{len(filtered_jobs)}"
    )

    print("[9/10] Building report...")

    report = build_report(
        filtered_jobs
    )

    report_date = datetime.now().strftime(
        "%d %b %Y"
    )

    html = render_daily_report(
        report,
        report_date,
    )

    subject = build_subject(
        report_date,
        len(report.new_today),
        len(report.apply_first),
    )

    print("[10/10] Sending email...")

    send_daily_report(
        recipient=RECIPIENT,
        subject=subject,
        html=html,
    )

    print("Email sent successfully.")

    print("Updating job database...")

    for job in jobs:
        store.save(job)

    print("=" * 60)
    print("PIPELINE COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
