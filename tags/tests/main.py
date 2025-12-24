import argparse
from pathlib import Path
from .. import db
from ..utils import tree

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
    with db.transaction(args.db_path, dry_run=False) as conn:
        db.init_db(conn)
        tree.show_tree(conn, 1)

if __name__ == "__main__":
    main()