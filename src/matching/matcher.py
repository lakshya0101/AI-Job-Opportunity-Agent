import re
from typing import Any, Dict, Iterable

from src.models.job import Job


def normalize_text(value: str) -> str:
    """Normalize text for matching."""

    if not value:
        return ""

    value = value.lower()

    # Normalize common separators.
    value = value.replace("/", " ")
    value = value.replace("-", " ")

    # Remove punctuation.
    value = re.sub(r"[^a-z0-9+#.\s]", " ", value)

    # Collapse whitespace.
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def contains_term(text: str, term: str) -> bool:
    """Check whether a term appears as a meaningful phrase."""

    text = normalize_text(text)
    term = normalize_text(term)

    if not text or not term:
        return False

    return term in text


def combined_job_text(job: Job) -> str:
    """Create searchable text from the job."""

    parts = [
        job.title,
        job.description,
        job.experience,
        job.eligibility,
        " ".join(job.skills),
    ]

    return normalize_text(" ".join(
        part for part in parts if part
    ))


def score_role_match(
    job: Job,
    role_preferences: Iterable[str],
) -> float:
    """
    Score role relevance out of 30.
    """

    title = normalize_text(job.title)

    if not title:
        return 0.0

    role_matches = 0

    for role in role_preferences:
        if contains_term(title, role):
            role_matches += 1

    if role_matches == 0:
        return 0.0

    # One strong title match is enough for a high score.
    if role_matches >= 2:
        return 30.0

    return 27.0


def score_skill_match(
    job: Job,
    skills: Iterable[str],
) -> float:
    """
    Score technical skill overlap out of 30.

    Score is based on the number of relevant candidate skills
    matched by the job, rather than requiring the job to match
    the entire candidate skill inventory.
    """

    job_text = combined_job_text(job)

    if not job_text:
        return 0.0

    normalized_skills = [
        normalize_text(skill)
        for skill in skills
        if skill
    ]

    if not normalized_skills:
        return 0.0

    matched = {
        skill
        for skill in normalized_skills
        if skill and skill in job_text
    }

    matched_count = len(matched)

    if matched_count == 0:
        return 0.0

    # Four meaningful skill matches = full technical score.
    return min(30.0, matched_count * 7.5)


def score_location_match(
    job: Job,
    location_priority: Dict[int, Iterable[str]],
    remote_locations: Iterable[str],
) -> float:
    """
    Score location compatibility out of 20.

    Priority:
        Noida/New Delhi/Gurugram -> highest
        Bangalore -> next
        Jaipur/Pune/Mumbai -> next
        Remote India -> supported
        Other locations -> lower
    """

    location = normalize_text(job.location)

    if not location:
        return 0.0

    # Check priority levels.
    for priority, locations in sorted(location_priority.items()):
        for preferred_location in locations:
            if contains_term(location, preferred_location):
                if priority == 1:
                    return 20.0
                if priority == 2:
                    return 19.0
                if priority == 3:
                    return 18.0
                if priority == 4:
                    return 16.0
                if priority == 5:
                    return 15.0
                if priority == 6:
                    return 14.0
                if priority == 7:
                    return 13.0

    # Remote India is intentionally included.
    for remote in remote_locations:
        if contains_term(location, remote):
            return 16.0

    # Other locations can still be considered later
    # when the technical match is especially strong.
    return 5.0


def score_experience_match(
    job: Job,
    preferred_experience: Iterable[str],
) -> float:
    """
    Score compatibility with a fresher / 0-2 year candidate.

    Seniority in the title is treated as a strong signal.
    Explicit experience requirements in the job text override
    ambiguous cases.
    """

    title = normalize_text(job.title)

    text = normalize_text(
        " ".join(
            part for part in [
                job.experience,
                job.eligibility,
                job.description,
            ]
            if part
        )
    )

    # Strong seniority indicators.
    senior_titles = [
        "senior",
        "sr ",
        "lead",
        "principal",
        "staff",
        "manager",
        "director",
        "head",
        "architect",
    ]

    for term in senior_titles:
        if contains_term(title, term):
            # Only recover if the actual job explicitly accepts
            # fresher / entry-level candidates.
            entry_terms = [
                "fresher",
                "freshers",
                "entry level",
                "entry-level",
                "graduate",
                "trainee",
                "0 1 year",
                "0 2 years",
                "0 2 year",
            ]

            if any(contains_term(text, term) for term in entry_terms):
                return 6.0

            return 0.0

    # Explicit entry-level signals.
    strong_terms = [
        "fresher",
        "freshers",
        "graduate",
        "trainee",
        "entry level",
        "entry-level",
        "0 1 year",
        "0 2 years",
        "0 2 year",
        "0 1 years",
        "campus",
    ]

    for term in strong_terms:
        if contains_term(text, term):
            return 10.0

    # Explicitly experienced roles.
    if re.search(r"\b[3-9]\+?\s*years?\b", text):
        return 2.0

    # Unknown experience.
    return 5.0

def score_freshness(job: Job) -> float:
    """
    Score freshness out of 10.

    The freshness module remains responsible for
    determining exact categories.
    """

    if job.is_new:
        return 10.0

    if job.is_urgent:
        return 10.0

    return 6.0


def calculate_match(
    job: Job,
    preferences: Dict[str, Any],
) -> Job:
    """
    Calculate the overall profile-match score and
    attach an explanation to the Job object.
    """

    role_groups = preferences.get("roles", {})

    role_preferences = []

    for roles in role_groups.values():
        if isinstance(roles, list):
            role_preferences.extend(roles)

    skill_groups = preferences.get("skills", {})

    skills = []

    for skill_group in skill_groups.values():
        if isinstance(skill_group, list):
            skills.extend(skill_group)

    location_config = preferences.get("locations", {})

    raw_priority = location_config.get("priority", {})

    # YAML may load numeric keys as integers.
    location_priority = {
        int(priority): locations
        for priority, locations in raw_priority.items()
    }

    remote_locations = location_config.get("remote", [])

    candidate_config = preferences.get("candidate", {})

    experience_config = candidate_config.get("experience", {})

    preferred_experience = experience_config.get(
        "preferred",
        [],
    )

    role_score = score_role_match(
        job,
        role_preferences,
    )

    skill_score = score_skill_match(
        job,
        skills,
    )

    location_score = score_location_match(
        job,
        location_priority,
        remote_locations,
    )

    experience_score = score_experience_match(
        job,
        preferred_experience,
    )

    freshness_score = score_freshness(job)

    total = (
        role_score
        + skill_score
        + location_score
        + experience_score
        + freshness_score
    )

    job.role_score = role_score
    job.skill_score = skill_score
    job.location_score = location_score
    job.experience_score = experience_score
    job.freshness_score = freshness_score
    
    job.match_score = round(
        min(100.0, total),
        2,
    )

    matched_skills = []

    job_text = combined_job_text(job)

    for skill in skills:
        if contains_term(job_text, skill):
            matched_skills.append(skill)

    reasons = []

    if role_score >= 27:
        reasons.append("strong role match")
    
    if skill_score > 0:
        reasons.append(
            f"skill score: {skill_score:.1f}/30"
        )
    
    if matched_skills:
        reasons.append(
            f"skills: {', '.join(matched_skills[:8])}"
        )
    
    if location_score >= 13:
        reasons.append("preferred location")
    
    if experience_score >= 9:
        reasons.append("fresher/entry-level compatible")
    
    if freshness_score >= 10:
        reasons.append("fresh or urgent")
    
    job.match_reason = "; ".join(reasons)
    
    return job
