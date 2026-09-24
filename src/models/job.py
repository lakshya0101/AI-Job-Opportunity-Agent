from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Job:
    """
    Standardized representation of a job opportunity.
    All job collectors should convert their results into this model.
    """

    company: str
    title: str

    location: str
    work_mode: Optional[str] = None

    experience: Optional[str] = None
    eligibility: Optional[str] = None
    compensation: Optional[str] = None

    posting_date: Optional[str] = None
    deadline: Optional[str] = None

    description: Optional[str] = None

    source: Optional[str] = None
    application_url: Optional[str] = None
    careers_url: Optional[str] = None

    recruiter_name: Optional[str] = None
    recruiter_email: Optional[str] = None

    skills: List[str] = field(default_factory=list)

    first_seen: Optional[str] = None
    last_seen: Optional[str] = None

    match_score: float = 0.0
    match_reason: Optional[str] = None

    is_new: bool = True
    is_updated: bool = False
    is_urgent: bool = False
