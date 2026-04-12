"""Session data model — one session per customer visit."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import List, Optional

TAGS = ["ISP Issue", "Hardware", "Placement", "Interference", "Resolved"]


@dataclass
class Session:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    customer_name: str = ""
    customer_address: str = ""
    notes: str = ""
    tags: List[str] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    ended_at: Optional[float] = None

    @property
    def is_active(self) -> bool:
        return self.ended_at is None

    @property
    def duration_s(self) -> float:
        end = self.ended_at or time.time()
        return end - self.started_at

    def end(self) -> None:
        self.ended_at = time.time()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "customer_name": self.customer_name,
            "customer_address": self.customer_address,
            "notes": self.notes,
            "tags": ",".join(self.tags),
            "started_at": self.started_at,
            "ended_at": self.ended_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Session:
        tags = [t for t in (d.get("tags") or "").split(",") if t]
        ea = d.get("ended_at")
        return cls(
            id=d.get("id", str(uuid.uuid4())),
            customer_name=d.get("customer_name", ""),
            customer_address=d.get("customer_address", ""),
            notes=d.get("notes", ""),
            tags=tags,
            started_at=float(d.get("started_at", time.time())),
            ended_at=float(ea) if ea is not None else None,
        )
