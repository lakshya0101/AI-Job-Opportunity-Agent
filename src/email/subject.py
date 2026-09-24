def build_subject(
    report_date: str,
    new_count: int,
    apply_first_count: int,
) -> str:
    """Build the daily email subject."""

    return (
        f"AI Job Opportunities — "
        f"{report_date} | "
        f"{new_count} New | "
        f"{apply_first_count} Apply First"
    )
