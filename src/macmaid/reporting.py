from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

MEASUREMENT_CAVEAT = (
    "Observed free-space change is a filesystem-wide before/after sample, not space proven to be reclaimed "
    "by MacMaid. APFS clones, snapshots, sparse files and concurrent disk activity can change the value."
)


@dataclass(slots=True)
class FreeSpaceProbe:
    """Best-effort free-space samples, deduplicated by filesystem device."""

    samples: dict[int, tuple[Path, int]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @classmethod
    def capture(cls, paths: Iterable[Path | None]) -> "FreeSpaceProbe":
        probe = cls()
        for raw in paths:
            if raw is None:
                continue
            anchor = Path(raw).absolute()
            while not anchor.exists() and anchor != anchor.parent:
                anchor = anchor.parent
            try:
                device = anchor.stat().st_dev
                probe.samples.setdefault(device, (anchor, shutil.disk_usage(anchor).free))
            except OSError as exc:
                probe.errors.append(f"Free-space measurement unavailable for {anchor}: {exc}")
        return probe

    def finish(self) -> tuple[int | None, list[str]]:
        if not self.samples:
            notes = [*self.errors, "No target filesystem was available for free-space measurement.", MEASUREMENT_CAVEAT]
            return None, notes
        delta = 0
        measured = 0
        notes = list(self.errors)
        for anchor, before in self.samples.values():
            try:
                delta += shutil.disk_usage(anchor).free - before
                measured += 1
            except OSError as exc:
                notes.append(f"Free-space measurement unavailable after operation for {anchor}: {exc}")
        notes.append(MEASUREMENT_CAVEAT)
        return (delta if measured else None), notes
