'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  BrainCircuit, Brain, Check, CircleDot, CircleMinus, CirclePlus, Droplets, Eraser, FileText, Film, History, Layers, Loader2, MousePointer2, PanelTop, Pause, Pencil, Play, Plus, RotateCcw, Save, ScanLine, ScanSearch, SkipBack, SkipForward, Sparkles, Trash2, Video, Workflow, X, ZoomIn,
} from 'lucide-react';
import type { LumenOverride, MaskBoundaryOverride, MaskHistoryEntry, Patient, VideoInfo, VideoMaskFrameOverride } from '@/types';
import type { SamReport } from '@/lib/reader/types';
import { bboxFromPolygon } from '@/lib/mask-override';
import { normalizeLumenBBox, type LumenBBox } from '@/lib/lumen-override';
import { useSettings } from '@/contexts/SettingsContext';
import { useDoctorAccount } from '@/contexts/DoctorAccountContext';
import { WallFeatureAnalysisCard } from '@/components/WallFeatureAnalysisCard';
import { ExplainableAnalysis, type ExplainableFramePayload } from '@/components/ExplainableAnalysis';
import type { ExplainableAnalysisResult } from '@/lib/concept-agent-merge';
import type { LayerAnalyzeResult } from '@/lib/human-assist/load-contact-geom';
import { computeLesionLumenGeometry, lumenBoxToPolygon, type LesionLumenGeometry } from '@/lib/lesion-lumen-geometry';
import { buildReportEvidenceImages } from '@/lib/report-evidence-images';
import type { GcUsReportImage } from '@/lib/gc-us-report-template';
import {
  LESION_CONTOUR_MAX_POINTS,
  LESION_CTRL_COUNT,
  LESION_SIMPLIFY_TARGET,
  LESION_SOFT_SIGMA,
  LUMEN_CONTOUR_MAX_POINTS,
  WALL_CONTOUR_MAX_POINTS,
  WALL_CTRL_COUNT,
  WALL_SIMPLIFY_TARGET,
  WALL_SOFT_SIGMA,
  clonePoly,
  controlIndices,
  prepareEditableContour,
  softDeform,
} from '@/lib/human-assist/contour-edit';
import {
  appendFinalPromptPoint,
  appendPromptPoint,
  prepareSubmitPromptStroke,
  strokeClosedPolyline,
} from '@/lib/human-assist/prompt-stroke';

type EditMode = 'soft' | 'hard' | 'add' | 'delete' | 'sam';
type MediaMode = 'image' | 'video';
type ContourLayer = 'lesion' | 'wall';
type DragLayer = ContourLayer;
type LesionSegmentationModel = 'sabm_sam2_guided' | 'sam31' | 'dinov3' | 'convnext';
type LumenBoxHandle = 'move' | 'nw' | 'ne' | 'sw' | 'se';
type ActiveSamPromptMode = 'point' | 'box' | 'scribble' | 'lasso';
type ActiveSamPromptLabel = 'positive' | 'negative';
type ActiveSamStroke = {
  points: number[][];
  label: ActiveSamPromptLabel;
  kind: 'scribble' | 'lasso';
  width: number;
  target?: 'lesion' | 'lumen';
};
type PersistOverrideOptions = {
  silent?: boolean;
};

type MaskAuditEventType = 'mask_event' | 'mask_saved' | 'model_trace' | 'error';

export type WorkflowTraceStep = {
  trace_id: string;
  step_id: string;
  action: string;
  status: 'started' | 'completed' | 'error' | 'skipped';
  source: 'doctor' | 'model' | 'agent' | 'system';
  frame_time_sec?: number | null;
  input?: Record<string, unknown>;
  output?: Record<string, unknown>;
  error?: string;
  recorded_at: string;
};

function formatHistoryBox(box: LumenBBox | null | undefined): string {
  if (!box) return '—';
  return `${Math.round(box.x1)}, ${Math.round(box.y1)} - ${Math.round(box.x2)}, ${Math.round(box.y2)}`;
}

function summarizeMaskForAudit(override: MaskBoundaryOverride | null | undefined) {
  const frames = override?.video_frames || [];
  const lastFrame = frames[frames.length - 1];
  return {
    mask_points: override?.mask_polygon?.length || 0,
    wall_points: override?.wall_polygon?.length || 0,
    roi_box_present: Boolean(override?.roi_bbox),
    video_frame_count: frames.length,
    frames_with_lesion_box: frames.filter((frame) => Boolean(frame.roi_bbox)).length,
    frames_with_lumen_mask: frames.filter((frame) => (frame.lumen_polygon?.length || 0) >= 3).length,
    frames_with_lumen_box: frames.filter((frame) => Boolean(frame.lumen_bbox)).length,
    last_frame_index: lastFrame?.frame_index,
    last_frame_time_sec: lastFrame?.timestamp_sec,
    source: override?.source,
    model_version: override?.model_version,
    video_present: Boolean(override?.video_url),
  };
}

function capturePointerSafely(target: HTMLCanvasElement, pointerId: number): void {
  try {
    target.setPointerCapture(pointerId);
  } catch {
    // Synthetic or already-ended pointer events may not have an active capture target.
  }
}

const VIDEO_PLAYBACK_RATES = [0.5, 0.75, 1, 1.25, 1.5, 2] as const;
const DINO_LAYER_INDICES = [2, 5, 8, 11] as const;

async function readJsonPayload<T>(response: Response, operation: string): Promise<T> {
  const text = await response.text();
  try {
    return JSON.parse(text) as T;
  } catch {
    const contentType = response.headers.get('content-type') || 'unknown content type';
    const prefix = text.replace(/\s+/g, ' ').trim().slice(0, 140);
    throw new Error(
      `${operation} returned HTTP ${response.status} as ${contentType}, not JSON`
        + (prefix ? `: ${prefix}` : ''),
    );
  }
}

type KeyframeCandidate = {
  timestamp_sec: number;
  frame_index?: number | null;
  frame_id?: string | null;
  image_width?: number | null;
  image_height?: number | null;
  score: number;
  reasons?: string[];
  thumb_url?: string;
  predicted_polygon?: number[][];
  prediction_status?: 'pending' | 'predicted' | 'needs_roi' | 'failed';
  prediction_error?: string;
};

type NnInteractiveSessionState = {
  key: string;
  id: string;
  initialized: boolean;
};

export type DinoLayerResult = {
  available?: boolean;
  model?: string;
  layer_index?: number;
  input_size?: number;
  token_grid?: [number, number];
  feature_dim?: number;
  feature_vector?: number[];
  feature_names?: string[];
  scalars?: Record<string, number>;
  vector_stats?: {
    mean?: number;
    std?: number;
    l2_norm?: number;
  };
  feature_overlay_png?: string;
  wall_evidence_overlay_png?: string;
  error?: string;
};

export type DinoFeatureResult = DinoLayerResult & {
  available?: boolean;
  case_id?: string;
  frame_time?: number;
  layer_indices?: number[];
  layers?: DinoLayerResult[];
};
interface InteractiveSegPanelProps {
  patient: Patient | null;
  override: MaskBoundaryOverride | null;
  onOverrideChange: (next: MaskBoundaryOverride | null) => void;
  /** Doctor-confirmed gastric lumen box / SAM3.1 contour for Agent geometry. */
  lumenOverride?: LumenOverride | null;
  onLumenOverrideChange?: (next: LumenOverride | null) => void;
  /** Optional: wall-layer + GC-US assist payload for DiagnosisPanel */
  onImagingAssist?: (payload: ImagingAssistPayload | null) => void;
  /** Current-frame system evidence shown in the AI-assisted task panel. */
  onSystemReport?: (report: SamReport | null) => void;
  /** Current-frame DINO region feature result shown in the workbench evidence panel. */
  onDinoFeatures?: (result: DinoFeatureResult | null) => void;
  /** Route the current video evidence into the unified research Agent. */
  onUnifiedAgentRun?: (capture: UnifiedAgentCapture) => Promise<void> | void;
  unifiedAgentBusy?: boolean;
  /** Receive normalized doctor and model trace steps for the unified Agent. */
  onWorkflowStep?: (step: WorkflowTraceStep) => void;
  /** Merge explainable boundary analysis into concept / diagnosis state (same as UltrasoundViewer). */
  onExplainableComplete?: (result: ExplainableAnalysisResult) => void;
  /** Emit report images generated from the current segmentation and keyframes. */
  onReportEvidenceImages?: (images: GcUsReportImage[], caseId?: string | null) => void;
  inline?: boolean;
}

export type UnifiedAgentFrame = {
  frame_png_b64: string;
  frame_id: string;
  frame_index: number;
  timestamp_sec: number;
  quality_score: number;
};

export type UnifiedAgentCapture = {
  frames: UnifiedAgentFrame[];
  current_time: number;
  image_width: number;
  image_height: number;
  mask_polygon: number[][];
  roi_bbox?: { x1: number; y1: number; x2: number; y2: number };
  lumen_bbox?: LumenBBox;
  lumen_polygon?: number[][];
  workflow_trace?: WorkflowTraceStep[];
  /** contour_anchored_fast (default Assist) | full */
  assist_profile?: 'contour_anchored_fast' | 'full';
  /** Contour-anchored diagnosis context assembled before Assist. */
  contour_context?: {
    lesion_confirmed: boolean;
    lumen_mask_type: 'sam31_polygon' | 'bbox_proxy' | 'missing';
    geometry_relation?: string;
    geometry_quality?: string;
    layer_label?: string | null;
    layer_pixel_based?: boolean;
    in_contact?: boolean | null;
    prepared_actions?: string[];
  };
};

export type ImagingAssistPayload = {
  layerResult: LayerAnalyzeResult | null;
  lesionPolygon: number[][];
  wallPolygon: number[][];
  frameSize: { width: number; height: number } | null;
  frameDataUrl?: string | null;
  lumenBBox?: LumenBBox | null;
  lumenPolygon?: number[][];
};

function dist2(a: number[], b: number[]) {
  const dx = a[0] - b[0];
  const dy = a[1] - b[1];
  return dx * dx + dy * dy;
}

function nearestVertex(points: number[][], imgPt: number[], thresholdPx: number): number {
  let best = -1;
  let bestD = thresholdPx * thresholdPx;
  for (let i = 0; i < points.length; i += 1) {
    const d = dist2(points[i], imgPt);
    if (d <= bestD) {
      bestD = d;
      best = i;
    }
  }
  return best;
}

function nearestEdgeInsert(points: number[][], imgPt: number[], thresholdPx: number): number {
  if (points.length < 2) return -1;
  let bestEdge = -1;
  let bestD = thresholdPx * thresholdPx;
  for (let i = 0; i < points.length; i += 1) {
    const a = points[i];
    const b = points[(i + 1) % points.length];
    const abx = b[0] - a[0];
    const aby = b[1] - a[1];
    const apx = imgPt[0] - a[0];
    const apy = imgPt[1] - a[1];
    const ab2 = abx * abx + aby * aby || 1;
    const t = Math.max(0, Math.min(1, (apx * abx + apy * aby) / ab2));
    const cx = a[0] + t * abx;
    const cy = a[1] + t * aby;
    const d = dist2([cx, cy], imgPt);
    if (d <= bestD) {
      bestD = d;
      bestEdge = i;
    }
  }
  return bestEdge;
}

async function videoOrImageToSamFrame(
  video: HTMLVideoElement | null,
  img: HTMLImageElement | null,
  preferVideo: boolean,
  maxSide = 1024,
): Promise<{ b64: string; width: number; height: number; fullWidth: number; fullHeight: number; scale: number }> {
  let fullW = 0;
  let fullH = 0;
  const draw = (ctx: CanvasRenderingContext2D, dw: number, dh: number) => {
    if (preferVideo && video && video.videoWidth > 0) {
      ctx.drawImage(video, 0, 0, dw, dh);
      return;
    }
    if (!img) throw new Error('no frame');
    ctx.drawImage(img, 0, 0, dw, dh);
  };
  if (preferVideo && video && video.videoWidth > 0) {
    fullW = video.videoWidth;
    fullH = video.videoHeight;
  } else if (img) {
    fullW = img.naturalWidth || img.width;
    fullH = img.naturalHeight || img.height;
  } else {
    throw new Error('no frame');
  }
  const scale = Math.min(1, maxSide / Math.max(fullW, fullH));
  const width = Math.max(1, Math.round(fullW * scale));
  const height = Math.max(1, Math.round(fullH * scale));
  const c = document.createElement('canvas');
  c.width = width;
  c.height = height;
  const ctx = c.getContext('2d');
  if (!ctx) throw new Error('canvas unavailable');
  draw(ctx, width, height);
  const b64 = c.toDataURL('image/jpeg', 0.85).replace(/^data:image\/jpeg;base64,/, '');
  return { b64, width, height, fullWidth: fullW, fullHeight: fullH, scale };
}

function polygonCentroid(points: number[][]): number[] | null {
  if (!points.length) return null;
  let sx = 0;
  let sy = 0;
  for (const p of points) {
    sx += p[0];
    sy += p[1];
  }
  return [sx / points.length, sy / points.length];
}

function polygonAreaAbs(points: number[][]): number {
  if (!points || points.length < 3) return 0;
  let area = 0;
  for (let i = 0; i < points.length; i += 1) {
    const a = points[i];
    const b = points[(i + 1) % points.length] || a;
    area += a[0] * b[1] - b[0] * a[1];
  }
  return Math.abs(area) / 2;
}

function pointInPolygon(pt: number[], poly: number[][]): boolean {
  if (!poly || poly.length < 3) return false;
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i, i += 1) {
    const xi = poly[i][0];
    const yi = poly[i][1];
    const xj = poly[j][0];
    const yj = poly[j][1];
    const intersect = ((yi > pt[1]) !== (yj > pt[1]))
      && (pt[0] < ((xj - xi) * (pt[1] - yi)) / ((yj - yi) || 1e-9) + xi);
    if (intersect) inside = !inside;
  }
  return inside;
}

function minDist2ToPolygon(pt: number[], poly: number[][]): number {
  if (!poly.length) return Number.POSITIVE_INFINITY;
  let best = Number.POSITIVE_INFINITY;
  for (let i = 0; i < poly.length; i += 1) {
    const a = poly[i];
    const b = poly[(i + 1) % poly.length] || a;
    best = Math.min(best, dist2(pt, a));
    const abx = b[0] - a[0];
    const aby = b[1] - a[1];
    const apx = pt[0] - a[0];
    const apy = pt[1] - a[1];
    const denom = abx * abx + aby * aby;
    if (denom <= 1e-9) continue;
    const t = Math.max(0, Math.min(1, (apx * abx + apy * aby) / denom));
    const cx = a[0] + abx * t;
    const cy = a[1] + aby * t;
    const d = (pt[0] - cx) ** 2 + (pt[1] - cy) ** 2;
    if (d < best) best = d;
  }
  return best;
}

function polygonHit(pt: number[], poly: number[][], edgeThrPx: number): boolean {
  if (!poly || poly.length < 3) return false;
  if (pointInPolygon(pt, poly)) return true;
  return minDist2ToPolygon(pt, poly) <= edgeThrPx * edgeThrPx;
}

function selectTopAreaKeyframes(
  frames: VideoMaskFrameOverride[],
  topK = 5,
  minGapSec = 0.5,
): KeyframeCandidate[] {
  const ranked = frames
    .filter((frame) => Array.isArray(frame.mask_polygon) && frame.mask_polygon.length >= 3)
    .map((frame) => ({
      frame,
      area: polygonAreaAbs(frame.mask_polygon),
    }))
    .filter((item) => item.area > 1)
    .sort((a, b) => b.area - a.area);

  const picked: Array<{ frame: VideoMaskFrameOverride; area: number }> = [];
  for (const item of ranked) {
    if (picked.length >= topK) break;
    if (picked.some((sel) => Math.abs(sel.frame.timestamp_sec - item.frame.timestamp_sec) < minGapSec)) {
      continue;
    }
    picked.push(item);
  }
  picked.sort((a, b) => a.frame.timestamp_sec - b.frame.timestamp_sec);

  return picked.map((item) => {
    const width = Math.max(1, item.frame.imageWidth || 1);
    const height = Math.max(1, item.frame.imageHeight || 1);
    return {
      timestamp_sec: item.frame.timestamp_sec,
      frame_index: item.frame.frame_index ?? null,
      frame_id: item.frame.frame_id ?? null,
      image_width: width,
      image_height: height,
      score: Number((item.area / 1000).toFixed(2)),
      reasons: [`area_px=${Math.round(item.area)}`, `gap>=${minGapSec}s`],
      predicted_polygon: item.frame.mask_polygon.map((point) => [
        Number((point[0] / width).toFixed(6)),
        Number((point[1] / height).toFixed(6)),
      ]),
      prediction_status: 'predicted' as const,
    };
  });
}

type PropagateApiFrame = {
  frame_index?: number;
  frame_time: number;
  direction?: string;
  mask_polygon?: number[][];
  quality_score?: number;
};

type PropagateApiResult = {
  status?: string;
  needs_reanchor?: boolean;
  accepted_frames?: number;
  num_frames?: number;
  propagation_mode?: string;
  frames?: PropagateApiFrame[];
};

function mapPropagateFramesToOverrides(
  frames: PropagateApiFrame[],
  imageWidth: number,
  imageHeight: number,
  source: VideoMaskFrameOverride['source'] = 'video_track',
): VideoMaskFrameOverride[] {
  return frames
    .filter((frame) => Array.isArray(frame.mask_polygon) && frame.mask_polygon.length >= 3)
    .map((frame) => {
      const maskPolygon = frame.mask_polygon!.map((point) => [Number(point[0]), Number(point[1])]);
      return {
        frame_index: Number.isFinite(Number(frame.frame_index))
          ? Number(frame.frame_index)
          : undefined,
        timestamp_sec: Number(Number(frame.frame_time).toFixed(3)),
        imageWidth,
        imageHeight,
        mask_polygon: maskPolygon,
        roi_bbox: bboxFromPolygon(maskPolygon),
        source,
        propagation_status: frame.direction === 'seed' ? 'seed' as const : 'accepted' as const,
        quality_score: Number(frame.quality_score ?? 0),
      };
    });
}

function nearestOverrideFrame(
  frames: VideoMaskFrameOverride[],
  timestampSec: number,
  maxDeltaSec = 0.35,
): VideoMaskFrameOverride | null {
  if (!frames.length) return null;
  // Propagate frames are time-ordered; binary search keeps scrub/playback redraws cheap.
  let lo = 0;
  let hi = frames.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (frames[mid].timestamp_sec < timestampSec) lo = mid + 1;
    else hi = mid;
  }
  let bestIdx = lo;
  if (lo > 0) {
    const prev = frames[lo - 1];
    const curr = frames[lo];
    if (Math.abs(prev.timestamp_sec - timestampSec) <= Math.abs(curr.timestamp_sec - timestampSec)) {
      bestIdx = lo - 1;
    }
  }
  const nearest = frames[bestIdx];
  if (Math.abs(nearest.timestamp_sec - timestampSec) > maxDeltaSec) return null;
  return nearest;
}

function mergeLumenIntoLesionFrames(
  lesionFrames: VideoMaskFrameOverride[],
  lumenFrames: VideoMaskFrameOverride[],
  seedLumen?: { polygon?: number[][]; box?: { x1: number; y1: number; x2: number; y2: number } | null },
  seedTimeSec?: number,
): VideoMaskFrameOverride[] {
  let carryPoly = seedLumen?.polygon && seedLumen.polygon.length >= 3
    ? seedLumen.polygon
    : undefined;
  const seedBox = seedLumen?.box || (carryPoly ? bboxFromPolygon(carryPoly) : undefined);
  const seedPoly = carryPoly && carryPoly.length >= 3 ? carryPoly : undefined;
  // Clamp runaway lumen tracking: do not let a tracked contour drift far from the
  // doctor-confirmed seed box, otherwise it paints the whole frame.
  const clampToSeed = (poly: number[][]) => {
    if (!seedBox) return poly;
    const bbox = bboxFromPolygon(poly);
    if (!bbox) return poly;
    const seedCx = (seedBox.x1 + seedBox.x2) / 2;
    const seedCy = (seedBox.y1 + seedBox.y2) / 2;
    const seedW = Math.max(24, seedBox.x2 - seedBox.x1);
    const seedH = Math.max(24, seedBox.y2 - seedBox.y1);
    const maxDx = seedW * 1.8;
    const maxDy = seedH * 1.8;
    const cx = (bbox.x1 + bbox.x2) / 2;
    const cy = (bbox.y1 + bbox.y2) / 2;
    const w = bbox.x2 - bbox.x1;
    const h = bbox.y2 - bbox.y1;
    const drifted = Math.abs(cx - seedCx) > maxDx
      || Math.abs(cy - seedCy) > maxDy
      || w > seedW * 3.5
      || h > seedH * 3.5;
    // Drifted → carry previous valid contour instead of the runaway one.
    return drifted ? (carryPoly && carryPoly.length >= 3 ? carryPoly : poly) : poly;
  };
  // The seed frame must keep the doctor-segmented lumen contour exactly;
  // the tracker only propagates to other frames.
  const seedFrame = seedPoly && typeof seedTimeSec === 'number'
    ? nearestOverrideFrame(lesionFrames, seedTimeSec, 0.6)
    : null;
  // Carry-forward logic assumes chronological order.
  const ordered = [...lesionFrames].sort((a, b) => a.timestamp_sec - b.timestamp_sec);
  return ordered.map((frame) => {
    if (seedPoly && seedFrame && frame.timestamp_sec === seedFrame.timestamp_sec) {
      return {
        ...frame,
        lumen_polygon: seedPoly.map((point) => [point[0], point[1]]),
        lumen_bbox: undefined,
      };
    }
    const matched = nearestOverrideFrame(lumenFrames, frame.timestamp_sec, 0.4);
    if (matched?.mask_polygon?.length) {
      carryPoly = clampToSeed(matched.mask_polygon);
    }
    if (!carryPoly || carryPoly.length < 3) return frame;
    return {
      ...frame,
      lumen_polygon: carryPoly.map((point) => [point[0], point[1]]),
      // Once a mask exists, drop the box so the view shows contour only.
      lumen_bbox: undefined,
    };
  });
}

async function requestVideoPropagate(body: Record<string, unknown>): Promise<PropagateApiResult> {
  const response = await fetch('/api/agent/video/propagate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const payload = await readJsonPayload<{
    ok?: boolean;
    error?: string;
    result?: PropagateApiResult;
  }>(response, 'Video propagation endpoint');
  if (!response.ok || !payload.ok || !payload.result) {
    throw new Error(payload.error || 'video propagation failed');
  }
  return payload.result;
}

/** Lumen-side preference vector for estimated wall offset (from lesion toward lumen). */
function lumenPreferVector(
  lesion: number[][],
  lumenPoly: number[][],
  lumenBox: LumenBBox | null,
): [number, number] | undefined {
  const lesionC = polygonCentroid(lesion);
  if (!lesionC) return undefined;
  let lumenC: number[] | null = null;
  if (lumenPoly.length >= 3) lumenC = polygonCentroid(lumenPoly);
  else if (lumenBox) {
    lumenC = [(lumenBox.x1 + lumenBox.x2) / 2, (lumenBox.y1 + lumenBox.y2) / 2];
  }
  if (!lumenC) return undefined;
  const dx = lumenC[0] - lesionC[0];
  const dy = lumenC[1] - lesionC[1];
  const len = Math.hypot(dx, dy) || 1;
  return [dx / len, dy / len];
}

function geometryRelationText(geometry: LesionLumenGeometry, zh: boolean): string {
  if (geometry.relation === 'overlap') {
    return zh
      ? '状态: 重叠 — 重点看病灶与胃腔壁接触处（突破分析关键区）'
      : 'Status: overlap — focus on lesion-to-lumen-wall contact (breakthrough zone)';
  }
  if (geometry.relation === 'near_lumen') {
    return zh
      ? '状态: 邻近胃腔壁 — 接触带为突破分析关键区'
      : 'Status: near lumen wall — contact band is the breakthrough analysis zone';
  }
  if (geometry.relation === 'separated') {
    return zh
      ? '状态: 分离, 病灶似在胃腔外 — 请扩大胃腔框使其包含胃壁与肿块后再分析'
      : 'Status: separated — lesion may be outside the lumen; expand the lumen to include wall and mass before analysis';
  }
  return zh ? '状态: 未评估' : 'Status: unknown';
}

function geometryQualityText(geometry: LesionLumenGeometry, zh: boolean): string {
  if (geometry.quality === 'high') return zh ? '轮廓质量较好' : 'Good contour quality';
  if (geometry.quality === 'moderate') return zh ? '轮廓质量中等' : 'Moderate contour quality';
  return zh ? '轮廓点较少' : 'Sparse contour points';
}

type ViewFocusBox = { x1: number; y1: number; x2: number; y2: number };
type ViewFocusMode = 'roi' | 'overlap';

function computeDisplayTransform(
  iw: number,
  ih: number,
  cw: number,
  ch: number,
  focus: ViewFocusBox | null,
): { scale: number; dx: number; dy: number } {
  if (!focus) {
    const scale = Math.min(cw / iw, ch / ih);
    return {
      scale,
      dx: (cw - iw * scale) / 2,
      dy: (ch - ih * scale) / 2,
    };
  }
  const pad = 0.22;
  const bw0 = Math.max(8, focus.x2 - focus.x1);
  const bh0 = Math.max(8, focus.y2 - focus.y1);
  const bx = Math.max(0, focus.x1 - bw0 * pad);
  const by = Math.max(0, focus.y1 - bh0 * pad);
  const bw = Math.min(iw - bx, bw0 * (1 + 2 * pad));
  const bh = Math.min(ih - by, bh0 * (1 + 2 * pad));
  const scale = Math.min(cw / bw, ch / bh, 4);
  return {
    scale,
    dx: (cw - bw * scale) / 2 - bx * scale,
    dy: (ch - bh * scale) / 2 - by * scale,
  };
}

// Distinct contour colors: lesion cyan, wall orange, lumen fuchsia (lighter so they do not hide wall layers).
const COLOR_LESION_FILL = 'rgba(34, 211, 238, 0.12)';
const COLOR_LESION_STROKE = 'rgba(103, 232, 249, 0.55)';
const COLOR_WALL_FILL = 'rgba(251, 146, 60, 0.08)';
const COLOR_WALL_STROKE = 'rgba(251, 146, 60, 0.50)';
const COLOR_LUMEN_FILL = 'rgba(217, 70, 239, 0.10)';
const COLOR_LUMEN_STROKE = 'rgba(232, 121, 249, 0.50)';
const COLOR_LUMEN_BOX_FILL = 'rgba(217, 70, 239, 0.04)';
const COLOR_LUMEN_BOX_STROKE = 'rgba(232, 121, 249, 0.45)';
const COLOR_LUMEN_HANDLE = 'rgba(232, 121, 249, 0.45)';
const COLOR_LESION_HANDLE = 'rgba(34, 211, 238, 0.45)';
const COLOR_WALL_HANDLE = 'rgba(234, 88, 12, 0.45)';
const CONTOUR_LINE_WIDTH = 1.15;
const HANDLE_STROKE = 'rgba(255, 255, 255, 0.55)';

function bboxFromPointsOrBox(
  points: number[][],
  box: LumenBBox | null | undefined,
): ViewFocusBox | null {
  const fromPoly = bboxFromPolygon(points);
  if (fromPoly) return fromPoly;
  if (box) return normalizeLumenBBox(box);
  return null;
}

function bboxFromPath(points: number[][], padding = 0): ViewFocusBox | null {
  if (!points || points.length < 2) return null;
  const valid = points.filter((point) => (
    Number.isFinite(Number(point[0])) && Number.isFinite(Number(point[1]))
  ));
  if (valid.length < 2) return null;
  const x1 = Math.min(...valid.map((point) => Number(point[0]))) - padding;
  const y1 = Math.min(...valid.map((point) => Number(point[1]))) - padding;
  const x2 = Math.max(...valid.map((point) => Number(point[0]))) + padding;
  const y2 = Math.max(...valid.map((point) => Number(point[1]))) + padding;
  if (x2 <= x1 || y2 <= y1) return null;
  return { x1, y1, x2, y2 };
}

function promptModeText(mode: ActiveSamPromptMode, zh: boolean): string {
  if (mode === 'point') return zh ? '正/负点' : 'Positive/negative points';
  if (mode === 'box') return zh ? '框选' : 'Box';
  if (mode === 'scribble') return zh ? '自由涂鸦' : 'Freehand scribble';
  return zh ? '套索' : 'Lasso';
}

function oppositePromptLabel(label: ActiveSamPromptLabel): ActiveSamPromptLabel {
  return label === 'positive' ? 'negative' : 'positive';
}

function unionFocusBoxes(...boxes: Array<ViewFocusBox | null | undefined>): ViewFocusBox | null {
  const valid = boxes.filter(Boolean) as ViewFocusBox[];
  if (!valid.length) return null;
  return {
    x1: Math.min(...valid.map((b) => b.x1)),
    y1: Math.min(...valid.map((b) => b.y1)),
    x2: Math.max(...valid.map((b) => b.x2)),
    y2: Math.max(...valid.map((b) => b.y2)),
  };
}

function segmentIntersectionPoint(
  firstStart: number[],
  firstEnd: number[],
  secondStart: number[],
  secondEnd: number[],
): number[] | null {
  const rx = firstEnd[0] - firstStart[0];
  const ry = firstEnd[1] - firstStart[1];
  const sx = secondEnd[0] - secondStart[0];
  const sy = secondEnd[1] - secondStart[1];
  const denominator = rx * sy - ry * sx;
  if (Math.abs(denominator) < 1e-8) return null;
  const qx = secondStart[0] - firstStart[0];
  const qy = secondStart[1] - firstStart[1];
  const t = (qx * sy - qy * sx) / denominator;
  const u = (qx * ry - qy * rx) / denominator;
  if (t < -1e-6 || t > 1 + 1e-6 || u < -1e-6 || u > 1 + 1e-6) return null;
  return [firstStart[0] + t * rx, firstStart[1] + t * ry];
}

function overlapFocusBox(
  lesion: number[][],
  lumen: number[][],
  lumenBox: LumenBBox | null | undefined,
  geometry: LesionLumenGeometry,
): ViewFocusBox | null {
  if (lesion.length < 3) return null;
  const lumenShape = lumen.length >= 3 ? lumen : lumenBoxToPolygon(lumenBox);
  if (lumenShape.length < 3) return null;

  const points: number[][] = [];
  lesion.forEach((point) => {
    if (pointInPolygon(point, lumenShape)) points.push(point);
  });
  lumenShape.forEach((point) => {
    if (pointInPolygon(point, lesion)) points.push(point);
  });
  for (let i = 0; i < lesion.length; i += 1) {
    const lesionStart = lesion[i];
    const lesionEnd = lesion[(i + 1) % lesion.length];
    for (let j = 0; j < lumenShape.length; j += 1) {
      const hit = segmentIntersectionPoint(
        lesionStart,
        lesionEnd,
        lumenShape[j],
        lumenShape[(j + 1) % lumenShape.length],
      );
      if (hit) points.push(hit);
    }
  }

  if (points.length) {
    const padded = points.length === 1
      ? [...points, [points[0][0] + 1, points[0][1] + 1]]
      : points;
    return bboxFromPath(padded, 18);
  }
  if (geometry.relation === 'near_lumen' && geometry.closestLesionPoint && geometry.closestLumenPoint) {
    return bboxFromPath(
      [geometry.closestLesionPoint, geometry.closestLumenPoint],
      24,
    );
  }
  return null;
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function seekVideoForAgent(video: HTMLVideoElement, time: number): Promise<void> {
  return new Promise((resolve) => {
    let settled = false;
    const done = () => {
      if (settled) return;
      settled = true;
      video.removeEventListener('seeked', done);
      resolve();
    };
    video.addEventListener('seeked', done, { once: true });
    video.currentTime = time;
    window.setTimeout(done, 1200);
  });
}

function sanitizeSystemCopy(value: unknown): string {
  return String(value ?? '')
    .replace(/\bSAM(?:2)?\b/gi, 'system analysis')
    .replace(/\bSegment Anything(?: Model)?\b/gi, 'system analysis');
}

function segmentationModelName(model: LesionSegmentationModel, zh: boolean): string {
  if (model === 'sabm_sam2_guided') return zh ? 'SABM-GUS 引导式模型' : 'SABM-GUS guided model';
  if (model === 'sam31') return zh ? 'SAM3.1 静态概念模型' : 'SAM3.1 static concept model';
  if (model === 'dinov3') return 'DINOv3';
  return 'ConvNeXt-UNet';
}

export function buildModelAssistReport(
  patient: Patient,
  polygon: number[][],
  frameWidth: number,
  frameHeight: number,
  model: LesionSegmentationModel,
  areaRatio?: number,
  zh = true,
): SamReport {
  const clinicalText = [
    patient.report?.ultrasound_findings,
    patient.report?.ultrasound_impression,
    patient.report?.ct_findings,
    patient.report?.ct_impression,
    patient.report?.enhanced_ct_report,
    patient.report?.endoscopy_report,
  ].filter(Boolean).join(' ');
  const text = clinicalText.toLowerCase();
  const bbox = bboxFromPolygon(polygon);
  const lengthPx = bbox ? Math.max(bbox.x2 - bbox.x1, bbox.y2 - bbox.y1) : 0;
  const thicknessPx = bbox ? Math.min(bbox.x2 - bbox.x1, bbox.y2 - bbox.y1) : 0;
  const polygonArea = polygon.reduce((sum, point, index) => {
    const next = polygon[(index + 1) % polygon.length] || point;
    return sum + point[0] * next[1] - next[0] * point[1];
  }, 0) / 2;
  const boxArea = Math.max(1, (bbox?.x2 || 0) - (bbox?.x1 || 0)) * Math.max(1, (bbox?.y2 || 0) - (bbox?.y1 || 0));
  const solidity = Math.abs(polygonArea) / boxArea;
  const shape = solidity < 0.72 || (lengthPx > 0 && lengthPx / Math.max(thicknessPx, 1) > 2.8)
    ? (zh ? '局部浸润型' : 'Focal infiltrative')
    : (zh ? '局限隆起型' : 'Localized protruding');
  const boundary = solidity < 0.72
    ? (zh ? '边界不规则' : 'Irregular boundary')
    : (zh ? '边界相对清晰，需结合连续帧复核' : 'Boundary relatively clear; recheck on consecutive frames');
  const layer = /突破肌层|侵犯肌层|固有肌层.*(破坏|受累)/.test(text)
    ? (zh ? '固有肌层受累/结构破坏' : 'Muscularis propria involved / disrupted')
    : /层次.*(完整|清晰)|肌层结构完整/.test(text)
      ? (zh ? '胃壁层次结构相对完整' : 'Wall layers relatively preserved')
      : (zh ? '当前帧层次显示有限，需多切面复核' : 'Limited layer visibility on this frame; multi-plane review needed');
  const serosa = /浆膜.*(中断|破坏|侵犯|不完整)/.test(text)
    ? (zh ? '浆膜连续性中断/受侵犯' : 'Serosal continuity interrupted / invaded')
    : /浆膜.*(完整|连续|光滑)/.test(text)
      ? (zh ? '浆膜连续' : 'Serosa continuous')
      : (zh ? '当前帧未能确认浆膜连续性' : 'Serosal continuity not confirmed on this frame');
  const perigastric = /胃周|脂肪间隙|邻近器官/.test(text)
    ? (zh ? '已从影像文字资料纳入胃周组织评估' : 'Perigastric tissues assessed from imaging text')
    : (zh ? '当前帧未能确认胃周组织' : 'Perigastric tissues not confirmed on this frame');
  // Text-derived draft labels only. Never unlock structured / definite cT from prose.
  const stageDraft = /浆膜.*(中断|破坏|侵犯|不完整)/.test(text)
    ? 'T4+'
    : /突破肌层|侵犯肌层|浆膜下/.test(text)
      ? 'T3'
      : /固有肌层.*(受累|侵犯)|肌层.*受累/.test(text)
        ? 'T2'
        : /黏膜下|肌层结构完整/.test(text)
          ? 'T1'
          : 'cTx';
  const stage = 'cTx';
  const location = patient.clinical?.location || (zh ? '胃' : 'Stomach');
  // Length / thickness are table clinical fields (fixed). tumorSize is stored in cm.
  const clinicalLengthCm = patient.clinical?.tumorSize?.length;
  const clinicalThicknessCm = patient.clinical?.tumorSize?.thickness;
  const lengthText = clinicalLengthCm != null
    ? `${Math.round(clinicalLengthCm * 10)} mm`
    : (zh ? '见临床表格' : 'See clinical table');
  const thicknessText = clinicalThicknessCm != null
    ? `${Math.round(clinicalThicknessCm * 10)} mm`
    : (zh ? '见临床表格' : 'See clinical table');
  const modelLabel = model === 'dinov3'
    ? 'DINOv3 lesion candidate'
    : model === 'convnext'
      ? 'ConvNeXt-Base UNet'
      : segmentationModelName(model, false);
  const layerUncertain = zh ? /当前帧/.test(layer) : /Limited layer|this frame/i.test(layer);
  const serosaUncertain = zh ? /当前帧/.test(serosa) : /not confirmed|this frame/i.test(serosa);
  const perigastricUncertain = zh ? /未能/.test(perigastric) : /not confirmed/i.test(perigastric);
  const signs = {
    size: {
      length: {
        value: lengthText,
        status: clinicalLengthCm != null ? 'suggested' : 'uncertain',
        source: 'clinical_data',
        confidence: clinicalLengthCm != null ? 0.9 : 0.2,
        evidence_ref: ['clinical.tumor_size'],
      },
      thickness: {
        value: thicknessText,
        status: clinicalThicknessCm != null ? 'suggested' : 'uncertain',
        source: 'clinical_data',
        confidence: clinicalThicknessCm != null ? 0.9 : 0.2,
        evidence_ref: ['clinical.tumor_size'],
      },
    },
    layer_structure: { value: layer, status: layerUncertain ? 'uncertain' : 'suggested', source: layerUncertain ? 'limited_frame' : 'clinical_text', confidence: 0.5, evidence_ref: ['clinical.imaging_text'] },
    morphology: { value: shape, status: 'suggested', source: 'mask_geometry', confidence: 0.58, evidence_ref: ['lesion_mask.solidity', 'lesion_mask.aspect_ratio'] },
    boundary: { value: boundary, status: 'suggested', source: 'mask_geometry', confidence: 0.55, evidence_ref: ['lesion_mask.boundary'] },
    growth_pattern: { value: shape, status: 'suggested', source: 'mask_geometry', confidence: 0.45, evidence_ref: ['lesion_mask.shape'] },
    serosa_change: { value: serosa, status: serosaUncertain ? 'uncertain' : 'suggested', source: serosaUncertain ? 'limited_frame' : 'clinical_text', confidence: 0.45, evidence_ref: ['clinical.imaging_text'] },
    perigastric_tissue: { value: perigastric, status: perigastricUncertain ? 'uncertain' : 'suggested', source: perigastricUncertain ? 'limited_frame' : 'clinical_text', confidence: 0.4, evidence_ref: ['clinical.imaging_text'] },
  } as unknown as NonNullable<SamReport['signs']>;
  const areaText = areaRatio != null ? `${(areaRatio * 100).toFixed(2)}%` : (zh ? '未返回' : 'n/a');
  const prose = zh
    ? `【超声所见】${location}见低回声占位性病变，大小约${lengthText}，最大厚度${thicknessText}。病灶呈${shape}，${boundary}。胃壁层次：${layer}；浆膜：${serosa}；胃周组织：${perigastric}。\n\n【辅助分析】${modelLabel} 当前帧病灶面积占比 ${areaText}。该结果为模型辅助证据，需医生在关键帧上修正。\n\n【分期倾向草稿】文本来源草稿 ${stageDraft}；结构化输出保持 cTx，不能覆盖经确认的壁层/浆膜证据门禁。`
    : `[Ultrasound findings] ${location}: hypoechoic lesion, size about ${lengthText}, max thickness ${thicknessText}. Morphology ${shape}; ${boundary}. Wall layers: ${layer}; serosa: ${serosa}; perigastric: ${perigastric}.\n\n[Assist analysis] ${modelLabel}; lesion area ratio on this frame ${areaText}. Model assist only; physician should correct on key frames.\n\n[Stage draft] Text-derived draft ${stageDraft}; structured output stays cTx and cannot override confirmed wall/serosa gates.`;
  return {
    recommended_stage: stage,
    recommendation_status: 'uncertain',
    signs,
    calibrated_confidence: 0.4,
    summary: prose,
    template_id: 'gc_us_t_report_template_v1',
    schema_version: 'gc_us_report_signs_v1',
    source_doc: '胃癌T分期自进化智能辅助诊断_报告模板_讨论版.docx',
    template_prose: prose,
    evidence: [
      { title: zh ? '病灶分割' : 'Lesion segmentation', detail: `${modelLabel}, ${polygon.length} contour points`, status: 'suggested', source: modelLabel },
      { title: zh ? '形态与边界' : 'Morphology and boundary', detail: `${shape}, ${boundary}`, status: 'suggested', source: 'mask_geometry' },
      { title: zh ? '层次与浆膜' : 'Layers and serosa', detail: `${layer}, ${serosa}`, status: 'uncertain', source: 'clinical_text_or_limited_frame' },
      { title: zh ? '文本分期草稿' : 'Text stage draft', detail: stageDraft, status: 'uncertain', source: 'clinical_text_draft_only' },
    ],
  };
}

function ToolRailButton({
  icon,
  label,
  hint,
  onClick,
  disabled = false,
  active = false,
  side = 'left',
  tone = 'cyan',
  showLabel = true,
}: {
  icon: React.ReactNode;
  label: string;
  hint: string;
  onClick: () => void;
  disabled?: boolean;
  active?: boolean;
  side?: 'left' | 'right';
  tone?: 'cyan' | 'fuchsia' | 'emerald' | 'amber' | 'violet' | 'orange' | 'sky' | 'rose' | 'lime' | 'slate';
  showLabel?: boolean;
}) {
  const toneClasses: Record<typeof tone, string> = {
    cyan: active
      ? 'bg-cyan-500/30 text-cyan-100'
      : 'text-cyan-200/85 hover:bg-white/10 hover:text-cyan-50',
    fuchsia: active
      ? 'bg-fuchsia-500/30 text-fuchsia-100'
      : 'text-fuchsia-200/85 hover:bg-white/10 hover:text-fuchsia-50',
    emerald: active
      ? 'bg-emerald-500/30 text-emerald-100'
      : 'text-emerald-200/85 hover:bg-white/10 hover:text-emerald-50',
    amber: active
      ? 'bg-amber-500/30 text-amber-100'
      : 'text-amber-200/85 hover:bg-white/10 hover:text-amber-50',
    violet: active
      ? 'bg-violet-500/30 text-violet-100'
      : 'text-violet-200/85 hover:bg-white/10 hover:text-violet-50',
    orange: active
      ? 'bg-orange-500/30 text-orange-100'
      : 'text-orange-200/85 hover:bg-white/10 hover:text-orange-50',
    sky: active
      ? 'bg-sky-500/30 text-sky-100'
      : 'text-sky-200/85 hover:bg-white/10 hover:text-sky-50',
    rose: active
      ? 'bg-rose-500/30 text-rose-100'
      : 'text-rose-200/85 hover:bg-white/10 hover:text-rose-50',
    lime: active
      ? 'bg-lime-500/30 text-lime-100'
      : 'text-lime-200/85 hover:bg-white/10 hover:text-lime-50',
    slate: active
      ? 'bg-white/20 text-white'
      : 'text-slate-300 hover:bg-white/10 hover:text-white',
  };
  // Keep hover hints outside the ultrasound canvas so they do not cover the lesion.
  const tooltipPosition = side === 'left'
    ? 'right-full mr-2 top-1/2 -translate-y-1/2'
    : 'left-full ml-2 top-1/2 -translate-y-1/2';
  return (
    <div className="group relative w-full">
      <button
        type="button"
        aria-label={`${label}. ${hint}`}
        title={`${label}: ${hint}`}
        disabled={disabled}
        onClick={onClick}
        className={`flex w-full items-center justify-center rounded-md transition-all focus:outline-none focus:ring-2 focus:ring-cyan-300/50 disabled:cursor-not-allowed disabled:opacity-35 ${
          showLabel
            ? 'min-h-10 flex-col gap-0.5 px-1 py-1.5 sm:min-h-[2.75rem]'
            : 'h-9 w-9'
        } ${toneClasses[tone]}`}
      >
        {icon}
        {showLabel ? (
          <span className="max-w-full text-center text-[11px] font-semibold leading-tight tracking-tight sm:text-xs">
            {label}
          </span>
        ) : null}
      </button>
      <span className={`pointer-events-none absolute z-[260] w-44 rounded-md border border-white/15 bg-slate-950/95 px-2 py-1.5 text-[10px] leading-relaxed text-slate-200 opacity-0 shadow-xl transition-opacity group-hover:opacity-100 group-focus-within:opacity-100 ${tooltipPosition}`}>
        <span className="font-semibold text-white">{label}</span>
        <span className="mt-0.5 block text-slate-400">{hint}</span>
      </span>
    </div>
  );
}

function ToolRailDivider() {
  return <div className="tool-rail-divider mx-auto my-0.5 h-px w-[85%] bg-white/15" aria-hidden="true" />;
}

function ToolRailSectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div className="w-full px-1 pb-1 pt-1.5 text-center text-[11px] font-bold tracking-wide text-slate-200 sm:text-xs">
      {children}
    </div>
  );
}

function FloatingToolGroup({
  children,
  accent = 'default',
}: {
  children: React.ReactNode;
  accent?: 'default' | 'cyan' | 'sky' | 'violet' | 'amber';
}) {
  const accentBorder =
    accent === 'cyan' ? 'border-cyan-400/25'
      : accent === 'sky' ? 'border-sky-400/30'
        : accent === 'violet' ? 'border-violet-400/25'
          : accent === 'amber' ? 'border-amber-400/25'
            : 'border-white/10';
  return (
    <div className={`flex items-center gap-0.5 rounded-lg border ${accentBorder} bg-black/70 px-1 py-0.5 backdrop-blur-md`}>
      {children}
    </div>
  );
}

function FloatingToolButton({
  icon,
  label,
  title,
  onClick,
  disabled = false,
  active = false,
  tone = 'slate',
  emphasize = false,
}: {
  icon: React.ReactNode;
  label: string;
  title: string;
  onClick: () => void;
  disabled?: boolean;
  active?: boolean;
  tone?: 'slate' | 'amber' | 'violet' | 'sky' | 'cyan';
  emphasize?: boolean;
}) {
  const toneActive: Record<typeof tone, string> = {
    slate: 'bg-white/20 text-white',
    amber: 'bg-amber-500/30 text-amber-100',
    violet: 'bg-violet-500/55 text-white',
    sky: 'bg-sky-500/45 text-white',
    cyan: 'bg-cyan-500/30 text-cyan-100',
  };
  const toneIdle: Record<typeof tone, string> = {
    slate: 'text-gray-400 hover:bg-white/10 hover:text-white',
    amber: 'text-amber-200/90 hover:bg-amber-400/15 hover:text-amber-50',
    violet: 'text-violet-200/90 hover:bg-violet-400/15 hover:text-violet-50',
    sky: 'text-sky-100 hover:bg-sky-400/20 hover:text-white',
    cyan: 'text-cyan-200/90 hover:bg-cyan-400/15 hover:text-cyan-50',
  };
  return (
    <button
      type="button"
      title={title}
      aria-label={title}
      disabled={disabled}
      onClick={onClick}
      className={`inline-flex items-center gap-1 rounded-md px-1.5 py-1.5 transition-all disabled:cursor-not-allowed disabled:opacity-40 ${
        emphasize ? 'px-2.5 text-[11px] font-extrabold' : 'text-[10px] font-semibold'
      } ${active ? toneActive[tone] : toneIdle[tone]}`}
    >
      {icon}
      <span>{label}</span>
    </button>
  );
}

function HistoryMaskThumbnail({
  entry,
  frameDataUrl,
  mediaMode,
  videoTime,
  zh = true,
}: {
  entry: MaskHistoryEntry;
  frameDataUrl: string | null;
  mediaMode: MediaMode;
  videoTime: number;
  zh?: boolean;
}) {
  const [thumbnail, setThumbnail] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (!frameDataUrl) {
      return () => {
        cancelled = true;
      };
    }
    const image = new Image();
    image.onload = () => {
      if (cancelled) return;
      const canvas = document.createElement('canvas');
      canvas.width = 320;
      canvas.height = 180;
      const context = canvas.getContext('2d');
      if (!context) return;
      context.fillStyle = '#050608';
      context.fillRect(0, 0, canvas.width, canvas.height);
      const scale = Math.min(canvas.width / image.naturalWidth, canvas.height / image.naturalHeight);
      const drawWidth = image.naturalWidth * scale;
      const drawHeight = image.naturalHeight * scale;
      const offsetX = (canvas.width - drawWidth) / 2;
      const offsetY = (canvas.height - drawHeight) / 2;
      context.drawImage(image, offsetX, offsetY, drawWidth, drawHeight);

      const historicalFrame = mediaMode === 'video'
        ? nearestOverrideFrame(entry.override.video_frames || [], videoTime, Number.POSITIVE_INFINITY)
        : null;
      const lesionPolygon = historicalFrame?.mask_polygon || entry.override.mask_polygon || [];
      const lumenPolygon = historicalFrame?.lumen_polygon || entry.lumen_override?.lumen_polygon || [];
      const lumenBox = historicalFrame?.lumen_bbox || entry.lumen_override?.lumen_bbox;
      const sourceWidth = historicalFrame?.roi_bbox
        ? entry.override.imageWidth
        : entry.override.imageWidth || image.naturalWidth;
      const sourceHeight = entry.override.imageHeight || image.naturalHeight;
      const drawPolygon = (polygon: number[][], stroke: string, fill: string) => {
        if (polygon.length < 3) return;
        context.beginPath();
        polygon.forEach(([x, y], index) => {
          const px = offsetX + (Number(x) / sourceWidth) * drawWidth;
          const py = offsetY + (Number(y) / sourceHeight) * drawHeight;
          if (index === 0) context.moveTo(px, py);
          else context.lineTo(px, py);
        });
        context.closePath();
        context.fillStyle = fill;
        context.fill();
        context.strokeStyle = stroke;
        context.lineWidth = 2;
        context.stroke();
      };
      drawPolygon(lesionPolygon, '#22d3ee', 'rgba(34, 211, 238, 0.18)');
      drawPolygon(lumenPolygon, '#e879f9', 'rgba(232, 121, 249, 0.12)');
      if (lumenBox) {
        context.strokeStyle = '#f0abfc';
        context.setLineDash([5, 3]);
        context.strokeRect(
          offsetX + (lumenBox.x1 / sourceWidth) * drawWidth,
          offsetY + (lumenBox.y1 / sourceHeight) * drawHeight,
          ((lumenBox.x2 - lumenBox.x1) / sourceWidth) * drawWidth,
          ((lumenBox.y2 - lumenBox.y1) / sourceHeight) * drawHeight,
        );
        context.setLineDash([]);
      }
      setThumbnail(canvas.toDataURL('image/jpeg', 0.78));
    };
    image.onerror = () => {
      if (!cancelled) setThumbnail(null);
    };
    image.src = frameDataUrl;
    return () => {
      cancelled = true;
    };
  }, [entry, frameDataUrl, mediaMode, videoTime]);

  return frameDataUrl && thumbnail ? (
    <img
      src={thumbnail}
      alt={zh ? '历史遮罩预览' : 'History mask preview'}
      className="h-20 w-32 shrink-0 rounded border border-white/10 bg-black object-contain"
    />
  ) : (
    <div className="flex h-20 w-32 shrink-0 items-center justify-center rounded border border-white/10 bg-black/40 text-[9px] text-slate-500">
      {zh ? '暂无预览' : 'No preview'}
    </div>
  );
}

export function InteractiveSegPanel({
  patient,
  override,
  onOverrideChange,
  lumenOverride = null,
  onLumenOverrideChange,
  onImagingAssist,
  onSystemReport,
  onDinoFeatures,
  onUnifiedAgentRun,
  unifiedAgentBusy = false,
  onWorkflowStep,
  onExplainableComplete,
  onReportEvidenceImages,
  inline = false,
}: InteractiveSegPanelProps) {
  const { language } = useSettings();
  const zh = language !== 'en';
  const { readerId: accountReaderId, authHeaders } = useDoctorAccount();
  const simpleVideoMode = inline && patient?.phase === 'reader_v150';
  const [simplePromptMode, setSimplePromptMode] = useState<ActiveSamPromptMode>('box');
  const [simpleEditMode, setSimpleEditMode] = useState(false);
  const [simpleEditLayer, setSimpleEditLayer] = useState<ContourLayer>('lesion');
  const [simpleToolsOpen, setSimpleToolsOpen] = useState(true);
  const [workflowBusy, setWorkflowBusy] = useState(false);
  const [workflowStepLabel, setWorkflowStepLabel] = useState<string | null>(null);
  const [lesionAutoBusy, setLesionAutoBusy] = useState(false);
  const [simplePromptBox, setSimplePromptBox] = useState<{ x1: number; y1: number; x2: number; y2: number } | null>(null);
  const [activeSamPromptLabel, setActiveSamPromptLabel] = useState<ActiveSamPromptLabel>('positive');
  const [showExplainable, setShowExplainable] = useState(false);
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<EditMode>('soft');
  const [mediaMode, setMediaMode] = useState<MediaMode>('image');
  const [activeLayer, setActiveLayer] = useState<ContourLayer>('lesion');
  const [points, setPoints] = useState<number[][]>([]);
  const [wallPoints, setWallPoints] = useState<number[][]>([]);
  const [imgLoaded, setImgLoaded] = useState(false);
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [dragLayer, setDragLayer] = useState<DragLayer | null>(null);
  const [saving, setSaving] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyBusy, setHistoryBusy] = useState(false);
  const [maskHistory, setMaskHistory] = useState<MaskHistoryEntry[]>([]);
  const [historyPreviewId, setHistoryPreviewId] = useState<string | null>(null);
  const [samBusy, setSamBusy] = useState(false);
  const [samReport, setSamReport] = useState<SamReport | null>(null);
  const [dinoBusy, setDinoBusy] = useState(false);
  const [dinoResult, setDinoResult] = useState<DinoFeatureResult | null>(null);
  const [segmentationModel, setSegmentationModel] = useState<LesionSegmentationModel>('sabm_sam2_guided');
  const [segmentationBusy, setSegmentationBusy] = useState(false);
  const [segmentationModelResult, setSegmentationModelResult] = useState<{
    model?: string;
    lesion_area_ratio?: number;
    validation_summary?: Record<string, unknown>;
    error?: string;
  } | null>(null);
  const [samClicks, setSamClicks] = useState<Array<{ x: number; y: number; label: 'positive' | 'negative' }>>([]);
  const [promptStrokes, setPromptStrokes] = useState<ActiveSamStroke[]>([]);
  const [activePromptStroke, setActivePromptStroke] = useState<ActiveSamStroke | null>(null);
  const [nnInteractiveClicks, setNnInteractiveClicks] = useState<Array<{ x: number; y: number; label: 'positive' | 'negative' }>>([]);
  const [samBoxPreview, setSamBoxPreview] = useState<{ x1: number; y1: number; x2: number; y2: number } | null>(null);
  const [samAvailable, setSamAvailable] = useState<boolean | null>(null);
  const [nnInteractiveBusy, setNnInteractiveBusy] = useState(false);
  const [nnInteractiveMode, setNnInteractiveMode] = useState(false);
  const [nnInteractiveTarget, setNnInteractiveTarget] = useState<'lesion' | 'lumen'>('lesion');
  const [nnInteractiveAvailable, setNnInteractiveAvailable] = useState<boolean | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [roiMode, setRoiMode] = useState<'predicted' | 'doctor' | 'auto'>('predicted');
  const [lumenBox, setLumenBox] = useState<LumenBBox | null>(null);
  const [lumenPolygon, setLumenPolygon] = useState<number[][]>([]);
  const [lumenConfidence, setLumenConfidence] = useState<number | null>(null);
  const [lumenBusy, setLumenBusy] = useState(false);
  const [lumenSamBusy, setLumenSamBusy] = useState(false);
  const [lumenEditMode, setLumenEditMode] = useState(false);
  const [lumenSaving, setLumenSaving] = useState(false);
  const [lumenResultMeta, setLumenResultMeta] = useState<{
    detector_backend_id?: string;
    sam_backend_id?: string;
    sam_score?: number;
    source?: LumenOverride['source'];
    error?: string;
  } | null>(null);
  const [videos, setVideos] = useState<VideoInfo[]>([]);
  const [videoUrl, setVideoUrl] = useState<string>('');
  const [videoTime, setVideoTime] = useState(0);
  const [videoDuration, setVideoDuration] = useState(0);
  const [videoPlaybackRate, setVideoPlaybackRate] = useState<number>(1);
  const videoPlaybackRateRef = useRef<number>(1);
  videoPlaybackRateRef.current = videoPlaybackRate;
  const [isPlaying, setIsPlaying] = useState(false);
  const [trackOnPlay, setTrackOnPlay] = useState(false);
  const [trackingPrepared, setTrackingPrepared] = useState(false);
  const [precomputeBusy, setPrecomputeBusy] = useState(false);
  const [precomputeProgress, setPrecomputeProgress] = useState<string | null>(null);
  /** Global long-task progress (tracking / assist); shown as a page-level bar, not only button text. */
  const [taskProgress, setTaskProgress] = useState<{
    label: string;
    step: number;
    totalSteps: number;
    detail?: string | null;
  } | null>(null);
  const [keyCandidates, setKeyCandidates] = useState<KeyframeCandidate[]>([]);
  const [keyBusy, setKeyBusy] = useState(false);
  const [pendingOpenVideoSam, setPendingOpenVideoSam] = useState(false);
  const [pendingKeyframeRequest, setPendingKeyframeRequest] = useState(false);
  /** Freeze display frame while editing vertices / after SAM — prevents click refresh flicker. */
  const [frameFrozen, setFrameFrozen] = useState(false);
  const [propagateBusy, setPropagateBusy] = useState(false);
  const [propagateProgress, setPropagateProgress] = useState<string | null>(null);
  const [videoFrameOverrides, setVideoFrameOverrides] = useState<VideoMaskFrameOverride[]>([]);
  const [frameDataUrl, setFrameDataUrl] = useState<string | null>(null);
  const [layerResult, setLayerResult] = useState<LayerAnalyzeResult | null>(null);
  const [wallAnalysisOpen, setWallAnalysisOpen] = useState(false);
  const [viewFocusBox, setViewFocusBox] = useState<ViewFocusBox | null>(null);
  const [viewFocusMode, setViewFocusMode] = useState<ViewFocusMode | null>(null);
  /** Mouse-follow circular magnifier (meeting B6); position kept in a ref to avoid React churn. */
  const [magnifierOn, setMagnifierOn] = useState(false);
  const magnifierPosRef = useRef<{ cx: number; cy: number; ix: number; iy: number } | null>(null);
  const [layerPick, setLayerPick] = useState<{ x: number; y: number } | null>(null);
  const [undoLen, setUndoLen] = useState(0);
  const [hasOriginal, setHasOriginal] = useState(false);
  const trackingClientIdRef = useRef(`tab_${Math.random().toString(36).slice(2)}`);
  const trackingSessionId = useMemo(() => {
    if (mediaMode !== 'video' || !videoUrl || !patient) return '';
    const raw = `${trackingClientIdRef.current}__${patient.patient_id || patient.id}__${videoUrl}`;
    return raw.replace(/[^A-Za-z0-9_-]+/g, '_').slice(0, 160);
  }, [mediaMode, patient, videoUrl]);

  useEffect(() => {
    if (!inline || patient?.phase !== 'reader_v150') return;
    setOpen(true);
    setPendingOpenVideoSam(true);
    setMediaMode('video');
    setMode('sam');
  }, [inline, patient?.id, patient?.phase]);

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const trackBusyRef = useRef(false);
  const lastTrackAtRef = useRef(0);
  const pointsRef = useRef<number[][]>([]);
  // Keep the latest successful model contour available to redraw callbacks.
  // Video pause/resize callbacks can briefly run with an older React closure.
  const generatedLesionRef = useRef<number[][]>([]);
  const generatedLesionPatientRef = useRef<string | null>(null);
  const initializedPatientRef = useRef<string | null>(null);
  const initializedLumenPatientRef = useRef<string | null>(null);
  const contourInteractionRef = useRef(false);
  const wallPointsRef = useRef<number[][]>([]);
  const dragIndexRef = useRef<number | null>(null);
  const dragLayerRef = useRef<DragLayer | null>(null);
  const dragSoftRef = useRef(true);
  const frameFrozenRef = useRef(false);
  const videoFrameOverridesRef = useRef<VideoMaskFrameOverride[]>([]);
  const captureCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const undoStackRef = useRef<Array<{ lesion: number[][]; wall: number[][] }>>([]);
  const originalRef = useRef<{ lesion: number[][]; wall: number[][] } | null>(null);
  const playbackRafRef = useRef<number | null>(null);
  const lastPolyClickRef = useRef<{ t: number; pt: number[] } | null>(null);
  const applyAreaKeyframesRef = useRef<(frames: VideoMaskFrameOverride[]) => Promise<void>>(async () => {});
  const playbackUiAtRef = useRef(0);
  const playbackStateAtRef = useRef(0);
  const scrubbingRef = useRef(false);
  const scrubPreviewRafRef = useRef<number | null>(null);
  const lastScrubRedrawAtRef = useRef(0);
  const videoProgressRefs = useRef<Array<HTMLInputElement | null>>([]);
  const videoTimeLabelRefs = useRef<Array<HTMLSpanElement | null>>([]);
  const taskProgressStartedAtRef = useRef<number | null>(null);
  const [taskElapsedSec, setTaskElapsedSec] = useState(0);
  const predictKeyframesRef = useRef<(candidates: KeyframeCandidate[]) => Promise<void>>(async () => {});
  const reportEvidenceGenerationRef = useRef(0);
  const runLesionModelRef = useRef<
    (
      imgPt: number[] | null,
      box: { x1: number; y1: number; x2: number; y2: number } | null,
      clicks: Array<{ x: number; y: number; label: 'positive' | 'negative' }>,
      modelOverride?: LesionSegmentationModel,
    ) => Promise<number[][] | null>
  >(async () => null);
  const samAbortRef = useRef<AbortController | null>(null);
  const samGenRef = useRef(0);
  const draggingRef = useRef(false);
  const samBusyRef = useRef(false);
  const samClicksRef = useRef<Array<{ x: number; y: number; label: 'positive' | 'negative' }>>([]);
  const promptStrokesRef = useRef<ActiveSamStroke[]>([]);
  const activePromptStrokeRef = useRef<ActiveSamStroke | null>(null);
  const pendingPromptPointRef = useRef<number[] | null>(null);
  const promptStrokeRafRef = useRef<number | null>(null);
  const samBoxDragRef = useRef<{ x0: number; y0: number; x1: number; y1: number } | null>(null);
  const contourPrepActionsRef = useRef<string[]>([]);
  const nnInteractiveSessionRef = useRef<NnInteractiveSessionState>({
    key: '',
    id: '',
    initialized: false,
  });
  const savingRef = useRef(false);
  const persistChainRef = useRef<Promise<boolean>>(Promise.resolve(true));
  const maskAuditSessionRef = useRef('');
  const maskAuditSequenceRef = useRef(0);
  const workflowTraceRef = useRef<WorkflowTraceStep[]>([]);
  const maskAuditRef = useRef<
    (eventType: MaskAuditEventType, payload: Record<string, unknown>) => void
  >(() => {});
  const persistOverrideRef = useRef<
    (action: string, options?: PersistOverrideOptions) => Promise<boolean>
  >(async () => false);
  const persistLumenOverrideRef = useRef<(silent?: boolean) => Promise<boolean>>(async () => false);
  const nnInteractiveRequestRef = useRef(0);
  const nnInteractiveAbortRef = useRef<AbortController | null>(null);
  const lumenBoxRef = useRef<LumenBBox | null>(null);
  const lumenPolygonRef = useRef<number[][]>([]);
  const lumenBoxDragRef = useRef<{
    handle: LumenBoxHandle;
    start: LumenBBox;
    origin: number[];
  } | null>(null);
  // Keep playback listeners attached while React redraws the canvas or tracks a frame.
  // Re-running the source effect on every state change would call video.load() and pause playback.
  const redrawRef = useRef<() => void>(() => {});
  const maybeTrackWhilePlayingRef = useRef<() => Promise<void>>(async () => {});
  useEffect(() => {
    pointsRef.current = points;
  }, [points]);
  useEffect(() => {
    promptStrokesRef.current = promptStrokes;
  }, [promptStrokes]);
  useEffect(() => {
    wallPointsRef.current = wallPoints;
  }, [wallPoints]);
  useEffect(() => {
    lumenBoxRef.current = lumenBox;
  }, [lumenBox]);
  useEffect(() => {
    lumenPolygonRef.current = lumenPolygon;
  }, [lumenPolygon]);
  useEffect(() => {
    dragIndexRef.current = dragIndex;
  }, [dragIndex]);
  useEffect(() => {
    dragLayerRef.current = dragLayer;
  }, [dragLayer]);
  useEffect(() => {
    frameFrozenRef.current = frameFrozen;
  }, [frameFrozen]);

  useEffect(() => {
    if (!patient?.id) {
      maskAuditSessionRef.current = '';
      maskAuditSequenceRef.current = 0;
      workflowTraceRef.current = [];
      maskAuditRef.current = () => {};
      return;
    }
    const params = typeof window !== 'undefined'
      ? new URLSearchParams(window.location.search)
      : null;
    const sessionId = `mask_${patient.id}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    const caseId = patient.id;
    const patientId = patient.patient_id;
    const readerId = accountReaderId || params?.get('reader_id') || 'workbench_reader';
    const round = params?.get('round') || 'round2';
    maskAuditSessionRef.current = sessionId;
    maskAuditSequenceRef.current = 0;
    workflowTraceRef.current = [];
    maskAuditRef.current = (eventType, payload) => {
      if (maskAuditSessionRef.current !== sessionId) return;
      const eventId = `${sessionId}:${++maskAuditSequenceRef.current}:${eventType}`;
      const operation = String(payload.operation || eventType);
      const outcome = String(payload.outcome || 'completed');
      const workflowStep: WorkflowTraceStep = {
        trace_id: String(payload.trace_id || eventId),
        step_id: operation,
        action: operation,
        status: outcome === 'error' ? 'error' : outcome === 'started' ? 'started' : 'completed',
        source: operation.includes('workflow') ? 'doctor' : operation.includes('segmentation') || operation.includes('detection') || operation.includes('propagation') ? 'model' : 'system',
        frame_time_sec: typeof payload.frame_time_sec === 'number' ? payload.frame_time_sec : null,
        input: payload.input && typeof payload.input === 'object' ? payload.input as Record<string, unknown> : undefined,
        output: payload.output && typeof payload.output === 'object' ? payload.output as Record<string, unknown> : undefined,
        error: typeof payload.error === 'string' ? payload.error : undefined,
        recorded_at: new Date().toISOString(),
      };
      workflowTraceRef.current = [...workflowTraceRef.current, workflowStep].slice(-160);
      onWorkflowStep?.(workflowStep);
      void fetch('/api/reader-audit/events', {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          event_id: eventId,
          event_type: eventType,
          session_id: sessionId,
          case_id: caseId,
          reader_id: readerId,
          round,
          patient_id: patientId,
          payload: {
            component: 'InteractiveSegPanel',
            ...payload,
          },
          client_recorded_at: new Date().toISOString(),
        }),
        keepalive: true,
      }).catch(() => {
        // Audit recording must not interrupt the reading workflow.
      });
    };
    return () => {
      maskAuditRef.current = () => {};
    };
  }, [accountReaderId, authHeaders, onWorkflowStep, patient?.id, patient?.patient_id]);

  useEffect(() => {
    const video = videoRef.current;
    if (playbackRafRef.current !== null) {
      cancelAnimationFrame(playbackRafRef.current);
      playbackRafRef.current = null;
    }
    video?.pause();
    if (video) {
      video.removeAttribute('src');
      video.load();
    }
    setIsPlaying(false);
    setVideoTime(0);
    setVideoDuration(0);
    setVideoUrl('');
    setVideos([]);
    setImgLoaded(false);
  }, [patient?.id]);

  const snapshotOriginal = useCallback((lesion: number[][], wall: number[][]) => {
    originalRef.current = { lesion: clonePoly(lesion), wall: clonePoly(wall) };
    undoStackRef.current = [];
    setUndoLen(0);
    setHasOriginal(true);
  }, []);

  const pushEditUndo = useCallback(() => {
    undoStackRef.current.push({
      lesion: clonePoly(pointsRef.current),
      wall: clonePoly(wallPointsRef.current),
    });
    if (undoStackRef.current.length > 40) undoStackRef.current.shift();
    setUndoLen(undoStackRef.current.length);
  }, []);

  const undoEdit = useCallback(() => {
    const prev = undoStackRef.current.pop();
    if (!prev) return;
    pointsRef.current = prev.lesion;
    wallPointsRef.current = prev.wall;
    setPoints(prev.lesion);
    setWallPoints(prev.wall);
    setUndoLen(undoStackRef.current.length);
    maskAuditRef.current('mask_event', {
      action: 'doctor_undo',
      lesion_points: prev.lesion.length,
      wall_points: prev.wall.length,
    });
    void persistOverrideRef.current('doctor_undo', { silent: true });
    setMessage(zh ? '已撤销上一步轮廓编辑' : 'Undid last contour edit');
  }, [zh]);

  const restoreOriginal = useCallback(() => {
    const orig = originalRef.current;
    if (!orig) return;
    pushEditUndo();
    pointsRef.current = clonePoly(orig.lesion);
    wallPointsRef.current = clonePoly(orig.wall);
    setPoints(clonePoly(orig.lesion));
    setWallPoints(clonePoly(orig.wall));
    maskAuditRef.current('mask_event', {
      action: 'doctor_restore_original',
      lesion_points: orig.lesion.length,
      wall_points: orig.wall.length,
    });
    void persistOverrideRef.current('doctor_restore_original', { silent: true });
    setMessage(zh ? '已恢复分割原始轮廓' : 'Restored original SAM/LabelMe contour');
  }, [pushEditUndo, zh]);

  const activePoints = activeLayer === 'wall' ? wallPoints : points;
  const historyPreview = historyPreviewId
    ? maskHistory.find((entry) => entry.id === historyPreviewId) || null
    : null;

  useEffect(() => {
    const patientKey = patient ? `${patient.id}:${patient.patient_id}` : null;
    const patientChanged = initializedPatientRef.current !== patientKey;
    if (patientChanged) {
      initializedPatientRef.current = patientKey;
      generatedLesionPatientRef.current = patientKey;
      generatedLesionRef.current = [];
      contourInteractionRef.current = false;
    }
    if (!patientChanged && contourInteractionRef.current) return;
    if (!patient) {
      setSamReport(null);
      setPoints([]);
      setWallPoints([]);
      samClicksRef.current = [];
      setSamClicks([]);
      promptStrokesRef.current = [];
      activePromptStrokeRef.current = null;
      setPromptStrokes([]);
      setActivePromptStroke(null);
      nnInteractiveAbortRef.current?.abort();
      nnInteractiveAbortRef.current = null;
      nnInteractiveRequestRef.current += 1;
      setNnInteractiveBusy(false);
      videoFrameOverridesRef.current = [];
      setVideoFrameOverrides([]);
      setImgLoaded(false);
      pointsRef.current = [];
      wallPointsRef.current = [];
      originalRef.current = null;
      setHasOriginal(false);
      setViewFocusBox(null);
      setViewFocusMode(null);
      return;
    }
    if (!(inline && patient.phase === 'reader_v150')) setOpen(false);
    setSamReport(null);
    setDinoResult(null);
    setSegmentationModelResult(null);
    setSegmentationBusy(false);
    onDinoFeatures?.(null);
    samClicksRef.current = [];
    setSamClicks([]);
    setSimplePromptMode('box');
    setActiveSamPromptLabel('positive');
    setSimpleEditMode(false);
    setNnInteractiveBusy(false);
    setNnInteractiveClicks([]);
    nnInteractiveAbortRef.current?.abort();
    nnInteractiveAbortRef.current = null;
    nnInteractiveRequestRef.current += 1;
    setPromptStrokes([]);
    promptStrokesRef.current = [];
    activePromptStrokeRef.current = null;
    setActivePromptStroke(null);
    setNnInteractiveMode(false);
    setNnInteractiveTarget('lesion');
    nnInteractiveSessionRef.current = { key: '', id: '', initialized: false };
    setSimpleToolsOpen(true);
    setSimplePromptBox(null);
    setLumenEditMode(false);
    pointsRef.current = [];
    wallPointsRef.current = [];
    originalRef.current = null;
    setPoints([]);
    setWallPoints([]);
    setHasOriginal(false);
    setUndoLen(0);
    videoFrameOverridesRef.current = [];
    setVideoFrameOverrides([]);
    setKeyCandidates([]);
    setPendingKeyframeRequest(false);
    setTrackingPrepared(false);
    setPrecomputeBusy(false);
    setPrecomputeProgress(null);
    setRoiMode('predicted');
    if (patientChanged) return;
    if (override?.mask_polygon?.length || override?.wall_polygon?.length) {
      const lesion = override?.mask_polygon?.length
        ? prepareEditableContour(
          override.mask_polygon.map((p) => [Number(p[0]), Number(p[1])]),
          LESION_CONTOUR_MAX_POINTS,
        )
        : [];
      const wall = override?.wall_polygon?.length
        ? prepareEditableContour(
          override.wall_polygon.map((p) => [Number(p[0]), Number(p[1])]),
          WALL_CONTOUR_MAX_POINTS,
        )
        : [];
      setPoints(lesion);
      setWallPoints(wall);
      snapshotOriginal(lesion, wall);
      return;
    }
  }, [inline, patient, patient?.id, patient?.patient_id, patient?.phase, override?.updated_at, override?.mask_polygon, override?.wall_polygon, snapshotOriginal, onDinoFeatures]);

  useEffect(() => {
    setHistoryOpen(false);
    setHistoryBusy(false);
    setMaskHistory([]);
    setHistoryPreviewId(null);
  }, [patient?.id]);

  useEffect(() => {
    const patientKey = patient ? `${patient.id}:${patient.patient_id}` : null;
    const patientChanged = initializedLumenPatientRef.current !== patientKey;
    if (patientChanged) {
      initializedLumenPatientRef.current = patientKey;
      setLumenBox(null);
      setLumenPolygon([]);
      setLumenConfidence(null);
      setLumenEditMode(false);
      setLumenResultMeta(null);
      lumenBoxRef.current = null;
      lumenPolygonRef.current = [];
      return;
    }
    if (!patient) {
      setLumenBox(null);
      setLumenPolygon([]);
      setLumenConfidence(null);
      setLumenEditMode(false);
      setLumenResultMeta(null);
      return;
    }
    setLumenBox(lumenOverride?.lumen_bbox ? normalizeLumenBBox(lumenOverride.lumen_bbox) : null);
    setLumenPolygon(lumenOverride?.lumen_polygon ? clonePoly(lumenOverride.lumen_polygon) : []);
    setLumenConfidence(lumenOverride?.lumen_confidence ?? null);
    setLumenEditMode(false);
    setViewFocusBox(null);
    setViewFocusMode(null);
    setLumenResultMeta(lumenOverride ? {
      detector_backend_id: lumenOverride.detector_backend_id,
      sam_backend_id: lumenOverride.sam_backend_id,
      sam_score: lumenOverride.sam_score,
      source: lumenOverride.source,
    } : null);
  }, [patient, patient?.id, patient?.patient_id, lumenOverride, lumenOverride?.updated_at, lumenOverride?.lumen_bbox, lumenOverride?.lumen_polygon, lumenOverride?.lumen_confidence, lumenOverride?.detector_backend_id, lumenOverride?.sam_backend_id, lumenOverride?.sam_score, lumenOverride?.source]);

  const refreshNnInteractiveStatus = useCallback(async (): Promise<boolean> => {
    try {
      const res = await fetch('/api/agent/nninteractive', { cache: 'no-store' });
      const payload = await res.json() as { available?: boolean };
      const available = payload.available === true;
      setNnInteractiveAvailable(available);
      return available;
    } catch {
      setNnInteractiveAvailable(false);
      return false;
    }
  }, []);

  useEffect(() => {
    void refreshNnInteractiveStatus();
  }, [refreshNnInteractiveStatus]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch('/api/agent/sam-interactive');
        const data = await res.json();
        if (!cancelled) setSamAvailable(Boolean(data.available));
      } catch {
        if (!cancelled) setSamAvailable(false);
      }
    })();
    return () => { cancelled = true; };
  }, [open]);

  useEffect(() => {
    if (!open || !patient) return;
    let cancelled = false;
    (async () => {
      // Always resolve from disk index (crop_ui / qualified / public) — no upload.
      const fromPatient = patient.video_urls || [];
      let list = fromPatient;
      // Reader-study media is already case-resolved. Other queues can use the
      // allowlisted patient video catalog, including external centers.
      if (patient.phase !== 'reader_v150') {
        try {
          const res = await fetch(
            `/api/patients/videos?patientId=${encodeURIComponent(patient.patient_id)}&limit=40`,
          );
          const data = await res.json();
          const remote = (data.videos || []) as VideoInfo[];
          if (remote.length) {
            const seen = new Set(list.map((v) => v.url));
            list = [...list, ...remote.filter((v) => !seen.has(v.url))];
          }
        } catch {
          /* keep fromPatient */
        }
      }
      if (cancelled) return;
      setVideos(list);
      setVideoUrl((prev) => {
        if (prev && list.some((v) => v.url === prev)) return prev;
        return list[0]?.url || '';
      });
      if (pendingOpenVideoSam && list.length) {
        setPendingOpenVideoSam(false);
        setVideoUrl(list[0].url);
        setMediaMode('video');
        setMode('sam');
        setMessage(
          zh
            ? `已打开对应视频：${list[0].filename}，请框选病灶`
            : `Opened ${list[0].filename}; draw an ROI box around the lesion`,
        );
      } else if (pendingOpenVideoSam && !list.length) {
        setPendingOpenVideoSam(false);
        setMessage(zh ? '未找到该病例对应视频（crop_ui/阅片库）' : 'No matching patient video on disk');
      }
    })();
    return () => { cancelled = true; };
  }, [open, patient?.patient_id, patient?.video_urls, pendingOpenVideoSam, zh]);

  useEffect(() => {
    if (!simpleVideoMode || mediaMode !== 'video' || !videoUrl || !videos.length) return;
    const filename = videos.find((video) => video.url === videoUrl)?.filename || videos[0].filename;
    setMessage(
      zh
        ? `已打开对应视频：${filename}，请框选病灶`
        : `Opened ${filename}; draw an ROI box around the lesion`,
    );
  }, [mediaMode, simpleVideoMode, videoUrl, videos, zh]);

  const openPatientVideoSam = useCallback(() => {
    if (!videos.length) {
      setMessage(zh ? '未找到该病例对应视频（crop_ui/阅片库）' : 'No matching patient video on disk');
      return;
    }
    const url = videoUrl || videos[0].url;
    setVideoUrl(url);
    setMediaMode('video');
    setMode('sam');
    setMessage(
      zh
        ? `已打开对应视频：${videos.find((v) => v.url === url)?.filename || 'video'}，请框选病灶`
        : `Opened patient video; draw an ROI box around the lesion`,
    );
  }, [videos, videoUrl, zh]);

  const scoreKeyframes = useCallback(async () => {
    if (!videoUrl || keyBusy) return;
    setKeyBusy(true);
    setMessage(zh ? '邻域关键帧打分中…' : 'Scoring neighborhood keyframes…');
    try {
      const res = await fetch('/api/agent/video/keyframes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          video_url: videoUrl,
          anchor_sec: videoTime,
          window_sec: 2.0,
          top_k: 5,
        }),
      });
      const data = await res.json() as { ok?: boolean; error?: string; keyframes?: KeyframeCandidate[] };
      if (!res.ok || !data.ok) throw new Error(data.error || 'keyframe failed');
      const candidates = (data.keyframes || []).map((candidate) => ({
        ...candidate,
        prediction_status: pointsRef.current.length >= 3 ? 'pending' as const : 'needs_roi' as const,
      }));
      setKeyCandidates(candidates);
      if (pointsRef.current.length < 3) {
        setMessage(
          zh
            ? `已选出 ${candidates.length} 个关键帧；请先框选病灶，再生成对应病灶预测`
            : `${candidates.length} keyframes selected; draw an ROI box first to predict the lesion on each frame`,
        );
      } else {
        await predictKeyframesRef.current(candidates);
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'keyframe failed');
    } finally {
      setKeyBusy(false);
    }
  }, [keyBusy, videoTime, videoUrl, zh]);

  const applyAreaKeyframesFromFrames = useCallback(async (frames: VideoMaskFrameOverride[]) => {
    const candidates = selectTopAreaKeyframes(frames, 5, 0.5);
    setKeyCandidates(candidates);
    if (!candidates.length) {
      setMessage(
        zh
          ? '跟踪扩散完成，但未能按病灶面积选出关键帧'
          : 'Tracking finished, but no area-based keyframes were selected',
      );
      return;
    }
    setMessage(
      zh
        ? `跟踪完成；算法附带 ${candidates.length} 个面积关键帧（仅辅助）。请医生 scrub 自选关键帧后分析`
        : `Tracking done; ${candidates.length} area keyframes are optional hints — scrub and pick frames yourself for analysis`,
    );
    const video = videoRef.current;
    if (!video?.videoWidth) return;
    const restore = video.currentTime || 0;
    const wasFrozen = frameFrozenRef.current;
    video.pause();
    setFrameFrozen(true);
    frameFrozenRef.current = true;
    try {
      for (const candidate of candidates) {
        await seekVideoForAgent(video, candidate.timestamp_sec);
        const canvas = document.createElement('canvas');
        canvas.width = Math.max(1, Math.round(video.videoWidth / 4));
        canvas.height = Math.max(1, Math.round(video.videoHeight / 4));
        const ctx = canvas.getContext('2d');
        if (!ctx) continue;
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        const thumb = canvas.toDataURL('image/jpeg', 0.72);
        setKeyCandidates((current) => current.map((item) => (
          item.timestamp_sec === candidate.timestamp_sec
            ? { ...item, thumb_url: thumb }
            : item
        )));
      }
    } finally {
      await seekVideoForAgent(video, restore);
      setVideoTime(restore);
      setFrameFrozen(wasFrozen);
      frameFrozenRef.current = wasFrozen;
      redrawRef.current();
    }
  }, [zh]);

  useEffect(() => {
    applyAreaKeyframesRef.current = applyAreaKeyframesFromFrames;
  }, [applyAreaKeyframesFromFrames]);

  useEffect(() => {
    if (!pendingKeyframeRequest || mediaMode !== 'video' || !videoUrl || keyBusy) return;
    setPendingKeyframeRequest(false);
    void scoreKeyframes();
  }, [keyBusy, mediaMode, pendingKeyframeRequest, scoreKeyframes, videoUrl]);

  const extractDinoFeatures = useCallback(async () => {
    if (!patient || dinoBusy) return;
    setDinoBusy(true);
    setMessage(zh ? 'DINO 特征提取中，首次加载可能较慢…' : 'Extracting DINO features; first load may take longer…');
    try {
      const frame = await videoOrImageToSamFrame(
        videoRef.current,
        imgRef.current,
        mediaMode === 'video',
        1024,
      );
      const scale = frame.scale || 1;
      const response = await fetch('/api/agent/dino/features', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          case_id: patient.patient_id,
          frame_time: mediaMode === 'video'
            ? Number(videoRef.current?.currentTime ?? videoTime)
            : 0,
          frame_png_b64: frame.b64,
          image_width: frame.width,
          image_height: frame.height,
          lesion_polygon: pointsRef.current.map((point) => [point[0] * scale, point[1] * scale]),
          wall_polygon: wallPointsRef.current.map((point) => [point[0] * scale, point[1] * scale]),
          layer_index: 11,
          layer_indices: DINO_LAYER_INDICES,
        }),
      });
      const payload = await response.json() as { ok?: boolean; result?: DinoFeatureResult; error?: string };
      if (!response.ok || !payload.ok || !payload.result?.available) {
        throw new Error(payload.error || payload.result?.error || 'DINO feature extraction unavailable');
      }
      setDinoResult(payload.result);
      onDinoFeatures?.(payload.result);
      setMessage(
        zh
          ? `DINO 多层特征已提取：${payload.result.layers?.length || 1} 个 layer，${payload.result.token_grid?.join(' × ') || '未知'} token 网格`
          : `DINO multi-layer features extracted: ${payload.result.layers?.length || 1} layers`,
      );
    } catch (error) {
      const failure: DinoFeatureResult = {
        available: false,
        error: error instanceof Error ? error.message : 'DINO feature extraction failed',
      };
      setDinoResult(failure);
      onDinoFeatures?.(failure);
      setMessage(failure.error || 'DINO feature extraction failed');
    } finally {
      setDinoBusy(false);
    }
  }, [dinoBusy, mediaMode, onDinoFeatures, patient, videoTime, zh]);

  const captureFrameDataUrl = useCallback(() => {
    const video = videoRef.current;
    if (mediaMode === 'video' && video && video.videoWidth) {
      const c = document.createElement('canvas');
      c.width = video.videoWidth;
      c.height = video.videoHeight;
      const ctx = c.getContext('2d');
      if (!ctx) return null;
      ctx.drawImage(video, 0, 0);
      const url = c.toDataURL('image/jpeg', 0.92);
      setFrameDataUrl(url);
      return url;
    }
    const img = imgRef.current;
    if (img?.naturalWidth) {
      const c = document.createElement('canvas');
      c.width = img.naturalWidth;
      c.height = img.naturalHeight;
      const ctx = c.getContext('2d');
      if (!ctx) return null;
      ctx.drawImage(img, 0, 0);
      const url = c.toDataURL('image/jpeg', 0.92);
      setFrameDataUrl(url);
      return url;
    }
    return null;
  }, [mediaMode]);

  const frameSize = useMemo(() => {
    const video = videoRef.current;
    if (mediaMode === 'video' && video?.videoWidth) {
      return { width: video.videoWidth, height: video.videoHeight };
    }
    const img = imgRef.current;
    if (img?.naturalWidth) return { width: img.naturalWidth, height: img.naturalHeight };
    return null;
  }, [mediaMode, videoTime, imgLoaded, points.length]);

  useEffect(() => {
    if (!onImagingAssist || points.length < 3 || !frameSize) return;
    onImagingAssist({
      layerResult,
      lesionPolygon: points,
      wallPolygon: wallPoints,
      frameSize,
      lumenBBox: lumenBox,
      lumenPolygon: lumenPolygon.length >= 3 ? lumenPolygon : undefined,
    });
  }, [
    frameSize,
    layerResult,
    lumenBox,
    lumenPolygon,
    onImagingAssist,
    points,
    wallPoints,
  ]);

  const emitReportEvidenceImages = useCallback(async () => {
    if (
      !onReportEvidenceImages
      || !frameDataUrl
      || !frameSize
      || pointsRef.current.length < 3
    ) return;
    const generation = ++reportEvidenceGenerationRef.current;
    const keyframes = keyCandidates
      .filter((candidate) => (
        Boolean(candidate.thumb_url)
        && Array.isArray(candidate.predicted_polygon)
        && candidate.predicted_polygon.length >= 3
      ))
      .map((candidate, index) => ({
        frameDataUrl: candidate.thumb_url as string,
        maskPolygon: candidate.predicted_polygon as number[][],
        frameWidth: candidate.image_width || frameSize.width,
        frameHeight: candidate.image_height || frameSize.height,
        frameTime: candidate.timestamp_sec,
        frameIndex: candidate.frame_index ?? index,
        normalizedMask: true,
        sourceFrameId: candidate.frame_id || `${patient?.id || 'case'}:${candidate.timestamp_sec.toFixed(3)}`,
        sourceVideoUrl: videoUrl || null,
        label: `关键帧 ${index + 1}, t=${candidate.timestamp_sec.toFixed(3)}s, 实际分割`,
      }));
    try {
      const images = await buildReportEvidenceImages({
        current: {
          frameDataUrl,
          maskPolygon: pointsRef.current,
          frameWidth: frameSize.width,
          frameHeight: frameSize.height,
          frameTime: mediaMode === 'video' ? videoTime : 0,
        },
        wallPolygon: wallPointsRef.current,
        lumenPolygon: lumenPolygonRef.current,
        lumenBBox: lumenBoxRef.current,
        keyframes,
      });
      if (generation === reportEvidenceGenerationRef.current) {
        onReportEvidenceImages(images, patient?.id);
      }
    } catch (error) {
      console.warn('report evidence render failed', error);
      if (generation === reportEvidenceGenerationRef.current) {
        setMessage(zh ? '证据帧渲染失败，请重试勾画或刷新当前帧' : 'Evidence-frame render failed; re-draw or refresh the current frame');
      }
    }
  }, [
    frameDataUrl,
    frameSize,
    keyCandidates,
    mediaMode,
    onReportEvidenceImages,
    patient?.id,
    videoTime,
    videoUrl,
    zh,
  ]);

  useEffect(() => {
    if (!frameDataUrl || points.length < 3) return;
    const timer = window.setTimeout(() => {
      void emitReportEvidenceImages();
    }, 350);
    return () => window.clearTimeout(timer);
  }, [
    emitReportEvidenceImages,
    frameDataUrl,
    keyCandidates,
    lumenBox,
    lumenPolygon,
    points,
    wallPoints,
  ]);

  const runUnifiedAgent = useCallback(async (opts?: {
    multiFrame?: boolean;
    assistProfile?: 'contour_anchored_fast' | 'full';
  }) => {
    if (!onUnifiedAgentRun || !simpleVideoMode || mediaMode !== 'video' || unifiedAgentBusy) return;
    const video = videoRef.current;
    if (!video?.videoWidth || !video.videoHeight || !videoUrl) {
      setMessage(zh ? '视频帧尚未准备好' : 'Video frame is not ready');
      return;
    }
    const originalTime = video.currentTime || videoTime;
    const duration = video.duration || 0;
    const span = duration > 0 ? Math.max(0.5, Math.min(2, duration / 8)) : 0;
    const multiFrame = Boolean(opts?.multiFrame);
    const assistProfile = opts?.assistProfile || (multiFrame ? 'full' : 'contour_anchored_fast');
    const totalSteps = multiFrame ? 3 : 4;
    const positions = multiFrame
      ? Array.from(new Set(
        [originalTime - span, originalTime, originalTime + span]
          .filter((time) => time >= 0 && (!duration || time < duration))
          .map((time) => Number(time.toFixed(3))),
      ))
      : [Number(originalTime.toFixed(3))];
    const wasPlaying = !video.paused;
    if (wasPlaying) video.pause();
    try {
      setTaskProgress({
        label: zh ? '辅助意见分析' : 'Assisted analysis',
        step: 1,
        totalSteps,
        detail: zh
          ? (multiFrame ? '采集关键帧…' : '采集当前帧…')
          : (multiFrame ? 'Capturing key frames…' : 'Capturing current frame…'),
      });
      const frames: UnifiedAgentFrame[] = [];
      for (const [index, position] of positions.entries()) {
        setTaskProgress({
          label: zh ? '辅助意见分析' : 'Assisted analysis',
          step: 1,
          totalSteps,
          detail: zh
            ? `采集帧 ${index + 1}/${positions.length}`
            : `Capturing frame ${index + 1}/${positions.length}`,
        });
        if (Math.abs(video.currentTime - position) > 0.01) {
          await seekVideoForAgent(video, position);
        }
        const frame = await videoOrImageToSamFrame(video, null, true, 1024);
        frames.push({
          frame_png_b64: frame.b64,
          frame_id: `${patient.id}:${position}`,
          frame_index: index,
          timestamp_sec: position,
          quality_score: Math.abs(position - originalTime) < 0.01 ? 1 : 0.9,
        });
      }
      if (Math.abs(video.currentTime - originalTime) > 0.01) {
        await seekVideoForAgent(video, originalTime);
      }
      setVideoTime(originalTime);
      if (wasPlaying) void video.play().catch(() => {});
      setTaskProgress({
        label: zh ? '辅助意见分析' : 'Assisted analysis',
        step: 2,
        totalSteps,
        detail: zh
          ? '分析病灶与胃壁证据（形态、层次、浸润）…'
          : 'Analyzing lesion and wall evidence (morphology, layers, penetration)…',
      });
      const geometry = computeLesionLumenGeometry(
        pointsRef.current,
        lumenPolygonRef.current,
        lumenBoxRef.current,
      );
      const lumenPoly = lumenPolygonRef.current.length >= 3 ? lumenPolygonRef.current : undefined;
      await onUnifiedAgentRun({
        frames,
        current_time: originalTime,
        image_width: video.videoWidth,
        image_height: video.videoHeight,
        mask_polygon: pointsRef.current,
        roi_bbox: bboxFromPolygon(pointsRef.current) || undefined,
        lumen_bbox: lumenBoxRef.current || undefined,
        lumen_polygon: lumenPoly,
        workflow_trace: workflowTraceRef.current,
        assist_profile: assistProfile,
        contour_context: {
          lesion_confirmed: pointsRef.current.length >= 3,
          lumen_mask_type: lumenPoly
            ? 'sam31_polygon'
            : (lumenBoxRef.current ? 'bbox_proxy' : 'missing'),
          geometry_relation: geometry.relation,
          geometry_quality: geometry.quality,
          layer_label: layerResult?.layer?.label || null,
          layer_pixel_based: Boolean(layerResult?.pixelBased),
          in_contact: layerResult?.inContact ?? null,
          prepared_actions: contourPrepActionsRef.current,
        },
      });
      if (!multiFrame) {
        setTaskProgress({
          label: zh ? '辅助意见分析' : 'Assisted analysis',
          step: 3,
          totalSteps,
          detail: zh
            ? '生成辅助意见与报告（DeepSeek-V4-Flash）…'
            : 'Generating assistive opinion and report (DeepSeek-V4-Flash)…',
        });
        await new Promise((resolve) => window.setTimeout(resolve, 350));
      }
      setTaskProgress({
        label: zh ? '辅助意见分析' : 'Assisted analysis',
        step: totalSteps,
        totalSteps,
        detail: zh ? '写入右侧证据面板…' : 'Updating evidence panel…',
      });
      setMessage(zh ? '轮廓锚定诊断已更新（右侧证据）' : 'Contour-anchored diagnosis updated in the evidence panel');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : (zh ? '统一 Agent 分析失败' : 'Unified Agent analysis failed'));
    } finally {
      setTaskProgress(null);
    }
  }, [layerResult, mediaMode, onUnifiedAgentRun, patient, simpleVideoMode, unifiedAgentBusy, videoTime, videoUrl, zh]);

  const lumenPrefer = useMemo(
    () => lumenPreferVector(points, lumenPolygon, lumenBox),
    [points, lumenPolygon, lumenBox],
  );
  const lumenLesionGeometry = useMemo(
    () => computeLesionLumenGeometry(points, lumenPolygon, lumenBox),
    [points, lumenPolygon, lumenBox],
  );
  const overlapFocus = useMemo(
    () => overlapFocusBox(points, lumenPolygon, lumenBox, lumenLesionGeometry),
    [lumenLesionGeometry, lumenBox, lumenPolygon, points],
  );

  const toggleZoomRoi = useCallback(() => {
    if (viewFocusMode === 'roi') {
      setViewFocusBox(null);
      setViewFocusMode(null);
      setMessage(zh ? '已退出 ROI 放大' : 'Exited ROI zoom');
      return;
    }
    setMagnifierOn(false);
    magnifierPosRef.current = null;
    const lesionBox = bboxFromPointsOrBox(pointsRef.current, null);
    const lumenFocus = bboxFromPointsOrBox(lumenPolygon, lumenBoxRef.current);
    const next = unionFocusBoxes(lesionBox, lumenFocus);
    if (!next) {
      setMessage(zh ? '请先有病灶或胃腔轮廓再放大' : 'Need lesion or lumen contour to zoom');
      return;
    }
    setViewFocusBox(next);
    setViewFocusMode('roi');
    setMessage(zh ? '已放大至病灶/胃腔 ROI' : 'Zoomed to lesion/lumen ROI');
  }, [lumenPolygon, viewFocusMode, zh]);

  const toggleOverlapZoom = useCallback(() => {
    if (viewFocusMode === 'overlap') {
      setViewFocusBox(null);
      setViewFocusMode(null);
      setMessage(zh ? '已退出重叠区域放大' : 'Exited overlap zoom');
      return;
    }
    if (!overlapFocus) {
      setMessage(
        lumenLesionGeometry.relation === 'near_lumen'
          ? (zh ? '当前为邻近胃腔，未形成可放大的交叠区域' : 'The contours are near the lumen but have no overlap focus region')
          : (zh ? '需要病灶和胃腔轮廓后才能放大交叠区域' : 'Create both lesion and lumen contours to zoom the overlap region'),
      );
      return;
    }
    setMagnifierOn(false);
    magnifierPosRef.current = null;
    setViewFocusBox(overlapFocus);
    setViewFocusMode('overlap');
    setMessage(zh ? '已放大病灶与胃腔交叠区域' : 'Zoomed to the lesion-lumen overlap region');
  }, [lumenLesionGeometry.relation, overlapFocus, viewFocusMode, zh]);

  const toggleMagnifier = useCallback(() => {
    setMagnifierOn((on) => {
      const next = !on;
      if (next) {
        setViewFocusBox(null);
        setViewFocusMode(null);
        setMessage(zh ? '放大镜已开启：在影像上滑动查看局部高倍细节' : 'Magnifier on: move over the image for local high-zoom detail');
      } else {
        magnifierPosRef.current = null;
        setMessage(zh ? '已关闭放大镜' : 'Magnifier off');
      }
      return next;
    });
  }, [zh]);

  const freezeCurrentFrame = useCallback(() => {
    const video = videoRef.current;
    if (video && !video.paused) video.pause();
    setFrameFrozen(true);
    frameFrozenRef.current = true;
    setTrackOnPlay(false);
    captureFrameDataUrl();
  }, [captureFrameDataUrl]);

  // Tissue-layer observation must use the actual displayed frame pixels.
  useEffect(() => {
    if (!wallAnalysisOpen) return;
    const video = videoRef.current;
    if (mediaMode === 'video' && video && !video.paused) {
      video.pause();
      setFrameFrozen(true);
      frameFrozenRef.current = true;
      setTrackOnPlay(false);
    }
    captureFrameDataUrl();
  }, [wallAnalysisOpen]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!wallAnalysisOpen || mediaMode !== 'video') return;
    const video = videoRef.current;
    if (!video) return;
    const onSeeked = () => {
      captureFrameDataUrl();
    };
    video.addEventListener('seeked', onSeeked);
    return () => video.removeEventListener('seeked', onSeeked);
  }, [wallAnalysisOpen, mediaMode, captureFrameDataUrl]);

  const buildExplainableFramePayload = useCallback(async (): Promise<ExplainableFramePayload | null> => {
    if (!patient) return null;
    const poly = pointsRef.current;
    if (!poly || poly.length < 3) return null;
    const frame = await videoOrImageToSamFrame(
      videoRef.current,
      imgRef.current,
      mediaMode === 'video',
      8192,
    );
    return {
      frame_png_b64: frame.b64,
      mask_polygon: poly.map((p) => [Number(p[0]), Number(p[1])]),
      image_width: frame.fullWidth,
      image_height: frame.fullHeight,
      frame_time: mediaMode === 'video' ? Number(videoTime.toFixed(3)) : undefined,
      patient_id: patient.patient_id,
      case_id: patient.id,
      lumen_bbox: lumenBoxRef.current || undefined,
      lumen_polygon: lumenPolygonRef.current.length >= 3
        ? lumenPolygonRef.current.map((p) => [Number(p[0]), Number(p[1])])
        : undefined,
    };
  }, [mediaMode, patient, videoTime]);

  const openExplainableAnalysis = useCallback(() => {
    if (pointsRef.current.length < 3) {
      setMessage(zh ? '请先在当前帧框选或生成病灶轮廓，再运行边界分析' : 'Draw a lesion contour on the current frame first');
      return;
    }
    freezeCurrentFrame();
    setShowExplainable(true);
  }, [freezeCurrentFrame, zh]);

  const syncFrameFromVideo = useCallback((opts?: { force?: boolean }) => {
    if (!opts?.force && (frameFrozenRef.current || dragIndexRef.current !== null)) return;
    const video = videoRef.current;
    if (!video || !video.videoWidth) return;
    setVideoTime(video.currentTime || 0);
    setImgLoaded(true);
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (canvas && container) {
      const rect = container.getBoundingClientRect();
      const w = Math.max(320, Math.floor(rect.width));
      const h = Math.max(240, Math.floor(rect.height));
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w;
        canvas.height = h;
      }
    }
  }, []);

  const paintProgressUi = useCallback((timeSec: number, options?: { forceSlider?: boolean }) => {
    const text = timeSec.toFixed(2);
    for (const label of videoTimeLabelRefs.current) {
      if (label) label.textContent = text;
    }
    if (scrubbingRef.current && !options?.forceSlider) return;
    const value = String(timeSec);
    for (const slider of videoProgressRefs.current) {
      if (slider && slider.value !== value) slider.value = value;
    }
  }, []);

  const scheduleScrubPreview = useCallback(() => {
    if (scrubPreviewRafRef.current != null) return;
    scrubPreviewRafRef.current = requestAnimationFrame(() => {
      scrubPreviewRafRef.current = null;
      const now = performance.now();
      // Keep scrub preview around 20fps so React/canvas do not thrash on every pointer sample.
      if (now - lastScrubRedrawAtRef.current < 50) return;
      lastScrubRedrawAtRef.current = now;
      redrawRef.current();
    });
  }, []);

  const beginVideoScrub = useCallback((event?: React.PointerEvent<HTMLInputElement>) => {
    const video = videoRef.current;
    if (!video) return;
    scrubbingRef.current = true;
    video.pause();
    setFrameFrozen(false);
    frameFrozenRef.current = false;
    if (event) {
      try {
        event.currentTarget.setPointerCapture(event.pointerId);
      } catch {
        // Some browsers reject capture on range inputs; scrubbing still works.
      }
    }
  }, []);

  const scrubVideoTo = useCallback((nextTime: number) => {
    const video = videoRef.current;
    if (!video) return;
    const clamped = Math.max(0, Math.min(video.duration || nextTime, nextTime));
    if (Math.abs(video.currentTime - clamped) > 0.001) {
      video.currentTime = clamped;
    }
    paintProgressUi(clamped, { forceSlider: true });
    scheduleScrubPreview();
  }, [paintProgressUi, scheduleScrubPreview]);

  const endVideoScrub = useCallback(() => {
    if (!scrubbingRef.current) return;
    const video = videoRef.current;
    scrubbingRef.current = false;
    if (scrubPreviewRafRef.current != null) {
      cancelAnimationFrame(scrubPreviewRafRef.current);
      scrubPreviewRafRef.current = null;
    }
    const t = video?.currentTime || 0;
    setVideoTime(t);
    paintProgressUi(t, { forceSlider: true });
    syncFrameFromVideo({ force: true });
    redrawRef.current();
  }, [paintProgressUi, syncFrameFromVideo]);

  const onVideoProgressChange = useCallback((nextTime: number) => {
    if (!scrubbingRef.current) {
      // Keyboard / accessibility seeks do not fire pointerdown.
      const video = videoRef.current;
      if (!video) return;
      video.pause();
      video.currentTime = Math.max(0, Math.min(video.duration || nextTime, nextTime));
      const t = video.currentTime || 0;
      setVideoTime(t);
      paintProgressUi(t, { forceSlider: true });
      syncFrameFromVideo({ force: true });
      redrawRef.current();
      return;
    }
    scrubVideoTo(nextTime);
  }, [paintProgressUi, scrubVideoTo, syncFrameFromVideo]);

  useEffect(() => {
    if (scrubbingRef.current) return;
    paintProgressUi(videoTime);
  }, [paintProgressUi, videoTime]);

  useEffect(() => {
    const max = String(Math.max(videoDuration, 0.01));
    for (const slider of videoProgressRefs.current) {
      if (slider) slider.max = max;
    }
  }, [videoDuration]);

  useEffect(() => {
    if (!taskProgress) {
      taskProgressStartedAtRef.current = null;
      setTaskElapsedSec(0);
      return;
    }
    if (taskProgressStartedAtRef.current == null) {
      taskProgressStartedAtRef.current = performance.now();
    }
    const tick = window.setInterval(() => {
      const started = taskProgressStartedAtRef.current;
      if (started == null) return;
      setTaskElapsedSec(Math.floor((performance.now() - started) / 1000));
    }, 250);
    return () => window.clearInterval(tick);
  }, [taskProgress]);

  const runSamAtPoint = useCallback(async (
    imgPt: number[] | null,
    opts?: {
      silent?: boolean;
      source?: MaskBoundaryOverride['source'];
      box?: { x1: number; y1: number; x2: number; y2: number };
      clicks?: Array<{ x: number; y: number; label: 'positive' | 'negative' }>;
      keepEditing?: boolean;
      stayInSam?: boolean;
      llmReport?: boolean;
    },
  ): Promise<number[][] | null> => {
    if (!patient) return null;
    const traceId = `sam_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    const traceStartedAt = performance.now();
    // Supersede in-flight interactive requests instead of dropping clicks.
    if (!opts?.silent) {
      samAbortRef.current?.abort();
      samGenRef.current += 1;
      samBusyRef.current = true;
      setSamBusy(true);
      setMessage(zh ? '系统分析中…' : 'Running SAM…');
    } else {
      samAbortRef.current?.abort();
    }
    const ac = new AbortController();
    samAbortRef.current = ac;
    const myGen = samGenRef.current;
    try {
      const frame = await videoOrImageToSamFrame(
        videoRef.current,
        imgRef.current,
        mediaMode === 'video',
        1024,
      );
      const scale = frame.scale || 1;
      const currentFrameTime = mediaMode === 'video'
        ? Number(videoRef.current?.currentTime ?? videoTime)
        : 0;
      const payload: Record<string, unknown> = {
        case_id: patient.patient_id,
        frame_png_b64: frame.b64,
        image_width: frame.width,
        image_height: frame.height,
        frame_time: currentFrameTime,
        model: segmentationModel,
        video_url: mediaMode === 'video' ? videoUrl : undefined,
        tracking_session_id: trackingSessionId || undefined,
        tracking_enabled: mediaMode === 'video' && Boolean(trackingSessionId),
        tracking_reset: mediaMode === 'video'
          && opts?.source === 'sam'
          && !opts?.silent,
        llm_report: Boolean(opts?.llmReport),
      };
      const promptClicks = opts?.clicks?.length
        ? opts.clicks
        : imgPt
          ? [{ x: imgPt[0], y: imgPt[1], label: 'positive' as const }]
          : [];
      if (opts?.box) {
        payload.box = {
          x1: opts.box.x1 * scale,
          y1: opts.box.y1 * scale,
          x2: opts.box.x2 * scale,
          y2: opts.box.y2 * scale,
        };
      }
      if (promptClicks.length) {
        payload.clicks = promptClicks.map((c) => ({
          x: c.x * scale,
          y: c.y * scale,
          label: c.label,
        }));
        const firstPos = promptClicks.find((c) => c.label !== 'negative') || promptClicks[0];
        payload.click = {
          x: firstPos.x * scale,
          y: firstPos.y * scale,
          label: firstPos.label,
        };
      } else if (!opts?.box) {
        throw new Error('missing click/box');
      }
      const res = await fetch('/api/agent/sam-interactive', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: ac.signal,
      });
      const data = await readJsonPayload<{
        ok?: boolean;
        error?: string;
        result?: {
          mask_polygon?: number[][];
          prompt_meta?: Record<string, unknown>;
          message?: string;
          sam_score?: number;
          backend_id?: string;
          report?: SamReport;
        };
      }>(res, 'Interactive segmentation endpoint');
      if (!data.ok || !data.result?.mask_polygon) {
        throw new Error(data.error || data.result?.message || 'SAM returned no polygon');
      }
      const rawPoly = (data.result.mask_polygon as number[][]).map((p) => [Number(p[0]), Number(p[1])]);
      if (rawPoly.length < 3) {
        throw new Error(
          zh
            ? '系统分析未得到有效区域，请换一个关注点重试'
            : 'No valid region returned — try another point',
        );
      }
      const promptMeta = (data.result.prompt_meta || {}) as Record<string, unknown>;
      const maskArea = Number(promptMeta.mask_area_px);
      const maskAreaRatio = Number.isFinite(maskArea) && frame.width > 0 && frame.height > 0
        ? maskArea / (frame.width * frame.height)
        : null;
      if (!opts?.silent && maskAreaRatio != null && maskAreaRatio > 0.65) {
        maskAuditRef.current('model_trace', {
          trace_id: traceId,
          operation: 'interactive_segmentation',
          model: segmentationModel,
          source: opts?.source || 'manual_prompt',
          outcome: 'rejected_oversized_mask',
          frame_time_sec: currentFrameTime,
          input: {
            has_box: Boolean(opts?.box),
            click_count: promptClicks.length,
            positive_clicks: promptClicks.filter((click) => click.label !== 'negative').length,
            negative_clicks: promptClicks.filter((click) => click.label === 'negative').length,
            silent: Boolean(opts?.silent),
          },
          output: { mask_area_ratio: maskAreaRatio },
          duration_ms: Math.round(performance.now() - traceStartedAt),
        });
        setSamAvailable(true);
        setMessage(
          zh
            ? `未采用过大的分割区域（${Math.round(maskAreaRatio * 100)}%），请改用框选或补充负点`
            : `Rejected an oversized region (${Math.round(maskAreaRatio * 100)}%); draw a box or add negative points`,
        );
        return null;
      }
      const maxCoord = Math.max(...rawPoly.flatMap((p) => p));
      const polyFull =
        maxCoord <= 1.5
          ? rawPoly.map((p) => [p[0] * frame.fullWidth, p[1] * frame.fullHeight])
          : rawPoly.map((p) => [p[0] / scale, p[1] / scale]);
      const poly = prepareEditableContour(polyFull, LESION_CONTOUR_MAX_POINTS);
      maskAuditRef.current('model_trace', {
        trace_id: traceId,
        operation: 'interactive_segmentation',
        model: segmentationModel,
        source: opts?.source || 'manual_prompt',
        outcome: 'success',
        frame_time_sec: currentFrameTime,
        input: {
          has_box: Boolean(opts?.box),
          click_count: promptClicks.length,
          positive_clicks: promptClicks.filter((click) => click.label !== 'negative').length,
          negative_clicks: promptClicks.filter((click) => click.label === 'negative').length,
          silent: Boolean(opts?.silent),
          tracking_session_id: trackingSessionId || undefined,
        },
        output: {
          polygon_points: poly.length,
          mask_area_ratio: maskAreaRatio,
          score: Number.isFinite(Number(data.result.sam_score))
            ? Number(data.result.sam_score)
            : undefined,
          backend_id: data.result.backend_id,
        },
        duration_ms: Math.round(performance.now() - traceStartedAt),
      });
      const nextReport = (
        data.result.report
        || buildModelAssistReport(
          patient,
          poly,
          frame.fullWidth,
          frame.fullHeight,
          segmentationModel,
          maskAreaRatio ?? undefined,
          zh,
        )
      ) as SamReport;
      setSamReport(nextReport);
      onSystemReport?.(nextReport);
      const targetLayer = opts?.source === 'video_track' || opts?.source === 'video_propagate'
        ? 'lesion'
        : activeLayer;
      if (targetLayer === 'wall') {
        setWallPoints(poly);
        wallPointsRef.current = poly;
        snapshotOriginal(pointsRef.current, poly);
      } else {
        contourInteractionRef.current = true;
        generatedLesionRef.current = clonePoly(poly);
        setPoints(poly);
        pointsRef.current = poly;
        snapshotOriginal(poly, wallPointsRef.current);
      }

      if (opts?.keepEditing !== false && opts?.source !== 'video_track') {
        freezeCurrentFrame();
        if (opts?.stayInSam || opts?.source === 'sam') {
          setMode('sam');
        } else {
          setMode('soft');
        }
      }

      if (!opts?.silent) {
        const score = Number(data.result.sam_score);
        const scoreText = Number.isFinite(score) ? `, score ${score.toFixed(2)}` : '';
        const positiveCount = promptClicks.filter((click) => click.label !== 'negative').length;
        const negativeCount = promptClicks.filter((click) => click.label === 'negative').length;
        setMessage(
          zh
            ? `当前帧 ROI 已更新（${poly.length} 点${scoreText}），正点 ${positiveCount}，负点 ${negativeCount}`
            : `Current-frame ROI updated (${poly.length} points${scoreText}), positive ${positiveCount}, negative ${negativeCount}`,
        );
      } else {
        setMessage(
          zh
            ? `视频跟随 t=${(videoRef.current?.currentTime || 0).toFixed(2)}s, ${poly.length}pt`
            : `Video track t=${(videoRef.current?.currentTime || 0).toFixed(2)}s, ${poly.length}pt`,
        );
      }
      setSamAvailable(true);
      return poly;
    } catch (err) {
      const aborted = (err as Error)?.name === 'AbortError';
      maskAuditRef.current('model_trace', {
        trace_id: traceId,
        operation: 'interactive_segmentation',
        model: segmentationModel,
        source: opts?.source || 'manual_prompt',
        outcome: aborted ? 'aborted' : 'error',
        frame_time_sec: Number((videoRef.current?.currentTime ?? videoTime).toFixed(3)),
        input: {
          has_box: Boolean(opts?.box),
          click_count: opts?.clicks?.length || (imgPt ? 1 : 0),
          silent: Boolean(opts?.silent),
        },
        error: aborted
          ? undefined
          : err instanceof Error ? err.message.slice(0, 240) : 'System analysis failed',
        duration_ms: Math.round(performance.now() - traceStartedAt),
      });
      if (aborted) return null;
      if (!opts?.silent) {
        setSamAvailable(false);
        setMessage(err instanceof Error ? sanitizeSystemCopy(err.message) : 'System analysis failed');
      }
      return null;
    } finally {
      if (!opts?.silent && samGenRef.current === myGen) {
        samBusyRef.current = false;
        setSamBusy(false);
      }
    }
  }, [
    patient,
    zh,
    activeLayer,
    mediaMode,
    videoTime,
    videoUrl,
    trackingSessionId,
    segmentationModel,
    freezeCurrentFrame,
    snapshotOriginal,
    onSystemReport,
  ]);

  const predictKeyframes = useCallback(async (candidates: KeyframeCandidate[]) => {
    const video = videoRef.current;
    const seed = clonePoly(pointsRef.current);
    const box = bboxFromPolygon(seed);
    const centroid = polygonCentroid(seed);
    if (!simpleVideoMode || mediaMode !== 'video' || !video?.videoWidth || !video.videoHeight || !box || !centroid) {
      setKeyCandidates((current) => current.map((candidate) => ({ ...candidate, prediction_status: 'needs_roi' })));
      setMessage(zh ? '请先框选病灶，再生成关键帧病灶预测' : 'Draw an ROI box first, then generate keyframe lesion predictions');
      return;
    }

    const originalTime = video.currentTime || videoTime;
    const wasFrozen = frameFrozenRef.current;
    let predictedCount = 0;
    video.pause();
    setFrameFrozen(true);
    frameFrozenRef.current = true;
    try {
      for (const [index, candidate] of candidates.entries()) {
        const timestamp = Number(candidate.timestamp_sec || 0);
        setMessage(
          zh
            ? `关键帧病灶预测 ${index + 1}/${candidates.length}…`
            : `Predicting lesion on keyframe ${index + 1}/${candidates.length}…`,
        );
        try {
          await seekVideoForAgent(video, timestamp);
          setVideoTime(timestamp);
          const poly = simpleVideoMode && segmentationModel === 'sabm_sam2_guided'
            ? await runSamAtPoint(centroid, {
                silent: true,
                source: 'video_track',
                box,
                keepEditing: false,
              })
            : simpleVideoMode
              ? await runLesionModelRef.current(centroid, box, samClicksRef.current)
              : await runSamAtPoint(centroid, {
                  silent: true,
                  source: 'video_track',
                  box,
                  keepEditing: false,
                });
          if (!poly || poly.length < 3) {
            setKeyCandidates((current) => current.map((item) => (
              item.timestamp_sec === candidate.timestamp_sec
                ? { ...item, prediction_status: 'failed', prediction_error: 'no polygon' }
                : item
            )));
            continue;
          }
          predictedCount += 1;
          const normalized = poly.map((point) => [
            Number((point[0] / video.videoWidth).toFixed(6)),
            Number((point[1] / video.videoHeight).toFixed(6)),
          ]);
          setKeyCandidates((current) => current.map((item) => (
            item.timestamp_sec === candidate.timestamp_sec
              ? { ...item, predicted_polygon: normalized, prediction_status: 'predicted' }
              : item
          )));
        } catch (error) {
          setKeyCandidates((current) => current.map((item) => (
            item.timestamp_sec === candidate.timestamp_sec
              ? {
                  ...item,
                  prediction_status: 'failed',
                  prediction_error: error instanceof Error ? error.message : 'prediction failed',
                }
              : item
          )));
        }
      }
    } finally {
      await seekVideoForAgent(video, originalTime);
      setVideoTime(originalTime);
      pointsRef.current = seed;
      setPoints(seed);
      setFrameFrozen(wasFrozen);
      frameFrozenRef.current = wasFrozen;
      redrawRef.current();
    }
    setMessage(
      zh
        ? `已完成 ${predictedCount}/${candidates.length} 个关键帧的病灶预测`
        : `Lesion predictions completed for ${predictedCount}/${candidates.length} keyframes`,
    );
  }, [mediaMode, runSamAtPoint, segmentationModel, simpleVideoMode, videoTime, zh]);

  useEffect(() => {
    predictKeyframesRef.current = predictKeyframes;
  }, [predictKeyframes]);

  const recordVideoFrameOverride = useCallback((poly: number[][], status: 'seed' | 'accepted' = 'accepted') => {
    if (mediaMode !== 'video') return;
    const video = videoRef.current;
    if (!video?.videoWidth || !video.videoHeight) return;
    const timestamp = Number((video.currentTime || 0).toFixed(3));
    const lumenPoly = lumenPolygonRef.current.length >= 3
      ? lumenPolygonRef.current
      : nearestOverrideFrame(videoFrameOverridesRef.current, timestamp, 0.35)?.lumen_polygon;
    const lumenBoxNow = lumenBoxRef.current || (lumenPoly ? bboxFromPolygon(lumenPoly) : undefined);
    const frame: VideoMaskFrameOverride = {
      timestamp_sec: timestamp,
      imageWidth: video.videoWidth,
      imageHeight: video.videoHeight,
      mask_polygon: poly.map((point) => [Math.round(point[0] * 10) / 10, Math.round(point[1] * 10) / 10]),
      roi_bbox: bboxFromPolygon(poly),
      lumen_polygon: lumenPoly?.length
        ? lumenPoly.map((point) => [Math.round(point[0] * 10) / 10, Math.round(point[1] * 10) / 10])
        : undefined,
      lumen_bbox: lumenBoxNow || undefined,
      source: 'video_track',
      propagation_status: status,
    };
    const next = [
      ...videoFrameOverridesRef.current.filter((item) => Math.abs(item.timestamp_sec - timestamp) > 0.12),
      frame,
    ].sort((a, b) => a.timestamp_sec - b.timestamp_sec);
    videoFrameOverridesRef.current = next;
    setVideoFrameOverrides(next);
  }, [mediaMode]);

  const resumeSimpleTracking = useCallback((poly: number[][] | null) => {
    if (!simpleVideoMode || !poly || poly.length < 3) return;
    recordVideoFrameOverride(poly, videoFrameOverridesRef.current.length ? 'accepted' : 'seed');
    setTrackingPrepared(false);
    setTrackOnPlay(false);
    setFrameFrozen(false);
    frameFrozenRef.current = false;
    setMessage(zh ? '当前帧轮廓已生成；请确认胃腔后点击“跟踪扩散”，将同时跟踪病灶与胃腔' : 'Contour ready; confirm lumen, then Track video for lesion + lumen');
  }, [recordVideoFrameOverride, simpleVideoMode, zh]);

  const getCurrentTrackedPolygon = useCallback((): number[][] => {
    if (mediaMode !== 'video' || !videoFrameOverridesRef.current.length) {
      return pointsRef.current;
    }
    const currentTime = videoRef.current?.currentTime || 0;
    const nearest = videoFrameOverridesRef.current.reduce((best, item) => (
      Math.abs(item.timestamp_sec - currentTime) < Math.abs(best.timestamp_sec - currentTime) ? item : best
    ), videoFrameOverridesRef.current[0]);
    return nearest?.mask_polygon?.length ? nearest.mask_polygon : pointsRef.current;
  }, [mediaMode]);

  const precomputeVideoTracking = useCallback(async () => {
    if (!simpleVideoMode || mediaMode !== 'video' || precomputeBusy) return;
    const video = videoRef.current;
    const seed = pointsRef.current;
    if (!video || !video.videoWidth || seed.length < 3) {
      setMessage(zh ? '请先在当前帧生成有效轮廓' : 'Generate a valid contour first');
      return;
    }
    const duration = video.duration || 0;
    const start = video.currentTime || 0;
    // Full-video tracking must cover frames before and after the seed, not only later frames.
    if (!duration || duration <= 0.1) {
      setMessage(zh ? '当前视频时长不可用' : 'Video duration unavailable');
      return;
    }
    const box = bboxFromPolygon(seed);
    const centroid = polygonCentroid(seed);
    if (!box || !centroid) {
      setMessage(zh ? '当前帧轮廓无法生成传播提示' : 'Could not create a propagation prompt');
      return;
    }
    const lumenSeedPoly = lumenPolygonRef.current.length >= 3 ? clonePoly(lumenPolygonRef.current) : [];
    const lumenSeedBox = lumenBoxRef.current || (lumenSeedPoly.length >= 3 ? bboxFromPolygon(lumenSeedPoly) : null);
    const lumenCentroid = lumenSeedPoly.length >= 3
      ? polygonCentroid(lumenSeedPoly)
      : (lumenSeedBox
        ? [(lumenSeedBox.x1 + lumenSeedBox.x2) / 2, (lumenSeedBox.y1 + lumenSeedBox.y2) / 2]
        : null);
    if (!lumenSeedBox || !lumenCentroid) {
      setMessage(zh ? '请先检测/分割胃腔，再同时跟踪病灶与胃腔' : 'Detect/segment lumen first, then track lesion and lumen together');
      return;
    }
    const traceId = `video_propagate_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    const traceStartedAt = performance.now();
    video.pause();
    setTrackOnPlay(false);
    setFrameFrozen(true);
    frameFrozenRef.current = true;
    setPrecomputeBusy(true);
    setTrackingPrepared(false);
    try {
      setPrecomputeProgress(zh ? '病灶跟踪中…' : 'Tracking lesion…');
      setTaskProgress({
        label: zh ? '整段视频跟踪' : 'Full-video tracking',
        step: 1,
        totalSteps: 3,
        detail: zh ? '病灶跟踪中…' : 'Tracking lesion…',
      });
      const lesionResult = await requestVideoPropagate({
        case_id: patient?.patient_id || patient?.id || '',
        model: segmentationModel,
        video_url: videoUrl,
        frame_time: start,
        image_width: video.videoWidth,
        image_height: video.videoHeight,
        clicks: samClicksRef.current.length
          ? samClicksRef.current
          : [{ x: centroid[0], y: centroid[1], label: 'positive' }],
        box,
        direction: 'both',
        max_frames: Math.max(120, Math.ceil(duration * 120)),
        text_prompt: 'gastric lesion',
      });
      const lesionFrames = mapPropagateFramesToOverrides(
        lesionResult.frames || [],
        video.videoWidth,
        video.videoHeight,
        'video_track',
      );
      if (!lesionFrames.length) throw new Error('full video precompute returned no lesion masks');

      setPrecomputeProgress(zh ? '胃腔跟踪中…' : 'Tracking lumen…');
      setTaskProgress({
        label: zh ? '整段视频跟踪' : 'Full-video tracking',
        step: 2,
        totalSteps: 3,
        detail: zh ? '胃腔跟踪中…' : 'Tracking lumen…',
      });
      let lumenFrames: VideoMaskFrameOverride[] = [];
      let lumenTracked = false;
      try {
        const lumenResult = await requestVideoPropagate({
          case_id: patient?.patient_id || patient?.id || '',
          model: segmentationModel,
          video_url: videoUrl,
          frame_time: start,
          image_width: video.videoWidth,
          image_height: video.videoHeight,
          clicks: [{ x: lumenCentroid[0], y: lumenCentroid[1], label: 'positive' }],
          box: lumenSeedBox,
          direction: 'both',
          max_frames: Math.max(120, Math.ceil(duration * 120)),
          text_prompt: 'gastric lumen cavity',
        });
        lumenFrames = mapPropagateFramesToOverrides(
          lumenResult.frames || [],
          video.videoWidth,
          video.videoHeight,
          'video_track',
        );
        lumenTracked = lumenFrames.length > 0;
      } catch (lumenError) {
        console.warn('lumen video track failed', lumenError);
      }

      const cachedFrames = mergeLumenIntoLesionFrames(lesionFrames, lumenFrames, {
        polygon: lumenSeedPoly,
        box: lumenSeedBox,
      }, start);
      setPrecomputeProgress(`${cachedFrames.length}/${lesionResult.num_frames || cachedFrames.length}`);
      setTaskProgress({
        label: zh ? '整段视频跟踪' : 'Full-video tracking',
        step: 3,
        totalSteps: 3,
        detail: zh
          ? `合并并保存 ${cachedFrames.length}/${lesionResult.num_frames || cachedFrames.length} 帧`
          : `Merging and saving ${cachedFrames.length}/${lesionResult.num_frames || cachedFrames.length} frames`,
      });
      videoFrameOverridesRef.current = cachedFrames;
      setVideoFrameOverrides(cachedFrames);
      const nearest = nearestOverrideFrame(cachedFrames, start, 1.0) || cachedFrames[0];
      if (nearest?.mask_polygon?.length) {
        pointsRef.current = nearest.mask_polygon;
        setPoints(nearest.mask_polygon);
      }
      if (nearest?.lumen_polygon?.length) {
        lumenPolygonRef.current = nearest.lumen_polygon;
        setLumenPolygon(nearest.lumen_polygon);
        const nextBox = nearest.lumen_bbox || bboxFromPolygon(nearest.lumen_polygon);
        if (nextBox) {
          lumenBoxRef.current = nextBox;
          setLumenBox(nextBox);
        }
      }
      setVideoTime(start);
      setTrackingPrepared(true);
      setTrackOnPlay(true);
      setFrameFrozen(false);
      frameFrozenRef.current = false;
      await applyAreaKeyframesRef.current(cachedFrames);
      const persisted = await persistOverrideRef.current('video_tracking_complete');
      maskAuditRef.current('model_trace', {
        trace_id: traceId,
        operation: 'video_propagation',
        model: segmentationModel,
        source: 'video_propagate',
        outcome: 'success',
        frame_time_sec: start,
        input: {
          direction: 'both',
          requested_max_frames: Math.ceil(duration * 120),
          video_duration_sec: duration,
        },
        output: {
          lesion_frame_count: lesionFrames.length,
          lumen_frame_count: lumenFrames.length,
          merged_frame_count: cachedFrames.length,
          lumen_tracked: lumenTracked,
          persisted,
          frames_with_lesion_box: cachedFrames.filter((frame) => Boolean(frame.roi_bbox)).length,
          frames_with_lumen_mask: cachedFrames.filter((frame) => (frame.lumen_polygon?.length || 0) >= 3).length,
          frames_with_lumen_box: cachedFrames.filter((frame) => Boolean(frame.lumen_bbox)).length,
        },
        duration_ms: Math.round(performance.now() - traceStartedAt),
      });
      setMessage(
        zh
          ? `跟踪扩散完成：病灶 ${cachedFrames.length} 帧${lumenTracked ? `，胃腔 ${lumenFrames.length} 帧` : '（胃腔跟踪失败，已用当前胃腔种子）'}；${persisted ? '完整结果已保存' : '保存失败，请点击保存轮廓'}`
          : `Tracking done: lesion ${cachedFrames.length} frames${lumenTracked ? `, lumen ${lumenFrames.length} frames` : ' (lumen track failed, seed carried)'}; ${persisted ? 'complete result saved' : 'save failed, click Save complete masks'}`,
      );
    } catch (error) {
      maskAuditRef.current('model_trace', {
        trace_id: traceId,
        operation: 'video_propagation',
        model: segmentationModel,
        source: 'video_propagate',
        outcome: 'error',
        frame_time_sec: start,
        error: error instanceof Error ? error.message.slice(0, 240) : 'Precompute failed',
        duration_ms: Math.round(performance.now() - traceStartedAt),
      });
      setMessage(error instanceof Error ? error.message : (zh ? '预计算失败' : 'Precompute failed'));
    } finally {
      setPrecomputeBusy(false);
      setPrecomputeProgress(null);
      setTaskProgress(null);
    }
  }, [mediaMode, patient?.id, patient?.patient_id, precomputeBusy, segmentationModel, simpleVideoMode, videoUrl, zh]);

  const maybeTrackWhilePlaying = useCallback(async () => {
    if (!trackOnPlay || mediaMode !== 'video' || !isPlaying) return;
    if (simpleVideoMode && (simpleEditMode || trackingPrepared)) return;
    if (frameFrozenRef.current || dragIndexRef.current !== null) return;
    if (trackBusyRef.current || (!simpleVideoMode && samAvailable === false)) return;
    const now = Date.now();
    if (now - lastTrackAtRef.current < 500) return;
    const poly = pointsRef.current;
    if (poly.length < 3) return;
    const bbox = bboxFromPolygon(poly);
    const centroid = polygonCentroid(poly);
    if (!bbox || !centroid) return;
    trackBusyRef.current = true;
    lastTrackAtRef.current = now;
    try {
      const nextPoly = simpleVideoMode && segmentationModel !== 'sabm_sam2_guided'
        ? await runLesionModelRef.current(centroid, bbox, samClicksRef.current)
        : await runSamAtPoint(centroid, {
            silent: true,
            source: 'video_track',
            box: bbox,
            keepEditing: false,
          });
      if (nextPoly && nextPoly.length >= 3) recordVideoFrameOverride(nextPoly);
    } finally {
      trackBusyRef.current = false;
    }
  }, [trackOnPlay, mediaMode, isPlaying, samAvailable, runSamAtPoint, recordVideoFrameOverride, segmentationModel, simpleEditMode, simpleVideoMode, trackingPrepared]);


  const redraw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || !imgLoaded) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const video = videoRef.current;
    const img = imgRef.current;
    const useVideo =
      mediaMode === 'video'
      && !!video
      && video.videoWidth > 0
      && video.readyState >= 2;

    const iw = useVideo ? video!.videoWidth : (img?.naturalWidth || 0);
    const ih = useVideo ? video!.videoHeight : (img?.naturalHeight || 0);
    if (!iw || !ih) return;

    const cw = canvas.width;
    const ch = canvas.height;
    const { scale, dx, dy } = computeDisplayTransform(iw, ih, cw, ch, viewFocusBox);

    const nativeVideoPlayback = simpleVideoMode && useVideo && !viewFocusBox;
    ctx.clearRect(0, 0, cw, ch);
    if (!nativeVideoPlayback) {
      ctx.fillStyle = '#0a0a0a';
      ctx.fillRect(0, 0, cw, ch);
      if (useVideo) ctx.drawImage(video!, dx, dy, iw * scale, ih * scale);
      else if (img) ctx.drawImage(img, dx, dy, iw * scale, ih * scale);
    }

    const map = (x: number, y: number) => ({ x: dx + x * scale, y: dy + y * scale });
    const trackedFrame = useVideo && videoFrameOverrides.length
      ? nearestOverrideFrame(videoFrameOverrides, video!.currentTime, Number.POSITIVE_INFINITY)
      : null;
    const displayPoints = trackedFrame?.mask_polygon?.length
      ? trackedFrame.mask_polygon
      : points.length >= 3
        ? points
        : generatedLesionRef.current;
    const displayLumenPoly = (!lumenEditMode && trackedFrame?.lumen_polygon && trackedFrame.lumen_polygon.length >= 3)
      ? trackedFrame.lumen_polygon
      : lumenPolygon;
    // Once a lumen mask exists (current frame or tracked), drop the box prompt so the
    // canvas shows the true contour only — no lingering rectangle around the mask.
    const displayLumenBox = displayLumenPoly.length >= 3
      ? null
      : (!lumenEditMode && trackedFrame?.lumen_bbox)
        ? trackedFrame.lumen_bbox
        : lumenBox;
    const historyPreviewFrame = historyPreview && useVideo
      ? nearestOverrideFrame(
        historyPreview.override.video_frames || [],
        video!.currentTime,
        Number.POSITIVE_INFINITY,
      )
      : null;
    const historyPreviewPoints = historyPreviewFrame?.mask_polygon?.length
      ? historyPreviewFrame.mask_polygon
      : historyPreview?.override.mask_polygon || [];
    const historyPreviewRoiBox = historyPreviewFrame?.roi_bbox || historyPreview?.override.roi_bbox;
    const historyPreviewLumenPoly = historyPreviewFrame?.lumen_polygon?.length
      ? historyPreviewFrame.lumen_polygon
      : historyPreview?.lumen_override?.lumen_polygon || [];
    const historyPreviewLumenBox = historyPreviewFrame?.lumen_bbox || historyPreview?.lumen_override?.lumen_bbox;

    const drawPoly = (poly: number[][], fill: string, stroke: string, dashed = false) => {
      if (poly.length < 2) return;
      strokeClosedPolyline(ctx, poly, map);
      ctx.fillStyle = fill;
      ctx.fill();
      ctx.strokeStyle = stroke;
      ctx.lineWidth = CONTOUR_LINE_WIDTH;
      ctx.setLineDash(dashed ? [7, 5] : []);
      ctx.stroke();
      ctx.setLineDash([]);
    };

    // Smaller, screen-stable handles so small lesions are not covered (meeting 2026-08-10).
    const hr = Math.max(2.0, Math.min(4.8, 3.6 / Math.sqrt(Math.max(scale, 0.15))));

    const drawHandles = (
      poly: number[][],
      count: number,
      fill: string,
      layer: DragLayer,
    ) => {
      if (poly.length < 3) return;
      controlIndices(poly.length, count).forEach((i) => {
        const p = poly[i];
        if (!p) return;
        const { x, y } = map(p[0], p[1]);
        const active = dragLayer === layer && dragIndex === i;
        ctx.beginPath();
        ctx.arc(x, y, active ? hr + 1.2 : hr, 0, Math.PI * 2);
        ctx.fillStyle = active ? 'rgba(251, 191, 36, 0.55)' : fill;
        ctx.fill();
        ctx.strokeStyle = HANDLE_STROKE;
        ctx.lineWidth = 1;
        ctx.stroke();
      });
    };

    if (simpleVideoMode) {
      if (wallPoints.length >= 3) {
        drawPoly(wallPoints, COLOR_WALL_FILL, COLOR_WALL_STROKE);
      }
      drawPoly(displayPoints, COLOR_LESION_FILL, COLOR_LESION_STROKE);
      if (simpleEditMode) {
        if (simpleEditLayer === 'wall' && wallPoints.length >= 3) {
          drawHandles(wallPoints, Math.min(12, WALL_CTRL_COUNT), COLOR_WALL_HANDLE, 'wall');
        } else if (displayPoints.length >= 3) {
          drawHandles(displayPoints, Math.min(12, LESION_CTRL_COUNT), COLOR_LESION_HANDLE, 'lesion');
        }
      }
      if (samBoxPreview) {
        const a = map(samBoxPreview.x1, samBoxPreview.y1);
        const b = map(samBoxPreview.x2, samBoxPreview.y2);
        ctx.fillStyle = 'rgba(34, 211, 238, 0.08)';
        ctx.fillRect(Math.min(a.x, b.x), Math.min(a.y, b.y), Math.abs(b.x - a.x), Math.abs(b.y - a.y));
        ctx.strokeStyle = COLOR_LESION_STROKE;
        ctx.lineWidth = 1.5;
        ctx.strokeRect(Math.min(a.x, b.x), Math.min(a.y, b.y), Math.abs(b.x - a.x), Math.abs(b.y - a.y));
      }
    } else {
      drawPoly(wallPoints, COLOR_WALL_FILL, COLOR_WALL_STROKE);
      drawPoly(displayPoints, COLOR_LESION_FILL, COLOR_LESION_STROKE);
      drawHandles(wallPoints, WALL_CTRL_COUNT, COLOR_WALL_HANDLE, 'wall');
      drawHandles(displayPoints, LESION_CTRL_COUNT, COLOR_LESION_HANDLE, 'lesion');

      if (samBoxPreview) {
        const a = map(samBoxPreview.x1, samBoxPreview.y1);
        const b = map(samBoxPreview.x2, samBoxPreview.y2);
        ctx.strokeStyle = 'rgba(168, 85, 247, 0.95)';
        ctx.lineWidth = 1.5;
        ctx.setLineDash([4, 3]);
        ctx.strokeRect(
          Math.min(a.x, b.x),
          Math.min(a.y, b.y),
          Math.abs(b.x - a.x),
          Math.abs(b.y - a.y),
        );
        ctx.setLineDash([]);
      }
    }

    const drawPromptStroke = (stroke: ActiveSamStroke) => {
      if (stroke.points.length < 2) return;
      const first = map(stroke.points[0][0], stroke.points[0][1]);
      ctx.save();
      ctx.beginPath();
      ctx.moveTo(first.x, first.y);
      for (const point of stroke.points.slice(1)) {
        const mapped = map(point[0], point[1]);
        ctx.lineTo(mapped.x, mapped.y);
      }
      if (stroke.kind === 'lasso') ctx.closePath();
      ctx.strokeStyle = stroke.target === 'lumen'
        ? (stroke.label === 'negative' ? '#fb7185' : '#e879f9')
        : (stroke.label === 'negative' ? '#fb7185' : '#4ade80');
      ctx.lineWidth = Math.max(2, Math.min(8, stroke.width * scale));
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      ctx.setLineDash(stroke.kind === 'lasso' ? [8, 5] : []);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.beginPath();
      ctx.arc(first.x, first.y, 4, 0, Math.PI * 2);
      ctx.fillStyle = ctx.strokeStyle;
      ctx.fill();
      ctx.strokeStyle = '#f8fafc';
      ctx.lineWidth = 1;
      ctx.stroke();
      ctx.restore();
    };

    for (const stroke of promptStrokes) drawPromptStroke(stroke);
    if (activePromptStroke) drawPromptStroke(activePromptStroke);

    for (const c of samClicks) {
      const { x, y } = map(c.x, c.y);
      ctx.beginPath();
      ctx.arc(x, y, 5, 0, Math.PI * 2);
      ctx.fillStyle = c.label === 'negative' ? '#f43f5e' : '#22c55e';
      ctx.fill();
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = 1.5;
      ctx.stroke();
    }

    for (const c of nnInteractiveClicks) {
      const { x, y } = map(c.x, c.y);
      const positive = c.label !== 'negative';
      ctx.save();
      ctx.beginPath();
      ctx.arc(x, y, 6, 0, Math.PI * 2);
      ctx.fillStyle = positive ? 'rgba(34, 197, 94, 0.9)' : 'rgba(244, 63, 94, 0.9)';
      ctx.fill();
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = 1.5;
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(x - 3, y);
      ctx.lineTo(x + 3, y);
      if (positive) {
        ctx.moveTo(x, y - 3);
        ctx.lineTo(x, y + 3);
      }
      ctx.strokeStyle = '#0f172a';
      ctx.lineWidth = 1.2;
      ctx.stroke();
      ctx.restore();
    }

    if (displayLumenPoly.length >= 3) {
      drawPoly(displayLumenPoly, COLOR_LUMEN_FILL, COLOR_LUMEN_STROKE);
    }
    const lumenBoxIsProxy = Boolean(displayLumenBox) && displayLumenPoly.length < 3;
    if (displayLumenBox) {
      const a = map(displayLumenBox.x1, displayLumenBox.y1);
      const b = map(displayLumenBox.x2, displayLumenBox.y2);
      const left = Math.min(a.x, b.x);
      const top = Math.min(a.y, b.y);
      const width = Math.abs(b.x - a.x);
      const height = Math.abs(b.y - a.y);
      ctx.fillStyle = COLOR_LUMEN_BOX_FILL;
      ctx.fillRect(left, top, width, height);
      ctx.strokeStyle = lumenEditMode ? COLOR_LUMEN_STROKE : COLOR_LUMEN_BOX_STROKE;
      ctx.lineWidth = lumenEditMode || lumenBoxIsProxy ? 1.35 : 1.05;
      // Solid box only — dashed proxy frame reads as unexplained orange/green clutter.
      ctx.setLineDash([]);
      ctx.strokeRect(left, top, width, height);
      if (lumenBoxIsProxy) {
        const label = zh ? '胃腔框代理' : 'Lumen box proxy';
        ctx.save();
        ctx.font = '10px ui-monospace, SFMono-Regular, Menlo, monospace';
        const labelWidth = ctx.measureText(label).width + 10;
        ctx.fillStyle = 'rgba(88, 28, 135, 0.72)';
        ctx.fillRect(left, Math.max(4, top - 16), labelWidth, 14);
        ctx.fillStyle = '#fdf4ff';
        ctx.fillText(label, left + 5, Math.max(14, top - 6));
        ctx.restore();
      }
      if (lumenEditMode) {
        const cornerSize = Math.max(2.2, Math.min(4.5, 3.2 / Math.sqrt(Math.max(scale, 0.15))));
        for (const [x, y] of [
          [left, top],
          [left + width, top],
          [left, top + height],
          [left + width, top + height],
        ]) {
          ctx.beginPath();
          ctx.rect(x - cornerSize, y - cornerSize, cornerSize * 2, cornerSize * 2);
          ctx.fillStyle = COLOR_LUMEN_HANDLE;
          ctx.fill();
          ctx.strokeStyle = HANDLE_STROKE;
          ctx.lineWidth = 1;
          ctx.stroke();
        }
      }
    }

    // Keep the ultrasound canvas clean: no green/orange LayerBridge dashes, contact arcs,
    // breakthrough rings, or outward arrows on the main view. Wall-layer graphics stay in
    // the side analysis card only (meeting: avoid "一眼乱分析" overlay clutter).
    const relationGeometry = computeLesionLumenGeometry(displayPoints, displayLumenPoly, displayLumenBox);
    if (relationGeometry.relation === 'overlap' && displayPoints.length >= 3) {
      const traceLesion = () => {
        strokeClosedPolyline(ctx, displayPoints, map);
      };
      const traceLumen = () => {
        if (displayLumenPoly.length >= 3) {
          strokeClosedPolyline(ctx, displayLumenPoly, map);
          return true;
        }
        if (!displayLumenBox) return false;
        const topLeft = map(displayLumenBox.x1, displayLumenBox.y1);
        const bottomRight = map(displayLumenBox.x2, displayLumenBox.y2);
        ctx.beginPath();
        ctx.rect(
          Math.min(topLeft.x, bottomRight.x),
          Math.min(topLeft.y, bottomRight.y),
          Math.abs(bottomRight.x - topLeft.x),
          Math.abs(bottomRight.y - topLeft.y),
        );
        return true;
      };
      if (traceLumen()) {
        // Soft overlap wash only — no hatch / dashed guides.
        ctx.save();
        ctx.clip();
        traceLesion();
        ctx.clip();
        ctx.fillStyle = 'rgba(251, 191, 36, 0.08)';
        ctx.fillRect(0, 0, cw, ch);
        ctx.restore();
      }
    }

    if (viewFocusMode === 'overlap' && overlapFocus) {
      const topLeft = map(overlapFocus.x1, overlapFocus.y1);
      const bottomRight = map(overlapFocus.x2, overlapFocus.y2);
      const left = Math.min(topLeft.x, bottomRight.x);
      const top = Math.min(topLeft.y, bottomRight.y);
      const width = Math.abs(bottomRight.x - topLeft.x);
      const height = Math.abs(bottomRight.y - topLeft.y);
      ctx.save();
      ctx.strokeStyle = '#fde68a';
      ctx.lineWidth = 2.5;
      ctx.setLineDash([7, 4]);
      ctx.strokeRect(left, top, width, height);
      ctx.setLineDash([]);
      const label = zh ? '接触/突破分析区放大' : 'Contact / breakthrough zoom';
      ctx.font = '600 10px ui-monospace, SFMono-Regular, Menlo, monospace';
      const labelWidth = ctx.measureText(label).width + 10;
      ctx.fillStyle = 'rgba(15, 23, 42, 0.72)';
      ctx.fillRect(left, Math.max(4, top - 17), labelWidth, 15);
      ctx.fillStyle = '#fde68a';
      ctx.fillText(label, left + 5, Math.max(15, top - 6));
      ctx.restore();
    }

    // Reader simple mode: keep the ultrasound canvas clean (no top-left status legend).
    // Non-simple / research mode still gets a compact geometry cue when useful.
    if (!simpleVideoMode && (displayPoints.length >= 3 || displayLumenPoly.length >= 3 || displayLumenBox) && relationGeometry.available) {
      const lumenSource = displayLumenPoly.length >= 3
        ? (zh ? '胃腔轮廓' : 'Lumen contour')
        : displayLumenBox
          ? (zh ? '胃腔框代理' : 'Lumen box proxy')
          : (zh ? '胃腔未标注' : 'Lumen missing');
      const legendLines = [
        lumenSource,
        geometryRelationText(relationGeometry, zh),
        geometryQualityText(relationGeometry, zh),
      ].filter(Boolean);
      ctx.save();
      ctx.font = '10px ui-monospace, SFMono-Regular, Menlo, monospace';
      const legendWidth = Math.max(...legendLines.map((line) => ctx.measureText(line).width)) + 16;
      const legendHeight = legendLines.length * 13 + 10;
      const legendX = 10;
      const legendY = 10;
      ctx.fillStyle = 'rgba(2, 6, 23, 0.84)';
      ctx.fillRect(legendX, legendY, legendWidth, legendHeight);
      ctx.strokeStyle = 'rgba(232, 121, 249, 0.35)';
      ctx.strokeRect(legendX, legendY, legendWidth, legendHeight);
      legendLines.forEach((line, index) => {
        ctx.fillStyle = '#f8fafc';
        ctx.fillText(line, legendX + 8, legendY + 14 + index * 13);
      });
      ctx.restore();
    }

    // Draw the lesion last so lumen fills, boxes, relation guides, and wall
    // annotations cannot hide the generated boundary.
    if (displayPoints.length >= 3 && (
      displayLumenPoly.length >= 3
      || displayLumenBox
      || points.length < 3
    )) {
      ctx.save();
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      strokeClosedPolyline(ctx, displayPoints, map);
      ctx.strokeStyle = 'rgba(2, 6, 23, 0.9)';
      ctx.lineWidth = 4.5;
      ctx.stroke();
      strokeClosedPolyline(ctx, displayPoints, map);
      ctx.strokeStyle = COLOR_LESION_STROKE;
      ctx.lineWidth = 2.4;
      ctx.stroke();
      if (simpleEditMode && simpleEditLayer === 'lesion') {
        drawHandles(displayPoints, Math.min(12, LESION_CTRL_COUNT), COLOR_LESION_HANDLE, 'lesion');
      }
      ctx.restore();
    }

    // Historical versions are preview-only: they are rendered with a dashed
    // yellow overlay and never replace the editable current mask.
    if (historyPreview && (
      historyPreviewPoints.length >= 3
      || historyPreviewRoiBox
      || historyPreviewLumenPoly.length >= 3
      || historyPreviewLumenBox
    )) {
      ctx.save();
      ctx.globalAlpha = 0.9;
      if (historyPreviewPoints.length >= 3) {
        drawPoly(historyPreviewPoints, 'rgba(250, 204, 21, 0.08)', '#facc15', true);
      }
      if (historyPreviewLumenPoly.length >= 3) {
        drawPoly(historyPreviewLumenPoly, 'rgba(244, 114, 182, 0.06)', '#f9a8d4', true);
      }
      if (historyPreviewRoiBox) {
        const a = map(historyPreviewRoiBox.x1, historyPreviewRoiBox.y1);
        const b = map(historyPreviewRoiBox.x2, historyPreviewRoiBox.y2);
        ctx.strokeStyle = '#fde68a';
        ctx.lineWidth = 1.5;
        ctx.setLineDash([5, 4]);
        ctx.strokeRect(
          Math.min(a.x, b.x),
          Math.min(a.y, b.y),
          Math.abs(b.x - a.x),
          Math.abs(b.y - a.y),
        );
        ctx.setLineDash([]);
      }
      if (historyPreviewLumenBox) {
        const a = map(historyPreviewLumenBox.x1, historyPreviewLumenBox.y1);
        const b = map(historyPreviewLumenBox.x2, historyPreviewLumenBox.y2);
        ctx.strokeStyle = '#f9a8d4';
        ctx.lineWidth = 1.5;
        ctx.setLineDash([5, 4]);
        ctx.strokeRect(
          Math.min(a.x, b.x),
          Math.min(a.y, b.y),
          Math.abs(b.x - a.x),
          Math.abs(b.y - a.y),
        );
        ctx.setLineDash([]);
      }
      const previewLabel = zh
        ? `历史预览: ${historyPreview.action || '版本'}`
        : `History preview: ${historyPreview.action || 'version'}`;
      ctx.font = '10px ui-monospace, SFMono-Regular, Menlo, monospace';
      const labelWidth = ctx.measureText(previewLabel).width + 12;
      ctx.fillStyle = 'rgba(120, 53, 15, 0.9)';
      ctx.fillRect(10, Math.max(10, ch - 28), labelWidth, 18);
      ctx.fillStyle = '#fef3c7';
      ctx.fillText(previewLabel, 16, Math.max(23, ch - 15));
      ctx.restore();
    }

    const lens = magnifierOn ? magnifierPosRef.current : null;
    const lensSource = useVideo ? video : img;
    if (lens && lensSource) {
      const lensR = Math.max(56, Math.min(96, Math.round(Math.min(cw, ch) * 0.12)));
      const zoom = 2.75;
      const magScale = scale * zoom;
      ctx.save();
      ctx.beginPath();
      ctx.arc(lens.cx, lens.cy, lensR, 0, Math.PI * 2);
      ctx.clip();
      ctx.fillStyle = '#0a0a0a';
      ctx.fillRect(lens.cx - lensR, lens.cy - lensR, lensR * 2, lensR * 2);
      ctx.drawImage(
        lensSource,
        lens.cx - lens.ix * magScale,
        lens.cy - lens.iy * magScale,
        iw * magScale,
        ih * magScale,
      );
      // Light contour cues inside the lens so breakthrough edges stay readable.
      if (displayPoints.length >= 3) {
        strokeClosedPolyline(ctx, displayPoints, (x, y) => ({
          x: lens.cx + (x - lens.ix) * magScale,
          y: lens.cy + (y - lens.iy) * magScale,
        }));
        ctx.strokeStyle = 'rgba(103, 232, 249, 0.85)';
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }
      if (displayLumenPoly.length >= 3) {
        strokeClosedPolyline(ctx, displayLumenPoly, (x, y) => ({
          x: lens.cx + (x - lens.ix) * magScale,
          y: lens.cy + (y - lens.iy) * magScale,
        }));
        ctx.strokeStyle = 'rgba(232, 121, 249, 0.75)';
        ctx.lineWidth = 1.25;
        ctx.stroke();
      }
      ctx.restore();
      ctx.beginPath();
      ctx.arc(lens.cx, lens.cy, lensR, 0, Math.PI * 2);
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.9)';
      ctx.lineWidth = 2;
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(lens.cx, lens.cy, lensR + 3, 0, Math.PI * 2);
      ctx.strokeStyle = 'rgba(14, 165, 233, 0.55)';
      ctx.lineWidth = 2;
      ctx.stroke();
      ctx.font = '600 10px ui-monospace, SFMono-Regular, Menlo, monospace';
      const lensLabel = zh ? `放大镜 x${zoom.toFixed(1)}` : `Lens x${zoom.toFixed(1)}`;
      const labelW = ctx.measureText(lensLabel).width + 10;
      ctx.fillStyle = 'rgba(2, 6, 23, 0.82)';
      ctx.fillRect(lens.cx - labelW / 2, lens.cy + lensR + 6, labelW, 16);
      ctx.fillStyle = '#e0f2fe';
      ctx.fillText(lensLabel, lens.cx - labelW / 2 + 5, lens.cy + lensR + 17);
    }

  }, [points, wallPoints, imgLoaded, dragIndex, dragLayer, mediaMode, frameFrozen, wallAnalysisOpen, samClicks, promptStrokes, activePromptStroke, nnInteractiveClicks, samBoxPreview, simpleVideoMode, simpleEditMode, simpleEditLayer, videoFrameOverrides, lumenBox, lumenPolygon, lumenEditMode, viewFocusBox, viewFocusMode, overlapFocus, layerResult, videoTime, historyPreview, magnifierOn, zh]);

  useEffect(() => {
    redrawRef.current = redraw;
  }, [redraw]);
  useEffect(() => {
    maybeTrackWhilePlayingRef.current = maybeTrackWhilePlaying;
  }, [maybeTrackWhilePlaying]);
  useEffect(() => {
    redraw();
  }, [redraw]);
  useEffect(() => {
    if (!open || mediaMode !== 'image' || !patient?.image_url) return;
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => {
      imgRef.current = img;
      setImgLoaded(true);
      const canvas = canvasRef.current;
      const container = containerRef.current;
      if (canvas && container) {
        const rect = container.getBoundingClientRect();
        canvas.width = Math.max(320, Math.floor(rect.width));
        canvas.height = Math.max(240, Math.floor(rect.height));
      }
      try {
        const c = document.createElement('canvas');
        c.width = img.naturalWidth;
        c.height = img.naturalHeight;
        const ctx = c.getContext('2d');
        if (ctx) {
          ctx.drawImage(img, 0, 0);
          setFrameDataUrl(c.toDataURL('image/jpeg', 0.92));
        }
      } catch {
        /* CORS / tainted canvas — analysis without echo rays still works */
      }
      redraw();
    };
    img.onerror = () => {
      setMessage(zh ? '图像加载失败' : 'Failed to load image');
      setImgLoaded(false);
    };
    img.src = patient.image_url;
  }, [open, mediaMode, patient?.image_url, patient?.id, zh, redraw]);

  useEffect(() => {
    if (!open || mediaMode !== 'video' || !videoUrl) return;
    const video = videoRef.current;
    if (!video) return;
    setFrameFrozen(false);
    frameFrozenRef.current = false;
    const stopPlaybackLoop = () => {
      if (playbackRafRef.current !== null) {
        cancelAnimationFrame(playbackRafRef.current);
        playbackRafRef.current = null;
      }
    };
    const playbackTick = () => {
      playbackRafRef.current = null;
      if (video.paused || video.ended || scrubbingRef.current) return;
      const now = performance.now();
      const t = video.currentTime || 0;
      // Paint the scrubber via DOM first; React state updates are much rarer.
      if (now - playbackUiAtRef.current >= 66) {
        playbackUiAtRef.current = now;
        paintProgressUi(t);
      }
      if (now - playbackStateAtRef.current >= 250) {
        playbackStateAtRef.current = now;
        setVideoTime(t);
      }
      if (!frameFrozenRef.current && dragIndexRef.current === null) {
        // Overlay refresh ~20fps is enough while the native <video> paints frames.
        if (now - lastScrubRedrawAtRef.current >= 50) {
          lastScrubRedrawAtRef.current = now;
          redrawRef.current();
        }
        void maybeTrackWhilePlayingRef.current();
      }
      playbackRafRef.current = requestAnimationFrame(playbackTick);
    };
    const startPlaybackLoop = () => {
      if (playbackRafRef.current === null) {
        playbackRafRef.current = requestAnimationFrame(playbackTick);
      }
    };
    const onMeta = () => {
      setVideoDuration(video.duration || 0);
      video.defaultPlaybackRate = videoPlaybackRateRef.current;
      video.playbackRate = videoPlaybackRateRef.current;
      syncFrameFromVideo({ force: true });
      redraw();
    };
    const onTime = () => {
      if (scrubbingRef.current) return;
      if (frameFrozenRef.current || dragIndexRef.current !== null) {
        // Still update clock when scrubbing while frozen? only if not dragging
        if (dragIndexRef.current === null && video.paused) {
          const t = video.currentTime || 0;
          paintProgressUi(t);
          setVideoTime(t);
        }
        return;
      }
      if (!video.paused) startPlaybackLoop();
    };
    const onPlay = () => {
      setIsPlaying(true);
      setFrameFrozen(false);
      frameFrozenRef.current = false;
      startPlaybackLoop();
    };
    const onPause = () => {
      if (scrubbingRef.current) {
        setIsPlaying(false);
        stopPlaybackLoop();
        return;
      }
      setIsPlaying(false);
      stopPlaybackLoop();
      const t = video.currentTime || 0;
      setVideoTime(t);
      paintProgressUi(t, { forceSlider: true });
      syncFrameFromVideo({ force: true });
      redrawRef.current();
    };
    const onEnded = () => {
      setIsPlaying(false);
      stopPlaybackLoop();
      const t = video.currentTime || 0;
      setVideoTime(t);
      paintProgressUi(t, { forceSlider: true });
      if (videoFrameOverridesRef.current.length) {
        void persistOverrideRef.current('video_tracking_complete');
      }
    };
    video.addEventListener('loadedmetadata', onMeta);
    video.addEventListener('timeupdate', onTime);
    video.addEventListener('play', onPlay);
    video.addEventListener('pause', onPause);
    video.addEventListener('ended', onEnded);
    video.src = videoUrl;
    video.load();
    return () => {
      stopPlaybackLoop();
      video.removeEventListener('loadedmetadata', onMeta);
      video.removeEventListener('timeupdate', onTime);
      video.removeEventListener('play', onPlay);
      video.removeEventListener('pause', onPause);
      video.removeEventListener('ended', onEnded);
    };
  }, [open, mediaMode, paintProgressUi, videoUrl, syncFrameFromVideo]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    video.defaultPlaybackRate = videoPlaybackRate;
    video.playbackRate = videoPlaybackRate;
  }, [videoPlaybackRate, videoUrl]);

  useEffect(() => {
    if (!open) return;
    const resizeCanvas = () => {
      const canvas = canvasRef.current;
      const container = containerRef.current;
      if (!canvas || !container) return;
      const rect = container.getBoundingClientRect();
      const nextWidth = Math.max(320, Math.floor(rect.width));
      const nextHeight = Math.max(240, Math.floor(rect.height));
      if (canvas.width !== nextWidth || canvas.height !== nextHeight) {
        canvas.width = nextWidth;
        canvas.height = nextHeight;
      }
      redraw();
    };
    const observer = typeof ResizeObserver !== 'undefined'
      ? new ResizeObserver(() => requestAnimationFrame(resizeCanvas))
      : null;
    if (observer && containerRef.current) observer.observe(containerRef.current);
    window.addEventListener('resize', resizeCanvas);
    resizeCanvas();
    return () => {
      observer?.disconnect();
      window.removeEventListener('resize', resizeCanvas);
    };
  }, [open, redraw]);

  const canvasToImage = useCallback((e: { clientX: number; clientY: number }): number[] | null => {
    const canvas = canvasRef.current;
    if (!canvas) return null;
    const video = videoRef.current;
    const img = imgRef.current;
    const useVideo = mediaMode === 'video' && video && video.videoWidth > 0;
    const iw = useVideo ? video!.videoWidth : (img?.naturalWidth || 0);
    const ih = useVideo ? video!.videoHeight : (img?.naturalHeight || 0);
    if (!iw || !ih) return null;
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    const cx = (e.clientX - rect.left) * scaleX;
    const cy = (e.clientY - rect.top) * scaleY;
    const { scale, dx, dy } = computeDisplayTransform(iw, ih, canvas.width, canvas.height, viewFocusBox);
    const ix = (cx - dx) / scale;
    const iy = (cy - dy) / scale;
    if (ix < 0 || iy < 0 || ix > iw || iy > ih) return null;
    return [ix, iy];
  }, [mediaMode, viewFocusBox]);

  const hitThreshold = useCallback(() => {
    const canvas = canvasRef.current;
    const video = videoRef.current;
    const img = imgRef.current;
    const useVideo = mediaMode === 'video' && video && video.videoWidth > 0;
    const iw = useVideo ? video!.videoWidth : (img?.naturalWidth || 1);
    const ih = useVideo ? video!.videoHeight : (img?.naturalHeight || 1);
    if (!canvas) return 24;
    const rect = canvas.getBoundingClientRect();
    // Hit target stays larger than the drawn handle so small/transparent handles remain grabable.
    const scale = Math.min(canvas.width / iw, canvas.height / ih) * (rect.width / Math.max(1, canvas.width));
    return Math.max(16, 12 / Math.max(scale, 1e-6));
  }, [mediaMode]);

  const invalidateNnInteractiveSession = useCallback((options: { abort?: boolean } = {}) => {
    if (options.abort !== false) {
      nnInteractiveAbortRef.current?.abort();
      nnInteractiveAbortRef.current = null;
    }
    nnInteractiveRequestRef.current += 1;
    setNnInteractiveBusy(false);
    nnInteractiveSessionRef.current = { key: '', id: '', initialized: false };
  }, []);

  const clearSamPrompts = useCallback(() => {
    samClicksRef.current = [];
    setSamClicks([]);
    setNnInteractiveClicks([]);
    invalidateNnInteractiveSession({ abort: true });
    if (promptStrokeRafRef.current != null) {
      cancelAnimationFrame(promptStrokeRafRef.current);
      promptStrokeRafRef.current = null;
    }
    pendingPromptPointRef.current = null;
    promptStrokesRef.current = [];
    activePromptStrokeRef.current = null;
    setPromptStrokes([]);
    setActivePromptStroke(null);
    samBoxDragRef.current = null;
    setSamBoxPreview(null);
  }, [invalidateNnInteractiveSession]);

  useEffect(() => () => {
    nnInteractiveAbortRef.current?.abort();
    nnInteractiveAbortRef.current = null;
    if (promptStrokeRafRef.current != null) {
      cancelAnimationFrame(promptStrokeRafRef.current);
      promptStrokeRafRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (!nnInteractiveMode || mediaMode !== 'video') return;
    const live = Number((videoRef.current?.currentTime ?? videoTime).toFixed(3)).toFixed(3);
    const sessionKey = nnInteractiveSessionRef.current.key;
    if (!sessionKey) return;
    const parts = sessionKey.split(':');
    // patient:id:target:mode:url:time:lumenKey — time is near the end.
    if (!parts.includes(live)) {
      invalidateNnInteractiveSession({ abort: true });
    }
  }, [invalidateNnInteractiveSession, mediaMode, nnInteractiveMode, videoTime]);

  const stopInteractivePrompt = useCallback(() => {
    setNnInteractiveMode(false);
    setNnInteractiveTarget('lesion');
    setActiveSamPromptLabel('positive');
    clearSamPrompts();
  }, [clearSamPrompts]);

  const enterSimpleBoxPrompt = useCallback(() => {
    stopInteractivePrompt();
    setMode('sam');
    setSimplePromptMode('box');
    setSimpleEditMode(false);
    setLumenEditMode(false);
    setSimpleEditLayer('lesion');
    setActiveLayer('lesion');
    setSimplePromptBox(null);
    setTrackOnPlay(false);
    setMessage(
      zh
        ? '框选病灶：在影像中拖出矩形后自动分割；随后可拖控制点微调'
        : 'Box lesion: drag a rectangle to segment automatically, then drag handles to refine',
    );
  }, [stopInteractivePrompt, zh]);

  const enterSimpleContourEdit = useCallback((layer: ContourLayer) => {
    stopInteractivePrompt();
    if (simpleVideoMode && mediaMode === 'video' && videoFrameOverridesRef.current.length) {
      const currentTime = videoRef.current?.currentTime || videoTime;
      const trackedFrame = nearestOverrideFrame(videoFrameOverridesRef.current, currentTime, Number.POSITIVE_INFINITY);
      if (trackedFrame?.mask_polygon?.length) {
        pointsRef.current = clonePoly(trackedFrame.mask_polygon);
        setPoints(pointsRef.current);
      }
      if (trackedFrame?.lumen_polygon?.length) {
        lumenPolygonRef.current = clonePoly(trackedFrame.lumen_polygon);
        setLumenPolygon(lumenPolygonRef.current);
      }
      if (trackedFrame?.lumen_bbox) {
        lumenBoxRef.current = trackedFrame.lumen_bbox;
        setLumenBox(trackedFrame.lumen_bbox);
      }
    }
    setMode('soft');
    setSimplePromptMode('box');
    setSimpleEditLayer(layer);
    setActiveLayer(layer);
    setSimpleEditMode(true);
    setLumenEditMode(false);
    setTrackOnPlay(false);
    setMessage('');
  }, [mediaMode, simpleVideoMode, stopInteractivePrompt, videoTime]);

  const toggleSimpleContourEdit = useCallback(() => {
    if (simpleEditMode) {
      setSimpleEditMode(false);
      setSimplePromptMode('box');
      void persistOverrideRef.current('doctor_edit', { silent: true });
      setMessage(zh ? '已完成控制点编辑；可点顶中「辅助意见」生成证据' : 'Contour edit finished; use top Assist to generate evidence');
      return;
    }
    enterSimpleContourEdit(points.length >= 3 ? 'lesion' : 'wall');
  }, [enterSimpleContourEdit, points.length, simpleEditMode, zh]);

  const enterLumenBoxEdit = useCallback((reason?: string) => {
    stopInteractivePrompt();
    setMode('soft');
    setSimplePromptMode('box');
    setSimpleEditMode(false);
    setLumenEditMode(true);
    setTrackOnPlay(false);
    setMessage(
      zh
        ? `胃腔框可连续调整：拖角点缩放，拖框内移动；框外拖拽可重画。胃腔须覆盖胃壁与肿块。${reason ? ` ${reason}` : ''} 点「完成调整」才退出。`
        : `Lumen box stays editable: drag corners/inside to adjust, drag outside to redraw. Cover wall and mass.${reason ? ` ${reason}` : ''} Tap Done to exit.`,
    );
  }, [stopInteractivePrompt, zh]);

  const toggleLumenBoxEdit = useCallback(() => {
    if (lumenEditMode) {
      setLumenEditMode(false);
      setSimplePromptMode('box');
      setMessage(zh ? '已退出胃腔框编辑；需要时可再点「调整框」继续改' : 'Left lumen box edit; tap Edit box again anytime to continue');
      return;
    }
    enterLumenBoxEdit();
  }, [enterLumenBoxEdit, lumenEditMode, zh]);

  const prepareLumenDetection = useCallback(() => {
    stopInteractivePrompt();
    setMode('soft');
    setSimplePromptMode('box');
    setSimpleEditMode(false);
    setLumenEditMode(false);
    setTrackOnPlay(false);
  }, [stopInteractivePrompt]);

  const runLesionModel = useCallback(async (
    imgPt: number[] | null,
    box: { x1: number; y1: number; x2: number; y2: number } | null = null,
    clicks: Array<{ x: number; y: number; label: 'positive' | 'negative' }> = [],
    modelOverride?: LesionSegmentationModel,
  ): Promise<number[][] | null> => {
    if (!patient || segmentationBusy) return null;
    const activeSegmentationModel = modelOverride || segmentationModel;
    const traceId = `lesion_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    const traceStartedAt = performance.now();
    setSegmentationBusy(true);
    setSegmentationModelResult(null);
    setMessage(
      zh
        ? `${segmentationModelName(activeSegmentationModel, true)} 病灶预测中…`
        : `${segmentationModelName(activeSegmentationModel, false)} lesion prediction…`,
    );
    try {
      const frame = await videoOrImageToSamFrame(
        videoRef.current,
        imgRef.current,
        mediaMode === 'video',
        1024,
      );
      const scale = frame.scale || 1;
      const response = await fetch('/api/agent/lesion-segmentation', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          frame_png_b64: frame.b64,
          model: activeSegmentationModel,
          threshold: 0.5,
          image_width: frame.width,
          image_height: frame.height,
          box: box
            ? {
                x1: box.x1 * scale,
                y1: box.y1 * scale,
                x2: box.x2 * scale,
                y2: box.y2 * scale,
              }
            : undefined,
          clicks: clicks.length
            ? clicks.map((point) => ({
                x: point.x * scale,
                y: point.y * scale,
                label: point.label,
              }))
            : imgPt
              ? [{ x: imgPt[0] * scale, y: imgPt[1] * scale, label: 'positive' }]
              : [],
        }),
      });
      const data = await readJsonPayload<{
        ok?: boolean;
        error?: string;
        mask_polygon?: number[][];
        model?: string;
        lesion_area_ratio?: number;
        validation_summary?: Record<string, unknown>;
      }>(response, 'Lesion segmentation endpoint');
      if (!response.ok || !data.ok || !Array.isArray(data.mask_polygon) || data.mask_polygon.length < 3) {
        throw new Error(data.error || 'Lesion model returned no valid mask');
      }
      setSegmentationModelResult({
        model: data.model,
        lesion_area_ratio: data.lesion_area_ratio,
        validation_summary: data.validation_summary,
      });
      const maxCoord = Math.max(...data.mask_polygon.flatMap((point) => point));
      const polyFull = maxCoord <= 1.5
        ? data.mask_polygon.map((point) => [point[0] * frame.fullWidth, point[1] * frame.fullHeight])
        : data.mask_polygon.map((point) => [point[0] / scale, point[1] / scale]);
      const poly = prepareEditableContour(polyFull, LESION_CONTOUR_MAX_POINTS);
      maskAuditRef.current('model_trace', {
        trace_id: traceId,
        operation: 'lesion_segmentation',
        model: data.model || activeSegmentationModel,
        source: 'lesion_segmentation_endpoint',
        outcome: 'success',
        frame_time_sec: Number((videoRef.current?.currentTime ?? videoTime).toFixed(3)),
        input: {
          has_box: Boolean(box),
          click_count: clicks.length || (imgPt ? 1 : 0),
          positive_clicks: clicks.filter((click) => click.label !== 'negative').length
            || (imgPt && !clicks.length ? 1 : 0),
          negative_clicks: clicks.filter((click) => click.label === 'negative').length,
        },
        output: {
          polygon_points: poly.length,
          lesion_area_ratio: data.lesion_area_ratio,
          validation_summary: data.validation_summary,
        },
        duration_ms: Math.round(performance.now() - traceStartedAt),
      });
      contourInteractionRef.current = true;
      generatedLesionRef.current = clonePoly(poly);
      pointsRef.current = poly;
      setPoints(poly);
      snapshotOriginal(poly, wallPointsRef.current);
      const assistReport = buildModelAssistReport(
        patient,
        poly,
        frame.fullWidth,
        frame.fullHeight,
        activeSegmentationModel,
        data.lesion_area_ratio,
        zh,
      );
      setSamReport(assistReport);
      onSystemReport?.(assistReport);
      onImagingAssist?.({
        layerResult,
        lesionPolygon: poly,
        wallPolygon: wallPointsRef.current,
        frameSize: { width: frame.fullWidth, height: frame.fullHeight },
        lumenBBox: lumenBoxRef.current,
        lumenPolygon: lumenPolygonRef.current.length >= 3 ? lumenPolygonRef.current : undefined,
      });
      setMessage(
        zh
          ? `${segmentationModelName(activeSegmentationModel, true)} 已生成病灶 ROI（${poly.length} 点），正点 ${clicks.filter((click) => click.label !== 'negative').length || (imgPt && !clicks.length ? 1 : 0)}，负点 ${clicks.filter((click) => click.label === 'negative').length}`
          : `${segmentationModelName(activeSegmentationModel, false)} lesion ROI ready (${poly.length} points), positive ${clicks.filter((click) => click.label !== 'negative').length || (imgPt && !clicks.length ? 1 : 0)}, negative ${clicks.filter((click) => click.label === 'negative').length}`,
      );
      return poly;
    } catch (error) {
      const messageText = error instanceof Error ? error.message : 'Lesion model failed';
      maskAuditRef.current('model_trace', {
        trace_id: traceId,
        operation: 'lesion_segmentation',
        model: activeSegmentationModel,
        source: 'lesion_segmentation_endpoint',
        outcome: 'error',
        frame_time_sec: Number((videoRef.current?.currentTime ?? videoTime).toFixed(3)),
        input: {
          has_box: Boolean(box),
          click_count: clicks.length || (imgPt ? 1 : 0),
        },
        error: messageText.slice(0, 240),
        duration_ms: Math.round(performance.now() - traceStartedAt),
      });
      setSegmentationModelResult({ error: messageText });
      setMessage(messageText);
      return null;
    } finally {
      setSegmentationBusy(false);
    }
  }, [layerResult, mediaMode, onImagingAssist, onSystemReport, patient, segmentationBusy, segmentationModel, snapshotOriginal, videoTime, wallPointsRef, zh]);

  useEffect(() => {
    runLesionModelRef.current = runLesionModel;
  }, [runLesionModel]);

  const refineWithNnInteractive = useCallback(async (
    target: 'lesion' | 'lumen' = 'lesion',
    interaction?: { x: number; y: number; label: 'positive' | 'negative' },
    scribbles: ActiveSamStroke[] = [],
    additionalPoints: Array<{ x: number; y: number; label: 'positive' | 'negative' }> = [],
  ) => {
    const lumenSeedBox = lumenBoxRef.current;
    const initialPolygon = target === 'lumen'
      ? (
        lumenPolygonRef.current.length >= 3
          ? lumenPolygonRef.current
          : lumenSeedBox
            ? [
              [lumenSeedBox.x1, lumenSeedBox.y1],
              [lumenSeedBox.x2, lumenSeedBox.y1],
              [lumenSeedBox.x2, lumenSeedBox.y2],
              [lumenSeedBox.x1, lumenSeedBox.y2],
            ]
            : []
      )
      : getCurrentTrackedPolygon();
    if (!patient || initialPolygon.length < 3 || nnInteractiveBusy) {
      if (!initialPolygon.length && patient) {
        setMessage(
          target === 'lumen'
            ? (zh ? '请先检测或分割胃腔，再启动胃腔边界辅助' : 'Detect or segment the lumen before boundary assistance')
            : (zh ? '请先框选病灶，再启动病灶边界辅助' : 'Create a lesion mask before boundary assistance'),
        );
      }
      return;
    }
    if (nnInteractiveAvailable !== true) {
      setNnInteractiveMode(false);
      setMessage(
        zh
          ? '边界辅助服务未连接，请启动辅助服务后点击状态图标重试'
          : 'Boundary assistance is offline; start the service and retry from the status icon',
      );
      return;
    }
    const traceId = `nninteractive_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    const traceStartedAt = performance.now();
    nnInteractiveAbortRef.current?.abort();
    const abortController = new AbortController();
    nnInteractiveAbortRef.current = abortController;
    const requestId = nnInteractiveRequestRef.current + 1;
    nnInteractiveRequestRef.current = requestId;
    setNnInteractiveBusy(true);
    freezeCurrentFrame();
    try {
      const liveVideoTime = mediaMode === 'video'
        ? Number((videoRef.current?.currentTime ?? videoTime).toFixed(3))
        : 0;
      const frame = await videoOrImageToSamFrame(
        videoRef.current,
        imgRef.current,
        mediaMode === 'video',
        1024,
      );
      if (requestId !== nnInteractiveRequestRef.current || abortController.signal.aborted) return;
      const lumenKey = lumenSeedBox
        ? [lumenSeedBox.x1, lumenSeedBox.y1, lumenSeedBox.x2, lumenSeedBox.y2]
          .map((value) => Number(value).toFixed(1))
          .join(',')
        : 'nolumen';
      const frameKey = [
        patient.id,
        target,
        mediaMode,
        videoUrl,
        mediaMode === 'video' ? liveVideoTime.toFixed(3) : 'image',
        lumenKey,
      ].join(':');
      const sessionState = nnInteractiveSessionRef.current;
      if (sessionState.key !== frameKey || !sessionState.id) {
        sessionState.key = frameKey;
        sessionState.id = `gastric_${patient.id}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
        sessionState.initialized = false;
        setNnInteractiveClicks([]);
        setPromptStrokes([]);
        promptStrokesRef.current = [];
      }
      const requestPoints = [
        ...additionalPoints,
        ...(interaction ? [interaction] : []),
      ];
      if (requestPoints.length) {
        setNnInteractiveClicks((previous) => [...previous, ...requestPoints]);
      }
      const scalePoint = (point: number[]) => [
        Number((point[0] * frame.scale).toFixed(2)),
        Number((point[1] * frame.scale).toFixed(2)),
      ];
      const scaleStroke = (stroke: ActiveSamStroke) => ({
        points: stroke.points.map((point) => {
          const [x, y] = scalePoint(point);
          return { x, y, label: stroke.label };
        }),
        label: stroke.label,
        width: Math.max(1, Math.round(stroke.width * frame.scale)),
      });
      const scaledScribbles = scribbles
        .filter((stroke) => stroke.kind === 'scribble')
        .map(scaleStroke);
      const scaledLassos = scribbles
        .filter((stroke) => stroke.kind === 'lasso')
        .map(scaleStroke);
      const response = await fetch('/api/agent/nninteractive', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionState.id,
          case_id: patient.patient_id,
          frame_time: liveVideoTime,
          frame_png_b64: frame.b64,
          image_width: frame.width,
          image_height: frame.height,
          reset_session: !sessionState.initialized,
          initial_mask_polygon: !sessionState.initialized
            ? initialPolygon.map(scalePoint)
            : [],
          points: requestPoints.map((point) => ({
            x: Number((point.x * frame.scale).toFixed(2)),
            y: Number((point.y * frame.scale).toFixed(2)),
            label: point.label,
          })),
          scribbles: scaledScribbles,
          lassos: scaledLassos,
        }),
        signal: abortController.signal,
      });
      const data = await response.json() as {
        ok?: boolean;
        available?: boolean;
        error?: string;
        result?: {
          mask_polygon?: number[][];
          backend_id?: string;
          model?: string;
          prompt_meta?: Record<string, unknown>;
          error?: string;
        };
      };
      if (requestId !== nnInteractiveRequestRef.current || abortController.signal.aborted) return;
      if (!response.ok || !data.ok || !data.result?.mask_polygon?.length) {
        throw new Error(data.error || data.result?.error || 'Boundary assistance returned no valid mask');
      }
      const rawPolygon = data.result.mask_polygon.map((point) => [
        point[0] / frame.scale,
        point[1] / frame.scale,
      ]);
      if (rawPolygon.length < 3) {
        throw new Error('Boundary assistance returned an invalid contour');
      }
      const nextPolygon = prepareEditableContour(
        rawPolygon,
        target === 'lumen' ? LUMEN_CONTOUR_MAX_POINTS : LESION_CONTOUR_MAX_POINTS,
      );
      maskAuditRef.current('model_trace', {
        trace_id: traceId,
        operation: 'nninteractive_refine',
        model: data.result.model || 'nninteractive',
        backend_id: data.result.backend_id,
        source: 'nninteractive',
        target,
        outcome: 'success',
        frame_time_sec: liveVideoTime,
        input: {
          reset_session: !sessionState.initialized,
          point_count: requestPoints.length,
          positive_points: requestPoints.filter((point) => point.label !== 'negative').length,
          negative_points: requestPoints.filter((point) => point.label === 'negative').length,
          scribble_count: scaledScribbles.length,
          lasso_count: scaledLassos.length,
          session_id: sessionState.id,
        },
        output: {
          polygon_points: nextPolygon.length,
          prompt_meta: data.result.prompt_meta,
        },
        duration_ms: Math.round(performance.now() - traceStartedAt),
      });
      sessionState.initialized = true;
      setNnInteractiveAvailable(true);
      if (target === 'lumen') {
        lumenPolygonRef.current = nextPolygon;
        setLumenPolygon(nextPolygon);
        setLumenEditMode(false);
        setLumenResultMeta((previous) => ({
          ...previous,
          source: 'nninteractive',
          sam_backend_id: 'nninteractive_remote_v1',
          error: undefined,
        }));
      } else {
        contourInteractionRef.current = true;
        generatedLesionRef.current = clonePoly(nextPolygon);
        pointsRef.current = nextPolygon;
        setPoints(nextPolygon);
      }
      if (simpleVideoMode && mediaMode === 'video') {
        recordVideoFrameOverride(
          target === 'lesion' ? nextPolygon : getCurrentTrackedPolygon(),
          'accepted',
        );
        setTrackingPrepared(false);
        setTrackOnPlay(false);
      }
      onImagingAssist?.({
        layerResult,
        lesionPolygon: target === 'lesion' ? nextPolygon : pointsRef.current,
        wallPolygon: wallPointsRef.current,
        frameSize: { width: frame.fullWidth, height: frame.fullHeight },
        lumenBBox: lumenBoxRef.current,
        lumenPolygon: lumenPolygonRef.current.length >= 3 ? lumenPolygonRef.current : undefined,
      });
      setMessage(
        zh
          ? `边界辅助已精修${target === 'lumen' ? '胃腔' : '病灶'}边界（${nextPolygon.length} 点），可继续用正/负点修正`
          : `Boundary assistance refined the ${target === 'lumen' ? 'lumen' : 'lesion'} contour (${nextPolygon.length} points); add positive or negative points to refine further`,
      );
    } catch (error) {
      const aborted = error instanceof DOMException && error.name === 'AbortError';
      maskAuditRef.current('model_trace', {
        trace_id: traceId,
        operation: 'nninteractive_refine',
        model: 'nninteractive',
        source: 'nninteractive',
        target,
        outcome: aborted ? 'aborted' : 'error',
        frame_time_sec: Number((videoRef.current?.currentTime ?? videoTime).toFixed(3)),
        input: {
          point_count: additionalPoints.length + (interaction ? 1 : 0),
          scribble_count: scribbles.filter((stroke) => stroke.kind === 'scribble').length,
          lasso_count: scribbles.filter((stroke) => stroke.kind === 'lasso').length,
          session_id: nnInteractiveSessionRef.current.id || undefined,
        },
        error: aborted
          ? undefined
          : error instanceof Error ? error.message.slice(0, 240) : 'Boundary assistance failed',
        duration_ms: Math.round(performance.now() - traceStartedAt),
      });
      if (requestId !== nnInteractiveRequestRef.current || abortController.signal.aborted) return;
      if (aborted) return;
      nnInteractiveSessionRef.current.initialized = false;
      const detail = error instanceof Error ? error.message : '';
      const serviceUnavailable = detail === 'fetch failed'
        || detail.includes('bridge')
        || detail.includes('NN_INTERACTIVE_SERVER_URL')
        || detail.toLowerCase().includes('nninteractive');
      if (serviceUnavailable) {
        setNnInteractiveAvailable(false);
      }
      setMessage(
        serviceUnavailable
          ? (target === 'lesion'
            ? (zh
              ? 'nnInteractive 边界辅助服务未连接，未切换到 SAM3.1；请启动服务后重试'
              : 'nnInteractive is unavailable; staying out of SAM3.1. Start the service and retry')
            : (zh
              ? '胃腔 nnInteractive 辅助服务未启动，请先启动辅助服务'
              : 'Lumen nnInteractive assistance is unavailable; start the service first'))
          : (detail || (zh ? '边界辅助失败' : 'Boundary assistance failed')),
      );
    } finally {
      if (nnInteractiveAbortRef.current === abortController) {
        nnInteractiveAbortRef.current = null;
      }
      if (requestId === nnInteractiveRequestRef.current) setNnInteractiveBusy(false);
    }
  }, [
    freezeCurrentFrame,
    getCurrentTrackedPolygon,
    layerResult,
    mediaMode,
    nnInteractiveAvailable,
    nnInteractiveBusy,
    onImagingAssist,
    patient,
    recordVideoFrameOverride,
    simpleVideoMode,
    videoTime,
    videoUrl,
    zh,
  ]);

  const activateNnInteractive = useCallback((target: 'lesion' | 'lumen') => {
    const hasMask = target === 'lesion'
      ? getCurrentTrackedPolygon().length >= 3
      : lumenPolygonRef.current.length >= 3 || Boolean(lumenBoxRef.current);
    if (!hasMask) {
      setMessage(
        target === 'lesion'
          ? (zh ? '请先框选病灶，再启动病灶边界辅助' : 'Create a lesion mask before boundary assistance')
          : (zh ? '请先检测或分割胃腔，再启动胃腔边界辅助' : 'Detect or segment the lumen before boundary assistance'),
      );
      return;
    }
    invalidateNnInteractiveSession({ abort: true });
    setMode('sam');
    setSimplePromptMode('point');
    setSimpleEditMode(false);
    setLumenEditMode(false);
    setNnInteractiveTarget(target);
    setNnInteractiveClicks([]);
    setNnInteractiveMode(true);
    if (nnInteractiveAvailable !== true) {
      setNnInteractiveMode(false);
      setMessage(
        target === 'lesion'
          ? (zh
            ? 'nnInteractive 未连接，已切换到本地 SAM 病灶正/负点模式；点击病灶外缘会自动作为负点'
            : 'nnInteractive is unavailable; using local SAM lesion prompts. Click outside the lesion to add a negative point')
          : (zh
            ? '胃腔辅助服务未连接，已切换到本地 SAM 胃腔正/负点模式'
            : 'Lumen assistance is unavailable; using local SAM lumen prompts'),
      );
      void refreshNnInteractiveStatus();
      return;
    }
    setMessage(
      target === 'lesion'
        ? (zh ? '病灶边界辅助已开启，请点击病灶边界添加正点，Shift 点击添加负点' : 'Lesion boundary assistance is ready; click positive points, Shift-click negative points')
        : (zh ? '胃腔边界辅助已开启，请点击胃腔边界添加正点，Shift 点击添加负点' : 'Lumen boundary assistance is ready; click positive points, Shift-click negative points'),
    );
  }, [
    getCurrentTrackedPolygon,
    invalidateNnInteractiveSession,
    nnInteractiveAvailable,
    refreshNnInteractiveStatus,
    zh,
  ]);

  const buildLumenOverride = useCallback((): LumenOverride | null => {
    const currentLumenBox = lumenBoxRef.current;
    const currentLumenPolygon = lumenPolygonRef.current;
    const resolvedLumenBox = currentLumenBox || (currentLumenPolygon.length >= 3 ? bboxFromPolygon(currentLumenPolygon) : null);
    if (!patient || !resolvedLumenBox) return null;
    const video = videoRef.current;
    const img = imgRef.current;
    const width =
      mediaMode === 'video' && video?.videoWidth
        ? video.videoWidth
        : (img?.naturalWidth || lumenOverride?.imageWidth || 0);
    const height =
      mediaMode === 'video' && video?.videoHeight
        ? video.videoHeight
        : (img?.naturalHeight || lumenOverride?.imageHeight || 0);
    if (!width || !height) return null;
    return {
      patientId: patient.patient_id,
      frameId: patient.id,
      imageWidth: width,
      imageHeight: height,
      lumen_bbox: normalizeLumenBBox(resolvedLumenBox),
      lumen_polygon: currentLumenPolygon.length >= 3
        ? currentLumenPolygon.map((p) => [Math.round(p[0] * 10) / 10, Math.round(p[1] * 10) / 10])
        : undefined,
      lumen_confidence: lumenConfidence ?? undefined,
      lumen_mask_type: currentLumenPolygon.length >= 3
        ? (lumenResultMeta?.source === 'nninteractive' ? 'nninteractive_polygon' : 'sam31_polygon')
        : 'bbox_proxy',
      source: lumenResultMeta?.source || (currentLumenPolygon.length >= 3 ? 'yolo_then_sam31' : 'yolo'),
      detector_backend_id: lumenResultMeta?.detector_backend_id,
      sam_backend_id: lumenResultMeta?.sam_backend_id,
      sam_score: lumenResultMeta?.sam_score,
      video_time_sec: mediaMode === 'video' ? Number(videoTime.toFixed(3)) : undefined,
      video_url: mediaMode === 'video' ? videoUrl || undefined : undefined,
      updated_at: new Date().toISOString(),
    };
  }, [
    lumenConfidence,
    lumenOverride?.imageHeight,
    lumenOverride?.imageWidth,
    lumenResultMeta,
    mediaMode,
    patient,
    videoTime,
    videoUrl,
  ]);

  const detectLumen = useCallback(async (): Promise<LumenBBox | null> => {
    if (!patient || lumenBusy) return null;
    const traceId = `lumen_detect_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    const traceStartedAt = performance.now();
    setLumenBusy(true);
    setLumenResultMeta(null);
    setMessage(zh ? '胃腔 YOLO 检测中…' : 'Detecting gastric lumen…');
    try {
      const frame = await videoOrImageToSamFrame(
        videoRef.current,
        imgRef.current,
        mediaMode === 'video',
        1024,
      );
      const scale = frame.scale || 1;
      const response = await fetch('/api/agent/lumen-detection', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          frame_png_b64: frame.b64,
          image_width: frame.width,
          image_height: frame.height,
        }),
      });
      const data = await readJsonPayload<{
        ok?: boolean;
        available?: boolean;
        lumen_detected?: boolean;
        lumen_bbox?: LumenBBox;
        lumen_confidence?: number;
        backend_id?: string;
        error?: string;
      }>(response, 'Lumen detection endpoint');
      if (!response.ok || !data.ok) {
        throw new Error(data.error || 'Lumen detection failed');
      }
      if (!data.lumen_detected || !data.lumen_bbox) {
        maskAuditRef.current('model_trace', {
          trace_id: traceId,
          operation: 'lumen_detection',
          model: 'lumen_detector',
          source: 'lumen_detection_endpoint',
          outcome: 'no_detection',
          frame_time_sec: Number((videoRef.current?.currentTime ?? videoTime).toFixed(3)),
          output: { backend_id: data.backend_id },
          duration_ms: Math.round(performance.now() - traceStartedAt),
        });
        setLumenBox(null);
        setLumenPolygon([]);
        setLumenConfidence(null);
        setLumenResultMeta({ error: data.error || 'no lumen detected', detector_backend_id: data.backend_id });
        setMessage(zh ? '未检测到胃腔，可手动框选后分割' : 'No lumen detected; draw a box then segment');
        return null;
      }
      // Keep the detector box as-is. Auto-expand made the lumen ROI jump toward the lesion.
      const box = normalizeLumenBBox({
        x1: data.lumen_bbox.x1 / scale,
        y1: data.lumen_bbox.y1 / scale,
        x2: data.lumen_bbox.x2 / scale,
        y2: data.lumen_bbox.y2 / scale,
      });
      lumenBoxRef.current = box;
      lumenPolygonRef.current = [];
      setLumenBox(box);
      setLumenPolygon([]);
      setLumenConfidence(typeof data.lumen_confidence === 'number' ? data.lumen_confidence : null);
      setNnInteractiveMode(false);
      setLumenResultMeta({
        detector_backend_id: data.backend_id,
        source: 'yolo',
      });
      maskAuditRef.current('model_trace', {
        trace_id: traceId,
        operation: 'lumen_detection',
        model: 'lumen_detector',
        source: 'lumen_detection_endpoint',
        outcome: 'success',
        frame_time_sec: Number((videoRef.current?.currentTime ?? videoTime).toFixed(3)),
        output: {
          backend_id: data.backend_id,
          confidence: data.lumen_confidence,
          bbox_present: true,
          expanded_for_wall_and_mass: false,
        },
        duration_ms: Math.round(performance.now() - traceStartedAt),
      });
      freezeCurrentFrame();
      // Stay in box-edit so the doctor can keep adjusting after detection.
      enterLumenBoxEdit(
        zh
          ? `已检出胃腔框（conf ${(data.lumen_confidence ?? 0).toFixed(2)}）。请手动拖调；勿依赖自动外扩。`
          : `Lumen box detected (conf ${(data.lumen_confidence ?? 0).toFixed(2)}). Drag to adjust; no auto-expand.`,
      );
      return box;
    } catch (error) {
      const messageText = error instanceof Error ? error.message : 'Lumen detection failed';
      maskAuditRef.current('model_trace', {
        trace_id: traceId,
        operation: 'lumen_detection',
        model: 'lumen_detector',
        source: 'lumen_detection_endpoint',
        outcome: 'error',
        frame_time_sec: Number((videoRef.current?.currentTime ?? videoTime).toFixed(3)),
        error: messageText.slice(0, 240),
        duration_ms: Math.round(performance.now() - traceStartedAt),
      });
      setLumenResultMeta({ error: messageText });
      setMessage(messageText);
      return null;
    } finally {
      setLumenBusy(false);
    }
  }, [enterLumenBoxEdit, freezeCurrentFrame, lumenBusy, mediaMode, patient, videoTime, zh]);

  const segmentLumenWithSam31 = useCallback(async (): Promise<boolean> => {
    const currentLumenBox = lumenBoxRef.current;
    if (!patient || !currentLumenBox || lumenSamBusy) return false;
    const traceId = `lumen_segment_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    const traceStartedAt = performance.now();
    setLumenSamBusy(true);
    setMessage(zh ? '胃腔分割中…' : 'Segmenting lumen…');
    try {
      const frame = await videoOrImageToSamFrame(
        videoRef.current,
        imgRef.current,
        mediaMode === 'video',
        1024,
      );
      const scale = frame.scale || 1;
      const box = normalizeLumenBBox(currentLumenBox);
      // Lumen uses base SAM3.1 (no gastric lesion LoRA) and box-only prompts.
      // Lesion negative clicks biased the contour away from true lumen.
      let response: Response;
      try {
        response = await fetch('/api/agent/sam-interactive', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            case_id: patient.patient_id,
            frame_png_b64: frame.b64,
            image_width: frame.width,
            image_height: frame.height,
            model: 'sam31',
            text_prompt: 'gastric lumen cavity',
            threshold: 0.2,
            use_lora: false,
            box: {
              x1: box.x1 * scale,
              y1: box.y1 * scale,
              x2: box.x2 * scale,
              y2: box.y2 * scale,
            },
            clicks: [],
          }),
        });
      } catch (networkError) {
        const detail = networkError instanceof Error ? networkError.message : 'network error';
        throw new Error(
          zh
            ? `胃腔分割请求失败（${detail}）。请确认 SAM 服务可用后重试`
            : `Lumen segment request failed (${detail}). Check SAM service and retry`,
        );
      }
      let data: {
        ok?: boolean;
        error?: string;
        result?: {
          ok?: boolean;
          mask_polygon?: number[][];
          backend_id?: string;
          fallback_backend?: string;
          prompt_meta?: { sam_score?: number };
          error?: string;
        };
      };
      try {
        data = await response.json();
      } catch {
        throw new Error(
          zh
            ? `胃腔分割接口异常（HTTP ${response.status}）`
            : `Lumen segment API error (HTTP ${response.status})`,
        );
      }
      const result = data.result;
      if (!response.ok || !data.ok || !result?.mask_polygon || result.mask_polygon.length < 3) {
        throw new Error(data.error || result?.error || 'SAM3.1 returned no lumen polygon');
      }
      const maxCoord = Math.max(...result.mask_polygon.flatMap((point) => point));
      const polyFull = maxCoord <= 1.5
        ? result.mask_polygon.map((point) => [point[0] * frame.fullWidth, point[1] * frame.fullHeight])
        : result.mask_polygon.map((point) => [point[0] / scale, point[1] / scale]);
      let poly = prepareEditableContour(polyFull, LUMEN_CONTOUR_MAX_POINTS);
      // Guard against a mask that drifts far outside the doctor-confirmed lumen box.
      const outBox = bboxFromPolygon(poly);
      if (outBox) {
        const boxW = Math.max(24, box.x2 - box.x1);
        const boxH = Math.max(24, box.y2 - box.y1);
        const drift = outBox.x2 < box.x1 - boxW * 0.5
          || outBox.x1 > box.x2 + boxW * 0.5
          || outBox.y2 < box.y1 - boxH * 0.5
          || outBox.y1 > box.y2 + boxH * 0.5
          || (outBox.x2 - outBox.x1) > boxW * 4
          || (outBox.y2 - outBox.y1) > boxH * 4;
        if (drift) {
          const cx = (box.x1 + box.x2) / 2;
          const cy = (box.y1 + box.y2) / 2;
          const hw = boxW * 1.6;
          const hh = boxH * 1.6;
          poly = poly.map(([px, py]) => [
            Math.min(cx + hw, Math.max(cx - hw, px)),
            Math.min(cy + hh, Math.max(cy - hh, py)),
          ]);
        }
      }
      const usedSam2Fallback = result.fallback_backend === 'sam2_interactive';
      maskAuditRef.current('model_trace', {
        trace_id: traceId,
        operation: 'lumen_segmentation',
        model: usedSam2Fallback ? 'sam2_interactive_fallback' : 'sam31',
        backend_id: result.backend_id,
        source: 'lumen_segmentation_endpoint',
        outcome: 'success',
        frame_time_sec: Number((videoRef.current?.currentTime ?? videoTime).toFixed(3)),
        input: {
          box_prompt: true,
          use_lora: false,
          negative_lesion_guard: false,
        },
        output: {
          polygon_points: poly.length,
          score: result.prompt_meta?.sam_score,
          fallback_backend: result.fallback_backend,
        },
        duration_ms: Math.round(performance.now() - traceStartedAt),
      });
      setLumenPolygon(poly);
      lumenPolygonRef.current = poly;
      // Mask exists → leave box-edit and clear the prompt box so the canvas shows
      // the true lumen contour only (no lingering rectangle around the mask).
      setSimplePromptMode('box');
      setNnInteractiveMode(false);
      setLumenEditMode(false);
      setLumenResultMeta((prev) => {
        const source = usedSam2Fallback
          ? 'sam2_fallback'
          : (prev?.source === 'manual' || prev?.source === 'yolo_then_manual'
            ? 'yolo_then_sam31'
            : (prev?.source === 'yolo' ? 'yolo_then_sam31' : 'sam31'));
        return {
          ...prev,
          sam_backend_id: result.backend_id || 'sam3.1_multiplex_static',
          sam_score: result.prompt_meta?.sam_score,
          source,
          error: undefined,
        };
      });
      onImagingAssist?.({
        layerResult,
        lesionPolygon: pointsRef.current,
        wallPolygon: wallPointsRef.current,
        frameSize: { width: frame.fullWidth, height: frame.fullHeight },
        lumenBBox: box,
        lumenPolygon: poly,
      });
      freezeCurrentFrame();
      setMessage(
        zh
          ? `已生成胃腔轮廓（${poly.length} 点，基座 SAM3.1）。仍可继续拖调胃腔框；满意后点顶中「辅助意见」。`
          : `Lumen contour ready (${poly.length} points, base SAM3.1). Keep adjusting the box if needed, then tap Assist.`,
      );
      return true;
    } catch (error) {
      const messageText = error instanceof Error ? error.message : (zh ? '胃腔分割失败' : 'Lumen segmentation failed');
      maskAuditRef.current('model_trace', {
        trace_id: traceId,
        operation: 'lumen_segmentation',
        model: 'sam31',
        source: 'lumen_segmentation_endpoint',
        outcome: 'error',
        frame_time_sec: Number((videoRef.current?.currentTime ?? videoTime).toFixed(3)),
        input: { box_prompt: true },
        error: messageText.slice(0, 240),
        duration_ms: Math.round(performance.now() - traceStartedAt),
      });
      setLumenResultMeta((prev) => ({ ...prev, error: messageText }));
      setMessage(messageText);
      return false;
    } finally {
      setLumenSamBusy(false);
    }
  }, [freezeCurrentFrame, layerResult, lumenSamBusy, mediaMode, onImagingAssist, patient, videoTime, zh]);

  const handleSaveLumen = useCallback(async (silent = false): Promise<boolean> => {
    const next = buildLumenOverride();
    if (!next) {
      if (!silent) setMessage(zh ? '请先检测或框选胃腔' : 'Detect or draw a lumen box first');
      return false;
    }
    setLumenSaving(true);
    try {
      const res = await fetch('/api/patients/lumen-overrides', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ override: next }),
      });
      const data = await res.json() as { override?: LumenOverride; error?: string };
      if (!res.ok) throw new Error(data.error || 'Save lumen failed');
      const saved = data.override || next;
      onLumenOverrideChange?.(saved);
      // Do not exit lumen box edit on save — doctors need continuous adjustment.
      // Only an explicit "完成调整" toggle leaves edit mode.
      if (pointsRef.current.length >= 3) {
        void persistOverrideRef.current(
          silent ? 'lumen_auto_save' : 'lumen_manual_save',
          { silent: true },
        );
      }
      maskAuditRef.current('mask_saved', {
        action: silent ? 'lumen_auto_save' : 'lumen_manual_save',
        success: true,
        lumen_points: saved.lumen_polygon?.length || 0,
        lumen_box_present: Boolean(saved.lumen_bbox),
        lumen_source: saved.source,
        detector_backend_id: saved.detector_backend_id,
        sam_backend_id: saved.sam_backend_id,
      });
      if (!silent) setMessage(zh ? '胃腔结果已保存，分析将优先使用此框' : 'Lumen override saved for Agent geometry');
      return true;
    } catch (error) {
      maskAuditRef.current('mask_saved', {
        action: silent ? 'lumen_auto_save' : 'lumen_manual_save',
        success: false,
        error: error instanceof Error ? error.message.slice(0, 240) : 'Save lumen failed',
      });
      setMessage(error instanceof Error ? error.message : 'Save lumen failed');
      return false;
    } finally {
      setLumenSaving(false);
    }
  }, [buildLumenOverride, onLumenOverrideChange, zh]);

  const recordDoctorWorkflowStep = useCallback((
    stepId: string,
    action: string,
    status: 'started' | 'completed' | 'error' | 'skipped',
    details: { input?: Record<string, unknown>; output?: Record<string, unknown>; error?: string } = {},
  ) => {
    const traceId = `doctor_workflow_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    maskAuditRef.current('model_trace', {
      trace_id: traceId,
      operation: `doctor_workflow:${stepId}`,
      model: 'doctor_workflow_agent',
      source: 'doctor_workflow',
      outcome: status,
      frame_time_sec: Number((videoRef.current?.currentTime ?? videoTime).toFixed(3)),
      ...details,
    });
    setWorkflowStepLabel(action);
  }, [videoTime]);

  const runDoctorWorkflow = useCallback(async () => {
    if (!simpleVideoMode || mediaMode !== 'video' || workflowBusy) return;
    setWorkflowBusy(true);
    recordDoctorWorkflowStep('workflow_start', '开始医生式全流程', 'started');
    try {
      let detectedLumenBox = lumenBoxRef.current;
      if (!detectedLumenBox) {
        recordDoctorWorkflowStep('lumen_detection', '自动检测胃腔框', 'started');
        detectedLumenBox = await detectLumen();
        if (!detectedLumenBox) throw new Error('自动检测胃腔失败，请手动框选胃腔');
        recordDoctorWorkflowStep('lumen_detection', '自动检测胃腔框', 'completed', {
          output: { bbox: detectedLumenBox, source: 'lumen_detector' },
        });
      } else {
        recordDoctorWorkflowStep('lumen_reuse', '复用已有胃腔位置', 'skipped', {
          output: { bbox: detectedLumenBox, reason: 'existing_lumen_prompt' },
        });
      }

      let lesion = pointsRef.current;
      if (lesion.length < 3) {
        recordDoctorWorkflowStep('lesion_detection', '自动检测病灶候选', 'started', {
          input: { model: 'dinov3', prompt: 'full_frame_candidate' },
        });
        lesion = await runLesionModelRef.current(null, null, [], 'dinov3') || [];
        if (lesion.length < 3) throw new Error('自动检测病灶失败，请手动框选病灶');
        recordDoctorWorkflowStep('lesion_detection', '自动检测病灶候选', 'completed', {
          output: { polygon_points: lesion.length, source: 'dinov3_candidate' },
        });
      } else {
        recordDoctorWorkflowStep('lesion_reuse', '复用已有病灶位置', 'skipped', {
          output: { polygon_points: lesion.length, reason: 'existing_lesion_prompt' },
        });
      }

      const seedBox = bboxFromPolygon(lesion);
      const seedCenter = polygonCentroid(lesion);
      if (!seedBox || !seedCenter) throw new Error('病灶候选无法生成中心提示');
      recordDoctorWorkflowStep('center_prompt', '在病灶中心添加正点并重新检测', 'started', {
        input: { center: seedCenter, box: seedBox, label: 'positive' },
      });
      const refined = segmentationModel === 'sabm_sam2_guided'
        ? await runSamAtPoint(seedCenter, {
            source: 'sam',
            box: seedBox,
            clicks: [{ x: seedCenter[0], y: seedCenter[1], label: 'positive' }],
            keepEditing: true,
          })
        : await runLesionModelRef.current(
            seedCenter,
            seedBox,
            [{ x: seedCenter[0], y: seedCenter[1], label: 'positive' }],
            segmentationModel,
          );
      if (refined && refined.length >= 3) {
        pointsRef.current = refined;
        setPoints(refined);
        lesion = refined;
      }
      recordDoctorWorkflowStep('center_prompt', '在病灶中心添加正点并重新检测', refined?.length ? 'completed' : 'error', {
        output: { polygon_points: refined?.length || 0 },
        error: refined?.length ? undefined : 'center_refinement_returned_no_mask',
      });
      if (!refined?.length) throw new Error('中心正点精修未返回有效病灶轮廓');

      recordDoctorWorkflowStep('lumen_refinement', '参考病灶位置重新生成胃腔轮廓', 'started');
      const lumenSegmented = await segmentLumenWithSam31();
      if (!lumenSegmented) throw new Error('胃腔轮廓精修未返回有效结果');
      const lumenSaved = await handleSaveLumen(true);
      if (!lumenSaved) throw new Error('胃腔轮廓自动保存失败');
      recordDoctorWorkflowStep('lumen_refinement', '参考病灶位置重新生成胃腔轮廓', 'completed', {
        output: {
          lumen_points: lumenPolygonRef.current.length,
          lesion_guard: true,
        },
      });

      recordDoctorWorkflowStep('video_tracking', '预计算整段视频病灶和胃腔跟踪', 'started');
      await precomputeVideoTracking();
      recordDoctorWorkflowStep('video_tracking', '预计算整段视频病灶和胃腔跟踪', 'completed', {
        output: { tracked_frames: videoFrameOverridesRef.current.length },
      });

      if (onUnifiedAgentRun) {
        recordDoctorWorkflowStep('agent_analysis', '调用 Agent 汇总证据并生成报告', 'started');
        await runUnifiedAgent({ multiFrame: true, assistProfile: 'full' });
        recordDoctorWorkflowStep('agent_analysis', '调用 Agent 汇总证据并生成报告', 'completed', {
          output: { trace_steps: workflowTraceRef.current.length },
        });
      }
      recordDoctorWorkflowStep('workflow_complete', '医生式全流程完成', 'completed', {
        output: { lesion_points: lesion.length, lumen_points: lumenPolygonRef.current.length },
      });
      setMessage(zh ? '医生式全流程完成，报告已进入自动保存和复核流程' : 'Doctor workflow complete; report autosave and review are ready');
    } catch (error) {
      const messageText = error instanceof Error ? error.message : '医生式全流程失败';
      recordDoctorWorkflowStep('workflow_complete', '医生式全流程失败', 'error', { error: messageText });
      setMessage(messageText);
    } finally {
      setWorkflowBusy(false);
    }
  }, [
    detectLumen,
    handleSaveLumen,
    mediaMode,
    onUnifiedAgentRun,
    precomputeVideoTracking,
    recordDoctorWorkflowStep,
    runUnifiedAgent,
    runSamAtPoint,
    segmentLumenWithSam31,
    segmentationModel,
    simpleVideoMode,
    workflowBusy,
    zh,
  ]);

  /** Contour-anchored Assist: ensure lumen polygon + contact geometry before diagnosis. */
  const runContourAnchoredAssist = useCallback(async () => {
    if (!onUnifiedAgentRun || !simpleVideoMode || mediaMode !== 'video' || unifiedAgentBusy || workflowBusy) return;
    const lesion = pointsRef.current;
    if (lesion.length < 3) {
      setMessage(zh ? '请先框选并确认病灶轮廓' : 'Confirm a lesion contour first');
      return;
    }
    let box: LumenBBox | null = lumenBoxRef.current;
    if (!box && lumenPolygonRef.current.length >= 3) {
      const derived = bboxFromPolygon(lumenPolygonRef.current);
      if (derived) {
        box = derived;
        lumenBoxRef.current = derived;
        setLumenBox(derived);
      }
    }
    if (!box) {
      setMessage(zh ? '请先检测或调整胃腔框（须覆盖胃壁与肿块）' : 'Detect or adjust the lumen box first (must cover wall and mass)');
      return;
    }

    const prepared: string[] = [];
    // Do not auto-expand the lumen box toward the lesion; doctors keep the box stable.

    if (lumenPolygonRef.current.length < 3) {
      setTaskProgress({
        label: zh ? '轮廓锚定诊断' : 'Contour-anchored diagnosis',
        step: 1,
        totalSteps: 4,
        detail: zh ? '由胃腔框生成轮廓…' : 'Segmenting lumen contour from box…',
      });
      const ok = await segmentLumenWithSam31();
      if (!ok || lumenPolygonRef.current.length < 3) {
        setTaskProgress(null);
        setMessage(zh ? '胃腔轮廓生成失败：请先手动调整胃腔框后再点辅助意见' : 'Lumen contour failed; adjust the lumen box, then retry Assist');
        return;
      }
      prepared.push('auto_lumen_polygon');
      await handleSaveLumen(true);
      prepared.push('save_lumen');
    }

    contourPrepActionsRef.current = prepared;
    setTaskProgress({
      label: zh ? '轮廓锚定诊断' : 'Contour-anchored diagnosis',
      step: 2,
      totalSteps: 4,
      detail: zh ? '病灶与胃腔轮廓已就绪，开始诊断…' : 'Lesion and lumen contours ready; starting diagnosis…',
    });
    await runUnifiedAgent();
  }, [
    handleSaveLumen,
    mediaMode,
    onUnifiedAgentRun,
    runUnifiedAgent,
    segmentLumenWithSam31,
    simpleVideoMode,
    unifiedAgentBusy,
    workflowBusy,
    zh,
  ]);

  const autoDetectLesion = useCallback(async () => {
    if (!simpleVideoMode || mediaMode !== 'video' || lesionAutoBusy) return;
    setLesionAutoBusy(true);
    recordDoctorWorkflowStep('lesion_detection', '自动检测病灶候选', 'started', {
      input: { model: 'dinov3', prompt: 'full_frame_candidate' },
    });
    try {
      const polygon = await runLesionModelRef.current(null, null, [], 'dinov3');
      if (!polygon || polygon.length < 3) {
        throw new Error('自动检测病灶未返回有效候选轮廓');
      }
      recordDoctorWorkflowStep('lesion_detection', '自动检测病灶候选', 'completed', {
        output: { polygon_points: polygon.length, model: 'dinov3' },
      });
      setMessage(zh ? '已找到病灶候选；可用「编辑轮廓」微调后点顶中辅助意见' : 'Lesion candidate found; refine with Edit, then use top Assist');
    } catch (error) {
      const messageText = error instanceof Error ? error.message : '自动检测病灶失败';
      recordDoctorWorkflowStep('lesion_detection', '自动检测病灶候选', 'error', { error: messageText });
      setMessage(messageText);
    } finally {
      setLesionAutoBusy(false);
    }
  }, [lesionAutoBusy, mediaMode, recordDoctorWorkflowStep, simpleVideoMode, zh]);

  useEffect(() => {
    persistLumenOverrideRef.current = handleSaveLumen;
  }, [handleSaveLumen]);

  const handleClearLumen = useCallback(async () => {
    if (!patient) return;
    setLumenSaving(true);
    try {
      await fetch(
        `/api/patients/lumen-overrides?patientId=${encodeURIComponent(patient.patient_id)}&frameId=${encodeURIComponent(patient.id)}`,
        { method: 'DELETE' },
      );
      setLumenBox(null);
      setLumenPolygon([]);
      setLumenConfidence(null);
      setLumenEditMode(false);
      setLumenResultMeta(null);
      setViewFocusBox(null);
      setViewFocusMode(null);
      onLumenOverrideChange?.(null);
      maskAuditRef.current('mask_event', {
        action: 'lumen_cleared',
        success: true,
        displayed_on_canvas: false,
      });
      setMessage(zh ? '已清除胃腔覆盖' : 'Lumen override cleared');
    } catch (error) {
      maskAuditRef.current('error', {
        operation: 'lumen_clear',
        error: error instanceof Error ? error.message.slice(0, 240) : 'Clear lumen failed',
      });
      setMessage(error instanceof Error ? error.message : 'Clear lumen failed');
    } finally {
      setLumenSaving(false);
    }
  }, [onLumenOverrideChange, patient, zh]);

  const hitLumenHandle = useCallback((imgPt: number[], box: LumenBBox, thr: number): LumenBoxHandle | null => {
    // Larger grab area so continuous box adjustment stays easy on clinical displays.
    const cornerThr = Math.max(thr * 2.8, 14);
    const corners: Array<[LumenBoxHandle, number, number]> = [
      ['nw', box.x1, box.y1],
      ['ne', box.x2, box.y1],
      ['sw', box.x1, box.y2],
      ['se', box.x2, box.y2],
    ];
    let best: LumenBoxHandle | null = null;
    let bestD = cornerThr * cornerThr;
    for (const [handle, x, y] of corners) {
      const d = dist2([x, y], imgPt);
      if (d <= bestD) {
        bestD = d;
        best = handle;
      }
    }
    if (best) return best;
    const pad = Math.max(thr * 0.5, 4);
    if (
      imgPt[0] >= box.x1 - pad
      && imgPt[0] <= box.x2 + pad
      && imgPt[1] >= box.y1 - pad
      && imgPt[1] <= box.y2 + pad
    ) {
      return 'move';
    }
    return null;
  }, []);

  const resolvePointPromptLabel = useCallback((
    imgPt: number[],
    requested: ActiveSamPromptLabel,
    target: 'lesion' | 'lumen' = 'lesion',
  ): ActiveSamPromptLabel => {
    if (requested === 'negative') return 'negative';
    const polygon = target === 'lumen'
      ? lumenPolygonRef.current
      : getCurrentTrackedPolygon();
    if (polygon.length >= 3) {
      return polygonHit(imgPt, polygon, Math.max(8, hitThreshold() * 1.5))
        ? 'positive'
        : 'negative';
    }
    if (target === 'lumen' && lumenBoxRef.current) {
      const box = lumenBoxRef.current;
      return imgPt[0] >= box.x1
        && imgPt[0] <= box.x2
        && imgPt[1] >= box.y1
        && imgPt[1] <= box.y2
        ? 'positive'
        : 'negative';
    }
    return requested;
  }, [getCurrentTrackedPolygon, hitThreshold]);

  const runSamClick = useCallback(async (
    imgPt: number[],
    label: 'positive' | 'negative' = 'positive',
    box?: { x1: number; y1: number; x2: number; y2: number } | null,
  ) => {
    freezeCurrentFrame();
    let next = samClicksRef.current;
    const alreadyPrompted = next.some((point) => (
      Math.abs(point.x - imgPt[0]) < 1
      && Math.abs(point.y - imgPt[1]) < 1
      && point.label === label
    ));
    if (!alreadyPrompted) {
      next = [...samClicksRef.current, { x: imgPt[0], y: imgPt[1], label }];
      samClicksRef.current = next;
      setSamClicks(next);
    }
    if (simpleVideoMode && mediaMode === 'video') {
      if (segmentationModel === 'sabm_sam2_guided') {
        const predicted = await runSamAtPoint(imgPt, {
          keepEditing: true,
          stayInSam: true,
          source: 'sam',
          clicks: next.length ? next : undefined,
          box: box || undefined,
        });
        const video = videoRef.current;
        if (predicted && video?.videoWidth && video.videoHeight && patient) {
          const assistReport = buildModelAssistReport(
            patient,
            predicted,
            video.videoWidth,
            video.videoHeight,
            segmentationModel,
            undefined,
            zh,
          );
          setSamReport(assistReport);
          onSystemReport?.(assistReport);
          onImagingAssist?.({
            layerResult,
            lesionPolygon: predicted,
            wallPolygon: wallPointsRef.current,
            frameSize: { width: video.videoWidth, height: video.videoHeight },
            lumenBBox: lumenBoxRef.current,
            lumenPolygon: lumenPolygonRef.current.length >= 3 ? lumenPolygonRef.current : undefined,
          });
        }
        return predicted;
      }
      return runLesionModel(imgPt, box || null, next);
    }
    return runSamAtPoint(imgPt, {
      keepEditing: true,
      stayInSam: true,
      source: 'sam',
      clicks: next.length ? next : undefined,
      box: box || undefined,
    });
  }, [freezeCurrentFrame, layerResult, mediaMode, onImagingAssist, onSystemReport, patient, runLesionModel, runSamAtPoint, segmentationModel, simpleVideoMode]);

  const activateActiveSamPrompt = useCallback((
    promptMode: ActiveSamPromptMode,
    target: 'lesion' | 'lumen' = 'lesion',
  ) => {
    const hasMask = target === 'lesion'
      ? getCurrentTrackedPolygon().length >= 3
      : lumenPolygonRef.current.length >= 3 || Boolean(lumenBoxRef.current);
    if (!hasMask) {
      setMessage(
        target === 'lesion'
          ? (zh ? '请先生成病灶轮廓，再启动 nnInteractive 交互' : 'Create a lesion mask before starting nnInteractive')
          : (zh ? '请先生成胃腔轮廓，再启动 nnInteractive 交互' : 'Create a lumen mask before starting nnInteractive'),
      );
      return;
    }
    if (promptMode !== 'point' && nnInteractiveAvailable !== true) {
      setSimplePromptMode('point');
      setNnInteractiveMode(false);
      setMessage(
        zh
          ? '自由涂鸦和套索需要边界辅助服务，当前未切换到 SAM 点击模式'
          : 'Scribble and lasso require boundary assistance; SAM click mode was not activated',
      );
      void refreshNnInteractiveStatus();
      return;
    }
    invalidateNnInteractiveSession({ abort: true });
    setMode('sam');
    setSimplePromptMode(promptMode);
    setSimpleEditMode(false);
    setLumenEditMode(false);
    setNnInteractiveTarget(target);
    setTrackOnPlay(false);
    if (nnInteractiveAvailable !== true) {
      setNnInteractiveMode(false);
      setMessage(
        target === 'lesion'
          ? (zh
            ? 'nnInteractive 未连接，已使用本地 SAM 提示；正点保留，负点排除'
            : 'nnInteractive is unavailable; using local SAM prompts. Positive keeps, negative excludes')
          : (zh
            ? '胃腔辅助服务未连接，已使用本地 SAM 提示；正点保留，负点排除'
            : 'Lumen assistance is unavailable; using local SAM prompts. Positive keeps, negative excludes'),
      );
      void refreshNnInteractiveStatus();
      return;
    }
    setNnInteractiveMode(true);
    setMessage(
      target === 'lesion'
        ? (zh
          ? `nnInteractive 病灶${promptModeText(promptMode, true)}已开启，${promptMode === 'point' ? '点击添加提示' : '拖动提交提示'}`
          : `nnInteractive lesion ${promptModeText(promptMode, false)} is ready; ${promptMode === 'point' ? 'click to add prompts' : 'drag to submit a prompt'}`)
        : (zh
          ? `nnInteractive 胃腔${promptModeText(promptMode, true)}已开启，${promptMode === 'point' ? '点击添加提示' : '拖动提交提示'}`
          : `nnInteractive lumen ${promptModeText(promptMode, false)} is ready; ${promptMode === 'point' ? 'click to add prompts' : 'drag to submit a prompt'}`),
    );
  }, [getCurrentTrackedPolygon, invalidateNnInteractiveSession, nnInteractiveAvailable, refreshNnInteractiveStatus, zh]);

  const applyActiveSamStroke = useCallback(async (stroke: ActiveSamStroke) => {
    const prepared = prepareSubmitPromptStroke(
      stroke.points,
      stroke.kind === 'lasso' ? 'lasso' : 'scribble',
      {
        maxPoints: stroke.kind === 'lasso' ? 64 : 48,
        minPoints: 2,
        minLengthPx: 4,
        minAreaPx2: 64,
      },
    );
    if (!prepared.ok) {
      setMessage(
        prepared.reason === 'lasso_area_too_small'
          ? (zh ? '套索面积过小，请扩大闭合区域后重试' : 'Lasso area is too small; enlarge the closed region and retry')
          : prepared.reason === 'too_short'
            ? (zh ? '笔画过短，请继续拖动画出有效提示' : 'Stroke is too short; keep dragging to form a usable prompt')
            : (zh ? '涂鸦或套索至少需要两个点' : 'A scribble or lasso needs at least two points'),
      );
      return;
    }
    const submitStroke: ActiveSamStroke = {
      ...stroke,
      points: prepared.points,
    };
    const target = stroke.target || (nnInteractiveMode ? nnInteractiveTarget : 'lesion');
    if (!nnInteractiveMode || nnInteractiveAvailable !== true) {
      setMessage(
        zh
          ? '涂鸦和套索需要边界辅助服务，未转换为 SAM 默认点击'
          : 'Scribble and lasso require boundary assistance and will not fall back to SAM clicks',
      );
      return;
    }

    setPromptStrokes((previous) => [...previous, submitStroke]);
    promptStrokesRef.current = [...promptStrokesRef.current, submitStroke];
    await refineWithNnInteractive(target, undefined, [submitStroke]);
  }, [
    nnInteractiveAvailable,
    nnInteractiveMode,
    nnInteractiveTarget,
    refineWithNnInteractive,
    zh,
  ]);

  const beginActiveSamStroke = useCallback((
    imgPt: number[],
    event: React.PointerEvent<HTMLCanvasElement>,
  ): boolean => {
    if (simpleVideoMode) return false;
    if (simplePromptMode !== 'scribble' && simplePromptMode !== 'lasso') return false;
    if (nnInteractiveAvailable !== true) {
      event.preventDefault();
      event.stopPropagation();
      setMessage(
        zh
          ? '涂鸦和套索暂不可用，请先启动边界辅助服务'
          : 'Scribble and lasso are unavailable until boundary assistance is running',
      );
      return true;
    }
    if (samBusy || nnInteractiveBusy || segmentationBusy) return true;
    const label = event.shiftKey ? oppositePromptLabel(activeSamPromptLabel) : activeSamPromptLabel;
    const stroke: ActiveSamStroke = {
      points: [imgPt],
      label,
      kind: simplePromptMode,
      width: simplePromptMode === 'lasso' ? 3 : 10,
      target: nnInteractiveMode ? nnInteractiveTarget : 'lesion',
    };
    activePromptStrokeRef.current = stroke;
    setActivePromptStroke(stroke);
    event.preventDefault();
    event.stopPropagation();
    capturePointerSafely(event.currentTarget, event.pointerId);
    freezeCurrentFrame();
    return true;
  }, [
    activeSamPromptLabel,
    freezeCurrentFrame,
    nnInteractiveBusy,
    nnInteractiveMode,
    nnInteractiveAvailable,
    nnInteractiveTarget,
    samBusy,
    segmentationBusy,
    simplePromptMode,
    simpleVideoMode,
    zh,
  ]);

  const onPointerDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const imgPt = canvasToImage(e);
    if (!imgPt) return;

    if (lumenEditMode) {
      if (samBusy || segmentationBusy || lumenBusy || lumenSamBusy) return;
      const activeBox = lumenBoxRef.current || lumenBox;
      if (activeBox) {
        const handle = hitLumenHandle(imgPt, activeBox, hitThreshold());
        if (handle) {
          e.preventDefault();
          capturePointerSafely(e.currentTarget, e.pointerId);
          freezeCurrentFrame();
          lumenBoxDragRef.current = {
            handle,
            start: normalizeLumenBBox(activeBox),
            origin: imgPt,
          };
          return;
        }
      }
      // Outside the current box: redraw a new lumen box and stay in edit mode.
      e.preventDefault();
      capturePointerSafely(e.currentTarget, e.pointerId);
      freezeCurrentFrame();
      lumenBoxDragRef.current = {
        handle: 'se',
        start: { x1: imgPt[0], y1: imgPt[1], x2: imgPt[0], y2: imgPt[1] },
        origin: imgPt,
      };
      const draft = { x1: imgPt[0], y1: imgPt[1], x2: imgPt[0], y2: imgPt[1] };
      lumenBoxRef.current = draft;
      setLumenBox(draft);
      setLumenPolygon([]);
      lumenPolygonRef.current = [];
      setLumenResultMeta((prev) => ({ ...prev, source: 'manual', error: undefined }));
      return;
    }

    if (
      !lumenEditMode
      && !simpleEditMode
      && (simplePromptMode === 'scribble' || simplePromptMode === 'lasso')
      && beginActiveSamStroke(imgPt, e)
    ) {
      return;
    }

    if (!lumenEditMode && !simpleEditMode && nnInteractiveMode && !simpleVideoMode) {
      if (nnInteractiveBusy) return;
      e.preventDefault();
      void refineWithNnInteractive(nnInteractiveTarget, {
        x: imgPt[0],
        y: imgPt[1],
        label: resolvePointPromptLabel(
          imgPt,
          e.shiftKey ? oppositePromptLabel(activeSamPromptLabel) : activeSamPromptLabel,
          nnInteractiveTarget,
        ),
      });
      return;
    }

    if (!lumenEditMode && !simpleEditMode && mode === 'sam' && !simpleVideoMode && simplePromptMode === 'point') {
      if (samBusy || segmentationBusy) return;
      e.preventDefault();
      void runSamClick(
        imgPt,
        resolvePointPromptLabel(
          imgPt,
          e.shiftKey ? oppositePromptLabel(activeSamPromptLabel) : activeSamPromptLabel,
          nnInteractiveTarget,
        ),
        simplePromptBox,
      );
      return;
    }

    if (simpleVideoMode && mediaMode === 'video') {
      if (samBusy || segmentationBusy) return;
      e.preventDefault();
      if (nnInteractiveMode) {
        setNnInteractiveMode(false);
      }
      if (simpleEditMode) {
        const thrSq = hitThreshold() * hitThreshold() * 9;
        if (simpleEditLayer === 'wall' && wallPointsRef.current.length >= 3) {
          let nearest = -1;
          let bestDistance = thrSq;
          wallPointsRef.current.forEach((point, index) => {
            const distance = dist2(point, imgPt);
            if (distance <= bestDistance) {
              bestDistance = distance;
              nearest = index;
            }
          });
          if (nearest >= 0) {
            capturePointerSafely(e.currentTarget, e.pointerId);
            freezeCurrentFrame();
            pushEditUndo();
            dragSoftRef.current = true;
            dragIndexRef.current = nearest;
            dragLayerRef.current = 'wall';
            setDragIndex(nearest);
            setDragLayer('wall');
          }
          return;
        }
        if (points.length >= 3) {
          const editablePoints = getCurrentTrackedPolygon();
          if (editablePoints !== pointsRef.current) {
            pointsRef.current = clonePoly(editablePoints);
            setPoints(pointsRef.current);
          }
          let nearest = -1;
          let bestDistance = thrSq;
          editablePoints.forEach((point, index) => {
            const distance = dist2(point, imgPt);
            if (distance <= bestDistance) {
              bestDistance = distance;
              nearest = index;
            }
          });
          if (nearest >= 0) {
            capturePointerSafely(e.currentTarget, e.pointerId);
            freezeCurrentFrame();
            pushEditUndo();
            dragSoftRef.current = true;
            dragIndexRef.current = nearest;
            dragLayerRef.current = 'lesion';
            setDragIndex(nearest);
            setDragLayer('lesion');
          }
        }
        return;
      }

      // Interactive lumen refine takes priority over starting a new lesion box.
      if (nnInteractiveMode && nnInteractiveTarget === 'lumen' && !nnInteractiveBusy) {
        e.preventDefault();
        void refineWithNnInteractive('lumen', {
          x: imgPt[0],
          y: imgPt[1],
          label: resolvePointPromptLabel(
            imgPt,
            e.shiftKey ? oppositePromptLabel(activeSamPromptLabel) : activeSamPromptLabel,
            'lumen',
          ),
        });
        return;
      }

      // Reader simple path: box + control-point edit only (no point/scribble/lasso).
      if (simplePromptMode !== 'box') {
        setNnInteractiveMode(false);
        setSimplePromptMode('box');
        setActiveSamPromptLabel('positive');
      }
      {
        lastPolyClickRef.current = null;
        contourInteractionRef.current = true;
        generatedLesionRef.current = [];
        videoFrameOverridesRef.current = [];
        setVideoFrameOverrides([]);
        setTrackingPrepared(false);
        setSimpleEditMode(false);
        clearSamPrompts();
        setSimplePromptBox(null);
        capturePointerSafely(e.currentTarget, e.pointerId);
        samBoxDragRef.current = { x0: imgPt[0], y0: imgPt[1], x1: imgPt[0], y1: imgPt[1] };
        setSamBoxPreview({ x1: imgPt[0], y1: imgPt[1], x2: imgPt[0], y2: imgPt[1] });
        return;
      }
    }

    // Alt/Option+click：设置浸润通道取样点（会议纪要：接触弧内点选）
    const editableLesionPoints = mediaMode === 'video' ? getCurrentTrackedPolygon() : points;
    if (mediaMode === 'video' && editableLesionPoints !== pointsRef.current) {
      pointsRef.current = clonePoly(editableLesionPoints);
      setPoints(pointsRef.current);
    }

    if (e.altKey && editableLesionPoints.length >= 3) {
      setLayerPick({ x: imgPt[0], y: imgPt[1] });
      captureFrameDataUrl();
      setMessage(zh ? `已设取样点 (${Math.round(imgPt[0])},${Math.round(imgPt[1])})` : `Pick set (${Math.round(imgPt[0])},${Math.round(imgPt[1])})`);
      return;
    }

    const thr = hitThreshold() * 1.6;
    const lesionCtrls = editableLesionPoints.length >= 3 ? controlIndices(editableLesionPoints.length, LESION_CTRL_COUNT) : [];
    const wallCtrls = wallPoints.length >= 3 ? controlIndices(wallPoints.length, WALL_CTRL_COUNT) : [];

    const nearestCtrl = (
      poly: number[][],
      idxs: number[],
      thresholdPx: number,
    ): number => {
      let best = -1;
      let bestD = thresholdPx * thresholdPx;
      for (const i of idxs) {
        const p = poly[i];
        if (!p) continue;
        const d = dist2(p, imgPt);
        if (d <= bestD) {
          bestD = d;
          best = i;
        }
      }
      return best;
    };

    // Prefer control handles on BOTH contours (direction_demo dual handles)
    const nearLes = nearestCtrl(editableLesionPoints, lesionCtrls, thr);
    const nearWall = nearestCtrl(wallPoints, wallCtrls, thr);
    let pickLayer: DragLayer | null = null;
    let pickIdx = -1;
    if (nearLes >= 0 && nearWall >= 0) {
      const dL = dist2(editableLesionPoints[nearLes], imgPt);
      const dW = dist2(wallPoints[nearWall], imgPt);
      if (dW <= dL) {
        pickLayer = 'wall';
        pickIdx = nearWall;
      } else {
        pickLayer = 'lesion';
        pickIdx = nearLes;
      }
    } else if (nearWall >= 0) {
      pickLayer = 'wall';
      pickIdx = nearWall;
    } else if (nearLes >= 0) {
      pickLayer = 'lesion';
      pickIdx = nearLes;
    }

    if (pickLayer && pickIdx >= 0 && (mode === 'soft' || mode === 'hard' || mode === 'sam' || mode === 'add')) {
      e.preventDefault();
      capturePointerSafely(e.currentTarget, e.pointerId);
      freezeCurrentFrame();
      pushEditUndo();
      setActiveLayer(pickLayer);
      const useSoft = mode !== 'hard';
      if (mode === 'sam' || mode === 'add') setMode('soft');
      dragSoftRef.current = useSoft;
      dragIndexRef.current = pickIdx;
      dragLayerRef.current = pickLayer;
      setDragIndex(pickIdx);
      setDragLayer(pickLayer);
      return;
    }

    const layerPts = activeLayer === 'lesion' ? editableLesionPoints : activePoints;

    // Hard / add: edge insert on active layer
    if ((mode === 'hard' || mode === 'add') && layerPts.length >= 3) {
      const edge = nearestEdgeInsert(layerPts, imgPt, thr);
      if (edge >= 0) {
        e.preventDefault();
        capturePointerSafely(e.currentTarget, e.pointerId);
        freezeCurrentFrame();
        pushEditUndo();
        const next = [...layerPts];
        next.splice(edge + 1, 0, imgPt);
        if (activeLayer === 'wall') {
          wallPointsRef.current = next;
          setWallPoints(next);
        } else {
          pointsRef.current = next;
          setPoints(next);
        }
        const newIdx = edge + 1;
        setMode('hard');
        dragSoftRef.current = false;
        dragIndexRef.current = newIdx;
        dragLayerRef.current = activeLayer;
        setDragIndex(newIdx);
        setDragLayer(activeLayer);
        return;
      }
    }

    if (mode === 'sam' && simplePromptMode === 'point') {
      void runSamClick(imgPt, e.shiftKey ? oppositePromptLabel(activeSamPromptLabel) : activeSamPromptLabel);
      return;
    }
    if (mode === 'sam') {
      e.preventDefault();
      capturePointerSafely(e.currentTarget, e.pointerId);
      freezeCurrentFrame();
      // Start potential box drag; commit on pointerup (click or box).
      samBoxDragRef.current = { x0: imgPt[0], y0: imgPt[1], x1: imgPt[0], y1: imgPt[1] };
      setSamBoxPreview({ x1: imgPt[0], y1: imgPt[1], x2: imgPt[0], y2: imgPt[1] });
      (e.currentTarget as HTMLCanvasElement).dataset.samNeg = e.shiftKey ? '1' : '0';
      return;
    }
    if (mode === 'add') {
      freezeCurrentFrame();
      pushEditUndo();
      const next = [...layerPts, imgPt];
      if (activeLayer === 'wall') {
        wallPointsRef.current = next;
        setWallPoints(next);
      } else {
        pointsRef.current = next;
        setPoints(next);
      }
      void persistOverrideRef.current('doctor_edit', { silent: true });
      return;
    }
    if (mode === 'delete') {
      freezeCurrentFrame();
      // Delete nearest control handle on active layer (or any vertex in hard mode)
      const idxs = activeLayer === 'wall' ? wallCtrls : lesionCtrls;
      const idx = nearestCtrl(layerPts, idxs.length ? idxs : layerPts.map((_, i) => i), thr);
      if (idx >= 0 && layerPts.length > 3) {
        pushEditUndo();
        const next = layerPts.filter((_, i) => i !== idx);
        if (activeLayer === 'wall') {
          wallPointsRef.current = next;
          setWallPoints(next);
        } else {
          pointsRef.current = next;
          setPoints(next);
        }
        void persistOverrideRef.current('doctor_edit', { silent: true });
      }
      return;
    }

    // soft mode fallback: grab nearest dense vertex with soft deform
    if (mode === 'soft' && layerPts.length >= 3) {
      const fallback = nearestVertex(layerPts, imgPt, thr * 3);
      if (fallback >= 0) {
        e.preventDefault();
        capturePointerSafely(e.currentTarget, e.pointerId);
        freezeCurrentFrame();
        pushEditUndo();
        dragSoftRef.current = true;
        dragIndexRef.current = fallback;
        dragLayerRef.current = activeLayer;
        setDragIndex(fallback);
        setDragLayer(activeLayer);
      }
    }
  };

  const onPointerMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (magnifierOn && dragIndexRef.current == null && !samBoxDragRef.current && !lumenBoxDragRef.current && !activePromptStrokeRef.current) {
      const canvas = canvasRef.current;
      const imgPt = canvasToImage(e);
      if (canvas && imgPt) {
        const rect = canvas.getBoundingClientRect();
        const scaleX = canvas.width / Math.max(1, rect.width);
        const scaleY = canvas.height / Math.max(1, rect.height);
        magnifierPosRef.current = {
          cx: (e.clientX - rect.left) * scaleX,
          cy: (e.clientY - rect.top) * scaleY,
          ix: imgPt[0],
          iy: imgPt[1],
        };
        redraw();
      }
    }
    const activeStroke = activePromptStrokeRef.current;
    if (activeStroke) {
      const imgPt = canvasToImage(e);
      if (!imgPt) return;
      e.preventDefault();
      pendingPromptPointRef.current = imgPt;
      if (promptStrokeRafRef.current != null) return;
      promptStrokeRafRef.current = window.requestAnimationFrame(() => {
        promptStrokeRafRef.current = null;
        const stroke = activePromptStrokeRef.current;
        const pending = pendingPromptPointRef.current;
        if (!stroke || !pending) return;
        const nextPoints = appendPromptPoint(stroke.points, pending, 2);
        if (nextPoints.length === stroke.points.length) return;
        const nextStroke = { ...stroke, points: nextPoints };
        activePromptStrokeRef.current = nextStroke;
        setActivePromptStroke(nextStroke);
        redraw();
      });
      return;
    }
    const lumenDrag = lumenBoxDragRef.current;
    if (lumenDrag) {
      const imgPt = canvasToImage(e);
      if (!imgPt) return;
      e.preventDefault();
      const { handle, start, origin } = lumenDrag;
      const dx = imgPt[0] - origin[0];
      const dy = imgPt[1] - origin[1];
      let next: LumenBBox = { ...start };
      if (handle === 'move') {
        next = {
          x1: start.x1 + dx,
          y1: start.y1 + dy,
          x2: start.x2 + dx,
          y2: start.y2 + dy,
        };
      } else {
        next = { ...start };
        if (handle.includes('n')) next.y1 = start.y1 + dy;
        if (handle.includes('s')) next.y2 = start.y2 + dy;
        if (handle.includes('w')) next.x1 = start.x1 + dx;
        if (handle.includes('e')) next.x2 = start.x2 + dx;
      }
      const normalized = normalizeLumenBBox(next);
      lumenBoxRef.current = normalized;
      setLumenBox(normalized);
      redraw();
      return;
    }
    const boxDrag = samBoxDragRef.current;
    if (boxDrag) {
      const imgPt = canvasToImage(e);
      if (!imgPt) return;
      e.preventDefault();
      boxDrag.x1 = imgPt[0];
      boxDrag.y1 = imgPt[1];
      setSamBoxPreview({ x1: boxDrag.x0, y1: boxDrag.y0, x2: boxDrag.x1, y2: boxDrag.y1 });
      redraw();
      return;
    }
    const idx = dragIndexRef.current;
    const layer = dragLayerRef.current;
    if (idx === null || !layer) return;
    e.preventDefault();
    const imgPt = canvasToImage(e);
    if (!imgPt) return;
    const src = layer === 'wall' ? wallPointsRef.current : pointsRef.current;
    if (!src[idx]) return;
    const next = clonePoly(src);
    if (dragSoftRef.current) {
      softDeform(
        next,
        idx,
        imgPt[0],
        imgPt[1],
        layer === 'wall' ? WALL_SOFT_SIGMA : LESION_SOFT_SIGMA,
      );
    } else {
      next[idx] = [imgPt[0], imgPt[1]];
    }
    if (layer === 'wall') {
      wallPointsRef.current = next;
    } else {
      pointsRef.current = next;
    }
    draggingRef.current = true;
    redraw();
  };

  const onPointerUp = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const activeStroke = activePromptStrokeRef.current;
    if (activeStroke) {
      if (promptStrokeRafRef.current != null) {
        cancelAnimationFrame(promptStrokeRafRef.current);
        promptStrokeRafRef.current = null;
      }
      const finalPoint = canvasToImage(e) || pendingPromptPointRef.current;
      pendingPromptPointRef.current = null;
      const finalizedStroke: ActiveSamStroke = {
        ...activeStroke,
        points: appendFinalPromptPoint(activeStroke.points, finalPoint, 0.5),
      };
      activePromptStrokeRef.current = null;
      setActivePromptStroke(null);
      try {
        if (e.currentTarget.hasPointerCapture(e.pointerId)) {
          e.currentTarget.releasePointerCapture(e.pointerId);
        }
      } catch {
        /* ignore */
      }
      void applyActiveSamStroke(finalizedStroke);
      return;
    }
    if (lumenBoxDragRef.current) {
      lumenBoxDragRef.current = null;
      try {
        if (e.currentTarget.hasPointerCapture(e.pointerId)) {
          e.currentTarget.releasePointerCapture(e.pointerId);
        }
      } catch {
        /* ignore */
      }
      const current = lumenBoxRef.current;
      if (current) {
        const normalized = normalizeLumenBBox(current);
        setLumenBox(normalized);
        setLumenPolygon([]);
        setLumenResultMeta((prev) => ({
          ...prev,
          source: prev?.source === 'yolo' || prev?.source === 'yolo_then_sam31' ? 'yolo_then_manual' : 'manual',
          sam_backend_id: undefined,
          sam_score: undefined,
          error: undefined,
        }));
        setMessage(
          zh
            ? '胃腔框已更新（仍可继续拖调）；轮廓已清除，满意后点「出轮廓」'
            : 'Lumen box updated (keep adjusting); contour cleared — tap Contour when ready',
        );
        // Stay in lumenEditMode for continuous adjustment.
        setLumenEditMode(true);
        if (mediaMode === 'video' && pointsRef.current.length >= 3) {
          recordVideoFrameOverride(pointsRef.current, 'accepted');
          void persistOverrideRef.current('doctor_edit', { silent: true });
        }
        void persistLumenOverrideRef.current(true);
      }
      return;
    }
    const boxDrag = samBoxDragRef.current;
    if (boxDrag) {
      samBoxDragRef.current = null;
      setSamBoxPreview(null);
      try {
        if (e.currentTarget.hasPointerCapture(e.pointerId)) {
          e.currentTarget.releasePointerCapture(e.pointerId);
        }
      } catch {
        /* ignore */
      }
      const dx = Math.abs(boxDrag.x1 - boxDrag.x0);
      const dy = Math.abs(boxDrag.y1 - boxDrag.y0);
      const neg = e.currentTarget.dataset.samNeg === '1' || e.shiftKey;
      delete e.currentTarget.dataset.samNeg;
      if (dx > 12 || dy > 12) {
        const box = {
          x1: Math.min(boxDrag.x0, boxDrag.x1),
          y1: Math.min(boxDrag.y0, boxDrag.y1),
          x2: Math.max(boxDrag.x0, boxDrag.x1),
          y2: Math.max(boxDrag.y0, boxDrag.y1),
        };
        const cx = (box.x1 + box.x2) / 2;
        const cy = (box.y1 + box.y2) / 2;
        // Box prompt resets click history (cleaner region seed).
        samClicksRef.current = [{ x: cx, y: cy, label: 'positive' }];
        setSamClicks(samClicksRef.current);
        setSimplePromptBox(box);
        // Stay on box / soft-edit path after box select (do not jump to default point mode).
        setSimplePromptMode('box');
        void runSamClick([cx, cy], 'positive', box).then((poly) => {
          resumeSimpleTracking(poly);
          if (poly && poly.length >= 3) {
            stopInteractivePrompt();
            setMode('soft');
            setSimplePromptMode('box');
            setSimpleEditMode(true);
            setSimpleEditLayer('lesion');
            setActiveLayer('lesion');
            setLumenEditMode(false);
            setMessage(
              zh
                ? '框选完成：已自动分割并进入轮廓编辑，拖控制点微调后点顶中「辅助意见」'
                : 'Box done: auto-segmented; drag handles to refine, then use top Assist',
            );
          }
        });
      } else if (simpleVideoMode) {
        setMessage(zh ? '请拖出矩形框选病灶（单击不会加正负点）' : 'Drag a rectangle to box the lesion (clicks do not add points)');
      } else {
        void runSamClick(
          [boxDrag.x0, boxDrag.y0],
          neg ? 'negative' : 'positive',
        )
          .then((poly) => resumeSimpleTracking(poly));
      }
      return;
    }
    if (dragIndexRef.current !== null) {
      const editedLayer = dragLayerRef.current;
      draggingRef.current = false;
      setPoints(clonePoly(pointsRef.current));
      setWallPoints(clonePoly(wallPointsRef.current));
      if (mediaMode === 'video' && editedLayer === 'lesion') {
        setTrackingPrepared(false);
        recordVideoFrameOverride(pointsRef.current, 'accepted');
      }
      setMessage(
        zh
          ? (editedLayer === 'wall' ? '胃壁区域已更新' : '当前帧病灶区域已更新')
          : (editedLayer === 'wall' ? 'Wall region updated' : 'Current-frame lesion region updated'),
      );
      void persistOverrideRef.current('doctor_edit', { silent: true });
      try {
        if (e.currentTarget.hasPointerCapture(e.pointerId)) {
          e.currentTarget.releasePointerCapture(e.pointerId);
        }
      } catch {
        /* ignore */
      }
    }
    dragIndexRef.current = null;
    dragLayerRef.current = null;
    setDragIndex(null);
    setDragLayer(null);
  };

  const onPointerCancel = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (activePromptStrokeRef.current) {
      if (promptStrokeRafRef.current != null) {
        cancelAnimationFrame(promptStrokeRafRef.current);
        promptStrokeRafRef.current = null;
      }
      pendingPromptPointRef.current = null;
      activePromptStrokeRef.current = null;
      setActivePromptStroke(null);
      try {
        if (e.currentTarget.hasPointerCapture(e.pointerId)) {
          e.currentTarget.releasePointerCapture(e.pointerId);
        }
      } catch {
        /* ignore */
      }
      e.preventDefault();
      redraw();
      return;
    }
    onPointerUp(e);
  };

  const propagateMaskAcrossVideo = useCallback(async () => {
    if (mediaMode !== 'video' || !videoRef.current || points.length < 3) {
      setMessage(zh ? '请先在视频帧上得到可编辑区域' : 'Need an editable region on a video frame');
      return;
    }
    const video = videoRef.current;
    const start = video.currentTime || 0;
    const duration = video.duration || 0;
    // Full-video tracking must cover frames before and after the seed, not only later frames.
    if (!duration || duration <= 0.1) {
      setMessage(zh ? '当前视频时长不可用' : 'Video duration unavailable');
      return;
    }
    freezeCurrentFrame();
    setPropagateBusy(true);
    setTrackOnPlay(false);
    const traceId = `video_propagate_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    const traceStartedAt = performance.now();
    const step = Math.max(0.2, Math.min(0.5, duration / 40));
    const maxSteps = 12;
    const imageWidth = video.videoWidth;
    const imageHeight = video.videoHeight;
    let currentPoly = points.map((p) => [p[0], p[1]]);
    const seedLumenPoly = lumenPolygonRef.current.length >= 3 ? clonePoly(lumenPolygonRef.current) : undefined;
    const seedLumenBox = lumenBoxRef.current || (seedLumenPoly ? bboxFromPolygon(seedLumenPoly) : undefined);
    let propagatedFrames: VideoMaskFrameOverride[] = [{
      timestamp_sec: Number(start.toFixed(3)),
      imageWidth,
      imageHeight,
      mask_polygon: currentPoly.map((p) => [Math.round(p[0] * 10) / 10, Math.round(p[1] * 10) / 10]),
      roi_bbox: bboxFromPolygon(currentPoly),
      lumen_polygon: seedLumenPoly,
      lumen_bbox: seedLumenBox || undefined,
      source: 'video_propagate',
      propagation_status: 'seed',
    }];
    setVideoFrameOverrides(propagatedFrames);
    let okSteps = 0;
    try {
      try {
        const centroid = polygonCentroid(currentPoly);
        const nativeResponse = await fetch('/api/agent/video/propagate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            case_id: patient?.patient_id || patient?.id || '',
            model: segmentationModel,
            video_url: videoUrl,
            frame_time: start,
            image_width: imageWidth,
            image_height: imageHeight,
            clicks: samClicksRef.current.length
              ? samClicksRef.current
              : centroid
                ? [{ x: centroid[0], y: centroid[1], label: 'positive' }]
                : [],
            box: bboxFromPolygon(currentPoly),
            direction: 'both',
            max_frames: Math.max(120, Math.ceil(duration * 120)),
          }),
        });
        const nativePayload = await nativeResponse.json() as {
          ok?: boolean;
          error?: string;
          result?: {
            status?: string;
            needs_reanchor?: boolean;
            accepted_frames?: number;
            num_frames?: number;
            propagation_mode?: string;
            frames?: Array<{
              frame_index?: number;
              frame_time: number;
              direction?: string;
              mask_polygon?: number[][];
              accepted?: boolean;
              quality_score?: number;
            }>;
          };
        };
        if (!nativeResponse.ok || !nativePayload.ok || !nativePayload.result) {
          throw new Error(nativePayload.error || 'native video propagation failed');
        }
        const nativeFrames = mapPropagateFramesToOverrides(
          nativePayload.result.frames || [],
          imageWidth,
          imageHeight,
          'video_track',
        );
        if (!nativeFrames.length) throw new Error('native video propagation returned no masks');

        const lumenSeedPoly = lumenPolygonRef.current.length >= 3 ? clonePoly(lumenPolygonRef.current) : [];
        const lumenSeedBox = lumenBoxRef.current || (lumenSeedPoly.length >= 3 ? bboxFromPolygon(lumenSeedPoly) : null);
        const lumenCentroid = lumenSeedPoly.length >= 3
          ? polygonCentroid(lumenSeedPoly)
          : (lumenSeedBox
            ? [(lumenSeedBox.x1 + lumenSeedBox.x2) / 2, (lumenSeedBox.y1 + lumenSeedBox.y2) / 2]
            : null);
        let lumenFrames: VideoMaskFrameOverride[] = [];
        let lumenTracked = false;
        if (lumenSeedBox && lumenCentroid) {
          setPropagateProgress(zh ? '胃腔跟踪中…' : 'Tracking lumen…');
          try {
            const lumenResult = await requestVideoPropagate({
              case_id: patient?.patient_id || patient?.id || '',
              model: segmentationModel,
              video_url: videoUrl,
              frame_time: start,
              image_width: imageWidth,
              image_height: imageHeight,
              clicks: [{ x: lumenCentroid[0], y: lumenCentroid[1], label: 'positive' }],
              box: lumenSeedBox,
              direction: 'both',
              max_frames: Math.max(120, Math.ceil(duration * 120)),
              text_prompt: 'gastric lumen cavity',
            });
            lumenFrames = mapPropagateFramesToOverrides(
              lumenResult.frames || [],
              imageWidth,
              imageHeight,
              'video_track',
            );
            lumenTracked = lumenFrames.length > 0;
          } catch (lumenError) {
            console.warn('lumen video track failed', lumenError);
          }
        }

        const mergedFrames = mergeLumenIntoLesionFrames(nativeFrames, lumenFrames, {
          polygon: lumenSeedPoly,
          box: lumenSeedBox,
        }, start);
        videoFrameOverridesRef.current = mergedFrames;
        setVideoFrameOverrides(mergedFrames);
        const nearest = mergedFrames.reduce((best, frame) => (
          Math.abs(frame.timestamp_sec - start) < Math.abs(best.timestamp_sec - start) ? frame : best
        ), mergedFrames[0]);
        if (nearest?.mask_polygon?.length) {
          pointsRef.current = nearest.mask_polygon;
          setPoints(nearest.mask_polygon);
        }
        if (nearest?.lumen_polygon?.length) {
          lumenPolygonRef.current = nearest.lumen_polygon;
          setLumenPolygon(nearest.lumen_polygon);
          const nextBox = nearest.lumen_bbox || bboxFromPolygon(nearest.lumen_polygon);
          if (nextBox) {
            lumenBoxRef.current = nextBox;
            setLumenBox(nextBox);
          }
        }
        setFrameFrozen(true);
        frameFrozenRef.current = true;
        const usedSam31MemoryPrompt = nativePayload.result.propagation_mode === 'sam3.1_motion_memory_box'
          || nativePayload.result.propagation_mode === 'sam3.1_framewise_fixed_box';
        await applyAreaKeyframesRef.current(mergedFrames);
        const persisted = await persistOverrideRef.current('video_tracking_complete');
        maskAuditRef.current('model_trace', {
          trace_id: traceId,
          operation: 'video_propagation',
          model: segmentationModel,
          source: 'video_propagate',
          outcome: 'success',
          frame_time_sec: start,
          input: {
            direction: 'both',
            requested_max_frames: nativePayload.result.num_frames,
            video_duration_sec: duration,
          },
          output: {
            lesion_frame_count: nativeFrames.length,
            lumen_frame_count: lumenFrames.length,
            merged_frame_count: mergedFrames.length,
            accepted_frames: nativePayload.result.accepted_frames,
            lumen_tracked: lumenTracked,
            needs_reanchor: nativePayload.result.needs_reanchor,
            persisted,
          },
          duration_ms: Math.round(performance.now() - traceStartedAt),
        });
        setMessage(
          zh
            ? `${usedSam31MemoryPrompt ? '视频跟踪完成' : '跟踪扩散完成'}：病灶 ${nativePayload.result.accepted_frames || nativeFrames.length}/${nativePayload.result.num_frames || nativeFrames.length} 帧${lumenTracked ? `，胃腔 ${lumenFrames.length} 帧` : (lumenSeedBox ? '（胃腔跟踪失败）' : '（未提供胃腔）')}；${persisted ? '完整结果已保存' : '保存失败，请点击保存轮廓'}${nativePayload.result.needs_reanchor ? '，已请求重锚定' : ''}`
            : `${usedSam31MemoryPrompt ? 'Video tracking complete' : 'Tracking propagation complete'}: lesion ${nativePayload.result.accepted_frames || nativeFrames.length}/${nativePayload.result.num_frames || nativeFrames.length} frames${lumenTracked ? `, lumen ${lumenFrames.length}` : ''}; ${persisted ? 'complete result saved' : 'save failed, click Save complete masks'}`,
        );
        return;
      } catch (nativeError) {
        maskAuditRef.current('model_trace', {
          trace_id: traceId,
          operation: 'video_propagation',
          model: segmentationModel,
          source: 'video_propagate',
          outcome: 'fallback_to_sampled_tracking',
          frame_time_sec: start,
          error: nativeError instanceof Error ? nativeError.message.slice(0, 240) : 'Native propagation failed',
        });
        setMessage(
          zh
            ? `原生视频传播不可用，回退逐帧跟踪：${nativeError instanceof Error ? nativeError.message : 'unknown error'}`
            : 'Native propagation unavailable; falling back to sampled tracking',
        );
      }

      // Fallback sampled tracking: cover both directions from the seed, not only later frames.
      const backwardSteps = Math.max(0, Math.floor(maxSteps * (start / Math.max(duration, 0.01))));
      const forwardSteps = maxSteps - backwardSteps;
      const sampleTimes = [
        ...Array.from({ length: backwardSteps }, (_, index) => Math.max(0.01, start - step * (backwardSteps - index))).reverse(),
        ...Array.from({ length: forwardSteps }, (_, index) => Math.min(duration - 0.01, start + step * (index + 1))),
      ].filter((t) => t > 0 && t < duration && Math.abs(t - start) > 0.05);

      for (let i = 0; i < sampleTimes.length; i += 1) {
        const t = sampleTimes[i];
        setPropagateProgress(`${i + 1}/${sampleTimes.length}, t=${t.toFixed(2)}s`);
        video.currentTime = t;
        await new Promise<void>((resolve) => {
          const done = () => {
            video.removeEventListener('seeked', done);
            resolve();
          };
          video.addEventListener('seeked', done);
        });
        await sleep(40);
        const bbox = bboxFromPolygon(currentPoly);
        const centroid = polygonCentroid(currentPoly);
        if (!bbox || !centroid) break;
        const prev = currentPoly;
        const nextPoly = await runSamAtPoint(centroid, {
          silent: true,
          source: 'video_propagate',
          box: bbox,
          keepEditing: false,
        });
        if (!nextPoly || nextPoly.length < 3) {
          setPoints(prev);
          break;
        }
        currentPoly = nextPoly;
        setPoints(nextPoly);
        propagatedFrames = ([
          ...propagatedFrames,
          {
            timestamp_sec: Number(t.toFixed(3)),
            imageWidth,
            imageHeight,
            mask_polygon: nextPoly.map((p) => [Math.round(p[0] * 10) / 10, Math.round(p[1] * 10) / 10]),
            roi_bbox: bboxFromPolygon(nextPoly),
            lumen_polygon: seedLumenPoly,
            lumen_bbox: seedLumenBox || undefined,
            source: 'video_propagate' as const,
            propagation_status: 'accepted' as const,
          },
        ] as VideoMaskFrameOverride[]).sort((a, b) => a.timestamp_sec - b.timestamp_sec);
        setVideoFrameOverrides(propagatedFrames);
        okSteps += 1;
        setVideoTime(t);
        redraw();
      }
      setFrameFrozen(true);
      frameFrozenRef.current = true;
      setMode('soft');
      videoFrameOverridesRef.current = propagatedFrames;
      await applyAreaKeyframesRef.current(propagatedFrames);
      const persisted = await persistOverrideRef.current('video_tracking_complete');
      maskAuditRef.current('model_trace', {
        trace_id: traceId,
        operation: 'video_propagation',
        model: segmentationModel,
        source: 'video_propagate_fallback',
        outcome: 'success',
        frame_time_sec: start,
        input: {
          direction: 'both',
          max_steps: maxSteps,
          video_duration_sec: duration,
        },
        output: {
          lesion_frame_count: propagatedFrames.length,
          successful_steps: okSteps,
          lumen_seed_present: Boolean(seedLumenBox),
          persisted,
        },
        duration_ms: Math.round(performance.now() - traceStartedAt),
      });
    setMessage(
      zh
        ? `已跟踪扩散 ${okSteps} 帧（覆盖种子帧前后）；${persisted ? '完整结果已保存' : '保存失败，请点击保存轮廓'}`
        : `Propagated ${okSteps} frames (before and after the seed); ${persisted ? 'complete result saved' : 'save failed, click Save complete masks'}`,
    );
    } catch (error) {
      maskAuditRef.current('model_trace', {
        trace_id: traceId,
        operation: 'video_propagation',
        model: segmentationModel,
        source: 'video_propagate',
        outcome: 'error',
        frame_time_sec: start,
        error: error instanceof Error ? error.message.slice(0, 240) : 'Video propagation failed',
        duration_ms: Math.round(performance.now() - traceStartedAt),
      });
      setMessage(error instanceof Error ? error.message : (zh ? '视频跟踪失败' : 'Video propagation failed'));
    } finally {
      setPropagateBusy(false);
      setPropagateProgress(null);
    }
  }, [mediaMode, patient?.id, patient?.patient_id, points, segmentationModel, videoUrl, zh, freezeCurrentFrame, runSamAtPoint, redraw]);

  const buildOverride = useCallback((): MaskBoundaryOverride | null => {
    const currentPoints = mediaMode === 'video' && videoFrameOverridesRef.current.length
      ? getCurrentTrackedPolygon()
      : pointsRef.current;
    const currentWallPoints = wallPointsRef.current;
    const currentVideoFrames = mediaMode === 'video' && videoFrameOverridesRef.current.length
      ? videoFrameOverridesRef.current
      : [];
    if (!patient || currentPoints.length < 3) return null;
    const video = videoRef.current;
    const img = imgRef.current;
    const width =
      mediaMode === 'video' && video?.videoWidth
        ? video.videoWidth
        : (img?.naturalWidth || 0);
    const height =
      mediaMode === 'video' && video?.videoHeight
        ? video.videoHeight
        : (img?.naturalHeight || 0);
    if (!width || !height) return null;
    return {
      patientId: patient.patient_id,
      frameId: patient.id,
      imageWidth: width,
      imageHeight: height,
      mask_polygon: currentPoints.map((p) => [Math.round(p[0]), Math.round(p[1])]),
      wall_polygon:
        currentWallPoints.length >= 3
          ? currentWallPoints.map((p) => [Math.round(p[0]), Math.round(p[1])])
          : undefined,
      roi_bbox: bboxFromPolygon(currentPoints),
      roi_mode: roiMode,
      source: nnInteractiveMode && nnInteractiveTarget === 'lesion'
        ? 'nninteractive'
        : (mode === 'sam' ? 'sam' : 'manual'),
      video_time_sec: mediaMode === 'video'
        ? Number((video?.currentTime ?? videoTime).toFixed(3))
        : undefined,
      video_url: mediaMode === 'video' ? videoUrl || undefined : undefined,
      video_frames: currentVideoFrames.length
        ? currentVideoFrames.map((frame) => {
          const maskPolygon = frame.mask_polygon.map((point) => [Math.round(point[0]), Math.round(point[1])]);
          const lumenPolygon = frame.lumen_polygon?.map((point) => [Math.round(point[0]), Math.round(point[1])]);
          return {
            ...frame,
            mask_polygon: maskPolygon,
            roi_bbox: frame.roi_bbox || bboxFromPolygon(maskPolygon),
            lumen_polygon: lumenPolygon,
            lumen_bbox: frame.lumen_bbox
              || (lumenPolygon && bboxFromPolygon(lumenPolygon)),
          };
        })
        : undefined,
      note: currentVideoFrames.length
        ? 'Video tracking stores complete lesion and lumen contours at sampled timestamps; doctor edits replace the current timestamp.'
        : undefined,
      prompt_type: mode === 'sam' ? simplePromptMode : mode,
      prompt_payload: {
        mode: mode === 'sam' ? simplePromptMode : mode,
        box: simplePromptBox,
        clicks: samClicks.map((click) => ({
          x: Math.round(click.x * 10) / 10,
          y: Math.round(click.y * 10) / 10,
          label: click.label,
        })),
        scribbles: promptStrokes.map((stroke) => ({
          points: stroke.points.map((point) => ({
            x: Math.round(point[0] * 10) / 10,
            y: Math.round(point[1] * 10) / 10,
          })),
          label: stroke.label,
          width: stroke.width,
          kind: stroke.kind,
        })),
      },
      model_version: nnInteractiveMode ? 'nnInteractive_v1.0' : segmentationModel,
      sam_score: samReport?.sam_score,
      updated_at: new Date().toISOString(),
    };
  }, [getCurrentTrackedPolygon, mediaMode, mode, nnInteractiveMode, nnInteractiveTarget, patient, promptStrokes, roiMode, samClicks, samReport?.sam_score, segmentationModel, simplePromptBox, simplePromptMode, videoTime, videoUrl]);

  const persistOverride = useCallback(async (
    action = 'manual_save',
    options: PersistOverrideOptions = {},
  ): Promise<boolean> => {
    const next = buildOverride();
    if (!next) {
      if (!options.silent) setMessage(zh ? '至少需要 3 个顶点' : 'Need at least 3 vertices');
      return false;
    }
    const lumenSnapshot = buildLumenOverride() || lumenOverride || undefined;
    const save = async (): Promise<boolean> => {
      savingRef.current = true;
      setSaving(true);
      if (!options.silent) setMessage(null);
      try {
        const res = await fetch('/api/patients/mask-overrides', {
          method: 'POST',
          headers: authHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify({
            override: next,
            lumen_override: lumenSnapshot,
            action,
            reader_id: accountReaderId || undefined,
          }),
        });
        const data = await res.json() as {
          override?: MaskBoundaryOverride;
          lumen_override?: LumenOverride;
          history_entry?: MaskHistoryEntry;
          error?: string;
        };
        if (!res.ok) throw new Error(data.error || 'Save failed');
        const saved = data.override || next;
        onOverrideChange(saved);
        videoFrameOverridesRef.current = saved.video_frames || [];
        setVideoFrameOverrides(videoFrameOverridesRef.current);
        maskAuditRef.current('mask_saved', {
          action,
          success: true,
          history_entry_id: data.history_entry?.id,
          ...summarizeMaskForAudit(saved),
        });
        if (data.history_entry) {
          setMaskHistory((current) => [
            data.history_entry!,
            ...current.filter((item) => item.id !== data.history_entry!.id),
          ].slice(0, 40));
        }
        if (!options.silent) {
          setMessage(
            action === 'video_tracking_complete'
              ? (zh ? '视频跟踪结果已完整保存，可在历史记录中恢复' : 'Complete video tracking result saved; it can be restored from history')
              : (zh ? '边界已保存，分析将使用此覆盖' : 'Boundary saved — analyze will use this override'),
          );
        }
        return true;
      } catch (err) {
        maskAuditRef.current('mask_saved', {
          action,
          success: false,
          error: err instanceof Error ? err.message.slice(0, 240) : 'Save failed',
        });
        if (!options.silent) {
          setMessage(err instanceof Error ? err.message : 'Save failed');
        }
        return false;
      } finally {
        savingRef.current = false;
        setSaving(false);
      }
    };
    const queued = persistChainRef.current.catch(() => false).then(save);
    persistChainRef.current = queued.catch(() => false);
    return queued;
  }, [accountReaderId, authHeaders, buildLumenOverride, buildOverride, lumenOverride, onOverrideChange, zh]);

  useEffect(() => {
    persistOverrideRef.current = persistOverride;
  }, [persistOverride]);

  const loadMaskHistory = useCallback(async () => {
    if (!patient) return;
    setHistoryBusy(true);
    try {
      const params = new URLSearchParams({
        patientId: patient.patient_id,
        frameId: patient.id,
        history: '1',
      });
      if (accountReaderId) params.set('readerId', accountReaderId);
      const res = await fetch(`/api/patients/mask-overrides?${params.toString()}`, {
        cache: 'no-store',
        headers: authHeaders(),
      });
      const data = await res.json() as { history?: MaskHistoryEntry[]; error?: string };
      if (!res.ok) throw new Error(data.error || 'History loading failed');
      const nextHistory = Array.isArray(data.history) ? data.history : [];
      setMaskHistory(nextHistory);
      setHistoryPreviewId((current) => (
        current && nextHistory.some((entry) => entry.id === current) ? current : null
      ));
      maskAuditRef.current('mask_event', {
        action: 'history_loaded',
        history_count: nextHistory.length,
        displayed_on_canvas: false,
      });
    } catch (error) {
      maskAuditRef.current('error', {
        operation: 'history_loaded',
        error: error instanceof Error ? error.message.slice(0, 240) : 'History loading failed',
      });
      setMessage(error instanceof Error ? error.message : (zh ? '历史记录加载失败' : 'History loading failed'));
    } finally {
      setHistoryBusy(false);
    }
  }, [accountReaderId, authHeaders, patient, zh]);

  const deleteMaskHistoryEntry = useCallback(async (entry: MaskHistoryEntry) => {
    if (!patient || !entry?.id || historyBusy) return;
    if (!window.confirm(zh ? '删除该历史版本？仅对本账号隐藏。' : 'Delete this history version? It will be hidden for your account.')) {
      return;
    }
    setHistoryBusy(true);
    try {
      const params = new URLSearchParams({
        patientId: patient.patient_id,
        frameId: patient.id,
        historyId: entry.id,
      });
      if (accountReaderId) params.set('readerId', accountReaderId);
      const res = await fetch(`/api/patients/mask-overrides?${params.toString()}`, {
        method: 'DELETE',
        headers: authHeaders(),
      });
      const data = await res.json() as { ok?: boolean; error?: string };
      if (!res.ok || !data.ok) throw new Error(data.error || 'Delete failed');
      if (historyPreviewId === entry.id) setHistoryPreviewId(null);
      maskAuditRef.current('mask_event', {
        action: 'history_deleted',
        history_entry_id: entry.id,
      });
      await loadMaskHistory();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : (zh ? '删除失败' : 'Delete failed'));
    } finally {
      setHistoryBusy(false);
    }
  }, [accountReaderId, authHeaders, historyBusy, historyPreviewId, loadMaskHistory, patient, zh]);

  const restoreMaskHistory = useCallback(async (entry: MaskHistoryEntry) => {
    if (!patient || !entry?.override || historyBusy || savingRef.current) return;
    setHistoryBusy(true);
    maskAuditRef.current('mask_event', {
      action: 'history_restore_requested',
      history_entry_id: entry.id,
      ...summarizeMaskForAudit(entry.override),
    });
    try {
      await persistChainRef.current.catch(() => false);
      const res = await fetch('/api/patients/mask-overrides', {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          override: entry.override,
          lumen_override: entry.lumen_override,
          action: 'restore_history',
          reader_id: accountReaderId || undefined,
        }),
      });
      const data = await res.json() as {
        override?: MaskBoundaryOverride;
        lumen_override?: LumenOverride;
        error?: string;
      };
      if (!res.ok) throw new Error(data.error || 'History restore failed');
      const restored = data.override || entry.override;
      let restoredLumen = data.lumen_override || entry.lumen_override;
      if (restoredLumen) {
        const lumenRes = await fetch('/api/patients/lumen-overrides', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ override: restoredLumen }),
        });
        const lumenData = await lumenRes.json() as { override?: LumenOverride; error?: string };
        if (!lumenRes.ok) throw new Error(lumenData.error || 'History lumen restore failed');
        restoredLumen = lumenData.override || restoredLumen;
      }
      pointsRef.current = clonePoly(restored.mask_polygon);
      wallPointsRef.current = clonePoly(restored.wall_polygon || []);
      videoFrameOverridesRef.current = restored.video_frames || [];
      setPoints(pointsRef.current);
      setWallPoints(wallPointsRef.current);
      setVideoFrameOverrides(videoFrameOverridesRef.current);
      onOverrideChange(restored);
      if (restoredLumen) {
        lumenBoxRef.current = restoredLumen.lumen_bbox;
        lumenPolygonRef.current = restoredLumen.lumen_polygon || [];
        setLumenBox(restoredLumen.lumen_bbox);
        setLumenPolygon(restoredLumen.lumen_polygon || []);
        setLumenConfidence(restoredLumen.lumen_confidence ?? null);
        setLumenResultMeta({
          detector_backend_id: restoredLumen.detector_backend_id,
          sam_backend_id: restoredLumen.sam_backend_id,
          sam_score: restoredLumen.sam_score,
          source: restoredLumen.source,
        });
        onLumenOverrideChange?.(restoredLumen);
      }
      setHistoryOpen(true);
      setHistoryPreviewId(entry.id);
      setMessage(zh ? '已恢复完整遮罩版本，历史面板保持打开' : 'Complete mask version restored; history stays open');
      maskAuditRef.current('mask_event', {
        action: 'history_restored',
        history_entry_id: entry.id,
        displayed_on_canvas: true,
        ...summarizeMaskForAudit(restored),
        lumen_points: restoredLumen?.lumen_polygon?.length || 0,
        lumen_box_present: Boolean(restoredLumen?.lumen_bbox),
      });
      await loadMaskHistory();
    } catch (error) {
      maskAuditRef.current('error', {
        operation: 'history_restore',
        history_entry_id: entry.id,
        error: error instanceof Error ? error.message.slice(0, 240) : 'History restore failed',
      });
      setMessage(error instanceof Error ? error.message : (zh ? '历史版本恢复失败' : 'History restore failed'));
    } finally {
      setHistoryBusy(false);
    }
  }, [accountReaderId, authHeaders, historyBusy, loadMaskHistory, onLumenOverrideChange, onOverrideChange, patient, zh]);

  const toggleHistoryPanel = useCallback(() => {
    const nextOpen = !historyOpen;
    setHistoryOpen(nextOpen);
    maskAuditRef.current('mask_event', {
      action: nextOpen ? 'history_opened' : 'history_closed',
      history_loaded: nextOpen,
      displayed_on_canvas: false,
    });
    if (nextOpen) {
      setHistoryPreviewId(null);
      void loadMaskHistory();
    } else {
      setHistoryPreviewId(null);
    }
  }, [historyOpen, loadMaskHistory]);

  const toggleHistoryPreview = useCallback((entry: MaskHistoryEntry) => {
    const previewing = historyPreviewId === entry.id;
    setHistoryPreviewId(previewing ? null : entry.id);
    maskAuditRef.current('mask_event', {
      action: previewing ? 'history_preview_closed' : 'history_preview_opened',
      history_entry_id: entry.id,
      displayed_on_canvas: !previewing,
      ...summarizeMaskForAudit(entry.override),
    });
  }, [historyPreviewId]);

  const handleSave = async () => {
    const ok = await persistOverride('manual_save');
    if (ok) {
      // Doctor action record: compact edit save with full-video frame count.
      recordDoctorWorkflowStep(
        'save_edit',
        mediaMode === 'video' ? '保存编辑（含全部视频帧轮廓）' : '保存编辑',
        'completed',
        {
          output: {
            video_frames: videoFrameOverridesRef.current.length,
            lesion_points: pointsRef.current.length,
            lumen_points: lumenPolygonRef.current.length,
          },
        },
      );
      setMessage(
        zh
          ? (mediaMode === 'video' && videoFrameOverridesRef.current.length
            ? `已保存编辑：${videoFrameOverridesRef.current.length} 帧轮廓 + 操作记录`
            : '已保存编辑并记录操作')
          : (mediaMode === 'video' && videoFrameOverridesRef.current.length
            ? `Edit saved: ${videoFrameOverridesRef.current.length} frame masks + action log`
            : 'Edit saved with action log'),
      );
    }
  };

  const handleClear = async () => {
    if (!patient) return;
    setSaving(true);
    try {
      await fetch(
        `/api/patients/mask-overrides?patientId=${encodeURIComponent(patient.patient_id)}&frameId=${encodeURIComponent(patient.id)}`,
        { method: 'DELETE' },
      );
      generatedLesionRef.current = [];
      setPoints([]);
      pointsRef.current = [];
      setWallPoints([]);
      wallPointsRef.current = [];
      setViewFocusBox(null);
      setViewFocusMode(null);
      videoFrameOverridesRef.current = [];
      setVideoFrameOverrides([]);
      clearSamPrompts();
      setNnInteractiveMode(false);
      nnInteractiveSessionRef.current = { key: '', id: '', initialized: false };
      setSimplePromptBox(null);
      setLayerResult(null);
      onImagingAssist?.(null);
      onOverrideChange(null);
      maskAuditRef.current('mask_event', {
        action: 'mask_cleared',
        success: true,
        displayed_on_canvas: false,
      });
      setMessage(zh ? '已清除覆盖，将使用模型分割' : 'Override cleared; model seg will be used');
    } catch (err) {
      maskAuditRef.current('error', {
        operation: 'mask_clear',
        error: err instanceof Error ? err.message.slice(0, 240) : 'Clear failed',
      });
      setMessage(err instanceof Error ? err.message : 'Clear failed');
    } finally {
      setSaving(false);
    }
  };

  const openEditor = useCallback((opts?: { videoSam?: boolean; sam?: boolean; keyframes?: boolean }) => {
    if (opts?.videoSam) setPendingOpenVideoSam(true);
    if (opts?.keyframes) setPendingKeyframeRequest(true);
    if (opts?.videoSam || opts?.keyframes) setMediaMode('video');
    if (opts?.sam && !opts?.videoSam && !opts?.keyframes) setMediaMode('image');
    const useSam = Boolean(opts?.videoSam || opts?.sam);
    setMode(useSam ? 'sam' : 'soft');
    clearSamPrompts();
    setNnInteractiveMode(false);
    nnInteractiveSessionRef.current = { key: '', id: '', initialized: false };
    setSamBoxPreview(null);
    setSimplePromptBox(null);
    // Keep dense contours — soft-deform uses sparse control handles (direction_demo)
    setOpen(true);
    maskAuditRef.current('mask_event', {
      action: 'editor_opened',
      mode: useSam ? 'sam' : 'soft',
      media_mode: opts?.videoSam || opts?.keyframes ? 'video' : opts?.sam ? 'image' : 'current',
      keyframe_request: Boolean(opts?.keyframes),
    });
    setMessage(
      useSam
        ? (zh
          ? '点击画面标记关注区域，系统返回当前帧结果'
          : 'Click the frame to get the current-frame result')
        : (zh
          ? '拖橙/绿控制点软变形边界（同人机互助 HTML）; 硬拖/加点/删点为辅助'
          : 'Drag orange/green handles to soft-deform (same as HTML demo)'),
    );
  }, [clearSamPrompts, zh]);

  // AssistHub / external open request (additive; floating buttons unchanged)
  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<{ videoSam?: boolean; sam?: boolean; keyframes?: boolean }>).detail;
      openEditor(detail || { sam: true });
    };
    window.addEventListener('gastric:open-boundary-edit', handler);
    return () => window.removeEventListener('gastric:open-boundary-edit', handler);
  }, [openEditor]);

  const simplifyActiveLayer = useCallback(() => {
    const src = activeLayer === 'wall' ? wallPoints : points;
    if (src.length < 8) return;
    pushEditUndo();
    const next = prepareEditableContour(
      src,
      activeLayer === 'wall' ? WALL_SIMPLIFY_TARGET : LESION_SIMPLIFY_TARGET,
    );
    if (activeLayer === 'wall') {
      wallPointsRef.current = next;
      setWallPoints(next);
    } else {
      pointsRef.current = next;
      setPoints(next);
    }
    setMode('soft');
    setMessage(
      zh
        ? `已弧长重采样为 ${next.length} 点, 控制手柄 ${controlIndices(next.length, activeLayer === 'wall' ? WALL_CTRL_COUNT : LESION_CTRL_COUNT).length} 个`
        : `Resampled to ${next.length} pts with sparse control handles`,
    );
  }, [activeLayer, points, wallPoints, zh, pushEditUndo]);

  if (!patient) return null;

  const lesionReady = getCurrentTrackedPolygon().length >= 3;
  const lumenReady = Boolean(lumenBox || lumenPolygon.length >= 3);
  const videoTrackReady = trackingPrepared && videoFrameOverrides.length > 0;

  const modal = open ? (
        <div className={inline
          ? 'pointer-events-auto absolute inset-0 z-[120] flex min-h-0 min-w-0 items-stretch justify-stretch overflow-hidden bg-[#080b0f]'
          : 'pointer-events-auto fixed inset-0 z-[150000] flex items-center justify-center bg-black/85 p-3 backdrop-blur-sm'}>
          <div className={inline
            ? 'relative flex h-full w-full min-h-0 min-w-0 flex-col overflow-hidden bg-black'
            : 'flex h-[min(94vh,920px)] w-[min(1380px,98vw)] flex-col overflow-hidden rounded-2xl border border-cyan-400/25 bg-slate-950 shadow-2xl'}>
            <div className={`workbench-toolbar flex min-w-0 flex-wrap items-center justify-between gap-3 border-b border-white/10 bg-black px-3 ${simpleVideoMode ? 'py-1.5' : 'py-3'}`}>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-bold text-slate-100">
                  {simpleVideoMode
                    ? (patient.id_short || patient.patient_id || 'Case')
                    : (zh ? (mediaMode === 'video' ? '视频工具' : '静态图分割') : (mediaMode === 'video' ? 'Video tools' : 'Static image segmentation'))}
                </div>
                <div className="mt-0.5 truncate text-[10px] text-slate-500">
                  {simpleVideoMode
                    ? (videos.find((video) => video.url === videoUrl)?.filename || videoUrl || (zh ? '病例视频' : 'Case video'))
                    : `${patient.id_short}, ${zh
                      ? mediaMode === 'video'
                        ? '当前帧证据与 ROI 工具'
                        : '当前静态图，点击或框选病灶'
                      : mediaMode === 'video'
                        ? 'Current-frame evidence and ROI tools'
                        : 'Current image, click or box the lesion'}`}
                </div>
              </div>
              <div className={simpleVideoMode ? 'hidden' : 'flex min-w-0 flex-wrap items-center justify-end gap-2'}>
                  <button
                    type="button"
                    disabled={dinoBusy}
                    onClick={() => void extractDinoFeatures()}
                    className="rounded-lg border border-amber-300/50 bg-amber-400/10 px-2.5 py-1.5 text-[11px] font-semibold text-amber-100 disabled:opacity-40"
                    title={zh ? '提取当前帧区域特征' : 'Extract current-frame region features'}
                  >
                    {dinoBusy ? (zh ? '特征提取中' : 'Extracting') : dinoResult?.available ? (zh ? '区域特征 ✓' : 'Features ✓') : (zh ? '区域特征' : 'Region features')}
                  </button>
                  {mediaMode === 'video' && (
                    <>
                      <button
                        type="button"
                        disabled={!videoUrl || propagateBusy || points.length < 3}
                        onClick={() => void propagateMaskAcrossVideo()}
                        className="rounded-lg border border-emerald-300/50 bg-emerald-400/10 px-2.5 py-1.5 text-[11px] font-semibold text-emerald-100 disabled:opacity-40"
                      >
                        {propagateBusy ? (zh ? '扩散中' : 'Propagating') : (zh ? '跟踪扩散' : 'Track video')}
                      </button>
                    </>
                  )}
                  {!simpleVideoMode && (
                    <>
                      <button
                        type="button"
                        disabled={undoLen <= 0}
                        onClick={undoEdit}
                        className="rounded-lg border border-white/15 px-2.5 py-1.5 text-[11px] text-slate-200 disabled:opacity-40"
                      >
                        {zh ? `撤销 (${undoLen})` : `Undo (${undoLen})`}
                      </button>
                      <button
                        type="button"
                        disabled={!hasOriginal}
                        onClick={restoreOriginal}
                        className="rounded-lg border border-white/15 px-2.5 py-1.5 text-[11px] text-slate-200 disabled:opacity-40"
                      >
                        {zh ? '恢复原始' : 'Restore'}
                      </button>
                    </>
                  )}
                  {!inline && (
                    <button
                      type="button"
                      onClick={() => setOpen(false)}
                      className="rounded-lg border border-white/15 p-2 text-slate-300 hover:bg-white/5"
                      aria-label={zh ? '关闭分割编辑器' : 'Close segmentation editor'}
                    >
                      <X size={16} />
                    </button>
                  )}
              </div>
              {inline && (
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  className="flex items-center gap-1.5 rounded-lg border border-white/15 px-2.5 py-1.5 text-[11px] text-slate-300 hover:bg-white/5"
                  aria-label={zh ? '收起分割编辑器' : 'Close segmentation editor'}
                >
                  <X size={14} />
                  {zh ? '收起' : 'Close'}
                </button>
              )}
            </div>

            {!simpleVideoMode && (
            <div className="workbench-toolbar flex flex-wrap items-center gap-2 border-b border-white/10 px-4 py-2">
              {([
                ['soft', zh ? '软变形' : 'Soft', MousePointer2],
                ['hard', zh ? '硬拖点' : 'Hard', Pencil],
                ['add', zh ? '加点' : 'Add', Plus],
                ['delete', zh ? '删点' : 'Delete', Eraser],
                ['sam', zh ? '标记关注区域' : 'Mark region', Sparkles],
              ] as const).map(([id, label, Icon]) => (
                <button
                  key={id}
                  type="button"
                  disabled={id === 'sam' && samAvailable === false}
                  onClick={() => {
                    setMode(id);
                    setNnInteractiveMode(false);
                    nnInteractiveRequestRef.current += 1;
                    setNnInteractiveBusy(false);
                    nnInteractiveSessionRef.current = { key: '', id: '', initialized: false };
                    if (id === 'sam') {
                      setSimplePromptMode('point');
                      setActiveSamPromptLabel('positive');
                      setMessage(
                        zh
                          ? '点击画面标记关注区域'
                          : 'Click the frame to mark a region',
                      );
                    }
                  }}
                  className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] ${
                    mode === id
                      ? 'border-cyan-400/50 bg-cyan-500/20 text-cyan-100'
                      : 'border-white/10 text-slate-300 hover:bg-white/5'
                  } disabled:opacity-40`}
                >
                  <Icon size={13} />
                  {label}
                </button>
              ))}
              <button
                type="button"
                disabled={getCurrentTrackedPolygon().length < 3 || nnInteractiveBusy}
                onClick={() => {
                  activateNnInteractive('lesion');
                }}
                className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] disabled:opacity-40 ${
                  nnInteractiveMode
                    ? 'border-lime-300/70 bg-lime-500/30 text-lime-50'
                    : 'border-lime-400/40 bg-lime-500/15 text-lime-100 hover:bg-lime-500/25'
                }`}
                title={zh ? '用当前病灶边界启动辅助精修' : 'Refine the current lesion boundary'}
              >
                {nnInteractiveBusy ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
                {nnInteractiveBusy ? (zh ? '边界精修中' : 'Refining') : (zh ? '边界精修' : 'Refine boundary')}
              </button>
              <div className="flex items-center gap-1 rounded-lg border border-emerald-400/25 bg-emerald-500/5 px-1 py-0.5">
                <span className="px-1 text-[10px] font-semibold text-emerald-200">nnInteractive</span>
                <button
                  type="button"
                  onClick={() => {
                    setActiveSamPromptLabel('positive');
                    activateActiveSamPrompt('point');
                  }}
                  className={`rounded px-1.5 py-1 text-[10px] ${activeSamPromptLabel === 'positive' ? 'bg-emerald-400/25 text-emerald-50' : 'text-slate-400 hover:bg-white/10'}`}
                >
                  {zh ? '正点' : '+ Point'}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setActiveSamPromptLabel('negative');
                    activateActiveSamPrompt('point');
                  }}
                  className={`rounded px-1.5 py-1 text-[10px] ${activeSamPromptLabel === 'negative' ? 'bg-rose-400/25 text-rose-50' : 'text-slate-400 hover:bg-white/10'}`}
                >
                  {zh ? '负点' : '- Point'}
                </button>
                <button
                  type="button"
                  disabled={nnInteractiveAvailable !== true || nnInteractiveBusy}
                  onClick={() => activateActiveSamPrompt('scribble')}
                  className={`rounded px-1.5 py-1 text-[10px] ${simplePromptMode === 'scribble' ? 'bg-emerald-400/25 text-emerald-50' : 'text-slate-400 hover:bg-white/10'}`}
                >
                  {zh ? '涂鸦' : 'Scribble'}
                </button>
                <button
                  type="button"
                  disabled={nnInteractiveAvailable !== true || nnInteractiveBusy}
                  onClick={() => activateActiveSamPrompt('lasso')}
                  className={`rounded px-1.5 py-1 text-[10px] ${simplePromptMode === 'lasso' ? 'bg-cyan-400/25 text-cyan-50' : 'text-slate-400 hover:bg-white/10'}`}
                >
                  {zh ? '套索' : 'Lasso'}
                </button>
                {promptStrokes.length ? (
                  <span className="px-1 text-[9px] text-slate-500">{promptStrokes.length}</span>
                ) : null}
              </div>
              {mode === 'sam' && (
                <button
                  type="button"
                  onClick={() => {
                    clearSamPrompts();
                    setNnInteractiveMode(false);
                    setNnInteractiveTarget('lesion');
                    nnInteractiveSessionRef.current = { key: '', id: '', initialized: false };
                    setMessage(zh ? '已清除关注标记' : 'Region markers cleared');
                  }}
                  className="rounded-lg border border-rose-400/40 bg-rose-500/10 px-2.5 py-1.5 text-[11px] text-rose-100"
                >
                  {zh
                    ? `清除提示 (${samClicks.length + promptStrokes.length})`
                    : `Clear prompts (${samClicks.length + promptStrokes.length})`}
                </button>
              )}
              <button
                type="button"
                disabled={activePoints.length < 8}
                onClick={simplifyActiveLayer}
                className="rounded-lg border border-amber-400/40 bg-amber-500/10 px-2.5 py-1.5 text-[11px] text-amber-100 disabled:opacity-40"
                title={zh ? '弧长重采样稠密轮廓（不砍成稀少折线）' : 'Arc-length resample dense contour'}
              >
                {zh ? '重采样' : 'Resample'}
              </button>
              <div className="h-5 w-px bg-white/10" />
              <button
                type="button"
                onClick={() => setActiveLayer('wall')}
                className={`rounded-lg border px-2.5 py-1.5 text-[11px] ${
                  activeLayer === 'wall'
                    ? 'border-orange-400/50 bg-orange-500/20 text-orange-100'
                    : 'border-white/10 text-slate-300'
                }`}
              >
                {zh ? '橙, 胃壁' : 'Orange wall'} ({wallPoints.length})
              </button>
              <button
                type="button"
                onClick={() => setActiveLayer('lesion')}
                className={`rounded-lg border px-2.5 py-1.5 text-[11px] ${
                  activeLayer === 'lesion'
                    ? 'border-cyan-400/50 bg-cyan-500/20 text-cyan-100'
                    : 'border-white/10 text-slate-300'
                }`}
              >
                {zh ? '青, 病灶' : 'Cyan lesion'} ({points.length})
              </button>
              <button
                type="button"
                disabled={points.length < 3 && !layerResult}
                onClick={() => setWallAnalysisOpen((value) => !value)}
                className={`flex items-center gap-1 rounded-lg border px-2.5 py-1.5 text-[11px] ${
                  wallAnalysisOpen
                    ? 'border-emerald-400/50 bg-emerald-500/20 text-emerald-100'
                    : 'border-white/10 text-slate-300 hover:bg-white/5'
                } disabled:opacity-40`}
              >
                <Layers size={13} />
                    {wallAnalysisOpen ? (zh ? '关闭组织层观察' : 'Close tissue view') : (zh ? '组织层观察' : 'Tissue view')}
              </button>
              <div className="h-5 w-px bg-white/10" />
              <button
                type="button"
                disabled={lumenBusy || !patient}
                onClick={() => {
                  prepareLumenDetection();
                  void detectLumen();
                }}
                className="flex items-center gap-1.5 rounded-lg border border-fuchsia-400/40 bg-fuchsia-500/10 px-2.5 py-1.5 text-[11px] text-fuchsia-100 disabled:opacity-40"
                title={zh ? 'YOLO 检测当前帧胃腔框' : 'YOLO lumen box on current frame'}
              >
                {lumenBusy ? <Loader2 size={13} className="animate-spin" /> : <ScanSearch size={13} />}
                {zh ? '检测胃腔' : 'Detect lumen'}
              </button>
              <button
                type="button"
                onClick={toggleLumenBoxEdit}
                className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] ${
                  lumenEditMode
                    ? 'border-fuchsia-400/50 bg-fuchsia-500/20 text-fuchsia-100'
                    : 'border-white/10 text-slate-300'
                }`}
              >
                <Pencil size={13} />
                {lumenEditMode ? (zh ? '完成调整' : 'Done') : (zh ? '调胃腔框' : 'Edit lumen')}
              </button>
              <button
                type="button"
                disabled={!lumenBox || lumenSamBusy}
                onClick={() => void segmentLumenWithSam31()}
                className="flex items-center gap-1.5 rounded-lg border border-fuchsia-400/40 bg-fuchsia-500/10 px-2.5 py-1.5 text-[11px] text-fuchsia-100 disabled:opacity-40"
                title={zh ? '以当前胃腔框生成胃腔轮廓' : 'Segment lumen from current box'}
              >
                {lumenSamBusy ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
                {zh ? '分割胃腔' : 'Segment lumen'}
              </button>
              <button
                type="button"
                disabled={lumenSaving || (!lumenBox && lumenPolygon.length < 3)}
                onClick={() => void handleSaveLumen()}
                className="flex items-center gap-1.5 rounded-lg border border-fuchsia-400/40 bg-fuchsia-500/15 px-2.5 py-1.5 text-[11px] text-fuchsia-100 disabled:opacity-40"
              >
                {lumenSaving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
                {zh ? '保存胃腔' : 'Save lumen'}
              </button>
              <div className="h-5 w-px bg-white/10" />
              <button
                type="button"
                onClick={() => setMediaMode('image')}
                className={`rounded-lg border px-2.5 py-1.5 text-[11px] ${
                  mediaMode === 'image'
                    ? 'border-cyan-400/50 bg-cyan-500/20 text-cyan-100'
                    : 'border-white/10 text-slate-300'
                }`}
              >
                {zh ? '静图' : 'Image'}
              </button>
              <button
                type="button"
                onClick={() => {
                  if (videos.length) openPatientVideoSam();
                  else setMediaMode('video');
                }}
                className={`flex items-center gap-1 rounded-lg border px-2.5 py-1.5 text-[11px] ${
                  mediaMode === 'video'
                    ? 'border-violet-400/50 bg-violet-500/20 text-violet-100'
                    : 'border-white/10 text-slate-300'
                }`}
              >
                <Video size={13} />
                {zh ? `视频工具${videos.length ? ` (${videos.length})` : ''}` : `Video tools${videos.length ? ` (${videos.length})` : ''}`}
              </button>
              <div className="ml-auto flex items-center gap-2 text-[10px] text-slate-400">
                <span>{zh ? '模型' : 'Model'}</span>
                <select
                  value={segmentationModel}
                  onChange={(e) => setSegmentationModel(e.target.value as LesionSegmentationModel)}
                  className="rounded border border-white/15 bg-black/40 px-2 py-1 text-[11px] text-slate-200"
                  aria-label={zh ? '静态分割模型' : 'Static segmentation model'}
                >
                  <option value="sabm_sam2_guided">{zh ? '引导式分割' : 'Guided segmentation'}</option>
                  <option value="sam31">{zh ? '概念分割' : 'Concept segmentation'}</option>
                  <option value="dinov3">{zh ? '区域特征分割' : 'Region-feature segmentation'}</option>
                  <option value="convnext">{zh ? '卷积分割' : 'Conv segmentation'}</option>
                </select>
                <span>ROI</span>
                <select
                  value={roiMode}
                  onChange={(e) => setRoiMode(e.target.value as typeof roiMode)}
                  className="rounded border border-white/15 bg-black/40 px-2 py-1 text-[11px] text-slate-200"
                >
                  <option value="predicted">{zh ? '编辑框' : 'Edited bbox'}</option>
                  <option value="doctor">{zh ? '磁盘医生 ROI' : 'Disk doctor ROI'}</option>
                  <option value="auto">Auto</option>
                </select>
              </div>
            </div>
            )}

            {mediaMode === 'video' && (
              <>
              {/* Simple video mode keeps the left and right rails as the single tool surface. */}
              <div className={simpleVideoMode ? 'hidden' : ''}>
              {simpleVideoMode ? (
                <>
                  {simpleToolsOpen && (
                    <div className="workbench-toolbar flex min-w-0 flex-wrap items-center gap-1.5 border-b border-white/10 bg-black/80 px-4 py-2">
                      <div className="flex min-w-0 flex-wrap items-center gap-1.5">
                        {onUnifiedAgentRun ? (
                          <button
                            type="button"
                            disabled={!videoUrl || workflowBusy || unifiedAgentBusy}
                            onClick={() => void runDoctorWorkflow()}
                            className="flex items-center gap-1.5 rounded-lg border border-amber-300/50 bg-amber-400/15 px-2.5 py-1.5 text-[11px] font-semibold text-amber-100 hover:bg-amber-400/25 disabled:opacity-40"
                            title={zh ? '按医生轨迹自动完成检测、精修、跟踪和报告' : 'Run the doctor workflow from detection through report'}
                          >
                            {workflowBusy ? <Loader2 size={13} className="animate-spin" /> : <Workflow size={13} />}
                            {workflowBusy ? (workflowStepLabel || (zh ? '医生式流程中' : 'Doctor workflow')) : (zh ? '医生式全流程' : 'Doctor workflow')}
                          </button>
                        ) : null}
                        <span className="mr-1 hidden text-[10px] font-semibold uppercase tracking-wide text-cyan-300/80 sm:inline">
                          {zh ? '病灶' : 'Lesion'}
                        </span>
                        <button
                          type="button"
                          onClick={enterSimpleBoxPrompt}
                          className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] ${
                            simplePromptMode === 'box' && !simpleEditMode && !lumenEditMode
                              ? 'border-cyan-300/70 bg-cyan-500/35 text-cyan-50'
                              : 'border-cyan-400/40 bg-cyan-500/15 text-cyan-100 hover:bg-cyan-500/25'
                          }`}
                        >
                          <ScanLine size={13} />
                          {zh ? '框选病灶' : 'Box lesion'}
                        </button>
                        <button
                          type="button"
                          disabled={!videoUrl || lesionAutoBusy || workflowBusy}
                          onClick={() => void autoDetectLesion()}
                          className="flex items-center gap-1.5 rounded-lg border border-cyan-300/40 bg-cyan-500/10 px-2.5 py-1.5 text-[11px] text-cyan-100 hover:bg-cyan-500/20 disabled:opacity-40"
                          title={zh ? '用全图候选模型先定位病灶，再用正负点确认' : 'Find a full-frame lesion candidate, then confirm it with positive and negative points'}
                        >
                          {lesionAutoBusy ? <Loader2 size={13} className="animate-spin" /> : <ScanSearch size={13} />}
                          {lesionAutoBusy ? (zh ? '寻找中' : 'Finding') : (zh ? '自动找病灶' : 'Auto-find lesion')}
                        </button>
                        <button
                          type="button"
                          disabled={getCurrentTrackedPolygon().length < 3 || nnInteractiveBusy}
                          onClick={() => {
                            activateNnInteractive('lesion');
                          }}
                          className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] disabled:opacity-40 ${
                            nnInteractiveMode
                              ? 'border-lime-300/70 bg-lime-500/30 text-lime-50'
                              : 'border-lime-400/40 bg-lime-500/15 text-lime-100 hover:bg-lime-500/25'
                          }`}
                          title={zh ? '用当前病灶边界启动辅助精修' : 'Refine the current lesion boundary'}
                        >
                          {nnInteractiveBusy ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
                          {nnInteractiveBusy ? (zh ? '边界精修中' : 'Refining') : (zh ? '边界精修' : 'Refine boundary')}
                        </button>
                        {nnInteractiveAvailable !== null ? (
                          <span
                            className={`rounded-md border px-2 py-1 text-[10px] ${
                              nnInteractiveAvailable
                                ? 'border-lime-300/30 bg-lime-500/10 text-lime-200'
                                : 'border-amber-300/25 bg-amber-500/10 text-amber-200'
                            }`}
                            title={nnInteractiveAvailable
                              ? (zh ? '边界辅助服务已连接' : 'Boundary assistance is ready')
                              : (zh ? '请先启动边界辅助服务' : 'Start the boundary assistance service first')}
                          >
                            {nnInteractiveAvailable
                              ? (zh ? '辅助已连接' : 'Assistance ready')
                              : (zh ? '辅助未连接' : 'Assistance offline')}
                          </span>
                        ) : null}
                        <div className="flex items-center gap-1 rounded-lg border border-emerald-400/25 bg-emerald-500/5 px-1 py-0.5">
                          <span className="px-1 text-[10px] font-semibold text-emerald-200">nnInteractive</span>
                          <button
                            type="button"
                            onClick={() => {
                              setActiveSamPromptLabel('positive');
                              activateActiveSamPrompt('point');
                            }}
                            className={`rounded px-1.5 py-1 text-[10px] ${simplePromptMode === 'point' && activeSamPromptLabel === 'positive' && nnInteractiveMode ? 'bg-emerald-400/25 text-emerald-50' : 'text-slate-400 hover:bg-white/10'}`}
                          >
                            {zh ? '正点' : '+ Point'}
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              setActiveSamPromptLabel('negative');
                              activateActiveSamPrompt('point');
                            }}
                            className={`rounded px-1.5 py-1 text-[10px] ${simplePromptMode === 'point' && activeSamPromptLabel === 'negative' && nnInteractiveMode ? 'bg-rose-400/25 text-rose-50' : 'text-slate-400 hover:bg-white/10'}`}
                          >
                            {zh ? '负点' : '- Point'}
                          </button>
                          <button
                            type="button"
                            disabled={nnInteractiveAvailable !== true || nnInteractiveBusy}
                            onClick={() => activateActiveSamPrompt('scribble')}
                            className={`rounded px-1.5 py-1 text-[10px] ${simplePromptMode === 'scribble' && nnInteractiveMode ? 'bg-emerald-400/25 text-emerald-50' : 'text-slate-400 hover:bg-white/10'}`}
                          >
                            {zh ? '涂鸦' : 'Scribble'}
                          </button>
                          <button
                            type="button"
                            disabled={nnInteractiveAvailable !== true || nnInteractiveBusy}
                            onClick={() => activateActiveSamPrompt('lasso')}
                            className={`rounded px-1.5 py-1 text-[10px] ${simplePromptMode === 'lasso' && nnInteractiveMode ? 'bg-cyan-400/25 text-cyan-50' : 'text-slate-400 hover:bg-white/10'}`}
                          >
                            {zh ? '套索' : 'Lasso'}
                          </button>
                        </div>
                        <button
                          type="button"
                          disabled={points.length < 3 && wallPoints.length < 3}
                          onClick={toggleSimpleContourEdit}
                          className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] disabled:opacity-40 ${
                            simpleEditMode
                              ? 'border-emerald-300/70 bg-emerald-500/35 text-emerald-50'
                              : 'border-emerald-400/40 bg-emerald-500/15 text-emerald-100 hover:bg-emerald-500/25'
                          }`}
                        >
                          <Pencil size={13} />
                          {simpleEditMode ? (zh ? '完成编辑' : 'Done') : (zh ? '编辑轮廓' : 'Edit contour')}
                        </button>
                        <button
                          type="button"
                          disabled={saving}
                          onClick={() => void handleClear()}
                          className="flex items-center gap-1.5 rounded-lg border border-slate-400/35 bg-slate-500/15 px-2.5 py-1.5 text-[11px] text-slate-200 hover:bg-slate-500/25 disabled:opacity-40"
                        >
                          <RotateCcw size={13} />
                          {zh ? '重置' : 'Reset'}
                        </button>
                        <button
                          type="button"
                          disabled={points.length < 3 && !lumenBox && lumenPolygon.length < 3}
                          onClick={toggleZoomRoi}
                          className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] disabled:opacity-40 ${
                            viewFocusBox
                              ? 'border-cyan-300/70 bg-cyan-500/35 text-cyan-50'
                              : 'border-indigo-400/40 bg-indigo-500/15 text-indigo-100 hover:bg-indigo-500/25'
                          }`}
                          title={zh ? '放大至病灶/胃腔 ROI' : 'Zoom to lesion/lumen ROI'}
                        >
                          <ZoomIn size={13} />
                          {viewFocusBox ? (zh ? '退出放大' : 'Exit zoom') : (zh ? '放大 ROI' : 'Zoom ROI')}
                        </button>
                        <button
                          type="button"
                          disabled={!overlapFocus}
                          onClick={toggleOverlapZoom}
                          className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] disabled:opacity-40 ${
                            viewFocusMode === 'overlap'
                              ? 'border-amber-300/70 bg-amber-500/35 text-amber-50'
                              : 'border-amber-400/40 bg-amber-500/15 text-amber-100 hover:bg-amber-500/25'
                          }`}
                          title={zh ? '只放大病灶与胃腔轮廓的交叠/接触局部' : 'Zoom only to the lesion-lumen overlap or contact region'}
                        >
                          <ScanSearch size={13} />
                          {viewFocusMode === 'overlap' ? (zh ? '退出交叠放大' : 'Exit overlap') : (zh ? '放大交叠' : 'Zoom overlap')}
                        </button>
                      </div>

                      <div className="flex min-w-0 flex-wrap items-center justify-end gap-1.5">
                        <span className="mr-1 hidden text-[10px] font-semibold uppercase tracking-wide text-fuchsia-300/80 sm:inline">
                          {zh ? '胃腔 / 分析' : 'Lumen / analysis'}
                        </span>
                        <button
                          type="button"
                          disabled={lumenBusy || !patient}
                          onClick={() => {
                            prepareLumenDetection();
                            void detectLumen();
                          }}
                          className="flex items-center gap-1.5 rounded-lg border border-fuchsia-400/40 bg-fuchsia-500/10 px-2.5 py-1.5 text-[11px] text-fuchsia-100 disabled:opacity-40"
                        >
                          {lumenBusy ? <Loader2 size={13} className="animate-spin" /> : <ScanSearch size={13} />}
                          {zh ? '检测胃腔' : 'Detect lumen'}
                        </button>
                        <button
                          type="button"
                          onClick={toggleLumenBoxEdit}
                          className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] ${
                            lumenEditMode
                              ? 'border-fuchsia-400/50 bg-fuchsia-500/20 text-fuchsia-100'
                              : 'border-fuchsia-400/30 bg-fuchsia-500/10 text-fuchsia-100 hover:bg-fuchsia-500/20'
                          }`}
                        >
                          <Pencil size={13} />
                          {lumenEditMode ? (zh ? '完成调整' : 'Done') : (zh ? '调胃腔框' : 'Edit lumen')}
                        </button>
                        <button
                          type="button"
                          disabled={!lumenBox || lumenSamBusy}
                          onClick={() => void segmentLumenWithSam31()}
                          className="flex items-center gap-1.5 rounded-lg border border-fuchsia-400/40 bg-fuchsia-500/10 px-2.5 py-1.5 text-[11px] text-fuchsia-100 disabled:opacity-40"
                        >
                          {lumenSamBusy ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
                          {zh ? '分割胃腔' : 'Segment lumen'}
                        </button>
                        <button
                          type="button"
                          disabled={(!lumenBox && lumenPolygon.length < 3) || nnInteractiveBusy}
                          onClick={() => {
                            setActiveSamPromptLabel('positive');
                            activateNnInteractive('lumen');
                          }}
                          className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] disabled:opacity-40 ${
                            nnInteractiveMode && nnInteractiveTarget === 'lumen'
                              ? 'border-lime-300/70 bg-lime-500/30 text-lime-50'
                              : 'border-lime-400/40 bg-lime-500/10 text-lime-100 hover:bg-lime-500/20'
                          }`}
                          title={zh ? '用当前胃腔边界启动辅助精修' : 'Refine the current lumen boundary'}
                        >
                          {nnInteractiveBusy && nnInteractiveTarget === 'lumen' ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
                          {nnInteractiveBusy && nnInteractiveTarget === 'lumen' ? (zh ? '胃腔精修中' : 'Refining lumen') : (zh ? '精修胃腔' : 'Refine lumen')}
                        </button>
                        <button
                          type="button"
                          disabled={(!lumenBox && lumenPolygon.length < 3) || nnInteractiveAvailable !== true || nnInteractiveBusy}
                          onClick={() => activateActiveSamPrompt('scribble', 'lumen')}
                          className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] disabled:opacity-40 ${
                            simplePromptMode === 'scribble' && nnInteractiveTarget === 'lumen'
                              ? 'border-fuchsia-300/70 bg-fuchsia-500/30 text-fuchsia-50'
                              : 'border-fuchsia-400/30 bg-fuchsia-500/10 text-fuchsia-100 hover:bg-fuchsia-500/20'
                          }`}
                        >
                          <Pencil size={13} />
                          {zh ? '胃腔涂鸦' : 'Lumen scribble'}
                        </button>
                        <button
                          type="button"
                          disabled={(!lumenBox && lumenPolygon.length < 3) || nnInteractiveAvailable !== true || nnInteractiveBusy}
                          onClick={() => activateActiveSamPrompt('lasso', 'lumen')}
                          className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] disabled:opacity-40 ${
                            simplePromptMode === 'lasso' && nnInteractiveTarget === 'lumen'
                              ? 'border-fuchsia-300/70 bg-fuchsia-500/30 text-fuchsia-50'
                              : 'border-fuchsia-400/30 bg-fuchsia-500/10 text-fuchsia-100 hover:bg-fuchsia-500/20'
                          }`}
                        >
                          <CircleDot size={13} />
                          {zh ? '圈选修正' : 'Lasso correction'}
                        </button>
                        <button
                          type="button"
                          disabled={lumenSaving || (!lumenBox && lumenPolygon.length < 3)}
                          onClick={() => void handleSaveLumen()}
                          className="flex items-center gap-1.5 rounded-lg border border-fuchsia-400/40 bg-fuchsia-500/15 px-2.5 py-1.5 text-[11px] text-fuchsia-100 disabled:opacity-40"
                        >
                          {lumenSaving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
                          {zh ? '保存胃腔' : 'Save lumen'}
                        </button>
                        <div className="mx-0.5 hidden h-5 w-px bg-white/10 sm:block" />
                        <button
                          type="button"
                          disabled={points.length < 3}
                          onClick={openExplainableAnalysis}
                          className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] font-semibold disabled:opacity-40 ${
                            points.length >= 3
                              ? 'border-lime-400/50 bg-lime-500/25 text-lime-50 hover:bg-lime-500/35'
                              : 'border-white/10 bg-white/5 text-slate-500'
                          }`}
                          title={zh ? '可解释性边界分析（当前帧）' : 'Explainable boundary analysis (current frame)'}
                        >
                          <Brain size={13} />
                          {zh ? '边界分析' : 'Boundary'}
                        </button>
                        <button
                          type="button"
                          disabled={points.length < 3 && !layerResult}
                          onClick={() => {
                            freezeCurrentFrame();
                            setWallAnalysisOpen((value) => !value);
                          }}
                          className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] disabled:opacity-40 ${
                            wallAnalysisOpen
                              ? 'border-orange-300/70 bg-orange-500/35 text-orange-50'
                              : 'border-orange-400/40 bg-orange-500/15 text-orange-100 hover:bg-orange-500/25'
                          }`}
                          title={zh ? '组织层 / 胃壁突破可视化' : 'Tissue layer / wall breakthrough'}
                        >
                          <Layers size={13} />
                          {zh ? '胃壁突破' : 'Wall breakthrough'}
                        </button>
                        <button
                          type="button"
                          disabled={dinoBusy}
                          onClick={() => void extractDinoFeatures()}
                          className="flex items-center gap-1.5 rounded-lg border border-orange-400/40 bg-orange-500/15 px-2.5 py-1.5 text-[11px] text-orange-100 hover:bg-orange-500/25 disabled:opacity-40"
                        >
                          <BrainCircuit size={13} />
                          {dinoBusy ? (zh ? '特征中' : 'Features…') : (zh ? '区域特征' : 'Region features')}
                        </button>
                        <button
                          type="button"
                          disabled={samBusy || points.length < 3}
                          onClick={() => {
                            const center = polygonCentroid(points);
                            const currentBox = bboxFromPolygon(points);
                            if (center && currentBox) {
                              freezeCurrentFrame();
                              void runSamAtPoint(center, {
                                source: 'sam',
                                box: currentBox,
                                keepEditing: true,
                                stayInSam: true,
                                llmReport: true,
                              });
                            }
                          }}
                          className="flex items-center gap-1.5 rounded-lg border border-teal-400/40 bg-teal-500/15 px-2.5 py-1.5 text-[11px] text-teal-100 hover:bg-teal-500/25 disabled:opacity-40"
                        >
                          <ScanLine size={13} />
                          {samBusy ? (zh ? '分析中' : 'Analyzing') : (zh ? '结构证据' : 'Structure')}
                        </button>
                        {onUnifiedAgentRun ? (
                          <button
                            type="button"
                            disabled={!videoUrl || unifiedAgentBusy}
                            onClick={() => void runContourAnchoredAssist()}
                            className="flex items-center gap-1.5 rounded-lg border border-sky-400/40 bg-sky-500/15 px-2.5 py-1.5 text-[11px] text-sky-100 hover:bg-sky-500/25 disabled:opacity-40"
                          >
                            <Sparkles size={13} />
                            {unifiedAgentBusy ? (zh ? '分析中' : 'Running') : (zh ? '辅助意见' : 'Assist')}
                          </button>
                        ) : null}
                        <button
                          type="button"
                          onClick={() => setSimpleToolsOpen(false)}
                          className="flex items-center gap-1.5 rounded-lg border border-white/10 px-2.5 py-1.5 text-[11px] text-slate-400 hover:bg-white/5"
                          title={zh ? '隐藏工具栏' : 'Hide tools'}
                        >
                          <PanelTop size={13} />
                          {zh ? '收起' : 'Hide'}
                        </button>
                      </div>
                    </div>
                  )}
                  {!simpleToolsOpen && (
                    <button
                      type="button"
                      onClick={() => setSimpleToolsOpen(true)}
                      className="flex items-center gap-1.5 border-b border-white/10 bg-black/80 px-3 py-1.5 text-[11px] text-slate-300"
                    >
                      <PanelTop size={13} />
                      {zh ? '工具栏' : 'Tools'}
                    </button>
                  )}
                </>
              ) : (
              <div className="flex flex-wrap items-center gap-2 border-b border-white/10 bg-black/80 px-4 py-2">
                <select
                  value={videoUrl}
                  onChange={(e) => {
                    setVideoUrl(e.target.value);
                    setIsPlaying(false);
                  }}
                  className="max-w-[280px] rounded border border-white/15 bg-black/40 px-2 py-1 text-[11px] text-slate-200"
                >
                  <option value="">{zh ? '选择视频…' : 'Select video…'}</option>
                  {videos.map((v) => (
                    <option key={v.url} value={v.url}>
                      {v.filename}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  disabled={!videoUrl}
                  onClick={() => {
                    const v = videoRef.current;
                    if (!v) return;
                    if (v.paused) void v.play();
                    else v.pause();
                  }}
                  className="flex items-center gap-1 rounded-lg border border-violet-400/40 px-2.5 py-1.5 text-[11px] text-violet-100 disabled:opacity-40"
                >
                  {isPlaying ? <Pause size={13} /> : <Play size={13} />}
                  {isPlaying ? (zh ? '暂停' : 'Pause') : (zh ? '播放' : 'Play')}
                </button>
                <input
                  ref={(node) => { videoProgressRefs.current[0] = node; }}
                  type="range"
                  min={0}
                  max={Math.max(videoDuration, 0.01)}
                  step={0.01}
                  defaultValue={videoTime}
                  disabled={!videoUrl}
                  onPointerDown={beginVideoScrub}
                  onPointerUp={endVideoScrub}
                  onPointerCancel={endVideoScrub}
                  onChange={(e) => {
                    onVideoProgressChange(Number(e.target.value));
                  }}
                  className="video-progress min-w-[140px] flex-1"
                />
                <span className="font-mono text-[10px] text-violet-200/90">
                  <span ref={(node) => { videoTimeLabelRefs.current[0] = node; }}>{videoTime.toFixed(2)}</span>
                  s / {videoDuration.toFixed(2)}s
                </span>
                <label className="flex items-center gap-1.5 text-[10px] text-violet-100/90">
                  <input
                    type="checkbox"
                    checked={trackOnPlay}
                    disabled={frameFrozen}
                    onChange={(e) => {
                      setTrackOnPlay(e.target.checked);
                      if (e.target.checked) {
                        setFrameFrozen(false);
                        frameFrozenRef.current = false;
                      }
                    }}
                  />
                  {zh ? '播放时自动跟随' : 'Auto-track on play'}
                </label>
                <button
                  type="button"
                  disabled={!videoUrl || keyBusy || propagateBusy || points.length < 3}
                  onClick={() => void propagateMaskAcrossVideo()}
                  className="rounded-lg border border-emerald-400/40 bg-emerald-500/10 px-2 py-1 text-[10px] text-emerald-100 disabled:opacity-40"
                >
                  {propagateBusy
                    ? (zh ? `跟踪扩散 ${propagateProgress || ''}` : `Tracking ${propagateProgress || ''}`)
                    : (zh ? '跟踪扩散' : 'Track video')}
                </button>
                <button
                  type="button"
                  disabled={!videoUrl || samBusy || propagateBusy || points.length < 3}
                  onClick={() => {
                    freezeCurrentFrame();
                    const c = polygonCentroid(points);
                    const box = bboxFromPolygon(points);
                    if (c && box) void runSamAtPoint(c, { source: 'sam', box, keepEditing: true });
                    else setMessage(zh ? '请先点击视频画面获得当前帧结果' : 'Click the video frame first');
                  }}
                  className="rounded-lg border border-violet-400/40 px-2 py-1 text-[10px] text-violet-100 disabled:opacity-40"
                >
                  {zh ? '重新分析当前帧' : 'Re-analyze current frame'}
                </button>

                {frameFrozen && (
                  <button
                    type="button"
                    onClick={() => {
                      setFrameFrozen(false);
                      frameFrozenRef.current = false;
                      syncFrameFromVideo({ force: true });
                      redraw();
                      setMessage(zh ? '已解除帧冻结，可继续播放' : 'Frame unfrozen');
                    }}
                    className="rounded-lg border border-amber-400/40 px-2 py-1 text-[10px] text-amber-100"
                  >
                    {zh ? '解除冻结' : 'Unfreeze'}
                  </button>
                )}
                {!videos.length && (
                  <span className="text-[10px] text-amber-300/90">
                    {zh
                      ? '未命中 crop_ui/阅片库视频：可换病例或用样例目录'
                      : 'No crop_ui/reader video match — try another case or sample catalog'}
                  </span>
                )}
                {!!videos.length && mediaMode === 'video' && !videoUrl && (
                  <button
                    type="button"
                    onClick={openPatientVideoSam}
                    className="rounded-lg border border-violet-400/50 bg-violet-500/30 px-2 py-1 text-[10px] text-violet-50"
                  >
                    {zh ? '打开对应视频' : 'Open matched video'}
                  </button>
                )}
                {!videos.length && (
                  <button
                    type="button"
                    onClick={async () => {
                      const res = await fetch('/api/patients/videos?list=1&limit=30');
                      const data = await res.json();
                      const list = (data.videos || []).map((v: VideoInfo & { patient_key?: string }) => ({
                        url: v.url,
                        filename: v.filename,
                        treatment: v.treatment || 'direct_surgery',
                        water_filled: Boolean(v.water_filled),
                      }));
                      setVideos(list);
                      if (list[0]) setVideoUrl(list[0].url);
                    }}
                    className="rounded border border-white/15 px-2 py-1 text-[10px] text-slate-300"
                  >
                    {zh ? '载入样例视频' : 'Load sample videos'}
                  </button>
                )}
              </div>
              )}
              </div>
              </>
            )}


            <div className="relative min-h-0 flex-1 overflow-hidden bg-black">
              <div ref={containerRef} className="relative h-full w-full bg-black">
                {simpleVideoMode && mediaMode === 'video' && (
                  <div className="pointer-events-none absolute inset-x-2 top-3 z-[180] overflow-x-auto">
                    <div className="pointer-events-auto mx-auto flex min-w-full w-max items-center justify-center gap-1.5 pb-1">
                      {onUnifiedAgentRun ? (
                        <FloatingToolGroup accent="amber">
                          <FloatingToolButton
                            icon={workflowBusy ? <Loader2 size={14} className="animate-spin" /> : <Workflow size={14} />}
                            label={workflowBusy ? (workflowStepLabel || (zh ? '流程中' : 'Running')) : (zh ? '全流程' : 'Workflow')}
                            title={zh ? '自动完成病灶候选、中心正点、胃腔保护、整段跟踪和报告' : 'Run lesion detection, center refinement, lumen guard, tracking, and report'}
                            disabled={!videoUrl || workflowBusy || unifiedAgentBusy}
                            onClick={() => void runDoctorWorkflow()}
                            tone="amber"
                          />
                        </FloatingToolGroup>
                      ) : null}
                      <FloatingToolGroup accent="violet">
                        <FloatingToolButton
                          icon={precomputeBusy ? <Loader2 size={14} className="animate-spin" /> : <Video size={14} />}
                          label={
                            precomputeBusy
                              ? (zh ? `跟踪 ${precomputeProgress || ''}` : `Track ${precomputeProgress || ''}`)
                              : trackOnPlay
                                ? (zh ? '跟踪开' : 'Tracking')
                                : (trackingPrepared ? (zh ? '播放跟踪' : 'On play') : (zh ? '视频跟踪' : 'Track video'))
                          }
                          title={
                            points.length < 3
                              ? (zh ? '请先框选病灶' : 'Box lesion first')
                              : (!lumenBox && lumenPolygon.length < 3)
                                ? (zh ? '请先检测或调整胃腔框' : 'Detect or adjust the lumen box first')
                                : (zh ? '整段预计算病灶和胃腔跟踪' : 'Precompute lesion and lumen tracking for the full video')
                          }
                          disabled={points.length < 3 || precomputeBusy || (!lumenBox && lumenPolygon.length < 3)}
                          active={trackOnPlay}
                          onClick={() => {
                            if (!trackingPrepared) void precomputeVideoTracking();
                            else setTrackOnPlay((value) => !value);
                          }}
                          tone="violet"
                        />
                        {trackingPrepared && videoFrameOverrides.length > 0 ? (
                          <span className="mr-1 rounded bg-white/10 px-1 py-0.5 font-mono text-[9px] text-violet-100">
                            {videoFrameOverrides.length}f
                          </span>
                        ) : null}
                      </FloatingToolGroup>
                      {onUnifiedAgentRun ? (
                        <FloatingToolGroup accent="sky">
                          <FloatingToolButton
                            icon={unifiedAgentBusy ? <Loader2 size={15} className="animate-spin" /> : <Sparkles size={15} />}
                            label={unifiedAgentBusy ? (zh ? '诊断中' : 'Diagnosing') : (zh ? '辅助意见' : 'Assist')}
                            title={zh ? '轮廓锚定诊断：确认病灶与胃腔后生成 T 分期证据' : 'Contour-anchored diagnosis after lesion and lumen are ready'}
                            disabled={!videoUrl || unifiedAgentBusy || workflowBusy || precomputeBusy}
                            onClick={() => void runContourAnchoredAssist()}
                            tone="sky"
                            emphasize
                          />
                        </FloatingToolGroup>
                      ) : null}
                    </div>
                  </div>
                )}
                {simpleVideoMode && simpleToolsOpen ? (
                  <>
                    <div className="pointer-events-none absolute top-2 bottom-2 left-2 z-[140] flex flex-col items-center justify-center gap-1.5 sm:top-3 sm:bottom-3 sm:left-3">
                      <div className="workbench-tool-rail pointer-events-auto max-h-full rounded-lg border border-white/10 bg-black/70 p-1 shadow-2xl shadow-black/40 backdrop-blur-md">
                        <ToolRailSectionTitle>{zh ? '病灶' : 'Lesion'}</ToolRailSectionTitle>
                        <ToolRailButton
                          icon={<ScanLine size={15} />}
                          label={zh ? '框选病灶' : 'Box lesion'}
                          hint={zh ? '拖框后自动分割' : 'Drag box to segment'}
                          active={simplePromptMode === 'box' && !simpleEditMode && !lumenEditMode}
                          onClick={enterSimpleBoxPrompt}
                          side="left"
                          tone="cyan"
                        />
                        <ToolRailButton
                          icon={lesionAutoBusy ? <Loader2 size={15} className="animate-spin" /> : <ScanSearch size={15} />}
                          label={zh ? '自动找病灶' : 'Auto-find'}
                          hint={zh ? '候选定位并分割' : 'Find and segment'}
                          disabled={!videoUrl || lesionAutoBusy || workflowBusy}
                          onClick={() => void autoDetectLesion()}
                          side="left"
                          tone="cyan"
                        />
                        <ToolRailButton
                          icon={<Pencil size={15} />}
                          label={simpleEditMode ? (zh ? '完成编辑' : 'Done') : (zh ? '编辑轮廓' : 'Edit')}
                          hint={zh ? '拖控制点微调' : 'Drag control points'}
                          disabled={points.length < 3 && wallPoints.length < 3}
                          active={simpleEditMode}
                          onClick={toggleSimpleContourEdit}
                          side="left"
                          tone="emerald"
                        />
                        <ToolRailButton
                          icon={<RotateCcw size={15} />}
                          label={zh ? '重置' : 'Reset'}
                          hint={zh ? '清除本帧覆盖' : 'Clear this frame'}
                          disabled={saving}
                          onClick={() => void handleClear()}
                          side="left"
                          tone="slate"
                        />
                        <ToolRailDivider />
                        <ToolRailSectionTitle>{zh ? '查看' : 'View'}</ToolRailSectionTitle>
                        <ToolRailButton
                          icon={<ZoomIn size={15} />}
                          label={magnifierOn ? (zh ? '关放大镜' : 'Lens off') : (zh ? '放大镜' : 'Lens')}
                          hint={zh ? '局部高倍细节' : 'Local high zoom'}
                          active={magnifierOn}
                          onClick={toggleMagnifier}
                          side="left"
                          tone="sky"
                        />
                        <ToolRailButton
                          icon={<ZoomIn size={15} />}
                          label={viewFocusBox ? (zh ? '退出放大' : 'Exit zoom') : (zh ? '放大区域' : 'Zoom ROI')}
                          hint={zh ? '聚焦病灶胃腔' : 'Focus lesion/lumen'}
                          disabled={points.length < 3 && !lumenBox && lumenPolygon.length < 3}
                          active={Boolean(viewFocusBox)}
                          onClick={toggleZoomRoi}
                          side="left"
                          tone="sky"
                        />
                      </div>
                    </div>

                    <div className="pointer-events-none absolute top-2 bottom-2 right-2 z-[140] flex flex-col items-center justify-center gap-1.5 sm:top-3 sm:bottom-3 sm:right-3">
                      <div className="workbench-tool-rail pointer-events-auto max-h-full rounded-lg border border-white/10 bg-black/70 p-1 shadow-2xl shadow-black/40 backdrop-blur-md">
                        <ToolRailSectionTitle>{zh ? '胃腔' : 'Lumen'}</ToolRailSectionTitle>
                        <ToolRailButton
                          icon={lumenBusy ? <Loader2 size={15} className="animate-spin" /> : <ScanSearch size={15} />}
                          label={zh ? '检测胃腔' : 'Detect'}
                          hint={zh ? '须含胃壁与肿块' : 'Cover wall and mass'}
                          disabled={lumenBusy || !patient}
                          onClick={() => {
                            prepareLumenDetection();
                            void detectLumen();
                          }}
                          side="right"
                          tone="fuchsia"
                        />
                        <ToolRailButton
                          icon={<Pencil size={15} />}
                          label={lumenEditMode ? (zh ? '完成调整' : 'Done') : (zh ? '调整框' : 'Edit box')}
                          hint={zh ? '拖角点/移动/重画' : 'Drag corners / move'}
                          active={lumenEditMode}
                          onClick={toggleLumenBoxEdit}
                          side="right"
                          tone="fuchsia"
                        />
                        <ToolRailButton
                          icon={lumenSamBusy ? <Loader2 size={15} className="animate-spin" /> : <Droplets size={15} />}
                          label={zh ? '出轮廓' : 'Contour'}
                          hint={zh ? '按当前框生成轮廓' : 'Segment from box'}
                          disabled={!lumenBox || lumenSamBusy}
                          onClick={() => void segmentLumenWithSam31()}
                          side="right"
                          tone="fuchsia"
                        />
                        <ToolRailButton
                          icon={nnInteractiveBusy && nnInteractiveTarget === 'lumen' ? <Loader2 size={15} className="animate-spin" /> : <CirclePlus size={15} />}
                          label={zh ? '精修胃腔' : 'Refine'}
                          hint={zh ? '正/负点交互精修' : 'Pos/neg point refine'}
                          disabled={(!lumenBox && lumenPolygon.length < 3) || nnInteractiveBusy}
                          active={nnInteractiveMode && nnInteractiveTarget === 'lumen'}
                          onClick={() => {
                            setActiveSamPromptLabel('positive');
                            activateNnInteractive('lumen');
                          }}
                          side="right"
                          tone="lime"
                        />
                        <ToolRailButton
                          icon={saving ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />}
                          label={zh ? '保存编辑' : 'Save edit'}
                          hint={zh ? '保存本帧与视频轮廓' : 'Save frame/video masks'}
                          disabled={saving || points.length < 3}
                          onClick={() => void handleSave()}
                          side="right"
                          tone="emerald"
                        />
                        <ToolRailDivider />
                        <ToolRailSectionTitle>{zh ? '分析' : 'Analyze'}</ToolRailSectionTitle>
                        <ToolRailButton
                          icon={<Brain size={15} />}
                          label={zh ? '边界分析' : 'Boundary'}
                          hint={zh ? '可解释边界证据' : 'Explainable boundary'}
                          disabled={points.length < 3}
                          onClick={openExplainableAnalysis}
                          side="right"
                          tone="emerald"
                        />
                        <ToolRailButton
                          icon={<Layers size={15} />}
                          label={zh ? '壁层层次' : 'Wall layers'}
                          hint={zh ? '五层与接触带' : 'Five layers / contact'}
                          disabled={points.length < 3 && !layerResult}
                          active={wallAnalysisOpen}
                          onClick={() => {
                            const next = !wallAnalysisOpen;
                            freezeCurrentFrame();
                            setWallAnalysisOpen(next);
                            setMessage(
                              next
                                ? (zh ? '已冻结当前帧，正在打开胃壁层次和接触通道辅助' : 'Current frame frozen; opening wall-layer and contact assistance')
                                : (zh ? '已收起胃壁突破辅助' : 'Wall breakthrough assistance collapsed'),
                            );
                          }}
                          side="right"
                          tone="orange"
                        />
                        <ToolRailDivider />
                        <ToolRailButton
                          icon={<PanelTop size={15} />}
                          label={zh ? '隐藏工具' : 'Hide'}
                          hint={zh ? '只保留中间影像' : 'Keep image only'}
                          onClick={() => setSimpleToolsOpen(false)}
                          side="right"
                          tone="slate"
                        />
                      </div>
                    </div>
                  </>
                ) : null}
                {simpleVideoMode && !simpleToolsOpen ? (
                  <div className="pointer-events-none absolute top-2 bottom-2 right-2 z-[140] flex items-center sm:top-3 sm:bottom-3 sm:right-5">
                    <div className="pointer-events-auto">
                      <div className="rounded-lg border border-white/10 bg-black/70 p-1 backdrop-blur-md">
                        <ToolRailButton
                          icon={<PanelTop size={16} />}
                          label={zh ? '显示工具' : 'Show tools'}
                          hint={zh ? '打开左右工具栏' : 'Open side tool rails'}
                          onClick={() => setSimpleToolsOpen(true)}
                          side="right"
                          tone="slate"
                        />
                      </div>
                    </div>
                  </div>
                ) : null}
                {mediaMode === 'video' && (
                  <video
                    ref={videoRef}
                    className={simpleVideoMode ? 'absolute inset-0 z-0 h-full w-full bg-black object-contain' : 'hidden'}
                    muted
                    playsInline
                    preload="auto"
                    crossOrigin="anonymous"
                  />
                )}
                <canvas
                  ref={canvasRef}
                  className="relative z-10 h-full w-full touch-none"
                  style={{ cursor: magnifierOn ? 'none' : dragIndex !== null ? 'grabbing' : simpleEditMode ? 'grab' : mode === 'soft' || mode === 'hard' ? 'grab' : 'crosshair' }}
                  onPointerDown={onPointerDown}
                  onPointerMove={onPointerMove}
                  onPointerUp={onPointerUp}
                  onPointerCancel={onPointerCancel}
                  onDoubleClick={(e) => {
                    if (simpleVideoMode) return;
                    const imgPt = canvasToImage(e);
                    if (!imgPt) return;
                    const edgeThr = hitThreshold() * 3;
                    const lesionHit = polygonHit(imgPt, pointsRef.current, edgeThr);
                    const wallHit = polygonHit(imgPt, wallPointsRef.current, edgeThr);
                    if (!lesionHit && !wallHit) return;
                    const preferWall = wallHit && (
                      !lesionHit
                      || minDist2ToPolygon(imgPt, wallPointsRef.current) <= minDist2ToPolygon(imgPt, pointsRef.current)
                    );
                    const layer: ContourLayer = preferWall ? 'wall' : 'lesion';
                    freezeCurrentFrame();
                    stopInteractivePrompt();
                    setSimplePromptMode('box');
                    setLumenEditMode(false);
                    setActiveLayer(layer);
                    setMode('soft');
                    setMessage(
                      zh
                        ? (layer === 'wall' ? '已进入胃壁编辑：拖动手柄微调' : '已进入病灶编辑：拖动手柄微调')
                        : (layer === 'wall' ? 'Wall edit mode: drag handles' : 'Lesion edit mode: drag handles'),
                    );
                  }}
                />
                {(samBusy || propagateBusy || precomputeBusy || unifiedAgentBusy || workflowBusy || (mediaMode === 'image' && !imgLoaded)) && (
                  <div className="pointer-events-none absolute inset-0 z-[170] flex flex-col items-center justify-center bg-black/45 px-4">
                    <Loader2 className="animate-spin text-cyan-300" size={34} />
                    {(taskProgress || precomputeProgress || workflowStepLabel || unifiedAgentBusy) ? (
                      <div className="mt-4 w-[min(40rem,100%)] rounded-2xl border border-white/20 bg-slate-950/95 px-6 py-5 text-center shadow-2xl backdrop-blur">
                        <div className="text-sm font-semibold text-slate-100">
                          {taskProgress?.label
                            || (precomputeBusy
                              ? (zh ? '整段视频跟踪' : 'Full-video tracking')
                              : unifiedAgentBusy
                                ? (zh ? '辅助意见分析' : 'Assisted analysis')
                                : (workflowStepLabel || (zh ? '处理中' : 'Working')))}
                        </div>
                        <div className="mt-2 text-xs leading-5 text-slate-300">
                          {taskProgress?.detail
                            || precomputeProgress
                            || workflowStepLabel
                            || (zh ? '请稍候，不要重复点击' : 'Please wait; do not click repeatedly')}
                        </div>
                        <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/10">
                          <div
                            className={`h-full rounded-full bg-sky-400/80 ${
                              taskProgress ? 'transition-[width] duration-500 ease-out' : 'task-progress-indeterminate'
                            }`}
                            style={taskProgress ? {
                              width: `${Math.max(
                                12,
                                Math.min(
                                  96,
                                  Math.round((taskProgress.step / Math.max(1, taskProgress.totalSteps)) * 100),
                                ),
                              )}%`,
                            } : undefined}
                          />
                        </div>
                        <div className="mt-2 flex items-center justify-center gap-4 font-mono text-[11px] text-slate-400">
                          {taskProgress ? (
                            <span>{zh ? `步骤 ${taskProgress.step}/${taskProgress.totalSteps}` : `Step ${taskProgress.step}/${taskProgress.totalSteps}`}</span>
                          ) : null}
                          <span>{zh ? `已用时 ${taskElapsedSec}s` : `Elapsed ${taskElapsedSec}s`}</span>
                        </div>
                      </div>
                    ) : null}
                  </div>
                )}
                {taskProgress && !(samBusy || propagateBusy || precomputeBusy || unifiedAgentBusy || workflowBusy) ? (
                  <div className="pointer-events-none absolute inset-x-0 bottom-3 z-[175] flex justify-center px-4">
                    <div className="w-[min(44rem,100%)] rounded-xl border border-white/20 bg-slate-950/95 px-4 py-3 shadow-xl backdrop-blur">
                      <div className="flex items-center justify-between gap-2 text-xs text-slate-200">
                        <span className="font-semibold">{taskProgress.label}</span>
                        <span className="font-mono text-slate-400">
                          {taskProgress.step}/{taskProgress.totalSteps} · {taskElapsedSec}s
                        </span>
                      </div>
                      <div className="mt-1 text-[11px] leading-4 text-slate-400">{taskProgress.detail}</div>
                      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/10">
                        <div
                          className="h-full rounded-full bg-sky-400/80 transition-[width] duration-500 ease-out"
                          style={{ width: `${Math.round((taskProgress.step / Math.max(1, taskProgress.totalSteps)) * 100)}%` }}
                        />
                      </div>
                    </div>
                  </div>
                ) : null}
                {(lumenEditMode || (!simpleVideoMode && (nnInteractiveMode || (mode === 'sam' && simplePromptMode !== 'box')))) && (
                  <div className={`pointer-events-none absolute top-3 z-20 rounded-lg border border-emerald-300/30 bg-slate-950/95 px-2.5 py-2 text-[10px] text-slate-200 shadow-lg ${simpleVideoMode ? 'left-[8.25rem] sm:left-[9rem]' : 'left-3'}`}>
                    <div className={`font-semibold ${lumenEditMode ? 'text-amber-100' : 'text-emerald-100'}`}>
                      {lumenEditMode
                        ? (zh ? '胃腔框编辑' : 'Lumen box edit')
                        : nnInteractiveMode
                          ? `${nnInteractiveTarget === 'lumen' ? (zh ? '胃腔' : 'Lumen') : (zh ? '病灶' : 'Lesion')} ${promptModeText(simplePromptMode, zh)}`
                          : `${zh ? '本地点提示' : 'Local prompt'} ${promptModeText(simplePromptMode, zh)}`}
                    </div>
                    {lumenEditMode ? (
                      <div className="mt-1 text-amber-200">
                        {zh ? '可连续拖调：角点缩放 / 框内移动 / 框外重画；点「完成调整」才退出' : 'Keep adjusting: corners / move / redraw outside; tap Done to exit'}
                      </div>
                    ) : (
                      <>
                        <div className="mt-1 flex items-center gap-2">
                          <span className="inline-flex items-center gap-0.5 text-emerald-300"><CirclePlus size={11} />{zh ? '正点' : 'Positive'}</span>
                          <span className="inline-flex items-center gap-0.5 text-rose-300"><CircleMinus size={11} />{zh ? '负点' : 'Negative'}</span>
                          <span className="text-slate-400">
                            {nnInteractiveMode ? nnInteractiveClicks.length : samClicks.length} {zh ? '点' : 'points'}
                            {promptStrokes.length ? `, ${promptStrokes.length} ${zh ? '笔' : 'strokes'}` : ''}
                          </span>
                        </div>
                        {nnInteractiveBusy ? (
                          <div className="mt-1 text-amber-200">{zh ? '边界更新中…' : 'Updating boundary…'}</div>
                        ) : null}
                      </>
                    )}
                  </div>
                )}
                {lumenLesionGeometry.available && (!simpleVideoMode || lumenLesionGeometry.relation === 'separated') ? (
                  <div className={`pointer-events-none absolute top-3 z-20 w-[min(265px,calc(100%-1.5rem))] rounded-lg border ${
                    lumenLesionGeometry.relation === 'separated'
                      ? 'border-rose-300/50 bg-rose-950/85'
                      : 'border-fuchsia-300/25 bg-slate-950/80'
                  } px-2.5 py-2 text-[10px] text-slate-200 shadow-lg ${simpleVideoMode ? 'right-[7rem] sm:right-[7.5rem]' : 'right-3'}`}>
                    <div className="flex items-center justify-between gap-2">
                      <span className={`font-semibold ${lumenLesionGeometry.relation === 'separated' ? 'text-rose-100' : 'text-fuchsia-100'}`}>
                        {zh ? '胃腔-病灶几何关系' : 'Lumen-lesion geometry'}
                      </span>
                      <span className="rounded-full border border-white/10 px-1.5 py-0.5 text-[8px] uppercase text-slate-400">
                        {lumenLesionGeometry.quality}
                      </span>
                    </div>
                    <div className={`mt-1 text-[9px] leading-relaxed ${lumenLesionGeometry.relation === 'separated' ? 'text-rose-100' : 'text-slate-400'}`}>
                      {geometryRelationText(lumenLesionGeometry, zh)}
                    </div>
                    <div className="mt-2 grid grid-cols-3 gap-1.5">
                      <div className="rounded border border-white/10 bg-white/[0.04] px-1.5 py-1">
                        <div className="text-[8px] text-slate-500">{zh ? '间距' : 'Gap'}</div>
                        <div className="font-mono text-fuchsia-100">
                          {lumenLesionGeometry.distancePx != null ? `${Math.round(lumenLesionGeometry.distancePx)} px` : '—'}
                        </div>
                      </div>
                      <div className="rounded border border-white/10 bg-white/[0.04] px-1.5 py-1">
                        <div className="text-[8px] text-slate-500">{zh ? '平滑度' : 'Smooth'}</div>
                        <div className="font-mono text-lime-100">
                          {lumenLesionGeometry.smoothnessIndex != null
                            ? `${Math.round(lumenLesionGeometry.smoothnessIndex * 100)}%`
                            : '—'}
                        </div>
                      </div>
                      <div className="rounded border border-white/10 bg-white/[0.04] px-1.5 py-1">
                        <div className="text-[8px] text-slate-500">{zh ? '向外扩张' : 'Outward'}</div>
                        <div className="font-mono text-lime-100">
                          {lumenLesionGeometry.outwardExpansionRatio != null
                            ? `${lumenLesionGeometry.outwardExpansionRatio >= 0 ? '+' : ''}${Math.round(lumenLesionGeometry.outwardExpansionRatio * 100)}%`
                            : '—'}
                        </div>
                      </div>
                    </div>
                    <div className="mt-1.5 text-[8px] text-slate-500">
                      {geometryQualityText(lumenLesionGeometry, zh)}
                      {zh ? '；仅为当前帧几何辅助' : '; current-frame geometry proxy only'}
                    </div>
                    <div className="mt-2 rounded border border-white/10 bg-white/[0.03] px-2 py-1.5 text-[9px] leading-relaxed text-slate-300">
                      {zh
                        ? '编辑逻辑：病灶是分割目标，胃腔是定位和排除参照。两条轮廓独立编辑；胃腔框改变会清空旧胃腔轮廓，重叠只提示复核，不直接等于侵犯。'
                        : 'Editing logic: the lesion is the segmentation target; the lumen is a localization and exclusion reference. Edit them independently. Changing the lumen box clears its old contour, and overlap only triggers review.'}
                    </div>
                  </div>
                ) : null}
              </div>
              {!wallAnalysisOpen && layerResult?.ok ? (
                <button
                  type="button"
                  onClick={() => setWallAnalysisOpen(true)}
                  className="absolute bottom-3 right-3 z-30 max-w-[min(360px,calc(100%-1.5rem))] rounded-xl border border-emerald-300/35 bg-slate-950/92 px-3 py-2 text-left shadow-2xl shadow-black/50 backdrop-blur-md hover:border-emerald-300/55"
                >
                  <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-wide text-emerald-100">
                    <Layers size={13} />
                    {zh ? '胃壁五层（主看点，已收起）' : 'Wall five-layer (primary, collapsed)'}
                  </div>
                  <div className="mt-1 text-[11px] font-semibold text-slate-100">
                    {!layerResult.inContact
                      ? (zh ? '未形成稳定接触弧，层次待复核' : 'No stable contact arc; layer pending review')
                      : layerResult.pixelBased && layerResult.layer?.label
                        ? `${zh ? '最深累及倾向' : 'Deepest involvement'}: ${layerResult.layer.label}${layerResult.layer.tHint ? ` (${layerResult.layer.tHint})` : ''}`
                        : (zh ? '几何代理层次，需结合回声与多切面' : 'Geometry-proxy layer; confirm with echo and multiplane')}
                  </div>
                  <div className="mt-1 text-[9px] leading-relaxed text-slate-400">
                    {zh
                      ? '关闭详细面板后仍保留层界叠层与本摘要；点击可重新打开五层分析。'
                      : 'Layer overlay and this summary remain after collapse; click to reopen five-layer analysis.'}
                  </div>
                </button>
              ) : null}
              <div className={`absolute inset-y-3 right-3 z-30 w-[min(390px,calc(100%-1.5rem))] max-w-[calc(100%-1.5rem)] flex-col overflow-hidden rounded-xl border border-emerald-300/30 bg-slate-950/95 shadow-2xl shadow-black/60 backdrop-blur-md ${wallAnalysisOpen ? 'flex' : 'hidden'}`}>
                <div className="flex shrink-0 items-center justify-between border-b border-white/10 px-3 py-2">
                  <div className="flex items-center gap-2 text-xs font-semibold text-emerald-100">
                    <Layers size={14} />
                    {zh ? '胃壁五层 / 突破分析（主看点）' : 'Wall five-layer / breakthrough (primary)'}
                  </div>
                  <button
                    type="button"
                    onClick={() => setWallAnalysisOpen(false)}
                    className="rounded-md border border-white/10 px-2 py-1 text-[10px] text-slate-300 hover:bg-white/10"
                  >
                    {zh ? '收起' : 'Collapse'}
                  </button>
                </div>
                <div className="min-h-0 flex-1 overflow-y-auto p-2 custom-scrollbar">
                  {mediaMode === 'video' && keyCandidates.length ? (
                    <div className="mb-2 rounded-lg border border-amber-300/25 bg-amber-500/[0.06] p-2">
                      <div className="mb-1 flex items-center justify-between gap-2 px-0.5">
                        <div className="flex items-center gap-1 text-[10px] font-semibold text-amber-100">
                          <Film size={12} />
                          {zh ? '跟踪关键帧' : 'Tracked key frames'}
                        </div>
                        <span className="text-[9px] text-slate-500">
                          {zh ? '点击跳转；建议帧仅辅助' : 'Click to seek; hints only'}
                        </span>
                      </div>
                      <div className="flex gap-1.5 overflow-x-auto pb-0.5">
                        {keyCandidates.slice(0, 6).map((candidate, index) => (
                          <button
                            key={`track-kf-${candidate.timestamp_sec}-${candidate.frame_index ?? index}`}
                            type="button"
                            onClick={() => {
                              const video = videoRef.current;
                              if (!video) return;
                              video.pause();
                              video.currentTime = candidate.timestamp_sec;
                              setVideoTime(candidate.timestamp_sec);
                              syncFrameFromVideo({ force: true });
                              redrawRef.current();
                              setMessage(
                                zh
                                  ? `已跳到跟踪关键帧 ${index + 1}，t=${candidate.timestamp_sec.toFixed(2)}s`
                                  : `Jumped to tracked key frame ${index + 1}, t=${candidate.timestamp_sec.toFixed(2)}s`,
                              );
                            }}
                            className="group shrink-0 overflow-hidden rounded-md border border-white/15 bg-black/40 text-left hover:border-amber-300/60"
                            title={zh
                              ? `跳到 t=${candidate.timestamp_sec.toFixed(2)}s（score ${Number(candidate.score || 0).toFixed(2)}）`
                              : `Seek t=${candidate.timestamp_sec.toFixed(2)}s (score ${Number(candidate.score || 0).toFixed(2)})`}
                          >
                            {candidate.thumb_url ? (
                              // eslint-disable-next-line @next/next/no-img-element
                              <img
                                src={candidate.thumb_url}
                                alt={`keyframe ${index + 1}`}
                                className="h-14 w-20 object-cover opacity-90 transition group-hover:opacity-100"
                              />
                            ) : (
                              <div className="flex h-14 w-20 items-center justify-center text-[9px] text-slate-500">
                                t={candidate.timestamp_sec.toFixed(1)}s
                              </div>
                            )}
                            <div className="flex items-center justify-between gap-1 bg-black/50 px-1 py-0.5 text-[9px] font-mono text-amber-100">
                              <span>#{index + 1}</span>
                              <span>{candidate.timestamp_sec.toFixed(1)}s</span>
                            </div>
                          </button>
                        ))}
                      </div>
                    </div>
                  ) : null}
                  <div className="mb-2 flex flex-wrap gap-2 px-1 text-[9px] text-slate-400">
                    <span className="inline-flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-sm bg-cyan-400" />{zh ? '青, 病灶' : 'Cyan lesion'}</span>
                    <span className="inline-flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-sm bg-fuchsia-400" />{zh ? '紫, 胃腔' : 'Fuchsia lumen'}</span>
                    <span className="inline-flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-sm bg-orange-400" />{zh ? '橙, 胃壁' : 'Orange wall'}</span>
                  </div>
                  <WallFeatureAnalysisCard
                    zh={zh}
                    lesionPolygon={points}
                    wallPolygon={wallPoints}
                    frameSize={frameSize}
                    frameDataUrl={frameDataUrl}
                    pick={layerPick}
                    lumenPrefer={lumenPrefer}
                    paused={dragIndex !== null || samBusy || propagateBusy || lumenBusy || lumenSamBusy}
                    onResult={(r) => {
                      setLayerResult(r);
                      onImagingAssist?.({
                        layerResult: r,
                        lesionPolygon: pointsRef.current,
                        wallPolygon: wallPointsRef.current,
                        frameSize,
                        lumenBBox: lumenBoxRef.current,
                        lumenPolygon: lumenPolygon.length >= 3 ? lumenPolygon : undefined,
                      });
                    }}
                  />
                  <p className="mt-2 px-1 text-[9px] leading-relaxed text-slate-500">
                    {zh
                      ? '合理进入：病灶+胃腔到位后自动分析。ContactGeom / LayerBridge 结果写入老板壁层模板报告，不作病理层次结论。Alt+点击设取样点。'
                      : 'Reasonable entry: auto-analyze after lesion+lumen. ContactGeom / LayerBridge feeds the boss wall-layer template; not pathology. Alt-click sets sample point.'}
                  </p>
                </div>
              </div>
            </div>
            {simpleVideoMode && (
              <div className="shrink-0 border-t border-white/10 bg-black px-3 py-2">
                <div className="flex items-center gap-2">
                  <span className="w-11 shrink-0 text-right font-mono text-[10px] text-slate-500">
                    <span ref={(node) => { videoTimeLabelRefs.current[1] = node; }}>{videoTime.toFixed(2)}</span>
                  </span>
                  <input
                    ref={(node) => { videoProgressRefs.current[1] = node; }}
                    type="range"
                    min={0}
                    max={Math.max(videoDuration, 0.01)}
                    step={0.01}
                    defaultValue={videoTime}
                    disabled={!videoUrl}
                    onPointerDown={beginVideoScrub}
                    onPointerUp={endVideoScrub}
                    onPointerCancel={endVideoScrub}
                    onChange={(event) => {
                      onVideoProgressChange(Number(event.target.value));
                    }}
                    className="video-progress min-w-0 flex-1"
                    aria-label={zh ? '视频进度' : 'Video progress'}
                  />
                  <span className="w-11 shrink-0 font-mono text-[10px] text-slate-500">
                    {videoDuration.toFixed(2)}
                  </span>
                </div>
                <div className="mt-1.5 flex items-center justify-between gap-2">
                  <span className="min-w-0 truncate text-[10px] text-slate-500">
                    {videos.find((video) => video.url === videoUrl)?.filename || (zh ? '病例视频' : 'Case video')}
                  </span>
                  <div className="flex shrink-0 items-center gap-1">
                    {simpleVideoMode && keyCandidates.length > 0 ? (
                      <div className="mr-1 flex max-w-[42%] items-center gap-1 overflow-x-auto">
                        <span className="shrink-0 text-[9px] text-slate-500" title={zh ? '算法建议帧，仅供参考；请医生 scrub 自选关键帧' : 'Algorithm hints only; scrub to pick your own key frames'}>
                          {zh ? '建议帧' : 'Hints'}
                        </span>
                        {keyCandidates.slice(0, 5).map((candidate) => (
                          <button
                            key={`${candidate.timestamp_sec}-${candidate.frame_index ?? 'x'}`}
                            type="button"
                            onClick={() => {
                              const video = videoRef.current;
                              if (!video) return;
                              video.pause();
                              video.currentTime = candidate.timestamp_sec;
                              setVideoTime(candidate.timestamp_sec);
                              syncFrameFromVideo({ force: true });
                              redrawRef.current();
                              setMessage(
                                zh
                                  ? `已跳到算法建议帧 t=${candidate.timestamp_sec.toFixed(2)}s；仍可自行 scrub 选帧`
                                  : `Jumped to suggested frame t=${candidate.timestamp_sec.toFixed(2)}s; you may still scrub freely`,
                              );
                            }}
                            className="shrink-0 rounded border border-amber-300/30 bg-amber-500/10 px-1.5 py-0.5 font-mono text-[9px] text-amber-100 hover:bg-amber-500/25"
                          >
                            {candidate.timestamp_sec.toFixed(1)}s
                          </button>
                        ))}
                      </div>
                    ) : (
                      <span className="mr-1 hidden text-[9px] text-slate-500 sm:inline">
                        {zh ? '关键帧以医生自选为主' : 'Doctor-selected frames preferred'}
                      </span>
                    )}
                    <button
                      type="button"
                      disabled={!videoUrl}
                      onClick={() => {
                        const video = videoRef.current;
                        if (!video) return;
                        video.pause();
                        const nextTime = Math.max(0, video.currentTime - 1 / 30);
                        video.currentTime = nextTime;
                        setVideoTime(nextTime);
                        syncFrameFromVideo({ force: true });
                        redrawRef.current();
                      }}
                      className="rounded-md p-1.5 text-slate-400 hover:bg-white/10 hover:text-white disabled:opacity-30"
                      title={zh ? '后退一帧' : 'Previous frame'}
                    >
                      <SkipBack size={13} />
                    </button>
                    <button
                      type="button"
                      disabled={!videoUrl}
                      onClick={() => {
                        const video = videoRef.current;
                        if (!video) return;
                        if (video.paused) void video.play();
                        else video.pause();
                      }}
                      className="flex h-7 min-w-12 items-center justify-center gap-1 rounded-md border border-white/20 bg-white/10 px-2 text-[10px] text-white hover:bg-white/15 disabled:opacity-30"
                    >
                      {isPlaying ? <Pause size={12} /> : <Play size={12} />}
                      {isPlaying ? (zh ? '暂停' : 'Pause') : (zh ? '播放' : 'Play')}
                    </button>
                    <button
                      type="button"
                      disabled={!videoUrl}
                      onClick={() => {
                        const video = videoRef.current;
                        if (!video) return;
                        video.pause();
                        const nextTime = Math.min(video.duration || videoTime, video.currentTime + 1 / 30);
                        video.currentTime = nextTime;
                        setVideoTime(nextTime);
                        syncFrameFromVideo({ force: true });
                        redrawRef.current();
                      }}
                      className="rounded-md p-1.5 text-slate-400 hover:bg-white/10 hover:text-white disabled:opacity-30"
                      title={zh ? '前进一帧' : 'Next frame'}
                    >
                      <SkipForward size={13} />
                    </button>
                    <label className="ml-1 flex items-center gap-1 rounded-md border border-white/10 px-2 py-1 text-[10px] text-slate-400">
                      <span>{zh ? '速度' : 'Speed'}</span>
                      <select
                        value={String(videoPlaybackRate)}
                        onChange={(event) => setVideoPlaybackRate(Number(event.target.value))}
                        className="bg-transparent text-slate-200 outline-none"
                        aria-label={zh ? '视频倍速' : 'Video playback speed'}
                      >
                        {VIDEO_PLAYBACK_RATES.map((rate) => (
                          <option key={rate} value={rate}>{rate}×</option>
                        ))}
                      </select>
                    </label>
                  </div>
                </div>
              </div>
            )}
            <div className="workbench-toolbar flex flex-wrap items-center gap-2 border-t border-white/10 px-4 py-3">
              {!simpleVideoMode && (
                <button
                  type="button"
                  disabled={saving || points.length < 3}
                  onClick={() => void handleSave()}
                  className="flex items-center gap-1.5 rounded-lg border border-emerald-400/40 bg-emerald-500/15 px-3 py-1.5 text-[11px] font-semibold text-emerald-100 disabled:opacity-40"
                >
                  {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
                  {zh ? '保存覆盖' : 'Save override'}
                </button>
              )}
              {!simpleVideoMode && (
                <button
                  type="button"
                  disabled={samBusy || points.length < 3}
                  onClick={() => {
                    const c = polygonCentroid(points);
                    const box = bboxFromPolygon(points);
                    if (c && box) {
                      freezeCurrentFrame();
                      void runSamAtPoint(c, { source: 'sam', box, keepEditing: true, stayInSam: true, llmReport: true });
                    }
                  }}
                  className="flex items-center gap-1.5 rounded-lg border border-white/15 bg-white/[0.06] px-3 py-1.5 text-[11px] font-semibold text-slate-200 hover:bg-white/10 disabled:opacity-40"
                >
                  {samBusy ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
                  {zh ? '生成系统证据' : 'Generate system evidence'}
                </button>
              )}
              {simpleVideoMode && points.length >= 3 && (
                <button
                  type="button"
                  disabled={saving}
                  onClick={() => void handleSave()}
                  className="flex items-center gap-1.5 rounded-lg border border-white/15 bg-white/[0.06] px-3 py-1.5 text-[11px] font-semibold text-slate-200 hover:bg-white/10 disabled:opacity-40"
                >
                  {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
                  {zh ? '保存完整遮罩' : 'Save complete masks'}
                </button>
              )}
              <button
                type="button"
                onClick={toggleHistoryPanel}
                className={`flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[11px] font-semibold ${
                  historyOpen
                    ? 'border-sky-300/60 bg-sky-500/20 text-sky-100'
                    : 'border-white/15 bg-white/[0.04] text-slate-300 hover:bg-white/10'
                }`}
                title={zh ? '默认关闭，按需查看并恢复完整遮罩版本' : 'Closed by default; open to inspect and restore complete mask versions'}
              >
                <History size={13} />
                {zh ? '历史记录' : 'History'}{historyOpen && maskHistory.length ? ` (${maskHistory.length})` : ''}
              </button>
              {!simpleVideoMode && (
                <>
                  <button
                    type="button"
                    disabled={saving}
                    onClick={() => void handleClear()}
                    className="flex items-center gap-1.5 rounded-lg border border-white/15 px-3 py-1.5 text-[11px] text-slate-300 hover:bg-white/5"
                  >
                    <Trash2 size={13} />
                    {zh ? '清除' : 'Clear'}
                  </button>
                  <button
                    type="button"
                    disabled={lumenSaving || (!lumenBox && !lumenOverride)}
                    onClick={() => void handleClearLumen()}
                    className="flex items-center gap-1.5 rounded-lg border border-white/15 px-3 py-1.5 text-[11px] text-slate-300 hover:bg-white/5 disabled:opacity-40"
                  >
                    <Trash2 size={13} />
                    {zh ? '清除胃腔' : 'Clear lumen'}
                  </button>
                </>
              )}
              {!inline && (
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  className="flex items-center gap-1.5 rounded-lg border border-cyan-400/30 bg-cyan-500/10 px-3 py-1.5 text-[11px] text-cyan-100"
                >
                  <Check size={13} />
                  {zh ? '完成并关闭' : 'Done'}
                </button>
              )}
              {simpleVideoMode && (
                <div className="order-last flex basis-full items-center gap-1.5 border-t border-white/5 pt-1.5 text-[9px] text-slate-400 sm:order-none sm:ml-auto sm:basis-auto sm:border-t-0 sm:pt-0">
                  <span className={`inline-flex items-center gap-1 rounded border px-1.5 py-1 ${lesionReady ? 'border-cyan-300/30 bg-cyan-400/10 text-cyan-100' : 'border-white/10 bg-white/[0.03]'}`}>
                    <ScanLine size={11} />
                    {zh ? (lesionReady ? '病灶已就绪' : '病灶待框选') : (lesionReady ? 'Lesion ready' : 'Lesion prompt needed')}
                  </span>
                  <span className={`inline-flex items-center gap-1 rounded border px-1.5 py-1 ${lumenReady ? 'border-fuchsia-300/30 bg-fuchsia-400/10 text-fuchsia-100' : 'border-white/10 bg-white/[0.03]'}`}>
                    <Droplets size={11} />
                    {zh ? (lumenReady ? '胃腔已就绪' : '胃腔待检测') : (lumenReady ? 'Lumen ready' : 'Lumen prompt needed')}
                  </span>
                  <span className={`inline-flex items-center gap-1 rounded border px-1.5 py-1 ${videoTrackReady ? 'border-violet-300/30 bg-violet-400/10 text-violet-100' : 'border-white/10 bg-white/[0.03]'}`}>
                    <Video size={11} />
                    {zh ? (videoTrackReady ? `视频 ${videoFrameOverrides.length} 帧` : '视频待预计算') : (videoTrackReady ? `Video ${videoFrameOverrides.length} frames` : 'Video not prepared')}
                  </span>
                </div>
              )}
              <div className="ml-auto flex flex-col items-end gap-0.5 text-[10px] text-slate-400">
                <div className="flex items-center gap-2">
                  <ZoomIn size={12} />
                  {simpleVideoMode ? (
                    <span>{zh ? '当前帧系统结果' : 'Current-frame system result'}</span>
                  ) : (
                    <span>
                      {zh ? '当前层' : 'Layer'} {activeLayer === 'wall' ? wallPoints.length : points.length}pt
                      {wallPoints.length >= 3 ? `, ${zh ? '壁' : 'wall'}${wallPoints.length}` : ''}
                    </span>
                  )}
                  {samAvailable === false && (
                    <span className="text-amber-300/90">
                      {zh ? '系统分析服务不可用' : 'Analysis service unavailable'}
                    </span>
                  )}
                </div>
              </div>
            </div>
            {historyOpen && (
              <div className="shrink-0 border-t border-sky-300/20 bg-sky-950/20 px-4 py-2.5">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5 text-[11px] font-semibold text-sky-100">
                    <History size={13} />
                    {zh ? '完整遮罩历史' : 'Complete mask history'}
                  </div>
                  <button
                    type="button"
                    onClick={() => void loadMaskHistory()}
                    disabled={historyBusy}
                    className="rounded border border-white/15 px-2 py-1 text-[10px] text-slate-300 hover:bg-white/10 disabled:opacity-40"
                  >
                    {historyBusy ? (zh ? '读取中' : 'Loading') : (zh ? '刷新' : 'Refresh')}
                  </button>
                </div>
                {historyBusy && !maskHistory.length ? (
                  <div className="py-2 text-[10px] text-slate-400">{zh ? '正在读取历史版本…' : 'Loading saved versions…'}</div>
                ) : maskHistory.length ? (
                  <div className="workbench-scrollless max-h-44 space-y-1.5 overflow-y-auto pr-1">
                    {maskHistory.map((entry) => {
                      const frames = entry.override.video_frames || [];
                      const lastFrame = frames[frames.length - 1];
                      const latestLumenFrame = [...frames].reverse().find(
                        (frame) => frame.lumen_polygon?.length || frame.lumen_bbox,
                      );
                      const historyLumen = entry.lumen_override;
                      const previewing = historyPreviewId === entry.id;
                      return (
                        <div key={entry.id} className="rounded-lg border border-white/10 bg-black/30 px-2.5 py-2">
                          <div className="flex items-start justify-between gap-2">
                            <HistoryMaskThumbnail
                              entry={entry}
                              frameDataUrl={frameDataUrl}
                              mediaMode={mediaMode}
                              videoTime={videoTime}
                              zh={zh}
                            />
                            <div className="min-w-0 flex-1">
                              <div className="truncate text-[10px] text-slate-200">
                                {new Date(entry.saved_at).toLocaleString()}
                              </div>
                              <div className="mt-0.5 text-[9px] text-slate-500">
                                {entry.action || 'manual_save'}
                                {frames.length
                                  ? `, ${frames.length} ${zh ? '帧' : 'frames'}`
                                  : ''}
                              </div>
                            </div>
                            <div className="flex shrink-0 items-center gap-1">
                              <button
                                type="button"
                                disabled={historyBusy}
                                onClick={() => toggleHistoryPreview(entry)}
                                className="rounded border border-white/15 px-2 py-1 text-[10px] text-slate-300 hover:bg-white/10 disabled:opacity-40"
                              >
                                {previewing ? (zh ? '关闭预览' : 'Hide preview') : (zh ? '查看版本' : 'View version')}
                              </button>
                              <button
                                type="button"
                                disabled={saving || historyBusy}
                                onClick={() => void restoreMaskHistory(entry)}
                                className="rounded border border-sky-300/30 bg-sky-400/10 px-2 py-1 text-[10px] text-sky-100 hover:bg-sky-400/20 disabled:opacity-40"
                              >
                                {zh ? '恢复' : 'Restore'}
                              </button>
                              <button
                                type="button"
                                disabled={historyBusy || !accountReaderId}
                                onClick={() => void deleteMaskHistoryEntry(entry)}
                                className="rounded border border-red-400/30 bg-red-500/10 px-2 py-1 text-[10px] text-red-200 hover:bg-red-500/20 disabled:opacity-40"
                                title={accountReaderId ? (zh ? '删除本账号该版本' : 'Delete this version for your account') : (zh ? '请先登录账号' : 'Sign in first')}
                              >
                                {zh ? '删除' : 'Delete'}
                              </button>
                            </div>
                          </div>
                          {previewing && (
                            <div className="mt-2 space-y-1 border-t border-white/10 pt-2 text-[9px] leading-relaxed text-slate-400">
                              <div className="flex flex-wrap gap-x-3 gap-y-0.5">
                                <span>{zh ? `病灶分割 ${entry.override.mask_polygon?.length || 0} 点` : `Lesion mask ${entry.override.mask_polygon?.length || 0} points`}</span>
                                <span>{zh ? `病灶框 ${formatHistoryBox(entry.override.roi_bbox)}` : `Lesion box ${formatHistoryBox(entry.override.roi_bbox)}`}</span>
                                <span>{zh ? `胃壁 ${entry.override.wall_polygon?.length || 0} 点` : `Wall ${entry.override.wall_polygon?.length || 0} points`}</span>
                              </div>
                              <div className="flex flex-wrap gap-x-3 gap-y-0.5">
                                <span>{zh ? `胃腔分割 ${latestLumenFrame?.lumen_polygon?.length || historyLumen?.lumen_polygon?.length || 0} 点` : `Lumen mask ${latestLumenFrame?.lumen_polygon?.length || historyLumen?.lumen_polygon?.length || 0} points`}</span>
                                <span>{zh ? `胃腔框 ${formatHistoryBox(latestLumenFrame?.lumen_bbox || historyLumen?.lumen_bbox)}` : `Lumen box ${formatHistoryBox(latestLumenFrame?.lumen_bbox || historyLumen?.lumen_bbox)}`}</span>
                              </div>
                              {lastFrame && (
                                <div className="rounded border border-white/10 bg-white/[0.03] px-2 py-1">
                                  <div className="text-slate-300">
                                    {zh ? '末帧' : 'Last frame'}: {lastFrame.frame_index ?? '—'} / {lastFrame.timestamp_sec.toFixed(3)}s
                                  </div>
                                  <div className="mt-0.5 flex flex-wrap gap-x-3 gap-y-0.5">
                                    <span>{zh ? `病灶分割 ${lastFrame.mask_polygon?.length || 0} 点` : `Lesion mask ${lastFrame.mask_polygon?.length || 0} points`}</span>
                                    <span>{zh ? `病灶框 ${formatHistoryBox(lastFrame.roi_bbox)}` : `Lesion box ${formatHistoryBox(lastFrame.roi_bbox)}`}</span>
                                    <span>{zh ? `胃腔分割 ${lastFrame.lumen_polygon?.length || 0} 点` : `Lumen mask ${lastFrame.lumen_polygon?.length || 0} points`}</span>
                                    <span>{zh ? `胃腔框 ${formatHistoryBox(lastFrame.lumen_bbox)}` : `Lumen box ${formatHistoryBox(lastFrame.lumen_bbox)}`}</span>
                                  </div>
                                </div>
                              )}
                              <div className="text-slate-500">
                                {zh ? '查看只显示历史预览，不会替换当前可编辑轮廓；确认后点击“恢复”。' : 'View shows a non-destructive history preview without replacing the editable contour; click Restore to apply it.'}
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="py-2 text-[10px] text-slate-500">
                    {zh ? '当前病例暂无已保存历史版本' : 'No saved versions for this case'}
                  </div>
                )}
              </div>
            )}
            {!simpleVideoMode && samReport && (
              <div className="border-t border-white/10 bg-black px-4 py-3 text-[11px] text-slate-200">
                <div className="font-semibold text-slate-100">{zh ? '系统证据（辅助意见）' : 'System evidence (assistive)'}</div>
                <div className="mt-1 flex flex-wrap gap-3 text-[10px] text-slate-400">
                  <span>{zh ? '推荐' : 'Recommendation'}: {samReport.recommended_stage || '—'}</span>
                  <span>{zh ? '置信度' : 'Confidence'}: {samReport.calibrated_confidence != null ? `${Math.round(samReport.calibrated_confidence * 100)}%` : '—'}</span>
                  <span>{zh ? '证据' : 'Evidence'}: {samReport.evidence?.length || 0}</span>
                  <span>{zh ? '相似病例' : 'Similar cases'}: {samReport.similar_cases?.length || 0}</span>
                </div>
                {samReport.summary ? <div className="mt-2 leading-relaxed text-slate-300">{sanitizeSystemCopy(samReport.summary)}</div> : null}
                <div className="mt-2 text-[10px] text-amber-200/80">{zh ? '仅供医生复核，不覆盖最终判断；证据不足时请继续查看连续帧。' : 'For clinician review only; does not overwrite final judgment.'}</div>
              </div>
            )}
            {message && (
              <div className="border-t border-white/5 px-4 py-2 text-[11px] text-slate-300">{message}</div>
            )}
          </div>
        </div>
  ) : null;

  return (
    <>
      {!inline && (<div className="pointer-events-auto absolute bottom-[5.75rem] left-3 z-[110] flex flex-col gap-2">
        <button
          type="button"
          onClick={() => openEditor({ sam: true })}
          className={`flex items-center gap-2 rounded-xl border px-3 py-2 text-[11px] font-semibold shadow-lg backdrop-blur transition hover:-translate-y-0.5 ${
            override
              ? 'border-cyan-400/50 bg-cyan-500/20 text-cyan-100'
              : 'border-white/15 bg-black/70 text-gray-200 hover:border-cyan-400/40'
          }`}
          title={zh ? '打开边界工具' : 'Open boundary tools'}
        >
          <Pencil size={14} />
          <span>{zh ? '边界工具' : 'Boundary tools'}</span>
          {override && (
            <span className="rounded-full bg-cyan-400/20 px-1.5 py-0.5 text-[9px] text-cyan-200">
              {override.mask_polygon.length}pt
            </span>
          )}
        </button>
        <button
          type="button"
          onClick={() => openEditor({ videoSam: true })}
          className="flex items-center gap-2 rounded-xl border border-white/15 bg-black/75 px-3 py-2 text-[11px] font-semibold text-slate-200 shadow-lg backdrop-blur transition hover:-translate-y-0.5 hover:border-white/30"
          title={zh ? '直接打开本例对应视频工具' : 'Open matched patient video tools'}
        >
          <Video size={14} />
          <span>{zh ? '视频工具' : 'Video tools'}</span>
        </button>
      </div>)}
      <ExplainableAnalysis
        patient={patient}
        isOpen={showExplainable}
        onClose={() => setShowExplainable(false)}
        onAnalysisComplete={onExplainableComplete}
        buildFramePayload={buildExplainableFramePayload}
      />
      {typeof document !== 'undefined' && !inline ? createPortal(modal, document.body) : modal}
    </>
  );
}
