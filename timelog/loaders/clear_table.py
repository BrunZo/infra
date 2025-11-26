import argparse
from pathlib import Path

from .. import db

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--db-path", dest="db_path", 
        type=Path, required=True,
        help="The path to the database file",
    )
    return p.parse_args()

def main():
    args = parse_args()
    confirmation = input(f"Are you sure you want to clear all entries in {args.db_path}? (y/n) ")
    if confirmation == "y":
        db.clear_all_entries(args.db_path)
        print("All entries cleared")
    else:
        print("Aborted")

if __name__ == "__main__":
    main()