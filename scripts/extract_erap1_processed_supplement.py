"""Read the public 2025 Supplement Table A; freeze small source-anchored inputs.

Requires openpyxl for read-only source extraction, not AXIS runtime/replay.
Original workbook/archive stay external. No raw-MS processing or new statistics.
"""

import argparse
import hashlib
import importlib.metadata
import io
import json
from pathlib import Path
from zipfile import ZipFile


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def main() -> None:
    import openpyxl

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    args = parser.parse_args()
    archive = args.cache / "PMC12136889-supplements.zip"
    metadata = json.loads(Path(str(archive) + ".provenance.json").read_text())
    if sha(archive.read_bytes()) != metadata["sha256"]:
        raise ValueError("supplement archive checksum mismatch")
    with ZipFile(archive) as source:
        raw = source.read("mmc2.xlsx")
    workbook = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    output = {
        "source": "10.1016/j.mcpro.2025.100964",
        "archive_sha256": metadata["sha256"],
        "workbook_sha256": sha(raw),
        "source_filename": "mmc2.xlsx",
        "extractor": "scripts/extract_erap1_processed_supplement.py",
        "extractor_sha256": sha(Path(__file__).read_bytes()),
        "openpyxl": importlib.metadata.version("openpyxl"),
        "reports": {},
        "classifications": {},
    }
    for name in ("Report 1 blanks removed", "Report 2 blanks removed"):
        rows = iter(workbook[name].values)
        headers = next(rows)
        columns = {header: i for i, header in enumerate(headers)}
        samples, sequences = {}, {}
        for row_number, row in enumerate(rows, 2):
            sample, condition, sequence = (
                row[columns[k]]
                for k in ("R.FileName", "R.Condition", "PEP.StrippedSequence")
            )
            if sample in samples and samples[sample] != condition:
                raise ValueError("conflicting source sample condition")
            samples[sample] = condition
            if 8 <= len(sequence) <= 16:
                sequences.setdefault(
                    sequence, f"{name}:row:{row_number}:PEP.StrippedSequence"
                )
        output["reports"][name] = {"samples": samples, "sequences": sequences}
    for name in ("inhibitor diff expressed+unique", "ko diff expressed+unique"):
        groups = {
            "common": {},
            "upregulated_or_unique": {},
            "downregulated_or_wt_unique": {},
        }
        for row_number, row in enumerate(list(workbook[name].values)[2:], 3):
            for index, group in zip((0, 4, 8), groups, strict=True):
                sequence = row[index]
                if isinstance(sequence, str) and 8 <= len(sequence) <= 16:
                    groups[group].setdefault(
                        sequence, f"{name}:row:{row_number}:column:{index + 1}"
                    )
        output["classifications"][name] = groups
    workbook.close()
    target = args.cache / "processed/2025-supplement-peptides.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    frozen = (json.dumps(output, sort_keys=True, indent=2) + "\n").encode()
    target.write_bytes(frozen)
    Path(str(target) + ".provenance.json").write_text(
        json.dumps(
            {
                "status": 200,
                "url": metadata["url"],
                "retrieved_at": metadata["retrieved_at"],
                "cache_path": str(target.relative_to(args.cache)),
                "sha256": sha(frozen),
                "bytes": len(frozen),
                "content_type": "application/json",
                "epistemic_type": "axis_observation",
                "parent_archive_sha256": metadata["sha256"],
                "parent_member_sha256": sha(raw),
            },
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )
    print(target)


if __name__ == "__main__":
    main()
