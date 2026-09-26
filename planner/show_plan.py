import argparse
from datetime import date
from pathlib import Path

from planner import loaders, planner
from planner.model import Plan


def parse_args():
    p = argparse.ArgumentParser(description="Assign time under a target tag to maximize its return")
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--tags-db", dest="tags_db", type=Path, help="The tags database")
    source.add_argument("--tags-csv", dest="tags_csv", type=Path, help="A tags CSV, as exported by tags.loaders.export_to_csv")
    p.add_argument("--estimates", type=Path, required=True, help="Estimates CSV, see planner/loaders.py")
    p.add_argument("--target", required=True, help="The tag to plan for")
    p.add_argument("--deadline", type=date.fromisoformat, required=True, help="Horizon, exclusive (YYYY-MM-DD)")
    p.add_argument("--start", type=date.fromisoformat, default=date.today(), help="First day to plan (default: today)")
    p.add_argument(
        "--hours-per-day", dest="hours_per_day", default="2",
        help="Hours available per day: one number, or seven comma-separated (Mon..Sun)",
    )
    p.add_argument("--slot-minutes", dest="slot_minutes", type=int, default=30)
    return p.parse_args()


def show(plan: Plan):
    print(f"target: {plan.target}   horizon: {plan.horizon}")
    print(f"hours: {plan.planned_hours:g} planned of {plan.capacity_hours:g} available")
    if plan.planned_hours:
        print(f"return: {plan.gain:.2f} fresh hours ({plan.gain / plan.planned_hours:.0%} per hour on average,"
              f" {plan.marginal_return:.0%} for the last hour)")
    print()
    print(f"{'leaf':<28}{'hours':>7}{'share':>8}{'gain':>8}{'next hour':>11}")
    for a in plan.allocations:
        print(f"{a.name:<28}{a.hours:>7g}{a.coefficient:>8.1%}{a.gain:>8.2f}{a.next_hour:>11.1%}")
    if plan.unestimated:
        print(f"\nunestimated (no halving_hours, got no time): {', '.join(plan.unestimated)}")
    print()
    for day, items in plan.schedule.items():
        print(f"{day} {day:%a}  " + ", ".join(f"{name} {hours:g}h" for name, hours in items))


def main():
    args = parse_args()
    if args.tags_db:
        children = loaders.children_from_tags_db(args.tags_db)
    else:
        children = loaders.children_from_tags_csv(args.tags_csv)
    if args.target not in children:
        raise SystemExit(f"Unknown target '{args.target}'")
    estimates = loaders.estimates_from_csv(args.estimates, children.keys())
    hours_per_day = [float(h) for h in args.hours_per_day.split(",")]
    show(planner.plan(children, args.target, estimates, args.start, args.deadline, hours_per_day, args.slot_minutes))


if __name__ == "__main__":
    main()
