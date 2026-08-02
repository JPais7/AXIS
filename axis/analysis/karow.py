"""Audit and use the published Karow axSpA monocyte signatures."""

from __future__ import annotations

import csv
import json
import posixpath
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

from axis.analysis.published_replication import NS, PublishedSupplementValidator


@dataclass(frozen=True)
class KarowAuditRun:
    cohort1_features: int
    cohort2_genes: int
    candidates: int
    supported_candidates: int
    conflicting_candidates: int
    signature_path: Path
    validation_path: Path
    audit_path: Path
    request_path: Path


class KarowSupplementAuditor:
    """Extract published signatures when participant-level matrices are absent."""

    SHEETS = (
        ("Cohort 1 (microarray)", "cohort_1", "microarray"),
        ("Cohort 2 (RNAseq)", "cohort_2", "rna_seq"),
    )

    def audit(
        self,
        workbook_path: str | Path,
        candidate_path: str | Path,
        *,
        output_root: str | Path = Path("data/analysis/karow"),
    ) -> KarowAuditRun:
        workbook = Path(workbook_path)
        signature: list[dict[str, str]] = []
        counts: dict[str, int] = {}
        for sheet, cohort, modality in self.SHEETS:
            rows = self._raw_rows(workbook, sheet)
            extracted = self._extract(rows, cohort, modality)
            signature.extend(extracted)
            counts[cohort] = len(
                {row["feature_id"] for row in extracted if row["feature_id"]}
            )
        candidates = self._candidates(Path(candidate_path))
        validation = [
            self._validate_candidate(gene, direction, signature)
            for gene, direction in candidates.items()
        ]
        destination = Path(output_root)
        destination.mkdir(parents=True, exist_ok=True)
        signature_path = destination / "published-signatures.tsv"
        validation_path = destination / "candidate-validation.tsv"
        self._write(signature_path, signature)
        self._write(validation_path, validation)
        supported = sum(
            row["status"] == "published_directional_support"
            for row in validation
        )
        conflicting = sum(
            row["status"] == "published_directional_conflict" for row in validation
        )
        audit_path = destination / "access-audit.json"
        audit_path.write_text(
            json.dumps(
                {
                    "publication": "PMC8461951",
                    "doi": "10.1186/s13075-021-02623-7",
                    "cohort_1": {
                        "participants": "25 axSpA + 10 healthy controls",
                        "modality": "Affymetrix GeneChip microarray",
                        "published_signature_rows": counts["cohort_1"],
                    },
                    "cohort_2": {
                        "participants": "32 axSpA + 22 healthy controls",
                        "modality": "CD14+ monocyte RNA-seq",
                        "published_signature_rows": counts["cohort_2"],
                    },
                    "primary_data_status": (
                        "participant-level matrices and repository accession "
                        "not identified"
                    ),
                    "available_now": (
                        "author-published directional differential lists only"
                    ),
                    "repository_search": [
                        "GEO",
                        "SRA",
                        "ENA",
                        "BioStudies",
                        "article and supplementary files",
                    ],
                    "scientific_scope": (
                        "publication-level directional validation; not an "
                        "independent reanalysis"
                    ),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        request_path = destination / "data-request.md"
        request_path.write_text(self._request_text(), encoding="utf-8")
        return KarowAuditRun(
            cohort1_features=counts["cohort_1"],
            cohort2_genes=counts["cohort_2"],
            candidates=len(validation),
            supported_candidates=supported,
            conflicting_candidates=conflicting,
            signature_path=signature_path,
            validation_path=validation_path,
            audit_path=audit_path,
            request_path=request_path,
        )

    @staticmethod
    def _extract(
        rows: list[list[str]], cohort: str, modality: str
    ) -> list[dict[str, str]]:
        output: list[dict[str, str]] = []
        header_index = next(
            (
                index
                for index, row in enumerate(rows)
                if "Affy-ID" in row or "Ensembl-ID" in row
            ),
            -1,
        )
        if header_index < 0:
            raise ValueError(f"signature header not found for {cohort}")
        header = rows[header_index]
        feature_indices = [
            index
            for index, value in enumerate(header)
            if value in {"Affy-ID", "Ensembl-ID"}
        ]
        if len(feature_indices) != 2:
            raise ValueError(f"two signature blocks not found for {cohort}")
        for row in rows[header_index + 1 :]:
            for direction, feature_index in zip(
                ("higher_in_case", "lower_in_case"),
                feature_indices,
                strict=True,
            ):
                gene_index = feature_index + 1
                feature = (
                    row[feature_index].strip()
                    if feature_index < len(row)
                    else ""
                )
                if not feature:
                    continue
                gene_text = (
                    row[gene_index].strip() if gene_index < len(row) else ""
                )
                genes = gene_text.split(" /// ") if gene_text else [""]
                for gene in genes:
                    output.append(
                        {
                            "cohort": cohort,
                            "modality": modality,
                            "direction": direction,
                            "feature_id": feature,
                            "gene_symbol": gene.strip().upper(),
                        }
                    )
        return output

    @staticmethod
    def _candidates(path: Path) -> dict[str, str]:
        with path.open(encoding="utf-8", newline="") as source:
            return {
                row["gene_symbol"].strip().upper(): row["direction"]
                for row in csv.DictReader(source, delimiter="\t")
                if row.get("selection_status") == "exploratory_candidate"
            }

    @staticmethod
    def _validate_candidate(
        gene: str, expected: str, signature: list[dict[str, str]]
    ) -> dict[str, object]:
        matches = [row for row in signature if row["gene_symbol"] == gene]
        agreement = [row for row in matches if row["direction"] == expected]
        conflicts = [row for row in matches if row["direction"] != expected]
        if agreement and not conflicts:
            status = "published_directional_support"
        elif conflicts:
            status = "published_directional_conflict"
        else:
            status = "not_reported_in_published_signature"
        return {
            "gene_symbol": gene,
            "axis_expected_direction": expected,
            "published_rows": len(matches),
            "supporting_rows": len(agreement),
            "conflicting_rows": len(conflicts),
            "cohorts": "|".join(sorted({row["cohort"] for row in matches})),
            "status": status,
        }

    @staticmethod
    def _raw_rows(path: Path, sheet_name: str) -> list[list[str]]:
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
            return [
                PublishedSupplementValidator._xlsx_row(row, shared)
                for row in root.findall("m:sheetData/m:row", NS)
            ]

    @staticmethod
    def _write(
        path: Path,
        rows: list[dict[str, object]] | list[dict[str, str]],
    ) -> None:
        fields = tuple(rows[0]) if rows else ("gene_symbol",)
        with path.open("w", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=fields, delimiter="\t")
            writer.writeheader()
            writer.writerows(rows)

    @staticmethod
    def _request_text() -> str:
        return "\n".join(
            (
                "Subject: Request for participant-level transcriptomic data "
                "from Karow et al. (2021)",
                "",
                "Dear Professor Syrbe,",
                "",
                "I am conducting a reproducible, non-commercial analysis of "
                "public transcriptomic evidence in axial spondyloarthritis. "
                "Your 2021 Arthritis Research & Therapy article reports two "
                "highly relevant CD14+ monocyte cohorts (25 axSpA/10 controls "
                "by GeneChip and 32 axSpA/22 controls by RNA-seq).",
                "",
                "The supplementary workbook provides differential gene lists, "
                "but I could not identify a GEO, SRA, ENA or BioStudies "
                "accession for the participant-level expression matrices. "
                "Would it be possible to share:",
                "",
                "1. the normalized GeneChip matrix and probe annotation for "
                "cohort 1;",
                "2. the raw count matrix for cohort 2;",
                "3. a de-identified sample sheet containing disease group, "
                "radiographic status, sex, sequencing experiment/batch and "
                "biological-treatment status; and",
                "4. any repository accession or reuse conditions that should "
                "be cited?",
                "",
                "No directly identifying or sensitive clinical information is "
                "requested. The aim is independent replication and "
                "pathway-level comparison, with full citation of the original "
                "study.",
                "",
                "Kind regards,",
                "AXIS project",
                "",
            )
        )
