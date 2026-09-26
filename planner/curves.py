"""
Progress curves: how much of a leaf is achieved after investing some hours.

Every curve maps total hours invested (including hours already spent) to a
progress fraction in [0, 1]. `effort` is the one parameter, in hours, and its
meaning depends on the shape:

| shape        | progress(t)            | effort means                  | use for                        |
|--------------|------------------------|-------------------------------|--------------------------------|
| linear       | min(1, t / effort)     | hours to finish               | finalizable, partial credit    |
| step         | 1 if t >= effort else 0| hours to finish               | finalizable, all-or-nothing    |
| diminishing  | 1 - 2^(-t / effort)    | hours to get halfway          | non-finalizable (learn piano)  |
"""
import math
from typing import Callable, Dict

Curve = Callable[[float], float]


def linear(effort: float) -> Curve:
    return lambda t: min(1.0, t / effort)


def step(effort: float) -> Curve:
    return lambda t: 1.0 if t >= effort - 1e-9 else 0.0


def diminishing(effort: float) -> Curve:
    return lambda t: 1.0 - math.pow(2.0, -t / effort)


SHAPES: Dict[str, Callable[[float], Curve]] = {
    "linear": linear,
    "step": step,
    "diminishing": diminishing,
}

# Shapes whose marginal return never increases. The greedy solver is exact
# for these; anything else needs the DP.
CONCAVE_SHAPES = {"linear", "diminishing"}


def make_curve(shape: str, effort: float) -> Curve:
    if shape not in SHAPES:
        raise ValueError(f"Unknown shape '{shape}', expected one of {sorted(SHAPES)}")
    if effort <= 0:
        raise ValueError(f"effort must be positive, got {effort}")
    return SHAPES[shape](effort)


def saturation_hours(shape: str, effort: float) -> float:
    """Hours after which more time adds no progress (inf if never)."""
    return math.inf if shape == "diminishing" else effort
