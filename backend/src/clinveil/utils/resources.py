"""Process resource measurement for ``report.json``."""

from __future__ import annotations

import sys


def peak_rss_mb() -> float:
    """Peak RSS of this process in MB (ru_maxrss is KiB on Linux, bytes on macOS)."""
    try:
        import resource

        r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return round(r / 1024 if sys.platform != "darwin" else r / 1048576, 1)
    except Exception:  # noqa: BLE001 - not available on every OS
        return 0.0
