"""Limma-style empirical-Bayes variance moderation for two-group designs."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import optimize, special, stats  # type: ignore[import-untyped]


@dataclass(frozen=True)
class ModeratedTest:
    statistic: np.ndarray
    p_value: np.ndarray
    prior_variance: float
    prior_degrees_of_freedom: float
    residual_degrees_of_freedom: int


@dataclass(frozen=True)
class ModeratedLinearModel:
    coefficient: np.ndarray
    statistic: np.ndarray
    p_value: np.ndarray
    prior_variance: float
    prior_degrees_of_freedom: float
    residual_degrees_of_freedom: int
    design_rank: int


def moderated_linear_model(
    values: np.ndarray,
    design: np.ndarray,
    contrast: np.ndarray,
) -> ModeratedLinearModel:
    """Fit a feature-wise linear model with a moderated contrast test."""
    if values.shape[1] != design.shape[0]:
        raise ValueError("expression samples and design rows do not align")
    rank = int(np.linalg.matrix_rank(design))
    if rank != design.shape[1]:
        raise ValueError("design matrix is rank deficient")
    residual_df = design.shape[0] - rank
    if residual_df < 1:
        raise ValueError("design has no residual degrees of freedom")
    inverse = np.linalg.inv(design.T @ design)
    coefficients = inverse @ design.T @ values.T
    fitted = design @ coefficients
    residuals = values.T - fitted
    residual_variances = np.sum(residuals**2, axis=0) / residual_df
    positive = residual_variances[
        np.isfinite(residual_variances) & (residual_variances > 0)
    ]
    if len(positive) < 2:
        prior_variance = float(np.mean(positive)) if len(positive) else 1.0
        prior_df = 0.0
    else:
        prior_variance, prior_df = _fit_variance_prior(positive, residual_df)
    moderated_variances = (
        prior_df * prior_variance + residual_df * residual_variances
    ) / (prior_df + residual_df)
    moderated_variances = np.maximum(
        moderated_variances,
        np.finfo(float).tiny,
    )
    unscaled_variance = float(contrast @ inverse @ contrast)
    contrast_coefficients = contrast @ coefficients
    standard_errors = np.sqrt(moderated_variances * unscaled_variance)
    statistic = contrast_coefficients / standard_errors
    p_value = 2.0 * stats.t.sf(
        np.abs(statistic),
        df=residual_df + prior_df,
    )
    return ModeratedLinearModel(
        coefficient=np.asarray(contrast_coefficients, dtype=float),
        statistic=np.asarray(statistic, dtype=float),
        p_value=np.asarray(p_value, dtype=float),
        prior_variance=prior_variance,
        prior_degrees_of_freedom=prior_df,
        residual_degrees_of_freedom=residual_df,
        design_rank=rank,
    )


def moderated_two_group_test(
    case_values: np.ndarray,
    control_values: np.ndarray,
) -> ModeratedTest:
    """Fit group means and moderate residual variances across features."""
    case_count = case_values.shape[1]
    control_count = control_values.shape[1]
    residual_df = case_count + control_count - 2
    if case_count < 2 or control_count < 2 or residual_df < 1:
        raise ValueError("moderated testing requires at least two samples per group")

    case_means = np.mean(case_values, axis=1)
    control_means = np.mean(control_values, axis=1)
    residual_sum_squares = np.sum(
        (case_values - case_means[:, None]) ** 2,
        axis=1,
    ) + np.sum(
        (control_values - control_means[:, None]) ** 2,
        axis=1,
    )
    residual_variances = residual_sum_squares / residual_df
    positive = residual_variances[
        np.isfinite(residual_variances) & (residual_variances > 0)
    ]
    if len(positive) < 2:
        prior_variance = float(np.mean(positive)) if len(positive) else 1.0
        prior_df = 0.0
    else:
        prior_variance, prior_df = _fit_variance_prior(
            positive,
            residual_df,
        )
    moderated_variances = (
        prior_df * prior_variance + residual_df * residual_variances
    ) / (prior_df + residual_df)
    moderated_variances = np.maximum(
        moderated_variances,
        np.finfo(float).tiny,
    )
    standard_errors = np.sqrt(
        moderated_variances * (1.0 / case_count + 1.0 / control_count)
    )
    statistic = (case_means - control_means) / standard_errors
    total_df = residual_df + prior_df
    p_value = 2.0 * stats.t.sf(np.abs(statistic), df=total_df)
    return ModeratedTest(
        statistic=np.asarray(statistic, dtype=float),
        p_value=np.asarray(p_value, dtype=float),
        prior_variance=prior_variance,
        prior_degrees_of_freedom=prior_df,
        residual_degrees_of_freedom=residual_df,
    )


def _fit_variance_prior(
    variances: np.ndarray,
    residual_df: int,
) -> tuple[float, float]:
    log_variances = np.log(variances)
    observed_variance = float(np.var(log_variances, ddof=1))
    residual_component = float(special.polygamma(1, residual_df / 2.0))
    target = observed_variance - residual_component
    if target <= 1e-8:
        prior_df = 1e6
    else:
        prior_df = float(
            2.0
            * optimize.brentq(
                lambda value: float(special.polygamma(1, value)) - target,
                1e-6,
                1e8,
            )
        )
    mean_log = float(np.mean(log_variances))
    prior_variance = float(
        np.exp(
            mean_log
            - special.digamma(residual_df / 2.0)
            + np.log(residual_df / 2.0)
            + special.digamma(prior_df / 2.0)
            - np.log(prior_df / 2.0)
        )
    )
    return prior_variance, prior_df
