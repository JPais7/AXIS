"""Source-anchored residue mapping, never author-number equality or alignment guess."""

import hashlib
import json

from axis.domain.structure import ResidueMapping, ResidueStatus


def map_residues(
    canonical: str,
    construct: str,
    chain_id: str,
    segments: list[tuple[int, int, int, int]],
    numbering: dict[int, tuple[str | None, str | None]],
    coordinates: set[int],
    differences: dict[int, str] | None = None,
) -> tuple[ResidueMapping, ...]:
    """Segments: deposited sequence begin/end, canonical begin/end (inclusive).

    Provider anchors are required. Unequal-span segments, overlaps and low identity
    are rejected, not reconciled by guessing. Multiple segments preserve indels.
    """
    if not segments:
        raise ValueError("authoritative mapping unavailable or ambiguous")
    forward: dict[int, int] = {}
    for sb, se, cb, ce in segments:
        if (
            not 1 <= sb <= se <= len(construct)
            or not 1 <= cb <= ce <= len(canonical)
            or se - sb != ce - cb
        ):
            raise ValueError("unsupported/invalid source mapping segment")
        for s, canonical_index in zip(
            range(sb, se + 1), range(cb, ce + 1), strict=True
        ):
            if s in forward or canonical_index in forward.values():
                raise ValueError("ambiguous overlapping source mapping")
            forward[s] = canonical_index
    matches = sum(construct[s - 1] == canonical[c - 1] for s, c in forward.items())
    if matches / len(forward) < 0.95:
        raise ValueError("source mapping disagrees with pinned protein sequence")
    if not coordinates.issubset(set(range(1, len(construct) + 1))):
        raise ValueError("coordinate sequence position outside construct")
    rows = []
    differences = differences or {}
    for s, aa in enumerate(construct, 1):
        c = forward.get(s)
        author, code = numbering.get(s, (None, None))
        present = s in coordinates
        difference = differences.get(s)
        if c is None:
            status = ResidueStatus.INSERTION
        elif aa != canonical[c - 1]:
            status = (
                ResidueStatus.ENGINEERED
                if difference and "engineered" in difference.lower()
                else ResidueStatus.SUBSTITUTION
                if difference
                else ResidueStatus.MISMATCH
            )
        else:
            status = ResidueStatus.EXACT if present else ResidueStatus.UNRESOLVED
        rows.append(
            ResidueMapping(
                chain_id,
                c,
                s,
                s,
                author,
                code,
                aa,
                canonical[c - 1] if c else None,
                present,
                status,
                difference,
            )
        )
    mapped = set(forward.values())
    low, high = min(mapped), max(mapped)
    for c, aa in enumerate(canonical, 1):
        if c not in mapped:
            status = ResidueStatus.DELETION if low < c < high else ResidueStatus.OUTSIDE
            rows.append(
                ResidueMapping(
                    chain_id, c, None, None, None, None, None, aa, False, status
                )
            )
    return tuple(rows)


def mapping_checksum(rows: tuple[ResidueMapping, ...]) -> str:
    from dataclasses import asdict

    return hashlib.sha256(
        json.dumps([asdict(row) for row in rows], sort_keys=True).encode()
    ).hexdigest()


def coverage(
    rows: tuple[ResidueMapping, ...], canonical_length: int
) -> dict[str, int | float]:
    mapped = [row for row in rows if row.canonical_position and row.construct_position]
    return {
        "canonical_length": canonical_length,
        "canonical_mapped": len(mapped),
        "canonical_with_coordinates": sum(row.coordinate_present for row in mapped),
        "mapped_coverage_percent": 100 * len(mapped) / canonical_length,
        "coordinate_coverage_percent": 100
        * sum(row.coordinate_present for row in mapped)
        / canonical_length,
        "unresolved_mapped": sum(not row.coordinate_present for row in mapped),
        "not_in_construct": sum(row.status == ResidueStatus.OUTSIDE for row in rows),
        "substitutions_or_mismatches": sum(
            row.canonical_position is not None
            and row.residue_identity != row.canonical_identity
            for row in mapped
        ),
        "inserted_positions": sum(
            row.status == ResidueStatus.INSERTION for row in rows
        ),
    }
