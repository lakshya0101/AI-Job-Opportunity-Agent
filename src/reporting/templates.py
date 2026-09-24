from html import escape
from typing import List

from src.models.job import Job
from src.reporting.report_builder import DailyReport


def job_card(job: Job) -> str:
    """Generate an HTML card for a single job."""

    company = escape(job.company or "Company not listed")
    title = escape(job.title or "Role not listed")
    location = escape(job.location or "Location not listed")

    work_mode = escape(
        job.work_mode or "Not specified"
    )

    experience = escape(
        job.experience or "Not specified"
    )

    compensation = escape(
        job.compensation or "Not listed"
    )

    source = escape(
        job.source or "Source not listed"
    )

    reason = escape(
        job.match_reason or "Profile match"
    )

    application_url = (
        job.application_url
        or job.careers_url
        or "#"
    )

    application_url = escape(
        application_url,
        quote=True,
    )

    return f"""
    <div style="
        border:1px solid #e5e7eb;
        border-radius:12px;
        padding:18px;
        margin-bottom:16px;
        background:#ffffff;
    ">

        <div style="
            font-size:18px;
            font-weight:700;
            color:#111827;
            margin-bottom:6px;
        ">
            {title}
        </div>

        <div style="
            font-size:15px;
            font-weight:600;
            color:#374151;
            margin-bottom:10px;
        ">
            {company}
        </div>

        <div style="
            font-size:14px;
            line-height:1.7;
            color:#4b5563;
        ">
            📍 {location}<br>
            💼 {work_mode}<br>
            🎓 {experience}<br>
            💰 {compensation}<br>
            🔎 Source: {source}
        </div>

        <div style="
            margin-top:12px;
            padding:10px;
            background:#f9fafb;
            border-radius:8px;
            font-size:13px;
            color:#374151;
        ">
            <strong>Match:</strong>
            {job.match_score:.0f}/100
            <br>
            <strong>Why:</strong>
            {reason}
        </div>

        <div style="margin-top:15px;">
            <a href="{application_url}"
               style="
                   display:inline-block;
                   padding:10px 16px;
                   background:#111827;
                   color:#ffffff;
                   text-decoration:none;
                   border-radius:7px;
                   font-weight:600;
                   font-size:14px;
               ">
                Apply Now →
            </a>
        </div>

    </div>
    """


def render_jobs(
    jobs: List[Job],
    empty_message: str = "No opportunities found.",
) -> str:
    """Render a list of jobs."""

    if not jobs:
        return f"""
        <p style="
            color:#6b7280;
            font-size:14px;
        ">
            {empty_message}
        </p>
        """

    return "\n".join(
        job_card(job)
        for job in jobs
    )


def render_daily_report(
    report: DailyReport,
    report_date: str,
) -> str:
    """Render the complete daily email."""

    return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>AI Job Opportunity Report</title>
</head>

<body style="
    margin:0;
    padding:0;
    background:#f3f4f6;
    font-family:Arial, Helvetica, sans-serif;
">

<div style="
    max-width:760px;
    margin:0 auto;
    padding:24px;
">

    <div style="
        background:#111827;
        color:#ffffff;
        padding:28px;
        border-radius:14px;
        margin-bottom:20px;
    ">

        <div style="
            font-size:26px;
            font-weight:700;
            margin-bottom:8px;
        ">
            AI Job Opportunity Report
        </div>

        <div style="
            font-size:14px;
            opacity:0.85;
        ">
            {escape(report_date)}
        </div>

    </div>


    <div style="
        background:#ffffff;
        border-radius:12px;
        padding:20px;
        margin-bottom:20px;
    ">

        <div style="
            font-size:18px;
            font-weight:700;
            margin-bottom:15px;
        ">
            Daily Summary
        </div>

        <div style="
            display:flex;
            gap:20px;
            font-size:14px;
            color:#374151;
        ">

            <div>
                <strong>{len(report.new_today)}</strong><br>
                New Today
            </div>

            <div>
                <strong>{len(report.urgent)}</strong><br>
                Urgent
            </div>

            <div>
                <strong>{report.total_jobs}</strong><br>
                Matched
            </div>

        </div>

    </div>


    <div style="
        font-size:22px;
        font-weight:700;
        margin:24px 0 12px;
        color:#111827;
    ">
        🔥 Apply First
    </div>

    {render_jobs(
        report.apply_first,
        "No high-priority opportunities found today."
    )}


    <div style="
        font-size:22px;
        font-weight:700;
        margin:30px 0 12px;
        color:#111827;
    ">
        🆕 New Today
    </div>

    {render_jobs(
        report.new_today,
        "No newly discovered opportunities today."
    )}


    <div style="
        font-size:22px;
        font-weight:700;
        margin:30px 0 12px;
        color:#111827;
    ">
        ⏰ Urgent
    </div>

    {render_jobs(
        report.urgent,
        "No urgent deadlines detected."
    )}


    <div style="
        font-size:22px;
        font-weight:700;
        margin:30px 0 12px;
        color:#111827;
    ">
        🟢 Fresh Active Roles
    </div>

    {render_jobs(
        report.fresh_active,
        "No additional fresh active opportunities."
    )}


    <div style="
        margin-top:35px;
        padding:18px;
        text-align:center;
        color:#6b7280;
        font-size:12px;
    ">
        Automatically generated by
        <strong>AI Job Opportunity Agent</strong>.
    </div>

</div>

</body>
</html>
"""
