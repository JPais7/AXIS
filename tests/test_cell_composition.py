import numpy as np

from axis.analysis import CellCompositionDiagnostic


def test_composition_adjustment_uses_group_as_target_coefficient() -> None:
    group = np.asarray([0.0] * 8 + [1.0] * 8)
    composition = np.column_stack(
        (
            np.linspace(-1.0, 1.0, 16),
            np.asarray([0.0, 1.0] * 8),
            np.linspace(1.0, -1.0, 16) ** 2,
        )
    )
    outcome = 2.0 + 0.5 * group + 0.2 * composition[:, 0]

    result = CellCompositionDiagnostic._fit(
        outcome,
        group,
        composition,
    )

    assert abs(float(result["effect"]) - 0.5) < 1e-10
    assert int(result["degrees"]) == 11
