# Differential-expression comparison v2: internal partial run

This run is an internal AI execution, not one of the two independent reviewer
runs required for publication.

## Completed

AXIS and the frozen manual Welch workflow both analyzed GSE18781/GPL570 using
the same 18 cases and 25 controls. AXIS completed in 3.258 seconds. The manual
workflow completed in 4.035 seconds with a peak of 165,763,497 Python-traced
bytes.

Across 54,675 shared probes, case-minus-control effects had Spearman correlation
approximately 1.0 and identical direction for every probe. This is expected
because both calculate the same group means.

The top-100 adjusted-p-value sets overlapped by 2 probes, whereas the top-500
sets overlapped by 361 probes. This difference is methodological: AXIS used its
documented moderated general linear model and the manual comparator used Welch
t-tests. It is not evidence that either list is biological truth.

## Incomplete

GEO2R loaded the accession but normal browser interaction could not finish the
43-sample assignment. ExpressAnalyst was accessible but its single-table action
timed out before upload. No hidden state manipulation or cross-tool repair was
used. The four-workflow comparison remains incomplete and no superiority claim
is permitted.
