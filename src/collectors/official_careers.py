from typing import Dict, Iterable, List, Optional

import requests


REQUEST_TIMEOUT = 20

GREENHOUSE_URL = (
    "https://boards-api.greenhouse.io/v1/boards/"
    "{board_token}/jobs"
)

LEVER_URL = (
    "https://api.lever.co/v0/postings/"
    "{site}"
)


def _clean(value) -> Optional[str]:
    """Convert a value into a clean string."""

    if value is None:
        return None

    if isinstance(value, str):
        value = value.strip()

        return value or None

    return str(value).strip() or None


def _location_from_greenhouse(job: dict) -> str:
    """Extract a readable Greenhouse location."""

    location = job.get("location")

    if isinstance(location, dict):
        return _clean(
            location.get("name")
        ) or "Not specified"

    return _clean(location) or "Not specified"


def collect_greenhouse(
    company_name: str,
    board_token: str,
) -> List[dict]:
    """
    Collect jobs from a company's Greenhouse job board.

    The returned structure matches the raw job format
    expected by the normalizer.
    """

    url = GREENHOUSE_URL.format(
        board_token=board_token
    )

    try:
        response = requests.get(
            url,
            params={
                "content": "true",
            },
            timeout=REQUEST_TIMEOUT,
            headers={
                "User-Agent": (
                    "AI-Job-Opportunity-Agent/1.0"
                )
            },
        )

        response.raise_for_status()

        data = response.json()

    except Exception as exc:
        print(
            f"[GREENHOUSE ERROR] "
            f"{company_name}: {exc}"
        )

        return []

    jobs = []

    for item in data.get("jobs", []):

        title = _clean(
            item.get("title")
        )

        if not title:
            continue

        location = _location_from_greenhouse(
            item
        )

        application_url = _clean(
            item.get("absolute_url")
        )

        description = _clean(
            item.get("content")
        )

        departments = item.get(
            "departments",
            [],
        )

        skills = []

        if isinstance(departments, list):
            for department in departments:
                if isinstance(department, dict):
                    name = _clean(
                        department.get("name")
                    )

                    if name:
                        skills.append(name)

        jobs.append(
            {
                "company": company_name,
                "title": title,
                "location": location,
                "work_mode": None,
                "experience": None,
                "eligibility": None,
                "compensation": None,
                "posting_date": _clean(
                    item.get("updated_at")
                ),
                "deadline": None,
                "description": description,
                "source": "official_company_careers",
                "application_url": application_url,
                "careers_url": application_url,
                "recruiter_name": None,
                "recruiter_email": None,
                "skills": skills,
            }
        )

    print(
        f"[GREENHOUSE] "
        f"{company_name}: {len(jobs)} jobs"
    )

    return jobs


def _location_from_lever(job: dict) -> str:
    """Extract a readable Lever location."""

    categories = job.get(
        "categories",
        {},
    )

    if isinstance(categories, dict):

        location = _clean(
            categories.get("location")
        )

        if location:
            return location

        all_locations = categories.get(
            "allLocations",
            [],
        )

        if isinstance(all_locations, list):
            locations = [
                _clean(location)
                for location in all_locations
                if _clean(location)
            ]

            if locations:
                return ", ".join(locations)

    return "Not specified"


def collect_lever(
    company_name: str,
    site: str,
) -> List[dict]:
    """
    Collect jobs from a company's Lever job board.
    """

    url = LEVER_URL.format(
        site=site
    )

    try:
        response = requests.get(
            url,
            params={
                "mode": "json",
            },
            timeout=REQUEST_TIMEOUT,
            headers={
                "User-Agent": (
                    "AI-Job-Opportunity-Agent/1.0"
                )
            },
        )

        response.raise_for_status()

        data = response.json()

    except Exception as exc:
        print(
            f"[LEVER ERROR] "
            f"{company_name}: {exc}"
        )

        return []

    jobs = []

    if not isinstance(data, list):
        return jobs

    for item in data:

        title = _clean(
            item.get("text")
        )

        if not title:
            continue

        location = _location_from_lever(
            item
        )

        application_url = _clean(
            item.get("hostedUrl")
        )

        description_parts = []

        description = item.get(
            "descriptionPlain"
        )

        if description:
            description_parts.append(
                description
            )

        additional = item.get(
            "additionalPlain"
        )

        if additional:
            description_parts.append(
                additional
            )

        combined_description = "\n".join(
            description_parts
        )

        categories = item.get(
            "categories",
            {},
        )

        skills = []

        if isinstance(categories, dict):

            team = _clean(
                categories.get("team")
            )

            commitment = _clean(
                categories.get("commitment")
            )

            if team:
                skills.append(team)

            if commitment:
                skills.append(commitment)

        jobs.append(
            {
                "company": company_name,
                "title": title,
                "location": location,
                "work_mode": None,
                "experience": None,
                "eligibility": None,
                "compensation": None,
                "posting_date": None,
                "deadline": None,
                "description": combined_description,
                "source": "official_company_careers",
                "application_url": application_url,
                "careers_url": application_url,
                "recruiter_name": None,
                "recruiter_email": None,
                "skills": skills,
            }
        )

    print(
        f"[LEVER] "
        f"{company_name}: {len(jobs)} jobs"
    )

    return jobs


def collect_company(
    company: Dict,
) -> List[dict]:
    """
    Collect jobs from one configured company.

    Supported platforms:
    - greenhouse
    - lever
    """

    company_name = _clean(
        company.get("name")
    )

    platform = _clean(
        company.get("platform")
    )

    identifier = _clean(
        company.get("identifier")
    )

    if not company_name:
        print(
            "[CAREERS] Skipping company "
            "without a name."
        )
        return []

    if not platform:
        print(
            f"[CAREERS] {company_name}: "
            "missing platform."
        )
        return []

    if not identifier:
        print(
            f"[CAREERS] {company_name}: "
            "missing identifier."
        )
        return []

    platform = platform.lower()

    if platform == "greenhouse":
        return collect_greenhouse(
            company_name,
            identifier,
        )

    if platform == "lever":
        return collect_lever(
            company_name,
            identifier,
        )

    print(
        f"[CAREERS] {company_name}: "
        f"unsupported platform '{platform}'."
    )

    return []


def collect(
    companies: Iterable[Dict],
) -> List[dict]:
    """Collect jobs from all configured companies."""

    all_jobs = []

    for company in companies:

        try:
            jobs = collect_company(
                company
            )

            all_jobs.extend(
                jobs
            )

        except Exception as exc:
            name = company.get(
                "name",
                "Unknown company",
            )

            print(
                f"[CAREERS ERROR] "
                f"{name}: {exc}"
            )

    print(
        f"[CAREERS] Total collected: "
        f"{len(all_jobs)}"
    )

    return all_jobs
