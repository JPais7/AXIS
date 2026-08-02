# Reproduce the frozen unadjusted AXIS contrast with native limma.
suppressPackageStartupMessages(library(limma))

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 3L) {
  stop("usage: analyze-limma.R ACCESSION PREPARED_DIRECTORY OUTPUT_DIRECTORY")
}
accession <- args[[1]]
prepared <- normalizePath(args[[2]])
output <- args[[3]]
dir.create(output, recursive = TRUE, showWarnings = FALSE)

started <- proc.time()
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
group <- factor(
  c(rep("case", ncol(cases)), rep("control", ncol(controls))),
  levels = c("control", "case")
)
design <- model.matrix(~ 0 + group)
colnames(design) <- levels(group)
fit <- lmFit(expression, design)
fit <- contrasts.fit(fit, makeContrasts(case - control, levels = design))
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
  gzfile(file.path(output, "limma-results.tsv.gz")),
  sep = "\t",
  quote = FALSE,
  row.names = FALSE
)
elapsed <- unname((proc.time() - started)[["elapsed"]])
methods <- data.frame(
  accession = accession,
  case_samples = ncol(cases),
  control_samples = ncol(controls),
  design = "~0 + group",
  contrast = "case - control",
  elapsed_seconds = elapsed,
  R = as.character(getRversion()),
  limma = as.character(packageVersion("limma"))
)
write.table(
  methods,
  file.path(output, "methods.tsv"),
  sep = "\t",
  quote = FALSE,
  row.names = FALSE
)
