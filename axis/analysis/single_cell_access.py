"""Audit whether a publication exposes a usable primary-data accession."""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

ACCESSION = re.compile(
    r"\b(?:GSE|GSM|PRJNA|SRP|SCP|EGAS)\d{5,}\b|\bE-MTAB-\d{3,}\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ReplicationAccessAuditRun:
    identifiers: tuple[str, ...]
    primary_accession_verified: bool
    output_path: Path


class ReplicationAccessAuditor:
    """Inspect full text and Office supplements without trusting boilerplate."""

    def audit(
        self,
        article_xml: str | Path,
        supplementary_zip: str | Path,
        *,
        known_validation_accessions: tuple[str, ...] = ("GSE194315",),
        output_root: str | Path = Path(
            "data/single-cell/independent-replication/access-audit"
        ),
    ) -> ReplicationAccessAuditRun:
        article = Path(article_xml)
        supplements = Path(supplementary_zip)
        article_text = article.read_text(encoding="utf-8", errors="replace")
        supplement_text = self._supplement_text(supplements)
        identifiers = tuple(
            sorted(
                {
                    match.group(0).upper()
                    for text in (article_text, supplement_text)
                    for match in ACCESSION.finditer(text)
                }
            )
        )
        known = {item.upper() for item in known_validation_accessions}
        primary = tuple(item for item in identifiers if item not in known)
        destination = Path(output_root)
        destination.mkdir(parents=True, exist_ok=True)
        output_path = destination / "publication-access-audit.json"
        output_path.write_text(
            json.dumps(
                {
                    "analysis_role": "publication_data_access_audit",
                    "created_at": datetime.now(UTC).isoformat(),
                    "publication": "PMC11926545",
                    "article_xml": str(article),
                    "article_sha256": self._checksum(article),
                    "supplementary_archive": str(supplements),
                    "supplementary_sha256": self._checksum(supplements),
                    "recognized_identifiers": list(identifiers),
                    "known_external_validation_accessions": sorted(known),
                    "candidate_primary_accessions": list(primary),
                    "primary_accession_verified": bool(primary),
                    "decision": (
                        "primary_data_access_verified"
                        if primary
                        else "primary_data_accession_not_reported_reproducibly"
                    ),
                    "next_action": (
                        "download_and_validate_primary_processed_counts"
                        if primary
                        else "contact_corresponding_authors_or_repository"
                    ),
                    "warning": (
                        "A generic data-availability statement is not treated "
                        "as access unless a machine-recognisable primary "
                        "repository identifier is present."
                    ),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return ReplicationAccessAuditRun(
            identifiers=identifiers,
            primary_accession_verified=bool(primary),
            output_path=output_path,
        )

    @staticmethod
    def _supplement_text(path: Path) -> str:
        fragments: list[str] = []
        with zipfile.ZipFile(path) as outer:
            for name in outer.namelist():
                if not name.lower().endswith((".docx", ".xlsx")):
                    continue
                payload = outer.read(name)
                try:
                    with zipfile.ZipFile(BytesIO(payload)) as office:
                        for member in office.namelist():
                            if member.lower().endswith((".xml", ".rels")):
                                fragments.append(
                                    office.read(member).decode(
                                        "utf-8", errors="replace"
                                    )
                                )
                except zipfile.BadZipFile:
                    continue
        return "\n".join(fragments)

    @staticmethod
    def _checksum(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return "sha256:" + digest.hexdigest()
