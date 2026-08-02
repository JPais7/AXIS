# Generate the small public limma reference used by the offline regression test.
suppressPackageStartupMessages(library(limma))

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 1L) {
  stop("usage: generate-regression-reference.R OUTPUT_TSV")
}
group_case <- c(0, 0, 0, 0, 0, 1, 1, 1, 1, 1)
sex_male <- c(0, 1, 0, 1, 0, 1, 0, 1, 0, 1)
age <- c(22, 35, 41, 29, 50, 25, 38, 46, 33, 55)
batch <- c(1, 1, 2, 2, 3, 1, 2, 2, 3, 3)
design <- cbind(1, group_case, sex_male, age, batch)

values <- matrix(0, nrow = 12, ncol = 10)
for (feature in seq_len(12)) {
  for (sample in seq_len(10)) {
    group_effect <- (-1)^feature * (0.1 + feature * 0.03)
    sex_effect <- ((feature %% 3) - 1) * 0.05
    age_effect <- 0.002 * (1 + feature %% 2)
    batch_effect <- 0.01 * ((feature %% 4) - 1.5)
    residual <- (
      ((feature * 7 + sample * 3) %% 11) - 5
    ) * 0.015 * (1 + feature / 10)
    values[feature, sample] <- (
      5 + feature * 0.2 +
      group_case[sample] * group_effect +
      sex_male[sample] * sex_effect +
      age[sample] * age_effect +
      batch[sample] * batch_effect +
      residual
    )
  }
}
rownames(values) <- sprintf("SYN%02d", seq_len(12))
fit <- lmFit(values, design)
fit <- contrasts.fit(fit, c(0, 1, 0, 0, 0))
fit <- eBayes(fit, proportion = 0.01)
table <- topTable(
  fit,
  number = Inf,
  adjust.method = "BH",
  sort.by = "none"
)
reference <- data.frame(
  feature = rownames(table),
  coefficient = table$logFC,
  statistic = table$t,
  p_value = table$P.Value,
  adjusted_p_value = table$adj.P.Val
)
write.table(
  reference,
  args[[1]],
  sep = "\t",
  quote = FALSE,
  row.names = FALSE
)
