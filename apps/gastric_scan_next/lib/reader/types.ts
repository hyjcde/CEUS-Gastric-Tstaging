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
  display_id?: string;
  study_mode?: 'benign_malignancy' | 't_staging' | string;
  reference_pt?: string;
  reference_lesion_nature?: string;
  has_video?: boolean;
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

export type SamBox = {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
};

export type SamReport = {
  recommended_stage?: string;
  stage_distribution?: Record<string, number>;
  calibrated_confidence?: number;
  summary?: string;
  sam_score?: number;
  elapsed_ms?: number;
  evidence?: Array<{ title?: string; detail?: string }>;
  similar_cases?: Array<{ case_id?: string; stage?: string; score?: number; note?: string }>;
  toolchain?: Array<{ id?: string; title?: string; detail?: string; status?: string }>;
  llm_report?: {
    provider?: string;
    model?: string;
    narrative?: string;
    error?: string;
    tokens?: number;
  };
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
  report?: SamReport;
};

export type InteractionMode = 'positive' | 'negative' | 'box' | 'inspect';

export type SamBackendStatus = {
  available: boolean;
  status?: {
    ready?: boolean;
    model?: string;
    cuda?: boolean;
    minimax?: { configured?: boolean };
    deepseek?: { configured?: boolean };
    llm_report?: { configured?: boolean; preferred?: string; providers?: string[] };
  };
  error?: string;
};
