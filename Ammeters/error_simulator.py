"""Configurable error-injection for exercising the testing framework's error handling.

Real hardware/communication links fail in predictable ways (dropped
connections, timeouts, garbled payloads, out-of-range readings). Since the
ammeter emulators in this repo never fail on their own, :class:`ErrorSimulator`
lets the test framework *deliberately* inject these failure modes, with
per-mode probabilities read from ``config.yaml``, so error handling and
reporting can be validated without touching the emulator code.
"""

import random
from dataclasses import dataclass, field
from typing import Dict

from Ammeters.exceptions import (
    SimulatedConnectionRefusedError,
    SimulatedDroppedSampleError,
    SimulatedTimeoutError,
)

#: Keys expected in the ``error_simulation`` section of config.yaml.
CONNECTION_REFUSED = "connection_refused_probability"
TIMEOUT = "timeout_probability"
DROPPED_SAMPLE = "dropped_sample_probability"
MALFORMED_RESPONSE = "malformed_response_probability"
OUT_OF_RANGE = "out_of_range_probability"


@dataclass
class ErrorSimulator:
    """Injects configurable, random communication failures for test samples.

    Parameters
    ----------
    profile:
        Mapping of failure-mode name -> probability (0.0-1.0) that the mode
        triggers on any given sample. Unknown/missing keys default to 0.0
        (i.e. disabled). An empty/``None`` profile never injects failures.
    enabled:
        Master on/off switch. When ``False`` the simulator never triggers,
        regardless of the configured probabilities.
    """

    profile: Dict[str, float] = field(default_factory=dict)
    enabled: bool = True

    def _probability(self, key: str) -> float:
        return float(self.profile.get(key, 0.0)) if self.enabled else 0.0

    def maybe_raise_pre_connection_error(self) -> None:
        """Possibly raise a simulated error *before* a real socket call is made.

        Raises
        ------
        SimulatedConnectionRefusedError
            With probability ``connection_refused_probability``.
        SimulatedTimeoutError
            With probability ``timeout_probability``.
        SimulatedDroppedSampleError
            With probability ``dropped_sample_probability``.
        """
        if random.random() < self._probability(CONNECTION_REFUSED):
            raise SimulatedConnectionRefusedError(
                "Simulated connection refused (error_simulation profile)."
            )
        if random.random() < self._probability(TIMEOUT):
            raise SimulatedTimeoutError(
                "Simulated timeout (error_simulation profile)."
            )
        if random.random() < self._probability(DROPPED_SAMPLE):
            raise SimulatedDroppedSampleError(
                "Simulated dropped sample / no data (error_simulation profile)."
            )

    def maybe_corrupt_response(self, data: bytes) -> bytes:
        """Possibly replace a valid response with an unparsable payload."""
        if random.random() < self._probability(MALFORMED_RESPONSE):
            return b"NOT_A_NUMBER"
        return data

    def maybe_push_out_of_range(self, value: float) -> float:
        """Possibly distort a valid measurement into a physically implausible one."""
        if random.random() < self._probability(OUT_OF_RANGE):
            # Current for these emulators is always small and positive;
            # a large negative spike is clearly "out of range".
            return -abs(value) * 1000.0
        return value

    @classmethod
    def from_config(cls, error_simulation_config: Dict) -> "ErrorSimulator":
        """Build an :class:`ErrorSimulator` from the ``error_simulation`` config block."""
        error_simulation_config = error_simulation_config or {}
        enabled = bool(error_simulation_config.get("enabled", False))
        profile = {
            CONNECTION_REFUSED: error_simulation_config.get(CONNECTION_REFUSED, 0.0),
            TIMEOUT: error_simulation_config.get(TIMEOUT, 0.0),
            DROPPED_SAMPLE: error_simulation_config.get(DROPPED_SAMPLE, 0.0),
            MALFORMED_RESPONSE: error_simulation_config.get(MALFORMED_RESPONSE, 0.0),
            OUT_OF_RANGE: error_simulation_config.get(OUT_OF_RANGE, 0.0),
        }
        return cls(profile=profile, enabled=enabled)
