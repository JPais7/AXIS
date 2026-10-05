# mypy: disable-error-code="no-untyped-call,attr-defined,arg-type,import-untyped,var-annotated"
"""Small, interpretable, deterministic predictive models (numpy/scipy only).

Algorithms: training-mean baseline, 1-nearest-neighbour, similarity-weighted kNN and
ridge regression. No deep learning, no pickle: a model is plain JSON. Every model is
compared with simpler baselines under a leakage-checked split, and every prediction
carries an applicability assessment and only qualitative uncertainty.
"""

import math
import warnings
from typing import Any

import numpy as np
from rdkit import Chem, DataStructs
from rdkit.Chem import rdFingerprintGenerator
from scipy import stats

from axis.computational import chem
from axis.learning.dataset import digest

MODEL_VERSION = "axis-chemical-model-1"
ALGORITHMS = ("mean_baseline", "nearest_neighbor", "weighted_knn", "ridge")
FEATURES = {
    "fingerprint": "Morgan radius 2, 1024 bits (Tanimoto, for neighbour methods and applicability)",
    "descriptors": "MW, Crippen logP, TPSA, HBD, HBA, standardised on training data (ridge)",
}
POLICY: dict[str, Any] = {
    "version": MODEL_VERSION,
    "applicability": {
        "inside": 0.5,
        "near_boundary": 0.3,
        "metric": "max Tanimoto to training set",
    },
    "hyperparameters": {
        "knn_k": 3,
        "ridge_alpha_grid": [0.1, 1.0, 10.0],
        "inner_folds": 3,
    },
    "min_test_for_correlation": 5,
    "permutations": 50,
    "stability_seeds": [11, 12, 13, 14, 15],
    "test_fraction": 0.25,
    "overfit_ratio": 0.5,
    "material_improvement": 0.9,
    "uncertainty": "qualitative only; no calibrated numerical interval is available",
}


def policy_fingerprint() -> str:
    return digest(POLICY)


# --- representation ----------------------------------------------------------------


def to_p(value_nm: float, unit: str) -> float:
    """Activity on a log scale: pX for concentrations, log10 for fold changes."""
    return 9.0 - math.log10(value_nm) if unit == "nM" else math.log10(value_nm)


def from_p(p: float, unit: str) -> float:
    return 10 ** (9.0 - p) if unit == "nM" else 10**p


def _bits(smiles: str) -> Any:
    mol = Chem.MolFromSmiles(smiles)
    gen = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=1024)
    return gen.GetFingerprint(mol)


def _vector(smiles: str) -> np.ndarray:
    fp = _bits(smiles)
    arr = np.zeros((1024,), dtype=float)
    DataStructs.ConvertToNumpyArray(fp, arr)
    return arr


def _descriptors(smiles: str) -> np.ndarray:
    d = chem.descriptors(smiles)
    return np.array(
        [d["molecular_weight"], d["crippen_logp"], d["tpsa"], d["hbd"], d["hba"]],
        dtype=float,
    )


def training_table(dataset: dict[str, Any]) -> list[dict[str, Any]]:
    """Exact-value, non-contradictory compounds only. Censored values are never
    substituted by their boundary (documented policy: they are excluded from fitting)."""
    smiles = {c["compound_ref"]: c["smiles"] for c in dataset["compounds"]}
    unit = dataset["unit"]
    dates = {}
    for m in dataset["measurements"]:
        if m["date"]:
            dates[m["compound_ref"]] = min(
                m["date"], dates.get(m["compound_ref"], m["date"])
            )
    rows = []
    for v in dataset["compound_values"]:
        if (
            v["operator"] == "="
            and v["value"]
            and not v["contradictory"]
            and v["value"] > 0
        ):
            rows.append(
                {
                    "compound_ref": v["compound_ref"],
                    "smiles": smiles[v["compound_ref"]],
                    "y": to_p(v["value"], unit),
                    "value": v["value"],
                    "date": dates.get(v["compound_ref"]),
                    "scaffold": chem.scaffold(smiles[v["compound_ref"]]),
                    "inchi_key": Chem.MolToInchiKey(
                        Chem.MolFromSmiles(smiles[v["compound_ref"]])
                    ),
                }
            )
    return sorted(rows, key=lambda r: r["compound_ref"])


# --- splits ------------------------------------------------------------------------


def split(
    rows: list[dict[str, Any]], kind: str, seed: int, fraction: float
) -> dict[str, Any]:
    n_test = max(1, round(len(rows) * fraction))
    if kind == "random":
        order = np.random.RandomState(seed).permutation(len(rows))
        test = {rows[i]["compound_ref"] for i in order[:n_test]}
    elif kind == "scaffold":
        groups: dict[str, list[str]] = {}
        for r in rows:
            groups.setdefault(r["scaffold"], []).append(r["compound_ref"])
        keys = sorted(groups)
        np.random.RandomState(seed).shuffle(keys)
        test = set()
        for k in keys:
            if len(test) >= n_test:
                break
            test |= set(groups[k])
    elif kind == "temporal":
        dated = [r for r in rows if r["date"]]
        if len(dated) != len(rows):
            raise ValueError("temporal split needs a date for every compound")
        ordered = sorted(rows, key=lambda r: (r["date"], r["compound_ref"]))
        test = {r["compound_ref"] for r in ordered[-n_test:]}
    else:
        raise ValueError(f"unknown split {kind!r}")
    train = [r for r in rows if r["compound_ref"] not in test]
    held = [r for r in rows if r["compound_ref"] in test]
    return {
        "kind": kind,
        "seed": seed,
        "train": train,
        "test": held,
        "leakage": leakage(train, held, kind),
    }


def leakage(
    train: list[dict[str, Any]], test: list[dict[str, Any]], kind: str
) -> dict[str, Any]:
    refs = {r["compound_ref"] for r in train} & {r["compound_ref"] for r in test}
    keys = {r["inchi_key"] for r in train} & {r["inchi_key"] for r in test}
    scaffolds = {r["scaffold"] for r in train} & {r["scaffold"] for r in test}
    findings = []
    if refs:
        findings.append(f"same compound in train and test: {sorted(refs)}")
    if keys:
        findings.append("duplicate structure across train and test")
    if kind == "scaffold" and scaffolds:
        findings.append(f"scaffold shared across a scaffold split: {len(scaffolds)}")
    if (
        kind == "temporal"
        and train
        and test
        and max(r["date"] for r in train) > min(r["date"] for r in test)
    ):
        findings.append("a training measurement postdates a test measurement")
    return {"valid": not findings, "findings": findings}


# --- fitting and prediction -----------------------------------------------------------


def fit(rows: list[dict[str, Any]], algorithm: str, seed: int = 0) -> dict[str, Any]:
    if algorithm not in ALGORITHMS:
        raise ValueError(f"unknown algorithm {algorithm!r}")
    y = np.array([r["y"] for r in rows], dtype=float)
    model: dict[str, Any] = {
        "algorithm": algorithm,
        "version": MODEL_VERSION,
        "n_train": len(rows),
        "training": [
            {
                "compound_ref": r["compound_ref"],
                "smiles": r["smiles"],
                "y": r["y"],
                "value": r["value"],
            }
            for r in rows
        ],
        "mean": float(np.mean(y)) if len(y) else 0.0,
    }
    if algorithm == "ridge":
        x, mu, sd = _design(rows)
        alpha = _select_alpha(x, y, seed)
        coef = _ridge(x, y - y.mean(), alpha)
        model.update(
            {
                "alpha": alpha,
                "intercept": float(y.mean()),
                "coef": [round(float(c), 10) for c in coef],
                "feature_mean": mu.tolist(),
                "feature_std": sd.tolist(),
            }
        )
    return model


def _design(rows: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    desc = np.vstack([_descriptors(r["smiles"]) for r in rows])
    mu, sd = desc.mean(axis=0), desc.std(axis=0)
    sd[sd == 0] = 1.0
    return (desc - mu) / sd, mu, sd


def _ridge(x: np.ndarray, y: np.ndarray, alpha: float) -> np.ndarray:
    gram = x.T @ x + alpha * np.eye(x.shape[1])
    return np.linalg.solve(gram, x.T @ y)


def _select_alpha(x: np.ndarray, y: np.ndarray, seed: int) -> float:
    grid = POLICY["hyperparameters"]["ridge_alpha_grid"]
    folds = min(POLICY["hyperparameters"]["inner_folds"], len(y))
    if len(y) < 2 * folds:
        return float(grid[1])
    order = np.random.RandomState(seed).permutation(len(y))
    best, best_err = grid[1], math.inf
    for alpha in grid:
        errs = []
        for k in range(folds):
            hold = order[k::folds]
            keep = np.setdiff1d(order, hold)
            coef = _ridge(x[keep], y[keep] - y[keep].mean(), alpha)
            errs.append(np.mean(np.abs(x[hold] @ coef + y[keep].mean() - y[hold])))
        err = float(np.mean(errs))
        if err < best_err - 1e-12:
            best, best_err = alpha, err
    return float(best)


def neighbours(model: dict[str, Any], smiles: str, k: int = 3) -> list[dict[str, Any]]:
    fp = _bits(smiles)
    scored = [
        (float(DataStructs.TanimotoSimilarity(fp, _bits(t["smiles"]))), t)
        for t in model["training"]
    ]
    scored.sort(key=lambda s: (-s[0], s[1]["compound_ref"]))
    return [
        {
            "compound_ref": t["compound_ref"],
            "similarity": round(sim, 4),
            "measured_value": t["value"],
        }
        for sim, t in scored[:k]
    ]


def predict_p(model: dict[str, Any], smiles: str) -> float:
    algo = model["algorithm"]
    if algo == "mean_baseline":
        return float(model["mean"])
    if algo == "ridge":
        desc = (_descriptors(smiles) - np.array(model["feature_mean"])) / np.array(
            model["feature_std"]
        )
        return float(desc @ np.array(model["coef"]) + model["intercept"])
    near = neighbours(
        model,
        smiles,
        1 if algo == "nearest_neighbor" else POLICY["hyperparameters"]["knn_k"],
    )
    by_ref = {t["compound_ref"]: t["y"] for t in model["training"]}
    if algo == "nearest_neighbor":
        return float(by_ref[near[0]["compound_ref"]])
    weights = np.array([max(n["similarity"], 1e-6) for n in near])
    return float(np.average([by_ref[n["compound_ref"]] for n in near], weights=weights))


def applicability(model: dict[str, Any], smiles: str) -> dict[str, Any]:
    near = neighbours(model, smiles, 3)
    best = near[0]["similarity"] if near else 0.0
    a = POLICY["applicability"]
    train_desc = np.vstack([_descriptors(t["smiles"]) for t in model["training"]])
    d = _descriptors(smiles)
    in_range = bool(
        np.all(d >= train_desc.min(axis=0)) and np.all(d <= train_desc.max(axis=0))
    )
    status = (
        "inside_domain"
        if best >= a["inside"]
        else "near_boundary"
        if best >= a["near_boundary"]
        else "outside_domain"
    )
    if status == "inside_domain" and not in_range:
        status = "near_boundary"
    return {
        "status": status,
        "max_similarity_to_training": round(best, 4),
        "descriptor_ranges_ok": in_range,
        "nearest_training_compounds": near,
        "criteria": a,
        "note": "inside the domain is not high confidence",
    }


def predict(model: dict[str, Any], smiles: str, unit: str) -> dict[str, Any]:
    p = predict_p(model, smiles)
    return {
        "predicted_p": round(p, 4),
        "predicted_value": round(from_p(p, unit), 4),
        "unit": unit,
        "applicability": applicability(model, smiles),
        "uncertainty": {"numerical": None, "note": POLICY["uncertainty"]},
    }


# --- evaluation ----------------------------------------------------------------------


def metrics(y_true: list[float], y_pred: list[float]) -> dict[str, Any]:
    n = len(y_true)
    err = np.array(y_pred) - np.array(y_true)
    out: dict[str, Any] = {
        "n": n,
        "mae": round(float(np.mean(np.abs(err))), 4),
        "rmse": round(float(np.sqrt(np.mean(err**2))), 4),
    }
    if n >= POLICY["min_test_for_correlation"] and float(np.var(y_true)) > 0:
        ss_res, ss_tot = (
            float(np.sum(err**2)),
            float(np.sum((np.array(y_true) - np.mean(y_true)) ** 2)),
        )
        out["r2"] = round(1 - ss_res / ss_tot, 4)
        if float(np.var(y_pred)) > 0:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                rho = stats.spearmanr(y_true, y_pred)[0]
            out["spearman"] = None if rho != rho else round(float(rho), 4)
        else:
            out["spearman"] = None
    else:
        out["r2"] = out["spearman"] = None
        out["suppressed"] = (
            f"R² and Spearman need at least {POLICY['min_test_for_correlation']} test compounds with variance"
        )
    return out


def evaluate(
    rows: list[dict[str, Any]], algorithm: str, split_kind: str, seed: int
) -> dict[str, Any]:
    sp = split(rows, split_kind, seed, POLICY["test_fraction"])
    if not sp["leakage"]["valid"] or not sp["test"] or len(sp["train"]) < 3:
        return {
            "algorithm": algorithm,
            "split": split_kind,
            "seed": seed,
            "valid": False,
            "leakage": sp["leakage"],
            "reason": "invalid or too small partition",
        }
    result: dict[str, Any] = {
        "algorithm": algorithm,
        "split": split_kind,
        "seed": seed,
        "valid": True,
        "leakage": sp["leakage"],
        "n_train": len(sp["train"]),
        "n_test": len(sp["test"]),
    }
    for name in dict.fromkeys(["mean_baseline", "nearest_neighbor", algorithm]):
        model = fit(sp["train"], name, seed)
        train_pred = [predict_p(model, r["smiles"]) for r in sp["train"]]
        test_pred = [predict_p(model, r["smiles"]) for r in sp["test"]]
        result[name] = {
            "train": metrics([r["y"] for r in sp["train"]], train_pred),
            "test": metrics([r["y"] for r in sp["test"]], test_pred),
        }
    m, base = result[algorithm]["test"]["mae"], result["mean_baseline"]["test"]["mae"]
    nn = result["nearest_neighbor"]["test"]["mae"]
    result["baseline_comparison"] = {
        "model_mae": m,
        "mean_baseline_mae": base,
        "nearest_neighbor_mae": nn,
        "beats_mean_baseline": m < POLICY["material_improvement"] * base,
        "beats_nearest_neighbor": (
            m < POLICY["material_improvement"] * nn
            if algorithm != "nearest_neighbor"
            else None
        ),
        "criterion": "a model must be at least 10% better (MAE) than a baseline to be called better",
    }
    tr = result[algorithm]["train"]["mae"]
    result["overfit_audit"] = {
        "train_mae": tr,
        "test_mae": m,
        "possible_overfit": bool(tr < POLICY["overfit_ratio"] * m or m >= base),
    }
    return result


def stability(
    rows: list[dict[str, Any]], algorithm: str, split_kind: str
) -> dict[str, Any]:
    runs = [evaluate(rows, algorithm, split_kind, s) for s in POLICY["stability_seeds"]]
    ok = [r for r in runs if r["valid"]]
    maes = [r[algorithm]["test"]["mae"] for r in ok]
    return {
        "split": split_kind,
        "seeds": POLICY["stability_seeds"],
        "valid_runs": len(ok),
        "test_mae": maes,
        "range": None if not maes else [min(maes), max(maes)],
        "stable": bool(maes) and (max(maes) - min(maes)) <= 0.5 * (np.mean(maes) or 1),
        "note": "performance on one favourable split is never reported alone",
    }


def permutation_control(
    rows: list[dict[str, Any]], algorithm: str, seed: int = 0
) -> dict[str, Any]:
    sp = split(rows, "random", seed, POLICY["test_fraction"])
    real = metrics(
        [r["y"] for r in sp["test"]],
        [predict_p(fit(sp["train"], algorithm, seed), r["smiles"]) for r in sp["test"]],
    )["mae"]
    rng = np.random.RandomState(seed + 1000)
    worse = 0
    for _ in range(POLICY["permutations"]):
        ys = rng.permutation([r["y"] for r in sp["train"]])
        shuffled = [{**r, "y": float(y)} for r, y in zip(sp["train"], ys, strict=True)]
        perm = metrics(
            [r["y"] for r in sp["test"]],
            [
                predict_p(fit(shuffled, algorithm, seed), r["smiles"])
                for r in sp["test"]
            ],
        )["mae"]
        worse += perm <= real
    return {
        "real_test_mae": real,
        "permutations": POLICY["permutations"],
        "permuted_at_least_as_good": int(worse),
        "reading": "signal beyond chance under this split"
        if worse <= 2
        else "no clear signal beyond chance",
    }


def leave_one_scaffold_out(
    rows: list[dict[str, Any]], algorithm: str
) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        groups.setdefault(r["scaffold"], []).append(r)
    per = {}
    for scaffold, members in sorted(groups.items()):
        train = [r for r in rows if r["scaffold"] != scaffold]
        if len(train) < 3:
            continue
        model = fit(train, algorithm)
        per[scaffold] = metrics(
            [r["y"] for r in members], [predict_p(model, r["smiles"]) for r in members]
        )["mae"]
    dominant = max(groups, key=lambda k: len(groups[k])) if groups else None
    return {
        "per_scaffold_mae": per,
        "dominant_scaffold": dominant,
        "dominant_fraction": round(len(groups[dominant]) / len(rows), 3)
        if dominant
        else None,
    }


def model_fingerprint(
    dataset: dict[str, Any], model: dict[str, Any], split_info: dict[str, Any]
) -> str:
    import importlib.metadata as md

    return digest(
        {
            "dataset": dataset["checksum"],
            "model": model,
            "split": split_info,
            "policy": policy_fingerprint(),
            "numpy": md.version("numpy"),
            "rdkit": chem.rdkit_version(),
        }
    )
