import numpy as np

from axis.analysis import moderated_two_group_test


def test_moderated_test_shrinks_feature_variances_and_detects_effect() -> None:
    case = np.asarray(
        (
            (10.0, 11.0, 9.0, 10.5),
            (5.0, 5.1, 4.9, 5.0),
            (2.0, 8.0, 3.0, 7.0),
        )
    )
    control = np.asarray(
        (
            (1.0, 2.0, 0.0, 1.5),
            (5.0, 5.1, 4.9, 5.0),
            (2.0, 7.0, 3.0, 8.0),
        )
    )

    result = moderated_two_group_test(case, control)

    assert result.residual_degrees_of_freedom == 6
    assert result.prior_degrees_of_freedom >= 0
    assert result.prior_variance > 0
    assert result.p_value.shape == (3,)
    assert result.p_value[0] < 0.05
    assert result.p_value[1] == 1.0
