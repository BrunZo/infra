import argparse
from pathlib import Path
from .. import db, tag

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--db-path", dest="db_path", 
        type=Path, required=True,
        help="The path to the database file",
    )
    return p.parse_args()

def test_add_tags(db_path: Path):
    db.add_tag(db_path, tag.Tag(id=1, name="Tag1", direct_ancestors=[]))
    db.add_tag(db_path, tag.Tag(id=2, name="Tag2", direct_ancestors=[1]))
    db.add_tag(db_path, tag.Tag(id=3, name="Tag3", direct_ancestors=[1]))
    db.add_tag(db_path, tag.Tag(id=4, name="Tag4", direct_ancestors=[2, 3]))

def main():
    args = parse_args()
    db.init_db(args.db_path)
    test_add_tags(args.db_path)

if __name__ == "__main__":
    main()