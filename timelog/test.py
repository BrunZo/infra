from datetime import datetime, timedelta

from . import db

def test_add_entry():
    entry = db.TimeLogEntry(start=datetime.now(), duration=timedelta(hours=1), tags=["work", "programming"], description="Worked on project")
    db.add_entry(entry)

def test_query_all_entries():
    entries = db.query_all_entries()
    print(entries)

def all_tests():
    db.init_db()
    test_add_entry()
    test_query_all_entries()

if __name__ == "__main__":
    all_tests()