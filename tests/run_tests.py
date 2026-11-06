"""End-to-end example: start the ammeter emulators and exercise the full
AmmeterTestFramework (sampling, archiving, cross-ammeter comparison, and
visualization) against all three ammeter types.

Run from the repository root:

    python tests/run_tests.py              # sequential (default)
    python tests/run_tests.py --parallel    # concurrent (threads)
"""

import argparse
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Tuple

# Allow running this script directly (``python tests/run_tests.py``)
# without having installed the project as a package.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Some emulators print non-ASCII characters (e.g. Greenlee's "Ω" for Ohms).
# On Windows the console's default codepage (cp1252) can't encode those,
# which previously crashed the emulator thread on its first request. Forcing
# UTF-8 stdout fixes it without changing the emulators' debug-print text.
# See README.md "Bugs Fixed" section.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from Ammeters.Circutor_Ammeter import CircutorAmmeter
from Ammeters.Entes_Ammeter import EntesAmmeter
from Ammeters.Greenlee_Ammeter import GreenleeAmmeter
from src.testing.test_framework import AmmeterTestFramework
from src.testing.models import TestResult

GREENLEE_PORT = 5000
ENTES_PORT = 5001
CIRCUTOR_PORT = 5002


def start_emulators() -> None:
    """Start all three ammeter emulators, each on its own daemon thread."""
    emulators = [
        GreenleeAmmeter(GREENLEE_PORT),
        EntesAmmeter(ENTES_PORT),
        CircutorAmmeter(CIRCUTOR_PORT),
    ]
    for emulator in emulators:
        threading.Thread(target=emulator.start_server, daemon=True).start()

    # Give the servers a moment to bind their sockets before we connect.
    time.sleep(2)


def _run_single_ammeter_test(
    framework: AmmeterTestFramework, ammeter_type: str
) -> Tuple[str, TestResult]:
    """Run the configured sampling loop against one live emulator.

    Returns the ``ammeter_type`` alongside its :class:`TestResult` so this
    can be used directly as the work unit for both the sequential loop and
    the parallel thread pool below.
    """
    result = framework.run_test(ammeter_type)
    return ammeter_type, result


def _report_result(framework: AmmeterTestFramework, ammeter_type: str, result: TestResult) -> None:
    """Archive one ammeter's result and print its summary."""
    # Archive the run as JSON under results/ for later retrieval/comparison.
    saved_path = framework.save_result(result)
    print(f"  [{ammeter_type}] Archived to: {saved_path}")

    stats = result.stats
    print(
        f"  [{ammeter_type}] Samples: {len(result.successful_values)}/{len(result.samples)} successful "
        f"(errors: {result.error_count})"
    )
    if stats:
        print(
            f"  [{ammeter_type}] Stats: "
            f"mean={stats.get('mean'):.4f}A "
            f"median={stats.get('median'):.4f}A "
            f"stdev={stats.get('stdev'):.4f}A "
            f"min={stats.get('min'):.4f}A "
            f"max={stats.get('max'):.4f}A"
        )
    else:
        # Every sample failed (e.g. emulator unreachable); nothing to
        # compute statistics over.
        print(f"  [{ammeter_type}] Stats: no successful samples")


def run_sequential(
    framework: AmmeterTestFramework, ammeter_types: List[str]
) -> Dict[str, TestResult]:
    """Run each ammeter's sampling test one after another (original behavior).

    Total wall-clock time is roughly the sum of each ammeter's run
    (``testing.sampling.total_duration_seconds`` x number of ammeters).
    """
    results: Dict[str, TestResult] = {}
    for ammeter_type in ammeter_types:
        print(f"\nTesting {ammeter_type} ammeter...")
        _, result = _run_single_ammeter_test(framework, ammeter_type)
        results[ammeter_type] = result
        _report_result(framework, ammeter_type, result)
    return results


def run_parallel(
    framework: AmmeterTestFramework, ammeter_types: List[str]
) -> Dict[str, TestResult]:
    """Run every ammeter's sampling test concurrently on separate threads.

    Each ``run_test`` call only talks to its own TCP port and produces its
    own independent ``TestResult``/samples, so the three runs don't share
    mutable state and are safe to execute in parallel (I/O-bound, so the
    GIL isn't a bottleneck). Archiving/printing is deferred until every run
    has finished so one ammeter's console output isn't interleaved with
    another's. Total wall-clock time is roughly the slowest single
    ammeter's run instead of the sum of all three.
    """
    print(f"\nTesting {len(ammeter_types)} ammeters in parallel: {', '.join(ammeter_types)}...")
    results: Dict[str, TestResult] = {}
    with ThreadPoolExecutor(max_workers=len(ammeter_types)) as executor:
        futures = {
            executor.submit(_run_single_ammeter_test, framework, ammeter_type): ammeter_type
            for ammeter_type in ammeter_types
        }
        for future in as_completed(futures):
            ammeter_type, result = future.result()
            results[ammeter_type] = result

    # Report in a stable, deterministic order once every run has finished.
    for ammeter_type in ammeter_types:
        _report_result(framework, ammeter_type, results[ammeter_type])
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--parallel",
        action="store_true",
        help=(
            "Run the sampling test for all ammeter types concurrently "
            "(threads) instead of one after another. Default: sequential."
        ),
    )
    args = parser.parse_args()

    start_emulators()

    # Reads config/config.yaml (sampling params, ammeter ports/commands,
    # enabled statistics/plots, result storage, error-simulation profile).
    framework = AmmeterTestFramework()
    ammeter_types = ["greenlee", "entes", "circutor"]

    results = (
        run_parallel(framework, ammeter_types)
        if args.parallel
        else run_sequential(framework, ammeter_types)
    )

    # Rank ammeter types by precision (coefficient of variation = stdev/mean).
    # There's no ground-truth current value to compare "accuracy" against
    # (see README.md "Design Decisions"), so consistency is used instead.
    print("\n=== Ammeter precision comparison (most to least consistent) ===")
    comparison = framework.compare_ammeters(results)
    for rank, entry in enumerate(comparison, start=1):
        cv = entry["coefficient_of_variation"]
        cv_str = f"{cv:.4f}" if cv != float("inf") else "inf"
        print(
            f"  {rank}. {entry['ammeter_type']}: "
            f"mean={entry['mean']}, stdev={entry['stdev']}, "
            f"coefficient_of_variation={cv_str}, samples={entry['sample_count']}"
        )

    # Generates whichever plot types are enabled in config.yaml
    # (analysis.visualization.plot_types) under results/plots/.
    plots = framework.generate_visualizations(results)
    if plots:
        print(f"\nGenerated {len(plots)} plot(s):")
        for path in plots:
            print(f"  {path}")
    else:
        print("\nVisualization disabled in config.yaml; no plots generated.")


if __name__ == "__main__":
    main()
