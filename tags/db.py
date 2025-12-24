from pathlib import Path
import sqlite3
from typing import List

from tags.tag import Tag
from tags.validation import validate_tag


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


# -- Adding --

def add_tag(db_path: Path, tag: Tag):
    """
    Add a tag to the database with validation.
    
    Args:
        db_path: Path to the database
        tag: Tag to add (should not have an ID set for new tags)
        existing_tag_ids: Set of tag IDs that will exist after batch import (for validation)
    
    Raises:
        ValueError: If validation fails
    """
    errors = validate_tag(db_path, tag)
    if errors:
        error_msg = "Validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
        raise ValueError(error_msg)
    
    conn = get_db(db_path)

    cursor = conn.execute("INSERT INTO tags (name) VALUES (?)", (tag.name,))
    tag_id = cursor.lastrowid
    for ancestor_id in tag.direct_ancestors:
        assert tag_exists(db_path, ancestor_id), f"Ancestor tag {ancestor_id} not found"
        conn.execute("INSERT INTO tag_relationships (parent_tag_id, child_tag_id, path_length) VALUES (?, ?, ?)", (ancestor_id, tag_id, 1))
    
    conn.commit()
    conn.close()
    return tag_id

def update_tag(db_path: Path, tag: Tag):
    """
    Update an existing tag in the database with validation.
    
    Args:
        db_path: Path to the database
        tag: Tag to update (must have an ID set)
        existing_tag_ids: Set of tag IDs that will exist after batch import (for validation)
    
    Raises:
        ValueError: If validation fails or tag ID is not set
    """
    errors = validate_tag(db_path, tag)
    if errors:
        error_msg = "Validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
        raise ValueError(error_msg)
    
    conn = get_db(db_path)
    conn.execute("UPDATE tags SET name = ? WHERE id = ?", (tag.name, tag.id))
    conn.execute("DELETE FROM tag_relationships WHERE child_tag_id = ?", (tag.id,))

    for ancestor_id in tag.direct_ancestors:
        assert tag_exists(db_path, ancestor_id), f"Ancestor tag {ancestor_id} not found"
        conn.execute(
            "INSERT INTO tag_relationships (parent_tag_id, child_tag_id, path_length) VALUES (?, ?, ?)",
            (ancestor_id, tag.id, 1)
        )
    
    conn.commit()
    conn.close()

def delete_tag(db_path: Path, tag_id: int):
    conn = get_db(db_path)
    conn.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
    conn.execute("DELETE FROM tag_relationships WHERE parent_tag_id = ? OR child_tag_id = ?", (tag_id, tag_id))
    conn.commit()
    conn.close()

# -- Getting --

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

def tag_exists(db_path: Path, id: int) -> bool:
    conn = get_db(db_path)
    cursor = conn.execute("SELECT * FROM tags WHERE id = ?", (id,))
    row = cursor.fetchone()
    conn.close()
    return row is not None

def get_tag_by_name(db_path: Path, name: str) -> Tag:
    conn = get_db(db_path)
    cursor = conn.execute("SELECT * FROM tags WHERE name = ?", (name,))
    row = cursor.fetchone()
    conn.close()
    if row is None:
        return None
    direct_ancestors = get_direct_ancestors_ids(db_path, row['id'])
    return Tag(id=row['id'], name=row['name'], direct_ancestors=direct_ancestors)

def get_all_tags(db_path: Path) -> List[Tag]:
    conn = get_db(db_path)
    cursor = conn.execute("SELECT * FROM tags")
    rows = cursor.fetchall()
    conn.close()
    return [Tag(id=row['id'], name=row['name'], direct_ancestors=get_direct_ancestors_ids(db_path, row['id'])) for row in rows]
