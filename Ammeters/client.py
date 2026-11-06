import socket as socket_module
from socket import socket, AF_INET, SOCK_STREAM
from typing import Optional

from Ammeters.error_simulator import ErrorSimulator
from Ammeters.exceptions import (
    AmmeterConnectionError,
    AmmeterMalformedResponseError,
    AmmeterNoDataError,
    AmmeterTimeoutError,
)

#: Default time (seconds) to wait for a response before raising AmmeterTimeoutError.
DEFAULT_TIMEOUT_SECONDS = 5.0


def request_current_from_ammeter(
    port: int,
    command: bytes,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    error_simulator: Optional[ErrorSimulator] = None,
) -> float:
    """Request a single current measurement from an ammeter emulator.

    Parameters
    ----------
    port:
        TCP port the target ammeter emulator is listening on (see README.md).
    command:
        Exact command bytes expected by the emulator's
        ``get_current_command`` property. The emulator does a byte-for-byte
        comparison, so this must match completely (including any
        ``-get_measurement``/``-get_data`` suffix).
    timeout:
        Socket timeout in seconds. Raises :class:`AmmeterTimeoutError` if
        exceeded.
    error_simulator:
        Optional :class:`~Ammeters.error_simulator.ErrorSimulator` used to
        deliberately inject failures (connection refused, timeout, dropped
        sample, malformed response, out-of-range value) for testing the
        framework's error handling. Pass ``None`` (default) to disable
        simulation and always perform a real request.

    Returns
    -------
    float
        The parsed current measurement in amps.

    Raises
    ------
    AmmeterConnectionError
        If the TCP connection could not be established (including simulated
        connection-refused failures).
    AmmeterTimeoutError
        If the emulator did not respond within ``timeout`` seconds (including
        simulated timeouts).
    AmmeterNoDataError
        If the emulator closed the connection without sending any data
        (including simulated dropped samples).
    AmmeterMalformedResponseError
        If the response could not be decoded/parsed as a float (including
        simulated malformed responses).
    """
    if error_simulator is not None:
        # May raise SimulatedConnectionRefusedError / SimulatedTimeoutError /
        # SimulatedDroppedSampleError, all of which are themselves
        # AmmeterCommunicationError subclasses, so callers only need to
        # handle the real exception types below.
        error_simulator.maybe_raise_pre_connection_error()

    try:
        with socket(AF_INET, SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect(('localhost', port))
            s.sendall(command)
            data = s.recv(1024)
    except socket_module.timeout as exc:
        raise AmmeterTimeoutError(
            f"Timed out waiting for a response from port {port}."
        ) from exc
    except OSError as exc:
        raise AmmeterConnectionError(
            f"Could not connect to ammeter emulator on port {port}: {exc}"
        ) from exc

    if not data:
        raise AmmeterNoDataError(f"No data received from port {port}.")

    if error_simulator is not None:
        data = error_simulator.maybe_corrupt_response(data)

    try:
        value = float(data.decode('utf-8'))
    except (UnicodeDecodeError, ValueError) as exc:
        raise AmmeterMalformedResponseError(
            f"Could not parse response from port {port}: {data!r}"
        ) from exc

    if error_simulator is not None:
        value = error_simulator.maybe_push_out_of_range(value)

    print(f"Received current measurement from port {port}: {value} A")
    return value

