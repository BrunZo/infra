"""
python -m planner.tests.main
"""
import itertools
import math
import random
import sqlite3
import tempfile
from datetime import date, timedelta
from pathlib import Path

from planner import dag, loaders, planner, solve
from planner.model import Estimate, Leaf

D0 = date(2026, 10, 1)


def value(leaves, slots, capacity):
    return sum(solve._gain(leaf, capacity)(slots[leaf.name]) for leaf in leaves)


def feasible(leaves, slots, capacity):
    return all(
        sum(slots[l.name] for l in leaves if l.deadline <= d) <= capacity.before(d)
        for d in {l.deadline for l in leaves}
    )


def brute_force(leaves, capacity):
    ranges = [range(solve._max_useful_slots(l, capacity) + 1) for l in leaves]
    best = 0.0
    for combo in itertools.product(*ranges):
        slots = {l.name: k for l, k in zip(leaves, combo)}
        if feasible(leaves, slots, capacity):
            best = max(best, value(leaves, slots, capacity))
    return best


def random_instance(rng, shapes):
    days = rng.randint(2, 4)
    capacity = planner.build_capacity(D0, D0 + timedelta(days=days), [rng.choice([1, 1.5, 2])], 30)
    leaves = [
        Leaf(
            name=f"l{i}",
            coefficient=rng.random(),
            deadline=D0 + timedelta(days=rng.randint(1, days)),
            shape=rng.choice(shapes),
            effort_hours=rng.choice([0.5, 1, 1.5, 2, 3]),
            spent_hours=rng.choice([0, 0, 0.5]),
        )
        for i in range(rng.randint(1, 4))
    ]
    return leaves, capacity


def test_greedy_is_optimal_for_concave():
    rng = random.Random(0)
    for _ in range(300):
        leaves, capacity = random_instance(rng, ["linear", "diminishing"])
        slots, _ = solve.greedy(leaves, capacity)
        assert feasible(leaves, slots, capacity)
        assert math.isclose(value(leaves, slots, capacity), brute_force(leaves, capacity), abs_tol=1e-9)


def test_dp_is_optimal_for_anything():
    rng = random.Random(1)
    for _ in range(300):
        leaves, capacity = random_instance(rng, ["linear", "step", "diminishing"])
        slots = solve.dp(leaves, capacity)
        assert feasible(leaves, slots, capacity)
        assert math.isclose(value(leaves, slots, capacity), brute_force(leaves, capacity), abs_tol=1e-9)


def test_coefficients_follow_shares_and_paths():
    children = {"t": ["a", "b"], "a": ["x", "y"], "b": ["y"], "x": [], "y": []}
    estimates = {n: Estimate(n, effort_hours=1) for n in "xy"}
    estimates["a"] = Estimate("a", weight=3)
    leaves, _ = dag.flatten(children, "t", estimates, D0)
    coefficient = {l.name: l.coefficient for l in leaves}
    # a is 3/4 of t, b is 1/4; y serves both a (half of it) and b (all of it).
    assert math.isclose(coefficient["x"], 0.75 * 0.5)
    assert math.isclose(coefficient["y"], 0.75 * 0.5 + 0.25)
    assert math.isclose(sum(coefficient.values()), 1.0)


def test_deadlines_are_inherited():
    children = {"t": ["a"], "a": ["x"], "x": []}
    estimates = {"a": Estimate("a", deadline=D0 + timedelta(days=2)), "x": Estimate("x", effort_hours=1)}
    leaves, _ = dag.flatten(children, "t", estimates, D0 + timedelta(days=9))
    assert leaves[0].deadline == D0 + timedelta(days=2)


def test_step_needs_the_whole_effort_before_the_deadline():
    # 2h/day for 2 days. The step task is worth more but needs 5h: impossible, so it gets nothing.
    children = {"t": ["big", "small"], "big": [], "small": []}
    estimates = {
        "big": Estimate("big", weight=10, effort_hours=5, shape="step"),
        "small": Estimate("small", effort_hours=2),
    }
    p = planner.plan(children, "t", estimates, D0, D0 + timedelta(days=2), [2])
    hours = {a.name: a.hours for a in p.allocations}
    assert p.solver == "dp"
    assert hours == {"big": 0, "small": 2}


def test_schedule_respects_deadlines_and_capacity():
    children = loaders.children_from_tags_csv(Path(__file__).parent.parent / "examples" / "tags.csv")
    estimates = loaders.estimates_from_csv(Path(__file__).parent.parent / "examples" / "estimates.csv", children)
    p = planner.plan(children, "MAT", estimates, D0, date(2026, 11, 1), [1, 1, 1, 1, 1, 4, 4])
    due = {a.name: a.deadline for a in p.allocations}
    per_leaf = {}
    for day, items in p.schedule.items():
        assert sum(h for _, h in items) <= (4 if day.weekday() >= 5 else 1)
        for name, h in items:
            assert day < due[name]
            per_leaf[name] = per_leaf.get(name, 0) + h
    assert per_leaf == {a.name: a.hours for a in p.allocations if a.hours}
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
