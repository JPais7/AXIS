"""Docking orchestration. AXIS captures what an engine did; it does not simulate one.

If no engine or preparation toolchain is available the method is recorded as
``not_executed`` and no pose or score is ever fabricated.
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

ENGINE_ENV = "AXIS_DOCKING_ENGINE"
KNOWN = {"AutoDock Vina": "vina"}
METHOD_STATES = ("method_available", "method_unavailable")
VALIDATION_STATES = ("validation_established", "validation_not_established")
EXECUTION_STATES = (
    "execution_not_attempted",
    "execution_attempted",
    "execution_failed",
)
RESULT_STATES = ("no_result", "result_available", "result_invalid")
BOUNDARIES = (
    "a docking score is not a binding affinity",
    "a predicted pose is not an observed binding mode",
    "favourable docking is not biochemical activity",
)


def find_engine() -> dict[str, Any]:
    override = os.environ.get(ENGINE_ENV)
    for name, executable in KNOWN.items():
        path = override or shutil.which(executable)
        if path and Path(path).is_file():
            version = subprocess.run(  # noqa: S603
                [path, "--version"],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            return {
                "available": True,
                "engine": name,
                "path": path,
                "version": (version.stdout or version.stderr).strip().splitlines()[0:1],
            }
    return {"available": False, "engine": None, "path": None, "version": []}


def parse_vina_poses(output: str) -> list[dict[str, Any]]:
    """Read ``REMARK VINA RESULT`` lines; anything unparseable is not a pose."""
    poses: list[dict[str, Any]] = []
    for line in output.splitlines():
        if line.startswith("REMARK VINA RESULT:"):
            parts = line.split(":", 1)[1].split()
            if len(parts) >= 3:
                try:
                    poses.append(
                        {
                            "rank": len(poses) + 1,
                            "score_kcal_mol": float(parts[0]),
                            "rmsd_lb": float(parts[1]),
                            "rmsd_ub": float(parts[2]),
                        }
                    )
                except ValueError:
                    return []
    return poses


def classify(run: dict[str, Any]) -> dict[str, str]:
    """Map an engine run to the explicit execution/result states."""
    if run["status"] == "completed" and run["poses"]:
        return {"execution": "execution_attempted", "result": "result_available"}
    if run["status"] == "failed" and run.get("exit_code", 1) == 0:
        return {"execution": "execution_attempted", "result": "result_invalid"}
    return {"execution": "execution_failed", "result": "no_result"}


def run_engine(argv: list[str], *, timeout: int, workdir: Path) -> dict[str, Any]:
    """Run an argument array (never a shell string); partial output is not success."""
    try:
        done = subprocess.run(  # noqa: S603
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=workdir,
            shell=False,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"status": "failed", "failure": f"timeout after {timeout}s", "poses": []}
    except OSError as error:
        return {"status": "failed", "failure": str(error), "poses": []}
    poses = parse_vina_poses(done.stdout + done.stderr)
    ok = done.returncode == 0 and bool(poses)
    return {
        "status": "completed" if ok else "failed",
        "exit_code": done.returncode,
        "stdout_tail": done.stdout[-500:],
        "stderr_tail": done.stderr[-500:],
        "poses": poses if ok else [],
        "failure": None if ok else "non-zero exit or no parseable pose",
    }


def docking_plan(site: dict[str, Any], receptor_validated: bool) -> dict[str, Any]:
    """What docking could support here, and whether it can run at all."""
    engine = find_engine()
    reasons = []
    if not engine["available"]:
        reasons.append("no docking engine installed (AutoDock Vina not found)")
    reasons.append("no PDBQT preparation toolchain is part of AXIS dependencies")
    if not receptor_validated:
        reasons.append("docking method validation not established for this target/site")
    if site.get("centre_component") == "ZN":
        reasons.append(
            "metal coordination is not represented by a standard scoring function"
        )
    return {
        "status": "not_executed",
        "states": {
            "method": "method_available"
            if engine["available"]
            else "method_unavailable",
            "validation": "validation_established"
            if receptor_validated
            else "validation_not_established",
            "execution": "execution_not_attempted",
            "result": "no_result",
        },
        "engine": engine,
        "reasons": reasons,
        "boundaries": list(BOUNDARIES),
        "validation": "Docking method validation not established for this target/site.",
    }
