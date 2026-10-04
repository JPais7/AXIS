"""Computational campaigns: register a frozen plan, prepare, run, report, review.

A campaign turns a chemical hypothesis and a bounded, frozen chemical space into a
panel of candidates for *experimental validation*. Nothing here is experimental
evidence, and nothing here runs a wet-lab step.
"""

import hashlib
import json
import re
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from typing import Any

from axis.computational import chem, docking, prioritize, structure
from axis.storage import EvidenceStore

CAMPAIGN_VERSION = "axis-campaign-1"
MAX_SPACE = 1000
FORBIDDEN_CLASSES = {"experimental_result", "source_assertion"}
REVIEW_DECISIONS = (
    "pending_review",
    "accepted",
    "accepted_with_conditions",
    "rejected",
    "needs_revision",
)
REVIEWER_BLOCK = re.compile(r"\b(ai|axis|assistant|claude|gpt|llm|model)\b", re.I)
SYNTHETIC_LABEL = "SYNTHETIC / TEST ONLY / NOT SCIENTIFIC EVIDENCE"


class CampaignError(ValueError):
    """A campaign operation was refused (state, integrity or bounds)."""


def registry_root() -> Path:
    return Path(str(resources.files("axis"))) / "resources/computational-discovery"


def now() -> datetime:
    return datetime.now(UTC)


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def load_plan(directory: Path) -> dict[str, Any]:
    manifest = json.loads((directory / "manifest.json").read_text())
    expected = (directory / "manifest.sha256").read_text().strip()
    if (
        hashlib.sha256((directory / "manifest.json").read_bytes()).hexdigest()
        != expected
    ):
        raise CampaignError("manifest checksum mismatch; refusing to use the package")
    for name, checksum in manifest["files"].items():
        if hashlib.sha256((directory / name).read_bytes()).hexdigest() != checksum:
            raise CampaignError(
                f"{name} checksum mismatch; refusing to use the package"
            )
    plan: dict[str, Any] = json.loads((directory / "campaign-plan.json").read_text())
    plan["_package"] = {
        "set_id": manifest["set_id"],
        "synthetic": manifest["synthetic"],
    }
    return plan


class CampaignService:
    def __init__(self, store: EvidenceStore, root: Path | None = None) -> None:
        self.store = store
        self.root = root or registry_root()
        self.repo = store.computational

    # -- registry ----------------------------------------------------------

    def packages(self) -> list[Path]:
        if not self.root.is_dir():
            return []
        return sorted(p.parent for p in self.root.glob("*/v*/manifest.json"))

    def plan_for(self, set_id: str) -> dict[str, Any]:
        for path in self.packages():
            plan = load_plan(path)
            if set_id in (path.parent.name, plan["campaign_id"]):
                return plan
        raise CampaignError(f"unknown campaign package {set_id!r}")

    # -- register ----------------------------------------------------------

    def register(self, set_id: str) -> str:
        plan = self.plan_for(set_id)
        project = plan["project_id"]
        members = plan["space"]["members"]
        if len(members) > MAX_SPACE:
            raise CampaignError(
                f"chemical space of {len(members)} exceeds the local campaign bound {MAX_SPACE}"
            )
        synthetic = bool(plan["_package"]["synthetic"])
        if not synthetic:
            self._verify_identities(plan)
        space_content = {
            "members": members,
            "source": plan["space"]["source"],
            "selection": plan["space"]["selection_criteria"],
        }
        space_id = f"space:{plan['campaign_id']}:{digest(space_content)[:12]}"
        plan_fp = digest({k: v for k, v in plan.items() if not k.startswith("_")})
        logical = plan["campaign_id"]
        existing = self.repo.rows(
            "computational_campaigns", "WHERE logical_id=?", [logical]
        )
        for row in existing:
            if row["payload"]["plan_fingerprint"] == plan_fp:
                return str(row["id"])
        revision = len(existing) + 1
        campaign_id = f"{logical}@r{revision}"
        with self.store._transaction():
            hyp_ids = []
            for h in plan["hypotheses"]:
                hid = f"{h['id']}@r{h.get('revision', 1)}"
                self.repo.put(
                    "chemical_hypotheses",
                    hid,
                    {
                        "logical_id": h["id"],
                        "revision": h.get("revision", 1),
                        "project_id": project,
                        "epistemic_status": h["epistemic_status"],
                    },
                    {**h, "target_label": plan["target_label"], "synthetic": synthetic},
                )
                hyp_ids.append(hid)
            self.repo.put(
                "chemical_spaces",
                space_id,
                {"project_id": project, "checksum": digest(space_content)},
                {
                    **plan["space"],
                    "checksum": digest(space_content),
                    "size_before_filtering": plan["space"].get(
                        "size_before_filtering", len(members)
                    ),
                    "size_after_filtering": len(members),
                    "synthetic": synthetic,
                },
            )
            for m in members:
                self._member(space_id, m)
            prepared_structure = None
            if plan.get("structure"):
                prepared_structure = self._prepare_structure(plan, project)
            campaign = {
                "campaign_id": campaign_id,
                "logical_id": logical,
                "revision": revision,
                "project_id": project,
                "title": plan["title"],
                "question": plan["question"],
                "target_label": plan["target_label"],
                "protein_id": plan.get("protein_id"),
                "intervention_strategy": plan["intervention_strategy"],
                "hypothesis_ids": hyp_ids,
                "space_id": space_id,
                "prepared_structure_id": prepared_structure,
                "site": plan.get("site"),
                "methods": plan["methods"],
                "constraints": plan["constraints"],
                "assay_options": plan["assay_options"],
                "decision_link_request": plan.get("decision_link"),
                "plan_fingerprint": plan_fp,
                "software": {
                    "campaign": CAMPAIGN_VERSION,
                    "rdkit": chem.rdkit_version(),
                    "prioritization": prioritize.RULES_VERSION,
                    "docking_engine": docking.find_engine(),
                },
                "synthetic": synthetic,
                "label": SYNTHETIC_LABEL if synthetic else "",
                "package": plan["_package"],
            }
            self.repo.put(
                "computational_campaigns",
                campaign_id,
                {
                    "logical_id": logical,
                    "revision": revision,
                    "project_id": project,
                    "status": "planned",
                    "created_at": now(),
                },
                campaign,
            )
        return campaign_id

    def _member(self, space_id: str, member: dict[str, Any]) -> None:
        row = self.repo._db.execute(
            "SELECT 1 FROM chemical_space_members WHERE space_id=? AND compound_ref=?",
            [space_id, member["ref"]],
        ).fetchone()
        if row is None:
            self.repo._db.execute(
                "INSERT INTO chemical_space_members VALUES (?,?,?)",
                [space_id, member["ref"], canonical(member)],
            )

    def _verify_identities(self, plan: dict[str, Any]) -> None:
        """Indexed members must match the stored CompoundIdentity exactly."""
        for m in plan["space"]["members"]:
            ident = m.get("compound_identity")
            if not ident:
                continue
            try:
                record = self.store.pharmacology.record("compounds", ident)
            except Exception as error:
                raise CampaignError(
                    f"indexed compound {ident!r} not in the store"
                ) from error
            if record["original_smiles"] != m["smiles"]:
                raise CampaignError(
                    f"{ident}: campaign SMILES differs from the indexed identity"
                )

    def _prepare_structure(self, plan: dict[str, Any], project: str) -> str:
        spec = plan["structure"]
        cif = Path(str(resources.files("axis"))) / spec["resource"]
        record = structure.prepare_structure(
            cif,
            source_structure_id=spec["source_structure_id"],
            chain=spec["chain"],
            expected_sha256=spec["source_sha256"],
        )
        site = plan["site"]
        site_record = structure.define_site(
            cif,
            chain=spec["chain"],
            around=site["around"],
            radius=float(site["radius"]),
            site_id=site["id"],
        )
        record["site"] = site_record
        record["structure_context"] = {
            "construct": spec.get("construct"),
            "structural_state": spec["structural_state"],
            "canonical_mapping": spec.get("canonical_mapping"),
            "ligands_cofactors": spec.get("ligands_cofactors"),
            "coordinates_checksum": record["output_sha256"],
        }
        self.repo.put(
            "prepared_structures",
            record["id"],
            {
                "project_id": project,
                "source_structure_id": record["source_structure_id"],
                "source_sha256": record["source_sha256"],
                "output_sha256": record["output_sha256"],
            },
            record,
        )
        return str(record["id"])

    # -- prepare -----------------------------------------------------------

    def campaign(self, campaign_id: str) -> dict[str, Any]:
        rows = self.repo.rows("computational_campaigns", "WHERE id=?", [campaign_id])
        if not rows:
            raise CampaignError(f"unknown campaign {campaign_id!r}")
        row = rows[0]
        return {**row["payload"], "status": row["status"]}

    def members(self, space_id: str) -> list[dict[str, Any]]:
        rows = self.repo.rows("chemical_space_members", "WHERE space_id=?", [space_id])
        return [r["payload"] for r in sorted(rows, key=lambda r: r["compound_ref"])]

    def prepare(self, campaign_id: str) -> dict[str, Any]:
        campaign = self.campaign(campaign_id)
        if campaign["status"] not in {"planned", "prepared", "failed"}:
            raise CampaignError(
                f"campaign is {campaign['status']}; preparation is closed"
            )
        prepared = {}
        with self.store._transaction():
            for m in self.members(campaign["space_id"]):
                p = chem.prepare_compound(
                    m["ref"],
                    m["smiles"],
                    compound_identity=m.get("compound_identity"),
                    input_stereo=m.get("input_stereochemistry"),
                )
                prepared[m["ref"]] = p
                self.repo.put(
                    "prepared_compounds",
                    f"prepared:{campaign['space_id']}:{m['ref']}",
                    {
                        "project_id": campaign["project_id"],
                        "compound_ref": m["ref"],
                        "output_sha256": p.get("output_sha256", ""),
                    },
                    p,
                )
            failed = [r for r, p in prepared.items() if p["status"] != "prepared"]
            status = "failed" if failed and len(failed) == len(prepared) else "prepared"
            self.repo.set_status(campaign_id, status)
        return {"campaign_id": campaign_id, "status": status, "failed": failed}

    # -- known chemistry ---------------------------------------------------

    def known_evidence(
        self, campaign: dict[str, Any], members: list[dict[str, Any]]
    ) -> dict[str, dict[str, Any]]:
        known: dict[str, dict[str, Any]] = {}
        project = campaign["project_id"]
        protein = None
        if not campaign["synthetic"]:
            ids = self.store.targets.project_ids(project)
            protein = ids[0] if len(ids) == 1 else None
        for m in members:
            ident = m.get("compound_identity")
            if m.get("fixture_evidence"):
                known[m["ref"]] = {
                    "has_experimental_evidence": True,
                    "source": SYNTHETIC_LABEL,
                    "summary": m["fixture_evidence"],
                }
            elif ident and protein:
                filters = {"compound": ident}
                measurements = self.store.pharmacology.collection(
                    project, protein, "measurements", 100, 0, filters
                )["items"]
                selectivity = self.store.pharmacology.collection(
                    project, protein, "selectivity", 100, 0, filters
                )["items"]
                cellular = self.store.cellular.collection(
                    project, protein, "experiments", 100, 0, ident
                )["items"]
                known[m["ref"]] = {
                    "has_experimental_evidence": bool(measurements),
                    "measurements": len(measurements),
                    "endpoints": sorted({str(x["endpoint"]) for x in measurements}),
                    "assays": sorted({str(x["assay_id"]) for x in measurements}),
                    "selectivity_records": len(selectivity),
                    "cellular_experiments": len(cellular),
                    "origin": "indexed AXIS pharmacology package (source-reported, not validated by AXIS)",
                    "summary": f"{len(measurements)} indexed measurements; biochemical, cellular and selectivity evidence stay separate",
                }
            else:
                known[m["ref"]] = {
                    "has_experimental_evidence": False,
                    "summary": "no direct evidence was identified in the indexed AXIS sources",
                }
        return known

    def decision_link(self, campaign: dict[str, Any]) -> dict[str, Any] | None:
        if campaign["synthetic"] or not campaign.get("decision_link_request"):
            return campaign.get("decision_link_request")
        from axis.decision import engine
        from axis.decision.service import DecisionService

        project = campaign["project_id"]
        ids = self.store.targets.project_ids(project)
        if len(ids) != 1:
            return None
        try:
            analysis = engine.analyze(
                DecisionService(self.store).inputs(project, ids[0]),
                with_sensitivity=False,
            )
        except ValueError:
            return {
                "status": "decision package not imported",
                **campaign["decision_link_request"],
            }
        return {
            **campaign["decision_link_request"],
            "critical_uncertainty_id": analysis["critical_uncertainty_id"],
            "recommended_experiment_id": analysis["recommended_experiment_id"],
            "note": "read from the current decision rules at run time; no decision state was written",
        }

    # -- run ---------------------------------------------------------------

    def run(self, campaign_id: str) -> dict[str, Any]:
        campaign = self.campaign(campaign_id)
        if campaign["status"] != "prepared":
            raise CampaignError(f"campaign is {campaign['status']}; prepare it first")
        members = self.members(campaign["space_id"])
        prepared = {
            m["ref"]: self.repo.get(
                "prepared_compounds", f"prepared:{campaign['space_id']}:{m['ref']}"
            )
            or {}
            for m in members
        }
        known = self.known_evidence(campaign, members)
        usable = {
            m["ref"]: m["smiles"]
            for m in members
            if prepared[m["ref"]].get("status") == "prepared"
        }
        refs = sorted(r for r, k in known.items() if k["has_experimental_evidence"])
        desc = {r: chem.descriptors(s) for r, s in usable.items()}
        flags = {
            r: chem.descriptor_flags(
                desc[r], campaign["constraints"].get("descriptor_ranges", {})
            )
            for r in usable
        }
        sims = {
            r: {
                x: chem.similarity(usable[r], usable[x])
                for x in refs
                if x != r and x in usable
            }
            for r in usable
        }
        scaffolds = {r: chem.scaffold(s) for r, s in usable.items()}
        clusters = chem.cluster(
            usable, float(campaign["constraints"]["cluster_threshold"])
        )
        structure_record = (
            self.repo.get("prepared_structures", campaign["prepared_structure_id"])
            if campaign["prepared_structure_id"]
            else None
        )
        site = (structure_record or {}).get("site") or {}
        dock = docking.docking_plan(site, receptor_validated=False)
        link = self.decision_link(campaign)
        result = prioritize.prioritize(
            members=members,
            prepared=prepared,
            known=known,
            descriptors=desc,
            flags=flags,
            similarities=sims,
            clusters=clusters,
            scaffolds=scaffolds,
            structure_available=structure_record is not None,
            docking=dock,
            constraints=campaign["constraints"],
            hypotheses=[
                self.repo.get("chemical_hypotheses", h) or {}
                for h in campaign["hypothesis_ids"]
            ],
            assay_options=campaign["assay_options"],
            decision_link=link,
        )
        observations = self._observations(
            campaign, usable, desc, sims, scaffolds, clusters, dock, flags
        )
        status = "failed" if result["outcome"] == "failed" else "completed"
        with self.store._transaction():
            for o in observations:
                if o["epistemic_class"] in FORBIDDEN_CLASSES:
                    raise CampaignError(
                        "a computational observation cannot be experimental evidence"
                    )
                self.repo.put(
                    "computational_observations",
                    o["id"],
                    {
                        "campaign_id": campaign_id,
                        "compound_ref": o["compound_ref"],
                        "method": o["method"],
                        "epistemic_class": o["epistemic_class"],
                    },
                    o,
                )
            for e in result["panel"]:
                self.repo.put(
                    "candidate_molecules",
                    f"candidate:{campaign_id}:{e['compound_ref']}",
                    {"campaign_id": campaign_id, "compound_ref": e["compound_ref"]},
                    e,
                )
            prio_id = f"prioritization:{campaign_id}:{result['rules_fingerprint'][:12]}"
            result["known_chemistry"] = known
            result["clusters"] = clusters
            result["docking"] = dock
            self.repo.put(
                "candidate_prioritizations",
                prio_id,
                {
                    "campaign_id": campaign_id,
                    "rules_fingerprint": result["rules_fingerprint"],
                    "created_at": now(),
                },
                result,
            )
            table = {"descriptors": desc, "similarity": sims, "scaffolds": scaffolds}
            self.repo.put(
                "campaign_artifacts",
                f"artifact:{campaign_id}:descriptor-similarity-table",
                {
                    "campaign_id": campaign_id,
                    "artifact_type": "descriptor_similarity_table",
                    "sha256": digest(table),
                },
                {
                    "type": "descriptor_similarity_table",
                    "sha256": digest(table),
                    "content": table,
                    "creator": "axis.computational.service",
                    "software": {"rdkit": chem.rdkit_version()},
                },
            )
            self.repo.set_status(campaign_id, status)
        return {
            "campaign_id": campaign_id,
            "status": status,
            "prioritization_id": prio_id,
            "outcome": result["outcome"],
        }

    def _observations(
        self,
        campaign: dict[str, Any],
        usable: dict[str, str],
        desc: dict[str, Any],
        sims: dict[str, Any],
        scaffolds: dict[str, str],
        clusters: dict[str, Any],
        dock: dict[str, Any],
        flags: dict[str, Any],
    ) -> list[dict[str, Any]]:
        out = []
        cid = campaign["campaign_id"]
        base = {
            "campaign_id": cid,
            "epistemic_class": "axis_observation",
            "experimental": False,
            "tool": "RDKit",
            "tool_version": chem.rdkit_version(),
            "limitations": ["computational output; not experimental evidence"],
        }
        cluster_of = {
            m: i for i, c in enumerate(clusters["clusters"]) for m in c["members"]
        }
        for ref in sorted(usable):
            out.append(
                {
                    **base,
                    "id": f"obs:{cid}:{ref}:descriptors",
                    "compound_ref": ref,
                    "method": "descriptors",
                    "parameters": {"descriptors": list(chem.DESCRIPTORS)},
                    "output": desc[ref],
                    "flags": flags[ref],
                }
            )
            out.append(
                {
                    **base,
                    "id": f"obs:{cid}:{ref}:similarity",
                    "compound_ref": ref,
                    "method": "similarity",
                    "parameters": {
                        "fingerprint": chem.FINGERPRINT,
                        "metric": chem.METRIC,
                    },
                    "output": sims[ref],
                    "interpretation_boundary": "chemical similarity under this fingerprint; not evidence of similar activity",
                }
            )
            out.append(
                {
                    **base,
                    "id": f"obs:{cid}:{ref}:scaffold",
                    "compound_ref": ref,
                    "method": "scaffold",
                    "parameters": {"definition": "Bemis-Murcko (RDKit)"},
                    "output": {"scaffold": scaffolds[ref]},
                }
            )
            out.append(
                {
                    **base,
                    "id": f"obs:{cid}:{ref}:cluster",
                    "compound_ref": ref,
                    "method": "clustering",
                    "parameters": {
                        k: clusters[k]
                        for k in ("algorithm", "distance", "distance_threshold")
                    },
                    "output": {"cluster": cluster_of.get(ref)},
                    "interpretation_boundary": "a cluster is not an activity class",
                }
            )
        out.append(
            {
                **base,
                "id": f"obs:{cid}:docking",
                "compound_ref": "*",
                "method": "docking",
                "parameters": {},
                "output": dock,
                "tool": "none",
                "tool_version": "not executed",
            }
        )
        return out

    # -- views -------------------------------------------------------------

    def list_campaigns(self, project: str | None = None) -> list[dict[str, Any]]:
        rows = self.repo.rows(
            "computational_campaigns",
            "WHERE project_id=?" if project else "",
            [project] if project else [],
        )
        return [
            {
                "campaign_id": r["id"],
                "project_id": r["project_id"],
                "status": r["status"],
                "title": r["payload"]["title"],
                "question": r["payload"]["question"],
                "synthetic": r["payload"]["synthetic"],
                "label": r["payload"]["label"],
            }
            for r in rows
        ]

    def view(self, campaign_id: str, project: str | None = None) -> dict[str, Any]:
        campaign = self.campaign(campaign_id)
        if project and campaign["project_id"] != project:
            raise CampaignError(
                f"campaign {campaign_id!r} is not part of project {project!r}"
            )
        prio = self.repo.rows(
            "candidate_prioritizations", "WHERE campaign_id=?", [campaign_id]
        )
        reviews = self.repo.rows(
            "campaign_reviews", "WHERE campaign_id=?", [campaign_id]
        )
        space = self.repo.get("chemical_spaces", campaign["space_id"]) or {}
        return {
            "campaign": campaign,
            "hypotheses": [
                self.repo.get("chemical_hypotheses", h)
                for h in campaign["hypothesis_ids"]
            ],
            "chemical_space": {**space, "members": self.members(campaign["space_id"])},
            "prepared_structure": self.repo.get(
                "prepared_structures", campaign["prepared_structure_id"]
            )
            if campaign["prepared_structure_id"]
            else None,
            "prepared_compounds": [
                r["payload"]
                for r in self.repo.rows(
                    "prepared_compounds", "WHERE project_id=?", [campaign["project_id"]]
                )
                if r["id"].startswith(f"prepared:{campaign['space_id']}:")
            ],
            "observations": [
                r["payload"]
                for r in self.repo.rows(
                    "computational_observations", "WHERE campaign_id=?", [campaign_id]
                )
            ],
            "prioritization": prio[-1]["payload"] if prio else None,
            "reviews": [
                {
                    "id": r["id"],
                    "object_id": r["object_id"],
                    "reviewer": r["reviewer"],
                    "decision": r["decision"],
                    **r["payload"],
                }
                for r in reviews
            ],
        }

    def review(
        self,
        campaign_id: str,
        object_id: str,
        reviewer: str,
        decision: str,
        rationale: str,
        caveat: str | None = None,
    ) -> str:
        campaign = self.campaign(campaign_id)
        if decision not in REVIEW_DECISIONS or decision == "pending_review":
            raise CampaignError(f"decision must be one of {REVIEW_DECISIONS[1:]}")
        if not reviewer.strip() or REVIEWER_BLOCK.search(reviewer):
            raise CampaignError("AI cannot accept its own scientific conclusions")
        if decision == "accepted_with_conditions" and not caveat:
            raise CampaignError("accepted_with_conditions requires the conditions")
        if not rationale.strip():
            raise CampaignError("a review needs a rationale")
        count = (
            len(
                self.repo.rows("campaign_reviews", "WHERE campaign_id=?", [campaign_id])
            )
            + 1
        )
        rid = f"review:{campaign_id}:{count}"
        self.repo.put(
            "campaign_reviews",
            rid,
            {
                "campaign_id": campaign_id,
                "object_id": object_id,
                "reviewer": reviewer,
                "decision": decision,
                "reviewed_at": now(),
            },
            {
                "rationale": rationale,
                "caveat": caveat,
                "project_id": campaign["project_id"],
            },
        )
        return rid

    def report(self, campaign_id: str) -> str:
        v = self.view(campaign_id)
        c, p = v["campaign"], v["prioritization"]
        lines = [f"# Campaign {c['campaign_id']} — {c['status']}", ""]
        if c["label"]:
            lines += [f"**{c['label']}**", ""]
        lines += [
            "Computational prioritization for experimental validation. Nothing below is an "
            "experimental result, an active compound or a drug candidate.",
            "",
            f"## Campaign question\n\n{c['question']}",
            "",
            "## Chemical hypotheses",
            "",
        ]
        for h in v["hypotheses"]:
            lines.append(
                f"- **{h['id']}** ({h['epistemic_status']}, review pending): {h['statement']}"
            )
        ps = v["prepared_structure"]
        if ps:
            lines += [
                "",
                "## Structural context",
                "",
                f"- source {ps['source_structure_id']} chain {ps['chain']} sha256 `{ps['source_sha256'][:16]}`; prepared output `{ps['output_sha256'][:16]}`",
                f"- site: {ps['site']['site_type']} ({ps['site']['status']}), {len(ps['site'].get('residues', []))} residues within {ps['site'].get('radius_angstrom')} Å of {ps['site'].get('centre_component')}",
                f"- {ps['metals']}; waters removed; hydrogens not added",
            ]
            lines += [f"- limitation: {x}" for x in ps["limitations"]]
        lines += [
            "",
            f"## Chemical space\n\n{len(v['chemical_space']['members'])} members, frozen checksum `{v['chemical_space']['checksum'][:16]}`; source: {v['chemical_space']['source']}",
            "",
        ]
        if p:
            lines += [
                "## Methods",
                "",
                "- descriptors, Morgan/Tanimoto similarity, Butina clustering, Murcko scaffolds (RDKit "
                + chem.rdkit_version()
                + ")",
                f"- docking: {p['docking']['status']} — "
                + "; ".join(p["docking"]["reasons"]),
                "",
                "## Known experimental chemistry (separate from predictions)",
                "",
            ]
            for r in p["reference_chemistry"]:
                lines.append(
                    f"- {r['name'] or r['compound_ref']}: {r['evidence']['summary']}"
                )
            lines += ["", f"## Outcome: {p['outcome']}", ""] + [
                f"- {s}" for s in p["statements"]
            ]
            for f in p["failure_states"]:
                lines.append(f"- FAILURE: {f}")
            for e in p["panel"]:
                lines += [
                    "",
                    f"### {e['name'] or e['compound_ref']} — {e['role']}",
                    "",
                    e["why_this_molecule"],
                    "",
                    f"- strongest reason against: {e['strongest_reason_against']}",
                    f"- missing: {'; '.join(e['missing_evidence'])}",
                    f"- would change our mind: {'; '.join(e['what_would_change_our_mind']) or 'not specified'}",
                ]
            lines += [
                "",
                "## Not computed",
                "",
                "- no aggregate score; no docking evidence; no ADME/PK; no patent novelty",
            ]
        lines += ["", "Requires external experimental validation."]
        return "\n".join(lines) + "\n"
