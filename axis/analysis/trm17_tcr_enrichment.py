"""Participant-aware TRBV enrichment analysis for Oxford-study TRM17 cells."""

from __future__ import annotations

import csv
import gzip
import json
import math
import re
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO, cast

from scipy import stats  # type: ignore[import-untyped]


@dataclass(frozen=True)
class Trm17TcrEnrichmentRun:
    status: str
    cells: int
    participants: int
    segment_path: Path
    participant_path: Path
    causal_path: Path
    summary_path: Path


class Trm17TcrEnrichmentAnalyzer:
    """Test TRBV enrichment without treating cells as independent patients."""

    barcode_aliases = ("cell_barcode", "barcode", "CellName")
    participant_aliases = ("participant", "cart_patient_id", "Subject", "donor")
    state_aliases = ("is_trm17", "trm17", "cell_state", "annotation")
    v_gene_aliases = ("v_gene", "TRBV", "v_call", "V_gene")

    def analyze(
        self,
        metadata_path: str | Path,
        *,
        repertoire_path: str | Path | None = None,
        output_root: str | Path = "data/single-cell/GSE290921/trm17-tcr-enrichment",
    ) -> Trm17TcrEnrichmentRun:
        metadata, metadata_fields = self._read(Path(metadata_path))
        destination = Path(output_root)
        destination.mkdir(parents=True, exist_ok=True)
        segment_path = destination / "trbv-enrichment.tsv"
        participant_path = destination / "participant-trbv-effects.tsv"
        causal_path = destination / "causal-evidence.tsv"
        summary_path = destination / "analysis-status.json"

        barcode_column = self._column(metadata_fields, self.barcode_aliases)
        participant_column = self._column(metadata_fields, self.participant_aliases)
        state_column = self._column(metadata_fields, self.state_aliases)
        missing = []
        if barcode_column is None:
            missing.append("cell barcode in expression metadata")
        if participant_column is None:
            missing.append("participant identifier in expression metadata")
        if state_column is None:
            missing.append("validated per-cell TRM17 annotation")

        repertoire: list[dict[str, str]] = []
        repertoire_fields: tuple[str, ...] = ()
        if repertoire_path is None or not Path(repertoire_path).exists():
            missing.append("paired single-cell TCR repertoire table")
        else:
            repertoire, repertoire_fields = self._read(Path(repertoire_path))
        repertoire_barcode = self._column(repertoire_fields, self.barcode_aliases)
        v_gene_column = self._column(repertoire_fields, self.v_gene_aliases)
        if repertoire and repertoire_barcode is None:
            missing.append("cell barcode in TCR repertoire")
        if repertoire and v_gene_column is None:
            missing.append("TRBV/V-gene call in TCR repertoire")

        status = "not_identifiable" if missing else "complete"
        diagnoses = Counter(
            row.get("diagnosis", "unspecified") or "unspecified" for row in metadata
        )
        tissues = Counter(
            row.get("tissue", "unspecified") or "unspecified" for row in metadata
        )
        segment_rows: list[dict[str, object]] = []
        participant_rows: list[dict[str, object]] = []
        matched: list[dict[str, str]] = []
        if not missing:
            # The missing-field audit above establishes these keys. Casts only
            # express that contract to the type checker; they do not alter data.
            metadata_barcode = cast(str, barcode_column)
            tcr_barcode = cast(str, repertoire_barcode)
            v_gene_key = cast(str, v_gene_column)
            participant_key = cast(str, participant_column)
            state_key = cast(str, state_column)
            by_barcode = {row[metadata_barcode]: row for row in metadata}
            for tcr in repertoire:
                expression = by_barcode.get(tcr[tcr_barcode])
                if expression is None:
                    continue
                v_gene = self._trbv(tcr[v_gene_key])
                if not v_gene:
                    continue
                matched.append(
                    {
                        "participant": expression[participant_key],
                        "is_trm17": str(self._is_trm17(expression[state_key])),
                        "trbv": v_gene,
                    }
                )
            segment_rows, participant_rows = self._enrichment(matched)
            if not matched:
                status = "no_matched_tcr_cells"

        self._write(segment_path, segment_rows, self._segment_fields())
        self._write(
            participant_path,
            participant_rows,
            ("participant", "trbv", "trm17_fraction", "other_t_fraction", "difference"),
        )
        causal_rows = self._causal_rows(status, bool(segment_rows))
        self._write(
            causal_path,
            causal_rows,
            ("criterion", "available", "interpretation"),
        )
        participants = len({row["participant"] for row in matched})
        summary_path.write_text(
            json.dumps(
                {
                    "created_at": datetime.now(UTC).isoformat(),
                    "accession": "GSE290921",
                    "question": (
                        "Are Oxford-study TRM17 cells enriched for TRBV9 or other "
                        "TRBV segments, and is there evidence of causal maintenance?"
                    ),
                    "status": status,
                    "missing_requirements": missing,
                    "metadata_cells": len(metadata),
                    "observed_diagnoses": dict(diagnoses),
                    "observed_tissues": dict(tissues),
                    "matched_tcr_cells": len(matched),
                    "participants": participants,
                    "statistical_unit": "participant",
                    "guardrails": [
                        (
                            "TRBV cannot be inferred reliably from the deposited "
                            "gene-expression matrix."
                        ),
                        (
                            "Cell-level Fisher tests are descriptive; participant "
                            "effects are primary."
                        ),
                        (
                            "Enrichment or clonality alone does not establish "
                            "causal maintenance."
                        ),
                        (
                            "Causality requires longitudinal depletion or "
                            "functional perturbation evidence."
                        ),
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return Trm17TcrEnrichmentRun(
            status=status,
            cells=len(matched),
            participants=participants,
            segment_path=segment_path,
            participant_path=participant_path,
            causal_path=causal_path,
            summary_path=summary_path,
        )

    @staticmethod
    def _open(path: Path) -> TextIO:
        if path.suffix == ".gz":
            return gzip.open(path, "rt", encoding="utf-8", newline="")
        return path.open(encoding="utf-8", newline="")

    @classmethod
    def _read(cls, path: Path) -> tuple[list[dict[str, str]], tuple[str, ...]]:
        with cls._open(path) as source:
            reader = csv.DictReader(source, delimiter="\t")
            rows = [dict(row) for row in reader]
            return rows, tuple(reader.fieldnames or ())

    @staticmethod
    def _column(fields: tuple[str, ...], aliases: tuple[str, ...]) -> str | None:
        lowered = {field.lower(): field for field in fields}
        return next(
            (lowered[name.lower()] for name in aliases if name.lower() in lowered), None
        )

    @staticmethod
    def _is_trm17(value: str) -> bool:
        return value.strip().lower() in {
            "1",
            "true",
            "yes",
            "trm17",
            "cd4 trm17",
        } or bool(re.search(r"\btrm\s*17\b", value, flags=re.IGNORECASE))

    @staticmethod
    def _trbv(value: str) -> str:
        match = re.search(r"TRBV\d+(?:-\d+)?", value.upper())
        return match.group(0) if match else ""

    @classmethod
    def _enrichment(
        cls, cells: list[dict[str, str]]
    ) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        segments = sorted({row["trbv"] for row in cells})
        totals = Counter(row["is_trm17"] for row in cells)
        counts = Counter((row["is_trm17"], row["trbv"]) for row in cells)
        per_participant: dict[tuple[str, str, str], int] = defaultdict(int)
        participant_totals: Counter[tuple[str, str]] = Counter()
        for row in cells:
            key = (row["participant"], row["is_trm17"])
            participant_totals[key] += 1
            per_participant[(row["participant"], row["is_trm17"], row["trbv"])] += 1

        segment_rows: list[dict[str, object]] = []
        participant_rows: list[dict[str, object]] = []
        p_values: list[float] = []
        participants = sorted({row["participant"] for row in cells})
        for segment in segments:
            a = counts[("True", segment)]
            b = totals["True"] - a
            c = counts[("False", segment)]
            d = totals["False"] - c
            odds, p_value = stats.fisher_exact([[a, b], [c, d]])
            differences = []
            for participant in participants:
                trm_total = participant_totals[(participant, "True")]
                other_total = participant_totals[(participant, "False")]
                if not trm_total or not other_total:
                    continue
                trm_fraction = (
                    per_participant[(participant, "True", segment)] / trm_total
                )
                other_fraction = (
                    per_participant[(participant, "False", segment)] / other_total
                )
                difference = trm_fraction - other_fraction
                differences.append(difference)
                participant_rows.append(
                    {
                        "participant": participant,
                        "trbv": segment,
                        "trm17_fraction": trm_fraction,
                        "other_t_fraction": other_fraction,
                        "difference": difference,
                    }
                )
            paired_p = math.nan
            if len(differences) >= 3 and any(value != 0 for value in differences):
                paired_p = float(stats.wilcoxon(differences).pvalue)
            p_values.append(float(p_value))
            segment_rows.append(
                {
                    "trbv": segment,
                    "trm17_cells": a,
                    "other_t_cells": c,
                    "trm17_fraction": a / totals["True"]
                    if totals["True"]
                    else math.nan,
                    "other_t_fraction": c / totals["False"]
                    if totals["False"]
                    else math.nan,
                    "odds_ratio_descriptive": float(odds),
                    "fisher_p_descriptive": float(p_value),
                    "fisher_fdr_descriptive": math.nan,
                    "participants_with_both_states": len(differences),
                    "median_participant_difference": (
                        float(stats.scoreatpercentile(differences, 50))
                        if differences
                        else math.nan
                    ),
                    "wilcoxon_p_participant": paired_p,
                }
            )
        adjusted = cls._bh(p_values)
        for segment_row, value in zip(segment_rows, adjusted, strict=True):
            segment_row["fisher_fdr_descriptive"] = value
        return segment_rows, participant_rows

    @staticmethod
    def _bh(values: list[float]) -> list[float]:
        order = sorted(range(len(values)), key=values.__getitem__)
        adjusted = [1.0] * len(values)
        running = 1.0
        for rank_index in range(len(order) - 1, -1, -1):
            index = order[rank_index]
            rank = rank_index + 1
            running = min(running, values[index] * len(values) / rank)
            adjusted[index] = min(1.0, running)
        return adjusted

    @staticmethod
    def _segment_fields() -> tuple[str, ...]:
        return (
            "trbv",
            "trm17_cells",
            "other_t_cells",
            "trm17_fraction",
            "other_t_fraction",
            "odds_ratio_descriptive",
            "fisher_p_descriptive",
            "fisher_fdr_descriptive",
            "participants_with_both_states",
            "median_participant_difference",
            "wilcoxon_p_participant",
        )

    @staticmethod
    def _causal_rows(status: str, has_enrichment: bool) -> list[dict[str, str]]:
        return [
            {
                "criterion": "TRBV enrichment",
                "available": str(has_enrichment),
                "interpretation": "association only",
            },
            {
                "criterion": "clonal expansion",
                "available": "False",
                "interpretation": "requires paired CDR3 alpha/beta clonotypes",
            },
            {
                "criterion": "tissue persistence",
                "available": "False",
                "interpretation": "requires paired tissue/blood or longitudinal TCR",
            },
            {
                "criterion": "selective intervention",
                "available": "False",
                "interpretation": (
                    "requires pre/post anti-TRBV9 or equivalent perturbation"
                ),
            },
            {
                "criterion": "causal conclusion",
                "available": "False",
                "interpretation": "not established"
                if status != "complete"
                else "not established by enrichment alone",
            },
        ]

    @staticmethod
    def _write(
        path: Path, rows: Sequence[Mapping[str, object]], fields: tuple[str, ...]
    ) -> None:
        with path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=fields, delimiter="\t")
            writer.writeheader()
            writer.writerows(rows)
