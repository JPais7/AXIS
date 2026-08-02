"""Validate candidates against published supplementary differential tables."""

from __future__ import annotations

import csv
import json
import posixpath
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree

NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "p": "http://schemas.openxmlformats.org/package/2006/relationships",
}


@dataclass(frozen=True)
class PublishedReplicationRun:
    candidates: int
    supported: int
    conflicts: int
    output_path: Path
    evidence_path: Path
    summary_path: Path


class PublishedSupplementValidator:
    """Use author-published DE tables when primary matrices are unavailable."""

    def validate(
        self,
        workbook_path: str | Path,
        candidate_path: str | Path,
        *,
        sheet_name: str = "AS vs HC",
        alpha: float = 0.05,
        output_root: str | Path = Path(
            "data/single-cell/independent-replication/published-validation"
        ),
    ) -> PublishedReplicationRun:
        workbook = Path(workbook_path)
        candidates = self._candidates(Path(candidate_path))
        table = self._sheet_rows(workbook, sheet_name)
        genes = set(candidates)
        evidence = [
            self._evidence(row, candidates[row["gene"]])
            for row in table
            if row.get("gene") in genes
        ]
        summaries = [
            self._summary(gene, direction, evidence, alpha=alpha)
            for gene, direction in candidates.items()
        ]
        destination = Path(output_root)
        destination.mkdir(parents=True, exist_ok=True)
        output_path = destination / "published-candidate-validation.tsv"
        evidence_path = destination / "published-matched-rows.tsv"
        summary_path = destination / "published-validation.json"
        self._write(output_path, summaries)
        self._write(evidence_path, evidence)
        supported = sum(
            row["validation_status"] == "published_directional_support"
            for row in summaries
        )
        conflicts = sum(
            row["validation_status"] == "published_directional_conflict"
            for row in summaries
        )
        summary_path.write_text(
            json.dumps(
                {
                    "analysis_role": "published_supplementary_replication",
                    "created_at": datetime.now(UTC).isoformat(),
                    "publication": "PMC11926545",
                    "source_workbook": str(workbook),
                    "source_sheet": sheet_name,
                    "candidates": len(summaries),
                    "directionally_supported": supported,
                    "directional_conflicts": conflicts,
                    "alpha": alpha,
                    "method": (
                        "Candidate directions are compared with author-published "
                        "AS-versus-HC avg_log2FC rows. Significant agreement or "
                        "conflict requires the published adjusted p-value <= alpha."
                    ),
                    "scope": (
                        "Independent publication-level validation only; not an "
                        "independent reanalysis of subject-level raw counts."
                    ),
                    "warning": (
                        "The published table was generated with cell-level Seurat "
                        "testing. It may be affected by pseudoreplication and does "
                        "not replace donor-level pseudobulk validation. A gene "
                        "missing from the table is inconclusive, not absent."
                    ),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return PublishedReplicationRun(
            candidates=len(summaries),
            supported=supported,
            conflicts=conflicts,
            output_path=output_path,
            evidence_path=evidence_path,
            summary_path=summary_path,
        )

    @staticmethod
    def _candidates(path: Path) -> dict[str, str]:
        with path.open(encoding="utf-8", newline="") as source:
            return {
                row["gene_symbol"].strip().upper(): row["single_cell_direction"]
                for row in csv.DictReader(source, delimiter="\t")
                if row.get("decision") == "generate_causal_evidence"
            }

    @staticmethod
    def _evidence(row: dict[str, str], expected: str) -> dict[str, object]:
        effect = float(row["avg_log2FC"])
        observed = "higher_in_case" if effect > 0 else "lower_in_case"
        return {
            "gene_symbol": row["gene"],
            "major_cell_type": row.get("Major Cell Type", ""),
            "cell_subtype": row.get("pheno", ""),
            "comparison_label": row.get("cluster", ""),
            "avg_log2fc": effect,
            "p_value": float(row["p_val"]),
            "adjusted_p_value": float(row["p_val_adj"]),
            "published_direction": observed,
            "axis_expected_direction": expected,
            "direction_agrees": observed == expected,
        }

    @staticmethod
    def _summary(
        gene: str,
        direction: str,
        evidence: list[dict[str, object]],
        *,
        alpha: float,
    ) -> dict[str, object]:
        matches = [row for row in evidence if row["gene_symbol"] == gene]
        significant = [
            row for row in matches if float(str(row["adjusted_p_value"])) <= alpha
        ]
        agreeing = [row for row in significant if row["direction_agrees"]]
        conflicting = [row for row in significant if not row["direction_agrees"]]
        if agreeing and not conflicting:
            status = "published_directional_support"
        elif conflicting:
            status = "published_directional_conflict"
        elif matches:
            status = "reported_but_not_significant"
        else:
            status = "not_reported_in_published_de_table"
        best = min(
            matches,
            key=lambda row: float(str(row["adjusted_p_value"])),
            default={},
        )
        return {
            "gene_symbol": gene,
            "axis_expected_direction": direction,
            "published_rows": len(matches),
            "published_significant_rows": len(significant),
            "significant_agreeing_rows": len(agreeing),
            "significant_conflicting_rows": len(conflicting),
            "best_published_adjusted_p_value": best.get("adjusted_p_value", ""),
            "best_published_cell_subtype": best.get("cell_subtype", ""),
            "best_published_direction": best.get("published_direction", ""),
            "validation_status": status,
        }

    @staticmethod
    def _sheet_rows(path: Path, sheet_name: str) -> list[dict[str, str]]:
        with zipfile.ZipFile(path) as archive:
            shared = PublishedSupplementValidator._shared_strings(archive)
            workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
            relationships = ElementTree.fromstring(
                archive.read("xl/_rels/workbook.xml.rels")
            )
            targets = {
                item.attrib["Id"]: item.attrib["Target"]
                for item in relationships.findall("p:Relationship", NS)
            }
            sheet_path = ""
            for sheet in workbook.findall("m:sheets/m:sheet", NS):
                if sheet.attrib["name"] == sheet_name:
                    relationship = sheet.attrib[f"{{{NS['r']}}}id"]
                    sheet_path = posixpath.normpath(
                        posixpath.join("xl", targets[relationship])
                    )
                    break
            if not sheet_path:
                raise ValueError(f"sheet not found: {sheet_name}")
            root = ElementTree.fromstring(archive.read(sheet_path))
            rows = [
                PublishedSupplementValidator._xlsx_row(row, shared)
                for row in root.findall("m:sheetData/m:row", NS)
            ]
        if len(rows) < 3:
            return []
        headers = rows[1]
        return [
            {
                headers[index]: value
                for index, value in enumerate(row)
                if index < len(headers) and headers[index]
            }
            for row in rows[2:]
        ]

    @staticmethod
    def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
        if "xl/sharedStrings.xml" not in archive.namelist():
            return []
        root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
        return [
            "".join(node.text or "" for node in item.findall(".//m:t", NS))
            for item in root.findall("m:si", NS)
        ]

    @staticmethod
    def _xlsx_row(row: ElementTree.Element, shared: list[str]) -> list[str]:
        values: dict[int, str] = {}
        for cell in row.findall("m:c", NS):
            reference = cell.attrib.get("r", "A1")
            letters = "".join(
                character for character in reference if character.isalpha()
            )
            column = 0
            for character in letters:
                column = column * 26 + ord(character.upper()) - ord("A") + 1
            value = cell.findtext("m:v", default="", namespaces=NS)
            if cell.attrib.get("t") == "s" and value:
                value = shared[int(value)]
            elif cell.attrib.get("t") == "inlineStr":
                value = "".join(node.text or "" for node in cell.findall(".//m:t", NS))
            values[column - 1] = value
        width = max(values, default=-1) + 1
        return [values.get(index, "") for index in range(width)]

    @staticmethod
    def _write(path: Path, rows: list[dict[str, object]]) -> None:
        fields = tuple(rows[0]) if rows else ("gene_symbol",)
        with path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(
                output, fieldnames=fields, delimiter="\t", lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows(rows)
