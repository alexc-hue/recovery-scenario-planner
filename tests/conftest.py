"""Shared pytest setup.

Forces matplotlib's non-interactive Agg backend before any test imports the
entry script, so tests that run it end to end can save charts on a machine
with no display (CI runners, headless servers).
"""

import matplotlib

matplotlib.use("Agg")
