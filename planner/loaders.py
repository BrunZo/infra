"""
Inputs for the planner: the DAG (tags db or tags CSV) and the estimates CSV.

Estimates CSV, one row per tag, blanks mean default:

    name,weight,halving_hours,shape,spent_hours
    topology,2,,,
    topology_p1,,20,log,12
    piano_repertoire,1,30,saturating,
"""
import csv
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable

from planner.dag import Children
from planner.model import Estimate


def children_from_tags_db(db_path: Path) -> Children:
    from tags import db
    with db.transaction(db_path, dry_run=True) as conn:
        tags = db.get_all_tags(conn)
    id_to_name = {t.id: t.name for t in tags}
    return _children((t.name, [id_to_name[a] for a in t.direct_ancestors]) for t in tags)


def children_from_tags_csv(csv_path: Path) -> Children:
    """Same format as tags/loaders/export_to_csv: id, name, direct_ancestors."""
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return _children((r["name"].strip(), r.get("direct_ancestors", "").split()) for r in rows)


def _children(pairs: Iterable) -> Children:
    children = defaultdict(list)
    for name, parents in pairs:
        children.setdefault(name, [])
        for parent in parents:
            children[parent].append(name)
    return dict(children)


def estimates_from_csv(csv_path: Path, known: Iterable[str]) -> Dict[str, Estimate]:
    known = set(known)
    estimates = {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            row = {k: (v or "").strip() for k, v in row.items()}
            name = row["name"]
            if name not in known:
                raise ValueError(f"Estimate for unknown tag '{name}'")
            estimates[name] = Estimate(
                name=name,
                weight=float(row["weight"]) if row.get("weight") else 1.0,
                halving_hours=float(row["halving_hours"]) if row.get("halving_hours") else None,
                shape=row.get("shape") or "log",
                spent_hours=float(row["spent_hours"]) if row.get("spent_hours") else 0.0,
            )
    return estimates
