from pathlib import Path

from axis.analysis import ValidationCohortSelector


def test_validation_selection_separates_bulk_reference_and_treated(
    tmp_path: Path,
) -> None:
    quarantine = tmp_path / "quarantine.tsv"
    evaluation = tmp_path / "evaluation.tsv"
    validation = tmp_path / "validation.tsv"
    participants = tmp_path / "participants.tsv"
    quarantine.write_text(
        "source\taccession\tdisease_signal\tassay\tsample_count\t"
        "bioproject_id\ttitle\tsource_uri\n"
        "GEO\tGSE1\taxspa_specific\tExpression profiling by array\t20\tP1\t"
        "Peripheral blood in ankylosing spondylitis\tu1\n"
        "GEO\tGSE2\taxspa_specific\tsingle-cell RNA-seq\t30\tP2\t"
        "PBMC atlas in ankylosing spondylitis\tu2\n"
        "GEO\tGSE3\taxspa_specific\tExpression profiling by array\t20\tP3\t"
        "Peripheral blood before and after treatment\tu3\n",
        encoding="utf-8",
    )
    evaluation.write_text(
        "accession\tsuggested_cases\tsuggested_controls\ttreated_cases\t"
        "different_disease_in_cases\n"
        "GSE1\t10\t10\t0\tFalse\n"
        "GSE3\t10\t10\t10\tFalse\n",
        encoding="utf-8",
    )
    validation.write_text("accession\tproposed_include\n", encoding="utf-8")
    participants.write_text(
        "accession\tankylosing_spondylitis_participants\t"
        "healthy_control_participants\n",
        encoding="utf-8",
    )

    result = ValidationCohortSelector().select(
        quarantine_path=quarantine,
        cohort_evaluation_path=evaluation,
        sample_validation_path=validation,
        participant_cohorts_path=participants,
        output_root=tmp_path / "out",
    )

    assert result.bulk_candidates == 1
    assert result.single_cell_candidates == 1
    assert result.priority_review == 2
