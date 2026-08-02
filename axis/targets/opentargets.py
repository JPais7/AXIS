"""Lightweight, cached Open Targets target-intelligence dossiers."""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import httpx

from axis.ingestion.geo import GeoApiError

API_URL = "https://api.platform.opentargets.org/api/v4/graphql"

SEARCH_QUERY = """
query ResolveTarget($query: String!) {
  search(
    queryString: $query
    entityNames: ["target"]
    page: {index: 0, size: 5}
  ) {
    hits { id entity name description }
  }
}
"""

TARGET_QUERY = """
query TargetDossier($id: String!) {
  target(ensemblId: $id) {
    id
    approvedSymbol
    approvedName
    biotype
    tractability { label modality value }
    prioritisation { items { key value } }
    safetyLiabilities { event eventId datasource }
    drugAndClinicalCandidates {
      count
      rows {
        id
        maxClinicalStage
        drug { id name drugType maximumClinicalStage }
        diseases {
          diseaseFromSource
          disease { id name }
        }
      }
    }
    associatedDiseases(page: {index: 0, size: 50}) {
      rows {
        disease { id name }
        score
        datatypeScores { id score }
      }
    }
  }
}
"""

GENETIC_EVIDENCE_QUERY = """
query GeneticEvidence($id: String!, $disease: String!) {
  target(ensemblId: $id) {
    evidences(
      efoIds: [$disease]
      datasourceIds: [
        "gwas_credible_sets"
        "gene_burden"
        "genomics_england"
      ]
      size: 100
    ) {
      count
      rows {
        id
        datasourceId
        datatypeId
        score
        directionOnTarget
        directionOnTrait
        beta
        oddsRatio
        variantRsId
        studyId
        targetFromSourceId
        diseaseFromSourceMappedId
      }
    }
  }
}
"""

CAUSAL_CONTEXT_QUERY = """
query CausalContext($id: String!, $disease: String!) {
  target(ensemblId: $id) {
    evidences(
      efoIds: [$disease]
      datasourceIds: ["gwas_credible_sets"]
      size: 100
    ) {
      count
      rows {
        id
        score
        credibleSet {
          studyLocusId
          finemappingMethod
          confidence
          purityMeanR2
          beta
          pValueMantissa
          pValueExponent
          variant { id rsIds }
          study {
            id
            traitFromSource
            nCases
            nControls
            nSamples
          }
          l2GPredictions {
            count
            rows { score target { id approvedSymbol } }
          }
          colocalisation {
            count
            rows {
              h4
              clpp
              rightStudyType
              colocalisationMethod
              otherStudyLocus {
                qtlGeneId
                study {
                  studyType
                  target { id approvedSymbol }
                  biosample { biosampleId biosampleName }
                }
              }
            }
          }
        }
      }
    }
    baselineExpression(page: {index: 0, size: 200}) {
      count
      rows {
        datasourceId
        datatypeId
        tissueBiosampleFromSource
        celltypeBiosampleFromSource
        median
        specificity_score
        distribution_score
      }
    }
  }
}
"""


@dataclass(frozen=True)
class TargetIntelligenceRun:
    requested_genes: int
    resolved_targets: int
    output_path: Path
    summary_path: Path
    dossier_directory: Path


class OpenTargetsClient:
    """GraphQL client with exact-response disk caching."""

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        endpoint: str = API_URL,
    ) -> None:
        self._client = client or httpx.Client(
            timeout=30.0,
            headers={"User-Agent": "AXIS/0.1 target-intelligence"},
        )
        self._owns_client = client is None
        self.endpoint = endpoint

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> OpenTargetsClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def target_dossier(
        self,
        gene_symbol: str,
        *,
        cache_directory: str | Path,
        refresh: bool = False,
    ) -> dict[str, object]:
        symbol = gene_symbol.strip().upper()
        if not symbol:
            raise ValueError("gene symbol must not be empty")
        cache_path = Path(cache_directory) / f"{symbol}.json"
        if cache_path.exists() and not refresh:
            return cast(
                dict[str, object],
                json.loads(cache_path.read_text(encoding="utf-8")),
            )
        resolved = self._resolve(symbol)
        if resolved is None:
            payload: dict[str, object] = {
                "requested_symbol": symbol,
                "resolved": False,
                "retrieved_at": datetime.now(UTC).isoformat(),
                "source_uri": self.endpoint,
            }
        else:
            target = self._request(
                TARGET_QUERY,
                {"id": resolved["id"]},
            ).get("target")
            if not isinstance(target, dict):
                raise GeoApiError(
                    f"Open Targets returned no target for {resolved['id']}"
                )
            payload = {
                "requested_symbol": symbol,
                "resolved": True,
                "resolution": resolved,
                "target": target,
                "retrieved_at": datetime.now(UTC).isoformat(),
                "source_uri": self.endpoint,
            }
        canonical = json.dumps(payload, sort_keys=True).encode()
        payload["response_checksum"] = "sha256:" + hashlib.sha256(canonical).hexdigest()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )
        return payload

    def genetic_evidence(
        self,
        ensembl_id: str,
        disease_id: str,
    ) -> dict[str, object]:
        data = self._request(
            GENETIC_EVIDENCE_QUERY,
            {"id": ensembl_id, "disease": disease_id},
        )
        target = data.get("target")
        if not isinstance(target, dict):
            raise GeoApiError(f"Open Targets returned no target for {ensembl_id}")
        evidences = target.get("evidences")
        if not isinstance(evidences, dict):
            raise GeoApiError("Open Targets returned no evidence collection")
        return cast(dict[str, object], evidences)

    def causal_context(
        self,
        ensembl_id: str,
        disease_id: str,
    ) -> dict[str, object]:
        data = self._request(
            CAUSAL_CONTEXT_QUERY,
            {"id": ensembl_id, "disease": disease_id},
        )
        target = data.get("target")
        if not isinstance(target, dict):
            raise GeoApiError(f"Open Targets returned no target for {ensembl_id}")
        return cast(dict[str, object], target)

    def _resolve(self, symbol: str) -> dict[str, str] | None:
        search = self._request(SEARCH_QUERY, {"query": symbol}).get("search")
        if not isinstance(search, dict):
            return None
        hits = search.get("hits", ())
        if not isinstance(hits, list):
            return None
        exact = next(
            (
                hit
                for hit in hits
                if isinstance(hit, dict)
                and str(hit.get("name", "")).upper() == symbol
                and hit.get("entity") == "target"
            ),
            None,
        )
        if exact is None:
            return None
        return {
            "id": str(exact["id"]),
            "symbol": str(exact["name"]),
            "description": str(exact.get("description") or ""),
        }

    def _request(
        self,
        query: str,
        variables: dict[str, str],
    ) -> dict[str, Any]:
        try:
            response = self._client.post(
                self.endpoint,
                json={"query": query, "variables": variables},
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise GeoApiError(f"Open Targets request failed: {error}") from error
        errors = payload.get("errors")
        if errors:
            raise GeoApiError(f"Open Targets GraphQL error: {errors}")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise GeoApiError("Open Targets response has no data object")
        return cast(dict[str, Any], data)


class TargetIntelligenceBuilder:
    """Create separate, auditable target dimensions from cached API data."""

    def build(
        self,
        genes: list[str] | tuple[str, ...],
        *,
        output_root: str | Path = Path("data/targets"),
        refresh: bool = False,
        client: OpenTargetsClient | None = None,
    ) -> TargetIntelligenceRun:
        normalized = tuple(
            dict.fromkeys(gene.strip().upper() for gene in genes if gene.strip())
        )
        if not normalized:
            raise ValueError("at least one gene is required")
        destination = Path(output_root)
        cache = destination / "cache" / "opentargets"
        dossiers = destination / "dossiers"
        dossiers.mkdir(parents=True, exist_ok=True)
        owns_client = client is None
        api = client or OpenTargetsClient()
        try:
            rows = [
                self._dossier_row(
                    api.target_dossier(
                        gene,
                        cache_directory=cache,
                        refresh=refresh,
                    ),
                    dossier_directory=dossiers,
                )
                for gene in normalized
            ]
        finally:
            if owns_client:
                api.close()
        output_path = destination / "target-intelligence.tsv"
        self._write(output_path, rows)
        resolved = sum(bool(row["resolved"]) for row in rows)
        summary_path = destination / "target-intelligence.json"
        summary_path.write_text(
            json.dumps(
                {
                    "analysis_role": "target_intelligence",
                    "source": "Open Targets Platform",
                    "source_uri": API_URL,
                    "created_at": datetime.now(UTC).isoformat(),
                    "requested_genes": len(normalized),
                    "resolved_targets": resolved,
                    "dimensions": (
                        "disease association",
                        "tractability",
                        "clinical precedence",
                        "safety",
                        "doability/prioritisation",
                    ),
                    "scoring_policy": (
                        "dimensions remain separate; no aggregate target score"
                    ),
                    "warning": (
                        "Target intelligence supports prioritisation but does "
                        "not establish causality or therapeutic efficacy."
                    ),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return TargetIntelligenceRun(
            requested_genes=len(normalized),
            resolved_targets=resolved,
            output_path=output_path,
            summary_path=summary_path,
            dossier_directory=dossiers,
        )

    @staticmethod
    def genes_from_shortlist(path: str | Path, *, limit: int = 100) -> tuple[str, ...]:
        if limit < 1:
            raise ValueError("limit must be at least one")
        try:
            with Path(path).open(encoding="utf-8", newline="") as source:
                return tuple(
                    row["gene_symbol"]
                    for row in list(csv.DictReader(source, delimiter="\t"))[:limit]
                )
        except (OSError, UnicodeError, csv.Error, KeyError) as error:
            raise GeoApiError(f"cannot read shortlist {path}: {error}") from error

    def _dossier_row(
        self,
        payload: dict[str, object],
        *,
        dossier_directory: Path,
    ) -> dict[str, object]:
        symbol = str(payload["requested_symbol"])
        dossier_path = dossier_directory / f"{symbol}.json"
        dossier_path.write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )
        if not payload["resolved"]:
            return {
                "gene_symbol": symbol,
                "ensembl_id": "",
                "resolved": False,
                "biotype": "",
                "disease_associations": 0,
                "axspa_associations": 0,
                "tractability_positive": 0,
                "tractability_modalities": "",
                "clinical_candidates": 0,
                "maximum_clinical_stage": "",
                "safety_liabilities": 0,
                "is_essential": "",
                "dossier_path": str(dossier_path),
                "response_checksum": payload["response_checksum"],
            }
        target = cast(dict[str, Any], payload["target"])
        tractability = cast(list[dict[str, Any]], target["tractability"])
        positive = [item for item in tractability if item["value"]]
        modalities = sorted({str(item["modality"]) for item in positive})
        associations = cast(
            dict[str, list[dict[str, Any]]],
            target["associatedDiseases"],
        )["rows"]
        axspa = [
            row
            for row in associations
            if any(
                term in str(row["disease"]["name"]).lower()
                for term in (
                    "ankylosing spondylitis",
                    "axial spondylo",
                    "spondyloarthritis",
                )
            )
        ]
        clinical = cast(dict[str, Any], target["drugAndClinicalCandidates"])
        stages = [
            str(row["maxClinicalStage"])
            for row in clinical["rows"]
            if row.get("maxClinicalStage")
        ]
        prioritisation = {
            str(item["key"]): str(item["value"])
            for item in target.get("prioritisation", {}).get("items", [])
        }
        return {
            "gene_symbol": target["approvedSymbol"],
            "ensembl_id": target["id"],
            "resolved": True,
            "biotype": target["biotype"],
            "disease_associations": len(associations),
            "axspa_associations": len(axspa),
            "tractability_positive": len(positive),
            "tractability_modalities": "|".join(modalities),
            "clinical_candidates": int(clinical["count"]),
            "maximum_clinical_stage": self._maximum_stage(stages),
            "safety_liabilities": len(target["safetyLiabilities"]),
            "is_essential": prioritisation.get("geneEssentiality", ""),
            "dossier_path": str(dossier_path),
            "response_checksum": payload["response_checksum"],
        }

    @staticmethod
    def _maximum_stage(stages: list[str]) -> str:
        order = {
            "UNKNOWN": 0,
            "NOT_YET_RECRUITING": 0,
            "PHASE_1": 1,
            "PHASE_1_2": 2,
            "PHASE_2": 2,
            "PHASE_2_3": 3,
            "PHASE_3": 3,
            "PHASE_4": 4,
            "APPROVAL": 5,
        }
        normalized = tuple(stage.strip().upper().replace(" ", "_") for stage in stages)
        return max(
            normalized,
            key=lambda stage: order.get(stage, -1),
            default="",
        )

    @staticmethod
    def _write(path: Path, rows: list[dict[str, object]]) -> None:
        fields = (
            "gene_symbol",
            "ensembl_id",
            "resolved",
            "biotype",
            "disease_associations",
            "axspa_associations",
            "tractability_positive",
            "tractability_modalities",
            "clinical_candidates",
            "maximum_clinical_stage",
            "safety_liabilities",
            "is_essential",
            "dossier_path",
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
