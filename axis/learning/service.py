"""Chemical learning service: datasets, SAR, eligibility, models, predictions, state.

Every mutation is an explicit method call. Reading never trains, builds or predicts.
"""

import re
from datetime import UTC, datetime
from importlib import metadata as md
from importlib import resources
from pathlib import Path
from typing import Any

from axis.computational import chem
from axis.learning import dataset as ds
from axis.learning import eligibility, models, sar, selection
from axis.storage import EvidenceStore

SYNTHETIC_LABEL = "SYNTHETIC / TEST ONLY / NOT SCIENTIFIC EVIDENCE"
REVIEW_DECISIONS = (
    "accepted",
    "accepted_with_conditions",
    "rejected",
    "needs_revision",
)
REVIEWER_BLOCK = re.compile(r"\b(ai|axis|assistant|claude|gpt|llm|model)\b", re.I)
INTENTS = ("retrospective", "prospective", "benchmark")
OUTCOMES = (
    "directionally_supported",
    "quantitatively_supported",
    "partially_supported",
    "contradicted",
    "outside_applicability",
    "non_comparable",
    "experimental_result_ambiguous",
    "not_tested",
)


class LearningError(ValueError):
    """A chemical-learning operation was refused (state, integrity or science)."""


def registry_root() -> Path:
    return Path(str(resources.files("axis"))) / "resources/chemical-learning"


def now() -> datetime:
    return datetime.now(UTC)


def load_records(directory: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    import hashlib
    import json

    manifest = json.loads((directory / "manifest.json").read_text())
    if (
        hashlib.sha256((directory / "manifest.json").read_bytes()).hexdigest()
        != (directory / "manifest.sha256").read_text().strip()
    ):
        raise LearningError("manifest checksum mismatch; refusing to use the package")
    for name, checksum in manifest["files"].items():
        if hashlib.sha256((directory / name).read_bytes()).hexdigest() != checksum:
            raise LearningError(
                f"{name} checksum mismatch; refusing to use the package"
            )
    body = json.loads((directory / "measurements.json").read_text())
    records: list[dict[str, Any]] = body["records"]
    return dict(manifest), records


class LearningService:
    def __init__(self, store: EvidenceStore, root: Path | None = None) -> None:
        self.store = store
        self.root = root or registry_root()
        self.repo = store.learning

    # -- sources -----------------------------------------------------------------

    def synthetic_records(
        self, cutoff: str | None = None
    ) -> tuple[str, list[dict[str, Any]]]:
        import json

        directory = self.root / "synthetic-generic/v1"
        _, records = load_records(directory)
        project = json.loads((directory / "measurements.json").read_text())[
            "project_id"
        ]
        if cutoff:
            records = [r for r in records if r["date"] <= cutoff]
        return project, records

    def indexed_records(self, project: str) -> list[dict[str, Any]]:
        """Indexed pharmacology measurements, with their assay context, unchanged."""
        ids = self.store.targets.project_ids(project)
        if len(ids) != 1:
            raise LearningError("project must have exactly one imported protein")
        items = self.store.pharmacology.collection(
            project, ids[0], "measurements", 100, 0, {}
        )["items"]
        out = []
        for m in items:
            assay = self.store.pharmacology.record("assays", m["assay_id"])
            compound = self.store.pharmacology.record("compounds", m["compound_id"])
            out.append(
                {
                    "id": m["id"],
                    "compound_ref": m["compound_id"],
                    "smiles": compound["original_smiles"],
                    "operator": m["relation_operator"],
                    "value": float(m["original_value"]),
                    "unit": m["original_unit"],
                    "endpoint": m["endpoint"],
                    "context": {
                        "target": assay["target_gene"],
                        "taxon": assay["taxon_id"],
                        "assay_type": assay["assay_type"],
                        "format": assay["assay_format"],
                        "substrate": assay["substrate"],
                        "system": assay["biological_system"],
                    },
                    "source": m["source_snapshot_id"],
                    "date": None,
                    "replicate_group": None,
                }
            )
        return out

    # -- datasets ----------------------------------------------------------------

    def build_datasets(
        self,
        project: str,
        records: list[dict[str, Any]],
        *,
        synthetic: bool = False,
        provenance: str = "",
    ) -> list[str]:
        """Freeze one dataset per assay context; a changed content is a new revision."""
        built = []
        for _, group in sorted(ds.group_records(records).items()):
            probe = ds.build_dataset(
                group,
                project_id=project,
                revision=1,
                synthetic=synthetic,
                label=SYNTHETIC_LABEL if synthetic else "",
                provenance=provenance,
            )
            logical = probe["logical_id"]
            existing = self.repo.rows(
                "chemical_learning_datasets", "WHERE logical_id=?", [logical]
            )
            same = [
                r
                for r in existing
                if r["payload"]["content_checksum"] == probe["content_checksum"]
            ]
            if same:
                built.append(str(same[-1]["id"]))
                continue
            revision = len(existing) + 1
            frozen = ds.build_dataset(
                group,
                project_id=project,
                revision=revision,
                synthetic=synthetic,
                label=SYNTHETIC_LABEL if synthetic else "",
                provenance=provenance,
            )
            self.repo.put(
                "chemical_learning_datasets",
                frozen["id"],
                {
                    "logical_id": logical,
                    "revision": revision,
                    "project_id": project,
                    "checksum": frozen["checksum"],
                    "synthetic": synthetic,
                },
                frozen,
            )
            built.append(str(frozen["id"]))
        self._comparability(project, built)
        return built

    def dataset(self, dataset_id: str, project: str | None = None) -> dict[str, Any]:
        row = self.repo.get("chemical_learning_datasets", dataset_id)
        if row is None:
            raise LearningError(f"unknown dataset {dataset_id!r}")
        if project and row["project_id"] != project:
            raise LearningError(
                f"dataset {dataset_id!r} is not part of project {project!r}"
            )
        return row

    def datasets(self, project: str) -> list[dict[str, Any]]:
        rows = self.repo.rows(
            "chemical_learning_datasets", "WHERE project_id=?", [project]
        )
        return [
            {
                "id": r["id"],
                "endpoint": r["payload"]["endpoint"],
                "target": r["payload"]["target"],
                "assay_context": r["payload"]["assay_context"],
                "revision": r["revision"],
                "compounds": len(r["payload"]["compounds"]),
                "measurements": len(r["payload"]["measurements"]),
                "checksum": r["checksum"],
                "synthetic": r["synthetic"],
                "label": r["payload"]["label"],
                "review_state": self.review_state(r["id"]),
            }
            for r in rows
        ]

    def _comparability(self, project: str, dataset_ids: list[str]) -> None:
        for i, a in enumerate(sorted(dataset_ids)):
            for b in sorted(dataset_ids)[i + 1 :]:
                ca = self.dataset(a)["assay_context"]
                cb = self.dataset(b)["assay_context"]
                result = ds.comparability(ca, cb)
                self.repo.put(
                    "measurement_comparability_assessments",
                    f"comparability:{a}|{b}",
                    {
                        "project_id": project,
                        "dataset_a": a,
                        "dataset_b": b,
                        "state": result["state"],
                    },
                    result,
                )

    def comparability_matrix(self, project: str) -> list[dict[str, Any]]:
        rows = self.repo.rows(
            "measurement_comparability_assessments", "WHERE project_id=?", [project]
        )
        return [
            {
                "id": r["id"],
                "dataset_a": r["dataset_a"],
                "dataset_b": r["dataset_b"],
                "state": r["state"],
                **r["payload"],
            }
            for r in rows
        ]

    # -- SAR -----------------------------------------------------------------------

    def derive_sar(self, dataset_id: str) -> dict[str, Any]:
        d = self.dataset(dataset_id)
        pairs = sar.matched_pairs(d)
        groups = sar.scaffold_groups(d)
        hyps = sar.hypotheses(d, pairs)
        with self.store._transaction():
            for p in pairs:
                self.repo.put(
                    "observed_sar",
                    p["id"],
                    {
                        "dataset_id": dataset_id,
                        "project_id": d["project_id"],
                        "kind": p["kind"],
                    },
                    p,
                )
            for g in groups:
                self.repo.put(
                    "observed_sar",
                    g["id"],
                    {
                        "dataset_id": dataset_id,
                        "project_id": d["project_id"],
                        "kind": g["kind"],
                    },
                    g,
                )
            for h in hyps:
                self.repo.put(
                    "sar_hypotheses",
                    h["id"],
                    {
                        "dataset_id": dataset_id,
                        "project_id": d["project_id"],
                        "epistemic_status": h["epistemic_status"],
                    },
                    h,
                )
        return {
            "matched_pairs": len(pairs),
            "scaffold_groups": len(groups),
            "hypotheses": len(hyps),
        }

    def observed_sar(self, dataset_id: str) -> dict[str, Any]:
        rows = self.repo.rows("observed_sar", "WHERE dataset_id=?", [dataset_id])
        hyps = self.repo.rows("sar_hypotheses", "WHERE dataset_id=?", [dataset_id])
        pairs = [r["payload"] for r in rows if r["kind"] == "matched_molecular_pair"]
        return {
            "dataset_id": dataset_id,
            "observed": {
                "label": "OBSERVED SAR",
                "matched_pairs": pairs,
                "scaffold_groups": [
                    r["payload"] for r in rows if r["kind"] != "matched_molecular_pair"
                ],
            },
            "inferred": {
                "label": "INFERRED SAR HYPOTHESES (not observations)",
                "hypotheses": [h["payload"] for h in hyps],
            },
            "contradictory": [
                h["payload"] for h in hyps if h["payload"]["contradictory_observations"]
            ],
            "missing_experiments": self._missing(pairs),
        }

    @staticmethod
    def _missing(pairs: list[dict[str, Any]]) -> list[str]:
        out = []
        if not pairs:
            out.append("no matched molecular pair is measured in this assay context")
        unquant = [
            p["id"]
            for p in pairs
            if p["activity_change"]["direction"] == "not_quantifiable"
        ]
        if unquant:
            out.append(
                f"{len(unquant)} pairs need an exact measurement for a quantified comparison"
            )
        return out

    # -- eligibility -----------------------------------------------------------------

    def assess_eligibility(self, dataset_id: str) -> dict[str, Any]:
        d = self.dataset(dataset_id)
        result = eligibility.assess(d)
        self.repo.put(
            "model_eligibility_assessments",
            f"eligibility:{dataset_id}:{result['policy_fingerprint'][:10]}",
            {
                "dataset_id": dataset_id,
                "project_id": d["project_id"],
                "conclusion": result["conclusion"],
                "readiness": result["readiness"],
                "policy_fingerprint": result["policy_fingerprint"],
            },
            result,
        )
        return result

    # -- models ------------------------------------------------------------------------

    def train(
        self,
        dataset_id: str,
        algorithm: str = "ridge",
        split_kind: str = "scaffold",
        seed: int = 7,
    ) -> dict[str, Any]:
        d = self.dataset(dataset_id)
        gate = self.assess_eligibility(dataset_id)
        if gate["conclusion"] == "not_eligible":
            return {
                "model_built": False,
                "status": "MODEL NOT BUILT",
                "dataset_id": dataset_id,
                "readiness": gate["readiness"],
                "reasons": gate["reasons"],
                "statement": "Insufficient data for a defensible predictive model.",
            }
        rows = models.training_table(d)
        evaluation = models.evaluate(rows, algorithm, split_kind, seed)
        if not evaluation["valid"]:
            return {
                "model_built": False,
                "status": "MODEL NOT BUILT",
                "dataset_id": dataset_id,
                "reasons": [
                    f"validation split invalid: {evaluation['leakage']['findings']}"
                ],
            }
        fitted = models.fit(rows, algorithm, seed)
        validation = {
            "split_policy": {
                "kind": split_kind,
                "seed": seed,
                "test_fraction": models.POLICY["test_fraction"],
            },
            "evaluation": evaluation,
            "stability": models.stability(rows, algorithm, split_kind),
            "permutation_control": models.permutation_control(rows, algorithm, seed)
            if gate["conclusion"] in ("eligible", "eligible_with_conditions")
            else None,
            "leave_one_scaffold_out": models.leave_one_scaffold_out(rows, algorithm),
        }
        fp = models.model_fingerprint(d, fitted, dict(validation["split_policy"] or {}))
        model_id = f"model:{dataset_id}:{algorithm}:{fp[:12]}"
        payload = {
            "model_id": model_id,
            "dataset_id": dataset_id,
            "dataset_checksum": d["checksum"],
            "target": d["target"],
            "endpoint": d["endpoint"],
            "unit": d["unit"],
            "algorithm": algorithm,
            "feature_representation": models.FEATURES,
            "hyperparameters": models.POLICY["hyperparameters"],
            "model": fitted,
            "validation": validation,
            "fingerprint": fp,
            "software": {
                "python": __import__("sys").version.split()[0],
                "rdkit": chem.rdkit_version(),
                "numpy": md.version("numpy"),
                "scipy": md.version("scipy"),
            },
            "policy_fingerprint": models.policy_fingerprint(),
            "eligibility": gate["conclusion"],
            "label": d["label"],
            "synthetic": d["synthetic"],
            "review_state": "pending_review",
            "limitations": [
                "cross-validation-style performance is not prospective validation",
                "model confidence is not experimental certainty",
                "predictions are not measurements",
            ],
            "interpretation_note": "feature contributions, if any, are associations and not mechanisms",
        }
        self.repo.put(
            "chemical_models",
            model_id,
            {
                "dataset_id": dataset_id,
                "project_id": d["project_id"],
                "algorithm": algorithm,
                "fingerprint": fp,
                "created_at": now(),
            },
            payload,
        )
        return {
            "model_built": True,
            "model_id": model_id,
            "fingerprint": fp,
            "dataset_id": dataset_id,
        }

    def model(self, model_id: str, project: str | None = None) -> dict[str, Any]:
        row = self.repo.get("chemical_models", model_id)
        if row is None:
            raise LearningError(f"unknown model {model_id!r}")
        d = self.dataset(row["dataset_id"])
        if project and d["project_id"] != project:
            raise LearningError(
                f"model {model_id!r} is not part of project {project!r}"
            )
        return row

    # -- predictions ----------------------------------------------------------------------

    def predict(
        self,
        model_id: str,
        compounds: dict[str, str],
        *,
        intent: str,
        evidence_cutoff: str | None,
        known_results_available: bool = False,
    ) -> list[str]:
        if intent not in INTENTS:
            raise LearningError(f"intent must be one of {INTENTS}")
        if intent == "prospective" and known_results_available:
            raise LearningError(
                "a prediction made after the result was known cannot be prospective"
            )
        m = self.model(model_id)
        d = self.dataset(m["dataset_id"])
        ids = []
        for ref, smiles in sorted(compounds.items()):
            if ref in {t["compound_ref"] for t in m["model"]["training"]}:
                raise LearningError(
                    f"{ref} is in the training set; refusing a circular prediction"
                )
            p = models.predict(m["model"], smiles, d["unit"])
            payload = {
                "prediction_id": f"prediction:{model_id}:{ref}",
                "compound_ref": ref,
                "smiles": smiles,
                "model_id": model_id,
                "model_fingerprint": m["fingerprint"],
                "dataset_id": d["id"],
                "dataset_checksum": d["checksum"],
                "endpoint": d["endpoint"],
                "intent": intent,
                "evidence_cutoff": evidence_cutoff,
                "experimental_result_available_at_prediction": known_results_available,
                "epistemic_class": "axis_inference",
                "label": "PREDICTION — NOT AN EXPERIMENTAL MEASUREMENT",
                **p,
                "review_state": "pending_review",
                "synthetic": d["synthetic"],
            }
            self.repo.put(
                "chemical_predictions",
                payload["prediction_id"],
                {
                    "model_id": model_id,
                    "project_id": d["project_id"],
                    "compound_ref": ref,
                    "intent": intent,
                    "created_at": now(),
                },
                payload,
            )
            ids.append(payload["prediction_id"])
        return ids

    def prediction(self, prediction_id: str) -> dict[str, Any]:
        row = self.repo.get("chemical_predictions", prediction_id)
        if row is None:
            raise LearningError(f"unknown prediction {prediction_id!r}")
        return row

    def assess_outcome(
        self, prediction_id: str, measured: dict[str, Any] | None
    ) -> dict[str, Any]:
        """Compare a frozen prediction with a later measurement; never overwrites it."""
        p = self.prediction(prediction_id)
        d = self.dataset(p["dataset_id"])
        if measured is None:
            conclusion, detail = "not_tested", "no measurement is available"
        elif measured["context"] != d["assay_context"]:
            conclusion, detail = (
                "non_comparable",
                "the measurement was made in a different assay context",
            )
        elif measured["operator"] != "=":
            conclusion, detail = (
                "experimental_result_ambiguous",
                "the measurement is censored",
            )
        elif p["applicability"]["status"] == "outside_domain":
            conclusion, detail = (
                "outside_applicability",
                "the compound was outside the model's applicability domain",
            )
        else:
            value, unit, _ = ds.normalise(
                float(measured["value"]), measured.get("unit")
            )
            import math

            assert value is not None
            err = abs(math.log10(value) - math.log10(p["predicted_value"]))
            ref_values = [
                t["value"] for t in self.model(p["model_id"])["model"]["training"]
            ]
            median = sorted(ref_values)[len(ref_values) // 2]
            same_side = (value < median) == (p["predicted_value"] < median)
            if err <= 0.3:
                conclusion = "quantitatively_supported"
            elif same_side and err <= 0.7:
                conclusion = "partially_supported"
            elif same_side:
                conclusion = "directionally_supported"
            else:
                conclusion = "contradicted"
            detail = f"|log10 error| = {err:.2f}; thresholds are descriptive, not a validation claim"
        payload = {
            "prediction_id": prediction_id,
            "conclusion": conclusion,
            "detail": detail,
            "measured": measured,
            "prediction_frozen_value": p["predicted_value"],
            "prediction_unchanged": True,
        }
        self.repo.put(
            "prediction_outcome_assessments",
            f"outcome:{prediction_id}",
            {
                "prediction_id": prediction_id,
                "project_id": d["project_id"],
                "conclusion": conclusion,
            },
            payload,
        )
        return payload

    # -- state and next compounds ----------------------------------------------------------

    def next_compounds(
        self, dataset_id: str, model_id: str | None, candidates: dict[str, str]
    ) -> dict[str, Any]:
        d = self.dataset(dataset_id)
        sarv = self.observed_sar(dataset_id)
        groups = sarv["observed"]["scaffold_groups"]
        dominant = (
            max(groups, key=lambda g: len(g["members"]))["scaffold"] if groups else None
        )
        hyps = sarv["inferred"]["hypotheses"]
        model = self.model(model_id) if model_id else None
        values = [v["value"] for v in d["compound_values"] if v["value"]]
        median = sorted(values)[len(values) // 2] if values else float("inf")
        rows: list[dict[str, Any]] = []
        for ref, smiles in sorted(candidates.items()):
            pred = models.predict(model["model"], smiles, d["unit"]) if model else None
            rows.append(
                {
                    "compound_ref": ref,
                    "scaffold": chem.scaffold(smiles),
                    "prediction": pred,
                    "reference_value": median,
                    "tests_hypotheses": [],
                    "analogue_of_weak": False,
                }
            )
        contradictory = [
            v["compound_ref"] for v in d["compound_values"] if v["contradictory"]
        ]
        result = selection.select(
            candidates=rows,
            dominant_scaffold=dominant,
            hypotheses=hyps,
            contradictory_refs=contradictory,
        )
        result["not_asserted"] = [
            "synthesis or purchase availability was not assessed",
            "AXIS cannot make or test any compound",
        ]
        return result

    def learning_state(
        self, project: str, next_compounds: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """A versioned snapshot of what has been learned, with a causal diff to the last."""
        logical = f"learning-state:{project}"
        previous = self.repo.rows(
            "chemical_learning_states", "WHERE logical_id=?", [logical]
        )
        datasets = self.datasets(project)
        entries: list[dict[str, Any]] = []
        for item in datasets:
            e = self.repo.rows(
                "model_eligibility_assessments", "WHERE dataset_id=?", [item["id"]]
            )
            mods = self.repo.rows("chemical_models", "WHERE dataset_id=?", [item["id"]])
            sarv = self.repo.rows("observed_sar", "WHERE dataset_id=?", [item["id"]])
            hyps = self.repo.rows("sar_hypotheses", "WHERE dataset_id=?", [item["id"]])
            preds = [
                r
                for r in self.repo.rows(
                    "chemical_predictions", "WHERE project_id=?", [project]
                )
                if r["payload"]["dataset_id"] == item["id"]
            ]
            entries.append(
                {
                    "dataset": item,
                    "eligibility": e[-1]["payload"]["conclusion"]
                    if e
                    else "not_assessed",
                    "readiness": e[-1]["payload"]["readiness"] if e else "not_assessed",
                    "models": [m["id"] for m in mods],
                    "observed_sar": len(sarv),
                    "sar_hypotheses": len(hyps),
                    "predictions": [p["id"] for p in preds],
                }
            )
        uncertainties: list[dict[str, Any]] = []
        for entry in entries:
            if entry["eligibility"] == "not_eligible":
                uncertainties.append(
                    {
                        "id": f"chemical-uncertainty:{entry['dataset']['id']}:learnability",
                        "question": "Is the chemistry measured in this context enough to learn from?",
                        "status": "open",
                        "dataset": entry["dataset"]["id"],
                    }
                )
            if entry["sar_hypotheses"]:
                uncertainties.append(
                    {
                        "id": f"chemical-uncertainty:{entry['dataset']['id']}:sar-hypotheses",
                        "question": "Do the inferred SAR hypotheses hold beyond their matched pairs?",
                        "status": "open",
                        "dataset": entry["dataset"]["id"],
                    }
                )
        state: dict[str, Any] = {
            "project_id": project,
            "logical_id": logical,
            "revision": len(previous) + 1,
            "entries": entries,
            "next_compounds": next_compounds,
            "chemical_uncertainties": uncertainties,
            "boundaries": [
                "measured activity is not a model prediction",
                "observed SAR is not inferred SAR",
                "cross-validation is not prospective validation",
            ],
            "diff": self._diff(previous[-1]["payload"] if previous else None, entries),
        }
        key = ds.digest(
            {k: v for k, v in state.items() if k not in ("revision", "diff")}
        )
        if previous and previous[-1]["payload"].get("content_key") == key:
            return dict(previous[-1]["payload"])
        state["content_key"] = key
        self.repo.put(
            "chemical_learning_states",
            f"{logical}@r{state['revision']}",
            {
                "project_id": project,
                "logical_id": logical,
                "revision": state["revision"],
                "created_at": now(),
            },
            state,
        )
        return state

    @staticmethod
    def _diff(
        prev: dict[str, Any] | None, entries: list[dict[str, Any]]
    ) -> dict[str, Any]:
        if prev is None:
            return {"from": None, "causes": ["initial_state"]}
        old = {e["dataset"]["id"]: e for e in prev["entries"]}
        new_datasets = [
            e["dataset"]["id"] for e in entries if e["dataset"]["id"] not in old
        ]
        causes = []
        if new_datasets:
            causes.append("new_experimental_evidence_or_dataset_revision")
        new_models = [
            m
            for e in entries
            for m in e["models"]
            if m not in {x for o in old.values() for x in o["models"]}
        ]
        if new_models:
            causes.append("model_added")
        new_preds = [
            p
            for e in entries
            for p in e["predictions"]
            if p not in {x for o in old.values() for x in o["predictions"]}
        ]
        return {
            "from_revision": prev["revision"],
            "new_datasets": new_datasets,
            "new_models": new_models,
            "new_predictions": new_preds,
            "causes": causes or ["no_change"],
            "history_preserved": "earlier predictions and models are never rewritten",
        }

    # -- review ---------------------------------------------------------------------------------

    def review(
        self,
        object_type: str,
        object_id: str,
        reviewer: str,
        decision: str,
        rationale: str,
        project: str,
    ) -> str:
        if decision not in REVIEW_DECISIONS:
            raise LearningError(f"decision must be one of {REVIEW_DECISIONS}")
        if not reviewer.strip() or REVIEWER_BLOCK.search(reviewer):
            raise LearningError("AI cannot accept its own model interpretation")
        if not rationale.strip():
            raise LearningError("a review needs a rationale")
        n = (
            len(
                self.repo.rows(
                    "chemical_learning_reviews", "WHERE object_id=?", [object_id]
                )
            )
            + 1
        )
        rid = f"review:{object_id}:{n}"
        self.repo.put(
            "chemical_learning_reviews",
            rid,
            {
                "project_id": project,
                "object_type": object_type,
                "object_id": object_id,
                "reviewer": reviewer,
                "decision": decision,
                "reviewed_at": now(),
            },
            {"rationale": rationale},
        )
        return rid

    def review_state(self, object_id: str) -> str:
        rows = self.repo.rows(
            "chemical_learning_reviews", "WHERE object_id=?", [object_id]
        )
        return rows[-1]["decision"] if rows else "pending_review"
