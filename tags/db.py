from pathlib import Path
import sqlite3
from typing import List

from tags.tag import Tag

def get_db(db_path: Path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path: Path):
    conn = get_db(db_path)
    schema_path = Path(__file__).parent / "schema.sql"
    schema_sql = open(schema_path).read()
    conn.executescript(schema_sql)
    conn.commit()
    conn.close()

def add_tag(db_path: Path, tag: Tag):
    conn = get_db(db_path)

    for ancestor_id in tag.direct_ancestors:
        cursor = conn.execute("SELECT * FROM tags WHERE id = ?", (ancestor_id,))
        if cursor.fetchone() is None:
            raise ValueError(f"Ancestor tag {ancestor_id} not found")

    cursor = conn.execute("INSERT INTO tags (name) VALUES (?)", (tag.name,))
    tag_id = cursor.lastrowid
    for ancestor_id in tag.direct_ancestors:
        conn.execute("INSERT INTO tag_relationships (parent_tag_id, child_tag_id, path_length) VALUES (?, ?, ?)", (ancestor_id, tag_id, 1))
    
    conn.commit()
    conn.close()

def get_direct_ancestors_ids(db_path: Path, tag_id: int) -> List[int]:
    conn = get_db(db_path)
    cursor = conn.execute("SELECT * FROM tag_relationships WHERE child_tag_id = ? AND path_length = 1", (tag_id,))
    rows = cursor.fetchall()
    conn.close()
    return [row['parent_tag_id'] for row in rows]

def get_direct_descendants_ids(db_path: Path, tag_id: int) -> List[int]:
    conn = get_db(db_path)
    cursor = conn.execute("SELECT * FROM tag_relationships WHERE parent_tag_id = ? AND path_length = 1", (tag_id,))
    rows = cursor.fetchall()
    conn.close()
    return [row['child_tag_id'] for row in rows]

def get_tag_by_id(db_path: Path, id: int) -> Tag:
    conn = get_db(db_path)
    cursor = conn.execute("SELECT * FROM tags WHERE id = ?", (id,))
    row = cursor.fetchone()
    conn.close()
    if row is None:
        return None
    return Tag(id=row['id'], name=row['name'], direct_ancestors=get_direct_ancestors_ids(db_path, row['id']))

def get_tag_by_name(db_path: Path, name: str) -> Tag:
    conn = get_db(db_path)
    cursor = conn.execute("SELECT * FROM tags WHERE name = ?", (name,))
    row = cursor.fetchone()
    conn.close()
    if row is None:
        return None
    direct_ancestors = get_direct_ancestors_ids(db_path, row['id'])
    return Tag(id=row['id'], name=row['name'], direct_ancestors=direct_ancestors)
