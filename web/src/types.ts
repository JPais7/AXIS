export interface Entity { identifier: string; label: string; kind: string; namespace: string }
export type Context = Record<string, string | null>;
export interface Transformation { name: string; version: string; parameters: [string, string][] }
export interface Provenance { source_identifier: string; source_kind: string; source_uri: string | null; retrieved_at: string; checksum: string | null; transformations: Transformation[] }
export interface ClaimSummary { claim_id: string; statement: string; knowledge_kind: string; source_id: string; domain: string; limitation: string; context: Context }
export interface Claim { identifier: string; subject: Entity; predicate: string; object: Entity; knowledge_kind: string; context: Context; provenance: Provenance }
export interface Assessment { assessment_id: string; role: string; reasoning: string; claim_id: string; strategy_id: string | null; question_id: string | null; provenance: Provenance }
export interface Mechanism { assessment_id: string; classification: string; reasoning: string; claim_id: string; provenance: Provenance }
export interface MechanismItem { assessment: Mechanism; claim: Claim; summary: ClaimSummary }
export interface Source { source_id: string; source_kind: string; title: string; doi?: string; source_uri: string | null; retrieved_at: string; locator?: string; access?: string; claim_count?: number }
export interface Drawer extends ClaimSummary { claim: Claim; assessments: Assessment[]; mechanisms: Mechanism[]; source: Source; inclusion_rationale: string | null; curation_status: string | null; package_version: string | null; assessments_may_be_truncated: boolean }
export interface Page<T> { items: T[]; total: number; limit: number; offset: number; has_more: boolean }
export interface ProjectRecord { project_id: string; objective: string; status: string }
export interface Pair { target: Entity; disease: Entity; indication_scope: string }
export interface ProjectItem { project: ProjectRecord; pair: Pair }
export interface MatrixItem { domain: string; label: string; state: string; explanation: string; claim_count: number; source_count: number; methodology_version: string }
export interface Project extends ProjectItem { project_kind: string; package_version: string | null; curation_status: string; coverage: string; counts: Record<string, number>; matrix: MatrixItem[] }
export interface Strategy { strategy_id: string; description: string; rationale: string; strategy_type: string; knowledge_kind: string; provenance: Provenance }
export interface Perturbation { perturbation_id: string; target: Entity; perturbation_type: string; direction: string; status: string; intervention: Entity | null; observed_effect_claim_id: string | null; scientific_context: Context; knowledge_kind: string; provenance: Provenance }
export interface Question { question_id: string; question: string; category: string; status: string; scientific_context: Context }
export interface QuestionItem { question: Question; links: { claim_ids: string[]; strategy_ids: string[]; perturbation_ids: string[] }; link_limit: number }
export interface Experiment { experiment_id: string; question_id: string; title: string; rationale: string; experimental_system: string; intervention_description: string; endpoint_description: string; scientific_context: Context; knowledge_kind: string; provenance: Provenance }
export interface ExperimentItem { experiment: Experiment; outcomes: { scenario_id: string; possible_outcome: string; interpretation: string }[]; outcome_limit: number }
export interface SourceDetail { source: Source; claims: ClaimSummary[]; projects: string[]; transformations: Transformation[]; package_version: string | null; total: number; limit: number; offset: number; has_more: boolean }
export interface ComparisonItem extends Drawer { perturbations: Perturbation[]; perturbations_may_be_truncated: boolean }
export interface Comparison { project_id: string; items: ComparisonItem[]; interpretation: string }
