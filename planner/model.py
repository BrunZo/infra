from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional


@dataclass
class Estimate:
    """
    What the planner needs to know about a tag, beyond the DAG itself.

    - weight: importance relative to siblings. A child's share of its parent
      is weight / sum of sibling weights (the `share` in prioritization).
    - effort_hours, shape: the progress curve, see curves.py. Leaves only.
    - spent_hours: already invested; the curve continues from there.
    - deadline: work counts only on days strictly before it. Inherited by
      every descendant.
    """
    name: str
    weight: float = 1.0
    effort_hours: Optional[float] = None
    shape: str = "linear"
    spent_hours: float = 0.0
    deadline: Optional[date] = None


@dataclass
class Leaf:
    name: str
    coefficient: float          # share of the target that this leaf is worth
    deadline: date              # effective: min over itself, ancestors, horizon
    shape: str
    effort_hours: float
    spent_hours: float


@dataclass
class Allocation:
    name: str
    hours: float
    coefficient: float
    deadline: date
    progress_before: float      # leaf progress, [0, 1]
    progress_after: float
    gain: float                 # target progress contributed by the new hours


@dataclass
class Plan:
    target: str
    horizon: date
    capacity_hours: float
    allocations: List[Allocation]
    schedule: Dict[date, List[tuple]]      # day -> [(leaf, hours)]
    progress_before: float                 # target progress, [0, 1]
    progress_after: float
    marginal_return: float                 # target progress per hour of the last slot bought
    solver: str
    unestimated: List[str] = field(default_factory=list)

    @property
    def planned_hours(self) -> float:
        return sum(a.hours for a in self.allocations)
