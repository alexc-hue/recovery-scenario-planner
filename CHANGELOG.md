# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and version numbers
follow [Semantic Versioning](https://semver.org/).

## [1.2.0] - 2026-09-28

Performance at larger sizes. Output is unchanged: the console report is byte-identical to the previous release on the sample data and on generated inputs, and the comparison chart renders pixel-identical, so no committed image changed.

### Added

- `benchmarks/size_test.py`, a hand-run size test: generates bigger inputs, runs the tool end to end
  and prints run time and peak memory. Not part of CI or the test suite.
- Measured size-test numbers in the README's Limitations section.

### Changed

- The vendored CPM engine re-copied from schedule-health-analyzer for its single-pass network
  ordering (same order, same results).
- The vendored risk engine re-copied from risk-trend-tracker for its per-risk rewrite (same
  results). 50,000 activities now run in about 19 seconds.

## [1.1.0] - 2026-09-28

Checks and tests only. The tool's output is unchanged.

### Added

- A test that runs `planner.py` end to end on the sample data and checks the README's Result block against what it actually prints, so the README can't drift from the code.
- Regression tests for the code-review fixes already in 1.0.0: the recovery score floored at 0, crash cost billed on the cut actually applied, chained fast-track pairs reading the original predecessors, chart code bugs surfacing instead of being swallowed, and a 4th scenario failing loudly rather than reusing a color.
- `engines/VENDORED.json`, recording the source repo, file and commit each vendored engine came from, plus `scripts/vendored.py` to check the copies.
- A test that fails if a vendored engine is edited here without being re-vendored from its source.
- A CI job, on every push and weekly, that checks the vendored engines against their sources on GitHub.
- A test that pins the chart colors and styling shared across all six toolkit repos.
- ruff linting, run locally from `ruff.toml` and as its own CI job.
- CI now tests on Python 3.11 and 3.12, matching the "Python 3.11+" badge.
- `.gitattributes` keeps line endings consistent (LF) on every OS.

### Changed

- Import ordering in `planner.py`, from the new lint rules. No behaviour change.

## [1.0.0] - 2026-09-13

First tagged release, marking the state of the repo before this changelog started. Models three recovery options (add resources, fast-track, accept the delay) with the vendored CPM engine and ranks them against schedule, cost and risk with a stated decision-rule table. Includes the fixes from code review, a pytest suite and CI.

[1.2.0]: https://github.com/alexc-hue/recovery-scenario-planner/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/alexc-hue/recovery-scenario-planner/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/alexc-hue/recovery-scenario-planner/releases/tag/v1.0.0
