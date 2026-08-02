"""Finalize publication figures, references and independent-review materials."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


@dataclass(frozen=True)
class ArticleFinalizationRun:
    figures: int
    references: int
    figures_dir: Path
    bibliography_path: Path
    captions_path: Path
    review_path: Path
    summary_path: Path


class ArticleFinalizer:
    """Create publication assets from the frozen cohort and context tables."""

    COLORS = {
        "CD8_single_cell": "#2364AA",
        "peripheral_blood_microarray": "#3DA35D",
        "whole_blood_RNA_sequencing": "#F28E2B",
    }

    def finalize(
        self,
        *,
        cohort_path: str | Path,
        context_path: str | Path,
        output_root: str | Path = Path("data/publication/ddx24-study"),
    ) -> ArticleFinalizationRun:
        cohorts = self._read(Path(cohort_path))
        contexts = self._read(Path(context_path))
        destination = Path(output_root)
        figures = destination / "figures"
        figures.mkdir(parents=True, exist_ok=True)
        self._cohort_figure(cohorts, figures / "figure-1-cohort-effects.png")
        self._context_figure(contexts, figures / "figure-2-context-concordance.png")
        self._study_table(cohorts, destination / "study-characteristics.tsv")
        bibliography_path = destination / "references.bib"
        references = self._references()
        bibliography_path.write_text(references, encoding="utf-8")
        captions_path = destination / "figure-captions.md"
        captions_path.write_text(self._captions(), encoding="utf-8")
        review_path = destination / "external-scientific-review-form.md"
        review_path.write_text(self._review_form(), encoding="utf-8")
        summary_path = destination / "article-finalization.json"
        summary_path.write_text(
            json.dumps(
                {
                    "created_at": datetime.now(UTC).isoformat(),
                    "figures": 2,
                    "references": 7,
                    "external_review_status": "awaiting_independent_reviewer",
                    "figure_policy": (
                        "Effects are displayed within assay contexts; no "
                        "cross-platform pooled estimate is drawn."
                    ),
                    "submission_blockers": [
                        "independent scientific review",
                        "author and affiliation details",
                        "journal-specific formatting",
                        "final reference verification by a human author",
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return ArticleFinalizationRun(
            figures=2,
            references=7,
            figures_dir=figures,
            bibliography_path=bibliography_path,
            captions_path=captions_path,
            review_path=review_path,
            summary_path=summary_path,
        )

    def _cohort_figure(self, rows: list[dict[str, str]], path: Path) -> None:
        selected = [row for row in rows if row["gene_symbol"] == "DDX24"]
        contexts = (
            "CD8_single_cell",
            "peripheral_blood_microarray",
            "whole_blood_RNA_sequencing",
        )
        figure, axes = plt.subplots(1, 3, figsize=(12.2, 4.4), sharey=False)
        titles = ("CD8 single-cell", "Blood microarray", "Whole-blood RNA-seq")
        for axis, context, title in zip(axes, contexts, titles, strict=True):
            subset = [row for row in selected if row["context"] == context]
            effects = [float(row["effect"]) for row in subset]
            positions = np.arange(len(subset))
            axis.barh(
                positions,
                effects,
                color=self.COLORS[context],
                alpha=0.86,
                height=0.62,
            )
            axis.axvline(0, color="#333333", linewidth=1, linestyle="--")
            axis.set_yticks(positions, [row["cohort"] for row in subset])
            axis.invert_yaxis()
            axis.set_title(title, fontsize=11, weight="bold")
            axis.set_xlabel("Case − control effect")
            axis.grid(axis="x", alpha=0.2)
            for position, effect in zip(positions, effects, strict=True):
                tiny = abs(effect) < 0.04
                axis.text(
                    effect - 0.025 if tiny else effect / 2,
                    position,
                    f"{effect:.2f}",
                    va="center",
                    ha="right" if tiny else "center",
                    fontsize=8,
                    color="#222222" if tiny else "white",
                    weight="bold",
                )
        figure.suptitle(
            "DDX24 effects by independent cohort and compatible assay context",
            fontsize=13,
            weight="bold",
        )
        figure.text(
            0.5,
            0.01,
            "Effects are not pooled across panels because assay scales differ.",
            ha="center",
            fontsize=9,
            color="#555555",
        )
        figure.tight_layout(rect=(0, 0.05, 1, 0.94))
        figure.savefig(path, dpi=300, bbox_inches="tight")
        plt.close(figure)

    def _context_figure(self, rows: list[dict[str, str]], path: Path) -> None:
        contexts = (
            "CD8_single_cell",
            "peripheral_blood_microarray",
            "whole_blood_RNA_sequencing",
        )
        genes = ("DDX24", "ADA")
        values = np.asarray(
            [
                [
                    int(
                        next(
                            row["lower_in_case_cohorts"]
                            for row in rows
                            if row["gene_symbol"] == gene
                            and row["context"] == context
                        )
                    )
                    / int(
                        next(
                            row["cohorts"]
                            for row in rows
                            if row["gene_symbol"] == gene
                            and row["context"] == context
                        )
                    )
                    for context in contexts
                ]
                for gene in genes
            ]
        )
        figure, axis = plt.subplots(figsize=(8.2, 3.4))
        image = axis.imshow(values, cmap="Blues", vmin=0, vmax=1, aspect="auto")
        axis.set_xticks(
            range(3), ("CD8 single-cell", "Blood microarray", "Blood RNA-seq")
        )
        axis.set_yticks(range(2), genes)
        axis.set_title(
            "Fraction of cohorts with lower expression in cases",
            weight="bold",
        )
        for row_index in range(2):
            for column_index in range(3):
                axis.text(
                    column_index,
                    row_index,
                    f"{values[row_index, column_index]:.0%}",
                    ha="center",
                    va="center",
                    color=(
                        "white"
                        if values[row_index, column_index] > 0.55
                        else "#222222"
                    ),
                    weight="bold",
                )
        figure.colorbar(image, ax=axis, label="Directional concordance")
        figure.tight_layout()
        figure.savefig(path, dpi=300, bbox_inches="tight")
        plt.close(figure)

    @staticmethod
    def _study_table(rows: list[dict[str, str]], path: Path) -> None:
        ddx = [row for row in rows if row["gene_symbol"] == "DDX24"]
        fields = (
            "cohort",
            "context",
            "assay",
            "case_samples",
            "control_samples",
            "effect",
            "p_value",
            "direction",
            "inferential_role",
        )
        with path.open("w", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(
                target, fieldnames=fields, delimiter="\t", lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows({key: row[key] for key in fields} for row in ddx)

    @staticmethod
    def _references() -> str:
        return """@article{Ma2013DDX24,
  author = {Ma, Z. and others},
  title = {DDX24 Negatively Regulates Cytosolic RNA-Mediated Innate Immune Signaling},
  journal = {PLoS Pathogens},
  year = {2013},
  pmid = {24204270},
  url = {https://pmc.ncbi.nlm.nih.gov/articles/PMC3814876/}
}

@article{Alber2022CITEseq,
  author = {Alber, Samuel and others},
  title = {Single Cell Transcriptome and Surface Epitope Analysis of Ankylosing
           Spondylitis Facilitates Disease Classification by Machine Learning},
  journal = {Frontiers in Immunology},
  year = {2022},
  doi = {10.3389/fimmu.2022.838636},
  pmid = {35634297}
}

@article{Tang2025CD8,
  author = {Tang, Michael and Qaiyum, Zoya and Lim, Melissa and Inman, Robert D.},
  title = {Single cell immune profiling in ankylosing spondylitis reveals
           resistance of CD8+ T cells to immune exhaustion},
  journal = {iScience},
  year = {2025},
  volume = {28},
  pages = {112715},
  doi = {10.1016/j.isci.2025.112715}
}

@article{Mauro2021AS,
  author = {Mauro, D. and others},
  title = {Ankylosing spondylitis: an autoimmune or autoinflammatory disease?},
  journal = {Nature Reviews Rheumatology},
  year = {2021},
  volume = {17},
  pages = {387--404},
  doi = {10.1038/s41584-021-00625-y}
}

@article{Page2021PRISMA,
  author = {Page, Matthew J. and others},
  title = {The PRISMA 2020 statement: an updated guideline for reporting
           systematic reviews},
  journal = {BMJ},
  year = {2021},
  volume = {372},
  pages = {n71},
  doi = {10.1136/bmj.n71}
}

@misc{GEO194315,
  title = {GSE194315: RNA and surface epitope sequencing of single cells
           involved in spondyloarthritis},
  publisher = {NCBI Gene Expression Omnibus},
  url = {https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE194315}
}

@misc{GEO288581,
  title = {GSE288581: Single Cell Immune Profiling in Ankylosing Spondylitis},
  publisher = {NCBI Gene Expression Omnibus},
  url = {https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE288581}
}
"""

    @staticmethod
    def _captions() -> str:
        return """# Figure captions

## Figure 1

DDX24 case-minus-control effects in seven independent cohorts, separated into
compatible assay contexts. Negative values indicate lower expression in cases.
Effects are displayed on each study's normalized log-expression scale and are
not pooled across panels. Donors, rather than cells, are the statistical units
in single-cell cohorts.

## Figure 2

Directional concordance for DDX24 and the contextual comparison target ADA.
Cells show the fraction of independent cohorts within each assay context whose
case-minus-control effect was below zero. This display summarizes direction,
not statistical significance or a cross-platform pooled effect.
"""

    @staticmethod
    def _review_form() -> str:
        return """# Independent scientific review form

Reviewer name:
Affiliation:
Date:
Relevant expertise:
Conflict of interest:

## Required assessment

For each item, mark: acceptable / minor revision / major revision / unclear.

1. Is the biological question sufficiently narrow and predeclared?
2. Are cohorts independent and counted once?
3. Are cells, technical libraries and participants distinguished correctly?
4. Is pooling restricted to compatible assay contexts?
5. Are heterogeneity and contradictory cohorts represented fairly?
6. Are the CD8 effect and its uncertainty interpreted proportionately?
7. Does ADA function as a contextual comparison without being overstated?
8. Are age, sex, medication and disease activity limitations sufficiently clear?
9. Does the manuscript avoid causal and therapeutic claims?
10. Are figures faithful to the underlying tables?
11. Are methods detailed enough for computational reproduction?
12. Is the proposed RT-qPCR study a valid next falsification step?

## Reviewer conclusions

Major strengths:

Major weaknesses:

Required analyses or corrections:

Claims that should be weakened or removed:

Recommendation: suitable for submission / revise and re-review / not suitable.

Signature or documented electronic approval:
"""

    @staticmethod
    def _read(path: Path) -> list[dict[str, str]]:
        with path.open(encoding="utf-8", newline="") as source:
            return list(csv.DictReader(source, delimiter="\t"))
