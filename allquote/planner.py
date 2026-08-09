"""Route planner. See PLAN.md Task 7.

Will read the registry and emit a RunPlan mapping each route to an executor or
a planning-time terminal status, backing the `make run` Makefile target. Not
implemented yet.
"""

import argparse
import sys


def run(route: str) -> None:
    raise NotImplementedError("Task 5/7 - planner.py run is not implemented yet")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m allquote.planner")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--route", required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            run(args.route)
    except NotImplementedError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
