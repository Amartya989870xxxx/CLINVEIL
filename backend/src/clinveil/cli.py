# Portions adapted from the Secret Wards toolkit starter, Copyright (c) 2026 kartikeyajay2006,
# MIT licence; see THIRD_PARTY_NOTICES.md. The MIT licence covers only those portions.
"""Command-line interface. Contract: ``--input <dir> --output <dir>`` (SPEC §1).

Exit codes: 0 = complete release; 1 = release incomplete or fatal error;
2 = usage/configuration error (missing secret, overlapping directories).
stdout/stderr carry counts and fixed messages only: both are scanned for PII.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from clinveil.config.policy import load_policy
from clinveil.security.secrets import MissingSecretError, ReleaseSecret

POLICY_ENV = "CLINVEIL_POLICY"


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="clinveil", description="CLINVEIL de-identification pipeline")
    ap.add_argument("--input", required=True, help="input directory (read-only)")
    ap.add_argument("--output", required=True, help="output directory (should be empty)")
    ap.add_argument("--policy", default=None, help="privacy policy file (default: config/policy.yaml)")
    return ap


def _overlaps(a: Path, b: Path) -> bool:
    a, b = a.resolve(), b.resolve()
    return a == b or a in b.parents or b in a.parents


def main(argv: list[str] | None = None, default_policy: Path | None = None) -> int:
    args = _parser().parse_args(argv)
    inp, out = Path(args.input), Path(args.output)
    if not inp.is_dir():
        print("clinveil: input directory not found", file=sys.stderr)
        return 2
    if _overlaps(inp, out):
        print("clinveil: input and output directories must not overlap", file=sys.stderr)
        return 2
    try:
        secret = ReleaseSecret.from_env()
    except MissingSecretError:
        print("clinveil: RAKSHA_SECRET is not set", file=sys.stderr)
        return 2

    policy_path = Path(args.policy or os.environ.get(POLICY_ENV) or default_policy or "config/policy.yaml")
    try:
        policy = load_policy(policy_path)
    except ValueError:
        print("clinveil: invalid policy file", file=sys.stderr)
        return 2

    from clinveil.pipeline import run

    try:
        summary = run(inp, out, secret, policy)
    except Exception as exc:  # noqa: BLE001 - never print a traceback: it can contain record content
        print(f"clinveil: fatal error ({type(exc).__name__})", file=sys.stderr)
        return 1

    print(
        f"files {summary.files_total} sanitized {summary.files_sanitized} "
        f"quarantined {summary.files_quarantined} records {summary.records}"
    )
    if not summary.ok:
        print(f"clinveil: release self-check failed ({len(summary.problems)} problems)", file=sys.stderr)
        for p in summary.problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
