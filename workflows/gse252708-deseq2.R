#!/usr/bin/env Rscript

# Exact negative-binomial sensitivity workflow for GSE252708.
# Requires R, BiocManager and DESeq2. AXIS does not install them implicitly.

suppressPackageStartupMessages(library("DESeq2"))

args <- commandArgs(trailingOnly = TRUE)
data_root <- if (length(args) >= 1) args[[1]] else "data/geo"
study_root <- file.path(data_root, "GSE252708")
counts_path <- file.path(
  study_root, "supplementary", "GSE252708_seq_raw.txt.gz"
)
samples_path <- file.path(
  study_root, "mirna-validation", "sample-sheet.tsv"
)
output_root <- file.path(study_root, "mirna-analysis", "deseq2")
dir.create(output_root, recursive = TRUE, showWarnings = FALSE)

counts_table <- read.delim(
  gzfile(counts_path),
  row.names = 1,
  check.names = FALSE
)
samples <- read.delim(samples_path, stringsAsFactors = FALSE)
rownames(samples) <- samples$participant_id

counts <- as.matrix(counts_table)
storage.mode(counts) <- "integer"
counts <- counts[, colSums(counts) > 0, drop = FALSE]
samples <- samples[colnames(counts), , drop = FALSE]
samples$age <- as.numeric(samples$age)
samples$crp <- log1p(as.numeric(samples$crp))
samples$sex <- factor(samples$sex)

comparisons <- list(
  all_axspa_vs_hc = c("r-axspa", "nr-axspa"),
  radiographic_axspa_vs_hc = c("r-axspa"),
  nonradiographic_axspa_vs_hc = c("nr-axspa")
)
designs <- list(
  unadjusted = ~ condition,
  age_sex = ~ age + sex + condition,
  age_sex_crp = ~ age + sex + crp + condition
)

summary_rows <- list()
for (comparison_name in names(comparisons)) {
  allowed <- c(comparisons[[comparison_name]], "hc")
  selected <- samples$diagnosis %in% allowed
  comparison_counts <- counts[, selected, drop = FALSE]
  comparison_samples <- droplevels(samples[selected, , drop = FALSE])
  comparison_samples$condition <- factor(
    ifelse(comparison_samples$diagnosis == "hc", "control", "case"),
    levels = c("control", "case")
  )

  for (model_name in names(designs)) {
    dds <- DESeqDataSetFromMatrix(
      countData = comparison_counts,
      colData = comparison_samples,
      design = designs[[model_name]]
    )
    dds <- DESeq(dds, quiet = TRUE)
    result <- results(
      dds,
      contrast = c("condition", "case", "control"),
      alpha = 0.05
    )
    result_table <- data.frame(
      mirna = rownames(result),
      as.data.frame(result),
      check.names = FALSE
    )
    result_table <- result_table[
      !is.na(result_table$baseMean) & result_table$baseMean > 10,
    ]
    result_table <- result_table[
      order(result_table$padj, na.last = TRUE),
    ]
    output_path <- file.path(
      output_root,
      paste0(comparison_name, "__", model_name, ".tsv")
    )
    write.table(
      result_table,
      output_path,
      sep = "\t",
      quote = FALSE,
      row.names = FALSE
    )
    summary_rows[[length(summary_rows) + 1]] <- data.frame(
      comparison = comparison_name,
      model = model_name,
      cases = sum(comparison_samples$condition == "case"),
      controls = sum(comparison_samples$condition == "control"),
      tested = nrow(result_table),
      significant = sum(result_table$padj <= 0.05, na.rm = TRUE)
    )
  }
}

write.table(
  do.call(rbind, summary_rows),
  file.path(output_root, "summary.tsv"),
  sep = "\t",
  quote = FALSE,
  row.names = FALSE
)
