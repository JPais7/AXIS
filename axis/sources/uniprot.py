"""Explicit UniProt ingestion; pure parsing also supports frozen replay."""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from axis.domain.protein import (
    ProteinIdentity,
    ProteinIsoform,
    SourceSnapshot,
    normalize_sequence,
    sequence_checksum,
)

IMPORTER_VERSION = "1"


def validate_accession(accession: str) -> None:
    if (
        re.fullmatch(
            r"(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2})",
            accession,
        )
        is None
    ):
        raise ValueError("invalid primary UniProt accession")


@dataclass(frozen=True)
class ParsedProtein:
    snapshot: SourceSnapshot
    protein: ProteinIdentity
    isoforms: tuple[ProteinIsoform, ...]


def parse_record(
    raw: bytes,
    accession: str,
    retrieved_at: datetime,
    *,
    expected_taxon: int,
    provider_release: str | None = None,
    resource_path: str | None = None,
) -> ParsedProtein:
    validate_accession(accession)
    digest = hashlib.sha256(raw).hexdigest()
    try:
        data: Any = json.loads(raw)
        if not isinstance(data, dict) or data["primaryAccession"] != accession:
            raise ValueError("response accession mismatch")
        taxon = data["organism"]["taxonId"]
        if type(taxon) is not int or taxon != expected_taxon:
            raise ValueError("unexpected source taxon")
        sequence = normalize_sequence(data["sequence"]["value"])
        if len(sequence) != data["sequence"]["length"]:
            raise ValueError("provider sequence length mismatch")
        audit = data.get("entryAudit", {})
        genes = data.get("genes", [])
        gene = genes[0].get("geneName", {}).get("value") if len(genes) == 1 else None
        name = (
            data.get("proteinDescription", {})
            .get("recommendedName", {})
            .get("fullName", {})
            .get("value")
        )
        snapshot_id = f"uniprot:{accession}:{digest}:{retrieved_at.isoformat()}"
        snapshot = SourceSnapshot(
            snapshot_id,
            "UniProt",
            accession,
            retrieved_at,
            f"https://rest.uniprot.org/uniprotkb/{accession}.json",
            digest,
            "application/json",
            IMPORTER_VERSION,
            provider_release,
            resource_path,
            json.dumps(
                {"normalization": "uppercase; remove whitespace; reject headers/gaps"}
            ),
        )
        protein = ProteinIdentity(
            f"protein:{snapshot_id}",
            "uniprot",
            accession,
            data["uniProtkbId"],
            name,
            gene,
            data["organism"]["scientificName"],
            taxon,
            sequence,
            len(sequence),
            sequence_checksum(sequence),
            audit.get("sequenceVersion"),
            audit.get("entryVersion"),
            data.get("entryType", "Not reported"),
            snapshot.id,
            retrieved_at,
        )
        isoforms = []
        for comment in data.get("comments", []):
            if comment.get("commentType") != "ALTERNATIVE PRODUCTS":
                continue
            for isoform in comment.get("isoforms", []):
                displayed = isoform.get("isoformSequenceStatus") == "Displayed"
                for iso_accession in isoform.get("isoformIds", []):
                    isoforms.append(
                        ProteinIsoform(
                            f"{protein.id}:isoform:{iso_accession}",
                            protein.id,
                            "uniprot",
                            iso_accession,
                            isoform.get("name", {}).get("value"),
                            sequence if displayed else None,
                            len(sequence) if displayed else None,
                            protein.sequence_checksum if displayed else None,
                            None,
                            displayed,
                            snapshot.id,
                        )
                    )
        # A displayed entry sequence alone does not establish an isoform accession.
        return ParsedProtein(snapshot, protein, tuple(isoforms))
    except (KeyError, TypeError, AttributeError, IndexError) as error:
        raise ValueError("malformed UniProt identity payload") from error


class UniProtAdapter:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self.client = client

    def retrieve(
        self, accession: str, retrieved_at: datetime, *, expected_taxon: int
    ) -> ParsedProtein:
        validate_accession(accession)
        url = f"https://rest.uniprot.org/uniprotkb/{accession}.json"
        if self.client is None:
            with httpx.Client(timeout=30, follow_redirects=False) as client:
                response = client.get(url)
        else:
            response = self.client.get(url)
        response.raise_for_status()
        return parse_record(
            response.content,
            accession,
            retrieved_at,
            expected_taxon=expected_taxon,
            provider_release=response.headers.get("x-uniprot-release"),
        )
