import csv
import json
from pathlib import Path

import pytest

from axis.analysis import Ddx24ValidationPlanner


def _decisions(path: Path, decision: str) -> None:
    path.write_text(
        "gene_symbol\tdecision\ttherapeutic_direction\tstop_rule\n"
        f"DDX24\t{decision}\ttest_partial_restoration\tstop_on_harm\n",
        encoding="utf-8",
    )


def test_ddx24_plan_counts_donors_not_technical_replicates(tmp_path: Path) -> None:
    decisions = tmp_path / "decisions.tsv"
    _decisions(decisions, "experimental_only_not_drug_ready")

    result = Ddx24ValidationPlanner().build(
        decisions_path=decisions,
        output_root=tmp_path / "out",
    )

    with result.sample_sheet_path.open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source, delimiter="\t"))
    plan = json.loads(result.protocol_path.read_text(encoding="utf-8"))
    assert result.donors == 12
    assert result.experimental_units == 120
    assert len({row["donor_id"] for row in rows}) == 12
    assert plan["analysis"]["experimental_unit"] == "human_donor"
    assert plan["status"] == "planned_not_executed"


def test_ddx24_plan_rejects_unapproved_decision(tmp_path: Path) -> None:
    decisions = tmp_path / "decisions.tsv"
    _decisions(decisions, "deprioritised")

    with pytest.raises(ValueError, match="not currently approved"):
        Ddx24ValidationPlanner().build(
            decisions_path=decisions,
            output_root=tmp_path / "out",
        )
