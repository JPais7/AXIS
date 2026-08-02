"""Fine-mapping, colocalisation and normal expression context for targets."""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from axis.ingestion.geo import GeoApiError
from axis.targets.opentargets import API_URL, OpenTargetsClient


@dataclass(frozen=True)
class CausalContextRun:
    targets: int
    strong_locus_to_gene: int
    molecular_colocalisation: int
    output_path: Path
    summary_path: Path


class CausalContextBuilder:
    """Deepen only genetically supported targets without aggregate scoring."""

    def build(
        self,
        genetic_table: str | Path,
        *,
        disease_id: str = "MONDO_0005306",
        output_root: str | Path = Path("data/targets/context"),
        refresh: bool = False,
        client: OpenTargetsClient | None = None,
    ) -> CausalContextRun:
        targets = self._supported_targets(Path(genetic_table))
        destination = Path(output_root)
        cache = destination / "cache" / disease_id
        cache.mkdir(parents=True, exist_ok=True)
        owns_client = client is None
        api = client or OpenTargetsClient()
        rows: list[dict[str, object]] = []
        try:
            for gene, ensembl_id in targets:
                cache_path = cache / f"{gene}.json"
                if cache_path.exists() and not refresh:
                    payload = cast(
                        dict[str, object],
                        json.loads(cache_path.read_text(encoding="utf-8")),
                    )
                else:
                    context = api.causal_context(ensembl_id, disease_id)
                    payload = {
                        "gene_symbol": gene,
                        "ensembl_id": ensembl_id,
                        "disease_id": disease_id,
                        "context": context,
                        "retrieved_at": datetime.now(UTC).isoformat(),
                        "source_uri": API_URL,
                    }
                    canonical = json.dumps(payload, sort_keys=True).encode()
                    payload["response_checksum"] = (
                        "sha256:" + hashlib.sha256(canonical).hexdigest()
                    )
                    cache_path.write_text(
                        json.dumps(payload, indent=2) + "\n",
                        encoding="utf-8",
                    )
                rows.append(self._summarize(payload))
        finally:
            if owns_client:
                api.close()

        rows.sort(
            key=lambda row: (
                -cast(float, row["maximum_locus_to_gene_score"]),
                str(row["gene_symbol"]),
            )
        )
        output_path = destination / "as-causal-context.tsv"
        self._write(output_path, rows)
        strong_l2g = sum(
            cast(float, row["maximum_locus_to_gene_score"]) >= 0.5 for row in rows
        )
        molecular = sum(
            cast(int, row["strong_molecular_colocalisations"]) > 0 for row in rows
        )
        summary_path = destination / "as-causal-context.json"
        summary_path.write_text(
            json.dumps(
                {
                    "analysis_role": "causal_target_context",
                    "source": "Open Targets Platform",
                    "source_uri": API_URL,
                    "created_at": datetime.now(UTC).isoformat(),
                    "disease_id": disease_id,
                    "targets": len(rows),
                    "targets_with_l2g_at_least_0_5": strong_l2g,
                    "targets_with_strong_molecular_colocalisation": molecular,
                    "strong_colocalisation_definition": (
                        "non-GWAS right study type and H4 >= 0.8"
                    ),
                    "expression_scope": (
                        "normal baseline expression context only; not disease "
                        "differential expression or causal direction"
                    ),
                    "warning": (
                        "Fine-mapping and colocalisation prioritise causal "
                        "genes but do not establish a safe therapeutic "
                        "modulation direction."
                    ),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return CausalContextRun(
            targets=len(rows),
            strong_locus_to_gene=strong_l2g,
            molecular_colocalisation=molecular,
            output_path=output_path,
            summary_path=summary_path,
        )

    @staticmethod
    def _supported_targets(path: Path) -> tuple[tuple[str, str], ...]:
        try:
            with path.open(encoding="utf-8", newline="") as source:
                return tuple(
                    (row["gene_symbol"], row["ensembl_id"])
                    for row in csv.DictReader(source, delimiter="\t")
                    if int(row["genetic_evidence_count"]) > 0
                )
        except (OSError, UnicodeError, csv.Error, KeyError, ValueError) as error:
            raise GeoApiError(
                f"cannot read genetic evidence table {path}: {error}"
            ) from error

    @staticmethod
    def _summarize(payload: dict[str, object]) -> dict[str, object]:
        context = cast(dict[str, Any], payload["context"])
        evidence_collection = cast(
            dict[str, Any],
            context.get("evidences", {}),
        )
        evidences = cast(
            list[dict[str, Any]],
            evidence_collection.get("rows", []),
        )
        credible_sets = [
            row["credibleSet"]
            for row in evidences
            if isinstance(row.get("credibleSet"), dict)
        ]
        studies = {
            str(item["study"]["id"])
            for item in credible_sets
            if isinstance(item.get("study"), dict)
        }
        variants = sorted(
            {
                str(item["variant"]["id"])
                for item in credible_sets
                if isinstance(item.get("variant"), dict)
            }
        )
        methods = sorted(
            {
                str(item["finemappingMethod"])
                for item in credible_sets
                if item.get("finemappingMethod")
            }
        )
        gene = str(payload["gene_symbol"])
        l2g_scores = [
            float(prediction["score"])
            for item in credible_sets
            for prediction in item.get("l2GPredictions", {}).get("rows", [])
            if prediction.get("target", {}).get("approvedSymbol") == gene
        ]
        colocations = [
            colocalisation
            for item in credible_sets
            for colocalisation in item.get("colocalisation", {}).get("rows", [])
        ]
        molecular = [
            row
            for row in colocations
            if str(row.get("rightStudyType", "")).lower() != "gwas"
        ]
        strong_molecular = [
            row
            for row in molecular
            if row.get("h4") is not None and float(row["h4"]) >= 0.8
        ]
        expression = cast(
            dict[str, Any],
            context.get("baselineExpression", {}),
        ).get("rows", [])
        top_expression = sorted(
            expression,
            key=lambda row: float(row.get("distribution_score") or 0.0),
            reverse=True,
        )[:5]
        expression_labels = tuple(
            str(
                row.get("celltypeBiosampleFromSource")
                or row.get("tissueBiosampleFromSource")
                or ""
            )
            for row in top_expression
            if (
                row.get("celltypeBiosampleFromSource")
                or row.get("tissueBiosampleFromSource")
            )
        )
        return {
            "gene_symbol": gene,
            "ensembl_id": payload["ensembl_id"],
            "credible_sets": len(credible_sets),
            "independent_studies": len(studies),
            "fine_mapping_methods": "|".join(methods),
            "lead_variants": "|".join(variants[:10]),
            "maximum_locus_to_gene_score": max(l2g_scores, default=0.0),
            "all_colocalisations": len(colocations),
            "molecular_colocalisations": len(molecular),
            "strong_molecular_colocalisations": len(strong_molecular),
            "strong_colocalisation_contexts": "|".join(
                sorted(
                    {
                        CausalContextBuilder._colocalisation_label(row)
                        for row in strong_molecular
                    }
                )
            ),
            "top_normal_expression_contexts": "|".join(expression_labels),
            "response_checksum": payload["response_checksum"],
        }

    @staticmethod
    def _colocalisation_label(row: dict[str, Any]) -> str:
        locus = row.get("otherStudyLocus") or {}
        study = locus.get("study") or {}
        biosample = study.get("biosample") or {}
        target = study.get("target") or {}
        return str(
            biosample.get("biosampleName")
            or target.get("approvedSymbol")
            or locus.get("qtlGeneId")
            or row.get("rightStudyType")
            or "unknown"
        )

    @staticmethod
    def _write(path: Path, rows: list[dict[str, object]]) -> None:
        fields = (
            "gene_symbol",
            "ensembl_id",
            "credible_sets",
            "independent_studies",
            "fine_mapping_methods",
            "lead_variants",
            "maximum_locus_to_gene_score",
            "all_colocalisations",
            "molecular_colocalisations",
            "strong_molecular_colocalisations",
            "strong_colocalisation_contexts",
            "top_normal_expression_contexts",
            "response_checksum",
        )
        with path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(
                output,
                fieldnames=fields,
                delimiter="\t",
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(rows)
