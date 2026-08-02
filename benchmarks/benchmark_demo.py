"""Compatibility entry point for the public AXIS benchmark command."""

from __future__ import annotations

import argparse
from pathlib import Path

from axis.analysis.benchmark import DemoBenchmarker


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repetitions", type=int, default=10)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--workspace", type=Path, default=Path("."))
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("benchmark-output"),
    )
    arguments = parser.parse_args()
    result = DemoBenchmarker().run(
        repetitions=arguments.repetitions,
        warmups=arguments.warmups,
        workspace=arguments.workspace,
        output_root=arguments.output_root,
    )
    print(result.report_path)
    print(result.runs_path)


if __name__ == "__main__":
    main()
