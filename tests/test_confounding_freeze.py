from axis.analysis import ConfoundingFreezeBuilder


def test_frozen_criteria_include_refutation_and_safety_gates() -> None:
    rows = ConfoundingFreezeBuilder._criteria()

    assert all(row["locked"] is True for row in rows)
    assert any(row["criterion"] == "primary_direction" for row in rows)
    assert any(row["criterion"] == "cell_fitness" for row in rows)
    assert all(row["refutation_or_stop"] for row in rows)
