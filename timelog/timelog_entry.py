from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List


@dataclass
class TimeLogEntry:
    start: datetime
    duration: timedelta
    tags: List[str]
    description: str
    id: int = None
    last_updated: datetime = None
