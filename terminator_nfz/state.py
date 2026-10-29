"""Trwały stan między uruchomieniami: zgłoszone już terminy i licznik błędów."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class State:
    seen: dict = field(default_factory=dict)  # klucz slotu -> ISO czasu wizyty
    fail_streak: int = 0
    failure_alerted: bool = False
    saved_at: datetime | None = None

    @classmethod
    def load(cls, path):
        path = Path(path)
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        saved_at = data.get("saved_at")
        return cls(
            seen=data.get("seen", {}),
            fail_streak=data.get("fail_streak", 0),
            failure_alerted=data.get("failure_alerted", False),
            saved_at=datetime.fromisoformat(saved_at) if saved_at else None,
        )

    def save(self, path, now):
        self.saved_at = now
        data = {
            "seen": dict(sorted(self.seen.items())),
            "fail_streak": self.fail_streak,
            "failure_alerted": self.failure_alerted,
            "saved_at": now.isoformat(timespec="seconds"),
        }
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
