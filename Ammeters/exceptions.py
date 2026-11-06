"""Custom exceptions raised while talking to an ammeter emulator.

Having a dedicated exception hierarchy lets the testing framework distinguish
*why* a measurement sample failed (connection problem vs. bad payload vs. a
deliberately injected simulated failure) instead of catching a generic
``Exception`` and losing that information.
"""


class AmmeterCommunicationError(Exception):
    """Base class for all errors raised by :mod:`Ammeters.client`.

    Catch this to handle any failure to obtain a measurement, regardless of
    the underlying cause.
    """


class AmmeterConnectionError(AmmeterCommunicationError):
    """Raised when the TCP connection to the ammeter emulator fails."""


class AmmeterTimeoutError(AmmeterCommunicationError):
    """Raised when the ammeter emulator does not respond in time."""


class AmmeterNoDataError(AmmeterCommunicationError):
    """Raised when the emulator closes the connection without sending data."""


class AmmeterMalformedResponseError(AmmeterCommunicationError):
    """Raised when the response cannot be decoded/parsed as a float."""


class SimulatedError(AmmeterCommunicationError):
    """Base class for errors deliberately injected by :mod:`Ammeters.error_simulator`.

    These subclass :class:`AmmeterCommunicationError` so existing error
    handling works unchanged, but they are also reported separately so test
    results clearly distinguish "real" failures from simulated ones.
    """


class SimulatedConnectionRefusedError(SimulatedError):
    """Simulated equivalent of a real ``ConnectionRefusedError``."""


class SimulatedTimeoutError(SimulatedError):
    """Simulated equivalent of a real socket timeout."""


class SimulatedDroppedSampleError(SimulatedError):
    """Simulates the emulator silently dropping/not answering a request."""
