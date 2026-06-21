"""Run the local deterministic demo and write JSON/CSV reports."""

from __future__ import annotations

import argparse
from pathlib import Path

from agent_ab.reporting import run_local_demo


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--output-root", type=Path, default=Path("demo_output"))
    args = parser.parse_args()
    summary = run_local_demo(args.project_root, args.output_root)
    print(f"run={summary.run_id}")
    print(f"json_report={summary.json_report}")
    print(f"csv_report={summary.csv_report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
