#!/usr/bin/env python3
"""CLINVEIL evaluator entry point (referenced by ``raksha.toml``).

    RAKSHA_SECRET=... python main.py --input <dir> --output <dir>

A thin shim: all logic lives in ``backend/src/clinveil``. It is put on
``sys.path`` directly so the evaluator needs no package install step.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend" / "src"))

from clinveil.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(default_policy=ROOT / "config" / "policy.yaml"))
