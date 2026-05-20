export interface DirectionBatchItem {
  image_path: string;
  annotation_path: string | null;
  patient_id: string;
  T_stage: string;
  label: number;
  source: string;
  split?: string;
  has_mask: boolean;
  mask_centroid: [number, number] | null;
  mask_bbox: [number, number, number, number] | null;
  is_annotated?: boolean;
}

export interface DirectionBatch {
  batch_name: string;
  created: string;
  total: number;
  items: DirectionBatchItem[];
}

export type VisibleLayers = 0 | 1 | 2 | "3+" | "uncertain";
export type BreachConfidence = "high" | "medium" | "low";

export interface GridCellAnnotation {
  row: number;
  col: number;
  has_breach: boolean;
  visible_layers: VisibleLayers;
  breach_confidence: BreachConfidence;
}

export interface BreachPolygon {
  points: [number, number][];
  label?: string;
}

export type GridMode = "3x3" | "4x3" | "4x4";

export interface DirectionAnnotationPayload {
  image_path: string;
  patient_id: string;
  T_stage: string;
  grid_mode: GridMode;
  grid_cells: GridCellAnnotation[];
  breach_polygons: BreachPolygon[];
  mask_centroid: [number, number];
  mask_bbox: [number, number, number, number];
  note: string;
  timestamp: string;
  annotator?: string;
}

export interface BatchResponse {
  success: boolean;
  items: DirectionBatchItem[];
  patient_groups: Record<string, number[]>;
  pagination: {
    page: number;
    pageSize: number;
    totalFiltered: number;
    totalPages: number;
    totalAll: number;
  };
  stage_counts: Record<string, number>;
  annotated_count: number;
  batch_name: string;
  error?: string;
}

export interface SaveResponse {
  success: boolean;
  saved_path?: string;
  error?: string;
}
