import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import requests

from src.collectors.base import BaseCollector, CollectorResult, CollectorStatus

logger = logging.getLogger(__name__)

UNSTOP_SEARCH_URL = "https://unstop.com/api/public/opportunity/search-result"
REQUEST_TIMEOUT = 10
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


def _clean(value: Any) -> Optional[str]:
    if value is None:
        return None
    val_str = str(value).strip()
    return val_str or None


def _format_compensation(job_detail: Dict[str, Any]) -> Optional[str]:
    if not job_detail or not isinstance(job_detail, dict):
        return None
    min_sal = job_detail.get("min_salary")
    max_sal = job_detail.get("max_salary")
    pay_in = job_detail.get("pay_in") or "year"

    if min_sal and max_sal:
        if min_sal == max_sal:
            return f"₹{min_sal:,} / {pay_in}"
        return f"₹{min_sal:,} - ₹{max_sal:,} / {pay_in}"
    elif min_sal:
        return f"₹{min_sal:,} / {pay_in}"
    elif max_sal:
        return f"Up to ₹{max_sal:,} / {pay_in}"
    return None


def _extract_locations(item: Dict[str, Any]) -> str:
    locations = item.get("locations") or []
    loc_strings = []
    if isinstance(locations, list):
        for loc in locations:
            if isinstance(loc, dict):
                city = _clean(loc.get("city"))
                state = _clean(loc.get("state"))
                country = _clean(loc.get("country")) or "India"
                if city:
                    loc_strings.append(f"{city}, {country}" if country else city)
                elif state:
                    loc_strings.append(f"{state}, {country}" if country else state)
            elif isinstance(loc, str) and loc.strip():
                loc_strings.append(loc.strip())

    job_detail = item.get("jobDetail") or {}
    if not loc_strings and isinstance(job_detail, dict):
        detail_locs = job_detail.get("locations") or []
        for dl in detail_locs:
            if isinstance(dl, str) and dl.strip():
                loc_strings.append(dl.strip())

    if loc_strings:
        # Deduplicate while preserving order
        seen = set()
        unique_locs = [x for x in loc_strings if not (x in seen or seen.add(x))]
        return ", ".join(unique_locs)

    # Check work mode
    work_type = str(job_detail.get("type", "")).lower() if isinstance(job_detail, dict) else ""
    if "work_from_home" in work_type or "remote" in work_type:
        return "Remote India"
    return "India"


def _format_work_mode(job_detail: Dict[str, Any]) -> Optional[str]:
    if not job_detail or not isinstance(job_detail, dict):
        return None
    type_str = str(job_detail.get("type", "")).lower()
    if "in_office" in type_str:
        return "Onsite"
    elif "work_from_home" in type_str or "remote" in type_str:
        return "Remote"
    elif "hybrid" in type_str:
        return "Hybrid"
    return None


def _parse_unstop_date(date_str: Optional[str]) -> Optional[str]:
    if not date_str:
        return None
    # e.g. "2026-09-30 14:36:12 GMT+0530" or ISO format
    try:
        clean_d = re.sub(r"\s+GMT[+-]\d+", "", date_str.strip())
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(clean_d, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.isoformat()
            except ValueError:
                continue
    except Exception:
        pass
    return _clean(date_str)


class UnstopCollector(BaseCollector):
    """
    Collector for opportunities published on Unstop (jobs & internships).
    Uses the official Unstop public REST search API.
    """

    def __init__(self, max_pages: int = 2, per_page: int = 50):
        self.max_pages = max_pages
        self.per_page = per_page

    @property
    def source_name(self) -> str:
        return "Unstop"

    def _collect_category(self, category: str) -> List[Dict[str, Any]]:
        category_jobs: List[Dict[str, Any]] = []

        for page in range(1, self.max_pages + 1):
            try:
                resp = requests.get(
                    UNSTOP_SEARCH_URL,
                    params={
                        "opportunity": category,
                        "page": page,
                        "per_page": self.per_page,
                    },
                    headers=HEADERS,
                    timeout=REQUEST_TIMEOUT,
                )
                if resp.status_code != 200:
                    logger.warning(f"[UNSTOP] Non-200 response ({resp.status_code}) for {category} page {page}")
                    break

                data = resp.json()
                items = data.get("data", {}).get("data", [])
                if not items:
                    break

                for item in items:
                    title = _clean(item.get("title"))
                    if not title:
                        continue

                    # Extract company name
                    org = item.get("organisation")
                    company_name = None
                    if isinstance(org, dict):
                        company_name = _clean(org.get("name"))
                    elif isinstance(org, str):
                        company_name = _clean(org)
                    company_name = company_name or "Unstop Employer"

                    # Extract application URL
                    seo_url = _clean(item.get("seo_url"))
                    public_url = _clean(item.get("public_url"))
                    if seo_url and seo_url.startswith("http"):
                        app_url = seo_url
                    elif public_url:
                        app_url = f"https://unstop.com/{public_url.lstrip('/')}"
                    else:
                        app_url = f"https://unstop.com/jobs/{item.get('id', '')}"

                    job_detail = item.get("jobDetail") or {}
                    location = _extract_locations(item)
                    work_mode = _format_work_mode(job_detail)
                    compensation = _format_compensation(job_detail)

                    # Posting date and deadline
                    posting_date = _parse_unstop_date(item.get("approved_date") or item.get("updated_at"))
                    deadline = _clean(item.get("end_date"))

                    # Skills
                    skills = []
                    raw_skills = item.get("required_skills") or []
                    if isinstance(raw_skills, list):
                        for sk in raw_skills:
                            if isinstance(sk, dict):
                                sk_name = _clean(sk.get("skill_name") or sk.get("skill"))
                                if sk_name:
                                    skills.append(sk_name)
                            elif isinstance(sk, str) and sk.strip():
                                skills.append(sk.strip())

                    # Experience and eligibility
                    eligibility = None
                    filters = item.get("filters") or []
                    if isinstance(filters, list):
                        elig_names = [f.get("name") for f in filters if isinstance(f, dict) and f.get("name")]
                        if elig_names:
                            eligibility = ", ".join(elig_names)

                    min_exp = job_detail.get("min_experience") if isinstance(job_detail, dict) else None
                    max_exp = job_detail.get("max_experience") if isinstance(job_detail, dict) else None
                    experience = None
                    if min_exp is not None and max_exp is not None:
                        experience = f"{min_exp}-{max_exp} years"
                    elif min_exp is not None:
                        experience = f"{min_exp}+ years"

                    category_jobs.append(
                        {
                            "company": company_name,
                            "title": title,
                            "location": location,
                            "work_mode": work_mode,
                            "experience": experience,
                            "eligibility": eligibility,
                            "compensation": compensation,
                            "posting_date": posting_date,
                            "deadline": deadline,
                            "description": _clean(item.get("details")) or title,
                            "source": self.source_name,
                            "application_url": app_url,
                            "careers_url": app_url,
                            "recruiter_name": None,
                            "recruiter_email": None,
                            "skills": skills,
                        }
                    )

            except Exception as exc:
                logger.error(f"[UNSTOP ERROR] Failed fetching {category} page {page}: {exc}")
                break

        return category_jobs

    def collect(self) -> CollectorResult:
        try:
            jobs = []
            print("[UNSTOP] Collecting jobs...", flush=True)
            jobs.extend(self._collect_category("jobs"))
            print(f"[UNSTOP] Jobs collected: {len(jobs)}. Collecting internships...", flush=True)
            jobs.extend(self._collect_category("internships"))
            print(f"[UNSTOP] Total opportunities collected: {len(jobs)}", flush=True)

            status = CollectorStatus.SUCCESS if jobs else CollectorStatus.EMPTY
            return CollectorResult(
                source=self.source_name,
                jobs=jobs,
                status=status,
                error=None,
                count=len(jobs),
            )
        except Exception as exc:
            print(f"[UNSTOP ERROR] {exc}", flush=True)
            return CollectorResult(
                source=self.source_name,
                jobs=[],
                status=CollectorStatus.FAILED,
                error=str(exc),
                count=0,
            )
