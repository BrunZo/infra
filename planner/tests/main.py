"""
python -m planner.tests.main
"""
import itertools
import math
import random
import tempfile
from datetime import date, timedelta
from pathlib import Path

from planner import dag, loaders, planner, solve
from planner.curves import make_curve
from planner.model import Estimate, Leaf

D0 = date(2026, 10, 1)
EXAMPLES = Path(__file__).parent.parent / "examples"


def value(leaves, slots, slot_hours):
    return sum(solve.gain_function(leaf, slot_hours)(slots[leaf.name]) for leaf in leaves)


def brute_force(leaves, total, slot_hours):
    best = 0.0
    for combo in itertools.product(range(total + 1), repeat=len(leaves)):
        if sum(combo) <= total:
            best = max(best, value(leaves, dict(zip((l.name for l in leaves), combo)), slot_hours))
    return best


def test_greedy_is_optimal():
    rng = random.Random(0)
    for _ in range(200):
        leaves = [
            Leaf(
                name=f"l{i}",
                coefficient=rng.random(),
                shape=rng.choice(["log", "saturating"]),
                halving_hours=rng.choice([0.5, 1, 2, 5]),
                spent_hours=rng.choice([0, 0, 1, 10]),
            )
            for i in range(rng.randint(1, 3))
        ]
        total = rng.randint(0, 8)
        slots, _ = solve.greedy(leaves, total, 0.5)
        assert sum(slots.values()) == total
        assert math.isclose(value(leaves, slots, 0.5), brute_force(leaves, total, 0.5), abs_tol=1e-9)


def test_curves_are_scaled_to_fresh_hours():
    for shape in ("log", "saturating"):
        curve = make_curve(shape, 4)
        slope = lambda t: (curve(t + 1e-6) - curve(t)) / 1e-6
        assert math.isclose(slope(0), 1, rel_tol=1e-4)
        assert math.isclose(slope(4), 0.5, rel_tol=1e-4)     # halving hours: worth half
        assert slope(1000) > 0 or shape == "saturating"      # log never stops paying


def test_every_hour_is_used():
    # Nothing finishes, so no amount of time is too much for any leaf.
    children = {"t": ["a"], "a": []}
    p = planner.plan(children, "t", {"a": Estimate("a", halving_hours=1)}, D0, D0 + timedelta(days=30), [8])
    assert p.planned_hours == 240


def test_neglected_leaf_is_fed_first():
    children = {"t": ["a", "b"], "a": [], "b": []}
    estimates = {"a": Estimate("a", halving_hours=5, spent_hours=50), "b": Estimate("b", halving_hours=5)}
    p = planner.plan(children, "t", estimates, D0, D0 + timedelta(days=5), [2])
    hours = {a.name: a.hours for a in p.allocations}
    assert hours["b"] > hours["a"]


def test_coefficients_follow_shares_and_paths():
    children = {"t": ["a", "b"], "a": ["x", "y"], "b": ["y"], "x": [], "y": []}
    estimates = {n: Estimate(n, halving_hours=1) for n in "xy"}
    estimates["a"] = Estimate("a", weight=3)
    leaves, _ = dag.flatten(children, "t", estimates)
    coefficient = {l.name: l.coefficient for l in leaves}
    # a is 3/4 of t, b is 1/4; y serves both a (half of it) and b (all of it).
    assert math.isclose(coefficient["x"], 0.75 * 0.5)
    assert math.isclose(coefficient["y"], 0.75 * 0.5 + 0.25)
    assert math.isclose(sum(coefficient.values()), 1.0)


def test_schedule_interleaves_and_respects_capacity():
    children = loaders.children_from_tags_csv(EXAMPLES / "tags.csv")
    estimates = loaders.estimates_from_csv(EXAMPLES / "estimates.csv", children)
    p = planner.plan(children, "MAT", estimates, D0, date(2026, 11, 1), [1, 1, 1, 1, 1, 4, 4])
    per_leaf = {}
    for day, items in p.schedule.items():
        assert sum(h for _, h in items) == (4 if day.weekday() >= 5 else 1)
        for name, h in items:
            per_leaf[name] = per_leaf.get(name, 0) + h
    assert per_leaf == {a.name: a.hours for a in p.allocations if a.hours}
    # Every leaf shows up in the first and the last week, not in one block.
    days = sorted(p.schedule)
    for week in (days[:7], days[-7:]):
        seen = {name for day in week for name, _ in p.schedule[day]}
        assert seen == set(per_leaf)
    assert p.unestimated == []


def test_tags_db_loader():
    from tags import db
    from tags.tag import Tag
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "tags.db"
        with db.transaction(path) as conn:
            db.init_db(conn)
            root = db.add_tag(conn, Tag(name="MAT", direct_ancestors=[]))
            db.add_tag(conn, Tag(name="topology", direct_ancestors=[root]))
        assert loaders.children_from_tags_db(path) == {"MAT": ["topology"], "topology": []}


def all_tests():
    tests = [(n, f) for n, f in globals().items() if n.startswith("test_")]
    for name, test in tests:
        test()
        print(f"ok  {name}")


if __name__ == "__main__":
    all_tests()
