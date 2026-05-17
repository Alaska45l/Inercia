from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Any


@dataclass
class EstadoBot:
    phase: str = "idle"
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    queued: int = 0
    processed: int = 0
    inserted: int = 0
    failed: int = 0
    current_query: str = ""
    errors: list[str] = field(default_factory=list)
    _lock: Lock = field(default_factory=Lock)

    def set_phase(self, phase: str) -> None:
        with self._lock:
            self.phase = phase

    def record_queued(self, count: int) -> None:
        with self._lock:
            self.queued += count

    def record_processed(self, inserted: bool) -> None:
        with self._lock:
            self.processed += 1
            if inserted:
                self.inserted += 1

    def record_error(self, message: str) -> None:
        with self._lock:
            self.failed += 1
            self.errors.append(message)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "phase": self.phase,
                "started_at": self.started_at.isoformat(),
                "queued": self.queued,
                "processed": self.processed,
                "inserted": self.inserted,
                "failed": self.failed,
                "current_query": self.current_query,
                "errors": list(self.errors),
            }


__all__ = ["EstadoBot"]
