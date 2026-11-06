"""Data structures used to represent a single ammeter test run and its samples.

Keeping these as explicit dataclasses (rather than loose dicts) gives the
rest of the framework type hints and a single place to change the JSON
serialization format.
"""

import json
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional


@dataclass
class Sample:
    """A single current measurement attempt taken during a test run.

    Attributes
    ----------
    index:
        0-based position of this sample within the run.
    timestamp:
        ISO-8601 timestamp of when the sample was *attempted*.
    value:
        Parsed current in amps, or ``None`` if the sample failed.
    success:
        Whether a usable measurement was obtained.
    error:
        Short description of the failure (exception type + message), or
        ``None`` on success.
    simulated:
        Whether the failure (if any) was deliberately injected by
        :class:`Ammeters.error_simulator.ErrorSimulator` rather than a real
        communication problem.
    """

    index: int
    timestamp: str
    value: Optional[float] = None
    success: bool = True
    error: Optional[str] = None
    simulated: bool = False


@dataclass
class TestResult:
    """The complete, self-contained record of one ``run_test()`` execution.

    This is what gets serialized to JSON for archiving (see
    :meth:`AmmeterTestFramework.save_result`) and is also what feeds the
    statistics, comparison, and visualization helpers.
    """

    run_id: str
    ammeter_type: str
    started_at: str
    finished_at: str
    config_snapshot: Dict
    samples: List[Sample] = field(default_factory=list)
    stats: Dict[str, float] = field(default_factory=dict)

    @property
    def successful_values(self) -> List[float]:
        """Current readings (amps) from samples that succeeded, in order."""
        return [s.value for s in self.samples if s.success and s.value is not None]

    @property
    def error_count(self) -> int:
        """Number of samples that failed (real or simulated)."""
        return sum(1 for s in self.samples if not s.success)

    @property
    def simulated_error_count(self) -> int:
        """Number of failures that were deliberately injected, not real."""
        return sum(1 for s in self.samples if not s.success and s.simulated)

    def to_dict(self) -> Dict:
        """Convert this result (including nested samples) to a plain dict."""
        return asdict(self)

    def save_json(self, path: str) -> None:
        """Write this result as pretty-printed JSON to ``path``."""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def from_dict(cls, data: Dict) -> "TestResult":
        """Reconstruct a :class:`TestResult` previously produced by :meth:`to_dict`."""
        samples = [Sample(**s) for s in data.get("samples", [])]
        return cls(
            run_id=data["run_id"],
            ammeter_type=data["ammeter_type"],
            started_at=data["started_at"],
            finished_at=data["finished_at"],
            config_snapshot=data.get("config_snapshot", {}),
            samples=samples,
            stats=data.get("stats", {}),
        )

    @classmethod
    def load_json(cls, path: str) -> "TestResult":
        """Load a previously saved result JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f))
