from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class CollectorStatus(str, Enum):
    SUCCESS = "SUCCESS"
    EMPTY = "EMPTY"
    FAILED = "FAILED"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"


@dataclass
class SourceHealth:
    """
    Summary representation of a collector source's execution health.
    """
    source: str
    status: CollectorStatus
    job_count: int = 0
    error: Optional[str] = None
    duration_seconds: float = 0.0


@dataclass
class CollectorResult:
    """
    Standard result returned by any job collector.
    
    Attributes:
        source: Name or identifier of the job source.
        jobs: List of raw job dictionaries collected.
        status: Execution status (SUCCESS, FAILED, EMPTY, NOT_IMPLEMENTED).
        error: Error message if failed/unimplemented, else None.
        count: Number of jobs collected.
        duration_seconds: Time taken to execute collection in seconds.
    """
    source: str
    jobs: List[Dict[str, Any]] = field(default_factory=list)
    status: CollectorStatus = CollectorStatus.SUCCESS
    error: Optional[str] = None
    count: int = 0
    duration_seconds: float = 0.0

    def __post_init__(self):
        if not self.count and self.jobs:
            self.count = len(self.jobs)
        if self.status == CollectorStatus.SUCCESS and len(self.jobs) == 0 and not self.error:
            self.status = CollectorStatus.EMPTY

    @property
    def source_health(self) -> SourceHealth:
        return SourceHealth(
            source=self.source,
            status=self.status,
            job_count=self.count,
            error=self.error,
            duration_seconds=self.duration_seconds,
        )


class BaseCollector(ABC):
    """
    Abstract base class for all job collectors.
    
    Subclasses must implement source_name and collect().
    """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Return the unique human-readable source name."""
        pass

    @abstractmethod
    def collect(self) -> CollectorResult:
        """
        Execute job collection for this source.
        
        Must return a CollectorResult and isolate internal exceptions.
        """
        pass


class NotImplementedCollector(BaseCollector):
    """Placeholder collector for configured sources whose scrapers are not yet implemented."""

    def __init__(self, name: str):
        self._name = name

    @property
    def source_name(self) -> str:
        return self._name

    def collect(self) -> CollectorResult:
        return CollectorResult(
            source=self.source_name,
            jobs=[],
            status=CollectorStatus.NOT_IMPLEMENTED,
            error="Collector not yet implemented",
            count=0,
            duration_seconds=0.0,
        )
