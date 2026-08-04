export interface ConceptState {
  c1: number; // Ki-67 proliferation index surrogate (0-100)
  c2: number; // CPS (combined positive score) surrogate (0-100)
  c3: number; // PD-1 expression surrogate (0-100)
  c4: number; // FoxP3 / immune regulation surrogate (0-100)
  c5: number; // CD3 density (0-100)
  c6: number; // CD4 density (0-100)
  c7: number; // CD8 density (0-100)
  differentiation: number; // 1=Well, 2=Mod, 3=Mod-Poor, 4=Poor, 5=Unknown
  lauren: number; // 1=Intestinal, 0=Diffuse, 4=Unknown
  vascularInvasion: number; // 0=No, 1=Yes
  neuralInvasion: number; // 0=No, 1=Yes
}

export const DEFAULT_STATE: ConceptState = {
  // Ki-67 通常在 20-80% 之间，胃癌中位数常在 40-60%
  c1: 45, 
  // CPS 评分通常在 0-100 之间，但大多数阴性或低表达（<10），阳性（>1）有临床意义
  c2: 5, 
  // PD-1 表达通常较低，除非富集淋巴细胞浸润
  c3: 10, 
  // FoxP3 代表 Treg，通常在肿瘤浸润淋巴细胞中占比不高（5-20%）
  c4: 15, 
  // CD3 是总 T 细胞，通常密度中等
  c5: 40, 
  // CD4/CD8
  c6: 30, 
  c7: 25, 
  // 分化程度：最常见的是中分化或低分化
  differentiation: 3, // 3: Mod-Poor
  // Lauren 分型：肠型略多于弥漫型，或各半
  lauren: 1, // 1: Intestinal
  vascularInvasion: 0,
  neuralInvasion: 0
};

export type ReaderStudyMode = 'benign_malignancy' | 't_staging';

export interface VideoInfo {
  url: string;
  filename: string;
  treatment: 'direct_surgery' | 'neoadjuvant' | 'reader_study';
  water_filled: boolean;
}

export interface ConceptFeatures {
  ki67?: string;
  cps?: string;
  pd1?: string;
  foxp3?: string;
  cd3?: string;
  cd4?: string;
  cd8?: string;
  vascular?: string;
  neural?: string;
  differentiation?: string;
  lauren?: string;
}

export interface BiomarkerSummary {
  cea: number | null;
  ca199: number | null;
  cea_positive: boolean;
  ca199_positive: boolean;
}

export interface ClinicalData {
  age: number | null;
  sex: string;
  tumorSize: {
    length: number | null;
    thickness: number | null;
  };
  location: string;
  biomarkers: BiomarkerSummary;
  differentiation?: string;
  lauren?: string;
  concept_features?: ConceptFeatures;
}

export interface PatientReportData {
  ultrasound_report?: string;
  ultrasound_findings?: string;
  ultrasound_impression?: string;
  ct_report?: string;
  ct_findings?: string;
  ct_impression?: string;
  enhanced_ct_report?: string;
  endoscopy_report?: string;
  pathology_report?: string;
  report_source?: string;
}

export interface SegmentationEvidence {
  source: string;
  has_annotation: boolean;
  has_overlay: boolean;
  has_roi: boolean;
  annotation_count: number;
  frame_count: number;
  roi_url?: string;
  annotation_url?: string;
  overlay_url?: string;
  overlay_transparent_url?: string;
}

/** One persisted lesion contour generated at a video timestamp. */
export interface VideoMaskFrameOverride {
  timestamp_sec: number;
  imageWidth: number;
  imageHeight: number;
  mask_polygon: number[][];
  roi_bbox?: { x1: number; y1: number; x2: number; y2: number };
  source?: 'video_track' | 'video_propagate' | 'sam' | 'manual';
  propagation_status?: 'seed' | 'accepted';
  quality_score?: number;
}

/** Doctor-edited lesion boundary fed into Agent analyze as mask/ROI override. */
export interface MaskBoundaryOverride {
  patientId: string;
  frameId?: string;
  imageWidth: number;
  imageHeight: number;
  /** Closed polygon in image pixel coords [[x,y], ...] — lesion (green) */
  mask_polygon: number[][];
  /** Optional gastric wall / lumen outer contour (orange) */
  wall_polygon?: number[][];
  /** Optional ROI box {x1,y1,x2,y2} derived from polygon or doctor crop */
  roi_bbox?: { x1: number; y1: number; x2: number; y2: number };
  /** predicted = use override bbox; doctor = use on-disk crop ROI when available */
  roi_mode?: 'predicted' | 'doctor' | 'auto';
  source?: 'manual' | 'sam' | 'labelme' | 'imported' | 'video_track' | 'video_propagate';
  /** When editing on video: timestamp in seconds */
  video_time_sec?: number;
  video_url?: string;
  /** Persisted lesion contours produced at sampled video timestamps. */
  video_frames?: VideoMaskFrameOverride[];
  updated_at?: string;
  note?: string;
}

export interface AgentReport {
  schema_version: string;
  case_token: string;
  data_source: string;
  frame_count: number;
  report_status: 'draft';
  image_quality: {
    status: 'pending';
    summary: string;
  };
  segmentation: {
    status: 'available' | 'partial' | 'missing';
    summary: string;
  };
  classification: {
    status: 'pending' | 'available' | 'placeholder';
    summary: string;
  };
  similar_case_support: {
    status: 'pending';
    summary: string;
  };
  manual_review_recommended: boolean;
}

export interface Patient {
  id: string;
  id_short: string;
  patient_id: string; // Pure numeric ID for matching
  group: string;
  phase: string;
  source_label: string;
  queue_id?: string;
  center_id?: string;
  center_label?: string;
  study_mode?: ReaderStudyMode;
  frame_count: number;
  image_url: string;
  overlay_url: string;
  roi_url?: string;
  overlay_transparent_url?: string;
  json_url: string;
  segmentation: SegmentationEvidence;
  agent_report: AgentReport;
  clinical?: ClinicalData;
  report?: PatientReportData;
  video_urls?: VideoInfo[];
}

export interface AgentToolResult {
  available?: boolean;
  error?: string;
  backend_id?: string;
  trust_label?: 'trusted' | 'caution' | 'avoid' | 'unknown' | string;
  [key: string]: unknown;
}

export interface AgentReportCue {
  cue: string;
  matched_terms?: string[];
}

export interface SimilarCaseResult {
  rank?: number;
  patient_id: string;
  cohort_year?: string;
  data_source: string;
  T_stage: string;
  frame_count?: number;
  annotation_ratio?: number;
  overlay_ratio?: number;
  roi_ratio?: number;
  similarity: number;
  preview_image_url?: string;
  preview_image_path?: string;
}

export interface KnowledgeSnippet {
  source: string;
  title: string;
  content: string;
  guideline_id?: string;
}

export interface GuidelineEvidence {
  id: string;
  title: string;
  domain?: 'tnm' | 'management' | 'guardrail' | string;
  statement: string;
  source_ids?: string[];
  citations?: string[];
  match_score?: number;
}

export interface ManagementAdvice {
  priority?: 'high' | 'routine' | string;
  action: string;
  basis?: string[];
  source_ids?: string[];
  citations?: string[];
}

export interface AgentWorkbenchReport {
  schema_version: string;
  status: string;
  recommended_t_stage: string;
  confidence: 'high' | 'medium' | 'low' | string;
  reasoning: string;
  /** Optional language-only refinement; never owns the stage or confidence. */
  llm_reasoning?: string;
  dynamic_report_draft?: {
    title: string;
    generated_by: string;
    language: 'zh' | 'en' | string;
    sections: Array<{
      heading: string;
      lines: string[];
      evidence_refs?: string[];
    }>;
    full_text: string;
    review_required: boolean;
  };
  supporting_evidence: string[];
  conflicting_evidence?: string[];
  uncertainty_flags: string[];
  rag_gate?: {
    rag_weight: number;
    rag_gate_reason: string;
    classifier_uncertainty?: number;
    top1_top2_gap?: number;
  };
  similar_case_summary: {
    majority_stage: string;
    stage_distribution: Record<string, number>;
  };
  knowledge_highlights: string[];
  guideline_evidence?: GuidelineEvidence[];
  management_advice?: ManagementAdvice[];
  guideline_sources?: Array<Record<string, unknown>>;
  guideline_limitations?: string[];
  guideline_status?: string;
  tool_status: Record<string, string>;
  dino_sign_fusion?: Record<string, unknown>;
  memory_update_candidates?: Array<Record<string, unknown>>;
  memory_applied?: boolean;
  active_rules_used?: string[];
  governance_trust_labels?: Record<string, string>;
  memory_context_summary?: Record<string, unknown>;
  clinical_decision?: {
    status?: string;
    requires_mdt?: boolean;
    provisional_stage?: string;
    recommendation?: string;
    conflicts?: Array<Record<string, unknown>>;
    missing_modalities?: string[];
    evidence?: Array<Record<string, unknown>>;
    requires_doctor_review?: boolean;
    [key: string]: unknown;
  };
  belief_state_schema_version?: string;
}

export interface AgentSessionSummary {
  session_id: string;
  created_at: string;
  updated_at: string;
  patient_ids: string[];
  analysis_count: number;
}

export interface AgentStep {
  order: number;
  step_id: string;
  title: string;
  intent: string;
  decision: string;
  tool_name?: string | null;
  status: string;
  inputs: Record<string, unknown>;
  outputs: Record<string, unknown>;
  reasoning: string;
  visual_refs?: Record<string, unknown>;
}

export interface RuntimeApiInvocation {
  component: string;
  api_kind?: string;
  called?: boolean;
  status?: string;
  endpoint?: string;
  base_url?: string;
  model?: string;
  checkpoint?: string;
  device?: string;
  forward_pass?: boolean;
  total_tokens?: number;
  skip_reason?: string;
  error?: string;
  [key: string]: unknown;
}

export interface RuntimeVerification {
  verified_at: string;
  session_id?: string;
  patient_id?: string;
  all_core_models_called: boolean;
  llm_api_called: boolean;
  invocations: RuntimeApiInvocation[];
  proxy_visual_notes?: string[];
}

export interface AgentEvidenceItem {
  evidence_id: string;
  domain: string;
  feature: string;
  status: string;
  source_type: string;
  source_ref: string;
  value?: unknown;
  confidence?: unknown;
  model_version?: unknown;
  rule_version?: unknown;
  frame_id_or_time?: unknown;
  supports?: string[];
  refutes?: string[];
  quality_score?: number | null;
  metadata?: Record<string, unknown>;
  created_at: string;
}

export interface AgentProvenance {
  schema_version: string;
  orchestrator: string;
  run_id: string;
  case_id: string;
  patient_id: string;
  data_source?: string;
  software_version?: string;
  manifest_version?: string;
  artifact_relative_dir?: string;
  step_count: number;
  model_steps?: Array<Record<string, unknown>>;
  belief_state_schema_version?: string;
  reader_context?: Record<string, unknown>;
  input_mode?: string;
}

export interface AgentBeliefHypothesis {
  hypothesis_id: string;
  label: string;
  probability: number | null;
  status?: string;
  supporting_evidence?: string[];
  refuting_evidence?: string[];
  reason?: string;
}

export interface AgentBeliefAction {
  action_id: string;
  action_type: string;
  reason: string;
  expected_information_gain: number;
  status?: string;
  target_frame_index?: number | null;
  target_timestamp_sec?: number | null;
  required_evidence?: string[];
  selected_at?: string | null;
}

export interface AgentBeliefState {
  schema_version: string;
  run_id: string;
  case_id: string;
  patient_id: string;
  hypotheses: AgentBeliefHypothesis[];
  evidence: AgentEvidenceItem[];
  conflicts: Array<Record<string, unknown>>;
  missing_evidence: string[];
  action_trace: AgentBeliefAction[];
  next_actions: AgentBeliefAction[];
  stop_reason?: string | null;
  updated_at: string;
}

export interface AgentAnalysisResponse {
  schema_version?: string;
  session_id: string;
  session_memory: AgentSessionSummary;
  frame_evidence?: {
    frame_count: number;
    frames?: Array<{
      image_path?: string;
      roi_path?: string | null;
      frame_id?: string | null;
      frame_index?: number;
      timestamp_sec?: number | null;
      quality_score?: number | null;
    }>;
    primary_image_path?: string;
    primary_frame_id?: string | null;
    primary_timestamp_sec?: number | null;
    aggregation?: string;
    aggregated_frame_count?: number;
  };
  tool_evidence: {
    lumen_detection?: AgentToolResult;
    wall_evidence?: AgentToolResult;
    segmentation: AgentToolResult;
    classification: AgentToolResult;
    morphology: AgentToolResult;
    clinical: AgentToolResult;
    report?: AgentToolResult;
    dino?: AgentToolResult;
    clinical_decision?: AgentToolResult;
  };
  similar_cases: SimilarCaseResult[];
  knowledge_context: KnowledgeSnippet[];
  report: AgentWorkbenchReport;
  evidence?: AgentEvidenceItem[];
  provenance?: AgentProvenance;
  belief_state?: AgentBeliefState;
  agent_steps?: AgentStep[];
  prediction_artifacts?: Record<string, unknown>;
  runtime_verification?: RuntimeVerification;
  traces: Array<Record<string, unknown>>;
  trajectory_ref?: {
    path: string;
    schema_version: string;
  };
  memory_context?: Record<string, unknown>;
  memory_store_ref?: {
    path: string;
    run_id?: string;
  };
}
