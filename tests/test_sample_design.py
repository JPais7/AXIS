import csv
from pathlib import Path

import numpy as np
import pytest

from axis.analysis import (
    SampleDesignBuilder,
    moderated_linear_model,
    write_sample_sheet_template,
)
from axis.ingestion import GeoApiError


def write_sheet(path: Path, rows: tuple[tuple[str, ...], ...]) -> None:
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output, delimiter="\t", lineterminator="\n")
        writer.writerow(("sample_id", "group", "sex", "age", "subject"))
        writer.writerows(rows)


def test_design_aligns_samples_and_encodes_numeric_and_categorical(
    tmp_path: Path,
) -> None:
    path = tmp_path / "samples.tsv"
    write_sheet(
        path,
        (
            ("S2", "control", "F", "42", "P2"),
            ("S1", "case", "M", "40", "P1"),
            ("S4", "control", "M", "44", "P4"),
            ("S3", "case", "F", "46", "P3"),
            ("S5", "case", "M", "50", "P5"),
            ("S6", "control", "F", "48", "P6"),
        ),
    )

    design = SampleDesignBuilder().build(
        path,
        sample_ids=("S1", "S2", "S3", "S4", "S5", "S6"),
        covariates=("sex", "age"),
    )

    assert design.columns == ("intercept", "group_case", "sex[M]", "age")
    assert design.matrix.shape == (6, 4)
    assert tuple(design.matrix[:, 1]) == (1.0, 0.0, 1.0, 0.0, 1.0, 0.0)
    assert tuple(design.contrast) == (0.0, 1.0, 0.0, 0.0)


def test_design_rejects_matrix_sample_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "samples.tsv"
    write_sheet(
        path,
        (
            ("S1", "case", "M", "40", "P1"),
            ("S2", "control", "F", "42", "P2"),
        ),
    )

    with pytest.raises(GeoApiError, match="does not match"):
        SampleDesignBuilder().build(
            path,
            sample_ids=("S1", "S3"),
        )


def test_template_populates_published_geo_covariates(tmp_path: Path) -> None:
    groups = tmp_path / "sample-groups.tsv"
    with groups.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output, delimiter="\t", lineterminator="\n")
        writer.writerow(("accession", "group", "title", "source", "characteristics"))
        writer.writerow(
            (
                "GSM1",
                "case",
                "case",
                "blood",
                "gender: Male | age (yr): 39 | set: 1",
            )
        )
        writer.writerow(("GSM2", "control", "control", "blood", "sex: F | batch: B"))
        writer.writerow(("GSM3", "excluded", "other", "blood", "age: 50"))

    destination = write_sample_sheet_template(
        groups,
        tmp_path / "design.tsv",
    )
    with destination.open(encoding="utf-8", newline="") as source:
        rows = tuple(csv.DictReader(source, delimiter="\t"))

    assert len(rows) == 2
    assert rows[0]["sex"] == "Male"
    assert rows[0]["age"] == "39"
    assert rows[0]["batch"] == "1"
    assert rows[1]["sex"] == "F"
    assert rows[1]["batch"] == "B"


def test_template_recovers_chip_batch_from_title(tmp_path: Path) -> None:
    groups = tmp_path / "sample-groups.tsv"
    groups.write_text(
        "accession\tgroup\ttitle\tsource\tcharacteristics\n"
        "GSM1\tcase\tAS [9963831033_D]\tblood\tsex: Male | age: 39\n"
        "GSM2\tcontrol\tHC [9963831033_C]\tblood\tsex: Female | age: 40\n",
        encoding="utf-8",
    )
    destination = write_sample_sheet_template(groups, tmp_path / "design.tsv")
    with destination.open(encoding="utf-8", newline="") as source:
        rows = tuple(csv.DictReader(source, delimiter="\t"))
    assert rows[0]["batch"] == "9963831033"
    assert rows[1]["batch"] == "9963831033"


def test_moderated_linear_model_estimates_adjusted_group_contrast() -> None:
    design = np.asarray(
        (
            (1.0, 1.0, 0.0),
            (1.0, 1.0, 1.0),
            (1.0, 1.0, 0.0),
            (1.0, 0.0, 1.0),
            (1.0, 0.0, 0.0),
            (1.0, 0.0, 1.0),
        )
    )
    values = np.asarray(
        (
            (10.0, 12.0, 10.5, 3.0, 1.0, 2.5),
            (5.0, 6.0, 5.0, 6.0, 5.0, 6.0),
            (2.0, 8.0, 3.0, 7.0, 2.0, 8.0),
        )
    )

    result = moderated_linear_model(
        values,
        design,
        np.asarray((0.0, 1.0, 0.0)),
    )

    assert result.design_rank == 3
    assert result.residual_degrees_of_freedom == 3
    assert result.coefficient[0] > 5
    assert result.p_value[0] < 0.05
