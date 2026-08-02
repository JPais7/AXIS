import csv
import json
from pathlib import Path

from axis.analysis import SraReprocessingPlanner


def test_sra_reprocessing_plan_is_guarded_and_resumable(tmp_path: Path) -> None:
    runinfo = tmp_path / "runinfo.csv"
    runinfo.write_text(
        "Run,BioSample,SampleName,size_MB,bases\n"
        "SRR1,SAM1,AF_1,1024,1000\n"
        "SRR2,SAM2,CF_1,1024,1000\n",
        encoding="utf-8",
    )
    samples = tmp_path / "audited.tsv"
    with samples.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(
            target,
            fieldnames=("biosample", "group"),
            delimiter="\t",
        )
        writer.writeheader()
        writer.writerows(
            (
                {"biosample": "SAM1", "group": "case"},
                {"biosample": "SAM2", "group": "control"},
            )
        )

    result = SraReprocessingPlanner().build(
        "SRP1", runinfo, samples, output_root=tmp_path / "workflow"
    )

    assert result.raw_download_gb == 2
    assert result.estimated_working_gb == 9
    assert result.execution_status == "blocked_by_preflight"
    script = result.script_path.read_text(encoding="utf-8")
    assert "Skipping completed" in script
    assert "prefetch $Run" in script
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert "only creates a plan" in manifest["execution_guard"]
