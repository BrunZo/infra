CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS tag_relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_tag_id INTEGER NOT NULL,
    child_tag_id INTEGER NOT NULL,
    path_length INTEGER NOT NULL,
    FOREIGN KEY (parent_tag_id) REFERENCES tags(id),
    FOREIGN KEY (child_tag_id) REFERENCES tags(id)
);