"""The per-release secret (``RAKSHA_SECRET``).

``ReleaseSecret`` wraps the key bytes so that accidental ``print``/``repr``/f-string
formatting can never write the secret anywhere (the evaluator scans every output
channel for it). There is deliberately no default secret: running without one
would make pseudonyms an unkeyed function of the patient key.
"""

from __future__ import annotations

import os

ENV_VAR = "RAKSHA_SECRET"


class MissingSecretError(RuntimeError):
    def __init__(self) -> None:
        super().__init__(f"{ENV_VAR} is not set")


class ReleaseSecret:
    __slots__ = ("_key",)

    def __init__(self, key: bytes) -> None:
        if not key:
            raise MissingSecretError()
        self._key = key

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> ReleaseSecret:
        env = os.environ if environ is None else environ
        return cls(env.get(ENV_VAR, "").encode("utf-8"))

    @property
    def key(self) -> bytes:
        return self._key

    def __repr__(self) -> str:
        return "ReleaseSecret(<redacted>)"

    __str__ = __repr__

    def __format__(self, spec: str) -> str:
        return repr(self)

    def __reduce__(self):  # refuse pickling (e.g. into a multiprocessing temp file)
        raise TypeError("ReleaseSecret cannot be serialised")
