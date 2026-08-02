# Frozen local reproduction of the GEO2R limma core for GSE18781.
suppressPackageStartupMessages(library(limma))

args <- commandArgs(trailingOnly = FALSE)
file_arg <- sub("--file=", "", args[grep("^--file=", args)])
script_dir <- dirname(normalizePath(file_arg))
root <- normalizePath(file.path(script_dir, "..", "..", "..", ".."))
prepared <- file.path(
  root, "data", "geo", "GSE18781", "prepared", "GSE18781_series_matrix"
)

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
stopifnot(ncol(cases) == 18L, ncol(controls) == 25L)

expression <- as.matrix(cbind(cases, controls))
group <- factor(
  c(rep("case", ncol(cases)), rep("control", ncol(controls))),
  levels = c("control", "case")
)
design <- model.matrix(~ 0 + group)
colnames(design) <- levels(group)
fit <- lmFit(expression, design)
contrast <- makeContrasts(case - control, levels = design)
fit <- contrasts.fit(fit, contrast)
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
  average_expression = table$AveExpr,
  t = table$t,
  p_value = table$P.Value,
  adjusted_p_value = table$adj.P.Val,
  B = table$B,
  direction = ifelse(
    table$logFC > 0,
    "higher_in_case",
    ifelse(table$logFC < 0, "lower_in_case", "no_difference")
  ),
  check.names = FALSE
)
write.table(
  results,
  file.path(script_dir, "differential-expression.tsv"),
  sep = "\t",
  quote = FALSE,
  row.names = FALSE
)
writeLines(capture.output(sessionInfo()), file.path(script_dir, "session-info.txt"))

elapsed <- unname((proc.time() - started)[["elapsed"]])
methods <- list(
  accession = "GSE18781",
  platform = "GPL570",
  status = "local_limma_reproduction_not_geo2r_server",
  case_samples = ncol(cases),
  control_samples = ncol(controls),
  design = "~0 + group",
  contrast = "case - control",
  empirical_bayes_proportion = 0.01,
  multiple_testing = "Benjamini-Hochberg",
  elapsed_seconds = elapsed,
  R = as.character(getRversion()),
  limma = as.character(packageVersion("limma"))
)
method_lines <- paste(names(methods), unlist(methods), sep = "\t")
writeLines(method_lines, file.path(script_dir, "methods.tsv"))
