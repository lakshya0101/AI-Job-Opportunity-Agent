from typing import Iterable, List


def collect_from_company(
    company_name: str,
    careers_url: str,
) -> List[dict]:
    """
    Placeholder for company-specific career collection.

    Each company career site can later have its own
    parser while returning the standard job dictionary.
    """

    return []


def collect(
    companies: Iterable[dict],
) -> List[dict]:
    """Collect jobs from configured company career pages."""

    jobs = []

    for company in companies:
        name = company.get("name")
        url = company.get("careers_url")

        if not name or not url:
            continue

        jobs.extend(
            collect_from_company(
                name,
                url,
            )
        )

    return jobs
