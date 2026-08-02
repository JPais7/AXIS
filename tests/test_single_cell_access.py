import io
import json
import zipfile
from pathlib import Path

from axis.analysis import ReplicationAccessAuditor


def test_access_audit_does_not_mistake_validation_data_for_primary(
    tmp_path: Path,
) -> None:
    article = tmp_path / "article.xml"
    article.write_text(
        "<p>Validation dataset GSE194315 was used.</p>", encoding="utf-8"
    )
    office_buffer = io.BytesIO()
    with zipfile.ZipFile(office_buffer, "w") as office:
        office.writestr(
            "word/document.xml",
            "<p>Data are available in the Supplementary Material.</p>",
        )
    supplements = tmp_path / "supplements.zip"
    with zipfile.ZipFile(supplements, "w") as outer:
        outer.writestr("DataSheet1.docx", office_buffer.getvalue())

    result = ReplicationAccessAuditor().audit(
        article, supplements, output_root=tmp_path / "out"
    )

    payload = json.loads(result.output_path.read_text(encoding="utf-8"))
    assert result.identifiers == ("GSE194315",)
    assert result.primary_accession_verified is False
    assert payload["decision"] == ("primary_data_accession_not_reported_reproducibly")
