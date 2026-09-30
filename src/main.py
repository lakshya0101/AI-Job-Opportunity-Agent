import argparse
from dataclasses import dataclass
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
from src.pipeline import PipelineResult, run_pipeline
from src.reporting.excel_report import generate_excel_report, get_default_excel_filename
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
    Execute the end-to-end production workflow.

    Sequential Stages:
    1. Configuration & Storage initialization
    2. Central pipeline execution (Collect -> Normalize -> Deduplicate -> Change Detection -> Freshness -> Match -> Filter)
    3. Failure safety check (Verify not all collectors failed)
    4. Daily report construction
    5. HTML email rendering
    6. Excel report generation
    7. Email dispatch via Resend
    8. Database persistence (strictly upon verified email dispatch)
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

    # 2. Central Pipeline Execution
    try:
        pipeline_result = run_pipeline(preferences, store, collectors=collectors)
    except Exception as exc:
        logger.error(f"Central pipeline execution failed: {exc}", exc_info=True)
        return ProductionRunResult(
            success=False,
            pipeline_status="PIPELINE_FAILED",
            error=str(exc),
        )

    # 3. All-Collectors-Failed Safety Check
    executed_sources = [
        sh for sh in pipeline_result.source_health
        if sh.status != CollectorStatus.NOT_IMPLEMENTED
    ]
    if executed_sources and all(sh.status == CollectorStatus.FAILED for sh in executed_sources):
        err_msg = "All executed job collectors failed. Halting to prevent misleading empty report."
        logger.error(err_msg)
        return ProductionRunResult(
            success=False,
            pipeline_status="ALL_COLLECTORS_FAILED",
            pipeline_result=pipeline_result,
            error=err_msg,
        )

    # 4. Build Structured Daily Report
    report = build_report(
        pipeline_result.reportable_jobs,
        pipeline_result=pipeline_result,
    )

    logger.info("Pipeline Execution Metrics:")
    logger.info(f"  Collected:   {pipeline_result.collected_count}")
    logger.info(f"  Unique:      {pipeline_result.deduplicated_count}")
    logger.info(f"  New (Seen):  {pipeline_result.new_count}")
    logger.info(f"  Updated:     {pipeline_result.updated_count}")
    logger.info(f"  Matched:     {pipeline_result.matched_count}")
    logger.info(f"  Reportable:  {pipeline_result.filtered_count}")

    # 5. Render HTML
    try:
        html_content = render_daily_report(report, report_date)
        html_status = "SUCCESS"
    except Exception as exc:
        logger.error(f"HTML rendering failed: {exc}", exc_info=True)
        return ProductionRunResult(
            success=False,
            pipeline_status="SUCCESS",
            html_status="FAILED",
            pipeline_result=pipeline_result,
            report=report,
            error=f"HTML error: {exc}",
        )

    # 6. Generate Excel Report
    output_dir.mkdir(parents=True, exist_ok=True)
    excel_filename = get_default_excel_filename(date_slug)
    excel_path = output_dir / excel_filename

    try:
        generate_excel_report(report, excel_path, report_date)
        excel_status = "SUCCESS"
        logger.info(f"Excel report generated: {excel_path}")
    except Exception as exc:
        logger.error(f"Excel report generation failed: {exc}", exc_info=True)
        return ProductionRunResult(
            success=False,
            pipeline_status="SUCCESS",
            html_status=html_status,
            excel_status="FAILED",
            pipeline_result=pipeline_result,
            report=report,
            error=f"Excel error: {exc}",
        )

    # 7. Configure Subject & Recipient
    email_cfg = preferences.get("email", {})
    recipient = os.getenv("JOB_REPORT_EMAIL", email_cfg.get("recipient", "lakshyadogra05@gmail.com"))
    subject_prefix = email_cfg.get("subject_prefix", "🚀 Daily Job Opportunities")
    attach_excel = email_cfg.get("attach_excel", True)

    subject = build_subject(
        report_date=report_date,
        new_count=report.summary.new,
        apply_first_count=len(report.apply_first),
        prefix=subject_prefix,
    )

    # 8. Dry Run Intercept
    if dry_run:
        logger.info("DRY RUN COMPLETE: Email sending and persistent database storage skipped.")
        return ProductionRunResult(
            success=True,
            pipeline_status="SUCCESS",
            html_status="SUCCESS",
            excel_status="SUCCESS",
            email_status="SKIPPED (DRY RUN)",
            persistence_status="SKIPPED (DRY RUN)",
            pipeline_result=pipeline_result,
            report=report,
            excel_path=excel_path,
        )

    # 9. Send Email via Resend
    attachment_to_send = excel_path if attach_excel else None
    try:
        send_daily_report(
            recipient=recipient,
            subject=subject,
            html=html_content,
            attachment_path=attachment_to_send,
        )
        email_status = "SUCCESS"
        logger.info(f"Report email successfully sent to {recipient}")
    except Exception as exc:
        logger.error(f"Email dispatch failed: {exc}")
        return ProductionRunResult(
            success=False,
            pipeline_status="SUCCESS",
            html_status=html_status,
            excel_status=excel_status,
            email_status="FAILED",
            persistence_status="SKIPPED (DUE TO EMAIL FAILURE)",
            pipeline_result=pipeline_result,
            report=report,
            excel_path=excel_path,
            error=f"Email dispatch error: {exc}",
        )

    # 10. Persist State (Strictly on successful email dispatch)
    try:
        # Save all processed jobs into persistent JobStore
        store.save_all(pipeline_result.all_matched_jobs)
        persistence_status = "SUCCESS"
        logger.info(f"Persisted {len(pipeline_result.all_matched_jobs)} job records into {db_path.name}")
    except Exception as exc:
        logger.error(f"Persistence failed: {exc}", exc_info=True)
        persistence_status = f"FAILED ({exc})"

    logger.info("=" * 60)
    logger.info("PRODUCTION RUN COMPLETED SUCCESSFULLY")
    logger.info("=" * 60)

    return ProductionRunResult(
        success=True,
        pipeline_status="SUCCESS",
        html_status=html_status,
        excel_status=excel_status,
        email_status=email_status,
        persistence_status=persistence_status,
        pipeline_result=pipeline_result,
        report=report,
        excel_path=excel_path,
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
