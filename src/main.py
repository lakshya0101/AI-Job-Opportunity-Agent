import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

import yaml

from src.collectors.base import CollectorStatus, SourceHealth
from src.email.resend_client import send_daily_report
from src.email.subject import build_subject
from src.pipeline import (
    PipelineResult,
    collect_and_process_base_jobs,
    evaluate_profile_jobs,
    get_profiles,
)
from src.reporting.excel_report import generate_excel_report, get_profile_excel_filename
from src.reporting.report_builder import DailyReport, build_report
from src.reporting.templates import render_daily_report
from src.storage.job_store import JobStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("AI-Job-Opportunity-Agent")

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = BASE_DIR / "config" / "preferences.yaml"
DEFAULT_DB_PATH = BASE_DIR / "data" / "jobs.db"
DEFAULT_OUTPUT_DIR = BASE_DIR / "output"


@dataclass
class ProfileRunResult:
    """Outcome of reporting for a single candidate profile."""
    profile_key: str
    profile_name: str
    recipient: str
    report: DailyReport
    html_content: str
    excel_path: Path
    subject: str
    email_status: str = "PENDING"
    error: Optional[str] = None


@dataclass
class ProductionRunResult:
    """Structured outcome of a full production orchestration cycle."""
    success: bool
    pipeline_status: str = "NOT_STARTED"
    html_status: str = "PENDING"
    excel_status: str = "PENDING"
    email_status: str = "PENDING"
    persistence_status: str = "PENDING"
    pipeline_result: Optional[PipelineResult] = None
    report: Optional[DailyReport] = None
    excel_path: Optional[Path] = None
    profile_results: Dict[str, ProfileRunResult] = field(default_factory=dict)
    error: Optional[str] = None


def load_preferences(config_path: Path = DEFAULT_CONFIG_PATH) -> Dict[str, Any]:
    """Load configuration from preferences YAML file."""
    if not config_path.exists():
        raise FileNotFoundError(f"Preferences configuration file not found at: {config_path}")

    with open(config_path, "r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def run_production(
    config_path: Path = DEFAULT_CONFIG_PATH,
    db_path: Path = DEFAULT_DB_PATH,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    dry_run: bool = False,
    collectors: Optional[List[Any]] = None,
) -> ProductionRunResult:
    """
    Execute the multi-user end-to-end production workflow.

    Sequential Stages:
    1. Configuration & Storage initialization
    2. Shared Upstream Pipeline (Collect once -> Normalize -> Deduplicate -> Change Detection -> Freshness -> Link Validation)
    3. Failure safety check (Verify not all collectors failed)
    4. Per-profile Evaluation, Reporting, HTML rendering, and Excel generation
    5. Transactional email dispatch per candidate
    6. Database persistence (strictly upon all emails succeeding)
    """
    start_time = datetime.now(timezone.utc)
    report_date = start_time.strftime("%d %b %Y")
    date_slug = start_time.strftime("%Y-%m-%d")

    logger.info("=" * 60)
    logger.info(f"AI JOB OPPORTUNITY AGENT - PRODUCTION RUN ({report_date})")
    logger.info(f"Mode: {'DRY RUN (No email/persistence)' if dry_run else 'LIVE DISPATCH'}")
    logger.info("=" * 60)

    # 1. Load configuration and initialize storage
    try:
        preferences = load_preferences(config_path)
    except Exception as exc:
        logger.error(f"Failed to load preferences: {exc}")
        return ProductionRunResult(
            success=False,
            pipeline_status="CONFIG_FAILED",
            error=str(exc),
        )

    store = JobStore(str(db_path))

    # 2. Shared Upstream Pipeline Execution (Collect once)
    try:
        base_jobs, source_health, metrics = collect_and_process_base_jobs(
            preferences,
            store,
            collectors=collectors,
        )
    except Exception as exc:
        logger.error(f"Upstream pipeline execution failed: {exc}", exc_info=True)
        return ProductionRunResult(
            success=False,
            pipeline_status="PIPELINE_FAILED",
            error=str(exc),
        )

    # 3. All-Collectors-Failed Safety Check
    executed_sources = [
        sh for sh in source_health
        if sh.status != CollectorStatus.NOT_IMPLEMENTED
    ]
    if executed_sources and all(sh.status == CollectorStatus.FAILED for sh in executed_sources):
        err_msg = "All executed job collectors failed. Halting to prevent misleading empty report."
        logger.error(err_msg)
        return ProductionRunResult(
            success=False,
            pipeline_status="ALL_COLLECTORS_FAILED",
            error=err_msg,
        )

    logger.info("Upstream Pipeline Execution Metrics:")
    logger.info(f"  Collected:   {metrics['collected_count']}")
    logger.info(f"  Normalized:  {metrics['normalized_count']}")
    logger.info(f"  Unique:      {metrics['deduplicated_count']}")

    # 4. Process each Candidate Profile
    profiles = get_profiles(preferences)
    profile_results: Dict[str, ProfileRunResult] = {}
    primary_pipeline_result: Optional[PipelineResult] = None
    primary_report: Optional[DailyReport] = None
    primary_excel_path: Optional[Path] = None

    output_dir.mkdir(parents=True, exist_ok=True)

    for profile_key, profile_cfg in profiles.items():
        profile_name = profile_cfg.get("name", profile_key.capitalize())
        logger.info(f"\n--- Evaluating Profile: {profile_name} ({profile_key}) ---")

        # Evaluate jobs against candidate criteria
        pipeline_res = evaluate_profile_jobs(
            base_jobs=base_jobs,
            profile_config=profile_cfg,
            source_health=source_health,
            metrics=metrics,
            global_preferences=preferences,
        )

        logger.info(f"  Matched:     {pipeline_res.matched_count}")
        logger.info(f"  Reportable:  {pipeline_res.filtered_count}")

        # Build DailyReport
        report = build_report(
            pipeline_res.reportable_jobs,
            pipeline_result=pipeline_res,
        )

        # Render HTML
        show_ba = bool(profile_key == "lakshya" or "business_analysis" in profile_cfg.get("roles", {}))
        html_content = render_daily_report(
            report,
            report_date,
            profile_name=profile_name,
            show_business_analyst=show_ba,
        )

        # Generate Excel
        excel_filename = get_profile_excel_filename(profile_key, date_slug)
        excel_path = output_dir / excel_filename
        generate_excel_report(report, excel_path, report_date, profile_name=profile_name)

        # Subject and recipient
        email_cfg = profile_cfg.get("email_config", {})
        env_key = f"JOB_REPORT_EMAIL_{profile_key.upper()}"
        recipient = os.getenv(env_key)
        if not recipient and len(profiles) == 1:
            recipient = os.getenv("JOB_REPORT_EMAIL")
        if not recipient:
            recipient = email_cfg.get("recipient", profile_cfg.get("email", "lakshyadogra05@gmail.com"))

        subject_prefix = email_cfg.get("subject_prefix", f"🚀 {profile_name}'s Daily Job Opportunities")
        subject = build_subject(
            report_date=report_date,
            new_count=report.summary.new,
            apply_first_count=len(report.apply_first),
            prefix=subject_prefix,
        )

        prof_res = ProfileRunResult(
            profile_key=profile_key,
            profile_name=profile_name,
            recipient=recipient,
            report=report,
            html_content=html_content,
            excel_path=excel_path,
            subject=subject,
        )
        profile_results[profile_key] = prof_res

        # Keep primary profile for backward compatibility
        if primary_pipeline_result is None or profile_key == "lakshya":
            primary_pipeline_result = pipeline_res
            primary_report = report
            primary_excel_path = excel_path

    # 5. Dry Run Intercept
    if dry_run:
        logger.info("\nDRY RUN COMPLETE: Email sending and persistent database storage skipped.")
        return ProductionRunResult(
            success=True,
            pipeline_status="SUCCESS",
            html_status="SUCCESS",
            excel_status="SUCCESS",
            email_status="SKIPPED (DRY RUN)",
            persistence_status="SKIPPED (DRY RUN)",
            pipeline_result=primary_pipeline_result,
            report=primary_report,
            excel_path=primary_excel_path,
            profile_results=profile_results,
        )

    # 6. Transactional Email Dispatch
    email_failures: List[str] = []
    for profile_key, prof_res in profile_results.items():
        profile_cfg = profiles[profile_key]
        email_cfg = profile_cfg.get("email_config", {})
        attach_excel = email_cfg.get("attach_excel", True)
        attachment = prof_res.excel_path if attach_excel else None

        try:
            send_daily_report(
                recipient=prof_res.recipient,
                subject=prof_res.subject,
                html=prof_res.html_content,
                attachment_path=attachment,
            )
            prof_res.email_status = "SUCCESS"
            logger.info(f"{prof_res.profile_name} email: SUCCESS (Sent to {prof_res.recipient})")
        except Exception as exc:
            prof_res.email_status = "FAILED"
            prof_res.error = str(exc)
            email_failures.append(f"{prof_res.profile_name} ({prof_res.recipient}): {exc}")
            logger.error(f"{prof_res.profile_name} email: FAILED ({exc})")

    # 7. Transactional State Persistence (Strictly if ALL emails succeed)
    if email_failures:
        err_msg = f"Email delivery failed for {len(email_failures)} recipient(s): {'; '.join(email_failures)}"
        logger.error(f"State persistence: SKIPPED (Due to email failure)")
        return ProductionRunResult(
            success=False,
            pipeline_status="SUCCESS",
            html_status="SUCCESS",
            excel_status="SUCCESS",
            email_status="FAILED",
            persistence_status="SKIPPED (DUE TO EMAIL FAILURE)",
            pipeline_result=primary_pipeline_result,
            report=primary_report,
            excel_path=primary_excel_path,
            profile_results=profile_results,
            error=err_msg,
        )

    # Persist all collected base jobs
    try:
        store.save_all(base_jobs)
        persistence_status = "SUCCESS"
        logger.info(f"State persistence: SUCCESS (Persisted {len(base_jobs)} records to {db_path.name})")
    except Exception as exc:
        logger.error(f"State persistence: FAILED ({exc})", exc_info=True)
        persistence_status = f"FAILED ({exc})"

    logger.info("=" * 60)
    logger.info("PRODUCTION RUN COMPLETED SUCCESSFULLY")
    logger.info("=" * 60)

    return ProductionRunResult(
        success=True,
        pipeline_status="SUCCESS",
        html_status="SUCCESS",
        excel_status="SUCCESS",
        email_status="SUCCESS",
        persistence_status=persistence_status,
        pipeline_result=primary_pipeline_result,
        report=primary_report,
        excel_path=primary_excel_path,
        profile_results=profile_results,
    )


def main():
    """CLI entrypoint for executing production runs."""
    parser = argparse.ArgumentParser(description="AI Job Opportunity Agent - Daily Production Orchestrator")
    parser.add_argument("--dry-run", action="store_true", help="Execute pipeline and generate reports without sending email or updating persistent DB.")
    parser.add_argument("--config", type=str, default=str(DEFAULT_CONFIG_PATH), help="Path to preferences.yaml")
    parser.add_argument("--db-path", type=str, default=str(DEFAULT_DB_PATH), help="Path to jobs.db SQLite database")
    parser.add_argument("--output-dir", type=str, default=str(DEFAULT_OUTPUT_DIR), help="Output directory for generated reports")

    args = parser.parse_args()

    result = run_production(
        config_path=Path(args.config),
        db_path=Path(args.db_path),
        output_dir=Path(args.output_dir),
        dry_run=args.dry_run,
    )

    if not result.success:
        logger.error(f"Production run failed: {result.error}")
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
