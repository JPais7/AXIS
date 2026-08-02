from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "publication" / "axis-methods"
DOCX = OUT / "AXIS_methods_manuscript_Joao_Pais_Diana_Koshman.docx"

NAVY = "17365D"
BLUE = "2F75B5"
PALE = "EAF2F8"
GRAY = "666666"
WHITE = "FFFFFF"


def font(run, size=10.5, bold=False, italic=False, color="000000"):
    run.font.name = "Aptos"
    run._element.get_or_add_rPr().rFonts.set(qn("w:ascii"), "Aptos")
    run._element.get_or_add_rPr().rFonts.set(qn("w:hAnsi"), "Aptos")
    run.font.size = Pt(size)
    run.bold = bold
    run.italic = italic
    run.font.color.rgb = RGBColor.from_string(color)


def shade(cell, fill):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def set_cell_width(cell, dxa):
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_w = tc_pr.find(qn("w:tcW"))
    if tc_w is None:
        tc_w = OxmlElement("w:tcW")
        tc_pr.append(tc_w)
    tc_w.set(qn("w:w"), str(dxa))
    tc_w.set(qn("w:type"), "dxa")


def set_table_geometry(table, widths):
    table.autofit = False
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    tbl_pr = table._tbl.tblPr
    tbl_w = tbl_pr.find(qn("w:tblW"))
    if tbl_w is None:
        tbl_w = OxmlElement("w:tblW")
        tbl_pr.append(tbl_w)
    tbl_w.set(qn("w:w"), str(sum(widths)))
    tbl_w.set(qn("w:type"), "dxa")
    tbl_ind = tbl_pr.find(qn("w:tblInd"))
    if tbl_ind is None:
        tbl_ind = OxmlElement("w:tblInd")
        tbl_pr.append(tbl_ind)
    tbl_ind.set(qn("w:w"), "120")
    tbl_ind.set(qn("w:type"), "dxa")
    grid = table._tbl.tblGrid
    for child in list(grid):
        grid.remove(child)
    for width in widths:
        col = OxmlElement("w:gridCol")
        col.set(qn("w:w"), str(width))
        grid.append(col)
    for row in table.rows:
        tr_pr = row._tr.get_or_add_trPr()
        cant_split = OxmlElement("w:cantSplit")
        tr_pr.append(cant_split)
        for idx, cell in enumerate(row.cells):
            set_cell_width(cell, widths[idx])
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            tc_pr = cell._tc.get_or_add_tcPr()
            margins = OxmlElement("w:tcMar")
            for side in ("top", "left", "bottom", "right"):
                node = OxmlElement(f"w:{side}")
                node.set(qn("w:w"), "110")
                node.set(qn("w:type"), "dxa")
                margins.append(node)
            tc_pr.append(margins)


def repeat_header(row):
    tr_pr = row._tr.get_or_add_trPr()
    tbl_header = OxmlElement("w:tblHeader")
    tbl_header.set(qn("w:val"), "true")
    tr_pr.append(tbl_header)


def add_body(doc, text, bold_start=None):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.line_spacing = 1.12
    if bold_start and text.startswith(bold_start):
        font(p.add_run(bold_start), bold=True)
        font(p.add_run(text[len(bold_start) :]))
    else:
        font(p.add_run(text))
    return p


def add_heading(doc, text, level=1):
    p = doc.add_paragraph(style=f"Heading {level}")
    p.paragraph_format.keep_with_next = True
    p.add_run(text)
    return p


def add_bullets(doc, items):
    for item in items:
        p = doc.add_paragraph(style="List Bullet")
        p.paragraph_format.space_after = Pt(3)
        font(p.add_run(item), size=10.2)


def add_table(doc, headers, rows, widths):
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    for index, value in enumerate(headers):
        cell = table.rows[0].cells[index]
        shade(cell, NAVY)
        p = cell.paragraphs[0]
        font(p.add_run(value), size=9.2, bold=True, color=WHITE)
    for row_index, row in enumerate(rows):
        cells = table.add_row().cells
        for index, value in enumerate(row):
            if row_index % 2 == 1:
                shade(cells[index], "F5F7FA")
            p = cells[index].paragraphs[0]
            font(p.add_run(value), size=9.0)
    set_table_geometry(table, widths)
    repeat_header(table.rows[0])
    doc.add_paragraph().paragraph_format.space_after = Pt(1)
    return table


def configure(doc):
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(0.85)
    section.bottom_margin = Inches(0.8)
    section.left_margin = Inches(1)
    section.right_margin = Inches(1)
    styles = doc.styles
    normal = styles["Normal"]
    normal.font.name = "Aptos"
    normal.font.size = Pt(10.5)
    normal.paragraph_format.space_after = Pt(6)
    for name, size, color in (("Heading 1", 16, NAVY), ("Heading 2", 12.5, BLUE), ("Heading 3", 11, NAVY)):
        style = styles[name]
        style.font.name = "Aptos Display"
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor.from_string(color)
        style.paragraph_format.space_before = Pt(12 if name == "Heading 1" else 8)
        style.paragraph_format.space_after = Pt(4)
    header = section.header.paragraphs[0]
    header.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    font(header.add_run("AXIS | Methods manuscript | Draft 1.0"), size=8.5, color=GRAY)
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), "PAGE")
    footer._p.append(field)


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    doc = Document()
    configure(doc)

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(72)
    p.paragraph_format.space_after = Pt(10)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    font(p.add_run("AXIS"), size=30, bold=True, color=NAVY)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(18)
    font(p.add_run("An auditable, participant-aware workflow for cross-study molecular evidence synthesis and therapeutic hypothesis generation"), size=15, color=BLUE)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    font(p.add_run("João Pais and Diana Koshman"), size=12, bold=True)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    font(p.add_run("Independent researchers; no institutional affiliation"), size=10, italic=True, color=GRAY)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(30)
    font(p.add_run("Software/methods manuscript - pre-submission draft"), size=10.5, bold=True, color=NAVY)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    font(p.add_run("Version 1.0 release candidate | 2 August 2026"), size=9.5, color=GRAY)

    doc.add_page_break()
    add_heading(doc, "Abstract")
    add_body(doc, "Public molecular datasets can support therapeutic hypothesis generation, but reuse is hindered by inconsistent sample metadata, incompatible tissues and assays, pseudoreplication, and weak provenance. AXIS is a local Python platform that organizes study discovery, eligibility review, expression analysis, cross-cohort synthesis, single-cell pseudobulk validation, target evidence integration, and frozen reproduction as one guarded workflow. It distinguishes discovery, independent validation, sensitivity analysis, mechanistic evidence, and treatment response; preserves participant-level independence; and records checksums and method decisions for audit. In a case study in axial spondyloarthritis, AXIS synthesized DDX24 expression in two compatible CD8 cohorts (14 cases and 33 controls) and retained a broader third CD8 cohort as sensitivity evidence. The frozen offline run passed 25 of 25 claim checks and reproduced an associative decrease in DDX24 expression, while explicitly preventing causal or therapeutic overinterpretation. The current codebase contains 84 Python modules and 138 automated tests. AXIS is intended as research software for generating falsifiable priorities, not as an autonomous drug-discovery or clinical decision system.")
    add_body(doc, "Keywords: axial spondyloarthritis; transcriptomics; single-cell RNA sequencing; pseudobulk; meta-analysis; target prioritization; reproducible research")

    add_heading(doc, "1. Summary")
    add_body(doc, "AXIS converts heterogeneous public molecular evidence into traceable research hypotheses. Its central design principle is that more records do not automatically mean more evidence: studies enter a synthesis only when their disease definition, biological material, assay, comparison, and participant structure support the declared question. In single-cell analyses, cells are aggregated within participants so that the biological participant, rather than each cell, remains the statistical unit. The platform then keeps compatible primary evidence separate from broader sensitivity evidence.")

    add_heading(doc, "2. Statement of need")
    add_body(doc, "Repositories such as the NCBI Gene Expression Omnibus provide access to high-throughput functional genomics studies [1]. However, the metadata needed for secondary disease research are frequently encoded in free text, and apparently similar studies may differ in tissue, cell state, treatment exposure, platform, or unit of replication. A naive pipeline can therefore inflate sample size, combine incompatible effects, or rediscover the same participants under multiple accessions.")
    add_body(doc, "AXIS addresses this gap by making eligibility, provenance, and allowed scientific use first-class objects. It is designed for investigators who need to move from a broad repository search to a small set of defensible, testable claims without concealing uncertainty behind a single opaque score.")

    add_heading(doc, "3. Software design")
    add_table(doc, ["Stage", "Purpose", "Guardrail"], [
        ("Discovery", "Search and deduplicate GEO, BioStudies/ArrayExpress and SRA records.", "A repository record is not counted as an eligible cohort."),
        ("Eligibility", "Review disease, tissue, assay, design, treatment and participant independence.", "Approvals are role-specific and invalidated when analyzed inputs change."),
        ("Analysis", "Run QC, bulk differential analysis, or participant-level single-cell pseudobulk.", "Outliers are flagged, not silently removed; cells are not independent replicates."),
        ("Synthesis", "Assess recurrence, directional concordance, validation and random-effects summaries.", "Incompatible scales and cell definitions remain stratified."),
        ("Translation", "Join genetic, mechanistic, tractability, safety, structure and drug evidence.", "Expression direction is not substituted for causal therapeutic direction."),
        ("Reproduction", "Verify frozen inputs, lockfile, numerical outputs and claim constraints offline.", "Checksum or scientific-guardrail failures stop the run."),
    ], [1450, 3880, 4030])

    add_heading(doc, "3.1 Evidence and provenance model", 2)
    add_body(doc, "AXIS stores scientific entities, contextual claims, source assertions, calculated evidence, researcher hypotheses, and immutable provenance separately. A local DuckDB evidence store supports versioned migrations and append-only hypothesis revision. Download manifests record source locations, retrieval times, sizes, and SHA-256 checksums. Eligibility decisions are bound to checksums of the analyzed results, preventing an approval from silently surviving reanalysis.")

    add_heading(doc, "3.2 Statistical safeguards", 2)
    add_body(doc, "For microarrays, AXIS supports probe-to-gene mapping, multiple-testing correction, a two-group moderated model, and declared covariate designs. Cross-study recurrence requires same-direction support and does not pool incompatible raw effect scales. For single-cell RNA sequencing, counts are aggregated by participant and cell type before comparison. This follows evidence that methods accounting for the dependence of cells within individuals, including pseudobulk approaches, provide more reliable differential-expression inference [2]. Random-effects summaries are reserved for contrasts with sufficiently compatible definitions.")

    add_heading(doc, "3.3 Therapeutic evidence", 2)
    add_body(doc, "Candidate genes can be linked to Open Targets evidence covering disease association, human genetics, tractability, clinical precedent, safety and target-prioritization properties [3,4]. These dimensions remain visible rather than being collapsed into a proprietary score. Protein structure and pharmacology are downstream filters: neither an AlphaFold model nor an existing ligand can rescue a target that lacks replicated biological evidence or a defensible causal direction.")

    add_heading(doc, "4. Case study: DDX24 in CD8 T cells")
    add_body(doc, "The current demonstration asks whether DDX24 expression differs in CD8 T cells from people with axial or ankylosing spondylitis and healthy controls. Two compatible participant-level cohorts form the primary synthesis: 14 cases and 33 controls. The random-effects estimate is -0.148 (95% confidence interval -0.272 to -0.024; p=0.019). A third, broader CD8 cohort is sensitivity-only because its cellular definition is less specific. With that cohort, the synthesis contains 51 participants and retains the same direction (estimate -0.145; 95% confidence interval -0.249 to -0.041; p=0.006). These results support an association, not causality, target validity, or treatment benefit.")
    add_table(doc, ["Evidence role", "Cohorts", "Participants", "Interpretation"], [
        ("Primary CD8 synthesis", "2", "47", "Compatible CD8 definitions; associative evidence."),
        ("Broad-CD8 sensitivity", "3", "51", "Directional robustness under a broader cellular definition."),
        ("Excluded pooled dataset", "0 added", "Not estimable", "One pooled library per group cannot establish participant-level replication."),
    ], [2050, 1100, 1400, 4810])

    add_heading(doc, "5. Verification and reproducibility")
    add_body(doc, "On 2 August 2026, the complete local test suite passed 138 of 138 tests. Ruff and strict mypy checks also passed. A 290 KB wheel was built locally and its packaged synthetic demonstration passed 9 of 9 checks outside the source tree. The DDX24 offline reproduction verifies three frozen participant-level inputs and the Poetry lockfile by SHA-256, recomputes the primary and sensitivity summaries, compares numerical values within tight tolerances, and enforces 25 scientific and computational checks. All 25 checks passed in the frozen Windows/Python 3.12 environment.")
    add_body(doc, "These results demonstrate internal re-executability and claim binding. They do not yet demonstrate portability to an independent computer. A lightweight redistributable example dataset, continuous integration across operating systems, a public version-controlled repository, and an independent installation test remain release requirements.")

    add_heading(doc, "6. Research impact and intended use")
    add_body(doc, "AXIS has already supported a structured axial-spondyloarthritis case study and the preparation of a prospective DDX24 laboratory validation protocol. Its intended impact is methodological: to make the path from public data to experiment selection more conservative, inspectable, and reproducible. The platform can be adapted through a research manifest defining disease, population, tissue, cell type, comparison, treatments, and exclusion criteria. It should be used to prioritize experiments and evidence gaps, not to recommend treatment or claim clinical efficacy.")

    add_heading(doc, "7. Limitations")
    add_bullets(doc, [
        "The current demonstration is disease-specific and based on few compatible cohorts.",
        "External reproduction on a second computer has not yet been completed.",
        "Benchmarking against alternative end-to-end tools and formal runtime/memory profiling remain pending.",
        "Human review is still required for sample interpretation, eligibility, confounders and biological meaning.",
        "RCT evidence, pharmacovigilance and clinical outcomes are not yet implemented as a dedicated evidence layer.",
        "The project is not yet eligible for a software-journal submission that requires a mature public development history and public issue tracking.",
    ])

    add_heading(doc, "8. Availability and release plan")
    availability = add_body(doc, "AXIS is implemented in Python 3.12 and exposes a command-line interface. The release candidate includes an Apache 2.0 license, citation and community guidance, locked dependencies, automated tests, a packaged synthetic demonstration, a cross-platform continuous-integration definition, frozen reproduction manifests and auditable tabular/JSON outputs. Version 1.0 should be tagged only after publication in a public repository, observation of successful cross-platform CI, independent installation and reproduction, benchmarking, and archived release metadata. Current status: version 1.0 release candidate.")
    availability.paragraph_format.keep_together = True

    add_heading(doc, "9. AI usage disclosure")
    add_body(doc, "Generative AI was used interactively to assist software implementation, documentation, test design and manuscript drafting. Scientific claims were constrained by explicit programmatic checks, source artifacts and author review. AI output was not treated as evidence, and the authors remain responsible for verification, interpretation and the final submitted text.")

    add_heading(doc, "10. Author contributions")
    add_body(doc, "João Pais: conceptualization, investigation, project direction and manuscript review. Diana Koshman: scientific collaboration, validation planning and manuscript review. Software engineering and manuscript drafting included AI-assisted work under author supervision. Final CRediT roles should be confirmed by both authors before submission.")

    add_heading(doc, "11. Funding, competing interests and data ethics")
    add_body(doc, "Funding: none declared. Competing interests: none declared. AXIS reuses de-identified public datasets and does not itself recruit participants. The ethical and consent conditions of each source study remain applicable. These statements must be reconfirmed before submission.")

    add_heading(doc, "References")
    refs = [
        "1. Barrett T, et al. NCBI GEO: archive for high-throughput functional genomic data. Nucleic Acids Research. 2009;37(Database issue):D885-D890. doi:10.1093/nar/gkn764.",
        "2. Murphy AE, Skene NG. A balanced measure shows superior performance of pseudobulk methods in single-cell RNA-sequencing analysis. Nature Communications. 2022;13:7851. doi:10.1038/s41467-022-35519-4.",
        "3. Ochoa D, et al. Open Targets Platform: supporting systematic drug-target identification and prioritisation. Nucleic Acids Research. 2021;49(D1):D1302-D1310. doi:10.1093/nar/gkaa1027.",
        "4. Open Targets Consortium. Open Targets Platform: facilitating therapeutic hypotheses building in drug discovery. Nucleic Acids Research. 2025;53(D1):D1467-D1475. doi:10.1093/nar/gkae1072.",
        "5. Alber S, et al. Single cell transcriptome and surface epitope analysis of ankylosing spondylitis facilitates disease classification by machine learning. Frontiers in Immunology. 2022;13:838636. doi:10.3389/fimmu.2022.838636.",
        "6. Tang M, Qaiyum Z, Lim M, Inman RD. Single cell immune profiling in ankylosing spondylitis reveals resistance of CD8+ T cells to immune exhaustion. iScience. 2025;28:112715. doi:10.1016/j.isci.2025.112715.",
    ]
    for ref in refs:
        p = doc.add_paragraph(style="List Number")
        p.paragraph_format.left_indent = Inches(0.18)
        p.paragraph_format.first_line_indent = Inches(-0.18)
        p.paragraph_format.space_after = Pt(4)
        font(p.add_run(ref.split(". ", 1)[1]), size=9.2)

    props = doc.core_properties
    props.title = "AXIS methods manuscript"
    props.author = "João Pais; Diana Koshman"
    props.subject = "Research software and methods"
    props.keywords = "AXIS, transcriptomics, reproducibility, pseudobulk, target prioritization"
    doc.save(DOCX)
    print(DOCX)


if __name__ == "__main__":
    build()
