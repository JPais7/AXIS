from axis.analysis import PublicationReadinessBuilder


def test_publication_checklist_keeps_external_lab_requirements_open() -> None:
    rows = PublicationReadinessBuilder._checklist()
    status = {row["item"]: row["status"] for row in rows}

    assert status["computational_results_frozen"] == "complete"
    assert status["ethics_approval_for_new_samples"] == "external"
    assert status["validated_DDX24_primers"] == "external"
