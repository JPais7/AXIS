# Native limma validation of the adjusted GSE73754 AXIS model.
suppressPackageStartupMessages(library(limma))

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 3L) {
  stop(
    "usage: analyze-limma-adjusted.R PREPARED_DIRECTORY SAMPLE_SHEET OUTPUT_DIRECTORY"
  )
}
prepared <- normalizePath(args[[1]])
sample_sheet_path <- normalizePath(args[[2]])
output <- args[[3]]
dir.create(output, recursive = TRUE, showWarnings = FALSE)

cases <- read.delim(
  gzfile(file.path(prepared, "case-matrix.tsv.gz")),
  row.names = 1,
  check.names = FALSE
)
controls <- read.delim(
  gzfile(file.path(prepared, "control-matrix.tsv.gz")),
  row.names = 1,
  check.names = FALSE
)
stopifnot(identical(rownames(cases), rownames(controls)))
expression <- as.matrix(cbind(cases, controls))
metadata <- read.delim(sample_sheet_path, stringsAsFactors = FALSE)
metadata <- metadata[match(colnames(expression), metadata$sample_id), ]
stopifnot(!anyNA(metadata$sample_id))

design <- cbind(
  intercept = 1,
  group_case = as.numeric(metadata$group == "case"),
  "sex[Male]" = as.numeric(metadata$sex == "Male"),
  age = as.numeric(metadata$age),
  batch = as.numeric(metadata$batch)
)
stopifnot(qr(design)$rank == ncol(design))
fit <- lmFit(expression, design)
contrast <- c(0, 1, 0, 0, 0)
fit <- contrasts.fit(fit, contrasts = contrast)
fit <- eBayes(fit, proportion = 0.01)
table <- topTable(
  fit,
  number = Inf,
  adjust.method = "BH",
  sort.by = "none"
)
results <- data.frame(
  probe_id = rownames(table),
  mean_difference = table$logFC,
  p_value = table$P.Value,
  adjusted_p_value = table$adj.P.Val,
  check.names = FALSE
)
write.table(
  results,
  gzfile(file.path(output, "limma-adjusted-results.tsv.gz")),
  sep = "\t",
  quote = FALSE,
  row.names = FALSE
)
write.table(
  data.frame(
    accession = "GSE73754",
    case_samples = sum(metadata$group == "case"),
    control_samples = sum(metadata$group == "control"),
    design = "intercept + group_case + sex[Male] + age + numeric batch",
    contrast = "group_case",
    R = as.character(getRversion()),
    limma = as.character(packageVersion("limma"))
  ),
  file.path(output, "adjusted-methods.tsv"),
  sep = "\t",
  quote = FALSE,
  row.names = FALSE
)
