from typing import Callable, Iterable, List

from src.models.job import Job


Collector = Callable[[], Iterable[dict]]


def run_collectors(
    collectors: Iterable[Collector],
) -> List[dict]:
    """Run all collectors without allowing one failure to stop the pipeline."""

    all_jobs = []

    for collector in collectors:
        try:
            jobs = collector()

            if jobs:
                all_jobs.extend(jobs)

        except Exception as exc:
            print(
                f"[COLLECTOR ERROR] "
                f"{collector.__name__}: {exc}"
            )

    return all_jobs
