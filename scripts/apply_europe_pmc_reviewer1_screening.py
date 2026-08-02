from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REVIEW = (
    ROOT
    / "data/analysis/single-cell-validation/CD8-evidence-review/"
    "europe-pmc-2026-07-30"
)
SOURCE = REVIEW / "records-screening.tsv"
OUTPUT = REVIEW / "reviewer-1-screening.tsv"


RETRIEVE = {
    "10.1016/j.isci.2025.112715": "Eligible published cohort; GSE288581.",
    "10.1186/s13075-025-03585-w": "Donor-resolved PBMC CD8 case-control design; processed data unavailable.",
    "10.1038/s12276-025-01619-6": "Primary blood single-cell study with healthy comparison; CD8 and data availability require full-text verification.",
    "10.1007/s10067-025-07549-y": "Eligible donor-resolved PBMC cohort; PRJNA1168183.",
    "10.3389/fimmu.2025.1546429": "Donor-resolved PBMC CITE-seq AS and healthy-control groups; processed data unavailable.",
    "10.1111/jcmm.17159": "Primary PBMC case-control scRNA-seq study; publication focuses on NK cells but reusable CD8 expression requires verification.",
    "10.3389/fimmu.2021.760381": "Primary PBMC single-cell RNA/ATAC study; donor pooling and RNA matrix require full-text verification.",
    "10.3389/fimmu.2022.838636": "Eligible published donor-resolved cohort; GSE194315.",
    "10.1186/s13075-021-02531-w": "Primary circulating immune-cell study with axSpA and control groups; CD8 donor-level compatibility requires verification.",
}


REASONS = {
    "10.1007/s11926-026-01213-3": "Review article; no original case-control expression cohort.",
    "10.1186/s13287-025-04701-y": "Mesenchymal stem-cell experiment; wrong cell population.",
    "10.1177/15578100261424002": "Secondary computational reanalysis; no new independent cohort.",
    "10.1002/advs.202520617": "Enthesis fibroblast/neutrophil study; wrong tissue and primary cell population.",
    "10.1016/j.ard.2026.03.023": "Macrophage and pathological osteogenesis study; wrong primary cell population/outcome.",
    "10.1007/s10067-025-07595-6": "Genetic/causal-inference and secondary single-cell analysis; no new donor-level CD8 cohort.",
    "10.1038/s41413-025-00474-5": "Osteoclast-precursor study; wrong cell population.",
    "10.1002/mco2.759": "Monocyte-focused cohort; no separable predeclared CD8 outcome.",
    "10.1111/jcmm.70206": "Vertebral bone-marrow cohort; wrong tissue for peripheral-blood question.",
    "10.1038/s41598-025-88775-x": "Neutrophil/ferroptosis study; wrong cell population.",
    "10.1063/5.0252297": "Secondary reanalysis of GSE194315 and bulk datasets; duplicate cohort.",
    "10.1007/s10875-025-01961-4": "Monocyte/macrophage NLRP3 study; wrong cell population.",
    "10.1111/1756-185x.70175": "Secondary multi-omics/machine-learning analysis; no new donor-level CD8 cohort.",
    "10.1080/08916934.2024.2445557": "Secondary reanalysis of GSE194315 and bulk datasets; duplicate cohort.",
    "10.1002/art.70069": "Osteogenic arthritis model; disease population not ankylosing spondylitis/axSpA.",
    "10.21203/rs.3.rs-9232122/v1": "Fibroblast/ossification preprint; wrong cell population and tissue.",
    "10.1101/2024.10.21.619465": "Secondary computational pathway/network analysis; no new independent cohort.",
    "10.1007/s00011-026-02257-y": "Ulcerative-colitis multisystem genetic analysis; wrong target population and no primary CD8 cohort.",
    "10.3390/ijms27093860": "Secondary diagnostic-signature analysis; no new independent donor-level CD8 cohort.",
    "10.1080/25785826.2024.2388343": "Review article; no original eligible cohort.",
    "10.3389/fimmu.2024.1454263": "Methods/integration evaluation; no primary AS case-control cohort.",
    "10.1016/j.intimp.2024.112040": "Angiogenesis/syndesmophyte study; no eligible peripheral CD8 case-control outcome.",
    "10.1101/2024.06.17.599349": "Preprint of methods/integration work; no primary eligible cohort.",
    "10.1186/s13020-026-01385-1": "Drug-combination computational framework; no primary eligible cohort.",
    "10.1136/ard-2023-224107": "Neutrophil/mesenchymal-cell study; wrong cell population.",
    "10.1101/2024.09.17.613463": "Psoriasis cohort; wrong disease.",
    "10.1007/s11926-023-01113-w": "Review article; no original eligible cohort.",
    "10.1101/2023.06.10.544264": "Monocyte trained-immunity study; wrong primary cell population.",
    "10.1007/s12016-023-08959-z": "Post-treatment axSpA series without an eligible untreated case-versus-healthy donor comparison.",
    "10.1101/2024.10.09.617402": "Joint-tissue CD8 study; wrong tissue for peripheral-blood question.",
    "10.1002/art.42476": "Th17/CD4-focused study; no predeclared peripheral CD8 outcome.",
    "10.1016/j.jdermsci.2023.07.005": "Psoriasis cohort; wrong disease.",
    "10.1136/annrheumdis-2021-220002": "Enthesis/osteogenesis study; wrong tissue and outcome.",
    "10.3389/fmed.2024.1369341": "Secondary reanalysis of existing public scRNA-seq data; no new independent cohort.",
    "10.1038/s42003-021-02931-3": "Synovial regulatory CD4 T-cell study; wrong tissue and cell population.",
    "10.21203/rs.3.rs-138435/v1": "Preprint duplicate of DOI 10.1186/s13075-021-02531-w.",
    "10.1101/2021.05.31.444674": "Preprint duplicate of DOI 10.1038/s42003-021-02931-3.",
    "10.1002/cyto.a.20505": "Cytometry/transcriptome classification study without single-cell RNA donor-level CD8 outcome.",
}


def main() -> None:
    with SOURCE.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
        fields = list(rows[0])

    decisions = []
    for row in rows:
        doi = row["doi"].lower().strip()
        if doi in RETRIEVE:
            decision = "retrieve_full_text"
            reason = RETRIEVE[doi]
        elif doi in REASONS:
            decision = "exclude_title_abstract"
            reason = REASONS[doi]
        else:
            raise RuntimeError(f"No reviewer-1 decision declared for DOI {doi!r}")
        row["human_reviewer_1"] = decision
        decisions.append(
            {
                "source_id": row["source_id"],
                "pmid": row["pmid"],
                "doi": row["doi"],
                "title": row["title"],
                "reviewer_1_decision": decision,
                "reviewer_1_reason": reason,
            }
        )

    with SOURCE.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)

    with OUTPUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(decisions[0]), delimiter="\t"
        )
        writer.writeheader()
        writer.writerows(decisions)

    retrieve = sum(d["reviewer_1_decision"] == "retrieve_full_text" for d in decisions)
    print(f"Screened {len(decisions)} records: {retrieve} retrieve, {len(decisions)-retrieve} exclude.")


if __name__ == "__main__":
    main()
