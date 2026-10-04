"""Explicit ChEMBL retrieval and lossless parsing, not experimental endorsement."""

import json
from typing import Any

import httpx

IMPORTER_VERSION = "axis-chembl-1"


class ChEMBLAdapter:
    def retrieve_record(self, resource: str, identifier: str) -> bytes:
        import re

        if resource not in {"molecule", "assay", "activity", "document", "target"}:
            raise ValueError("unsupported ChEMBL resource")
        if not re.fullmatch(r"CHEMBL[0-9]+|[0-9]+", identifier):
            raise ValueError("invalid ChEMBL identifier")
        response = httpx.get(
            f"https://www.ebi.ac.uk/chembl/api/data/{resource}/{identifier}.json",
            timeout=30,
            follow_redirects=False,
        )
        response.raise_for_status()
        return response.content


def parse_activity(record: dict[str, Any]) -> dict[str, Any]:
    """Preserve reported and provider-normalized representations separately."""
    return {
        key: record.get(key)
        for key in (
            "activity_id",
            "molecule_chembl_id",
            "assay_chembl_id",
            "target_chembl_id",
            "document_chembl_id",
            "type",
            "relation",
            "value",
            "units",
            "standard_type",
            "standard_relation",
            "standard_value",
            "standard_units",
            "pchembl_value",
            "data_validity_comment",
            "activity_comment",
        )
    }


def parse_frozen(raw: bytes) -> dict[str, Any]:
    value: dict[str, Any] = json.loads(raw)
    if value.get("provider_release") != "ChEMBL_37":
        raise ValueError("unsupported frozen ChEMBL release")
    return value
