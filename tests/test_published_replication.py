import csv
import zipfile
from pathlib import Path

from axis.analysis import PublishedSupplementValidator


def test_published_validation_distinguishes_support_and_missing(
    tmp_path: Path,
) -> None:
    workbook = tmp_path / "supplement.xlsx"
    shared = (
        "title",
        "Major Cell Type",
        "gene",
        "p_val",
        "avg_log2FC",
        "p_val_adj",
        "pheno",
        "cluster",
        "M cells",
        "EWSR1",
        "CD14 Mono",
        "HC_B27+",
    )
    shared_xml = "".join(f"<si><t>{value}</t></si>" for value in shared)
    sheet_xml = """
    <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
      <sheetData>
        <row r="1"><c r="B1" t="s"><v>0</v></c></row>
        <row r="2">
          <c r="A2" t="s"><v>1</v></c><c r="B2" t="s"><v>2</v></c>
          <c r="C2" t="s"><v>3</v></c><c r="D2" t="s"><v>4</v></c>
          <c r="E2" t="s"><v>5</v></c><c r="F2" t="s"><v>6</v></c>
          <c r="G2" t="s"><v>7</v></c>
        </row>
        <row r="3">
          <c r="A3" t="s"><v>8</v></c><c r="B3" t="s"><v>9</v></c>
          <c r="C3"><v>0.0001</v></c><c r="D3"><v>-0.4</v></c>
          <c r="E3"><v>0.01</v></c><c r="F3" t="s"><v>10</v></c>
          <c r="G3" t="s"><v>11</v></c>
        </row>
      </sheetData>
    </worksheet>
    """
    with zipfile.ZipFile(workbook, "w") as archive:
        archive.writestr(
            "xl/workbook.xml",
            '<workbook xmlns="http://schemas.openxmlformats.org/'
            'spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/'
            'officeDocument/2006/relationships"><sheets><sheet name="AS vs HC" '
            'sheetId="1" r:id="rId1"/></sheets></workbook>',
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/'
            '2006/relationships"><Relationship Id="rId1" '
            'Target="worksheets/sheet1.xml"/></Relationships>',
        )
        archive.writestr(
            "xl/sharedStrings.xml",
            '<sst xmlns="http://schemas.openxmlformats.org/'
            f'spreadsheetml/2006/main">{shared_xml}</sst>',
        )
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    candidates = tmp_path / "candidates.tsv"
    candidates.write_text(
        "gene_symbol\tdecision\tsingle_cell_direction\n"
        "EWSR1\tgenerate_causal_evidence\tlower_in_case\n"
        "ATG14\tgenerate_causal_evidence\tlower_in_case\n",
        encoding="utf-8",
    )

    result = PublishedSupplementValidator().validate(
        workbook, candidates, output_root=tmp_path / "out"
    )

    with result.output_path.open(encoding="utf-8", newline="") as source:
        rows = {
            row["gene_symbol"]: row for row in csv.DictReader(source, delimiter="\t")
        }
    assert rows["EWSR1"]["validation_status"] == "published_directional_support"
    assert rows["ATG14"]["validation_status"] == ("not_reported_in_published_de_table")
