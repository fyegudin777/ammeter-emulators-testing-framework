"""Statistical analysis helpers for ammeter test results.

Notably, these emulators have no external ground-truth current to compare
against (each one derives its reading from independently randomized,
physically different inputs - voltage/resistance, magnetic field/calibration
factor, or sampled voltages - so there is no single "correct" value a given
run should match). Because of that, "accuracy" here is reframed as a
**precision / consistency** comparison: an ammeter that repeatedly reports
tightly clustered values is considered more reliable than one whose readings
are widely scattered, regardless of the absolute magnitude of its current.
"""

import statistics
from typing import Dict, List

from src.testing.models import TestResult

#: Supported metric names, matched against config.yaml's statistical_metrics list.
_METRIC_FUNCS = {
    "mean": statistics.mean,
    "median": statistics.median,
    "stdev": lambda values: statistics.stdev(values) if len(values) > 1 else 0.0,
    "min": min,
    "max": max,
}


def compute_statistics(values: List[float], metrics: List[str]) -> Dict[str, float]:
    """Compute the requested statistical metrics over a list of measurements.

    Parameters
    ----------
    values:
        Successful current measurements (amps) collected during a run.
    metrics:
        Names of metrics to compute, e.g. ``["mean", "median", "stdev",
        "min", "max"]`` (typically read from ``config.yaml``). Unknown
        metric names are silently skipped.

    Returns
    -------
    Dict[str, float]
        Metric name -> computed value. Returns an empty dict if ``values``
        is empty (no successful samples to analyze).
    """
    if not values:
        return {}
    return {
        name: _METRIC_FUNCS[name](values)
        for name in metrics
        if name in _METRIC_FUNCS
    }


def coefficient_of_variation(values: List[float]) -> float:
    """Return the coefficient of variation (stdev / mean) for ``values``.

    This is a unit-independent measure of relative dispersion, which makes
    it meaningful to compare *precision* across ammeter types even though
    each one measures current via a different physical quantity and range.
    Returns ``float('inf')`` if the mean is zero, or ``0.0`` for fewer than
    2 samples (no variability can be computed).
    """
    if len(values) < 2:
        return 0.0
    mean = statistics.mean(values)
    if mean == 0:
        return float("inf")
    return statistics.stdev(values) / abs(mean)


def compare_ammeters(results: Dict[str, TestResult]) -> List[Dict]:
    """Rank ammeter types by measurement precision/consistency.

    Parameters
    ----------
    results:
        Mapping of ammeter_type -> its :class:`TestResult`.

    Returns
    -------
    List[Dict]
        One entry per ammeter type, each with ``ammeter_type``, ``mean``,
        ``stdev``, ``coefficient_of_variation``, and ``sample_count``,
        sorted from most consistent (lowest coefficient of variation) to
        least. Ammeter types with no successful samples are placed last
        with ``coefficient_of_variation`` set to ``float('inf')``.

    Notes
    -----
    There is no ground-truth current value to measure *accuracy* against,
    so this ranks relative *precision* (how tightly clustered each
    ammeter's own readings are), not correctness.
    """
    summary = []
    for ammeter_type, result in results.items():
        values = result.successful_values
        if not values:
            summary.append(
                {
                    "ammeter_type": ammeter_type,
                    "mean": None,
                    "stdev": None,
                    "coefficient_of_variation": float("inf"),
                    "sample_count": 0,
                }
            )
            continue
        summary.append(
            {
                "ammeter_type": ammeter_type,
                "mean": statistics.mean(values),
                "stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
                "coefficient_of_variation": coefficient_of_variation(values),
                "sample_count": len(values),
            }
        )
    summary.sort(key=lambda row: row["coefficient_of_variation"])
    return summary
