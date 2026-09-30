from html import escape
from typing import List, Optional

from src.collectors.base import CollectorStatus, SourceHealth
from src.models.job import Job
from src.reporting.report_builder import DailyReport


def _badge(text: str, bg_color: str, text_color: str = "#ffffff") -> str:
    """Helper to render inline badge chips."""
    return f"""<span style="
        display:inline-block;
        padding:3px 8px;
        font-size:11px;
        font-weight:700;
        border-radius:6px;
        background:{bg_color};
        color:{text_color};
        margin-right:6px;
        text-transform:uppercase;
        letter-spacing:0.5px;
    ">{escape(text)}</span>"""


def job_card(job: Job) -> str:
    """Generate a modern, responsive HTML card for a single job opportunity."""
    company = escape(job.company or "Company not listed")
    title = escape(job.title or "Role not listed")
    location = escape(job.location or "Location not listed")

    badges_html = ""
    if getattr(job, "is_new", False):
        badges_html += _badge("NEW", "#10b981")
    if getattr(job, "is_updated", False):
        badges_html += _badge("UPDATED", "#3b82f6")
    if getattr(job, "is_urgent", False):
        badges_html += _badge("URGENT", "#ef4444")

    # Meta details
    meta_rows = []
    meta_rows.append(f"📍 <strong>Location:</strong> {location}")
    if job.work_mode:
        meta_rows.append(f"💼 <strong>Mode:</strong> {escape(job.work_mode)}")
    if job.experience:
        meta_rows.append(f"🎓 <strong>Experience:</strong> {escape(job.experience)}")
    if job.eligibility:
        meta_rows.append(f"📜 <strong>Eligibility:</strong> {escape(job.eligibility)}")
    if job.compensation:
        meta_rows.append(f"💰 <strong>Compensation:</strong> {escape(job.compensation)}")
    if job.posting_date:
        meta_rows.append(f"📅 <strong>Posted:</strong> {escape(job.posting_date)}")
    if job.deadline:
        meta_rows.append(f"⏰ <strong>Deadline:</strong> {escape(job.deadline)}")
    if job.source:
        meta_rows.append(f"🔎 <strong>Source:</strong> {escape(job.source)}")

    meta_html = "<br>".join(meta_rows)

    # Score breakdown details
    score_breakdown = (
        f"Role: {job.role_score:.0f}/30 | "
        f"Skills: {job.skill_score:.1f}/30 | "
        f"Location: {job.location_score:.0f}/20 | "
        f"Experience: {job.experience_score:.0f}/10 | "
        f"Freshness: {job.freshness_score:.0f}/10"
    )

    reason = escape(job.match_reason or "Profile qualification match")

    skills_html = ""
    if job.skills:
        skill_chips = "".join(
            f"""<span style="
                display:inline-block;
                padding:2px 7px;
                margin:2px;
                font-size:11px;
                background:#e0e7ff;
                color:#3730a3;
                border-radius:4px;
            ">{escape(skill)}</span>"""
            for skill in job.skills[:10]
        )
        skills_html = f"""<div style="margin-top:10px;"><strong>Skills:</strong> {skill_chips}</div>"""

    # Application link button
    if job.application_url:
        app_link = escape(job.application_url, quote=True)
        btn_html = f"""<a href="{app_link}" style="
            display:inline-block;
            padding:9px 18px;
            background:#1e40af;
            color:#ffffff;
            text-decoration:none;
            border-radius:6px;
            font-weight:600;
            font-size:13px;
        ">Apply Directly →</a>"""
    elif job.careers_url:
        careers_link = escape(job.careers_url, quote=True)
        btn_html = f"""<a href="{careers_link}" style="
            display:inline-block;
            padding:9px 18px;
            background:#374151;
            color:#ffffff;
            text-decoration:none;
            border-radius:6px;
            font-weight:600;
            font-size:13px;
        ">Company Careers Page →</a>"""
    else:
        btn_html = """<span style="font-size:12px; color:#9ca3af; font-style:italic;">Application link not available</span>"""

    return f"""
    <div style="
        border:1px solid #e2e8f0;
        border-radius:10px;
        padding:16px;
        margin-bottom:14px;
        background:#ffffff;
        box-shadow:0 1px 3px rgba(0,0,0,0.05);
    ">
        <div style="margin-bottom:6px;">
            {badges_html}
            <span style="font-size:17px; font-weight:700; color:#0f172a;">{title}</span>
        </div>
        <div style="font-size:14px; font-weight:600; color:#475569; margin-bottom:10px;">
            {company}
        </div>
        <div style="font-size:13px; line-height:1.6; color:#334155;">
            {meta_html}
        </div>
        {skills_html}
        <div style="
            margin-top:10px;
            padding:10px;
            background:#f8fafc;
            border-left:3px solid #3b82f6;
            border-radius:4px;
            font-size:12px;
            color:#334155;
        ">
            <div><strong>Match Score:</strong> <span style="font-size:14px; font-weight:700; color:#1e40af;">{job.match_score:.1f}/100</span> ({score_breakdown})</div>
            <div style="margin-top:4px;"><strong>Why:</strong> {reason}</div>
        </div>
        <div style="margin-top:12px;">
            {btn_html}
        </div>
    </div>
    """


def render_jobs(
    jobs: List[Job],
    empty_message: str = "No opportunities in this category.",
) -> str:
    """Render a list of job cards or a friendly fallback message."""
    if not jobs:
        return f"""<p style="color:#64748b; font-size:13px; font-style:italic; margin:8px 0 16px;">{empty_message}</p>"""
    return "\n".join(job_card(job) for job in jobs)


def render_source_health(source_health: List[SourceHealth]) -> str:
    """Render the source health table."""
    if not source_health:
        return "<p style='color:#64748b; font-size:13px;'>No source health data available.</p>"

    rows = []
    for h in source_health:
        source_name = escape(h.source)
        status_val = h.status.value if isinstance(h.status, CollectorStatus) else str(h.status)

        if status_val == "SUCCESS":
            status_chip = """<span style="color:#059669; font-weight:700;">● SUCCESS</span>"""
        elif status_val == "EMPTY":
            status_chip = """<span style="color:#6b7280; font-weight:600;">○ EMPTY</span>"""
        elif status_val == "FAILED":
            status_chip = """<span style="color:#dc2626; font-weight:700;">✕ FAILED</span>"""
        elif status_val == "NOT_IMPLEMENTED":
            status_chip = """<span style="color:#9ca3af; font-style:italic;">NOT IMPLEMENTED</span>"""
        else:
            status_chip = escape(status_val)

        err_detail = f"<br><small style='color:#dc2626;'>{escape(h.error)}</small>" if h.error else ""
        dur_str = f"{h.duration_seconds:.2f}s" if h.duration_seconds > 0 else "—"

        rows.append(f"""
        <tr style="border-bottom:1px solid #f1f5f9; font-size:12px;">
            <td style="padding:8px 10px; font-weight:600; color:#1e293b;">{source_name}</td>
            <td style="padding:8px 10px;">{status_chip}{err_detail}</td>
            <td style="padding:8px 10px; text-align:center; color:#334155;">{h.job_count}</td>
            <td style="padding:8px 10px; text-align:right; color:#64748b;">{dur_str}</td>
        </tr>
        """)

    return f"""
    <table style="width:100%; border-collapse:collapse; background:#ffffff; border-radius:8px; overflow:hidden; border:1px solid #e2e8f0;">
        <thead>
            <tr style="background:#f8fafc; font-size:12px; color:#475569; text-align:left; border-bottom:1px solid #e2e8f0;">
                <th style="padding:8px 10px;">Source</th>
                <th style="padding:8px 10px;">Status</th>
                <th style="padding:8px 10px; text-align:center;">Jobs</th>
                <th style="padding:8px 10px; text-align:right;">Duration</th>
            </tr>
        </thead>
        <tbody>
            {"".join(rows)}
        </tbody>
    </table>
    """


def render_daily_report(
    report: DailyReport,
    report_date: str,
    profile_name: Optional[str] = None,
    show_business_analyst: bool = True,
) -> str:
    """Render the full daily HTML email report."""
    summary = report.summary

    is_smriti = bool(profile_name and "smriti" in profile_name.lower())
    
    if is_smriti:
        header_title = "🚀 Smriti's AI Job Opportunity Report"
        page_title = f"Smriti's AI Job Opportunity Report — {escape(report_date)}"
        footer_candidate = "Candidate: Smriti Verma &bull; Final-Year / Fresher (0–2 YOE) &bull; Noida / Delhi / Gurgaon / Bangalore / Hyderabad / Pune / Mumbai"
    else:
        header_title = "🚀 AI Job Opportunity Report"
        page_title = f"AI Job Opportunity Report — {escape(report_date)}"
        footer_candidate = "Candidate: Lakshya Dogra &bull; B.Tech CSE (Data Science) &bull; 0–2 YOE &bull; Delhi-NCR / Bangalore / Remote India"

    empty_banner = ""
    if report.total_jobs == 0:
        empty_banner = """
        <div style="background:#fef3c7; border:1px solid #f59e0b; border-radius:8px; padding:16px; margin-bottom:20px; color:#92400e; font-size:14px;">
            <strong>Notice:</strong> No matching opportunities were found in this run based on configured criteria.
        </div>
        """

    # Optional Business Analyst Section
    ba_section_html = ""
    if show_business_analyst and not is_smriti:
        ba_section_html = f"""
        <!-- Section: Business Analyst -->
        <div style="font-size:19px; font-weight:800; color:#0f172a; margin:26px 0 10px;">
            📈 Business & BI Analyst Roles
        </div>
        <div style="font-size:12px; color:#64748b; margin-bottom:12px;">
            Business analysis and business intelligence opportunities.
        </div>
        {render_jobs(report.business_analyst, "No business analyst opportunities found today.")}
        """

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{page_title}</title>
</head>
<body style="
    margin:0;
    padding:0;
    background:#f1f5f9;
    font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
    color:#0f172a;
">

<div style="max-width:740px; margin:0 auto; padding:20px;">

    <!-- Header -->
    <div style="
        background:linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
        color:#ffffff;
        padding:26px 24px;
        border-radius:12px;
        margin-bottom:18px;
    ">
        <div style="font-size:24px; font-weight:800; letter-spacing:-0.5px;">
            {header_title}
        </div>
        <div style="font-size:13px; color:#94a3b8; margin-top:4px;">
            {escape(report_date)} &bull; Automated Candidate Matching
        </div>
    </div>

    {empty_banner}

    <!-- Pipeline Summary Metrics -->
    <div style="
        background:#ffffff;
        border-radius:10px;
        border:1px solid #e2e8f0;
        padding:16px;
        margin-bottom:22px;
    ">
        <div style="font-size:14px; font-weight:700; color:#334155; margin-bottom:12px; text-transform:uppercase; letter-spacing:0.5px;">
            📊 Pipeline Summary
        </div>
        <table style="width:100%; text-align:center; font-size:12px;">
            <tr>
                <td style="padding:6px;"><strong style="font-size:18px; color:#0f172a;">{summary.collected}</strong><br><span style="color:#64748b;">Collected</span></td>
                <td style="padding:6px;"><strong style="font-size:18px; color:#0f172a;">{summary.deduplicated}</strong><br><span style="color:#64748b;">Unique</span></td>
                <td style="padding:6px;"><strong style="font-size:18px; color:#10b981;">{summary.new}</strong><br><span style="color:#64748b;">New</span></td>
                <td style="padding:6px;"><strong style="font-size:18px; color:#3b82f6;">{summary.updated}</strong><br><span style="color:#64748b;">Updated</span></td>
                <td style="padding:6px;"><strong style="font-size:18px; color:#6366f1;">{summary.matched}</strong><br><span style="color:#64748b;">Matched</span></td>
                <td style="padding:6px;"><strong style="font-size:18px; color:#059669;">{report.total_jobs}</strong><br><span style="color:#64748b;">Reportable</span></td>
            </tr>
        </table>
    </div>

    <!-- Section: Apply First -->
    <div style="font-size:19px; font-weight:800; color:#0f172a; margin:22px 0 10px;">
        🔥 Apply First
    </div>
    <div style="font-size:12px; color:#64748b; margin-bottom:12px;">
        Highest objective matches based on configured role, skill, location, experience, and freshness criteria.
    </div>
    {render_jobs(report.apply_first, "No high-priority opportunities found today.")}

    <!-- Section: New Today -->
    <div style="font-size:19px; font-weight:800; color:#0f172a; margin:26px 0 10px;">
        🆕 New Today
    </div>
    <div style="font-size:12px; color:#64748b; margin-bottom:12px;">
        Jobs verified to be posted today by official company sources.
    </div>
    {render_jobs(report.new_today, "No jobs posted today.")}

    <!-- Section: Updated -->
    <div style="font-size:19px; font-weight:800; color:#0f172a; margin:26px 0 10px;">
        🔄 Meaningfully Updated
    </div>
    <div style="font-size:12px; color:#64748b; margin-bottom:12px;">
        Existing openings with meaningful changes to compensation, description, skills, or application details.
    </div>
    {render_jobs(report.updated, "No updated job listings in this run.")}

    <!-- Section: Urgent -->
    <div style="font-size:19px; font-weight:800; color:#0f172a; margin:26px 0 10px;">
        ⏰ Urgent &bull; Deadline Soon
    </div>
    <div style="font-size:12px; color:#64748b; margin-bottom:12px;">
        Opportunities with verified application deadlines within 48 hours.
    </div>
    {render_jobs(report.urgent, "No urgent deadlines approaching.")}

    <!-- Section: Fresh & Active -->
    <div style="font-size:19px; font-weight:800; color:#0f172a; margin:26px 0 10px;">
        🟢 Fresh & Active
    </div>
    <div style="font-size:12px; color:#64748b; margin-bottom:12px;">
        Active openings posted within the last 1–7 days.
    </div>
    {render_jobs(report.fresh_active, "No additional fresh active roles found.")}

    <!-- Section: Remote India -->
    <div style="font-size:19px; font-weight:800; color:#0f172a; margin:26px 0 10px;">
        🌐 Remote India Opportunities
    </div>
    <div style="font-size:12px; color:#64748b; margin-bottom:12px;">
        Remote positions open to candidates across India.
    </div>
    {render_jobs(report.remote_india, "No remote opportunities found today.")}

    {ba_section_html}

    <!-- Section: Other Strong Matches -->
    <div style="font-size:19px; font-weight:800; color:#0f172a; margin:26px 0 10px;">
        ⭐ Other Strong Matches
    </div>
    {render_jobs(report.other_strong_matches, "No other strong matches found.")}

    <!-- Section: Source Health -->
    <div style="font-size:19px; font-weight:800; color:#0f172a; margin:28px 0 10px;">
        📡 Source Health & Status
    </div>
    {render_source_health(report.source_health)}

    <!-- Footer -->
    <div style="
        margin-top:35px;
        padding-top:18px;
        border-top:1px solid #e2e8f0;
        text-align:center;
        color:#94a3b8;
        font-size:11px;
    ">
        Generated automatically by <strong>AI Job Opportunity Agent</strong>.<br>
        {footer_candidate}
    </div>

</div>

</body>
</html>"""
