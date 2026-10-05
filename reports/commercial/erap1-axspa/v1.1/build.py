"""Build bounded pending-review briefs from the frozen addendum, not a new state."""

import hashlib
import json
import re
from pathlib import Path
from xml.sax.saxutils import escape

from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
PACKAGE = ROOT / "axis/resources/evidence-addendum/erap1-axspa/2020-2026/v1"


def read(name):
    return json.loads((PACKAGE / name).read_text())


D = read("decision-impact.json")
CLAIMS = read("claims.json")
IMPACTS = read("impact-assessments.json")
STUDIES = read("candidate-studies.json")
NAVY = colors.HexColor("#152B36")
TEAL = colors.HexColor("#246E73")
PALE = colors.HexColor("#EDF3F2")
GRAY = colors.HexColor("#52616A")
WIDTH = A4[0] - 92
STYLES = {
    "body": ParagraphStyle(
        "body",
        fontName="Helvetica",
        fontSize=10,
        leading=14.2,
        textColor=NAVY,
        spaceAfter=8,
    ),
    "small": ParagraphStyle(
        "small",
        fontName="Helvetica",
        fontSize=8.4,
        leading=11.5,
        textColor=GRAY,
        spaceAfter=6,
    ),
    "h1": ParagraphStyle(
        "h1",
        fontName="Helvetica-Bold",
        fontSize=25,
        leading=29,
        textColor=NAVY,
        spaceAfter=16,
    ),
    "h2": ParagraphStyle(
        "h2",
        fontName="Helvetica-Bold",
        fontSize=12.5,
        leading=17,
        textColor=TEAL,
        spaceBefore=10,
        spaceAfter=8,
    ),
    "cell": ParagraphStyle(
        "cell",
        fontName="Helvetica",
        fontSize=8.2,
        leading=11.2,
        textColor=NAVY,
    ),
    "label": ParagraphStyle(
        "label",
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=11,
        textColor=TEAL,
        spaceAfter=9,
    ),
}


def plain(text):
    return str(text).translate(
        str.maketrans(
            {
                "–": "-",
                "—": "-",
                "−": "-",
                "→": "to",
                "≠": "!=",
                "≥": ">=",
                "≤": "<=",
                "μ": "micro",
                "α": "alpha",
                "β": "beta",
                "γ": "gamma",
                "’": "'",
                "“": '"',
                "”": '"',
            }
        )
    )


def p(text, style="body"):
    return Paragraph(escape(plain(text)).replace("\n", "<br/>"), STYLES[style])


def table(rows, widths):
    result = Table(
        [[p(value, "cell") for value in row] for row in rows],
        colWidths=widths,
        repeatRows=1,
        hAlign="LEFT",
    )
    result.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), PALE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LINEBELOW", (0, 0), (-1, 0), 0.8, TEAL),
                ("LINEBELOW", (0, 1), (-1, -1), 0.35, colors.HexColor("#D6DFDF")),
            ]
        )
    )
    return result


def box(title, text):
    result = Table([[p(title, "label")], [p(text)]], colWidths=[WIDTH])
    result.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PALE),
                ("LEFTPADDING", (0, 0), (-1, -1), 14),
                ("RIGHTPADDING", (0, 0), (-1, -1), 14),
                ("TOPPADDING", (0, 0), (-1, 0), 12),
                ("BOTTOMPADDING", (0, -1), (-1, -1), 10),
                ("LINEBEFORE", (0, 0), (0, -1), 3, TEAL),
            ]
        )
    )
    return result


def heading(title):
    return [p("AXIS | TARGET DECISION INTELLIGENCE | v1.1", "label"), p(title, "h1")]


STATEMENTS = [
    (
        "CM01",
        "Recent accessible studies strengthen ERAP1-AS biological rationale, "
        "not validated therapeutic benefit.",
        ["wang-2022", "tran-2023", "genomics-2026"],
    ),
    (
        "CM02",
        "Full allotype, HLA/ERAP2 context and peptide substrate must be specified; "
        "a protective allotype is not universally inactive.",
        ["hutchinson-2021", "temponeras-2024", "tedeschi-2023", "melanocyte-2025"],
    ),
    (
        "CM03",
        "Experimental benefit is endpoint-dependent: germline loss reduced rat "
        "arthritis incidence but worsened colon histology.",
        ["tran-2023"],
    ),
    (
        "CM04",
        "New cyclohexyl-acid tools and four ligand-bound structures expand "
        "options, not validated cellular occupancy or clinical readiness.",
        ["cyclohexyl-2024", "maben-2021"],
    ),
    (
        "CM05",
        "Patient PBMC and expanded CD8 experiments add context, not clinical "
        "efficacy or patient-drug engagement.",
        ["wang-2022", "tedeschi-2023"],
    ),
    (
        "CM06",
        "Relevant-exposure engagement and chemical-genetic dependency remain "
        "the discriminating gap for baseline phenotype-producing compounds.",
        ["proteome-2025", "cyclohexyl-2024", "hutchinson-2021"],
    ),
    (
        "CM07",
        "Keep the matched-genotype engagement experiment; sharpen allotype, "
        "substrate, exposure and intracellular-versus-surface controls.",
        [
            "wang-2022",
            "tran-2023",
            "hutchinson-2021",
            "temponeras-2024",
            "proteome-2025",
        ],
    ),
    (
        "CM08",
        "Limited new-series ERAP2/IRAP counter-screen results do not establish "
        "a cross-substrate selectivity ratio or resolve baseline selectivity.",
        ["cyclohexyl-2024"],
    ),
]


def executive():
    first = heading("ERAP1 x axial\nspondyloarthritis") + [
        p("BOUNDED RECENT EVIDENCE ADDENDUM | 5 October 2026", "label"),
        p(D["commercial"]["coverage_wording"], "small"),
        box(
            "CURRENT POSITION",
            "Investigate context-specific ERAP1 modulation. "
            "Therapeutic benefit from ERAP1 inhibition is not established by this "
            "bounded evidence scope.\n\nDecision: resolve the critical uncertainty "
            "first. No canonical DecisionState v2 has been created.",
        ),
        p("What the usable evidence changes", "h2"),
        p(STATEMENTS[0][1] + " [CM01]"),
        p(STATEMENTS[1][1] + " [CM02]"),
        p(STATEMENTS[2][1] + " [CM03]"),
        p(
            "AS is not every axSpA phenotype. Patient-genotype studies and disease "
            "models must not be silently generalized to every patient.",
            "small",
        ),
        p(D["commercial"]["inaccessible_wording"], "small"),
        p("Independent scientific review pending.", "label"),
    ]
    second = heading("Evidence strengthened.\nAttribution still open.") + [
        table(
            [
                ["Recent accessible evidence", "Decision relevance"],
                [
                    "Human genetics, PBMC and expanded CD8 responses",
                    "Stronger target/HLA context, not demonstrated "
                    "drug benefit [CM01/05]",
                ],
                [
                    "Substrate-sensitive recombinant and cellular allotype studies",
                    "Full sequence/context required; no universal "
                    "low-activity label [CM02]",
                ],
                [
                    "Divergent genetic-loss and inhibitor/KO phenotypes",
                    "Inhibition, lifelong loss and allosteric "
                    "modulation differ [CM03/06]",
                ],
                [
                    "New chemical series and regulatory-site complexes",
                    "More assay-specific tools; no intact-cell "
                    "occupancy inferred [CM04]",
                ],
                [
                    "Sparse ERAP2/IRAP counter-screen",
                    "Censored bounds retained; no non-comparable ratio [CM08]",
                ],
            ],
            [220, WIDTH - 220],
        ),
        p("Recent evidence addendum", "h2"),
        p(
            "10 primary studies integrated in the addendum; 21 atomic assertions "
            "and 10 impact assessments remain pending_review. This is not expert "
            "acceptance or a comprehensive review."
        ),
        p(
            "Four insufficient-access candidates remain outside assertion extraction. "
            "Corilagin 2025 is potentially material but its interaction/phenotype "
            "report cannot adjudicate intact-cell engagement without methods."
        ),
        p("Clinical development, not efficacy", "h2"),
        p(
            "EAST1 (NCT07047703), an ERAP1-directed axSpA phase I/II trial, was "
            "registered with no posted results in the consulted record. No AS/axSpA "
            "efficacy results were identified in the searched sources. [REG01]"
        ),
        p(
            "Chemical Learning: MODEL NOT BUILT in the unchanged indexed dataset. "
            "No new standardized measurements imported; recent-literature modelling "
            "eligibility was not assessed. [BASE01]",
            "small",
        ),
    ]
    third = heading("The next discriminating\nexperiment") + [
        box("SAME PRIORITY, REFINED SPECIFICATION", STATEMENTS[6][1] + " [CM07]"),
        p("Measure engagement and phenotype together", "h2"),
        p(
            "Use matched WT/null/rescue backgrounds, vehicle, dose/time, viability "
            "and interference controls. Resolve tested identity/form and validate a "
            "proximal cellular assay first. Specify HLA-B27 subtype, complete ERAP1 "
            "allotype and ERAP2 status. Distinguish intracellular folding/UPR from "
            "surface free-heavy-chain effects. [CM07]"
        ),
        table(
            [
                ["Interpretable result", "Scientific consequence"],
                [
                    "Engagement + dependency + rescue",
                    "Strengthens compound/context-specific ERAP1 attribution; "
                    "translation "
                    "and broader selectivity still need testing.",
                ],
                [
                    "Phenotype persists without ERAP1",
                    "Weakens this compound's ERAP1 explanation, "
                    "not the target universally.",
                ],
                [
                    "Toxicity or invalid assay/genetic model",
                    "No mechanism conclusion; validate controls and repeat.",
                ],
            ],
            [170, WIDTH - 170],
        ),
        p("What remains unresolved", "h2"),
        p(STATEMENTS[5][1] + " [CM06]"),
        p(
            "On-target, off-target, indirect and context-dependent explanations remain "
            "viable. New biology does not automatically select an inhibition strategy."
        ),
        p(
            "Bounded addendum does not replace the earlier failed exhaustive refresh: "
            "INSUFFICIENT REFRESH COMPLETENESS TO ASSESS. Full traceability and "
            "non-adjudicated reports are separated in the full brief.",
            "small",
        ),
        p("Independent scientific review pending.", "label"),
    ]
    return [first, second, third]


def appendix():
    pages = [
        heading("Recent Evidence 2020-2026\nIntegrated-study table")
        + [
            p(
                "All ten entries: primary studies, sufficient inspected "
                "methods/results, "
                "INTEGRATE in this addendum only, pending independent review. Full "
                "experimental context, claim locators and limitations follow.",
                "small",
            ),
            table(
                [["Study / year", "Evidence layers", "Accessibility / impact"]]
                + [
                    [
                        s["id"] + " / " + str(s["year"]),
                        ", ".join(s["layers"]),
                        s["accessibility"]
                        + "; "
                        + s["materiality"]
                        + ": "
                        + s["impact_rationale"],
                    ]
                    for s in STUDIES
                    if s["action"] == "INTEGRATE"
                ],
                [108, 165, WIDTH - 273],
            ),
        ]
    ]
    for offset in (0, 8):
        pages.append(
            heading("Recent Evidence 2020-2026\nBefore / after")
            + [
                p(
                    "Categorical bounded interpretation, "
                    "not numerical maturity scores. "
                    "All inferences pending_review; canonical state unchanged.",
                    "small",
                ),
                table(
                    [["Layer", "Baseline", "Recent / interpretation"]]
                    + [
                        [r[0], r[1], r[2] + "; " + r[3]]
                        for r in D["evidence_matrix"][offset : offset + 8]
                    ],
                    [90, 145, WIDTH - 235],
                ),
            ]
        )
    for offset in (0, 7):
        pages.append(
            heading("Scientific questions\n" + ("Q1-Q7" if not offset else "Q8-Q14"))
            + [
                table(
                    [["ID", "Assessment", "Rationale"]]
                    + [
                        [q["id"], q["status"], q["answer"]]
                        for q in D["questions"][offset : offset + 7]
                    ],
                    [43, 113, WIDTH - 156],
                ),
            ]
        )
    for study in STUDIES:
        if study["action"] != "INTEGRATE":
            continue
        impact = next(i for i in IMPACTS if i["study_id"] == study["id"])
        items = heading("Recent primary evidence\n" + study["id"])
        items += [
            p(study["title"], "h2"),
            p("DOI: " + study["doi"] + " | " + study["accessibility"], "small"),
            p("INTEGRATE: addendum inclusion only. pending_review.", "label"),
            p("Design: " + ", ".join(study["design"]), "small"),
            p("Disease relevance: " + study["disease_relevance"], "small"),
        ]
        items.append(p("Experimental context", "h2"))
        for key, value in study["context"].items():
            value = (
                json.dumps(value, ensure_ascii=False)
                if not isinstance(value, str)
                else value
            )
            items.append(p(key.replace("_", " ") + ": " + value, "small"))
        items.append(
            p("Atomic source assertions (not independent expert approval)", "h2")
        )
        for claim in CLAIMS:
            if claim["study_id"] == study["id"]:
                items.append(p(claim["claim_text"], "small"))
                items.append(
                    p(claim["id"] + " | " + claim["source_locator"]["section"], "small")
                )
        items += [
            p("Evidence impact / limitations", "h2"),
            p(
                impact["impact_direction"]
                + "; "
                + impact["materiality"]
                + ": "
                + impact["rationale"],
                "small",
            ),
            p("; ".join(study["limitations"]), "small"),
        ]
        pages.append(items)
    pages.append(
        heading("Potentially Material -\nNot Fully Adjudicated")
        + [
            p(D["commercial"]["inaccessible_wording"]),
            p(
                "These are access/adjudication records, NOT accepted "
                "source assertions. No conclusion from them resolves "
                "engagement or chooses therapeutic direction."
            ),
        ]
        + [
            item
            for study in STUDIES
            if study["action"] == "INSUFFICIENT_ACCESS"
            for item in [
                p(study["id"] + " | " + study["accessibility"], "h2"),
                p("DOI: " + study["doi"], "small"),
                p(study["rationale"], "small"),
                p(
                    "Reported, not adjudicated: "
                    + study.get(
                        "reported_not_adjudicated", "No new assertions extracted."
                    ),
                    "small",
                ),
            ]
        ]
    )
    pages.append(
        heading("Selection boundaries\n& provenance")
        + [
            p(
                "18 selected candidates from 176 retrieved metadata records. "
                "Eight bounded searches and nine seed-verification queries "
                "do not constitute complete "
                "screening. Default ordering/truncation, accessibility and purposeful "
                "selection can bias this sample. 10 integrate; "
                "1 contextualize; 1 already "
                "indexed; 4 insufficient access; 2 not integrated."
            ),
            p(
                "INTEGRATE studies are detailed individually above. "
                "Complete selected-study table and rationale are in the frozen "
                "study-selection.md/candidate-studies.json.",
                "small",
            ),
            p("Other selected records", "h2"),
        ]
        + [
            p(s["id"] + ": " + s["action"] + ". " + s["rationale"], "small")
            for s in STUDIES
            if s["action"] not in {"INTEGRATE", "INSUFFICIENT_ACCESS"}
        ]
        + [
            p("Inference and source are separate", "h2"),
            p(
                "AI-assisted source extraction and recommendation wording "
                "remain pending independent scientific review. Deterministic "
                "integrity/boundary checks do not approve scientific claims "
                "or independently validate an experiment."
            ),
            p(
                "traceability.json maps each CM conclusion to "
                "study-level AXIS inference, "
                "atomic claim, experiment/context, DOI and section locator. REG01 is a "
                "registration fact with primary registry provenance, not a clinical "
                "source assertion. BASE01 is unchanged baseline learning status.",
                "small",
            ),
            p(
                "Original v1 brief and canonical resources are unchanged. This bounded "
                "addendum does not supersede "
                "INSUFFICIENT REFRESH COMPLETENESS TO ASSESS.",
                "small",
            ),
            p("Independent scientific review pending.", "label"),
        ]
    )
    return pages


def footer(canvas, doc):
    canvas.setStrokeColor(TEAL)
    canvas.line(46, 42, A4[0] - 46, 42)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(GRAY)
    canvas.drawString(46, 28, "AXIS | bounded evidence | independent review pending")
    canvas.drawRightString(A4[0] - 46, 28, f"v1.1 | {doc.page}")


def build(path, pages):
    path.parent.mkdir(parents=True, exist_ok=True)
    story = []
    for number, items in enumerate(pages):
        if number:
            story.append(PageBreak())
        story.extend(items)
        story.append(Spacer(1, 3))
    SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=46,
        rightMargin=46,
        topMargin=45,
        bottomMargin=58,
        title="AXIS ERAP1 axSpA v1.1",
        author="AXIS - Independent scientific review pending",
        invariant=1,
    ).build(story, onFirstPage=footer, onLaterPages=footer)
    return len(PdfReader(path).pages)


def main():
    trace = []
    for identifier, conclusion, studies in STATEMENTS:
        trace.append(
            {
                "commercial_statement_id": identifier,
                "conclusion": conclusion,
                "epistemic_kind": "axis_inference",
                "review_status": "pending_review",
                "impact_ids": [i["id"] for i in IMPACTS if i["study_id"] in studies],
                "source_chain": [
                    {
                        k: c[k]
                        for k in (
                            "id",
                            "study_id",
                            "experiment_id",
                            "experimental_context",
                            "source_locator",
                        )
                    }
                    for c in CLAIMS
                    if c["study_id"] in studies
                ],
                "limitations": [
                    s["limitations"] for s in STUDIES if s["id"] in studies
                ],
            }
        )
    trace += [
        {
            "commercial_statement_id": "REG01",
            "epistemic_kind": "registry_fact",
            "url": "https://clinicaltrials.gov/study/NCT07047703",
            "source": "context-access.json",
            "clinical_efficacy": False,
        },
        {
            "commercial_statement_id": "BASE01",
            "epistemic_kind": "baseline_status",
            "source": "baseline.json",
            "learning": "MODEL NOT BUILT",
        },
    ]
    (OUT / "traceability.json").write_text(json.dumps(trace, indent=2) + "\n")
    paths = [
        OUT / "executive/AXIS-ERAP1-axSpA-Executive-Brief.pdf",
        OUT / "full/AXIS-ERAP1-axSpA-Target-Decision-Brief.pdf",
    ]
    counts = [build(paths[0], executive()), build(paths[1], executive() + appendix())]
    assert counts[0] == 3, counts
    for path in paths:
        text = "\n".join(page.extract_text() for page in PdfReader(path).pages)
        assert "Independent scientific review pending." in text
        assert "bounded addendum" in text
        assert "Not Fully Adjudicated" in text or "potentially material" in text
        assert not re.search(r"evidence updated through 2026", text, re.I)
    manifest = {
        "version": "v1.1",
        "review_status": "pending_review",
        "baseline": read("baseline.json"),
        "addendum_manifest_sha256": hashlib.sha256(
            (PACKAGE / "manifest.json").read_bytes()
        ).hexdigest(),
        "canonical_decision_created": False,
        "outputs": [
            {
                "path": str(p.relative_to(OUT)),
                "pages": n,
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            }
            for p, n in zip(paths, counts, strict=True)
        ],
        "traceability_sha256": hashlib.sha256(
            (OUT / "traceability.json").read_bytes()
        ).hexdigest(),
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
