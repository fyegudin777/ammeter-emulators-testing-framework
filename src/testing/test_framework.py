"""Unified testing framework for the ammeter emulators.

:class:`AmmeterTestFramework` is the single entry point used to:

1. Run a configurable sampling test against any ammeter type (
   :meth:`AmmeterTestFramework.run_test`).
2. Archive results as JSON with a unique run ID (
   :meth:`AmmeterTestFramework.save_result` /
   :meth:`AmmeterTestFramework.load_results`).
3. Compare precision across ammeter types (
   :meth:`AmmeterTestFramework.compare_ammeters`).
4. Generate visualizations (
   :meth:`AmmeterTestFramework.generate_visualizations`).

Everything the framework needs - which ammeters exist, sampling parameters,
which statistics/plots to produce, and the error-simulation profile - comes
from ``config.yaml``. Adding a new ammeter type only requires a new entry
under ``ammeters:`` in the config plus a new emulator subclass; no changes
to this file are needed.
"""

import os
import re
import shutil
import time
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from Ammeters.client import request_current_from_ammeter
from Ammeters.error_simulator import ErrorSimulator
from Ammeters.exceptions import AmmeterCommunicationError, SimulatedError
from src.testing import visualization
from src.testing.analysis import compare_ammeters as _compare_ammeters
from src.testing.analysis import compute_statistics
from src.testing.models import Sample, TestResult
from src.utils.config import load_config
from src.utils.logger import TestLogger

#: Matches the ``YYYYMMDD_HHMMSS`` timestamp prefix used for result JSON
#: files, plot PNGs, and log files (e.g. ``20261106_001832_greenlee_...``).
_TIMESTAMP_PREFIX_RE = re.compile(r"^(\d{8}_\d{6})_")


class AmmeterTestFramework:
    """Config-driven test runner for the ammeter emulators.

    Parameters
    ----------
    config_path:
        Path to the YAML configuration file describing sampling parameters,
        known ammeters, enabled statistics/plots, result storage location,
        and the error-simulation profile.
    """

    def __init__(self, config_path: str = "config/config.yaml"):
        self.config = load_config(config_path)

        result_cfg = self.config.get("result_management", {}) or {}
        self.results_dir = result_cfg.get("results_dir", "results")
        self.filename_pattern = result_cfg.get(
            "filename_pattern", "{timestamp}_{ammeter_type}_{run_id}.json"
        )

        # Move any outputs left over from a previous run into
        # results/archive/results_<timestamp>/ *before* this run's
        # logger/results start writing, so results_dir only ever contains
        # the most recent run's artifacts, while every prior run stays
        # grouped in its own dated folder for easy side-by-side comparison.
        self._archive_existing_results()

        self.logger = TestLogger("ammeter_framework")
        os.makedirs(self.results_dir, exist_ok=True)

    def _archive_existing_results(self) -> None:
        """Move everything currently under ``results_dir`` into a single
        dated ``results_dir/archive/results_<timestamp>/`` folder ahead of
        a new run.

        Grouping a whole run's JSON results, ``plots/``, and ``logs/``
        together under one folder (named after when that run started)
        means every past run can be compared directly - e.g.
        ``results/archive/results_20261106_001832/`` vs.
        ``results/archive/results_20261106_001920/`` - instead of being
        mixed together in flat ``archive/plots`` / ``archive/logs``
        folders.
        """
        if not os.path.isdir(self.results_dir):
            return

        entries = [name for name in os.listdir(self.results_dir) if name != "archive"]
        if not entries:
            return  # Nothing to archive.

        session_timestamp = self._earliest_timestamp(entries) or datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )
        session_archive_dir = os.path.join(
            self.results_dir, "archive", f"results_{session_timestamp}"
        )
        os.makedirs(session_archive_dir, exist_ok=True)

        for name in entries:
            shutil.move(
                os.path.join(self.results_dir, name),
                os.path.join(session_archive_dir, name),
            )

    @staticmethod
    def _earliest_timestamp(entries: List[str]) -> Optional[str]:
        """Extract the earliest ``YYYYMMDD_HHMMSS`` prefix found among
        ``entries`` (e.g. a previous run's JSON result filenames), used to
        name that run's archive folder after when it started. Entries
        without a recognizable prefix (e.g. the ``plots``/``logs``
        subdirectories themselves) are ignored.
        """
        timestamps = [
            match.group(1)
            for name in entries
            for match in [_TIMESTAMP_PREFIX_RE.match(name)]
            if match
        ]
        return min(timestamps) if timestamps else None

    # ------------------------------------------------------------------
    # Core test execution
    # ------------------------------------------------------------------
    def _ammeter_config(self, ammeter_type: str) -> Dict:
        ammeters = self.config.get("ammeters", {}) or {}
        if ammeter_type not in ammeters:
            raise ValueError(
                f"Unknown ammeter_type '{ammeter_type}'. "
                f"Known types: {sorted(ammeters.keys())}"
            )
        return ammeters[ammeter_type]

    def run_test(self, ammeter_type: str) -> TestResult:
        """Run a full sampling test against one configured ammeter type.

        Connects to the ammeter emulator repeatedly according to the
        ``testing.sampling`` config (measurement count, total duration, and
        sampling frequency - whichever limit is hit first stops the run),
        recording every sample's outcome. Communication failures (real or,
        if ``testing.error_simulation`` is enabled, deliberately simulated)
        are caught per-sample and recorded rather than aborting the run.

        Parameters
        ----------
        ammeter_type:
            Key into the ``ammeters`` config section, e.g. ``"greenlee"``.

        Returns
        -------
        TestResult
            The full record of the run, including every sample and computed
            statistics over the successful ones.
        """
        ammeter_cfg = self._ammeter_config(ammeter_type)
        port = ammeter_cfg["port"]
        command = ammeter_cfg["command"].encode("utf-8")

        sampling_cfg = self.config.get("testing", {}).get("sampling", {}) or {}
        measurements_count = sampling_cfg.get("measurements_count") or 20
        total_duration_seconds = sampling_cfg.get("total_duration_seconds") or 10
        sampling_frequency_hz = sampling_cfg.get("sampling_frequency_hz") or 2
        interval = 1.0 / sampling_frequency_hz if sampling_frequency_hz else 0

        error_sim_cfg = self.config.get("testing", {}).get("error_simulation", {})
        error_simulator = ErrorSimulator.from_config(error_sim_cfg)

        run_id = str(uuid.uuid4())
        started_at = datetime.now().isoformat()
        start_time = time.monotonic()
        samples: List[Sample] = []

        self.logger.info(f"Starting run {run_id} for ammeter '{ammeter_type}'")

        index = 0
        while (
            index < measurements_count
            and (time.monotonic() - start_time) < total_duration_seconds
        ):
            sample = self._take_sample(index, port, command, error_simulator)
            samples.append(sample)
            index += 1
            if interval:
                time.sleep(interval)

        finished_at = datetime.now().isoformat()

        stats_metrics = (
            self.config.get("analysis", {}).get("statistical_metrics")
            or ["mean", "median", "stdev", "min", "max"]
        )
        successful_values = [s.value for s in samples if s.success]
        stats = compute_statistics(successful_values, stats_metrics)

        result = TestResult(
            run_id=run_id,
            ammeter_type=ammeter_type,
            started_at=started_at,
            finished_at=finished_at,
            config_snapshot={
                "port": port,
                "command": ammeter_cfg["command"],
                "sampling": sampling_cfg,
                "error_simulation": error_sim_cfg,
            },
            samples=samples,
            stats=stats,
        )

        self.logger.info(
            f"Finished run {run_id} for '{ammeter_type}': "
            f"{len(successful_values)}/{len(samples)} successful samples, "
            f"stats={stats}"
        )
        return result

    def _take_sample(
        self,
        index: int,
        port: int,
        command: bytes,
        error_simulator: ErrorSimulator,
    ) -> Sample:
        """Attempt a single measurement, catching and recording any failure."""
        timestamp = datetime.now().isoformat()
        try:
            value = request_current_from_ammeter(
                port, command, error_simulator=error_simulator
            )
            return Sample(index=index, timestamp=timestamp, value=value, success=True)
        except AmmeterCommunicationError as exc:
            simulated = isinstance(exc, SimulatedError)
            self.logger.warning(
                f"Sample {index} failed ({'simulated' if simulated else 'real'}): {exc}"
            )
            return Sample(
                index=index,
                timestamp=timestamp,
                value=None,
                success=False,
                error=f"{type(exc).__name__}: {exc}",
                simulated=simulated,
            )

    # ------------------------------------------------------------------
    # Result archiving
    # ------------------------------------------------------------------
    def save_result(self, result: TestResult) -> str:
        """Archive a :class:`TestResult` as JSON under ``results_dir``.

        Returns the path the file was written to.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = self.filename_pattern.format(
            timestamp=timestamp, ammeter_type=result.ammeter_type, run_id=result.run_id
        )
        path = os.path.join(self.results_dir, filename)
        result.save_json(path)
        self.logger.info(f"Saved result for run {result.run_id} to {path}")
        return path

    def load_results(self, ammeter_type: Optional[str] = None) -> List[TestResult]:
        """Load all previously archived results, optionally filtered by ammeter type."""
        results = []
        if not os.path.isdir(self.results_dir):
            return results
        for name in os.listdir(self.results_dir):
            if not name.endswith(".json"):
                continue
            path = os.path.join(self.results_dir, name)
            try:
                result = TestResult.load_json(path)
            except (ValueError, KeyError, OSError) as exc:
                self.logger.warning(f"Skipping unreadable result file {path}: {exc}")
                continue
            if ammeter_type is None or result.ammeter_type == ammeter_type:
                results.append(result)
        return results

    # ------------------------------------------------------------------
    # Analysis / reporting
    # ------------------------------------------------------------------
    def compare_ammeters(self, results: Dict[str, TestResult]) -> List[Dict]:
        """Rank ammeter types by measurement precision/consistency.

        See :func:`src.testing.analysis.compare_ammeters` for details; there
        is no ground-truth current to compare *accuracy* against, so this
        ranks relative consistency instead.
        """
        return _compare_ammeters(results)

    def generate_visualizations(
        self, results: Dict[str, TestResult]
    ) -> List[str]:
        """Generate all plots enabled in ``analysis.visualization`` config.

        Produces per-run plots (line/histogram/consistency_trend) for each
        result plus one comparison boxplot across all of them, saved under
        ``analysis.visualization.output_dir``.

        Returns
        -------
        List[str]
            Paths to every PNG file generated. Empty if visualization is
            disabled in config.
        """
        viz_cfg = self.config.get("analysis", {}).get("visualization", {}) or {}
        if not viz_cfg.get("enabled", False):
            return []

        output_dir = viz_cfg.get("output_dir", "results/plots")
        plot_types = viz_cfg.get("plot_types", []) or []
        generated = []

        for result in results.values():
            generated.extend(
                visualization.generate_plots(result, output_dir, plot_types)
            )

        if "boxplot" in plot_types and len(results) > 1:
            generated.append(
                visualization.plot_comparison_boxplot(results, output_dir)
            )

        self.logger.info(f"Generated {len(generated)} plot(s) under {output_dir}")
        return generated