from datetime import datetime, timedelta
from typing import Optional

from .db import History

SUCCESS_COOLDOWN = timedelta(minutes=10)
FAILURE_COOLDOWN = timedelta(seconds=30)
BRUTE_FORCE_LIMIT = 5
BRUTE_FORCE_WINDOW = timedelta(minutes=1)


def compute_cooldown(last_action: Optional[History]) -> Optional[timedelta]:
    if not last_action:
        return None
    now = datetime.utcnow()
    delta = now - last_action.timestamp
    if last_action.result == "success":
        remaining = SUCCESS_COOLDOWN - delta
    else:
        remaining = FAILURE_COOLDOWN - delta
    if remaining.total_seconds() > 0:
        return remaining
    return None
