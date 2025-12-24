from pathlib import Path
import sqlite3
from typing import List
from contextlib import contextmanager

from tags.tag import Tag
from tags.validation import validate_tag


@contextmanager
def transaction(db_path: Path, dry_run: bool = False):
    """
    Context manager for database transactions.
    
    If dry_run is True, all changes are rolled back at the end.
    Otherwise, changes are committed.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        if not dry_run:
            conn.commit()
        else:
            conn.rollback()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# -- Schema --

def init_db(conn: sqlite3.Connection):
    schema_path = Path(__file__).parent / "schema.sql"
    schema_sql = open(schema_path).read()
    conn.executescript(schema_sql)


# -- Adding --

def add_tag(conn: sqlite3.Connection, tag: Tag):
    """
    Add a tag to the database with validation.
    
    Args:
        conn: Database connection to use
        tag: Tag to add (should not have an ID set for new tags)
    
    Returns:
        tag_id (int) on success, or list of error strings on validation failure
    """
    errors = validate_tag(conn, tag)
    if errors:
        return errors
    
    cursor = conn.execute("INSERT INTO tags (name) VALUES (?)", (tag.name,))
    tag_id = cursor.lastrowid
    for ancestor_id in tag.direct_ancestors:
        conn.execute("INSERT INTO tag_relationships (parent_tag_id, child_tag_id, path_length) VALUES (?, ?, ?)", (ancestor_id, tag_id, 1))
    return tag_id

def update_tag(conn: sqlite3.Connection, tag: Tag):
    """
    Update an existing tag in the database with validation.
    
    Args:
        conn: Database connection to use
        tag: Tag to update (must have an ID set)
    
    Returns:
        None on success, or list of error strings on validation failure
    """
    errors = validate_tag(conn, tag)
    if errors:
        return errors
    
    conn.execute("UPDATE tags SET name = ? WHERE id = ?", (tag.name, tag.id))
    conn.execute("DELETE FROM tag_relationships WHERE child_tag_id = ?", (tag.id,))
    for ancestor_id in tag.direct_ancestors:
        conn.execute(
            "INSERT INTO tag_relationships (parent_tag_id, child_tag_id, path_length) VALUES (?, ?, ?)",
            (ancestor_id, tag.id, 1)
        )

def delete_tag(conn: sqlite3.Connection, tag_id: int):
    """
    Delete a tag from the database.
    
    Args:
        conn: Database connection to use
        tag_id: ID of the tag to delete
    """
    conn.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
    conn.execute("DELETE FROM tag_relationships WHERE parent_tag_id = ? OR child_tag_id = ?", (tag_id, tag_id))


# -- Getting --

def get_direct_ancestors_ids(conn: sqlite3.Connection, tag_id: int) -> List[int]:
    cursor = conn.execute("SELECT * FROM tag_relationships WHERE child_tag_id = ? AND path_length = 1", (tag_id,))
    rows = cursor.fetchall()
    return [row['parent_tag_id'] for row in rows]

def get_direct_descendants_ids(conn: sqlite3.Connection, tag_id: int) -> List[int]:
    cursor = conn.execute("SELECT * FROM tag_relationships WHERE parent_tag_id = ? AND path_length = 1", (tag_id,))
    rows = cursor.fetchall()
    return [row['child_tag_id'] for row in rows]

def get_tag_by_id(conn: sqlite3.Connection, id: int) -> Tag:
    cursor = conn.execute("SELECT * FROM tags WHERE id = ?", (id,))
    row = cursor.fetchone()
    if row is None:
        return None
    return Tag(id=row['id'], name=row['name'], direct_ancestors=get_direct_ancestors_ids(conn, row['id']))

def tag_exists(conn: sqlite3.Connection, id: int) -> bool:
    cursor = conn.execute("SELECT * FROM tags WHERE id = ?", (id,))
    row = cursor.fetchone()
    return row is not None

def get_tag_by_name(conn: sqlite3.Connection, name: str) -> Tag:
    cursor = conn.execute("SELECT * FROM tags WHERE name = ?", (name,))
    row = cursor.fetchone()
    if row is None:
        return None
    direct_ancestors = get_direct_ancestors_ids(conn, row['id'])
    return Tag(id=row['id'], name=row['name'], direct_ancestors=direct_ancestors)

def get_all_tags(conn: sqlite3.Connection) -> List[Tag]:
    cursor = conn.execute("SELECT * FROM tags")
    rows = cursor.fetchall()
    return [Tag(id=row['id'], name=row['name'], direct_ancestors=get_direct_ancestors_ids(conn, row['id'])) for row in rows]
