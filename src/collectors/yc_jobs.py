import logging
import re
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional
import requests

from src.collectors.base import BaseCollector, CollectorResult, CollectorStatus

logger = logging.getLogger(__name__)

HN_JOBSTORIES_URL = "https://hacker-news.firebaseio.com/v0/jobstories.json"
HN_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{item_id}.json"
REQUEST_TIMEOUT = 5
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


def _parse_yc_title(raw_title: str) -> tuple[str, str]:
    """
    Parse company name and job title from typical YC job story titles.
    e.g. 'Bild AI (YC W25) Is Hiring a Founding Product Engineer' -> ('Bild AI', 'Founding Product Engineer')
    e.g. 'Supabase (YC S20) Is Hiring for OrioleDB' -> ('Supabase', 'OrioleDB Engineer')
    """
    if not raw_title:
        return "YC Startup", "Software Engineer"

    # Pattern: Company (YC Batch) is hiring Role
    match = re.match(r"^(.+?)\s*\((?:YC\s*)?[A-Z]\d+\)\s*(?:is hiring|hiring|seeks|is looking for)\s+(?:\b(?:a|an|for)\b\s+)?(.+)$", raw_title, re.IGNORECASE)
    if match:
        company = match.group(1).strip()
        role = match.group(2).strip()
        return company, role

    # Pattern: Company is hiring Role
    match2 = re.match(r"^(.+?)\s+(?:is hiring|hiring|seeks|is looking for)\s+(?:\b(?:a|an|for)\b\s+)?(.+)$", raw_title, re.IGNORECASE)
    if match2:
        company = match2.group(1).strip()
        role = match2.group(2).strip()
        return company, role

    return "YC Startup", raw_title


class YCJobsCollector(BaseCollector):
    """
    Collector for Y Combinator startup job opportunities via the official Hacker News / YC API.
    """

    def __init__(self, max_items: int = 50):
        self.max_items = max_items

    @property
    def source_name(self) -> str:
        return "YC Jobs"

    def _fetch_single_item(self, item_id: int) -> Optional[Dict[str, Any]]:
        try:
            url = HN_ITEM_URL.format(item_id=item_id)
            resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                item = resp.json()
                if item and not item.get("deleted") and not item.get("dead"):
                    return item
        except Exception as exc:
            logger.debug(f"[YC JOBS] Failed fetching item {item_id}: {exc}")
        return None

    def collect(self) -> CollectorResult:
        try:
            print("[YC JOBS] Fetching job stories list...", flush=True)
            resp = requests.get(HN_JOBSTORIES_URL, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            if resp.status_code != 200:
                return CollectorResult(
                    source=self.source_name,
                    jobs=[],
                    status=CollectorStatus.FAILED,
                    error=f"HTTP {resp.status_code}",
                    count=0,
                )

            item_ids = resp.json()
            if not isinstance(item_ids, list) or not item_ids:
                return CollectorResult(
                    source=self.source_name,
                    jobs=[],
                    status=CollectorStatus.EMPTY,
                    count=0,
                )

            target_ids = item_ids[:self.max_items]
            print(f"[YC JOBS] Fetching details for {len(target_ids)} job postings...", flush=True)
            items: List[Dict[str, Any]] = []

            with ThreadPoolExecutor(max_workers=20) as executor:
                futures = [executor.submit(self._fetch_single_item, i_id) for i_id in target_ids]
                for f in as_completed(futures):
                    res = f.result()
                    if res:
                        items.append(res)

            print(f"[YC JOBS] Successfully fetched {len(items)} raw job stories", flush=True)

            jobs = []
            for item in items:
                raw_title = _clean(item.get("title"))
                if not raw_title:
                    continue

                company, title = _parse_yc_title(raw_title)
                app_url = _clean(item.get("url")) or f"https://news.ycombinator.com/item?id={item.get('id')}"

                posting_date = None
                timestamp = item.get("time")
                if timestamp and isinstance(timestamp, (int, float)):
                    try:
                        posting_date = datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
                    except Exception:
                        pass

                text_content = _clean(item.get("text")) or ""
                description = f"{raw_title}\n{text_content}".strip()

                loc_lower = (raw_title + " " + text_content).lower()
                location = "Remote" if ("remote" in loc_lower or "anywhere" in loc_lower) else "Remote India / Global"
                work_mode = "Remote" if "remote" in loc_lower else None

                jobs.append(
                    {
                        "company": company,
                        "title": title,
                        "location": location,
                        "work_mode": work_mode,
                        "experience": None,
                        "eligibility": None,
                        "compensation": None,
                        "posting_date": posting_date,
                        "deadline": None,
                        "description": description,
                        "source": self.source_name,
                        "application_url": app_url,
                        "careers_url": app_url,
                        "recruiter_name": None,
                        "recruiter_email": None,
                        "skills": [],
                    }
                )

            status = CollectorStatus.SUCCESS if jobs else CollectorStatus.EMPTY
            return CollectorResult(
                source=self.source_name,
                jobs=jobs,
                status=status,
                error=None,
                count=len(jobs),
            )

        except Exception as exc:
            return CollectorResult(
                source=self.source_name,
                jobs=[],
                status=CollectorStatus.FAILED,
                error=str(exc),
                count=0,
            )
