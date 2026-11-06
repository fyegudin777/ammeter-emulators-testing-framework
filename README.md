# Ammeter Emulators & Testing Framework

This project provides emulators for different types of ammeters: Greenlee, ENTES, and CIRCUTOR. Each ammeter emulator runs on a separate thread and can respond to current measurement requests. On top of that, it provides a config-driven testing framework (`src/testing/`) that samples all three emulators, computes statistics, archives results, compares ammeter precision, and generates visualizations.

## Project Structure

- `main.py`: Starts the three emulators and makes one ad-hoc measurement request to each (smoke test for the emulators themselves).
- `Ammeters/`
  - `Circutor_Ammeter.py`, `Entes_Ammeter.py`, `Greenlee_Ammeter.py`: Emulators for each ammeter type.
  - `base_ammeter.py`: Base class for all ammeter emulators (TCP server loop).
  - `client.py`: TCP client used to request a single current measurement from an emulator.
  - `error_simulator.py`: Injects configurable, probability-based communication failures (connection refused, timeout, dropped sample, malformed response, out-of-range value) for exercising error handling.
  - `exceptions.py`: Exception hierarchy distinguishing real vs. simulated communication failures.
- `config/config.yaml`: Single source of configuration for sampling parameters, ammeter ports/commands, enabled statistics/plots, result storage, and the error-simulation profile.
- `tests/run_tests.py`: End-to-end example that starts the emulators and runs the full testing framework (sampling, archiving, comparison, visualization) against all three ammeter types. **Run this to see the framework in action.**
- `src/`
  - `testing/`
    - `test_framework.py`: `AmmeterTestFramework` - the main entry point (run a test, save/load results, compare ammeters, generate plots).
    - `models.py`: `Sample` / `TestResult` dataclasses used for in-memory data and JSON archiving.
    - `analysis.py`: Statistics (mean/median/stdev/min/max) and precision comparison across ammeter types.
    - `visualization.py`: Line, histogram, consistency-trend, and comparison boxplot plots (matplotlib).
  - `utils/`
    - `config.py`: YAML config loader.
    - `logger.py`: File + console logger, one log file per test run under `results/logs/`.
    - `Utils.py`: Utility functions, including `generate_random_float`.
- `results/` (generated at runtime, not committed): holds only the **most recent run's** `*.json` result(s), `plots/*.png`, and `logs/*.log`. Every time `AmmeterTestFramework` starts, whatever was left from the previous run is moved as a group into its own dated folder `results/archive/results_<timestamp>/` (containing that run's JSON files, `plots/`, and `logs/` together), so each past run can be opened and compared side-by-side with any other run's folder.

## Usage

### 1. Run the emulators standalone

To start the ammeter emulators and make one ad-hoc measurement request to each, run:
```sh
python main.py
```

### 2. Run the full testing framework

To start the emulators and run a complete sampling test (with statistics, JSON archiving, precision comparison, and plots) against all three ammeter types:
```sh
python tests/run_tests.py              # sequential: one ammeter at a time (default)
python tests/run_tests.py --parallel    # concurrent: all three ammeters tested simultaneously (threads)
```
This writes archived results to `results/*.json`, plots to `results/plots/*.png`, and logs to `results/logs/*.log`.

`--parallel` runs each ammeter's sampling test on its own thread instead of one after another. Each run only talks to its own TCP port and builds its own independent `TestResult`, so the three runs share no mutable state and are safe to execute concurrently (I/O-bound TCP calls, so the GIL isn't a bottleneck). Total wall-clock time drops from roughly the sum of all three runs to roughly the slowest single run.

### 3. Use the framework in your own code

```python
from src.testing.test_framework import AmmeterTestFramework

framework = AmmeterTestFramework()  # reads config/config.yaml
result = framework.run_test("entes")  # "greenlee" | "entes" | "circutor"
framework.save_result(result)
print(result.stats)  # {'mean': ..., 'median': ..., 'stdev': ..., 'min': ..., 'max': ...}
```
Start the emulators first (e.g. via `main.py`'s thread-starting logic or `tests/run_tests.py`'s `start_emulators()`), since `run_test` connects over TCP to whichever ports are configured.

### Configuration

All sampling parameters (`measurements_count`, `total_duration_seconds`, `sampling_frequency_hz`), ammeter ports/commands, enabled statistics and plot types, result storage location, and the error-simulation profile live in `config/config.yaml`. Adding a new ammeter type only requires a new entry under `ammeters:` plus a new emulator subclass - no framework code changes needed.

## Sample Test Results

A sample run of `python tests/run_tests.py` (20 samples per ammeter) produced:

| Ammeter   | Samples | Mean (A) | Median (A) | Stdev (A) | Min (A) | Max (A) | Coefficient of Variation |
|-----------|---------|----------|------------|-----------|---------|---------|---------------------------|
| ENTES     | 20/20   | 61.45    | 52.59      | 36.39     | 15.87   | 170.53  | 0.59 (most consistent)    |
| CIRCUTOR  | 20/20   | 0.0272   | 0.0235     | 0.0168    | 0.0051  | 0.0589  | 0.62                      |
| Greenlee  | 20/20   | 0.2716   | 0.1974     | 0.1974    | 0.0442  | 0.6853  | 0.73 (least consistent)   |

Full JSON archives and PNG plots (line/histogram/consistency-trend per ammeter plus a cross-ammeter boxplot) are written to `results/` each time the script runs; they are not committed since values are randomized per run.

## Design Decisions

- **Config-driven, not hardcoded**: every tunable (sampling, ammeters, statistics, plots, error simulation) lives in `config/config.yaml`, so new ammeter types or test parameters don't require touching framework code.
- **Auto-archiving of previous runs**: each time `AmmeterTestFramework` is instantiated, any files left in `results/` from a prior run are moved together into a single dated folder `results/archive/results_<timestamp>/`, so `results/` always reflects only the latest run while every past run stays grouped and directly comparable (e.g. `results/archive/results_20261106_001832/` vs. `results/archive/results_20261106_001920/`).
- **No ground-truth current value exists** across the three emulators (each derives its reading from independently randomized, physically different inputs - voltage/resistance, magnetic field/calibration factor, or sampled voltages). "Accuracy Assessment" is therefore reframed as a **precision/consistency** comparison using the coefficient of variation (stdev/mean), which is unit-independent and lets different-scale ammeters be compared fairly.
- **Dataclasses (`Sample`, `TestResult`) instead of raw dicts** for results, giving type hints, a single JSON (de)serialization path, and convenience properties (`successful_values`, `error_count`).
- **Per-sample error isolation**: a failed sample (real or simulated) is recorded, not fatal - the run continues and reports a success/failure ratio rather than aborting on the first problem.
- **Error simulation is opt-in and probabilistic** (`testing.error_simulation` in config), so the same framework can validate error-handling paths without modifying the emulators.
- **Sequential and parallel test execution, selectable at run time**: `tests/run_tests.py` defaults to testing each ammeter type one after another, but `--parallel` runs all three concurrently on separate threads via `ThreadPoolExecutor`. Each `run_test(ammeter_type)` call only opens its own TCP connection and builds its own independent `TestResult`/samples - no shared mutable state - so the runs are safe to parallelize (I/O-bound waits, so the GIL isn't a bottleneck); archiving/printing is deferred until every run finishes to keep per-ammeter output and JSON filenames from interleaving. This cuts total wall-clock time from roughly the sum of all three runs to roughly the slowest single run.

## Bugs Fixed

1. **`main.py` port/command mismatch**: the original script used ports `5001`/`5002`/`5003` and sent only command prefixes (e.g. `b'MEASURE_GREENLEE'`), but the emulators listen on `5000`/`5001`/`5002` and do a byte-for-byte comparison against the full command (e.g. `b'MEASURE_GREENLEE -get_measurement'`). Requests therefore never matched and no data was ever returned. Fixed by aligning the ports and sending the full command strings, matching this README.
2. **Greenlee emulator crash on Windows (`UnicodeEncodeError`)**: `Greenlee_Ammeter.py` prints a debug line containing the `Ω` (Ohm) character. On Windows, the console's default codepage (`cp1252`) cannot encode that character, which raised an unhandled exception inside the server thread on the very first request - silently killing the emulator (all subsequent connections were then refused, since nothing was listening anymore). Fixed by:
   - Reconfiguring `stdout` to UTF-8 (`sys.stdout.reconfigure(encoding="utf-8", errors="replace")`) in the entry points (`main.py`, `tests/run_tests.py`), so the existing debug print succeeds.
   - Hardening `base_ammeter.py`'s server loop to catch and log any exception while handling a single connection instead of letting it kill the whole thread, so one bad request/print can no longer take down an entire emulator for the rest of the process's lifetime.
3. **`tests/run_tests.py` was non-functional**: it called `framework.run_test()` without the required `ammeter_type` argument, never started the emulators, and never called `save_result`/`compare_ammeters`/`generate_visualizations`. Rewritten into a working end-to-end example (see Usage above).

## Libraries Installed

All dependencies are listed in `requirements.txt` and were already present in the project's virtual environment; no additional libraries beyond these were installed to build the framework:
- `pyyaml` - loading `config/config.yaml`.
- `matplotlib` - all visualizations (line/histogram/boxplot/consistency-trend plots).
- `numpy`, `scipy`, `pandas`, `seaborn` - available per `requirements.txt`; the core framework itself only relies on the Python standard library (`statistics`, `socket`, `json`, `dataclasses`) plus `pyyaml`/`matplotlib`, keeping the statistics/archiving path dependency-light.

## Ammeter Emulator Reference

### Greenlee Ammeter

- **Port**: 5000
- **Command**: `MEASURE_GREENLEE -get_measurement`
- **Measurement Logic**: Calculates current using voltage (1V - 10V) and resistance (0.1Ω - 100Ω).
- **Measurement method** : Ohm's Law: I = V / R

### ENTES Ammeter

- **Port**: 5001
- **Command**: `MEASURE_ENTES -get_data`
- **Measurement Logic**: Calculates current using magnetic field strength (0.01T - 0.1T) and calibration factor (500 - 2000).
- **Measurement method** : Hall Effect: I = B * K

### CIRCUTOR Ammeter

- **Port**: 5002
- **Command**: `MEASURE_CIRCUTOR -get_measurement -current`
- **Measurement Logic**: Calculates current using voltage values (0.1V - 1.0V) over a number of samples and a random time step (0.001s - 0.01s).
- **Measurement method** : Rogowski Coil Integration: I = ∫V dt