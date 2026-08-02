"""Safe, resumable planning for local SRA bulk RNA-seq reprocessing."""

from __future__ import annotations

import csv
import json
import os
import re
import shutil
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

SAFE_ID = re.compile(r"^[A-Za-z0-9_.-]+$")


@dataclass(frozen=True)
class SraWorkflowSample:
    run: str
    biosample: str
    sample_name: str
    group: str


@dataclass(frozen=True)
class SraReprocessingPlan:
    accession: str
    samples: int
    raw_download_gb: float
    estimated_working_gb: float
    free_disk_gb: float
    disk_ready: bool
    transcriptome_index: str
    reference_ready: bool
    required_tools: str
    missing_tools: str
    tools_ready: bool
    execution_status: str
    sample_sheet_path: Path
    script_path: Path
    manifest_path: Path


class SraReprocessingPlanner:
    """Prepare commands, but never start a large download implicitly."""

    TOOLS = ("prefetch", "fasterq-dump", "fastp", "salmon")

    def build(
        self,
        accession: str,
        runinfo_path: str | Path,
        audit_samples_path: str | Path,
        *,
        transcriptome_index: str | Path | None = None,
        output_root: str | Path = Path("data/raw-workflows"),
        threads: int | None = None,
        disk_multiplier: float = 4.5,
    ) -> SraReprocessingPlan:
        if not SAFE_ID.fullmatch(accession):
            raise ValueError(f"unsafe SRA accession: {accession}")
        if disk_multiplier < 3:
            raise ValueError("disk multiplier must be at least 3")
        runinfo = self._read_runinfo(Path(runinfo_path))
        groups = self._read_groups(Path(audit_samples_path))
        samples = self._samples(runinfo, groups)
        raw_gb = sum(float(row.get("size_MB", "") or 0) for row in runinfo) / 1024
        estimated_gb = raw_gb * disk_multiplier
        destination = Path(output_root) / accession
        destination.mkdir(parents=True, exist_ok=True)
        free_gb = shutil.disk_usage(destination).free / (1024**3)
        index = Path(transcriptome_index).resolve() if transcriptome_index else None
        reference_ready = bool(index and index.is_dir())
        missing = tuple(tool for tool in self.TOOLS if shutil.which(tool) is None)
        tools_ready = not missing
        disk_ready = free_gb >= estimated_gb
        status = (
            "ready_for_explicit_execution"
            if disk_ready and reference_ready and tools_ready
            else "blocked_by_preflight"
        )
        sample_sheet_path = destination / "samples.tsv"
        self._write_samples(sample_sheet_path, samples)
        script_path = destination / "run-workflow.ps1"
        script_path.write_text(
            self._script(
                samples,
                index,
                threads or max(1, min(8, os.cpu_count() or 1)),
            ),
            encoding="utf-8",
        )
        manifest_path = destination / "workflow-plan.json"
        plan = SraReprocessingPlan(
            accession=accession,
            samples=len(samples),
            raw_download_gb=round(raw_gb, 3),
            estimated_working_gb=round(estimated_gb, 3),
            free_disk_gb=round(free_gb, 3),
            disk_ready=disk_ready,
            transcriptome_index=str(index or ""),
            reference_ready=reference_ready,
            required_tools="; ".join(self.TOOLS),
            missing_tools="; ".join(missing),
            tools_ready=tools_ready,
            execution_status=status,
            sample_sheet_path=sample_sheet_path,
            script_path=script_path,
            manifest_path=manifest_path,
        )
        manifest_path.write_text(
            json.dumps(
                {
                    **asdict(plan),
                    "sample_sheet_path": str(sample_sheet_path),
                    "script_path": str(script_path),
                    "manifest_path": str(manifest_path),
                    "created_at": datetime.now(UTC).isoformat(),
                    "method": (
                        "SRA Toolkit retrieval, paired FASTQ extraction, fastp "
                        "quality trimming and Salmon transcript quantification."
                    ),
                    "execution_guard": (
                        "This command only creates a plan. The generated script "
                        "must be launched explicitly after every preflight gate "
                        "is satisfied."
                    ),
                    "scientific_scope": (
                        "Salmon quantification is not differential expression. "
                        "Gene-level aggregation, QC and a declared case-control "
                        "model remain required."
                    ),
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return plan

    @staticmethod
    def _read_runinfo(path: Path) -> list[dict[str, str]]:
        with path.open(encoding="utf-8", newline="") as source:
            rows = list(csv.DictReader(source))
        if not rows:
            raise ValueError("SRA runinfo is empty")
        return rows

    @staticmethod
    def _read_groups(path: Path) -> dict[str, str]:
        with path.open(encoding="utf-8", newline="") as source:
            rows = list(csv.DictReader(source, delimiter="\t"))
        groups = {
            row["biosample"]: row["group"]
            for row in rows
            if row.get("biosample") and row.get("group")
        }
        if not groups:
            raise ValueError("audited SRA sample groups are empty")
        return groups

    @staticmethod
    def _samples(
        runinfo: list[dict[str, str]], groups: dict[str, str]
    ) -> tuple[SraWorkflowSample, ...]:
        samples: list[SraWorkflowSample] = []
        for row in runinfo:
            run = row.get("Run", "").strip()
            biosample = row.get("BioSample", "").strip()
            sample_name = row.get("SampleName", "").strip()
            identifiers = (run, biosample, sample_name)
            if not all(SAFE_ID.fullmatch(value) for value in identifiers):
                raise ValueError("runinfo contains unsafe or missing identifiers")
            group = groups.get(biosample, "")
            if group not in {"case", "control"}:
                raise ValueError(f"unresolved group for BioSample {biosample}")
            samples.append(SraWorkflowSample(run, biosample, sample_name, group))
        if len({sample.run for sample in samples}) != len(samples):
            raise ValueError("runinfo contains duplicate runs")
        return tuple(samples)

    @staticmethod
    def _write_samples(
        path: Path, samples: tuple[SraWorkflowSample, ...]
    ) -> None:
        fields = list(SraWorkflowSample.__dataclass_fields__)
        with path.open("w", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=fields, delimiter="\t")
            writer.writeheader()
            writer.writerows(asdict(sample) for sample in samples)

    @staticmethod
    def _script(
        samples: tuple[SraWorkflowSample, ...],
        index: Path | None,
        threads: int,
    ) -> str:
        index_text = str(index or "REPLACE_WITH_SALMON_INDEX").replace("'", "''")
        runs = ", ".join(f"'{sample.run}'" for sample in samples)
        names = "; ".join(
            f"'{sample.run}' = '{sample.sample_name}'" for sample in samples
        )
        return f"""# Generated by AXIS; review workflow-plan.json before running.
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Sra = Join-Path $Root 'sra'
$Fastq = Join-Path $Root 'fastq'
$Trimmed = Join-Path $Root 'trimmed'
$Quant = Join-Path $Root 'salmon'
$Temp = Join-Path $Root 'temp'
$Index = '{index_text}'
$Threads = {threads}
$Runs = @({runs})
$SampleNames = @{{{names}}}

New-Item -ItemType Directory -Force -Path $Sra,$Fastq,$Trimmed,$Quant,$Temp | Out-Null
foreach ($Run in $Runs) {{
    $QuantDone = Join-Path (Join-Path $Quant $SampleNames[$Run]) 'quant.sf'
    if (Test-Path $QuantDone) {{
        Write-Host "Skipping completed $Run"
        continue
    }}
    prefetch $Run --output-directory $Sra
    fasterq-dump (Join-Path (Join-Path $Sra $Run) "$Run.sra") `
        --split-files --threads $Threads --outdir $Fastq --temp $Temp
    fastp -i (Join-Path $Fastq "$Run`_1.fastq") `
        -I (Join-Path $Fastq "$Run`_2.fastq") `
        -o (Join-Path $Trimmed "$Run`_1.fastq.gz") `
        -O (Join-Path $Trimmed "$Run`_2.fastq.gz") `
        --thread $Threads --json (Join-Path $Trimmed "$Run.fastp.json") `
        --html (Join-Path $Trimmed "$Run.fastp.html")
    salmon quant -i $Index -l A `
        -1 (Join-Path $Trimmed "$Run`_1.fastq.gz") `
        -2 (Join-Path $Trimmed "$Run`_2.fastq.gz") `
        -p $Threads --validateMappings `
        -o (Join-Path $Quant $SampleNames[$Run])
}}
Write-Host 'Quantification complete. Run AXIS QC before differential analysis.'
"""
