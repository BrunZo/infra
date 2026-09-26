"""
planner(tags, target, deadline) -> Plan

Assigns time to the leaves under `target` so the target gains as much
progress as possible before `deadline`, then lays that time out day by day.
"""
from datetime import date, timedelta
from typing import Dict, List, Sequence

from planner import dag, solve
from planner.curves import make_curve
from planner.model import Allocation, Estimate, Leaf, Plan


def build_capacity(start: date, horizon: date, hours_per_day: Sequence[float], slot_minutes: int) -> solve.Capacity:
    """
    hours_per_day: one number for every day, or seven (Monday first).
    The horizon is exclusive: the last working day is the one before it.
    """
    if len(hours_per_day) not in (1, 7):
        raise ValueError("hours_per_day takes one value or seven (Mon..Sun)")
    slot_hours = slot_minutes / 60
    slots = {}
    day = start
    while day < horizon:
        hours = hours_per_day[0] if len(hours_per_day) == 1 else hours_per_day[day.weekday()]
        slots[day] = int(hours / slot_hours + 1e-9)
        day += timedelta(days=1)
    return solve.Capacity(slots=slots, slot_hours=slot_hours)


def plan(
    children: dag.Children,
    target: str,
    estimates: Dict[str, Estimate],
    start: date,
    horizon: date,
    hours_per_day: Sequence[float],
    slot_minutes: int = 30,
) -> Plan:
    leaves, unestimated = dag.flatten(children, target, estimates, horizon)
    capacity = build_capacity(start, horizon, hours_per_day, slot_minutes)
    slots, marginal, solver = solve.solve(leaves, capacity)

    allocations = []
    for leaf in sorted(leaves, key=lambda l: (-slots[l.name], l.name)):
        hours = slots[leaf.name] * capacity.slot_hours
        curve = make_curve(leaf.shape, leaf.effort_hours)
        before, after = curve(leaf.spent_hours), curve(leaf.spent_hours + hours)
        allocations.append(Allocation(
            name=leaf.name,
            hours=hours,
            coefficient=leaf.coefficient,
            deadline=leaf.deadline,
            progress_before=before,
            progress_after=after,
            gain=leaf.coefficient * (after - before),
        ))

    progress_before = sum(a.coefficient * a.progress_before for a in allocations)
    return Plan(
        target=target,
        horizon=horizon,
        capacity_hours=capacity.total * capacity.slot_hours,
        allocations=allocations,
        schedule=schedule(leaves, slots, capacity),
        progress_before=progress_before,
        progress_after=progress_before + sum(a.gain for a in allocations),
        marginal_return=marginal,
        solver=solver,
        unestimated=unestimated,
    )


def schedule(leaves: List[Leaf], slots: Dict[str, int], capacity: solve.Capacity) -> Dict[date, List[tuple]]:
    """
    Earliest deadline first. The solver kept every deadline's prefix within
    capacity, so this never leaves a leaf's slots after its deadline.
    """
    remaining = dict(slots)
    order = sorted(leaves, key=lambda l: (l.deadline, -l.coefficient, l.name))
    days = {}
    for day in sorted(capacity.slots):
        free = capacity.slots[day]
        today = []
        for leaf in order:
            if free == 0:
                break
            n = min(free, remaining[leaf.name])
            if n == 0:
                continue
            assert leaf.deadline > day, f"{leaf.name} scheduled on {day}, due {leaf.deadline}"
            remaining[leaf.name] -= n
            free -= n
            today.append((leaf.name, n * capacity.slot_hours))
        if today:
            days[day] = today
    return days
