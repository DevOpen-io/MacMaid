from __future__ import annotations

import threading


class ScanCancelled(RuntimeError):
    """Cooperative, read-only scan cancellation signal."""


class CancellationToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def check(self) -> None:
        if self._event.is_set():
            raise ScanCancelled("Scan cancelled")
