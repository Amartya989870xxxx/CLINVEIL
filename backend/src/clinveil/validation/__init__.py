"""Pre-exit release self-checks.

The evaluator penalises "exit 0 with report.json missing or inputs silently
dropped" by -10. ``contract.check_release`` re-verifies the release on disk
before the CLI returns 0, and the CLI exits non-zero if any check fails.
The official ``validate_output.py`` remains the authority; this is a guard.
"""
