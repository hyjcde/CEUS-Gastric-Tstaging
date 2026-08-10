export type ReaderCohort = 'all' | 'benign_malignancy' | 't_staging';

export type ReaderFrame = {
  video_rel?: string;
  still_rel?: string;
  media_type?: string;
  axis_label?: string;
  media_token?: string;
};

export type ReaderCase = {
  case_id: string;
  patient_id?: string;
  display_id?: string;
  study_mode?: 'benign_malignancy' | 't_staging' | string;
  reference_pt?: string;
  reference_lesion_nature?: string;
  has_video?: boolean;
  clinical?: Record<string, unknown>;
  frames: ReaderFrame[];
};

export type ReaderCasesBundle = {
  schema_version?: string;
  created_at?: string;
  cases: ReaderCase[];
};

export type SamClick = {
  x: number;
  y: number;
  label: 'positive' | 'negative' | string;
};

export type ReaderPromptStroke = {
  kind: 'scribble' | 'lasso';
  points: Array<{ x: number; y: number }>;
  label: 'positive' | 'negative' | string;
  width: number;
};

export type SamBox = {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
};

export type SamReport = {
  recommended_stage?: string;
  recommendation_status?: 'suggested' | 'conflict' | 'uncertain' | string;
  conflicts?: Array<{
    code?: string;
    severity?: 'low' | 'medium' | 'high' | string;
    fields?: string[];
    message?: string;
  }>;
  signs?: Record<string, {
    value?: unknown;
    status?: string;
    source?: string;
    confidence?: number | null;
    evidence_ref?: string[];
  }>;
  reference_stage?: {
    band?: string;
    source?: string;
    conflicts?: Array<Record<string, unknown>>;
  };
  stage_distribution?: Record<string, number>;
  calibrated_confidence?: number;
  summary?: string;
  template_id?: string;
  schema_version?: string;
  source_doc?: string;
  template_prose?: string;
  structured?: Record<string, unknown>;
  sam_score?: number;
  elapsed_ms?: number;
  evidence?: Array<{ title?: string; detail?: string; status?: string; source?: string }>;
  similar_cases?: Array<{ case_id?: string; stage?: string; score?: number; note?: string }>;
  toolchain?: Array<{ id?: string; title?: string; detail?: string; status?: string }>;
  llm_report?: {
    provider?: string;
    model?: string;
    narrative?: string;
    ai_polish?: string;
    error?: string;
    tokens?: number;
  };
};

export type ReaderDoctorAction = {
  action_type: 'accept' | 'modify' | 'reject' | 'request_more_evidence' | 'skip';
  final_t_stage?: string;
  reason?: string;
};

export type PrecomputedSimilarCase = {
  rank?: number;
  patient_id?: string;
  T_stage?: string;
  data_source?: string;
  similarity?: number;
};

export type PrecomputedSimilarCases = {
  available: boolean;
  reason?: string;
  basis?: string[];
  clinical_summary?: {
    location?: string | null;
    size_mm?: number | null;
    thickness_mm?: number | null;
    cea_positive?: boolean;
    ca199_positive?: boolean;
  };
  similar_cases?: PrecomputedSimilarCase[];
  stage_distribution?: Record<string, number>;
  memory_version?: string;
  query_mode?: string;
};

export type SamAnalyzeResult = {
  ok?: boolean;
  sam_score?: number;
  elapsed_ms?: number;
  mask_polygon?: number[][];
  mask_overlay_png?: string;
  prompt_meta?: {
    num_points?: number;
    num_positive?: number;
    num_negative?: number;
    has_box?: boolean;
    cascade_box?: boolean;
    auto_center_point?: boolean;
    refinement_passes?: number;
  };
  tracking?: {
    enabled?: boolean;
    mode?: string;
    session_id?: string | null;
    memory_used?: boolean;
    reset?: boolean;
    stored?: boolean;
    current_frame_time?: number;
    previous_frame_time?: number;
  };
  report?: SamReport;
};

export type InteractionMode = 'positive' | 'negative' | 'box' | 'inspect' | 'scribble' | 'lasso';

export type SamBackendStatus = {
  available: boolean;
  status?: {
    ready?: boolean;
    model?: string;
    cuda?: boolean;
    tracking?: { mode?: string; session_count?: number; ttl_sec?: number };
    minimax?: { configured?: boolean };
    deepseek?: { configured?: boolean };
    llm_report?: { configured?: boolean; preferred?: string; providers?: string[] };
  };
  error?: string;
};

export type NnInteractiveStatus = {
  available: boolean;
  client_available?: boolean;
  configured?: boolean;
  remote_available?: boolean;
  remote_error?: string | null;
  server_url?: string | null;
  model?: string;
  mode?: string;
  supports?: string[];
  error?: string;
};
