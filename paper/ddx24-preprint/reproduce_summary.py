from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from statistics import NormalDist

ROOT = Path(__file__).resolve().parent


def pool(rows: list[dict[str, str]]) -> dict[str, float | int]:
    effects = [float(row["effect_log2_cpm"]) for row in rows]
    variances = [float(row["standard_error"]) ** 2 for row in rows]
    fixed_weights = [1.0 / value for value in variances]
    fixed = sum(w * e for w, e in zip(fixed_weights, effects, strict=True)) / sum(
        fixed_weights
    )
    q_value = sum(
        w * (effect - fixed) ** 2
        for w, effect in zip(fixed_weights, effects, strict=True)
    )
    degrees = len(rows) - 1
    c_value = sum(fixed_weights) - sum(w**2 for w in fixed_weights) / sum(
        fixed_weights
    )
    tau_squared = max(0.0, (q_value - degrees) / c_value)
    weights = [1.0 / (variance + tau_squared) for variance in variances]
    estimate = sum(w * e for w, e in zip(weights, effects, strict=True)) / sum(
        weights
    )
    standard_error = math.sqrt(1.0 / sum(weights))
    z_value = estimate / standard_error
    p_value = 2.0 * (1.0 - NormalDist().cdf(abs(z_value)))
    i_squared = (
        max(0.0, (q_value - degrees) / q_value) * 100.0
        if q_value > 0
        else 0.0
    )
    return {
        "cohorts": len(rows),
        "participants": sum(int(row["cases"]) + int(row["controls"]) for row in rows),
        "random_effect": estimate,
        "standard_error": standard_error,
        "ci_low": estimate - 1.96 * standard_error,
        "ci_high": estimate + 1.96 * standard_error,
        "p_value": p_value,
        "tau_squared": tau_squared,
        "i_squared_percent": i_squared,
    }


def main() -> None:
    with (ROOT / "cd8-effects.tsv").open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source, delimiter="\t"))
    primary = [row for row in rows if row["role"] != "broad_cd8_sensitivity_only"]
    result = {
        "method": "inverse-variance DerSimonian-Laird random effects",
        "effect_definition": "case minus control donor-pseudobulk log2-CPM",
        "primary": pool(primary),
        "broad_cd8_sensitivity": pool(rows),
        "guardrail": (
            "GSE163314 is sensitivity-only because its author-annotated CD8_T "
            "population is broader than the primary memory/effector definition."
        ),
    }
    output = ROOT / "reproduced-summary.json"
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
