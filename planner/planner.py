"""
planner(tags, target, deadline) -> Plan

Assigns time to the leaves under `target` so the target gets as much return
as possible before `deadline`, then spreads that time out day by day.
"""
from datetime import date, timedelta
from typing import Dict, List, Sequence

from planner import dag, solve
from planner.model import Allocation, Estimate, Plan


def daily_slots(start: date, horizon: date, hours_per_day: Sequence[float], slot_hours: float) -> Dict[date, int]:
    """
    hours_per_day: one number for every day, or seven (Monday first).
    The horizon is exclusive: the last working day is the one before it.
    """
    if len(hours_per_day) not in (1, 7):
        raise ValueError("hours_per_day takes one value or seven (Mon..Sun)")
    slots = {}
    day = start
    while day < horizon:
        hours = hours_per_day[0] if len(hours_per_day) == 1 else hours_per_day[day.weekday()]
        slots[day] = int(hours / slot_hours + 1e-9)
        day += timedelta(days=1)
    return slots


def plan(
    children: dag.Children,
    target: str,
    estimates: Dict[str, Estimate],
    start: date,
    horizon: date,
    hours_per_day: Sequence[float],
    slot_minutes: int = 30,
) -> Plan:
    slot_hours = slot_minutes / 60
    leaves, unestimated = dag.flatten(children, target, estimates)
    days = daily_slots(start, horizon, hours_per_day, slot_hours)
    slots, marginal = solve.greedy(leaves, sum(days.values()), slot_hours)

    allocations = []
    for leaf in sorted(leaves, key=lambda l: (-slots[l.name], l.name)):
        gain = solve.gain_function(leaf, slot_hours)
        k = slots[leaf.name]
        allocations.append(Allocation(
            name=leaf.name,
            hours=k * slot_hours,
            coefficient=leaf.coefficient,
            gain=gain(k),
            next_hour=(gain(k + 1) - gain(k)) / slot_hours,
        ))

    return Plan(
        target=target,
        horizon=horizon,
        capacity_hours=sum(days.values()) * slot_hours,
        allocations=allocations,
        schedule=schedule(slots, days, slot_hours),
        marginal_return=marginal,
        unestimated=unestimated,
    )


def schedule(slots: Dict[str, int], days: Dict[date, int], slot_hours: float) -> Dict[date, List[tuple]]:
    """
    Nothing finishes, so nothing is urgent: spread each leaf evenly over
    the horizon. The k-th of a leaf's n slots goes at position (k + 1/2) / n;
    sorting all slots by position interleaves the leaves, then the sequence
    is cut into days by capacity.
    """
    sequence = sorted(
        ((k + 0.5) / n, name)
        for name, n in slots.items()
        for k in range(n)
    )
    names = iter(name for _, name in sequence)
    plan = {}
    for day in sorted(days):
        today = {}
        for _ in range(days[day]):
            name = next(names, None)
            if name is None:
                break
            today[name] = today.get(name, 0) + slot_hours
        if today:
            plan[day] = sorted(today.items(), key=lambda item: (-item[1], item[0]))
    return plan
