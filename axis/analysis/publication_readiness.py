"""Build a data-bound manuscript draft and operational RT-qPCR protocol."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class PublicationReadinessRun:
    manuscript_path: Path
    protocol_path: Path
    checklist_path: Path
    summary_path: Path


class PublicationReadinessBuilder:
    """Render publication documents from frozen evidence, not hand-entered claims."""

    def build(
        self,
        *,
        hierarchical_path: str | Path,
        context_path: str | Path,
        decision_path: str | Path,
        criteria_path: str | Path,
        output_root: str | Path = Path("data/publication/ddx24-study"),
    ) -> PublicationReadinessRun:
        hierarchical = {
            row["gene_symbol"]: row for row in self._read(Path(hierarchical_path))
        }
        contexts = self._read(Path(context_path))
        decision = json.loads(Path(decision_path).read_text(encoding="utf-8"))
        criteria = self._read(Path(criteria_path))
        destination = Path(output_root)
        destination.mkdir(parents=True, exist_ok=True)
        manuscript_path = destination / "manuscript-draft.md"
        protocol_path = destination / "rt-qpcr-operational-protocol.md"
        checklist_path = destination / "manuscript-completion-checklist.tsv"
        summary_path = destination / "publication-readiness.json"
        manuscript_path.write_text(
            self._manuscript(hierarchical, contexts), encoding="utf-8"
        )
        protocol_path.write_text(
            self._protocol(criteria), encoding="utf-8"
        )
        checklist = self._checklist()
        self._write(checklist_path, checklist)
        summary_path.write_text(
            json.dumps(
                {
                    "created_at": datetime.now(UTC).isoformat(),
                    "manuscript_status": "complete_computational_draft",
                    "laboratory_protocol_status": "ready_for_lab_review",
                    "computational_status": decision["computational_status"],
                    "therapeutic_status": decision["therapeutic_status"],
                    "remaining_before_submission": [
                        row["item"]
                        for row in checklist
                        if row["status"] != "complete"
                    ],
                    "warning": (
                        "The manuscript is a secondary computational study, "
                        "not a clinical or therapeutic validation."
                    ),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return PublicationReadinessRun(
            manuscript_path=manuscript_path,
            protocol_path=protocol_path,
            checklist_path=checklist_path,
            summary_path=summary_path,
        )

    @staticmethod
    def _manuscript(
        evidence: dict[str, dict[str, str]],
        contexts: list[dict[str, str]],
    ) -> str:
        ddx = evidence["DDX24"]
        ada = evidence["ADA"]
        ddx_context = {
            row["context"]: row
            for row in contexts
            if row["gene_symbol"] == "DDX24"
        }
        cd8 = ddx_context["CD8_single_cell"]
        array = ddx_context["peripheral_blood_microarray"]
        sequencing = ddx_context["whole_blood_RNA_sequencing"]
        title = (
            "# Recurrent context-dependent reduction of DDX24 in "
            "ankylosing spondylitis\n"
        )
        return title + f"""

## Abstract

### Background

Ankylosing spondylitis is an immune-mediated disease with heterogeneous blood
transcriptomic findings. We evaluated whether DDX24 shows reproducible,
cell-contextual expression differences that justify independent functional
testing.

### Methods

We performed a reproducible secondary integration of seven independent human
case-control cohorts. Donors, never cells, were the statistical units.
Compatible effects were pooled only within two predeclared strata:
donor-pseudobulk CD8 single-cell RNA sequencing and normalized peripheral-blood
microarrays. Incompatible whole-blood RNA-sequencing scales were summarized
directionally. Batch adjustment, leave-one-participant-out sensitivity and
cross-context concordance were assessed. ADA was retained as a contextual
comparison target.

### Results

The analysis included {ddx['independent_cohorts']} independent cohorts and
{ddx['participants']} participants. DDX24 was lower in cases in
{ddx['lower_in_case_cohorts']} of {ddx['independent_cohorts']} cohorts. Across
two independent CD8 cohorts ({cd8['participants']} participants), the pooled
effect was {float(cd8['pooled_effect']):.3f} log2-CPM
(p={float(cd8['pooled_p_value']):.3g}). Three peripheral-blood microarray
cohorts ({array['participants']} participants) were directionally concordant,
although the random-effects result was imprecise
(effect={float(array['pooled_effect']):.3f},
p={float(array['pooled_p_value']):.3g}) and heterogeneous. Two whole-blood
RNA-sequencing cohorts were directionally mixed. ADA was mixed across contexts
({ada['lower_in_case_cohorts']} of {ada['independent_cohorts']} cohorts lower).

### Conclusions

DDX24 shows a recurrent, within-CD8 reduction in ankylosing spondylitis and
broader directional support across blood cohorts. The evidence supports a
falsification-focused laboratory study but does not establish causality,
druggability or therapeutic efficacy.

## Introduction

Blood transcriptomic studies of ankylosing spondylitis vary in participant
selection, cellular composition and assay technology. Pooling all such effects
into one estimate can obscure genuine cell-state specificity. DDX24 emerged
from the AXIS discovery workflow as a recurrent candidate and is biologically
relevant to innate RNA-sensing pathways. The present study asked a narrower
question: is reduced DDX24 expression reproducible within human peripheral
CD8 T-cell populations, and is its direction supported in independent blood
cohorts?

## Methods

### Design and eligibility

Public human case-control transcriptomic cohorts were eligible when disease and
control groups could be separated at participant level. Repeated assays,
technical libraries and cells were not counted as independent observations.
Studies without healthy controls, pooled participants without donor resolution,
or non-expression assays were excluded from inferential synthesis.

### Target and outcomes

DDX24 and its expected lower-in-case direction were frozen before the next
dataset. The primary outcome was case-minus-control DDX24 expression in
memory/effector CD8 cells. ADA was analysed identically as a comparison target.

### Statistical synthesis

Within compatible strata, inverse-variance random-effects models were used.
CD8 effects were derived from donor pseudobulk log2-CPM. Microarray effects
were case-minus-control normalized log expression. Whole-blood FPKM and
long-read TPM studies were reported directionally and were not pooled with
CD8 or microarray effects. No global cross-platform effect or p-value was
estimated.

### Robustness and confounding

GSE194315 was adjusted using available processing-batch principal components
and analysed separately by cell type. Each participant was omitted in turn.
GSE288581 was similarly evaluated by leave-one-donor-out analysis. Age, sex,
medication and disease activity were unavailable in the principal single-cell
deposit and were retained as unresolved limitations.

## Results

### CD8-specific evidence

Both CD8 cohorts showed lower DDX24 expression in cases. The pooled CD8
estimate excluded zero, and every donor omission in the external cohort
preserved the direction. In GSE194315, CD8 TEM and CD8 Naive directions also
persisted after processing-batch adjustment and participant omission.

### Evidence across blood contexts

All three microarray cohorts showed lower DDX24 expression, but magnitude varied
substantially and the random-effects confidence interval included zero. The
whole-blood RNA-sequencing stratum was mixed
({sequencing['lower_in_case_cohorts']} lower and
{sequencing['higher_in_case_cohorts']} higher). Consequently, the evidence is
best interpreted as a robust CD8 association with broader but heterogeneous
blood support.

### Comparison target

ADA did not reproduce the same cross-context pattern. Its direction differed
between CD8 and microarray strata, supporting the interpretation that the DDX24
result is not merely a universal consequence of combining all blood datasets.

## Discussion

The main contribution is not a new global transcriptomic signature, but a
carefully bounded observation: DDX24 is repeatedly lower within CD8 populations
from people with ankylosing spondylitis. Participant-level analyses reduce the
risk of cell-level pseudoreplication, while the independent sorted-CD8 cohort
reduces reliance on one atlas. Nevertheless, residual clinical confounding,
small external cohorts and cross-platform heterogeneity remain.

The result should be used to design a falsification experiment. An initial
RT-qPCR study in isolated CD8 cells can test whether the direction survives
prospective matching and clinical metadata collection. Functional restoration
experiments should proceed only after expression replication and must include
fitness and nonspecific RNA-processing safety endpoints.

## Limitations

Age, sex, medication and disease activity could not be adjusted consistently.
The CD8 meta-analysis contains only two independent cohorts. Whole-blood
RNA-sequencing studies disagree directionally. No human genetic association
currently establishes DDX24 causality, and no perturbation result establishes
therapeutic direction.

## Data and code availability

All derived tables, frozen inputs, checksums and analysis code are stored in the
AXIS project. Public source accessions and eligibility decisions are preserved
in the reproducibility manifest.

## Provisional title and claims

Allowed claim: “DDX24 is recurrently reduced within CD8 T-cell populations in
ankylosing spondylitis and merits prospective falsification.”

Prohibited claims: DDX24 causes ankylosing spondylitis; DDX24 is a validated
therapeutic target; restoring DDX24 will benefit patients.
"""

    @staticmethod
    def _protocol(criteria: list[dict[str, str]]) -> str:
        locked = "\n".join(
            f"- **{row['criterion']}** — confirm: {row['confirmation']}; "
            f"stop/refute: {row['refutation_or_stop']}."
            for row in criteria
        )
        return f"""# Operational protocol: prospective DDX24 RT-qPCR falsification

## Objective

Test whether DDX24 RNA expression is lower in prospectively collected,
participant-resolved peripheral-blood CD8 T cells from people with
clinician-confirmed axial spondyloarthritis than from matched healthy controls.

## Status and oversight

This is an expression-replication pilot, not treatment research. Obtain ethics
approval, informed consent, laboratory biosafety approval and a sample-handling
plan before recruitment. A qualified clinical laboratory must review and
approve this protocol.

## Design

- Recruit at least 6 independent cases and 6 independent controls.
- Match or frequency-balance age band and sex.
- Record age, sex, HLA-B27, disease activity, current medication, infection
  status, collection time and processing batch.
- Treat the human participant as the experimental unit.
- Process cases and controls in balanced batches.
- Randomize sample order within batch and analyse under blinded identifiers.
- Do not replace participants after examining DDX24 results unless a
  predeclared sample-quality criterion fails.

## Eligibility

Cases require clinician-confirmed axial spondyloarthritis. Controls must have no
known inflammatory rheumatic disease. Exclude active infection, missing
participant-level metadata, inadequate blood volume, or viability below the
laboratory's preapproved threshold.

## Sample processing

1. Collect peripheral blood using one tube type and a fixed collection window.
2. Record time from collection to processing.
3. Isolate PBMCs with the laboratory's validated procedure.
4. Enrich or sort CD3-positive, CD8-positive T cells using one frozen method.
5. Record yield, viability and CD8 purity for every participant.
6. Extract total RNA with DNase treatment under a single validated SOP.
7. Measure RNA quantity and integrity using the same instruments and thresholds.
8. Store RNA under documented conditions and limit freeze-thaw cycles.

Exact reagent brands, centrifugation settings and instrument programs must come
from the performing laboratory's validated SOPs rather than being improvised
from this computational protocol.

## RT-qPCR assay qualification

- Design at least two DDX24 primer pairs spanning exon junctions.
- Verify specificity in silico and by a single product/melt profile.
- Determine amplification efficiency using a dilution series; freeze the
  accepted pair before unblinding.
- Use no-template and no-reverse-transcriptase controls.
- Pre-evaluate at least three candidate reference genes and retain two that are
  stable across case/control status and processing batches.
- Do not select reference genes based on which combination favours DDX24.
- Run technical replicates, but aggregate them before participant-level
  inference.

Primer sequences and cycling conditions remain deliberately unset until assay
qualification by the performing laboratory.

## Primary endpoint

The primary endpoint is participant-level normalized DDX24 expression,
calculated from efficiency-aware delta-Cq values relative to the geometric mean
of two frozen reference genes. Higher normalized delta-Cq must be mapped to the
expression direction consistently before unblinding.

## Quality control

Exclude a measurement only for frozen technical failures: failed controls,
non-specific amplification, efficiency outside the laboratory-approved range,
insufficient RNA, unacceptable replicate dispersion or failed purity/viability.
Retain biological outliers unless a predeclared technical failure is documented.
Report all exclusions and repeat measurements.

## Statistical analysis

Use one value per participant. The primary model is normalized expression as a
function of disease group plus prespecified age, sex and processing batch, with
medication and disease activity included when the sample size and variation
permit. Report effect, 95% confidence interval and exact p-value. Show all
participant values. Provide an unadjusted estimate, the prespecified adjusted
estimate and leave-one-participant-out sensitivity. Do not use post-hoc subgroup
searches as confirmation.

## Frozen decision gates

{locked}

## Interpretation

Advancement requires the expected direction, acceptable uncertainty and
participant-level stability. A null or opposite adequately powered result is a
valid falsification outcome. Even successful expression replication does not
validate therapeutic restoration; it only permits a separately approved
functional pilot.
"""

    @staticmethod
    def _checklist() -> list[dict[str, object]]:
        return [
            {"item": "computational_results_frozen", "status": "complete"},
            {"item": "reproducibility_manifest", "status": "complete"},
            {"item": "manuscript_first_draft", "status": "complete"},
            {"item": "figures_and_captions", "status": "pending"},
            {"item": "complete_reference_library", "status": "pending"},
            {"item": "second_scientific_reviewer", "status": "pending"},
            {"item": "journal_selection_and_formatting", "status": "pending"},
            {"item": "ethics_approval_for_new_samples", "status": "external"},
            {"item": "laboratory_SOP_review", "status": "external"},
            {"item": "validated_DDX24_primers", "status": "external"},
        ]

    @staticmethod
    def _read(path: Path) -> list[dict[str, str]]:
        with path.open(encoding="utf-8", newline="") as source:
            return list(csv.DictReader(source, delimiter="\t"))

    @staticmethod
    def _write(path: Path, rows: list[dict[str, object]]) -> None:
        with path.open("w", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(
                target,
                fieldnames=tuple(rows[0]),
                delimiter="\t",
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(rows)
