from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

from axis.analysis.differential import DifferentialAnalyzer
from axis.analysis.empirical_bayes import moderated_linear_model


def _synthetic_values() -> tuple[np.ndarray, np.ndarray]:
    group = np.array([0, 0, 0, 0, 0, 1, 1, 1, 1, 1], dtype=float)
    sex = np.array([0, 1, 0, 1, 0, 1, 0, 1, 0, 1], dtype=float)
    age = np.array([22, 35, 41, 29, 50, 25, 38, 46, 33, 55], dtype=float)
    batch = np.array([1, 1, 2, 2, 3, 1, 2, 2, 3, 3], dtype=float)
    design = np.column_stack((np.ones(10), group, sex, age, batch))
    values = np.zeros((12, 10), dtype=float)
    for feature_index in range(12):
        feature = feature_index + 1
        for sample_index in range(10):
            sample = sample_index + 1
            group_effect = (-1) ** feature * (0.1 + feature * 0.03)
            sex_effect = ((feature % 3) - 1) * 0.05
            age_effect = 0.002 * (1 + feature % 2)
            batch_effect = 0.01 * ((feature % 4) - 1.5)
            residual = (
                ((feature * 7 + sample * 3) % 11) - 5
            ) * 0.015 * (1 + feature / 10)
            values[feature_index, sample_index] = (
                5
                + feature * 0.2
                + group[sample_index] * group_effect
                + sex[sample_index] * sex_effect
                + age[sample_index] * age_effect
                + batch[sample_index] * batch_effect
                + residual
            )
    return values, design


def test_moderated_model_matches_frozen_native_limma_reference() -> None:
    values, design = _synthetic_values()
    result = moderated_linear_model(
        values,
        design,
        np.array([0, 1, 0, 0, 0], dtype=float),
    )
    adjusted = DifferentialAnalyzer._benjamini_hochberg(result.p_value)
    fixture = Path(__file__).parent / "limma-regression-reference.tsv"
    with fixture.open(encoding="utf-8", newline="") as handle:
        expected = list(csv.DictReader(handle, delimiter="\t"))

    np.testing.assert_allclose(
        result.coefficient,
        [float(row["coefficient"]) for row in expected],
        rtol=1e-9,
        atol=1e-11,
    )
    expected_statistic = np.array(
        [float(row["statistic"]) for row in expected]
    )
    expected_adjusted = np.array(
        [float(row["adjusted_p_value"]) for row in expected]
    )
    assert spearmanr(result.statistic, expected_statistic).statistic > 0.999999
    assert spearmanr(adjusted, expected_adjusted).statistic > 0.999999
    np.testing.assert_array_equal(
        np.sign(result.statistic),
        np.sign(expected_statistic),
    )
    assert set(np.argsort(adjusted)[:5]) == set(
        np.argsort(expected_adjusted)[:5]
    )
    np.testing.assert_allclose(
        result.statistic,
        expected_statistic,
        rtol=0.06,
        atol=1e-10,
    )
