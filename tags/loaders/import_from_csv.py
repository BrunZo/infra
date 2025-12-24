"""
Import tags from CSV file to database with two-way sync.
"""
import argparse
from pathlib import Path

from tags.utils import tree
from tags import sync, db


def parse_args():
    p = argparse.ArgumentParser(description="Import tags from CSV to database with two-way sync")
    p.add_argument(
        "--db-path", dest="db_path",
        type=Path, required=True,
        help="The path to the database file",
    )
    p.add_argument(
        "--csv-file", dest="csv_file",
        type=Path, required=True,
        help="The CSV file to import from",
    )
    p.add_argument(
        "--delete-missing", dest="delete_missing",
        action="store_true",
        help="Delete tags from database that are not in CSV",
    )
    p.add_argument(
        "-n", "--dry-run", dest="dry_run",
        action="store_true",
        help="Don't modify database, just report what would happen",
    )
    return p.parse_args()


def main():
    args = parse_args()
    result = sync.import_from_csv(
        args.db_path,
        args.csv_file,
        delete_missing=args.delete_missing,
        dry_run=args.dry_run
    )
    
    print(f"\nSync results:")
    print(f"  Added: {result.added}")
    print(f"  Updated: {result.updated}")
    print(f"  Deleted: {result.deleted}")
    
    if result.errors:
        print(f"\nErrors ({len(result.errors)}):")
        for error in result.errors:
            print(f"  - {error}")
    else:
        print("\nNo errors!")


if __name__ == "__main__":
    main()

