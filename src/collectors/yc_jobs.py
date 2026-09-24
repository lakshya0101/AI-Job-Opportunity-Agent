import requests


YC_JOBS_URL = (
    "https://www.ycombinator.com/jobs"
)


def collect() -> list:
    """
    Collect jobs from YC Jobs.

    This initial implementation intentionally uses
    a lightweight HTTP request. Parsing will be refined
    after the first live pipeline test.
    """

    try:
        response = requests.get(
            YC_JOBS_URL,
            timeout=20,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 "
                    "AI-Job-Opportunity-Agent"
                )
            },
        )

        response.raise_for_status()

        return []

    except Exception as exc:
        print(
            f"[YC JOBS ERROR] {exc}"
        )

        return []
