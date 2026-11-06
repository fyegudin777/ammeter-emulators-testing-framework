"""Visualization helpers for ammeter test results.

All plotting is optional and config-driven (``analysis.visualization`` in
config.yaml): callers pass in which plot types are enabled and this module
renders only those, saving each figure as a PNG under
``analysis.visualization.output_dir`` (default ``results/plots``).
"""

import os
from datetime import datetime
from typing import Dict, List

import matplotlib
# Use a non-interactive backend so this works headlessly on any platform
# (no display required), which keeps the framework cross-platform and
# avoids a GUI dependency.
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.testing.models import TestResult


def _ensure_dir(output_dir: str) -> None:
    os.makedirs(output_dir, exist_ok=True)


def _compact_timestamp(iso_timestamp: str) -> str:
    """Convert an ISO-8601 timestamp (e.g. ``result.finished_at``) into the
    same compact ``YYYYMMDD_HHMMSS`` format used for archived JSON result
    filenames, so plot files are datetime-named/sortable just like them.
    Falls back to the current time if parsing fails.
    """
    try:
        dt = datetime.fromisoformat(iso_timestamp)
    except (TypeError, ValueError):
        dt = datetime.now()
    return dt.strftime("%Y%m%d_%H%M%S")


def plot_line(result: TestResult, output_dir: str) -> str:
    """Plot current measurements over sample index for a single run.

    Returns the path to the saved PNG.
    """
    _ensure_dir(output_dir)
    values = [s.value for s in result.samples if s.success]
    indices = [s.index for s in result.samples if s.success]
    timestamp = _compact_timestamp(result.finished_at)

    fig, ax = plt.subplots()
    ax.plot(indices, values, marker="o")
    ax.set_title(f"{result.ammeter_type} - current over samples ({result.run_id})")
    ax.set_xlabel("Sample index")
    ax.set_ylabel("Current (A)")
    path = os.path.join(
        output_dir, f"{timestamp}_{result.ammeter_type}_{result.run_id}_line.png"
    )
    fig.savefig(path)
    plt.close(fig)
    return path


def plot_histogram(result: TestResult, output_dir: str) -> str:
    """Plot a histogram of successful current measurements for a single run."""
    _ensure_dir(output_dir)
    values = result.successful_values
    timestamp = _compact_timestamp(result.finished_at)

    fig, ax = plt.subplots()
    ax.hist(values, bins=min(10, max(1, len(values))))
    ax.set_title(f"{result.ammeter_type} - measurement distribution ({result.run_id})")
    ax.set_xlabel("Current (A)")
    ax.set_ylabel("Frequency")
    path = os.path.join(
        output_dir, f"{timestamp}_{result.ammeter_type}_{result.run_id}_hist.png"
    )
    fig.savefig(path)
    plt.close(fig)
    return path


def plot_consistency_trend(result: TestResult, output_dir: str, window: int = 5) -> str:
    """Plot a rolling standard deviation over the run to visualize stability.

    A flat, low line indicates a consistently precise ammeter; spikes
    indicate periods of erratic measurement.
    """
    _ensure_dir(output_dir)
    values = result.successful_values
    timestamp = _compact_timestamp(result.finished_at)
    rolling_std = []
    for i in range(len(values)):
        window_values = values[max(0, i - window + 1): i + 1]
        if len(window_values) > 1:
            mean = sum(window_values) / len(window_values)
            variance = sum((v - mean) ** 2 for v in window_values) / (len(window_values) - 1)
            rolling_std.append(variance ** 0.5)
        else:
            rolling_std.append(0.0)

    fig, ax = plt.subplots()
    ax.plot(range(len(rolling_std)), rolling_std, marker="o", color="tab:orange")
    ax.set_title(f"{result.ammeter_type} - rolling std-dev (window={window}) ({result.run_id})")
    ax.set_xlabel("Sample index")
    ax.set_ylabel("Rolling std-dev (A)")
    path = os.path.join(
        output_dir, f"{timestamp}_{result.ammeter_type}_{result.run_id}_trend.png"
    )
    fig.savefig(path)
    plt.close(fig)
    return path


def plot_comparison_boxplot(results: Dict[str, TestResult], output_dir: str) -> str:
    """Plot a boxplot comparing successful measurements across ammeter types."""
    _ensure_dir(output_dir)
    labels = list(results.keys())
    data = [results[name].successful_values or [0.0] for name in labels]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    fig, ax = plt.subplots()
    ax.boxplot(data, tick_labels=labels)
    ax.set_title("Current measurement comparison across ammeter types")
    ax.set_ylabel("Current (A)")
    path = os.path.join(output_dir, f"{timestamp}_ammeter_comparison_boxplot.png")
    fig.savefig(path)
    plt.close(fig)
    return path


def generate_plots(
    result: TestResult, output_dir: str, plot_types: List[str]
) -> List[str]:
    """Generate all per-run plots enabled in ``plot_types``.

    Parameters
    ----------
    result:
        The run to visualize.
    output_dir:
        Directory to save PNGs into (created if missing).
    plot_types:
        Subset of ``{"line", "histogram", "consistency_trend"}`` (typically
        read from ``config.yaml``'s ``analysis.visualization.plot_types``).
        Unknown names are ignored. ``"boxplot"`` is handled separately by
        :func:`plot_comparison_boxplot` since it compares multiple runs.

    Returns
    -------
    List[str]
        Paths to the PNG files that were generated.
    """
    if not result.successful_values:
        return []

    generated = []
    if "line" in plot_types:
        generated.append(plot_line(result, output_dir))
    if "histogram" in plot_types:
        generated.append(plot_histogram(result, output_dir))
    if "consistency_trend" in plot_types:
        generated.append(plot_consistency_trend(result, output_dir))
    return generated
