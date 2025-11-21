import datetime
import sqlite3
from pathlib import Path

from .timelog_entry import TimeLogEntry

DB_PATH = Path(__file__).parent / "timelog.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS time_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start DATETIME NOT NULL,
            duration_seconds INTEGER NOT NULL,
            tags TEXT NOT NULL,
            description TEXT NOT NULL,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def row_to_entry(row) -> TimeLogEntry:
    return TimeLogEntry(
        id=row["id"],
        start=row["start"],
        duration=datetime.timedelta(seconds=row["duration_seconds"]),
        tags=row["tags"].split(","),
        description=row["description"],
        last_updated=row["last_updated"]
    )

def add_entry(entry: TimeLogEntry): 
    conn = get_db()
    conn.execute(
        "INSERT INTO time_logs (start, duration_seconds, tags, description) VALUES (?, ?, ?, ?)",
        (entry.start, entry.duration.total_seconds(), ",".join(entry.tags), entry.description)
    )
    conn.commit()
    conn.close()

def query_all_entries():
    conn = get_db()
    cursor = conn.execute("SELECT * FROM time_logs")
    results = [row_to_entry(row) for row in cursor.fetchall()]
    conn.close()
    return results

